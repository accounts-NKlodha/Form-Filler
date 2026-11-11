# MCA form filler: staff guide

Fills AOC-4, MGT-7 and MGT-7A drafts on the MCA V3 portal from the client's Excel. **It only fills and clicks Save.** Login, captcha, attachments, DSC, Pre-scrutiny, Submit and Pay are always done by you.

## One-time setup (per computer)

1. Install Python 3 and run `pip install openpyxl`.
2. Open the MCA Chrome window: right-click `open_mca_chrome.ps1` > Run with PowerShell. Always use this window for MCA work.
3. **Before logging in**, go to `chrome://extensions` in that window. Turn on Developer mode, click **Load unpacked**, and pick the `MVP\extension` folder.
4. If the old **MCA spike filler** extension is listed, click **Remove**. Both use the same keys, and the old one types dummy test data.

## Each client (filing app)

1. Double-click `start_server.bat`. The filing app opens at http://127.0.0.1:8742. Leave the black window open while you work.
2. **New filing**: type the client name and click Start. Then work down the four steps on the client's page:
   1. **Details**: CIN, year ended, and the forms (AOC-4, MGT-7A, ADT-1).
   2. **Upload data**: this year's Schedule III workbook (Checks sheet OK, rounding divisor 1, saved and closed), last year's filed AOC-4 and MGT-7A PDFs, last year's MCA Excel attachments, and the attachments the tool uploads on the portal (signed financial statements for AOC-4, registered office photo for MGT-7A).
   3. **Answer the questions**: click Prepare questions. Most answers are suggested; fill the ones marked *needed*, correct anything else, then click Save answers and rebuild.
   4. **Fill on MCA**: check the ready counts, then click **Start filling** (one client), or put the client in the filing queue (many clients).
3. The old dashboard (captured forms, Build / Use for filling) is at http://127.0.0.1:8742/admin.

## Many clients in one sitting: the filing queue

1. On the app's home page, tick the clients and forms under **Filing queue** and click **Add to queue**. A client is added only when its CIN, answers and mandatory attachments are in place; the page says what is missing otherwise.
2. In the MCA Chrome window, log in once, open the side panel and click **Start the queue**.
3. For each client the tool opens the form, picks the company by CIN, fills each section, clicks Save and Next, and uploads the attachments.
4. On the last page it outlines **Submit** in red and waits. Check the form and click Submit yourself. The tool reads the SRN and, after a 5-second countdown, opens the next client's form.
5. When something needs you (a failed field, an error from the portal), it stops and says what. Fix it and click **Fill again**, or **Skip to next client**.
6. **Pause** in the side panel stops after the client being filled now. Alt+Shift+X stops at once.
7. Submitted forms wait under **Review before payment** with their SRN. Check each one, affix DSC, upload it and pay on MCA, then click **Checked and paid**. If the tool missed an SRN, type it in the side panel ("Submitted but the tool missed the SRN?") or on the home page.

The tool never clicks Submit, DSC or payment itself.

## The Chrome side panel

Click the **MCA filler** icon in the Chrome toolbar (pin it from the puzzle-piece menu). The panel stays open beside the portal and has:
- **Filing queue**: Start, Pause, and the client being filled.
- **Client for filling**: switch the client for one-off filling.
- **Save form** (same as Alt+Shift+D): records this page's fields for a new or changed form.
- **Form Filler** (same as Alt+Shift+F): fills the next section of the open draft.
- **Values list** (Alt+Shift+S) and **Stop** (Alt+Shift+X).

## Filling a form (one section at a time)

1. In the MCA Chrome window, log in yourself and open the form draft for the same client and year. Upload the **office photo** first; the portal won't open later sections without it (the tool reminds you if it's empty).
2. Click **Form Filler** in the side panel (or press **Alt+Shift+F**). A box at the bottom right shows the client, form and version (e.g. "MCA filler v0.4.6"). Check them, then click **Fill**.
3. The tool fills the open fields of **one section**, then stops. It scrolls to that section's **Save** and outlines it in red. **You click that Save.** The tool never clicks Save, Next, Upload or Submit.
4. Press **Alt+Shift+F** again for the next section. Fields already done show as **unchanged**, so repeating is always safe.
5. When the box says "Click the highlighted Save to save this page", click it, then go to the next page with the portal's **Next** and carry on.
6. **Don't press F5 in the middle of a page.** Values are kept only after you save.
7. Summary words:
   - **filled**: entered now.
   - **unchanged**: already correct.
   - **next-section**: waits for the Save you have to click.
   - **other-page**: on another page of the form.
   - **skipped-readonly**: locked or filled by the portal.
   - **manual** and **failed**: do these yourself.
8. **Alt+Shift+X** stops a running fill. **Esc** is left to the portal, e.g. for closing calendars.
9. **Alt+Shift+S** opens a side panel with every label and its value. Drag a value onto the MCA box (empty the box first), or press **Fill** or **Copy** for one field. Use this when a client doesn't want automatic filling.
10. Uploads stay with you. The tool prepares this year's MCA Excels (board meetings, members' meetings, shareholder list) in the client's `attachments` folder. Open each once to check it, then upload it with the portal's button.
11. Review every page, then do Pre-scrutiny, DSC and Submit yourself.

After the extension is updated (**reload** in chrome://extensions), always press **F5** on the MCA tab, or the old copy keeps running.

## When something is wrong

- **"Could not get a plan"**: the server is not running (start `start_server.bat`), or no client is marked **Use for filling**.
- **"the inputs workbook is locked"**: save the file in Excel, or close it.
- **A figure is wrong**: correct the Schedule III workbook, or the expression in `mapping\aoc4_map.xlsx` (column E), then Build again.
- **A new or changed MCA form**: open the blank draft and press **Alt+Shift+D**. This records the form's fields (no data) for the tool. Then Build again.
