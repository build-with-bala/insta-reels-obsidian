const DEFAULT_SERVER_URL = "http://localhost:7890";

document.addEventListener("DOMContentLoaded", async () => {
  const enabledEl = document.getElementById("enabled");
  const chatNameEl = document.getElementById("chatName");
  const serverUrlEl = document.getElementById("serverUrl");
  const saveBtn = document.getElementById("save");
  const statusEl = document.getElementById("status");
  const serverPendingEl = document.getElementById("serverPending");
  const pendingListEl = document.getElementById("pendingList");
  const retryBtn = document.getElementById("retryBtn");
  const retryResultEl = document.getElementById("retryResult");

  // Load saved settings
  const settings = await chrome.storage.local.get([
    "enabled",
    "chatName",
    "serverUrl",
  ]);
  enabledEl.checked = settings.enabled || false;
  chatNameEl.value = settings.chatName || "";
  serverUrlEl.value = settings.serverUrl || DEFAULT_SERVER_URL;

  // Check server status on popup open
  const serverResult = await checkServer(settings.serverUrl || DEFAULT_SERVER_URL);
  renderStatus(statusEl, serverResult);
  renderServerPending(serverPendingEl, serverResult);

  // Browser-side queue of reels that could not be sent to the server
  const { pendingReels } = await chrome.storage.local.get(["pendingReels"]);
  renderPendingList(pendingListEl, pendingReels || []);

  // Live-update the list while the popup is open
  chrome.storage.onChanged.addListener((changes) => {
    if (changes.pendingReels) {
      renderPendingList(pendingListEl, changes.pendingReels.newValue || []);
    }
  });

  saveBtn.addEventListener("click", async () => {
    const serverUrl = serverUrlEl.value.trim() || DEFAULT_SERVER_URL;
    await chrome.storage.local.set({
      enabled: enabledEl.checked,
      chatName: chatNameEl.value.trim(),
      serverUrl: serverUrl,
    });
    // Report the real server state: green only when the server actually
    // responded with a 2xx, red with the failure reason otherwise.
    renderStatus(statusEl, await checkServer(serverUrl), true);
  });

  retryBtn.addEventListener("click", async () => {
    const saved = await chrome.storage.local.get(["serverUrl"]);
    const serverUrl = saved.serverUrl || DEFAULT_SERVER_URL;
    retryBtn.disabled = true;
    retryBtn.textContent = "Retrying…";
    try {
      const resp = await fetch(`${serverUrl}/retry`, { method: "POST" });
      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}`);
      }
      const data = await resp.json();
      retryResultEl.textContent =
        `Retried ${data.retried}: ${data.recovered} recovered, ` +
        `${data.still_pending} still pending`;
      retryResultEl.className = "status connected";
      // Refresh counts now that the server queue has changed
      const refreshed = await checkServer(serverUrl);
      renderStatus(statusEl, refreshed);
      renderServerPending(serverPendingEl, refreshed);
    } catch {
      retryResultEl.textContent = "Retry failed: server not reachable";
      retryResultEl.className = "status disconnected";
    } finally {
      retryBtn.disabled = false;
      retryBtn.textContent = "Retry failed now";
    }
  });
});

async function checkServer(url) {
  try {
    const resp = await fetch(`${url}/status`);
    if (!resp.ok) {
      return { ok: false, message: `Server error (HTTP ${resp.status})` };
    }
    const data = await resp.json();
    const counts = data.reel_counts || {};
    const total = Object.values(counts).reduce((a, b) => a + b, 0);
    return {
      ok: true,
      message: `Server connected (${total} reels saved)`,
      counts: counts,
    };
  } catch {
    return { ok: false, message: "Server not reachable" };
  }
}

function renderServerPending(serverPendingEl, result) {
  if (!result.ok) {
    serverPendingEl.textContent = "Server queue: unavailable";
    return;
  }
  const counts = result.counts || {};
  const fetchFailed = counts["fetch-failed"] || 0;
  const untagged = counts["untagged"] || 0;
  if (fetchFailed === 0 && untagged === 0) {
    serverPendingEl.textContent = "Server queue: empty";
  } else {
    serverPendingEl.textContent =
      `Server queue: ${fetchFailed} fetch-failed, ${untagged} untagged`;
  }
}

function renderPendingList(pendingListEl, pendingReels) {
  const MAX_ITEMS = 10;
  pendingListEl.textContent = "";
  if (pendingReels.length === 0) {
    const li = document.createElement("li");
    li.className = "muted";
    li.textContent = "No reels queued in this browser.";
    pendingListEl.appendChild(li);
    return;
  }
  for (const reel of pendingReels.slice(0, MAX_ITEMS)) {
    const li = document.createElement("li");
    li.textContent = reel.userNote
      ? `${reel.reelId} (${reel.userNote})`
      : reel.reelId;
    pendingListEl.appendChild(li);
  }
  if (pendingReels.length > MAX_ITEMS) {
    const li = document.createElement("li");
    li.textContent = `…and ${pendingReels.length - MAX_ITEMS} more`;
    pendingListEl.appendChild(li);
  }
}

function renderStatus(statusEl, result, justSaved = false) {
  const prefix = justSaved ? "Settings saved. " : "";
  statusEl.textContent = prefix + result.message;
  statusEl.className = result.ok ? "status connected" : "status disconnected";
}
