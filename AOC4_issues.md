# AOC-4 live test: issues list (Chennai Hydro-Maatics, FY 2025-26)

| # | Issue | Status |
|---|-------|--------|
| 1 | Alt+Shift+F wiped values: Yes/No buttons all carry the value "on", so the tool ticked "Yes" and re-ticked gate questions, which makes MCA clear dependent sections | Fixed v0.4.8: picks the option by its label, never touches an answered question |
| 2 | Type of industry showed "0" | Fixed v0.4.9: dropdowns chosen by visible text (Commercial & Industrial, from last year's AOC-4) |
| 3 | Balance sheet date "Figures as at the end of (Current reporting period)" not filled | Fixed: filled with the FY end date (To date) |
| 4 | Previous-year figures must not be changed when MCA pre-fills them; if empty, take them from last year's AOC-4 | Fixed: tool keeps any pre-filled previous-year figure; inputs now take previous-year figures from last year's filed AOC-4 (93 of 112 matched; rest from the workbook) |
| 5 | Long-term loans and advances, "3 Other loans and advances" was 0 (should be 17,96,468.69) | Fixed in map: LT security deposits + LT other + ST other loans (security deposits row is hidden on the portal; same treatment as last year's AOC-4). BS (d) = 17,96,468.69, BS (e) = 2,15,730.32 |
| 6 | Trade receivables "Unsecured, considered good" was 0 | Fixed in map: value goes in the visible column (the hidden "less than 6 months" column is left blank) |
| 7 | Balance sheet header date "Figures as at the end of (Current reporting period)" still empty | Fixed (inputs): 31/03/2026 (FY end) |
| 8 | Gross PPE and intangible assets (parameter 44) blank | Fixed (inputs): BS PPE + intangible assets (Tally keeps WDV only) |
| 9 | Re-running after Save re-typed the previous-year creditors figure (10068624 → 10068624.41) | Fixed v0.5.0: amounts compare as numbers (commas and paise ignored), so a saved figure counts as unchanged |
| 10 | Services company: all revenue under "Sale or supply of services" (3,33,79,661.65); goods traded / manufactured 0 | Fixed (inputs): applies when last year's product codes are NPCS services (99xx) |
| 11 | Proposed dividend % field to be 0 | Fixed (inputs) |

## Shared-file note (ADT-1 thread, 14/10/2026)

`mca.py` got small additive hooks for ADT-1 (code lives in `ADT1/adt1.py`). Nothing changes for AOC-4 / MGT-7A: the hooks only act when the form slug starts with `adt` or the path starts with `/adt1`. Added: `GET /adt1` page, `/plan?slug=adt…` served from `ADT1/ADT-1 companies.xlsx`, `POST /adt1/...`, ADT-1 column map rebuilt after an ADT-1 dump, ADT-1 fill logs go to `ADT1/logs`, and a link on the dashboard. The extension is unchanged (still v0.5.1). AOC-4 `/plan` checked after the change: same output.

**Extension v0.5.2 (ADT-1 thread, 14/10/2026):** opt-in auto Save / Next. Only a plan with `autoSave: true` (and `autoNext: true`) makes the extension click the highlighted Save, then the portal's exact-text "Next" when the page is done, and loop round by round until a round fills nothing. The ADT-1 plan sets it at Rohit's request; AOC-4 / MGT-7A plans don't, so they behave exactly as in v0.5.1. Alt+Shift+X now also stops the loop between rounds. Submit / Upload / DSC are still never clicked.

**Extension v0.5.3 (ADT-1 thread):** still opt-in (`autoSave` plans only). Dropdowns with no matching option yet (Area/Locality loads after the pin code) are retried last, up to ~15 s, before Save. Next is clicked when no field waits below an unclicked Save (portal-filled read-only fields no longer block it); if Next isn't there, the run stops. AOC-4 / MGT-7A unaffected.

**Extension v0.5.4 (ADT-1 thread):** plans with an `attachments` list (ADT-1 only) upload each still-empty attachment on the page: the PDF comes from the local server (`GET /adt1/file`, new in mca.py, ADT-1 only), is put in that attachment's file box, and that attachment's own Upload button is pressed. Plans without `attachments` (AOC-4 / MGT-7A) never upload, as before. DSC upload and Submit are still never touched.

**Extension v0.5.5 (ADT-1 thread):** `autoAdvance` plans (ADT-1 only): after the attachments page is saved (no Next there), the server marks the company Saved and picks the next company with all attachments and a signatory; the tab opens a fresh ADT-1 and fills it on its own. Alt+Shift+X stops it. Other forms unaffected.

**Extension v0.5.6 (ADT-1 thread):** during `autoSave` runs only, browser alerts ("Document uploaded successfully") and in-page notices with a single OK ("Informational message", "saved successfully") are acknowledged automatically; confirm() dialogs are never answered. 2 s gap between uploads. A fresh ADT-1 opened for the next company now asks "Continue / Stop here" instead of starting by itself. AOC-4 / MGT-7A unaffected (alerts behave normally outside autoSave runs).
