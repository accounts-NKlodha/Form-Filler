import csv, sys
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.comments import Comment
from openpyxl.utils import get_column_letter

import json, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mapping import HEADS, LINES, SIGN, G_DEF, L_BASE, resolve, line_of
import present as P

# usage: build_sch3.py <client_config.json> <tb_cy.csv> <tb_py.csv or -> <out.xlsx>
CFG = json.load(open(sys.argv[1], encoding="utf-8"))
SRC = sys.argv[2]
PYSRC = sys.argv[3] if sys.argv[3] != "-" else ""
OUT = sys.argv[4]
ROWS_CY = list(csv.DictReader(open(SRC, encoding="utf-8")))
ROWS_PY = list(csv.DictReader(open(PYSRC, encoding="utf-8"))) if PYSRC else []
TB_ROWS = max(len(ROWS_CY), len(ROWS_PY)) + 500

F = "Arial"
f_base = Font(name=F, size=10)
f_b = Font(name=F, size=10, bold=True)
f_title = Font(name=F, size=13, bold=True)
f_sub = Font(name=F, size=10, italic=True, color="555555")
f_in = Font(name=F, size=10, color="0000FF")
f_link = Font(name=F, size=10, color="008000")
f_hdr = Font(name=F, size=10, bold=True, color="FFFFFF")
fill_hdr = PatternFill("solid", fgColor="1F3864")
fill_sec = PatternFill("solid", fgColor="D9E1F2")
fill_in = PatternFill("solid", fgColor="FFF2CC")
fill_ok = PatternFill("solid", fgColor="E2EFDA")
thin = Side(style="thin", color="999999")
b_top = Border(top=thin)
b_tot = Border(top=thin, bottom=Side(style="double", color="000000"))
NUM = '#,##0.00;(#,##0.00);"-"'

def setw(ws, widths):
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w

def hdr(ws, row, vals, col=1):
    for i, v in enumerate(vals):
        c = ws.cell(row=row, column=col + i, value=v)
        c.font = f_hdr; c.fill = fill_hdr
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

wb = Workbook()

# ---------------------------------------------------------------- Heads (engine/mapping.py, labels per client config)
HEADS = [(c, l, st, CFG.get("head_labels", {}).get(c, lab), sg) for c, l, st, lab, sg in HEADS]
SIGN = {h[0]: h[4] for h in HEADS}
HIDE = {"Notes": [], "BS": [], "PL": []}
SUBROWS = []   # (row, [cols]) in Notes - hidden after caching when all zero

# ---------------------------------------------------------------- Map_Groups
G_CLIENT = [tuple(g) for g in CFG.get("groups", [])]
L_OVR = [tuple(l) for l in L_BASE] + [tuple(l) for l in CFG.get("ledgers", []) if l[0].lower() != "profit & loss a/c"]
GROUPS_ALL = G_CLIENT + G_DEF

# Lines nil in both years: rows hidden and no note number (formulas kept; rebuild if a balance appears)
_amt = {}
for rows_, cols in ((ROWS_CY, ("closing_balance", "opening_balance")), (ROWS_PY, ("closing_balance",))):
    for x in rows_:
        for col in cols:
            v = float(x[col] or 0)
            code = resolve(x["ledger_name"], x["group_name"], x["primary_group"], v, L_OVR, GROUPS_ALL)
            if code and abs(v) > 0.004:
                _amt[line_of(code)] = 1
                _amt[code] = 1
ALWAYS = {"SC", "RS"}
SKIP = {ln for ln in LINES if ln not in _amt and ln not in ALWAYS} | {"EXC", "EXO"}
if "INV" in SKIP: SKIP.add("CHINV")
else: SKIP.discard("CHINV")
_lt = CFG.get("setup", {})
if any(float(_lt.get(k) or 0) for k in ("Long-term portion of loans from related parties (Rs) - current year",
                                         "Long-term portion of loans from related parties (Rs) - previous year")):
    SKIP.discard("LTB"); _amt["LTB.UNSRP"] = 1
USED_CODES = set(k for k in _amt if "." in k)

# ---------------------------------------------------------------- Setup
ws = wb.active; ws.title = "Setup"
setw(ws, [44, 44, 4, 70])
ws["A1"] = "Schedule III Financial Statements - Tally to Excel"; ws["A1"].font = f_title
ws["A2"] = "Companies Act, 2013 - Schedule III Division I (non-Ind AS). N K Lodha & Co template. Built by the Schedule III app - edit inputs here or in the app."; ws["A2"].font = f_sub
from setup_fields import FIELDS as inputs
r = 4
hdr(ws, r, ["Input", "Value", "", "Note / source"]); r += 1
SETUP = CFG.get("setup", {}); SETUP_NOTES = CFG.get("setup_notes", {})
DEFAULTS = {"Rounding divisor (1 = Rs, 1000 = Rs '000, 100000 = Rs lakhs)": 1, "Amount label": "Amount in Rs",
            "Long-term portion of loans from related parties (Rs) - current year": 0,
            "Long-term portion of loans from related parties (Rs) - previous year": 0}
inputs = [(k, None if v is None else SETUP.get(k, DEFAULTS.get(k, "")), n if v is None else SETUP_NOTES.get(k, "")) for k, v, n in inputs]
INP = {}
for k, v, n in inputs:
    if v is None:
        r += 1; ws.cell(row=r, column=1, value=k).font = f_b; ws.cell(row=r, column=4, value=n).font = f_sub; r += 1; continue
    ws.cell(row=r, column=1, value=k).font = f_base
    c = ws.cell(row=r, column=2, value=v); c.font = f_in; c.fill = fill_in
    if isinstance(v, (int, float)): c.number_format = NUM
    ws.cell(row=r, column=4, value=n).font = f_sub
    INP[k] = f"Setup!$B${r}"; r += 1
UNIT = INP["Rounding divisor (1 = Rs, 1000 = Rs '000, 100000 = Rs lakhs)"]
CO = INP["Company name"]; CYD = INP["Current year - balance sheet date"]; PYD = INP["Previous year - balance sheet date"]
LBL = INP["Amount label"]
_LTC = INP["Long-term portion of loans from related parties (Rs) - current year"]
_LTP = INP["Long-term portion of loans from related parties (Rs) - previous year"]
ADJ = {"LTB.UNSRP": (f"+N({_LTC})", f"+N({_LTP})"), "STB.RP": (f"-N({_LTC})", f"-N({_LTP})")}
# Client-approved previous-year reclasses that keep the signed PY presentation: [from code, to code, amount in Rs, reason]
for _f, _t, _a, *_ in CFG.get("py_reclass", []):
    for _c, _s in ((_f, "-"), (_t, "+")):
        _x = ADJ.get(_c, ("", ""))
        ADJ[_c] = (_x[0], _x[1] + f"{_s}{float(_a)}")
r += 1
ws.cell(row=r, column=1, value="How to refresh each year / for a new client").font = f_b; r += 1
steps = [
 "1. In Tally Prime: F1 Help > Settings > Connectivity > TallyPrime acts as Server, port 9000. Open the company.",
 "2. Ask Claude in this project to refresh: it pulls the ledger-wise Trial Balance via the Tally connector and pastes it into TB_CY (and the previous-year company's TB into TB_PY).",
 "   Manual route: paste a ledger-wise TB into TB_CY columns A:G. Sign convention: Debit = negative, Credit = positive.",
 "3. Open the Checks sheet. Every line must read OK.",
 "4. Filter TB_CY column S for 'MAP!' and add the group to Map_Groups or the ledger to Map_Ledgers. Do not edit formulas in TB columns H:S.",
 "5. Review the Review Points sheet, then print BS, PL and Notes.",
 "New client: save a copy, clear TB_CY / TB_PY columns A:G, delete the rows marked 'Client group' in Map_Groups and the client rows in Map_Ledgers, then pull.",
]
for s in steps:
    ws.cell(row=r, column=1, value=s).font = f_base; r += 1
r += 1
ws.cell(row=r, column=1, value="Legend").font = f_b; r += 1
c = ws.cell(row=r, column=1, value="Blue on yellow = input cell (edit)"); c.font = f_in; c.fill = fill_in; r += 1
ws.cell(row=r, column=1, value="Black = formula (do not edit)").font = f_base; r += 1
ws.cell(row=r, column=1, value="Green = link from another sheet").font = f_link; r += 1

# ---------------------------------------------------------------- Heads sheet
wh = wb.create_sheet("Heads")
setw(wh, [14, 8, 6, 46, 70, 6])
hdr(wh, 1, ["Sub-head code", "Line", "Stmt", "Sch III line item", "Note sub-head", "Sign"])
for i, (code, line, st, lab, sg) in enumerate(HEADS, 2):
    for j, v in enumerate([code, line, st, LINES[line], lab, sg], 1):
        wh.cell(row=i, column=j, value=v).font = f_base
wh.cell(row=len(HEADS) + 3, column=1, value="Sign: +1 = credit-nature (liability / income), -1 = debit-nature (asset / expense). Used for contra-balance reclassification.").font = f_sub
wh.freeze_panes = "A2"
# Heads layout: A code, B line, C stmt, D line label, E sub label, F sign
HEAD_SIGN_COL = "F"

# ---------------------------------------------------------------- Map_Groups
wg = wb.create_sheet("Map_Groups")
setw(wg, [36, 16, 16, 60])
hdr(wg, 1, ["Tally group (immediate or primary)", "Sub-head code", "Contra-balance code", "Source / note"])
rr = 2
for g in G_CLIENT + G_DEF:
    for j, v in enumerate(g, 1):
        c = wg.cell(row=rr, column=j, value=v); c.font = f_in if j in (2, 3) else f_base
    rr += 1
wg.freeze_panes = "A2"
# move code to col B/C: formula references below use B (code) and C (contra)

# ---------------------------------------------------------------- Map_Ledgers
wl = wb.create_sheet("Map_Ledgers")
setw(wl, [40, 16, 16, 70])
hdr(wl, 1, ["Tally ledger name (exact)", "Sub-head code", "Contra-balance code", "Reason"])
rr = 2
for g in L_OVR:
    for j, v in enumerate(g, 1):
        c = wl.cell(row=rr, column=j, value=v); c.font = f_in if j in (2, 3) else f_base
    rr += 1
wl.cell(row=rr + 1, column=1, value="Add MSME creditors here with code TP.MSME (contra STLA.SUPP).").font = f_sub
wl.freeze_panes = "A2"

# ---------------------------------------------------------------- TB sheets
def tb_sheet(name, rows, title):
    t = wb.create_sheet(name)
    setw(t, [44, 26, 22, 15, 15, 15, 15, 12, 12, 12, 12, 12, 12, 6, 12, 12, 8, 8, 26])
    hdr(t, 1, ["Ledger", "Tally group", "Primary group", "Opening (Dr -ve)", "Net debit", "Net credit",
               "Closing (Dr -ve)", "Ledger ovr", "Ledger ovr contra", "Group code", "Group contra",
               "Base code", "Base contra", "Sign", "Code - closing", "Code - opening",
               "Line - closing", "Line - opening", "Flag"])
    t.row_dimensions[1].height = 30
    for i in range(TB_ROWS):
        n = i + 2
        if i < len(rows):
            x = rows[i]
            vals = [x["ledger_name"], x["group_name"], x["primary_group"],
                    float(x["opening_balance"]), float(x["net_debit"]), float(x["net_credit"]), float(x["closing_balance"])]
            for j, v in enumerate(vals, 1):
                c = t.cell(row=n, column=j, value=v); c.font = f_base
                if j >= 4: c.number_format = NUM
        f = {
         8: f'=IFERROR(INDEX(Map_Ledgers!$B$2:$B$600,MATCH($A{n},Map_Ledgers!$A$2:$A$600,0))&"","")',
         9: f'=IFERROR(INDEX(Map_Ledgers!$C$2:$C$600,MATCH($A{n},Map_Ledgers!$A$2:$A$600,0))&"","")',
         10: f'=IFERROR(INDEX(Map_Groups!$B$2:$B$600,MATCH($B{n},Map_Groups!$A$2:$A$600,0))&"",IFERROR(INDEX(Map_Groups!$B$2:$B$600,MATCH($C{n},Map_Groups!$A$2:$A$600,0))&"","UNMAPPED"))',
         11: f'=IFERROR(INDEX(Map_Groups!$C$2:$C$600,MATCH($B{n},Map_Groups!$A$2:$A$600,0))&"",IFERROR(INDEX(Map_Groups!$C$2:$C$600,MATCH($C{n},Map_Groups!$A$2:$A$600,0))&"",""))',
         12: f'=IF($H{n}<>"",$H{n},$J{n})',
         13: f'=IF($H{n}<>"",$I{n},$K{n})',
         14: f'=IFERROR(INDEX(Heads!$F$2:$F$600,MATCH($L{n},Heads!$A$2:$A$600,0)),0)',
         15: f'=IF($A{n}="","",IF(AND($M{n}<>"",$G{n}*$N{n}<0),$M{n},$L{n}))',
         16: f'=IF($A{n}="","",IF(AND($M{n}<>"",$D{n}*$N{n}<0),$M{n},$L{n}))',
         17: f'=IF($A{n}="","",IFERROR(INDEX(Heads!$B$2:$B$600,MATCH($O{n},Heads!$A$2:$A$600,0)),"BADCODE"))',
         18: f'=IF($A{n}="","",IFERROR(INDEX(Heads!$B$2:$B$600,MATCH($P{n},Heads!$A$2:$A$600,0)),"BADCODE"))',
         19: f'=IF($A{n}="","",IF(OR($Q{n}="BADCODE",$R{n}="BADCODE"),"MAP!",IF(OR($O{n}<>$L{n},$P{n}<>$L{n}),"Reclassified: contra balance",IF($H{n}<>"","Ledger override",""))))',
        }
        for col, fx in f.items():
            t.cell(row=n, column=col, value=fx).font = f_base
    t.freeze_panes = "B2"
    t.auto_filter.ref = f"A1:S{TB_ROWS + 1}"
    return t

rows = ROWS_CY
tb_sheet("TB_CY", rows, "")
tb_sheet("TB_PY", ROWS_PY, "")

def cy(code): return f'SUMIFS(TB_CY!$G$2:$G$3001,TB_CY!$O$2:$O$3001,"{code}")'
def py_bs(code): return f'SUMIFS(TB_CY!$D$2:$D$3001,TB_CY!$P$2:$P$3001,"{code}")'
def py_pl(code): return f'SUMIFS(TB_PY!$G$2:$G$3001,TB_PY!$O$2:$O$3001,"{code}")'

# ---------------------------------------------------------------- Notes
wn = wb.create_sheet("Notes")
setw(wn, [6, 62, 20, 20])
ADDR = INP["Registered office address"]; CIN = INP["CIN"]; FV = INP["Face value per equity share (Rs)"]
P.title_block(wn, 4, CO, CIN, ADDR, f'="Notes forming part of the financial statements for the year ended "&{CYD}', LBL)
NOTE_TOT = {}   # line -> (cy cell, py cell)
SUB_CELL = {}   # code -> (cy, py)
NOTE_NO = {}
NOTE_BLOCKS = []  # (start row, end row) of each note, for lines and page breaks
r = 7
note_no = [3]
WCH = 62 + 20 + 20  # approx characters across B:D

def note_title(no, title):
    """Band row: note number in A, title across B:D."""
    global r
    NOTE_BLOCKS.append([r, None])
    for col in range(1, 5):
        c = wn.cell(row=r, column=col); c.fill = P.fill_band; c.font = P.f_note
    wn.cell(row=r, column=1, value=no).alignment = Alignment(horizontal="center", vertical="center")
    wn.cell(row=r, column=2, value=title).alignment = Alignment(vertical="center")
    wn.row_dimensions[r].height = 18
    r += 1

def col_head(labels=("Particulars", None, None), bs=True):
    global r
    vals = [labels[0], labels[1] or (f'="As at "&{CYD}' if bs else f'="Year ended "&{CYD}'),
            labels[2] or (f'="As at "&{PYD}' if bs else f'="Year ended "&{PYD}')]
    for k, v in enumerate(vals):
        c = wn.cell(row=r, column=2 + k, value=v); c.font = P.f_b
        c.alignment = Alignment(horizontal="left" if k == 0 else "center", vertical="center", wrap_text=True)
        P._merge_border(c, bottom=P.line)
    wn.row_dimensions[r].height = 26
    r += 1

def end_note():
    """Close the open note block at the last used row."""
    if NOTE_BLOCKS and NOTE_BLOCKS[-1][1] is None:
        NOTE_BLOCKS[-1][1] = r - 1

# Notes 1 and 2: corporate information and significant accounting policies
_corp = CFG.get("corporate_info") or ("{co} (the Company) is a company incorporated in India under the Companies Act. "
                                      "Its registered office is at {addr}.")
note_title(1, "Corporate information")
P.para(wn, r, 2, 4, _corp.format(co=SETUP.get("Company name", ""), addr=SETUP.get("Registered office address", ""),
                                 cin=SETUP.get("CIN", ""), inc=SETUP.get("Date of incorporation", "")), WCH); r += 1
end_note(); r += 1
from policies import policies_for
note_title(2, "Significant accounting policies")
for k, (head, text) in enumerate(policies_for(CFG), 1):
    P.para(wn, r, 2, 4, f"2.{k}  {head}", WCH, bold=True); wn.row_dimensions[r].height = 15; r += 1
    for t in (text if isinstance(text, list) else [text]):
        P.para(wn, r, 2, 4, t, WCH, indent=2); r += 1
end_note(); r += 1

def note_header(line, title=None):
    global r
    NOTE_NO[line] = None if line in SKIP else note_no[0]
    note_title(note_no[0], title or LINES[line])
    if line in SKIP: NOTE_BLOCKS[-1].append("skip")
    col_head(bs=line in BS_LINES)
    if line not in SKIP: note_no[0] += 1

AGE_CHK = []
def std_note(line, title=None):
    global r
    r_start = r
    note_header(line, title)
    codes = [h for h in HEADS if h[1] == line]
    start = r
    stmt = codes[0][2]
    for h in codes:
        code, sg = h[0], h[4]
        wn.cell(row=r, column=2, value=h[3]).font = f_base
        a1, a2 = ADJ.get(code, ("", ""))
        c1 = wn.cell(row=r, column=3, value=f"=({cy(code)}*{sg}{a1})/{UNIT}")
        c2 = wn.cell(row=r, column=4, value=f"=({(py_bs if stmt=='BS' else py_pl)(code)}*{sg}{a2})/{UNIT}")
        for c in (c1, c2): c.number_format = NUM; c.font = f_base
        SUB_CELL[code] = (f"Notes!$C${r}", f"Notes!$D${r}")
        SUBROWS.append((r, ["C", "D"]))
        r += 1
    wn.cell(row=r, column=2, value="Total").font = f_b
    for col in (3, 4):
        L = get_column_letter(col)
        c = wn.cell(row=r, column=col, value=f"=SUM({L}{start}:{L}{r-1})"); c.number_format = NUM; c.font = f_b; c.border = b_tot
    NOTE_TOT[line] = (f"Notes!$C${r}", f"Notes!$D${r}")
    _ag = CFG.get("ageing", {}).get(line)
    if _ag and line not in SKIP:
        _tr = r; r += 2
        wn.cell(row=r, column=2, value=_ag.get("title", "Ageing schedule")).font = P.f_note; r += 1
        _a0 = r
        for _lab, _cy, _py in _ag["rows"]:
            wn.cell(row=r, column=2, value=_lab).alignment = Alignment(indent=1)
            for _col, _v in ((3, _cy), (4, _py)):
                c = wn.cell(row=r, column=_col, value=f"={float(_v or 0)}/{UNIT}"); c.number_format = NUM; c.font = f_base
            r += 1
        wn.cell(row=r, column=2, value="Total").font = f_b
        for col in (3, 4):
            L = get_column_letter(col)
            c = wn.cell(row=r, column=col, value=f"=SUM({L}{_a0}:{L}{r-1})"); c.number_format = NUM; c.font = f_b; c.border = b_tot
        AGE_CHK.append((line, f"=Notes!$C${r}-Notes!$C${_tr}", f"=Notes!$D${r}-Notes!$D${_tr}"))
        r += 1
        for _t in _ag.get("notes", []):
            P.para(wn, r, 2, 4, _t, WCH, font=P.f_foot); r += 1
    r += 1; end_note(); r += 1
    if line in SKIP: HIDE["Notes"].extend(range(r_start, r))

BS_LINES = ["SC","RS","MRSW","SAM","LTB","DTL","OLTL","LTP","STB","TP","OCL","STP",
            "PPE","INT","CWIP","IAUD","NCI","DTA","LTLA","ONCA","CI","INV","TR","CCE","STLA","OCA"]

# Note: share capital - authorised / issued, reconciliation, rights, >5% holders, promoters
def inr(n):
    n = int(round(float(n or 0))); s_ = str(abs(n))
    if len(s_) > 3:
        h, t = s_[:-3], s_[-3:]
        h = ",".join([h[max(0, i - 2):i] for i in range(len(h), 0, -2)][::-1])
        s_ = h + "," + t
    return ("-" if n < 0 else "") + s_
_fv = float(SETUP.get("Face value per equity share (Rs)") or 10)
_fvt = f"{_fv:g}"
_sh = CFG.get("shareholding", {})
note_header("SC")
_auth = float(SETUP.get("Authorised share capital (Rs) - current year") or 0)
wn.cell(row=r, column=2, value="Authorised").font = f_b; r += 1
wn.cell(row=r, column=2, value=f"{inr(_auth / _fv)} equity shares of Rs {_fvt} each").alignment = Alignment(indent=1)
c = wn.cell(row=r, column=3, value=f'=IF({INP["Authorised share capital (Rs) - current year"]}="",0,{INP["Authorised share capital (Rs) - current year"]})/{UNIT}'); c.number_format = NUM
c = wn.cell(row=r, column=4, value=f'=IF({INP["Authorised share capital (Rs) - previous year"]}="",0,{INP["Authorised share capital (Rs) - previous year"]})/{UNIT}'); c.number_format = NUM
r += 1
wn.cell(row=r, column=2, value="Issued, subscribed and fully paid up").font = f_b; r += 1
start = r
_issued = abs(sum(float(x["closing_balance"] or 0) for x in ROWS_CY if resolve(x["ledger_name"], x["group_name"], x["primary_group"], float(x["closing_balance"] or 0), L_OVR, GROUPS_ALL) == "SC.EQ"))
for code in ["SC.EQ"]:
    wn.cell(row=r, column=2, value=f"{inr(_issued / _fv)} equity shares of Rs {_fvt} each, fully paid up").alignment = Alignment(indent=1)
    c1 = wn.cell(row=r, column=3, value=f"={cy(code)}*1/{UNIT}"); c2 = wn.cell(row=r, column=4, value=f"={py_bs(code)}*1/{UNIT}")
    for c in (c1, c2): c.number_format = NUM
    r += 1
wn.cell(row=r, column=2, value="Total").font = f_b
for col in (3, 4):
    L = get_column_letter(col)
    c = wn.cell(row=r, column=col, value=f"=SUM({L}{start}:{L}{r-1})"); c.number_format = NUM; c.font = f_b; c.border = b_tot
NOTE_TOT["SC"] = (f"Notes!$C${r}", f"Notes!$D${r}"); r += 2
SHN = '#,##0;(#,##0);"-"'
def _sub(t):
    global r
    wn.cell(row=r, column=2, value=t).font = P.f_note; r += 1
_sub("(a) Reconciliation of the number of equity shares outstanding")
col_head(("Number of equity shares", None, None))
_sc_cy, _sc_py = NOTE_TOT["SC"]
_py_open = f'SUMIFS(TB_PY!$D$2:$D$3001,TB_PY!$P$2:$P$3001,"SC.EQ")'
rb = r
wn.cell(row=r, column=2, value="Shares outstanding at the beginning of the year")
wn.cell(row=r, column=3, value=f"={_sc_py}*{UNIT}/{FV}"); wn.cell(row=r, column=4, value=f"={_py_open}/{FV}"); r += 1
wn.cell(row=r, column=2, value="Add: Shares issued during the year")
wn.cell(row=r, column=3, value=f"=C{r+2}-C{rb}"); wn.cell(row=r, column=4, value=f"=D{r+2}-D{rb}"); r += 1
wn.cell(row=r, column=2, value="Less: Shares bought back during the year")
wn.cell(row=r, column=3, value=0); wn.cell(row=r, column=4, value=0); r += 1
wn.cell(row=r, column=2, value="Shares outstanding at the end of the year").font = f_b
wn.cell(row=r, column=3, value=f"={_sc_cy}*{UNIT}/{FV}"); wn.cell(row=r, column=4, value=f"={_sc_py}*{UNIT}/{FV}")
for rr_ in range(rb, r + 1):
    for col in (3, 4): wn.cell(row=rr_, column=col).number_format = SHN
for col in (3, 4): wn.cell(row=r, column=col).border = b_tot; wn.cell(row=r, column=col).font = f_b
SHARES_END = (f"Notes!$C${r}", f"Notes!$D${r}")
r += 2
_sub("(b) Terms and rights attached to equity shares")
for t in _sh.get("rights") or [
        f"The Company has only one class of equity shares having a face value of Rs {_fvt} per share. Each holder of equity shares is entitled to one vote per share.",
        "The Company declares and pays dividends in Indian Rupees. The dividend proposed by the Board of Directors is subject to the approval of the shareholders in the ensuing Annual General Meeting, except in the case of interim dividend.",
        "In the event of liquidation of the Company, the holders of equity shares will be entitled to receive the remaining assets of the Company, after distribution of all preferential amounts. The distribution will be in proportion to the number of equity shares held by the shareholders."]:
    P.para(wn, r, 2, 4, t, WCH, indent=1); r += 1
r += 1
if _sh.get("over5"):
    _sub("(c) Shareholders holding more than 5% of the equity shares")
    col_head(("Name of shareholder", None, None))
    for nm, a1, a2 in _sh["over5"]:
        wn.cell(row=r, column=2, value=nm)
        c1 = wn.cell(row=r, column=3, value=a1); c2 = wn.cell(row=r, column=4, value=a2)
        for c in (c1, c2): c.number_format = SHN
        r += 1
        wn.cell(row=r, column=2, value="% of total equity shares").alignment = Alignment(indent=2)
        wn.cell(row=r, column=2).font = P.f_foot
        for col, ref in ((3, SHARES_END[0]), (4, SHARES_END[1])):
            c = wn.cell(row=r, column=col, value=f"=IFERROR({get_column_letter(col)}{r-1}/{ref},0)"); c.number_format = "0.00%"; c.font = P.f_foot
        r += 1
    r += 1
if _sh.get("promoters"):
    _sub(f"({'d' if _sh.get('over5') else 'c'}) Shares held by promoters at the end of the year")
    col_head(("Name of promoter", "No. of shares", "% of total shares"))
    p0 = r
    for nm, a1, a2 in _sh["promoters"]:
        wn.cell(row=r, column=2, value=nm)
        c = wn.cell(row=r, column=3, value=a1); c.number_format = SHN
        c = wn.cell(row=r, column=4, value=f"=IFERROR(C{r}/{SHARES_END[0]},0)"); c.number_format = "0.00%"
        r += 1
    wn.cell(row=r, column=2, value="Total").font = f_b
    c = wn.cell(row=r, column=3, value=f"=SUM(C{p0}:C{r-1})"); c.number_format = SHN; c.font = f_b; c.border = b_tot
    c = wn.cell(row=r, column=4, value=f"=SUM(D{p0}:D{r-1})"); c.number_format = "0.00%"; c.font = f_b; c.border = b_tot
    r += 1
    _chg = [nm for nm, a1, a2 in _sh["promoters"] if a1 != a2]
    P.para(wn, r, 2, 4, "% change during the year: " + ("nil - there has been no change in the shareholding of any promoter during the year." if not _chg
                         else "change in holding of " + ", ".join(_chg) + "."), WCH, font=P.f_foot); r += 1
r += 0
end_note(); r += 1

# Note: reserves and surplus (movement) - Parekh layout as signed FY 24-25 note 2
note_header("RS")
def S(tb, col, codecol, code, extra=""):
    return f'SUMIFS({tb}!${col}$2:${col}$3001,{tb}!${codecol}$2:${codecol}$3001,"{code}"{extra})'
PYL = 'COUNTIF(TB_PY!$A$2:$A$3001,"?*")=0'
def two(row, label, fcy, fpy, bold=False, border=None):
    wn.cell(row=row, column=2, value=label).font = f_b if bold else f_base
    for col, fx in ((3, fcy), (4, fpy)):
        c = wn.cell(row=row, column=col, value=fx); c.number_format = NUM
        if bold: c.font = f_b
        if border: c.border = border
_letters = iter("abcdefgh")
_rs_parts = []
_st_start = r
if "RS.STAT" in USED_CODES: _rs_parts.append(next(_letters))
wn.cell(row=r, column=2, value=f"({_rs_parts[-1] if _rs_parts else 'a'}) Statutory reserve as per RBI NBFC guidelines (s.45-IC)").font = f_b; r += 1
st_o = r; two(r, "Opening balance", f"={S('TB_CY','D','P','RS.STAT')}/{UNIT}", f"=IF({PYL},\"\",{S('TB_PY','D','P','RS.STAT')}/{UNIT})"); r += 1
st_t = r; two(r, "Add: Transferred from Statement of Profit and Loss", f"=({S('TB_CY','E','O','RS.STAT')}+{S('TB_CY','F','O','RS.STAT')})/{UNIT}", f"=IF({PYL},\"\",({S('TB_PY','E','O','RS.STAT')}+{S('TB_PY','F','O','RS.STAT')})/{UNIT})"); r += 1
st_c = r; two(r, "Closing balance", f"={S('TB_CY','G','O','RS.STAT')}/{UNIT}", f"={S('TB_CY','D','P','RS.STAT')}/{UNIT}", True, b_top); r += 2
_st_end = r
_rs_blocks = []  # (code, closing row) for securities premium / general reserve
for _code, _lbl in (("RS.SEC", "Securities premium"), ("RS.GEN", "General reserve")):
    if _code not in USED_CODES: continue
    _lt_ = next(_letters); _rs_parts.append(_lt_)
    wn.cell(row=r, column=2, value=f"({_lt_}) {_lbl}").font = f_b; r += 1
    _o = r; two(r, "Opening balance", f"={S('TB_CY','D','P',_code)}/{UNIT}", f"=IF({PYL},\"\",{S('TB_PY','D','P',_code)}/{UNIT})"); r += 1
    _a = r; two(r, "Add: Additions during the year", f"={S('TB_CY','F','O',_code)}/{UNIT}", f"=IF({PYL},\"\",{S('TB_PY','F','O',_code)}/{UNIT})"); r += 1
    two(r, "Less: Utilised / transferred", f"=-{S('TB_CY','E','O',_code)}/{UNIT}", f"=IF({PYL},\"\",-{S('TB_PY','E','O',_code)}/{UNIT})"); r += 1
    _c = r; two(r, "Closing balance", f"={S('TB_CY','G','O',_code)}/{UNIT}", f"={S('TB_CY','D','P',_code)}/{UNIT}", True, b_top); r += 2
    _rs_blocks.append((_code, _a, _c))
_sl = next(_letters); _rs_parts.append(_sl)
wn.cell(row=r, column=2, value=f"({_sl}) " + CFG.get("rs_surplus_label", "Surplus in Statement of Profit and Loss")).font = f_b; r += 1
rs_open = r; two(r, "Opening balance", f"={S('TB_CY','D','P','RS.SURP')}/{UNIT}", f"=IF({PYL},\"\",{S('TB_PY','D','P','RS.SURP')}/{UNIT})"); r += 1
rs_prof = r; wn.cell(row=r, column=2, value="Add: Profit for the year").font = f_base; r += 1
_xc = S("TB_CY", "E", "O", "RS.SURP", ',TB_CY!$A$2:$A$3001,"<>Profit & Loss A/c"')
_xp = S("TB_PY", "E", "O", "RS.SURP", ',TB_PY!$A$2:$A$3001,"<>Profit & Loss A/c"')
rs_cont = r; two(r, CFG.get("rs_other_label", "Less: Other transfers / appropriations"), f'=-{_xc}/{UNIT}', f'=IF({PYL},"",-{_xp}/{UNIT})'); r += 1
rs_st = r; two(r, "Less: Transfer to statutory reserve", f"=C{st_t}", f'=IF({PYL},"",D{st_t})'); r += 1
if "RS.STAT" not in USED_CODES: HIDE["Notes"].append(rs_st)
_gen = [b for b in _rs_blocks if b[0] == "RS.GEN"]
rs_gen = None
if _gen:
    rs_gen = r; two(r, "Less: Transfer to general reserve", f"=C{_gen[0][1]}", f'=IF({PYL},"",D{_gen[0][1]})'); r += 1
rs_oth = r; wn.cell(row=r, column=2, value="Other movements - should be nil; review if not").font = f_base; r += 1
rs_close = r; two(r, "Closing balance", f"={S('TB_CY','G','O','RS.SURP')}/{UNIT}", f"={S('TB_CY','D','P','RS.SURP')}/{UNIT}", True, b_top); r += 2
for col in (3, 4):
    L = get_column_letter(col)
    fx = f"={L}{rs_close}-{L}{rs_open}-{L}{rs_prof}+{L}{rs_cont}+{L}{rs_st}" + (f"+{L}{rs_gen}" if rs_gen else "")
    if col == 4: fx = f'=IF({PYL},"",{fx[1:]})'
    c = wn.cell(row=rs_oth, column=col, value=fx); c.number_format = NUM
tot_rs = r
_ex = "".join(f"+C{b[2]}" for b in _rs_blocks); _exp = "".join(f"+D{b[2]}" for b in _rs_blocks)
two(r, "Total reserves and surplus" + (f" ({' + '.join(_rs_parts)})" if len(_rs_parts) > 1 else ""),
    f"=C{st_c}+C{rs_close}{_ex}", f"=D{st_c}+D{rs_close}{_exp}", True, b_tot)
NOTE_TOT["RS"] = (f"Notes!$C${tot_rs}", f"Notes!$D${tot_rs}")
RS_OTH = (f"Notes!$C${rs_oth}", f"N(Notes!$D${rs_oth})")
if "RS.STAT" not in USED_CODES:
    HIDE["Notes"].extend(range(_st_start, _st_end))
r += 1; end_note(); r += 1

for line in ["MRSW","SAM","LTB","DTL","OLTL","LTP","STB","TP","OCL","STP"]:
    std_note(line)
r += 1

# PPE note: net carrying amount by asset class, then movement (WDV as maintained in Tally)
note_header("PPE", "Property, plant and equipment")
wn.cell(row=r, column=2, value="Net carrying amount (written down value)").font = P.f_note; r += 1
start = r
_ppe = [h for h in HEADS if h[1] == "PPE"]
for h in _ppe:
    code = h[0]
    wn.cell(row=r, column=2, value=h[3]).alignment = Alignment(indent=1)
    c1 = wn.cell(row=r, column=3, value=f"=-{cy(code)}/{UNIT}"); c2 = wn.cell(row=r, column=4, value=f"=-{py_bs(code)}/{UNIT}")
    for c in (c1, c2): c.number_format = NUM
    SUBROWS.append((r, ["C", "D"]))
    r += 1
wn.cell(row=r, column=2, value="Total").font = f_b
for col in (3, 4):
    L = get_column_letter(col)
    c = wn.cell(row=r, column=col, value=f"=SUM({L}{start}:{L}{r-1})"); c.number_format = NUM; c.font = f_b; c.border = b_tot
NOTE_TOT["PPE"] = (f"Notes!$C${r}", f"Notes!$D${r}")
r += 2
wn.cell(row=r, column=2, value="Movement during the year").font = P.f_note; r += 1
def _ppe_sum(tb, col):
    return "+".join(f'SUMIFS({tb}!${col}$2:${col}$3001,{tb}!$O$2:$O$3001,"{h[0]}")' for h in _ppe)
def _ppe_open(tb):
    return "+".join(f'SUMIFS({tb}!$D$2:$D$3001,{tb}!$P$2:$P$3001,"{h[0]}")' for h in _ppe)
m0 = r
wn.cell(row=r, column=2, value="Opening written down value")
wn.cell(row=r, column=3, value=f"=-({_ppe_open('TB_CY')})/{UNIT}"); wn.cell(row=r, column=4, value=f"=-({_ppe_open('TB_PY')})/{UNIT}"); r += 1
wn.cell(row=r, column=2, value="Add: Additions during the year")
wn.cell(row=r, column=3, value=f"=-({_ppe_sum('TB_CY','E')})/{UNIT}"); wn.cell(row=r, column=4, value=f"=-({_ppe_sum('TB_PY','E')})/{UNIT}"); r += 1
PPE_DED = f"Notes!$C${r}"
wn.cell(row=r, column=2, value="Less: Depreciation and deductions")
wn.cell(row=r, column=3, value=f"=({_ppe_sum('TB_CY','F')})/{UNIT}"); wn.cell(row=r, column=4, value=f"=({_ppe_sum('TB_PY','F')})/{UNIT}"); r += 1
wn.cell(row=r, column=2, value="Closing written down value").font = f_b
for col in (3, 4):
    L = get_column_letter(col)
    c = wn.cell(row=r, column=col, value=f"={L}{m0}+{L}{m0+1}-{L}{m0+2}"); c.font = f_b; c.border = b_tot
for rr_ in range(m0, r + 1):
    for col in (3, 4): wn.cell(row=rr_, column=col).number_format = NUM
r += 1
P.para(wn, r, 2, 4, CFG.get("ppe_note", "The Company maintains its property, plant and equipment at written down value. Gross block and accumulated depreciation are not maintained separately in the books of account."), WCH, font=P.f_foot); r += 1
end_note(); r += 1

for line in ["INT","CWIP","IAUD","NCI","DTA","LTLA","ONCA","CI","INV","TR","CCE","STLA","OCA"]:
    std_note(line)
    if line == "TR":
        pass

for line in ["REV","OI","COMC","PUR"]:
    std_note(line)

# Changes in inventories
ch_start = r
note_header("CHINV")
ch_o = r
wn.cell(row=r, column=2, value="Inventories at the beginning of the year").font = f_base
c = wn.cell(row=r, column=3, value=f'=-SUMIFS(TB_CY!$D$2:$D$3001,TB_CY!$R$2:$R$3001,"INV")/{UNIT}'); c.number_format = NUM
c = wn.cell(row=r, column=4, value=f'=-SUMIFS(TB_PY!$D$2:$D$3001,TB_PY!$R$2:$R$3001,"INV")/{UNIT}'); c.number_format = NUM
r += 1
ch_c = r
wn.cell(row=r, column=2, value="Less: Inventories at the end of the year").font = f_base
c = wn.cell(row=r, column=3, value=f'=-SUMIFS(TB_CY!$G$2:$G$3001,TB_CY!$Q$2:$Q$3001,"INV")/{UNIT}'); c.number_format = NUM
c = wn.cell(row=r, column=4, value=f'=-SUMIFS(TB_PY!$G$2:$G$3001,TB_PY!$Q$2:$Q$3001,"INV")/{UNIT}'); c.number_format = NUM
r += 1
wn.cell(row=r, column=2, value="(Increase) / decrease in inventories").font = f_b
for col in (3, 4):
    L = get_column_letter(col)
    c = wn.cell(row=r, column=col, value=f"={L}{ch_o}-{L}{ch_c}"); c.number_format = NUM; c.font = f_b; c.border = b_tot
NOTE_TOT["CHINV"] = (f"Notes!$C${r}", f"Notes!$D${r}")
r += 1; end_note()
if "CHINV" in SKIP: HIDE["Notes"].extend(range(ch_start, r + 1))
r += 1

for line in ["EMP","FIN","DEP","OEXP"]:
    std_note(line)
std_note("TAXC", "Tax expense - current tax")
std_note("TAXD", "Tax expense - deferred tax")
# exceptional / extraordinary (no note number shown on face if nil, but computed)
for line in ["EXC","EXO"]:
    std_note(line)
NR = r  # Notes continue after the PL is built (related parties, ratios, other disclosures)
wn.freeze_panes = "A7"

# ---------------------------------------------------------------- BS
wbsh = wb.create_sheet("BS", 1)
setw(wbsh, [56, 9, 21, 21])
P.title_block(wbsh, 4, CO, CIN, ADDR, f'="Balance Sheet as at "&{CYD}', LBL)
hdr(wbsh, 6, ["Particulars", "Note No.", None, None])
wbsh["C6"] = f'="As at "&{CYD}'; wbsh["D6"] = f'="As at "&{PYD}'
P.header_row(wbsh, 6, 1, 4)
r = 7
def put(ws, label, line=None, bold=False, indent=0, cells=None, border=None):
    global r
    c = ws.cell(row=r, column=1, value=label); c.font = f_b if bold else f_base
    c.alignment = Alignment(indent=indent)
    if line in SKIP:
        HIDE[ws.title].append(r)
    if line:
        ws.cell(row=r, column=2, value=NOTE_NO.get(line)).alignment = Alignment(horizontal="center")
        cells = NOTE_TOT[line]
    if cells:
        for k, v in enumerate(cells):
            cc = ws.cell(row=r, column=3 + k, value=f"={v}" if not str(v).startswith("=") else v)
            cc.number_format = NUM; cc.font = f_b if bold else f_base
            if border: cc.border = border
    r += 1
    return r - 1

put(wbsh, "I. EQUITY AND LIABILITIES", bold=True)
put(wbsh, "(1) Shareholders' funds", bold=True, indent=1)
eq = [put(wbsh, "(a) Share capital", "SC", indent=2), put(wbsh, "(b) Reserves and surplus", "RS", indent=2),
      put(wbsh, "(c) Money received against share warrants", "MRSW", indent=2)]
put(wbsh, "(2) Share application money pending allotment", "SAM", indent=1)
eq.append(r - 1)
put(wbsh, "(3) Non-current liabilities", bold=True, indent=1)
eq += [put(wbsh, "(a) Long-term borrowings", "LTB", indent=2), put(wbsh, "(b) Deferred tax liabilities (net)", "DTL", indent=2),
       put(wbsh, "(c) Other long-term liabilities", "OLTL", indent=2), put(wbsh, "(d) Long-term provisions", "LTP", indent=2)]
put(wbsh, "(4) Current liabilities", bold=True, indent=1)
eq.append(put(wbsh, "(a) Short-term borrowings", "STB", indent=2))
tpr = put(wbsh, "(b) Trade payables", indent=2)
wbsh.cell(row=tpr, column=2, value=NOTE_NO["TP"]).alignment = Alignment(horizontal="center")
eq.append(put(wbsh, "(A) total outstanding dues of micro enterprises and small enterprises", indent=3, cells=SUB_CELL["TP.MSME"]))
eq.append(put(wbsh, "(B) total outstanding dues of creditors other than micro enterprises and small enterprises", indent=3, cells=SUB_CELL["TP.OTH"]))
if "TP" in SKIP: HIDE["BS"] += [tpr, eq[-2], eq[-1]]
eq += [put(wbsh, "(c) Other current liabilities", "OCL", indent=2), put(wbsh, "(d) Short-term provisions", "STP", indent=2)]
eq_tot = put(wbsh, "TOTAL", bold=True, cells=[f"=SUM({','.join('C'+str(x) for x in eq)})", f"=SUM({','.join('D'+str(x) for x in eq)})"], border=b_tot)
r += 1
put(wbsh, "II. ASSETS", bold=True)
put(wbsh, "(1) Non-current assets", bold=True, indent=1)
put(wbsh, "(a) Property, plant and equipment and intangible assets", indent=2)
asr = [put(wbsh, "(i) Property, plant and equipment", "PPE", indent=3), put(wbsh, "(ii) Intangible assets", "INT", indent=3),
       put(wbsh, "(iii) Capital work-in-progress", "CWIP", indent=3), put(wbsh, "(iv) Intangible assets under development", "IAUD", indent=3),
       put(wbsh, "(b) Non-current investments", "NCI", indent=2), put(wbsh, "(c) Deferred tax assets (net)", "DTA", indent=2),
       put(wbsh, "(d) Long-term loans and advances", "LTLA", indent=2), put(wbsh, "(e) Other non-current assets", "ONCA", indent=2)]
put(wbsh, "(2) Current assets", bold=True, indent=1)
asr += [put(wbsh, "(a) Current investments", "CI", indent=2), put(wbsh, "(b) Inventories", "INV", indent=2),
        put(wbsh, "(c) Trade receivables", "TR", indent=2), put(wbsh, "(d) Cash and cash equivalents", "CCE", indent=2),
        put(wbsh, "(e) Short-term loans and advances", "STLA", indent=2), put(wbsh, "(f) Other current assets", "OCA", indent=2)]
as_tot = put(wbsh, "TOTAL", bold=True, cells=[f"=SUM({','.join('C'+str(x) for x in asr)})", f"=SUM({','.join('D'+str(x) for x in asr)})"], border=b_tot)
r += 1
P.frame(wbsh, 6, as_tot, 1, 4)
P.para(wbsh, r, 1, 4, "The accompanying notes 1 to " + "{LASTNOTE}" + " form an integral part of the financial statements.", 108, font=P.f_foot); r += 2
P.sign_block(wbsh, r, INP, 1, (3, 4), CO)
wbsh.freeze_panes = "A7"
BS_EQ = (f"BS!$C${eq_tot}", f"BS!$D${eq_tot}"); BS_AS = (f"BS!$C${as_tot}", f"BS!$D${as_tot}")

# ---------------------------------------------------------------- PL
wp = wb.create_sheet("PL", 2)
setw(wp, [56, 9, 21, 21])
P.title_block(wp, 4, CO, CIN, ADDR, f'="Statement of Profit and Loss for the year ended "&{CYD}', LBL)
hdr(wp, 6, ["Particulars", "Note No.", None, None])
wp["C6"] = f'="Year ended "&{CYD}'; wp["D6"] = f'="Year ended "&{PYD}'
P.header_row(wp, 6, 1, 4)
r = 7
def sumrows(rows_, sign=None):
    return [f"=SUM({','.join(L+str(x) for x in rows_)})" for L in ("C", "D")]
def expr(fmt):
    return [fmt.replace("#", L) for L in ("C", "D")]
r1 = put(wp, "I. Revenue from operations", "REV")
r2 = put(wp, "II. Other income", "OI")
r3 = put(wp, "III. Total income (I + II)", bold=True, cells=expr(f"=#{r1}+#{r2}"), border=b_top)
put(wp, "IV. Expenses", bold=True)
ex = [put(wp, "Cost of materials consumed", "COMC", indent=2), put(wp, "Purchases of stock-in-trade", "PUR", indent=2),
      put(wp, "Changes in inventories of finished goods, work-in-progress and stock-in-trade", "CHINV", indent=2),
      put(wp, "Employee benefits expense", "EMP", indent=2), put(wp, "Finance costs", "FIN", indent=2),
      put(wp, "Depreciation and amortization expense", "DEP", indent=2), put(wp, "Other expenses", "OEXP", indent=2)]
r4 = put(wp, "Total expenses (IV)", bold=True, cells=sumrows(ex), border=b_top)
r5 = put(wp, "V. Profit before exceptional and extraordinary items and tax (III - IV)", bold=True, cells=expr(f"=#{r3}-#{r4}"))
r6 = put(wp, "VI. Exceptional items", "EXC")
r7 = put(wp, "VII. Profit before extraordinary items and tax (V - VI)", bold=True, cells=expr(f"=#{r5}-#{r6}"))
r8 = put(wp, "VIII. Extraordinary items", "EXO")
r9 = put(wp, "IX. Profit before tax (VII - VIII)", bold=True, cells=expr(f"=#{r7}-#{r8}"), border=b_top)
HIDE["PL"] += [r5, r7]
put(wp, "X. Tax expense:", bold=True)
t1 = put(wp, "(1) Current tax", "TAXC", indent=2)
t2 = put(wp, "(2) Deferred tax", "TAXD", indent=2)
r11 = put(wp, "XI. Profit / (loss) for the period from continuing operations (IX - X)", bold=True, cells=expr(f"=#{r9}-#{t1}-#{t2}"), border=b_top)
r12 = put(wp, "XII. Profit / (loss) from discontinuing operations", cells=[0, 0])
r13 = put(wp, "XIII. Tax expense of discontinuing operations", cells=[0, 0])
r14 = put(wp, "XIV. Profit / (loss) from discontinuing operations (after tax) (XII - XIII)", cells=expr(f"=#{r12}-#{r13}"))
r15 = put(wp, "XV. Profit / (loss) for the period (XI + XIV)", bold=True, cells=expr(f"=#{r11}+#{r14}"), border=b_tot)
put(wp, "XVI. Earnings per equity share:", bold=True)
sh_cy = INP["Weighted avg. equity shares - current year (for EPS)"]; sh_py = INP["Weighted avg. equity shares - previous year (for EPS)"]
put(wp, "(1) Basic (Rs)", indent=2, cells=[f'=IFERROR(C{r15}*{UNIT}/{sh_cy},"-")', f'=IFERROR(D{r15}*{UNIT}/{sh_py},"-")'])
put(wp, "(2) Diluted (Rs)", indent=2, cells=[f'=IFERROR(C{r15}*{UNIT}/{sh_cy},"-")', f'=IFERROR(D{r15}*{UNIT}/{sh_py},"-")'])
PL_LAST = r - 1
P.frame(wp, 6, PL_LAST, 1, 4)
r += 1
P.para(wp, r, 1, 4, "The accompanying notes 1 to " + "{LASTNOTE}" + " form an integral part of the financial statements.", 108, font=P.f_foot); r += 2
P.sign_block(wp, r, INP, 1, (3, 4), CO)
wp.freeze_panes = "A7"
PROFIT = (f"PL!$C${r15}", f"PL!$D${r15}")
# profit into RS note
wn.cell(row=rs_prof, column=3, value=f"={PROFIT[0]}").number_format = NUM
wn.cell(row=rs_prof, column=4, value=f"={PROFIT[1]}").number_format = NUM
exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "extra_notes.py"), encoding="utf-8").read())
CF_CHK = ("=0", "=0")
if CFG.get("cash_flow", True):
    exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "cash_flow.py"), encoding="utf-8").read())

# ---------------------------------------------------------------- Checks
wc = wb.create_sheet("Checks", 1)
setw(wc, [70, 18, 18, 12])
wc["A1"] = "Checks - all must read OK before issuing"; wc["A1"].font = f_title
hdr(wc, 3, ["Check", "Current year", "Previous year", "Status"])
TOL = 1
checks = [
 ("Balance Sheet tallies (Assets - Equity & Liabilities)", f"={BS_AS[0]}-{BS_EQ[0]}", f"={BS_AS[1]}-{BS_EQ[1]}", "abs2"),
 ("Profit per Schedule III P&L less profit per Tally", f"=PL!$C${r15}*{UNIT}-IF({INP['Net profit as per Tally P&L - current year']}=\"\",PL!$C${r15}*{UNIT},{INP['Net profit as per Tally P&L - current year']})",
   f"=IF({INP['Net profit as per Tally P&L - previous year']}=\"\",0,PL!$D${r15}*{UNIT}-{INP['Net profit as per Tally P&L - previous year']})", "abs2"),
 ("Ledgers not mapped (MAP! flags in TB_CY)", '=COUNTIF(TB_CY!$S$2:$S$3001,"MAP!")', '=COUNTIF(TB_PY!$S$2:$S$3001,"MAP!")', "abs2"),
 ("Suspense balances (should be nil)", '=SUMIFS(TB_CY!$G$2:$G$3001,TB_CY!$O$2:$O$3001,"OCL.SUSP")+SUMIFS(TB_CY!$G$2:$G$3001,TB_CY!$O$2:$O$3001,"OCA.SUSP")',
   '=SUMIFS(TB_CY!$D$2:$D$3001,TB_CY!$P$2:$P$3001,"OCL.SUSP")+SUMIFS(TB_CY!$D$2:$D$3001,TB_CY!$P$2:$P$3001,"OCA.SUSP")', "abs2"),
 ("Reserves: unexplained movement (closing - opening - profit)", f"={RS_OTH[0]}", f'=IF(COUNTIF(TB_PY!$A$2:$A$3001,"?*")=0,0,{RS_OTH[1]})', "abs2"),
 ("PPE: credits to assets less depreciation charged in P&L (disposals if non-zero)", f"={PPE_DED}-{SUB_CELL['DEP.DEP'][0]}", "=0", "warn"),
 *[(f"Ageing schedule ({LINES[_l]}) less note total", _c, _p, "abs2") for _l, _c, _p in AGE_CHK],
 *([("Cash Flow: closing cash per statement less cash and cash equivalents", CF_CHK[0], CF_CHK[1], "abs2")] if CFG.get("cash_flow", True) else []),
]
for i, (lab, a, b, kind) in enumerate(checks, 4):
    wc.cell(row=i, column=1, value=lab).font = f_base
    for col, v in ((2, a), (3, b)):
        c = wc.cell(row=i, column=col, value=v); c.number_format = NUM
    st = f'=IF(AND(ABS(B{i})<{TOL},ABS(C{i})<{TOL}),"OK",' + ('"REVIEW")' if kind == "warn" else '"ERROR")')
    wc.cell(row=i, column=4, value=st).font = f_b
n = 4 + len(checks)
wc.cell(row=n, column=1, value="Previous-year TB loaded in TB_PY (needed for PY P&L)").font = f_base
wc.cell(row=n, column=2, value='=COUNTIF(TB_PY!$A$2:$A$3001,"?*")')
wc.cell(row=n, column=4, value=f'=IF(B{n}>0,"OK","PY P&L BLANK")').font = f_b
wc.cell(row=n + 2, column=1, value="Tolerance: Rs 1. Checks are in rupees except rows 1, 5 and 7, which follow the rounding divisor.").font = f_sub
rf = n + 4
wc.cell(row=rf, column=1, value="Roll-forward: previous-year company closing (TB_PY) vs previous-year column (current-year opening)").font = f_b
hdr(wc, rf + 1, ["Balance Sheet line", "Per PY company", "Per PY column", "Difference"])
rr_ = rf + 2
first = rr_
for ln in BS_LINES:
    sg = -1 if ln in ("PPE","INT","CWIP","IAUD","NCI","DTA","LTLA","ONCA","CI","INV","TR","CCE","STLA","OCA") else 1
    wc.cell(row=rr_, column=1, value=LINES[ln]).font = f_base
    c = wc.cell(row=rr_, column=2, value=f'=SUMIFS(TB_PY!$G$2:$G$3001,TB_PY!$Q$2:$Q$3001,"{ln}")*{sg}/{UNIT}'); c.number_format = NUM
    c = wc.cell(row=rr_, column=3, value=f'=SUMIFS(TB_CY!$D$2:$D$3001,TB_CY!$R$2:$R$3001,"{ln}")*{sg}/{UNIT}'); c.number_format = NUM
    c = wc.cell(row=rr_, column=4, value=f"=B{rr_}-C{rr_}"); c.number_format = NUM
    rr_ += 1
wc.cell(row=rr_, column=1, value="Total absolute difference").font = f_b
c = wc.cell(row=rr_, column=4, value=f"=SUMPRODUCT(ABS(D{first}:D{rr_-1}))"); c.number_format = NUM; c.font = f_b
wc.cell(row=n + 1, column=1, value="Roll-forward: PY company closing = CY opening (see table below)").font = f_base
c = wc.cell(row=n + 1, column=2, value=f'=IF(COUNTIF(TB_PY!$A$2:$A$3001,"?*")=0,0,D{rr_})'); c.number_format = NUM
wc.cell(row=n + 1, column=4, value=f'=IF(ABS(B{n+1})<1,"OK","ERROR")').font = f_b

# ---------------------------------------------------------------- Review points
wr = wb.create_sheet("Review Points", 5)
setw(wr, [5, 60, 18, 70])
wr["A1"] = f'="Review points for engagement partner - "&{CO}'; wr["A1"].font = f_title
hdr(wr, 3, ["#", "Observation", "Amount (Rs)", "Treatment in this draft / action"])
def led(name, col="G", sign=-1): return f'={sign}*SUMIFS(TB_CY!${col}$2:${col}$3001,TB_CY!$A$2:$A$3001,"{name}")'
import re as _re
def _amount(a):
    """Config amount tokens: {ledger:Name} (Dr +ve), {ledger_cr:Name}, {note:LINE} (Rs), {input:Setup label}."""
    if not a: return ""
    if isinstance(a, (int, float)): return a
    m = _re.fullmatch(r"\{(ledger|ledger_cr|note|input):(.+)\}", a)
    if not m: return a
    kind, arg = m.groups()
    if kind == "ledger": return led(arg)
    if kind == "ledger_cr": return led(arg, sign=1)
    if kind == "note": return f"={NOTE_TOT[arg][0]}*{UNIT}" if arg in NOTE_TOT else ""
    return f"={INP[arg]}" if arg in INP else ""
RP = [(o, _amount(a), t) for o, a, t in CFG.get("review_points", [])]
RP += [
 ("Lines with no balance in either year are hidden on the face and in the notes; note numbers skip them.", "", "Unhide the rows if a balance appears after a re-pull, or rebuild from the app."),
 ("Notes 1-2 (corporate information, accounting policies), related parties (AS 18), ratios and other disclosures are generated from standard wording and the client config.", "", "Partner to review the wording before signing." + ("" if ("TR" in SKIP and "TP" in SKIP) else " Ageing schedules for trade receivables / payables are not generated by the tool - add from Tally bills outstanding.")),
]
for i, (o, a, t) in enumerate(RP, 4):
    wr.cell(row=i, column=1, value=i - 3).font = f_base
    wr.cell(row=i, column=2, value=o).font = f_base
    c = wr.cell(row=i, column=3, value=a); c.number_format = NUM
    wr.cell(row=i, column=4, value=t).font = f_base
    for col in (2, 4): wr.cell(row=i, column=col).alignment = Alignment(wrap_text=True, vertical="top")

# order sheets
order = ["Setup", "Checks", "BS", "PL", "Cash Flow", "Notes", "Ratios", "Review Points", "TB_CY", "TB_PY", "Map_Groups", "Map_Ledgers", "Heads"]
if "Related_Parties" in wb.sheetnames: order.insert(order.index("TB_CY"), "Related_Parties")
wb._sheets = [wb[n] for n in order if n in wb.sheetnames]
for wsx in wb.worksheets:
    wsx.sheet_view.showGridLines = wsx.title in ("TB_CY", "TB_PY", "Map_Groups", "Map_Ledgers", "Heads")
    for p in (wsx.page_setup,):
        p.orientation = "portrait"; p.fitToWidth = 1; p.fitToHeight = 0
    wsx.sheet_properties.pageSetUpPr.fitToPage = True
wb["Notes"].print_title_rows = "1:5"
wb.calculation.fullCalcOnLoad = True
HIDE["PL"] += [r11, r12, r13, r14]
# Renumber face items so hidden lines leave no gaps: (1)(2).. sections and (a)(b).. items on BS
import string as _st
_hidden_bs = set(HIDE["BS"])
# hide a section / group header when every row under it is hidden
_rowsA = [(c[0].row, c[0].value) for c in wbsh.iter_rows(min_col=1, max_col=1) if isinstance(c[0].value, str)]
def _lvl(v):
    if _re.match(r"^(I|II)\. ", v) or v == "TOTAL": return 0
    if _re.match(r"^\(\d\) ", v): return 1
    if _re.match(r"^\([a-h]\) ", v): return 2
    if _re.match(r"^\((i|ii|iii|iv|A|B)\) ", v): return 3
    return None
for k_, (rw, v) in enumerate(_rowsA):
    L_ = _lvl(v)
    if L_ not in (1, 2) or rw in _hidden_bs: continue
    kids = []
    for rw2, v2 in _rowsA[k_ + 1:]:
        L2 = _lvl(v2)
        if L2 is None or L2 <= L_: break
        kids.append(rw2)
    has_cells = wbsh.cell(row=rw, column=3).value not in (None, "")
    if kids and not has_cells and all(x in _hidden_bs for x in kids):
        _hidden_bs.add(rw); HIDE["BS"].append(rw)
_sec = 0; _item = 0
for row_ in wbsh.iter_rows(min_col=1, max_col=1):
    c_ = row_[0]; v_ = c_.value
    if not isinstance(v_, str) or c_.row in _hidden_bs: continue
    if v_.startswith("I. ") or v_.startswith("II. "): _sec = 0; continue
    m_ = _re.match(r"^\((\d)\) (.*)", v_)
    if m_:
        _sec += 1; _item = 0; c_.value = f"({_sec}) {m_.group(2)}"; continue
    m_ = _re.match(r"^\(([a-h])\) (.*)", v_)
    if m_:
        c_.value = f"({_st.ascii_lowercase[_item]}) {m_.group(2)}"; _item += 1
PL_RELABEL = {"IX. Profit before tax (VII - VIII)": "V. Profit before tax (III - IV)", "X. Tax expense:": "VI. Tax expense:",
              "XV. Profit / (loss) for the period (XI + XIV)": "VII. Profit for the year (V - VI)",
              "XVI. Earnings per equity share:": CFG.get("eps_label", "VIII. Earnings per equity share:")}
for row_ in wp.iter_rows(min_col=1, max_col=1):
    if row_[0].value in PL_RELABEL: row_[0].value = PL_RELABEL[row_[0].value]
# ---------------------------------------------------------------- presentation pass
_hid = {k: set(v) for k, v in HIDE.items()}
for ws_ in (wbsh, wp, wn):
    for row_ in ws_.iter_rows():
        for c_ in row_:
            f_ = c_.font
            if f_ is None or f_.name != "Arial":
                c_.font = Font(name="Arial", size=10, bold=bool(f_ and f_.b), italic=bool(f_ and f_.i))
            if isinstance(c_.value, str) and "{LASTNOTE}" in c_.value:
                c_.value = c_.value.replace("{LASTNOTE}", str(LASTNOTE))
            if c_.column >= 3 and c_.row > 6 and isinstance(c_.value, str) and c_.value.startswith("=") and c_.alignment.horizontal is None:
                c_.alignment = Alignment(horizontal="right")
def _style_face(ws_, last):
    for rr_ in range(7, last + 1):
        v_ = ws_.cell(row=rr_, column=1).value
        if not isinstance(v_, str): continue
        has_num = ws_.cell(row=rr_, column=3).value not in (None, "")
        bold_ = ws_.cell(row=rr_, column=1).font.b
        if ws_ is wbsh and _re.match(r"^(I|II)\. ", v_): kind = "section"
        elif v_ == "TOTAL" or v_.startswith("VII. Profit for the year"): kind = "grand"
        elif bold_ and not has_num: kind = "sub"
        elif bold_: kind = "total"
        else: kind = None
        if kind: P.style_row(ws_, rr_, 1, 4, kind)
        ws_.cell(row=rr_, column=2).alignment = Alignment(horizontal="center")
_style_face(wbsh, as_tot); _style_face(wp, PL_LAST)
P.frame(wbsh, 6, as_tot, 1, 4); P.frame(wp, 6, PL_LAST, 1, 4)
for b_ in NOTE_BLOCKS:
    if b_[1] is None: b_[1] = b_[0]
    # inner lines only inside a table: from its first to its last row with figures, a merged paragraph ends the table
    _mrg = {m_.min_row for m_ in wn.merged_cells.ranges if m_.max_col >= 3 and b_[0] <= m_.min_row <= b_[1]}
    _sk, _seg = {b_[0]}, []
    for rr_ in list(range(b_[0] + 1, b_[1] + 1)) + [None]:
        if rr_ is None or rr_ in _mrg:
            _v = [x_ for x_ in _seg if wn.cell(row=x_, column=3).value not in (None, "") or wn.cell(row=x_, column=4).value not in (None, "")]
            _sk |= {x_ for x_ in _seg if not _v or x_ < _v[0] or x_ > _v[-1]}
            if rr_ is not None: _sk.add(rr_)
            _seg = []
        else: _seg.append(rr_)
    P.frame(wn, b_[0], b_[1], 1, 4, skip_inner_rows=_sk)
for ws_, tr in ((wbsh, None), (wp, None), (wn, "1:5")):
    P.page(ws_, tr)
for sh, rows_ in HIDE.items():
    for n_ in rows_: wb[sh].row_dimensions[n_].hidden = True
import json
_hts = {str(i): (wn.row_dimensions[i].height or 13.5) for i in range(1, wn.max_row + 1)}
json.dump({"subrows": SUBROWS, "notes": [b_[:2] for b_ in NOTE_BLOCKS], "heights": _hts, "hidden": sorted(_hid.get("Notes", []))},
          open(OUT + ".subrows.json", "w"))
wb.save(OUT)
print("saved", OUT)
