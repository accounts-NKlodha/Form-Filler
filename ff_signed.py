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


# ---------------------------------------------------------------- Reports and meetings tab: attachments for MCA

BOX_KINDS = ("signed", "att_xl_board", "att_xl_members", "att_mgt7a_shareholders", "att_mgt7a_Photograph")
_JS = """<script>(()=>{let busy=0,msgs=[];const c=document.querySelector('.doc')?.dataset.c||'';
const done=()=>{if(busy)return;location.href=location.pathname+'?c='+encodeURIComponent(c)+'&tab=reports&msg='+encodeURIComponent(msgs.join('. '))};
async function send(d,files){if(!files.length)return;const note=d.querySelector('.note');let who='';
try{who=encodeURIComponent((localStorage.getItem('ff_user')||'').trim())}catch(e){}
busy++;window.ffBusy=true;for(const fi of files){note.textContent='Uploading '+fi.name+' ...';
try{const r=await fetch('/ff/doc/upload?c='+encodeURIComponent(d.dataset.c)+'&kind='+d.dataset.k+'&name='+encodeURIComponent(fi.name)+'&user='+who,{method:'POST',body:fi});
const j=await r.json();msgs.push(j.error?('Not saved '+fi.name+': '+j.error):('Saved '+j.saved));note.textContent=j.error?('Not saved: '+j.error):('Saved '+j.saved)}
catch(e){msgs.push('Not saved '+fi.name+': the server did not answer');note.textContent='Not saved: the server did not answer'}}
busy--;window.ffBusy=busy>0;done()}
for(const d of document.querySelectorAll('.doc')){const inp=d.querySelector('input[type=file]');
inp.addEventListener('change',()=>send(d,[...inp.files]));
d.addEventListener('dragover',e=>{e.preventDefault();d.classList.add('over')});d.addEventListener('dragleave',()=>d.classList.remove('over'));
d.addEventListener('drop',e=>{e.preventDefault();d.classList.remove('over');const f=[...e.dataTransfer.files];send(d,inp.multiple?f:f.slice(0,1))})}})()</script>"""


def box(folder, ui):
    """Every file the filing queue attaches on MCA, with where it stands and an upload, in the order staff work."""
    import ff_docs
    import filing_queue
    folder = Path(folder)
    st = state(folder)
    try:
        path, note = attachment(folder, folder / filing_queue.ATTACH_DIR / SLOT)
    except Exception as e:  # noqa: BLE001
        path, note = None, f"signed PDF could not be read: {str(e)[:80]}"
    rows = {r["kind"]: r for r in ff_docs.checklist(folder)}
    out = []
    for k in BOX_KINDS:
        r = rows.get(k)
        if not r:
            continue
        if k == "signed":
            status = ui.tag("Ready to attach on MCA", "good") if path else ui.tag("Last page will stay pending", "need")
            why = "Financial statements, Auditor's report, Board's report and AGM notice, signed. One PDF is attached as it is; several are joined in that order. " + note
        else:
            status = ui.tag("Ready", "good") if r["files"] else ui.tag("Not there yet", "need")
            why = r["why"]
        files = "".join(f"<div class=fl><span>{ui.esc(f.name)}</span><span class=mut>{ff_docs.stamp(f)}</span></div>" for f in r["files"])
        btn = "Add files" if r["multi"] and r["files"] else "Replace" if r["files"] else "Choose files" if r["multi"] else "Choose file"
        out.append(f"<div class=doc data-c=\"{ui.esc(folder.name)}\" data-k=\"{k}\"><div><b>{ui.esc(r['title'])}</b>"
                   f"<div class=mut>{ui.esc(why)}</div>{files}<div class=\"mut note\" role=status></div></div>"
                   f"<div class=side>{status}<label class=\"btn sm pick\">{btn}<input type=file accept=\"{r['accept']}\" "
                   f"{'multiple' if r['multi'] else ''} aria-label=\"{ui.esc(r['title'])}\"></label></div></div>")
    bad = "".join(f"<li>{ui.esc(n)}: an MCA form, left out</li>" for n in st["rejected"])
    return ("<div class=sec>Attachments for MCA</div><p>The filing queue attaches these on the portal. Drop a file on a row or choose it. "
            f"Signed PDFs can also be saved straight into <code>{ui.esc(st['dir'])}</code>.</p>"
            + "".join(out) + (f"<ul>{bad}</ul>" if bad else "") + _JS)
