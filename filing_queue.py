"""Filing queue: many clients and forms, filled one after another until Submit.

    queue.json  {"jobs": [{id, client, slug, status, srn, note, updated}], "running", "current", "submit", "next_id"}

A job is one form for one client (AOC-4 or MGT-7A; ADT-1 has its own run on /adt1). While the queue
runs, /plan for that form returns the job's plan with the loop flags on: the extension fills a section,
clicks its Save, moves on with Next and uploads the attachments staff gave the app. On the last page it
outlines Submit and waits: staff click Submit, the extension reads the SRN and opens the next client's
form. It never clicks Submit, DSC or payment itself: submitted forms wait in "Review before payment".
"""
import base64
import json
from datetime import datetime
from pathlib import Path

import app
import ff_signed

QUEUE = app.ROOT / "queue.json"
DONE = ("submitted", "skipped", "saved")
STATUS_TEXT = {"queued": "Waiting", "filling": "Filling now", "submitted": "Submitted, payment pending",
               "held": "Needs attention", "skipped": "Skipped", "saved": "Saved, not submitted"}
# Attachments the loop uploads itself: element name -> (slot title, mandatory, stored file stem).
# Stored names avoid "AOC-4" / "MGT-7A" so last year's-form finders never pick them up.
ATTACH = {
    "aoc4": [("aoc4_financialState", "Signed financial statements with auditor's and board's reports (attachment a)", True, "Financial statements"),
             ("aoc4_optional", "Optional attachment", False, "Optional attachment")],
    "mgt7a": [("mgt7a_Photograph", "Photograph of the registered office showing the building and name board", True, "Registered office photo"),
              ("mgt7a_shareholders", "List of shareholders (MCA Excel, prepared by the app when shareholders did not change)", False, "Shareholder list")],
}
ATTACH_DIR = "mca_attachments"


def load():
    try:
        q = json.loads(QUEUE.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        q = {}
    q.setdefault("jobs", [])
    q.setdefault("running", False)
    q.setdefault("current", None)
    q.setdefault("submit", True)
    q.setdefault("auto_submit", False)  # the partner's switch: the tool clicks Submit itself on a clean, verified form
    q.setdefault("next_id", 1)
    return q


def save(q):
    QUEUE.write_text(json.dumps(q, indent=1), encoding="utf-8")


def _job(q, jid):
    return next((j for j in q["jobs"] if j["id"] == jid), None)


def current():
    q = load()
    return q, _job(q, q["current"]) if q["current"] else None


def form_url(slug):
    d = json.loads((app.ROOT / "dumps" / f"{slug}.json").read_text(encoding="utf-8"))
    return d.get("url") or ""


# ---------------------------------------------------------------- attachments

# Excel files uploaded through an "Upload Excel" button (no file box on the form): kind -> (button key ending,
# file name pattern in the client's attachments folder, heading the button must sit under, title)
XL = {"mgt7a": [("xl_members", "panel1641551788472-panel_copy_copy_copy-guidebutton_copy_cop_1466332206", r"meeting of members",
                 r"A\s+MEMBERS", "Meetings of members (Excel)"),
                ("xl_board", "panel1641552137996-panel_copy_copy_copy-guidebutton_copy_cop_1466332206", r"board\s*meeting",
                 r"B\s+BOARD MEETINGS", "Board meetings (Excel)")]}


def excel_files(folder, slug):
    """{kind: Path} of this year's MCA Excel attachments the app prepared (clients/<c>/attachments)."""
    import re
    d, out = Path(folder) / "attachments", {}
    for kind, _, pat, _, _ in XL.get(slug, []):
        mine = Path(folder) / ATTACH_DIR / kind  # a file staff uploaded wins over the one the app prepared
        up = sorted(p for p in mine.glob("*.xls*") if not p.name.startswith("~$")) if mine.exists() else []
        if up:
            out[kind] = up[-1]
            continue
        hits = sorted(p for p in d.glob("*.xls*") if re.search(pat, p.name, re.I) and not p.name.startswith("~$")) if d.exists() else []
        if hits:
            out[kind] = hits[-1]
    return out


def attachment_files(folder, slug):
    """{element: Path} of the files staff uploaded for this form."""
    out = {}
    for el, _, _, _ in ATTACH.get(slug, []):
        d = Path(folder) / ATTACH_DIR / el
        if el == ff_signed.SLOT:  # signed set from the client's signed folder; an MCA form PDF is never attached
            try:
                path, _ = ff_signed.attachment(folder, d)
            except Exception:  # noqa: BLE001  a damaged PDF must not take the screens down
                path = None
            if path:
                out[el] = path
            continue
        files = sorted(p for p in d.glob("*") if p.is_file()) if d.exists() else []
        if not files and el == "mgt7a_shareholders":  # the copy the app carried forward from last year's filed form
            a = Path(folder) / "attachments"
            files = sorted(p for p in a.glob("*hareholder*.xls*") if not p.name.startswith("~$")) if a.exists() else []
        if files:
            out[el] = files[-1]
    return out


def pending(folder, slug):
    """Mandatory attachments not there yet: the form is filled and saved up to the last page, which waits for them."""
    have = attachment_files(folder, slug)
    out = []
    for el, title, must, _ in ATTACH.get(slug, []):
        if must and el not in have and el == ff_signed.SLOT:  # the photo for MGT-7A sits on its first page: that one still blocks
            why = ""
            if el == ff_signed.SLOT:
                try:
                    why = ff_signed.attachment(folder, Path(folder) / ATTACH_DIR / el)[1]
                except Exception as e:  # noqa: BLE001
                    why = f"signed PDF could not be read: {str(e)[:80]}"
            out.append((el, title, why))
    return out


def store_attachment(folder, el, filename, data):
    slot = next(((s, a) for s, rows in ATTACH.items() for a in rows if a[0] == el), None)
    xl = next((x for rows in XL.values() for x in rows if x[0] == el), None)
    if xl or el == "mgt7a_shareholders":  # MCA Excel formats: kept under the name staff gave, older copy moved aside
        if Path(filename).suffix.lower() not in (".xlsm", ".xlsx"):
            raise ValueError("attach the MCA Excel file (.xlsm)")
        d = Path(folder) / ATTACH_DIR / el
        d.mkdir(parents=True, exist_ok=True)
        for old in d.glob("*"):
            app._move_aside(folder, old)
        dest = d / filename
        dest.write_bytes(data)
        return dest
    if not slot:
        raise ValueError("unknown attachment")
    d = Path(folder) / ATTACH_DIR / el
    d.mkdir(parents=True, exist_ok=True)
    for old in d.glob("*"):
        app._move_aside(folder, old)
    ext = Path(filename).suffix.lower() or ".pdf"
    if ext not in (".pdf", ".jpg", ".jpeg", ".png"):
        raise ValueError("attach a PDF, JPG or PNG")
    dest = d / f"{slot[1][3]}{ext}"
    dest.write_bytes(data)
    if el == ff_signed.SLOT and ext == ".pdf" and ff_signed.is_mca_form(dest):
        app._move_aside(folder, dest)
        raise ValueError("this PDF is an MCA form (for example last year's AOC-4), not the signed financial statements: it was not kept")
    return dest


# ---------------------------------------------------------------- readiness

def problems(client, slug):
    """Why this client's form can't go into the queue yet (empty list = ready)."""
    folder = app.folder_of(client)
    f = app.load(folder)
    out = []
    if not f.get("verified"):
        out.append("financials not ticked verified, okay to file (Review financials)")
    if not f.get("cin"):
        out.append("CIN missing (Details)")
    if not app.inputs_path(folder).exists():
        out.append("questions not prepared")
    else:
        st = app.steps(folder)
        if st["open_q"]:
            out.append("questions still to answer: " + "; ".join(st["open_q"]))
        try:
            errs = app.plan_stats(folder, slug)["errors"]
            if errs:
                out.append(f"{len(errs)} data errors in the inputs")
        except Exception as e:  # noqa: BLE001
            out.append(str(e))
    have = attachment_files(folder, slug)
    for el, title, must, _ in ATTACH.get(slug, []):
        if must and el not in have and el != ff_signed.SLOT:
            out.append(f"attachment missing: {title}")
    return out


# ---------------------------------------------------------------- queue actions

def add(pairs):
    """Queue (client, slug) pairs that are ready. Returns (added, [(client, slug, reasons)])."""
    q = load()
    added, refused = 0, []
    for client, slug in pairs:
        if any(j["client"] == client and j["slug"] == slug and j["status"] in ("queued", "filling", "held") for j in q["jobs"]):
            continue
        why = problems(client, slug)
        if why:
            refused.append((client, slug, why))
            continue
        q["jobs"].append({"id": q["next_id"], "client": client, "slug": slug, "status": "queued", "srn": "", "note": "",
                          "updated": datetime.now().isoformat(timespec="seconds")})
        q["next_id"] += 1
        added += 1
    save(q)
    return added, refused


def _audit(j, text, by="agent"):
    try:
        import ff_audit
        ff_audit.event(app.folder_of(j["client"]), "srn", f"{app.FORM_LABEL.get(j['slug'], j['slug'])}: {text}",
                       form=j["slug"], srn=j.get("srn"), by=by)
    except Exception:  # noqa: BLE001
        pass


def _activate(q, j):
    j["status"] = "filling"
    j["updated"] = datetime.now().isoformat(timespec="seconds")
    q["current"] = j["id"]
    folder = app.folder_of(j["client"])
    app._mca().set_state(active=str(app.inputs_path(folder).relative_to(app.ROOT)))


def start():
    """Run the queue from the job being filled, else the first waiting one. Returns that job or None."""
    q = load()
    j = _job(q, q["current"]) if q["current"] else None
    if not j or j["status"] != "filling":
        j = next((x for x in q["jobs"] if x["status"] == "queued"), None)
        if not j:
            q["running"] = False
            save(q)
            return None
        _activate(q, j)
    q["running"] = True
    save(q)
    return dict(j, url=form_url(j["slug"]))


def set_auto(on):
    q = load()
    q["auto_submit"] = bool(on)
    save(q)


def pause():
    q = load()
    q["running"] = False
    save(q)


def advance(body):
    """The extension finished the current job: record how, then move to the next waiting job."""
    q = load()
    j = _job(q, q["current"]) if q["current"] else None
    if j:
        outcome = body.get("outcome") or "submitted"
        j["status"] = outcome if outcome in STATUS_TEXT else "held"
        j["srn"] = str(body.get("srn") or j.get("srn") or "")[:20]
        j["note"] = str(body.get("note") or "")[:300]
        j["counts"] = body.get("counts") or {}
        j["updated"] = datetime.now().isoformat(timespec="seconds")
        tool = "automatic Submit" in j["note"]
        _audit(j, {"submitted": f"Submitted on MCA{' (Submit clicked by Form Filler, automatic Submit switched on by staff)' if tool else ''}, SRN {j['srn'] or 'not read'}", "saved": "Draft saved on MCA, not submitted",
                   "held": f"Filing stopped: {j['note'] or 'needs attention'}", "skipped": "Skipped"}.get(j["status"], j["status"]))
    q["current"] = None
    nxt = next((x for x in q["jobs"] if x["status"] == "queued"), None) if q["running"] else None
    if not nxt:
        q["running"] = False
        save(q)
        return {"next": None}
    _activate(q, nxt)
    save(q)
    left = sum(1 for x in q["jobs"] if x["status"] == "queued")
    return {"next": nxt["id"], "name": f"{nxt['client']} · {app.FORM_LABEL.get(nxt['slug'], nxt['slug'])}",
            "slug": nxt["slug"], "left": left, "nextUrl": form_url(nxt["slug"])}


def edit(form):
    """Dashboard buttons on one job: remove, requeue, mark submitted with an SRN typed by staff."""
    q = load()
    j = _job(q, int(form.get("id") or 0))
    if not j:
        return "No such job."
    act = form.get("act")
    if act == "remove":
        q["jobs"].remove(j)
        if q["current"] == j["id"]:
            q["current"], q["running"] = None, False
    elif act == "requeue":
        j["status"] = "queued"
        if q["current"] == j["id"]:
            q["current"] = None
    elif act == "srn":
        j["srn"] = form.get("srn", "").strip().upper()[:20]
        j["status"] = "submitted" if j["srn"] else j["status"]
        _audit(j, f"SRN {j['srn']} entered by staff", by=form.get("user") or "staff")
    elif act == "paid":
        j["paid"] = datetime.now().isoformat(timespec="seconds")
        _audit(j, "Checked and paid on MCA", by=form.get("user") or "staff")
    j["updated"] = datetime.now().isoformat(timespec="seconds")
    save(q)
    return ""


def clear_done():
    q = load()
    q["jobs"] = [j for j in q["jobs"] if not (j["status"] in ("submitted", "skipped") and j.get("paid"))]
    save(q)


def switch(slug):
    """Staff opened another queued form in the MCA tab: fill that one now. The form that was being filled goes back
    to waiting (its draft stays saved on the portal) and is taken up again in its turn."""
    q, j = current()
    cand = [x for x in q["jobs"] if x["slug"] == slug and x["status"] in ("queued", "held")]
    if not cand:
        raise ValueError(f"no {app.FORM_LABEL.get(slug, slug)} is waiting in the queue")
    nxt = next((x for x in cand if j and x["client"] == j["client"]), cand[0])  # the same client's form first
    if j and j["status"] == "filling":
        j["status"] = "queued"
        j["note"] = "Set aside part way: draft saved on MCA"
        j["updated"] = datetime.now().isoformat(timespec="seconds")
        _audit(j, f"Set aside part way; {app.FORM_LABEL.get(slug, slug)} taken up first", by="staff")
    _activate(q, nxt)
    q["running"] = True
    save(q)
    return {"job": dict(nxt, url=form_url(slug))}


# ---------------------------------------------------------------- the plan the extension gets

def plan(slug):
    """Plan for the running job, or None when the queue is not running (normal one-client filling)."""
    q, j = current()
    if not q["running"] or not j:
        return None
    if j["slug"] != slug:
        e = ValueError(f"the filing queue is on {j['client']}'s {app.FORM_LABEL.get(j['slug'], j['slug'])}, "
                       f"but this tab is {app.FORM_LABEL.get(slug, slug)}. Open that form, or pause the queue in the app")
        e.can_switch = any(x["slug"] == slug and x["status"] in ("queued", "held") for x in q["jobs"])
        e.other = app.FORM_LABEL.get(j["slug"], j["slug"])
        e.same_client = any(x["slug"] == slug and x["status"] in ("queued", "held") and x["client"] == j["client"] for x in q["jobs"])
        raise e
    m = app._mca()
    folder = app.folder_of(j["client"])
    app.refresh_questions(folder)
    cin = app.load(folder).get("cin", "")
    p = m.make_plan(app.inputs_path(folder), slug)
    p["client"] = f"{j['client']} ({cin})"
    # The company is picked by CIN at the top of the form: put it first so the portal prefills from it.
    have = {e["key"] for e in p["fields"]}
    first = []
    for f in m.schema(slug)["fields"]:
        if f.get("name") in ("CIN_Number_Other_User", "CIN_Number_Professional_User") and f["key"] not in have and cin:
            e = {k: f.get(k) for k in ("code", "key", "domBase", "som", "type", "label", "sectionText", "group", "segment")}
            e.update(value=cin, display=cin)
            first.append(e)
    p["fields"] = first + p["fields"]
    p.update(autoSave=True, autoNext=True, autoAdvance=True, autoContinue=True, watchSubmit=True,
             advancePath="/queue/advance", queueJob=j["id"], nextUrl=form_url(slug), autoSubmit=bool(q.get("auto_submit")))
    files = attachment_files(folder, slug)
    by_name = {f.get("name"): f for f in m.schema(slug)["fields"] if f["type"] == "file"}
    p["attachments"] = []
    for el, title, must, _ in ATTACH.get(slug, []):
        f, path = by_name.get(el), files.get(el)
        if f and path:
            p["attachments"].append({"code": f["code"], "key": f["key"], "domBase": f["domBase"], "som": f["som"], "label": f["label"],
                                     "kind": el, "file": path.name, "url": f"/queue/file?job={j['id']}&el={el}"})
    xl = excel_files(folder, slug)
    buttons = {b["key"]: b for b in m.load_dump(slug).get("buttons") or []}
    for kind, tail, _, heading, title in XL.get(slug, []):
        key = next((k for k in buttons if k.endswith(tail)), None)
        if key and xl.get(kind):
            p["attachments"].append({"code": kind, "key": key, "button": "guideContainer-" + key + "__", "heading": heading, "label": title,
                                     "kind": kind, "file": xl[kind].name, "url": f"/queue/file?job={j['id']}&el={kind}"})
    # Mandatory attachments not there yet: the tool fills and saves every page before them, then holds this form
    # as "last page pending" and goes on to the next client.
    p["pendingAttachments"] = [{"domBase": by_name[el]["domBase"], "label": by_name[el]["label"], "title": title.split("(")[0].strip()}
                               for el, title, _ in pending(folder, slug) if by_name.get(el)]
    return p


def file_json(job_id, el):
    q = load()
    j = _job(q, int(job_id or 0))
    if not j:
        raise FileNotFoundError("no such job")
    p = attachment_files(app.folder_of(j["client"]), j["slug"]).get(el) or excel_files(app.folder_of(j["client"]), j["slug"]).get(el)
    if not p:
        raise FileNotFoundError(f"no file for {el}")
    return {"name": p.name, "b64": base64.b64encode(p.read_bytes()).decode("ascii")}


# ---------------------------------------------------------------- dashboard section

def section():
    q = load()
    esc = app.esc
    rows = []
    for j in q["jobs"]:
        st = j["status"]
        cls = {"filling": "pill on", "held": "pill bad", "submitted": "pill sub"}.get(st, "pill")
        c = j.get("counts") or {}
        cnt = ", ".join(f"{k} {v}" for k, v in c.items() if k in ("filled", "failed", "manual")) if c else ""
        acts = []
        if st in ("held", "skipped", "saved"):
            acts.append(("requeue", "Fill again"))
        if st != "filling":
            acts.append(("remove", "Remove"))
        btns = "".join(f"<form method=post action=/queue/edit style=display:inline><input type=hidden name=id value={j['id']}>"
                       f"<input type=hidden name=act value={a}><button>{t}</button></form> " for a, t in acts)
        srn_box = "" if j.get("srn") or st not in ("held", "saved") else (
            f"<form method=post action=/queue/edit style=display:inline><input type=hidden name=id value={j['id']}>"
            f"<input type=hidden name=act value=srn><input type=text name=srn placeholder=SRN style=width:110px> <button>Save SRN</button></form>")
        rows.append(f"<tr><td><a href=\"/client?c={app.quote(j['client'])}\">{esc(j['client'])}</a></td><td>{app.FORM_LABEL.get(j['slug'], j['slug'])}</td>"
                    f"<td><span class=\"{cls}\">{STATUS_TEXT.get(st, st)}</span><br><span class=muted>{esc(j.get('note', ''))}</span></td>"
                    f"<td>{esc(j.get('srn', ''))}{srn_box}</td><td class=muted>{esc(cnt)}</td><td>{btns}</td></tr>")
    waiting = sum(1 for j in q["jobs"] if j["status"] == "queued")
    # Clients that could be queued: every client with AOC-4 / MGT-7A picked in Details.
    picks = []
    CL = app.CLIENTS
    for d in sorted(p for p in CL.iterdir() if p.is_dir()) if CL.exists() else []:
        for s in app.load(d).get("forms") or []:
            if s in app.SMART and not any(j["client"] == d.name and j["slug"] == s and j["status"] in ("queued", "filling", "held", "submitted") for j in q["jobs"]):
                picks.append(f"<label style=\"display:inline-block;margin:3px 14px 3px 0\"><input type=checkbox name=job value=\"{esc(d.name)}|{s}\"> "
                             f"{esc(d.name)} · {app.FORM_LABEL[s]}</label>")
    run = (f"<form method=post action=/queue/pause style=display:inline><button>Pause after this client</button></form>" if q["running"] else
           f"<form method=post action=/queue/start style=display:inline><button class=go {'disabled' if not waiting and not q['current'] else ''}>Start the queue</button></form>")
    sub = ""
    review = [j for j in q["jobs"] if j["status"] == "submitted" and not j.get("paid")]
    rev_rows = "".join(
        f"<tr><td>{esc(j['client'])}</td><td>{app.FORM_LABEL.get(j['slug'], j['slug'])}</td><td><b>{esc(j['srn'] or 'SRN not read')}</b></td>"
        f"<td class=muted>{esc(', '.join(f'{k} {v}' for k, v in (j.get('counts') or {}).items()))}</td>"
        f"<td><form method=post action=/queue/edit><input type=hidden name=id value={j['id']}><input type=hidden name=act value=paid>"
        f"<button>Checked and paid</button></form></td></tr>" for j in review)
    return f"""<div class=card id=queue><h2>Filing queue</h2>
<p class=muted style=margin-top:0>Pick clients and forms, then start. In the MCA Chrome window, log in once and open the side panel:
the tool opens each form, fills it section by section, clicks Save and Next and uploads the attachments you gave it.
On the last page it outlines <b>Submit</b>: you click it, the tool reads the SRN and opens the next client's form.
When something needs you it stops and says what. Login, captcha, Submit, DSC and payment stay with you.</p>
<p style="margin:14px 0">{run} {sub}</p>
<table><tr><th>Client</th><th>Form</th><th>Status</th><th>SRN</th><th>Last run</th><th></th></tr>
{''.join(rows) or '<tr><td colspan=6 class=muted>Nothing queued.</td></tr>'}</table>
{f'<form method=post action=/queue/add style=margin-top:12px><div>{"".join(picks)}</div><button class=primary style=margin-top:8px>Add to queue</button> <span class=muted>Only clients with answered questions, a CIN and the mandatory attachments are added.</span></form>' if picks else ''}
</div>
<div class=card id=review><h2>Review before payment</h2>
{'<table><tr><th>Client</th><th>Form</th><th>SRN</th><th>Fill result</th><th></th></tr>' + rev_rows + '</table>' if review else '<p class=muted>No submitted forms waiting.</p>'}
<p class=muted>Before paying: open each SRN on MCA, check the form PDF against the client's financials, affix DSC and upload it, then pay. Mark it here when done.</p></div>"""
