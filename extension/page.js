// MCA form filler, page side. Runs in the page's own JS world (manifest
// "world": "MAIN") so it can read the AEM adaptive-form model (window.guideBridge).
// content.js talks to it with CustomEvents on document; payloads are JSON strings.
// Never clicks Submit / Pay / Upload / Affix DSC. The only button it clicks is Save.
(() => {
  if (window.__mcaFillPage) return;
  window.__mcaFillPage = true;

  const BLOCKED = /submit|pay|upload|affix|dsc|sign|proceed|certif|scrutiny|validate|check ?form|attach|file/i;

  // autoSave runs (ADT-1): acknowledge the portal's own notices so the run doesn't wait on staff.
  // Only plain notices: browser alerts while a run is on, and in-page "Informational message" /
  // "uploaded / saved successfully" boxes with a single OK. confirm() and anything else are left alone.
  let autoNotices = false;
  const nativeAlert = window.alert.bind(window);
  window.alert = msg => { if (autoNotices) { console.log('[MCA filler] alert acknowledged:', msg); return; } return nativeAlert(msg); };
  setInterval(() => {
    if (!autoNotices) return;
    for (const d of document.querySelectorAll('[role="dialog"], .modal, [class*="modal"], [class*="Modal"], [class*="popup"], [class*="Popup"]')) {
      if (!d.offsetParent && getComputedStyle(d).position !== 'fixed') continue;
      const t = (d.innerText || '').replace(/\s+/g, ' ');
      if (!/informational message|uploaded successfully|saved successfully|successfully saved|successfully uploaded/i.test(t)) continue;
      const btns = [...d.querySelectorAll('button, [type="button"], a')].filter(b => b.offsetParent && /^(ok|okay|close)$/i.test((b.innerText || b.value || '').trim()));
      if (btns.length === 1) btns[0].click();
    }
  }, 700);
  const GENERIC = /^(text ?box|text ?area|numeric ?box|date ?picker|drop ?down( ?list)?|radio ?button|check ?box|switch|field|untitled)\s*\d*$/i;
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const jitter = (a, b) => sleep(a + Math.random() * (b - a));
  const strip = s => String(s ?? '').replace(/<[^>]*>/g, ' ').replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&')
    .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/\s+/g, ' ').trim();
  const gb = () => (window.guideBridge && typeof window.guideBridge.visit === 'function') ? window.guideBridge : null;
  const safe = (fn, dflt = null) => { try { return fn(); } catch (e) { return dflt; } };
  const keyOf = base => base.replace(/^guideContainer-/, '').replace(/_+$/, '');
  // DOM widget ids: "<base>_widget" for text/select, "<base>-<n>_widget" for each radio/checkbox option.
  // Checkbox options can also be "<base>_<n>_widget".
  const baseOfWidget = id => id.replace(/([-_]\d+)?_widget$/, '');
  let abort = false;
  let fieldMap = {};

  function typeOf(cls) {
    const c = String(cls || '').toLowerCase();
    if (c.includes('date')) return 'date';
    if (c.includes('numeric')) return 'number';
    if (c.includes('dropdown')) return 'dropdown';
    if (c.includes('radio')) return 'radio';
    if (c.includes('checkbox') || c.includes('switch')) return 'checkbox';
    if (c.includes('fileupload') || c.includes('file')) return 'file';
    if (c.includes('button')) return 'button';
    if (c.includes('textbox') || c.includes('textfield') || c.includes('telephone') || c.includes('email')
      || c.includes('password') || c.includes('textarea')) return 'text';
    return null;
  }

  function domType(el) {
    if (el.tagName === 'SELECT') return 'dropdown';
    if (el.type === 'radio') return 'radio';
    if (el.type === 'checkbox') return 'checkbox';
    if (el.type === 'file') return 'file';
    if (el.tagName === 'BUTTON' || el.type === 'button' || el.type === 'submit') return 'button';
    if (/datepicker/i.test(el.id)) return 'date';
    if (/numeric/i.test(el.id) || el.type === 'number') return 'number';
    return 'text';
  }

  // All widget elements for a field base id (several for radio/checkbox groups).
  function widgets(base) {
    if (!base) return [];
    const one = document.getElementById(base + '_widget');
    if (one) return [one];
    return [...document.querySelectorAll(`[id^="${base}"][id$="_widget"]`)]
      .filter(e => baseOfWidget(e.id) === base);
  }

  function isShown(el) {
    if (!el) return false;
    if (el.offsetWidth || el.offsetHeight || el.getClientRects().length) return true;
    // Styled tick boxes / radios hide the real input: judge by its label or wrapper instead.
    if (el.type === 'checkbox' || el.type === 'radio' || el.type === 'file') {
      const l = (el.id && document.querySelector(`label[for="${el.id}"]`)) || el.parentElement;
      return !!(l && (l.offsetWidth || l.offsetHeight));
    }
    return false;
  }

  function tableLabel(el) {
    const td = el.closest('td,th');
    const tr = td && td.closest('tr');
    const table = tr && tr.closest('table');
    if (!table) return '';
    const idx = td.cellIndex;
    let col = '';
    const head = table.querySelector('thead tr') || table.rows[0];
    if (head && head !== tr && head.cells[idx]) col = strip(head.cells[idx].innerText);
    // Row label: text of the cells to the left of this one (MCA tables put "(a) Share capital" there,
    // sometimes inside nested elements), else the first cell without an input.
    let row = '';
    for (const c of tr.cells) {
      if (c === td) break;
      if (c.querySelector('input,select,textarea')) continue;
      const t = strip(c.innerText);
      if (t) row = row ? row + ' ' + t : t;
    }
    if (!row) {
      const first = tr.cells[0];
      if (first && first !== td && !first.querySelector('input,select,textarea')) row = strip(first.innerText);
    }
    return [row.slice(0, 120), col].filter(Boolean).join(' / ');
  }

  function domLabel(el) {
    if (!el) return '';
    let lab = '';
    const node = el.closest('[class*="guideFieldNode"]');
    if (node) {
      const l = node.querySelector('[class*="guideFieldLabel"], label');
      if (l) lab = strip(l.innerText || l.textContent);
    }
    if (!lab && el.id) {
      const l = document.querySelector(`label[for="${el.id}"]`);
      if (l) lab = strip(l.innerText);
    }
    if (!lab) lab = strip(el.getAttribute('aria-label') || el.title || '');
    if (!lab || GENERIC.test(lab)) lab = tableLabel(el) || lab;
    return lab;
  }

  function optionLabel(input) {
    const l = input.id && document.querySelector(`label[for="${input.id}"]`);
    return strip(l ? l.innerText : (input.parentElement && input.parentElement.innerText) || input.value);
  }

  function parseOptions(raw, els) {
    const out = [];
    if (Array.isArray(raw)) {
      for (const o of raw) {
        if (typeof o === 'string') {
          const k = o.indexOf('=');
          out.push(k >= 0 ? { value: o.slice(0, k), text: strip(o.slice(k + 1)) } : { value: o, text: strip(o) });
        } else if (o && typeof o === 'object') {
          out.push({ value: String(o.value ?? o.key ?? ''), text: strip(o.text ?? o.label ?? o.displayValue ?? o.value) });
        }
      }
    }
    if (!out.length && els.length) {
      if (els[0].tagName === 'SELECT') {
        for (const o of els[0].options) out.push({ value: o.value, text: strip(o.text) });
      } else if (els[0].type === 'radio' || els[0].type === 'checkbox') {
        for (const e of els) out.push({ value: e.value, text: optionLabel(e) });
      }
    }
    return out.filter(o => o.value !== '' || (o.text && !/^-*\s*select/i.test(o.text)))
      .filter(o => o.value !== '');
  }

  function repeatInfo(p) {
    const im = safe(() => p.instanceManager);
    const max = safe(() => im && im.maxOccur, undefined) ?? safe(() => p.jsonModel.maxOccur, undefined);
    if (!im && max === undefined) return null;
    if (!(max === -1 || max > 1 || max === '-1')) return null;
    return {
      min: safe(() => im.minOccur, null) ?? safe(() => p.jsonModel.minOccur, null),
      max: Number(max),
      count: safe(() => im.instanceCount, null),
    };
  }

  // ---------- dump ----------

  function modelDump() {
    const g = gb();
    const fields = [], buttons = [];
    let order = 0;
    g.visit(cmp => {
      const cls = safe(() => cmp.className, '');
      const t = typeOf(cls);
      if (!t) return;
      const base = safe(() => cmp.id, '') || '';
      const els = widgets(base);
      // Walk up: section titles, first repeatable ancestor, skip non-first instances.
      const sections = [];
      let rep = null, repCmp = null, extraInstance = false;
      let p = safe(() => cmp.parent);
      for (let n = 0; p && n < 60; n++, p = safe(() => p.parent)) {
        const pname = safe(() => p.name, '') || '';
        const idx = safe(() => p.instanceIndex, 0);
        const ri = repeatInfo(p);
        if (ri) {
          if (idx > 0) extraInstance = true;
          if (!repCmp) { repCmp = p; rep = ri; }
        }
        const title = strip(safe(() => p.title) || safe(() => p.jsonModel['jcr:title']));
        const pcls = String(safe(() => p.className, '') || '');
        if (title && !/rootpanel/i.test(pname) && !/tablerow/i.test(pcls) && !GENERIC.test(title)) sections.unshift(title);
      }
      if (extraInstance || safe(() => cmp.instanceIndex, 0) > 0 && repCmp === null) return;
      if (t === 'button') {
        const el = els[0];
        buttons.push({ key: keyOf(base), name: safe(() => cmp.name, ''), text: strip(el ? (el.innerText || el.value) : safe(() => cmp.title, '')) });
        return;
      }
      let label = strip(safe(() => cmp.title) || safe(() => cmp.jsonModel['jcr:title']));
      if (!label || GENERIC.test(label)) label = domLabel(els[0]) || label;
      else if (els[0] && els[0].closest('td')) {
        // Table cell titled with its column ("Figures as at the end of…"): put the row caption in front.
        const tl = tableLabel(els[0]);
        const rowPart = tl.includes(' / ') ? tl.split(' / ')[0] : '';
        if (rowPart && !label.toLowerCase().includes(rowPart.toLowerCase())) label = rowPart + ' / ' + label;
      }
      const mandatory = !!safe(() => cmp.mandatory) || /\*/.test(label);
      const field = {
        order: order++,
        key: keyOf(base),
        domBase: base,
        som: safe(() => cmp.somExpression, ''),
        name: safe(() => cmp.name, ''),
        cls,
        type: t,
        label: label.replace(/\*/g, '').replace(/\s+/g, ' ').trim(),
        section: sections,
        mandatory,
        readOnly: !!safe(() => cmp.readOnly) || els.some(e => e.readOnly),
        disabled: safe(() => cmp.enabled) === false || els.some(e => e.disabled),
        visible: safe(() => cmp.visible) !== false,
        rendered: els.some(isShown),
        hasDom: els.length > 0,
        options: (t === 'dropdown' || t === 'radio' || t === 'checkbox')
          ? parseOptions(safe(() => cmp.options) || safe(() => cmp.jsonModel.options), els) : [],
        repeat: null,
        page: sections[0] || '',
      };
      if (repCmp) {
        const gsom = safe(() => repCmp.somExpression, '');
        field.repeat = {
          groupKey: keyOf(safe(() => repCmp.id, '') || ''),
          groupSom: gsom,
          relSom: field.som.startsWith(gsom) ? field.som.slice(gsom.length) : '',
          title: strip(safe(() => repCmp.title)) || field.section[field.section.length - 1] || 'Table',
          ...rep,
        };
      }
      fields.push(field);
    });
    return { source: 'model', fields, buttons };
  }

  function domSections(el) {
    const out = [];
    for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
      if (!p.id || !p.id.startsWith('guideContainer') || !/panel/i.test(p.className)) continue;
      const h = p.querySelector(':scope > [class*="Title"], :scope > [class*="title"], :scope > legend, :scope > h1, :scope > h2, :scope > h3, :scope > h4, :scope > div > h2, :scope > div > h3, :scope > div > [class*="Title"]');
      const t = h && strip(h.innerText);
      if (t && t.length < 200 && out[0] !== t) out.unshift(t);
    }
    return out;
  }

  function domDump() {
    const fields = [], buttons = [], seen = new Set();
    let order = 0;
    for (const el of document.querySelectorAll('[id^="guideContainer-rootPanel"][id$="_widget"], [id^="guideContainer-rootPanel"] button')) {
      const base = el.id ? baseOfWidget(el.id) : '';
      if (base && seen.has(base)) continue;
      if (base) seen.add(base);
      const t = domType(el);
      if (t === 'button') { buttons.push({ key: keyOf(base), text: strip(el.innerText || el.value) }); continue; }
      const els = base ? widgets(base) : [el];
      const label = domLabel(el);
      fields.push({
        order: order++, key: keyOf(base), domBase: base, som: '', name: '', cls: el.className || '', type: t,
        label: label.replace(/\*/g, '').trim(), section: domSections(el), mandatory: /\*/.test(label),
        readOnly: els.some(e => e.readOnly), disabled: els.some(e => e.disabled), visible: true,
        rendered: els.some(isShown), hasDom: true, options: parseOptions(null, els),
        repeat: /-table-Row|_instance|\[\d+\]/i.test(base) ? { groupKey: '', groupSom: '', relSom: '', title: 'Table (DOM)', manual: true } : null,
      });
    }
    return { source: 'dom', fields, buttons };
  }

  function dump() {
    let res = null, modelError = null;
    if (gb()) {
      try { res = modelDump(); } catch (e) { modelError = String(e && e.message || e); }
    }
    if (!res || !res.fields.length) res = domDump();
    const formTitle = strip(document.querySelector('h1')?.innerText || document.title);
    const m = location.pathname.match(/form-([a-z0-9_-]+)\.html/i);
    return {
      slug: (m ? m[1] : location.pathname.split('/').pop().replace(/\.html$/, '')).toLowerCase(),
      url: location.origin + location.pathname,
      title: formTitle,
      capturedAt: new Date().toISOString(),
      guideBridge: !!gb(),
      modelError,
      domWidgetCount: document.querySelectorAll('[id^="guideContainer-rootPanel"][id$="_widget"]').length,
      ...res,
      pagesOnScreen: [...new Set(res.fields.filter(f => f.rendered).map(f => f.page || (f.section || [])[0] || ''))].filter(Boolean),
    };
  }

  // ---------- fill ----------

  function setNative(el, value) {
    el.focus();
    const proto = el.tagName === 'SELECT' ? HTMLSelectElement.prototype
      : el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, value);
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
    el.dispatchEvent(new Event('blur', { bubbles: false }));
    el.dispatchEvent(new FocusEvent('focusout', { bubbles: true }));
    el.blur();
  }

  const norm = v => String(v ?? '').trim();
  function listOf(v) {
    if (Array.isArray(v)) return v.map(norm).filter(Boolean).sort();
    return norm(v).split(',').map(norm).filter(Boolean).sort();
  }

  // Does the model / widget already hold the wanted value?
  function matches(f, current) {
    if (current === null || current === undefined) return false;
    switch (f.type) {
      case 'number': return norm(current) !== '' && Number(current) === Number(f.value);
      case 'date': return norm(current) === f.iso || norm(current) === f.value;
      case 'checkbox': return listOf(current).join(',') === listOf(f.value).join(',');
      default: {
        if (norm(current) === norm(f.value)) return true;
        // Amounts in text boxes: "10,068,624" vs "10068624.41" is the same figure to MCA.
        const a = Number(norm(current).replace(/,/g, '')), b = Number(norm(f.value).replace(/,/g, ''));
        return norm(current) !== '' && norm(f.value) !== '' && !isNaN(a) && !isNaN(b) && Math.abs(a - b) < 1;
      }
    }
  }

  // MCA radios often have no value attribute, so every option reads "on".
  // Pick the option by its value only when values are distinct; otherwise by its label text.
  function radioTarget(f, els) {
    const vals = els.map(e => e.value);
    const distinct = new Set(vals).size === vals.length;
    if (distinct) {
      const byVal = els.find(e => e.value === f.value);
      if (byVal && !(f.value === 'on' && f.display)) return byVal;
    }
    const want = norm(f.display ?? f.value).toLowerCase();
    return els.find(e => norm(optionLabel(e)).toLowerCase() === want) ||
           (distinct ? els.find(e => e.value === f.value) : null) || null;
  }

  function domValue(f, els) {
    if (!els.length) return null;
    if (f.type === 'radio') { const c = els.find(e => e.checked); return c ? c.value : ''; }
    if (f.type === 'checkbox') return els.filter(e => e.checked).map(e => e.value);
    return els[0].value;
  }

  async function domSet(f, els) {
    if (f.type === 'radio') {
      const target = radioTarget(f, els);
      if (!target) return 'no radio option "' + (f.display ?? f.value) + '"';
      if (!target.checked) target.click();
      return null;
    }
    if (f.type === 'checkbox' && typeof f.value === 'boolean') {
      if (els[0].checked !== f.value) els[0].click();
      return null;
    }
    if (f.type === 'checkbox') {
      const want = listOf(f.value);
      for (const e of els) {
        if (e.checked !== want.includes(e.value)) { e.click(); await jitter(80, 200); }
      }
      return null;
    }
    const el = els[0];
    if (el.tagName === 'SELECT' && ![...el.options].some(o => o.value === f.value)) {
      // Options that load on the page: match by the visible text instead.
      const want = norm(f.display ?? f.value).toLowerCase();
      const o = [...el.options].find(o => norm(o.text).toLowerCase() === want) ||
                [...el.options].find(o => want.length >= 8 && norm(o.text).toLowerCase().startsWith(want));
      if (!o) return 'dropdown has no option ' + (f.display ?? f.value);
      f = { ...f, value: o.value };
      setNative(el, o.value);
      return null;
    }
    setNative(el, f.value);
    return null;
  }

  function modelSet(g, cmp, f) {
    const v = f.type === 'date' ? f.iso : f.type === 'checkbox' ? listOf(f.value).join(',') : f.value;
    const som = safe(() => cmp.somExpression);
    try { g.setProperty([som], 'value', [v]); } catch (e) { cmp.value = v; }
  }

  // A field that already holds an answer is never re-typed: re-runs after Save stay harmless, and
  // MCA's pre-filled or staff-corrected values are kept.
  function hasValue(f, els, cmp) {
    if (!els.length) return norm(cmp ? safe(() => cmp.value) : '') !== '';
    if (f.type === 'radio') return els.some(e => e.checked);
    if (f.type === 'checkbox') return els.some(e => e.checked);
    const el = els[0];
    if (el.tagName === 'SELECT') {
      const o = el.selectedIndex >= 0 ? el.options[el.selectedIndex] : null;
      return !!o && norm(o.value) !== '' && !/^\s*(-+\s*)?select\b|^\s*-+\s*$/i.test(o.text || '');
    }
    return norm(el.value) !== '';
  }

  async function fillOne(g, f, cmp) {
    if (f.copyFrom) {
      // Same value as another (usually read-only) portal field, e.g. "as on filing date".
      const src = fieldMap[f.copyFrom];
      const sv = src ? safe(() => src.value) : null;
      const srcEls = widgets('guideContainer-' + f.copyFrom + '__');
      const val = norm(sv ?? (srcEls[0] && srcEls[0].value));
      if (!val) return { code: f.code, key: f.key, label: f.label, section: f.sectionText || '', status: 'manual', msg: 'nothing to copy from the filing-date column' };
      f = { ...f, value: val, copyFrom: null };
    }
    const entry = { code: f.code, key: f.key, label: f.label, section: f.sectionText || '', value: f.display ?? f.value, status: '', method: '', msg: '' };
    const base = (cmp && safe(() => cmp.id)) || f.domBase;
    const els = widgets(base);
    if (!cmp && !els.length) return { ...entry, status: 'other-page', msg: 'not on this page' };
    // Multi-page forms: only touch fields whose widget is on screen on the current page.
    if (!f.allowOffscreen && !els.some(isShown)) return { ...entry, status: 'other-page', msg: 'not on this page' };
    if (cmp && safe(() => cmp.visible) === false) {
      await sleep(500);
      if (safe(() => cmp.visible) === false) return { ...entry, status: 'hidden', msg: 'field is hidden by an earlier answer; not filled' };
    }
    if ((cmp && (safe(() => cmp.readOnly) || safe(() => cmp.enabled) === false)) || els.some(e => e.readOnly || e.disabled)) {
      return { ...entry, status: 'skipped-readonly' };
    }
    if (f.type === 'checkbox' && typeof f.value === 'boolean') {
      if (!els.length) return { ...entry, status: 'manual', msg: 'tick box not on screen' };
      if (els[0].checked === f.value) return { ...entry, status: 'unchanged' };
      await domSet(f, els);
      await sleep(150);
      return { ...entry, method: 'dom', status: els[0].checked === f.value ? 'filled' : 'failed' };
    }
    if (f.prev) {
      // Previous-year figures: MCA pre-fills them from last year's filing. Never change a pre-filled one.
      const pv = cmp ? safe(() => cmp.value) : domValue(f, els);
      const dv = els.length ? domValue(f, els) : null;
      if (norm(pv) !== '' || (typeof dv === 'string' && norm(dv) !== '')) {
        return { ...entry, status: 'unchanged', msg: 'kept MCA pre-filled previous-year figure' };
      }
    }
    if (f.type !== 'checkbox' && hasValue(f, els, cmp)) {
      return { ...entry, status: 'unchanged', msg: matches(f, cmp ? safe(() => cmp.value) : domValue(f, els)) ? '' : 'already has a value: kept' };
    }
    if (f.type === 'dropdown' && els.length && els[0].tagName === 'SELECT' && f.display) {
      // Choose by the visible option text, like a person would; the portal's own change handler
      // then stores whatever code it uses for that option.
      const sel = els[0];
      const want = norm(f.display).toLowerCase();
      const cur = sel.selectedIndex >= 0 ? norm(sel.options[sel.selectedIndex].text).toLowerCase() : '';
      if (cur === want) return { ...entry, status: 'unchanged' };
      const o = [...sel.options].find(o => norm(o.text).toLowerCase() === want) ||
                [...sel.options].find(o => want.length >= 8 && norm(o.text).toLowerCase().startsWith(want));
      if (!o) return { ...entry, status: 'failed', msg: 'dropdown has no option ' + f.display };
      if (isShown(sel)) safe(() => sel.scrollIntoView({ block: 'center', behavior: 'smooth' }));
      setNative(sel, o.value);
      await sleep(200);
      const now = sel.selectedIndex >= 0 ? norm(sel.options[sel.selectedIndex].text).toLowerCase() : '';
      return now === norm(o.text).toLowerCase() ? { ...entry, method: 'dom-text', status: 'filled' }
                                                : { ...entry, method: 'dom-text', status: 'failed', msg: 'dropdown did not keep ' + f.display };
    }
    if (f.type === 'radio' && els.length) {
      // Radios are judged and set on screen only. Re-setting a gate question (even to the same
      // answer) makes MCA clear every field that depends on it, so an already-ticked option is left alone.
      const target = radioTarget(f, els);
      if (!target) return { ...entry, status: 'failed', msg: 'no radio option "' + (f.display ?? f.value) + '"' };
      if (target.checked) return { ...entry, status: 'unchanged' };
      if (isShown(target)) safe(() => target.scrollIntoView({ block: 'center', behavior: 'smooth' }));
      target.click();
      await sleep(200);
      return target.checked ? { ...entry, method: 'dom', status: 'filled' }
                            : { ...entry, method: 'dom', status: 'failed', msg: 'radio did not stay ticked' };
    }
    const cur = cmp ? safe(() => cmp.value) : domValue(f, els);
    if (matches(f, cur)) return { ...entry, status: 'unchanged' };

    let err = null;
    if (els.length) {
      if (isShown(els[0])) safe(() => els[0].scrollIntoView({ block: 'center', behavior: 'smooth' }));
      err = await domSet(f, els);
      entry.method = 'dom';
      await sleep(120);
    }
    if (cmp && g) {
      if (!matches(f, safe(() => cmp.value))) {
        modelSet(g, cmp, f);
        entry.method = entry.method ? 'dom+model' : 'model';
        await sleep(80);
      }
      if (matches(f, safe(() => cmp.value))) return { ...entry, status: 'filled' };
      return { ...entry, status: 'failed', msg: err || ('portal holds "' + norm(safe(() => cmp.value)) + '" after fill') };
    }
    if (err) return { ...entry, status: 'failed', msg: err };
    return matches(f, domValue(f, els)) ? { ...entry, status: 'filled' } : { ...entry, status: 'failed', msg: 'value did not stick' };
  }

  // Fill one field; if the portal rejects the new value, put back what was there before.
  async function fillOneSafe(g, f, cmp) {
    const base = (cmp && safe(() => cmp.id)) || f.domBase;
    const els0 = widgets(base);
    const before = cmp ? safe(() => cmp.value) : domValue(f, els0);
    const r = await fillOne(g, f, cmp);
    r.el = els0[0] || null;
    if (r.status === 'failed' && before !== null && before !== undefined && norm(before) !== '' && typeof before !== 'object') {
      try {
        if (els0.length && f.type !== 'radio' && f.type !== 'checkbox') setNative(els0[0], String(before));
        if (cmp && g && norm(safe(() => cmp.value)) !== norm(before)) g.setProperty([safe(() => cmp.somExpression)], 'value', [before]);
        r.msg = (r.msg ? r.msg + '; ' : '') + 'previous value put back';
      } catch (e) { /* leave as is */ }
    }
    return r;
  }

  // Section "Save" buttons: many MCA panels stay locked until the Save just above them is pressed.
  function sectionSaves() {
    return [...document.querySelectorAll('[id^="guideContainer"] button, [id^="guideContainer"] [type="button"]')]
      .filter(b => isShown(b) && !b.disabled && /^save$/i.test(strip(b.innerText || b.value || '')));
  }
  const before = (a, b) => !!(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);

  async function dismissSaved() {
    await sleep(400);
    for (const dlg of document.querySelectorAll('[role="dialog"], .modal, [class*="modal"], [class*="Modal"]')) {
      if (!isShown(dlg) || !/saved|success/i.test(dlg.innerText || '')) continue;
      const ok = [...dlg.querySelectorAll('button, [type="button"], a')].find(b => isShown(b) && /^(ok|close|okay)$/i.test(strip(b.innerText || b.value || '')));
      if (ok) { ok.click(); await sleep(300); }
    }
  }

  function findSave() {
    // MCA has a Save per section plus a page Save at the bottom: the page Save is the last visible one.
    const main = [...document.querySelectorAll('[id*="saveguidedraft"][id$="_widget"]')]
      .filter(b => isShown(b) && !b.disabled && /^save$/i.test(strip(b.innerText || b.value || ''))).pop();
    if (main) return main;
    const cands = [...document.querySelectorAll('[id^="guideContainer"] button, button')];
    for (const b of cands) {
      const text = strip(b.innerText || b.value || '');
      if (!/^save( (as )?draft)?$/i.test(text)) continue;
      if (BLOCKED.test(text)) continue;
      if (!isShown(b) || b.disabled) continue;
      return b;
    }
    return null;
  }

  // Filing queue: on the last page the tool outlines Submit and waits. Staff click it themselves;
  // the tool only reads the SRN the portal shows afterwards, then the queue moves to the next client.
  const shownDialogs = () => [...document.querySelectorAll('[role="dialog"], .modal, [class*="modal"], [class*="Modal"], [class*="popup"], [class*="Popup"]')].filter(isShown);
  function readSrn() {
    const texts = shownDialogs().map(d => d.innerText || '').concat([document.body.innerText || '']);
    for (const t of texts) {
      const m = t.match(/\bSRN\b[^A-Z0-9]{0,60}([A-Z]{1,2}\d{7,10})\b/i) || t.match(/service request number[^A-Z0-9]{0,60}([A-Z]{1,2}\d{7,10})\b/i);
      if (m) return m[1].toUpperCase();
    }
    return '';
  }
  async function awaitSubmit(maxMs) {
    const before = readSrn();
    const sub = [...document.querySelectorAll('button, [type="button"], [type="submit"]')]
      .find(b => isShown(b) && !b.disabled && /^submit$/i.test(strip(b.innerText || b.value || '')));
    if (!sub) return { srn: '', msg: 'no Submit button on this page' };
    safe(() => sub.scrollIntoView({ block: 'center', behavior: 'smooth' }));
    sub.style.outline = '4px solid #ff4d4f';
    sub.style.outlineOffset = '3px';
    sub.style.boxShadow = '0 0 0 8px rgba(255,77,79,.35)';
    abort = false;
    for (let t = 0; t < maxMs && !abort; t += 1000) {
      await sleep(1000);
      const s = readSrn();
      if (s && s !== before) { sub.style.outline = ''; sub.style.boxShadow = ''; return { srn: s, msg: 'Submitted. SRN ' + s }; }
    }
    return { srn: '', msg: abort ? 'stopped' : 'no SRN seen yet' };
  }

  function progress(detail) {
    document.dispatchEvent(new CustomEvent('mcafill:progress', { detail: JSON.stringify(detail) }));
  }

  async function fill(plan) {
    abort = false;
    autoNotices = !!plan.autoSave;
    const g = gb();
    const log = [];
    const map = fieldMap = {};
    if (g) safe(() => g.visit(c => { const id = safe(() => c.id); if (id) map[keyOf(id)] = c; }));
    const total = plan.fields.length + (plan.tables || []).reduce((n, t) => n + t.rows.reduce((m, r) => m + r.length, 0), 0);
    let done = 0, lastSection = null;

    for (const e of plan.errors || []) log.push({ ...e, status: 'failed', method: 'excel' });

    // One section at a time: find the first field that still needs a value, and the first Save
    // below it. Fields under that Save wait until staff click it and press Alt+Shift+F again.
    const cmpOf = f => map[f.key] || (g && f.som ? safe(() => g.resolveNode(f.som)) : null);
    const elOf = f => { const c = cmpOf(f); return widgets((c && safe(() => c.id)) || f.domBase).find(isShown) || null; };
    const needsWork = f => {
      const c = cmpOf(f), els = widgets((c && safe(() => c.id)) || f.domBase);
      if (!els.some(isShown) || els.some(e => e.readOnly || e.disabled) || (c && safe(() => c.readOnly))) return false;
      if (f.type === 'checkbox' && typeof f.value === 'boolean') return els[0].checked !== f.value;
      return !hasValue(f, els, c);
    };
    let stopAt = null;
    const firstWork = plan.fields.find(needsWork);
    const firstEl = firstWork && elOf(firstWork);
    if (firstEl) stopAt = sectionSaves().find(b => before(firstEl, b)) || null;
    else {
      // Nothing editable needs work: the next step is the Save above the first locked field that is still wrong.
      const lockedWrong = plan.fields.find(f => {
        const c = cmpOf(f), els = widgets((c && safe(() => c.id)) || f.domBase);
        return els.some(isShown) && (els.some(e => e.readOnly || e.disabled) || (c && safe(() => c.readOnly))) &&
          !matches(f, c ? safe(() => c.value) : domValue(f, els));
      });
      const le = lockedWrong && elOf(lockedWrong);
      if (le) stopAt = sectionSaves().filter(b => before(b, le)).pop() || null;
    }
    const beyond = el => !!(stopAt && el && before(stopAt, el));
    let passedStop = false;
    // Tables are filled in form order: right after the last field of their own section.
    const tablesLeft = [...(plan.tables || [])];
    const lastOfSection = {};
    plan.fields.forEach((f, i) => { lastOfSection[f.sectionText || ''] = i; });
    const runSectionTables = async f => {
      if (lastOfSection[f.sectionText || ''] !== plan.fields.indexOf(f)) return;
      for (const t of tablesLeft.filter(t => (t.section || '') === (f.sectionText || ''))) {
        tablesLeft.splice(tablesLeft.indexOf(t), 1);
        await doTableFn(t);
      }
    };

    for (const f of plan.fields) {
      if (abort) { log.push({ code: f.code, key: f.key, label: f.label, status: 'not-run', msg: 'stopped by user' }); continue; }
      if (beyond(elOf(f))) { passedStop = true; log.push({ code: f.code, key: f.key, label: f.label, section: f.sectionText || '', status: 'next-section', msg: 'below the Save to click first' }); done++; await runSectionTables(f); continue; }
      if (f.sectionText !== lastSection) {
        if (lastSection !== null) await jitter(500, 1100);
        lastSection = f.sectionText;
      }
      // Fields not on screen or locked are logged straight away, without the typing pause.
      const quickEl = elOf(f);
      if (!quickEl && !f.copyFrom) { log.push({ code: f.code, key: f.key, label: f.label, section: f.sectionText || '', status: 'other-page', msg: 'not on this page' }); done++; await runSectionTables(f); continue; }
      progress({ done, total, label: f.label, section: f.sectionText });
      if (needsWork(f)) await jitter(150, 420);
      let cmp = map[f.key] || null;
      if (!cmp && g && f.som) cmp = safe(() => g.resolveNode(f.som));
      let r;
      try { r = await fillOneSafe(g, f, cmp); } catch (e) { r = { code: f.code, key: f.key, label: f.label, status: 'failed', msg: String(e && e.message || e) }; }
      r.retry = () => fillOneSafe(g, f, map[f.key] || (g && f.som ? safe(() => g.resolveNode(f.som)) : null));
      log.push(r);
      done++;
      await runSectionTables(f);
    }

    async function doTableFn(t) {
      // A table is held back only when it sits below the Save to click (checked on its own position
      // further down); tables whose section has no fields of its own run after the fields and must
      // not be skipped just because a later field was below the Save.
      if (passedStop && stopAt && !isShown(stopAt)) { for (const c of t.rows.flat()) log.push({ code: c.code, key: c.key, label: `${t.title} row ${c.row + 1}: ${c.label}`, status: 'next-section', msg: 'below the Save to click first' }); return; }
      const cells = t.rows.flat();
      const manual = msg => { for (const c of cells) log.push({ code: c.code, key: c.key, label: `${t.title} row ${c.row + 1}: ${c.label}`, value: c.display ?? c.value, status: 'manual', msg }); };
      if (abort) { manual('stopped by user'); return; }
      if (!g || !t.groupSom) { manual('repeatable table: fill by hand (no form model)'); return; }
      const grp = safe(() => g.resolveNode(t.groupSom));
      const gid = (grp && safe(() => grp.id, '')) || '';
      // Nearest rendered container of the table (the instance itself, else its parent panels).
      let box = null;
      for (let p = grp; p && !box; p = safe(() => p.parent)) box = document.getElementById((safe(() => p.id, '') || '') + '_guide-item');
      const shownHere = (box && isShown(box)) || widgets(gid).some(isShown) ||
        (grp && (() => { let hit = false; safe(() => g.visit(c => {
          if (hit) return;
          for (let p = safe(() => c.parent); p; p = safe(() => p.parent)) if (p === grp) { hit = widgets(safe(() => c.id, '')).some(isShown); break; }
        })); return hit; })());
      const tEl = (() => { for (const c of t.rows[0]) { const cc = c.relSom ? safe(() => g.resolveNode(t.groupSom.replace(/\[\d+\]$/, '[0]') + c.relSom)) : null; const e = cc && widgets(safe(() => cc.id, '')).find(isShown); if (e) return e; } return null; })();
      if (beyond(tEl)) { for (const c of cells) log.push({ code: c.code, key: c.key, label: `${t.title} row ${c.row + 1}: ${c.label}`, status: 'next-section', msg: 'below the Save to click first' }); return; }
      // Tables like the equity class grid only appear after an earlier answer (number of classes = 1):
      // give the portal a moment and look again before calling it "not on this page".
      let visibleNow = shownHere;
      for (let w = 0; w < 4 && !visibleNow; w++) {
        await sleep(700);
        let bx = null;
        for (let p = grp; p && !bx; p = safe(() => p.parent)) bx = document.getElementById((safe(() => p.id, '') || '') + '_guide-item');
        visibleNow = (bx && isShown(bx)) || widgets(gid).some(isShown) ||
          t.rows[0].some(c => { const cc = c.relSom ? safe(() => g.resolveNode(t.groupSom.replace(/\[\d+\]$/, '[0]') + c.relSom)) : null; return cc && widgets(safe(() => cc.id, '')).some(isShown); });
      }
      if (!visibleNow) { for (const c of cells) log.push({ code: c.code, key: c.key, label: `${t.title} row ${c.row + 1}: ${c.label}`, status: 'other-page', msg: 'table not on this page' }); return; }
      const im = grp && safe(() => grp.instanceManager);
      if (!im) { manual('repeatable table: could not find its row manager, fill by hand'); return; }
      await jitter(600, 1200);
      for (let r = 0; r < t.rows.length && !abort; r++) {
        let count = safe(() => im.instanceCount, 0);
        while (count <= r) {
          if (t.max > 0 && count >= t.max) break;
          const before = count;
          safe(() => im.addInstance());
          await jitter(500, 900);
          count = safe(() => im.instanceCount, 0);
          if (count === before) break;
        }
        if (count <= r) {
          for (const rr of t.rows.slice(r)) for (const c of rr) log.push({ code: c.code, key: c.key, label: `${t.title} row ${r + 1}: ${c.label}`, value: c.display ?? c.value, status: 'manual', msg: 'could not add table row' });
          break;
        }
        const instSom = t.groupSom.replace(/\[\d+\]$/, `[${r}]`);
        for (const c of t.rows[r]) {
          progress({ done, total, label: `${t.title} row ${r + 1}: ${c.label}`, section: t.title });
          await jitter(150, 400);
          const cmp = c.relSom ? safe(() => g.resolveNode(instSom + c.relSom)) : null;
          let res;
          if (!cmp) res = { code: c.code, key: c.key, label: c.label, value: c.display ?? c.value, status: 'manual', msg: 'table cell not found' };
          else { try { res = await fillOneSafe(g, { ...c, domBase: null, allowOffscreen: true }, cmp); } catch (e) { res = { code: c.code, status: 'failed', msg: String(e) }; } }
          res.label = `${t.title} row ${r + 1}: ${c.label}`;
          const som = instSom + c.relSom, lab = res.label;
          res.retry = async () => { const x = await fillOneSafe(g, { ...c, domBase: null, allowOffscreen: true }, safe(() => g.resolveNode(som))); x.label = lab; return x; };
          log.push(res);
          done++;
        }
      }
        }
    for (const t of [...tablesLeft]) await doTableFn(t);

    // Version 1 keeps it simple: the tool does not press Save itself (MCA only unlocks the next
    // section on a real click). Set AUTO_SECTION_SAVE to true to try automatic section saves again.
    const AUTO_SECTION_SAVE = false;
    const pressed = new Set();
    for (let round = 0; round < 12 && !abort && AUTO_SECTION_SAVE; round++) {
      const locked = log.map((e, i) => [e, i]).filter(([e]) => e.status === 'skipped-readonly' && e.el && isShown(e.el) && e.retry);
      if (!locked.length) break;
      const first = locked[0][0].el;
      const btn = sectionSaves().filter(b => !pressed.has(b) && before(b, first)).pop();
      if (!btn) break;
      pressed.add(btn);
      progress({ done, total, label: 'Section Save', section: 'unlocking the next part of the form' });
      await jitter(500, 900);
      btn.click();
      log.push({ code: '', key: '', label: 'Clicked section Save (to unlock the fields below it)', status: 'section-save', msg: btn.id || '' });
      await sleep(2500);
      await dismissSaved();
      for (const [e, i] of locked) {
        if (abort) break;
        await jitter(150, 400);
        let r2;
        try { r2 = await e.retry(); } catch (err) { r2 = { ...e, status: 'failed', msg: String(err) }; }
        r2.retry = e.retry;
        log[i] = r2;
      }
    }

    // autoSave plans: dropdowns whose options load from an earlier answer (Area/Locality after the pin code)
    // are tried again last, waiting up to ~15 s for the portal to load them.
    if (plan.autoSave) {
      for (let i = 0; i < log.length && !abort; i++) {
        const e = log[i];
        if (e.status !== 'failed' || !/dropdown has no option/.test(e.msg || '') || !e.retry) continue;
        progress({ done, total, label: e.label, section: 'waiting for the portal to load the list' });
        for (let w = 0; w < 15 && !abort; w++) {
          await sleep(1000);
          let r2;
          try { r2 = await e.retry(); } catch (err) { r2 = { ...e, status: 'failed', msg: String(err) }; }
          r2.retry = e.retry;
          log[i] = r2;
          if (r2.status !== 'failed') break;
        }
      }
      await sleep(800);
    }

    // Point staff at the Save to press: the first Save below the last field filled on this page.
    let save = { clicked: false, msg: '' };
    if (abort) save.msg = 'stopped by user';
    else {
      const filledEls = log.filter(e => ['filled', 'unchanged'].includes(e.status) && e.el && isShown(e.el)).map(e => e.el);
      const lastEl = filledEls.length ? filledEls.reduce((a, b) => (before(a, b) ? b : a)) : null;
      const saves = sectionSaves();
      const lockedEls = log.filter(e => e.status === 'skipped-readonly' && e.el && isShown(e.el)).map(e => e.el);
      const locked = lockedEls.length;
      // Locked fields left: the Save just above the first of them unlocks it. Otherwise the Save after our last field.
      const btn = (stopAt && isShown(stopAt) && stopAt) || (locked && saves.filter(b => before(b, lockedEls[0])).pop())
        || (lastEl && saves.find(b => before(lastEl, b))) || saves[saves.length - 1] || findSave();
      if (!btn) save.msg = 'no Save button visible';
      else {
        safe(() => btn.scrollIntoView({ block: 'center', behavior: 'smooth' }));
        btn.style.outline = '4px solid #ff4d4f';
        btn.style.outlineOffset = '3px';
        btn.style.boxShadow = '0 0 0 8px rgba(255,77,79,.35)';
        setTimeout(() => { btn.style.outline = ''; btn.style.boxShadow = ''; }, 60000);
        const more = locked || log.some(e => e.status === 'next-section');
        save = { clicked: false, highlighted: true, locked,
                 msg: more ? 'Section done. Click the highlighted Save, then press Alt+Shift+F again for the next section'
                             : 'Click the highlighted Save to save this page' };
        // Opt-in per plan (ADT-1 sets it): press that Save, and the portal's Next when the page is done.
        // Still never Submit / Upload / DSC: Next is matched on its exact text only.
        if (plan.autoSave && !(log.some(e => e.status === 'failed'))) {
          await jitter(400, 800);
          btn.click();
          save.clicked = true;
          await sleep(2500);
          await dismissSaved();
          save.msg = 'Saved';
          // Read-only fields the portal fills itself don't hold the page back: only fields below an unclicked Save do.
          save.more = log.some(e => e.status === 'next-section');
          // A field hidden by an earlier answer may open once that answer is saved: give it one more round.
          const seen = (window.__mcaHiddenSeen = window.__mcaHiddenSeen || new Set());
          const fresh = log.filter(e => e.status === 'hidden' && !seen.has(e.key + '|' + e.label));
          fresh.forEach(e => seen.add(e.key + '|' + e.label));
          if (fresh.length) save.more = true;
          const next = plan.autoNext && !save.more && [...document.querySelectorAll('button, [type="button"]')]
            .find(b => isShown(b) && !b.disabled && /^next$/i.test(strip(b.innerText || b.value || '')) && !BLOCKED.test(strip(b.innerText || b.value || '')));
          if (next) {
            await jitter(400, 800);
            next.click();
            save.next = true;
            save.msg = 'Saved and moved to the next page';
            await sleep(3000);
          } else if (plan.watchSubmit && !save.more) {
            save.lastPage = true;  // filing queue: staff click Submit here; content.js waits for the SRN
          }
        }
      }
    }
    for (const e of log) { delete e.retry; delete e.el; }
    progress({ done: total, total, label: 'done', section: '' });
    return { log, save };
  }

  // ---------- wiring ----------

  document.addEventListener('mcafill:req', async ev => {
    let req;
    try { req = JSON.parse(ev.detail); } catch (e) { return; }
    let res;
    try {
      if (req.op === 'probe') res = { hasForm: !!document.querySelector('[id^="guideContainer-rootPanel"]'), guideBridge: !!gb() };
      else if (req.op === 'dump') res = dump();
      else if (req.op === 'fill') res = await fill(req.plan);
      else if (req.op === 'abort') { abort = true; res = { ok: true }; }
      else if (req.op === 'awaitSubmit') res = await awaitSubmit(req.maxMs || 1800000);
      else if (req.op === 'fillOne') {
        const g = gb(); const f = req.field;
        let cmp = null;
        if (g) { safe(() => g.visit(c => { const id = safe(() => c.id); if (id && keyOf(id) === f.key) cmp = c; })); if (!cmp && f.som) cmp = safe(() => g.resolveNode(f.som)); }
        const r = await fillOneSafe(g, { ...f, allowOffscreen: true }, cmp); delete r.el; delete r.value; res = r;
      }
      else if (req.op === 'uploadsMissing') {
        // Attachments on this page that the portal needs but that are still empty (we never upload).
        const out = [];
        const g = gb();
        if (g) safe(() => g.visit(c => {
          if (!/fileupload/i.test(String(safe(() => c.className, '')))) return;
          const els = widgets(safe(() => c.id, '') || '');
          if (!els.some(isShown)) return;
          const v = safe(() => c.value);
          const box = els[0].closest('[class*="guideFieldNode"]') || els[0].parentElement;
          const listed = box && box.querySelector('[class*="fileItem"], [class*="file-item"], .guide-fu-fileItemList li');
          const label = strip(safe(() => c.title) || domLabel(els[0]));
          if ((v === null || v === undefined || norm(v) === '') && !listed && (safe(() => c.mandatory) || /\*/.test(label))) out.push(label.replace(/\*/g, '').trim());
        }));
        res = out;
      }
      else if (req.op === 'attachState') {
        // For autoSave plans (ADT-1): is this attachment on screen, and does it already hold a file?
        res = req.list.map(a => {
          const els = widgets(a.domBase).filter(isShown);
          const any = document.querySelector(`[id^="${a.domBase}"]`);
          const box = (els[0] || any) && (els[0] || any).closest('[class*="guideFieldNode"]');
          if (!box || !isShown(box)) return 'other-page';
          const listed = box.querySelector('[class*="fileItem"], [class*="file-item"], .guide-fu-fileItemList li');
          const txt = [...box.querySelectorAll('input[type="text"], input:not([type])')].map(i => norm(i.value)).join('');
          return (listed && norm(listed.innerText)) || /\.pdf/i.test(txt) ? 'has-file' : 'empty';
        });
      }
      else if (req.op === 'notices') {
        autoNotices = !!req.on;
        res = autoNotices;
      }
      else if (req.op === 'attach') {
        autoNotices = true;
        // Choose the PDF (sent by the local server) and press this attachment's own Upload button.
        const a = req.att;
        const any = widgets(a.domBase).find(isShown) || document.querySelector(`[id^="${a.domBase}"]`);
        const box = any && any.closest('[class*="guideFieldNode"]');
        const input = box && box.querySelector('input[type="file"]');
        if (!input) res = { status: 'failed', msg: 'file box not found' };
        else {
          const bytes = Uint8Array.from(atob(req.b64), c => c.charCodeAt(0));
          const dt = new DataTransfer();
          const type = /\.jpe?g$/i.test(req.name) ? 'image/jpeg' : /\.png$/i.test(req.name) ? 'image/png' : 'application/pdf';
          dt.items.add(new File([bytes], req.name, { type }));
          input.files = dt.files;
          input.dispatchEvent(new Event('change', { bubbles: true }));
          input.dispatchEvent(new Event('input', { bubbles: true }));
          safe(() => box.scrollIntoView({ block: 'center' }));
          let up = null;
          for (let w = 0; w < 20 && !up; w++) {
            await sleep(300);
            up = [...box.querySelectorAll('button, [type="button"], a')].find(b => isShown(b) && !b.disabled && /^upload$/i.test(strip(b.innerText || b.value || '')));
          }
          if (!up) res = { status: 'failed', msg: 'Upload button did not become active' };
          else {
            await jitter(300, 600);
            up.click();
            let ok = false;
            for (let w = 0; w < 40 && !ok; w++) {
              await sleep(500);
              const listed = box.querySelector('[class*="fileItem"], [class*="file-item"], .guide-fu-fileItemList li');
              const dlg = [...document.querySelectorAll('[role="dialog"], .modal, [class*="modal"], [class*="Modal"]')].find(d => isShown(d) && /upload|success|attached/i.test(d.innerText || ''));
              ok = !!(listed && norm(listed.innerText)) || !!dlg || ![...box.querySelectorAll('button')].some(b => b === up && isShown(b) && !b.disabled);
            }
            await dismissSaved();
            for (const d of document.querySelectorAll('[role="dialog"], .modal, [class*="modal"], [class*="Modal"]')) {
              if (!isShown(d) || !/upload/i.test(d.innerText || '')) continue;
              const okb = [...d.querySelectorAll('button, [type="button"], a')].find(b => isShown(b) && /^(ok|close|okay)$/i.test(strip(b.innerText || b.value || '')));
              if (okb) { okb.click(); await sleep(300); }
            }
            res = ok ? { status: 'filled', msg: 'uploaded ' + req.name } : { status: 'failed', msg: 'clicked Upload, no confirmation seen: check ' + req.name };
          }
        }
      }
      else if (req.op === 'onPage') {
        res = req.keys.map(k => widgets('guideContainer-' + k + '__').some(isShown));
      }
    } catch (e) {
      res = { error: String(e && e.message || e) };
    }
    document.dispatchEvent(new CustomEvent('mcafill:res', { detail: JSON.stringify({ id: req.id, res }) }));
  });
})();
