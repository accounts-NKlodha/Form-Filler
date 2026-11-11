# Included by build_sch3.py (exec) after the PL is built: related parties (AS 18), ratios, other disclosures,
# board signature at the end of the Notes. Shares build_sch3's globals.
r = NR

def _blank_head(no, title):
    note_title(no, title)

# ---------------------------------------------------------------- Related parties (AS 18)
RPL = CFG.get("related_parties", [])
if RPL:
    wrp = wb.create_sheet("Related_Parties")
    setw(wrp, [36, 40, 44, 12, 15, 15, 15, 15, 15, 15])
    hdr(wrp, 1, ["Party", "Tally ledger", "Relationship (AS 18)", "Nature", "CY credits", "CY debits", "CY closing (Cr +)",
                 "PY credits", "PY debits", "PY closing (Cr +)"])
    for i, (party, ledger, rel, nat) in enumerate(RPL, 2):
        for j, v in enumerate([party, ledger, rel, nat], 1): wrp.cell(row=i, column=j, value=v).font = f_in if j in (3, 4) else f_base
        for j, (tb, col) in enumerate([("TB_CY", "F"), ("TB_CY", "E"), ("TB_CY", "G"), ("TB_PY", "F"), ("TB_PY", "E"), ("TB_PY", "G")], 5):
            sg = "-" if col == "E" else ""
            c = wrp.cell(row=i, column=j, value=f'={sg}SUMIFS({tb}!${col}$2:${col}$3001,{tb}!$A$2:$A$3001,$B{i})'); c.number_format = NUM
    wrp.freeze_panes = "A2"
    _n = len(RPL) + 1
    def rps(col, rel, nat, sign=1):
        return f'{"-" if sign < 0 else ""}SUMIFS(Related_Parties!${col}$2:${col}${_n},Related_Parties!$C$2:$C${_n},"{rel}",Related_Parties!$D$2:$D${_n},"{nat}")'
    rp_start = r
    no = note_no[0]; note_no[0] += 1
    note_title(no, "Related party disclosures (AS 18)")
    wn.cell(row=r, column=2, value="(a) Names of related parties and nature of relationship").font = P.f_note; r += 1
    rels = []
    for _, _, rel, _ in RPL:
        if rel not in rels: rels.append(rel)
    for rel in rels:
        names = []
        for party, _, rel2, _ in RPL:
            if rel2 == rel and party not in names: names.append(party)
        P.para(wn, r, 2, 4, rel, WCH, bold=True, indent=1); wn.row_dimensions[r].height = 15; r += 1
        P.para(wn, r, 2, 4, ", ".join(names), WCH, indent=2); r += 1
    r += 1
    wn.cell(row=r, column=2, value="(b) Transactions during the year and balances outstanding").font = P.f_note; r += 1
    col_head(("Nature of transaction", None, None), bs=False)
    NATS = [("loan_taken", [("Loans received (including interest credited)", "E", "H", 1), ("Loans repaid", "F", "I", 1),
                            ("Balance payable / (receivable) at the year end", "G", "J", 1)]),
            ("remuneration", [("Directors' remuneration", "F", "I", 1)]),
            ("salary", [("Salary / remuneration", "E", "H", 1)]),
            ("loan_given", [("Loans given (including interest)", "F", "I", 1), ("Loans received back", "E", "H", 1),
                            ("Balance receivable at the year end", "G", "J", -1)])]
    for rel in rels:
        wn.cell(row=r, column=2, value=rel).font = f_b; hr_ = r; r += 1
        kids = []
        for nat, items in NATS:
            if not any(x[2] == rel and x[3] == nat for x in RPL): continue
            for lab, ccy, cpy, sg in items:
                wn.cell(row=r, column=2, value=lab).alignment = Alignment(indent=1)
                c1 = wn.cell(row=r, column=3, value=f"={rps(ccy, rel, nat, sg)}/{UNIT}")
                _po = CFG.get("rp_py_override", {}).get(f"{rel}|{lab}")
                c2 = wn.cell(row=r, column=4, value=_po if _po is not None else f"={rps(cpy, rel, nat, sg)}/{UNIT}")
                for c in (c1, c2): c.number_format = NUM
                SUBROWS.append((r, ["C", "D"])); kids.append(r); r += 1
    P.para(wn, r, 2, 4, CFG.get("rp_footnote", "Related parties are as identified by the management and relied upon by the auditors. "
           "Transactions with related parties are in the ordinary course of business. Loans received include interest credited to the lenders' accounts."), WCH, font=P.f_foot); r += 1
    end_note(); r += 1

# ---------------------------------------------------------------- Ratios (Schedule III para 6.L(xv) / 7)
def T(line, k): return NOTE_TOT[line][k]
def _sum(lines, k): return "(" + "+".join(T(l, k) for l in lines) + ")"
CA = ["CI", "INV", "TR", "CCE", "STLA", "OCA"]; CLI = ["STB", "TP", "OCL", "STP"]
EQ = ["SC", "RS"]; DEBT = ["LTB", "STB"]
_eq_py_open = f'((SUMIFS(TB_PY!$D$2:$D$3001,TB_PY!$R$2:$R$3001,"SC")+SUMIFS(TB_PY!$D$2:$D$3001,TB_PY!$R$2:$R$3001,"RS"))/{UNIT})'
no = note_no[0]; note_no[0] += 1
RATIO_NOTE = no
note_title(no, "Financial ratios")
P.para(wn, r, 2, 4, f"The ratios required by Schedule III (Division I, para 6.L(xv)), with their computation and the reasons for "
       f"variances of more than 25%, are set out in the statement of financial ratios annexed as part of this Note {no}.", WCH, indent=1); r += 1
end_note(); r += 1

# Financial Ratios sheet (part of the notes)
_E = lambda k: _sum(EQ, k); _D = lambda k: _sum(DEBT, k); _CA = lambda k: _sum(CA, k); _CL = lambda k: _sum(CLI, k)
_EBIT = (f"(PL!$C${r9}+{T('FIN',0)})", f"(PL!$D${r9}+{T('FIN',1)})")

def _pyo(line):
    sg = "-" if line in ("INV", "TR", "CCE", "STLA", "OCA", "LTLA", "PPE") else ""
    return f'({sg}SUMIFS(TB_PY!$D$2:$D$3001,TB_PY!$R$2:$R$3001,"{line}")/{UNIT})'
def _avg(line):
    if line in SKIP: return None
    return (f"(({T(line,0)}+{T(line,1)})/2)", f"(({T(line,1)}+{_pyo(line)})/2)")
def _k(line): return "na" if line in SKIP else "times"
def _tot0(lines, k): return "(" + "+".join(f"N({T(l,k)})" for l in lines if l in NOTE_TOT and l not in SKIP) + "+0)"
_COGS = (_tot0(["PUR", "COMC", "CHINV"], 0), _tot0(["PUR", "COMC", "CHINV"], 1))
_PURX = (_tot0(["PUR", "COMC"], 0), _tot0(["PUR", "COMC"], 1))
_LTREP = lambda tb: f'(-SUMIFS({tb}!$E$2:$E$3001,{tb}!$Q$2:$Q$3001,"LTB")/{UNIT})'
_DS_K = "na" if ("LTB" in SKIP and "STB" in SKIP) else "times"
_DS_N = (f"({PROFIT[0]}+N({T('DEP',0)})+N({T('FIN',0)}))", f"({PROFIT[1]}+N({T('DEP',1)})+N({T('FIN',1)}))") if _DS_K != "na" else None
_DS_D = (f"(N({T('FIN',0)})+{_LTREP('TB_CY')})", f"(N({T('FIN',1)})+{_LTREP('TB_PY')})") if _DS_K != "na" else None
RAT = [  # name, numerator label, (cy, py), denominator label, (cy, py), kind
 ("Current ratio", "Current assets", (_CA(0), _CA(1)), "Current liabilities", (_CL(0), _CL(1)), "times"),
 ("Debt-equity ratio", "Total borrowings", (_D(0), _D(1)), "Shareholders' equity", (_E(0), _E(1)), "times"),
 ("Debt service coverage ratio", "Earnings available for debt service (PAT + depreciation + finance costs)", _DS_N, "Debt service (finance costs + long-term principal repaid)", _DS_D, _DS_K),
 ("Return on equity", "Profit after tax", (PROFIT[0], PROFIT[1]), "Average shareholders' equity",
  (f"(({_E(0)}+{_E(1)})/2)", f"(({_E(1)}+{_eq_py_open})/2)"), "pct"),
 ("Inventory turnover ratio", "Cost of materials / goods consumed", _COGS, "Average inventory", _avg("INV"), _k("INV")),
 ("Trade receivables turnover ratio", "Revenue from operations", (T('REV',0), T('REV',1)), "Average trade receivables", _avg("TR"), _k("TR")),
 ("Trade payables turnover ratio", "Purchases", _PURX, "Average trade payables", _avg("TP"), _k("TP")),
 ("Net capital turnover ratio", "Revenue from operations", (T('REV',0), T('REV',1)), "Working capital (current assets - current liabilities)",
  (f"({_CA(0)}-{_CL(0)})", f"({_CA(1)}-{_CL(1)})"), "times"),
 ("Net profit ratio", "Profit after tax", (PROFIT[0], PROFIT[1]), "Revenue from operations", (T('REV',0), T('REV',1)), "pct"),
 ("Return on capital employed", "Profit before interest and tax", _EBIT, "Capital employed (equity + borrowings)",
  (f"({_E(0)}+{_D(0)})", f"({_E(1)}+{_D(1)})"), "pct"),
 ("Return on investment", "Income from investments", None, "Average investments", None, "na"),
]
wra = wb.create_sheet("Ratios")
setw(wra, [6, 30, 34, 34, 15, 15, 13, 56])
P.title_block(wra, 8, CO, CIN, ADDR, f'="Note {no}: Financial ratios for the year ended "&{CYD}', '"Schedule III, Division I - para 6.L(xv)"')
hdr(wra, 6, ["No.", "Ratio", "Numerator", "Denominator", None, None, "Variance", "Reason for variance of more than 25%"])
wra["E6"] = f'="FY "&YEAR(DATEVALUE({CYD}))-1&"-"&RIGHT(YEAR(DATEVALUE({CYD})),2)'
wra["F6"] = f'="FY "&YEAR(DATEVALUE({PYD}))-1&"-"&RIGHT(YEAR(DATEVALUE({PYD})),2)'
P.header_row(wra, 6, 1, 8, height=32)
_rc = CFG.get("ratio_comments", {})
rr = 7; RAT_ROWS = []
for i, (nm, nl, nv, dl, dv, kind) in enumerate(RAT, 1):
    vals = [i, nm, nl, dl]
    for j, v in enumerate(vals, 1):
        c = wra.cell(row=rr, column=j, value=v); c.font = P.f_b if j == 2 else P.f_base
        c.alignment = Alignment(horizontal="center" if j == 1 else "left", vertical="center", wrap_text=True)
    if kind == "na":
        for col in (5, 6):
            c = wra.cell(row=rr, column=col, value="NA"); c.alignment = Alignment(horizontal="center", vertical="center"); c.font = P.f_foot
        c = wra.cell(row=rr, column=8, value="Not applicable to the Company's business"); c.font = P.f_foot
        c.alignment = Alignment(vertical="center", wrap_text=True)
    else:
        fmt = "0.00%" if kind == "pct" else '0.00" times"'
        for col, k in ((5, 0), (6, 1)):
            c = wra.cell(row=rr, column=col, value=f"=IFERROR({nv[k]}/{dv[k]},0)"); c.number_format = fmt
            c.alignment = Alignment(horizontal="right", vertical="center")
        c = wra.cell(row=rr, column=7, value=f"=IFERROR(E{rr}/F{rr}-1,0)"); c.number_format = '0.0%;(0.0%);"-"'
        c.alignment = Alignment(horizontal="right", vertical="center")
        txt = _rc.get(nm, "")
        wra.cell(row=rr, column=10, value=txt or "Reason to be given")  # helper text (a formula literal is capped at 255 characters)
        c = wra.cell(row=rr, column=8, value=f'=IF(ABS(G{rr})>0.25,J{rr},"Variance within 25%")')
        c.font = P.f_base; c.alignment = Alignment(vertical="center", wrap_text=True)
    wra.row_dimensions[rr].height = 40 if (kind != "na" and len(_rc.get(nm, "")) > 90) else 30
    RAT_ROWS.append((rr, nm, nl, nv, dl, dv, kind)); rr += 1
P.frame(wra, 6, rr - 1, 1, 8)
for x in range(7, rr, 2):
    for col in range(1, 9): wra.cell(row=x, column=col).fill = P.fill_tot
rr += 1
wra.cell(row=rr, column=2, value="Computation of ratios").font = P.f_note
wra.cell(row=rr, column=6, value=f'="("&{LBL}&")"').font = P.f_unit; wra.cell(row=rr, column=6).alignment = Alignment(horizontal="right"); rr += 1
hdr(wra, rr, [None, "Ratio", "Component", None, None, None])
wra.merge_cells(start_row=rr, start_column=3, end_row=rr, end_column=4)
wra.cell(row=rr, column=5, value=f"=E6"); wra.cell(row=rr, column=6, value=f"=F6")
P.header_row(wra, rr, 1, 6, height=22); h0 = rr; rr += 1
for x, nm, nl, nv, dl, dv, kind in RAT_ROWS:
    if kind == "na": continue
    for lab, v in ((nl, nv), (dl, dv)):
        wra.cell(row=rr, column=2, value=nm if lab == nl else None).font = P.f_b
        wra.merge_cells(start_row=rr, start_column=3, end_row=rr, end_column=4)
        wra.cell(row=rr, column=3, value=("Numerator: " if lab == nl else "Denominator: ") + lab).font = P.f_base
        for col, k in ((5, 0), (6, 1)):
            c = wra.cell(row=rr, column=col, value=f"=IFERROR({v[k]},0)"); c.number_format = NUM; c.alignment = Alignment(horizontal="right")
        if lab == dl:
            for col in range(2, 7): P._merge_border(wra.cell(row=rr, column=col), bottom=P.line)
        rr += 1
P.frame(wra, h0, rr - 1, 1, 6)
rr += 1
P.para(wra, rr, 1, 8, "Ratios are computed on the figures in the Balance Sheet and Statement of Profit and Loss. Shareholders' equity is share "
       "capital plus reserves and surplus; borrowings are long-term and short-term borrowings. The Company is a Non-Banking Financial "
       "Company and holds no inventory, trade receivables or trade payables; debt service coverage and return on investment are not applicable.",
       150, font=P.f_foot); rr += 2
P.sign_block(wra, rr, INP, 2, (4, 8), CO)
wra.column_dimensions["J"].hidden = True
wra.print_area = f"A1:H{wra.max_row}"
wra.freeze_panes = "A7"
for row_ in wra.iter_rows():
    for c_ in row_:
        if c_.font is None or c_.font.name != "Arial": c_.font = Font(name="Arial", size=10, bold=bool(c_.font and c_.font.b))
P.page(wra, landscape=True)

# ---------------------------------------------------------------- Other disclosures
no = note_no[0]; note_no[0] += 1
note_title(no, "Other disclosures")
k_ = iter("abcdefghijklmnop")
def _h(t):
    global r
    wn.cell(row=r, column=2, value=f"({next(k_)}) {t}").font = P.f_note; r += 1
_h("Contingent liabilities and commitments")
P.para(wn, r, 2, 4, CFG.get("contingent", "There are no contingent liabilities or capital commitments as at the balance sheet date (previous year: nil)."), WCH, indent=1); r += 2
if "OEXP.AUD" in SUB_CELL:
    _h("Payment to auditors (excluding taxes)")
    col_head(("Particulars", None, None), bs=False)
    wn.cell(row=r, column=2, value="Statutory audit fees").alignment = Alignment(indent=1)
    for col, ref in ((3, SUB_CELL["OEXP.AUD"][0]), (4, SUB_CELL["OEXP.AUD"][1])):
        c = wn.cell(row=r, column=col, value=f"={ref}"); c.number_format = NUM; c.border = b_tot; c.font = f_b
    r += 2
_h("Earnings per share (AS 20)")
col_head(("Particulars", None, None), bs=False)
e0 = r
wn.cell(row=r, column=2, value="Profit after tax attributable to equity shareholders (Rs)").alignment = Alignment(indent=1)
for col, ref in ((3, PROFIT[0]), (4, PROFIT[1])):
    c = wn.cell(row=r, column=col, value=f"={ref}*{UNIT}"); c.number_format = '#,##0.00'
r += 1
wn.cell(row=r, column=2, value="Weighted average number of equity shares").alignment = Alignment(indent=1)
for col, ref in ((3, INP["Weighted avg. equity shares - current year (for EPS)"]), (4, INP["Weighted avg. equity shares - previous year (for EPS)"])):
    c = wn.cell(row=r, column=col, value=f"={ref}"); c.number_format = SHN
r += 1
wn.cell(row=r, column=2, value="Face value per share (Rs)").alignment = Alignment(indent=1)
for col in (3, 4): wn.cell(row=r, column=col, value=f"={FV}").number_format = "0.00"
r += 1
wn.cell(row=r, column=2, value="Basic and diluted earnings per share (Rs)").font = f_b
for col in (3, 4):
    L = get_column_letter(col)
    c = wn.cell(row=r, column=col, value=f"=IFERROR({L}{e0}/{L}{e0+1},0)"); c.number_format = "0.00"; c.font = f_b; c.border = b_tot
r += 2
_h("Dues to micro and small enterprises")
P.para(wn, r, 2, 4, CFG.get("msme", "Based on the information available with the Company, there are no amounts due to micro and small enterprises as defined under the Micro, Small and Medium Enterprises Development Act, 2006 (previous year: nil)."), WCH, indent=1); r += 2
_h("Earnings and expenditure in foreign currency")
P.para(wn, r, 2, 4, f'="Earnings in foreign currency: "&{INP["Foreign exchange earnings (nil or amount)"]}&". Expenditure in foreign currency: "&{INP["Foreign exchange outgo (nil or amount)"]}&" (previous year: nil)."', WCH, indent=1); r += 2
_h("Additional regulatory information (Schedule III)")
for t in CFG.get("regulatory") or [
    "The Company does not hold any immovable property; disclosure of title deeds not held in the name of the Company is not applicable.",
    "The Company has not revalued its property, plant and equipment or intangible assets during the year.",
    "No proceedings have been initiated or are pending against the Company for holding any benami property under the Prohibition of Benami Property Transactions Act, 1988.",
    "The Company has not been declared a wilful defaulter by any bank, financial institution or other lender.",
    "The Company has no transactions or balances with companies struck off under section 248 of the Companies Act, 2013 or section 560 of the Companies Act, 1956.",
    "There are no charges or satisfaction of charges yet to be registered with the Registrar of Companies beyond the statutory period.",
    "The Company has complied with the number of layers prescribed under clause (87) of section 2 of the Act read with the Companies (Restriction on number of Layers) Rules, 2017.",
    "No scheme of arrangement has been approved by the competent authority in terms of sections 230 to 237 of the Companies Act, 2013.",
    "The Company has not advanced, loaned or invested funds, nor received funds, with the understanding that the intermediary or the Company shall lend or invest in other persons or entities identified by or on behalf of the funding party (ultimate beneficiaries).",
    "The Company has no transactions not recorded in the books of account that have been surrendered or disclosed as income in the tax assessments under the Income Tax Act, 1961.",
    "The Company has not traded or invested in crypto currency or virtual currency during the year.",
    "The provisions of section 135 of the Companies Act, 2013 (Corporate Social Responsibility) are not applicable to the Company."]:
    P.para(wn, r, 2, 4, "•  " + t, WCH, indent=1); r += 1
r += 1
_h("Previous year figures")
P.para(wn, r, 2, 4, "Previous year figures have been regrouped and reclassified wherever necessary to conform to the current year's presentation.", WCH, indent=1); r += 1
end_note(); r += 2
LASTNOTE = note_no[0] - 1
P.sign_block(wn, r, INP, 2, (3, 4), CO)
