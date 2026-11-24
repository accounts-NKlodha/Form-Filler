"""Fill this year's copies of the MCA Excel attachments (board meetings, members' meetings,
shareholder list) from last year's copies in the client folder. Staff still attach them on the
portal by hand; this only saves retyping. Macros and the MCA MetaInfo sheet are kept as is.
"""
import re
import shutil
from datetime import datetime
from pathlib import Path

import openpyxl


TEMPLATES = Path(__file__).resolve().parent / "Samples" / "MGT 7A"  # MCA's blank formats, kept beside the app


def _find(folder, pat, shared=True):
    """Last year's copy in the client folder, else (shared) MCA's format from the app's Samples folder.
    A shared file may hold another company's rows: use it only where every row is rewritten."""
    for d in [Path(folder)] + ([TEMPLATES] if shared else []):
        for p in sorted(d.glob("*.xlsm")) if d.exists() else []:
            if re.search(pat, p.name, re.I) and "this year" not in p.name.lower():
                return p
    return None


def _rewrite(src, out, sheet, first_row, rows):
    shutil.copyfile(src, out)
    wb = openpyxl.load_workbook(out, keep_vba=True)
    ws = wb[sheet] if sheet in wb.sheetnames else wb.worksheets[1]
    for r in range(first_row, max(ws.max_row, first_row) + 1):
        for c in range(1, ws.max_column + 1):
            ws.cell(r, c).value = None
    for i, row in enumerate(rows):
        for c, v in enumerate(row, 1):
            ws.cell(first_row + i, c).value = v
    wb.save(out)


def make(folder, facts, answers, fy_label):
    """Returns a list of (file name, what it is) written to <folder>/attachments."""
    folder = Path(folder)
    out_dir = folder / "attachments"
    made = []
    dirs = (facts or {}).get("directors") or []
    last_bm = (facts or {}).get("board_meetings") or []
    n_dirs = len(dirs) or int((last_bm[-1].get("directors") if last_bm else 0) or 0)  # no director list read: last year's board strength
    all_att = str(answers.get("all_attended") or "Yes").lower().startswith("y")

    bm_src = _find(folder, r"board\s*meeting")
    dates = [d.strip() for d in re.split(r"[,;\n]+", str(answers.get("board_meetings") or "")) if d.strip()]
    if bm_src and dates and n_dirs:
        out_dir.mkdir(exist_ok=True)
        out = out_dir / f"Board Meeting - {fy_label}.xlsm"
        rows = [[i, datetime.strptime(d, "%d/%m/%Y"), n_dirs, n_dirs if all_att else None, 100 if all_att else None]
                for i, d in enumerate(dates, 1)]
        _rewrite(bm_src, out, "Board Meeting", 3, rows)
        made.append((out.name, f"{len(rows)} board meetings" + ("" if all_att else ": enter attendance per meeting")))

    mm_src = _find(folder, r"meeting of members")
    # Members' meetings held DURING the year: the AGM of the previous year (its date is on last year's form),
    # not this year's AGM, which falls after the year end.
    agm = (facts or {}).get("agm_date") or answers.get("prev_agm_date")
    held = bool(agm)
    if mm_src and agm and held:
        out_dir.mkdir(exist_ok=True)
        out = out_dir / f"Meeting of members - {fy_label}.xlsm"
        last = ((facts or {}).get("member_meetings") or [{}])[0]
        entitled = last.get("entitled") or (facts or {}).get("n_holders_listed")
        _rewrite(mm_src, out, "Sheet1", 2, [["AGM", datetime.strptime(agm, "%d/%m/%Y"), entitled,
                                             entitled if all_att else None, 100 if all_att else None]])
        made.append((out.name, f"last year's AGM, held {agm}"))

    sh_src = _find(folder, r"shareholder", shared=False)  # never another company's list
    if sh_src and not str(answers.get("holders_changed") or "No").lower().startswith("y"):
        out_dir.mkdir(exist_ok=True)
        out = out_dir / f"Shareholder list - {fy_label}.xlsm"
        shutil.copyfile(sh_src, out)
        made.append((out.name, "same shareholders as last year (no change answered)"))
    return made
