(() => {
  const REEL_PATTERN = /instagram\.com\/(?:reel|p)\/([A-Za-z0-9_-]+)/;
  const RETRY_INTERVAL = 30000;
  const sentReels = new Set();
  let pendingQueue = [];
  let settings = {
    enabled: false,
    chatName: "",
    serverUrl: "http://localhost:7890",
  };

  async function loadSettings() {
    const stored = await chrome.storage.local.get([
      "enabled",
      "chatName",
      "serverUrl",
    ]);
    settings.enabled = stored.enabled || false;
    settings.chatName = stored.chatName || "";
    settings.serverUrl = stored.serverUrl || "http://localhost:7890";
  }

  chrome.storage.onChanged.addListener((changes) => {
    if (changes.enabled) settings.enabled = changes.enabled.newValue;
    if (changes.chatName) settings.chatName = changes.chatName.newValue;
    if (changes.serverUrl) settings.serverUrl = changes.serverUrl.newValue;
  });

  function showToast(message) {
    let toast = document.querySelector(".insta-reels-toast");
    if (!toast) {
      toast = document.createElement("div");
      toast.className = "insta-reels-toast";
      document.body.appendChild(toast);
    }
    toast.textContent = message;
    toast.classList.add("show");
    setTimeout(() => toast.classList.remove("show"), 2500);
  }

  function isInTargetChat() {
    if (!settings.chatName) return false;
    const target = settings.chatName.toLowerCase();

    // Try multiple selectors since Instagram's DOM structure changes
    const selectors = [
      '[role="heading"]',
      'header [dir="auto"]',
      '[class*="thread"] [dir="auto"]',
      // Newer IG web layout
      'div[role="main"] header span',
      'section > header span[dir="auto"]',
    ];

    for (const selector of selectors) {
      const els = document.querySelectorAll(selector);
      for (const el of els) {
        const text = el.textContent.trim().toLowerCase();
        if (text === target || text.includes(target)) {
          return true;
        }
      }
    }
    return false;
  }

  function extractReelUrls(node) {
    const urls = [];
    if (!node || !node.querySelectorAll) return urls;

    const links = node.querySelectorAll(
      'a[href*="instagram.com/reel/"], a[href*="instagram.com/p/"]'
    );
    links.forEach((link) => {
      const match = link.href.match(REEL_PATTERN);
      if (match) {
        urls.push({ url: link.href, reelId: match[1] });
      }
    });

    // Check text content for URLs without anchor tags
    const textContent = node.textContent || "";
    const textMatches = textContent.match(
      /https?:\/\/(?:www\.)?instagram\.com\/(?:reel|p)\/[A-Za-z0-9_-]+\/?/g
    );
    if (textMatches) {
      textMatches.forEach((url) => {
        const match = url.match(REEL_PATTERN);
        if (match && !urls.find((u) => u.reelId === match[1])) {
          urls.push({ url, reelId: match[1] });
        }
      });
    }

    return urls;
  }

  function getUserNote(messageNode) {
    const sibling = messageNode.nextElementSibling;
    if (!sibling) return null;
    const text = sibling.textContent?.trim();
    if (text && text.length < 200 && !REEL_PATTERN.test(text)) {
      return text;
    }
    return null;
  }

  async function sendReel(reelData) {
    try {
      const resp = await fetch(`${settings.serverUrl}/reel`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: reelData.url,
          timestamp: new Date().toISOString(),
          userNote: reelData.userNote || null,
        }),
      });
      if (resp.ok) {
        sentReels.add(reelData.reelId);
        showToast("Reel captured!");
        return true;
      }
    } catch {
      // Server unreachable, will be queued
    }
    return false;
  }

  function queueReel(reelData) {
    if (!pendingQueue.find((r) => r.reelId === reelData.reelId)) {
      pendingQueue.push(reelData);
      chrome.storage.local.set({ pendingReels: pendingQueue });
      showToast("Reel queued (server offline)");
    }
  }

  async function processReel(reelData) {
    if (sentReels.has(reelData.reelId)) return;
    const sent = await sendReel(reelData);
    if (!sent) {
      queueReel(reelData);
    }
  }

  async function retryPending() {
    if (pendingQueue.length === 0) return;
    const remaining = [];
    for (const reel of pendingQueue) {
      const sent = await sendReel(reel);
      if (!sent) remaining.push(reel);
    }
    pendingQueue = remaining;
    chrome.storage.local.set({ pendingReels: pendingQueue });
  }

  function startObserver() {
    const observer = new MutationObserver((mutations) => {
      if (!settings.enabled || !isInTargetChat()) return;

      for (const mutation of mutations) {
        for (const node of mutation.addedNodes) {
          if (node.nodeType !== Node.ELEMENT_NODE) continue;
          const reelUrls = extractReelUrls(node);
          for (const reel of reelUrls) {
            processReel({
              url: reel.url,
              reelId: reel.reelId,
              userNote: getUserNote(node),
            });
          }
        }
      }
    });

    observer.observe(document.body, {
      childList: true,
      subtree: true,
    });
  }

  async function init() {
    await loadSettings();

    const stored = await chrome.storage.local.get(["pendingReels"]);
    pendingQueue = stored.pendingReels || [];

    startObserver();
    setInterval(retryPending, RETRY_INTERVAL);

    // Scan existing messages on page load
    if (settings.enabled && isInTargetChat()) {
      const reelUrls = extractReelUrls(document.body);
      for (const reel of reelUrls) {
        processReel({ url: reel.url, reelId: reel.reelId, userNote: null });
      }
    }
  }

  init();
})();
