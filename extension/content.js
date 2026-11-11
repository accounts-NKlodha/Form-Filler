// MCA form filler, extension side (isolated world).
//   Alt+Shift+D  dump the form's field structure (no values) to the local server + Downloads
//   Alt+Shift+F  fetch the fill plan for this form from the local server, confirm, fill, Save
//   Alt+Shift+S  side panel: every label + value, drag onto MCA boxes or click Fill per field
//   Alt+Shift+X  stop a running fill (plain Esc is left to the portal, e.g. to close a date picker)
//   The side panel (toolbar icon) has the same actions as buttons: Save form = D, Form Filler = F.
// Talks to page.js (page world) via CustomEvents; to the local server via background.js.
(() => {
  if (window.__mcaFillContent) return;
  window.__mcaFillContent = true;

  const hasForm = () => !!document.querySelector('[id^="guideContainer-rootPanel"]');
  const slug = () => {
    const m = location.pathname.match(/form-([a-z0-9_-]+)\.html/i);
    return (m ? m[1] : location.pathname.split('/').pop().replace(/\.html$/, '')).toLowerCase();
  };
  let busy = false;

  // ---------- page.js bridge ----------
  let seq = 0;
  const pending = {};
  document.addEventListener('mcafill:res', ev => {
    const msg = JSON.parse(ev.detail);
    const p = pending[msg.id];
    if (p) { delete pending[msg.id]; p(msg.res); }
  });
  document.addEventListener('mcafill:progress', ev => {
    const p = JSON.parse(ev.detail);
    status(`Filling ${p.done}/${p.total}<br><small>${esc(p.section || '')}</small><br><b>${esc(p.label || '')}</b><br><small>Alt+Shift+X = stop</small>`);
  });
  function page(op, extra = {}) {
    const id = ++seq;
    return new Promise(res => {
      pending[id] = res;
      document.dispatchEvent(new CustomEvent('mcafill:req', { detail: JSON.stringify({ id, op, ...extra }) }));
    });
  }

  // ---------- server bridge ----------
  function server(path, body) {
    return new Promise(res => {
      // After the extension is reloaded, this tab's old copy can no longer reach it: say so instead of hanging.
      const stale = { ok: false, error: 'the extension was updated: press F5 to refresh this page, then try again' };
      const timer = setTimeout(() => res(stale), 8000);
      try {
        chrome.runtime.sendMessage({ path, body: body === undefined ? undefined : JSON.stringify(body) }, r => {
          clearTimeout(timer);
          res(r || { ok: false, error: chrome.runtime.lastError ? chrome.runtime.lastError.message : 'no reply' });
        });
      } catch (e) { clearTimeout(timer); res(stale); }
    });
  }

  // ---------- UI ----------
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  let box = null;
  function panel() {
    if (box && document.body.contains(box)) return box;
    box = document.createElement('div');
    box.style.cssText = 'position:fixed;right:16px;bottom:16px;z-index:2147483647;max-width:380px;background:#102a43;color:#fff;' +
      'font:13px/1.4 Segoe UI,Arial,sans-serif;padding:12px 14px;border-radius:8px;box-shadow:0 4px 16px rgba(0,0,0,.35)';
    document.body.appendChild(box);
    return box;
  }
  function status(html, buttons = []) {
    const b = panel();
    b.innerHTML = `<div style="font-weight:600;margin-bottom:4px">MCA filler <span style="font-weight:400;opacity:.7">v${chrome.runtime.getManifest().version}</span></div><div>${html}</div>`;
    if (buttons.length) {
      const row = document.createElement('div');
      row.style.cssText = 'margin-top:10px;display:flex;gap:8px;flex-wrap:wrap';
      for (const [label, fn, primary] of buttons) {
        const btn = document.createElement('button');
        btn.textContent = label;
        btn.style.cssText = `padding:5px 12px;border:0;border-radius:4px;cursor:pointer;font:inherit;` +
          (primary ? 'background:#3ebd93;color:#102a43;font-weight:600' : 'background:#486581;color:#fff');
        btn.addEventListener('click', ev => { ev.preventDefault(); ev.stopPropagation(); fn(); });
        row.appendChild(btn);
      }
      b.appendChild(row);
    }
    mirror(html, buttons.map(x => x[0]));
  }
  // Copy of the box text for the side panel (it shows what the page box says).
  function mirror(html, buttons) {
    const t = document.createElement('div');
    t.innerHTML = String(html).replace(/<br\s*\/?>|<\/li>/gi, '\n');
    try {
      chrome.runtime.sendMessage({ type: 'mcafill-status', text: t.innerText || t.textContent, buttons }, () => void chrome.runtime.lastError);
    } catch (e) { /* extension reloaded: this tab needs F5 */ }
  }
  const close = () => { if (box) box.remove(); box = null; };

  function download(name, obj) {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([JSON.stringify(obj, null, 1)], { type: 'application/json' }));
    a.download = name;
    document.body.appendChild(a); a.click(); a.remove();
  }
  const stamp = () => new Date().toISOString().replace(/[-:]/g, '').replace('T', '_').slice(0, 15);

  // ---------- dump ----------
  async function doDump() {
    busy = true;
    status('Reading form structure…');
    const d = await page('dump');
    busy = false;
    if (!d || d.error) { status('Dump failed: ' + esc(d && d.error), [['Close', close]]); return; }
    const tables = new Set(d.fields.filter(f => f.repeat).map(f => f.repeat.groupKey || f.repeat.title)).size;
    const r = await server('/dump', d);
    download(`mca_dump_${d.slug}_${stamp()}.json`, d);
    let total = null;
    try { total = JSON.parse(r.text); } catch (e) { /* server down */ }
    const where = r.ok && total ? `Saved ${esc(d.slug.toUpperCase())} structure: <b>${total.added}</b> new fields, ` +
      `<b>${total.total}</b> in total across ${total.pages} page(s).<br>Go to the next page with the portal's own buttons and press Alt+Shift+D again.`
      : 'Server not running: the file is in Downloads.';
    status(`This page of <b>${esc(d.slug.toUpperCase())}</b>: ${d.fields.filter(f => f.rendered).length} fields on screen ` +
      `(${d.fields.length} in the form model), ${tables} repeatable tables, source ${esc(d.source)}` +
      `${d.modelError ? ' (model error: ' + esc(d.modelError) + ')' : ''}.<br>${where}`, [['Close', close]]);
  }

  // ---------- fill ----------
  async function doFill() {
    status('Getting fill plan from the MCA filler server…');
    const r = await server('/plan?slug=' + encodeURIComponent(slug()));
    if (!r.ok) {
      let msg = r.error || r.text || ('HTTP ' + r.status);
      try { msg = JSON.parse(r.text).error || msg; } catch (e) { /* plain text */ }
      status(`Could not get a plan: ${esc(msg)}<br><small>Start the server (start_server.bat) or load a plan file.</small>`,
        [['Load plan file…', pickFile, true], ['Close', close]]);
      return;
    }
    confirmPlan(JSON.parse(r.text));
  }

  function pickFile() {
    const inp = document.createElement('input');
    inp.type = 'file';
    inp.accept = '.json,application/json';
    inp.addEventListener('change', async () => {
      const f = inp.files[0];
      if (!f) return;
      try { confirmPlan(JSON.parse(await f.text())); } catch (e) { status('Not a plan file: ' + esc(e.message), [['Close', close]]); }
    });
    inp.click();
  }

  function confirmPlan(plan) {
    if (plan.slug && plan.slug !== slug()) {
      status(`This plan is for <b>${esc(plan.slug.toUpperCase())}</b> but this page is <b>${esc(slug().toUpperCase())}</b>.`, [['Close', close]]);
      return;
    }
    const cells = (plan.tables || []).reduce((n, t) => n + t.rows.reduce((m, r) => m + r.length, 0), 0);
    status(`Client: <b>${esc(plan.client)}</b><br>Form: <b>${esc((plan.slug || '').toUpperCase())}</b><br>` +
      `${plan.fields.length} fields, ${cells} table cells${(plan.errors || []).length ? `, <span style="color:#ffb4a2">${plan.errors.length} Excel errors</span>` : ''}<br>` +
      `<small>Workbook: ${esc(plan.workbook || '')}</small><br>Fill now? It fills this page and then shows you which Save to click. It never clicks Submit.`,
      [['Fill', () => runFill(plan), true], ['Cancel', close]]);
    if (autorun && plan.autoAdvance && plan.autoContinue) {
      autorun = false;
      stopLoop = false;
      let n = 5, done = false;
      const go = () => { if (!done) { done = true; runFill(plan); } };
      const tick = () => {
        if (done) return;
        if (stopLoop) { done = true; status('Stopped. Click Form Filler to carry on.', [['Close', close]]); return; }
        if (n <= 0) { go(); return; }
        status(`Next client: <b>${esc(plan.client)}</b> · ${esc((plan.slug || '').toUpperCase())}<br>Starting in ${n} s. Check the name.`,
          [['Start now', go, true], ['Stop', () => { stopLoop = true; tick(); }]]);
        n--;
        setTimeout(tick, 1000);
      };
      tick();
      return;
    }
    if (autorun && plan.autoAdvance) {
      autorun = false;
      status(`Next company: <b>${esc(plan.client)}</b><br>Continue filing ADT-1 for it?`,
        [['Continue', () => runFill(plan), true], ['Stop here', close]]);
    }
  }

  let stopLoop = false, autorun = false;
  async function runFill(plan, force = false, round = 0, idle = 0) {
    if (round === 0) stopLoop = false;
    // Plans that bring their attachments (ADT-1): upload the ones on this page that are still empty.
    const attachLog = [];
    if ((plan.attachments || []).length) {
      const st = await page('attachState', { list: plan.attachments });
      for (let i = 0; i < plan.attachments.length && Array.isArray(st); i++) {
        const a = plan.attachments[i];
        if (st[i] === 'other-page') continue;
        const entry = { code: a.code, key: a.key, label: a.label + ' (attachment)', status: 'unchanged', msg: a.file };
        if (st[i] === 'empty' && !stopLoop) {
          status(`Uploading <b>${esc(a.file)}</b><br><small>${esc(a.label)}</small>`);
          const r = await server(a.url || `/adt1/file?cin=${encodeURIComponent(a.cin)}&kind=${encodeURIComponent(a.kind)}`);
          let d = null;
          try { d = JSON.parse(r.text); } catch (e) { /* below */ }
          if (!r.ok || !d || !d.b64) Object.assign(entry, { status: 'failed', msg: (d && d.error) || r.error || 'file not served' });
          else {
            Object.assign(entry, await page('attach', { att: a, name: d.name, b64: d.b64 }));
            await new Promise(r => setTimeout(r, 2000));  // Rohit: 2 s between uploads
          }
        }
        attachLog.push(entry);
      }
      force = true;  // uploads handled here, so skip the "attach first" prompt
    }
    if (!force) {
      const missing = await page('uploadsMissing');
      if (Array.isArray(missing) && missing.length) {
        status(`Before filling, attach on this page (the portal needs it before later sections open):<ul style="margin:6px 0 0 16px;padding:0">` +
          missing.map(m => `<li>${esc(m)}</li>`).join('') + `</ul><small>Upload it with the portal's own button, then click Continue.</small>`,
          [['Continue', () => runFill(plan), true], ['Fill anyway', () => runFill(plan, true)], ['Cancel', close]]);
        return;
      }
    }
    busy = true;
    status('Starting…');
    // On the attachments page of an autoAdvance plan the last Save ends this company: no Next (that leads to Submit).
    const lastPage = plan.autoAdvance && !plan.watchSubmit && attachLog.length > 0;
    const res = await page('fill', { plan: lastPage ? { ...plan, autoNext: false } : plan });
    busy = false;
    if (!res || res.error) { status('Fill stopped with an error: ' + esc(res && res.error), [['Close', close]]); return; }
    res.log = attachLog.concat(res.log);
    const count = {};
    for (const e of res.log) count[e.status] = (count[e.status] || 0) + 1;
    // Field names and statuses only: client values never go into the log.
    const log = {
      client: plan.client, slug: plan.slug, workbook: plan.workbook, url: location.origin + location.pathname,
      finishedAt: new Date().toISOString(), counts: count, save: res.save,
      entries: res.log.map(({ value, ...rest }) => rest),
    };
    const sent = await server('/log', log);
    // Plans with autoSave (ADT-1): keep going section by section and page by page until a round makes no progress.
    const idleNow = count.filled ? 0 : idle + 1;
    // Carry on only to the next page (Next clicked) or the next section of this page; no Next = stop here.
    if (plan.autoSave && res.save.clicked && (res.save.next || res.save.more) && !count.failed && round < 20 && idleNow < 2 && !stopLoop) {
      status(`Round ${round + 1}: filled <b>${count.filled || 0}</b>. ${esc(res.save.msg)}. Continuing… <small>(Alt+Shift+X stops)</small>`);
      setTimeout(() => { if (!stopLoop) runFill(plan, true, round + 1, idleNow); else status('Stopped.', [['Close', close]]); }, 2500);
      return;
    }
    // Filing queue: last page saved. Staff click Submit; we wait for the SRN, then open the next client's form.
    if (plan.watchSubmit && res.save.lastPage && !count.failed && !stopLoop) {
      status(`<b>${esc(plan.client)}</b>: every page is filled and saved.<br><b style="color:#ffd166">Check the form, then click the outlined Submit yourself.</b>` +
        `<br>The tool waits for the SRN, then opens the next client. <small>(Alt+Shift+X stops)</small>`);
      busy = true;
      const w = await page('awaitSubmit', {});
      busy = false;
      if (w && w.srn) { await queueNext(plan, 'submitted', w.srn, count, ''); return; }
      status(`No SRN seen for <b>${esc(plan.client)}</b> (${esc(w && w.msg)}).<br>If you submitted, note the SRN in the app's queue.`,
        [['Next client', () => queueNext(plan, 'saved', '', count, 'SRN not read'), true], ['Wait again', () => runFill(plan, true)], ['Close', close]]);
      return;
    }
    if (plan.watchSubmit && !stopLoop && (count.failed || !res.save.clicked)) {
      const bad = res.log.filter(e => ['failed', 'manual'].includes(e.status)).slice(0, 8)
        .map(e => `<li>${esc(e.code || '')} ${esc(e.label)}: ${esc(e.msg || e.status)}</li>`).join('');
      status(`<b>${esc(plan.client)}</b> needs you on this page.<br>${esc(res.save.msg || '')}` +
        (bad ? `<ul style="margin:6px 0 0 16px;padding:0;max-height:180px;overflow:auto">${bad}</ul>` : '') +
        `<small>Fix it on the portal, then Fill again. Or move on and come back to this client later.</small>`,
        [['Fill again', () => runFill(plan, true), true],
         ['Skip to next client', () => queueNext(plan, 'held', '', count, (res.log.find(e => e.status === 'failed') || {}).label || res.save.msg || 'stopped')],
         ['Close', close]]);
      return;
    }
    // Company done (attachments page saved, nothing failed): move on to the next ready company on a fresh form.
    if (lastPage && res.save.clicked && !res.save.more && !count.failed && !stopLoop &&
        attachLog.every(e => ['filled', 'unchanged'].includes(e.status))) {
      const adv = await server('/adt1/advance', {});
      let a = null;
      try { a = JSON.parse(adv.text); } catch (e) { /* below */ }
      if (a && a.next) {
        status(`<b>${esc(plan.client)}</b> saved.<br>Next: <b>${esc(a.name)}</b> (${a.left} left)… <small>(Alt+Shift+X stops)</small>`);
        setTimeout(() => {
          if (stopLoop) { status('Stopped before the next company.', [['Close', close]]); return; }
          try { sessionStorage.setItem('mcafill_autorun', JSON.stringify({ t: Date.now(), name: a.name, left: a.left })); } catch (e) { /* ignore */ }
          location.href = plan.nextUrl;
        }, 3000);
        return;
      }
      status(`<b>${esc(plan.client)}</b> saved.<br>${a && a.next === null ? 'No more companies with all attachments and a signatory.' : 'Could not pick the next company: ' + esc((a && a.error) || adv.error || '')}`, [['Close', close]]);
      return;
    }
    if (plan.autoSave) page('notices', { on: false });
    download(`mca_fill_log_${plan.slug}_${stamp()}.json`, log);
    const order = ['filled', 'unchanged', 'next-section', 'section-save', 'skipped-readonly', 'hidden', 'manual', 'other-page', 'failed', 'not-run'];
    const summary = order.filter(k => count[k]).map(k => `${k}: <b>${count[k]}</b>`).join('<br>');
    const problems = res.log.filter(e => ['failed', 'manual', 'hidden'].includes(e.status)).slice(0, 12)
      .map(e => `<li>${esc(e.code || '')} ${esc(e.label)}: ${esc(e.status)}${e.msg ? ' (' + esc(e.msg) + ')' : ''}</li>`).join('');
    status(`${summary}<br><b style="color:#ffd166">${esc(res.save.msg)}</b><br>${problems ? '<ul style="margin:6px 0 0 16px;padding:0;max-height:200px;overflow:auto">' + problems + '</ul>' : ''}` +
      (count['other-page'] ? `<small>${count['other-page']} fields are on other pages: go there with the portal's own buttons and press Alt+Shift+F again.</small><br>` : '') +
      `<small>Log ${sent.ok ? 'saved in the client folder and ' : ''}downloaded. Review this page before you move on.</small>`, [['Close', close]]);
  }

  // Filing queue: record this client's result and open the next client's form (it starts filling by itself).
  async function queueNext(plan, outcome, srn, counts, note) {
    const adv = await server(plan.advancePath || '/queue/advance', { outcome, srn, counts, note });
    let a = null;
    try { a = JSON.parse(adv.text); } catch (e) { /* below */ }
    if (!a || a.error) { status('Could not move the queue on: ' + esc((a && a.error) || adv.error || ''), [['Close', close]]); return; }
    if (!a.next) { status(`<b>${esc(plan.client)}</b>: ${esc(outcome)}${srn ? ' (SRN ' + esc(srn) + ')' : ''}.<br>The queue is finished or paused. Review the SRNs in the app before payment.`, [['Close', close]]); return; }
    status(`<b>${esc(plan.client)}</b>: ${esc(outcome)}${srn ? ' (SRN ' + esc(srn) + ')' : ''}.<br>Next: <b>${esc(a.name)}</b> (${a.left} more waiting)… <small>(Alt+Shift+X stops)</small>`);
    setTimeout(() => {
      if (stopLoop) { status('Stopped before the next client.', [['Close', close]]); return; }
      try { sessionStorage.setItem('mcafill_autorun', JSON.stringify({ t: Date.now(), name: a.name, left: a.left })); } catch (e) { /* ignore */ }
      location.href = a.nextUrl;
    }, 3000);
  }

  // ---------- side panel: label + value list for staff who fill by hand ----------
  let side = null, sidePlan = null, sideAll = false;
  async function toggleSide() {
    if (side && document.body.contains(side)) { side.remove(); side = null; return; }
    const r = await server('/plan?slug=' + encodeURIComponent(slug()));
    if (!r.ok) {
      let msg = r.error || r.text; try { msg = JSON.parse(r.text).error || msg; } catch (e) { /* text */ }
      status('Side panel: could not get the values (' + esc(msg) + ')', [['Close', close]]);
      return;
    }
    sidePlan = JSON.parse(r.text);
    side = document.createElement('div');
    side.style.cssText = 'position:fixed;top:0;right:0;width:370px;height:100vh;z-index:2147483646;background:#f8fafc;color:#102a43;' +
      'font:13px/1.35 Segoe UI,Arial,sans-serif;box-shadow:-4px 0 16px rgba(0,0,0,.25);display:flex;flex-direction:column';
    document.body.appendChild(side);
    await renderSide();
  }

  const shownText = f => f.type === 'checkbox' && typeof f.value === 'boolean' ? (f.value ? 'Tick' : 'Untick')
    : Array.isArray(f.value) ? f.value.join(', ') : String(f.display ?? f.value ?? '');

  async function renderSide() {
    const p = sidePlan;
    const items = p.fields.map(f => ({ f, label: f.label, section: f.sectionText || '' }));
    for (const t of p.tables || []) t.rows.forEach((row, i) => row.forEach(c => items.push({ f: c, label: `${t.title} row ${i + 1}: ${c.label}`, section: 'Tables', table: true })));
    const on = await page('onPage', { keys: items.map(x => x.f.key) });
    const list = items.filter((x, i) => sideAll || x.table || (on && on[i]));
    side.innerHTML = '';
    const head = document.createElement('div');
    head.style.cssText = 'padding:10px 12px;background:#102a43;color:#fff';
    head.innerHTML = `<div style="font-weight:600">MCA values: ${esc(p.client)} · ${esc((p.slug || '').toUpperCase())}</div>` +
      `<div style="font-size:12px;opacity:.85;margin-top:3px">Drag a value onto the MCA box (empty it first), or press Fill. ${list.length} of ${items.length} shown.</div>`;
    const bar = document.createElement('div');
    bar.style.cssText = 'margin-top:6px;display:flex;gap:6px';
    for (const [lab, fn] of [[sideAll ? 'This page only' : 'Show all pages', () => { sideAll = !sideAll; renderSide(); }],
                             ['Refresh', () => renderSide()], ['Close', () => { side.remove(); side = null; }]]) {
      const b = document.createElement('button');
      b.textContent = lab;
      b.style.cssText = 'padding:3px 8px;border:0;border-radius:4px;background:#486581;color:#fff;cursor:pointer;font:inherit;font-size:12px';
      b.addEventListener('click', ev => { ev.preventDefault(); fn(); });
      bar.appendChild(b);
    }
    head.appendChild(bar);
    side.appendChild(head);
    const body = document.createElement('div');
    body.style.cssText = 'overflow:auto;flex:1;padding:6px 10px 20px';
    let last = null;
    for (const x of list) {
      if (x.section !== last) {
        last = x.section;
        const h = document.createElement('div');
        h.textContent = last || 'General';
        h.style.cssText = 'margin:10px 0 4px;font-weight:600;color:#334e68;border-bottom:1px solid #d9e2ec';
        body.appendChild(h);
      }
      const row = document.createElement('div');
      row.style.cssText = 'margin:4px 0;padding:5px 6px;background:#fff;border:1px solid #e4e7eb;border-radius:4px';
      const lab = document.createElement('div');
      lab.textContent = x.label;
      lab.style.cssText = 'font-size:11.5px;color:#486581';
      const line = document.createElement('div');
      line.style.cssText = 'display:flex;align-items:center;gap:6px;margin-top:3px';
      const chip = document.createElement('span');
      const text = shownText(x.f);
      chip.textContent = text;
      chip.draggable = true;
      chip.title = 'Drag onto the MCA box';
      chip.style.cssText = 'flex:1;padding:2px 6px;background:#e3f8ff;border:1px dashed #2bb0ed;border-radius:3px;cursor:grab;word-break:break-word';
      chip.addEventListener('dragstart', ev => { ev.dataTransfer.setData('text/plain', text); ev.dataTransfer.effectAllowed = 'copy'; });
      const copy = document.createElement('button');
      copy.textContent = 'Copy';
      const fill = document.createElement('button');
      fill.textContent = 'Fill';
      for (const b of [copy, fill]) b.style.cssText = 'padding:2px 6px;border:0;border-radius:3px;background:#d9e2ec;cursor:pointer;font:inherit;font-size:11.5px';
      copy.addEventListener('click', async ev => { ev.preventDefault(); try { await navigator.clipboard.writeText(text); copy.textContent = 'Copied'; } catch (e) { copy.textContent = 'Use drag'; } });
      if (x.table) fill.disabled = true, fill.title = 'Table rows: use Alt+Shift+F or drag';
      fill.addEventListener('click', async ev => {
        ev.preventDefault();
        fill.textContent = '…';
        const r = await page('fillOne', { field: x.f });
        fill.textContent = r && r.status === 'filled' ? 'Done' : (r && r.status) || 'failed';
        fill.title = (r && r.msg) || '';
      });
      line.append(chip, copy, fill);
      row.append(lab, line);
      body.appendChild(row);
    }
    side.appendChild(body);
  }

  // One entry point for the keys and the side panel buttons.
  //   dump = Save form (Alt+Shift+D), fill = Form Filler (Alt+Shift+F), values = Alt+Shift+S, stop = Alt+Shift+X
  function command(cmd) {
    if (cmd === 'stop') {
      stopLoop = true;
      if (busy) { page('abort'); status('Stopping after the current field…'); }
      return 'ok';
    }
    if (busy) return 'busy';
    if (cmd === 'dump') doDump();
    else if (cmd === 'fill') doFill();
    else if (cmd === 'values') toggleSide();
    else return 'unknown';
    return 'ok';
  }

  document.addEventListener('keydown', e => {
    if (!hasForm()) {
      // Say so (top frame only) instead of doing nothing, so staff know the key reached us.
      if (e.altKey && e.shiftKey && (e.code === 'KeyD' || e.code === 'KeyF' || e.code === 'KeyS') && window === window.top) {
        e.preventDefault();
        status('No MCA web form found on this page yet. Open the form draft, wait until it has fully loaded, then press the key again.', [['Close', close]]);
      }
      return;
    }
    if (!(e.altKey && e.shiftKey)) return;
    const cmd = { KeyD: 'dump', KeyF: 'fill', KeyS: 'values', KeyX: 'stop' }[e.code];
    if (!cmd || (busy && cmd !== 'stop')) return;
    e.preventDefault();
    command(cmd);
  }, true);

  // Side panel buttons. Only the frame that holds the form answers, so the panel hears from exactly one.
  chrome.runtime.onMessage.addListener((msg, sender, reply) => {
    if (msg && msg.type === 'mcafill-cmd' && msg.cmd === 'goto' && window === window.top) {
      try { sessionStorage.setItem('mcafill_autorun', JSON.stringify({ t: Date.now() })); } catch (e) { /* ignore */ }
      reply({ ok: true });
      location.href = msg.url;
      return false;
    }
    if (!msg || msg.type !== 'mcafill-cmd' || !hasForm()) return false;
    if (msg.cmd === 'probe') reply({ ok: true, slug: slug(), busy, version: chrome.runtime.getManifest().version });
    else reply({ ok: true, slug: slug(), result: command(msg.cmd) });
    return false;
  });

  // ADT-1 run across companies: the previous company's last Save opened a fresh form here; start filling it.
  (async () => {
    let t = null;
    try { t = sessionStorage.getItem('mcafill_autorun'); } catch (e) { return; }
    let info = {};
    try { info = JSON.parse(t); } catch (e) { info = { t: Number(t) }; }
    if (!t || Date.now() - Number(info.t) > 600000) return;
    for (let w = 0; w < 90 && !hasForm(); w++) await new Promise(r => setTimeout(r, 1000));
    if (!hasForm()) return;
    try { if (!sessionStorage.getItem('mcafill_autorun')) return; sessionStorage.removeItem('mcafill_autorun'); } catch (e) { return; }
    await new Promise(r => setTimeout(r, 4000));  // let the portal finish building the form
    autorun = true;
    doFill();
  })();
})();
