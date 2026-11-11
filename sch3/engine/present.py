"""Print presentation for BS / PL / Notes: title block, table lines, signature block, paragraphs, page setup."""
import math
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter as CL

F = "Arial"
NAVY = "1F3864"
f_co = Font(name=F, size=14, bold=True, color=NAVY)
f_small = Font(name=F, size=9, color="404040")
f_stmt = Font(name=F, size=11, bold=True, color=NAVY)
f_unit = Font(name=F, size=9, italic=True, color="404040")
f_hdr = Font(name=F, size=10, bold=True, color="FFFFFF")
f_base = Font(name=F, size=10)
f_b = Font(name=F, size=10, bold=True)
f_note = Font(name=F, size=10, bold=True, color=NAVY)
f_para = Font(name=F, size=9.5)
f_foot = Font(name=F, size=8.5, italic=True, color="404040")
fill_hdr = PatternFill("solid", fgColor=NAVY)
fill_sec = PatternFill("solid", fgColor="E8EDF5")
fill_tot = PatternFill("solid", fgColor="F3F5F9")
fill_band = PatternFill("solid", fgColor="D6DFEE")
line = Side(style="thin", color="8C9BB5")
dark = Side(style="medium", color=NAVY)
dbl = Side(style="double", color="000000")
none = Side(style=None)


def _merge_border(cell, left=None, right=None, top=None, bottom=None):
    b = cell.border
    cell.border = Border(left=left or b.left, right=right or b.right, top=top or b.top, bottom=bottom or b.bottom)


def title_block(ws, last_col, co, cin, addr, stmt, unit):
    """Rows 1-5: company, CIN, registered office, statement title, amount label. Formulas point at Setup."""
    L = CL(last_col)
    rows = [(f"=UPPER({co})", f_co, 24), (f'="CIN: "&{cin}', f_small, 14),
            (f'=IF({addr}="","","Registered office: "&{addr})', f_small, 14), (stmt, f_stmt, 20)]
    for i, (v, font, h) in enumerate(rows, 1):
        ws.merge_cells(f"A{i}:{L}{i}")
        c = ws.cell(row=i, column=1, value=v); c.font = font
        c.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[i].height = h
    ws.merge_cells(f"A5:{L}5")
    c = ws.cell(row=5, column=1, value=f'="("&{unit}&")"'); c.font = f_unit
    c.alignment = Alignment(horizontal="right")
    for col in range(1, last_col + 1):
        _merge_border(ws.cell(row=4, column=col), bottom=dark)


def header_row(ws, row, c0, c1, height=30):
    for col in range(c0, c1 + 1):
        c = ws.cell(row=row, column=col)
        c.font = f_hdr; c.fill = fill_hdr
        c.alignment = Alignment(horizontal="center" if col > c0 else "left", vertical="center", wrap_text=True, indent=0 if col > c0 else 1)
    ws.row_dimensions[row].height = height


def frame(ws, r0, r1, c0, c1, inner=True, skip_inner_rows=()):
    """Outer box and vertical column lines from r0 to r1."""
    for rr in range(r0, r1 + 1):
        for col in range(c0, c1 + 1):
            c = ws.cell(row=rr, column=col)
            left = dark if col == c0 else (line if inner and rr not in skip_inner_rows else None)
            right = dark if col == c1 else None
            top = dark if rr == r0 else None
            bottom = dark if rr == r1 else None
            _merge_border(c, left=left, right=right, top=top, bottom=bottom)


def style_row(ws, row, c0, c1, kind):
    """kind: section | sub | item | total | grand"""
    for col in range(c0, c1 + 1):
        c = ws.cell(row=row, column=col)
        if kind == "section":
            c.fill = fill_sec; c.font = Font(name=F, size=10, bold=True, color=NAVY)
        elif kind == "sub":
            c.font = f_b
        elif kind == "total":
            c.font = f_b
            if col > c0: _merge_border(c, top=line)
        elif kind == "grand":
            c.font = f_b; c.fill = fill_tot
            _merge_border(c, top=line, bottom=dbl)
        else:
            c.font = f_base


def sign_block(ws, r, inp, left_col, right_cols, co):
    """Auditor on the left, two directors on the right. Returns next free row."""
    a, (d1, d2) = left_col, right_cols
    def put(row, col, v, font=f_base, al="left"):
        c = ws.cell(row=row, column=col, value=v); c.font = font; c.alignment = Alignment(horizontal=al, wrap_text=False)
    put(r, a, "As per our report of even date attached")
    ws.merge_cells(start_row=r, start_column=d1, end_row=r, end_column=d2)
    put(r, d1, "For and on behalf of the Board of Directors", al="center")
    put(r + 1, a, f'="For "&{inp["Auditor firm name"]}', f_b)
    ws.merge_cells(start_row=r + 1, start_column=d1, end_row=r + 1, end_column=d2)
    put(r + 1, d1, f"={co}", f_b, "center")
    put(r + 2, a, "Chartered Accountants")
    put(r + 3, a, f'="Firm Registration No.: "&{inp["Auditor FRN"]}')
    s = r + 7
    put(s, a, f'={inp["Signing partner name"]}', f_b)
    put(s, d1, f'={inp["Signing director 1 name"]}', f_b, "center")
    put(s, d2, f'={inp["Signing director 2 name"]}', f_b, "center")
    put(s + 1, a, f'={inp["Partner designation (Proprietor or Partner)"]}')
    put(s + 1, d1, "Director", al="center"); put(s + 1, d2, "Director", al="center")
    put(s + 2, a, f'="Membership No.: "&{inp["Partner membership number"]}')
    put(s + 2, d1, f'="DIN: "&{inp["Signing director 1 DIN"]}', al="center")
    put(s + 2, d2, f'="DIN: "&{inp["Signing director 2 DIN"]}', al="center")
    put(s + 3, a, f'="UDIN: "&{inp["UDIN"]}')
    put(s + 4, a, f'="Place: "&{inp["Place of signing"]}')
    put(s + 4, d1, f'="Place: "&{inp["Place of signing"]}', al="center")
    k_aud, k_bm = "Date of auditor's report", "Date of board meeting approving board's report"
    put(s + 5, a, f'="Date: "&{inp[k_aud]}')
    put(s + 5, d1, f'="Date: "&{inp[k_bm]}', al="center")
    for col in (d1, d2):
        _merge_border(ws.cell(row=s - 1, column=col), bottom=Side(style="hair", color="808080"))
    _merge_border(ws.cell(row=s - 1, column=a), bottom=Side(style="hair", color="808080"))
    return s + 6


def para(ws, row, c0, c1, text, width_chars, font=f_para, bold=False, indent=0):
    """Merged, wrapped paragraph with an estimated row height."""
    ws.merge_cells(start_row=row, start_column=c0, end_row=row, end_column=c1)
    c = ws.cell(row=row, column=c0, value=text)
    c.font = Font(name=F, size=font.size, bold=bold, italic=font.italic, color=font.color)
    c.alignment = Alignment(wrap_text=True, vertical="top", horizontal="justify" if not bold else "left", indent=indent)
    n = len(text) if isinstance(text, str) and not text.startswith("=") else 120
    lines = max(1, math.ceil(n / max(20, (width_chars - 2 * indent) * 1.12)))
    ws.row_dimensions[row].height = max(14, 13.2 * lines + 2)


def page(ws, title_rows=None, landscape=False):
    ws.sheet_view.showGridLines = False
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.orientation = "landscape" if landscape else "portrait"
    ws.page_setup.fitToWidth = 1; ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_options.horizontalCentered = True
    m = ws.page_margins; m.left = m.right = 0.5; m.top = 0.55; m.bottom = 0.6; m.header = 0.25; m.footer = 0.3
    ws.oddFooter.left.text = "&8&\"Arial,Italic\"&A"
    ws.oddFooter.right.text = "&8&\"Arial\"Page &P of &N"
    if title_rows: ws.print_title_rows = title_rows
