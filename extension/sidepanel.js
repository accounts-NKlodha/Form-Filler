// Side panel: buttons for Save form (Alt+Shift+D) and Form Filler (Alt+Shift+F) on the open MCA tab,
// plus the client picker. Talks to the tab's content.js (chrome.tabs.sendMessage) and to the
// local server on :8742 directly (the extension has host permission for it).
const BASE = 'http://127.0.0.1:8742';
const $ = id => document.getElementById(id);
const FORM_NAMES = { aoc4: 'AOC-4', 'aoc-4': 'AOC-4', mgt7a: 'MGT-7A', 'mgt-7a': 'MGT-7A', mgt7: 'MGT-7', 'adt-1': 'ADT-1', adt1: 'ADT-1' };
const formName = s => FORM_NAMES[s] || (s || '').toUpperCase();
let tabSlug = null, info = null;

$('ver').textContent = 'v' + chrome.runtime.getManifest().version;

async function api(path, body) {
  const r = await fetch(BASE + path, body === undefined ? {} : {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  const d = await r.json();
  if (!r.ok) throw new Error(d.error || ('HTTP ' + r.status));
  return d;
}

async function activeTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab;
}

function send(tab, cmd) {
  return new Promise(res => {
    chrome.tabs.sendMessage(tab.id, { type: 'mcafill-cmd', cmd }, r => {
      const err = chrome.runtime.lastError;
      res(err ? { ok: false, error: err.message } : (r || { ok: false }));
    });
  });
}

// ---------- server + client picker ----------
async function loadServer() {
  try {
    info = await api('/api/panel');
    $('srvdot').className = 'dot on';
    $('srv').textContent = 'Server running on port 8742';
  } catch (e) {
    info = null;
    $('srvdot').className = 'dot off';
    $('srv').textContent = 'Server not running: double-click start_server.bat';
  }
  renderClients();
  renderQueue();
}

function renderClients() {
  const sel = $('client');
  sel.innerHTML = '';
  if (!info) { sel.disabled = true; $('clientnote').textContent = ''; return; }
  const isAdt = /^adt/.test(tabSlug || '');
  if (isAdt) {
    sel.disabled = true;
    const o = document.createElement('option');
    o.textContent = info.adt1 && info.adt1.current ? `ADT-1: ${info.adt1.name || info.adt1.current}` : 'ADT-1: no company picked';
    sel.appendChild(o);
    $('clientnote').innerHTML = 'ADT-1 uses the ADT-1 companies list. Pick the company on the <a href="#" data-open="/adt1">ADT-1 page</a> or in the client\'s filing.';
    return;
  }
  sel.disabled = false;
  const ready = info.clients.filter(c => c.inputs);
  if (!ready.length) {
    const o = document.createElement('option');
    o.textContent = 'No client is ready yet';
    sel.appendChild(o);
    sel.disabled = true;
    $('clientnote').innerHTML = 'Start a filing in the <a href="#" data-open="/">filing app</a>: details, uploads, questions.';
    return;
  }
  if (!info.active) sel.appendChild(new Option('Pick the client…', ''));
  for (const c of ready) {
    const o = new Option(c.name + (c.forms.length ? '  (' + c.forms.map(formName).join(', ') + ')' : ''), c.name);
    o.selected = c.active;
    sel.appendChild(o);
  }
  const act = ready.find(c => c.active);
  $('clientnote').innerHTML = act
    ? `Form Filler uses <b>${esc(act.name)}</b>${act.cin ? ' (' + esc(act.cin) + ')' : ''}. Check it matches the draft you opened.`
    : 'Pick the client whose draft is open on this tab.';
}

$('client').addEventListener('change', async () => {
  const name = $('client').value;
  if (!name) return;
  try { await api('/api/active', { client: name }); } catch (e) { showStatus('Could not switch client: ' + e.message); }
  loadServer();
});

// ---------- filing queue ----------
function renderQueue() {
  const q = info && info.queue;
  const box = $('qstate');
  if (!q) { box.textContent = info ? 'Queue not available.' : ''; return; }
  box.innerHTML = q.job
    ? `${q.running ? '<b>Running</b>' : 'Paused'}: ${esc(q.job.client)} · ${esc(q.job.form)}. ${q.waiting} more waiting.`
    : (q.waiting ? `${q.waiting} waiting. Log in on MCA, then Start.` : 'Nothing queued. Add clients on the app\'s home page.');
  $('qstart').disabled = q.running || (!q.job && !q.waiting);
  $('qpause').disabled = !q.running;
}

$('qstart').addEventListener('click', async () => {
  try {
    const d = await api('/api/queue/start', {});
    if (!d.job) { showStatus(d.error || 'Nothing waiting.'); return; }
    showStatus(`Starting with ${d.job.client}. The form opens and starts filling by itself.`);
    const tab = await activeTab();
    if (tab && /^https:\/\/www\.mca\.gov\.in\//.test(tab.url || '')) {
      chrome.tabs.sendMessage(tab.id, { type: 'mcafill-cmd', cmd: 'goto', url: d.job.url }, () => {
        if (chrome.runtime.lastError) { chrome.tabs.update(tab.id, { url: d.job.url }); showStatus('Opening the form. When it has loaded, click Form Filler.'); }
      });
    } else showStatus('Switch to the MCA tab (logged in), then click Start again.');
  } catch (e) { showStatus('Could not start: ' + e.message); }
  loadServer();
});
$('qpause').addEventListener('click', async () => {
  try { await api('/api/queue/pause', {}); showStatus('The queue stops after the client being filled now.'); } catch (e) { showStatus(e.message); }
  loadServer();
});
$('qnext').addEventListener('click', async () => {
  const srn = $('qsrn').value.trim().toUpperCase();
  try {
    const a = await api('/queue/advance', { outcome: srn ? 'submitted' : 'saved', srn, note: srn ? 'SRN typed by staff' : 'SRN not noted' });
    $('qsrn').value = '';
    if (!a.next) { showStatus('Queue finished or paused.'); loadServer(); return; }
    const tab = await activeTab();
    chrome.tabs.sendMessage(tab.id, { type: 'mcafill-cmd', cmd: 'goto', url: a.nextUrl }, () => {
      if (chrome.runtime.lastError) chrome.tabs.update(tab.id, { url: a.nextUrl });
    });
    showStatus('Next: ' + a.name);
  } catch (e) { showStatus(e.message); }
  loadServer();
});

// ---------- the open tab ----------
async function probe() {
  const tab = await activeTab();
  const onMca = tab && /^https:\/\/www\.mca\.gov\.in\//.test(tab.url || '');
  let r = { ok: false };
  if (onMca) r = await send(tab, 'probe');
  const prev = tabSlug;
  tabSlug = r.ok ? r.slug : null;
  const p = $('page');
  if (r.ok) {
    p.className = '';
    p.textContent = `${formName(r.slug)} form open${r.busy ? ' (filling now…)' : ''}`;
  } else {
    p.className = 'warn';
    p.textContent = !onMca ? 'This tab is not the MCA portal. Switch to the MCA tab.'
      : /Receiving end does not exist|Could not establish/i.test(r.error || '')
        ? 'No MCA form found on this tab yet. Open the form draft and wait until it loads. If you just updated the extension, press F5 on this tab.'
        : 'No MCA form found on this tab yet. Open the form draft and wait until it loads.';
  }
  for (const id of ['dump', 'fill', 'values']) $(id).disabled = !r.ok || r.busy;
  if (prev !== tabSlug) renderClients();
}

async function run(cmd) {
  const tab = await activeTab();
  if (!tab) return;
  if (cmd === 'fill' && info && !/^adt/.test(tabSlug || '') && !info.active) {
    showStatus('Pick the client first (top of this panel).');
    return;
  }
  const r = await send(tab, cmd);
  if (!r.ok) showStatus('The MCA tab did not answer. Open the form draft, wait until it loads, then try again (press F5 if you just updated the extension).');
  else if (r.result === 'busy') showStatus('A fill is running. Click Stop first if you want to stop it.');
  setTimeout(probe, 400);
}

$('dump').addEventListener('click', () => run('dump'));
$('fill').addEventListener('click', () => run('fill'));
$('values').addEventListener('click', () => run('values'));
$('stop').addEventListener('click', () => run('stop'));

// ---------- page box mirror ----------
function showStatus(text) {
  const s = $('status');
  s.className = '';
  s.textContent = text;
}
chrome.runtime.onMessage.addListener(msg => {
  if (msg && msg.type === 'mcafill-status') {
    showStatus(msg.text + (msg.buttons && msg.buttons.length ? '\n\nButtons on the page: ' + msg.buttons.join(' · ') : ''));
  }
});

// ---------- links to the app ----------
document.addEventListener('click', e => {
  const a = e.target.closest('a[data-open], #openapp');
  if (!a) return;
  e.preventDefault();
  chrome.tabs.create({ url: BASE + (a.dataset.open || '/') });
});

const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

chrome.tabs.onActivated.addListener(() => probe());
chrome.tabs.onUpdated.addListener((id, ch) => { if (ch.status === 'complete') probe(); });
loadServer().then(probe);
setInterval(probe, 3000);
setInterval(loadServer, 15000);
