const DEFAULT_SERVER_URL = "http://localhost:7890";

// Show the number of queued (unsent) reels on the action badge,
// or clear the badge when nothing is pending.
async function updateBadgeFromPending() {
  const { pendingReels } = await chrome.storage.local.get(["pendingReels"]);
  const pending = pendingReels || [];
  if (pending.length > 0) {
    chrome.action.setBadgeText({ text: String(pending.length) });
    chrome.action.setBadgeBackgroundColor({ color: "#F44336" });
  } else {
    chrome.action.setBadgeText({ text: "" });
  }
}

// Monitor pending reels and keep the badge count in sync
chrome.storage.onChanged.addListener((changes) => {
  if (changes.pendingReels) {
    updateBadgeFromPending();
  }
});

// Check server connectivity periodically. Sets the "!" badge while the
// server is down and clears it (restoring any pending count) on recovery.
async function checkServerHealth() {
  const { serverUrl, enabled } = await chrome.storage.local.get([
    "serverUrl",
    "enabled",
  ]);
  if (!enabled) {
    // Don't leave a stale "!" up while capture is turned off; fall back to
    // the pending-count badge (which clears itself when nothing is queued).
    await updateBadgeFromPending();
    return;
  }

  const url = serverUrl || DEFAULT_SERVER_URL;
  let healthy = false;
  try {
    const resp = await fetch(`${url}/status`);
    healthy = resp.ok;
  } catch {
    healthy = false;
  }

  if (healthy) {
    await updateBadgeFromPending();
  } else {
    chrome.action.setBadgeText({ text: "!" });
    chrome.action.setBadgeBackgroundColor({ color: "#FF9800" });
  }
}

// Check every 60 seconds, plus once whenever the service worker starts
chrome.alarms.create("healthCheck", { periodInMinutes: 1 });
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === "healthCheck") {
    checkServerHealth();
  }
});
checkServerHealth();
