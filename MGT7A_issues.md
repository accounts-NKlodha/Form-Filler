# MGT-7A live test: issues list (Chennai Hydro-Maatics, FY 2025-26)

| # | Issue | Status |
|---|-------|--------|
| 1 | "As on FY end" name / address / lat-long were cleared by the copy step | Fixed: the tool no longer touches that table, and any field the portal rejects gets its old value back |
| 2 | Telephone missing (masked in last year's PDF) | Fixed: Questions sheet, stored with the leading 0 |
| 3 | Section Save buttons: later sections stay locked until Save is clicked | Fixed (v0.4.x): the tool fills one section, stops and highlights the Save; staff click it |
| 4 | Esc (closing the date picker) stopped the fill | Fixed: Alt+Shift+X stops; Esc is left to the portal |
| 5 | Equity class grid left empty (appears only after "Number of classes = 1") | Fixed: tables are filled in form order, the tool waits for late tables, and the class name is added |
| 6 | Office photo is mandatory before the save works | Reminder box before filling. v0.4.6 also detects the hidden file input MCA uses |
| 7 | "Others, specify" rows (4 in the share capital break-up) must stay blank, not 0 | Fixed in the inputs: no value is sent for those rows |
| 8 | Section values seemed lost after F5 mid-page | Use the page's bottom Save before refreshing |
| 9 | "Nil" tick boxes (penalties, compounding, share transfers) not ticked: the tool did not find them | Fixed in v0.4.5: recognises MCA tick-box ids (`…_1_widget`) and styled hidden inputs |
| 10 | Meeting counts need the MCA Excel upload (members' and board meetings) | Excels pre-filled in the client's attachments folder; staff upload |
| … | More from Rohit after pages 2-3 | |
