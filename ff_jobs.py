"""Agent queue: background jobs the agent runs one after another, with an activity log.

    agent_jobs.json  {"jobs": [{id, client, kind, status, now, started, updated, error}], "next_id", "paused"}

Kinds:
    get_data   read this year's and last year's trial balance from Tally, build the Schedule III workbook,
               then prepare the MCA inputs workbook (questions and form values)
    build      build the Schedule III workbook again from the stored trial balances (after mapping changes)
    docs       draft the board's report, auditor's report and meeting papers

Filing jobs (fill and save on MCA) stay in filing_queue.py, because the Chrome extension drives them;
the Agent queue screen shows both lists together.
Status: queued, working, staff (stopped for a person), done, failed.
"""
import json
import threading
import time
import traceback
from datetime import datetime

import app
import ff_audit

JOBS = app.ROOT / "agent_jobs.json"
LOCK = threading.RLock()
KINDS = {"get_data": "Get data", "build": "Build financials", "docs": "Reports and meeting papers"}
_worker = None


def load():
    with LOCK:
        try:
            q = json.loads(JOBS.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            q = {}
        q.setdefault("jobs", [])
        q.setdefault("next_id", 1)
        q.setdefault("paused", False)
        return q


def save(q):
    with LOCK:
        tmp = JOBS.with_suffix(".tmp")
        tmp.write_text(json.dumps(q, indent=1), encoding="utf-8")
        tmp.replace(JOBS)


def _now():
    return datetime.now().isoformat(timespec="seconds")


def add(client, kind, user="staff"):
    """Queue a job unless the same one is already waiting or running. Returns the job id or None."""
    with LOCK:
        q = load()
        if any(j["client"] == client and j["kind"] == kind and j["status"] in ("queued", "working") for j in q["jobs"]):
            return None
        j = {"id": q["next_id"], "client": client, "kind": kind, "status": "queued", "now": "Next in line",
             "added": _now(), "started": "", "updated": _now(), "by": user}
        q["jobs"].append(j)
        q["next_id"] += 1
        save(q)
    ff_audit.event(app.folder_of(client), "job", f"{KINDS.get(kind, kind)} queued", by=user)
    kick()
    return j["id"]


def _set(jid, **kw):
    with LOCK:
        q = load()
        for j in q["jobs"]:
            if j["id"] == jid:
                j.update(kw, updated=_now())
        save(q)


def retry(jid):
    _set(jid, status="queued", now="Next in line", error="")
    kick()


def remove(jid):
    with LOCK:
        q = load()
        q["jobs"] = [j for j in q["jobs"] if not (j["id"] == jid and j["status"] != "working")]
        save(q)


def pause(on=True):
    with LOCK:
        q = load()
        q["paused"] = on
        save(q)
    if not on:
        kick()


def clear_done():
    with LOCK:
        q = load()
        q["jobs"] = [j for j in q["jobs"] if j["status"] not in ("done",)]
        save(q)


# ---------------------------------------------------------------- the runner

def kick():
    """Start the worker thread if it is not running."""
    global _worker
    if _worker and _worker.is_alive():
        return
    _worker = threading.Thread(target=_run, name="ff-agent", daemon=True)
    _worker.start()


def _next():
    with LOCK:
        q = load()
        if q["paused"]:
            return None
        j = next((x for x in q["jobs"] if x["status"] == "queued"), None)
        if j:
            j.update(status="working", started=_now(), updated=_now(), now="Starting")
            save(q)
        return j


def _run():
    while True:
        j = _next()
        if not j:
            return
        try:
            outcome = RUN[j["kind"]](j)
            status, now = outcome if isinstance(outcome, tuple) else ("done", outcome)
            _set(j["id"], status=status, now=now)
        except StaffNeeded as e:
            _set(j["id"], status="staff", now=str(e))
            ff_audit.event(app.folder_of(j["client"]), "job", f"{KINDS.get(j['kind'])} stopped: {e}", by="agent")
        except Exception as e:  # noqa: BLE001
            _set(j["id"], status="failed", now=str(e)[:200], error=traceback.format_exc()[-1500:])
            ff_audit.event(app.folder_of(j["client"]), "job", f"{KINDS.get(j['kind'])} failed: {e}", by="agent")
        time.sleep(0.2)


class StaffNeeded(Exception):
    """The job cannot go on without a person (Tally company not open, file locked in Excel...)."""


def _tally_error(e, company):
    s = str(e)
    if "10061" in s or "refused" in s.lower() or "timed out" in s.lower() or "unreachable" in s.lower():
        return StaffNeeded("Tally is not answering on port 9000: start Tally with the XML server on")
    if "no ledgers" in s.lower():
        return StaffNeeded(f"Open '{company}' in Tally")
    return e


def run_get_data(j):
    import ff_fin
    folder = app.folder_of(j["client"])
    cfg = ff_fin.load_cfg(folder)
    for which, label in (("tb_cy", "this year"), ("tb_py", "last year")):
        company = cfg.get("tally_company_cy" if which == "tb_cy" else "tally_company_py") or folder.name
        _set(j["id"], now=f"Reading {label} from Tally ('{company}')")
        try:
            n = ff_fin.pull(folder, which, company, user="agent")
        except Exception as e:  # noqa: BLE001
            if which == "tb_py" and (ff_fin.work_dir(folder) / "tb_py.csv").exists():
                ff_audit.event(folder, "tally", f"Last year's company not read ({e}); the stored copy is used", by="agent")
                continue
            raise _tally_error(e, company)
        _set(j["id"], now=f"Read {n} ledgers for {label}")
    return run_build(j)


def run_build(j):
    import ff_fin
    folder = app.folder_of(j["client"])
    _set(j["id"], now="Building Schedule III (about a minute)")
    st = ff_fin.build(folder, user="agent")
    if st["state"] != "done":
        raise RuntimeError(st.get("error") or "build failed")
    f = app.load(folder)
    if any(s in app.SMART for s in f.get("forms") or []):
        _set(j["id"], now="Preparing the form values and questions")
        try:
            app.build(folder)
        except PermissionError as e:
            raise StaffNeeded(str(e))
        except Exception as e:  # noqa: BLE001
            ff_audit.event(folder, "questions", f"Form values not prepared: {e}", by="agent")
    n = len(ff_fin.open_points(folder))
    ff_audit.event(folder, "job", f"Financials ready with {n} review points", by="agent")
    return ("staff", f"{n} review points for staff") if n else ("done", "Financials ready, no open points")


def run_docs(j):
    import ff_fin
    folder = app.folder_of(j["client"])
    _set(j["id"], now="Drafting reports and meeting papers")
    out, flags = ff_fin.make_docs(folder)
    return ("done", f"Drafted in {out.name}, {len(flags)} points to check")


RUN = {"get_data": run_get_data, "build": run_build, "docs": run_docs}


def recover():
    """At server start: jobs left 'working' by a stopped server go back in the queue."""
    with LOCK:
        q = load()
        changed = False
        for j in q["jobs"]:
            if j["status"] == "working":
                j.update(status="queued", now="Restarted after the server stopped")
                changed = True
        if changed:
            save(q)
    if any(j["status"] == "queued" for j in load()["jobs"]):
        kick()
