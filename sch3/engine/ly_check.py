"""Tie the previous-year column of the new workbook to last year's signed Schedule III Excel and to last year's
filed AOC-4 PDF. Both are matched by amount, so the layout of last year's files does not matter."""
import re
import openpyxl


def _num(v):
    if isinstance(v, bool): return None
    if isinstance(v, (int, float)): return float(v)
    if isinstance(v, str):
        s = v.strip().replace(",", "")
        neg = s.startswith("(") and s.endswith(")")
        s = s.strip("()").strip()
        if re.fullmatch(r"-?\d+(\.\d+)?", s):
            return -float(s) if neg else float(s)
    return None


def built_lines(xlsx):
    """(sheet, label, CY, PY) for every visible BS / PL row with a value in the built workbook."""
    wb = openpyxl.load_workbook(xlsx, data_only=True)
    out = []
    for sn in ("BS", "PL"):
        ws = wb[sn]
        for i, row in enumerate(ws.iter_rows(values_only=True), 1):
            if ws.row_dimensions[i].hidden or not isinstance(row[0], str): continue
            nums = [c for c in row[1:6] if isinstance(c, (int, float)) and not isinstance(c, bool)]
            if len(nums) >= 2 and not (isinstance(row[1], (int, float)) and len(nums) == 2 and False):
                cy, py = nums[-2], nums[-1]
                if abs(cy) > 0.004 or abs(py) > 0.004:
                    out.append((sn, row[0].strip(), cy, py))
    return out


def _match(target, pool, tol):
    return any(abs(abs(target) - abs(p)) <= tol for p in pool)


def tie_ly_excel(built_xlsx, ly_xlsx, divisor=1):
    """Every PY figure in the new workbook should appear somewhere in last year's signed Excel (as its CY figure)."""
    wb = openpyxl.load_workbook(ly_xlsx, data_only=True)
    pool, text = [], []
    for ws in wb.worksheets:
        for row in ws.iter_rows(values_only=True):
            for c in row:
                n = _num(c)
                if n is not None and abs(n) >= 1: pool.append(n)
                elif isinstance(c, str): text.append(c.lower())
    blob = " ".join(text)
    unit = "'00s" if re.search(r"'00|in hundreds", blob) else "lakhs" if "lakh" in blob else \
        "'000s" if re.search(r"'000|thousand", blob) else "rupees"
    factor = {"'00s": 100, "lakhs": 100000, "'000s": 1000}.get(unit, 1)
    rows = []
    for sn, lbl, cy, py in built_lines(built_xlsx):
        rs = py * divisor
        if abs(rs) < 0.5: continue
        ok = any(abs(abs(p) * f - abs(rs)) <= max(1.0, f * 0.51) for p in pool for f in {factor, 1})
        rows.append({"statement": sn, "line": lbl, "py": py, "found": ok})
    note = "" if factor == divisor else f"Last year's accounts are in {unit}; this workbook uses divisor {divisor:g}. Set the rounding divisor to {factor} in Setup to match last year's presentation."
    return {"unit_in_ly": unit, "note": note, "rows": rows, "matched": sum(r["found"] for r in rows), "total": len(rows)}


def aoc4_fields(pdf_path):
    """Leaf fields of an MCA e-form (XFA) or AcroForm PDF: {field name: value}."""
    from pypdf import PdfReader
    rd = PdfReader(pdf_path)
    fields = {}
    try:
        xfa = rd.trailer["/Root"]["/AcroForm"].get("/XFA")
    except Exception:
        xfa = None
    if xfa is not None:
        parts = xfa.get_object() if hasattr(xfa, "get_object") else xfa
        if isinstance(parts, list):
            for k in range(0, len(parts) - 1, 2):
                if str(parts[k]) == "datasets":
                    xml = parts[k + 1].get_object().get_data().decode("utf-8", "replace")
                    for m in re.finditer(r"<([A-Za-z_][\w.\-]*)(?:\s[^>]*)?>([^<]+)</\1>", xml):
                        v = m.group(2).strip()
                        if v: fields.setdefault(m.group(1), v)
    if not fields:
        for k, f in (rd.get_fields() or {}).items():
            v = f.get("/V")
            if v not in (None, ""): fields[k] = str(v)
    return fields


def tie_aoc4(built_xlsx, pdf_path, divisor=1):
    """Match last year's AOC-4 amounts (filed in rupees) to the PY column of the new workbook (in its unit)."""
    f = aoc4_fields(pdf_path)
    amounts = {k: _num(v) for k, v in f.items()}
    amounts = {k: v for k, v in amounts.items() if v is not None and abs(v) >= 1}
    pool = list(amounts.values())
    rows = []
    for sn, lbl, cy, py in built_lines(built_xlsx):
        if abs(py) < 0.5: continue
        rs = py * divisor
        hit = [k for k, v in amounts.items() if abs(abs(v) - abs(rs)) <= max(1.0, divisor)]
        rows.append({"statement": sn, "line": lbl, "py_rs": round(rs, 2), "aoc4_field": ", ".join(hit[:3]), "found": bool(hit)})
    text = {k: v for k, v in f.items() if k not in amounts}
    return {"fields": len(f), "rows": rows, "matched": sum(r["found"] for r in rows), "total": len(rows),
            "text_fields": dict(list(text.items())[:200])}
