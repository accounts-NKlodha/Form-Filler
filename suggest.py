import re

"""Starting suggestions for mapping MCA form fields to the firm's Schedule III workbook.

Each rule: (section pattern, label pattern, source expression). Patterns are regexes
matched against the normalised section path and field label (lower case, words only).
The first matching rule wins, so specific rules come before general ones. These are
only suggestions: they are written into mapping/<form>_map.xlsx, where the firm
reviews and edits them. Rows with no rule are left blank for staff.
"""

AOC4 = [
    # ---- Break-up A: long-term borrowings (unsecured)
    (r"long term borrowings.*unsecured|details of long term borrowings", r"related part", "Notes:Long-term borrowings/Loans from directors / related parties - unsecured|Loans from related parties - unsecured"),
    (r"long term borrowings.*unsecured|details of long term borrowings", r"other loans", "Notes:Long-term borrowings/Other loans - unsecured"),
    # ---- Break-up B: short-term borrowings (unsecured)
    (r"short term borrowings.*unsecured|details of short term borrowings", r"related part", "Notes:Short-term borrowings/Loans from directors / related parties - unsecured|Loans repayable on demand - from related parties (unsecured)"),
    (r"short term borrowings.*unsecured|details of short term borrowings", r"other loans", "Notes:Short-term borrowings/Other short-term borrowings"),
    # ---- Break-up C: long-term loans and advances (good)
    (r"long term loans and advances.*good", r"capital advances", "Notes:Long-term loans and advances/Capital advances"),
    (r"long term loans and advances.*good", r"other loans", "Notes:Long-term loans and advances/Other long-term loans and advances + Notes:Long-term loans and advances/Security deposits - unsecured, considered good"),
    # ---- Break-up E: trade receivables
    (r"trade receivables", r"unsecured considered good", "Notes:Trade receivables/Unsecured, considered good"),
    # ---- Financial parameters (balance sheet)
    (r"financial parameters", r"net worth", "BS:Share capital + BS:Reserves and surplus"),
    (r"financial parameters", r"^secured loan", "Notes:Long-term borrowings/Term loans from banks - secured + Notes:Long-term borrowings/Term loans from others - secured + Notes:Short-term borrowings/Loans repayable on demand from banks - secured (CC / OD)"),
    (r"financial parameters", r"^depreciation and amortization", "PL:Depreciation and amortization expense"),
    (r"financial parameters", r"rent paid", "Notes:Other expenses/Rent"),
    # ---- Balance sheet
    (r"", r"^share capital\b", "BS:Share capital"),
    (r"", r"^reserves and surplus", "BS:Reserves and surplus"),
    (r"", r"money received against share", "BS:Money received against share warrants"),
    (r"", r"share application money pending", "BS:Share application money pending allotment"),
    (r"", r"^long term borrowings", "BS:Long-term borrowings"),
    (r"", r"^deferred tax liabilities", "BS:Deferred tax liabilities (net)"),
    (r"", r"^other long term liabilities", "BS:Other long-term liabilities"),
    (r"", r"^long term provisions", "BS:Long-term provisions"),
    (r"", r"^short term borrowings", "BS:Short-term borrowings"),
    (r"", r"creditors other", "Notes:Trade payables/Total outstanding dues of creditors other than micro and small enterprises"),
    (r"", r"micro enterprises and small", "Notes:Trade payables/Total outstanding dues of micro and small enterprises"),
    (r"", r"^other current liabilities", "BS:Other current liabilities"),
    (r"", r"^short term provisions", "BS:Short-term provisions"),
    (r"", r"^property plant and equipment$", "BS:Property, plant and equipment"),
    (r"", r"^intangible assets under development", "BS:Intangible assets under development"),
    (r"", r"^intangible assets$", "BS:Intangible assets"),
    (r"", r"^capital work in progress", "BS:Capital work-in-progress"),
    (r"", r"^non current investments", "BS:Non-current investments"),
    (r"", r"^deferred tax assets", "BS:Deferred tax assets (net)"),
    (r"", r"^long term loans and advances", "BS:Long-term loans and advances"),
    (r"", r"^other non current assets", "BS:Other non-current assets"),
    (r"", r"^current investments", "BS:Current investments"),
    (r"", r"^inventories", "BS:Inventories"),
    (r"", r"^trade receivables", "BS:Trade receivables"),
    (r"", r"^cash and cash equivalents", "BS:Cash and cash equivalents"),
    (r"", r"^short term loans and advances", "BS:Short-term loans and advances"),
    (r"", r"^other current assets", "BS:Other current assets"),
    # ---- Statement of profit and loss
    (r"domestic|revenue", r"sale of goods traded", "Notes:Revenue from operations/Sale of products"),
    (r"domestic|revenue", r"sale or supply of services", "PL:Revenue from operations - Notes:Revenue from operations/Sale of products"),
    (r"other income", r"interest income", "Notes:Other income/Interest income|Interest on income tax refund"),
    (r"other income", r"other non operating income", "Notes:Other income/Other non-operating income"),
    (r"", r"^cost of materials consumed", "PL:Cost of materials consumed"),
    (r"", r"^purchases of stock in trade", "PL:Purchases of stock-in-trade"),
    (r"changes in inventories|expenses", r"^stock in trade", "PL:Changes in inventories of finished goods, work-in-progress and stock-in-trade"),
    (r"", r"^employee benefit", "PL:Employee benefits expense"),
    (r"", r"^payment to auditors", "Notes:Other expenses/Payment to auditor - statutory audit|Audit fees"),
    (r"", r"^insurance expenses", "Notes:Other expenses/Insurance"),
    (r"", r"^power and fuel", "Notes:Other expenses/Power and fuel"),
    (r"", r"^finance cost", "PL:Finance costs"),
    (r"", r"^depreciation and amortization", "PL:Depreciation and amortization expense"),
    (r"", r"^other expenses", "PL:Other expenses - Notes:Other expenses/Payment to auditor - statutory audit|Audit fees - Notes:Other expenses/Insurance - Notes:Other expenses/Power and fuel"),
    (r"", r"^exceptional items", "PL:Exceptional items"),
    (r"", r"^extraordinary items", "PL:Extraordinary items"),
    (r"", r"^current tax", "PL:Current tax"),
    (r"", r"^deferred tax$", "PL:Deferred tax"),
]

MGT7 = [
    (r"", r"^turnover", "PL:Revenue from operations"),
    (r"", r"net worth", "BS:Share capital + BS:Reserves and surplus"),
]

RULES = {"aoc4": AOC4, "mgt7": MGT7, "mgt7a": MGT7}


def rules_for(slug):
    s = slug.lower().replace("-", "")
    if s.startswith("aoc4"):
        return AOC4
    return RULES.get(s, [])


# AOC-4 by AEM element name (exact, so it beats label matching). Current and Previous
# columns share one rule; the period comes from the field. "0" = nothing of that kind.
_RV = r"^revenueFromOperations(Current|Previous)"
_BU = r"^(current|previous)ReportingPeriod"
AOC4_NAMES = [
    (_RV + r"2$", "Notes:Revenue from operations/Sale of products"),
    (_RV + r"3$", "PL:Revenue from operations - Notes:Revenue from operations/Sale of products"),
    (_RV + r"(1|4|5|6|7)$", "0"),
    (_RV + r"8$", "Notes:Other income/Interest income|Interest on income tax refund"),
    (r"^netGainOrLossOnInvestmentSale(Current|Previous)$", "0"),
    (_RV + r"9$", "Notes:Other income/Other non-operating income"),
    (_RV + r"11$", "PL:Cost of materials consumed"),
    (_RV + r"12$", "PL:Purchases of stock-in-trade"),
    (_RV + r"(13|14)$", "0"),
    (_RV + r"15$", "PL:Changes in inventories of finished goods, work-in-progress and stock-in-trade"),
    (_RV + r"16$", "PL:Employee benefits expense"),
    (_RV + r"17$", "0"),
    (_RV + r"18$", "Notes:Other expenses/Payment to auditor - statutory audit|Audit fees"),
    (_RV + r"19$", "Notes:Other expenses/Insurance"),
    (_RV + r"20$", "Notes:Other expenses/Power and fuel"),
    (_RV + r"21$", "PL:Finance costs"),
    (_RV + r"22$", "PL:Depreciation and amortization expense"),
    (_RV + r"23$", "PL:Other expenses - Notes:Other expenses/Payment to auditor - statutory audit|Audit fees - Notes:Other expenses/Insurance - Notes:Other expenses/Power and fuel"),
    (_RV + r"26$", "PL:Exceptional items"),
    (_RV + r"28$", "PL:Extraordinary items"),
    (_RV + r"30$", "PL:Current tax"),
    (_RV + r"31$", "PL:Deferred tax"),
    (_RV + r"(33|34)$", "0"),
    # Break-up A: long-term borrowings (unsecured)
    (_BU + r"7$", "Notes:Long-term borrowings/Loans from directors / related parties - unsecured|Loans from related parties - unsecured"),
    (_BU + r"9$", "Notes:Long-term borrowings/Other loans - unsecured"),
    (_BU + r"(1|3|4|5|6|8|11)$", "0"),
    # Break-up B: short-term borrowings (unsecured)
    (_BU + r"B3$", "Notes:Short-term borrowings/Loans from directors / related parties - unsecured|Loans repayable on demand - from related parties (unsecured)"),
    (_BU + r"B5$", "Notes:Short-term borrowings/Other short-term borrowings"),
    (_BU + r"B(1|2|4|7)$", "0"),
    # Break-up C: long-term loans and advances (good); D: doubtful = nil
    (_BU + r"C1$", "Notes:Long-term loans and advances/Capital advances"),
    (_BU + r"C2$", "Notes:Long-term loans and advances/Security deposits - unsecured, considered good"),
    (_BU + r"C4$", "Notes:Long-term loans and advances/Other long-term loans and advances"),
    (_BU + r"C(3|6|7|9)$", "0"),
    (_BU + r"D(1|2|3|4|6|7|9)$", "0"),
    # Break-up E: trade receivables (no ageing in the workbook: all shown as within 6 months - check)
    (r"^(current|previous)_lesser6_unsecuredconsideredgood$", "Notes:Trade receivables/Unsecured, considered good"),
    (r"^(current|previous)_(greater6|lesser6)_(securedconsideredgood|doubt|less|debt_due)$", "0"),
    (r"^(current|previous)_greater6_unsecuredconsideredgood$", "0"),
    # Financial parameters
    (r"^netWorthOfCompany$", "BS:Share capital + BS:Reserves and surplus"),
    (r"^secureLoan$", "Notes:Long-term borrowings/Term loans from banks - secured + Notes:Long-term borrowings/Term loans from others - secured + Notes:Short-term borrowings/Loans repayable on demand from banks - secured (CC / OD)"),
    (r"^depreciationAndAmortization$", "PL:Depreciation and amortization expense"),
    (r"^rent_paid$", "Notes:Other expenses/Rent"),
    (r"^(amountOfIssueForContracts|shareApplicationMoney\d|paidUpCapital\d|paidUpPercentage\d|numberOfShares|depositsAcceptedOrRenewed|depositsMaturedAndClaimed\d|depositsMatured|unclaimedMatured|debenturesClaimed|interestOnDepositsAccrued|unpaidDividend|investmenetInSubsidiary|invisementInGov|capitalReserve|amountDueForTransfer|interCorporateDeposits|grossValueOfTransaction|capitalSubsidiesOrGrants|callsUnpaidBy\w+|forfeitedShares\w*|borrowingFromForeign\d?|interCorporateBorrowings\d|commercialPaper|conversionOfWarrants\d|warrantsIssued\d|defaultInPayment\d|numberOfShareholders|miscellaneousExpenditure|unhedgedForeign)$", "0"),
    (r"^(Proposed_Dividend|Income_in_foreign_currency|Exp_in_foreign_currency|Revenue_sub|Consumptionofstores|Grossvalue|BadDebts|contributionUnderSection182)$", "0"),
    # Foreign exchange earnings / expenditure: nil unless the firm says otherwise
    (r"^Part(C|P)\d$", "0"),
    (r"^Part2(CR|PR)\d+$", "0"),
]
SKIP_NAME = re.compile(r"reason|^tableItem|^headerItem|^reas\d", re.I)
