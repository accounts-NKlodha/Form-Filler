"""AOC-4 document set for the firm's standard template (notice, board's report, auditor's report + CARO annexure,
SAP & notes, shareholder / director lists), rolled forward from last year's signed documents and filled from the
cached Schedule III workbook, so every figure agrees with the accounts.

Usage: make_docs_std.py <client.json> <schedule III.xlsx> <last-year dir> <out dir>

Last-year dir file names (any missing one is skipped; a missing notice uses app/templates/notice.docx):
  notice.docx, board report.docx, auditors report.docx, sap.docx, Shareholders list.xlsx, Directors list.xlsx
Client cfg "docs" keys: short, doc_date, agm_date, agm_time, place, list_date, ly_dates (list), dec, ops_text,
  audit_trail ("used" / "not used"), caro (bool), caro_clauses ([[heading, text, flag]]), rp_text, name_fixes ([[old, new]]),
  policy_note, udin."""
import os, re, sys, json, copy, datetime as dt
import docx, openpyxl
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from docroll import inr, paras, replace, replace_all, year_pairs, set_text, cell, highlight, delete, find

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FLAGS = []


def ordsfx(n): return "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
def long_date(d): return f"{d.day}{ordsfx(d.day)} {d.strftime('%B %Y')}"
def pdate(s): return dt.datetime.strptime(s, "%d/%m/%Y").date()


def load(xlsx):
    wb = openpyxl.load_workbook(xlsx, data_only=True)
    st = {str(r[0]).strip(): r[1] for r in wb["Setup"].iter_rows(max_col=2, values_only=True) if r[0]}

    def rows(sheet):
        out = {}
        ws = wb[sheet]
        for i, r in enumerate(ws.iter_rows(values_only=True), 1):
            if ws.row_dimensions[i].hidden: continue
            lab = next((x for x in r if isinstance(x, str) and x.strip()), None)
            nums = [x for x in r if isinstance(x, (int, float)) and not isinstance(x, bool)]
            if lab and len(nums) >= 2: out.setdefault(lab.strip(), (nums[-2] or 0, nums[-1] or 0))
        return out
    pl, notes = rows("PL"), rows("Notes")
    rp = [r for r in wb["Related_Parties"].iter_rows(min_row=2, values_only=True) if r[0]]
    return st, pl, notes, rp


def pick(d, *prefixes):
    for p in prefixes:
        for k, v in d.items():
            if k.startswith(p): return v
    return (0, 0)


def main(cfg_path, xlsx, ly, out):
    cfg = json.load(open(cfg_path)); D = cfg["docs"]; S = cfg["setup"]
    st, pl, notes, rp = load(xlsx)
    os.makedirs(out, exist_ok=True)
    FYE = int(str(st["Current year - balance sheet date"])[-4:]); FY, PFY = f"{FYE-1}-{FYE}", f"{FYE-2}-{FYE-1}"
    CO = st["Company name"]; SHORT = D.get("short", CO)
    DOC, AGM = D["doc_date"], pdate(D["agm_date"]); DEC = D.get("dec", 0)
    UDIN = D.get("udin") or "[UDIN to be generated]"
    ARNO = st.get("Annual report number (e.g. 32nd)", "")
    BMS = [x.strip() for x in str(st.get("Board meeting dates", "")).split(",") if x.strip()]
    PRES = [x.strip() for x in str(st.get("Directors present at each board meeting", "")).split(",")]
    STRENGTH = str(st.get("Board strength (number of directors)", 2))
    D1, D2 = st["Signing director 1 name"].upper(), st["Signing director 2 name"].upper()
    num = lambda x: ("0.00" if DEC else "0") if not x else inr(x, DEC)

    rev, oi = pick(pl, "I. Revenue"), pick(pl, "II. Other income")
    fin, dep = pick(pl, "Finance costs"), pick(pl, "Depreciation")
    pbt, pat = pick(pl, "V. Profit before tax"), pick(pl, "VII. Profit for the year", "IX. Profit")
    ct, dtx = pick(pl, "(1) Current tax"), pick(pl, "(2) Deferred tax")
    aud = pick(notes, "Audit fees", "Payment to auditors", "As auditor")
    y = lambda f: tuple(f(i) for i in (0, 1))
    tot_inc = y(lambda i: rev[i] + oi[i]); tax = y(lambda i: ct[i] + dtx[i])
    pbidt = y(lambda i: pbt[i] + fin[i] + dep[i]); pbdt = y(lambda i: pbt[i] + dep[i])

    kmp = [r for r in rp if str(r[2]).startswith("Key")]
    rel = [r for r in rp if not str(r[2]).startswith(("Key", "Enterprise"))]
    def s(rows, nat, i, sign=1): return sum(sign * (r[i] or 0) for r in rows if r[3] == nat)
    rem_py_ovr = next((v for k, v in (cfg.get("rp_py_override") or {}).items() if k.startswith("Key") and "remuneration" in k.lower()), None)
    rem = {"kmp": (s(kmp, "remuneration", 5), rem_py_ovr if rem_py_ovr is not None else s(kmp, "remuneration", 8)),
           "rel": (s(rel, "remuneration", 5) + s(rel, "salary", 5), s(rel, "remuneration", 8) + s(rel, "salary", 8))}
    loan = {g: {"taken": (s(rows, "loan_taken", 4), s(rows, "loan_taken", 7)), "repaid": (s(rows, "loan_taken", 5), s(rows, "loan_taken", 8)),
                "bal": (s(rows, "loan_taken", 6), s(rows, "loan_taken", 9))} for g, rows in (("kmp", kmp), ("rel", rel))}

    COMMON = year_pairs(FYE) + [(x, DOC) for x in D.get("ly_dates", [])] + [
        ("KOMAL LODHA & CO", "N K LODHA & CO"), ("FOR N.K LODHA & CO", "FOR N K LODHA & CO"), ("Firm Reg. No.: 0001869S", "FRN: 001869S"),
        ("KOMAL LODHA N", "KOMAL LODHA"), ("(Figures in 00s)", "")] + [tuple(x) for x in D.get("name_fixes", [])]
    COMMON += [(m, UDIN) for m in D.get("ly_udins", [])]
    fn = lambda kind: os.path.join(out, f"{SHORT} - {kind}")
    lyf = lambda n: os.path.join(ly, n)

    # ------------------------------------------------------------ notice
    auditor_agm = pdate(st["Date of AGM appointing auditor"]) if st.get("Date of AGM appointing auditor") else None
    if os.path.exists(lyf("notice.docx")):
        d = docx.Document(lyf("notice.docx"))
        replace_all(d, COMMON + [(m.group(0), f"{ARNO} Annual General Meeting") for p in d.paragraphs
                                 for m in [re.search(r"\d+(st|nd|rd|th) Annual General Meeting", p.text)] if m])
        for p in d.paragraphs:
            m = re.search(r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday), \d+\w\w \w+ \d{4}", p.text)
            if m: replace(p, m.group(0), f"{AGM.strftime('%A')}, {long_date(AGM)}")
        if not (auditor_agm and auditor_agm.year == AGM.year):
            for p in [p for p in d.paragraphs if p.text.strip().startswith(("To appoint / re-appoint Auditors", "For Continuing Auditor", "“RESOLVED THAT pursuant to the provisions of Section 139"))]: delete(p)
        if not D.get("special_business"):
            for p in [p for p in d.paragraphs if p.text.strip().startswith("An explanatory statement pursuant to section 102")]: delete(p)
    else:
        d = docx.Document(os.path.join(APP, "templates", "notice.docx"))
        replace_all(d, [("{{AGM_NO}}", ARNO), ("{{CO}}", CO.upper()), ("{{AGM_DAY}}", AGM.strftime("%A")), ("{{AGM_DATE}}", long_date(AGM)),
                        ("{{ADDR}}", st["Registered office address"].upper()), ("{{AGM_TIME}}", D.get("agm_time", "11:00 A.M.")),
                        ("{{FYE_TEXT}}", f"31st March, {FYE}"), ("{{PLACE}}", D.get("place", "CHENNAI").upper()), ("{{DOC_DATE}}", DOC),
                        ("{{DIR1}}", D1), ("{{DIR2}}", D2), ("{{DIN1}}", st["Signing director 1 DIN"]), ("{{DIN2}}", st["Signing director 2 DIN"]),
                        ("{{CIN}}", st["CIN"])])
        FLAGS.append("Notice: no last-year notice was supplied, so it is built from the firm's standard template.")
    d.save(fn(f"AGM Notice {AGM.year}.docx"))

    # ------------------------------------------------------------ board's report
    if os.path.exists(lyf("board report.docx")):
        d = docx.Document(lyf("board report.docx"))
        replace_all(d, COMMON)
        for p in paras(d):
            t = p.text.strip()
            if t.startswith("Your Directors are pleased to present the"):
                set_text(p, f"Your Directors are pleased to present the {ARNO} Annual Report together with the Audited Financial statements for the year ended 31st March, {FYE}.")
            elif t.startswith("During the year under review your company did well") and D.get("ops_text"):
                set_text(p, D["ops_text"].format(rev=inr(rev[0]), prev=inr(rev[1]), pat=inr(pat[0], DEC), loss=inr(-pat[0], DEC), ppat=inr(pat[1], DEC)))
            elif t.startswith(("The following amount Rs.", "The Company has not transferred any amount to general reserves")):
                set_text(p, f"The Company has not transferred any amount to general reserves during the year {FY}.")
            elif t.startswith(("Based on the company’s performance, the directors are pleased to recommend", "There is no declaration of dividend")) \
                    and str(st.get("Dividend recommended (nil or Rs. per share)", "Nil")).lower() == "nil":
                set_text(p, f"The Board of Directors does not recommend any dividend for the financial year {FY}.")
            elif re.match(r"\d+ meetings of the Board", t):
                replace(p, re.match(r"\d+ meetings", t).group(0), f"{len(BMS)} meetings")
            elif t.startswith("At the Annual General Meeting held on") and auditor_agm:
                m = re.match(r"At the Annual General Meeting held on [^,]*,", t)
                if m: replace(p, m.group(0), f"At the Annual General Meeting held on {st['Date of AGM appointing auditor']},")
                m = re.search(r"calendar year \d{4}", p.text)
                if m: replace(p, m.group(0), f"calendar year {st['Auditor term ends in year']}")
            elif t.startswith(("There are no Related Party Transactions", "All contracts/arrangements/transactions entered")) and D.get("rp_text"):
                set_text(p, D["rp_text"])
        t0 = d.tables[0]
        vals = {"Sales and Other Income": tot_inc, "Operating Profit (PBIDT)": pbidt, "Interest Cost": fin,
                "Profit before Depreciation (PBDT)": pbdt, "Depreciation": dep, "Profit before Tax": pbt,
                "Provision for Taxation": tax, "Profit after Tax": pat}
        for r in t0.rows[1:]:
            k = r.cells[0].text.strip()
            if k in vals: cell(r.cells[1], num(vals[k][0])); cell(r.cells[2], num(vals[k][1]))
        t1 = d.tables[1]
        for r in list(t1.rows)[1:]: r._tr.getparent().remove(r._tr)
        for j, b in enumerate(BMS):
            row = t1.add_row()
            for k, v in enumerate((b, STRENGTH, PRES[j] if j < len(PRES) and PRES[j] else STRENGTH)): cell(row.cells[k], v)
        d.save(fn(f"Board's Report FY{FYE-1}-{str(FYE)[2:]}.docx"))

    # ------------------------------------------------------------ auditor's report (+ CARO annexure)
    if os.path.exists(lyf("auditors report.docx")):
        d = docx.Document(lyf("auditors report.docx"))
        replace_all(d, COMMON)
        for p in paras(d):
            t = p.text.strip()
            if t.startswith("This report does not include a statement on the matters specified in paragraph 3 and 4") and D.get("caro"):
                set_text(p, "As required by the Companies (Auditor’s Report) Order, 2020 (“the Order”), issued by the Central Government "
                            "in terms of Section 143(11) of the Act, we give in Annexure A a statement on the matters specified in paragraphs 3 "
                            "and 4 of the Order, to the extent applicable.")
            elif t.startswith("Based on our examination which included test checks, the company has"):
                if D.get("audit_trail") == "used":
                    set_text(p, "Based on our examination which included test checks, the company has used an accounting software for maintaining "
                                "its books of account which has a feature of recording audit trail (edit log) facility and the same has operated "
                                "throughout the year for all relevant transactions recorded in the software. Further, during the course of our audit "
                                "we did not come across any instance of audit trail feature being tampered with.")
                elif D.get("audit_trail") == "not used":
                    set_text(p, "Based on our examination which included test checks, the company has not used an accounting software for "
                                "maintaining its books of account which has a feature of recording audit trail (edit log) facility.")
            if UDIN in p.text and "[" in UDIN: highlight(p)
        d.save(fn(f"Auditor's Report FY{FYE-1}-{str(FYE)[2:]}.docx"))
        if D.get("caro"): caro_annexure(D, st, FYE, DOC, UDIN, fn(f"Auditor's Report - CARO Annexure A FY{FYE-1}-{str(FYE)[2:]}.docx"))

    # ------------------------------------------------------------ SAP and notes
    if os.path.exists(lyf("sap.docx")):
        d = docx.Document(lyf("sap.docx"))
        replace_all(d, COMMON)
        kmp_names = list(dict.fromkeys(r[0].upper() for r in kmp))
        rel_names = list(dict.fromkeys(r[0].upper() for r in rel))
        sec = None
        for p in d.paragraphs:
            t = p.text.strip()
            if re.match(r"Note No\.:", t): set_text(p, f"Note No.: {D.get('policy_note', 2)}")
            m = re.match(r"Salaries includes directors remuneration on account of salary Rs\. .*", t)
            if m: set_text(p, f"Salaries include directors' remuneration of Rs. {inr(rem['kmp'][0])}/- (Previous Year Rs. {inr(rem['kmp'][1])}/-).")
            if t.startswith("(I) Key Management"): sec = ("kmp", 0); continue
            if t.startswith("(II) Relative"): sec = ("rel", 0); continue
            if t.startswith("Transactions with Related parties") or t.startswith("(III)"): sec = None
            if sec and re.fullmatch(r"\d+\.(\s*\S.*)?", t):
                names = kmp_names if sec[0] == "kmp" else rel_names
                k = sec[1]; sec = (sec[0], k + 1)
                set_text(p, f"\t{k+1}. {names[k]}" if k < len(names) else ("\tNIL" if k == 0 else ""))
        for r in d.tables[0].rows:
            lab = r.cells[0].text.strip()
            if lab in ("Audit Fees", "Total"): cell(r.cells[1], inr(aud[0])); cell(r.cells[2], inr(aud[1]))
        for r in d.tables[2].rows:
            if r.cells[0].text.strip().startswith("Remuneration"):
                for k, v in enumerate((rem["kmp"][0], rem["rel"][0], rem["kmp"][1], rem["rel"][1]), 1): cell(r.cells[k], inr(v))
        t3 = d.tables[3]
        for r in t3.rows:
            lab = r.cells[0].text.strip()
            key = "taken" if lab == "Loans Taken" else "repaid" if lab == "Loans Repaid" else None
            if key:
                for k, v in enumerate((loan["kmp"][key][0], loan["rel"][key][0], loan["kmp"][key][1], loan["rel"][key][1]), 1): cell(r.cells[k], inr(v))
        if any(v for g in loan.values() for v in g["bal"]):
            src = t3.rows[-1]._tr; new = copy.deepcopy(src); src.addnext(new); bal = t3.rows[-1]
            cell(bal.cells[0], "Balance payable / (receivable) at the year end")
            fmt = lambda v: inr(v) if v >= 0 else f"({inr(-v)})"
            for k, v in enumerate((loan["kmp"]["bal"][0], loan["rel"]["bal"][0], loan["kmp"]["bal"][1], loan["rel"]["bal"][1]), 1): cell(bal.cells[k], fmt(v))
        for p in paras(d):
            if UDIN in p.text and "[" in UDIN: highlight(p)
        d.save(fn(f"SAP and Notes FY{FYE-1}-{str(FYE)[2:]}.docx"))

    # ------------------------------------------------------------ lists
    LD = D.get("list_date", DOC)
    for src, kind in (("Shareholders list.xlsx", "Shareholders List"), ("Directors list.xlsx", "Directors List")):
        if not os.path.exists(lyf(src)): continue
        x = openpyxl.load_workbook(lyf(src))
        pairs = [(o, n) for o, n in year_pairs(FYE) if "/" in o or "March" in o] + [(o, LD) for o in D.get("ly_list_dates", [])] + [tuple(v) for v in D.get("name_fixes", [])]
        for ws in x.worksheets:
            for row in ws.iter_rows():
                for c in row:
                    if isinstance(c.value, str) and not c.value.startswith("="):
                        v = c.value
                        for o, n in pairs: v = v.replace(o, n)
                        if v != c.value: c.value = v
        x.save(fn(f"{kind} 31-03-{FYE}.xlsx"))
    FLAGS.append(f"Dates: documents {DOC}, AGM {AGM.strftime('%A')} {long_date(AGM)}, lists {LD}. UDIN: {UDIN}.")
    json.dump(FLAGS, open(os.path.join(out, "flags.json"), "w"), indent=1)
    return FLAGS


def caro_annexure(D, st, FYE, DOC, UDIN, path):
    d = docx.Document()
    sty = d.styles["Normal"]; sty.font.name = "Calibri"; sty.font.size = Pt(10.5)
    h = d.add_paragraph(); h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = h.add_run("ANNEXURE A TO THE INDEPENDENT AUDITOR’S REPORT"); r.bold = True
    d.add_paragraph(f"(Referred to in paragraph 1 under ‘Report on Other Legal and Regulatory Requirements’ section of our report "
                    f"to the Members of {st['Company name'].upper()} of even date for the year ended 31st March, {FYE})")
    d.add_paragraph("To the best of our information and according to the explanations provided to us by the Company and the books of "
                    "account and records examined by us in the normal course of audit, we state that:")
    for k, (head, text, flag) in enumerate(D["caro_clauses"], 1):
        p = d.add_paragraph(); r = p.add_run(f"({['i','ii','iii','iv','v','vi','vii','viii','ix','x','xi','xii','xiii','xiv','xv','xvi','xvii','xviii','xix','xx','xxi'][k-1]}) {head}"); r.bold = True
        q = d.add_paragraph(text)
        if flag: highlight(q)
    d.add_paragraph()
    for line in (f"For {st['Auditor firm name'].upper()}", "Chartered Accountants", f"FRN: {st['Auditor FRN']}", "", "",
                 st["Signing partner name"].upper(), st["Partner designation (Proprietor or Partner)"], f"Membership No.: {st['Partner membership number']}",
                 f"UDIN: {UDIN}", f"Place: {st.get('Place of signing', 'Chennai')}", f"Date: {DOC}"):
        p = d.add_paragraph(line)
        if "[" in line: highlight(p)
    d.save(path)


if __name__ == "__main__":
    print("\n".join(main(*sys.argv[1:5])))
