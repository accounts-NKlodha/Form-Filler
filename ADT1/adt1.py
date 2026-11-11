"""ADT-1 (appointment of auditor) for many companies from one workbook.

    python ADT1/adt1.py template            create (or upgrade) ADT1/ADT-1 companies.xlsx
    python ADT1/adt1.py prefill             fill blank cells from earlier filings / master data
    python ADT1/adt1.py columns             (re)build ADT1/adt1_columns.xlsx after ADT-1 was captured (Alt+Shift+D)
    python ADT1/adt1.py plan <CIN or row>   print the fill plan for one company (what Alt+Shift+F would send)

One row per company on the Companies sheet. A blank cell takes the value on the Defaults sheet
(the firm's own auditor details, nature of appointment, number of years...). The dashboard page
http://127.0.0.1:8742/adt1 picks the company that Alt+Shift+F fills next.

Sources the prefill reads (blank cells only, never overwrites what staff typed):
  * Excel files in ADT1/source with a CIN column (company master, last year's ADT-1 list...)
  * filed PDFs (ADT-1, AOC-4, MGT-7/7A) in ADT1/source and in every clients/<name> folder
"""
import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import openpyxl
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

BOOK = HERE / "ADT-1 companies.xlsx"
COLMAP = HERE / "adt1_columns.xlsx"
SOURCE = HERE / "source"
STATE = HERE / "state.json"

YELLOW = PatternFill("solid", fgColor="FFF2CC")
GREEN = PatternFill("solid", fgColor="E2F0D9")
BLUE = PatternFill("solid", fgColor="D9E1F2")
HEAD = PatternFill("solid", fgColor="1F4E78")
GREY = PatternFill("solid", fgColor="EDEDED")

CIN_RE = re.compile(r"\b([UL]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6})\b")

# id, header, hint, allowed values (None = free), default, portal element name(s) (AEM name, stable across companies)
YN = ["Yes", "No"]
COLUMNS = [
    ("status", "Status", "Blank / Ready / Filled / Saved / Submitted / Skip", ["Ready", "Filled", "Saved", "Submitted", "Skip"], None, None),
    ("name", "Company name", "", None, None, None),
    ("cin", "CIN", "21 characters", None, None, "CIN_Number_Other_User"),
    ("class_139", "3(a) Falls under class of cos u/s 139(2)?", "Yes / No", YN, "No", "whetherCompanyIsFallingUnderAnyClassOfCompaniesAsPerSection139_2"),
    ("nature", "3(b) Nature of appointment", "as on the portal", ["Appointment of Auditors in AGM", "Re-appointment of Auditors in AGM",
     "First auditor by Board of directors/ members/ C&AG", "Auditor appointed in case of casual vacancy", "Others"],
     "Appointment of Auditors in AGM", "natureOfAppointment"),
    ("nature_other", "3(b)(i) If others, specify", "", None, None, "IfOthersPleaseSpecify"),
    ("agm_appointed", "3(c) Appointed in AGM?", "Yes / No", YN, "Yes", "whetherAuditorsHasBeenAppointedInTheAnnualGeneralMeeting_AGM"),
    ("agm_date", "3(d) Date of AGM", "DD/MM/YYYY", None, None, "ifYesDateOfAGM"),
    ("joint", "4(b) Joint auditors?", "Yes / No", YN, "No", "whetherJointAuditorsHaveBeenAppointed"),
    ("category", "4(d) Category of auditor", "Auditor's Firm / Individual", ["Auditor's Firm", "Individual"], None, "categoryOfAuditor"),
    ("frn", "4(e) Firm registration no.", "", None, None, "firmRegistrationNumber"),
    ("firm_name", "4(f) Name of auditor's firm", "", None, None, "nameOfTheAuditorsFirm"),
    ("firm_pan", "4(f)(i) PAN of auditor's firm", "", None, None, "incomeTaxpermanentAccountNumberOfAuditorsFirm"),
    ("addr1", "Firm address line 1", "", None, None, "frn_addressLine1"),
    ("addr2", "Firm address line 2", "", None, None, "frn_addressLine2"),
    ("country", "Firm country", "", None, "India", "frn_country"),
    ("pin", "Firm pin code", "", None, None, "frn_pinCode_ZipCode"),
    ("area", "Firm area / locality", "", None, None, "frn_areaLocality"),
    ("city", "Firm city", "", None, None, "frn_city"),
    ("district", "Firm district", "", None, None, "frn_district"),
    ("state", "Firm state / UT", "", None, None, "frn_state"),
    ("email_firm", "Firm email", "", None, None, "frn_emailId"),
    ("memno", "4(g) Membership no. of signing auditor", "", None, None, "membershipNumberOfAuditorSigningTheBalanceSheetOfTheCompany"),
    ("aud_name", "4(h) Name of the auditor", "", None, None, "nameOfTheAuditor"),
    ("aud_pan", "4(h)(i) PAN of auditor", "", None, None, "incomeTaxPermanentAccountNumberOfAuditor"),
    ("m_addr1", "Auditor address line 1", "blank = firm's", None, None, "mem_AddressLine1"),
    ("m_addr2", "Auditor address line 2", "blank = firm's", None, None, "mem_AddressLine2"),
    ("m_country", "Auditor country", "blank = firm's", None, None, "mem_Country"),
    ("m_pin", "Auditor pin code", "blank = firm's", None, None, "mem_PinCodeZipCode"),
    ("m_area", "Auditor area / locality", "blank = firm's", None, None, "mem_AreaLocality"),
    ("m_city", "Auditor city", "blank = firm's", None, None, "mem_city"),
    ("m_district", "Auditor district", "blank = firm's", None, None, "mem_district"),
    ("m_state", "Auditor state / UT", "blank = firm's", None, None, "mem_StateUT"),
    ("m_email", "Auditor email", "blank = firm's", None, None, "mem_emailId"),
    ("period_from", "4(i) Period from", "DD/MM/YYYY; blank = 1 April of the FY the AGM falls in", None, None, "fromDate"),
    ("period_to", "4(i) Period to", "DD/MM/YYYY; blank = from + years", None, None, "toDate"),
    ("years", "4(j) Number of financial years", "", None, 5, "numberOfFinancialYearsToWhichAppointmentRelates"),
    ("within_20", "4(k) Within limit of 20 companies?", "Yes / No", YN, "Yes", "whetherTheAppointmentOfAuditorIsWithinTheLimitsOfTwentyCompaniesAsSpecifiedInSubSection3gOfSection141"),
    ("prev_audit", "4(l) Audited this company before?", "Yes / No", YN, "No", "hasTheAuditorOrAuditorsFirmOrItsMemberPreviouslyConducted____Rule6"),
    ("prev_years", "4(n) Years audited before", "blank = count of the years below", None, None, "numberOfFinancialYears"),
    ("prev_fys", "(r)-(s) Years audited before", "DD/MM/YYYY-DD/MM/YYYY; ... one per row of the portal table", None, None, None),
    ("prev_frn", "(p) FRN for earlier years", "blank = 4(e)", None, None, None),
    ("prev_memno", "(q) Membership no. for earlier years", "blank = 4(g)", None, None, None),
    ("ac_recommend", "5 Audit committee recommendation", "Yes / No / Not Applicable", ["Yes", "No", "Not Applicable"], "Not Applicable", "whetherTheRecommendation___BeforeTheAppointment"),
    ("res_no", "Declaration: resolution no.", "", None, None, "resolutionNumber_textbox"),
    ("res_date", "Declaration: resolution dated", "DD/MM/YYYY", None, None, "dated_Declaration_datepicker"),
    ("designation", "Declaration: designation", "", None, "Director", "designation_value"),
    ("sign_din", "Declaration: DIN of signatory", "8 digits", None, None, "din_Pan_MembershipNumber"),
    ("last_adt1", "Last ADT-1 (SRN / period)", "from earlier filings (info only)", None, None, None),
    ("source", "Prefilled from", "files the blanks came from (info only)", None, None, None),
    ("notes", "Notes", "", None, None, None),
]
LIVE_OPTIONS = {"CIN_Number_Other_User", "frn_areaLocality", "mem_AreaLocality"}
IDS = [c[0] for c in COLUMNS]
HEADERS = {c[0]: c[1] for c in COLUMNS}
PORTAL = {c[5]: c[0] for c in COLUMNS if c[5]}
PORTAL["cin"] = "cin"  # the CIN box staff see; CIN_Number_Other_User is the hidden list behind it
INFO_ONLY = {"status", "name", "last_adt1", "source", "notes"}
DATES = {"period_from", "period_to", "agm_date", "res_date"}
NUMS = {"years", "prev_years"}
MEM_FROM_FIRM = {"m_addr1": "addr1", "m_addr2": "addr2", "m_country": "country", "m_pin": "pin", "m_area": "area",
                 "m_city": "city", "m_district": "district", "m_state": "state", "m_email": "email_firm"}
FIRST = 3  # first data row on Companies (row 1 headers, row 2 hints)


# ---------------------------------------------------------------- workbook

def _head(cell):
    cell.font = Font(bold=True, color="FFFFFF")
    cell.fill = HEAD
    cell.alignment = Alignment(wrap_text=True, vertical="top")


def template():
    """Create the companies workbook, or add any missing columns to an existing one (data kept)."""
    if BOOK.exists():
        wb = openpyxl.load_workbook(BOOK)
        ws = wb["Companies"]
        have = [c.value for c in ws[1]]
        for cid in IDS:
            if HEADERS[cid] not in have:
                c = ws.max_column + 1
                ws.cell(1, c, HEADERS[cid])
                _head(ws.cell(1, c))
                ws.cell(2, c, dict((x[0], x[2]) for x in COLUMNS)[cid]).font = Font(size=8, color="808080")
        _save(wb)
        return BOOK
    wb = openpyxl.Workbook()
    info = wb.active
    info.title = "Info"
    for k, v in [
        ("ADT-1 companies", "One row per company on the Companies sheet. Save and close (or just save) before pressing Alt+Shift+F."),
        ("Blank cells", "A blank cell takes the value on the Defaults sheet. Type in a company's row only where it differs."),
        ("Computed", "Appointed from / to and Date of appointment are worked out from the AGM date and Number of years when blank."),
        ("Filling", "Open http://127.0.0.1:8742/adt1, click Fill next to the company, open its ADT-1 draft on MCA, press Alt+Shift+F. "
                    "The box shows the company name: check it before clicking Fill. You click Save, Upload, DSC and Submit."),
        ("Prefill", "Put the company master / earlier filed forms in MVP\\ADT1\\source and click Prefill on the dashboard. Only blank cells are filled."),
        ("Extra fields", "A portal field without a column here: add a column whose header is the portal's label, then click Rebuild column map."),
        ("Colours", "Green: prefilled from a file (check it). Yellow: typed by you. Blue on Defaults: firm-wide values."),
    ]:
        info.append([k, v])
    info.column_dimensions["A"].width = 18
    info.column_dimensions["B"].width = 120
    for row in info.iter_rows():
        row[0].font = Font(bold=True)
        row[1].alignment = Alignment(wrap_text=True)

    dfl = wb.create_sheet("Defaults")
    dfl.append(["Field", "Default (used when the company's cell is blank)", "id"])
    for c in range(1, 4):
        _head(dfl.cell(1, c))
    for cid, head, hint, allowed, default, _ in COLUMNS:
        if cid in INFO_ONLY or cid == "cin":
            continue
        dfl.append([head, default, cid])
        dfl.cell(dfl.max_row, 2).fill = BLUE
        if cid in DATES:
            dfl.cell(dfl.max_row, 2).number_format = "DD/MM/YYYY"
    dfl.column_dimensions["A"].width = 42
    dfl.column_dimensions["B"].width = 60
    dfl.column_dimensions["C"].hidden = True

    ws = wb.create_sheet("Companies", 1)
    for c, (cid, head, hint, allowed, default, _) in enumerate(COLUMNS, 1):
        _head(ws.cell(1, c, head))
        ws.cell(2, c, hint).font = Font(size=8, color="808080")
        L = get_column_letter(c)
        ws.column_dimensions[L].width = 30 if cid in ("name", "aud_name", "firm_name", "addr1", "nature", "source", "notes") else 16
        if allowed:
            dv = DataValidation(type="list", formula1='"' + ",".join(allowed) + '"', allow_blank=True)
            ws.add_data_validation(dv)
            dv.add(f"{L}{FIRST}:{L}500")
        for r in range(FIRST, 101):
            cell = ws.cell(r, c)
            if cid in DATES:
                cell.number_format = "DD/MM/YYYY"
            elif cid not in NUMS:
                cell.number_format = "@"
    ws.row_dimensions[1].height = 42
    ws.freeze_panes = "C3"
    wb.move_sheet("Defaults", offset=1)
    _save(wb)
    return BOOK


def _save(wb):
    try:
        wb.save(BOOK)
    except PermissionError:
        raise PermissionError(f"{BOOK.name} is open in Excel: close it and try again")


def _cols(ws):
    """header text -> column number; ids map through HEADERS."""
    return {str(c.value).strip(): c.column for c in ws[1] if c.value}


def read_book():
    """(defaults {id: value}, companies [ {id or header: value, '_row': n} ])."""
    if not BOOK.exists():
        template()
    wb = openpyxl.load_workbook(BOOK, data_only=True)
    defaults = {}
    for row in wb["Defaults"].iter_rows(min_row=2, values_only=True):
        if row and row[2] and row[1] not in (None, ""):
            defaults[row[2]] = row[1]
    ws = wb["Companies"]
    cols = _cols(ws)
    by_head = {v: k for k, v in HEADERS.items()}
    out = []
    for r in range(FIRST, ws.max_row + 1):
        rec = {"_row": r}
        for head, c in cols.items():
            v = ws.cell(r, c).value
            if v not in (None, ""):
                rec[by_head.get(head, head)] = v.strip() if isinstance(v, str) else v
        if rec.get("cin") or rec.get("name"):
            out.append(rec)
    return defaults, out


def find(companies, which):
    which = str(which).strip()
    for c in companies:
        if str(c.get("cin", "")).upper() == which.upper() or str(c["_row"]) == which:
            return c
    raise KeyError(f"no company with CIN or row {which} in {BOOK.name}")


# ---------------------------------------------------------------- resolving a company's values

def _as_date(v):
    if v in (None, ""):
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(v).strip(), fmt).date()
        except ValueError:
            pass
    return None


def resolve(company, defaults):
    """Company row + defaults + computed dates. Returns ({id: value}, {id: where it came from})."""
    vals, src = {}, {}
    for cid in IDS:
        if company.get(cid) not in (None, ""):
            vals[cid], src[cid] = company[cid], "row"
        elif defaults.get(cid) not in (None, ""):
            vals[cid], src[cid] = defaults[cid], "default"
    for k, v in company.items():  # extra columns named after portal labels
        if k not in vals and not k.startswith("_"):
            vals[k], src[k] = v, "row"
    agm = _as_date(vals.get("agm_date"))
    years = int(float(vals.get("years") or 5))
    if not company.get("nature") and str(vals.get("prev_audit", "")).lower() == "yes":
        vals["nature"], src["nature"] = "Re-appointment of Auditors in AGM", "audited before"
    if re.search(r"director", str(vals.get("designation", "")), re.I):
        vals["designation"] = "Director"  # the portal's list has only "Director" (no MD / WTD / Additional)
    for m, f_ in MEM_FROM_FIRM.items():  # signing auditor's address: same as the firm's unless typed
        if vals.get(m) in (None, "") and vals.get(f_) not in (None, ""):
            vals[m], src[m] = vals[f_], "= firm's"
    if agm and not vals.get("period_from"):
        # AGM in Sept 2026 (adopting FY 2025-26): the auditor audits FY 2026-27 onwards, so from 01/04/2026
        y = agm.year if agm.month >= 4 else agm.year - 1
        vals["period_from"], src["period_from"] = date(y, 4, 1), "start of the FY in which the AGM is held"
    pf = _as_date(vals.get("period_from"))
    if pf and not vals.get("period_to"):
        vals["period_to"], src["period_to"] = date(pf.year + years, pf.month, pf.day) - timedelta(days=1), f"from + {years} years"
    for k in DATES:
        d = _as_date(vals.get(k))
        if d:
            vals[k] = d
    if vals.get("prev_years") in (None, "") and str(vals.get("prev_audit", "")).lower() == "yes" and prev_fys(vals):
        vals["prev_years"], src["prev_years"] = len(prev_fys(vals)), "count of earlier years"
    return vals, src


def prev_fys(vals):
    """Earlier financial years audited: [(start, end)] from the '(r)-(s)' cell, e.g. '01/04/2024-31/03/2025; 01/04/2025-31/03/2026'."""
    out = []
    for part in re.split(r"[;\n]+", str(vals.get("prev_fys") or "")):
        ds = re.findall(r"\d{1,2}[/.-]\d{1,2}[/.-]\d{4}", part)
        if len(ds) == 2 and _as_date(ds[0]) and _as_date(ds[1]):
            out.append((_as_date(ds[0]), _as_date(ds[1])))
    return out


def fy_rows(start, upto):
    """Financial years from `start` (date the earlier audit began) to `upto` (end of the last one)."""
    rows, s = [], start
    while s <= upto:
        e = date(s.year + 1 if s.month >= 4 else s.year, 3, 31)
        rows.append((s, min(e, upto)))
        s = e + timedelta(days=1)
    return rows


def import_master(path=None):
    """Load the firm's master workbook (Sheet1: one row per company, old / new auditor; MCA Data: directors,
    'Yes' in Check marks who signs) into the Companies sheet. Rewrites the auditor columns; keeps Status and Notes."""
    path = Path(path) if path else next(p for p in sorted(SOURCE.glob("*.xlsx")) if not p.name.startswith("~$"))
    src = openpyxl.load_workbook(path, data_only=True)
    ws = src.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    hi = next(i for i, r in enumerate(rows[:10]) if any(str(v or "").strip().upper() == "CIN" for v in r))
    heads = [str(v or "").strip().lower() for v in rows[hi]]

    def col(*pats):
        for i, h in enumerate(heads):
            if all(re.search(p, h) for p in pats):
                return i
        return None
    c = {"name": col(r"name of the company"), "cin": col(r"^cin$"), "old_frn": col(r"old", r"firm reg"),
         "old_pan": col(r"old", r"pan"), "firm_name": col(r"new auditor firm"), "frn": col(r"^firm registration"),
         "aud_name": col(r"new partner"), "memno": col(r"membership"), "aud_pan": col(r"new auditor pan"),
         "old_date": col(r"date of adt")}
    pan_mem = {}  # partner PAN -> membership no. (to name the partner who signed the earlier years)
    recs = []
    for r in rows[hi + 1:]:
        cin = CIN_RE.search(str(r[c["cin"]] or "").upper())
        if not cin:
            continue
        g = lambda k: r[c[k]] if c[k] is not None and c[k] < len(r) else None  # noqa: E731
        recs.append({k: g(k) for k in c} | {"cin": cin.group(1)})
        if g("aud_pan") and g("memno"):
            pan_mem[str(g("aud_pan")).strip()] = g("memno")
    signers = {}
    if "MCA Data" in src.sheetnames:
        md = list(src["MCA Data"].iter_rows(values_only=True))
        mh = [str(v or "").strip().lower() for v in md[0]]
        i_cin, i_din, i_des = mh.index("cin"), mh.index("din"), mh.index("designation")
        i_chk = mh.index("signer") if "signer" in mh else mh.index("check")  # 'Signer' column (K) when present
        for r in md[1:]:
            if r and r[i_cin] and str(r[i_chk] or "").strip().lower() in ("yes", "y"):
                signers.setdefault(str(r[i_cin]).strip().upper(), (str(r[i_din]).zfill(8), r[i_des]))

    template()
    wb = openpyxl.load_workbook(BOOK)
    ws = wb["Companies"]
    cols = _cols(ws)
    col_of = {cid: cols[HEADERS[cid]] for cid in IDS if HEADERS[cid] in cols}
    keep = {}
    for r in range(FIRST, ws.max_row + 1):
        cin = str(ws.cell(r, col_of["cin"]).value or "").strip().upper()
        if cin:
            keep[cin] = {k: ws.cell(r, col_of[k]).value for k in ("status", "notes", "res_no", "res_date", "agm_date",
                                                                  "prev_audit", "prev_fys", "prev_frn", "prev_memno") if k in col_of}
        for cc in range(1, ws.max_column + 1):
            ws.cell(r, cc).value = None
            ws.cell(r, cc).fill = PatternFill()
    end = date(2026, 3, 31)
    no_sign, no_prev = [], []
    for i, rec in enumerate(recs):
        r = FIRST + i
        old = _as_date(rec["old_date"])
        v = {"name": rec["name"], "cin": rec["cin"], "category": "Auditor's Firm", "frn": rec["frn"], "firm_name": rec["firm_name"],
             "aud_name": rec["aud_name"], "memno": rec["memno"], "aud_pan": rec["aud_pan"],
             "nature": "Re-appointment of Auditors in AGM", "source": path.name}
        if old:
            y = old.year if old.month >= 4 else old.year - 1  # earlier audit began with the FY of the old ADT-1
            fys = fy_rows(date(y, 4, 1), end)
            v.update(prev_audit="Yes", prev_fys="; ".join(f"{a:%d/%m/%Y}-{b:%d/%m/%Y}" for a, b in fys),
                     prev_frn=rec["old_frn"], prev_memno=pan_mem.get(str(rec["old_pan"] or "").strip()))
            v["last_adt1"] = f"{old:%d/%m/%Y} ({rec['old_frn']})"
        else:
            no_prev.append(rec["name"])
        s = signers.get(rec["cin"])
        if s:
            v["sign_din"], v["designation"] = s
        else:
            no_sign.append(rec["name"])
        kept = keep.get(rec["cin"], {})
        if old:  # earlier years come from the old ADT-1 date; typed ones only where there was none
            kept = {k: x for k, x in kept.items() if not k.startswith("prev_")}
        elif kept.get("prev_fys"):
            no_prev.remove(rec["name"])
        v.update({k: x for k, x in kept.items() if x not in (None, "")})
        for k, x in v.items():
            if k in col_of and x not in (None, ""):
                cell = ws.cell(r, col_of[k])
                cell.value = x if k in NUMS or k in DATES and isinstance(x, (date, datetime)) else str(x).strip()
                cell.fill = GREEN
    _save(wb)
    return {"companies": len(recs), "no_signatory": no_sign, "no_earlier_adt1": no_prev}


# ---------------------------------------------------------------- prefill from files

def _pdf_text(p):
    import pdfplumber
    with pdfplumber.open(p) as pdf:
        return "\n".join(pg.extract_text() or "" for pg in pdf.pages)


def _after(lines, pat):
    for i, l in enumerate(lines):
        if re.search(pat, l, re.I):
            rest = re.sub(pat, "", l, flags=re.I).strip(" :*")
            if rest:
                return rest
            return lines[i + 1].strip() if i + 1 < len(lines) else None
    return None


def facts_from_pdf(p):
    """Whatever an earlier filed form tells about the company and its auditor."""
    text = _pdf_text(p)
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    f = {}
    m = CIN_RE.search(text)
    if m:
        f["cin"] = m.group(1)
    for i, l in enumerate(lines[:-1]):  # label on its own line, name on the next one or two
        if re.search(r"Name of the company\s*$", l, re.I):
            nm = lines[i + 1]
            if not re.search(r"LIMITED|LTD|LLP$", nm, re.I) and i + 2 < len(lines) and not lines[i + 2].startswith("("):
                nm += " " + lines[i + 2]
            if not CIN_RE.search(nm):
                f["name"] = nm.strip()
            break
    em = re.search(r"e-?mail id of the company\s*\*?\s*(\S+@\S+)", text, re.I)
    if em and "*" not in em.group(1):
        f["email"] = em.group(1)
    kind = "ADT-1" if re.search(r"adt[- ]?1", p.name + text[:400], re.I) else \
        "AOC-4" if re.search(r"aoc[- ]?4", p.name, re.I) else "MGT-7" if re.search(r"mgt[- ]?7", p.name, re.I) else "PDF"
    if kind == "AOC-4":
        try:
            import lastyear
            a = lastyear.read_aoc4(p)
            au = a.get("auditor") or {}
            firm = str(au.get("category") or "").lower().startswith("aud")
            f.update({k: v for k, v in {
                "category": "Auditor's Firm" if firm else ("Individual" if au.get("category") else None),
                ("firm_pan" if firm else "aud_pan"): au.get("pan"), ("frn" if firm else "memno"): au.get("membership_or_frn"),
                ("firm_name" if firm else "aud_name"): au.get("name"), "addr1": au.get("address1"), "addr2": au.get("address2"),
                "pin": au.get("pin"), "area": au.get("area"), "city": au.get("city"), "district": au.get("district"),
                "state": au.get("state"), "country": au.get("country"), "sign_din": a.get("signing_din")}.items() if v})
            if a.get("adt1_srn"):
                f["last_adt1"] = f"SRN {a['adt1_srn']} (per AOC-4)"
            f["_fy_to"] = a.get("fy_to")
        except Exception:  # noqa: BLE001
            pass
    if kind == "ADT-1":
        for cid, pat in (("frn", r"Firm Registration Number"), ("firm_name", r"Name of the Auditor.s Firm"),
                         ("firm_pan", r"permanent account number of auditor.s firm"),
                         ("memno", r"Membership Number of Auditor signing.*"), ("aud_name", r"\(h\) \*?Name of the Auditor$"),
                         ("aud_pan", r"permanent account number of auditor$"), ("email_firm", r"^\*?Email ID"),
                         ("addr1", r"^\*?Address Line ?1"), ("addr2", r"^Address Line ?2"), ("pin", r"^\*?Pin ?Code.*?"),
                         ("city", r"^\*?City"), ("district", r"^\*?District"), ("state", r"^\*?State.*?")):
            v = _after(lines, pat)
            if v:
                f[cid] = v
        m = re.search(r"Category of (the )?auditor\s*\*?\s*(Individual|Auditor'?s firm)", text, re.I)
        if m:
            f["category"] = "Individual" if m.group(2).lower().startswith("ind") else "Auditor's Firm"
        dates = re.findall(r"\d\d/\d\d/\d{4}", text)
        m = re.search(r"period of account.*?(\d\d/\d\d/\d{4}).*?(\d\d/\d\d/\d{4})", text, re.I | re.S)
        srn = re.search(r"\bSRN\b\s*:?\s*([A-Z]\d{8})", text)
        if m:
            f["last_adt1"] = f"{m.group(1)} to {m.group(2)}" + (f", SRN {srn.group(1)}" if srn else "")
        elif dates:
            f["last_adt1"] = "filed" + (f", SRN {srn.group(1)}" if srn else "")
    f["_kind"] = kind
    return f


_HEAD_MATCH = [  # master Excel header -> our column
    ("cin", r"^\s*cin\b|corporate identi"), ("name", r"company.*name|name of (the )?company|^\s*name\s*$|client"),
    ("agm_date", r"\bagm\b|annual general"), ("sign_din", r"\bdin\b"), ("prev_years", r"previous|earlier"),
    ("years", r"years|tenure"), ("frn", r"\bfrn\b|firm reg"), ("firm_name", r"firm.*name|name.*firm"),
    ("firm_pan", r"firm.*pan"), ("aud_pan", r"auditor.*pan"), ("memno", r"membership"),
    ("aud_name", r"auditor.*name|^\s*auditor\s*$"), ("category", r"category"), ("nature", r"nature"),
    ("period_from", r"from"), ("period_to", r"\bto\b"), ("res_no", r"resolution n"), ("res_date", r"resolution date"),
]


def facts_from_excel(p):
    """Rows of any sheet whose header row has a CIN column."""
    out = []
    wb = openpyxl.load_workbook(p, data_only=True, read_only=True)
    for ws in wb.worksheets:
        rows = list(ws.iter_rows(max_row=2000, values_only=True))
        for hi, row in enumerate(rows[:15]):
            heads = [str(v or "").strip().lower() for v in row]
            if not any(re.search(r"^\s*cin\b|corporate identi", h) for h in heads):
                continue
            colmap = {}
            for i, h in enumerate(heads):
                for cid, pat in _HEAD_MATCH:
                    if h and cid not in colmap.values() and re.search(pat, h):
                        colmap[i] = cid
                        break
            for row2 in rows[hi + 1:]:
                rec = {cid: row2[i] for i, cid in colmap.items() if i < len(row2) and row2[i] not in (None, "")}
                cin = CIN_RE.search(str(rec.get("cin", "")).upper())
                if cin:
                    rec["cin"] = cin.group(1)
                    out.append(rec)
                elif rec.get("name"):
                    out.append(rec)
            break
    return out


def prefill():
    """Fill blank Companies cells from ADT1/source and the client folders. Adds new companies found there."""
    template()
    SOURCE.mkdir(exist_ok=True)
    found = []  # (facts, file name)
    for p in sorted(SOURCE.rglob("*.xls*")):
        if p.name.startswith("~$"):
            continue
        try:
            found += [(r, p.name) for r in facts_from_excel(p)]
        except Exception as e:  # noqa: BLE001
            print(f"  could not read {p.name}: {e}")
    pdfs = sorted(SOURCE.rglob("*.pdf")) + sorted((ROOT / "clients").rglob("*.pdf"))
    for p in pdfs:
        try:
            f = facts_from_pdf(p)
            if f.get("cin") or f.get("name"):
                found.append((f, p.name))
        except Exception as e:  # noqa: BLE001
            print(f"  could not read {p.name}: {e}")

    wb = openpyxl.load_workbook(BOOK)
    ws = wb["Companies"]
    cols = _cols(ws)
    col_of = {cid: cols[HEADERS[cid]] for cid in IDS if HEADERS[cid] in cols}
    rows_by_cin, rows_by_name = {}, {}
    last = FIRST - 1
    for r in range(FIRST, ws.max_row + 1):
        cin = str(ws.cell(r, col_of["cin"]).value or "").strip().upper()
        nm = str(ws.cell(r, col_of["name"]).value or "").strip().lower()
        if cin or nm:
            last = r
            if cin:
                rows_by_cin[cin] = r
            if nm:
                rows_by_name[nm] = r
    filled, added = 0, 0
    # Excel masters first (most trusted), then PDFs; later sources only fill what is still blank.
    for facts, fname in found:
        cin = str(facts.get("cin") or "").upper()
        nm = str(facts.get("name") or "").strip().lower()
        r = rows_by_cin.get(cin) or (rows_by_name.get(nm) if nm else None)
        if not r:
            if not cin:
                continue
            last += 1
            r = last
            rows_by_cin[cin] = r
            if nm:
                rows_by_name[nm] = r
            added += 1
        used = False
        for cid, v in facts.items():
            if cid.startswith("_") or cid not in col_of or v in (None, ""):
                continue
            cell = ws.cell(r, col_of[cid])
            if cell.value in (None, ""):
                d = _as_date(v) if cid in DATES else None
                cell.value = d or (v if cid in NUMS else str(v).strip())
                cell.fill = GREEN
                filled += 1
                used = True
        if used:
            sc = ws.cell(r, col_of["source"])
            names = [s for s in str(sc.value or "").split("; ") if s]
            if fname not in names:
                sc.value = "; ".join(names + [fname])
    _save(wb)
    return {"files": len(found), "cells": filled, "companies_added": added, "rows": last - FIRST + 1}


# ---------------------------------------------------------------- portal column map

def dump_slug():
    import mca
    hits = sorted(mca.DUMPS.glob("adt*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return hits[0].stem if hits else None


def build_columns():
    """ADT1/adt1_columns.xlsx: each fillable portal field -> the Companies column it takes its value from."""
    import mca
    slug = dump_slug()
    if not slug:
        raise FileNotFoundError("ADT-1 not captured yet: open an ADT-1 draft on MCA and press Alt+Shift+D on each page")
    sc = mca.schema(slug)
    old = {}
    if COLMAP.exists():
        for row in openpyxl.load_workbook(COLMAP, data_only=True)["Columns"].iter_rows(min_row=3, values_only=True):
            if row and row[6]:
                old[row[6]] = row[4]
    extra = []
    if BOOK.exists():
        extra = [h for h in _cols(openpyxl.load_workbook(BOOK, read_only=True)["Companies"]) if h not in HEADERS.values()]
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Columns"
    ws["A1"] = "ADT-1: which column of 'ADT-1 companies.xlsx' fills each portal field. Edit column E (blank = the tool leaves the field alone)."
    ws["A1"].font = Font(bold=True)
    for c, h in enumerate(["Code", "Section", "Portal field", "Type", "Companies column", "Allowed values", "key"], 1):
        _head(ws.cell(2, c, h))
    heads = [HEADERS[c] for c in IDS if c not in INFO_ONLY] + extra
    dv = DataValidation(type="list", formula1="=Lists!$A$1:$A$%d" % len(heads), allow_blank=True)
    ws.add_data_validation(dv)
    used, r, n_map = set(), 3, 0
    for f in sc["fields"] + [f for t in sc["tables"] for f in t["fields"]]:
        if f["type"] == "file":
            continue
        lab = f["label"]
        pick = old.get(f["key"])
        if pick not in heads:
            pick = None
        if pick is None:
            if lab in extra or f["code"] in extra:
                pick = lab if lab in extra else f["code"]
            elif f.get("name") in PORTAL:
                pick = HEADERS[PORTAL[f["name"]]]
        if pick:
            used.add(pick)
            n_map += 1
        allowed = " | ".join(o["text"] for o in f.get("options") or [])[:250]
        for c, v in enumerate([f["code"], f["sectionText"], lab, f["type"], pick, allowed, f["key"]], 1):
            ws.cell(r, c, v)
        ws.cell(r, 5).fill = YELLOW if not pick else GREEN
        if f.get("readOnly"):
            for c in range(1, 7):
                ws.cell(r, c).font = Font(color="808080")
        dv.add(f"E{r}")
        r += 1
    lst = wb.create_sheet("Lists")
    for i, h in enumerate(heads, 1):
        lst.cell(i, 1, h)
    lst.sheet_state = "hidden"
    for col, w in zip("ABCDEFG", (11, 40, 60, 10, 34, 60, 30)):
        ws.column_dimensions[col].width = w
    ws.column_dimensions["G"].hidden = True
    ws.freeze_panes = "A3"
    wb.save(COLMAP)
    _sync_allowed(sc)
    return COLMAP, r - 3, n_map


def _sync_allowed(sc):
    """Put the portal's own option texts as dropdowns on the Companies sheet."""
    if not BOOK.exists():
        return
    mp = read_columns()
    wb = openpyxl.load_workbook(BOOK)
    ws = wb["Companies"]
    cols = _cols(ws)
    changed = False
    for f in sc["fields"]:
        head = mp.get(f["key"])
        if head in cols and f["type"] in ("dropdown", "radio") and f.get("options"):
            L = get_column_letter(cols[head])
            texts = [str(o["text"] or o["value"]).replace(",", " ") for o in f["options"]]
            ws.cell(2, cols[head], " / ".join(texts)[:250]).font = Font(size=8, color="808080")
            if len(",".join(texts)) < 250:
                dv = DataValidation(type="list", formula1='"' + ",".join(texts) + '"', allow_blank=True)
                ws.add_data_validation(dv)
                dv.add(f"{L}{FIRST}:{L}500")
            changed = True
    if changed:
        _save(wb)


def read_columns():
    if not COLMAP.exists():
        return {}
    ws = openpyxl.load_workbook(COLMAP, data_only=True)["Columns"]
    return {row[6]: row[4] for row in ws.iter_rows(min_row=3, values_only=True) if row and row[6] and row[4]}


# ---------------------------------------------------------------- plan (what Alt+Shift+F fills)

def state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def set_current(which):
    STATE.write_text(json.dumps({"current": str(which)}, indent=1), encoding="utf-8")


def make_plan(slug, which=None):
    import mca
    which = which or state().get("current")
    if not which:
        raise ValueError("no ADT-1 company picked: open http://127.0.0.1:8742/adt1 and click Fill next to the company")
    defaults, companies = read_book()
    comp = find(companies, which)
    vals, _ = resolve(comp, defaults)
    sc = mca.schema(slug)
    mp = read_columns()
    if not mp:
        raise ValueError("no ADT-1 column map yet: click 'Rebuild column map' on http://127.0.0.1:8742/adt1")
    by_head = {v: k for k, v in HEADERS.items()}
    label = f"{comp.get('name') or ''} ({comp.get('cin') or 'row ' + str(comp['_row'])})"
    plan = {"client": label, "workbook": BOOK.name, "slug": slug, "form": "ADT-1",
            "generatedAt": datetime.now().isoformat(timespec="seconds"), "fields": [], "tables": [], "errors": [], "save": True,
            "autoSave": True, "autoNext": True,  # Rohit: ADT-1 clicks Save and Next itself (never Submit / DSC / Upload)
            # after the attachments page is saved: next ready company on a fresh ADT-1
            "autoAdvance": True, "nextUrl": "https://www.mca.gov.in/content/mca/global/en/mca/e-filing/complianceServices/ADT-1.html"}
    tables = {}
    for f in sc["fields"] + [f for t in sc["tables"] for f in t["fields"]]:
        head = mp.get(f["key"])
        if not head or f["type"] == "file":
            continue
        v = vals.get(by_head.get(head, head))
        if v in (None, ""):
            continue
        e = {k: f.get(k) for k in ("code", "key", "domBase", "som", "type", "label", "sectionText")}
        try:
            if f.get("name") in LIVE_OPTIONS:  # options load on the portal (user's companies, areas of the pin code)
                v = str(v).strip().upper() if f["name"] == "CIN_Number_Other_User" else str(v).strip()
                e.update(value=v, display=v)
            else:
                e.update(mca.convert(f, v))
        except ValueError as ex:
            plan["errors"].append({"code": f["code"], "key": f["key"], "label": f["label"], "msg": f"{head}: {ex}"})
            continue
        rep = f.get("repeat")
        if rep and rep.get("groupSom"):
            t = next(t for t in sc["tables"] if f in t["fields"])
            e.update(relSom=rep["relSom"], row=0)
            tables.setdefault(t["groupKey"], {"groupKey": t["groupKey"], "groupSom": t["groupSom"], "title": t["title"],
                                              "max": t["max"], "section": t["section"], "rows": [[]]})["rows"][0].append(e)
        else:
            plan["fields"].append(e)
    # (o)-(s): one row per financial year the auditor audited before, counted back from this appointment
    fys = prev_fys(vals)
    sec = next((t for t in sc["tables"] if any(f.get("name") == "financialYearStartDate" for f in t["fields"])), None)
    if str(vals.get("prev_audit", "")).lower() == "yes" and fys and sec:
        if len(fys) > (sec["max"] or 10):
            plan["errors"].append({"code": "", "key": "", "label": "(r)-(s) Years audited before", "msg": f"{len(fys)} rows: the portal allows {sec['max']}"})
        rows = []
        for i, (fs_, fe_) in enumerate(fys, 1):
            vals_row = {"sNo": i, "r_firmRegistrationNumber": vals.get("prev_frn") or vals.get("frn"),
                        "membershipNumberOfAuditor": vals.get("prev_memno") or vals.get("memno"),
                        "financialYearStartDate": fs_, "financialYearEndDate": fe_}
            cells = []
            for f in sec["fields"]:
                v = vals_row.get(f.get("name"))
                if v in (None, ""):
                    continue
                e = {k_: f.get(k_) for k_ in ("code", "key", "domBase", "som", "type", "label", "sectionText")}
                e.update(mca.convert(f, v), relSom=f["repeat"]["relSom"], row=i - 1)
                cells.append(e)
            rows.append(cells)
        tables[sec["groupKey"]] = {"groupKey": sec["groupKey"], "groupSom": sec["groupSom"], "title": "Financial years audited earlier",
                                   "max": sec["max"], "section": sec["section"], "rows": rows}
    plan["tables"] = list(tables.values())
    # Attachments from the company's folder: uploaded by the extension (Choose File + the portal's Upload button).
    plan["attachments"] = []
    files = attachments_of(comp)
    by_name = {f.get("name"): f for f in sc["fields"] if f["type"] == "file"}
    for kind, (el, what) in ATTACH.items():
        f = by_name.get(el)
        if not f:
            continue
        p = files.get(kind)
        if not p:
            plan["errors"].append({"code": f["code"], "key": f["key"], "label": f["label"], "msg": f"no {what} in the company's folder"})
            continue
        plan["attachments"].append({"code": f["code"], "key": f["key"], "domBase": f["domBase"], "som": f["som"], "label": f["label"],
                                    "kind": kind, "file": p.name, "cin": comp.get("cin")})
    return plan


# ---------------------------------------------------------------- attachments

ATTACH_ROOT = SOURCE / "For ADT 1 - AGM project"  # <partner>/<company name>/<any folder>/*.pdf
ATTACH = {  # kind: (portal element, what it is), matched on the file name
    "intimation": ("a_Attachment_CopyOfTheIntimationSentByCompany", "Company Appoin Letter"),
    "consent": ("b_Attachment_CopyOfWrittenConsentGivenByAuditor", "Consent Letter"),
    "optional": ("e_Attachment_OptionalAttachmentsIfAny", "AGM Resolution - Auditor apt"),
}
_PATS = {"intimation": r"appoin", "consent": r"consent", "optional": r"resolution"}


def _key(s):
    return re.sub(r"[^A-Z0-9]", "", str(s).upper().replace("LTD", "LIMITED"))


def attachments_of(comp):
    """{kind: Path} for one company; a kind with 0 or 2+ matching PDFs is left out (staff decide)."""
    want = _key(comp.get("name", ""))
    folder = next((d for d in ATTACH_ROOT.glob("*/*") if d.is_dir() and _key(d.name) == want), None) if ATTACH_ROOT.exists() else None
    if not folder:
        return {}
    pdfs = [p for p in folder.rglob("*.pdf")]
    out = {}
    for kind, pat in _PATS.items():
        hits = [p for p in pdfs if re.search(pat, p.name, re.I)]
        if len(hits) == 1:
            out[kind] = hits[0]
    return out


FLAT = HERE / "flattened"  # image-only copies of the attachments (Rohit: upload scans, not selectable text)
LIMIT = 2 * 1024 * 1024


def flatten(p):
    """PDF -> PDF of page images (no selectable text), under the portal's 2 MB. Cached by source time."""
    import pypdfium2 as pdfium
    out = FLAT / p.parent.parent.name / p.name if p.parent.name.upper().startswith("ADT") else FLAT / p.parent.name / p.name
    if out.exists() and out.stat().st_mtime >= p.stat().st_mtime:
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    doc = pdfium.PdfDocument(str(p))
    try:
        for dpi, quality in ((200, 85), (150, 75), (120, 65), (100, 55)):
            pages = [doc[i].render(scale=dpi / 72).to_pil().convert("RGB") for i in range(len(doc))]
            pages[0].save(out, "PDF", save_all=True, append_images=pages[1:], resolution=dpi, quality=quality)
            if out.stat().st_size <= LIMIT:
                break
    finally:
        doc.close()
    return out


def attachment_json(cin, kind):
    import base64
    _, companies = read_book()
    p = attachments_of(find(companies, cin)).get(kind)
    if not p:
        raise FileNotFoundError(f"no single {kind} PDF for {cin}")
    f = flatten(p)
    if f.stat().st_size > LIMIT:
        raise ValueError(f"{p.name} is still over the portal's 2 MB limit as images")
    return {"name": p.name, "b64": base64.b64encode(f.read_bytes()).decode("ascii")}


# ---------------------------------------------------------------- dashboard page

def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def page(msg=""):
    try:
        defaults, companies = read_book()
    except Exception as e:  # noqa: BLE001
        defaults, companies, msg = {}, [], f"{msg}\nCould not read {BOOK.name}: {e}"
    cur = state().get("current")
    slug = dump_slug()
    mapped = len(read_columns())
    rows = []
    need = ("cin", "category", "memno", "aud_name", "aud_pan", "agm_date", "period_from", "period_to", "res_no", "res_date", "sign_din")
    for c in companies:
        vals, _ = resolve(c, defaults)
        miss = [HEADERS[k] for k in need if vals.get(k) in (None, "")]
        key = c.get("cin") or str(c["_row"])
        is_cur = cur and (cur.upper() == str(c.get("cin", "")).upper() or cur == str(c["_row"]))
        pf, pt = vals.get("period_from"), vals.get("period_to")
        rows.append(
            f"<tr{' class=active' if is_cur else ''}><td>{c['_row']}</td><td><b>{_esc(c.get('name', ''))}</b><br><small>{_esc(c.get('cin', ''))}</small></td>"
            f"<td>{_esc(c.get('status', ''))}</td><td>{_esc(vals.get('aud_name', ''))}</td>"
            f"<td>{pf.strftime('%d/%m/%Y') if isinstance(pf, date) else ''} – {pt.strftime('%d/%m/%Y') if isinstance(pt, date) else ''}</td>"
            f"<td>{'<span class=ok>ready</span>' if not miss else '<span class=miss>missing: ' + _esc(', '.join(miss)) + '</span>'}</td>"
            f"<td><form method=post action=/adt1/select><input type=hidden name=which value=\"{_esc(key)}\">"
            f"<button {'disabled' if is_cur else ''}>{'Filling this' if is_cur else 'Fill'}</button></form></td></tr>")
    done = sum(1 for c in companies if str(c.get("status", "")).lower() in ("saved", "submitted", "skip"))
    return f"""<!doctype html><html><head><meta charset=utf-8><title>ADT-1 companies</title><style>
body{{font:14px Segoe UI,Arial,sans-serif;margin:24px;color:#102a43}} table{{border-collapse:collapse;margin:8px 0 24px}}
td,th{{border:1px solid #bcccdc;padding:5px 9px;text-align:left;vertical-align:middle}} th{{background:#d9e2ec}}
tr.active td{{background:#e3f9e5}} form{{display:inline}} button{{padding:4px 10px}} .msg{{background:#fff3c4;padding:8px 12px;white-space:pre-wrap}}
.ok{{color:#2f8132}} .miss{{color:#b44d12}} small{{color:#627d98}}</style></head><body>
<p><a href="/">&larr; MCA filler</a></p><h2>ADT-1 companies</h2>
{f'<div class=msg>{_esc(msg)}</div>' if msg else ''}
<p>Workbook: <code>{_esc(BOOK)}</code>. Companies: <b>{len(companies)}</b>, done (Saved / Submitted / Skip): <b>{done}</b>.
 Form captured: <b>{_esc(slug) if slug else 'not yet: open ADT-1 on MCA and press Alt+Shift+D on each page'}</b>. Portal fields mapped: <b>{mapped}</b>.</p>
<p><form method=post action=/adt1/import><button>Load master data</button></form>
 <form method=post action=/adt1/prefill><button>Prefill from files</button></form>
 <form method=post action=/adt1/columns><button>Rebuild column map</button></form>
 <small>Prefill reads MVP\\ADT1\\source (company master, earlier ADT-1 / AOC-4 PDFs) and the clients folders; it fills blank cells only.</small></p>
<p>Click <b>Fill</b> next to a company, open <b>that company's</b> ADT-1 draft on MCA, then press Alt+Shift+F. The box shows the company: check it before you click Fill.</p>
<table><tr><th>Row</th><th>Company</th><th>Status</th><th>Auditor</th><th>Period</th><th>Check</th><th></th></tr>
{''.join(rows) or '<tr><td colspan=7>No companies yet: type them on the Companies sheet or click Prefill.</td></tr>'}</table>
</body></html>"""


DONE = ("skip", "filled", "saved", "submitted")


def ready(comp, defaults):
    """Filled automatically only when all 3 attachments and the signing director are known (Rohit, 14/10)."""
    vals, _ = resolve(comp, defaults)
    return len(attachments_of(comp)) == len(ATTACH) and vals.get("sign_din") not in (None, "")


def set_status(cin, status):
    wb = openpyxl.load_workbook(BOOK)
    ws = wb["Companies"]
    cols = _cols(ws)
    for r in range(FIRST, ws.max_row + 1):
        if str(ws.cell(r, cols[HEADERS["cin"]]).value or "").upper() == str(cin).upper():
            ws.cell(r, cols[HEADERS["status"]]).value = status
    _save(wb)


def mark_master(cins, status="Filled"):
    """Write 'Filled <date time>' in an 'ADT-1 Status' column of the master workbook (Rohit, 14/10).
    Returns a note when the master is open in Excel (then the ADT-1 workbook still holds the status)."""
    path = next((p for p in sorted(SOURCE.glob("*.xlsx")) if not p.name.startswith("~$")), None)
    if not path:
        return "no master workbook"
    wb = openpyxl.load_workbook(path)
    ws = wb.worksheets[0]
    hi = next(r for r in range(1, 11) if any(str(c.value or "").strip().upper() == "CIN" for c in ws[r]))
    heads = {str(c.value or "").strip().lower(): c.column for c in ws[hi]}
    c_cin = heads["cin"]
    c_st = heads.get("adt-1 status")
    if not c_st:
        c_st = ws.max_column + 1
        ws.cell(hi, c_st, "ADT-1 Status").font = Font(bold=True)
    want = {str(c).upper() for c in cins}
    stamp = datetime.now().strftime("%d/%m/%Y %H:%M")
    for r in range(hi + 1, ws.max_row + 1):
        if str(ws.cell(r, c_cin).value or "").strip().upper() in want:
            ws.cell(r, c_st, f"{status} {stamp}")
    try:
        wb.save(path)
    except PermissionError:
        return f"{path.name} is open in Excel: status not written there"
    return ""


def advance():
    """After the last Save of a company: mark it Saved, pick the next ready company. JSON for the extension."""
    cur = state().get("current")
    if cur:
        set_status(cur, "Saved")
        try:
            mark_master([cur])
        except Exception:  # noqa: BLE001
            pass
    defaults, companies = read_book()
    for c in companies:
        if str(c.get("status", "")).lower() not in DONE and c.get("cin") and ready(c, defaults):
            set_current(c["cin"])
            return {"next": c["cin"], "name": c.get("name", ""),
                    "left": sum(1 for x in companies if str(x.get("status", "")).lower() not in DONE and x.get("cin") and ready(x, defaults))}
    STATE.write_text(json.dumps({"current": ""}), encoding="utf-8")
    return {"next": None}


def handle(path, form):
    """POST /adt1/... from the dashboard. Returns the page HTML."""
    if path == "/adt1/advance":
        try:
            return json.dumps(advance())
        except Exception as e:  # noqa: BLE001
            return json.dumps({"error": str(e)})
    try:
        if path == "/adt1/select":
            set_current(form.get("which", ""))
            return page(f"Alt+Shift+F now fills ADT-1 for {form.get('which')}.")
        if path == "/adt1/import":
            r = import_master()
            return page(f"Loaded {r['companies']} companies from the master workbook. No signatory marked Yes: {len(r['no_signatory'])}. "
                        f"No earlier ADT-1 date: {', '.join(r['no_earlier_adt1']) or 'none'}.")
        if path == "/adt1/prefill":
            r = prefill()
            return page(f"Prefill: {r['cells']} blank cells filled from {r['files']} records; {r['companies_added']} companies added; {r['rows']} rows in all.")
        if path == "/adt1/columns":
            p, n, hits = build_columns()
            return page(f"Column map rebuilt: {hits} of {n} portal fields matched to a column. Check {p.name} (green = matched, yellow = blank).")
    except Exception as e:  # noqa: BLE001
        return page(f"Error: {e}")
    return page()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("template")
    sub.add_parser("prefill")
    sub.add_parser("columns")
    sub.add_parser("import")
    p = sub.add_parser("plan")
    p.add_argument("which")
    a = ap.parse_args()
    if a.cmd == "template":
        print(template())
    elif a.cmd == "prefill":
        print(prefill())
    elif a.cmd == "import":
        print(import_master())
    elif a.cmd == "columns":
        print(build_columns())
    elif a.cmd == "plan":
        print(json.dumps(make_plan(dump_slug(), a.which), indent=1, default=str))


if __name__ == "__main__":
    main()
