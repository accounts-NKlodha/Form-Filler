"""MCA automation - Form Filler: the five screens on http://<this PC>:8742.

    1 Get data            /data      Tally this year + last year, batch over clients
    2 Review financials   /review    Schedule III with review points; "verified, okay to file" tick
    3 File on MCA         /file      filing queue for ticked clients (Chrome side panel does the portal work)
      Agent queue         /agents    every job and an activity log
      Audit trail         /audit     every filled field and the chain back to Tally

Layout and rules follow the signed-off wireframe (11 Nov 2026) in the N K Lodha colours: sentence case,
nothing under 13 px, one filled button per screen, no stat strips. The older screens (client details,
ADT-1 list, captured forms, local AI) stay reachable under "More".
"""
import json
import re
from datetime import datetime
from html import escape
from pathlib import Path
from urllib.parse import quote

import app
import ff_audit
import ff_fin
import ff_jobs
import filing_queue

FORM_LABEL = app.FORM_LABEL


def esc(s):
    return escape("" if s is None else str(s), quote=True)


def money(v):
    """Indian grouping, no decimals; brackets for negatives."""
    if v is None or v == "":
        return ""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return esc(v)
    neg, x = x < 0, abs(round(x))
    s = str(int(x))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        s = ",".join(parts) + "," + tail
    return f"({s})" if neg else s


def when(iso):
    if not iso:
        return ""
    try:
        d = datetime.fromisoformat(str(iso).replace("Z", ""))
    except ValueError:
        return esc(iso)
    return d.strftime("%d %b, %H:%M") if d.date() != datetime.now().date() else d.strftime("%H:%M")


def clients():
    app.CLIENTS.mkdir(exist_ok=True)
    return sorted(p for p in app.CLIENTS.iterdir() if p.is_dir() and not p.name.startswith(("_", ".")))


def fy_label(folder=None):
    try:
        return "FY " + ff_fin.fy_of(folder) if folder else "FY " + ff_fin.fy_of(clients()[0])
    except Exception:  # noqa: BLE001
        return ""


# ---------------------------------------------------------------- shell

CSS = """
:root{--bg:oklch(0.985 0.004 95);--fg:oklch(0.235 0.014 260);--surface:oklch(0.972 0.005 95);--card:oklch(1 0 0);
--primary:oklch(0.285 0.038 258);--on-primary:oklch(0.985 0.004 95);--muted:oklch(0.957 0.005 95);--mfg:oklch(0.47 0.014 258);
--brass:oklch(0.62 0.086 76);--bad:oklch(0.52 0.176 27);--good:oklch(0.45 0.088 158);--info:oklch(0.47 0.07 245);
--border:oklch(0.905 0.006 95);--strong:oklch(0.80 0.008 95);--ring:oklch(0.62 0.086 76);
--side:oklch(0.256 0.024 258);--side-fg:oklch(0.87 0.01 95);--side-on:oklch(0.31 0.026 258);--side-line:oklch(0.34 0.022 258)}
*{box-sizing:border-box}
body{margin:0;font:14px/20px "IBM Plex Sans",system-ui,sans-serif;color:var(--fg);background:var(--bg);-webkit-font-smoothing:antialiased}
a{color:var(--primary)}:focus-visible{outline:2px solid var(--ring);outline-offset:2px}
.num,td.n,th.n{font-variant-numeric:tabular-nums;text-align:right;white-space:nowrap}
aside{position:fixed;inset:0 auto 0 0;width:240px;background:var(--side);color:var(--side-fg);padding:24px 12px;display:flex;flex-direction:column;gap:4px;z-index:5}
.brand{color:#fff;font-weight:600;font-size:16px;line-height:22px;padding:0 12px 24px;text-decoration:none;display:block}
.brand small{display:block;font-weight:400;font-size:13px;color:var(--side-fg);opacity:.8}
aside a.nv{display:flex;gap:10px;align-items:center;padding:8px 12px;border-radius:6px;color:var(--side-fg);text-decoration:none}
aside a.nv:hover{background:var(--side-on)}aside a.on{background:#fff;color:var(--fg);font-weight:500}
aside a.nv .k{width:20px;height:20px;border-radius:10px;border:1px solid currentColor;display:inline-flex;align-items:center;justify-content:center;font-size:13px;flex:none;opacity:.85}
aside .gap{height:24px}
aside .more{margin-top:auto;border-top:1px solid var(--side-line);padding:12px 12px 0;font-size:13px;line-height:18px}
aside .more a{color:var(--side-fg);display:block;padding:3px 0;text-decoration:none;opacity:.85}aside .more a:hover{opacity:1;text-decoration:underline}
aside .who{display:flex;flex-direction:column;gap:4px;padding:12px;border-top:1px solid var(--side-line);margin-top:12px;font-size:13px}
aside .who input{height:32px;border-radius:6px;border:1px solid var(--side-line);background:var(--side-on);color:#fff;padding:0 8px;font:inherit}
main{margin-left:240px;padding:32px 48px 48px;display:flex;flex-direction:column;gap:24px;max-width:1500px}
.head{display:flex;justify-content:space-between;align-items:flex-end;gap:24px;flex-wrap:wrap}
.crumb{font-size:13px;color:var(--mfg)}h1{font-size:28px;line-height:34px;font-weight:600;letter-spacing:-.01em;margin:2px 0 0}
.acts{display:flex;gap:12px;flex-wrap:wrap;align-items:center}
.g12{display:grid;grid-template-columns:repeat(12,minmax(0,1fr));gap:24px;align-items:start}
.s8{grid-column:span 8}.s4{grid-column:span 4}.s7{grid-column:span 7}.s5{grid-column:span 5}.s9{grid-column:span 9}.s3{grid-column:span 3}.s12{grid-column:span 12}
@media (max-width:1100px){.g12>*{grid-column:span 12!important}main{padding:24px 16px;margin-left:0}aside{position:static;width:auto}}
.card{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:24px}
.h{font-size:14px;font-weight:500;color:var(--mfg);margin:0 0 12px}
table{width:100%;border-collapse:collapse}th{font-weight:500;color:var(--mfg);font-size:13px;text-align:left;padding:0 8px 8px}
td{border-top:1px solid var(--border);padding:8px;vertical-align:top}tr.sel td{background:var(--muted)}
tr.click{cursor:pointer}tr.click:hover td{background:var(--surface)}
.tag{display:inline-block;font-size:13px;line-height:18px;border:1px solid var(--strong);border-radius:4px;padding:1px 8px;white-space:nowrap;background:var(--card)}
.need{border-color:var(--fg);font-weight:600}.good{border-color:var(--good);color:var(--good)}.badt{border-color:var(--bad);color:var(--bad);font-weight:600}
.work{border-color:var(--info);color:var(--info)}
.mut{color:var(--mfg);font-size:13px}.err{color:var(--bad)}.ok{color:var(--good)}
.btn,button{font:inherit;font-size:15px;height:40px;padding:0 18px;border:1px solid var(--fg);border-radius:6px;background:var(--card);color:var(--fg);cursor:pointer;text-decoration:none;display:inline-flex;align-items:center;gap:8px}
.btn:hover,button:hover{background:var(--muted)}button:disabled{opacity:.45;cursor:not-allowed}
.p{background:var(--primary);border-color:var(--primary);color:var(--on-primary)}.p:hover{background:oklch(0.33 0.04 258)}
.sm{height:32px;font-size:13px;padding:0 12px}.link{border:0;background:none;height:auto;padding:0;color:var(--primary);text-decoration:underline;font-size:13px}
input[type=text],select,textarea{font:inherit;height:36px;padding:0 10px;border:1px solid var(--strong);border-radius:6px;background:var(--card);color:var(--fg);min-width:0}
textarea{height:auto;padding:8px 10px}input[type=checkbox]{width:16px;height:16px;accent-color:var(--primary)}
label.f{display:flex;flex-direction:column;gap:4px;font-size:13px;color:var(--mfg)}
.row{display:flex;gap:12px;flex-wrap:wrap;align-items:flex-end}
.steps{display:flex;gap:24px}.steps>div{flex:1;border-top:2px solid var(--strong);padding-top:12px}.steps>div.d{border-color:var(--primary)}
.steps b{display:block;margin-bottom:2px}
.filters{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.filters a{text-decoration:none;color:var(--fg)}
.tabs{display:flex;gap:28px;border-bottom:1px solid var(--border);flex-wrap:wrap}.tabs a{padding:10px 0;color:var(--mfg);text-decoration:none}
.tabs a.on{color:var(--fg);font-weight:500;border-bottom:2px solid var(--fg)}
.msg{border:1px solid var(--brass);background:oklch(0.62 0.086 76 / .08);border-radius:8px;padding:12px 16px;white-space:pre-wrap}
.chain{border-left:2px solid var(--primary);padding:0 0 16px 16px}.chain:last-child{padding-bottom:0}.chain.off{border-color:var(--strong)}
.chain b{display:block}.ledgers{margin:6px 0 0;padding:0;list-style:none;font-size:13px}.ledgers li{display:flex;justify-content:space-between;gap:12px;border-top:1px dashed var(--border);padding:3px 0}
.pt{display:flex;flex-direction:column;gap:8px;border-top:1px solid var(--border);padding:10px 0}.pt:first-of-type{border-top:0}
.pt.done{flex-direction:row;justify-content:space-between;align-items:flex-start;gap:12px}
table.fixed{table-layout:fixed}table.fixed td{overflow-wrap:anywhere}
.log{display:grid;grid-template-columns:64px 1fr;gap:12px;border-top:1px solid var(--border);padding:8px 0;font-size:13px}.log:first-of-type{border-top:0}
details>summary{cursor:pointer;color:var(--primary);font-size:13px}
.total td{font-weight:600}.hd td{font-weight:600;color:var(--mfg);background:var(--surface)}
"""

SCRIPT = """<script>
(()=>{const k='ff_user';const box=document.getElementById('who');let v='';try{v=localStorage.getItem(k)||''}catch(e){}
if(box){box.value=v;box.addEventListener('change',()=>{try{localStorage.setItem(k,box.value.trim())}catch(e){}})}
for(const f of document.querySelectorAll('form'))f.addEventListener('submit',e=>{let u=(box&&box.value.trim())||'';
 if(f.dataset.who==='need'&&!u){e.preventDefault();alert('Type your name at the bottom left first: this step is recorded against a person.');box&&box.focus();return}
 let h=f.querySelector('input[name=user]');if(!h){h=document.createElement('input');h.type='hidden';h.name='user';f.appendChild(h)}h.value=u;
 const b=f.querySelector('button[data-busy]');if(b){b.disabled=true;b.textContent=b.dataset.busy}});
for(const t of document.querySelectorAll('[data-all]'))t.addEventListener('change',()=>{for(const c of document.querySelectorAll('input[name='+t.dataset.all+']'))c.checked=t.checked});
const r=document.body.dataset.refresh;if(r)setTimeout(()=>location.reload(),+r*1000);
})();</script>"""

NAV = [("/data", "1", "Get data"), ("/review", "2", "Review financials"), ("/file", "3", "File on MCA"),
       None, ("/agents", "", "Agent queue"), ("/audit", "", "Audit trail")]


def shell(title, body, active="", msg="", refresh=0):
    nav = []
    for item in NAV:
        if item is None:
            nav.append("<div class=gap></div>")
            continue
        href, k, name = item
        nav.append(f"<a class=\"nv{' on' if href == active else ''}\" href=\"{href}\">"
                   f"{f'<span class=k>{k}</span>' if k else '<span class=k style=border:0></span>'}{name}</a>")
    return f"""<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>{esc(title)} · Form Filler</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>{CSS}</style></head><body{f' data-refresh={refresh}' if refresh else ''}>
<aside><a class=brand href="/data">MCA automation<small>Form Filler · N K Lodha &amp; Co</small></a>
{''.join(nav)}
<div class=more><a href="/filings">Client details and questions</a><a href="/adt1">ADT-1 companies</a><a href="/admin">Captured forms</a><a href="/ai">Local AI</a></div>
<label class=who for=who>Your name<input id=who type=text autocomplete=name placeholder="Recorded on approvals"></label></aside>
<main>{f'<div class=msg role=status>{esc(msg)}</div>' if msg else ''}{body}</main>{SCRIPT}</body></html>"""


def head(crumb, title, actions=""):
    return f"<div class=head><div><div class=crumb>{crumb}</div><h1>{esc(title)}</h1></div><div class=acts>{actions}</div></div>"


def tag(text, kind=""):
    return f"<span class=\"tag {kind}\">{esc(text)}</span>"


# ---------------------------------------------------------------- client status (shared by the screens)

def status(folder):
    """(text, tag class, where to go) for a client's position in the three steps."""
    jobs = [j for j in ff_jobs.load()["jobs"] if j["client"] == folder.name]
    live = next((j for j in reversed(jobs) if j["status"] in ("working", "queued")), None)
    if live:
        return ("Agent working" if live["status"] == "working" else "Waiting for the agent"), "work", "/agents"
    stuck = next((j for j in reversed(jobs) if j["status"] in ("staff", "failed")), None)
    v = ff_fin.verified(folder)
    if v:
        return "Verified, okay to file", "good", f"/file"
    if stuck and stuck["status"] == "failed":
        return "Failed: see agent queue", "badt", "/agents"
    if not ff_fin.output(folder):
        if stuck:
            return stuck["now"], "need", "/agents"
        return "No data yet", "", ""
    n = len(ff_fin.open_points(folder))
    return (f"{n} review point{'s' if n != 1 else ''}", "need", f"/review?c={quote(folder.name)}") if n else \
        ("Ready for the tick", "need", f"/review?c={quote(folder.name)}")


# ---------------------------------------------------------------- 1 Get data

def page_data(msg=""):
    rows = []
    working = False
    for d in clients():
        f = app.load(d)
        cfg = ff_fin.load_cfg(d)
        cy, py = ff_fin.tb_info(d, "tb_cy"), ff_fin.tb_info(d, "tb_py")
        text, cls, go = status(d)
        working = working or cls == "work"

        def yr(info):
            if not info:
                return "<span class=mut>Not read</span>"
            how = "From Tally" if info["how"] == "Tally" else "Uploaded"
            return f"{how}, {info['ledgers']} ledgers<br><span class=mut>{when(info['at'])}</span>"
        forms = ", ".join(FORM_LABEL.get(s, s) for s in f.get("forms") or []) or "no forms"
        st = f"<a href=\"{go}\">{tag(text, cls)}</a>" if go else tag(text, cls)
        q = quote(d.name)
        rows.append(f"""<tr><td><input type=checkbox name=c value="{esc(d.name)}" form=getdata aria-label="Select {esc(d.name)}"></td>
<td><a href="/review?c={q}"><b>{esc(d.name)}</b></a><br><span class=mut>{esc(f.get('cin', '') or 'CIN not set')} · {esc(forms)}</span></td>
<td>{esc(cfg.get('tally_company_cy', ''))}<br><span class=mut>Last year: {esc(cfg.get('tally_company_py', ''))}</span>
<details><summary>Change Tally names or upload Excel</summary>
<form method=post action="/ff/client/tally" class=row style="margin-top:8px"><input type=hidden name=c value="{esc(d.name)}">
<label class=f>This year's company<input type=text name=cy value="{esc(cfg.get('tally_company_cy', ''))}"></label>
<label class=f>Last year's company<input type=text name=py value="{esc(cfg.get('tally_company_py', ''))}"></label>
<button class=sm>Save names</button></form>
<form method=post action="/ff/upload_tb?c={q}" enctype=multipart/form-data class=row style="margin-top:8px" data-tb>
<select name=which aria-label="Which year"><option value=tb_cy>This year</option><option value=tb_py>Last year</option></select>
<input type=file name=file accept=".xlsx,.xlsm,.csv" aria-label="Trial balance file"><button class=sm>Upload trial balance</button></form>
<p class=mut style="margin:6px 0 0">Excel or CSV with columns ledger_name, group_name, primary_group, opening_balance, net_debit, net_credit, closing_balance (Dr negative).</p>
</details></td>
<td>{yr(cy)}</td><td>{yr(py)}</td><td>{st}</td></tr>""")
    steps = """<div class=steps>
<div class=d><b>1 Reads Tally</b><span class=mut>Trial balance and ledgers, this year and last year</span></div>
<div class=d><b>2 Maps ledgers</b><span class=mut>To Schedule III heads, reusing last year's approved mapping</span></div>
<div class=d><b>3 Builds financials</b><span class=mut>Balance sheet, profit and loss, notes, checks, and the form values</span></div>
<div class=d><b>4 Raises review points</b><span class=mut>Differences, unmapped ledgers, last year's tie-out, open questions</span></div>
<div><b>5 Staff review</b><span class=mut>Next screen</span></div></div>"""
    add = f"""<details class=card id=add><summary style="font-size:14px">Add client</summary>
<form method=post action="/ff/client/new" style="margin-top:12px;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px">
<label class=f>Client name (folder name)<input type=text name=name required></label>
<label class=f>CIN<input type=text name=cin maxlength=21 placeholder="U12345TN2010PTC123456"></label>
<label class=f>Financial year ended<input type=text name=fy_end value="31/03/2026"></label>
<label class=f>Tally company, this year<input type=text name=cy placeholder="As shown in Tally"></label>
<label class=f>Tally company, last year<input type=text name=py placeholder="e.g. the '- Audited' copy"></label>
<fieldset style="border:0;padding:0;margin:0"><legend class=mut>Forms</legend>
{''.join(f'<label style="margin-right:12px"><input type=checkbox name=forms value="{s}" {"checked" if s in ("aoc4", "mgt7a") else ""}> {n}</label>' for s, n, _ in app.FORMS)}</fieldset>
<div><button class=sm>Add client</button></div></form></details>"""
    body = (head(f"Step 1 of 3 · {fy_label()}", "Get data from Tally",
                 "<a class=btn href=#add onclick=\"document.getElementById('add').open=true\">Add client</a>"
                 "<form id=getdata method=post action=/ff/getdata><button class=p data-busy=\"Queued\">Get data for selected</button></form>")
            + f"<div class=card><div class=h>What the agent does for each client once its Tally company is open</div>{steps}</div>"
            + f"""<div class=card><div class=h style="display:flex;justify-content:space-between"><span>Clients</span><span id=tally class=mut>Checking Tally…</span></div>
<table><tr><th style="width:28px"><input type=checkbox data-all=c aria-label="Select all"></th><th>Client</th><th>Tally company</th><th>This year</th><th>Last year</th><th>Status</th></tr>
{''.join(rows) or '<tr><td colspan=6 class=mut>No clients yet. Add one above.</td></tr>'}</table>
<p class=mut style="margin:12px 0 0">A client without Tally uploads an Excel trial balance (Change Tally names or upload Excel) and follows the same steps.
Tally needs F1 Help &gt; Settings &gt; Connectivity: Client/Server set to Both, port 9000.</p></div>"""
            + add
            + """<script>fetch('/ff/api/tally').then(r=>r.json()).then(d=>{const t=document.getElementById('tally');
t.textContent=d.error?('Tally not reachable: '+d.error):('Tally connected. Open: '+(d.companies||[]).join(', '))}).catch(()=>{});
for(const f of document.querySelectorAll('form[data-tb]'))f.addEventListener('submit',async e=>{e.preventDefault();const fi=f.querySelector('input[type=file]').files[0];
if(!fi)return;const r=await fetch(f.action+'&which='+f.which.value+'&name='+encodeURIComponent(fi.name),{method:'POST',body:fi});const d=await r.json();
location.href='/data?msg='+encodeURIComponent(d.error?('Upload failed: '+d.error):('Read '+d.ledgers+' ledgers from '+fi.name+'. Click Get data for selected to build.'))});</script>""")
    return shell("Get data", body, "/data", msg, refresh=8 if working else 0)


# ---------------------------------------------------------------- 2 Review financials

TABS = [("bs", "Balance sheet"), ("pl", "Profit and loss"), ("notes", "Notes to accounts"), ("mapping", "Mapping"),
        ("questions", "Questions for the forms"), ("reports", "Reports and meetings")]


def page_review(name="", tab="bs", msg=""):
    cl = clients()
    if not cl:
        return shell("Review financials", head("Step 2 of 3", "Review financials") + "<div class=card>No clients yet.</div>", "/review", msg)
    names = [d.name for d in cl]
    if name not in names:
        # first client that still needs review
        name = next((d.name for d in cl if ff_fin.output(d) and not ff_fin.verified(d)), names[0])
    folder = app.folder_of(name)
    q = quote(name)
    v = ff_fin.verified(folder)
    pts = ff_fin.review_points(folder)
    open_n = sum(1 for p in pts if not p["passed"] and not p["cleared"])
    i = names.index(name)
    pick = ("<form method=get action=/review class=row><input type=hidden name=tab value=\"" + esc(tab) + "\">"
            "<select name=c onchange=this.form.submit() aria-label=Client>"
            + "".join(f"<option {'selected' if n == name else ''}>{esc(n)}</option>" for n in names) + "</select></form>")
    fs = ff_fin.output(folder)
    if v:
        tick = (f"<form method=post action=/ff/unverify><input type=hidden name=c value=\"{esc(name)}\">"
                f"<span class=\"tag good\" style=\"margin-right:12px\">Verified by {esc(v['by'])}, {when(v['at'])}</span>"
                f"<button class=sm>Remove tick</button></form>")
    else:
        tick = (f"<form method=post action=/ff/verify data-who=need><input type=hidden name=c value=\"{esc(name)}\">"
                f"<button class=p {'disabled' if open_n or not fs else ''} title=\"{'Clear every review point first' if open_n else ''}\">Verified, okay to file</button></form>")
    acts = pick + (f"<a class=btn href=\"/ff/workbook?c={q}\">Open in Excel</a>" if fs else "") + tick
    tabs = "<nav class=tabs>" + "".join(f"<a href=\"/review?c={q}&tab={k}\" class=\"{'on' if k == tab else ''}\">{t}</a>" for k, t in TABS) + "</nav>"
    left = _review_tab(folder, tab)
    pts_html = []
    for p in pts:
        if p["passed"]:
            right = tag("Passed", "good")
        elif p["cleared"]:
            right = tag(f"Cleared by {p['cleared']['by']}", "good")
        elif p["kind"] == "questions":
            right = f"<a href=\"/review?c={q}&tab=questions\">{tag('Answer', 'need')}</a>"
        elif p["kind"] == "mapping":
            right = f"<a href=\"/review?c={q}&tab=mapping\">{tag('Confirm', 'need')}</a>"
        elif p["kind"] == "block":
            right = f"<a href=\"/data\">{tag('Get data', 'need')}</a>"
        else:
            right = (f"<form method=post action=/ff/point/clear data-who=need class=row style=\"gap:6px\"><input type=hidden name=c value=\"{esc(name)}\">"
                     f"<input type=hidden name=id value=\"{esc(p['id'])}\"><input type=text name=note placeholder=\"Note on how it was cleared (optional)\" style=\"flex:1;height:32px\" aria-label=Note>"
                     f"<button class=sm>Clear</button></form>")
        det = f"<div class=mut>{esc(p['detail'])}</div>" if p["detail"] else ""
        cn = f"<div class=mut>Note: {esc(p['cleared']['note'])}</div>" if p["cleared"] and p["cleared"].get("note") else ""
        done = p["passed"] or p["cleared"] or p["kind"] in ("questions", "mapping", "block")
        pts_html.append(f"<div class=\"pt{' done' if done else ''}\"><div>{esc(p['text'])}{det}{cn}</div><div>{right}</div></div>")
    fyl = fy_label(folder)
    body = (head(f"Step 2 of 3 · {esc(name)} · {fyl} · client {i + 1} of {len(names)}", "Review financials", acts) + tabs
            + f"""<div class=g12><div class="card s7">{left}</div>
<div class="card s5"><div class=h>Review points from the agent. All must be cleared before the tick.</div>{''.join(pts_html)}
<p class=mut style="margin:16px 0 0">The tick is recorded with your name and the time. Only ticked clients go to step 3. Getting data or building again removes the tick.</p></div></div>""")
    return shell(f"Review: {name}", body, "/review", msg)


def _change(cy, py):
    if cy is None and py is None:
        return ""
    d = (cy or 0) - (py or 0)
    return "Nil" if abs(d) < 0.5 else money(d)


def _review_tab(folder, tab):
    name = folder.name
    q = quote(name)
    if tab in ("bs", "pl", "notes"):
        st = ff_fin.statements(folder)
        if not st:
            return "<div class=h>No Schedule III workbook yet</div><p>Go to <a href=/data>Get data</a> and get this client's data from Tally.</p>"
        if tab == "notes":
            items = "".join(f"<tr><td class=n style=\"width:40px\">{n['no']}</td><td>{esc(n['title'])}</td></tr>" for n in st["notes"])
            return (f"<div class=h>Notes to accounts in {esc(st['file'])}</div><table>{items}</table>"
                    f"<p class=mut>Open the workbook to read each note in full.</p>")
        rows = []
        for r in st["BS" if tab == "bs" else "PL"]:
            lab = r["label"]
            if r["cy"] is None and r["py"] is None:
                rows.append(f"<tr class=hd><td colspan=4>{esc(lab)}</td></tr>")
                continue
            total = lab.upper().startswith("TOTAL") or re.match(r"^[IVX]+\.", lab)
            note = f" <span class=mut>note {esc(r['note'])}</span>" if r["note"] else ""
            rows.append(f"<tr class=\"{'total' if total else ''}\"><td>{esc(lab)}{note}</td>"
                        f"<td class=n>{money(r['cy'])}</td><td class=n>{money(r['py'])}</td><td class=n>{_change(r['cy'], r['py'])}</td></tr>")
        div = st["divisor"]
        unit = f" Figures shown in rupees (the workbook is in Rs/{div:g})." if div != 1 else ""
        return (f"<div class=h>Financials as per Schedule III, this year against last year</div>"
                f"<table><tr><th>{'Balance sheet' if tab == 'bs' else 'Profit and loss'}</th><th class=n>This year</th><th class=n>Last year</th><th class=n>Change</th></tr>{''.join(rows)}</table>"
                f"<p class=mut style=\"margin:12px 0 0\">Last year's column is checked against last year's filed AOC-4 (see review points).{unit} From {esc(st['file'])}.</p>")
    if tab == "mapping":
        if not ff_fin.tb_info(folder, "tb_cy"):
            return "<div class=h>No trial balance yet</div>"
        rows = ff_fin.mapping_rows(folder)
        heads = ff_fin.head_options()
        pend = [r for r in rows if not r["approved"]]
        opts = lambda cur: "".join(f"<option value=\"{h['code']}\" {'selected' if h['code'] == cur else ''}>{esc(h['label'])}</option>" for h in heads)
        trs = []
        for r in pend + [r for r in rows if r["approved"]]:
            led = esc(r["ledger"])
            box = "" if r["approved"] else f'<input type=checkbox name=ok value="{led}" checked aria-label=Approve>'
            warn = f"<div class=err>{esc(r['warn'])}</div>" if r["warn"] else ""
            if r["approved"]:
                head_ = esc(r["proposed"]["line"] + " - " + r["proposed"]["label"])
            else:
                head_ = f'<select name="h:{led}" style="max-width:320px" aria-label=Head>{opts(r["proposed"]["code"])}</select>'
            why = esc(r["source"]) + (": " + esc(r["reason"]) if r["reason"] else "")
            trs.append(f"<tr><td>{box}</td><td><b>{led}</b><br><span class=mut>{esc(r['group'])}</span>{warn}</td>"
                       f"<td class=n>{money(r['cy'])}</td><td>{head_}<div class=mut>{why}</div></td></tr>")
        return (f"<form method=post action=/ff/map/approve data-who=need><input type=hidden name=c value=\"{esc(name)}\">"
                f"<div class=h>{len(pend)} ledgers wait for approval; {len(rows) - len(pend)} are approved or follow Tally's group</div>"
                f"<table><tr><th></th><th>Ledger</th><th class=n>This year</th><th>Schedule III head</th></tr>{''.join(trs)}</table>"
                + (f"<p><button class=sm>Approve ticked heads and rebuild</button></p>" if pend else "") + "</form>")
    if tab == "questions":
        if not app.inputs_path(folder).exists():
            f = app.load(folder)
            if not any(s in app.SMART for s in f.get("forms") or []):
                return "<div class=h>No AOC-4 or MGT-7A for this client</div><p class=mut>Pick the forms on the <a href=\"/client?c=" + q + "\">client details</a> page.</p>"
            return (f"<div class=h>Questions not prepared yet</div><form method=post action=/ff/prepare><input type=hidden name=c value=\"{esc(name)}\">"
                    f"<button class=sm {'disabled' if not ff_fin.output(folder) else ''}>Prepare questions</button></form>"
                    "<p class=mut>Most answers come pre-filled from last year's forms and Setup.</p>")
        qs, _ = app.questions(folder)
        answered = set(app.load(folder).get("answered") or [])
        trs = []
        for key, text, how, ans, came in qs:
            opts = re.findall(r"^([A-Za-z]+) / ([A-Za-z]+)$", how.strip())
            if opts:
                field = f"<select name=\"q_{esc(key)}\" aria-label=Answer>" + "".join(
                    f"<option {'selected' if c.lower() == ans.lower() else ''}>{esc(c)}</option>" for c in [""] + list(opts[0])) + "</select>"
            else:
                field = f"<input type=text name=\"q_{esc(key)}\" value=\"{esc(ans)}\" placeholder=\"{esc(how)}\" style=\"width:100%\" aria-label=Answer>"
            t = (tag("Needed", "need") if key in app.MUST and not ans.strip() else tag("Your answer", "good") if key in answered
                 else tag("Suggested") if ans.strip() else "")
            trs.append(f"<tr><td style=\"width:50%\">{esc(text)}<div class=mut>{esc(how)}</div></td><td>{field}</td><td>{t}</td></tr>")
        return (f"<form method=post action=/ff/answers><input type=hidden name=c value=\"{esc(name)}\">"
                f"<div class=h>What only staff know. Suggestions come from last year's forms and Setup.</div><table>{''.join(trs)}</table>"
                f"<p class=row><button class=sm data-busy=Saving>Save answers</button> <a class=mut href=\"/ai/questions?c={q}\">Suggest answers with local AI</a></p></form>")
    if tab == "reports":
        ok, why = ff_fin.docs_ready(folder)
        made = ff_fin.docs_list(folder)
        flags = ff_fin.docs_flags(folder)
        lst = "".join(f"<li><a href=\"/ff/report?c={q}&f={quote(n)}\">{esc(n)}</a></li>" for n in made)
        fl = "".join(f"<li>{esc(x)}</li>" for x in flags)
        return (f"<div class=h>Board's report, auditor's report with CARO, notice, board and members' meeting papers</div>"
                f"<p>Rolled forward from last year's signed documents and filled from this year's Schedule III, so every figure agrees with the accounts.</p>"
                + (f"<form method=post action=/ff/docs><input type=hidden name=c value=\"{esc(name)}\"><button class=sm>Draft the documents</button></form>" if ok
                   else f"<p class=mut>Not ready: {esc(why)}. Last year's documents go in <code>financials\\{esc(ff_fin.fy_of(folder))}\\last_year_docs</code> "
                        f"(notice.docx, board report.docx, auditors report.docx, sap.docx, Shareholders list.xlsx, Directors list.xlsx).</p>")
                + (f"<p><b>Drafted</b></p><ul>{lst}</ul>" if made else "")
                + (f"<p><b>To check before signing</b></p><ul>{fl}</ul>" if fl else ""))
    return ""


# ---------------------------------------------------------------- 3 File on MCA

def page_file(form="all", msg=""):
    Q = filing_queue.load()
    jobs = Q["jobs"]
    rows = []
    pend = 0
    for d in clients():
        f = app.load(d)
        v = ff_fin.verified(d)
        for s in f.get("forms") or []:
            if s not in app.SMART or (form != "all" and s != form):
                continue
            if not v:
                pend += 1
                continue
            j = next((x for x in reversed(jobs) if x["client"] == d.name and x["slug"] == s), None)
            st = j["status"] if j else ""
            portal = {"": tag("Not started"), "queued": tag("Waiting"), "filling": tag("Filling now", "work"),
                      "held": tag("Needs attention: " + (j or {}).get("note", "")[:60], "badt"),
                      "saved": tag("Staff: DSC and submit", "need"), "skipped": tag("Skipped"),
                      "submitted": tag("Staff: check and pay", "need") if j and not j.get("paid") else tag("Filed", "good")}.get(st, tag(st))
            acts = ""
            if not j or st == "":
                why = filing_queue.problems(d.name, s)
                portal = tag("Ready to file", "good") if not why else tag("Not ready", "need") + "".join(f"<div class=mut>{esc(w)}</div>" for w in why)
                have = filing_queue.attachment_files(d, s)
                for el, title, must, _ in filing_queue.ATTACH.get(s, []):
                    if el not in have and must:
                        acts += (f"<form class=\"row att\" style=\"gap:6px;margin-top:6px\" data-c=\"{esc(d.name)}\" data-k=\"att_{el}\">"
                                 f"<input type=file accept=\".pdf,.jpg,.jpeg,.png\" aria-label=\"{esc(title)}\"><button class=sm>Upload {esc(title.split('(')[0].strip().lower())}</button></form>")
            if j and st in ("held", "saved", "skipped"):
                acts += _qbtn(j, "requeue", "Fill again")
            if j and st in ("held", "saved") and not j.get("srn"):
                acts += (f"<form method=post action=/ff/queue/edit class=row style=\"gap:6px;margin-top:6px\"><input type=hidden name=id value={j['id']}>"
                         f"<input type=hidden name=act value=srn><input type=text name=srn placeholder=SRN style=\"width:110px;height:32px\" aria-label=SRN><button class=sm>Save SRN</button></form>")
            if j and st == "submitted" and not j.get("paid"):
                acts += _qbtn(j, "paid", "Checked and paid")
            rows.append(f"<tr><td><a href=\"/audit?c={quote(d.name)}&f={s}\">{esc(d.name)}</a></td><td>{FORM_LABEL[s]}</td>"
                        f"<td>Verified by {esc(v['by'])}<div class=mut>{when(v['at'])}</div></td><td>{portal}{acts}</td><td>{esc((j or {}).get('srn', ''))}</td></tr>")
    running = Q["running"]
    filt = "".join(f"<a href=\"/file?form={k}\">{tag(t, 'need' if k == form else '')}</a>"
                   for k, t in (("all", "All"), ("aoc4", "AOC-4"), ("mgt7a", "MGT-7A")))
    filt += f"<a href=/adt1>{tag('ADT-1 (own list)')}</a><span class=mut>MGT-7 once its form is captured</span>"
    acts = (f"<form method=post action=/ff/queue/pause><button {'disabled' if not running else ''}>Pause</button></form>"
            f"<form method=post action=/ff/queue/start><button class=p data-busy=Starting>Start filing for all</button></form>")
    who = """<div class=steps><div><b>Staff</b><span class=mut>Log in and enter the captcha, once a session</span></div>
<div class=d><b>Form Filler</b><span class=mut>Opens the form, fills each section, attaches the PDFs, saves the draft</span></div>
<div><b>Staff</b><span class=mut>Review, attach DSC, submit, pay</span></div>
<div class=d><b>Form Filler</b><span class=mut>Reads the SRN, records it, opens the next client</span></div></div>"""
    cur = next((j for j in jobs if j["id"] == Q.get("current")), None)
    side = (f"<div class=h>Chrome side panel on mca.gov.in</div>"
            + (f"<p><b>{esc(cur['client'])}</b><br>{FORM_LABEL.get(cur['slug'], cur['slug'])}, filling now</p>" if cur else "<p class=mut>Nothing filling now.</p>")
            + "<ol style=\"padding-left:18px;margin:0\"><li>Open MCA in the Chrome window started by <code>open_mca_chrome.ps1</code>.</li>"
              "<li>Log in and enter the captcha.</li><li>Click the MCA filler icon, then <b>Start the queue</b> in the side panel.</li>"
              "<li>On the last page click Submit yourself. The SRN is read and the next client opens.</li></ol>"
              "<p class=mut>It works inside your own Chrome, because MCA blocks automated browsers. Alt+Shift+X stops it.</p>")
    body = (head(f"Step 3 of 3 · {fy_label()}", "File on MCA", acts)
            + f"<div class=filters><span class=mut>Form</span>{filt}</div>"
            + f"""<div class=g12><div class=s9 style="display:flex;flex-direction:column;gap:24px">
<div class=card><div class=h>Only clients ticked "verified, okay to file" appear here. The agent goes through them one after another.</div>
<table><tr><th>Client</th><th>Form</th><th>Data</th><th>Portal</th><th>SRN</th></tr>{''.join(rows) or '<tr><td colspan=5 class=mut>No ticked clients yet. Tick them on Review financials.</td></tr>'}</table>
{f'<p class=mut style="margin:12px 0 0">{pend} more form{"s" if pend != 1 else ""} wait for the tick on <a href=/review>Review financials</a>.</p>' if pend else ''}</div>
<div class=card><div class=h>Who does what on the MCA portal</div>{who}</div></div>
<div class="card s3">{side}</div></div>
<script>for(const f of document.querySelectorAll('form.att'))f.addEventListener('submit',async e=>{{e.preventDefault();const fi=f.querySelector('input').files[0];if(!fi)return;
const r=await fetch('/app/upload?c='+encodeURIComponent(f.dataset.c)+'&kind='+f.dataset.k+'&name='+encodeURIComponent(fi.name),{{method:'POST',body:fi}});const d=await r.json();
location.href='/file?msg='+encodeURIComponent(d.error?('Upload failed: '+d.error):('Saved '+d.saved+'. The tool uploads it on the portal.'))}});</script>""")
    return shell("File on MCA", body, "/file", msg, refresh=10 if running else 0)


def _qbtn(j, act, text):
    return (f"<form method=post action=/ff/queue/edit style=\"display:inline-block;margin:6px 6px 0 0\"><input type=hidden name=id value={j['id']}>"
            f"<input type=hidden name=act value={act}><button class=sm>{esc(text)}</button></form>")


# ---------------------------------------------------------------- Agent queue

def page_agents(show="all", msg=""):
    A = ff_jobs.load()
    Q = filing_queue.load()
    items = []
    for j in A["jobs"]:
        st = {"queued": ("Queued", ""), "working": ("Working", "work"), "staff": ("Staff: " + j["now"][:50], "need"),
              "done": ("Done", "good"), "failed": ("Failed: retry", "badt")}[j["status"]]
        grp = {"queued": "working", "working": "working", "staff": "staff", "done": "done", "failed": "failed"}[j["status"]]
        acts = ""
        if j["status"] in ("failed", "staff"):
            acts += _jbtn(j, "retry", "Retry")
        if j["status"] != "working":
            acts += _jbtn(j, "remove", "Remove")
        items.append((j.get("updated", ""), grp, f"<tr><td><a href=\"/review?c={quote(j['client'])}\">{esc(j['client'])}</a></td>"
                      f"<td>{ff_jobs.KINDS.get(j['kind'], j['kind'])}</td><td>{esc(j['now'])}</td><td>{when(j.get('started'))}</td>"
                      f"<td>{tag(*st)}{acts}</td></tr>"))
    for j in Q["jobs"]:
        s = j["status"]
        st = {"queued": ("Queued", ""), "filling": ("Working", "work"), "held": ("Failed: retry", "badt"),
              "saved": ("Staff: DSC and submit", "need"), "skipped": ("Skipped", ""),
              "submitted": ("Staff: check and pay", "need") if not j.get("paid") else ("Done", "good")}.get(s, (s, ""))
        grp = {"queued": "working", "filling": "working", "held": "failed", "saved": "staff", "skipped": "done",
               "submitted": "staff" if not j.get("paid") else "done"}.get(s, "done")
        now = {"queued": "Next in line", "filling": "Filling on MCA", "held": j.get("note") or "Stopped",
               "saved": "Draft saved", "submitted": f"SRN {j['srn']} read" if j.get("srn") else "Submitted"}.get(s, j.get("note", ""))
        items.append((j.get("updated", ""), grp, f"<tr><td><a href=\"/audit?c={quote(j['client'])}&f={j['slug']}\">{esc(j['client'])}</a></td>"
                      f"<td>File {FORM_LABEL.get(j['slug'], j['slug'])}</td><td>{esc(now)}</td><td>{when(j.get('updated'))}</td><td>{tag(*st)}</td></tr>"))
    items.sort(key=lambda x: x[0], reverse=True)
    rows = [h for _, g, h in items if show == "all" or g == show]
    filt = "".join(f"<a href=\"/agents?show={k}\">{tag(t, 'need' if k == show else '')}</a>"
                   for k, t in (("all", "All"), ("working", "Working"), ("staff", "Waiting for staff"), ("done", "Done"), ("failed", "Failed")))
    log = "".join(f"<div class=log><span class=mut>{when(e['at'])}</span><span><b>{esc(e.get('client', ''))}</b>: {esc(e['text'])}"
                  f"{' · ' + esc(e['by']) if e.get('by') and e.get('by') != 'agent' else ''}</span></div>" for e in ff_audit.activity(40))
    paused = A["paused"]
    acts = (f"<form method=post action=/ff/jobs/act><input type=hidden name=act value=\"{'resume' if paused else 'pause'}\">"
            f"<button>{'Resume' if paused else 'Pause all'}</button></form>"
            f"<form method=post action=/ff/jobs/act><input type=hidden name=act value=clear><button>Clear done</button></form>")
    working = any(j["status"] in ("queued", "working") for j in A["jobs"]) or Q["running"]
    body = (head(f"All clients · {fy_label()}" + (" · paused" if paused else ""), "Agent queue", acts)
            + f"<div class=filters><span class=mut>Show</span>{filt}</div>"
            + f"""<div class=g12><div class="card s8"><div class=h>One row per job, newest first. Jobs run one after another across the three steps.</div>
<table><tr><th>Client</th><th>Job</th><th>Now doing</th><th>Started</th><th>Status</th></tr>{''.join(rows) or '<tr><td colspan=5 class=mut>No jobs.</td></tr>'}</table>
<p class=mut style="margin:12px 0 0">Bold tags are jobs stopped for a person. Clicking a client opens it at the right step.</p></div>
<div class="card s4"><div class=h>Activity log, newest first</div>{log or '<p class=mut>Nothing yet.</p>'}
<p class=mut style="margin:12px 0 0">Every line here is also written to that client's audit trail.</p></div></div>""")
    return shell("Agent queue", body, "/agents", msg, refresh=5 if working else 0)


def _jbtn(j, act, text):
    return (f"<form method=post action=/ff/jobs/act style=\"display:inline-block;margin-left:6px\"><input type=hidden name=id value={j['id']}>"
            f"<input type=hidden name=act value={act}><button class=link>{esc(text)}</button></form>")


# ---------------------------------------------------------------- Audit trail

CATS = [("all", "All fields"), ("tally", "From Tally"), ("lastyear", "From last year's form"), ("staff", "Typed by staff"),
        ("ai", "Suggested by AI"), ("auto", "Worked out")]


def page_audit(name="", slug="", cat="all", msg=""):
    cl = [d for d in clients() if app.inputs_path(d).exists()]
    if not cl:
        return shell("Audit trail", head("Audit trail", "Audit trail") +
                     "<div class=card>No client has form values yet. They are prepared after Get data.</div>", "/audit", msg)
    names = [d.name for d in cl]
    name = name if name in names else names[0]
    folder = app.folder_of(name)
    forms = [s for s in (app.load(folder).get("forms") or []) if s in app.SMART] or ["aoc4"]
    slug = slug if slug in forms else forms[0]
    data = ff_audit.chain(folder, slug)
    rows = data["rows"]
    shown = [r for r in rows if cat == "all" or r["category"] == cat]
    pick = ("<form method=get action=/audit class=row><select name=c aria-label=Client>"
            + "".join(f"<option {'selected' if n == name else ''}>{esc(n)}</option>" for n in names) + "</select>"
            + "<select name=f aria-label=Form>" + "".join(f"<option value={s} {'selected' if s == slug else ''}>{FORM_LABEL[s]}</option>" for s in forms)
            + "</select><button>Change client or form</button></form>")
    acts = pick + f"<a class=\"btn p\" href=\"/ff/audit/download?c={quote(name)}&f={slug}\">Download audit file</a>"
    counts = {k: (len(rows) if k == "all" else sum(1 for r in rows if r["category"] == k)) for k, _ in CATS}
    filt = "".join(f"<a href=\"/audit?c={quote(name)}&f={slug}&cat={k}\">{tag(f'{t} ({counts[k]})', 'need' if k == cat else '')}</a>"
                   for k, t in CATS if counts[k] or k == "all")
    trs = []
    for i, r in enumerate(shown):
        fl = r["filled"]
        fcell = (f"{when(fl['at'].replace(' ', 'T'))}, Form Filler" if fl and fl["status"] in ("filled", "unchanged")
                 else tag(fl["status"].replace("-", " "), "badt" if fl["status"] in ("failed", "manual") else "") if fl else "<span class=mut>Not yet</span>")
        val = money(r["value"]) if isinstance(r["value"], (int, float)) else esc(r["value"])
        trs.append(f"<tr class=\"click{' sel' if i == 0 else ''}\" data-i={rows.index(r)} tabindex=0><td><b>{esc(r['label'][:70])}</b><div class=mut>{esc(r['code'])} · {esc(str(r['section'] or '')[:40])}</div></td>"
                   f"<td class=n>{val}</td><td>{esc(r['picked'][:90])}</td><td>{esc(r['built'])}</td><td>{fcell}</td></tr>")
    v = data.get("verified")
    job = data.get("job") or {}
    ctx = {"tb": data.get("tb") or {}, "fs": data.get("fs"), "verified": v, "srn": job.get("srn"), "jobStatus": job.get("status"),
           "paid": job.get("paid"), "form": FORM_LABEL[slug]}
    payload = json.dumps({"rows": rows, "ctx": ctx}, default=str).replace("</", "<\\/")
    body = (head(f"{esc(name)} · {FORM_LABEL[slug]} · {fy_label(folder)}", "Audit trail", acts)
            + f"<div class=filters><span class=mut>Show</span>{filt}</div>"
            + f"""<div class=g12><div class="card s8"><div class=h>Every field filled on the form, with what was filled and where the value came from</div>
<div style="max-height:70vh;overflow:auto"><table class=fixed><colgroup><col style="width:32%"><col style="width:14%"><col style="width:26%"><col style="width:14%"><col style="width:14%"></colgroup>
<tr><th>Form field</th><th class=n>Filled</th><th>Picked from</th><th>Built from</th><th>Filled on portal</th></tr>{''.join(trs) or '<tr><td colspan=5 class=mut>No fields in this group.</td></tr>'}</table></div>
<p class=mut style="margin:12px 0 0">{'Ledger detail comes from the TB sheets of ' + esc(data['fs']) + '.' if data['ledger_detail'] else 'This Schedule III workbook was made by hand, so the chain stops at the Schedule III line. Build it from Tally on Get data for ledger detail.'}
The same trail, with every event, is saved in the client's audit folder when you download it.</p></div>
<div class="card s4" id=chain aria-live=polite></div></div>
<script id=data type="application/json">{payload}</script>
<script>{CHAIN_JS}</script>""")
    return shell(f"Audit: {name}", body, "/audit", msg)


CHAIN_JS = r"""
(()=>{const D=JSON.parse(document.getElementById('data').textContent);const box=document.getElementById('chain');
const e=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const m=v=>{const n=Number(v);if(!isFinite(n))return e(v);const s=Math.abs(Math.round(n)).toLocaleString('en-IN');return n<0?'('+s+')':s};
const t=s=>{if(!s)return'';const d=new Date(String(s).replace(' ','T'));return isNaN(d)?e(s):d.toLocaleString('en-IN',{day:'2-digit',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit'})};
function step(n,title,body,on){return `<div class="chain${on?'':' off'}"><b>${n} ${title}</b><div class=mut>${body}</div></div>`}
function show(i){const r=D.rows[i],c=D.ctx;let h=`<div class=h>Full chain for: ${e(r.label)}</div>`;
 const tb=c.tb||{};const cy=tb.tb_cy||{},py=tb.tb_py||{};
 if(r.category==='tally'){
  let led='';for(const x of r.terms){led+=`<div style="margin-top:6px">${x.sign<0?'Less: ':''}${e(x.desc)}</div>`;
   if(x.ledgers.length)led+='<ul class=ledgers>'+x.ledgers.slice(0,40).map(l=>`<li><span>${e(l.ledger)}<br><span class=mut>${e(l.group)} · mapping: ${e(l.approved)}</span></span><span class=num>${m(l.amount)}</span></li>`).join('')+(x.ledgers.length>40?`<li>${x.ledgers.length-40} more in the download</li>`:'')+'</ul>'}
  h+=step(1,'Tally',cy.at?`Read from '${e(cy.company)}' (${cy.ledgers} ledgers) on ${t(cy.at)}`+(py.at?`; last year from '${e(py.company)}' on ${t(py.at)}`:''):'Trial balance not recorded (workbook made outside this app)',!!cy.at);
  h+=step(2,'Mapping',led||'No ledgers behind this line',true);
  h+=step(3,'Schedule III',`${e(r.picked)}<br>Workbook ${e(c.fs)}`,true);
 }else if(r.category==='lastyear'){h+=step(1,'Source',`${e(r.picked)}. Carried forward because it did not change.`,true)}
 else if(r.category==='staff'){h+=step(1,'Source',`${e(r.picked)}`,true)}
 else{h+=step(1,'Source',`Worked out by the app: ${e(r.picked)}`,true)}
 const v=c.verified;h+=step(r.category==='tally'?4:2,'Review',v?`Ticked verified, okay to file by ${e(v.by)} on ${t(v.at)}`:'Not ticked yet',!!v);
 const f=r.filled;h+=step(r.category==='tally'?5:3,'Form field',`${e(c.form)} ${e(r.code)}, ${e(r.section||'')}. Value ${typeof r.value==='number'?m(r.value):e(r.value)}.`+(f?` ${e(f.status)} on the portal ${t(f.at)}${f.msg?' ('+e(f.msg)+')':''}`:' Not filled on the portal yet.'),!!f);
 h+=step(r.category==='tally'?6:4,'Filing',c.srn?`Submitted by staff with DSC, SRN ${e(c.srn)}${c.paid?', paid':''}`:'Not submitted yet',!!c.srn);
 box.innerHTML=h}
const trs=[...document.querySelectorAll('tr[data-i]')];
for(const tr of trs){const go=()=>{trs.forEach(x=>x.classList.remove('sel'));tr.classList.add('sel');show(+tr.dataset.i)};tr.addEventListener('click',go);tr.addEventListener('keydown',ev=>{if(ev.key==='Enter')go()})}
if(trs.length)show(+trs[0].dataset.i);else box.innerHTML='<div class=h>Select a field</div>';
})();"""


# ---------------------------------------------------------------- routes

def _back(path, msg="", **q):
    qs = "&".join(f"{k}={quote(str(v))}" for k, v in q.items() if v) + (f"&msg={quote(msg)}" if msg else "")
    return 303, "", "text/html", f"{path}?{qs.lstrip('&')}" if qs else path


def handle_get(path, query):
    """(status, body, content type) or None."""
    q = {k: v[0] for k, v in query.items()}
    msg = q.get("msg", "")
    if path in ("/", "/data"):
        return 200, page_data(msg), "text/html"
    if path == "/review":
        return 200, page_review(q.get("c", ""), q.get("tab", "bs"), msg), "text/html"
    if path == "/file":
        return 200, page_file(q.get("form", "all"), msg), "text/html"
    if path == "/agents":
        return 200, page_agents(q.get("show", "all"), msg), "text/html"
    if path == "/audit":
        return 200, page_audit(q.get("c", ""), q.get("f", ""), q.get("cat", "all"), msg), "text/html"
    if path == "/filings":
        return 200, app.home(msg), "text/html"
    if path == "/ff/api/tally":
        try:
            return 200, json.dumps({"companies": ff_fin.tally_companies()}), "application/json"
        except Exception as e:  # noqa: BLE001
            return 200, json.dumps({"error": str(e)[:120]}), "application/json"
    if path == "/ff/api/state":
        return 200, json.dumps({"jobs": ff_jobs.load()["jobs"], "activity": ff_audit.activity(20)}, default=str), "application/json"
    if path in ("/ff/workbook", "/ff/audit/download", "/ff/report"):
        folder = app.folder_of(q.get("c", ""))
        if path == "/ff/workbook":
            p = ff_fin.output(folder)
        elif path == "/ff/report":
            p = (folder / "reports" / Path(q.get("f", "")).name)
        else:
            p = ff_audit.export(folder, q.get("f", "aoc4"))
        if not p or not p.exists():
            return 404, "not found", "text/plain"
        return 200, ("FILE", p), "application/octet-stream"
    return None


def handle_post(path, query, body, form):
    """(status, body, content type, location or None) or None."""
    if not path.startswith("/ff/"):
        return None
    q = {k: v[0] for k, v in query.items()}
    user = (form.get("user") or "").strip()
    name = form.get("c") or q.get("c") or ""
    lists = form.get("_lists", {})
    try:
        if path == "/ff/upload_tb":
            folder = app.folder_of(name)
            n = ff_fin.upload_tb(folder, q.get("which", "tb_cy"), q.get("name", "upload.xlsx"), body, user)
            return 200, json.dumps({"ledgers": n}), "application/json", None
        if path == "/ff/client/new":
            folder = app.folder_of(form.get("name", ""))
            folder.mkdir(parents=True, exist_ok=True)
            cin = form.get("cin", "").strip().upper()
            if cin and not app.CIN_RE.fullmatch(cin):
                return _back("/data", "That CIN does not look right (21 characters).")
            app.save(folder, cin=cin, fy_end=form.get("fy_end", "31/03/2026").strip(),
                     forms=[s for s, _, _ in app.FORMS if s in lists.get("forms", [])])
            cfg = ff_fin.load_cfg(folder)
            cfg["tally_company_cy"] = form.get("cy", "").strip() or folder.name
            cfg["tally_company_py"] = form.get("py", "").strip() or cfg["tally_company_cy"]
            cfg["setup"]["CIN"] = cin
            ff_fin.save_cfg(folder, cfg)
            ff_audit.event(folder, "job", "Client added", by=user or "staff")
            return _back("/data", f"Added {folder.name}. Tick it and click Get data for selected.")
        if path == "/ff/client/tally":
            folder = app.folder_of(name)
            cfg = ff_fin.load_cfg(folder)
            cfg["tally_company_cy"] = form.get("cy", "").strip() or cfg.get("tally_company_cy")
            cfg["tally_company_py"] = form.get("py", "").strip() or cfg.get("tally_company_py")
            ff_fin.save_cfg(folder, cfg)
            return _back("/data", f"Tally company names saved for {folder.name}.")
        if path == "/ff/getdata":
            picked = lists.get("c", [])
            if not picked:
                return _back("/data", "Tick at least one client.")
            n = sum(1 for c in picked if ff_jobs.add(app.folder_of(c).name, "get_data", user or "staff"))
            return _back("/agents", f"{n} client{'s' if n != 1 else ''} queued. The agent reads Tally one company at a time.")
        if path == "/ff/map/approve":
            folder = app.folder_of(name)
            ok = set(lists.get("ok", []))
            dec = {k[2:]: v for k, v in form.items() if k.startswith("h:") and k[2:] in ok}
            n = ff_fin.approve(folder, dec, user)
            ff_jobs.add(folder.name, "build", user)
            return _back("/review", f"{n} heads approved. The financials are being rebuilt (Agent queue).", c=folder.name, tab="mapping")
        if path == "/ff/point/clear":
            folder = app.folder_of(name)
            ff_fin.clear_point(folder, form.get("id", ""), user, form.get("note", ""))
            return _back("/review", "", c=folder.name, tab=q.get("tab") or "bs")
        if path == "/ff/verify":
            folder = app.folder_of(name)
            ff_fin.verify(folder, user)
            nxt = next((d.name for d in clients() if ff_fin.output(d) and not ff_fin.verified(d)), "")
            return _back("/review", f"{folder.name} ticked verified, okay to file." + (f" Next: {nxt}." if nxt else " Every client is ticked."), c=nxt or folder.name)
        if path == "/ff/unverify":
            folder = app.folder_of(name)
            ff_fin.unverify(folder, user)
            return _back("/review", "Tick removed.", c=folder.name)
        if path == "/ff/prepare":
            folder = app.folder_of(name)
            m = app.build(folder)
            ff_audit.event(folder, "questions", "Form values and questions prepared", by=user or "staff")
            return _back("/review", m, c=folder.name, tab="questions")
        if path == "/ff/answers":
            folder = app.folder_of(name)
            n = app.save_answers(folder, form)
            m = app.build(folder)
            ff_audit.event(folder, "questions", f"{n} answers saved", by=user or "staff")
            return _back("/review", f"{n} answers saved. {m}", c=folder.name, tab="questions")
        if path == "/ff/docs":
            folder = app.folder_of(name)
            ff_jobs.add(folder.name, "docs", user)
            return _back("/review", "Drafting the documents (Agent queue).", c=folder.name, tab="reports")
        if path == "/ff/queue/start":
            pairs = [(d.name, s) for d in clients() if ff_fin.verified(d) for s in app.load(d).get("forms") or [] if s in app.SMART]
            added, refused = filing_queue.add(pairs)
            job = filing_queue.start()
            m = f"{added} form{'s' if added != 1 else ''} added to the queue. "
            m += ("Now log in on MCA, open the side panel and click Start the queue." if job else "Nothing waiting to file.")
            for c, s, why in refused:
                m += f"\nNot added, {c} {FORM_LABEL.get(s, s)}: {'; '.join(why)}"
            return _back("/file", m)
        if path == "/ff/queue/pause":
            filing_queue.pause()
            return _back("/file", "The queue stops after the client being filled now.")
        if path == "/ff/queue/edit":
            m = filing_queue.edit(form) or "Updated."
            return _back("/file", m)
        if path == "/ff/jobs/act":
            act = form.get("act")
            jid = int(form.get("id") or 0)
            if act == "retry":
                ff_jobs.retry(jid)
            elif act == "remove":
                ff_jobs.remove(jid)
            elif act == "pause":
                ff_jobs.pause(True)
                filing_queue.pause()
            elif act == "resume":
                ff_jobs.pause(False)
            elif act == "clear":
                ff_jobs.clear_done()
            return _back("/agents")
    except PermissionError as e:
        return _back(_page_of(path), str(e), c=name)
    except Exception as e:  # noqa: BLE001
        if path == "/ff/upload_tb":
            return 400, json.dumps({"error": str(e)}), "application/json", None
        return _back(_page_of(path), f"Error: {e}", c=name)
    return None


def _page_of(path):
    if path.startswith(("/ff/map", "/ff/point", "/ff/verify", "/ff/unverify", "/ff/prepare", "/ff/answers", "/ff/docs")):
        return "/review"
    if path.startswith("/ff/queue"):
        return "/file"
    if path.startswith("/ff/jobs"):
        return "/agents"
    return "/data"
