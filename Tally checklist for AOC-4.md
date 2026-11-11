# Tally checklist for AOC-4: what to pull from Tally into the Setup sheet

Schedule III gives the Balance Sheet and P&L totals. AOC-4 also asks for some splits and memo figures that only Tally (or the books) has. Pull each item below from Tally and put it on the **Setup sheet**: label in column A, exactly as shown, and the amount in column B (current year, absolute rupees, no commas needed).

- **Leave a row blank or out** if the item is nil. The filler then puts 0, or keeps its default.
- **Previous-year figures:** MCA pre-fills these from last year's filing. You don't need to add them.

When Claude prepares the Schedule III workbook with the Tally connector, give it this checklist and ask it to add these Setup rows as well.

## A. Foreign exchange (AOC-4 Segment II, Part II-A and II-B, and P&L parameters 3–4)

Where to look in Tally:
- ledgers kept in a foreign currency (if multi-currency is on)
- import purchase ledgers (Purchase – Import, Customs duty) and export sales ledgers (Sales – Export / LUT / SEZ)
- foreign vendors and customers in Sundry Creditors / Debtors
- GST "Import of goods / services" and "Exports" summaries

| Setup label | What to take |
|---|---|
| Export of goods FOB | Export sales of goods at FOB value |
| Forex earnings - interest and dividend | Interest/dividend received in foreign currency |
| Forex earnings - royalty | |
| Forex earnings - know-how | |
| Forex earnings - professional and consultation fees | Export of services billed in foreign currency |
| Forex earnings - other income | Other income received in foreign currency |
| Imports CIF - raw material | Import purchases of raw material at CIF value |
| Imports CIF - components and spare parts | |
| Imports CIF - capital goods | Imported machinery/assets (fixed asset ledgers) |
| Forex expenditure - royalty | |
| Forex expenditure - know-how | |
| Forex expenditure - professional and consultation fees | Payments to foreign consultants, software subscriptions billed abroad |
| Forex expenditure - interest | Interest on foreign borrowings |
| Forex expenditure - other matters | Foreign travel, foreign subscriptions and the like |
| Forex expenditure - dividend paid | Dividend remitted to non-resident shareholders |

The filler totals these itself into "Total earning / expenditure in foreign exchange" and "Income / Expenditure in foreign currency".

## B. Related party transactions: AS-18 (BS parameter 22, P&L parameter 8)

- **Directors' remuneration is included automatically.** It is taken from the Notes ("Directors' remuneration"), because it is a related-party (KMP) transaction under AS-18.
- **Add every other related-party transaction for the year** as one total. Look in Tally under director / relative / group-company ledgers: purchases, sales, rent paid to directors or relatives, interest on director loans, loans given or taken, reimbursements.

| Setup label | What to take |
|---|---|
| Related party transactions other than directors' remuneration | Total value of all other AS-18 transactions in the year |
| Bad debts of related parties | Bad debts written off for related-party balances |

- **Also update the question "Related party transactions during the year (Yes/No)".** It drives AOC-4 Segment III, and Yes means AOC-2 is needed. Use the section 188 view: directors' remuneration alone normally does not make this Yes.

## C. Trade receivables and loans (Break-up E and C)

In Tally, go to Display More Reports → Statements of Accounts → Outstandings → Receivables, and use the ageing analysis (by due date or bill date).

| Setup label | What to take |
|---|---|
| Trade receivables outstanding more than 6 months | Debtors outstanding over 6 months from the due date. The rest goes to "less than 6 months" automatically. |
| Trade receivables due by directors | Debtor balances of directors / their firms |
| Loans and advances due by directors | Loans or advances given to directors |

## D. Borrowings (Break-up A and B)

Look in the Loans (Liability) group and the bank OD ledgers, plus the sanction letters.

| Setup label | What to take |
|---|---|
| Borrowings guaranteed by directors - long term | Long-term loans backed by a director's personal guarantee |
| Borrowings guaranteed by directors - short term | CC / OD and other short-term loans with a director's guarantee |

## E. Profit and loss lines AOC-4 shows separately

| Setup label | What to take | Effect |
|---|---|---|
| Managerial remuneration (AOC-4 line) | Remuneration to MD / WTD / Manager | Shown on AOC-4 line (e) and taken out of "Employee benefit expenses". Leave it out to keep it inside employee benefits, as last year. |
| Consumption of stores and spare parts | Stores consumed (stock group "Stores and spares") | P&L parameter 7 |
| Revenue subsidies or grants received | Government grants credited to P&L | P&L parameter 5 |
| Capital subsidies or grants received | Capital grants received | BS parameter 23 |
| Contribution to political parties (section 182) | | P&L parameter 10 |

## F. Balance sheet memo items (AOC-4 Financial parameters)

| Setup label | Where in Tally |
|---|---|
| Deposits accepted or renewed during the year | Loans (Liability) from non-directors / public, if any (DPT-3 data) |
| Proposed dividend | Board decision, not in Tally |
| Unpaid dividend | Unpaid dividend bank account / ledger |
| Unhedged foreign currency exposure | Open foreign-currency creditors and debtors at year end without forward cover |
| Gross property plant and equipment | Leave blank to use net PPE + intangibles + depreciation for the year (firm practice) |

## G. Things that stay a portal check

- **Revenue split:** domestic vs export, and manufactured vs traded vs services. The filler puts everything under services for services companies (NPCS code 99xx); otherwise check it.
- **Payment to auditors:** taxation, other services and reimbursement, if the firm bills them separately.
- **The "reason for change in pre-filled previous-year figures" boxes.**
