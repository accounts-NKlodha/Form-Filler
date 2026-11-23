// Clicking the toolbar button opens the side panel. All the work is in sidepanel.js.
chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true }).catch(() => {});
