"""Partner review: time each form took by hand against the time Form Filler took, per client and form.

Time by tool comes only from the fill logs the Chrome extension sends (clients/<c>/logs, ADT1/logs).
Time by hand is the firm's own figure, typed on this screen and kept in partner.json. Nothing is assumed:
a form with no hand figure, or no timed run, shows as such and is left out of the totals.
"""
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import app
import filing_queue

SETTINGS = app.ROOT / "partner.json"
KEYBOOK = app.ROOT / "Client name key.xlsx"
FORMS = [("adt-1", "ADT-1"), ("aoc4", "AOC-4"), ("mgt7a", "MGT-7A"), ("mgt7", "MGT-7")]
GAP = 180  # seconds: rounds closer than this belong to one run (the tool pauses 4 to 6 s between Saves)
DONE = ("filled", "unchanged")


def settings():
    try:
        s = json.loads(SETTINGS.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        s = {}
    s.setdefault("manual", {}).setdefault("adt-1", 9)  # the partner's figure, 24 Nov 2026; editable on the screen
    return s


def save_settings(s):
    SETTINGS.write_text(json.dumps(s, indent=1), encoding="utf-8")


def _t(iso):
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except Exception:  # noqa: BLE001
        return None


def runs(logs):
    """Group one form's fill rounds into runs. Each log: {"startedAt"?, "finishedAt", "counts"}.
    Returns [{"start", "end", "seconds", "timed", "rounds", "filled", "left"}], oldest first.
    timed is False when a round has no start time (logs from before 24 Nov 2026): the run is then measured
    from the first Save to the last, which leaves out the first section, so it reads as "at least"."""
    rows = []
    for d in logs:
        end = _t(d.get("finishedAt"))
        if not end:
            continue
        start = _t(d.get("startedAt"))
        rows.append((start or end, end, bool(start), d.get("counts") or {}))
    rows.sort(key=lambda r: r[1])
    out = []
    for start, end, timed, c in rows:
        filled = int(c.get("filled") or 0)
        left = sum(int(c.get(k) or 0) for k in ("manual", "failed", "hidden"))
        last = out[-1] if out else None
        if last and (start - last["end"]).total_seconds() <= GAP:
            last["end"] = end
            last["timed"] = last["timed"] and timed
            last["rounds"] += 1
            last["filled"] += filled
            last["left"] = left
        else:
            out.append({"start": start, "end": end, "timed": timed, "rounds": 1, "filled": filled, "left": left})
    for r in out:
        r["seconds"] = int((r["end"] - r["start"]).total_seconds())
    return out


def _read(folder, pattern):
    out = []
    for p in sorted(Path(folder).glob(pattern)) if Path(folder).exists() else []:
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001
            continue
    return out


def best(rs):
    """The run to show: the latest one that filled something and took measurable time."""
    good = [r for r in rs if r["filled"] and r["seconds"] > 0]
    return good[-1] if good else None


def rows():
    """One row per client and form that has a fill log or a queue job."""
    jobs = filing_queue.load().get("jobs", [])
    out = []
    for d in sorted(p for p in (app.ROOT / "clients").glob("*") if p.is_dir()) if (app.ROOT / "clients").exists() else []:
        logs = _read(d / "logs", "fill_*.json")
        for slug, label in FORMS:
            mine = [x for x in logs if x.get("slug") == slug]
            j = next((x for x in reversed(jobs) if x["client"] == d.name and x["slug"] == slug), None)
            if not mine and not j:
                continue
            out.append({"client": d.name, "slug": slug, "form": label, "run": best(runs(mine)), "runs": len(runs(mine)), "job": j})
    by_co = {}
    for x in _read(app.ROOT / "ADT1" / "logs", "fill_adt*.json"):
        by_co.setdefault(str(x.get("client") or "ADT-1 company"), []).append(x)
    for name, logs in sorted(by_co.items()):
        out.append({"client": name, "slug": "adt-1", "form": "ADT-1", "run": best(runs(logs)), "runs": len(runs(logs)), "job": None})
    return out


def codes():
    """{client folder or name: 'Client name N'} from the key workbook kept beside the app (never in the repo)."""
    if not KEYBOOK.exists():
        return {}
    try:
        import openpyxl
        ws = openpyxl.load_workbook(KEYBOOK, read_only=True, data_only=True).worksheets[0]
        out = {}
        for r in ws.iter_rows(min_row=2, values_only=True):
            if r and r[0] is not None:
                for v in r[1:]:
                    if v:
                        out[str(v).strip().lower()] = f"Client name {r[0]}"
        return out
    except Exception:  # noqa: BLE001
        return {}


_PLAIN = {"private", "pvt", "pvt.", "limited", "ltd", "ltd.", "llp", "and", "&", "co", "co.", "company", "india", "opc", "(opc)", "(india)", "(p)", "p"}


def mask(name):
    """Client name partly hidden: first two letters of each word stay, the rest become dots; words like Private Limited stay."""
    out = []
    for w in str(name).replace("_", " ").split():
        if w.lower() in _PLAIN or len(w) <= 2:
            out.append(w)
        else:
            out.append(w[:2] + "".join("\u2022" if c.isalnum() else c for c in w[2:]))
    return " ".join(out)


def dur(sec):
    if sec is None:
        return ""
    m, s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    return f"{h} h {m} min" if h else f"{m} min {s:02d} s" if m else f"{s} s"


def page(msg="", names=False):
    import ff_ui as ui
    s = settings()
    manual = {k: v for k, v in s["manual"].items() if isinstance(v, (int, float)) and v > 0}
    data = rows()
    hand = tool = n = 0
    untimed = 0
    trs = []
    extra = {}
    for r in data:
        run, m = r["run"], manual.get(r["slug"])
        shown = r["client"] if names else mask(r["client"])
        j = r["job"] or {}
        st = {"submitted": ("Filed, SRN " + j.get("srn", "") if j.get("paid") else "Submitted: check and pay", "good" if j.get("paid") else "need"),
              "saved": ("Draft saved", "need"), "held": (j.get("note") or "Needs attention", "badt"), "filling": ("Filling now", "work"),
              "queued": ("Waiting", ""), "skipped": ("Skipped", "")}.get(j.get("status"), ("Filled outside the queue" if run else "", ""))
        by_tool = "<span class=mut>No timed run yet</span>"
        saved = ""
        if run:
            by_tool = ("" if run["timed"] else "at least ") + dur(run["seconds"])
            by_tool += f"<div class=mut>{ui.when(run['end'].astimezone().replace(tzinfo=None).isoformat())}, {run['rounds']} Save{'s' if run['rounds'] != 1 else ''}</div>"
            untimed += 0 if run["timed"] else 1
            if m:
                diff = m * 60 - run["seconds"]
                saved = f"{dur(diff)}<div class=mut>{round(100 * diff / (m * 60))}% less</div>" if diff > 0 else "None"
                hand += m * 60
                tool += run["seconds"]
                n += 1
        appr = j.get("approved")
        act = ""
        if appr:
            act = f"<div class=mut>Approved for payment by {ui.esc(appr.get('by') or 'partner')}, {ui.when(appr.get('at', ''))}</div>"
        elif j.get("status") in ("submitted", "saved"):
            act = (f"<form method=post action=/ff/partner/approve data-who=need style=\"margin-top:6px\"><input type=hidden name=id value={j['id']}>"
                   f"<button class=sm>Approve for payment</button></form>")
        trs.append(f"<tr><td>{ui.esc(shown)}</td><td>{r['form']}</td><td class=n>{f'{m:g} min' if m else '<span class=mut>Enter below</span>'}</td>"
                   f"<td class=n>{by_tool}</td><td class=n>{saved}</td><td class=n>{run['filled'] if run else ''}</td>"
                   f"<td class=n>{run['left'] if run else ''}</td><td>{ui.tag(st[0][:70], st[1]) if st[0] else ''}{act}</td></tr>")

    def tile(label, value, sub=""):
        return (f"<div class=card style=\"margin:0\"><div class=mut>{label}</div><div style=\"font-size:24px;font-weight:600;margin-top:4px\">{value}</div>"
                f"<div class=mut>{sub}</div></div>")
    tiles = ("<div style=\"display:grid;grid-template-columns:repeat(4,1fr);gap:24px;margin-bottom:24px\">"
             + tile("Forms with both times", n, f"of {len(data)} on this screen")
             + tile("By hand", dur(hand) if n else "-", "the firm's usual time per form")
             + tile("By Compliance Copilot", dur(tool) if n else "-", "from the fill logs")
             + tile("Time saved", dur(hand - tool) if n and hand > tool else "-", f"{round(100 * (hand - tool) / hand)}% less" if n and hand > tool else "")
             + "</div>")
    inputs = "".join(f"<label class=mut style=\"display:flex;gap:6px;align-items:center\">{lab}"
                     f"<input type=number min=0 step=0.5 name=\"m_{slug}\" value=\"{manual.get(slug, '')}\" style=\"width:80px;height:32px\" aria-label=\"{lab} minutes by hand\"> min</label>"
                     for slug, lab in FORMS)
    form = (f"<div class=card><div class=h>Usual time by hand, per form</div><p class=mut style=\"margin:0 0 8px\">The firm's own figure for one form typed by staff. "
            f"A form with no figure stays out of the totals.</p><form method=post action=/ff/partner/manual class=row style=\"gap:16px;flex-wrap:wrap;align-items:center\">"
            f"{inputs}<button class=sm>Save</button></form></div>")
    note = ("<p class=mut>Time by tool is the latest run that filled the form, from the first field to the last Save, as logged by the Chrome extension. "
            "Login, captcha, DSC and payment are done by staff and are not in either figure."
            + (f" {untimed} run{'s' if untimed != 1 else ''} from before 24 Nov 2026 carry no start time and show as \"at least\"." if untimed else "") + "</p>")
    table = ("<div class=card><table><tr><th>Client</th><th>Form</th><th class=n>By hand</th><th class=n>By Compliance Copilot</th><th class=n>Saved</th>"
             "<th class=n>Fields filled</th><th class=n>Left for staff</th><th>Status</th></tr>" + "".join(trs) + "</table></div>") if trs else \
        "<div class=card>No form has been filled yet. Times appear here after the first run on MCA.</div>"
    toggle = (f"<a class=btn href=\"/partner{'?names=1' if not names else ''}\">{'Show full client names' if not names else 'Mask client names'}</a>")
    body = ui.head("Partner review", "Time saved, form by form", toggle) + tiles + table + note + form
    return ui.shell("Partner review", body, "/partner", msg)


def post(path, form, user=""):
    """(status, body, content type, location)."""
    back = lambda m: (303, "", "text/html", f"/partner?msg={quote(m)}")  # noqa: E731
    if path == "/ff/partner/manual":
        s = settings()
        for slug, _ in FORMS:
            v = (form.get(f"m_{slug}") or "").strip()
            try:
                s["manual"][slug] = float(v) if v else None
            except ValueError:
                return back(f"Not saved: '{v}' is not a number of minutes.")
        save_settings(s)
        return back("Time by hand saved.")
    if path == "/ff/partner/approve":
        q = filing_queue.load()
        j = next((x for x in q["jobs"] if str(x["id"]) == str(form.get("id"))), None)
        if not j:
            return back("That form is no longer in the queue.")
        j["approved"] = {"by": user or "partner", "at": datetime.now().isoformat(timespec="seconds")}
        filing_queue.save(q)
        filing_queue._audit(j, "Approved for payment on the partner review screen", by=user or "partner")
        return back(f"{app.FORM_LABEL.get(j['slug'], j['slug'])} approved for payment. Payment itself is made by staff on MCA.")
    return back("")
