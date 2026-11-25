"""The GST work area inside a client folder, and what is recorded there.

    clients/<Client>/gst/<GSTIN>/<FY>/portal/<kind>/GST_<GSTIN>_<FY>_<KIND>_<MMYYYY>.json|zip   files as they came off the portal
    clients/<Client>/gst/<GSTIN>/<FY>/portal/_manifest.json                                     file, size, SHA-256, who, when, how
    clients/<Client>/gst/<GSTIN>/<FY>/review.json                                               cleared review points

A client's GSTINs are the folders under clients/<Client>/gst/. Files are read by content, so files copied in by hand
under portal/ (any name, any sub-folder) are picked up too.
"""
import datetime as dt
import hashlib
import json
import re
import threading
from pathlib import Path

from . import checks, portal, recon

GSTIN = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]Z[0-9A-Z]$")
FY = re.compile(r"^20[0-9]{2}-[0-9]{2}$")
TREATMENTS = ("No change, explain only", "Report in tables 10 to 13", "Pay through DRC-03", "Raise to partner")
SHORT = {"gstr3b": "GSTR3B", "gstr1_summary": "GSTR1SUM", "gstr1": "GSTR1", "gstr2a": "GSTR2A", "gstr2b": "GSTR2B"}
_cache, _lock = {}, threading.RLock()
_trail = None   # set by the app: trail(folder, text, by, **data)


def now():
    return dt.datetime.now().isoformat(timespec="seconds")


def default_fy(today=None):
    """The year whose annual return is being prepared: the financial year that ended last 31 March."""
    d = today or dt.date.today()
    y = d.year - (2 if d.month < 4 else 1)
    return "%d-%02d" % (y, (y + 1) % 100)


def valid_fy(fy):
    return bool(FY.match(fy or "")) and int(fy[5:]) == (int(fy[:4]) + 1) % 100


def registrations(clients_dir):
    """[(client folder, GSTIN)] for every client folder that has a gst/<GSTIN>/ folder."""
    out = []
    root = Path(clients_dir)
    for c in sorted(root.iterdir(), key=lambda p: p.name.lower()) if root.is_dir() else []:
        g = c / "gst"
        if c.name.startswith(("_", ".")) or not g.is_dir():
            continue
        out += [(c, p.name) for p in sorted(g.iterdir()) if p.is_dir() and GSTIN.match(p.name)]
    return out


def add_registration(client_folder, gstin, user=""):
    gstin = re.sub(r"\s", "", str(gstin or "")).upper()
    if not GSTIN.match(gstin):
        raise ValueError("That is not a GSTIN: it has 15 characters, like 33ABCDE1234F1Z5.")
    d = Path(client_folder) / "gst" / gstin
    if not d.is_dir():
        d.mkdir(parents=True)
        _log(client_folder, "GSTIN %s added for GST annual returns" % gstin, user)
    return gstin


def area(client_folder, gstin, fy):
    return Path(client_folder) / "gst" / gstin / fy


def _log(folder, text, by, **data):
    if _trail:
        _trail(folder, text, by, **data)


def _json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default
    except (ValueError, OSError):
        return default


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _read(p):
    """portal.read with a cache keyed on the file's size and time."""
    st = p.stat()
    key = (str(p), st.st_mtime_ns, st.st_size)
    with _lock:
        doc = _cache.get(key)
    if doc is None:
        try:
            doc = portal.read(p.read_bytes())
        except portal.Unrecognised as e:
            doc = dict(error=str(e))
        except OSError as e:
            doc = dict(error="Could not be read: %s" % e)
        with _lock:
            if len(_cache) > 4000:
                _cache.clear()
            _cache[key] = doc
    return doc


def _files(folder):
    for p in sorted(folder.rglob("*")) if folder.is_dir() else []:
        rel = p.relative_to(folder)
        if p.is_file() and p.suffix.lower() in (".json", ".zip") and not any(part.startswith("_") for part in rel.parts):
            yield p, rel


def ingest(client_folder, gstin, fy, raw, user, source="upload"):
    """Check one portal file and file it. Returns dict(kind, period, state, file); state is saved, same or replaced.
    Raises ValueError with a message for staff when the file is not for this GSTIN or this year."""
    try:
        doc = portal.read(raw)
    except portal.Unrecognised as e:
        raise ValueError(str(e))
    if doc["gstin"] != gstin:
        raise ValueError("This file is for GSTIN %s, not %s." % (doc["gstin"] or "(none)", gstin))
    kind, period = doc["kind"], doc["period"]
    nxt = period in portal.next_months(fy)
    if period not in portal.months(fy) and not nxt:
        raise ValueError("This %s is for %s, outside FY %s." % (portal.LABEL[kind], portal.month_name(period), fy))
    folder = area(client_folder, gstin, fy) / "portal"
    y = int(period[2:]) - (1 if int(period[:2]) < 4 else 0)
    name = "GST_%s_%d-%02d_%s_%s%s" % (gstin, y, (y + 1) % 100, SHORT[kind], period, ".zip" if raw[:2] == b"PK" else ".json")
    dest = folder / (kind + ("_next_year" if nxt else "")) / name
    sha = hashlib.sha256(raw).hexdigest()
    with _lock:
        state = "saved"
        old = [p for p, _ in _files(folder) if (_read(p).get("kind"), _read(p).get("period")) == (kind, period)]
        if any(hashlib.sha256(p.read_bytes()).hexdigest() == sha for p in old):
            return dict(kind=kind, period=period, state="same", file=name)
        for p in old + ([dest] if dest.exists() and dest not in old else []):   # keep what was there: every figure must stay traceable
            keep = folder / "_replaced" / ("%s_%s" % (dt.datetime.now().strftime("%Y%m%d-%H%M%S"), p.name))
            keep.parent.mkdir(parents=True, exist_ok=True)
            p.replace(keep)
            state = "replaced"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(raw)
        rel = dest.relative_to(folder).as_posix()
        man = _json(folder / "_manifest.json", [])
        man = [m for m in (man if isinstance(man, list) else []) if isinstance(m, dict) and m.get("file") != rel]
        man.append(dict(file=rel, kind=kind, period=period, bytes=len(raw), sha256=sha, source=source, by=user, at=now()))
        _write(folder / "_manifest.json", man)
    _log(client_folder, "%s for %s %s (%s)" % (portal.LABEL[kind], portal.month_name(period),
                                             "replaced" if state == "replaced" else "received", source), user, file=name, sha256=sha)
    return dict(kind=kind, period=period, state=state, file=name)


def load(client_folder, gstin, fy):
    """Everything under portal/, read by content. Returns (data, problems): data is {kind: {period: figures}};
    problems lists files that were left out and why."""
    folder = area(client_folder, gstin, fy) / "portal"
    data, problems = {}, []
    ok = portal.months(fy) + portal.next_months(fy)
    for p, rel in _files(folder):
        doc = _read(p)
        if "error" in doc:
            problems.append((rel.as_posix(), doc["error"]))
        elif doc["gstin"] != gstin:
            problems.append((rel.as_posix(), "For GSTIN %s, not this one." % doc["gstin"]))
        elif doc["period"] not in ok:
            problems.append((rel.as_posix(), "For %s, outside FY %s." % (portal.month_name(doc["period"]), fy)))
        else:
            data.setdefault(doc["kind"], {})[doc["period"]] = doc["figures"]
    return data, problems


def coverage(fy, data):
    """Per kind: which of the 12 months (and next-year months for 2B) are present."""
    out = []
    for kind in portal.KINDS:
        have = data.get(kind) or {}
        out.append(dict(kind=kind, label=portal.LABEL[kind], months=[(p, p in have) for p in portal.months(fy)],
                        found=sum(1 for p in portal.months(fy) if p in have),
                        next_found=sum(1 for p in portal.next_months(fy) if p in have) if kind in ("gstr2a", "gstr2b") else None))
    return out


def status(client_folder, gstin, fy):
    """Checks with their review state. A cleared point re-opens by itself when its figures change."""
    data, problems = load(client_folder, gstin, fy)
    cleared = _json(area(client_folder, gstin, fy) / "review.json", {}).get("cleared", {})
    results = checks.run(fy, data)
    for c in results:
        rec = cleared.get(c["id"])
        c["cleared"] = rec if rec and rec.get("sig") == c["sig"] and c["state"] == "point" else None
    return dict(data=data, problems=problems, coverage=coverage(fy, data), checks=results,
                open=sum(1 for c in results if c["state"] == "point" and not c["cleared"]),
                points=sum(1 for c in results if c["state"] == "point"),
                needs=sum(1 for c in results if c["state"] == "needs"),
                files=sum(len(v) for v in data.values()))


def inputs(client_folder, gstin, fy):
    """Files staff have put under books/<input>/ for the reconciliations: {input key: number of files}."""
    base = area(client_folder, gstin, fy) / "books"
    return {k: sum(1 for p in (base / k).iterdir() if p.is_file() and not p.name.startswith(("_", "~", ".")))
            for k, _, _ in recon.INPUTS if (base / k).is_dir()}


def clear_point(client_folder, gstin, fy, check_id, user, note, treatment):
    note = " ".join((note or "").split())
    if not (user or "").strip():
        raise ValueError("Type your name at the bottom left first: clearing a point is recorded against a person.")
    if len(note) < 10:
        raise ValueError("Write the reason for clearing this point (at least a short sentence).")
    if treatment not in TREATMENTS:
        raise ValueError("Choose the treatment in the return.")
    c = next((c for c in status(client_folder, gstin, fy)["checks"] if c["id"] == check_id and c["state"] == "point"), None)
    if not c:
        raise ValueError("This review point is no longer open.")
    p = area(client_folder, gstin, fy) / "review.json"
    with _lock:
        rev = _json(p, {})
        rev.setdefault("cleared", {})[check_id] = dict(sig=c["sig"], by=user, at=now(), note=note, treatment=treatment,
                                                       difference=str(c["diff"]))
        _write(p, rev)
    _log(client_folder, "GST review point cleared: %s. %s (%s)" % (c["title"], note, treatment), user, check=check_id, gstin=gstin, fy=fy)


def reopen_point(client_folder, gstin, fy, check_id, user):
    p = area(client_folder, gstin, fy) / "review.json"
    with _lock:
        rev = _json(p, {})
        if rev.get("cleared", {}).pop(check_id, None):
            _write(p, rev)
            _log(client_folder, "GST review point re-opened: %s" % check_id, user, check=check_id, gstin=gstin, fy=fy)
