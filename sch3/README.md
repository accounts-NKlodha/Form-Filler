# Schedule III Builder: user guide

The app pulls trial balances from Tally and builds a formula-driven Schedule III workbook (Division I, non-Ind AS). The workbook is ready for the AOC-4 / MGT-7 filler. The app runs on your PC and opens in your browser. No data leaves the office.

## One-time install (each PC)
1. Copy the `Schedule-III-App` folder anywhere, for example `D:\Schedule-III-App`.
2. Double-click **setup.bat**.
   - It installs Python 3.12 if it is missing (through winget). If winget is not available, install Python from python.org and tick "Add python.exe to PATH".
   - It then installs three packages: openpyxl, pycel and pypdf.
3. Double-click **start.bat**. The browser opens at http://localhost:8765. Keep the black window open while you work.

## Tally setting (once)
In Tally Prime, go to F1 Help > Settings > Connectivity and set Client/Server configuration to **Both** (or Server), port **9000**. Load both companies: this year's and last year's (for example the "- Audited" copy).

## Monthly / annual flow
| Step | Screen | What happens |
|---|---|---|
| 1 | Tally trial balances | Click **List open companies**, pick the CY and PY company, and fetch each. Net profit is taken from Tally. The roll-forward check lists any ledger whose LY closing does not equal its CY opening. You can upload a TB CSV/Excel instead. |
| 2 | Masters & last year | Upload the Auditor & director master, the ROC master, LY signed Schedule III and LY filed AOC-4. Enter the AGM date and click **Read masters**. Every value shows its file, sheet, column and row. Tick the values to use. |
| 3 | Mapping approval | Every ledger is compared with its plain Tally grouping and sorted into these groups: **Section changes**, **Head changes within the section**, **Contra balances** (firm defaults), **Borrowings** (related-party confirmation, with the LT/ST split typed in and never moved automatically), **Not mapped** and **No change**. Change the head from the dropdown, tick, enter your name and save. Approvals are remembered for next year. |
| 4 | Setup inputs | All Setup-sheet fields the AOC-4 filler reads, including the rounding divisor, EPS shares, report dates and AOC-4 parameters. |
| 5 | Build & tie-out | Builds and calculates the workbook (1-3 minutes). It shows the Checks sheet, ties every PY figure to LY signed Schedule III and LY AOC-4, and lets you download the Excel. |

Next year, click **Start next year**. Mappings and approvals carry forward, this year's TB becomes last year's, and this year's output becomes the LY tie-out file.

## Sharing with the team
- **Each person on their own PC:** copy the folder and run setup.bat. To share approved client mappings, open `settings.json` (create it next to app.py) and point the clients folder to a shared drive:
  `{"clients_folder": "\\\\server\\share\\Schedule-III\\clients", "data_folder": "\\\\server\\share\\Schedule-III\\data"}`
- **One PC serving everyone:** run **start_lan.bat**. Team members open `http://<that-PC-IP>:8765`. The Tally PC box on screen 1 can point at any office PC running Tally (port 9000).

## Rules built in
- Firm defaults:
  - Debtor Cr balances go to Advances from customers.
  - Creditor Dr balances go to Advances to suppliers.
  - Bank Cr balances go to OD.
- Every regrouping needs a named approval. The build warns if any ledger is unapproved.
- Borrowings are never split between LT and ST automatically.
- A P&L ledger mapped to a Balance Sheet head, or the reverse, is flagged in red.
- The ROC master is read only from the "ROC Companies" sheets (incorporation date, auditor, BM dates). Credential sheets and columns are never opened.

## Files
- `clients/<company>.json`: approved mapping, Setup values and approvals log for each client.
- `data/<company>/<FY>/`: TBs, uploads, the built Excel and `last_build.json`.
- `engine/`: workbook generator (`build_sch3.py`), mapping rules (`mapping.py`), Tally client (`tally.py`), masters reader, LY tie-out.
