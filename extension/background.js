// Monitor pending reels and show badge count
chrome.storage.onChanged.addListener((changes) => {
  if (changes.pendingReels) {
    const pending = changes.pendingReels.newValue || [];
    if (pending.length > 0) {
      chrome.action.setBadgeText({ text: String(pending.length) });
      chrome.action.setBadgeBackgroundColor({ color: "#F44336" });
    } else {
      chrome.action.setBadgeText({ text: "" });
    }
  }
});

// Check server connectivity periodically
async function checkServerHealth() {
  const { serverUrl, enabled } = await chrome.storage.local.get([
    "serverUrl",
    "enabled",
  ]);
  if (!enabled) return;

  const url = serverUrl || "http://localhost:7890";
  try {
    const resp = await fetch(`${url}/status`);
    if (!resp.ok) {
      chrome.action.setBadgeText({ text: "!" });
      chrome.action.setBadgeBackgroundColor({ color: "#FF9800" });
    }
  } catch {
    chrome.action.setBadgeText({ text: "!" });
    chrome.action.setBadgeBackgroundColor({ color: "#FF9800" });
  }
}

// Check every 60 seconds
chrome.alarms.create("healthCheck", { periodInMinutes: 1 });
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "healthCheck") {
    checkServerHealth();
  }
});
