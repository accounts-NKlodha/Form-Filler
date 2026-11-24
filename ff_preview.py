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
        f = dict(f, label=mca.clean_label(f.get("label") or r["label"]))
        k = (f.get("segment") or "", f.get("group") or "Other details")
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
        html.append(f"<div class=\"{'nil' if only_nil else ''}\"><div class=part>{ui.esc(part)}</div><div class=blk>{_part(items, ui)}</div></div>")
    nils = sum(1 for r in rows if _nil(r["value"]))
    return "".join(html), len(rows), nils


def render(folder, ui):
    if not app.inputs_path(folder).exists():
        return "<p class=mut>The form values are prepared after Get data. Nothing to preview yet.</p>"
    forms = [s for s in (app.load(folder).get("forms") or []) if s in app.SMART]
    legend = "".join(f"<span><i style=\"background:{c}\"></i>{w}</span>" for w, c in SRC.values())
    out = [CSS, "<div class=h>What will be typed on MCA, laid out as on the form</div>"
           "<p>Read-only. To change a value, correct its source: the mapping, an answer on Inputs for the forms, or the document it was read from. "
           "Fields the portal fills by itself (company name, auditor details from the ADT-1 SRN) are not listed.</p>"
           f"<div class=pv-lg><span class=mut>Colour on each box shows the source (hover for detail):</span>{legend}</div>"
           "<input type=checkbox id=pvnil style=\"margin-right:6px\"><label for=pvnil>Hide lines that are 0 in every column</label>"]
    for slug in forms:
        try:
            body, n, nils = form_html(folder, slug, ui)
        except Exception as e:  # noqa: BLE001
            out.append(f"<div class=pv><div class=seg>{ui.FORM_LABEL.get(slug, slug)}</div><div class=blk>Could not read the form values ({ui.esc(str(e))}).</div></div>")
            continue
        out.append(f"<div class=pv><div class=seg style=\"background:#102a43\">Form {ui.FORM_LABEL.get(slug, slug)}: {n} fields, {nils} of them 0</div>{body}</div>")
    return "".join(out)
