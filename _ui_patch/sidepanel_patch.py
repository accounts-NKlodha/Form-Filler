"""Restyle extension/sidepanel.html in the NKL Design Language. Only the <head> styles and the
header markup change; every id the script uses is kept."""
import re
import sys
from pathlib import Path

P = Path(__file__).resolve().parent.parent / "extension" / "sidepanel.html"

STYLE = """<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin="anonymous">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
  :root { --background:oklch(0.985 0.004 95); --foreground:oklch(0.235 0.014 260); --surface:oklch(0.972 0.005 95); --card:oklch(1 0 0);
    --primary:oklch(0.285 0.038 258); --primary-foreground:oklch(0.985 0.004 95); --secondary:oklch(0.955 0.006 95); --secondary-foreground:oklch(0.3 0.02 258);
    --muted-foreground:oklch(0.53 0.014 258); --accent:oklch(0.94 0.012 95); --brass:oklch(0.62 0.086 76); --brass-foreground:oklch(0.99 0.004 95);
    --destructive:oklch(0.52 0.176 27); --success:oklch(0.49 0.088 158); --warning-foreground:oklch(0.24 0.03 72);
    --border:oklch(0.905 0.006 95); --border-strong:oklch(0.84 0.008 95); --ring:oklch(0.62 0.086 76);
    --sidebar:oklch(0.256 0.024 258); --sidebar-foreground:oklch(0.87 0.01 95); --sidebar-border:oklch(0.34 0.022 258);
    --shadow-xs:0 1px 2px 0 rgb(0 0 0 / 0.05); }
  * { box-sizing: border-box; }
  body { margin: 0; font: 13px/1.45 "IBM Plex Sans", ui-sans-serif, system-ui, sans-serif; font-feature-settings: "cv05","ss01"; -webkit-font-smoothing: antialiased; color: var(--foreground); background: var(--background); }
  :focus-visible { outline: 2px solid var(--ring); outline-offset: 2px; }
  header { background: var(--sidebar); color: var(--sidebar-foreground); padding: 12px 14px; display: flex; align-items: center; gap: 10px; border-bottom: 2px solid var(--brass); }
  .tile { width: 32px; height: 32px; border-radius: 6px; background: var(--brass); color: var(--brass-foreground); display: grid; place-items: center; font-weight: 600; font-size: 15px; flex: none; }
  header h1 { font-size: 14px; font-weight: 600; margin: 0; color: oklch(0.97 0.005 95); }
  header .sub { font-size: 11.5px; margin-top: 1px; opacity: .85; }
  .dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; background: var(--sidebar-foreground); opacity: .6; margin-right: 6px; vertical-align: 1px; }
  .dot.on { background: oklch(0.72 0.12 158); opacity: 1; animation: pulse 2.4s ease-in-out infinite; } .dot.off { background: oklch(0.65 0.17 27); opacity: 1; }
  @keyframes pulse { 0%,100% { box-shadow: 0 0 0 0 oklch(0.72 0.12 158 / .5); } 50% { box-shadow: 0 0 0 4px oklch(0.72 0.12 158 / 0); } }
  main { padding: 12px 12px 24px; }
  .card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 12px 14px; margin-bottom: 12px; box-shadow: var(--shadow-xs); }
  .card h2 { font-size: 11px; line-height: 16px; font-weight: 600; text-transform: uppercase; letter-spacing: .09em; color: var(--muted-foreground); margin: 0 0 8px; display: flex; align-items: center; gap: 8px; }
  .card h2::before { content: ""; width: 12px; height: 2px; background: var(--brass); }
  select, input { width: 100%; height: 34px; padding: 0 10px; font: inherit; color: var(--foreground); background: var(--card); border: 1px solid var(--border-strong); border-radius: 7px; box-shadow: var(--shadow-xs); }
  button { font: inherit; font-weight: 500; cursor: pointer; border: 1px solid var(--border-strong); border-radius: 7px; background: var(--card); color: var(--foreground); box-shadow: var(--shadow-xs); transition: background .15s; }
  button:hover:not(:disabled) { background: var(--accent); }
  .big { display: block; width: 100%; text-align: left; padding: 10px 12px; margin: 8px 0; background: var(--secondary); color: var(--secondary-foreground); }
  .big b { display: block; font-size: 14px; font-weight: 600; }
  .big small { color: var(--muted-foreground); }
  .big.fill { background: var(--primary); border-color: var(--primary); color: var(--primary-foreground); position: relative; padding-left: 30px; }
  .big.fill::before { content: ""; position: absolute; left: 13px; top: 16px; width: 8px; height: 8px; border-radius: 50%; background: var(--brass); }
  .big.fill small { color: oklch(0.87 0.01 95); }
  .big.fill:hover:not(:disabled) { background: oklch(0.33 0.04 258); }
  .big:disabled, button:disabled { opacity: .5; cursor: not-allowed; }
  .row { display: flex; gap: 8px; }
  .row button { flex: 1; height: 34px; padding: 0 8px; }
  #qstart { background: var(--primary); border-color: var(--primary); color: var(--primary-foreground); }
  .row button.stop { color: var(--destructive); border-color: oklch(0.52 0.176 27 / .35); background: oklch(0.52 0.176 27 / .05); }
  #page { font-weight: 600; padding: 8px 10px; border-radius: 7px; background: oklch(0.49 0.088 158 / .08); border: 1px solid oklch(0.49 0.088 158 / .3); color: var(--success); }
  #page.warn { color: var(--warning-foreground); font-weight: 400; background: oklch(0.68 0.126 72 / .12); border-color: oklch(0.68 0.126 72 / .45); }
  #status { white-space: pre-wrap; font-size: 12.5px; max-height: 260px; overflow: auto; font-family: "IBM Plex Mono", ui-monospace, monospace; background: var(--surface); border: 1px solid var(--border); border-radius: 7px; padding: 8px 10px; }
  #qstate { padding: 8px 10px; border-radius: 7px; background: var(--surface); border: 1px solid var(--border); }
  ol { margin: 4px 0 0 18px; padding: 0; } li { margin: 3px 0; }
  a { color: var(--primary); font-weight: 500; }
  details summary { cursor: pointer; }
  .muted { color: var(--muted-foreground); font-size: 12px; }
  @media (prefers-reduced-motion: reduce) { * { animation: none !important; transition: none !important; } }
</style>"""

HEADER_OLD = """<header>
  <h1>MCA filler <span id="ver" style="font-weight:400;opacity:.7"></span></h1>
  <div class="sub"><span id="srvdot" class="dot"></span><span id="srv">Checking the server…</span></div>
</header>"""
HEADER_NEW = """<header>
  <span class="tile">N</span>
  <div>
    <h1>ROC Autopilot <span id="ver" style="font-weight:400;opacity:.65;font-size:12px"></span></h1>
    <div class="sub"><span id="srvdot" class="dot"></span><span id="srv">Checking the server…</span></div>
  </div>
</header>"""

t = P.read_text(encoding="utf-8")
t, n = re.subn(r"<style>.*?</style>", lambda m: STYLE, t, count=1, flags=re.S)
if n != 1 or t.count(HEADER_OLD) != 1:
    sys.exit("sidepanel.html not as expected; nothing written")
t = t.replace(HEADER_OLD, HEADER_NEW).replace('<input id="qsrn" placeholder="SRN" style="flex:1;padding:6px;border:1px solid #d9e2ec;border-radius:4px">',
                                              '<input id="qsrn" placeholder="SRN" style="flex:1">')
P.write_text(t, encoding="utf-8")
print("sidepanel.html restyled")
