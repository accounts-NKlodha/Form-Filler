# ADT-1 for many companies

1. Restart `start_server.bat` (once, to load the ADT-1 page), then open http://127.0.0.1:8742/adt1.
2. Capture the form once: open any ADT-1 draft on MCA and press **Alt+Shift+D** on each page. The column map (`adt1_columns.xlsx`) builds itself; check it once (green = matched).
3. Fill `ADT-1 companies.xlsx`: one row per company. Firm-wide values (auditor details, nature, years) go once on the **Defaults** sheet; a row only needs what differs. Appointed from / to and Date of appointment are worked out from the AGM date when blank.
4. **Prefill from files** reads `ADT1\source` (company master Excel with a CIN column, earlier ADT-1 / AOC-4 / MGT-7 PDFs) and the `clients` folders. Blank cells only.
5. Per company: click **Fill** on the page, log in and open that company's ADT-1 draft, press **Alt+Shift+F**, check the company name in the box, click Fill, then Save. Attachments, DSC and Submit stay with you. Set Status to Saved / Submitted in the workbook.
