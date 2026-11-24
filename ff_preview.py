"""Form preview laid out like the MCA form: segment bar, part heading, then the form's own rows.

A line that has a current and a previous figure (or several columns, as in the share capital table) is one
table row, as on the portal. Single fields are a label with its box. Every box carries a colour for where the
value came from; the full source is in the tooltip. Read-only: nothing here is typed by hand.
"""
import re

import app
import ff_audit

SRC = {"tally": ("Tally", "#1f7a4d"), "lastyear": ("Last year's form", "#8a6d1a"), "staff": ("Typed by staff", "#1d4f91"),
       "ai": ("Local AI, confirmed by staff", "#7a3e9d"), "auto": ("Worked out", "#5c6470")}
CY, PY = "Current reporting period", "Previous reporting period"

# Fields whose label on the portal is a placeholder ("Text Box", "1", an internal name): what the box is, in words.
NICE = {
    "datepicker_to_date": "(b) Financial year for which the annual return is being filed (To date)",
    "number_associate_company": "Number of associate companies (including joint ventures)",
    "preference_shareClass": "Preference shares: number of classes",
    "Debenture3NoNConvertiNC": "Non-convertible debentures: number of classes",
    "partiallyConDebNumOfClasses": "Partly convertible debentures: number of classes",
    "fullyConDebNumOfClasses": "Fully convertible debentures: number of classes",
    "SecutiryOtherShareDebeunt": "Securities other than shares and debentures: number",
    "individual_female": "Members other than promoters: individual, female", "individual_male": "Members other than promoters: individual, male",
    "individual_transgender": "Members other than promoters: individual, transgender",
    "other_than_individuals": "Members other than promoters: other than individuals",
    "meeting_held_IXA": "Members' meetings: number of meetings held", "meeting_held_IXB": "Board meetings: number of meetings held",
    "details_penalities_ch": "A Details of penalties or punishment imposed on company, directors or officers",
    "details_of_offenses_ch": "B Details of compounding of offences",
    "dinPanMemberShipNum": "DIN, PAN or membership number of the designated person",
    "textbox1641789712635": "Board resolution number", "decDatepicker": "Date of the board resolution",
    "DeclarationDesignation": "Declaration: designation of the person signing", "DeclarationDINOfTheDirector": "Declaration: DIN of the director signing",
    "whetherAnyOperating": "40 Whether any operating lease has been converted to financial lease or vice-versa",
}
NIL_TICK = {"details_penalities_ch", "details_of_offenses_ch", "ivNill"}  # a ticked box here means "Nil"
MGT7A_SEC = [  # (test on field name / internal panel, section heading in the form's words)
    (lambda n, k: n in ("turnoverV", "NetWorthOfTeCompany"), "V Turnover and net worth"),
    (lambda n, k: n.startswith(("individual_", "other_than_individuals")), "VII Number of promoters, members and debenture holders"),
    (lambda n, k: n.startswith("meeting_held") or n == "AttendanceOfDirectorDate", "VIII Meetings of members and board of directors"),
    (lambda n, k: n == "number_ceo_cfo_remuneration", "IX Remuneration of directors and key managerial personnel"),
    (lambda n, k: n == "radiobutton1641559612315", "X Certification of compliances and disclosures"),
    (lambda n, k: n in ("details_penalities_ch", "details_of_offenses_ch"), "XI Penalty and punishment"),
    (lambda n, k: n == "number_share_debentureholder", "Details of shareholders and debenture holders"),
    (lambda n, k: "businessactivitiespanel" in k, "II and III Principal business activities and associate companies"),
    (lambda n, k: "sharecapitalanddebenturespanel" in k, "IV Share capital, debentures and other securities"),
    (lambda n, k: "shareholdingpatternpanel" in k, "VI Shareholding pattern"),
    (lambda n, k: "promotersanddirectorspanel" in k, "VII Number of promoters, members and debenture holders"),
    (lambda n, k: "attachmentanddeclarationsection" in k, "Attachments and declaration"),
    (lambda n, k: "companydetailsinformation" in k, "I Registration and other details"),
]


# Shareholding pattern (MGT-7A, VI): the portal's boxes carry no row text, only a row number in their name.
SH_ROWS = {2: "1 Individual or Hindu undivided family: (i) Indian", 3: "1 Individual or Hindu undivided family: (ii) Non-resident Indian (NRI)",
           4: "1 Individual or Hindu undivided family: (iii) Foreign national (other than NRI)",
           6: "2 Government: (i) Central Government", 7: "2 Government: (ii) State Government", 8: "2 Government: (iii) Government companies",
           9: "3 Insurance companies", 10: "4 Banks", 11: "5 Financial institutions", 12: "6 Foreign institutional investors",
           13: "7 Mutual funds", 14: "8 Venture capital", 15: "9 Body corporate (not mentioned above)", 16: "10 Others"}
SH_COL = {"equity_no_share": "Equity: number of shares", "equity_percent": "Equity: %", "pref_tot_no_share": "Preference: number of shares",
          "pref_percent": "Preference: %"}
SH_PART = {"a": "(a) Promoters", "b": "(b) Public / other than promoters"}
COLS = {  # raw column names in repeating tables
    "numberequity_authorizedcapital": "Number of shares: authorised", "numberequity_issuedcapital": "Number of shares: issued",
    "numberequity_subscribed_capital": "Number of shares: subscribed", "numberequity_paidupcapital": "Number of shares: paid-up",
    "nominalvalue_authorizedcapital": "Nominal value per share (Rs): authorised", "nominalvalue_issuedcapital": "Nominal value per share (Rs): issued",
    "nominalvalue_subscribedcapital": "Nominal value per share (Rs): subscribed", "nominalvalue_paidupcapital": "Nominal value per share (Rs): paid-up",
    "tot_amt_authorizedcapital": "Total amount (Rs): authorised", "tot_amt_issuedcapital": "Total amount (Rs): issued",
    "tot_amt_subscribed_capital": "Total amount (Rs): subscribed", "tot_amt_paidupcapital": "Total amount (Rs): paid-up",
    "principal_mainactivity_code": "Main activity group code", "business_activitycode": "Business activity code",
    "Principal_turnover": "% of turnover of the company",
}


def _shareholding(f):
    """(part, label) for a shareholding pattern box, or None."""
    m = re.fullmatch(r"(equity_no_share|equity_percent|pref_tot_no_share|pref_percent)_([ab])(?:_(\d+))?", f.get("name") or "")
    if not m:
        return None
    row = SH_ROWS.get(int(m.group(3))) if m.group(3) else "Total"
    return SH_PART[m.group(2)], f"{row or 'Row ' + m.group(3)} / {SH_COL[m.group(1)]}"


def _table_title(t):
    title, key = str(t.get("title") or ""), str(t.get("groupKey") or "")
    if "panel_2074267803_cop" in key:
        return "Signatories of the board's report"
    if "panel_2074267803-" in key:
        return "Signatories of the financial statements"
    first = [str(c.get("label") or "") for c in (t.get("rows") or [[]])[0]]
    if any(x.startswith("numberequity_") for x in first):
        return "Equity share capital"
    if any(x.startswith("numberpref") or x.startswith("numberpreference") for x in first):
        return "Preference share capital"
    if title == "auditorDetailsInnerPanel":
        return "Auditor details"
    if re.fullmatch(r"Row \d+", title) or not title:
        return "Repeating rows"
    title = re.sub(r"(?<=[a-z])(?=[A-Z])|_", " ", title)
    title = re.sub(r"\b(inner|panel)\b", " ", title, flags=re.I)
    title = re.sub(r"\s+", " ", title).strip()
    return title[:1].upper() + title[1:]


def _col_label(c):
    import mca
    lab = mca.clean_label(str(c.get("label") or ""))
    if lab in COLS:
        return COLS[lab]
    if " " not in lab and ("_" in lab or re.search(r"[a-z][A-Z]", lab)):  # an internal box name: put spaces in
        lab = re.sub(r"(?<=[a-z])(?=[A-Z])|_", " ", lab).strip()
        lab = lab[:1].upper() + lab[1:].lower()
    return "Date" if re.match(r"(text box|date picker)\s+please enter date", lab, re.I) else lab


def _mgt7a(f):
    n = f.get("name") or ""
    k = [re.sub(r"[^a-z0-9]", "", str(x).lower()) for x in f.get("section") or []]
    for test, title in MGT7A_SEC:
        if test(n, k):
            return title
    return f.get("group") or "Other details"


CSS = """<style>
.pv{margin-top:12px;border:1px solid #c9ced6;background:#fff;overflow-x:auto}
.pv .seg{background:#1d3c6e;color:#fff;font-weight:600;font-size:15px;padding:10px 14px}
.pv .part{background:#e8edf5;color:#1b1d21;font-weight:600;padding:8px 14px;border-top:1px solid #c9ced6;border-bottom:1px solid #c9ced6}
.pv .blk{padding:10px 14px 14px}
.pv .fld{display:grid;grid-template-columns:minmax(0,1fr) minmax(220px,340px);gap:6px 16px;align-items:center;padding:5px 0}
.pv .box{border:1px solid #9aa3b0;border-left:4px solid #5c6470;border-radius:2px;background:#f9fafb;padding:6px 8px;min-height:32px;overflow-wrap:anywhere}
.pv td .box{text-align:right;font-variant-numeric:tabular-nums;min-width:84px}
.pv td .box.t{text-align:left}
.pv table{width:100%;border-collapse:collapse}
.pv th{background:#f1f3f7;font-weight:600;text-align:right;padding:6px 8px;border:1px solid #c9ced6;font-size:13px}
.pv th:first-child{text-align:left}
.pv td{padding:4px 8px;border:1px solid #dfe3ea;vertical-align:middle}
.pv td:first-child{min-width:180px}
.pv-lg{display:flex;gap:16px;flex-wrap:wrap;align-items:center;margin:8px 0}
.pv-lg i{display:inline-block;width:12px;height:12px;border-radius:2px;margin-right:6px;vertical-align:-1px}
#pvnil:checked ~ .pv .nil{display:none}
</style>"""


def _nil(v):
    return (isinstance(v, (int, float)) and not isinstance(v, bool) and v == 0) or bool(re.fullmatch(r"-?0+(\.0+)?", str(v).strip()))


def _split(label):
    """('row label', 'column label or empty')."""
    if " / " not in label:
        return label.strip(), ""
    a, b = label.split(" / ", 1)
    return a.strip(), b.strip()


def _col(f, col, row):
    """The column a value sits in. Uninformative column text falls back to the period read from the field itself."""
    low = col.lower()
    if not col or low == "headeritem" or low in row.lower() or row.lower() in low or "reporting period" in low or low.startswith("figures"):
        import mca
        return PY if mca.period_of(f) == "PY" else CY
    return col


def _box(r, ui, text=False):
    v = r["value"]
    val = ui.money(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else ui.esc(v)
    if r.get("_nil_tick"):  # the form has a "Nil" tick box here: say what the tick means
        val = "Nil (box ticked)" if str(v).strip().lower() in ("yes", "true", "1") else "Not ticked: details to be entered"
    elif r.get("_tick"):
        val = "Ticked" if str(v).strip().lower() in ("yes", "true", "1") else "Not ticked"
    word, colour = SRC.get(r["category"], (r["category"], "#5c6470"))
    how = r.get("built") or r.get("picked") or ""
    tip = word + (f": {how}" if how and how != word else "")
    return (f"<div class=\"box{' t' if text else ''}\" style=\"border-left-color:{colour}\" title=\"{ui.esc(str(tip)[:300])}\">"
            f"{val if str(val).strip() else '&nbsp;'}</div>")


def _part(items, ui):
    """items: [(schema field, chain row)] of one part, in form order -> html."""
    runs = []  # [row label, [(column, field, row)]]
    for f, r in items:
        row, col = _split(f["label"])
        col = _col(f, col, row) if " / " in f["label"] or re.search(r"reporting period", f["label"], re.I) else ""
        if re.search(r"^figures (as at the end of|for the period)", f["label"], re.I):  # the period dates above a statement
            row, col = "Period", (PY if "previous" in f["label"].lower() else CY)
        if runs and runs[-1][0] == row and col and all(c != col for c, _, _ in runs[-1][1]):
            runs[-1][1].append((col, f, r))
        else:
            runs.append([row, [(col, f, r)]])
    out, i = [], 0
    while i < len(runs):
        if runs[i][1][0][0]:  # a stretch of rows with columns: one table
            j, cols = i, []
            while j < len(runs) and runs[j][1][0][0]:
                for c, _, _ in runs[j][1]:
                    if c not in cols:
                        cols.append(c)
                j += 1
            if len(cols) > 6:  # too wide to be one table (mixed headers): fall back to rows with their own column names
                cols = None
            body = []
            for row, cells in runs[i:j]:
                nil = all(_nil(r["value"]) for _, _, r in cells)
                if cols:
                    by = {c: r for c, _, r in cells}
                    tds = "".join(f"<td>{_box(by[c], ui) if c in by else ''}</td>" for c in cols)
                else:
                    tds = "<td>" + "".join(f"<div class=mut>{ui.esc(c)}</div>{_box(r, ui)}" for c, _, r in cells) + "</td>"
                body.append(f"<tr{' class=nil' if nil else ''}><td>{ui.esc(row[:160])}</td>{tds}</tr>")
            head = "<tr><th>Particulars</th>" + ("<th>Value</th>" if cols == [CY] else "".join(f"<th>{ui.esc(c)}</th>" for c in cols) if cols else "<th>Values</th>") + "</tr>"
            out.append(f"<table>{head}{''.join(body)}</table>")
            i = j
        else:
            row, cells = runs[i]
            _, f, r = cells[0]
            out.append(f"<div class=\"fld{' nil' if _nil(r['value']) else ''}\"><div>{ui.esc(f['label'][:200])}</div>"
                       f"{_box(r, ui, text=not isinstance(r['value'], (int, float)))}</div>")
            i += 1
    return "".join(out)


def form_html(folder, slug, ui):
    import mca
    rows = ff_audit.chain(folder, slug)["rows"]
    sc = {f["code"]: f for f in mca.schema(slug)["fields"]}
    blocks = []  # [segment, part, [(f, r)]]
    for r in rows:
        f = sc.get(r["code"]) or {"label": mca.clean_label(r["label"]), "segment": "", "group": r.get("section") or "Other details", "name": ""}
        f = dict(f, label=NICE.get(f.get("name") or "") or mca.clean_label(f.get("label") or r["label"]))
        if slug == "mgt7a":
            f["segment"], f["group"] = _mgt7a(f), ""
            sh = _shareholding(f)
            if sh:
                f["segment"], f["group"], f["label"] = "VI Shareholding pattern", sh[0], sh[1]
            elif f.get("name") in ("tot_shareholers_vi_a",):
                f["group"] = SH_PART["a"]
            elif f.get("name") in ("Total_Other_Prometers", "Total_Promoters_public_Share"):
                f["group"] = SH_PART["b"]
        r = dict(r, _nil_tick=(f.get("name") in NIL_TICK), _tick=(f.get("type") == "checkbox"))
        k = (f.get("segment") or "", f.get("group") if f.get("segment") else (f.get("group") or "Other details"))
        if blocks and (blocks[-1][0], blocks[-1][1]) == k:
            blocks[-1][2].append((f, r))
        else:
            blocks.append([k[0], k[1], [(f, r)]])
    html, last = [], None
    for seg, part, items in blocks:
        if seg and seg != last:
            html.append(f"<div class=seg>{ui.esc(seg)}</div>")
        last = seg or last
        only_nil = all(_nil(r["value"]) for _, r in items)
        bar = f"<div class=part>{ui.esc(part)}</div>" if part and part != seg else ""
        html.append(f"<div class=\"{'nil' if only_nil and bar else ''}\">{bar}<div class=blk>{_part(items, ui)}</div></div>")
    nils = sum(1 for r in rows if _nil(r["value"]))
    # Repeating tables (share capital classes, directors, auditors ...): the rows the tool adds, as on the form.
    extra = 0
    try:
        tables = [t for t in mca.make_plan(app.inputs_path(folder), slug).get("tables") or [] if t.get("rows")]
    except Exception:  # noqa: BLE001
        tables = []
    if tables:
        html.append("<div class=seg>Tables on the form: rows Form Filler adds</div>")
    for t in tables:
        cols = []
        for row in t["rows"]:
            for c in row:
                lab = _col_label(c)
                if lab not in cols:
                    cols.append(lab)
        body = ""
        for i, row in enumerate(t["rows"], 1):
            by = {_col_label(c): c for c in row}
            body += f"<tr><td>Row {i}</td>" + "".join(
                f"<td><div class=\"box t\">{ui.esc(str(by[c].get('display', by[c].get('value', ''))) if c in by else '') or '&nbsp;'}</div></td>" for c in cols) + "</tr>"
        extra += sum(len(row) for row in t["rows"])
        if len(cols) > 5:  # too wide to read across: one line per column, one value column per row
            cell = lambda row, c: next((x for x in row if _col_label(x) == c), None)  # noqa: E731
            val = lambda x: (ui.esc(str(x.get("display", x.get("value", "")))) if x else "") or "&nbsp;"  # noqa: E731
            body = "".join(f"<tr><td>{ui.esc(c[:80])}</td>" + "".join(f"<td><div class=\"box t\">{val(cell(row, c))}</div></td>" for row in t["rows"]) + "</tr>"
                           for c in cols)
            head = "<tr><th>Particulars</th>" + "".join(f"<th style=\"text-align:left\">Row {i}</th>" for i in range(1, len(t["rows"]) + 1)) + "</tr>"
            html.append(f"<div class=part>{ui.esc(_table_title(t))}</div><div class=blk><table>{head}{body}</table></div>")
            continue
        head = "<tr><th>&nbsp;</th>" + "".join(f"<th style=\"text-align:left\">{ui.esc(c[:60])}</th>" for c in cols) + "</tr>"
        html.append(f"<div class=part>{ui.esc(_table_title(t))}</div><div class=blk><table>{head}{body}</table></div>")
    return "".join(html), len(rows) + extra, nils


def render(folder, ui):
    if not app.inputs_path(folder).exists():
        return "<p class=mut>The form values are prepared after Get data. Nothing to preview yet.</p>"
    try:
        app.refresh_questions(folder)  # rules changed since the values were prepared: rebuild first, saved answers are kept
    except Exception:  # noqa: BLE001
        pass
    forms = [s for s in (app.load(folder).get("forms") or []) if s in app.SMART]
    legend = "".join(f"<span><i style=\"background:{c}\"></i>{w}</span>" for w, c in SRC.values())
    radios = "".join(f"<input type=radio name=pvf id=pvf{n} {'checked' if n == 0 else ''} style=\"position:absolute;opacity:0;pointer-events:none\">"
                     for n in range(len(forms)))
    tabs = "".join(f"<label for=pvf{n} class=btn tabindex=0>{ui.FORM_LABEL.get(s_, s_)}</label>" for n, s_ in enumerate(forms))
    pick = "".join(f"#pvf{n}:checked ~ .pv.pvf{n}{{display:block}}#pvf{n}:checked ~ .pvtabs label[for=pvf{n}]{{background:#1b1d21;color:#fff;border-color:#1b1d21}}"
                   for n in range(len(forms)))
    out = [CSS, f"<style>.pv[class*=pvf]{{display:none}}{pick}"
           ".g12:has(.pv-root)>.s5{display:none}.g12:has(.pv-root)>.s7{grid-column:1/-1}</style>"
           "<div class=pv-root><div class=h>What will be typed on MCA, laid out as on the form</div>"
           "<p>Read-only. To change a value, correct its source: the mapping, an answer on Inputs for the forms, or the document it was read from. "
           "Fields the portal fills by itself (company name, auditor details from the ADT-1 SRN) are not listed.</p>"
           f"{radios}<div class=\"pvtabs row\" style=\"gap:8px;margin:12px 0\">{tabs}</div>"
           f"<div class=pv-lg><span class=mut>Colour on each box shows the source (hover for detail):</span>{legend}</div>"
           "<input type=checkbox id=pvnil style=\"margin-right:6px\"><label for=pvnil>Hide lines that are 0 in every column</label>"]
    for n, slug in enumerate(forms):
        try:
            body, cnt, nils = form_html(folder, slug, ui)
        except Exception as e:  # noqa: BLE001
            out.append(f"<div class=\"pv pvf{n}\"><div class=seg>{ui.FORM_LABEL.get(slug, slug)}</div><div class=blk>Could not read the form values ({ui.esc(str(e))}).</div></div>")
            continue
        out.append(f"<div class=\"pv pvf{n}\"><div class=seg style=\"background:#102a43\">Form {ui.FORM_LABEL.get(slug, slug)}: {cnt} fields, {nils} of them 0</div>{body}</div>")
    out.append("</div>")
    return "".join(out)
