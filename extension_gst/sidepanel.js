// GST portal reader: reads what the logged-in staff member can already see and download, and hands each file to
// Form Filler on this PC, which checks the GSTIN and the year and files it in the client folder.
// Read only: every portal call below is a GET. Nothing is saved, submitted, filed or paid.
const APP = 'http://127.0.0.1:8742';
const RET = 'https://return.gst.gov.in';
const G2B = 'https://gstr2b.gst.gov.in';
const PACE = 1500;   // ms between portal calls
const KINDS = [
  ['gstr3b', 'GSTR-3B'], ['gstr1_summary', 'GSTR-1 summary'], ['gstr2b', 'GSTR-2B'],
  ['gstr2a', 'GSTR-2A'], ['gstr1', 'GSTR-1 invoice detail'],
];
const $ = (id) => document.getElementById(id);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const run = { note: {}, have: {} };
let busy = false, aliveTimer = null, aliveUntil = 0;

function log(t) { $('log').textContent = new Date().toTimeString().slice(0, 5) + '  ' + t + '\n' + $('log').textContent; }
function state(t) { $('state').textContent = t; }
function mname(p) { return 'Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec'.split(' ')[+p.slice(0, 2) - 1] + ' ' + p.slice(2); }
function past(p) { const d = new Date(); return +p.slice(2) * 12 + +p.slice(0, 2) <= d.getFullYear() * 12 + d.getMonth() + 1; }
function draw(months) {
  $('rows').replaceChildren(...KINDS.map(([k, label]) => {
    const tr = document.createElement('tr');
    const n = (run.have[k] || []).filter((p) => !months || months.includes(p)).length;
    for (const [text, cls] of [[label, ''], [months ? n + ' of 12' : '', 'n'], [run.note[k] || '', '']]) {
      const td = document.createElement('td'); td.textContent = text; td.className = cls; tr.appendChild(td);
    }
    return tr;
  }));
}

// One GET inside the portal tab, with the staff member's own session.
async function inPage(tabId, url) {
  const [r] = await chrome.scripting.executeScript({
    target: { tabId }, world: 'MAIN', args: [url],
    func: async (u) => {
      try {
        const r = await fetch(u, { credentials: 'include', headers: { Accept: 'application/json, text/plain, */*' } });
        return { status: r.status, text: await r.text() };
      } catch (e) { return { status: 0, text: '', error: String(e) }; }
    },
  });
  return r.result || { status: 0, text: '', error: 'no answer from the page' };
}
function parse(text) { try { return JSON.parse(text); } catch (e) { return null; } }
function loggedOut(r) { return r.status === 401 || r.status === 403 || /access denied|session (has )?expired|<title>\s*login/i.test(r.text.slice(0, 4000)); }
function portalSays(j) {
  const e = j && (j.error || j.errorDesc || j.message || (j.data && j.data.msg));
  return typeof e === 'string' ? e : e ? (e.message || e.detailMessage || e.error_cd || JSON.stringify(e).slice(0, 120)) : '';
}

async function appGet(path) {
  const r = await fetch(APP + path);
  return { status: r.status, json: await r.json() };
}
async function hand(body, ctx) {   // give one file to Form Filler
  const r = await fetch(`${APP}/gst/api/ingest?t=${ctx.token}&fy=${ctx.fy}&user=${encodeURIComponent($('who').value.trim())}`, { method: 'POST', body });
  const j = await r.json().catch(() => ({ error: 'Form Filler did not answer' }));
  return r.ok ? j : { error: j.error || 'Form Filler refused the file' };
}
async function tabOn(origin) {
  const tabs = await chrome.tabs.query({ url: origin + '/*' });
  return (tabs.find((t) => t.active) || tabs[0] || {}).id;
}

// Month by month for one kind of return. `get(p)` returns {body} to hand over, {skip: why} or {stop: why}.
async function each(kind, periods, ctx, get) {
  let saved = 0, skipped = 0; const notes = []; const pending = [];
  for (const p of periods) {
    if (!past(p)) continue;
    if (!ctx.again && (run.have[kind] || []).includes(p)) { skipped++; continue; }
    run.note[kind] = 'Reading ' + mname(p) + '...'; draw(ctx.months);
    const got = await get(p);
    if (got.stop) { run.note[kind] = got.stop; draw(ctx.months); return null; }
    if (got.pending) pending.push(p);
    else if (got.skip) notes.push(mname(p) + ': ' + got.skip);
    for (const body of got.bodies || []) {
      const j = await hand(body, ctx);
      if (j.error) notes.push(mname(p) + ': ' + j.error);
      else { saved++; (run.have[j.kind] = run.have[j.kind] || []).includes(j.period) || run.have[j.kind].push(j.period); }
    }
    await sleep(PACE);
  }
  run.note[kind] = [saved ? saved + ' filed' : '', skipped ? skipped + ' already there' : '', pending.length ? pending.length + ' being made by the portal' : '', notes.length ? notes.length + ' not read' : ''].filter(Boolean).join(', ') || 'Nothing to read';
  notes.forEach((n) => log(KINDS.find((k) => k[0] === kind)[1] + ', ' + n));
  draw(ctx.months);
  return pending;
}
const summary = (tab, path) => async (p) => {
  const r = await inPage(tab, path + p);
  if (loggedOut(r)) return { stop: 'The portal session has ended. Log in again and press Read the year.' };
  const j = parse(r.text);
  if (!j || !j.data || j.error) return { skip: portalSays(j) || 'the portal gave no data (status ' + r.status + ')' };
  return { bodies: [r.text] };
};
// GSTR-2A and GSTR-1 detail files are made by the portal on request and take up to 20 minutes.
const offline = (tab, typ) => async (p) => {
  const r = await inPage(tab, `${RET}/returns/auth/api/offline/download/generate?flag=0&rtn_prd=${p}&rtn_typ=${typ}`);
  if (loggedOut(r)) return { stop: 'The portal session has ended. Log in again and press Read the year.' };
  const j = parse(r.text);
  const urls = j && j.data && Array.isArray(j.data.url) ? j.data.url.filter((u) => /^https:\/\/files\.gst\.gov\.in\//.test(u)) : [];
  if (!urls.length) return { pending: true };
  const bodies = [];
  for (const u of urls) {
    try {
      const f = await fetch(u);
      if (!f.ok) throw new Error('status ' + f.status);
      bodies.push(await f.arrayBuffer());
    } catch (e) { return { skip: 'the file is ready but could not be fetched (' + e.message + '). Download it on the portal and add it on the GST page of Form Filler.' }; }
  }
  return { bodies };
};

// On the portal's welcome page after login: press its own "Return Dashboard" button (plain navigation, nothing is filed).
async function openDashboard() {
  const SVC = 'https://services.gst.gov.in';
  const tab = await tabOn(SVC);
  if (!tab) return null;
  state('Opening the Returns dashboard...');
  const [r] = await chrome.scripting.executeScript({
    target: { tabId: tab }, world: 'MAIN',
    func: () => {
      const b = [...document.querySelectorAll('a,button')].find((x) => /^return dashboard\b/i.test(x.innerText.trim()));
      if (b) b.click();
      return !!b;
    },
  });
  if (!r || !r.result) return null;
  for (let i = 0; i < 20; i++) {
    await sleep(1000);
    const t = await chrome.tabs.get(tab).catch(() => null);
    if (t && t.url && t.url.startsWith(RET) && t.status === 'complete') { await sleep(1500); return tab; }
  }
  return null;
}

async function go() {
  if (busy) return;
  busy = true; $('go').disabled = true; run.note = {}; draw();
  try {
    const fy = $('fy').value;
    let a;
    try { a = await appGet('/gst/api/clients?fy=' + fy); } catch (e) { return state('Form Filler is not running on this PC. Start it and try again.'); }
    const ctx = { fy, token: a.json.token, months: a.json.months, next: a.json.next_months, again: $('again').checked };
    let tab = await tabOn(RET);
    if (!tab) tab = await openDashboard();
    if (!tab) return state('No logged-in GST portal tab found. Log in at gst.gov.in, then press Read the year.');
    // whose login is this? the first filed GSTR-3B says
    state('Checking which GSTIN is logged in...');
    let gstin = '';
    for (const p of ctx.months.filter(past)) {
      const r = await inPage(tab, `${RET}/returns/auth/api/gstr3b/summary?rtn_prd=${p}`);
      if (loggedOut(r)) return state('The portal session has ended, or this tab is not past the login. Log in, open the Returns dashboard and try again.');
      gstin = ((parse(r.text) || {}).data || {}).gstin || '';
      if (gstin) break;
      await sleep(PACE);
    }
    if (!gstin) return state('Could not read a filed GSTR-3B for FY ' + fy + ', so the GSTIN is not known. Check the year.');
    const s = await appGet(`/gst/api/status?gstin=${gstin}&fy=${fy}`);
    if (s.status !== 200) return state(s.json.error || 'Form Filler does not know GSTIN ' + gstin);
    run.have = s.json.have; draw(ctx.months);
    state(`Reading FY ${fy} for ${s.json.client} (${gstin}). Keep the portal tab open.`);
    alive(tab);
    if (await each('gstr3b', ctx.months, ctx, summary(tab, `${RET}/returns/auth/api/gstr3b/summary?rtn_prd=`)) === null) return;
    if (await each('gstr1_summary', ctx.months, ctx, summary(tab, `${RET}/returns/auth/api/gstr1/summary?rtn_prd=`)) === null) return;
    const tab2b = await tabOn(G2B);
    if (!tab2b) { run.note.gstr2b = 'Open GSTR-2B once (step 2 above), then read again'; draw(ctx.months); }
    else {
      await each('gstr2b', ctx.months.concat(ctx.next), ctx, summary(tab2b, `${G2B}/gstr2b/auth/api/gstr2b/getjson?rtnprd=`));
    }
    // The portal makes these files on request. Ask once, then look again every minute until they arrive.
    let wait = { gstr2a: ctx.months, gstr1: ctx.months };
    const typ = { gstr2a: 'GSTR2A', gstr1: 'GSTR1' };
    for (let round = 0; round <= 30; round++) {
      for (const k of Object.keys(wait)) {
        if (!wait[k].length) continue;
        const left = await each(k, wait[k], Object.assign({}, ctx, { again: ctx.again && round === 0 }), offline(tab, typ[k]));
        if (left === null) return;
        wait[k] = left;
      }
      const n = wait.gstr2a.length + wait.gstr1.length;
      if (!n) break;
      if (round === 30) { state(`${n} file(s) are still being made by the portal after 30 minutes. Press Read the year again later.`); return; }
      state(`Waiting for the portal to make ${n} file(s). Looking again every minute (${round + 1} of 30). Keep this panel and the portal tab open.`);
      await sleep(60000);
    }
    state(`Done for ${s.json.client}. Open the GST page of Form Filler to see the checks.`);
  } catch (e) {
    state('Stopped: ' + (e && e.message || e)); log(String(e && e.stack || e));
  } finally { busy = false; $('go').disabled = false; }
}

// Optional: a light status call every minute so the portal does not log an idle user out while files are being made.
function alive(tab) {
  clearInterval(aliveTimer);
  if (!$('alive').checked) return;
  aliveUntil = Date.now() + 40 * 60 * 1000;
  aliveTimer = setInterval(async () => {
    if (Date.now() > aliveUntil || !$('alive').checked) return clearInterval(aliveTimer);
    { try { await inPage(tab, RET + '/services/api/ustatus'); } catch (e) { clearInterval(aliveTimer); } }
  }, 60000);
}

(function init() {
  const d = new Date(), y = d.getFullYear() - (d.getMonth() < 3 ? 2 : 1);
  for (const a of [y, y - 1, y - 2, y + 1]) {
    const o = document.createElement('option'); o.textContent = a + '-' + String((a + 1) % 100).padStart(2, '0'); $('fy').appendChild(o);
  }
  chrome.storage.local.get(['who'], (v) => { $('who').value = v.who || ''; });
  $('who').addEventListener('change', () => chrome.storage.local.set({ who: $('who').value.trim() }));
  $('go').addEventListener('click', go);
  draw();
})();
