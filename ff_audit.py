"""Audit trail: what was filled on each form and the full chain back to Tally.

Two parts:
1. An event log written as things happen (Tally read, mapping approved, build, review cleared, tick,
   fill, SRN). One compact JSON line per event in clients/<Client>/audit/trail.jsonl (kept with the
   client's papers), plus the office-wide activity log activity.jsonl that the Agent queue screen shows.
2. The per-field chain, put together from the records each step already keeps:
     form field  <- MCA inputs workbook (value and its "Source / note")
                 <- Schedule III line or note row (expression in mapping/<form>_map.xlsx)
                 <- Tally ledgers mapped to that head (TB_CY / TB_PY sheets of the built workbook)
                 <- mapping approval (who, when), Tally read (company, when)
     and forward: review tick, fill on the portal (fill logs), submit and SRN (filing queue).
"""
import csv
import io
import json
import re
from datetime import datetime
from pathlib import Path

import openpyxl

import app

ACTIVITY = app.ROOT / "activity.jsonl"
KIND_TEXT = {"tally": "Tally", "mapping": "Mapping", "build": "Schedule III", "review": "Review", "verify": "Review",
             "questions": "Questions", "fill": "Portal", "srn": "Filing", "queue": "Filing", "docs": "Reports", "job": "Agent"}


# ---------------------------------------------------------------- event log

def trail_path(folder):
    d = Path(folder) / "audit"
    d.mkdir(parents=True, exist_ok=True)
    return d / "trail.jsonl"


def event(folder, kind, text, **data):
    """Record one event for a client (and in the office-wide activity log)."""
    rec = {"at": datetime.now().isoformat(timespec="seconds"), "kind": kind, "text": text}
    rec.update({k: v for k, v in data.items() if v not in (None, "")})
    line = json.dumps(rec, ensure_ascii=False, default=str)
    if folder:
        with open(trail_path(folder), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    act = dict(rec, client=Path(folder).name if folder else "")
    with open(ACTIVITY, "a", encoding="utf-8") as f:
        f.write(json.dumps(act, ensure_ascii=False, default=str) + "\n")
    return rec


def events(folder, kinds=None):
    p = Path(folder) / "audit" / "trail.jsonl"
    out = []
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if not kinds or e.get("kind") in kinds:
                out.append(e)
    return out


def activity(limit=60):
    if not ACTIVITY.exists():
        return []
    lines = ACTIVITY.read_text(encoding="utf-8").splitlines()[-limit:]
    out = []
    for line in reversed(lines):
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def last(folder, kind, **match):
    for e in reversed(events(folder, (kind,))):
        if all(e.get(k) == v for k, v in match.items()):
            return e
    return None


# ---------------------------------------------------------------- the chain

def _norm(s):
    from schedule3 import norm
    return norm(s)


class Ledgers:
    """Tally ledgers behind each Schedule III line and head, read from the built workbook's TB sheets."""

    def __init__(self, fs_path):
        self.ok = False
        self.cy, self.py = [], []
        self.div = 1.0
        if not fs_path:
            return
        try:
            wb = openpyxl.load_workbook(fs_path, data_only=True, read_only=True)
        except Exception:  # noqa: BLE001
            return
        if "TB_CY" not in wb.sheetnames:
            return  # a hand-made workbook: no ledger detail
        self.ok = True
        for sheet, dest in (("TB_CY", self.cy), ("TB_PY", self.py)):
            if sheet not in wb.sheetnames:
                continue
            for r in wb[sheet].iter_rows(min_row=2, values_only=True):
                if not r or not r[0]:
                    continue
                r = list(r) + [None] * 19
                dest.append({"ledger": r[0], "group": r[1], "opening": r[3] or 0, "closing": r[6] or 0,
                             "code": r[14] or "", "code_open": r[15] or "", "line": r[16] or "", "line_open": r[17] or ""})
        sys_path_engine()
        from mapping import LINES, HEADS
        self.lines = {_norm(v): k for k, v in LINES.items()}
        self.heads = [(h[0], h[1], _norm(h[3])) for h in HEADS]
        self.line_label = LINES

    def line_of(self, label):
        n = _norm(label)
        if n in self.lines:
            return self.lines[n]
        hits = [c for k, c in self.lines.items() if k.startswith(n) or n.startswith(k)]
        return hits[0] if len(hits) == 1 else None

    def head_of(self, line, row_label):
        n = _norm(row_label)
        hits = [c for c, ln, lab in self.heads if ln == line and (lab == n or lab.startswith(n) or n.startswith(lab))]
        return hits[0] if hits else None

    def for_term(self, term, period):
        """(description, [ledger rows], scope) for one expression term like 'BS:Long-term borrowings'."""
        term = term.strip()
        if re.fullmatch(r"-?\d+(\.\d+)?", term):
            return "Fixed value " + term, [], None
        if "|" in term:
            term = term.split("|", 1)[0]
        if "@" in term:
            term = term.rsplit("@", 1)[0]
        if ":" not in term:
            return term, [], None
        sheet, label = term.split(":", 1)
        sheet = sheet.strip().lower()
        if sheet == "setup":
            return f"Setup value '{label.strip()}'", [], "setup"
        line = code = None
        if sheet in ("bs", "pl"):
            line = self.line_of(label)
            desc = f"{'Balance sheet' if sheet == 'bs' else 'Profit and loss'}: {label.strip()}"
        elif sheet == "notes":
            heading, _, row = label.partition("/")
            line = self.line_of(heading)
            code = self.head_of(line, row) if line else None
            desc = f"Note '{heading.strip()}', row '{row.strip()}'"
        else:
            return term, [], None
        if not self.ok or not line:
            return desc, [], None
        pl = line in ("REV", "OI", "COMC", "PUR", "CHINV", "EMP", "FIN", "DEP", "OEXP", "EXC", "EXO", "TAXC", "TAXD")
        if period == "PY" and not pl:  # previous-year balance sheet = this year's opening balances
            src, key, amt = self.cy, ("code_open" if code else "line_open"), "opening"
        elif period == "PY":
            src, key, amt = self.py, ("code" if code else "line"), "closing"
        else:
            src, key, amt = self.cy, ("code" if code else "line"), "closing"
        want = code or line
        rows = [{"ledger": r["ledger"], "group": r["group"], "amount": r[amt], "code": r["code"]}
                for r in src if r[key] == want and abs(r[amt] or 0) >= 0.005]
        return desc, rows, ("head " + code if code else "line " + line)


def sys_path_engine():
    import sys
    p = str(app.ROOT / "sch3" / "engine")
    if p not in sys.path:
        sys.path.insert(0, p)


def _source(note):
    """(category, picked_from) from the inputs workbook's 'Source / note' text."""
    n = str(note or "")
    m = re.match(r"From FS \((CY|PY)\): (.*)", n)
    if m:
        return "tally", f"Schedule III ({'this year' if m.group(1) == 'CY' else 'last year'}): {m.group(2)}"
    if n.startswith("Last year's AOC-4") or n.startswith("Last year's MGT-7A"):
        return "lastyear", n
    m = re.match(r"Auto \((.*)\)", n)
    if m:
        src = m.group(1)
        if "question" in src.lower() or "answer" in src.lower():
            return "staff", "Staff answer (Questions)"
        if "last year" in src.lower():
            return "lastyear", f"Carried from {src}"
        if "ai" in src.lower().split():
            return "ai", src
        return "auto", src
    if n.startswith("Map:"):
        return "tally", n
    return "staff", "Typed in the inputs workbook"


def _fill_status(folder, slug):
    """{field key: (status, time)} from the latest fill log that touched each field."""
    out = {}
    for p in sorted((Path(folder) / "logs").glob(f"fill_{slug}_*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        at = (d.get("finishedAt") or "")[:19].replace("T", " ")
        for e in d.get("entries") or []:
            st = e.get("status")
            if st in ("filled", "unchanged", "failed", "manual", "skipped-readonly"):
                if st == "unchanged" and e.get("key") in out and out[e["key"]][0] == "filled":
                    continue
                out[e.get("key")] = (st, at, e.get("msg") or "")
    return out


def chain(folder, slug):
    """Every field with a value on the form: [{code, section, label, value, category, picked, built, filled, detail}]."""
    folder = Path(folder)
    inp = app.inputs_path(folder)
    if not inp.exists():
        return {"rows": [], "error": "No MCA inputs workbook yet for this client"}
    from ff_fin import output, load_cfg
    fs = output(folder)
    led = Ledgers(fs)
    cfg = load_cfg(folder)
    approvals = {k.lower(): v for k, v in (cfg.get("approvals") or {}).items()}
    overrides = {str(l[0]).lower(): (l[3] if len(l) > 3 else "") for l in cfg.get("ledgers") or []}
    setup = cfg.get("setup") or {}
    tbm = app.load(folder).get("tb") or {}
    fills = _fill_status(folder, slug)
    wb = openpyxl.load_workbook(inp, data_only=True)
    rows = []
    for name, s, kind, _ in wb["Meta"].iter_rows(min_row=2, values_only=True):
        if s != slug or kind != "form":
            continue
        for r in wb[name].iter_rows(min_row=4, values_only=True):
            r = list(r) + [None] * 10
            code, section, label, value, note, key = r[0], r[1], r[2], r[5], r[7], r[8]
            if not key or value is None or str(value).strip() == "":
                continue
            if hasattr(value, "strftime"):
                value = value.strftime("%d/%m/%Y")
            cat, picked = _source(note)
            built, ledgers, terms = "", [], []
            m = re.match(r"From FS \((CY|PY)\): (.*)", str(note or ""))
            if m:
                period, expr = m.group(1), m.group(2)
                parts = re.split(r"\s+([+-])\s+(?=(?:BS|PL|Notes|Setup)\s*:|\d)", expr, flags=re.I)
                sign = 1
                for part in parts:
                    if part in ("+", "-"):
                        sign = 1 if part == "+" else -1
                        continue
                    desc, lrows, scope = led.for_term(part, period)
                    for x in lrows:
                        a = approvals.get(str(x["ledger"]).lower())
                        ov = overrides.get(str(x["ledger"]).lower())
                        x["approved"] = (f"{a.get('by')} on {a.get('on')}" if a else
                                         f"Client mapping: {ov}" if ov else "Tally group, firm default")
                        x["sign"] = sign
                    if scope and scope.endswith(("LTB", "LTB.UNSRP", "STB", "STB.RP")):
                        k = "Long-term portion of loans from related parties (Rs) - " + ("current year" if period == "CY" else "previous year")
                        if setup.get(k):
                            desc += f"; includes the long-term portion of related-party loans, {float(setup[k]):,.0f}, " \
                                    f"moved between short and long term as entered in Setup"
                    terms.append({"term": part, "desc": desc, "sign": sign, "scope": scope, "ledgers": lrows})
                    ledgers += lrows
                if not led.ok and fs:
                    built = "Hand-made Schedule III (no Tally detail)"
                elif ledgers:
                    built = f"{len(ledgers)} Tally ledger{'s' if len(ledgers) != 1 else ''}"
                elif any("long-term portion" in t["desc"] for t in terms):
                    built = "Setup: long-term portion of related-party loans"
                elif all(t["scope"] is None and t["desc"].startswith("Fixed") for t in terms):
                    built = "Fixed value in the form map"
                else:
                    built = "No ledger with a balance"
            elif cat == "lastyear":
                built = "Carried forward"
            elif cat == "staff":
                built = "Staff"
            fst = fills.get(key)
            rows.append({"code": code, "section": section, "label": label, "value": value, "category": cat,
                         "picked": picked, "built": built, "terms": terms, "key": key,
                         "filled": {"status": fst[0], "at": fst[1], "msg": fst[2]} if fst else None})
    # Forward links: the tick and the filing.
    f = app.load(folder)
    q_job = None
    try:
        import filing_queue
        jobs = [j for j in filing_queue.load()["jobs"] if j["client"] == folder.name and j["slug"] == slug]
        q_job = jobs[-1] if jobs else None
    except Exception:  # noqa: BLE001
        pass
    return {"rows": rows, "fs": fs.name if fs else "", "ledger_detail": led.ok, "tb": tbm,
            "verified": f.get("verified"), "job": q_job,
            "filled_at": max((r["filled"]["at"] for r in rows if r["filled"]), default="")}


def export(folder, slug):
    """Write the trail as an Excel file in the client's audit folder. Returns the path."""
    from mca import form_name
    data = chain(folder, slug)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Fields"
    ws.append(["Code", "Section", "Field", "Filled value", "Picked from", "Built from", "Filled on portal", "Fill time"])
    for r in data["rows"]:
        ws.append([r["code"], r["section"], r["label"], r["value"], r["picked"], r["built"],
                   (r["filled"] or {}).get("status", "not yet"), (r["filled"] or {}).get("at", "")])
    lg = wb.create_sheet("Ledgers")
    lg.append(["Code", "Field", "Period term", "Ledger", "Tally group", "Amount (Dr -ve)", "Head", "Mapping approved"])
    for r in data["rows"]:
        for t in r["terms"]:
            for x in t["ledgers"]:
                lg.append([r["code"], r["label"], t["desc"], x["ledger"], x["group"], x["amount"], x["code"], x["approved"]])
    ev = wb.create_sheet("Events")
    ev.append(["Time", "Step", "What happened", "By"])
    for e in events(folder):
        ev.append([e["at"].replace("T", " "), KIND_TEXT.get(e["kind"], e["kind"]), e["text"], e.get("by", "")])
    for sh, widths in ((ws, (10, 28, 50, 18, 50, 22, 16, 18)), (lg, (10, 40, 40, 36, 26, 16, 12, 26)), (ev, (20, 14, 90, 16))):
        for i, w in enumerate(widths):
            sh.column_dimensions[chr(65 + i)].width = w
        for c in sh[1]:
            c.font = openpyxl.styles.Font(bold=True)
        sh.freeze_panes = "A2"
    p = Path(folder) / "audit" / f"{Path(folder).name} - {form_name(slug)} audit trail {datetime.now():%Y-%m-%d %H%M}.xlsx"
    p.parent.mkdir(parents=True, exist_ok=True)
    wb.save(p)
    event(folder, "docs", f"Audit trail for {form_name(slug)} saved: {p.name}", by="staff")
    return p
