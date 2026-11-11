"""UI polish for the hackathon demo (2026-11-01), in the NKL Design Language (ink on ivory,
restrained brass, IBM Plex Sans). Text-only edits to app.py and filing_queue.py: new CSS,
sidebar shell, page header + metric tiles, stepper. No ids, form actions, field names or
endpoints change. Run from the MVP folder: python _ui_patch/patch_ui.py"""
import re
import sys
from pathlib import Path

MVP = Path(__file__).resolve().parent.parent


def sub_once(text, old, new, label):
    n = text.count(old)
    if n != 1:
        sys.exit(f"[{label}] expected 1 match, found {n}")
    return text.replace(old, new)


UP = ("url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' "
      "stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4'/%3E"
      "%3Cpolyline points='17 8 12 3 7 8'/%3E%3Cline x1='12' x2='12' y1='3' y2='15'/%3E%3C/svg%3E\")")
TICK = ("url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' "
        "stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M20 6 9 17l-5-5'/%3E%3C/svg%3E\")")

CSS = r'''CSS = """
:root{--background:oklch(0.985 0.004 95);--foreground:oklch(0.235 0.014 260);--surface:oklch(0.972 0.005 95);--card:oklch(1 0 0);
--primary:oklch(0.285 0.038 258);--primary-foreground:oklch(0.985 0.004 95);--secondary:oklch(0.955 0.006 95);--secondary-foreground:oklch(0.3 0.02 258);
--muted:oklch(0.957 0.005 95);--muted-foreground:oklch(0.53 0.014 258);--accent:oklch(0.94 0.012 95);--brass:oklch(0.62 0.086 76);--brass-foreground:oklch(0.99 0.004 95);
--destructive:oklch(0.52 0.176 27);--success:oklch(0.49 0.088 158);--warning:oklch(0.68 0.126 72);--warning-foreground:oklch(0.24 0.03 72);--info:oklch(0.5 0.07 245);
--border:oklch(0.905 0.006 95);--border-strong:oklch(0.84 0.008 95);--input:oklch(0.888 0.007 95);--ring:oklch(0.62 0.086 76);
--sidebar:oklch(0.256 0.024 258);--sidebar-foreground:oklch(0.87 0.01 95);--sidebar-accent:oklch(0.31 0.026 258);--sidebar-accent-foreground:oklch(0.97 0.005 95);--sidebar-border:oklch(0.34 0.022 258);
--shadow-xs:0 1px 2px 0 rgb(0 0 0 / 0.05);--shadow-panel:0 1px 2px oklch(0.25 0.02 260 / 0.05),0 8px 24px -16px oklch(0.25 0.02 260 / 0.25);
--shadow-raised:0 1px 2px oklch(0.25 0.02 260 / 0.06),0 18px 40px -24px oklch(0.25 0.02 260 / 0.35);
/* legacy names still used by inline styles */--ink:var(--foreground);--line:var(--border);--go:var(--success);--bad:var(--destructive)}
*{box-sizing:border-box}html{scroll-behavior:smooth}
body{margin:0;font:14px/20px "IBM Plex Sans",ui-sans-serif,system-ui,sans-serif;font-feature-settings:"cv05","ss01";-webkit-font-smoothing:antialiased;color:var(--foreground);background:var(--background)}
a{color:var(--primary)}h1,h2,h3{letter-spacing:-0.014em}
code,.mono{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:13px}.numeric,.kpi .v,td{font-variant-numeric:tabular-nums}
:focus-visible{outline:2px solid var(--ring);outline-offset:2px}
/* sidebar + top bar */
aside.side{position:fixed;inset:0 auto 0 0;width:240px;background:var(--sidebar);color:var(--sidebar-foreground);display:flex;flex-direction:column;z-index:30}
.brandrow{height:64px;display:flex;align-items:center;gap:10px;padding:0 16px;border-bottom:1px solid var(--sidebar-border);text-decoration:none;color:var(--sidebar-accent-foreground)}
.tile{width:32px;height:32px;border-radius:6px;background:var(--brass);color:var(--brass-foreground);display:grid;place-items:center;font-weight:600;font-size:15px;flex:none}
.brandrow b{display:block;font-size:14px;font-weight:600;line-height:18px}.brandrow small{display:block;font-size:11px;line-height:16px;opacity:.75}
aside nav{padding:12px 8px;display:flex;flex-direction:column;gap:2px}
aside nav a{display:flex;align-items:center;gap:10px;padding:8px 12px;border-radius:7px;color:var(--sidebar-foreground);opacity:.75;text-decoration:none;font-size:14px;transition:background .15s,opacity .15s}
aside nav a:hover{opacity:1;background:var(--sidebar-accent)}aside nav a.on{opacity:1;background:var(--sidebar-accent);color:var(--sidebar-accent-foreground);font-weight:500}
aside nav a.on::after{content:"";margin-left:auto;width:6px;height:6px;border-radius:50%;background:var(--brass)}
aside svg,.ico{width:16px;height:16px;flex:none}
.sidefoot{margin-top:auto;padding:14px 16px;border-top:1px solid var(--sidebar-border);font-size:12px;line-height:16px;opacity:.75}
.sidefoot .label{font-size:11px;font-weight:600;letter-spacing:.09em;text-transform:uppercase;color:var(--brass);opacity:1;margin-bottom:4px}
.wrap{margin-left:240px;min-height:100vh;display:flex;flex-direction:column}
.topbar{position:sticky;top:0;z-index:20;height:64px;display:flex;align-items:center;gap:12px;padding:0 32px;border-bottom:1px solid var(--border);background:oklch(0.985 0.004 95 / 0.85);backdrop-filter:blur(8px)}
.topbar .trail{font-size:14px;color:var(--muted-foreground)}.topbar .trail b{color:var(--foreground);font-weight:500}
.live{margin-left:auto;display:flex;align-items:center;gap:8px;font-size:12px;color:var(--muted-foreground);border:1px solid var(--border);background:var(--card);padding:5px 10px;border-radius:6px;box-shadow:var(--shadow-xs)}
.live i{width:7px;height:7px;border-radius:50%;background:var(--success);animation:pulse 2.4s ease-in-out infinite}
@keyframes pulse{0%,100%{box-shadow:0 0 0 0 oklch(0.49 0.088 158 / .45)}50%{box-shadow:0 0 0 5px oklch(0.49 0.088 158 / 0)}}
main{width:100%;max-width:1400px;margin:0 auto;padding:32px 32px 40px;flex:1}
footer{border-top:1px solid var(--border);padding:16px 32px;color:var(--muted-foreground);font-size:12px;display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap}
@keyframes rise{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important;scroll-behavior:auto!important}}
/* page header + metrics */
.phead{display:flex;justify-content:space-between;align-items:flex-end;gap:16px;flex-wrap:wrap;padding-bottom:24px;margin-bottom:24px;border-bottom:1px solid var(--border)}
.phead h1{font-size:28px;line-height:34px;font-weight:600;margin:0}.phead p{margin:6px 0 0;color:var(--muted-foreground);max-width:720px}
.eyebrow{font-size:11px;line-height:16px;font-weight:600;letter-spacing:.09em;text-transform:uppercase;color:var(--muted-foreground);margin-bottom:6px;display:flex;align-items:center;gap:8px}
.eyebrow::before{content:"";width:16px;height:2px;background:var(--brass)}
.kpis{display:grid;grid-template-columns:1fr;gap:16px;margin-bottom:24px}
@media (min-width:640px){.kpis{grid-template-columns:repeat(2,1fr)}}@media (min-width:1280px){.kpis{grid-template-columns:repeat(4,1fr)}}
.kpi{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:20px;box-shadow:var(--shadow-xs);animation:rise .35s ease both}
.kpi:nth-child(2){animation-delay:.04s}.kpi:nth-child(3){animation-delay:.08s}.kpi:nth-child(4){animation-delay:.12s}
.kpi .l{font-size:11px;line-height:16px;font-weight:600;letter-spacing:.09em;text-transform:uppercase;color:var(--muted-foreground);display:flex;align-items:center;gap:8px}
.kpi .l .ico{color:var(--brass)}.kpi .v{font-size:30px;line-height:36px;font-weight:600;margin-top:10px}.kpi .s{font-size:12px;color:var(--muted-foreground);margin-top:2px}
/* cards */
.card{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:20px 24px;margin-bottom:20px;box-shadow:var(--shadow-xs);animation:rise .35s ease both}
.card h2{font-size:16px;line-height:24px;font-weight:600;margin:0 0 14px;display:flex;align-items:center;gap:10px}
.num{display:inline-flex;width:28px;height:28px;border-radius:6px;background:var(--secondary);border:1px solid var(--border-strong);color:var(--secondary-foreground);align-items:center;justify-content:center;font-size:13px;font-weight:600;flex:none}
.num.done{background:var(--success);border-color:var(--success);color:var(--primary-foreground)}
.step.done{border-color:oklch(0.49 0.088 158 / .35)}
.msg{background:oklch(0.68 0.126 72 / .12);border:1px solid oklch(0.68 0.126 72 / .45);color:var(--warning-foreground);padding:12px 16px;border-radius:8px;margin-bottom:20px;white-space:pre-wrap;animation:rise .3s ease both}
.err{color:var(--destructive)}.ok{color:var(--success);font-weight:500}.warn{color:var(--warning-foreground);font-weight:500}.muted{color:var(--muted-foreground);font-size:13px}
table{border-collapse:separate;border-spacing:0;width:100%}td,th{border-bottom:1px solid var(--border);padding:12px 10px;text-align:left;vertical-align:top}
th{font-size:11px;line-height:16px;color:var(--muted-foreground);font-weight:600;text-transform:uppercase;letter-spacing:.09em;background:var(--surface);padding-top:12px;padding-bottom:12px}
tr:last-child td{border-bottom:0}table tr:hover td{background:var(--muted)}
input[type=text],select{font:inherit;height:36px;padding:0 12px;border:1px solid var(--border-strong);border-radius:7px;width:100%;background:var(--card);color:var(--foreground);box-shadow:var(--shadow-xs);transition:border-color .15s}
input[type=text]:focus,select:focus{outline:2px solid var(--ring);outline-offset:2px;border-color:var(--ring)}
input[type=checkbox]{accent-color:var(--primary);width:16px;height:16px;vertical-align:-3px}
label.muted{display:block;font-size:11px;line-height:16px;font-weight:600;letter-spacing:.09em;text-transform:uppercase;margin-bottom:6px}
button,.btn{font:inherit;font-weight:500;height:36px;padding:0 16px;border-radius:7px;border:1px solid var(--border-strong);background:var(--card);color:var(--foreground);cursor:pointer;text-decoration:none;display:inline-flex;align-items:center;gap:8px;box-shadow:var(--shadow-xs);transition:background .15s,border-color .15s}
button:hover:not(:disabled),.btn:hover{background:var(--accent)}
button.primary,.btn.primary,button.go{background:var(--primary);color:var(--primary-foreground);border-color:var(--primary)}
button.primary:hover:not(:disabled),.btn.primary:hover,button.go:hover:not(:disabled){background:oklch(0.33 0.04 258)}
button.go{height:40px;padding:0 20px}button.go::before{content:"";width:8px;height:8px;border-radius:50%;background:var(--brass)}
button:disabled{opacity:.5;cursor:not-allowed}form{margin:0}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:12px}
.drop{border:1px dashed var(--border-strong);border-radius:8px;padding:16px 16px 14px 60px;min-height:120px;position:relative;background:var(--surface);transition:border-color .15s,background .15s}
.drop::before{content:"";position:absolute;left:16px;top:16px;width:32px;height:32px;border-radius:6px;background:var(--card);border:1px solid var(--border)}
.drop::after{content:"";position:absolute;left:24px;top:24px;width:16px;height:16px;background:var(--primary);-webkit-mask:@@UP@@ center/contain no-repeat;mask:@@UP@@ center/contain no-repeat}
.drop:hover{border-color:var(--primary);background:var(--card)}.drop.hover{border-color:var(--ring);background:oklch(0.62 0.086 76 / .07)}
.drop:has(.file.ok){border-style:solid;border-color:oklch(0.49 0.088 158 / .4);background:var(--card)}
.drop:has(.file.ok)::before{background:var(--success);border-color:var(--success)}
.drop:has(.file.ok)::after{background:var(--primary-foreground);-webkit-mask-image:@@TICK@@;mask-image:@@TICK@@}
.drop b{display:block;font-weight:600;margin-bottom:2px}.drop .file{margin-top:8px;font-size:13px;word-break:break-word}
.drop input{position:absolute;inset:0;opacity:0;cursor:pointer;z-index:2}
.tag{display:inline-flex;font-size:12px;font-weight:500;padding:2px 8px;border-radius:6px;border:1px solid var(--border-strong);background:var(--muted);color:var(--secondary-foreground)}
.tag.sug{background:oklch(0.5 0.07 245 / .08);border-color:oklch(0.5 0.07 245 / .3);color:var(--info)}
.tag.you{background:oklch(0.49 0.088 158 / .08);border-color:oklch(0.49 0.088 158 / .3);color:var(--success)}
.tag.need{background:oklch(0.52 0.176 27 / .07);border-color:oklch(0.52 0.176 27 / .3);color:var(--destructive)}
.clients td{vertical-align:middle}
.pill{display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:500;padding:2px 8px;border-radius:6px;border:1px solid var(--border-strong);background:var(--muted);color:var(--secondary-foreground)}
.pill::before{content:"";width:6px;height:6px;border-radius:50%;background:currentColor}
.pill.on{background:oklch(0.49 0.088 158 / .08);border-color:oklch(0.49 0.088 158 / .3);color:var(--success)}.pill.on::before{animation:pulse 2s ease-in-out infinite}
.pill.bad{background:oklch(0.52 0.176 27 / .07);border-color:oklch(0.52 0.176 27 / .3);color:var(--destructive)}
.pill.sub{background:oklch(0.5 0.07 245 / .08);border-color:oklch(0.5 0.07 245 / .3);color:var(--info)}
details summary{cursor:pointer;color:var(--muted-foreground);margin-top:10px;font-weight:500}details summary:hover{color:var(--primary)}
ol.how li{margin:6px 0}
.bar{height:6px;border-radius:3px;background:var(--muted);border:1px solid var(--border);overflow:hidden;width:120px;margin-bottom:4px}
.bar i{display:block;height:100%;background:var(--primary);transition:width .6s ease}.bar.full i{background:var(--success)}
.how4{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}
.how4>div{border:1px solid var(--border);border-radius:8px;padding:16px;background:var(--surface)}
.how4 .num{margin-bottom:10px}.how4>div>b{display:block;font-weight:600;margin-bottom:4px}.how4 p{margin:0;color:var(--muted-foreground);font-size:13px}
.guard{margin-top:14px;padding:12px 16px;border-radius:8px;background:var(--surface);border:1px solid var(--border);font-size:13px;color:var(--secondary-foreground);display:flex;gap:10px;align-items:center}
.guard .ico{color:var(--brass)}
/* client page */
.chead .meta{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px}
.chead .meta span{font-size:12px;font-weight:500;padding:2px 8px;border-radius:6px;background:var(--card);border:1px solid var(--border-strong)}
.chead .meta span.mono{font-size:12px}
.prog{min-width:200px}.prog .l{font-size:11px;font-weight:600;letter-spacing:.09em;text-transform:uppercase;color:var(--muted-foreground)}
.prog .v{font-size:30px;line-height:36px;font-weight:600}.prog .bar{width:200px}
.stepper{display:flex;margin:0 0 20px;background:var(--card);border:1px solid var(--border);border-radius:8px;padding:12px 16px;box-shadow:var(--shadow-panel);position:sticky;top:76px;z-index:10}
.stepper a{flex:1;display:flex;align-items:center;gap:10px;text-decoration:none;color:var(--muted-foreground);font-weight:500;font-size:14px}
.stepper a:not(:last-child)::after{content:"";flex:1;height:1px;background:var(--border-strong);margin:0 12px}
.stepper a.done{color:var(--foreground)}.stepper a.done:not(:last-child)::after{background:var(--success)}
.stepper a.cur{color:var(--foreground)}.stepper a.cur .num{background:var(--card);border:2px solid var(--brass);color:var(--foreground)}
.stepper .num{width:26px;height:26px;font-size:12px}
@media (max-width:1023px){aside.side{position:static;width:auto;flex-direction:row;align-items:center;flex-wrap:wrap}.brandrow{border:0}aside nav{flex-direction:row;padding:8px;overflow:auto}
.sidefoot{display:none}.wrap{margin-left:0}.topbar{display:none}main{padding:24px 16px}.stepper{position:static;flex-wrap:wrap;gap:8px}.stepper a:not(:last-child)::after{display:none}}
"""
'''.replace("@@UP@@", UP).replace("@@TICK@@", TICK)

ICONS = {
    "file": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M16 13H8"/><path d="M16 17H8"/><path d="M10 9H8"/></svg>',
    "building": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="16" height="20" x="4" y="2" rx="2"/><path d="M9 22v-4h6v4"/><path d="M8 6h.01M16 6h.01M12 6h.01M12 10h.01M12 14h.01M16 10h.01M16 14h.01M8 10h.01M8 14h.01"/></svg>',
    "sliders": '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 4h-7M10 4H3M21 12h-9M8 12H3M21 20h-5M12 20H3M14 2v4M8 10v4M16 18v4"/></svg>',
    "shield": '<svg class=ico viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/><path d="m9 12 2 2 4-4"/></svg>',
}

SHELL_OLD = '''<title>{esc(title)}</title><style>{CSS}</style></head><body>
<header><h1>MCA filing</h1><a href="/">Filings</a><a href="/adt1">ADT-1 companies</a><a href="/admin">Forms &amp; settings</a></header>
<main>{f'<div class=msg>{esc(msg)}</div>' if msg else ''}{body}</main></body></html>"""'''
SHELL_NEW = '''<title>{esc(title)} · N K Lodha &amp; Co</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin="anonymous">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:ital,wght@0,400;0,500;0,600;1,400&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>{CSS}</style></head><body>
<aside class=side><a class=brandrow href="/"><span class=tile>N</span><span><b>ROC Autopilot</b><small>N K Lodha &amp; Co</small></span></a>
<nav><a class=on href="/">@@FILE@@Filings</a><a href="/adt1">@@BUILDING@@ADT-1 companies</a><a href="/admin">@@SLIDERS@@Forms &amp; settings</a></nav>
<div class=sidefoot><div class=label>Human in the loop</div>Login, captcha, Submit, DSC and payment stay with your team.</div></aside>
<div class=wrap><div class=topbar><span class=trail>ROC filings / <b>{esc(title)}</b></span><span class=live><i></i>Live on office LAN · port 8742</span></div>
<main>{f'<div class=msg>{esc(msg)}</div>' if msg else ''}{body}</main>
<footer><span>N K Lodha &amp; Co · Chartered Accountants, Chennai</span><span>AOC-4 · MGT-7A · ADT-1 on MCA V3</span></footer></div>
<script>for(const el of document.querySelectorAll('[data-count]')){{const t=+el.dataset.count;if(!t||matchMedia('(prefers-reduced-motion: reduce)').matches)continue;let s=null;const f=n=>{{s=s||n;const p=Math.min(1,(n-s)/800);el.textContent=Math.round(t*(1-Math.pow(1-p,3))).toLocaleString('en-IN');if(p<1)requestAnimationFrame(f)}};requestAnimationFrame(f)}}</script>
</body></html>"""'''.replace("@@FILE@@", ICONS["file"]).replace("@@BUILDING@@", ICONS["building"]).replace("@@SLIDERS@@", ICONS["sliders"])

HOME_ROW_OLD = '''f"<td>{forms}</td><td>{done} of 4 steps</td>"'''
HOME_ROW_NEW = '''f"<td>{forms}</td><td><div class=\\"bar{' full' if done == 4 else ''}\\"><i style=\\"width:{done * 25}%\\"></i></div><span class=muted>{done} of 4 steps</span></td>"'''

HOME_BODY_OLD = '''    body = f"""<div class=card><h2>New filing</h2>'''
HOME_BODY_NEW = '''    n_cl = len(rows)
    n_forms = sum(len(load(d).get("forms") or []) for d in CLIENTS.iterdir() if d.is_dir())
    try:
        jobs = _queue().load()["jobs"]
    except Exception:  # noqa: BLE001
        jobs = []
    n_q = sum(1 for j in jobs if j.get("status") in ("queued", "filling"))
    n_sub = sum(1 for j in jobs if j.get("status") == "submitted" and not j.get("paid"))
    head = f"""<div class=phead><div><div class=eyebrow>MCA V3 · AI-assisted</div><h1>ROC filings</h1>
<p>AOC-4 and MGT-7A built from this year's Schedule III and last year's filed forms. The tool carries forward what didn't change, asks only what did, and fills the portal section by section.</p></div></div>
<div class=kpis><div class=kpi><div class=l>Clients</div><div class=v data-count={n_cl}>{n_cl}</div><div class=s>with a filing folder</div></div>
<div class=kpi><div class=l>Forms set up</div><div class=v data-count={n_forms}>{n_forms}</div><div class=s>AOC-4, MGT-7A, ADT-1</div></div>
<div class=kpi><div class=l>In the queue</div><div class=v data-count={n_q}>{n_q}</div><div class=s>waiting or filling now</div></div>
<div class=kpi><div class=l>Before payment</div><div class=v data-count={n_sub}>{n_sub}</div><div class=s>submitted, to review and pay</div></div></div>"""
    body = head + f"""<div class=card><h2>New filing</h2>'''

HOW_OLD = '''<div class=card><h2>How it works</h2><ol class=how>
<li><b>Details</b>: CIN, year and the forms to file.</li>
<li><b>Uploads</b>: this year's Schedule III workbook and last year's filed forms. These fill most of every form.</li>
<li><b>Questions</b>: a short list only you can answer (dates of meetings, changes during the year). Suggestions are pre-filled.</li>
<li><b>Fill</b>: for one client, click <i>Start filling</i> and use <b>Form Filler</b> in the Chrome side panel. For many, add them to the <b>Filing queue</b> and click <i>Start the queue</i> in the side panel: the tool fills, saves and moves page by page, waits for you to click Submit, then goes to the next client. Login, captcha, Submit, DSC and payment stay with you.</li></ol></div>"""'''
HOW_NEW = '''<div class=card><h2>How it works</h2><div class=how4>
<div><span class=num>1</span><b>Details</b><p>CIN, year and the forms to file.</p></div>
<div><span class=num>2</span><b>Uploads</b><p>This year's Schedule III workbook and last year's filed forms. These fill most of every form.</p></div>
<div><span class=num>3</span><b>Questions</b><p>A short list only you can answer (dates of meetings, changes during the year). Suggestions are pre-filled.</p></div>
<div><span class=num>4</span><b>Fill</b><p>One client: <i>Start filling</i>, then <b>Form Filler</b> in the Chrome side panel. Many: add them to the <b>Filing queue</b> and the tool fills, saves and moves page by page, then opens the next client.</p></div></div>
<div class=guard>@@SHIELD@@<span>Login, captcha, Submit, DSC and payment always stay with your team. The tool never submits or pays.</span></div></div>"""'''.replace("@@SHIELD@@", ICONS["shield"])

STEP_OLD = '''    return f"<div class=card id=s{n}><h2><span class=\\"num{' done' if done else ''}\\">{'&#10003;' if done else n}</span>{esc(title)}</h2>{inner}</div>"'''
STEP_NEW = '''    return f"<div class=\\"card step{' done' if done else ''}\\" id=s{n}><h2><span class=\\"num{' done' if done else ''}\\">{'&#10003;' if done else n}</span>{esc(title)}</h2>{inner}</div>"'''

CBODY_OLD = '''    body = (f"<p><a href=/>&larr; Filings</a></p><h2 style=\\"margin:4px 0 16px\\">{esc(folder.name)}</h2>"'''
CBODY_NEW = '''    flags = [st["details"], st["uploads"] and st["details"], st["questions"] and st["built"], st["fill"]]
    names = ["Details", "Upload data", "Questions", "Fill on MCA"]
    cur = next((i for i, x in enumerate(flags) if not x), None)
    stepper = "<nav class=stepper>" + "".join(
        f"<a href=#s{i + 1} class=\\"{'done' if x else 'cur' if i == cur else ''}\\"><span class=\\"num{' done' if x else ''}\\">{'&#10003;' if x else i + 1}</span>{nm}</a>"
        for i, (x, nm) in enumerate(zip(flags, names))) + "</nav>"
    n_done = sum(flags)
    meta = ((f"<span class=mono>{esc(cin)}</span>" if cin else "") + (f"<span>FY ended {esc(f.get('fy_end'))}</span>" if f.get("fy_end") else "")
            + "".join(f"<span>{FORM_LABEL.get(s, s)}</span>" for s in forms))
    head = (f"<div class=\\"phead chead\\"><div><div class=eyebrow><a href=/ style=\\"color:inherit;text-decoration:none\\">&larr; All filings</a></div>"
            f"<h1>{esc(folder.name)}</h1><div class=meta>{meta}</div></div>"
            f"<div class=prog><div class=l>Progress</div><div class=v>{n_done} of 4</div><div class=\\"bar{' full' if n_done == 4 else ''}\\"><i style=\\"width:{n_done * 25}%\\"></i></div></div></div>{stepper}")
    body = (head'''

QUEUE_RUN_OLD = '''<p>{run} {sub}</p>'''
QUEUE_RUN_NEW = '''<p style="margin:14px 0">{run} {sub}</p>'''


def main():
    p = MVP / "app.py"
    t = p.read_text(encoding="utf-8")
    m = re.search(r'^CSS = """.*?^"""\n', t, flags=re.S | re.M)
    if not m:
        sys.exit("CSS block not found")
    t = t[:m.start()] + CSS + t[m.end():]
    t = sub_once(t, SHELL_OLD, SHELL_NEW, "shell")
    t = sub_once(t, HOME_ROW_OLD, HOME_ROW_NEW, "home row")
    t = sub_once(t, HOME_BODY_OLD, HOME_BODY_NEW, "home body")
    t = sub_once(t, HOW_OLD, HOW_NEW, "how")
    t = sub_once(t, STEP_OLD, STEP_NEW, "step")
    t = sub_once(t, CBODY_OLD, CBODY_NEW, "client body")
    p.write_text(t, encoding="utf-8")

    q = MVP / "filing_queue.py"
    t = q.read_text(encoding="utf-8")
    t = sub_once(t, QUEUE_RUN_OLD, QUEUE_RUN_NEW, "queue run")
    q.write_text(t, encoding="utf-8")
    print("patched app.py and filing_queue.py")


if __name__ == "__main__":
    main()
