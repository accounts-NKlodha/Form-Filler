// Relays content-script requests to the local MCA filler server. Doing the fetch
// here avoids the portal page's CSP / CORS rules entirely.
const BASE = 'http://127.0.0.1:8742';

// Clicking the toolbar icon opens the side panel (Save form / Form Filler buttons).
chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => {});

chrome.runtime.onMessage.addListener((msg, sender, reply) => {
  if (!msg || !msg.path) return false;  // status messages for the side panel, not server requests
  (async () => {
    try {
      const r = await fetch(BASE + msg.path, msg.body === undefined ? {} : {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: msg.body,
      });
      reply({ ok: r.ok, status: r.status, text: await r.text() });
    } catch (e) {
      reply({ ok: false, error: 'MCA filler server not reachable on port 8742 (' + e.message + ')' });
    }
  })();
  return true;
});
