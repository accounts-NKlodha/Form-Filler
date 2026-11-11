# Board's Report and Auditor's Report templates (in sync with AOC-4 / MGT-7A)

The two templates are your own sample reports. Every company-specific word or figure has been replaced with a `{{PLACEHOLDER}}`; the layout and standard wording are unchanged.

Every placeholder takes its value from the **same source the MCA filler uses**: the Schedule III workbook (Setup, BS, PL and Notes sheets). So the reports, AOC-4 and MGT-7A can never disagree.

- `Board report - template.docx`: 60 placeholders.
- `Auditor report - template.docx`: 14 placeholders.

## 1. Rows to add to the Setup sheet (column A label, column B value)

Add these on top of the AOC-4 rows already listed. One row each; dates as DD/MM/YYYY.

| Setup label | Used in | Also fills |
|---|---|---|
| Annual report number (e.g. 32nd) | Board's Report | |
| Place of signing | both reports | |
| Signing director 1 name / Signing director 1 DIN | Board's Report signature | AOC-4 signatories |
| Signing director 2 name / Signing director 2 DIN | Board's Report signature | AOC-4 signatories |
| Board strength (number of directors) | Board meetings table | MGT-7A attendance |
| Board meeting dates (already listed) | Board meetings table | MGT-7A + board meeting Excel |
| Auditor firm name | both reports | AOC-4 auditor details |
| Auditor FRN | both reports | |
| Signing partner name / Partner membership number / Partner designation (Proprietor or Partner) | Auditor's Report | AOC-4 auditor details |
| UDIN | Auditor's Report | |
| Date of AGM appointing auditor / Auditor term ends in year | Board's Report (Auditors) | ADT-1 reference |
| Date of auditor's report (already listed) | Auditor's Report date | AOC-4 item 6 |
| Date of board meeting approving board's report (already listed) | Board's Report date | AOC-4 item 5(a) |
| Deposits accepted (nil or amount) | Board's Report | AOC-4 parameter 9 |
| Dividend recommended (nil or Rs. per share) | Board's Report | AOC-4 proposed dividend |
| Transfer to general reserve (nil or amount) | Board's Report | |
| Foreign exchange earnings / outgo (nil or amount) | Board's Report | AOC-4 forex tables |
| CSR applicability, secretarial audit, cost records (already listed) | Board's Report wording | AOC-4 Yes/No items |
| Annual return web link (or "not hosted") | Board's Report | |

## 2. Figures in the Board's Report "Financial Results" table

These come from the PL sheet, current and previous year:

| Placeholder | Formula |
|---|---|
| SALES AND OTHER INCOME | Revenue from operations + Other income |
| PBIDT | Profit before tax + Finance costs + Depreciation |
| INTEREST | Finance costs |
| PBDT | Profit before tax + Depreciation |
| DEPRECIATION | Depreciation and amortization expense |
| PBT | Profit before tax |
| TAX | Current tax + Deferred tax |
| PAT | Profit for the period |

`FY` is written as 2025-2026 and `PREVIOUS FY` as 2024-2025. `FY END YEAR` is the year of the balance sheet date.

## 3. Placeholders with a choice

Some placeholders offer options, for example `{{DIVIDEND: has not declared any Dividend / has recommended a dividend of Rs. ___ per share}}`. Pick the option that fits and delete the rest, including the braces. Use the Setup answer so it matches what AOC-4 says.

Board meeting rows: the table has 5 rows. Add or delete rows so it matches the number of board meeting dates.

## 4. Prompt to give Claude when preparing a client's reports

Attach the two templates and the client's Schedule III workbook, then paste:

> Fill the attached Board's Report and Auditor's Report templates for this company, using only the attached Schedule III workbook. Replace every {{PLACEHOLDER}} as described in "How to use the report templates": take the company details and dates from the Setup sheet rows of the same name, and take the Financial Results figures from the PL sheet using the formulas given (current and previous year, Indian number format, no decimals). For placeholders with options, keep the option that matches the Setup answer and delete the others. Make the board-meeting table match the "Board meeting dates" row. Keep all other wording and formatting exactly as in the template. List any placeholder you could not fill instead of guessing.

## 5. Notes from the sample

- The sample Board's Report still referred to **Form MGT-9 (Extract of Annual Return)**. MGT-9 has been omitted since FY 2020-21. The template now carries the Section 92(3) / 134(3)(a) Annual Return wording instead.
- In the sample Auditor's Report, **022565S is the auditor's FRN** (firm registration number), not a certificate of practice number. AOC-4's certificate of practice number for the certifying CA is a different number. Please check it.
