# What to add to the Schedule III workbook so MCA forms fill without questions

Today the filler reads the BS, PL, Notes and Setup sheets. Everything below is what AOC-4, MGT-7A and MGT-7 still need from somewhere else: last year's filed form, a staff question, or typing by hand. If the workbook carries it, those questions go away.

Suggested home: one new sheet called **MCA**. It has two columns, Label | Value, and a few small tables. The filler finds things by label, so the order doesn't matter.

## 1. Company master (MCA sheet, one value each)
| Label | Used in | Note |
|---|---|---|
| Telephone number with STD code | MGT-7A/7 | Masked in last year's PDF, so it can't be carried forward |
| Website | MGT-7A/7 | |
| PAN of the company | MGT-7A/7 | Masked in PDF |
| Class / Category / Sub-category of company | MGT-7A/7 | E.g. Private company / Limited by shares / Non-government |
| Small company or OPC (Yes/No) | MGT-7A | |
| Main business activity: group code, activity code, % of turnover | MGT-7A/7, AOC-4 | NIC codes. AOC-4 also wants product/service ITC or NPCS codes and turnover per product |
| Designated person (Rule 9(4)): DIN / PAN and name | MGT-7A/7 | |
| Signing director: DIN and designation | AOC-4, MGT-7A/7 | |
| Auditor: firm name, FRN, PAN, address, signing partner and membership no., ADT-1 SRN | AOC-4 | |

## 2. Meetings and dates (MCA sheet)
| Label | Used in |
|---|---|
| Date of board meeting approving the financial statements | AOC-4 |
| Date of board meeting approving the board's report | AOC-4 |
| Date of signing of the auditor's report | AOC-4 |
| AGM held (Yes/No), AGM date, AGM due date, extension SRN and extended date | AOC-4, MGT-7A/7 |
| Board meeting dates during the year (list) and attendance per director | MGT-7A/7 (plus the MCA board-meeting Excel) |
| Date of board resolution authorising the signatory (and resolution number) | AOC-4, MGT-7A/7 |

## 3. Share capital and shareholders (MCA sheet, small tables)
- **Nominal value per share** and **number of shares** for authorised, issued, subscribed and paid-up capital, by class (equity and preference).
- **Movement during the year**: allotments (rights, bonus, private placement, ESOP, sweat equity, conversion), buy-back, forfeiture and reduction. Give the number of shares, the nominal amount and the premium for each.
- **Shareholder list**: name, PAN, category (promoter / other; individual / body corporate / …), residential status, gender, number of shares. The filler can then produce the shareholding pattern, the gender break-up, promoter and member counts, and the MCA shareholder Excel.
- **Weighted average number of shares** for EPS. The Setup cells exist but were blank.
- **Debentures and other securities**, if any: classes, units and nominal value.

## 4. Directors and KMP (MCA sheet, table)
For each director or KMP: DIN/PAN, name, designation (MD / WTD / Director / CFO / CS), date of appointment or cessation during the year, and remuneration paid. Split remuneration into gross salary, commission, stock options and others. Today the Notes give only one total line, "Directors' remuneration".

## 5. Figures AOC-4 needs that Schedule III does not split (Notes)
| Item | Today |
|---|---|
| Revenue split: domestic / export × goods manufactured / goods traded / services | Only products / services / other operating revenue |
| Other income split: dividend, interest, net gain on sale of investments, other | Only interest / other |
| Changes in inventories split: finished goods / WIP / stock-in-trade | One line |
| Inventories split: raw material, WIP, finished goods, stock-in-trade, stores, loose tools | Stock-in-trade only |
| Payment to auditor: as auditor / taxation / company law / management services / other services / reimbursement | Statutory audit only |
| Managerial remuneration as its own line (out of employee benefits) | Inside employee benefits |
| Gross block and accumulated depreciation of PPE | Tally WDV only (gross PPE is an AOC-4 financial parameter) |
| Trade receivables: secured / unsecured / doubtful, provision, outstanding > 6 months, debts due by directors | Unsecured good only |
| Loans and advances (long and short term): secured / unsecured / doubtful, related parties, due by directors | Partly |
| Borrowings: secured / unsecured by type, guaranteed by directors | Partly |
| Reserves: securities premium, general reserve, capital reserve as separate rows | Surplus only in Notes |
| Earnings and expenditure in foreign currency (CIF imports, royalty, know-how, fees, interest, dividend) | Not present |
| Proposed dividend, unpaid dividend, deposits accepted, CSR spend and applicability | Not present |

## 6. Yes/No disclosures (MCA sheet)
Related party transactions (and AOC-2 if yes), cost records/audit applicable, secretarial audit applicable, CSR applicable, auditor's report qualified (and the qualification text), any penalty/compounding, any change in share capital / shareholders / directors during the year.

## 7. Workbook rules that help the filler
- Keep the **rounding divisor at 1** (MCA wants absolute rupees). Save the file in Excel after every refresh, so the formula results are stored.
- Keep **row labels exactly as in the Heads sheet**. The filler matches by label, so a renamed label shows up as an orange "not found" cell.
- Put the **CIN** in Setup (it is blank today) so the filler can confirm it is filling the right company.
