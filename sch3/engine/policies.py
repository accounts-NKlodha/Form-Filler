"""Note 2 - significant accounting policies (Accounting Standards under the Companies (Accounting Standards) Rules, 2021).
A client config can replace any policy by heading ("policies": {heading: text or [paragraphs]}), add new ones, or drop
one by setting it to "". "nbfc": true adds the NBFC-specific policies."""

BASE = [
 ("Basis of preparation",
  "The financial statements have been prepared under the historical cost convention on the accrual basis of accounting, "
  "in accordance with the generally accepted accounting principles in India, the Accounting Standards specified under "
  "section 133 of the Companies Act, 2013 read with the Companies (Accounting Standards) Rules, 2021 and the relevant "
  "provisions of the Act. The financial statements are presented in the format prescribed in Division I of Schedule III to the Act."),
 ("Use of estimates",
  "The preparation of financial statements requires management to make estimates and assumptions that affect the reported "
  "amounts of assets and liabilities, the disclosure of contingent liabilities and the reported income and expenses. "
  "Differences between actual results and estimates are recognised in the period in which they are known."),
 ("Current and non-current classification",
  "Assets and liabilities are classified as current or non-current on the basis of the operating cycle of the Company, "
  "which has been determined as twelve months, and the other criteria set out in Schedule III to the Act."),
 ("Revenue recognition",
  "Revenue is recognised to the extent that it is probable that the economic benefits will flow to the Company and the "
  "revenue can be reliably measured. Interest income is recognised on a time proportion basis."),
 ("Property, plant and equipment and depreciation",
  "Property, plant and equipment are stated at cost less accumulated depreciation. Cost includes all expenses incidental "
  "to bringing the asset to its working condition. Depreciation is provided on the written down value method over the "
  "useful lives of the assets as prescribed in Schedule II to the Companies Act, 2013."),
 ("Investments",
  "Investments intended to be held for more than one year are classified as long-term investments and are carried at "
  "cost. Provision for diminution is made to recognise a decline, other than temporary, in the value of long-term investments."),
 ("Taxes on income",
  "Current tax is determined as the amount of tax payable in respect of taxable income for the year in accordance with "
  "the Income Tax Act, 1961. Deferred tax is recognised, subject to prudence, on timing differences between taxable "
  "income and accounting income that originate in one period and are capable of reversal in subsequent periods."),
 ("Provisions and contingent liabilities",
  "A provision is recognised when the Company has a present obligation as a result of a past event and it is probable "
  "that an outflow of resources will be required to settle the obligation, in respect of which a reliable estimate can "
  "be made. Contingent liabilities are disclosed in the notes. Contingent assets are not recognised."),
 ("Employee benefits",
  "Short-term employee benefits are recognised as an expense in the year in which the related service is rendered."),
 ("Earnings per share",
  "Basic earnings per share is computed by dividing the net profit after tax by the weighted average number of equity "
  "shares outstanding during the year. There are no dilutive potential equity shares."),
 ("Cash and cash equivalents",
  "Cash and cash equivalents comprise cash on hand and balances with banks in current accounts."),
]

NBFC = [
 ("Revenue recognition",
  "Revenue is recognised to the extent that it is probable that the economic benefits will flow to the Company and the "
  "revenue can be reliably measured. Interest income on loans is recognised on a time proportion basis, taking into "
  "account the amount outstanding and the rate applicable, in accordance with the prudential norms issued by the Reserve "
  "Bank of India. Interest on non-performing assets is recognised only when it is actually realised."),
 ("Asset classification and provisioning",
  "Loans and advances are classified as standard, sub-standard, doubtful or loss assets, and provision is made, in "
  "accordance with the prudential norms prescribed by the Reserve Bank of India for Non-Banking Financial Companies. "
  "A contingent provision against standard assets is made at the rate prescribed by the Reserve Bank of India."),
 ("Statutory reserve",
  "In accordance with section 45-IC of the Reserve Bank of India Act, 1934, the Company transfers not less than twenty "
  "per cent of its net profit for the year to the statutory reserve."),
]


def policies_for(cfg):
    if cfg.get("policies_list"):  # the client's own signed wording, used as is (also feeds the SAP document)
        return [(h, t) for h, t in cfg["policies_list"]]
    out = list(BASE)
    if cfg.get("nbfc"):
        heads = [h for h, _ in out]
        for h, t in NBFC:
            if h in heads: out[heads.index(h)] = (h, t)
            else: out.insert(heads.index("Taxes on income"), (h, t)); heads = [x for x, _ in out]
    for h, t in (cfg.get("policies") or {}).items():
        heads = [x for x, _ in out]
        if h in heads:
            if t: out[heads.index(h)] = (h, t)
            else: out.pop(heads.index(h))
        elif t:
            out.append((h, t))
    return out
