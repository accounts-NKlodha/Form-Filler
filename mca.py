"""MCA form filler: local tool.

    python mca.py serve                      start the local server on 127.0.0.1:8742 (dashboard + extension API)
    python mca.py map aoc4                   (re)build mapping/aoc4_map.xlsx from the latest AOC-4 dump
    python mca.py workbook "clients/ABC Ltd" build "ABC Ltd - MCA inputs.xlsx" in that client folder
    python mca.py plan <inputs.xlsx> aoc4    write the fill plan JSON (for the extension's "Load plan file")

Dumps (field structure, no values) arrive from the extension (Alt+Shift+D) into dumps/.
"""
import argparse
import json
import re
import sys
import threading
import webbrowser
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

import app
import attachments
import ff_audit
import ff_jobs
import ff_ui
import lastyear
import smart
import suggest
from schedule3 import FSError, Schedule3, find_schedule3, norm

ROOT = Path(__file__).resolve().parent
DUMPS = ROOT / "dumps"
CLIENTS = ROOT / "clients"
MAPS = ROOT / "mapping"
STATE = ROOT / "state.json"
PORT = 8742

FORM_NAMES = {"aoc4": "AOC-4", "aoc-4": "AOC-4", "mgt7": "MGT-7", "mgt-7": "MGT-7", "mgt7a": "MGT-7A", "mgt-7a": "MGT-7A"}
INPUT_TYPES = ("text", "number", "date", "dropdown", "radio", "checkbox")

YELLOW = PatternFill("solid", fgColor="FFF2CC")
GREEN = PatternFill("solid", fgColor="E2F0D9")
GREY = PatternFill("solid", fgColor="EDEDED")
ORANGE = PatternFill("solid", fgColor="FCE4D6")
BLUE = PatternFill("solid", fgColor="DDEBF7")
AUTO = PatternFill("solid", fgColor="D9E1F2")
AUTO_MARK = "(auto-filled)"
HEAD = PatternFill("solid", fgColor="1F4E78")


def form_name(slug):
    return FORM_NAMES.get(slug.lower(), slug.upper())


def prefix(slug):
    return re.sub(r"[^A-Z0-9]", "", form_name(slug).upper())


# ---------------------------------------------------------------- form schema

def merge_dump(slug, new):
    """Add one page's dump to the saved dump of the form. Fields match by key; a new field
    is inserted after the field that precedes it in this capture, so form order holds."""
    p = DUMPS / f"{slug}.json"
    old = json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    pages = list(old.get("pages", [])) if old else []
    for pg in new.get("pagesOnScreen") or []:
        if pg not in pages:
            pages.append(pg)
    if not old:
        return dict(new, pages=pages), len(new.get("fields", []))
    fields = list(old.get("fields", []))
    pos = {f.get("key"): i for i, f in enumerate(fields)}
    added, anchor = 0, None
    for f in new.get("fields", []):
        k = f.get("key")
        if k in pos:
            prev = fields[pos[k]]
            # Pages lock each other (and the final verification page locks everything), so a
            # field counts as read-only / disabled only if it was so in every capture.
            fields[pos[k]] = dict(f, rendered=f.get("rendered") or prev.get("rendered"), page=f.get("page") or prev.get("page"),
                                  readOnly=bool(f.get("readOnly") and prev.get("readOnly")),
                                  disabled=bool(f.get("disabled") and prev.get("disabled")))
            anchor = pos[k]
        else:
            at = anchor + 1 if anchor is not None else len(fields)
            fields.insert(at, f)
            added += 1
            pos = {ff.get("key"): i for i, ff in enumerate(fields)}
            anchor = at
    buttons = {b.get("key"): b for b in old.get("buttons", []) + new.get("buttons", [])}
    merged = dict(old, fields=fields, buttons=list(buttons.values()), pages=pages,
                  capturedAt=new.get("capturedAt"), source=new.get("source") or old.get("source"))
    return merged, added


def load_dump(slug):
    p = DUMPS / f"{slug}.json"
    if not p.exists():
        raise FileNotFoundError(f"no dump for {form_name(slug)} yet: open the form on MCA and press Alt+Shift+D")
    return json.loads(p.read_text(encoding="utf-8"))


def section_text(f):
    """Readable section path: drops the portal's internal panel names (LLP-form04_Panel, Section...)."""
    keep = []
    for part in f.get("section") or []:
        if "_" in part or part in ("Section", "Field Panel", "Fields Panel", "Table", "Row 2") or re.fullmatch(r"[A-Za-z0-9-]+", part) and not part.istitle():
            continue
        part = re.sub(r"\s+Panel$", "", part)
        if not keep or keep[-1] != part:
            keep.append(part)
    return " › ".join(keep[-2:]) or "(general)"


def is_technical(f):
    """Hidden helper fields the portal keeps for itself (savedCinVal, EL, table2ExcelData...)."""
    lab = (f.get("label") or "").strip()
    if f.get("rendered"):
        return False
    if not lab or lab.lower() in ("text box", "company search box", "server date"):
        return True
    # one token that looks like a variable name: savedCinVal, table2ExcelData, number_associate_company, EL
    return re.fullmatch(r"[A-Za-z0-9_]+", lab) is not None and (
        "_" in lab or re.search(r"[a-z][A-Z]|[A-Za-z]\d", lab) is not None or len(lab) <= 2)


def row_label(label):
    return label.split(" / ")[0] if " / " in label else label


def period_of(f):
    lab = norm(f["label"]) + " " + norm(f.get("name", ""))
    if re.search(r"previous|prev\b|py\b|last year", lab):
        return "PY"
    return "CY"


def schema(slug):
    """Fields of a form in form order, with codes; repeatable fields grouped into tables."""
    d = load_dump(slug)
    pre = prefix(slug)
    fields, tables, seen, n = [], {}, set(), 0
    for f in d["fields"]:
        if f["type"] not in INPUT_TYPES + ("file",) or not f.get("key") or f["key"] in seen or is_technical(f):
            continue
        seen.add(f["key"])
        n += 1
        f = dict(f, code=f"{pre}-{n:03d}", sectionText=section_text(f))
        rep = f.get("repeat")
        if rep and rep.get("groupSom") and f["type"] != "file":
            t = tables.setdefault(rep["groupKey"] or rep["title"], {
                "groupKey": rep["groupKey"], "groupSom": rep["groupSom"], "title": rep["title"],
                "section": f["sectionText"], "max": rep.get("max") or -1, "fields": []})
            t["fields"].append(f)
        else:
            if rep:
                f["note"] = "In a repeatable table the tool cannot fill: enter on the portal"
            fields.append(f)
    for i, t in enumerate(tables.values(), 1):
        t["sheet"] = f"{pre} T{i}"
    return {"slug": slug, "name": form_name(slug), "title": d.get("title", ""), "capturedAt": d.get("capturedAt"),
            "source": d.get("source"), "fields": fields, "tables": list(tables.values())}


# ---------------------------------------------------------------- mapping file

def map_path(slug):
    return MAPS / f"{slug}_map.xlsx"


def read_map(slug):
    p = map_path(slug)
    if not p.exists():
        return {}
    ws = openpyxl.load_workbook(p, data_only=True)["Map"]
    out = {}
    for row in ws.iter_rows(min_row=3, values_only=True):
        if row and row[6]:
            out[row[6]] = {"period": (row[3] or "CY").strip().upper(), "expr": (row[4] or "").strip(), "note": row[5] or ""}
    return out


def build_map(slug):
    """Write mapping/<slug>_map.xlsx for every number field, keeping the firm's existing edits."""
    sc = schema(slug)
    old = read_map(slug)
    rules = suggest.rules_for(slug)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Map"
    ws["A1"] = f"{sc['name']}: where each figure comes from in the Schedule III workbook. Edit column E. " \
               "Terms: BS:<line>, PL:<line>, Notes:<note heading>/<row>, Setup:<label>, joined with ' + ' or ' - '."
    ws["A1"].font = Font(bold=True)
    heads = ["Code", "Section", "Portal field", "Period (CY/PY)", "Source expression", "Note", "key"]
    for c, h in enumerate(heads, 1):
        cell = ws.cell(2, c, h)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = HEAD
    r = 3
    # Number fields always get a row; text fields only when a rule (or the firm) gave them a
    # source, because some portal forms (MGT-7A) use plain text boxes for amounts.
    cands = [f for f in sc["fields"] + [f for t in sc["tables"] for f in t["fields"]] if f["type"] in ("number", "text")]
    hits = rows = 0
    for f in cands:
        prev = old.get(f["key"])
        if suggest.SKIP_NAME.search(f.get("name") or "") or "reason for change" in f["label"].lower():
            continue  # "reason for change in pre-filled figures" boxes are text, not figures
        if prev:
            period, expr, note = prev["period"], prev["expr"], prev["note"]
        elif slug.startswith("aoc4") and any(re.search(p_, f.get("name") or "") for p_, _ in suggest.AOC4_NAMES):
            period = "PY" if re.search(r"previous|^Part(P|2PR)", f.get("name") or "", re.I) else "CY"
            expr = next(e_ for p_, e_ in suggest.AOC4_NAMES if re.search(p_, f.get("name") or ""))
            note = "by field name: check"
        else:
            period, expr, note = period_of(f), "", ""
            lab, sec = norm(row_label(f["label"])), norm(f["sectionText"])
            lab = re.sub(r"^(?:[ivx]+|[a-z]|\d+) (?=\w)", "", lab)  # bare numbering: "i Turnover", "a From banks"
            for spat, lpat, e in rules:
                if re.search(lpat, lab) and (not spat or re.search(spat, sec)):
                    expr, note = e, "suggested: check"
                    break
        if f["type"] == "text" and not expr and not prev:
            continue
        hits += bool(expr)
        rows += 1
        for c, v in enumerate([f["code"], f["sectionText"], f["label"], period, expr, note, f["key"]], 1):
            ws.cell(r, c, v)
        ws.cell(r, 5).fill = YELLOW
        r += 1
    for col, w in zip("ABCDEFG", (11, 40, 55, 9, 80, 20, 30)):
        ws.column_dimensions[col].width = w
    ws.column_dimensions["G"].hidden = True
    ws.freeze_panes = "A3"
    MAPS.mkdir(exist_ok=True)
    wb.save(map_path(slug))
    return map_path(slug), rows, hits


# ---------------------------------------------------------------- client workbook

def _sheet_name(s):
    return re.sub(r"[\[\]:*?/\\]", "-", s)[:31]


def _hint(f):
    if f["type"] == "date":
        return "DD/MM/YYYY"
    if f["type"] in ("dropdown", "radio"):
        return " | ".join(o["text"] for o in f["options"])[:250]
    if f["type"] == "checkbox":
        return ("Yes / No" if len(f["options"]) <= 1 else "comma list: " + ", ".join(o["text"] for o in f["options"]))[:250]
    if f["type"] == "number":
        return "number (absolute Rs)"
    return ""


class Lists:
    """Hidden sheet holding dropdown option lists for data validation."""

    def __init__(self, wb):
        self.ws = wb.create_sheet("Lists")
        self.ws.sheet_state = "hidden"
        self.col = 0
        self.cache = {}

    def ref(self, texts):
        key = tuple(texts)
        if key not in self.cache:
            self.col += 1
            for i, t in enumerate(texts, 1):
                self.ws.cell(i, self.col, t)
            L = get_column_letter(self.col)
            self.cache[key] = f"Lists!${L}$1:${L}${len(texts)}"
        return self.cache[key]


def _validate(ws, lists, f, cell_range):
    texts = None
    if f["type"] in ("dropdown", "radio") and f["options"]:
        texts = [o["text"] or o["value"] for o in f["options"]]
    elif f["type"] == "checkbox" and len(f["options"]) <= 1:
        texts = ["Yes", "No"]
    if texts:
        dv = DataValidation(type="list", formula1="=" + lists.ref(texts), allow_blank=True, showErrorMessage=True,
                            errorTitle="Not allowed", error="Pick a value from the list")
        ws.add_data_validation(dv)
        dv.add(cell_range)


def existing_values(path):
    """Values staff already typed in an earlier inputs workbook: {key: value} and {groupKey: [row dicts]}."""
    vals, rows = {}, {}
    if not path.exists():
        return vals, rows
    wb = openpyxl.load_workbook(path, data_only=True)
    if "Meta" not in wb.sheetnames:
        return vals, rows
    for name, slug, kind, gkey in wb["Meta"].iter_rows(min_row=2, values_only=True):
        if name not in wb.sheetnames:
            continue
        ws = wb[name]
        if kind == "form":
            for row in ws.iter_rows(min_row=4, values_only=True):
                if len(row) >= 9 and row[8] and row[5] not in (None, "") and not str(row[7] or "").startswith(("From FS", "Auto")):
                    vals[row[8]] = row[5]
        else:
            if AUTO_MARK in str(ws["A1"].value or ""):
                continue  # rebuilt from the Questions each time
            keys = [c.value for c in ws[4]]
            out = []
            for row in ws.iter_rows(min_row=5, values_only=True):
                if any(v not in (None, "") for v in row):
                    out.append({k: v for k, v in zip(keys, row) if k})
            rows[gkey] = out
    return vals, rows


def old_answers(path):
    if not path.exists():
        return {}
    wb = openpyxl.load_workbook(path, data_only=True)
    if "Questions" not in wb.sheetnames:
        return {}
    return {r[0]: r[3] for r in wb["Questions"].iter_rows(min_row=4, values_only=True) if r and r[0]}


def _el(f):
    """AEM element name of a table field (last part of its SOM path)."""
    return re.sub(r"\[\d+\]", "", (f.get("repeat") or {}).get("relSom", "").split(".")[-1]) or f.get("name", "")


def build_workbook(folder, slugs=None):
    folder = Path(folder)
    client = folder.name
    out = folder / f"{client} - MCA inputs.xlsx"
    slugs = slugs or sorted(p.stem for p in DUMPS.glob("*.json"))
    if not slugs:
        raise FileNotFoundError("no form dumps yet: open each form on MCA and press Alt+Shift+D")
    fs_path = find_schedule3(folder)
    fs, fs_error = None, None
    if fs_path:
        try:
            fs = Schedule3(fs_path)
        except FSError as e:
            fs_error = str(e)
    old_vals, old_rows = existing_values(out)
    answers_old = old_answers(out)
    # Last year's filed forms in the client folder: what carries forward.
    facts_by, ly_names = {}, []
    for slug_, finder, reader in (("mgt7a", lastyear.find_last_mgt7a, lastyear.read_mgt7a),
                                  ("aoc4", lastyear.find_last_aoc4, lastyear.read_aoc4)):
        p_ = finder(folder)
        if not p_:
            ly_names.append(f"{form_name(slug_)}: none in the client folder")
            continue
        try:
            facts_by[slug_] = reader(p_)
            ly_names.append(f"{form_name(slug_)}: {p_.name}")
        except Exception as e:  # noqa: BLE001
            ly_names.append(f"{form_name(slug_)}: {p_.name} could not be read ({e})")
    if True:  # Setup sheet rows fill gaps in last year's AOC-4 facts
        facts_by["aoc4"] = smart.setup_facts_aoc4(fs, facts_by.get("aoc4"))
    facts = facts_by.get("mgt7a")

    wb = openpyxl.Workbook()
    info = wb.active
    info.title = "Info"
    lists = Lists(wb)
    meta = wb.create_sheet("Meta")
    meta.sheet_state = "hidden"
    meta.append(["sheet", "slug", "kind", "groupKey"])
    lines = [
        ("Client", client),
        ("Schedule III workbook", fs_path.name if fs_path else "none found in the client folder"),
        ("Schedule III status", fs_error or ("checks OK" if fs and not fs.checks() else
                                              "; ".join(fs.checks()) if fs else "no figures pulled")),
        ("Built", datetime.now().strftime("%d/%m/%Y %H:%M")),
        ("", ""),
        ("How to use", "Fill the yellow Value cells. Green cells came from the Schedule III workbook: change the "
                       "Schedule III workbook (or mapping) and rebuild rather than typing over them. Grey rows are "
                       "filled by the portal or need manual action (attachments)."),
        ("", "Blank cells are left alone on the portal. Save this file before pressing Alt+Shift+F."),
        ("", "Rebuilding keeps what you typed in yellow cells and table sheets."),
        ("Last year's filings", "; ".join(ly_names)),
        ("Blue cells", "Auto-filled from the Questions sheet, last year's filing or the Schedule III workbook. "
                       "To change them, answer the Questions sheet and click Build again."),
    ]
    for k, v in lines:
        info.append([k, v])
    info.column_dimensions["A"].width = 24
    info.column_dimensions["B"].width = 110
    for row in info.iter_rows():
        row[0].font = Font(bold=True)
        row[1].alignment = Alignment(wrap_text=True)

    derived_by = {}
    smart_forms = [s_ for s_ in ("mgt7a", "aoc4") if s_ in slugs]
    if smart_forms:
        qs = wb.create_sheet("Questions", 1)
        qs["A1"] = "Answer these, save, then click Build / refresh inputs on the dashboard. Everything else is filled for you."
        qs["A1"].font = Font(bold=True, size=12)
        qs.append([])
        for c, h in enumerate(["key", "Question", "How to answer", "Answer", "Default came from"], 1):
            cell = qs.cell(3, c, h)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = HEAD
        answers = {}
        qlist, seen_q = [], set()
        for s_ in smart_forms:
            for key, q, how, dflt in (smart.QUESTIONS if s_ == "mgt7a" else smart.QUESTIONS_AOC4 + smart.QUESTIONS):
                if key not in seen_q:
                    seen_q.add(key)
                    qlist.append((key, q, how, dflt, facts_by.get(s_)))
        for key, q, how, dflt, f_ in qlist:
            prev = answers_old.get(key)
            from_setup = fs.setup(smart.SETUP_ANSWERS[key]) if (fs and key in smart.SETUP_ANSWERS) else None
            if isinstance(from_setup, str) and not from_setup.strip():
                from_setup = None
            val = prev if prev not in (None, "") else (from_setup if from_setup is not None else dflt(f_, fs))
            if isinstance(val, (datetime, date)):
                val = val.strftime("%d/%m/%Y")
            answers[key] = val
            qs.append([key, q, how, val, "your answer" if prev not in (None, "") else ("suggested" if val else "")])
            cell = qs.cell(qs.max_row, 4)
            cell.fill = YELLOW if val in (None, "") else GREEN
            cell.number_format = "@"
        for col, w in zip("ABCDE", (16, 62, 34, 46, 16)):
            qs.column_dimensions[col].width = w
        qs.column_dimensions["A"].hidden = True
        if "mgt7a" in smart_forms:
            derived_by["mgt7a"] = smart.derive(facts_by.get("mgt7a"), answers, fs)
        if "aoc4" in smart_forms:
            derived_by["aoc4"] = smart.derive_aoc4(facts_by.get("aoc4"), answers, fs, facts_by.get("mgt7a"))
        must = ("agm_date", "board_meetings", "resolution_date", "board_fs_date", "auditor_report_date", "ca_cop")
        missing = [q for key, q, _, _, _ in qlist if answers.get(key) in (None, "") and key in must]
        r0 = qs.max_row + 2
        qs.cell(r0, 2, "Still to answer").font = Font(bold=True)
        for i, q in enumerate(missing or ["nothing: all key questions answered"], 1):
            qs.cell(r0 + i, 2, q)
        r1 = r0 + len(missing or [1]) + 2
        try:
            end = smart._fy_end(fs, facts)
            made = [] if "mgt7a" not in smart_forms else attachments.make(folder, facts, answers, f"FY {end.year - 1}-{str(end.year)[2:]}" if end else "this year")
        except Exception as e:  # noqa: BLE001
            made = [("(attachments not made)", str(e))]
        if made:
            qs.cell(r1, 2, "Attachments prepared in the client's 'attachments' folder (check, then attach on the portal)").font = Font(bold=True)
            for i, (name, what) in enumerate(made, 1):
                qs.cell(r1 + i, 2, f"{name}: {what}")
            r1 += len(made) + 2
        qs.cell(r1, 2, "Do by hand on the portal").font = Font(bold=True)
        todos = [t_ for d_ in derived_by.values() for t_ in d_.todo]
        for i, t in enumerate(dict.fromkeys(todos), 1):
            qs.cell(r1 + i, 2, t).alignment = Alignment(wrap_text=True)

    fs_problems = []
    # Previous-year figures: last year's filed AOC-4 (its current-year column) wins over the workbook,
    # so the filing stays consistent with what MCA already has.
    ly_prev, ly_prev_src = {}, None
    p_aoc4 = lastyear.find_last_aoc4(folder)
    if p_aoc4 and "aoc4" in slugs:
        try:
            mp_ = read_map("aoc4")
            want = [(f["key"], row_label(f["label"])) for f in schema("aoc4")["fields"]
                    if (mp_.get(f["key"]) or {}).get("period") == "PY" and (mp_.get(f["key"]) or {}).get("expr")]
            ly_prev = lastyear.match_previous(want, lastyear.read_aoc4_figures(p_aoc4))
            ly_prev_src = p_aoc4.name
        except Exception:  # noqa: BLE001
            ly_prev = {}
    for slug in slugs:
        sc = schema(slug)
        mp = read_map(slug)
        ws = wb.create_sheet(_sheet_name(sc["name"]))
        meta.append([ws.title, slug, "form", ""])
        ws["A1"] = f"{sc['name']}  —  {client}"
        ws["A1"].font = Font(bold=True, size=13)
        ws["A2"] = f"Form structure captured {sc['capturedAt'] or ''}. Fill yellow cells; tables are on the '{prefix(slug)} T…' sheets."
        heads = ["Code", "Section", "Field", "Type", "Req", "Value", "Allowed values / format", "Source / note", "key"]
        for c, h in enumerate(heads, 1):
            cell = ws.cell(3, c, h)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = HEAD
        r, last, tables_by_section = 4, None, {}
        for t in sc["tables"]:
            tables_by_section.setdefault(t["section"], []).append(t)
        for f in sc["fields"]:
            if f["sectionText"] != last:
                last = f["sectionText"]
                ws.cell(r, 1, last).font = Font(bold=True)
                for c in range(1, 9):
                    ws.cell(r, c).fill = BLUE
                r += 1
                for t in tables_by_section.pop(last, []):
                    ws.cell(r, 3, f"Table: {t['title']} → sheet '{t['sheet']}'").font = Font(italic=True)
                    r += 1
            ws.cell(r, 1, f["code"])
            ws.cell(r, 2, f["sectionText"])
            ws.cell(r, 3, f["label"])
            ws.cell(r, 4, f["type"])
            ws.cell(r, 5, "*" if f.get("mandatory") else "")
            ws.cell(r, 7, _hint(f))
            ws.cell(r, 9, f["key"])
            v = ws.cell(r, 6)
            note = f.get("note", "")
            if f["type"] == "file":
                note = "Attachment: upload by hand on the portal"
                v.fill = GREY
            elif f.get("readOnly") and not ((derived_by.get(slug) and (f.get("name") in derived_by[slug].fields
                                                                         or f.get("name") in derived_by[slug].override))
                                            or (mp.get(f["key"]) or {}).get("expr")):
                # Locked when captured. Fields we have a value for stay in: MCA unlocks them section by section.
                note = "Pre-filled by the portal: leave blank"
                v.fill = GREY
            else:
                v.fill = YELLOW
                if f.get("disabled"):
                    note = "Opens up after an earlier answer"
                m = mp.get(f["key"])
                if m and m["expr"] and f["type"] in ("number", "text"):
                    if fs:
                        try:
                            v.value = fs.eval(m["expr"], m["period"])
                            v.fill = GREEN
                            note = f"From FS ({m['period']}): {m['expr']}"
                            if slug == "aoc4" and m["period"] == "PY" and f["key"] in ly_prev:
                                ly = ly_prev[f["key"]]
                                diff = "" if abs(ly - float(v.value or 0)) < 1 else f" (workbook says {v.value})"
                                v.value = int(ly) if float(ly).is_integer() else ly
                                note = f"Last year's AOC-4 ({ly_prev_src}){diff}"
                        except FSError as e:
                            v.fill = ORANGE
                            note = f"FS error: {e}"
                            fs_problems.append(f"{f['code']} {f['label']}: {e}")
                    else:
                        note = f"Map: {m['expr']} (no Schedule III figures)"
                if v.value is None and f["key"] in old_vals:
                    v.value = old_vals[f["key"]]
                derived = derived_by.get(slug)
                if derived and f.get("name", "") in derived.override:
                    v.value, src = derived.override[f["name"]]
                    v.fill = AUTO
                    note = f"Auto ({src})"
                if derived and v.value is None:
                    nm = f.get("name", "")
                    if nm in derived.fields:
                        v.value, src = derived.fields[nm]
                        v.fill = AUTO
                        note = f"Auto ({src})"
                    elif nm in derived.copies:
                        row_lab = row_label(f["label"])
                        twin = next((g for g in sc["fields"] if g is not f and row_label(g["label"]) == row_lab
                                     and "filing date" in g["label"].lower()), None)
                        if twin:
                            v.value = "(same as on filing date)"
                            v.fill = AUTO
                            note = "Auto (copied from the portal's 'as on filing date' value)"
                            ws.cell(r, 10, twin["key"])
                if f["type"] == "date":
                    v.number_format = "DD/MM/YYYY"
                elif f["type"] == "text":
                    v.number_format = "@"
                _validate(ws, lists, f, v.coordinate)
            ws.cell(r, 8, note)
            if f.get("readOnly") or f["type"] == "file":
                for c in (1, 2, 3, 4, 7, 8):
                    ws.cell(r, c).font = Font(color="808080")
            r += 1
        for rest in tables_by_section.values():
            for t in rest:
                ws.cell(r, 3, f"Table: {t['title']} → sheet '{t['sheet']}'").font = Font(italic=True)
                r += 1
        for col, w in zip("ABCDEFGHI", (10, 34, 60, 9, 4, 28, 40, 45, 30)):
            ws.column_dimensions[col].width = w
        ws.column_dimensions["I"].hidden = True
        ws.column_dimensions["J"].hidden = True
        ws.freeze_panes = "D4"

        for t in sc["tables"]:
            ts = wb.create_sheet(_sheet_name(t["sheet"]))
            meta.append([ts.title, slug, "table", t["groupKey"]])
            ts["A1"] = f"{t['title']}  ({t['section']})  —  one row per entry" + \
                       (f", at most {t['max']}" if t["max"] and t["max"] > 0 else "")
            ts["A1"].font = Font(bold=True)
            for c, f in enumerate(t["fields"], 1):
                h = ts.cell(2, c, f["label"])
                h.font = Font(bold=True, color="FFFFFF")
                h.fill = HEAD
                h.alignment = Alignment(wrap_text=True, vertical="top")
                ts.cell(3, c, f"{f['code']}  {f['type']}  {_hint(f)}".strip()).font = Font(size=8, color="808080")
                ts.cell(4, c, f["key"])
                ts.column_dimensions[get_column_letter(c)].width = 22
                L = get_column_letter(c)
                for rr in range(5, 45):
                    cell = ts.cell(rr, c)
                    cell.fill = YELLOW
                    if f["type"] == "date":
                        cell.number_format = "DD/MM/YYYY"
                    elif f["type"] == "text":
                        cell.number_format = "@"
                _validate(ts, lists, f, f"{L}5:{L}44")
            ts.row_dimensions[4].hidden = True
            ts.row_dimensions[2].height = 45
            auto_rows = None
            derived = derived_by.get(slug)
            if derived and not old_rows.get(t["groupKey"]):
                names = {_el(f) for f in t["fields"]}
                auto_rows = next((rows for rows in derived.tables.values() if rows and set(rows[0]) & names), None)
            if auto_rows:
                ts["A1"] = f"{ts['A1'].value}  {AUTO_MARK}: rebuilt from the Questions each time"
                for i, row in enumerate(auto_rows):
                    for c, f in enumerate(t["fields"], 1):
                        val = row.get(_el(f))
                        if val not in (None, ""):  # read-only at capture time may open later; the fill checks live
                            ts.cell(5 + i, c, val).fill = AUTO
            for i, row in enumerate(old_rows.get(t["groupKey"], [])):
                for c, f in enumerate(t["fields"], 1):
                    if f["key"] in row:
                        ts.cell(5 + i, c, row[f["key"]])
            ts.freeze_panes = "A5"

    if fs_problems:
        info.append(["FS mapping problems", "\n".join(fs_problems[:60])])
        info.cell(info.max_row, 2).alignment = Alignment(wrap_text=True)
    wb.move_sheet("Lists", offset=len(wb.sheetnames))
    wb.move_sheet("Meta", offset=len(wb.sheetnames))
    try:
        wb.save(out)
    except PermissionError:
        raise PermissionError(f"{out.name} is open in Excel: close it and try again")
    return out, fs_problems, fs_error


# ---------------------------------------------------------------- plan

def _num_str(v):
    if isinstance(v, bool):
        raise ValueError("expected a number")
    if isinstance(v, (int, float)):
        return str(int(v)) if float(v).is_integer() else f"{v:.2f}".rstrip("0").rstrip(".")
    s = str(v).replace(",", "").strip()
    float(s)
    return s


def _date(v):
    if isinstance(v, datetime):
        v = v.date()
    if isinstance(v, date):
        return v.strftime("%d/%m/%Y"), v.isoformat()
    s = str(v).strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d"):
        try:
            d = datetime.strptime(s, fmt).date()
            return d.strftime("%d/%m/%Y"), d.isoformat()
        except ValueError:
            pass
    raise ValueError("not a date (use DD/MM/YYYY)")


def _option(f, v):
    s = str(v).strip()
    if not f["options"]:
        return s  # options load on the portal later: matched by text there
    for o in f["options"]:
        if s.casefold() in (str(o["text"]).casefold(), str(o["value"]).casefold()):
            return o["value"]
    for o in f["options"]:  # long option texts: allow a clear prefix either way
        t = str(o["text"]).casefold().strip()
        if len(s) >= 12 and (t.startswith(s.casefold()) or s.casefold().startswith(t)):
            return o["value"]
    raise ValueError("not one of the allowed values in column G")


def convert(f, v):
    """Excel cell value -> plan entry fields for this field type. Raises ValueError (message has no client value)."""
    t = f["type"]
    if t == "number":
        try:
            return {"value": _num_str(v)}
        except ValueError:
            raise ValueError("not a number")
    if t == "date":
        disp, iso = _date(v)
        return {"value": disp, "iso": iso}
    if t in ("dropdown", "radio"):
        return {"value": _option(f, v), "display": str(v).strip()}
    if t == "checkbox":
        if not f["options"]:
            return {"value": str(v).strip().lower() in ("yes", "y", "true", "1", "x", "✓")}
        if len(f["options"]) <= 1:
            yes = str(v).strip().lower() in ("yes", "y", "true", "1", "x", "✓")
            return {"value": [f["options"][0]["value"]] if (yes and f["options"]) else []}
        return {"value": [_option(f, p) for p in str(v).split(",") if p.strip()]}
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if isinstance(v, (datetime, date)):
        v = v.strftime("%d/%m/%Y")
    return {"value": str(v).strip()}


def make_plan(xlsx, slug):
    xlsx = Path(xlsx)
    wb = openpyxl.load_workbook(xlsx, data_only=True)
    if "Meta" not in wb.sheetnames:
        raise ValueError(f"{xlsx.name} is not an MCA inputs workbook (no Meta sheet)")
    sheets = [(n, k, g) for n, s, k, g in wb["Meta"].iter_rows(min_row=2, values_only=True) if s == slug]
    if not sheets:
        raise ValueError(f"{xlsx.name} has no {form_name(slug)} sheet: rebuild it after dumping {form_name(slug)}")
    sc = schema(slug)
    by_key = {f["key"]: f for f in sc["fields"]}
    tables = {t["groupKey"]: t for t in sc["tables"]}
    plan = {"client": xlsx.parent.name, "workbook": xlsx.name, "slug": slug, "form": form_name(slug),
            "generatedAt": datetime.now().isoformat(timespec="seconds"), "fields": [], "tables": [], "errors": [], "save": True}

    mp = read_map(slug)

    def entry(f, v):
        e = {k: f.get(k) for k in ("code", "key", "domBase", "som", "type", "label", "sectionText")}
        e.update(convert(f, v))
        # Previous-year figures: the extension keeps whatever MCA pre-filled.
        if (mp.get(f["key"]) or {}).get("period") == "PY" or re.search(r"previous", f.get("som") or "", re.I):
            e["prev"] = True
        return e

    for name, kind, gkey in sheets:
        ws = wb[name]
        if kind == "form":
            for row in ws.iter_rows(min_row=4, values_only=True):
                key, v = (row[8] if len(row) > 8 else None), row[5]
                if not key or v is None or str(v).strip() == "":
                    continue
                f = by_key.get(key)
                if not f or f["type"] == "file":
                    continue  # read-only fields are checked live on the portal, not here
                if len(row) > 9 and row[9]:
                    e = {k: f.get(k) for k in ("code", "key", "domBase", "som", "type", "label", "sectionText")}
                    e.update(value="", copyFrom=row[9])
                    plan["fields"].append(e)
                    continue
                try:
                    plan["fields"].append(entry(f, v))
                except ValueError as e:
                    plan["errors"].append({"code": f["code"], "key": key, "label": f["label"], "msg": f"Excel: {e}"})
        else:
            t = tables.get(gkey)
            if not t:
                continue
            fmap = {f["key"]: f for f in t["fields"]}
            keys = [c.value for c in ws[4]]
            rows = []
            for row in ws.iter_rows(min_row=5, values_only=True):
                cells = []
                for k, v in zip(keys, row):
                    if not k or k not in fmap or v is None or str(v).strip() == "":
                        continue
                    f = fmap[k]
                    try:
                        c = entry(f, v)
                        c.update(relSom=f["repeat"]["relSom"], row=len(rows))
                        cells.append(c)
                    except ValueError as e:
                        plan["errors"].append({"code": f["code"], "key": k, "label": f"{t['title']} row {len(rows) + 1}: {f['label']}", "msg": f"Excel: {e}"})
                if cells:
                    rows.append(cells)
            if rows:
                plan["tables"].append({"groupKey": gkey, "groupSom": t["groupSom"], "title": t["title"], "max": t["max"],
                                       "section": t["section"], "rows": rows})
    if slug == "aoc4":
        # Column-head dates of the financial statements: the financial year from the general section.
        have = {e["code"]: e for e in plan["fields"]}
        by_code = {f["code"]: f for f in sc["fields"]}
        for code, src in (("AOC4-079", "AOC4-012"),):
            if code not in have and src in have and code in by_code:
                f = by_code[code]
                e = {k: f.get(k) for k in ("code", "key", "domBase", "som", "type", "label", "sectionText")}
                e.update(convert(f, have[src]["value"]))
                plan["fields"].append(e)
    return plan


# ---------------------------------------------------------------- server

def _adt1():
    """ADT-1 lives in ADT1/adt1.py (one workbook, many companies)."""
    sys.path.insert(0, str(ROOT / "ADT1"))
    import adt1
    return adt1


def state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def set_state(**kw):
    s = state()
    s.update(kw)
    STATE.write_text(json.dumps(s, indent=1), encoding="utf-8")


def client_folders():
    CLIENTS.mkdir(exist_ok=True)
    return sorted(p for p in CLIENTS.iterdir() if p.is_dir())


def inputs_of(folder):
    p = Path(folder) / f"{Path(folder).name} - MCA inputs.xlsx"
    return p if p.exists() else None


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def dashboard(msg=""):
    active = state().get("active", "")
    rows = []
    for d in client_folders():
        inp = inputs_of(d)
        fs = find_schedule3(d)
        rel = str(d.relative_to(ROOT))
        is_active = inp and str(inp.relative_to(ROOT)) == active
        rows.append(
            f"<tr{' class=active' if is_active else ''}><td><b>{esc(d.name)}</b></td>"
            f"<td>{esc(fs.name) if fs else '<i>no Schedule III file</i>'}</td>"
            f"<td>{esc(inp.name) if inp else '<i>not built</i>'}</td><td>"
            f"<form method=post action=/build><input type=hidden name=folder value=\"{esc(rel)}\"><button>Build / refresh inputs</button></form> "
            + (f"<form method=post action=/active><input type=hidden name=path value=\"{esc(str(inp.relative_to(ROOT)))}\">"
               f"<button {'disabled' if is_active else ''}>{'Active' if is_active else 'Use for filling'}</button></form>" if inp else "")
            + "</td></tr>")
    dumps = []
    for p in sorted(DUMPS.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            mp = map_path(p.stem)
            dumps.append(f"<tr><td>{esc(form_name(p.stem))}</td><td>{len(d.get('fields', []))}</td><td>{esc(d.get('source'))}</td>"
                         f"<td>{esc(d.get('capturedAt', ''))[:16]}</td><td>{'mapping/' + esc(mp.name) if mp.exists() else '-'}</td>"
                         f"<td>{len(d.get('pages', []))}: {esc(', '.join(d.get('pages', [])))[:160]}</td>"
                         f"<td><form method=post action=/forget onsubmit=\"return confirm('Forget this form and capture every page again?')\">"
                         f"<input type=hidden name=slug value={esc(p.stem)}><button>Start capture again</button></form></td></tr>")
        except Exception:  # noqa: BLE001
            continue
    return f"""<!doctype html><html><head><meta charset=utf-8><title>MCA filler</title><style>
body{{font:14px Segoe UI,Arial,sans-serif;margin:24px;color:#102a43}} table{{border-collapse:collapse;margin:8px 0 24px}}
td,th{{border:1px solid #bcccdc;padding:6px 10px;text-align:left;vertical-align:middle}} th{{background:#d9e2ec}}
tr.active td{{background:#e3f9e5}} form{{display:inline}} button{{padding:4px 10px}} .msg{{background:#fff3c4;padding:8px 12px;white-space:pre-wrap}}
</style></head><body><p><a href="/">&larr; Filing app</a></p><h2>MCA form filler: forms &amp; settings</h2>
<p><a href="/adt1">ADT-1 for many companies &rarr;</a></p>
{f'<div class=msg>{esc(msg)}</div>' if msg else ''}
<p>Active inputs workbook (used by Alt+Shift+F): <b>{esc(active) or 'none'}</b></p>
<h3>Clients</h3><p>One folder per client under <code>{esc(CLIENTS)}</code>, holding that client's Schedule III workbook.</p>
<form method=post action=/newclient>New client folder: <input name=name size=40> <button>Create</button></form>
<table><tr><th>Client</th><th>Schedule III workbook</th><th>MCA inputs</th><th></th></tr>{''.join(rows) or '<tr><td colspan=4>none yet</td></tr>'}</table>
<h3>Captured forms</h3><table><tr><th>Form</th><th>Fields</th><th>Read via</th><th>Captured</th><th>Mapping</th><th>Pages captured</th><th></th></tr>{''.join(dumps) or '<tr><td colspan=7>none yet: open a form on MCA and press Alt+Shift+D</td></tr>'}</table>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (datetime.now().strftime("%H:%M:%S"), fmt % args))

    def _send(self, code, body, ctype="application/json"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj))

    def _file(self, p):
        data = Path(p).read_bytes()
        self.send_response(200)
        ctype = {".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                 ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}.get(Path(p).suffix.lower(), "application/octet-stream")
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + quote(Path(p).name))
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _body(self):
        if not hasattr(self, "_raw"):  # read once: the app and the old dashboard both look at it
            n = int(self.headers.get("Content-Length") or 0)
            self._raw = self.rfile.read(n) if n else b""
        return self._raw

    def _form(self):
        return {k: v[0] for k, v in parse_qs(self._body().decode("utf-8")).items()}

    def _redirect_msg(self, msg):
        self._send(200, dashboard(msg), "text/html")

    def do_GET(self):
        u = urlsplit(self.path)
        try:
            got = ff_ui.handle_get(u.path, parse_qs(u.query))  # Form Filler: /, /data, /review, /file, /agents, /audit
        except Exception as e:  # noqa: BLE001
            got = 500, f"<pre>Form Filler error: {esc(e)}</pre>", "text/html"
        if got:
            code, body, ctype = got
            if isinstance(body, tuple) and body[0] == "FILE":
                return self._file(body[1])
            return self._send(code, body, ctype)
        got = app.handle_get(u.path, parse_qs(u.query))  # filing app: /client, /api/panel
        if got:
            return self._send(*got)
        if u.path == "/admin":
            return self._send(200, dashboard(), "text/html")
        if u.path == "/adt1":  # ADT-1 for many companies (ADT1/adt1.py)
            return self._send(200, _adt1().page(), "text/html")
        if u.path == "/adt1/file":  # one attachment PDF, base64 in JSON, for the extension to upload
            q = parse_qs(u.query)
            try:
                return self._json(200, _adt1().attachment_json((q.get("cin") or [""])[0], (q.get("kind") or [""])[0]))
            except Exception as e:  # noqa: BLE001
                return self._json(404, {"error": str(e)})
        if u.path == "/plan":
            slug = (parse_qs(u.query).get("slug") or [""])[0].lower()
            if slug.startswith("adt"):
                try:
                    return self._json(200, _adt1().make_plan(slug))
                except PermissionError:
                    return self._json(409, {"error": "ADT-1 companies.xlsx is locked: save it in Excel and try again"})
                except Exception as e:  # noqa: BLE001
                    return self._json(400, {"error": str(e)})
            try:  # filing queue running: the job's plan, with the loop flags
                qp = app._queue().plan(slug)
            except Exception as e:  # noqa: BLE001
                return self._json(409, {"error": str(e)})
            if qp:
                return self._json(200, qp)
            active = state().get("active")
            if not active:
                return self._json(404, {"error": "no active client: open http://127.0.0.1:8742 and click 'Use for filling'"})
            try:
                return self._json(200, make_plan(ROOT / active, slug))
            except PermissionError:
                return self._json(409, {"error": "the inputs workbook is locked: save it in Excel and try again"})
            except Exception as e:  # noqa: BLE001
                return self._json(400, {"error": str(e)})
        self._json(404, {"error": "not found"})

    def do_POST(self):
        u = urlsplit(self.path)
        body = self._body()
        lists = parse_qs(body.decode("utf-8", "replace")) if "form-urlencoded" in (self.headers.get("Content-Type") or "") else {}
        form = {k: v[0] for k, v in lists.items()}
        form["_forms"] = lists.get("forms", [])
        form["_lists"] = lists
        got = ff_ui.handle_post(u.path, parse_qs(u.query), body, form) or \
            app.handle_post(u.path, parse_qs(u.query), body, form)  # Form Filler /ff/..., filing app /app/..., /api/active
        if got:
            code, text, ctype, location = got
            if location:
                self.send_response(code)
                self.send_header("Location", location)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            return self._send(code, text, ctype)
        if u.path.startswith("/adt1/"):
            return self._send(200, _adt1().handle(u.path, self._form()), "text/html")
        try:
            if u.path == "/dump":
                d = json.loads(self._body())
                slug = re.sub(r"[^a-z0-9_-]", "", str(d.get("slug", "form")).lower()) or "form"
                DUMPS.mkdir(exist_ok=True)
                (DUMPS / "archive").mkdir(exist_ok=True)
                (DUMPS / "archive" / f"{slug}_{datetime.now():%Y%m%d_%H%M%S}.json").write_text(json.dumps(d, indent=1), encoding="utf-8")
                merged, added = merge_dump(slug, d)
                (DUMPS / f"{slug}.json").write_text(json.dumps(merged, indent=1), encoding="utf-8")
                note = ""
                try:
                    p, n, hits = build_map(slug)
                    note = f"; mapping {p.name}: {hits}/{n} number fields suggested"
                except Exception as e:  # noqa: BLE001
                    note = f"; mapping not built: {e}"
                if slug.startswith("adt"):
                    try:
                        _, n_, hits_ = _adt1().build_columns()
                        note += f"; ADT-1 column map: {hits_}/{n_} fields matched"
                    except Exception as e:  # noqa: BLE001
                        note += f"; ADT-1 column map not built: {e}"
                print(f"dump saved: {slug} page {d.get('pagesOnScreen')} +{added} fields, total {len(merged['fields'])}, via {d.get('source')}{note}")
                return self._json(200, {"ok": True, "added": added, "total": len(merged["fields"]), "pages": len(merged.get("pages", []))})
            if u.path == "/log":
                log = json.loads(self._body())
                act = state().get("active")
                folder = (ROOT / act).parent / "logs" if act else ROOT / "logs"
                if str(log.get("slug", "")).startswith("adt"):
                    folder = ROOT / "ADT1" / "logs"
                folder.mkdir(parents=True, exist_ok=True)
                p = folder / f"fill_{log.get('slug', 'form')}_{datetime.now():%Y%m%d_%H%M%S}.json"
                p.write_text(json.dumps(log, indent=1), encoding="utf-8")
                print(f"fill log saved: {p.relative_to(ROOT)}  {log.get('counts')}")
                try:
                    c = log.get("counts") or {}
                    if act and not str(log.get("slug", "")).startswith("adt"):
                        ff_audit.event((ROOT / act).parent, "fill", f"{form_name(log.get('slug', ''))}: {c.get('filled', 0)} fields filled"
                                       + (f", {c['failed']} failed" if c.get("failed") else "")
                                       + (" and the section saved" if (log.get("save") or {}).get("clicked") else ""),
                                       form=log.get("slug"), counts=c, by="agent")
                except Exception:  # noqa: BLE001
                    pass
                return self._json(200, {"ok": True})
            if u.path == "/active":
                path = self._form().get("path", "")
                if not (ROOT / path).exists():
                    return self._redirect_msg("That workbook does not exist.")
                set_state(active=path)
                return self._redirect_msg(f"Active: {path}")
            if u.path == "/forget":
                slug = re.sub(r"[^a-z0-9_-]", "", self._form().get("slug", ""))
                (DUMPS / f"{slug}.json").unlink(missing_ok=True)
                return self._redirect_msg(f"Forgot {form_name(slug)}. Press Alt+Shift+D on each of its pages again (archive copies are kept).")
            if u.path == "/newclient":
                name = re.sub(r'[<>:"/\\|?*]', "", self._form().get("name", "")).strip()
                if not name:
                    return self._redirect_msg("Give the client a name.")
                (CLIENTS / name).mkdir(parents=True, exist_ok=True)
                return self._redirect_msg(f"Created {CLIENTS / name}. Put the client's Schedule III workbook in it, then click Build.")
            if u.path == "/build":
                folder = ROOT / self._form().get("folder", "")
                out, problems, fs_error = build_workbook(folder)
                msg = f"Built {out.relative_to(ROOT)}."
                if fs_error:
                    msg += f"\nSchedule III not used: {fs_error}"
                if problems:
                    msg += f"\n{len(problems)} figures could not be pulled (orange cells; see the Info sheet)."
                return self._redirect_msg(msg)
        except Exception as e:  # noqa: BLE001
            if u.path in ("/dump", "/log"):
                return self._json(500, {"error": str(e)})
            return self._redirect_msg(f"Error: {e}")
        self._json(404, {"error": "not found"})


def serve(open_browser=True, lan=False):
    sys.stdout.reconfigure(line_buffering=True)
    srv = ThreadingHTTPServer(("0.0.0.0" if lan else "127.0.0.1", PORT), Handler)
    print(f"Form Filler on http://127.0.0.1:{PORT}" + (f"  (office LAN: http://<this PC's IP>:{PORT})" if lan else "") + "  (Ctrl+C to stop)")
    ff_jobs.recover()
    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(f"http://127.0.0.1:{PORT}")).start()
    print("Screens: /data  /review  /file  /agents  /audit   Older screens: /filings  /admin  /adt1  /ai")
    srv.serve_forever()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve")
    s.add_argument("--no-browser", action="store_true")
    s.add_argument("--lan", action="store_true", help="also serve other PCs on the office LAN")
    m = sub.add_parser("map")
    m.add_argument("slug")
    w = sub.add_parser("workbook")
    w.add_argument("folder")
    w.add_argument("--forms", nargs="*")
    p = sub.add_parser("plan")
    p.add_argument("xlsx")
    p.add_argument("slug")
    p.add_argument("-o", "--out")
    a = ap.parse_args()
    if a.cmd == "serve":
        serve(not a.no_browser, a.lan)
    elif a.cmd == "map":
        path, n, hits = build_map(a.slug)
        print(f"{path}: {n} number fields, {hits} with a source expression")
    elif a.cmd == "workbook":
        out, problems, fs_error = build_workbook(a.folder, a.forms)
        print(f"built {out}")
        if fs_error:
            print("Schedule III not used:", fs_error)
        for line in problems:
            print("  FS:", line)
    elif a.cmd == "plan":
        plan = make_plan(a.xlsx, a.slug)
        out = Path(a.out or Path(a.xlsx).with_name(f"plan_{a.slug}.json"))
        out.write_text(json.dumps(plan, indent=1), encoding="utf-8")
        print(f"{out}: {len(plan['fields'])} fields, {len(plan['tables'])} tables, {len(plan['errors'])} errors")


if __name__ == "__main__":
    main()
