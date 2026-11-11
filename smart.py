"""Auto-fill MGT-7A from what the firm already has, so staff answer only a few questions.

Sources, in order of trust:
  1. Questions sheet: the handful of things only staff know (AGM date, board meeting dates, changes).
  2. This year's Schedule III workbook: FY dates, turnover, net worth, capital, directors' remuneration.
  3. Last year's filed MGT-7A PDF in the client folder: everything that rarely changes
     (class / category, activity codes, share capital, shareholding, directors, designated person).
Portal fields are addressed by their AEM element name (stable across companies), never by position.
"""
import re
from datetime import date, datetime, timedelta

from schedule3 import FSError

# key, question, how to answer, default-maker(facts, fs) -> value
QUESTIONS = [
    ("form_type", "Type of annual filing", "Original / Revised", lambda f, fs: "Original"),
    ("agm_held", "Was the AGM held for this financial year?", "Yes / No", lambda f, fs: "Yes"),
    ("agm_date", "Date of AGM", "DD/MM/YYYY  (required if AGM held)", lambda f, fs: None),
    ("agm_due", "Due date of AGM", "DD/MM/YYYY", lambda f, fs: _agm_due(fs, f)),
    ("agm_extension", "Was an extension of AGM granted (GNL-1)?", "Yes / No", lambda f, fs: "No"),
    ("board_meetings", "Board meeting dates during the year", "DD/MM/YYYY, comma separated", lambda f, fs: None),
    ("all_attended", "Did every director attend every board meeting and the AGM?", "Yes / No", lambda f, fs: "Yes"),
    ("capital_changed", "Any change in share capital during the year (allotment, buy-back, transfer)?", "Yes / No", lambda f, fs: "No"),
    ("holders_changed", "Any change in shareholders or their shareholding during the year?", "Yes / No", lambda f, fs: "No"),
    ("directors_changed", "Any change in directors / KMP during the year?", "Yes / No", lambda f, fs: "No"),
    ("remuneration", "Remuneration to MD / WTD this year (Name = amount; …)", "e.g. A = 900000; B = 900000", lambda f, fs: _rem_default(f, fs)),
    ("phone", "Telephone number of the company with STD code (portal needs it)", "e.g. 04412345678", lambda f, fs: None),
    ("penalties", "Any penalty, punishment or compounding during the year?", "Yes / No", lambda f, fs: "No"),
    ("resolution_date", "Date of board resolution authorising the signatory", "DD/MM/YYYY", lambda f, fs: None),
    ("signing_din", "DIN of the director who will sign (DSC)", "8 digits",
     lambda f, fs: (f or {}).get("signing_din") or (fs.setup("Signing director 1 DIN") if fs else None)),
    ("designated_din", "DIN / PAN of the designated person (Rule 9(4))", "", lambda f, fs: (f or {}).get("designated_din")),
]


def _fy_end(fs, facts):
    if fs:
        v = fs.setup("Current year - balance sheet date")
        if isinstance(v, (datetime, date)):
            return v if isinstance(v, date) and not isinstance(v, datetime) else v.date()
        if isinstance(v, str):
            for fmt in ("%d %B %Y", "%d/%m/%Y", "%d-%m-%Y", "%d %b %Y"):
                try:
                    return datetime.strptime(v.strip(), fmt).date()
                except ValueError:
                    pass
    if facts and facts.get("fy_to"):
        d = datetime.strptime(facts["fy_to"], "%d/%m/%Y").date()
        return d.replace(year=d.year + 1)
    return None


def _agm_due(fs, facts):
    end = _fy_end(fs, facts)
    return f"30/09/{end.year}" if end else None


def _num(fs, expr, default=None):
    if not fs:
        return default
    try:
        return fs.eval(expr)
    except FSError:
        return default


def _rem_default(facts, fs):
    rem = (facts or {}).get("remuneration") or []
    if not rem:
        return None
    total = _num(fs, "Notes:Employee benefits expense/Directors' remuneration")
    last = sum(r["gross"] for r in rem) or 1
    parts = []
    for r in rem:
        amt = round(total * r["gross"] / last) if total is not None else r["gross"]
        parts.append(f"{r.get('name', 'Director ' + str(r['sno']))} = {int(amt)}")
    return "; ".join(parts)


def _yes(v):
    return str(v or "").strip().lower() in ("yes", "y", "true", "1")


def _dates(v):
    out = []
    for s in re.split(r"[,;\n]+", str(v or "")):
        s = s.strip()
        if s:
            out.append(s)
    return out


def _i(x):
    if x is None:
        return None
    return str(int(round(x))) if float(x).is_integer() else f"{x:.2f}"


# Setup sheet (column A label, column B value) -> question key. Filled Setup rows answer the
# question, so a workbook prepared with these needs no Questions at all.
SETUP_ANSWERS = {
    "board_fs_date": "Date of board meeting approving financial statements",
    "board_report_date": "Date of board meeting approving board's report",
    "fs_sign_date": "Date of signing of financial statements",
    "auditor_report_date": "Date of auditor's report",
    "agm_held": "AGM held",
    "agm_date": "Date of AGM",
    "agm_due": "Due date of AGM",
    "agm_extension": "AGM extension granted",
    "resolution_date": "Date of board resolution authorising signatory",
    "signing_din": "DIN of signing director",
    "related_party": "Related party transactions during the year",
    "ca_cop": "Certificate of practice number of certifying CA",
    "ca_fellow": "Certifying CA Associate or Fellow",
    "product_desc": "Main product or service description",
    "phone": "Telephone number with STD code",
    "board_meetings": "Board meeting dates",
    "designated_din": "DIN of designated person",
}

# Setup rows that stand in for last year's filed AOC-4 when it is not in the client folder.
SETUP_FACTS_AOC4 = {
    "signatories": "Directors signing financial statements",   # "DIN:Designation; DIN:Designation"
    "industry": "Type of industry",
    "product_code4": "Product or service code (4 digit)",
    "product_code8": "Product or service code (8 digit)",
    "auditor_category": "Auditor category",
    "is_subsidiary": "Company is a subsidiary",
    "has_subsidiary": "Company has subsidiary or associate",
    "cost_records": "Cost records applicab",
    "secretarial_audit": "Secretarial audit applicab",
    "csr": "CSR applicab",
    "resolution_no": "Board resolution number",
}


def setup_facts_aoc4(fs, facts):
    """Fill gaps in last year's AOC-4 facts from the Setup sheet (Setup wins when both exist)."""
    f = dict(facts or {})
    if not fs:
        return f
    get = lambda k: fs.setup(SETUP_FACTS_AOC4[k])  # noqa: E731
    sig = get("signatories")
    if sig:
        rows = []
        for part in str(sig).split(";"):
            if part.strip():
                din, _, desig = part.partition(":")
                rows.append({"din": din.strip(), "name": "", "designation": desig.strip() or "Director", "date": None})
        f["fs_signatories"] = rows
        f["report_signatories"] = rows
    if not sig:
        # Board's Report signature rows double as the AOC-4 signatories
        rows = []
        for i in (1, 2, 3):
            din = fs.setup(f"Signing director {i} DIN")
            if din:
                rows.append({"din": str(din).strip(), "name": str(fs.setup(f"Signing director {i} name") or "").strip(),
                             "designation": "Director", "date": None})
        if rows and not f.get("fs_signatories"):
            f["fs_signatories"] = rows
            f["report_signatories"] = rows
    for k in ("industry", "is_subsidiary", "has_subsidiary", "cost_records", "secretarial_audit", "csr", "resolution_no"):
        v = get(k)
        if v not in (None, ""):
            f[k] = str(v).strip()
    if str(f.get("csr", "")).strip().lower() in ("no", "nil", "n"):
        f["csr"] = "Not applicable"
    elif str(f.get("csr", "")).strip().lower() in ("yes", "y"):
        f["csr"] = "Section 135"
    if get("auditor_category"):
        f["auditor"] = dict(f.get("auditor") or {}, category=str(get("auditor_category")).strip())
    c4, c8 = get("product_code4"), get("product_code8")
    if c4 and c8:
        f["products"] = [{"code4": str(c4).strip(), "code8": str(c8).strip(), "turnover4": None, "turnover8": None}]
    return f


# Figures that Schedule III does not split but Tally has: one Setup row each (current year).
# Setup label -> AOC-4 element names that take the amount. Blank or missing rows keep the default (0).
SETUP_FIGURES_AOC4 = {
    "Export of goods FOB": ["PartC1"],
    "Forex earnings - interest and dividend": ["PartC2"],
    "Forex earnings - royalty": ["PartC3"],
    "Forex earnings - know-how": ["PartC4"],
    "Forex earnings - professional and consultation fees": ["PartC5"],
    "Forex earnings - other income": ["PartC6"],
    "Imports CIF - raw material": ["Part2CR1"],
    "Imports CIF - components and spare parts": ["Part2CR2"],
    "Imports CIF - capital goods": ["Part2CR3"],
    "Forex expenditure - royalty": ["Part2CR4"],
    "Forex expenditure - know-how": ["Part2CR5"],
    "Forex expenditure - professional and consultation fees": ["Part2CR6"],
    "Forex expenditure - interest": ["Part2CR7"],
    "Forex expenditure - other matters": ["Part2CR8"],
    "Forex expenditure - dividend paid": ["Part2CR9"],
    "Deposits accepted or renewed during the year": ["depositsAcceptedOrRenewed"],
    "Proposed dividend": ["Proposed_Dividend"],
    "Unpaid dividend": ["unpaidDividend"],
    "Revenue subsidies or grants received": ["Revenue_sub"],
    "Capital subsidies or grants received": ["capitalSubsidiesOrGrants"],
    "Consumption of stores and spare parts": ["Consumptionofstores"],
    "Bad debts of related parties": ["BadDebts"],
    "Borrowings guaranteed by directors - long term": ["currentReportingPeriod11"],
    "Borrowings guaranteed by directors - short term": ["currentReportingPeriodB7"],
    "Loans and advances due by directors": ["currentReportingPeriodC9"],
    "Trade receivables due by directors": ["current_greater6_debt_due"],
    "Contribution to political parties (section 182)": ["contributionUnderSection182"],
    "Unhedged foreign currency exposure": ["unhedgedForeign"],
}


def _setup_amount(fs, label):
    v = fs.setup(label) if fs else None
    if v in (None, ""):
        return None
    try:
        return float(str(v).replace(",", "").strip())
    except ValueError:
        return None


def tally_overrides(d, fs, FS):
    """Setup rows taken from Tally (forex, AS-18, receivable ageing, managerial remuneration...)."""
    if not fs:
        return
    TL = "Setup (from Tally)"
    for label, names in SETUP_FIGURES_AOC4.items():
        amt = _setup_amount(fs, label)
        if amt is not None:
            for n in names:
                d.override[n] = (_i(amt), TL)
    earn = sum(_setup_amount(fs, l) or 0 for l in SETUP_FIGURES_AOC4 if l.startswith(("Export of goods", "Forex earnings")))
    spend = sum(_setup_amount(fs, l) or 0 for l in SETUP_FIGURES_AOC4 if l.startswith(("Imports CIF", "Forex expenditure")))
    d.override["PartC7"] = (_i(earn), TL)
    d.override["Part2CR10"] = (_i(spend), TL)
    d.override["Income_in_foreign_currency"] = (_i(earn), TL)
    d.override["Exp_in_foreign_currency"] = (_i(spend), TL)
    # AS-18: directors' remuneration is a related-party transaction (KMP), plus any other related-party
    # transactions the firm lists from Tally.
    rem = _num(fs, "Notes:Employee benefits expense/Directors' remuneration") or 0
    other = _setup_amount(fs, "Related party transactions other than directors' remuneration") or 0
    if rem or other:
        d.override["grossValueOfTransaction"] = (_i(rem + other), FS)   # BS financial parameter 22
        d.override["Grossvalue"] = (_i(rem + other), FS)                # P&L financial parameter 8
    # Trade receivables ageing: the part outstanding over 6 months goes in its own column
    over6 = _setup_amount(fs, "Trade receivables outstanding more than 6 months")
    total = _num(fs, "Notes:Trade receivables/Unsecured, considered good")
    if over6 is not None and total is not None:
        d.override["current_greater6_unsecuredconsideredgood"] = (_i(over6), TL)
        d.override["current_lesser6_unsecuredconsideredgood"] = (_i(total - over6), TL)
    # Managerial remuneration shown on its own line, taken out of employee benefits
    mgr = _setup_amount(fs, "Managerial remuneration (AOC-4 line)")
    emp = _num(fs, "PL:Employee benefits expense")
    if mgr is not None and emp is not None:
        d.override["revenueFromOperationsCurrent17"] = (_i(mgr), TL)
        d.override["revenueFromOperationsCurrent16"] = (_i(emp - mgr), TL)


class Derived:
    """Values for portal fields: by element name (main sheet) and table rows (by element name too)."""

    def __init__(self):
        self.fields = {}     # element name -> (value, source)
        self.copies = {}     # element name -> element name of the field to copy on the portal
        self.tables = {}     # table element name -> [ {element name: value} ]
        self.todo = []       # things staff still have to do by hand
        self.override = {}   # element name -> (value, source): wins over the Schedule III mapping

    def set(self, name, value, src):
        if value is not None and value != "":
            self.fields[name] = (value, src)


def derive(facts, answers, fs):
    """facts: last year's MGT-7A (or None); answers: {question key: value}; fs: Schedule3 or None."""
    d = Derived()
    f = facts or {}
    a = dict(answers)
    LY, FS, Q = "last year's MGT-7A", "Schedule III", "Questions"

    end = _fy_end(fs, facts)
    if end:
        start = (end.replace(year=end.year - 1) + timedelta(days=1))
        d.set("financial_year_date", start.strftime("%d/%m/%Y"), FS)
        d.set("datepicker_to_date", end.strftime("%d/%m/%Y"), FS)
    d.set("TypeOfAnnual", a.get("form_type") or "Original", Q)
    # Name, address, lat/long "as on FY end": same as the portal's own "as on filing date" values.
    # Name / address / lat-long "as on FY end" are kept by the portal itself: never touch them.
    d.set("TelephoneNumber", a.get("phone"), Q)
    cls = f.get("class") or ""
    d.set("ClassOfCompany1", "One Person Company" if "one person" in cls.lower() else ("Private company" if cls else None), LY)
    d.set("CategoryCompany", f.get("category"), LY)
    d.set("SubCategory", f.get("subcategory"), LY)
    d.set("WhetherTheFormIsFiled", f.get("opc_or_small"), LY)
    d.set("WhetherCompanyRadio", f.get("has_share_capital"), LY)
    held = _yes(a.get("agm_held", "Yes"))
    d.set("WhetherShareListed", "Yes" if held else "No", Q)
    if held:
        d.set("IfYesDateOFAGM", a.get("agm_date"), Q)
    d.set("DueDateOf_AGM", a.get("agm_due"), Q)
    d.set("Whether_ANyExtensionForAGM", "Yes" if _yes(a.get("agm_extension")) else "No", Q)

    acts = f.get("activities") or []
    if acts:
        d.set("number_business_activities_company", str(len(acts)), LY)
        d.tables["business_activities"] = [{"principal_mainactivity_code": x["group"], "business_activitycode": x["code"], "Principal_turnover": x["pct"]} for x in acts]
    d.set("number_associate_company", str(f.get("associates") or 0), LY)

    # ---- share capital: Schedule III amounts, last year's nominal value / class
    eq = f.get("equity") or {}
    nominal = (eq.get("nominal") or [None])[0]
    auth_amt = _num(fs, "Notes:Share capital/Authorised share capital") or ((eq.get("amount") or [None])[0])
    paid_amt = _num(fs, "Notes:Share capital/Total issued, subscribed and fully paid up") or ((eq.get("amount") or [None, None, None, None])[3])
    changed = _yes(a.get("capital_changed"))
    if nominal and paid_amt is not None:
        d.set("NumberOfClassesEquity", str(eq.get("classes") or 1), LY)
        auth_n = auth_amt / nominal if auth_amt else None
        paid_n = paid_amt / nominal
        d.tables["EquitySharePanel"] = [{
            "classOfShares": eq.get("class_name") or f"Equity shares of Rs.{_i(nominal)} each",
            "numberequity_authorizedcapital": _i(auth_n), "numberequity_issuedcapital": _i(paid_n),
            "numberequity_subscribed_capital": _i(paid_n), "numberequity_paidupcapital": _i(paid_n),
            "nominalvalue_authorizedcapital": _i(nominal), "nominalvalue_issuedcapital": _i(nominal),
            "nominalvalue_subscribedcapital": _i(nominal), "nominalvalue_paidupcapital": _i(nominal),
            "tot_amt_subscribed_capital": _i(paid_amt), "tot_amt_paidupcapital": _i(paid_amt)}]
    d.set("preference_shareClass", str(f.get("preference_classes") or 0), LY)
    d.set("unclassified_shareAmt", "0", LY)
    ye = f.get("equity_year_end")
    if ye and not changed:
        for i, v in enumerate(ye, 1):
            d.set(f"begining_of_year{i}", _i(v), LY)
            d.set(f"at_yearEnd{i}", _i(v), LY)
        # "Others, specify" rows stay blank (no 0): MCA expects them empty unless there is such a movement.
        for stem in ("right_issues", "Bonus_issue", "Private_placement", "esop", "debenture_Conversion", "Conversion_preference",
                     "buy_back_share", "share_forfieted", "reduction_share_capital"):
            for i in (1, 2, 3):
                d.set(f"{stem}{i}", "0", LY)
        for n in ("SweatEquityShareAllotted", "SweatEquityShareAllotted2", "SweatEquityShareAllotted3"):
            d.set(n, "0", LY)
        for stem in ("AtTheBegining_OftheYear", "Issue_Of_Shares", "Re_Issue_Of_Shares", "I_RedemptionOf_Shares",
                     "Shares_II_Forfeited", "III_REdemption_ofShare", "III_AtTheEndOf_Year"):
            for sfx in ("", "1", "2"):
                d.set(stem + sfx, "0", LY)
        d.set("ivNill", "Yes", LY)
    elif changed:
        d.todo.append("Share capital changed: enter the paid-up break-up (IV(d)) and transfers by hand.")
    for n in ("Debenture3NoNConvertiNC", "partiallyConDebNumOfClasses", "fullyConDebNumOfClasses", "SecutiryOtherShareDebeunt"):
        d.set(n, "0", LY)

    # ---- turnover / net worth
    t = _num(fs, "PL:Revenue from operations")
    nw = _num(fs, "BS:Share capital + BS:Reserves and surplus")
    d.set("turnoverV", _i(t) if t is not None else None, FS)
    d.set("NetWorthOfTeCompany", _i(nw) if nw is not None else None, FS)

    # ---- shareholding pattern (carried forward unless holders changed)
    rows = [2, 3, 4, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]  # portal row numbers for 1(i)..10 (the 2(...) group skips 5)
    hchanged = _yes(a.get("holders_changed"))
    if not hchanged:
        for grp, key in (("a", "promoters"), ("b", "others")):
            pat = f.get(key) or []
            # PDF rows: 1(i),1(ii),1(iii),2(i),2(ii),2(iii),3..10 = 16 rows; portal has 14 data rows
            data = pat[:3] + pat[3:6] + pat[6:14] if len(pat) >= 14 else pat
            for r, vals in zip(rows, data):
                d.set(f"equity_no_share_{grp}_{r}", _i(vals[0]), LY)
                d.set(f"pref_tot_no_share_{grp}_{r}", _i(vals[2]), LY)
        d.set("tot_shareholers_vi_a", _i(f.get("n_promoters")), LY)
        d.set("Total_Other_Prometers", _i(f.get("n_others")), LY)
        g = f.get("gender") or {}
        for k, n in (("female", "individual_female"), ("male", "individual_male"),
                     ("transgender", "individual_transgender"), ("other", "other_than_individuals")):
            d.set(n, _i(g.get(k, 0)), LY)
        h = f.get("holders") or {}
        for k, (b, e) in (("promoters", ("AtheBeginingPromoters", "At_theEndPromoters")),
                          ("members", ("AtTheBeginMemebers", "At_theEndMEmbers")),
                          ("debenture", ("AtTheBeginningDebenture", "AtTheEndDebenture"))):
            if h.get(k):
                d.set(b, str(h[k][1]), LY)   # this year's beginning = last year's end
                d.set(e, str(h[k][1]), LY)
        total_holders = (f.get("n_promoters") or 0) + (f.get("n_others") or 0)
        d.set("number_share_debentureholder", str(total_holders), LY)
    else:
        d.todo.append("Shareholders changed: fill the shareholding pattern (VI), member counts (VII) and the shareholder list by hand.")

    # ---- meetings and attendance
    bm = _dates(a.get("board_meetings"))
    d.set("meeting_held_IXA", "1" if held else "0", Q)
    if bm:
        d.set("meeting_held_IXB", str(len(bm)), Q)
    if held:
        d.set("AttendanceOfDirectorDate", a.get("agm_date"), Q)
    dirs = f.get("directors") or []
    if dirs and not _yes(a.get("directors_changed")):
        n = len(bm) if bm else None
        all_att = _yes(a.get("all_attended", "Yes"))
        d.tables["AtendanceOfDiretor_Table"] = [{
            "din": x["din"], "nameOfDirector": x["name"],
            "meeting_entitled_ix_d": str(n) if n else None,
            "meeting_attended_ix_d": str(n) if (n and all_att) else None,
            "percentageOfAttendance": "100" if (n and all_att) else None,
            "AttendanceOfDirectorRadio23": ("Yes" if all_att else None) if held else "Not applicable"} for x in dirs]
        if not all_att:
            d.todo.append("Not every director attended: enter meetings attended per director (VIII C).")
    elif dirs:
        d.todo.append("Directors changed: enter the attendance table (VIII C) by hand.")
    if bm:
        d.todo.append(f"Board meetings ({len(bm)}): attach the MCA 'Board Meeting' Excel with these dates on the portal.")

    # ---- remuneration
    rem = []
    for part in re.split(r";", str(a.get("remuneration") or "")):
        if "=" in part:
            name, amt = part.split("=", 1)
            try:
                rem.append((name.strip(), float(str(amt).replace(",", "").strip())))
            except ValueError:
                pass
    if rem:
        desig = {r.get("name", "").lower(): r["designation"] for r in f.get("remuneration") or []}
        d.set("number_managingdirector_remuneration", str(len(rem)), Q)
        d.tables["AnumberTableMDiretor"] = [{
            "remuneration_managingdirector_name": n, "remuneration_managingdirector_designation": desig.get(n.lower(), "Whole-time director"),
            "remuneration_managingdirector_grosssalary": _i(v), "remuneration_managingdirector_commission": "0",
            "remuneration_managingdirector_stockoption": "0", "remuneration_managingdirector_others": "0"} for n, v in rem]
    d.set("number_ceo_cfo_remuneration", "0", LY)

    # ---- compliance, penalties, declaration
    d.set("radiobutton1641559612315", "Yes", LY if f.get("compliance_ok") else Q)
    if not _yes(a.get("penalties")):
        d.set("details_penalities_ch", "Yes", Q)
        d.set("details_of_offenses_ch", "Yes", Q)
    else:
        d.todo.append("Penalty / compounding: fill section XI by hand.")
    d.set("dinPanMemberShipNum", a.get("designated_din"), Q)
    d.set("textbox1641789712635", f.get("resolution_no") or "nil", LY)
    d.set("decDatepicker", a.get("resolution_date"), Q)
    d.set("DeclarationDesignation", "Director", LY)
    d.set("DeclarationDINOfTheDirector", a.get("signing_din"), Q)
    d.todo.append("Attach: photo of registered office (if asked), list of shareholders (MCA Excel), optional attachments.")
    return d


# ---------------------------------------------------------------- AOC-4

def _d(facts, key):
    return (facts or {}).get(key)


QUESTIONS_AOC4 = [
    ("board_fs_date", "Date of board meeting that approved the financial statements", "DD/MM/YYYY",
     lambda f, fs: fs.setup("Date of board meeting approving board's report") if fs else None),
    ("board_report_date", "Date of board meeting that approved the board's report", "DD/MM/YYYY (often the same day)", lambda f, fs: None),
    ("fs_sign_date", "Date the directors signed the financial statements and board's report", "DD/MM/YYYY",
     lambda f, fs: fs.setup("Date of board meeting approving board's report") if fs else None),
    ("auditor_report_date", "Date of signing of the auditor's report", "DD/MM/YYYY", lambda f, fs: None),
    ("product_desc", "Description of the main product or service (AOC-4 product table)", "text",
     lambda f, fs: _d(f, "product_desc")),
    ("related_party", "Any transactions with related parties this year?", "Yes / No", lambda f, fs: _d(f, "related_party") or "No"),
    ("ca_cop", "Certificate of practice number of the certifying CA", "number", lambda f, fs: None),
    ("ca_fellow", "Certifying CA is Associate or Fellow?", "Associate / Fellow", lambda f, fs: None),
]


def derive_aoc4(facts, answers, fs, mgt7a_facts=None):
    """Non-financial AOC-4 fields by AEM element name; the figures come from mapping/aoc4_map.xlsx."""
    d = Derived()
    f = facts or {}
    a = dict(answers)
    LY, FS, Q = "last year's AOC-4", "Schedule III", "Questions"
    end = _fy_end(fs, None)
    if not end and f.get("fy_to"):
        e0 = datetime.strptime(f["fy_to"], "%d/%m/%Y").date()
        end = e0.replace(year=e0.year + 1)
    if end:
        d.set("fromDate", (end.replace(year=end.year - 1) + timedelta(days=1)).strftime("%d/%m/%Y"), FS)
        d.set("toDate", end.strftime("%d/%m/%Y"), FS)
    if end:
        # Balance sheet header date: "Figures as at the end of (Current reporting period)"
        d.set("FiguresAtEndOfCurrentReporting", end.strftime("%d/%m/%Y"), FS)
    # Gross PPE (financial parameter 44) = net PPE and intangibles + depreciation for the year (firm practice)
    gross = _setup_amount(fs, "Gross property plant and equipment") or         _num(fs, "BS:Property, plant and equipment + BS:Intangible assets + PL:Depreciation and amortization expense")
    try:
        gross = float(str(gross).replace(",", "")) if gross is not None else None
    except ValueError:
        gross = None
    if gross is not None:
        d.override["grossPropertyPlant"] = (_i(gross), FS)
    d.override["paidupper"] = ("0", LY)  # proposed dividend %
    tally_overrides(d, fs, FS)
    # Revenue: a services company (product codes 99xx, NPCS) reports all revenue as "sale or supply of services"
    prods_ = f.get("products") or []
    if prods_ and all(str(p_.get("code4", "")).startswith("99") for p_ in prods_):
        rev_ = _num(fs, "PL:Revenue from operations")
        if rev_ is not None:
            d.override["revenueFromOperationsCurrent3"] = (_i(rev_), FS)
            d.override["revenueFromOperationsCurrent2"] = ("0", FS)
            d.override["revenueFromOperationsCurrent1"] = ("0", FS)
    d.set("textbox1643785189026", a.get("board_fs_date"), Q)
    d.set("natureS", "Adopted Financial statements", LY)
    d.set("wetherProFinancialStatement", "No", LY)
    d.set("whetherAdoptedAdjAGM", "No", LY)
    sign = a.get("fs_sign_date") or a.get("board_fs_date")
    if f.get("fs_signatories"):
        d.tables["fs_signatories"] = [{"DINorIncome": s["din"], "designation": s["designation"], "DateOfSigning": sign}
                                      for s in f["fs_signatories"]]
    d.set("DateOfBoard", a.get("board_report_date") or a.get("board_fs_date"), Q)
    if f.get("report_signatories") or f.get("fs_signatories"):
        d.tables["report_signatories"] = [{"din": s["din"], "designation1": s["designation"], "DateOfSigningOfBoard": sign}
                                          for s in (f.get("report_signatories") or f["fs_signatories"])]
    d.set("dateOfSigningOfReports", a.get("auditor_report_date"), Q)
    held = _yes(a.get("agm_held", "Yes"))
    d.set("whetherAnnualGeneralMeeting", "Yes" if held else "No", Q)
    if held:
        d.set("ifyesDateOfAGM", a.get("agm_date"), Q)
    d.set("dueDateOfAGM", a.get("agm_due"), Q)
    d.set("whetherAnyExtension", "Yes" if _yes(a.get("agm_extension")) else "No", Q)
    d.set("WhetherCompanyIsSubsidiary", f.get("is_subsidiary") or "No", LY)
    d.set("whetherCompanyHasSubsidiary", f.get("has_subsidiary") or "No", LY)
    cat = (f.get("auditor") or {}).get("category")
    d.set("categoryOfAuditor", cat, LY)
    if f.get("industry"):
        d.set("InsuranceOrNBFC", f["industry"], LY)
    d.set("whetherSchedule3", f.get("sch3_applicable") or "Yes", LY)
    d.set("whetherConsolidated", f.get("consolidated") or "No", LY)
    d.set("WhetherCompanyisMaintainingBooks", f.get("books_electronic"), LY)
    d.set("whetherAnyOperating", f.get("lease_converted") or "No", LY)
    d.set("Whether_maintenance", f.get("cost_records") or "No", LY)
    d.set("Whether_audit_of_cost_records", f.get("cost_records") or "No", LY)
    # products / services: the main category gets the whole revenue from operations
    prods = f.get("products") or []
    rev = _num(fs, "PL:Revenue from operations")
    if prods:
        d.set("TotalNumberProductService123", str(len(prods)), LY)
        d.tables["products"] = [{"ProductCategory1": p["code4"], "HighestContribuProduct44": p["code8"],
                                 "DescriptionOftheProduct1223": a.get("product_desc") or f.get("product_desc"),
                                 "TurnoverOfTheRupees3": _i(rev) if (rev is not None and len(prods) == 1) else None,
                                 "DetailstableLAstcolumn": _i(rev) if (rev is not None and len(prods) == 1) else None}
                                for p in prods]
    # EPS = profit for the year / equity shares; share capital raised = no change unless answered otherwise
    eq = (mgt7a_facts or {}).get("equity") or {}
    nominal = ((eq.get("nominal") or [None])[0]) or 10
    paid = _num(fs, "Notes:Share capital/Total issued, subscribed and fully paid up")
    paid_py = _num(fs, "Notes:Share capital/Total issued, subscribed and fully paid up") if False else None
    shares = _num(fs, "Setup:Weighted avg. equity shares - current year") or ((paid / nominal) if paid else None)
    shares_py = _num(fs, "Setup:Weighted avg. equity shares - previous year") or shares
    for per, shr, sfx in (("CY", shares, "Current"), ("PY", shares_py, "Previous")):
        prof = None
        if fs and shr:
            try:
                prof = fs.eval("PL:Profit / (loss) for the period (XI + XIV)", per)
            except Exception:  # noqa: BLE001
                prof = None
        if prof is not None and shr:
            eps = f"{prof / shr:.2f}"
            for n in (37, 38, 40, 41):
                d.set(f"revenueFromOperations{sfx}{n}", eps, FS)
            if per == "CY":
                d.set("a_basic", eps, FS)
                d.set("b_dilut", eps, FS)
    if paid and not _yes(a.get("capital_changed")):
        row = {"noOfShares_shareCapRaise": _i(paid / nominal), "totNominalAmtCapRaise": _i(paid), "totPaidupAmtCapRaise": _i(paid)}
        for n in (2, 19):
            for k, v in row.items():
                d.set(f"{k}{n}", v, FS)
        for n in list(range(4, 13)) + [15, 16, 17] + [21] + list(range(23, 25)) + [27, 28, 29, 31]:
            for k in ("noOfShares_shareCapRaise", "totNominalAmtCapRaise", "totPaidupAmtCapRaise", "totPremCapRaise"):
                d.set(f"{k}{n}", "0", LY)
        # rows 13, 18, 25, 30 are "Others, specify": left blank on purpose
    d.set("Whether_any_transactions_entered", "Yes" if _yes(a.get("related_party")) else "No", Q)
    d.set("segmentIVradioIa", "Not applicable", LY)
    d.set("segmentIVradioII", "No", LY)
    if f.get("csr"):
        d.set("csrApplicability", f["csr"], LY)
    d.set("segmentVradio1", f.get("secretarial_audit") or "No", LY)
    # declaration and certificate
    d.set("dec_no", f.get("resolution_no") or "nil", LY)
    d.set("dec_date", a.get("resolution_date"), Q)
    d.set("designation_dec", "Director", LY)
    d.set("dec_directorIdentification", a.get("signing_din") or f.get("signing_din"), Q)
    d.set("categoryOfProfessional", "Chartered Accountant (in whole-time practice) or", LY)
    d.set("whetherAssociateOrFellow", a.get("ca_fellow"), Q)
    d.set("certificateOfPracticeNumber", a.get("ca_cop"), Q)
    if _yes(a.get("related_party")):
        d.todo.append("Related party transactions: attach AOC-2 on the portal.")
    d.todo.append("Attach: financial statements with auditor's and board's report (PDF), and any optional attachments.")
    return d
