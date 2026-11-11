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
        passages = chunks(folder)
        if not passages:
            raise ValueError("no PDFs in the client folder to read (upload last year's filed forms first)")
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
            raw = chat(SYSTEM, user, SCHEMA)
            try:
                items = json.loads(raw).get("answers", [])
            except ValueError:
                items = []
            for it in items:
                k = str(it.get("key", "")).strip()
                if k in {q[0] for q in batch}:
                    results[k] = {"answer": str(it.get("answer", "")).strip(), "source": str(it.get("source", "")).strip()[:400],
                                  "confidence": it.get("confidence", "low")}
            log["batches"].append({"keys": [q[0] for q in batch], "files": sorted({f for f, _ in ctx}),
                                   "seconds": round(time.time() - t0, 1), "items": items})
            job["done"] = min(job["total"], job["done"] + len(batch))
            _save(folder, name, results, s, final=False)
        _save(folder, name, results, s, final=True)
        job["state"] = "done"
    except Exception as e:  # noqa: BLE001
        job.update(state="error", error=str(e))
        log["error"] = str(e)
    log["finished"] = datetime.now().isoformat(timespec="seconds")
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


def page_questions(name, msg=""):
    app = _app()
    folder = app.folder_of(name)
    if not folder.exists():
        return page_status(f"No client called {name}.")
    s = settings()
    job = _jobs.get(name) or {}
    res = load_result(folder)
    ans = res.get("answers", {})
    qs, _ = app.questions(folder)
    running = job.get("state") == "running"
    refresh = '<meta http-equiv=refresh content=3>' if running else ""
    if running:
        pct = int(100 * job.get("done", 0) / job["total"]) if job.get("total") else 0
        head = (f"<p><b>Reading the documents with {app.esc(s['model'])}:</b> {job.get('done', 0)} of {job.get('total') or '?'} questions "
                f"({pct}%).</p><div style='height:8px;background:var(--line);border-radius:4px'><div style='height:8px;width:{pct}%;"
                f"background:var(--go);border-radius:4px'></div></div><p class=muted>Files: {app.esc(', '.join(job.get('files') or []))}</p>")
    elif job.get("state") == "error":
        head = f"<p class=err>Stopped: {app.esc(job.get('error'))}</p>"
    elif res:
        head = f"<p class=muted>Last run {app.esc(res.get('when', ''))} with {app.esc(res.get('model', ''))}{'' if res.get('complete') else ' (incomplete)'}.</p>"
    else:
        head = "<p class=muted>Not run yet for this client.</p>"
    agree = differ = new = 0
    rows = []
    for key, text, how, cur, came in qs:
        a = ans.get(key)
        if not a:
            verdict, ai_cell = "", "<span class=muted>-</span>"
        elif not a["answer"] or a.get("confidence") == "none":
            verdict, ai_cell = "<span class=tag>not in documents</span>", "<span class=muted>no answer found</span>"
        else:
            if not cur.strip():
                verdict, new = "<span class='tag sug'>AI filled a blank</span>", new + 1
            elif _norm(cur) == _norm(a["answer"]):
                verdict, agree = "<span class='tag you'>agrees</span>", agree + 1
            else:
                verdict, differ = "<span class='tag need'>check: differs</span>", differ + 1
            ai_cell = (f"<b>{app.esc(a['answer'])}</b> <span class=muted>({app.esc(a.get('confidence', ''))})</span>"
                       f"<div class=muted style='margin-top:4px;font-style:italic'>&ldquo;{app.esc(a.get('source', ''))}&rdquo;</div>")
        value = cur if cur.strip() else (a or {}).get("answer", "")
        field = f"<input type=text name=\"q_{app.esc(key)}\" value=\"{app.esc(value)}\">"
        rows.append(f"<tr><td style='width:30%'>{app.esc(text)}<br><span class=muted>{app.esc(how)}</span></td>"
                    f"<td style='width:34%'>{ai_cell}</td><td>{field}<div style='margin-top:4px'>{verdict}</div></td></tr>")
    summary = (f"<div class=kpis><div class=kpi><div class=l>Agree</div><div class=v>{agree}</div><div class=s>AI matches the current answer</div></div>"
               f"<div class=kpi><div class=l>Differ</div><div class=v>{differ}</div><div class=s>check these before filing</div></div>"
               f"<div class=kpi><div class=l>Blanks filled</div><div class=v>{new}</div><div class=s>taken from the documents</div></div></div>") if ans else ""
    body = f"""{refresh}<div class=phead><h1>Local AI check: {app.esc(name)}</h1><p>Answers read from last year's filed forms and the reports in the client folder, with the line each one came from.</p></div>
{summary}<div class=card><h2>Run</h2>{head}
<form method=post action=/ai/run style="display:inline"><input type=hidden name=c value="{app.esc(name)}">
<button class=primary {'disabled' if running or not s['enabled'] else ''}>{'Run again' if res else 'Suggest answers with local AI'}</button></form>
<a class=btn href="/client?c={quote(name)}#s3">Back to the client</a>
{'' if s['enabled'] else ' <span class=warn>Local AI is off in <a href=/ai>settings</a>.</span>'}</div>
<div class=card><form method=post action=/app/answers><input type=hidden name=c value="{app.esc(name)}">
<table><tr><th>Question</th><th>AI answer and the line it used</th><th>Answer to save</th></tr>{''.join(rows)}</table>
<p><button class=primary>Save answers and rebuild</button> <span class=muted>Blanks take the AI's answer; nothing else changes unless you edit it.</span></p></form></div>"""
    return app.shell(f"Local AI: {name}", body, msg)


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
