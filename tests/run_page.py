"""Drive extension/page.js against the local mock form (never MCA).

    python run_page.py dump out.json
    python run_page.py fill plan.json out.json
Needs Playwright (the spike venv has it).
"""
import json
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
PAGE_JS = (HERE.parent / "extension" / "page.js").read_text(encoding="utf-8")

CALL = """async ([op, extra]) => new Promise(res => {
  document.addEventListener('mcafill:res', ev => res(JSON.parse(ev.detail).res), { once: true });
  document.dispatchEvent(new CustomEvent('mcafill:req', { detail: JSON.stringify({ id: 1, op, ...extra }) }));
})"""


def main():
    op = sys.argv[1]
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page()
        page.goto((HERE / "form-mocktest.html").as_uri())
        page.add_script_tag(content=PAGE_JS)
        show = os.environ.get("MOCK_PAGE")  # '1' = Part A + signatories, '2' = Balance Sheet, unset = all
        if show:
            page.evaluate("""p => {
              const one = ['partA', 'sig'], hide = p === '1' ? ['bs'] : one;
              for (const n of hide) document.getElementById(`guideContainer-rootPanel-${n}___guide-item`).style.display = 'none';
            }""", show)
        if os.environ.get("MOCK_LOCK"):
            # Balance sheet row 2 stays read-only until a section Save above it is pressed (like MCA panels).
            page.evaluate("""() => {
              const ids = ['bs-table-Row2-numericbox_rs_cy', 'bs-table-Row2-numericbox_rs_py'];
              const lock = on => { for (const i of ids) { const el = document.getElementById('guideContainer-rootPanel-' + i + '___widget'); el.readOnly = on; }
                guideBridge.visit(c => { if (ids.some(i => (c.id || '').includes(i))) c.readOnly = on; }); };
              lock(true);
              const b = document.createElement('button'); b.type = 'button'; b.textContent = 'Save';
              b.id = 'guideContainer-rootPanel-bs-panel_1415762635_cop-saveguidedraft_copy___widget';
              b.addEventListener('click', () => setTimeout(() => lock(false), 300));
              const bs = document.getElementById('guideContainer-rootPanel-bs___guide-item');
              bs.parentNode.insertBefore(b, bs);
            }""")
        if op == "dump":
            out = page.evaluate(CALL, ["dump", {}])
            Path(sys.argv[2]).write_text(json.dumps(out, indent=1), encoding="utf-8")
        else:
            plan = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
            res = page.evaluate(CALL, ["fill", {"plan": plan}])
            res["dom"] = page.evaluate("""() => Object.fromEntries([...document.querySelectorAll('input,select')]
                .map(e => [e.id.replace(/^guideContainer-rootPanel-/, ''), e.type === 'radio' ? e.checked : e.value]))""")
            res["model"] = page.evaluate("""() => { const o = {}; guideBridge.visit(c => { if (c.className && /Box|Picker|List|Radio/.test(c.className)) o[c.somExpression] = c.value; }); return o; }""")
            res["clicks"] = page.evaluate("window.clicks")
            Path(sys.argv[3]).write_text(json.dumps(res, indent=1), encoding="utf-8")
        b.close()


if __name__ == "__main__":
    main()
