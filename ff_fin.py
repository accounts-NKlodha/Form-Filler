"""Financials for Form Filler: Tally -> mapping -> Schedule III workbook -> review points -> "verified, okay to file".

This wraps the Schedule III engine in sch3/engine (the former Schedule III app on port 8765) so it runs inside
the filing server on 8742. Everything for one client lives in its MCA client folder:

    clients/<Client>/financials/config.json        mapping, approvals, Setup values (the old sch3 clients/<slug>.json)
    clients/<Client>/financials/<FY>/tb_cy.csv      trial balances read from Tally (or uploaded)
    clients/<Client>/financials/<FY>/last_build.json checks, last-year tie-outs, build log
    clients/<Client>/<Client> - Schedule III FY<FY>.xlsx   the built workbook, which the MCA side reads

filing.json gets "schedule3" (which workbook the forms use), "cleared" (review points cleared, by whom)
and "verified" (the tick that lets the client into File on MCA).
"""
import csv
import datetime as dt
import json
import os
import re
import shutil
import sys
import threading
import traceback
from pathlib import Path

import openpyxl

import app
import ff_audit

ENGINE = app.ROOT / "sch3" / "engine"
sys.path.insert(0, str(ENGINE))
import approval  # noqa: E402
import ly_check  # noqa: E402
import masters  # noqa: E402
import pipeline  # noqa: E402
import tally  # noqa: E402
from mapping import HEAD, LINES  # noqa: E402
from setup_fields import FIELDS as SETUP_FIELDS  # noqa: E402

SETTINGS_FILE = app.ROOT / "settings.json"
SETTINGS = {"tally_host": "localhost", "tally_port": 9000}
try:
    SETTINGS.update(json.loads(SETTINGS_FILE.read_text(encoding="utf-8")))
except Exception:  # noqa: BLE001
    pass
DIV_KEY = "Rounding divisor (1 = Rs, 1000 = Rs '000, 100000 = Rs lakhs)"
FV_KEY = "Face value per equity share (Rs)"
FV_ASSUMED = "Assumed Rs 10 - not entered"
BUILDS = {}  # client name -> {"state", "log"}
LOCK = threading.Lock()


# ---------------------------------------------------------------- paths and config

def fy_of(folder):
    """'2025-26' from filing.json fy_end (31/03/2026)."""
    end = str(app.load(folder).get("fy_end") or "31/03/2026")
    y = int(end[-4:])
    return f"{y - 1}-{str(y)[2:]}"


def fy_dates(fy):
    y = int(fy[:4])
    return dt.date(y, 4, 1), dt.date(y + 1, 3, 31)


def fin_dir(folder):
    return Path(folder) / "financials"


def cfg_path(folder):
    return fin_dir(folder) / "config.json"


def work_dir(folder, fy=None):
    d = fin_dir(folder) / (fy or fy_of(folder))
    d.mkdir(parents=True, exist_ok=True)
    return d


def has_cfg(folder):
    return cfg_path(folder).exists()


def load_cfg(folder):
    p = cfg_path(folder)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return new_cfg(folder)


def save_cfg(folder, cfg):
    p = cfg_path(folder)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)


def new_cfg(folder):
    folder = Path(folder)
    f = app.load(folder)
    fy = fy_of(folder)
    y = int(fy[:4])
    return {"client": folder.name, "fy": fy, "tally_company_cy": folder.name, "tally_company_py": folder.name,
            "groups": [], "ledgers": [], "head_labels": {}, "approvals": {}, "review_points": [],
            "setup": {"Company name": folder.name, "CIN": f.get("cin", ""),
                      "Current year - balance sheet date": f"31 March {y + 1}",
                      "Previous year - balance sheet date": f"31 March {y}",
                      DIV_KEY: 1, "Amount label": "Amount in Rs",
                      "Annual return web link (or \"not hosted\")": "Not hosted"},
            "setup_notes": {}}


def out_name(folder):
    return f"{Path(folder).name} - Schedule III FY{fy_of(folder)}.xlsx"


def output(folder):
    """The Schedule III workbook the forms read: the one built here, else whatever find_schedule3 finds."""
    p = Path(folder) / out_name(folder)
    if p.exists():
        return p
    from schedule3 import find_schedule3
    return find_schedule3(folder)


def tb(folder, which):
    p = work_dir(folder) / f"{which}.csv"
    return tally.read_tb(str(p)) if p.exists() else []


def tb_info(folder, which):
    """{'ledgers', 'company', 'at'} for a stored trial balance, or None."""
    p = work_dir(folder) / f"{which}.csv"
    if not p.exists():
        return None
    meta = app.load(folder).get("tb", {}).get(which, {})
    try:
        n = sum(1 for _ in open(p, encoding="utf-8")) - 1
    except OSError:
        n = 0
    return {"ledgers": n, "company": meta.get("company", ""), "at": meta.get("at", ""), "how": meta.get("how", "Tally")}


# ---------------------------------------------------------------- Tally

def tally_companies():
    return tally.companies(SETTINGS["tally_host"], int(SETTINGS["tally_port"]))


def pull(folder, which, company=None, user=""):
    """Read one year's trial balance from Tally into tb_cy.csv / tb_py.csv. Returns the ledger count."""
    folder = Path(folder)
    cfg = load_cfg(folder)
    fy = fy_of(folder)
    key = "tally_company_cy" if which == "tb_cy" else "tally_company_py"
    company = company or cfg.get(key) or folder.name
    yr = fy if which == "tb_cy" else f"{int(fy[:4]) - 1}-{fy[2:4]}"
    frm, to = fy_dates(yr)
    rows = tally.trial_balance(company, frm, to, SETTINGS["tally_host"], int(SETTINGS["tally_port"]))
    if not rows:
        raise ValueError(f"Tally returned no ledgers for '{company}'. Is the company open in Tally for {yr}?")
    tally.write_csv(rows, str(work_dir(folder) / f"{which}.csv"))
    cfg[key] = company
    np_key = "Net profit as per Tally P&L - " + ("current year" if which == "tb_cy" else "previous year")
    cfg["setup"][np_key] = tally.net_profit(rows)
    now = dt.datetime.now()
    cfg.setdefault("setup_notes", {})[np_key] = f"Tally '{company}', {frm:%d-%b-%y} to {to:%d-%b-%y}, pulled {now:%d-%b-%y}"
    save_cfg(folder, cfg)
    _record_tb(folder, which, company, "Tally", len(rows))
    ff_audit.event(folder, "tally", f"{'This' if which == 'tb_cy' else 'Last'} year's trial balance read from Tally "
                   f"'{company}' ({len(rows)} ledgers, {frm:%d-%b-%Y} to {to:%d-%b-%Y})",
                   which=which, company=company, ledgers=len(rows), net_profit=cfg["setup"][np_key], by=user or "agent")
    return len(rows)


def upload_tb(folder, which, filename, data, user=""):
    """An Excel / CSV trial balance for a client without Tally."""
    d = work_dir(folder)
    ext = ".xlsx" if filename.lower().endswith((".xlsx", ".xlsm")) else ".csv"
    tmp = d / f"{which}_upload{ext}"
    tmp.write_bytes(data)
    rows = tally.read_tb(str(tmp))
    tally.write_csv(rows, str(d / f"{which}.csv"))
    cfg = load_cfg(folder)
    np_key = "Net profit as per Tally P&L - " + ("current year" if which == "tb_cy" else "previous year")
    cfg["setup"][np_key] = tally.net_profit(rows)
    cfg.setdefault("setup_notes", {})[np_key] = f"Uploaded file {filename}, {dt.date.today():%d-%b-%y}"
    save_cfg(folder, cfg)
    _record_tb(folder, which, filename, "Upload", len(rows))
    ff_audit.event(folder, "tally", f"{'This' if which == 'tb_cy' else 'Last'} year's trial balance uploaded from {filename} "
                   f"({len(rows)} ledgers)", which=which, file=filename, ledgers=len(rows), by=user or "staff")
    return len(rows)


def _record_tb(folder, which, company, how, n):
    f = app.load(folder)
    tbm = f.get("tb", {})
    tbm[which] = {"company": company, "how": how, "ledgers": n, "at": dt.datetime.now().isoformat(timespec="seconds")}
    app.save(folder, tb=tbm, verified=None)  # new data: the tick has to be given again


# ---------------------------------------------------------------- mapping

def mapping_rows(folder):
    return approval.analyse(tb(folder, "tb_cy"), tb(folder, "tb_py"), load_cfg(folder))


def approve(folder, decisions, user):
    """decisions: {ledger: head code}. Records the approver on each ledger."""
    if not user.strip():
        raise ValueError("Enter your name: every mapping approval is recorded against a person")
    cfg = load_cfg(folder)
    rows = approval.analyse(tb(folder, "tb_cy"), tb(folder, "tb_py"), cfg)
    approval.apply_decisions(cfg, rows, decisions, user.strip(), cfg.get("fy") or fy_of(folder))
    save_cfg(folder, cfg)
    for led, code in decisions.items():
        h = HEAD.get(code)
        ff_audit.event(folder, "mapping", f"Ledger '{led}' mapped to {LINES[h[1]]} - {h[3]}" if h else f"Ledger '{led}' mapped to {code}",
                       ledger=led, code=code, by=user.strip())
    app.save(folder, verified=None)
    return len(decisions)


def head_options():
    return approval.head_options()


# ---------------------------------------------------------------- build

def build_state(folder):
    name = Path(folder).name
    st = BUILDS.get(name)
    if st:
        return st
    p = work_dir(folder) / "last_build.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
    return {"state": "idle", "log": []}


def build(folder, user="agent", log=None):
    """Build the Schedule III workbook now (blocking, 30 s to 3 min). Returns the state dict."""
    folder = Path(folder)
    name = folder.name
    st = BUILDS[name] = {"state": "running", "log": [], "started": dt.datetime.now().isoformat(timespec="seconds")}

    def say(m):
        for line in str(m or "").splitlines():
            if line.strip():
                st["log"].append(line.strip())
                if log:
                    log(line.strip())
    try:
        d = work_dir(folder)
        cy, py = d / "tb_cy.csv", d / "tb_py.csv"
        if not cy.exists():
            raise ValueError("No trial balance for this year yet: get data from Tally first")
        cfg = load_cfg(folder)
        # The engine reads the config from a path: keep the FY and the CIN in step with filing.json.
        f = app.load(folder)
        cfg["fy"] = fy_of(folder)
        if f.get("cin") and not cfg["setup"].get("CIN"):
            cfg["setup"]["CIN"] = f["cin"]
        if not cfg["setup"].get(FV_KEY):
            # the share capital note divides by the face value: a blank one fills the note with #DIV/0!
            cfg["setup"][FV_KEY] = 10
            cfg.setdefault("setup_notes", {})[FV_KEY] = FV_ASSUMED
        save_cfg(folder, cfg)
        tmp_out = d / out_name(folder)
        pipeline.build_workbook(str(cfg_path(folder)), str(cy), str(py) if py.exists() else None, str(tmp_out), log=say)
        final = folder / out_name(folder)
        try:
            shutil.copyfile(tmp_out, final)
        except PermissionError:
            raise PermissionError(f"{final.name} is open in Excel: close it and build again")
        st["out"] = final.name
        wb = openpyxl.load_workbook(final, data_only=True)
        st["checks"] = [[str(c) if c is not None else "" for c in row[:4]] for row in wb["Checks"].iter_rows(values_only=True)
                        if any(c not in (None, "") for c in row[:4])]
        div = float(cfg["setup"].get(DIV_KEY) or 1)
        ly_x = d / "ly_schedule3.xlsx"
        if ly_x.exists():
            try:
                st["ly"] = ly_check.tie_ly_excel(str(final), str(ly_x), div)
            except Exception as e:  # noqa: BLE001
                st["ly"] = {"error": str(e)}
        import lastyear
        ly_pdf = lastyear.find_last_aoc4(folder)
        if ly_pdf:
            try:
                st["aoc4"] = tie_aoc4(final, ly_pdf, div)
                st["aoc4_file"] = ly_pdf.name
            except Exception as e:  # noqa: BLE001
                st["aoc4"] = {"error": str(e)}
        st["state"] = "done"
        st["finished"] = dt.datetime.now().isoformat(timespec="seconds")
        app.save(folder, schedule3=final.name, verified=None)
        ff_audit.event(folder, "build", f"Schedule III workbook built: {final.name}", file=final.name, by=user)
    except Exception as e:  # noqa: BLE001
        st["state"] = "error"
        st["error"] = str(e)
        st["log"].append(str(e))
        st["log"].append(traceback.format_exc()[-1500:])
        ff_audit.event(folder, "build", f"Schedule III build failed: {e}", error=str(e), by=user)
    (work_dir(folder) / "last_build.json").write_text(json.dumps(st, default=str, indent=1), encoding="utf-8")
    return st


def tie_aoc4(built, pdf, divisor=1):
    """Every previous-year figure on the face of the new statements against last year's filed AOC-4.

    Reads the V3 portal PDF with the filing app's own reader (lastyear.read_aoc4_figures); falls back to
    the XFA reader of the old Schedule III app for V2 e-forms."""
    import lastyear
    figs = [v for _, v in lastyear.read_aoc4_figures(pdf) if v is not None]
    if not figs:
        return ly_check.tie_aoc4(str(built), str(pdf), divisor)
    rows = []
    for sn, lbl, cy, py in ly_check.built_lines(str(built)):
        rs = py * divisor
        if abs(rs) < 0.5:
            continue
        hit = any(abs(abs(v) - abs(rs)) <= max(1.0, divisor) for v in figs)
        rows.append({"statement": sn, "line": lbl, "py_rs": round(rs, 2), "found": hit})
    return {"fields": len(figs), "rows": rows, "matched": sum(r["found"] for r in rows), "total": len(rows)}


# ---------------------------------------------------------------- statements for the review screen

def _rows(ws, first_col=1):
    """[(label, note, cy, py, hidden, bold)] of a statement sheet below its Particulars header."""
    out, started = [], False
    for i, r in enumerate(ws.iter_rows(values_only=True), 1):
        lab = r[0] if r else None
        if not started:
            started = isinstance(lab, str) and lab.strip().lower() == "particulars"
            continue
        if not isinstance(lab, str) or not lab.strip():
            continue
        if lab.startswith(("As per our report", "For ", "The accompanying")):
            break
        nums = [x for x in r[2:4]]
        out.append({"label": lab.strip(), "note": r[1] if len(r) > 1 else None,
                    "cy": nums[0] if nums and isinstance(nums[0], (int, float)) else None,
                    "py": nums[1] if len(nums) > 1 and isinstance(nums[1], (int, float)) else None,
                    "hidden": bool(ws.row_dimensions[i].hidden), "row": i})
    return out


def statements(folder):
    """Balance sheet and P&L as built, in rupees, for the review screen."""
    p = output(folder)
    if not p:
        return None

    def read():
        wb = openpyxl.load_workbook(p, data_only=True)
        div = 1.0
        if "Setup" in wb.sheetnames:
            for r in wb["Setup"].iter_rows(max_col=2, values_only=True):
                if r[0] and str(r[0]).startswith("Rounding divisor"):
                    try:
                        div = float(r[1] or 1)
                    except (TypeError, ValueError):
                        pass
        res = {"file": p.name, "divisor": div}
        for s in ("BS", "PL"):
            rows = _rows(wb[s]) if s in wb.sheetnames else []
            for r in rows:
                for k in ("cy", "py"):
                    if r[k] is not None:
                        r[k] = r[k] * div
            res[s] = [r for r in rows if not r["hidden"]]
        res["notes"] = []
        if "Notes" in wb.sheetnames:
            ws = wb["Notes"]
            for i, r in enumerate(ws.iter_rows(values_only=True), 1):
                if ws.row_dimensions[i].hidden:
                    continue  # a note with no figures either year is hidden in the workbook
                if r and isinstance(r[0], (int, float)) and isinstance(r[1], str):
                    if res["notes"] and res["notes"][-1]["no"] == int(r[0]):
                        continue  # a nil note keeps the number of the note before it: only its heading is left
                    res["notes"].append({"no": int(r[0]), "title": r[1].strip()})
        return res
    return app._cached("ffst", p, read)


def drill(folder):
    """Ledgers behind each line on the face of the balance sheet and P&L, for the drill-down on the review screen.

    {(sheet, row): [{"ledger", "group", "cy", "py"}]} in rupees, signed as on the face of the statement."""
    p = output(folder)
    st = statements(folder)
    if not p or not st:
        return {}

    def read():
        L = ff_audit.Ledgers(p)
        if not L.ok:
            return None
        sign = {h[1]: h[4] for h in HEAD.values()}
        res = {}
        for sheet in ("BS", "PL"):
            parent = None
            for r in st[sheet]:
                if r["cy"] is None and r["py"] is None:
                    continue
                lab = re.sub(r"^\(?[a-zA-Z0-9]{1,4}\)\s*", "", r["label"]).strip()
                line = L.line_of(lab)
                code = None
                if line:
                    parent = line
                elif parent:
                    code = L.head_of(parent, lab)
                    line = parent if code else None
                if not line:
                    continue
                term = f"Notes:{L.line_label[line]}/{HEAD[code][3]}" if code else f"{sheet}:{L.line_label[line]}"
                led = {}
                for per in ("CY", "PY"):
                    for x in L.for_term(term, per)[1]:
                        d = led.setdefault(x["ledger"], {"ledger": x["ledger"], "group": x["group"], "cy": 0.0, "py": 0.0})
                        d[per.lower()] += (x["amount"] or 0) * sign.get(line, 1)
                if led:
                    res[(sheet, r["row"])] = sorted(led.values(), key=lambda d: -abs(d["cy"] or d["py"]))
        return res
    return app._cached("ffdrill", p, read) or {}


# ---------------------------------------------------------------- review points

def inr(x):
    from docroll import inr as _inr
    return _inr(round(float(x or 0)))


def review_points(folder):
    """Every point that must be cleared before the tick: [{id, text, kind, detail, cleared}]."""
    folder = Path(folder)
    f = app.load(folder)
    cleared = f.get("cleared") or {}
    pts = []

    def add(pid, text, kind, detail="", auto_ok=None):
        c = cleared.get(pid)
        if c and (c.get("text") and c["text"] != text or pid in FIGURE_CHECKS and not c.get("note")):
            c = None  # the figures behind the point changed after it was cleared: it is open again
        pts.append({"id": pid, "text": text, "kind": kind, "detail": detail,
                    "cleared": c, "passed": auto_ok is True})

    st = build_state(folder)
    fs = output(folder)
    if not fs:
        add("no-fs", "No Schedule III workbook yet", "block", "Get data from Tally, then build the financials.")
        return pts
    if st.get("state") == "error":
        add("build-error", "Last build failed", "block", st.get("error", ""))
    # 1. the workbook's own Checks sheet
    from schedule3 import Schedule3, FSError
    try:
        bad = Schedule3(fs).checks()
        if bad:
            for pid, text, detail, kind in explain_checks(fs):
                add(pid, text, kind, detail)
        else:
            add("checks-ok", "Balance sheet tallies, profit agrees with Tally, all ledgers mapped", "auto", auto_ok=True)
    except FSError as e:
        add("fs-error", "Schedule III workbook cannot be read", "block", str(e))
    # 2. mapping: ledgers nobody approved
    if (work_dir(folder) / "tb_cy.csv").exists():
        try:
            rows = mapping_rows(folder)
            pend = [r for r in rows if not r["approved"]]
            if pend:
                add("map-pending", f"{len(pend)} ledger{'s' if len(pend) != 1 else ''} mapped by the agent: confirm the head{'s' if len(pend) != 1 else ''}", "mapping",
                    ", ".join(r["ledger"] for r in pend[:8]) + (" ..." if len(pend) > 8 else ""))
            else:
                add("map-ok", "Every ledger's Schedule III head is approved", "auto", auto_ok=True)
        except Exception as e:  # noqa: BLE001
            add("map-error", "Mapping could not be read", "block", str(e))
        cy, py = tb(folder, "tb_cy"), tb(folder, "tb_py")
        if cy and py:
            diffs = tally.roll_forward(py, cy)
            if diffs:
                net = sum(d["difference"] for d in diffs)
                why = ("The differences add up to nil, so the balances were most likely moved between ledgers "
                       "(renamed or merged) when the new year's company was made. "
                       if abs(net) < 1 else f"The differences add up to Rs {inr(net)}: an opening balance was changed. ")
                add("rollfwd", f"{len(diffs)} ledgers open this year with a balance different from last year's closing", "check",
                    why + "Ledger and difference: " + "; ".join(f"{d['ledger']} {inr(d['difference'])}" for d in diffs[:6])
                    + (" ..." if len(diffs) > 6 else ""))
            else:
                add("rollfwd-ok", "Opening balances match last year's closing", "auto", auto_ok=True)
    # 3. last year's figures against last year's filed AOC-4
    a = st.get("aoc4")
    if isinstance(a, dict) and a.get("error"):
        add("ly-aoc4-err", "Last year's AOC-4 could not be read for the tie-out", "check", a["error"])
    elif isinstance(a, dict) and a.get("rows"):
        off = [r for r in a["rows"] if not r.get("found")]
        if off:
            add("ly-aoc4", f"{len(off)} of {a['total']} previous-year figures not found in last year's filed AOC-4", "check",
                "; ".join(f"{r['line']} {inr(r['py_rs'])}" for r in off[:5]))
        else:
            add("ly-aoc4-ok", f"All {a['total']} previous-year figures agree with last year's filed AOC-4", "auto", auto_ok=True)
    elif not a:
        add("ly-aoc4-none", "No last year's AOC-4 in the client folder to tie the previous-year column to", "check",
            "Upload last year's filed AOC-4, or clear this point if the client is filing for the first time.")
    ly = st.get("ly")
    if isinstance(ly, dict) and ly.get("rows"):
        off = [r for r in ly["rows"] if not r.get("found")]
        if off:
            add("ly-excel", f"{len(off)} previous-year figures not found in last year's signed Schedule III", "check",
                "; ".join(f"{r['line']}" for r in off[:5]) + (f". {ly['note']}" if ly.get("note") else ""))
    # 4. the partner's / agent's review points written into the workbook
    try:
        wb = openpyxl.load_workbook(fs, read_only=True, data_only=True)
        if "Review Points" in wb.sheetnames:
            for r in wb["Review Points"].iter_rows(min_row=3, values_only=True):
                if r and isinstance(r[0], (int, float)) and r[1]:
                    amt = f"Rs {inr(r[2])}. " if isinstance(r[2], (int, float)) else ""
                    add(f"rp:{int(r[0])}:{re.sub(r'[^a-z0-9]+', '-', str(r[1]).lower())[:30]}", str(r[1]), "point",
                        amt + str(r[3] or ""))
    except Exception:  # noqa: BLE001
        pass
    # 4a. values the agent assumed
    cfg = load_cfg(folder)
    if (cfg.get("setup_notes") or {}).get(FV_KEY) == FV_ASSUMED:
        add("fv-assumed", f"Face value per share taken as Rs {cfg['setup'].get(FV_KEY)}", "setup",
            "It was not entered, and the share capital note needs it for the number of shares. Change it here if it is not Rs 10.")
    # 5. what only staff know (dates of meetings etc.)
    if app.inputs_path(folder).exists():
        open_q = app.steps(folder)["open_q"]
        stale = []
        try:
            import ai
            stale = [t for _, t, how, a, _ in app.questions(folder)[0] if ai.stale_dates(folder, t, how, a)]
        except Exception:  # noqa: BLE001
            pass
        if stale:
            add("questions-stale", f"{len(stale)} input{'s' if len(stale) != 1 else ''} for the forms carry last year's date", "questions",
                "; ".join(stale[:6]) + ". Enter this year's dates on Inputs for the forms.")
        if open_q:
            add("questions", "Questions for the forms still to answer", "questions", "; ".join(open_q))
        else:
            add("questions-ok", "AGM, board meeting and report dates answered", "auto", auto_ok=True)
    else:
        add("questions", "Prepare the questions for the forms (AGM, meetings, report dates)", "questions")
    return pts


# Checks that say the figures themselves do not agree. They are fixed, not noted: clearing one needs a written reason.
FIGURE_CHECKS = {"chk:bs", "chk:profit", "chk:suspense", "chk:reserves", "chk:ppe", "chk:cashflow", "chk:nopy"}


def building(folder):
    """True while a get-data or build job for this client is waiting or running: the figures are about to change."""
    import ff_jobs
    name = Path(folder).name
    return any(j["client"] == name and j["kind"] in ("get_data", "build") and j["status"] in ("queued", "working")
               for j in ff_jobs.load()["jobs"])


CHECK_TEXT = [  # (start of the label on the Checks sheet, id, sentence, what to do)
    ("Balance Sheet tallies", "bs", "Balance sheet does not tally: assets and liabilities differ by {amt}",
     "Usually a ledger with no Schedule III head, or a profit that does not agree with Tally. Clear those points first."),
    ("Profit per Schedule III", "profit", "Profit in the P&L differs from the profit in Tally by {amt}",
     "A P&L ledger is mapped to a balance sheet head, or the other way round. See Mapping."),
    ("Ledgers not mapped", "unmapped", "{n} with no Schedule III head, so {its} balance is left out of the statements",
     "{names}Pick a head on the Mapping tab."),
    ("Suspense balances", "suspense", "Suspense has a balance of {amt}",
     "Suspense should be nil before the accounts are signed: pass the entries in Tally and get the data again."),
    ("Reserves: unexplained", "reserves", "Reserves moved by {amt} more than the year's profit explains",
     "Look for a reserves ledger kept under share capital in Tally, a dividend, or an entry passed straight to reserves."),
    ("PPE:", "ppe", "Fixed assets were reduced by {amt} more than the depreciation charged",
     "There may be a sale or disposal: check the fixed asset note."),
    ("Cash Flow:", "cashflow", "Cash flow statement is out by {amt} against cash and bank",
     "This normally follows from the points above (reserves, unmapped ledgers). It clears when they are fixed."),
    ("Previous-year TB", "nopy", "Last year's trial balance is not loaded, so last year's P&L is blank",
     "Open last year's company in Tally and get the data again, or upload last year's trial balance."),
    ("Roll-forward", "regroup", "Last year's balances are grouped differently in the two Tally companies",
     "{lines}The last-year column follows this year's grouping. Check it against last year's signed accounts."),
]


def explain_checks(fs):
    """The Checks sheet lines that do not read OK, in plain words: [(id, text, detail, kind)]."""
    wb = openpyxl.load_workbook(fs, read_only=True, data_only=True)
    ws = wb["Checks"]
    rows = [list(r[:4]) + [None] * 4 for r in ws.iter_rows(min_row=4, values_only=True)]
    num = lambda v: v if isinstance(v, (int, float)) else 0
    out, i = [], 0
    for i, r in enumerate(rows):
        if not r[0] or not isinstance(r[3], str):
            break
        if r[3].strip() == "OK":
            continue
        label, cy, py = str(r[0]), num(r[1]), num(r[2])
        hit = next((c for c in CHECK_TEXT if label.startswith(c[0])), None)
        if not hit:
            out.append(("chk:" + re.sub(r"\W+", "-", label[:40]).lower(), f"{label}: does not agree", "", "check"))
            continue
        _, pid, text, detail = hit
        amt = f"Rs {inr(abs(cy))} this year" if abs(cy) >= 1 else ""
        if abs(py) >= 1 and pid not in ("regroup", "nopy"):
            amt += (" and " if amt else "") + f"Rs {inr(abs(py))} last year"
        kind, names, lines, n = "check", "", "", ""
        if pid == "unmapped":
            led = []
            for sh in ("TB_CY", "TB_PY"):
                if sh in wb.sheetnames:
                    led += [str(x[0]) for x in wb[sh].iter_rows(min_row=2, max_col=19, values_only=True)
                            if x and x[0] and len(x) > 18 and x[18] == "MAP!" and str(x[0]) not in led]
            n = f"{len(led)} ledger{'s' if len(led) != 1 else ''}" if led else "Some ledgers"
            names = ("Ledger: " + ", ".join(led[:6]) + (" ..." if len(led) > 6 else "") + ". ") if led else ""
            kind = "mapping"
            detail = detail.replace("{its}", "its" if len(led) == 1 else "their")
            text = text.replace("{its}", "its" if len(led) == 1 else "their")
        if pid == "regroup":
            diff = []
            for x in rows[i:]:
                if x[0] and isinstance(x[3], (int, float)) and abs(x[3]) >= 1 and not str(x[0]).startswith("Total"):
                    diff.append(f"{x[0]}: Rs {inr(num(x[1]))} in last year's company, Rs {inr(num(x[2]))} in this year's opening")
            lines = ("; ".join(diff[:6]) + ". ") if diff else ""
        out.append(("chk:" + pid, text.format(amt=amt or "a small amount", n=n), detail.format(names=names, lines=lines), kind))
    return out


def set_setup(folder, key, value, user):
    """A Setup value typed by staff on a review point (face value). The workbook is rebuilt by the caller."""
    if not user.strip():
        raise ValueError("Enter your name: the change is recorded against a person")
    if key != FV_KEY:
        raise ValueError("That value cannot be changed here")
    try:
        v = float(str(value).replace(",", "").strip())
    except ValueError:
        raise ValueError("Enter the face value as a number, for example 10")
    if v <= 0:
        raise ValueError("The face value must be more than zero")
    cfg = load_cfg(folder)
    cfg["setup"][key] = int(v) if v == int(v) else v
    cfg.setdefault("setup_notes", {})[key] = f"Entered by {user.strip()} on {dt.date.today():%d-%b-%y}"
    save_cfg(folder, cfg)
    app.save(folder, verified=None)
    ff_audit.event(folder, "review", f"Face value per share set to Rs {cfg['setup'][key]}", by=user.strip())


def open_points(folder):
    return [p for p in review_points(folder) if not p["passed"] and not p["cleared"]]


def clear_point(folder, pid, user, note=""):
    if not user.strip():
        raise ValueError("Enter your name to clear a review point")
    pts = {p["id"]: p for p in review_points(folder)}
    p = pts.get(pid)
    if not p:
        raise ValueError("That review point is no longer open")
    if p["kind"] in ("block", "questions", "mapping"):
        raise ValueError("This point clears itself once the work is done: " +
                         {"block": "fix the data and build again", "questions": "answer the questions",
                          "mapping": "approve the mapping"}[p["kind"]])
    if p["kind"] == "setup":  # clearing confirms the assumed value
        cfg = load_cfg(folder)
        cfg.setdefault("setup_notes", {})[FV_KEY] = f"Rs {cfg['setup'].get(FV_KEY)} confirmed by {user.strip()} on {dt.date.today():%d-%b-%y}"
        save_cfg(folder, cfg)
        ff_audit.event(folder, "review", f"Face value per share confirmed as Rs {cfg['setup'].get(FV_KEY)}", by=user.strip())
        return
    f = app.load(folder)
    c = f.get("cleared") or {}
    if pid in FIGURE_CHECKS and not note.strip():
        raise ValueError("Write the reason: this point says the figures do not agree, so it cannot be cleared without one")
    c[pid] = {"by": user.strip(), "at": dt.datetime.now().isoformat(timespec="seconds"), "note": note.strip(), "text": p["text"]}
    app.save(folder, cleared=c)
    ff_audit.event(folder, "review", f"Review point cleared: {p['text']}" + (f" ({note.strip()})" if note.strip() else ""),
                   point=pid, by=user.strip())


def verify(folder, user):
    """The tick: financials verified, okay to file. Refused while any point is open."""
    if not user.strip():
        raise ValueError("Enter your name: the tick is recorded against a person")
    if building(folder):
        raise ValueError("The financials are being rebuilt: wait for the new figures, then review and tick")
    left = open_points(folder)
    if left:
        raise ValueError(f"{len(left)} review points are still open: " + "; ".join(p["text"] for p in left[:4]))
    fs = output(folder)
    v = {"by": user.strip(), "at": dt.datetime.now().isoformat(timespec="seconds"), "file": fs.name if fs else ""}
    app.save(folder, verified=v)
    ff_audit.event(folder, "verify", "Financials ticked verified, okay to file", by=user.strip(), file=v["file"])
    return v


def unverify(folder, user):
    app.save(folder, verified=None)
    ff_audit.event(folder, "verify", "Tick removed: financials to be reviewed again", by=user or "staff")


def verified(folder):
    """The tick, or None. A tick does not stand while a review point is open or the figures are being rebuilt."""
    v = app.load(folder).get("verified")
    if not v:
        return None
    try:
        if building(folder) or open_points(folder):
            return None
    except Exception:  # noqa: BLE001
        return None
    return v


# ---------------------------------------------------------------- reports and meeting papers

def docs_ready(folder):
    """(ok, why) for the board's report / auditor's report / notice set (engine/make_docs_std.py)."""
    try:
        import docx  # noqa: F401
    except ImportError:
        return False, "python-docx is not installed: run setup.bat"
    cfg = load_cfg(folder)
    if not cfg.get("docs"):
        return False, "The AGM date, the date of the documents and the company's short name are not entered yet"
    if not output(folder):
        return False, "Build the financials first"
    return True, ""


def ly_docs_dir(folder):
    d = work_dir(folder) / "last_year_docs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def make_docs(folder, user="agent"):
    """Notice, board's report, auditor's report + CARO, lists: rolled forward from last year's signed documents."""
    ok, why = docs_ready(folder)
    if not ok:
        raise ValueError(why)
    import importlib
    mds = importlib.import_module("make_docs_std")
    mds.FLAGS.clear()
    out = Path(folder) / "reports"
    flags = mds.main(str(cfg_path(folder)), str(output(folder)), str(ly_docs_dir(folder)), str(out))
    ff_audit.event(folder, "docs", f"Reports and meeting papers drafted in {out.name} ({len(flags)} points to check)", by=user)
    return out, flags


def docs_list(folder):
    d = Path(folder) / "reports"
    return sorted(p.name for p in d.glob("*") if p.suffix.lower() in (".docx", ".xlsx")) if d.exists() else []


def docs_flags(folder):
    p = Path(folder) / "reports" / "flags.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []
