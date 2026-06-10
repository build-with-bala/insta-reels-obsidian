(() => {
  const REEL_PATTERN = /instagram\.com\/(?:reel|p)\/([A-Za-z0-9_-]+)/;
  const RETRY_INTERVAL = 30000;
  const SENT_REELS_LIMIT = 500;
  const sentReels = new Set();
  let pendingQueue = [];
  let captureActive = false;
  let lastPathname = location.pathname;
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
    if (changes.enabled) {
      settings.enabled = changes.enabled.newValue;
      if (settings.enabled && captureActive) scanExistingMessages();
    }
    if (changes.chatName) settings.chatName = changes.chatName.newValue;
    if (changes.serverUrl) settings.serverUrl = changes.serverUrl.newValue;
    if (changes.sentReels) {
      // Merge ids written by other tabs so we don't re-send their reels.
      for (const id of changes.sentReels.newValue || []) sentReels.add(id);
    }
  });

  // --- SPA navigation handling -------------------------------------------
  // Instagram is a single-page app: the script is injected on any
  // instagram.com page and capture activates only while the user is on a
  // /direct/ (DM) route. Route changes are detected by hooking
  // history.pushState/replaceState, listening for popstate, and as a
  // fallback re-checking the URL on DOM mutations.

  function isDirectPath() {
    return location.pathname.startsWith("/direct");
  }

  function updateCaptureState() {
    const shouldBeActive = isDirectPath();
    if (shouldBeActive && !captureActive) {
      captureActive = true;
      scanExistingMessages();
    } else if (!shouldBeActive && captureActive) {
      captureActive = false;
    }
  }

  function handleUrlChange() {
    if (location.pathname === lastPathname) return;
    lastPathname = location.pathname;
    updateCaptureState();
  }

  function hookHistoryNavigation() {
    for (const method of ["pushState", "replaceState"]) {
      const original = history[method];
      if (typeof original !== "function") continue;
      history[method] = function (...args) {
        const result = original.apply(this, args);
        handleUrlChange();
        return result;
      };
    }
    window.addEventListener("popstate", handleUrlChange);
  }

  // ------------------------------------------------------------------------

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

  async function markReelSent(reelId) {
    sentReels.add(reelId);
    try {
      // Re-read storage so concurrent tabs' writes aren't clobbered.
      const stored = await chrome.storage.local.get(["sentReels"]);
      const ids = stored.sentReels || [];
      if (!ids.includes(reelId)) ids.push(reelId);
      await chrome.storage.local.set({
        sentReels: ids.slice(-SENT_REELS_LIMIT),
      });
    } catch {
      // Storage unavailable; the in-memory set still dedupes this session.
    }
  }

  async function persistPendingQueue() {
    try {
      // Merge with what other tabs may have queued, drop anything already
      // sent, and dedupe by reel id before writing back.
      const stored = await chrome.storage.local.get(["pendingReels"]);
      const merged = [];
      const seen = new Set();
      for (const reel of [...(stored.pendingReels || []), ...pendingQueue]) {
        if (!reel || !reel.reelId) continue;
        if (seen.has(reel.reelId) || sentReels.has(reel.reelId)) continue;
        seen.add(reel.reelId);
        merged.push(reel);
      }
      pendingQueue = merged;
      await chrome.storage.local.set({ pendingReels: merged });
    } catch {
      // Keep the in-memory queue; the next retry cycle persists again.
    }
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
        let status = null;
        try {
          status = (await resp.json()).status;
        } catch {
          // Non-JSON body; treat as a normal capture.
        }
        await markReelSent(reelData.reelId);
        showToast(status === "duplicate" ? "Already saved" : "Reel captured!");
        return true;
      }
    } catch {
      // Server unreachable, will be queued
    }
    return false;
  }

  async function queueReel(reelData) {
    if (pendingQueue.find((r) => r.reelId === reelData.reelId)) return;
    pendingQueue.push(reelData);
    await persistPendingQueue();
    showToast("Reel queued (server offline)");
  }

  async function processReel(reelData) {
    if (sentReels.has(reelData.reelId)) return;
    const sent = await sendReel(reelData);
    if (!sent) {
      await queueReel(reelData);
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
    await persistPendingQueue();
  }

  function scanExistingMessages() {
    if (!settings.enabled || !isInTargetChat()) return;
    const reelUrls = extractReelUrls(document.body);
    for (const reel of reelUrls) {
      processReel({ url: reel.url, reelId: reel.reelId, userNote: null });
    }
  }

  function startObserver() {
    const observer = new MutationObserver((mutations) => {
      // Fallback SPA-navigation detection: Instagram re-renders on route
      // changes, so DOM mutations catch URL changes missed by the
      // history hooks.
      handleUrlChange();

      if (!captureActive || !settings.enabled || !isInTargetChat()) return;

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

    const stored = await chrome.storage.local.get([
      "pendingReels",
      "sentReels",
    ]);
    pendingQueue = stored.pendingReels || [];
    for (const id of stored.sentReels || []) sentReels.add(id);

    hookHistoryNavigation();
    startObserver();
    setInterval(retryPending, RETRY_INTERVAL);

    // Activate capture (and scan existing messages) if we loaded on /direct/
    updateCaptureState();
  }

  init();
})();
