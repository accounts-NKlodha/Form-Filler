"""GST annual returns in Form Filler: /gst (one row per GSTIN), /gst/client (files, checks, review points) and the
small JSON API the "GST portal reader" Chrome extension talks to (/gst/api/...).

The app reads portal files and checks them. It never logs in, saves, submits, files or pays on the GST portal.
"""
import json
import secrets
from decimal import Decimal
from html import escape
from urllib.parse import quote

import app
import ff_audit
import ff_ui
from gst import portal, work

TOKEN = secrets.token_urlsafe(18)   # new on every start; a web page cannot read it, so it cannot post files here
work._trail = lambda folder, text, by, **data: ff_audit.event(folder, "gst", text, by=by or "staff", **data)


def esc(s):
    return escape(str(s if s is not None else ""), quote=True)


def money(x):
    """Indian digit grouping, two decimals: 1234567.5 -> 12,34,567.50"""
    x = Decimal(x).quantize(Decimal("0.01"))
    sign, (whole, frac) = ("-" if x < 0 else ""), ("%.2f" % abs(x)).split(".")
    if len(whole) > 3:
        head, tail, parts = whole[:-3], whole[-3:], []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        whole = ",".join(([head] if head else []) + parts + [tail])
    return sign + whole + "." + frac


def _fy(q):
    fy = q.get("fy") or work.default_fy()
    return fy if work.valid_fy(fy) else work.default_fy()


def _reg(q):
    """(client folder, GSTIN) from c= and g=, or raise ValueError."""
    folder, g = app.folder_of(q.get("c", "")), (q.get("g") or "").upper()
    if not work.GSTIN.match(g) or not (folder / "gst" / g).is_dir():
        raise ValueError("No such GSTIN for this client.")
    return folder, g


def _link(folder, g, fy, **more):
    qs = "c=%s&g=%s&fy=%s" % (quote(folder.name), g, fy) + "".join("&%s=%s" % (k, quote(str(v))) for k, v in more.items() if v)
    return "/gst/client?" + qs


# ---------------------------------------------------------------- pages
def page_list(fy, msg=""):
    regs = work.registrations(app.CLIENTS)
    rows = []
    for folder, g in regs:
        st = work.status(folder, g, fy)
        need = ff_ui.tag("%d check%s" % (st["needs"], "" if st["needs"] == 1 else "s"), "need") if st["needs"] else "<span class=mut>None</span>"
        pts = (ff_ui.tag("%d open" % st["open"], "need") if st["open"] else ff_ui.tag("All cleared", "good")) if st["points"] else "<span class=mut>None</span>"
        rows.append(f"<tr><td><a href=\"{_link(folder, g, fy)}\">{esc(folder.name)}</a></td><td>{g}</td>"
                    f"<td class=n>{st['files']}</td><td>{need}</td><td>{pts}</td></tr>")
    table = ("<table><thead><tr><th>Client</th><th>GSTIN</th><th class=n>Portal files read</th><th>Needs input</th><th>Review points</th></tr></thead>"
             f"<tbody>{''.join(rows)}</tbody></table>") if rows else \
        "<p class=mut>No GSTIN yet. Add the first one on the right; the extension can then file the portal downloads under it.</p>"
    names = "".join(f"<option value=\"{esc(p.name)}\">" for p in ff_ui.clients())
    add = (f"<form method=post action=/gst/add style=\"display:flex;flex-direction:column;gap:12px\"><input type=hidden name=fy value={fy}>"
           f"<label class=f>Client<input type=text name=c list=gst-clients required placeholder=\"Pick or type a new client\"></label><datalist id=gst-clients>{names}</datalist>"
           "<label class=f>GSTIN<input type=text name=gstin required maxlength=15 placeholder=\"15 characters\"></label>"
           "<div><button class=p>Add GSTIN</button></div></form>")
    y0 = int(work.default_fy()[:4])
    years = "".join(f"<a href=\"/gst?fy={y}\">{ff_ui.tag(y, 'need' if y == fy else '')}</a>" for y in ("%d-%02d" % (a, (a + 1) % 100) for a in (y0, y0 - 1, y0 - 2)))
    body = (ff_ui.head("GST", f"Annual returns, FY {fy}", f"<div class=filters>{years}</div>")
            + f"<div class=g12><div class=\"card s8\"><div class=h>GSTR-9 and GSTR-9C, one row per GSTIN</div>{table}</div>"
            f"<div class=s4 style=\"display:flex;flex-direction:column;gap:24px\"><div class=card><div class=h>Add a GSTIN</div>{add}</div>"
            "<div class=card><div class=h>Chrome extension: GST portal reader</div>"
            "<p style=\"margin:0 0 8px\">Staff log in to the GST portal themselves and open the Returns dashboard. The extension then reads the year's "
            "GSTR-1, 2A, 2B and 3B and files them in the client folder.</p>"
            "<p class=mut style=\"margin:0\">It only reads. It never saves, submits, files or pays on the portal. "
            "Load it once in Chrome from the folder <b>extension_gst</b> (chrome://extensions, Developer mode, Load unpacked).</p></div></div></div>"
            "<p class=mut style=\"margin:0\">Checks against the books in Tally, the GSTR-9 and 9C preview and the JSON for upload are the next steps of this build.</p>")
    return ff_ui.shell("GST annual returns", body, "/gst", msg)


def page_client(folder, g, fy, check="", msg=""):
    st = work.status(folder, g, fy)
    mon = portal.months(fy)
    th = "".join(f"<th title=\"{portal.month_name(p)}\">{portal.month_name(p)[:3]}</th>" for p in mon)
    cov = ""
    for k in st["coverage"]:
        cells = "".join(f"<td title=\"{portal.month_name(p)}\">{'<span class=ok aria-label=found>&#10003;</span>' if has else '<span class=mut aria-label=missing>-</span>'}</td>"
                        for p, has in k["months"])
        cov += f"<tr><td>{esc(k['label'])}</td>{cells}<td class=mut>{'%d of 7' % k['next_found'] if k['next_found'] is not None else ''}</td></tr>"
    up = ("<label class=\"btn sm pick\">Add portal files<input type=file id=gst-up multiple accept=\".json,.zip\"></label>"
          "<span class=mut id=gst-upmsg>JSON or zip, any name: files are recognised by what is inside, and checked for GSTIN and year.</span>")
    files = (f"<div class=card><div class=h>Portal files, FY {fy}: {st['files']} read</div>"
             f"<table><thead><tr><th>Return</th>{th}<th>Apr to Oct next year</th></tr></thead><tbody>{cov}</tbody></table>"
             f"<div class=row style=\"margin-top:16px;align-items:center\">{up}</div>"
             f"<p class=mut style=\"margin:12px 0 0\">Folder: {esc(str(work.area(folder, g, fy) / 'portal'))}</p></div>")
    left = "".join(f"<tr><td>{esc(f)}</td><td>{esc(why)}</td></tr>" for f, why in st["problems"])
    if left:
        files += f"<div class=card><div class=h>Files left out</div><table><tbody>{left}</tbody></table></div>"
    rows = ""
    for k in st["checks"]:
        if k["state"] == "needs":
            state = ff_ui.tag("Needs input", "badt")
        elif k["cleared"]:
            state = ff_ui.tag("Cleared", "good") + f" <span class=mut>{esc(k['cleared']['by'])}</span>"
        elif k["state"] == "point":
            state = ff_ui.tag("Review point", "need") + (f" <span class=mut>{k['gaps']} months</span>" if k["gaps"] else "")
        else:
            state = ff_ui.tag("Ties", "good")
        a, b, d = (money(k["total_a"]), money(k["total_b"]) if k["b_label"] else "", money(k["diff"])) if k["rows"] else ("", "", "")
        rows += (f"<tr class=\"click{' sel' if k['id'] == check else ''}\" onclick=\"location='{_link(folder, g, fy, check=k['id'])}#detail'\">"
                 f"<td><a href=\"{_link(folder, g, fy, check=k['id'])}#detail\" style=\"font-weight:500;text-decoration:none;color:inherit\">{esc(k['title'])}</a>"
                 f"<div class=mut>{esc(k['area'])} · GSTR-9 table {esc(k['ref'])}</div></td><td class=n>{a}</td><td class=n>{b}</td><td class=n>{d}</td><td>{state}</td></tr>")
    chk = ("<div class=card><div class=h>Checks, month by month and for the year. A gap above Rs 1 is a review point.</div>"
           "<table><thead><tr><th>Check</th><th class=n>First source</th><th class=n>Second source</th><th class=n>Difference</th><th>State</th></tr></thead>"
           f"<tbody>{rows}</tbody></table></div>")
    k = next((k for k in st["checks"] if k["id"] == check), None)
    script = """<script>(()=>{const i=document.getElementById('gst-up'),m=document.getElementById('gst-upmsg');if(!i)return;
i.addEventListener('change',async()=>{const out=[];let u='';try{u=localStorage.getItem('ff_user')||''}catch(e){}
for(const f of i.files){m.textContent='Reading '+f.name+'...';try{const r=await fetch('/gst/upload?t=%s&c=%s&g=%s&fy=%s&user='+encodeURIComponent(u),{method:'POST',body:f});
const j=await r.json();out.push(f.name+': '+(j.error||(j.label+' '+j.month+', '+j.state)))}catch(e){out.push(f.name+': could not be sent')}}
location='%s&msg='+encodeURIComponent(out.join('\\n'))})})();</script>""" % (TOKEN, quote(folder.name), g, fy, _link(folder, g, fy))
    body = (ff_ui.head(f"<a href=\"/gst?fy={fy}\">GST annual returns</a> / {g} / FY {fy}", folder.name)
            + files + chk + (_detail(folder, g, fy, k) if k else "") + script)
    return ff_ui.shell(folder.name + " GST", body, "/gst", msg)


def _detail(folder, g, fy, k):
    rows = ""
    for r in k["rows"]:
        gap = abs(r["diff"]) > Decimal("1")
        rows += (f"<tr><td>{esc(r['month'])}</td><td class=n>{money(r['a'])}</td><td class=n>{money(r['b']) if k['b_label'] else ''}</td>"
                 f"<td class=n{' style=font-weight:600' if gap else ''}>{money(r['diff'])}</td></tr>")
    if k["rows"]:
        rows += (f"<tr class=total><td>Year</td><td class=n>{money(k['total_a'])}</td><td class=n>{money(k['total_b']) if k['b_label'] else ''}</td>"
                 f"<td class=n>{money(k['diff'])}</td></tr>")
    notes = (["Missing: %s." % esc(k["missing"])] if k["missing"] else []) + \
        (["The months differ but the year ties: a timing gap."] if k["timing"] else []) + ([esc(k["note"])] if k["note"] else [])
    hid = (f"<input type=hidden name=c value=\"{esc(folder.name)}\"><input type=hidden name=g value={g}><input type=hidden name=fy value={fy}>"
           f"<input type=hidden name=check value=\"{esc(k['id'])}\">")
    if k["cleared"]:
        r = k["cleared"]
        side = (f"<p style=\"margin:0 0 12px\">Cleared by {esc(r['by'])}, {ff_ui.when(r['at'])}: {esc(r['note'])} <span class=mut>({esc(r['treatment'])})</span></p>"
                f"<form method=post action=/gst/reopen data-who=need>{hid}<button class=sm>Re-open this point</button></form>")
    elif k["state"] == "point":
        opts = "".join(f"<option>{esc(t)}</option>" for t in work.TREATMENTS)
        side = (f"<form method=post action=/gst/clear data-who=need style=\"display:flex;flex-direction:column;gap:12px\">{hid}"
                "<label class=f>Reason for clearing<textarea name=note rows=3 required></textarea></label>"
                f"<label class=f>Treatment in the return<select name=treatment>{opts}</select></label>"
                "<div><button class=p>Clear point</button></div><span class=mut>Who, when and the reason are kept in the client's audit trail.</span></form>")
    else:
        side = "<p class=mut style=\"margin:0\">Nothing to clear.</p>"
    return (f"<div class=g12 id=detail><div class=\"card s8\"><div class=h>{esc(k['title'])} · GSTR-9 table {esc(k['ref'])}</div>"
            f"<table><thead><tr><th>Month</th><th class=n>{esc(k['a_label'])}</th><th class=n>{esc(k['b_label'])}</th><th class=n>Difference</th></tr></thead>"
            f"<tbody>{rows}</tbody></table><p style=\"margin:12px 0 0\">{' '.join(notes)}</p></div><div class=\"card s4\"><div class=h>Review</div>{side}</div></div>")


# ---------------------------------------------------------------- routes (called from ff_ui)
def _j(code, obj):
    return code, json.dumps(obj, default=str), "application/json"


def handle_get(path, q):
    fy, msg = _fy(q), q.get("msg", "")
    if path == "/gst":
        return 200, page_list(fy, msg), "text/html"
    if path == "/gst/client":
        try:
            folder, g = _reg(q)
        except ValueError as e:
            return 404, ff_ui.shell("GST", ff_ui.head("GST", "Not found") + f"<p>{esc(e)} <a href=/gst>Back to GST</a></p>", "/gst"), "text/html"
        return 200, page_client(folder, g, fy, q.get("check", ""), msg), "text/html"
    if path == "/gst/api/clients":   # the extension starts here
        return _j(200, dict(app="Form Filler", fy=fy, token=TOKEN, months=portal.months(fy), next_months=portal.next_months(fy),
                            clients=[dict(name=f.name, gstin=g) for f, g in work.registrations(app.CLIENTS)]))
    if path == "/gst/api/status":
        reg = _by_gstin(q.get("gstin"))
        if not reg:
            return _j(404, dict(error="GSTIN %s is not in Form Filler yet. Add it on the GST page first." % (q.get("gstin") or "(none)")))
        data, _ = work.load(reg[0], reg[1], fy)
        return _j(200, dict(client=reg[0].name, gstin=reg[1], fy=fy, months=portal.months(fy), next_months=portal.next_months(fy),
                            have={k: sorted(v) for k, v in data.items()}))
    return 404, "not found", "text/plain"


def _by_gstin(gstin):
    g = (gstin or "").upper()
    return next(((f, x) for f, x in work.registrations(app.CLIENTS) if x == g), None)


def _ingest(folder, g, fy, body, user, source):
    try:
        r = work.ingest(folder, g, fy, body, user, source)
    except ValueError as e:
        return _j(422, dict(error=str(e))) + (None,)
    return _j(200, dict(r, label=portal.LABEL[r["kind"]], month=portal.month_name(r["period"]), client=folder.name)) + (None,)


def handle_post(path, q, body, form):
    try:
        return _post(path, q, body, form)
    except Exception as e:  # noqa: BLE001  a GST fault must never take the MCA screens down
        if path.startswith("/gst/api/") or path == "/gst/upload":
            return _j(500, dict(error="Form Filler error: %s" % e)) + (None,)
        return 303, "", "text/html", "/gst?msg=%s" % quote("Could not do that: %s" % e)


def _post(path, q, body, form):
    fy = _fy(dict(q, **{k: v for k, v in form.items() if k == "fy"}))
    user = (form.get("user") or q.get("user") or "").strip()[:60]
    if path in ("/gst/upload", "/gst/api/ingest"):
        if q.get("t") != TOKEN:
            return _j(403, dict(error="Form Filler was restarted: reload and try again.")) + (None,)
        if path == "/gst/upload":
            try:
                folder, g = _reg(q)
            except ValueError as e:
                return _j(404, dict(error=str(e))) + (None,)
            return _ingest(folder, g, fy, body, user, "added by staff")
        try:   # the extension does not say whose file it is: the file does
            g = portal.read(body)["gstin"]
        except portal.Unrecognised as e:
            return _j(422, dict(error=str(e))) + (None,)
        reg = _by_gstin(g)
        if not reg:
            return _j(404, dict(error="GSTIN %s is not in Form Filler yet. Add it on the GST page first." % g)) + (None,)
        return _ingest(reg[0], reg[1], fy, body, user, "GST portal, browser extension")
    if path == "/gst/add":
        try:
            folder = app.folder_of(form.get("c", ""))
            folder.mkdir(parents=True, exist_ok=True)
            g = work.add_registration(folder, form.get("gstin", ""), user)
        except ValueError as e:
            return 303, "", "text/html", "/gst?fy=%s&msg=%s" % (fy, quote(str(e) if "GSTIN" in str(e) else "Type the client name."))
        return 303, "", "text/html", _link(folder, g, fy)
    if path in ("/gst/clear", "/gst/reopen"):
        try:
            folder, g = _reg(form)
            if path == "/gst/clear":
                work.clear_point(folder, g, fy, form.get("check", ""), user, form.get("note", ""), form.get("treatment", ""))
            else:
                work.reopen_point(folder, g, fy, form.get("check", ""), user)
        except ValueError as e:
            return 303, "", "text/html", "/gst?fy=%s&msg=%s" % (fy, quote(str(e))) if "No such" in str(e) else \
                _link(app.folder_of(form.get("c", "")), form.get("g", ""), fy, check=form.get("check", ""), msg=str(e)) + "#detail"
        return 303, "", "text/html", _link(folder, g, fy, check=form.get("check", "")) + "#detail"
    return 404, "not found", "text/plain", None
