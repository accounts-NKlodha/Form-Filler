"""Schedule III mapping tables and rules shared by the workbook builder and the app.

Codes: <LINE>.<SUB>. Sign +1 = credit nature, -1 = debit nature.
"""
import re

HEADS = [
 # code, line, stmt, sublabel, sign
 ("SC.EQ","SC","BS","Equity share capital - issued, subscribed and fully paid up",1),
 ("RS.SEC","RS","BS","Securities premium",1),
 ("RS.STAT","RS","BS","Statutory reserve as per RBI NBFC guidelines (s.45-IC)",1),
 ("RS.GEN","RS","BS","General reserve",1),
 ("RS.SURP","RS","BS","Surplus in Statement of Profit and Loss",1),
 ("MRSW.OTH","MRSW","BS","Money received against share warrants",1),
 ("SAM.OTH","SAM","BS","Share application money pending allotment",1),
 ("LTB.SECBANK","LTB","BS","Term loans from banks - secured",1),
 ("LTB.SECOTH","LTB","BS","Term loans from others - secured",1),
 ("LTB.UNSBANK","LTB","BS","Term loans from banks - unsecured",1),
 ("LTB.UNSNBFC","LTB","BS","Term loans from NBFCs / financial institutions - unsecured",1),
 ("LTB.UNSRP","LTB","BS","Loans from related parties - unsecured",1),
 ("LTB.UNSOTH","LTB","BS","Other loans - unsecured",1),
 ("DTL.NET","DTL","BS","Deferred tax liability (net)",1),
 ("OLTL.OTH","OLTL","BS","Other long-term liabilities",1),
 ("LTP.EMP","LTP","BS","Provision for employee benefits",1),
 ("LTP.OTH","LTP","BS","Other long-term provisions",1),
 ("STB.BANKOD","STB","BS","Loans repayable on demand from banks - secured (CC / OD)",1),
 ("STB.RP","STB","BS","Loans from directors / related parties - unsecured",1),
 ("STB.BD","STB","BS","Bill discounting / factoring facility from others - secured",1),
 ("STB.CM","STB","BS","Current maturities of long-term borrowings",1),
 ("STB.OTH","STB","BS","Other short-term borrowings",1),
 ("TP.MSME","TP","BS","Total outstanding dues of micro and small enterprises",1),
 ("TP.OTH","TP","BS","Total outstanding dues of creditors other than micro and small enterprises",1),
 ("OCL.STAT","OCL","BS","Statutory dues payable (GST, TDS etc.)",1),
 ("OCL.ADVC","OCL","BS","Advances from customers",1),
 ("OCL.RET","OCL","BS","Security deposits / retention money from sub-contractors",1),
 ("OCL.EMP","OCL","BS","Employee benefits payable",1),
 ("OCL.EXP","OCL","BS","Expenses payable",1),
 ("OCL.SUSP","OCL","BS","Suspense / unreconciled balances",1),
 ("OCL.OTH","OCL","BS","Other payables",1),
 ("STP.TAX","STP","BS","Provision for income tax",1),
 ("STP.EMP","STP","BS","Provision for employee benefits",1),
 ("STP.CONT","STP","BS","Contingent provision against standard assets",1),
 ("STP.AUD","STP","BS","Audit fees payable",1),
 ("STP.OTH","STP","BS","Other provisions",1),
 ("PPE.LAND","PPE","BS","Land",-1),
 ("PPE.BLDG","PPE","BS","Buildings",-1),
 ("PPE.EPBAX","PPE","BS","EPBAX",-1),
 ("PPE.PM","PPE","BS","Plant and machinery",-1),
 ("PPE.UPS","PPE","BS","UPS",-1),
 ("PPE.FF","PPE","BS","Furniture and fixtures",-1),
 ("PPE.VEH","PPE","BS","Vehicles",-1),
 ("PPE.OE","PPE","BS","Office equipment",-1),
 ("PPE.COMP","PPE","BS","Computers",-1),
 ("PPE.ELEC","PPE","BS","Electrical installations",-1),
 ("PPE.OTH","PPE","BS","Other assets",-1),
 ("INT.OTH","INT","BS","Intangible assets",-1),
 ("CWIP.OTH","CWIP","BS","Capital work-in-progress",-1),
 ("IAUD.OTH","IAUD","BS","Intangible assets under development",-1),
 ("NCI.EQ","NCI","BS","Investment in equity instruments - unquoted",-1),
 ("NCI.OTH","NCI","BS","Other investments",-1),
 ("DTA.NET","DTA","BS","Deferred tax asset (net)",-1),
 ("LTLA.SD","LTLA","BS","Security deposits - unsecured, considered good",-1),
 ("LTLA.BG","LTLA","BS","Margin money / deposits against bank guarantees",-1),
 ("LTLA.RET","LTLA","BS","Retention money withheld by customers",-1),
 ("LTLA.CAP","LTLA","BS","Capital advances",-1),
 ("LTLA.RP","LTLA","BS","Loans given to related parties - unsecured, considered good",-1),
 ("LTLA.LOAN","LTLA","BS","Loans given to unrelated parties - unsecured, considered good",-1),
 ("LTLA.OTH","LTLA","BS","Other long-term loans and advances",-1),
 ("ONCA.OTH","ONCA","BS","Other non-current assets",-1),
 ("CI.OTH","CI","BS","Current investments",-1),
 ("INV.ST","INV","BS","Stock-in-trade",-1),
 ("TR.GOOD","TR","BS","Unsecured, considered good",-1),
 ("CCE.CASH","CCE","BS","Cash on hand",-1),
 ("CCE.BANK","CCE","BS","Balances with banks - current accounts",-1),
 ("CCE.FD","CCE","BS","Other bank balances - fixed / recurring deposits",-1),
 ("STLA.RP","STLA","BS","Loans and advances to related parties (directors)",-1),
 ("STLA.SUPP","STLA","BS","Advances to suppliers",-1),
 ("STLA.EMP","STLA","BS","Advances to employees",-1),
 ("STLA.OTH","STLA","BS","Other loans and advances",-1),
 ("OCA.GOVT","OCA","BS","Balances with government authorities (GST, TDS, advance tax)",-1),
 ("OCA.SUSP","OCA","BS","Suspense / unreconciled balances",-1),
 ("OCA.OTH","OCA","BS","Other current assets",-1),
 ("REV.INT","REV","PL","Interest income (financing business)",1),
 ("REV.SALE","REV","PL","Sale of products",1),
 ("REV.SERV","REV","PL","Sale of services",1),
 ("REV.OOR","REV","PL","Other operating revenue (freight, packing recovered)",1),
 ("OI.INT","OI","PL","Interest income",1),
 ("OI.OTH","OI","PL","Other non-operating income",1),
 ("COMC.MAT","COMC","PL","Cost of materials consumed",-1),
 ("PUR.PUR","PUR","PL","Purchases of stock-in-trade",-1),
 ("PUR.FRT","PUR","PL","Freight and other costs on purchases",-1),
 ("PUR.DISC","PUR","PL","Less: discounts on purchases",-1),
 ("EMP.SAL","EMP","PL","Salaries and wages",-1),
 ("EMP.DIR","EMP","PL","Directors' remuneration",-1),
 ("EMP.PF","EMP","PL","Contribution to provident and other funds",-1),
 ("EMP.WELF","EMP","PL","Staff welfare expenses",-1),
 ("FIN.INT","FIN","PL","Interest expense",-1),
 ("FIN.OTH","FIN","PL","Other borrowing costs",-1),
 ("DEP.DEP","DEP","PL","Depreciation on property, plant and equipment",-1),
 ("OEXP.SUBC","OEXP","PL","Labour and sub-contract charges at site",-1),
 ("OEXP.HIRE","OEXP","PL","Hire charges - cranes, hydra and equipment",-1),
 ("OEXP.SITE","OEXP","PL","Site expenses",-1),
 ("OEXP.VEH","OEXP","PL","Vehicle maintenance",-1),
 ("OEXP.AGM","OEXP","PL","AGM expenses",-1),
 ("OEXP.AUD","OEXP","PL","Audit fees",-1),
 ("OEXP.BANK","OEXP","PL","Bank charges",-1),
 ("OEXP.TRAV","OEXP","PL","Conveyance expenses",-1),
 ("OEXP.ELEC","OEXP","PL","Electricity charges",-1),
 ("OEXP.MEMB","OEXP","PL","Membership fees for credit rating agencies & renewal for ISIN & RTA",-1),
 ("OEXP.OFF","OEXP","PL","Office expenses",-1),
 ("OEXP.MAINT","OEXP","PL","Office & other maintenance",-1),
 ("OEXP.POST","OEXP","PL","Postage & telegram",-1),
 ("OEXP.PRINT","OEXP","PL","Printing & stationery",-1),
 ("OEXP.RENT","OEXP","PL","Rent",-1),
 ("OEXP.ROC","OEXP","PL","ROC fees",-1),
 ("OEXP.COMM","OEXP","PL","Telephone charges",-1),
 ("OEXP.PWR","OEXP","PL","Power and fuel",-1),
 ("OEXP.REPB","OEXP","PL","Repairs to buildings",-1),
 ("OEXP.REPM","OEXP","PL","Repairs to machinery",-1),
 ("OEXP.REPO","OEXP","PL","Repairs and maintenance - others",-1),
 ("OEXP.INS","OEXP","PL","Insurance",-1),
 ("OEXP.RATES","OEXP","PL","Rates and taxes",-1),
 ("OEXP.FRT","OEXP","PL","Freight, packing and forwarding",-1),
 ("OEXP.PROF","OEXP","PL","Legal and professional fees",-1),
 ("OEXP.ADV","OEXP","PL","Advertisement and sales promotion",-1),
 ("OEXP.ADMIN","OEXP","PL","Office and administrative expenses",-1),
 ("OEXP.BD","OEXP","PL","Business development",-1),
 ("OEXP.PEN","OEXP","PL","Interest, penalty and late fees on statutory dues",-1),
 ("OEXP.DON","OEXP","PL","Donations, gifts and complements",-1),
 ("OEXP.FX","OEXP","PL","Net loss on foreign currency transactions",-1),
 ("OEXP.MISC","OEXP","PL","Miscellaneous expenses",-1),
 ("EXC.OTH","EXC","PL","Exceptional items",-1),
 ("EXO.OTH","EXO","PL","Extraordinary items",-1),
 ("TAX.CUR","TAXC","PL","Current tax",-1),
 ("TAX.EARLY","TAXC","PL","Tax relating to earlier years",-1),
 ("TAX.DEF","TAXD","PL","Deferred tax",-1),
]
LINES = {  # line: label
 "SC":"Share capital","RS":"Reserves and surplus","MRSW":"Money received against share warrants",
 "SAM":"Share application money pending allotment","LTB":"Long-term borrowings",
 "DTL":"Deferred tax liabilities (net)","OLTL":"Other long-term liabilities","LTP":"Long-term provisions",
 "STB":"Short-term borrowings","TP":"Trade payables","OCL":"Other current liabilities","STP":"Short-term provisions",
 "PPE":"Property, plant and equipment","INT":"Intangible assets","CWIP":"Capital work-in-progress",
 "IAUD":"Intangible assets under development","NCI":"Non-current investments","DTA":"Deferred tax assets (net)",
 "LTLA":"Long-term loans and advances","ONCA":"Other non-current assets","CI":"Current investments",
 "INV":"Inventories","TR":"Trade receivables","CCE":"Cash and cash equivalents",
 "STLA":"Short-term loans and advances","OCA":"Other current assets",
 "REV":"Revenue from operations","OI":"Other income","COMC":"Cost of materials consumed",
 "PUR":"Purchases of stock-in-trade","CHINV":"Changes in inventories of finished goods, work-in-progress and stock-in-trade",
 "EMP":"Employee benefits expense","FIN":"Finance costs","DEP":"Depreciation and amortization expense",
 "OEXP":"Other expenses","EXC":"Exceptional items","EXO":"Extraordinary items",
 "TAXC":"Current tax","TAXD":"Deferred tax",
}
SIGN = {h[0]: h[4] for h in HEADS}
HEAD = {h[0]: h for h in HEADS}

G_DEF = [  # group, code, contra, note
 ("Capital Account","SC.EQ","","Tally default"),
 ("Reserves & Surplus","RS.SURP","","Tally default"),
 ("Loans (Liability)","LTB.UNSOTH","STLA.OTH","Tally default - review current maturities"),
 ("Secured Loans","LTB.SECBANK","STLA.OTH","Tally default - review current maturities"),
 ("Unsecured Loans","LTB.UNSOTH","STLA.OTH","Tally default"),
 ("Bank OD A/c","STB.BANKOD","CCE.BANK","Tally default"),
 ("Current Liabilities","OCL.OTH","OCA.OTH","Tally default"),
 ("Duties & Taxes","OCL.STAT","OCA.GOVT","Tally default"),
 ("Provisions","STP.OTH","OCA.OTH","Tally default"),
 ("Sundry Creditors","TP.OTH","STLA.SUPP","Tally default - Dr balances to advances to suppliers (firm default). MSME split via Map_Ledgers"),
 ("Suspense A/c","OCL.SUSP","OCA.SUSP","Tally default - should be nil"),
 ("Branch / Divisions","OCL.OTH","OCA.OTH","Tally default"),
 ("Fixed Assets","PPE.OTH","","Tally default"),
 ("Investments","NCI.OTH","","Tally default - split current portion if any"),
 ("Misc. Expenses (ASSET)","ONCA.OTH","","Tally default"),
 ("Current Assets","OCA.OTH","OCL.OTH","Tally default"),
 ("Bank Accounts","CCE.BANK","STB.BANKOD","Tally default"),
 ("Cash-in-Hand","CCE.CASH","","Tally default"),
 ("Deposits (Asset)","LTLA.SD","OCL.OTH","Tally default"),
 ("Loans & Advances (Asset)","STLA.OTH","OCL.OTH","Tally default"),
 ("Stock-in-Hand","INV.ST","","Tally default"),
 ("Sundry Debtors","TR.GOOD","OCL.ADVC","Tally default - Cr balances to advances from customers (firm default)"),
 ("Sales Accounts","REV.SALE","","Tally default"),
 ("Direct Incomes","REV.OOR","","Tally default"),
 ("Indirect Incomes","OI.OTH","","Tally default"),
 ("Purchase Accounts","PUR.PUR","","Tally default (trading). Manufacturer: change to COMC.MAT"),
 ("Direct Expenses","OEXP.FRT","","Tally default"),
 ("Indirect Expenses","OEXP.MISC","","Tally default"),
]

G_DEF_MAP = {g[0].lower(): g for g in G_DEF}

# Ledgers every Tally company has
L_BASE = [
 ("Profit & Loss A/c", "RS.SURP", "", "Tally P&L A/c forms part of surplus"),
]

BS_LINES = ["SC","RS","MRSW","SAM","LTB","DTL","OLTL","LTP","STB","TP","OCL","STP",
            "PPE","INT","CWIP","IAUD","NCI","DTA","LTLA","ONCA","CI","INV","TR","CCE","STLA","OCA"]

# Keyword suggestions for ledgers sitting in a generic Tally group. (regex, code, contra, reason, groups it applies to)
_PL = ("indirect expenses", "direct expenses")
RULES = [
 (r"^income ?tax( paid)?$|income tax expense|provision for (income )?tax.*expense|current tax", "TAX.CUR", "", "Tax booked in expenses; Sch III shows it below PBT", _PL),
 (r"deferred tax", "TAX.DEF", "", "Deferred tax below PBT", _PL),
 (r"depreciation|amorti[sz]ation", "DEP.DEP", "", "Separate P&L line", _PL),
 (r"interest on (loan|unsecured|borrow|od|cc|term)|bank interest|interest paid|interest on loan", "FIN.INT", "", "Finance cost", _PL),
 (r"loan processing|processing fee", "FIN.OTH", "", "Other borrowing cost", _PL),
 (r"director.*(remuneration|salary)", "EMP.DIR", "", "Directors' remuneration", _PL),
 (r"salar|wages|bonus|gratuity", "EMP.SAL", "", "Employee benefits", _PL),
 (r"provident|\bpf\b|\besi", "EMP.PF", "", "Contribution to funds", _PL),
 (r"staff welfare", "EMP.WELF", "", "Employee benefits", _PL),
 (r"audit fee", "OEXP.AUD", "", "Payment to auditor", _PL),
 (r"bank charge", "OEXP.BANK", "", "Other expenses", _PL),
 (r"^rent", "OEXP.RENT", "", "Other expenses", _PL),
 (r"electricity|power", "OEXP.ELEC", "", "Other expenses", _PL),
 (r"printing|stationery|stationary", "OEXP.PRINT", "", "Other expenses", _PL),
 (r"postage|courier", "OEXP.POST", "", "Other expenses", _PL),
 (r"telephone|internet|mobile", "OEXP.COMM", "", "Other expenses", _PL),
 (r"conveyance|travel", "OEXP.TRAV", "", "Other expenses", _PL),
 (r"insurance", "OEXP.INS", "", "Other expenses", _PL),
 (r"professional|consultan|legal", "OEXP.PROF", "", "Other expenses", _PL),
 (r"\broc\b|filing fee", "OEXP.ROC", "", "Other expenses", _PL),
 (r"repair|maintenance|maintanance", "OEXP.MAINT", "", "Other expenses", _PL),
 (r"advertis|sales promotion|business promotion", "OEXP.ADV", "", "Other expenses", _PL),
 (r"rates and taxes|rates & taxes", "OEXP.RATES", "", "Other expenses", _PL),
 (r"interest", "OI.INT", "", "Interest income", ("indirect incomes",)),
 (r"audit fee.*payable|expenses? payable|rent payable", "OCL.EXP", "", "A payable, not a provision", ("provisions",)),
 (r"salary.*payable|salaries payable|wages payable", "OCL.EMP", "", "Employee payable, not a provision", ("provisions",)),
 (r"income ?tax|provision for tax|taxation", "STP.TAX", "OCA.GOVT", "Provision for income tax", ("provisions",)),
 (r"\btds\b|\btcs\b|advance tax|income tax refund", "OCA.GOVT", "OCL.STAT", "Balances with revenue authorities", ("current assets", "loans & advances (asset)")),
 (r"deferred tax asset", "DTA.NET", "DTL.NET", "Non-current: deferred tax asset (net)", ("current assets", "loans & advances (asset)")),
 (r"\bfd\b|fixed deposit|recurring deposit", "CCE.FD", "", "Other bank balances", ("deposits (asset)", "current assets", "investments")),
 (r"general reserve", "RS.GEN", "", "General reserve", ("reserves & surplus",)),
 (r"statutory reserve", "RS.STAT", "", "Statutory reserve (s.45-IC)", ("reserves & surplus",)),
 (r"securities premium|share premium", "RS.SEC", "", "Securities premium", ("reserves & surplus",)),
]


def group_code(group, primary, groups):
    """Code/contra for a ledger from its immediate group, then primary group. groups: list of (group, code, contra, note), client first."""
    for g in (group, primary):
        if not g:
            continue
        for row in groups:
            if row[0].lower() == g.lower():
                return row[1], row[2], row[3]
    return None, "", ""


def resolve(ledger, group, primary, closing, ledgers, groups):
    """Final sub-head code as the workbook formulas compute it (ledger override > group > primary group, contra by sign)."""
    lmap = {l[0].lower(): l for l in ledgers}
    if ledger.lower() in lmap:
        _, code, contra, _ = lmap[ledger.lower()]
    else:
        code, contra, _ = group_code(group, primary, groups)
        if code is None:
            return None
    sg = SIGN.get(code, 0)
    if contra and closing * sg < 0:
        return contra
    return code


def suggest(ledger, group, primary):
    """Keyword suggestion for a ledger sitting in a generic Tally group. Returns (code, contra, reason) or None."""
    g, p = (group or "").lower(), (primary or "").lower()
    for rx, code, contra, why, applies in RULES:
        if (g in applies or p in applies) and re.search(rx, ledger, re.I):
            return code, contra, why
    return None


def line_of(code):
    return HEAD[code][1] if code in HEAD else None
