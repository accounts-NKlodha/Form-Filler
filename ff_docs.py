"""Documents each client needs, with where they are stored. Staff upload them on Review financials > Documents.

    kind           stored in                                   read by
    ly_aoc4        client folder (name keeps 'AOC-4')          last-year tie-outs, carry-forward, local AI
    ly_mgt7        client folder (name keeps 'MGT-7A')         carry-forward, local AI
    ly_board       client folder, PDF                          local AI
    ly_auditor     client folder, PDF                          local AI
    ly_docx        financials/<FY>/last_year_docs/, Word       drafting this year's reports
    att_<element>  mca_attachments/<element>/                  the filing queue (MCA attachment)
    other          client folder, PDF                          local AI
"""
import re
from datetime import datetime
from pathlib import Path

import app
import ff_audit
import ff_fin
import filing_queue
import lastyear

MAX = 60 * 1024 * 1024


def _safe(name):
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", Path(name).name).strip() or "upload"


def _root_pdfs(folder, pat):
    return [p for p in sorted(Path(folder).glob("*.pdf")) if re.search(pat, p.name, re.I)]


def checklist(folder):
    """[{kind, title, why, need ('must'|'useful'), files [Path], multi, accept}] for this client."""
    folder = Path(folder)
    forms = [s for s in (app.load(folder).get("forms") or []) if s in app.SMART]
    rows = []

    def add(kind, title, why, need, files, multi=False, accept=".pdf"):
        rows.append({"kind": kind, "title": title, "why": why, "need": need, "files": [f for f in files if f],
                     "multi": multi, "accept": accept})

    # this year: MCA attachments the filing queue uploads
    for s in forms:
        have = filing_queue.attachment_files(folder, s)
        for el, title, must, _ in filing_queue.ATTACH.get(s, []):
            add(f"att_{el}", f"{app.FORM_LABEL.get(s, s)}: {title}", "Uploaded to MCA by the filing queue",
                "must" if must else "useful", [have.get(el)], accept=".pdf,.jpg,.jpeg,.png")
    # last year
    add("ly_aoc4", "Last year's filed AOC-4 (PDF from MCA)",
        "Last year's figures are tied out against it; signatories and auditor carry forward; the local AI reads it",
        "must" if "aoc4" in forms else "useful", [lastyear.find_last_aoc4(folder)])
    add("ly_mgt7", "Last year's filed MGT-7 / MGT-7A (PDF from MCA)",
        "Shareholding, directors and meetings carry forward; the local AI reads it",
        "must" if "mgt7a" in forms else "useful", [lastyear.find_last_mgt7a(folder)] + _root_pdfs(folder, r"mgt[-_ ]?7(?!a)"))
    add("ly_board", "Last year's Board's report (PDF)", "The local AI reads it for dates, meetings and directors",
        "useful", _root_pdfs(folder, r"board"), multi=True)
    add("ly_auditor", "Last year's Auditor's report and CARO (PDF)", "The local AI reads it for the auditor's details",
        "useful", _root_pdfs(folder, r"audit"), multi=True)
    d = ff_fin.ly_docs_dir(folder)
    add("ly_docx", "Last year's signed Word files: Board's report, Auditor's report, notice",
        "This year's reports are drafted from them", "useful",
        sorted(p for p in d.glob("*.doc*") if p.is_file()), multi=True, accept=".docx,.doc")
    known = {f for r in rows for f in r["files"]}
    add("other", "Other supporting documents (PDF)", "Anything else the local AI should read: minutes, registers, letters",
        "useful", [p for p in sorted(folder.glob("*.pdf")) if p not in known], multi=True)
    return rows


def missing(folder):
    return [r for r in checklist(folder) if r["need"] == "must" and not r["files"]]


def upload(folder, kind, filename, data, user=""):
    folder = Path(folder)
    if len(data) > MAX:
        raise ValueError("file is larger than 60 MB")
    filename = _safe(filename)
    ext = Path(filename).suffix.lower()
    label = next((r["title"] for r in checklist(folder) if r["kind"] == kind), kind)
    if kind.startswith("att_"):
        dest = filing_queue.store_attachment(folder, kind[4:], filename, data)
    elif kind == "ly_aoc4":
        dest = folder / app.upload(folder.name, "ly_aoc4", filename, data)["saved"]
    elif kind == "ly_mgt7":
        if ext != ".pdf":
            raise ValueError("expected a PDF")
        if not re.search(r"mgt[-_ ]?7", filename, re.I):
            filename = f"Last year MGT-7A - {filename}"
        dest = folder / filename
        if dest.exists():
            app._move_aside(folder, dest)
        dest.write_bytes(data)
    elif kind in ("ly_board", "ly_auditor", "other"):
        if ext != ".pdf":
            raise ValueError("expected a PDF")
        tag = {"ly_board": ("board", "Last year Board's report - "), "ly_auditor": ("audit", "Last year Auditor's report - ")}.get(kind)
        if tag and not re.search(tag[0], filename, re.I):
            filename = tag[1] + filename
        if kind == "other" and re.search(r"aoc[-_ ]?4|mgt[-_ ]?7", filename, re.I):
            raise ValueError("this looks like a filed form: use the last year's AOC-4 / MGT-7 row instead")
        dest = folder / filename
        if dest.exists():
            app._move_aside(folder, dest)
        dest.write_bytes(data)
    elif kind == "ly_docx":
        if ext not in (".docx", ".doc"):
            raise ValueError("expected a Word file (.docx)")
        dest = ff_fin.ly_docs_dir(folder) / filename
        if dest.exists():
            app._move_aside(folder, dest)
        dest.write_bytes(data)
    else:
        raise ValueError("unknown document")
    ff_audit.event(folder, "document", f"Uploaded {dest.name} ({label})", by=user or "staff", file=dest.name, doc=kind)
    return dest


def remove(folder, kind, fname, user=""):
    """Move one uploaded file aside to _replaced/ (never deleted)."""
    folder = Path(folder)
    row = next((r for r in checklist(folder) if r["kind"] == kind), None)
    p = next((f for f in (row["files"] if row else []) if f.name == fname), None)
    if not p:
        raise ValueError("file not found")
    app._move_aside(folder, p)
    ff_audit.event(folder, "document", f"Removed {fname} (kept in _replaced)", by=user or "staff", file=fname, doc=kind)


def stamp(p):
    try:
        return datetime.fromtimestamp(Path(p).stat().st_mtime).strftime("%d %b %Y")
    except OSError:
        return ""
