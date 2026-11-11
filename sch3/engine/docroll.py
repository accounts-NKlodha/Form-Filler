"""Roll last year's Word / Excel documents (notice, board's report, auditor's report, SAP, lists) forward.
Generic helpers shared by the client document scripts: text replacement across runs (keeps formatting),
every paragraph including tables, simultaneous year roll (2024-25 -> 2025-26 without chaining)."""
import copy, re
from docx.enum.text import WD_COLOR_INDEX


def inr(x, dec=0):
    neg = x < 0; s = f"{abs(x):.{dec}f}"; i, _, d = s.partition(".")
    if len(i) > 3:
        h, t = i[:-3], i[-3:]; i = ",".join([h[max(0, k - 2):k] for k in range(len(h), 0, -2)][::-1]) + "," + t
    return ("-" if neg and float(s) else "") + i + ("." + d if d else "")


def paras(doc):
    """Every paragraph: body, table cells (nested), headers and footers; each merged cell once."""
    def walk(container):
        for p in container.paragraphs: yield p
        for t in getattr(container, "tables", []):
            seen = set()
            for row in t.rows:
                for c in row.cells:
                    if c._tc in seen: continue
                    seen.add(c._tc); yield from walk(c)
    yield from walk(doc)
    for s in doc.sections:
        for part in (s.header, s.footer): yield from walk(part)


def replace(p, old, new, hl=False):
    """Replace text that may span several runs, keeping the first run's formatting. Returns hits."""
    n = 0
    while True:
        runs = p.runs; text = "".join(r.text for r in runs); i = text.find(old)
        if i < 0 or not old: return n
        pos = 0; hit = []
        for k, r in enumerate(runs):
            a, b = pos, pos + len(r.text); pos = b
            if b > i and a < i + len(old): hit.append((k, a))
        (k0, a0), (k1, a1) = hit[0], hit[-1]
        tail = runs[k1].text[i + len(old) - a1:]
        runs[k0].text = runs[k0].text[:i - a0] + new + (tail if k0 == k1 else "")
        for k, _ in hit[1:]: runs[k].text = ""
        if k1 != k0: runs[k1].text = tail
        if hl: runs[k0].font.highlight_color = WD_COLOR_INDEX.YELLOW
        n += 1
        if old in new: return n


def replace_all(doc, pairs, hl=False):
    """Apply (old, new) pairs simultaneously to every paragraph (tokens stop 2024-25 -> 2025-26 -> 2026-27)."""
    tok = [(o, f"\u27e6{k}\u27e7", n) for k, (o, n) in enumerate(pairs)]
    for p in paras(doc):
        if not any(o in p.text for o, _, _ in tok): continue
        for o, t, _ in tok: replace(p, o, t)
        for _, t, n in tok: replace(p, t, n, hl)


def year_pairs(fye):
    """Old -> new strings for rolling a financial year forward by one (fye = new year-end, e.g. 2026)."""
    a, b, c = fye - 2, fye - 1, fye
    out = []
    for y0, y1 in ((b, c), (a, b)):          # newest first so the token pass handles both
        p0, p1 = y0 - 1, y1 - 1
        out += [(f"{p0}-{y0}", f"{p1}-{y1}"), (f"{p0}-{str(y0)[2:]}", f"{p1}-{str(y1)[2:]}"),
                (f"{p0}-{str(y0)[2:]}", f"{p1}-{str(y1)[2:]}"), (f"31st March {y0}", f"31st March {y1}"),
                (f"31st March, {y0}", f"31st March, {y1}"), (f"31st march, {y0}", f"31st March, {y1}"),
                (f"31/03/{y0}", f"31/03/{y1}"), (f"31.03.{y0}", f"31.03.{y1}"), (f"31-03-{y0}", f"31-03-{y1}")]
    seen, res = set(), []
    for o, n in out:
        if o not in seen: seen.add(o); res.append((o, n))
    return res


def set_text(p, text, hl=False):
    if not p.runs: p.add_run("")
    p.runs[0].text = text
    for r in p.runs[1:]: r.text = ""
    if hl:
        for r in p.runs: r.font.highlight_color = WD_COLOR_INDEX.YELLOW


def cell(c, text, hl=False):
    ps = c.paragraphs; set_text(ps[0], text, hl)
    for p in ps[1:]: set_text(p, "")


def highlight(p):
    for r in p.runs: r.font.highlight_color = WD_COLOR_INDEX.YELLOW


def delete(p): p._element.getparent().remove(p._element)


def find(doc, prefix, start=0):
    ps = doc.paragraphs
    return next((i for i in range(start, len(ps)) if ps[i].text.strip().startswith(prefix)), None)


def clone_after(p, text):
    new = copy.deepcopy(p._element); p._element.addnext(new)
    from docx.text.paragraph import Paragraph
    q = Paragraph(new, p._parent); set_text(q, text); return q


def wb_values(xlsx):
    """Setup labels, and the BS / PL / Notes figures by row label, from a cached Schedule III workbook."""
    import openpyxl
    wb = openpyxl.load_workbook(xlsx, data_only=True)
    st = {str(r[0]).strip(): r[1] for r in wb["Setup"].iter_rows(max_col=2, values_only=True) if r[0]}
    return wb, st
