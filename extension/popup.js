const DEFAULT_SERVER_URL = "http://localhost:7890";

document.addEventListener("DOMContentLoaded", async () => {
  const enabledEl = document.getElementById("enabled");
  const chatNameEl = document.getElementById("chatName");
  const serverUrlEl = document.getElementById("serverUrl");
  const saveBtn = document.getElementById("save");
  const statusEl = document.getElementById("status");

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
  await checkServer(settings.serverUrl || DEFAULT_SERVER_URL, statusEl);

  saveBtn.addEventListener("click", async () => {
    const serverUrl = serverUrlEl.value.trim() || DEFAULT_SERVER_URL;
    await chrome.storage.local.set({
      enabled: enabledEl.checked,
      chatName: chatNameEl.value.trim(),
      serverUrl: serverUrl,
    });
    await checkServer(serverUrl, statusEl);
    statusEl.textContent = "Settings saved!";
    statusEl.className = "status connected";
  });
});

async function checkServer(url, statusEl) {
  try {
    const resp = await fetch(`${url}/status`);
    if (resp.ok) {
      statusEl.textContent = "Server connected";
      statusEl.className = "status connected";
    } else {
      statusEl.textContent = "Server error";
      statusEl.className = "status disconnected";
    }
  } catch {
    statusEl.textContent = "Server not reachable";
    statusEl.className = "status disconnected";
  }
}
