# Included by build_sch3.py (exec) after extra_notes.py: Cash Flow Statement (AS 3, indirect method).
# Every line is a formula on the trial balances, so CY and PY both work: CY = CY closing less CY opening,
# PY = CY opening (PY closing) less PY company opening. CF_CHK feeds the Checks sheet.
wcf = wb.create_sheet("Cash Flow", 3)
setw(wcf, [64, 6, 21, 21])
P.title_block(wcf, 4, CO, CIN, ADDR, f'="Cash Flow Statement for the year ended "&{CYD}', LBL)
hdr(wcf, 6, ["Particulars", None, None, None])
wcf["C6"] = f'="Year ended "&{CYD}'; wcf["D6"] = f'="Year ended "&{PYD}'
P.header_row(wcf, 6, 1, 4)
_ASSET = ("PPE", "INT", "CWIP", "IAUD", "NCI", "DTA", "LTLA", "ONCA", "CI", "INV", "TR", "CCE", "STLA", "OCA")

def _bal(lines, when):
    """Natural-sign balance of BS lines in display units. when: cy (CY closing), py (CY opening), pyo (PY company opening)."""
    tb, amt, key = {"cy": ("TB_CY", "G", "Q"), "py": ("TB_CY", "D", "R"), "pyo": ("TB_PY", "D", "R")}[when]
    parts = [f'{"-" if l in _ASSET else ""}SUMIFS({tb}!${amt}$2:${amt}$3001,{tb}!${key}$2:${key}$3001,"{l}")' for l in lines]
    return "((" + "+".join(parts) + f")/{UNIT})"

def _chg(lines, sign=1):
    """(CY formula, PY formula) for the increase in the lines; sign -1 turns an asset increase into an outflow."""
    s = "-" if sign < 0 else ""
    return (f"={s}({_bal(lines, 'cy')}-{_bal(lines, 'py')})",
            f"=IF({PYL},0,{s}({_bal(lines, 'py')}-{_bal(lines, 'pyo')}))")

def _pl_row(prefix):
    for rr_ in range(7, PL_LAST + 1):
        v_ = wp.cell(row=rr_, column=1).value
        if isinstance(v_, str) and v_.strip().startswith(prefix): return rr_
    return None

_ct, _dt = _pl_row("(1) Current tax"), _pl_row("(2) Deferred tax")
def _plc(row_, col): return f"N(PL!${col}${row_})" if row_ else "0"
_dep = SUB_CELL.get("DEP.DEP", ("0", "0"))
r = 7
CF = {}
def cf(label, cy=None, py=None, kind=None, indent=0):
    global r
    c = wcf.cell(row=r, column=1, value=label); c.alignment = Alignment(indent=indent)
    if cy is not None:
        for col, v in ((3, cy), (4, py)):
            x = wcf.cell(row=r, column=col, value=v); x.number_format = NUM; x.alignment = Alignment(horizontal="right")
    if kind: P.style_row(wcf, r, 1, 4, kind)
    r += 1
    return r - 1

def tot(rows_):
    return tuple("=" + "+".join(f"{L}{x}" for x in rows_) for L in ("C", "D"))

cf("A. Cash flow from operating activities", kind="section")
a1 = cf("Net profit after tax as per Statement of Profit and Loss", cy=f"={PROFIT[0]}", py=f"={PROFIT[1]}", indent=1)
cf("Adjustments for:", kind="sub", indent=1)
a2 = cf("Depreciation and amortization expense", cy=f"=N({_dep[0]})", py=f"=N({_dep[1]})", indent=2)
a3 = cf("Transfer to contingent provision against standard assets", cy=f"=-N(Notes!$C${rs_cont})", py=f"=-N(Notes!$D${rs_cont})", indent=2)
a4 = cf("Deferred tax expense", cy=f"={_plc(_dt, 'C')}", py=f"={_plc(_dt, 'D')}", indent=2)
a5 = cf("Provision for current tax", cy=f"={_plc(_ct, 'C')}", py=f"={_plc(_ct, 'D')}", indent=2)
op = cf("Operating profit before working capital changes", *tot([a1, a2, a3, a4, a5]), kind="total")
cf("Changes in working capital:", kind="sub", indent=1)
w1 = cf("Increase / (decrease) in borrowings, liabilities and provisions", *_chg(["LTB", "STB", "TP", "OCL", "STP", "OLTL", "LTP"]), indent=2)
w2 = cf("(Increase) / decrease in other current and non-current assets", *_chg(["INV", "TR", "STLA", "OCA", "ONCA"], -1), indent=2)
cg = cf("Cash generated from operations", *tot([op, w1, w2]), kind="total")
tx = cf("Less: Income tax paid", cy=f"=-C{a5}", py=f"=-D{a5}", indent=1)
na = cf("Net cash flow from operating activities (A)", *tot([cg, tx]), kind="total")
r += 1
cf("B. Cash flow from investing activities", kind="section")
i1 = cf("Purchase of property, plant and equipment and investments (net)",
        cy=f"=-({_bal(['PPE', 'INT', 'CWIP', 'NCI', 'CI', 'IAUD'], 'cy')}-{_bal(['PPE', 'INT', 'CWIP', 'NCI', 'CI', 'IAUD'], 'py')})-C{a2}",
        py=f"=IF({PYL},0,-({_bal(['PPE', 'INT', 'CWIP', 'NCI', 'CI', 'IAUD'], 'py')}-{_bal(['PPE', 'INT', 'CWIP', 'NCI', 'CI', 'IAUD'], 'pyo')})-D{a2})", indent=1)
nb = cf("Net cash used in investing activities (B)", *tot([i1]), kind="total")
r += 1
cf("C. Cash flow from financing activities", kind="section")
f1 = cf("(Increase) / decrease in loans given", *_chg(["LTLA"], -1), indent=1)
f2 = cf("Proceeds from issue of share capital", *_chg(["SC"]), indent=1)
nc = cf("Net cash from financing activities (C)", *tot([f1, f2]), kind="total")
r += 1
ni = cf("Net increase / (decrease) in cash and cash equivalents (A + B + C)", *tot([na, nb, nc]), kind="total")
op_c = cf("Cash and cash equivalents at the beginning of the year", cy=f"={_bal(['CCE'], 'py')}", py=f"=IF({PYL},0,{_bal(['CCE'], 'pyo')})", indent=1)
cl = cf("Cash and cash equivalents at the end of the year", *tot([ni, op_c]), kind="grand")
CF_LAST = r - 1
r += 1
cf("Components of cash and cash equivalents", kind="sub")
_cc = []
for code, lab in (("CCE.CASH", "Cash on hand"), ("CCE.BANK", "Balances with banks in current accounts"), ("CCE.FD", "Other bank balances")):
    _cc.append(cf(lab, cy=f'=-SUMIFS(TB_CY!$G$2:$G$3001,TB_CY!$O$2:$O$3001,"{code}")/{UNIT}',
                  py=f'=-SUMIFS(TB_CY!$D$2:$D$3001,TB_CY!$P$2:$P$3001,"{code}")/{UNIT}', indent=1))
if "CCE.FD" not in USED_CODES: wcf.row_dimensions[_cc[-1]].hidden = True
ct_ = cf("Total cash and cash equivalents (Note " + str(NOTE_NO.get("CCE") or "") + ")", *tot(_cc), kind="total")
CF_TBL_END = r - 1
P.frame(wcf, 6, CF_LAST, 1, 4)
CF_CHK = (f"='Cash Flow'!C{cl}-'Cash Flow'!C{ct_}", f"='Cash Flow'!D{cl}-'Cash Flow'!D{ct_}")
r += 1
for t in CFG.get("cf_notes") or [
        "1. The Cash Flow Statement has been prepared under the indirect method set out in Accounting Standard 3, Cash Flow Statements.",
        "2. Previous year figures have been regrouped / reclassified wherever necessary.",
        "3. Figures in brackets represent cash outflows."]:
    P.para(wcf, r, 1, 4, t, 112, font=P.f_foot); r += 1
r += 1
P.sign_block(wcf, r, INP, 1, (3, 4), CO)
wcf.freeze_panes = "A7"
for row_ in wcf.iter_rows(min_row=7):
    for c_ in row_:
        if c_.font is None or c_.font.name != "Arial":
            c_.font = Font(name="Arial", size=10, bold=bool(c_.font and c_.font.b))
P.page(wcf)
