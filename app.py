"""Filing app: the staff-facing flow on http://127.0.0.1:8742.

One filing per client folder, four steps:
  1. Details    CIN, financial year, which forms (AOC-4, MGT-7A, ADT-1)
  2. Uploads    this year's Schedule III workbook, last year's filed AOC-4 / MGT-7A PDFs, other files
  3. Questions  the few things only staff know; everything else comes from the uploads
  4. Fill       mark the client for filling, then use the Chrome side panel on MCA

The filing's settings live in clients/<name>/filing.json. The inputs workbook, the Schedule III
reader, last year's PDF readers and the fill plan are the existing ones in mca.py.
mca.py routes "/", "/client", "/app/..." and "/api/..." here; the old dashboard is at /admin.
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import openpyxl

import lastyear
from schedule3 import FSError, Schedule3, find_schedule3

ROOT = Path(__file__).resolve().parent
CLIENTS = ROOT / "clients"
FORMS = [("aoc4", "AOC-4", "Financial statements"), ("mgt7a", "MGT-7A", "Annual return (small company / OPC)"),
         ("adt-1", "ADT-1", "Auditor appointment")]
FORM_LABEL = {s: n for s, n, _ in FORMS}
SMART = ("aoc4", "mgt7a")  # forms built from the inputs workbook; ADT-1 has its own companies list
MUST = ("agm_date", "board_meetings", "resolution_date", "board_fs_date", "auditor_report_date", "ca_cop")
CIN_RE = re.compile(r"\b([UL]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6})\b")
UPLOADS = {  # kind: (title, what, accepted extensions)
    "fs": ("This year's financial statements", "Schedule III workbook (.xlsx with BS, PL and Notes sheets; rounding divisor 1)", (".xlsx",)),
    "ly_aoc4": ("Last year's filed AOC-4", "PDF downloaded from MCA. Carries forward auditor, signatories, previous-year figures", (".pdf",)),
    "ly_mgt7a": ("Last year's filed MGT-7A", "PDF downloaded from MCA. Carries forward activity, shareholding, directors, meetings", (".pdf",)),
    "other": ("Other files", "Last year's MCA Excel attachments (board meetings, members' meetings, shareholder list) and anything else", None),
}
MAX_UPLOAD = 60 * 1024 * 1024


def _mca():
    import mca  # mca.py runs as __main__; this import gives the same functions
    return mca


def _queue():
    import filing_queue
    return filing_queue


def _adt1():
    sys.path.insert(0, str(ROOT / "ADT1"))
    import adt1
    return adt1


# ---------------------------------------------------------------- filing state

def folder_of(name):
    """Client folder for a name typed or posted by the browser; never outside clients/."""
    name = re.sub(r'[<>:"/\\|?*]', "", str(name or "")).strip().rstrip(".")
    if not name:
        raise ValueError("no client name")
    p = (CLIENTS / name).resolve()
    if p.parent != CLIENTS.resolve():
        raise ValueError("bad client name")
    return p


def load(folder):
    p = Path(folder) / "filing.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        # Clients set up before the app: their inputs workbook says which forms they have.
        if inputs_path(folder).exists():
            try:
                wb = openpyxl.load_workbook(inputs_path(folder), read_only=True)
                forms = sorted({r[1] for r in wb["Meta"].iter_rows(min_row=2, values_only=True) if r[1] in SMART})
                return {"forms": forms, "fy_end": "31/03/2026", "cin": ""}
            except Exception:  # noqa: BLE001
                pass
        return {}


def save(folder, **kw):
    d = load(folder)
    d.update(kw, updated=datetime.now().isoformat(timespec="seconds"))
    d.setdefault("created", d["updated"])
    (Path(folder) / "filing.json").write_text(json.dumps(d, indent=1), encoding="utf-8")
    return d


def inputs_path(folder):
    return Path(folder) / f"{Path(folder).name} - MCA inputs.xlsx"


def active_folder():
    act = _mca().state().get("active")
    return (ROOT / act).parent.resolve() if act else None


def guess_cin(folder):
    for finder in (lastyear.find_last_aoc4, lastyear.find_last_mgt7a):
        p = finder(folder)
        if not p:
            continue
        try:
            import pdfplumber
            with pdfplumber.open(p) as pdf:
                m = CIN_RE.search(pdf.pages[0].extract_text() or "")
            if m:
                return m.group(1)
        except Exception:  # noqa: BLE001
            continue
    return ""


_cache = {}


def _cached(kind, p, fn):
    """fn() remembered until the file at p changes (Schedule III workbooks take a second or two to open)."""
    try:
        st = Path(p).stat()
    except OSError:
        return fn()
    key = (kind, str(p))
    hit = _cache.get(key)
    if hit and hit[0] == (st.st_mtime, st.st_size):
        return hit[1]
    val = fn()
    _cache[key] = ((st.st_mtime, st.st_size), val)
    return val


def fs_status(folder):
    """(path or None, problem text or '', checks list)."""
    p = find_schedule3(folder)
    if not p:
        return None, "", []

    def read():
        try:
            return p, "", Schedule3(p).checks()
        except FSError as e:
            return p, str(e), []
    return _cached("fs", p, read)


def questions(folder):
    """Questions sheet of the inputs workbook: [(key, question, how, answer, came_from)] and the notes below it."""
    p = inputs_path(folder)
    if not p.exists():
        return [], {}
    return _cached("q", p, lambda: _read_questions(p))


def _read_questions(p):
    wb = openpyxl.load_workbook(p, data_only=True)
    if "Questions" not in wb.sheetnames:
        return [], {}
    qs, notes, head = [], {}, None
    for row in wb["Questions"].iter_rows(min_row=4, values_only=True):
        row = list(row) + [None] * 5
        if row[0]:
            ans = row[3]
            if hasattr(ans, "strftime"):
                ans = ans.strftime("%d/%m/%Y")
            qs.append((row[0], row[1] or "", row[2] or "", "" if ans is None else str(ans), row[4] or ""))
        elif row[1]:
            text = str(row[1])
            if text in ("Still to answer", "Do by hand on the portal") or text.startswith("Attachments prepared"):
                head = text
                notes[head] = []
            elif head:
                notes[head].append(text)
    return qs, notes


def blanks(folder, slug):
    """Mandatory yellow cells still empty on a form sheet of the inputs workbook: [(code, section, label)]."""
    p = inputs_path(folder)
    wb = openpyxl.load_workbook(p, data_only=True)
    meta = [n for n, s, k, g in wb["Meta"].iter_rows(min_row=2, values_only=True) if s == slug and k == "form"]
    out = []
    for name in meta:
        for row in wb[name].iter_rows(min_row=4):
            if len(row) < 9 or not row[8].value or row[4].value != "*" or row[5].value not in (None, ""):
                continue
            note = str(row[7].value or "")
            if note.startswith(("Pre-filled", "Attachment")):
                continue
            out.append((row[0].value, row[1].value, row[2].value))
    return out


def plan_stats(folder, slug):
    plan = _mca().make_plan(inputs_path(folder), slug)
    cells = sum(len(r) for t in plan["tables"] for r in t["rows"])
    return {"fields": len(plan["fields"]), "cells": cells, "errors": plan["errors"]}


def last_logs(folder):
    out = {}
    for p in sorted((Path(folder) / "logs").glob("fill_*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            out[d.get("slug")] = (d.get("finishedAt", "")[:16].replace("T", " "), d.get("counts") or {})
        except Exception:  # noqa: BLE001
            continue
    return out


def adt1_row(cin):
    """The client's row in the ADT-1 companies list, or None."""
    if not cin:
        return None
    a = _adt1()
    defaults, companies = a.read_book()
    for c in companies:
        if str(c.get("cin", "")).upper() == cin.upper():
            vals, _ = a.resolve(c, defaults)
            need = ("category", "memno", "aud_name", "aud_pan", "agm_date", "period_from", "period_to", "res_no", "res_date", "sign_din")
            return {"row": c, "missing": [a.HEADERS[k] for k in need if vals.get(k) in (None, "")],
                    "attachments": len(a.attachments_of(c)), "need_attachments": len(a.ATTACH),
                    "current": str(a.state().get("current", "")).upper() == cin.upper()}
    return None


def steps(folder):
    """Done flags for the four steps, plus what each is waiting on."""
    f = load(folder)
    forms = f.get("forms") or []
    smart = [s for s in forms if s in SMART]
    d1 = bool(f.get("cin") and forms)
    fs, fs_err, _ = fs_status(folder)
    d2 = not smart or bool(fs and not fs_err)
    built = inputs_path(folder).exists()
    qs, _ = questions(folder) if built else ([], {})
    open_q = [q for k, q, _, a, _ in qs if k in MUST and not a.strip()]
    d3 = not smart or (built and not open_q)
    act = active_folder()
    d4 = bool(smart and act == Path(folder).resolve())
    return {"details": d1, "uploads": d2, "questions": d3, "fill": d4, "open_q": open_q, "built": built}


# ---------------------------------------------------------------- pages

CSS = """
:root{--background:oklch(0.985 0.004 95);--foreground:oklch(0.235 0.014 260);--surface:oklch(0.972 0.005 95);--card:oklch(1 0 0);
--primary:oklch(0.285 0.038 258);--primary-foreground:oklch(0.985 0.004 95);--secondary:oklch(0.955 0.006 95);--secondary-foreground:oklch(0.3 0.02 258);
--muted:oklch(0.957 0.005 95);--muted-foreground:oklch(0.53 0.014 258);--accent:oklch(0.94 0.012 95);--brass:oklch(0.62 0.086 76);--brass-foreground:oklch(0.99 0.004 95);
--destructive:oklch(0.52 0.176 27);--success:oklch(0.49 0.088 158);--warning:oklch(0.68 0.126 72);--warning-foreground:oklch(0.24 0.03 72);--info:oklch(0.5 0.07 245);
--border:oklch(0.905 0.006 95);--border-strong:oklch(0.84 0.008 95);--input:oklch(0.888 0.007 95);--ring:oklch(0.62 0.086 76);
--sidebar:oklch(0.256 0.024 258);--sidebar-foreground:oklch(0.87 0.01 95);--sidebar-accent:oklch(0.31 0.026 258);--sidebar-accent-foreground:oklch(0.97 0.005 95);--sidebar-border:oklch(0.34 0.022 258);
--shadow-xs:0 1px 2px 0 rgb(0 0 0 / 0.05);--shadow-panel:0 1px 2px oklch(0.25 0.02 260 / 0.05),0 8px 24px -16px oklch(0.25 0.02 260 / 0.25);
--shadow-raised:0 1px 2px oklch(0.25 0.02 260 / 0.06),0 18px 40px -24px oklch(0.25 0.02 260 / 0.35);
/* legacy names still used by inline styles */--ink:var(--foreground);--line:var(--border);--go:var(--success);--bad:var(--destructive)}
*{box-sizing:border-box}html{scroll-behavior:smooth}
body{margin:0;font:14px/20px "IBM Plex Sans",ui-sans-serif,system-ui,sans-serif;font-feature-settings:"cv05","ss01";-webkit-font-smoothing:antialiased;color:var(--foreground);background:var(--background)}
a{color:var(--primary)}h1,h2,h3{letter-spacing:-0.014em}
code,.mono{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:13px}.numeric,.kpi .v,td{font-variant-numeric:tabular-nums}
:focus-visible{outline:2px solid var(--ring);outline-offset:2px}
/* sidebar + top bar */
aside.side{position:fixed;inset:0 auto 0 0;width:240px;background:var(--sidebar);color:var(--sidebar-foreground);display:flex;flex-direction:column;z-index:30}
.brandrow{height:64px;display:flex;align-items:center;gap:10px;padding:0 16px;border-bottom:1px solid var(--sidebar-border);text-decoration:none;color:var(--sidebar-accent-foreground)}
.tile{width:32px;height:32px;border-radius:6px;background:var(--brass);color:var(--brass-foreground);display:grid;place-items:center;font-weight:600;font-size:15px;flex:none}
.brandrow b{display:block;font-size:14px;font-weight:600;line-height:18px}.brandrow small{display:block;font-size:11px;line-height:16px;opacity:.75}
aside nav{padding:12px 8px;display:flex;flex-direction:column;gap:2px}
aside nav a{display:flex;align-items:center;gap:10px;padding:8px 12px;border-radius:7px;color:var(--sidebar-foreground);opacity:.75;text-decoration:none;font-size:14px;transition:background .15s,opacity .15s}
aside nav a:hover{opacity:1;background:var(--sidebar-accent)}aside nav a.on{opacity:1;background:var(--sidebar-accent);color:var(--sidebar-accent-foreground);font-weight:500}
aside nav a.on::after{content:"";margin-left:auto;width:6px;height:6px;border-radius:50%;background:var(--brass)}
aside svg,.ico{width:16px;height:16px;flex:none}
.sidefoot{margin-top:auto;padding:14px 16px;border-top:1px solid var(--sidebar-border);font-size:12px;line-height:16px;opacity:.75}
.sidefoot .label{font-size:11px;font-weight:600;letter-spacing:.09em;text-transform:uppercase;color:var(--brass);opacity:1;margin-bottom:4px}
.wrap{margin-left:240px;min-height:100vh;display:flex;flex-direction:column}
.topbar{position:sticky;top:0;z-index:20;height:64px;display:flex;align-items:center;gap:12px;padding:0 32px;border-bottom:1px solid var(--border);background:oklch(0.985 0.004 95 / 0.85);backdrop-filter:blur(8px)}
.topbar .trail{font-size:14px;color:var(--muted-foreground)}.topbar .trail b{color:var(--foreground);font-weight:500}
.live{margin-left:auto;display:flex;align-items:center;gap:8px;font-size:12px;color:var(--muted-foreground);border:1px solid var(--border);background:var(--card);padding:5px 10px;border-radius:6px;box-shadow:var(--shadow-xs)}
.live i{width:7px;height:7px;border-radius:50%;background:var(--success);animation:pulse 2.4s ease-in-out infinite}
@keyframes pulse{0%,100%{box-shadow:0 0 0 0 oklch(0.49 0.088 158 / .45)}50%{box-shadow:0 0 0 5px oklch(0.49 0.088 158 / 0)}}
main{width:100%;max-width:1400px;margin:0 auto;padding:32px 32px 40px;flex:1}
footer{border-top:1px solid var(--border);padding:16px 32px;color:var(--muted-foreground);font-size:12px;display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap}
@keyframes rise{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important;scroll-behavior:auto!important}}
/* page header + metrics */
.phead{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;flex-wrap:wrap;padding-bottom:24px;margin-bottom:24px;border-bottom:1px solid var(--border)}
.phead h1{font-size:28px;line-height:34px;font-weight:600;margin:0}.phead p{margin:6px 0 0;color:var(--muted-foreground);max-width:720px}
.eyebrow{font-size:11px;line-height:16px;font-weight:600;letter-spacing:.09em;text-transform:uppercase;color:var(--muted-foreground);margin-bottom:6px;display:flex;align-items:center;gap:8px}
.eyebrow::before{content:"";width:16px;height:2px;background:var(--brass)}
.kpis{display:grid;grid-template-columns:1fr;gap:16px;margin-bottom:24px}
@media (min-width:640px){.kpis{grid-template-columns:repeat(2,1fr)}}@media (min-width:1280px){.kpis{grid-template-columns:repeat(4,1fr)}}
.kpi{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:20px;box-shadow:var(--shadow-xs);animation:rise .35s ease both}
.kpi:nth-child(2){animation-delay:.04s}.kpi:nth-child(3){animation-delay:.08s}.kpi:nth-child(4){animation-delay:.12s}
.kpi .l{font-size:11px;line-height:16px;font-weight:600;letter-spacing:.09em;text-transform:uppercase;color:var(--muted-foreground);display:flex;align-items:center;gap:8px}
.kpi .l .ico{color:var(--brass)}.kpi .v{font-size:30px;line-height:36px;font-weight:600;margin-top:10px}.kpi .s{font-size:12px;color:var(--muted-foreground);margin-top:2px}
/* cards */
.card{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:20px 24px;margin-bottom:20px;box-shadow:var(--shadow-xs);animation:rise .35s ease both}
.card h2{font-size:16px;line-height:24px;font-weight:600;margin:0 0 14px;display:flex;align-items:center;gap:10px}
.num{display:inline-flex;width:28px;height:28px;border-radius:6px;background:var(--secondary);border:1px solid var(--border-strong);color:var(--secondary-foreground);align-items:center;justify-content:center;font-size:13px;font-weight:600;flex:none}
.num.done{background:var(--success);border-color:var(--success);color:var(--primary-foreground)}
.step.done{border-color:oklch(0.49 0.088 158 / .35)}
.msg{background:oklch(0.68 0.126 72 / .12);border:1px solid oklch(0.68 0.126 72 / .45);color:var(--warning-foreground);padding:12px 16px;border-radius:8px;margin-bottom:20px;white-space:pre-wrap;animation:rise .3s ease both}
.err{color:var(--destructive)}.ok{color:var(--success);font-weight:500}.warn{color:var(--warning-foreground);font-weight:500}.muted{color:var(--muted-foreground);font-size:13px}
table{border-collapse:separate;border-spacing:0;width:100%}td,th{border-bottom:1px solid var(--border);padding:12px 10px;text-align:left;vertical-align:top}
th{font-size:11px;line-height:16px;color:var(--muted-foreground);font-weight:600;text-transform:uppercase;letter-spacing:.09em;background:var(--surface);padding-top:12px;padding-bottom:12px}
tr:last-child td{border-bottom:0}table tr:hover td{background:var(--muted)}
input[type=text],select{font:inherit;height:36px;padding:0 12px;border:1px solid var(--border-strong);border-radius:7px;width:100%;background:var(--card);color:var(--foreground);box-shadow:var(--shadow-xs);transition:border-color .15s}
input[type=text]:focus,select:focus{outline:2px solid var(--ring);outline-offset:2px;border-color:var(--ring)}
input[type=checkbox]{accent-color:var(--primary);width:16px;height:16px;vertical-align:-3px}
label.muted{display:block;font-size:11px;line-height:16px;font-weight:600;letter-spacing:.09em;text-transform:uppercase;margin-bottom:6px}
button,.btn{font:inherit;font-weight:500;height:36px;padding:0 16px;border-radius:7px;border:1px solid var(--border-strong);background:var(--card);color:var(--foreground);cursor:pointer;text-decoration:none;display:inline-flex;align-items:center;gap:8px;box-shadow:var(--shadow-xs);transition:background .15s,border-color .15s}
button:hover:not(:disabled),.btn:hover{background:var(--accent)}
button.primary,.btn.primary,button.go{background:var(--primary);color:var(--primary-foreground);border-color:var(--primary)}
button.primary:hover:not(:disabled),.btn.primary:hover,button.go:hover:not(:disabled){background:oklch(0.33 0.04 258)}
button.go{height:40px;padding:0 20px}button.go::before{content:"";width:8px;height:8px;border-radius:50%;background:var(--brass)}
button:disabled{opacity:.5;cursor:not-allowed}form{margin:0}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:12px}
.drop{border:1px dashed var(--border-strong);border-radius:8px;padding:16px 16px 14px 60px;min-height:120px;position:relative;background:var(--surface);transition:border-color .15s,background .15s}
.drop::before{content:"";position:absolute;left:16px;top:16px;width:32px;height:32px;border-radius:6px;background:var(--card);border:1px solid var(--border)}
.drop::after{content:"";position:absolute;left:24px;top:24px;width:16px;height:16px;background:var(--primary);-webkit-mask:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4'/%3E%3Cpolyline points='17 8 12 3 7 8'/%3E%3Cline x1='12' x2='12' y1='3' y2='15'/%3E%3C/svg%3E") center/contain no-repeat;mask:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4'/%3E%3Cpolyline points='17 8 12 3 7 8'/%3E%3Cline x1='12' x2='12' y1='3' y2='15'/%3E%3C/svg%3E") center/contain no-repeat}
.drop:hover{border-color:var(--primary);background:var(--card)}.drop.hover{border-color:var(--ring);background:oklch(0.62 0.086 76 / .07)}
.drop:has(.file.ok){border-style:solid;border-color:oklch(0.49 0.088 158 / .4);background:var(--card)}
.drop:has(.file.ok)::before{background:var(--success);border-color:var(--success)}
.drop:has(.file.ok)::after{background:var(--primary-foreground);-webkit-mask-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M20 6 9 17l-5-5'/%3E%3C/svg%3E");mask-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M20 6 9 17l-5-5'/%3E%3C/svg%3E")}
.drop b{display:block;font-weight:600;margin-bottom:2px}.drop .file{margin-top:8px;font-size:13px;word-break:break-word}
.drop input{position:absolute;inset:0;opacity:0;cursor:pointer;z-index:2}
.tag{display:inline-flex;font-size:12px;font-weight:500;padding:2px 8px;border-radius:6px;border:1px solid var(--border-strong);background:var(--muted);color:var(--secondary-foreground)}
.tag.sug{background:oklch(0.5 0.07 245 / .08);border-color:oklch(0.5 0.07 245 / .3);color:var(--info)}
.tag.you{background:oklch(0.49 0.088 158 / .08);border-color:oklch(0.49 0.088 158 / .3);color:var(--success)}
.tag.need{background:oklch(0.52 0.176 27 / .07);border-color:oklch(0.52 0.176 27 / .3);color:var(--destructive)}
.clients td{vertical-align:middle}
.pill{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:500;padding:2px 8px;border-radius:6px;border:1px solid var(--border-strong);background:var(--muted);color:var(--secondary-foreground)}
.pill::before{content:"";width:6px;height:6px;border-radius:50%;background:currentColor}
.pill.on{background:oklch(0.49 0.088 158 / .08);border-color:oklch(0.49 0.088 158 / .3);color:var(--success)}.pill.on::before{animation:pulse 2s ease-in-out infinite}
.pill.bad{background:oklch(0.52 0.176 27 / .07);border-color:oklch(0.52 0.176 27 / .3);color:var(--destructive)}
.pill.sub{background:oklch(0.5 0.07 245 / .08);border-color:oklch(0.5 0.07 245 / .3);color:var(--info)}
details summary{cursor:pointer;color:var(--muted-foreground);margin-top:10px;font-weight:500}details summary:hover{color:var(--primary)}
ol.how li{margin:6px 0}
.bar{height:6px;border-radius:3px;background:var(--muted);border:1px solid var(--border);overflow:hidden;width:120px;margin-bottom:4px}
.bar i{display:block;height:100%;background:var(--primary);transition:width .6s ease}.bar.full i{background:var(--success)}
.how4{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}
.how4>div{border:1px solid var(--border);border-radius:8px;padding:16px;background:var(--surface)}
.how4 .num{margin-bottom:10px}.how4>div>b{display:block;font-weight:600;margin-bottom:4px}.how4 p{margin:0;color:var(--muted-foreground);font-size:13px}
.guard{margin-top:14px;padding:12px 16px;border-radius:8px;background:var(--surface);border:1px solid var(--border);font-size:13px;color:var(--secondary-foreground);display:flex;gap:10px;align-items:center}
.guard .ico{color:var(--brass)}
/* client page */
.chead .meta{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px}
.chead .meta span{font-size:12px;font-weight:500;padding:2px 8px;border-radius:6px;background:var(--card);border:1px solid var(--border-strong)}
.chead .meta span.mono{font-size:12px}
.prog{min-width:200px}.prog .l{font-size:11px;font-weight:600;letter-spacing:.09em;text-transform:uppercase;color:var(--muted-foreground)}
.prog .v{font-size:30px;line-height:36px;font-weight:600}.prog .bar{width:200px}
.stepper{display:flex;margin:0 0 20px;background:var(--card);border:1px solid var(--border);border-radius:8px;padding:12px 16px;box-shadow:var(--shadow-panel);position:sticky;top:76px;z-index:10}
.stepper a{flex:1;display:flex;align-items:center;gap:10px;text-decoration:none;color:var(--muted-foreground);font-weight:500;font-size:14px}
.stepper a:not(:last-child)::after{content:"";flex:1;height:1px;background:var(--border-strong);margin:0 12px}
.stepper a.done{color:var(--foreground)}.stepper a.done:not(:last-child)::after{background:var(--success)}
.stepper a.cur{color:var(--foreground)}.stepper a.cur .num{background:var(--card);border:2px solid var(--brass);color:var(--foreground)}
.stepper .num{width:26px;height:26px;font-size:12px}
@media (max-width:1023px){aside.side{position:static;width:auto;flex-direction:row;align-items:center;flex-wrap:wrap}.brandrow{border:0}aside nav{flex-direction:row;padding:8px;overflow:auto}
.sidefoot{display:none}.wrap{margin-left:0}.topbar{display:none}main{padding:24px 16px}.stepper{position:static;flex-wrap:wrap;gap:8px}.stepper a:not(:last-child)::after{display:none}}
"""


def esc(s):
    return str("" if s is None else s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def shell(title, body, msg=""):
    return f"""<!doctype html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>{esc(title)} · N K Lodha &amp; Co</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin="anonymous">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:ital,wght@0,400;0,500;0,600;1,400&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>{CSS}</style></head><body>
<aside class=side><a class=brandrow href="/"><span class=tile>N</span><span><b>ROC Autopilot</b><small>N K Lodha &amp; Co</small></span></a>
<nav><a href="/"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M16 13H8"/><path d="M16 17H8"/><path d="M10 9H8"/></svg>Filings</a><a href="/adt1"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="16" height="20" x="4" y="2" rx="2"/><path d="M9 22v-4h6v4"/><path d="M8 6h.01M16 6h.01M12 6h.01M12 10h.01M12 14h.01M16 10h.01M16 14h.01M8 10h.01M8 14h.01"/></svg>ADT-1 companies</a><a href="/admin"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 4h-7M10 4H3M21 12h-9M8 12H3M21 20h-5M12 20H3M14 2v4M8 10v4M16 18v4"/></svg>Forms &amp; settings</a><a href="/ai"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="16" height="16" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M9 1v3M15 1v3M9 20v3M15 20v3M20 9h3M20 14h3M1 9h3M1 14h3"/></svg>Local AI</a></nav>
<div class=sidefoot><div class=label>Human in the loop</div>Login, captcha, Submit, DSC and payment stay with your team.</div></aside>
<div class=wrap><div class=topbar><span class=trail>ROC filings / <b>{esc(title)}</b></span><span class=live><i></i>Live on office LAN · port 8742</span></div>
<main>{f'<div class=msg>{esc(msg)}</div>' if msg else ''}{body}</main>
<footer><span>N K Lodha &amp; Co · Chartered Accountants, Chennai</span><span>AOC-4 · MGT-7A · ADT-1 on MCA V3</span></footer></div>
<script>{{const p=location.pathname;for(const a of document.querySelectorAll('aside nav a')){{const h=a.getAttribute('href');if(h==='/'?(p==='/'||p.startsWith('/client')):p.startsWith(h))a.classList.add('on')}}}}for(const el of document.querySelectorAll('[data-count]')){{const t=+el.dataset.count;if(!t||matchMedia('(prefers-reduced-motion: reduce)').matches)continue;let s=null;const f=n=>{{s=s||n;const p=Math.min(1,(n-s)/800);el.textContent=Math.round(t*(1-Math.pow(1-p,3))).toLocaleString('en-IN');if(p<1)requestAnimationFrame(f)}};requestAnimationFrame(f)}}</script>
</body></html>"""


ON = '<span class="pill on">Filling now</span>'
HINT = "<div class=muted>Read from last year's form: check it.</div>"


def home(msg=""):
    act = active_folder()
    rows = []
    CLIENTS.mkdir(exist_ok=True)
    for d in sorted(p for p in CLIENTS.iterdir() if p.is_dir()):
        f = load(d)
        st = steps(d)
        done = sum(st[k] for k in ("details", "uploads", "questions", "fill"))
        forms = ", ".join(FORM_LABEL.get(s, s) for s in f.get("forms") or []) or "<span class=muted>not set</span>"
        rows.append(f"<tr><td><a href=\"/client?c={quote(d.name)}\"><b>{esc(d.name)}</b></a><br><span class=muted>{esc(f.get('cin', ''))}</span></td>"
                    f"<td>{forms}</td><td><div class=\"bar{' full' if done == 4 else ''}\"><i style=\"width:{done * 25}%\"></i></div><span class=muted>{done} of 4 steps</span></td>"
                    f"<td>{ON if act == d.resolve() else ''}</td>"
                    f"<td><a class=btn href=\"/client?c={quote(d.name)}\">Open</a></td></tr>")
    n_cl = len(rows)
    n_forms = sum(len(load(d).get("forms") or []) for d in CLIENTS.iterdir() if d.is_dir())
    try:
        jobs = _queue().load()["jobs"]
    except Exception:  # noqa: BLE001
        jobs = []
    n_q = sum(1 for j in jobs if j.get("status") in ("queued", "filling"))
    n_sub = sum(1 for j in jobs if j.get("status") == "submitted" and not j.get("paid"))
    head = f"""<div class=phead><div><div class=eyebrow>MCA V3 · AI-assisted</div><h1>ROC filings</h1>
<p>AOC-4 and MGT-7A built from this year's Schedule III and last year's filed forms. The tool carries forward what didn't change, asks only what did, and fills the portal section by section.</p></div></div>
<div class=kpis><div class=kpi><div class=l>Clients</div><div class=v data-count={n_cl}>{n_cl}</div><div class=s>with a filing folder</div></div>
<div class=kpi><div class=l>Forms set up</div><div class=v data-count={n_forms}>{n_forms}</div><div class=s>AOC-4, MGT-7A, ADT-1</div></div>
<div class=kpi><div class=l>In the queue</div><div class=v data-count={n_q}>{n_q}</div><div class=s>waiting or filling now</div></div>
<div class=kpi><div class=l>Before payment</div><div class=v data-count={n_sub}>{n_sub}</div><div class=s>submitted, to review and pay</div></div></div>"""
    body = head + f"""<div class=card><h2>New filing</h2>
<form method=post action=/app/new style="display:flex;gap:10px;align-items:center">
<input type=text name=name placeholder="Client name, as you want the folder called" required style="max-width:420px">
<button class=primary>Start</button></form>
<p class=muted style="margin:8px 0 0">Creates a folder under {esc(CLIENTS)}. If the folder already exists, it is opened.</p></div>
{_queue().section()}
<div class=card><h2>Clients</h2><table class=clients><tr><th>Client</th><th>Forms</th><th>Progress</th><th></th><th></th></tr>
{''.join(rows) or '<tr><td colspan=5 class=muted>None yet.</td></tr>'}</table></div>
<div class=card><h2>How it works</h2><div class=how4>
<div><span class=num>1</span><b>Details</b><p>CIN, year and the forms to file.</p></div>
<div><span class=num>2</span><b>Uploads</b><p>This year's Schedule III workbook and last year's filed forms. These fill most of every form.</p></div>
<div><span class=num>3</span><b>Questions</b><p>A short list only you can answer (dates of meetings, changes during the year). Suggestions are pre-filled.</p></div>
<div><span class=num>4</span><b>Fill</b><p>One client: <i>Start filling</i>, then <b>Form Filler</b> in the Chrome side panel. Many: add them to the <b>Filing queue</b> and the tool fills, saves and moves page by page, then opens the next client.</p></div></div>
<div class=guard><svg class=ico viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/></svg><span>Login, captcha, Submit, DSC and payment always stay with your team. The tool never submits or pays.</span></div></div>"""
    return shell("MCA filing", body, msg)


def _step(n, title, done, inner):
    return f"<div class=\"card step{' done' if done else ''}\" id=s{n}><h2><span class=\"num{' done' if done else ''}\">{'&#10003;' if done else n}</span>{esc(title)}</h2>{inner}</div>"


def client_page(name, msg=""):
    folder = folder_of(name)
    if not folder.exists():
        return home(f"No client folder called {name}.")
    f = load(folder)
    st = steps(folder)
    forms = f.get("forms") or []
    smart = [s for s in forms if s in SMART]
    cin = f.get("cin") or ""
    q = quote(folder.name)

    # 1. details
    cin_hint = "" if cin else guess_cin(folder)
    boxes = "".join(f"<label style=\"display:block;margin:4px 0\"><input type=checkbox name=forms value=\"{s}\" {'checked' if s in forms else ''}> "
                    f"<b>{n}</b> <span class=muted>{esc(t)}</span></label>" for s, n, t in FORMS)
    s1 = f"""<form method=post action=/app/details><input type=hidden name=c value="{esc(folder.name)}">
<div class=grid><div><label class=muted>CIN</label><input type=text name=cin value="{esc(cin or cin_hint)}" placeholder="U12345TN2010PTC123456" maxlength=21>
{HINT if cin_hint else ''}</div>
<div><label class=muted>Financial year ended</label><input type=text name=fy_end value="{esc(f.get('fy_end', '31/03/2026'))}"></div>
<div><label class=muted>Prepared by</label><input type=text name=staff value="{esc(f.get('staff', ''))}"></div></div>
<div style="margin:12px 0">{boxes}</div><button class=primary>Save details</button></form>"""

    # 2. uploads
    fs, fs_err, fs_checks = fs_status(folder)
    have = {"fs": fs.name if fs else "", "ly_aoc4": (lastyear.find_last_aoc4(folder) or Path("")).name,
            "ly_mgt7a": (lastyear.find_last_mgt7a(folder) or Path("")).name}
    others = sorted(p.name for p in folder.glob("*.xlsm") if not p.name.startswith("~$"))
    have["other"] = ", ".join(others)
    cards = []
    for kind, (title, what, exts) in UPLOADS.items():
        if kind == "ly_aoc4" and "aoc4" not in forms or kind == "ly_mgt7a" and "mgt7a" not in forms:
            continue
        cur = have.get(kind)
        state = f"<div class=\"file ok\">&#10003; {esc(cur)}</div>" if cur else "<div class=\"file muted\">Drop the file here or click</div>"
        if kind == "fs" and fs_err:
            state += f"<div class=\"file err\">{esc(fs_err)}</div>"
        elif kind == "fs" and fs_checks:
            state += f"<div class=\"file warn\">Checks sheet not OK: {esc('; '.join(fs_checks[:3]))}</div>"
        accept = ",".join(exts) if exts else ""
        cards.append(f"<div class=drop data-kind={kind}><b>{esc(title)}</b><span class=muted>{esc(what)}</span>{state}"
                     f"<input type=file {'multiple' if kind == 'other' else ''} accept=\"{accept}\"></div>")
    q_ = _queue()
    for s in smart:
        have_att = q_.attachment_files(folder, s)
        for el, title, must, _ in q_.ATTACH.get(s, []):
            cur = have_att.get(el)
            state = (f"<div class=\"file ok\">&#10003; {esc(cur.name)}</div>" if cur else
                     "<div class=\"file muted\">Drop the file here or click</div>")
            need = " (needed for the queue)" if must else ""
            cards.append(f"<div class=drop data-kind=\"att_{el}\"><b>{FORM_LABEL[s]}: {esc(title)}</b>"
                         f"<span class=muted>Uploaded on the portal by the tool{need}</span>{state}"
                         f"<input type=file accept=\".pdf,.jpg,.jpeg,.png\"></div>")
    s2 = (f"<div class=grid>{''.join(cards)}</div><p class=muted id=upmsg style=\"margin:10px 0 0\">"
          "Re-uploading replaces the earlier file (kept in the client's _replaced folder).</p>") if smart else \
        "<p class=muted>ADT-1 needs no uploads here: its details and attachments come from the ADT-1 companies list.</p>"

    # 3. questions
    if not smart:
        s3 = "<p class=muted>No questions for ADT-1 alone.</p>"
    elif not st["built"]:
        s3 = (f"<p>Read the uploads and prepare the questions. Most answers come pre-filled.</p>"
              f"<form method=post action=/app/prepare><input type=hidden name=c value=\"{esc(folder.name)}\">"
              f"<button class=primary {'disabled' if not (fs and not fs_err) else ''}>Prepare questions</button>"
              f"{'' if fs and not fs_err else ' <span class=warn>Upload the Schedule III workbook first.</span>'}</form>")
    else:
        qs, notes = questions(folder)
        answered = set(f.get("answered") or [])
        rows = []
        for key, text, how, ans, came in qs:
            opts = re.findall(r"^([A-Za-z]+) / ([A-Za-z]+)$", how.strip())
            if opts:
                choices = [""] + list(opts[0])
                field = f"<select name=\"q_{esc(key)}\">" + "".join(
                    f"<option {'selected' if c.lower() == ans.lower() else ''}>{esc(c)}</option>" for c in choices) + "</select>"
            else:
                field = f"<input type=text name=\"q_{esc(key)}\" value=\"{esc(ans)}\" placeholder=\"{esc(how)}\">"
            tag = ("<span class=\"tag need\">needed</span>" if key in MUST and not ans.strip() else
                   "<span class=\"tag you\">your answer</span>" if key in answered else
                   "<span class=\"tag sug\">suggested</span>" if ans.strip() else "")
            rows.append(f"<tr><td style=\"width:48%\">{esc(text)}<br><span class=muted>{esc(how)}</span></td><td>{field}</td><td style=\"width:90px\">{tag}</td></tr>")
        extra = ""
        for head in ("Do by hand on the portal",):
            items = [x for x in notes.get(head, []) if x]
            if items:
                extra += f"<details><summary>{esc(head)} ({len(items)})</summary><ul>" + "".join(f"<li>{esc(x)}</li>" for x in items) + "</ul></details>"
        made = [k for k in notes if k.startswith("Attachments prepared")]
        if made and notes[made[0]]:
            extra += f"<details><summary>MCA Excel attachments prepared ({len(notes[made[0]])})</summary><ul>" + \
                     "".join(f"<li>{esc(x)}</li>" for x in notes[made[0]]) + "</ul></details>"
        s3 = (f"<form method=post action=/app/answers><input type=hidden name=c value=\"{esc(folder.name)}\">"
              f"<table>{''.join(rows)}</table><p><button class=primary>Save answers and rebuild</button> "
              f"<a class=btn href=\"/ai/questions?c={quote(folder.name)}\">Suggest answers with local AI</a> "
              f"<span class=muted>Workbook: {esc(inputs_path(folder).name)} (close it in Excel before saving).</span></p></form>{extra}")

    # 4. fill
    parts = []
    act = active_folder() == folder.resolve()
    logs = last_logs(folder) if smart else {}
    if smart and st["built"]:
        for s in smart:
            try:
                ps = plan_stats(folder, s)
                bl = blanks(folder, s)
            except Exception as e:  # noqa: BLE001
                parts.append(f"<tr><td><b>{FORM_LABEL[s]}</b></td><td colspan=3 class=err>{esc(e)}</td></tr>")
                continue
            errs = "".join(f"<li>{esc(e['code'])} {esc(e['label'])}: {esc(e['msg'])}</li>" for e in ps["errors"][:15])
            bl_html = (f"<details><summary>{len(bl)} mandatory boxes not in the data (enter on the portal, or type them in the workbook)</summary><ul>"
                       + "".join(f"<li>{esc(c)} {esc(lab)} <span class=muted>{esc(sec)}</span></li>" for c, sec, lab in bl[:60]) + "</ul></details>") if bl else ""
            lg = logs.get(s)
            lg_html = f"<br><span class=muted>Last fill {esc(lg[0])}: " + ", ".join(f"{k} {v}" for k, v in lg[1].items()) + "</span>" if lg else ""
            parts.append(f"<tr><td><b>{FORM_LABEL[s]}</b></td><td>{ps['fields']} fields and {ps['cells']} table cells ready{lg_html}</td>"
                         f"<td>{'<ul class=err>' + errs + '</ul>' if errs else '<span class=ok>no data errors</span>'}{bl_html}</td></tr>")
    fill_tbl = f"<table><tr><th>Form</th><th>Ready to fill</th><th>Check</th></tr>{''.join(parts)}</table>" if parts else ""
    adt = ""
    if "adt-1" in forms:
        try:
            r = adt1_row(cin)
        except Exception as e:  # noqa: BLE001
            r, adt = None, f"<p class=err>ADT-1 list could not be read: {esc(e)}</p>"
        if not adt and not r:
            adt = (f"<p><b>ADT-1</b>: this CIN is not in the ADT-1 companies list yet. Add it on the "
                   f"<a href=/adt1>ADT-1 page</a> (Load master data or Prefill), then come back.</p>")
        elif r:
            miss = (f"<span class=warn>missing: {esc(', '.join(r['missing']))}</span>" if r["missing"] else "<span class=ok>details complete</span>")
            att = f"attachments {r['attachments']} of {r['need_attachments']}"
            adt = (f"<p><b>ADT-1</b>: {esc(r['row'].get('name', ''))}, status {esc(r['row'].get('status') or 'not filed')}; {miss}; {att}.</p>"
                   f"<form method=post action=/app/adt1><input type=hidden name=c value=\"{esc(folder.name)}\">"
                   f"<button class=go {'disabled' if r['current'] else ''}>{'ADT-1 Form Filler is set to this company' if r['current'] else 'Use this company for ADT-1'}</button></form>")
    start = ""
    if smart:
        ready = st["built"]
        start = (f"<form method=post action=/app/start style=\"margin:12px 0\"><input type=hidden name=c value=\"{esc(folder.name)}\">"
                 f"<button class=go {'disabled' if act or not ready else ''}>{'Filling this client now' if act else 'Start filling'}</button> "
                 f"{'' if ready else '<span class=warn>Finish the questions first.</span>'}"
                 f"{'<span class=warn> Still needed: ' + esc('; '.join(st['open_q'])) + '</span>' if st['open_q'] and ready else ''}</form>")
    s4 = f"""{fill_tbl}{start}{adt}
<ol class=how><li>In the MCA Chrome window, log in and open this client's draft for the form.</li>
<li>Click the <b>MCA filler</b> icon in the Chrome toolbar to open the side panel. Check it shows <b>{esc(folder.name)}</b>.</li>
<li>Click <b>Form Filler</b>. The tool fills one section and outlines that section's Save in red: you click Save.</li>
<li>Click Form Filler again for each section and page. Upload attachments, Pre-scrutiny, DSC and Submit yourself.</li></ol>
<p class=muted>New or changed MCA form? Open the blank draft and click <b>Save form</b> in the side panel on each page.</p>"""

    flags = [st["details"], st["uploads"] and st["details"], st["questions"] and st["built"], st["fill"]]
    names = ["Details", "Upload data", "Questions", "Fill on MCA"]
    cur = next((i for i, x in enumerate(flags) if not x), None)
    stepper = "<nav class=stepper>" + "".join(
        f"<a href=#s{i + 1} class=\"{'done' if x else 'cur' if i == cur else ''}\"><span class=\"num{' done' if x else ''}\">{'&#10003;' if x else i + 1}</span>{nm}</a>"
        for i, (x, nm) in enumerate(zip(flags, names))) + "</nav>"
    n_done = sum(flags)
    meta = ((f"<span class=mono>{esc(cin)}</span>" if cin else "") + (f"<span>FY ended {esc(f.get('fy_end'))}</span>" if f.get("fy_end") else "")
            + "".join(f"<span>{FORM_LABEL.get(s, s)}</span>" for s in forms))
    head = (f"<div class=\"phead chead\"><div><div class=eyebrow><a href=/ style=\"color:inherit;text-decoration:none\">&larr; All filings</a></div>"
            f"<h1>{esc(folder.name)}</h1><div class=meta>{meta}</div></div>"
            f"<div class=prog><div class=l>Progress</div><div class=v>{n_done} of 4</div><div class=\"bar{' full' if n_done == 4 else ''}\"><i style=\"width:{n_done * 25}%\"></i></div></div></div>{stepper}")
    body = (head
            + _step(1, "Details", st["details"], s1) + _step(2, "Upload data", st["uploads"] and st["details"], s2)
            + _step(3, "Answer the questions", st["questions"] and st["built"], s3) + _step(4, "Fill on MCA", st["fill"], s4)
            + UPLOAD_JS.replace("__CLIENT__", json.dumps(folder.name)))
    return shell(folder.name, body, msg)


UPLOAD_JS = """<script>
(() => {
  const client = __CLIENT__;
  const msg = document.getElementById('upmsg');
  async function send(kind, files) {
    for (const f of files) {
      if (msg) msg.textContent = 'Uploading ' + f.name + '…';
      const r = await fetch('/app/upload?c=' + encodeURIComponent(client) + '&kind=' + kind + '&name=' + encodeURIComponent(f.name), { method: 'POST', body: f });
      let d = {}; try { d = await r.json(); } catch (e) {}
      if (!r.ok) { if (msg) { msg.textContent = 'Upload failed: ' + (d.error || r.status); msg.className = 'err'; } return; }
    }
    location.href = '/client?c=' + encodeURIComponent(client) + '&msg=' + encodeURIComponent('Uploaded. The questions are rebuilt when you click Prepare / Save answers.') + '#s2';
  }
  for (const box of document.querySelectorAll('.drop')) {
    const inp = box.querySelector('input');
    inp.addEventListener('change', () => inp.files.length && send(box.dataset.kind, [...inp.files]));
    box.addEventListener('dragover', e => { e.preventDefault(); box.classList.add('hover'); });
    box.addEventListener('dragleave', () => box.classList.remove('hover'));
    box.addEventListener('drop', e => { e.preventDefault(); box.classList.remove('hover'); send(box.dataset.kind, [...e.dataTransfer.files]); });
  }
})();
</script>"""


# ---------------------------------------------------------------- actions

def _move_aside(folder, p):
    """Keep a replaced file in _replaced/ under a name the finders ignore."""
    aside = Path(folder) / "_replaced"
    aside.mkdir(exist_ok=True)
    p.rename(aside / f"{p.name}.{datetime.now():%Y%m%d_%H%M%S}.old")


def upload(name, kind, filename, data):
    folder = folder_of(name)
    if not folder.exists():
        raise ValueError("no such client")
    if len(data) > MAX_UPLOAD:
        raise ValueError("file is larger than 60 MB")
    if kind.startswith("att_"):
        dest = _queue().store_attachment(folder, kind[4:], filename, data)
        return {"ok": True, "saved": dest.name}
    if kind not in UPLOADS:
        raise ValueError("unknown upload kind")
    filename = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", Path(filename).name).strip() or "upload"
    ext = Path(filename).suffix.lower()
    exts = UPLOADS[kind][2]
    if exts and ext not in exts:
        raise ValueError(f"expected a {' or '.join(exts)} file")
    if kind == "fs":
        if "mca inputs" in filename.lower():
            raise ValueError("that is the tool's own inputs workbook, not the Schedule III workbook")
        old = find_schedule3(folder)
        if old:
            _move_aside(folder, old)
    elif kind in ("ly_aoc4", "ly_mgt7a"):
        finder = lastyear.find_last_aoc4 if kind == "ly_aoc4" else lastyear.find_last_mgt7a
        old = finder(folder)
        if old:
            _move_aside(folder, old)
        tag = "AOC-4" if kind == "ly_aoc4" else "MGT-7A"
        if not re.search(r"aoc[-_ ]?4" if kind == "ly_aoc4" else r"mgt[-_ ]?7a", filename, re.I):
            filename = f"Last year {tag} - {filename}"
    dest = folder / filename
    if dest.exists():
        _move_aside(folder, dest)
    dest.write_bytes(data)
    out = {"ok": True, "saved": dest.name}
    if kind == "fs":
        _, err, checks = fs_status(folder)
        out.update(problem=err, checks=checks)
    return out


def build(folder):
    f = load(folder)
    slugs = [s for s in (f.get("forms") or []) if s in SMART and (ROOT / "dumps" / f"{s}.json").exists()]
    if not slugs:
        raise ValueError("pick AOC-4 or MGT-7A in Details first (and capture the form once with Save form)")
    out, problems, fs_error = _mca().build_workbook(folder, slugs)
    msg = f"Prepared {out.name}."
    if fs_error:
        msg += f"\nSchedule III not used: {fs_error}"
    if problems:
        msg += f"\n{len(problems)} figures could not be pulled from the Schedule III workbook (see the Info sheet)."
    return msg


def save_answers(folder, form):
    p = inputs_path(folder)
    wb = openpyxl.load_workbook(p)
    ws = wb["Questions"]
    changed = []
    for row in ws.iter_rows(min_row=4):
        key = row[0].value
        if key and f"q_{key}" in form:
            val = form[f"q_{key}"].strip()
            cur = row[3].value
            cur = cur.strftime("%d/%m/%Y") if hasattr(cur, "strftime") else str(cur if cur is not None else "")
            if cur != val:
                row[3].value = val or None
                row[4].value = "your answer"
                changed.append(key)
    try:
        wb.save(p)
    except PermissionError:
        raise PermissionError(f"{p.name} is open in Excel: close it and click Save again")
    save(folder, answered=sorted(set(load(folder).get("answered") or []) | set(changed)))
    return len(changed)


def handle_get(path, query):
    """(status, body, content type) or None when the path is not the app's."""
    q = {k: v[0] for k, v in query.items()}
    if path.startswith("/ai"):
        import ai
        return ai.handle_get(path, q)
    if path == "/":
        return 200, home(q.get("msg", "")), "text/html"
    if path == "/client":
        try:
            return 200, client_page(q.get("c", ""), q.get("msg", "")), "text/html"
        except Exception as e:  # noqa: BLE001
            return 200, home(f"Error: {e}"), "text/html"
    if path == "/queue/file":
        try:
            return 200, json.dumps(_queue().file_json(q.get("job"), q.get("el"))), "application/json"
        except Exception as e:  # noqa: BLE001
            return 404, json.dumps({"error": str(e)}), "application/json"
    if path == "/api/panel":
        m = _mca()
        act = active_folder()
        clients = []
        for d in sorted(p for p in CLIENTS.iterdir() if p.is_dir()):
            f = load(d)
            clients.append({"name": d.name, "cin": f.get("cin", ""), "forms": [s for s in f.get("forms") or [] if s in SMART],
                            "inputs": inputs_path(d).exists(), "active": act == d.resolve()})
        adt = {}
        try:
            a = _adt1()
            cur = a.state().get("current", "")
            if cur:
                _, comps = a.read_book()
                c = next((c for c in comps if str(c.get("cin", "")).upper() == str(cur).upper()), {})
                adt = {"current": cur, "name": c.get("name", "")}
        except Exception:  # noqa: BLE001
            pass
        q_, job = _queue().current()
        queue = {"running": q_["running"], "waiting": sum(1 for j in q_["jobs"] if j["status"] == "queued"),
                 "job": {"client": job["client"], "slug": job["slug"], "form": FORM_LABEL.get(job["slug"], job["slug"])} if job else None,
                 "submit": q_["submit"]}
        return 200, json.dumps({"active": act.name if act else "", "clients": clients, "adt1": adt, "queue": queue,
                                "forms": sorted(p.stem for p in (ROOT / "dumps").glob("*.json"))}), "application/json"
    return None


def handle_post(path, query, body, form):
    """(status, body, content type, location or None) or None when the path is not the app's."""
    q = {k: v[0] for k, v in query.items()}
    if path.startswith("/ai/"):
        import ai
        return ai.handle_post(path, form)

    def back(name, msg, anchor=""):
        return 303, "", "text/html", f"/client?c={quote(name)}&msg={quote(msg)}{anchor}"

    if path == "/app/upload":
        try:
            return 200, json.dumps(upload(q.get("c", ""), q.get("kind", ""), q.get("name", ""), body)), "application/json", None
        except PermissionError:
            return 409, json.dumps({"error": "a file with that name is open in Excel: close it and try again"}), "application/json", None
        except Exception as e:  # noqa: BLE001
            return 400, json.dumps({"error": str(e)}), "application/json", None
    if path in ("/queue/advance", "/api/queue/start", "/api/queue/pause"):
        try:
            Q = _queue()
            if path == "/queue/advance":
                out = Q.advance(json.loads(body or b"{}"))
            elif path == "/api/queue/start":
                job = Q.start()
                out = {"job": job} if job else {"job": None, "error": "nothing waiting in the queue"}
            else:
                Q.pause()
                out = {"ok": True}
            return 200, json.dumps(out), "application/json", None
        except Exception as e:  # noqa: BLE001
            return 400, json.dumps({"error": str(e)}), "application/json", None
    if path.startswith("/queue/"):
        Q = _queue()
        msg = ""
        try:
            if path == "/queue/add":
                pairs = [tuple(x.split("|", 1)) for x in form.get("_lists", {}).get("job", []) if "|" in x]
                added, refused = Q.add(pairs)
                msg = f"Added {added} to the queue."
                for c, s, why in refused:
                    msg += f"\nNot added, {c} {FORM_LABEL.get(s, s)}: {'; '.join(why)}"
            elif path == "/queue/start":
                job = Q.start()
                msg = (f"Queue running. Open MCA (logged in), open the side panel and click Start the queue there, "
                       f"or open {FORM_LABEL.get(job['slug'], job['slug'])} and click Form Filler." if job else "Nothing waiting in the queue.")
            elif path == "/queue/pause":
                Q.pause()
                msg = "The queue stops after the client being filled now."
            elif path == "/queue/submit":
                qq = Q.load()
                qq["submit"] = form.get("on") == "1"
                Q.save(qq)
                msg = "Submit at the end: " + ("on" if qq["submit"] else "off (each form stops after its last Save)")
            elif path == "/queue/edit":
                msg = Q.edit(form) or "Updated."
        except Exception as e:  # noqa: BLE001
            msg = f"Error: {e}"
        return 303, "", "text/html", f"/?msg={quote(msg)}#queue"
    if path == "/api/active":
        try:
            d = json.loads(body or b"{}")
            folder = folder_of(d.get("client", ""))
            inp = inputs_path(folder)
            if not inp.exists():
                raise ValueError("that client has no inputs workbook yet: answer its questions in the filing app")
            _mca().set_state(active=str(inp.relative_to(ROOT)))
            return 200, json.dumps({"ok": True}), "application/json", None
        except Exception as e:  # noqa: BLE001
            return 400, json.dumps({"error": str(e)}), "application/json", None
    if not path.startswith("/app/"):
        return None
    name = form.get("c") or form.get("name") or ""
    try:
        if path == "/app/new":
            folder = folder_of(name)
            folder.mkdir(parents=True, exist_ok=True)
            if not load(folder):
                save(folder, forms=["aoc4", "mgt7a"], fy_end="31/03/2026", cin="")
            return back(folder.name, "Fill the details, then upload the data.", "#s1")
        folder = folder_of(name)
        if path == "/app/details":
            cin = form.get("cin", "").strip().upper()
            if cin and not CIN_RE.fullmatch(cin):
                return back(folder.name, "That CIN does not look right (21 characters, e.g. U12345TN2010PTC123456).", "#s1")
            save(folder, cin=cin, fy_end=form.get("fy_end", "").strip(), staff=form.get("staff", "").strip(),
                 forms=[s for s, _, _ in FORMS if s in form.get("_forms", [])])
            return back(folder.name, "Details saved.", "#s2")
        if path == "/app/prepare":
            return back(folder.name, build(folder) + "\nNow answer the questions below.", "#s3")
        if path == "/app/answers":
            n = save_answers(folder, form)
            msg = build(folder)
            return back(folder.name, f"{n} answers saved. {msg}", "#s3" if steps(folder)["open_q"] else "#s4")
        if path == "/app/start":
            inp = inputs_path(folder)
            if not inp.exists():
                return back(folder.name, "Prepare the questions first.", "#s3")
            _mca().set_state(active=str(inp.relative_to(ROOT)))
            return back(folder.name, f"Form Filler now uses {folder.name}. Open the draft on MCA and use the side panel.", "#s4")
        if path == "/app/adt1":
            cin = load(folder).get("cin", "")
            if not cin:
                return back(folder.name, "Enter the CIN in Details first.", "#s1")
            if not adt1_row(cin):
                return back(folder.name, "This CIN is not in the ADT-1 companies list yet: add it on the ADT-1 page.", "#s4")
            _adt1().set_current(cin)
            return back(folder.name, "ADT-1 Form Filler now uses this company.", "#s4")
    except PermissionError as e:
        return back(name, str(e))
    except Exception as e:  # noqa: BLE001
        return back(name, f"Error: {e}") if name else (303, "", "text/html", f"/?msg={quote('Error: ' + str(e))}")
    return None
