"""Local AI (Ollama) for the filing app: suggest and cross-check Questions-step answers.

What it does
  For one client, it reads the client's own documents (last year's filed AOC-4 / MGT-7A PDFs,
  board's and auditor's report extracts, any other PDF in the client folder), finds the passages
  relevant to each question, and asks a local model on the LAN (Ollama) for an answer, the exact
  line it relied on, and a confidence. Staff see the AI's answer beside the current one and decide;
  nothing is written to the workbook until staff click Save (the normal /app/answers route).

Pages (routed from app.handle_get / app.handle_post):
  GET  /ai                    status: is Ollama reachable, which models, settings
  POST /ai/settings           save URL / model / on-off
  GET  /ai/questions?c=NAME   suggestions page for one client (auto-refreshes while running)
  POST /ai/run                start a run in the background

Settings: ai.json next to this file. Default URL http://localhost:11434, model qwen3:4b.
Data never leaves the LAN: the only network call is to the Ollama URL in settings.
Each run is logged to clients/<name>/logs/ai_<timestamp>.json (model, questions, answers, sources).
"""
import json
import re
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "ai.json"
DEFAULTS = {"enabled": True, "url": "http://localhost:11434", "model": "qwen3:4b", "batch": 6, "context_chars": 3500}
RESULT = "ai_suggestions.json"
CACHE_DIR = "_ai_cache"
STOP = set("the a an of to in for on and or is was any this that with by be are as at from during year date dd mm yyyy "
           "did does has have were which who what number no yes".split())

_jobs = {}  # client name -> {"state", "done", "total", "error", "started"}
_lock = threading.Lock()


def _app():
    import app
    return app


# ---------------------------------------------------------------- settings and Ollama

def settings():
    s = dict(DEFAULTS)
    try:
        s.update(json.loads(CONFIG.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    return s


def save_settings(**kw):
    s = settings()
    s.update(kw)
    CONFIG.write_text(json.dumps(s, indent=1), encoding="utf-8")
    return s


def _call(path, payload=None, timeout=5):
    s = settings()
    url = s["url"].rstrip("/") + path
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def status():
    """{"ok", "models", "error", "ms"}"""
    t = time.time()
    try:
        tags = _call("/api/tags", timeout=4)
        return {"ok": True, "models": [m.get("name") for m in tags.get("models", [])], "error": "",
                "ms": int((time.time() - t) * 1000)}
    except (urllib.error.URLError, OSError, ValueError) as e:
        return {"ok": False, "models": [], "error": str(getattr(e, "reason", e)), "ms": 0}


def chat(system, user, schema=None, timeout=600):
    s = settings()
    body = {"model": s["model"], "stream": False, "think": False,
            "options": {"temperature": 0, "num_ctx": 8192},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    if schema:
        body["format"] = schema
    try:
        out = _call("/api/chat", body, timeout=timeout)
    except urllib.error.HTTPError as e:
        if e.code == 400 and "think" in body:  # older Ollama or a model without a thinking switch
            body.pop("think")
            out = _call("/api/chat", body, timeout=timeout)
        else:
            raise
    text = out.get("message", {}).get("content", "")
    return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()


# ---------------------------------------------------------------- client documents

def _pdf_text(p, cache):
    cache.mkdir(exist_ok=True)
    c = cache / (p.stem + ".txt")
    if c.exists() and c.stat().st_mtime >= p.stat().st_mtime:
        return c.read_text(encoding="utf-8", errors="replace")
    import pdfplumber
    parts = []
    with pdfplumber.open(p) as pdf:
        for page in pdf.pages[:40]:
            parts.append(page.extract_text() or "")
    text = "\n".join(parts)
    c.write_text(text, encoding="utf-8")
    return text


def chunks(folder):
    """[(source file, passage)] from every PDF in the client folder, about 600 characters each."""
    out = []
    folder = Path(folder)
    for p in sorted(folder.glob("*.pdf")):
        try:
            text = _pdf_text(p, folder / CACHE_DIR)
        except Exception:  # noqa: BLE001  unreadable PDF: skip it
            continue
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        buf = ""
        for ln in lines:
            if len(buf) + len(ln) > 600 and buf:
                out.append((p.name, buf))
                buf = ""
            buf += ln + "\n"
        if buf:
            out.append((p.name, buf))
    return out


def _words(s):
    return {w for w in re.findall(r"[a-z0-9]+", str(s).lower()) if w not in STOP and len(w) > 1}


def relevant(passages, questions, limit):
    """Pick the passages sharing the most words with this batch of questions, up to `limit` characters."""
    want = set()
    for _, text, how, _, _ in questions:
        want |= _words(text) | _words(how)
    scored = sorted(((len(want & _words(t)), i) for i, (_, t) in enumerate(passages)), reverse=True)
    picked, size = [], 0
    for score, i in scored:
        if score == 0 or size > limit:
            break
        picked.append(i)
        size += len(passages[i][1])
    return [passages[i] for i in sorted(picked)]


# ---------------------------------------------------------------- the run

SYSTEM = ("You help an Indian chartered accountant's staff prepare MCA (ROC) annual filings. "
          "Answer each question ONLY from the company documents given. Copy the exact supporting line "
          "into 'source'. If the documents do not answer it, give answer \"\" and confidence \"none\". "
          "Dates as DD/MM/YYYY. For Yes / No questions answer exactly Yes or No. Never invent figures, DINs or dates.")

THIS_YEAR = ("This filing is for the financial year {start} to {end}. Most documents given are LAST year's filed forms, so their "
             "dates belong to the year before. For a question about a date or event of THIS financial year (AGM, board meetings, "
             "signing, approval, resolution), answer only when the document shows a date that fits this financial year or the "
             "months after it; otherwise give answer \"\" and confidence \"none\". Standing facts (names, DINs, addresses, auditor, "
             "type of company) may be taken from last year's forms.")
_DATE = re.compile(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})\b")


def fy_window(folder):
    """(first day, last day) of the financial year being filed, from the client's details (default 2025-26)."""
    from datetime import date
    try:
        d, m, y = (int(x) for x in str(_app().load(folder).get("fy_end") or "31/03/2026").split("/"))
        end = date(y, m, d)
    except (ValueError, TypeError):
        end = date(2026, 3, 31)
    return date(end.year - 1, 4, 1), end


def date_rule(text, how):
    """Which dates fit a question: 'in' (inside the year), 'after' (after the year end) or None (no rule)."""
    if "DD/MM/YYYY" not in (how or "").upper():
        return None
    t = (text or "").lower()
    if "appoint" in t or "incorporat" in t:
        return None  # may rightly be an older date
    return "in" if "during the year" in t else "after"


def stale_dates(folder, text, how, answer):
    """Dates in an answer that cannot belong to this year's filing (they are last year's). [] when the answer fits."""
    from datetime import date
    rule = date_rule(text, how)
    if not rule or not answer:
        return []
    start, end = fy_window(folder)
    bad = []
    for d, m, y in _DATE.findall(str(answer)):
        try:
            v = date(int(y), int(m), int(d))
        except ValueError:
            continue
        if (rule == "in" and not start <= v <= end) or (rule == "after" and v <= end):
            bad.append(v.strftime("%d/%m/%Y"))
    return bad


def propose(folder, text, how, last):
    """This year's dates worked out from last year's: the same day one year on. '' when that does not fit the filing year.
    A proposal only: staff confirm it against the minutes before saving."""
    from datetime import date
    out = []
    for d, m, y in _DATE.findall(str(last or "")):
        try:
            v = date(int(y) + 1, int(m), int(d))
        except ValueError:
            try:
                v = date(int(y) + 1, int(m), int(d) - 1)  # 29 February
            except ValueError:
                continue
        out.append(v)
    text_ = ", ".join(v.strftime("%d/%m/%Y") for v in out)
    if not out or stale_dates(folder, text, how, text_):
        return "", ""
    sun = [f"{v:%d/%m/%Y}" for v in out if v.weekday() == 6]
    return text_, (f"{', '.join(sun)} is a Sunday" if sun else "")


def need_text(folder, text, how):
    start, end = fy_window(folder)
    return (f"a date from {start:%d/%m/%Y} to {end:%d/%m/%Y}" if date_rule(text, how) == "in" else f"a date after {end:%d/%m/%Y}")


SCHEMA = {"type": "object", "properties": {"answers": {"type": "array", "items": {
    "type": "object", "properties": {"key": {"type": "string"}, "answer": {"type": "string"},
                                     "source": {"type": "string"},
                                     "confidence": {"type": "string", "enum": ["high", "medium", "low", "none"]}},
    "required": ["key", "answer", "source", "confidence"]}}}, "required": ["answers"]}


def _norm(v):
    v = str(v or "").strip().lower()
    return re.sub(r"[\s,.;]+", " ", v)


def run(name):
    app = _app()
    folder = app.folder_of(name)
    s = settings()
    job = _jobs[name]
    log = {"client": name, "model": s["model"], "url": s["url"], "started": datetime.now().isoformat(timespec="seconds"),
           "batches": []}
    try:
        qs, _ = app.questions(folder)
        if not qs:
            raise ValueError("no questions yet: click Prepare questions in step 3 first")
        asked_all = len(qs)
        qs = [q for q in qs if not str(q[3] or "").strip()]  # only the inputs still open go to the model, with the passages that match them
        if not qs:
            raise ValueError(f"all {asked_all} inputs already have an answer: nothing to ask the local AI")
        passages = chunks(folder)
        if not passages:
            raise ValueError("no PDFs in the client folder to read (upload last year's filed forms first)")
        start_, end_ = fy_window(folder)
        this_year = THIS_YEAR.format(start=start_.strftime("%d/%m/%Y"), end=end_.strftime("%d/%m/%Y"))
        log["fy"] = f"{start_:%d/%m/%Y} to {end_:%d/%m/%Y}"
        size = max(1, int(s.get("batch") or 6))
        batches = [qs[i:i + size] for i in range(0, len(qs), size)]
        job.update(total=len(qs), done=0, files=sorted({f for f, _ in passages}))
        results = {}
        for batch in batches:
            ctx = relevant(passages, batch, int(s.get("context_chars") or 3500))
            docs = "\n\n".join(f"[{f}]\n{t}" for f, t in ctx) or "(no matching passages)"
            ask = "\n".join(f"- key: {k} | question: {t} | format: {h}" for k, t, h, _, _ in batch)
            user = f"COMPANY DOCUMENTS:\n{docs}\n\nQUESTIONS:\n{ask}\n\nReply as JSON with one item per key."
            t0 = time.time()
            raw = chat(SYSTEM + " " + this_year, user, SCHEMA)
            try:
                items = json.loads(raw).get("answers", [])
            except ValueError:
                items = []
            for it in items:
                k = str(it.get("key", "")).strip()
                if k in {q[0] for q in batch}:
                    results[k] = {"answer": str(it.get("answer", "")).strip(), "source": str(it.get("source", "")).strip()[:400],
                                  "confidence": it.get("confidence", "low")}
                    qrow = next(q for q in batch if q[0] == k)
                    if stale_dates(folder, qrow[1], qrow[2], results[k]["answer"]):
                        # last year's date: kept for reference, never offered as this year's answer
                        results[k].update(last_year=results[k]["answer"], answer="", confidence="none")
            log["batches"].append({"keys": [q[0] for q in batch], "files": sorted({f for f, _ in ctx}),
                                   "seconds": round(time.time() - t0, 1), "items": items})
            job["done"] = min(job["total"], job["done"] + len(batch))
            _save(folder, name, results, s, final=False)
        _save(folder, name, results, s, final=True)
        job["state"] = "done"
        got = sum(1 for r in results.values() if r.get("answer"))
        log.update(questions=len(qs), answered=got, not_used=sum(1 for r in results.values() if r.get("last_year")))
        try:
            import ff_audit
            ff_audit.event(folder, "ai", f"Local AI ({s['model']}) read {len(job.get('files') or [])} documents and suggested "
                           f"{got} of {len(qs)} inputs; nothing is saved until staff accept", by="agent")
        except Exception:  # noqa: BLE001
            pass
    except Exception as e:  # noqa: BLE001
        job.update(state="error", error=str(e))
        log["error"] = str(e)
    log["finished"] = datetime.now().isoformat(timespec="seconds")
    log["files"] = job.get("files") or []
    (folder / "logs").mkdir(exist_ok=True)
    (folder / "logs" / f"ai_{datetime.now():%Y%m%d_%H%M%S}.json").write_text(json.dumps(log, indent=1), encoding="utf-8")


def _save(folder, name, results, s, final):
    data = {"client": name, "model": s["model"], "when": datetime.now().isoformat(timespec="seconds"),
            "complete": final, "answers": results}
    (Path(folder) / RESULT).write_text(json.dumps(data, indent=1), encoding="utf-8")


def start(name):
    with _lock:
        j = _jobs.get(name)
        if j and j.get("state") == "running":
            return False
        _jobs[name] = {"state": "running", "done": 0, "total": 0, "error": "", "started": time.time()}
    threading.Thread(target=run, args=(name,), daemon=True).start()
    return True


def runs(limit=60):
    """Every Local AI run, newest first: what was sent, what came back. Running ones first, then the run logs in each client folder."""
    app = _app()
    out = []
    for name, j in list(_jobs.items()):
        if j.get("state") == "running":
            out.append({"client": name, "started": datetime.fromtimestamp(j["started"]).isoformat(timespec="seconds"), "finished": "",
                        "model": settings()["model"], "files": j.get("files") or [], "questions": j.get("total") or 0,
                        "answered": None, "done": j.get("done") or 0, "state": "running", "error": "", "not_used": 0})
    if app.CLIENTS.exists():
        for d in app.CLIENTS.iterdir():
            for p in sorted((d / "logs").glob("ai_*.json"), reverse=True)[:10] if (d / "logs").exists() else []:
                try:
                    g = json.loads(p.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                b = g.get("batches") or []
                files = g.get("files") or sorted({f for x in b for f in x.get("files", [])})
                asked = g.get("questions") or sum(len(x.get("keys", [])) for x in b)
                got = g.get("answered")
                if got is None:
                    got = sum(1 for x in b for it in x.get("items", []) if str(it.get("answer", "")).strip())
                out.append({"client": d.name, "started": g.get("started", ""), "finished": g.get("finished", ""), "model": g.get("model", ""),
                            "files": files, "questions": asked, "answered": got, "done": asked, "not_used": g.get("not_used", 0),
                            "seconds": round(sum(x.get("seconds", 0) for x in b)), "state": "error" if g.get("error") else "done",
                            "error": g.get("error", "")})
    out.sort(key=lambda r: (r["state"] != "running", r["started"]), reverse=False)
    run_, rest = [r for r in out if r["state"] == "running"], [r for r in out if r["state"] != "running"]
    rest.sort(key=lambda r: r["started"], reverse=True)
    return (run_ + rest)[:limit]


def load_result(folder):
    try:
        return json.loads((Path(folder) / RESULT).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


# ---------------------------------------------------------------- pages

def page_status(msg=""):
    app = _app()
    s, st = settings(), status()
    models = "".join(f"<option {'selected' if m == s['model'] else ''}>{app.esc(m)}</option>" for m in st["models"])
    if s["model"] not in st["models"]:
        models = f"<option selected>{app.esc(s['model'])}</option>" + models
    state = (f"<span class='pill on'>Connected</span> <span class=muted>{len(st['models'])} models, {st['ms']} ms</span>" if st["ok"]
             else f"<span class='pill bad'>Not reachable</span> <span class=muted>{app.esc(st['error'])}</span>")
    clients = sorted(p.name for p in app.CLIENTS.iterdir() if p.is_dir()) if app.CLIENTS.exists() else []
    links = " ".join(f"<a class=btn href=\"/ai/questions?c={quote(c)}\">{app.esc(c)}</a>" for c in clients)
    body = f"""<div class=phead><h1>Local AI</h1><p>A model on your own LAN reads each client's documents and suggests answers. Staff decide.</p></div>
<div class=kpis><div class=kpi><div class=l>Ollama</div><div class=v>{'Online' if st['ok'] else 'Offline'}</div><div class=s>{app.esc(s['url'])}</div></div>
<div class=kpi><div class=l>Model</div><div class=v>{app.esc(s['model'])}</div><div class=s>{len(st['models'])} installed</div></div>
<div class=kpi><div class=l>Leaves the LAN</div><div class=v>Nothing</div><div class=s>no cloud calls</div></div></div>
<div class=card><h2>Connection</h2>
<p>{state}</p>
<p class=muted>The model runs on your own machine on the LAN through Ollama. Client documents are read on this PC and sent
only to the address below. Nothing goes to the internet. The AI only suggests; staff decide what is saved.</p>
<form method=post action=/ai/settings style="display:grid;grid-template-columns:160px 1fr;gap:8px;max-width:620px;align-items:center">
<label>Ollama address</label><input type=text name=url value="{app.esc(s['url'])}">
<label>Model</label><select name=model>{models}</select>
<label>Use local AI</label><select name=enabled><option {'selected' if s['enabled'] else ''}>On</option><option {'' if s['enabled'] else 'selected'}>Off</option></select>
<span></span><p><button class=primary>Save and test</button></p></form></div>
<div class=card><h2>Suggest and cross-check answers</h2>
<p>Pick a client. The AI reads last year's filed forms and the reports in the client's folder, answers each question
with the line it relied on, and flags where it differs from the current answer.</p><p>{links or '<span class=muted>No clients yet.</span>'}</p></div>"""
    return app.shell("Local AI", body, msg)


def _dates(text):
    """A list of dates, one per line when there are several."""
    parts = [x.strip() for x in str(text or "").split(",") if x.strip()]
    return _app().esc(text) if len(parts) < 3 else "<br>".join(_app().esc(x) for x in parts)


def _source(src, answer):
    """The line the model relied on, folded away: the document's name shows, the words open on a click."""
    src = str(src or "").strip()
    if not src:
        return ""
    m = re.match(r"^\[(.+?)\]\s*(.*)$", src, re.S)
    fname, quote_ = (m.group(1), m.group(2)) if m else ("", src)
    up = fname.upper()
    doc = ("last year's AOC-4" if "AOC" in up else "last year's MGT-7A" if "MGT" in up else "the board's report" if "BOARD" in up
           else "the auditor's report" if "AUDIT" in up else fname or "the documents")
    quote_ = " ".join(quote_.split())
    if len(quote_) > 180:  # keep the part around the answer
        at = quote_.lower().find(str(answer).lower()) if len(str(answer)) > 3 else -1
        a0 = max(0, (at if at >= 0 else 0) - 90)
        quote_ = ("... " if a0 else "") + quote_[a0:a0 + 180].strip() + " ..."
    esc = _app().esc
    return (f"<details class=src><summary>From {esc(doc)}</summary><div>&ldquo;{esc(quote_)}&rdquo;"
            + (f"<br>File: {esc(fname)}" if fname else "") + "</div></details>")


def page_questions(name, msg=""):
    app = _app()
    import ff_ui
    folder = app.folder_of(name)
    if not folder.exists():
        return page_status(f"No client called {name}.")
    s = settings()
    job = _jobs.get(name) or {}
    res = load_result(folder)
    ans = res.get("answers", {})
    qs, _ = app.questions(folder)
    running = job.get("state") == "running"
    start, end = fy_window(folder)
    if running:
        pct = int(100 * job.get("done", 0) / job["total"]) if job.get("total") else 0
        head = (f"<div class=h>Reading the documents with {app.esc(s['model'])}: {job.get('done', 0)} of {job.get('total') or '?'} questions</div>"
                f"<div class=pbar><i style=\"width:{pct}%\"></i></div><p class=mut>Sent to the model: {app.esc(', '.join(job.get('files') or []))}</p>")
    elif job.get("state") == "error":
        head = f"<div class=h>The last run stopped</div><p class=err>{app.esc(job.get('error'))}</p>"
    elif res:
        head = (f"<div class=h>Last run {ff_ui.when(res.get('when', ''))} with {app.esc(res.get('model', ''))}"
                f"{'' if res.get('complete') else ' (not finished)'}</div>")
    else:
        head = "<div class=h>Not run yet for this client</div>"
    agree = differ = new = stale = 0
    groups = {"confirm": [], "type": [], "differ": [], "ok": []}
    for key, text, how, cur, came in qs:
        a = dict(ans.get(key) or {})
        if a.get("answer") and stale_dates(folder, text, how, a["answer"]):  # a run made before this check
            a.update(last_year=a["answer"], answer="", confidence="none")
        cur_stale = stale_dates(folder, text, how, cur)
        g = "ok"
        if not a:
            verdict, ai_cell = "", "<span class=mut>Not asked yet</span>"
            g = "ok" if cur.strip() else "type"
        elif a.get("last_year"):
            stale += 1
            prop, warn = propose(folder, text, how, a["last_year"])
            g = "confirm"
            if prop:
                a["answer"] = prop
                verdict = ff_ui.tag("Proposed: confirm", "sug")
                ai_cell = (f"<b>{_dates(prop)}</b><div class=mut>Last year: {app.esc(a['last_year'])}</div>"
                           + (f"<div class=mut>{app.esc(warn)}</div>" if warn else ""))
            else:
                verdict = ff_ui.tag("Enter this year's date", "need")
                ai_cell = f"<span class=mut>Last year: {_dates(a['last_year'])}. Needs {need_text(folder, text, how)}.</span>"
        elif not a.get("answer") or a.get("confidence") == "none":
            if cur.strip():
                verdict, ai_cell = ff_ui.tag("Saved answer kept"), "<span class=mut>Not in the documents</span>"
            else:
                verdict, ai_cell, g = ff_ui.tag("Type the answer", "need"), "<span class=mut>Not in the documents</span>", "type"
        else:
            if not cur.strip():
                verdict, new = ff_ui.tag("AI filled a blank", "sug"), new + 1
            elif _norm(cur) == _norm(a["answer"]):
                verdict, agree = ff_ui.tag("Agrees", "good"), agree + 1
            else:
                verdict, differ, g = ff_ui.tag("Differs: check", "need"), differ + 1, "differ"
            conf = a.get("confidence", "")
            ai_cell = (f"<b>{app.esc(a['answer'])}</b>" + (f" <span class=mut>· {app.esc(conf)} confidence</span>" if conf and conf != "high" else "")
                       + _source(a.get("source", ""), a["answer"]))
        if cur_stale:
            verdict, g = ff_ui.tag("Saved answer is last year's date", "badt"), "confirm"
        value = cur if cur.strip() else a.get("answer", "")
        field = f"<input type=text name=\"q_{app.esc(key)}\" value=\"{app.esc(value)}\" style=\"width:100%\" aria-label=\"Answer to save\">"
        groups[g].append(f"<tr><td style=\"width:34%\">{app.esc(text)}<div class=mut>{app.esc(how)}</div></td>"
                         f"<td style=\"width:30%\">{ai_cell}</td><td>{field}<div style=\"margin-top:6px\">{verdict}</div></td></tr>")
    titles = [("confirm", "Dates to confirm", "Proposed as the same day this year. Check each against the minutes."),
              ("type", "Type these yourself", "The documents do not say."),
              ("differ", "AI differs from the saved answer", "Open the source to see which is right."),
              ("ok", "No action needed", "The AI agrees, filled a blank from the documents, or the saved answer stands.")]
    rows = [f"<tr class=grp><td colspan=3><b>{t}</b> <span class=mut>({len(groups[k])}) · {h}</span></td></tr>" + "".join(groups[k])
            for k, t, h in titles if groups[k]]
    summary = (f"<p style=\"margin:0\">{len(groups['confirm'])} dates to confirm · {len(groups['type'])} to type · "
               f"{len(groups['differ'])} differ · {len(groups['ok'])} need no action</p>") if ans else ""
    q = quote(name)
    acts = (f"<a class=btn href=\"/review?c={q}&tab=questions\">Back to the inputs</a>"
            f"<form method=post action=/ai/run><input type=hidden name=c value=\"{app.esc(name)}\">"
            f"<button {'disabled' if running or not s['enabled'] else ''}>{'Run again' if res else 'Read the documents'}</button></form>")
    off = "" if s["enabled"] else "<p class=err>Local AI is off. Turn it on under Local AI settings.</p>"
    body = (ff_ui.head(f"Step 2 of 3 · {app.esc(name)} · filing for {start:%d/%m/%Y} to {end:%d/%m/%Y}", "Local AI suggestions", acts)
            + f"<div class=card>{head}{summary}{off}<p class=mut style=\"margin:12px 0 0\">Read from last year's filed forms on the office network. "
              f"Nothing is saved until you click Save answers. <a href=\"/agents?q=ai\">See what was sent and received</a></p></div>"
            + f"<div class=card><form method=post action=/ff/answers><input type=hidden name=c value=\"{app.esc(name)}\">"
              f"<style>tr.grp td{{background:var(--muted);padding-top:10px;padding-bottom:10px}}details.src{{margin-top:4px}}details.src div{{font-size:13px;color:var(--mfg);margin-top:4px;max-width:44ch}}</style><table><tr><th>Question</th><th>AI suggestion</th><th>Answer to save</th></tr>{''.join(rows)}</table>"
              f"<p class=row style=\"margin:16px 0 0;align-items:center\"><button class=p data-busy=Saving>Save answers</button>"
              f"<span class=mut>Blanks take the AI's answer. Nothing else changes unless you edit it.</span></p></form></div>")
    return ff_ui.shell(f"Local AI: {name}", body, "/review", msg, refresh=3 if running else 0)


def handle_get(path, q):
    if path == "/ai":
        return 200, page_status(q.get("msg", "")), "text/html"
    if path == "/ai/questions":
        return 200, page_questions(q.get("c", ""), q.get("msg", "")), "text/html"
    if path == "/ai/status.json":
        return 200, json.dumps(status()), "application/json"
    return None


def handle_post(path, form):
    if path == "/ai/settings":
        save_settings(url=form.get("url", DEFAULTS["url"]).strip() or DEFAULTS["url"],
                      model=form.get("model", DEFAULTS["model"]).strip() or DEFAULTS["model"],
                      enabled=form.get("enabled", "On") == "On")
        st = status()
        msg = f"Saved. Connected, {len(st['models'])} models." if st["ok"] else f"Saved, but Ollama is not reachable: {st['error']}"
        return 303, "", "text/html", f"/ai?msg={quote(msg)}"
    if path == "/ai/run":
        name = form.get("c", "")
        if not settings()["enabled"]:
            msg = "Local AI is off in settings."
        elif not status()["ok"]:
            msg = "Ollama is not reachable: check the address on the Local AI page and that Ollama is running."
        else:
            msg = "Started." if start(name) else "Already running."
        return 303, "", "text/html", f"/ai/questions?c={quote(name)}&msg={quote(msg)}"
    return None
