"""Signed documents: the folder a CA saves the signed set in, and the one PDF the queue attaches on MCA.

    clients/<client>/reports/   drafts the app makes (Board's report, Auditor's report, notice, lists)
    clients/<client>/signed/    signed PDFs, saved by the CA after signing (or uploaded on the Documents tab)

AOC-4 takes one PDF (financial statements with the auditor's and board's reports). One signed PDF is attached
as it is; several are joined in a fixed order. A PDF that is itself an MCA form is never attached.
"""
import re
from pathlib import Path

SIGNED = "signed"
SLOT = "aoc4_financialState"
MERGED = "Signed financial statements.pdf"
ORDER = [(r"financial|balance|schedule|accounts|\bfs\b", "Financial statements"), (r"audit|caro", "Auditor's report"),
         (r"board|director", "Board's report"), (r"notice|agm", "AGM notice")]
_FORM = re.compile(r"form\s*(no\.?)?\s*(aoc|mgt|adt)\s*-?\s*\d|pursuant to section 137|pursuant to sub-?section \(1\) of section 92", re.I)
_seen = {}


def signed_dir(folder):
    d = Path(folder) / SIGNED
    d.mkdir(parents=True, exist_ok=True)
    return d


def is_mca_form(path):
    """True when the PDF's first page is an MCA e-form (last year's filed AOC-4, MGT-7 ...)."""
    path = Path(path)
    key = (str(path), path.stat().st_mtime)
    if key not in _seen:
        text = ""
        try:
            import pdfplumber
            with pdfplumber.open(path) as pdf:
                text = (pdf.pages[0].extract_text() or "")[:1500] if pdf.pages else ""
        except Exception:  # noqa: BLE001  unreadable or scanned: not recognisably a form
            text = ""
        _seen[key] = bool(_FORM.search(text)) or bool(re.search(r"aoc[-_ ]?4|mgt[-_ ]?7", path.name, re.I))
    return _seen[key]


def _rank(p):
    for i, (pat, _) in enumerate(ORDER):
        if re.search(pat, p.name, re.I):
            return i
    return len(ORDER)


def signed_files(folder):
    """Signed PDFs in filing order, MCA forms left out."""
    d = Path(folder) / SIGNED
    if not d.exists():
        return []
    return sorted((p for p in d.glob("*.pdf") if p.is_file() and not is_mca_form(p)), key=lambda p: (_rank(p), p.name.lower()))


def rejected(folder):
    d = Path(folder) / SIGNED
    return sorted(p for p in d.glob("*.pdf") if p.is_file() and is_mca_form(p)) if d.exists() else []


def attachment(folder, slot_dir):
    """(path or None, note) for the AOC-4 financial statements attachment.
    slot_dir is mca_attachments/aoc4_financialState, where a joined file is written and a hand upload lives."""
    folder, slot_dir = Path(folder), Path(slot_dir)
    files = signed_files(folder)
    if len(files) == 1:
        return files[0], f"signed folder: {files[0].name}"
    if len(files) > 1:
        out = slot_dir / MERGED
        newest = max(p.stat().st_mtime for p in files)
        if not out.exists() or out.stat().st_mtime < newest:
            from pypdf import PdfWriter
            w = PdfWriter()
            for p in files:
                w.append(str(p))
            slot_dir.mkdir(parents=True, exist_ok=True)
            tmp = slot_dir / (MERGED + ".part")
            with open(tmp, "wb") as fh:
                w.write(fh)
            tmp.replace(out)
        return out, "signed folder, joined: " + ", ".join(p.name for p in files)
    old = sorted(p for p in slot_dir.glob("*") if p.is_file() and p.name != MERGED) if slot_dir.exists() else []
    if old:
        if old[-1].suffix.lower() == ".pdf" and is_mca_form(old[-1]):
            return None, f"{old[-1].name} is an MCA form, not the signed financial statements"
        return old[-1], f"uploaded by staff: {old[-1].name}"
    return None, "no signed PDF in the signed folder yet"


def state(folder):
    """For the screens: drafts made, signed files, what is still to come."""
    folder = Path(folder)
    rep = folder / "reports"
    drafts = sorted(p.name for p in rep.glob("*") if p.suffix.lower() in (".docx", ".xlsx", ".pdf")) if rep.exists() else []
    files = signed_files(folder)
    have = {ORDER[_rank(p)][1] for p in files if _rank(p) < len(ORDER)}
    return {"drafts": drafts, "signed": [p.name for p in files], "rejected": [p.name for p in rejected(folder)],
            "named": sorted(have), "dir": str(signed_dir(folder))}
