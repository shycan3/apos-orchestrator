(() => {
  "use strict";

  const CONFIG = Object.freeze({
    wsUrl: "ws://127.0.0.1:8765",
    scanDebounceMs: 600,
    reconnectBaseMs: 1000,
    reconnectMaxMs: 15000,
    maxQueue: 50,
    maxAutoRetries: 2,
  });

  const state = {
    socket: null,
    reconnectTimer: null,
    reconnectAttempt: 0,
    scanTimer: null,
    queue: [],
    sentKeys: new Set(),
    retryCounts: new Map(),
    observer: null,
  };

  function log(message, details) {
    if (details === undefined) {
      console.log("[APOS] " + message);
    } else {
      console.log("[APOS] " + message, details);
    }
  }

  function debug(message, details) {
    if (details === undefined) {
      console.log("[APOS Debug] " + message);
    } else {
      console.log("[APOS Debug] " + message, details);
    }
  }

  function fail(message, details) {
    if (details === undefined) {
      console.error("[APOS Error] " + message);
    } else {
      console.error("[APOS Error] " + message, details);
    }
  }

  function init() {
    log("Content script initialized");
    connect();
    installObserver();
    scheduleScan("initial");
    window.__APOS_V32__ = {
      scan: () => scan("manual"),
      inject: injectPrompt,
      commit: commitPatch,
      connect,
      state,
    };
  }

  function installObserver() {
    const root = document.documentElement || document.body;
    if (!root) {
      window.setTimeout(installObserver, 250);
      return;
    }

    if (state.observer) {
      state.observer.disconnect();
    }

    state.observer = new MutationObserver(() => scheduleScan("mutation"));
    state.observer.observe(root, {
      childList: true,
      subtree: true,
      characterData: true,
      attributes: true,
      attributeFilter: ["class", "data-message-author-role"],
    });
  }

  function scheduleScan(reason) {
    window.clearTimeout(state.scanTimer);
    state.scanTimer = window.setTimeout(() => scan(reason), CONFIG.scanDebounceMs);
  }

  function scan(reason) {
    const blocks = Array.from(document.querySelectorAll("pre code"));
    debug("Raw blocks", blocks.map(describeBlock));

    for (let index = 0; index < blocks.length; index += 1) {
      const metadataBlock = blocks[index];
      if (!isAposPatchBlock(metadataBlock)) {
        continue;
      }

      if (isUserAuthored(metadataBlock)) {
        debug("Skipping user-authored apos-patch block", describeBlock(metadataBlock, index));
        continue;
      }

      const sourceBlock = blocks[index + 1];
      if (!sourceBlock) {
        requestCorrection(
          "client:missing-source:" + shortHashSync(getCodeText(metadataBlock)),
          "An apos-patch metadata block was found, but there was no immediately following source code block.",
          {
            metadataText: getCodeText(metadataBlock),
            serverResponse: null,
          }
        );
        continue;
      }

      if (isUserAuthored(sourceBlock) || !sameMessageScope(metadataBlock, sourceBlock)) {
        requestCorrection(
          "client:source-scope:" + shortHashSync(getCodeText(metadataBlock)),
          "The code block immediately after apos-patch was not in the same assistant message scope.",
          {
            metadataText: getCodeText(metadataBlock),
            nextBlock: describeBlock(sourceBlock, index + 1),
            serverResponse: null,
          }
        );
        continue;
      }

      processPair(metadataBlock, sourceBlock, index, reason).catch((error) => {
        fail("Unexpected pair processing failure", error);
      });
    }
  }

  async function processPair(metadataBlock, sourceBlock, index, reason) {
    const metadataText = getCodeText(metadataBlock).trim();
    const sourceContent = normalizeNewlines(getCodeText(sourceBlock));
    const sourceLanguage = detectLanguage(sourceBlock);
    const parsed = parseMetadata(metadataText);

    if (!parsed.ok) {
      requestCorrection(
        "client:metadata-json:" + shortHashSync(metadataText),
        parsed.message,
        {
          metadataText,
          sourceLanguage,
          sourcePreview: sourceContent.slice(0, 800),
          serverResponse: null,
        }
      );
      return;
    }

    const metadata = parsed.value;
    metadata.type = "propose_patch";
    metadata.language = String(metadata.language || sourceLanguage || "").trim();
    metadata.content = sourceContent;

    const contentSha = await sha256Hex(sourceContent);
    const declaredSha = String(metadata.sha256 || "").trim();
    if (declaredSha && !isShaPlaceholder(declaredSha) && declaredSha !== contentSha) {
      requestCorrection(
        "client:sha-mismatch:" + String(metadata.patch_id || shortHashSync(metadataText)),
        "sha256 does not match the immediately following source code block.",
        {
          declared_sha256: declaredSha,
          actual_sha256: contentSha,
          metadataText,
          sourceLanguage,
          sourcePreview: sourceContent.slice(0, 800),
          serverResponse: null,
        }
      );
      return;
    }
    metadata.sha256 = contentSha;

    const validation = validatePayloadShape(metadata);
    if (!validation.ok) {
      requestCorrection(
        "client:bad-shape:" + String(metadata.patch_id || shortHashSync(metadataText)),
        validation.message,
        {
          metadata,
          sourceLanguage,
          sourcePreview: sourceContent.slice(0, 800),
          serverResponse: null,
        }
      );
      return;
    }

    const key = metadata.patch_id + ":" + metadata.sha256;
    if (state.sentKeys.has(key)) {
      return;
    }
    state.sentKeys.add(key);

    debug("Parsed metadata", {
      patch_id: metadata.patch_id,
      target: metadata.target,
      language: metadata.language,
      sourceLanguage,
      sha256: metadata.sha256,
      blockIndex: index,
      reason,
    });
    debug("Sending", metadata);
    sendJson(metadata);
  }

  function parseMetadata(text) {
    if (!text) {
      return { ok: false, message: "apos-patch metadata block is empty." };
    }

    try {
      const parsed = JSON.parse(text);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        return { ok: false, message: "apos-patch metadata must be one JSON object." };
      }
      return { ok: true, value: parsed };
    } catch (error) {
      return {
        ok: false,
        message: "apos-patch metadata JSON parsing failed: " + (error && error.message ? error.message : String(error)),
      };
    }
  }

  function validatePayloadShape(payload) {
    for (const key of ["patch_id", "project_root", "target", "language", "content", "sha256"]) {
      if (typeof payload[key] !== "string" || payload[key].length === 0) {
        return { ok: false, message: key + " is required and must be a non-empty string." };
      }
    }
    return { ok: true };
  }

  function connect() {
    if (state.socket && (state.socket.readyState === WebSocket.OPEN || state.socket.readyState === WebSocket.CONNECTING)) {
      return;
    }

    window.clearTimeout(state.reconnectTimer);
    try {
      state.socket = new WebSocket(CONFIG.wsUrl);
    } catch (error) {
      fail("WebSocket construction failed", error);
      scheduleReconnect();
      return;
    }

    state.socket.addEventListener("open", () => {
      state.reconnectAttempt = 0;
      log("Connected to local server");
      flushQueue();
    });

    state.socket.addEventListener("message", (event) => {
      handleServerMessage(event.data);
    });

    state.socket.addEventListener("close", (event) => {
      log("WebSocket closed; reconnect scheduled", {
        code: event.code,
        reason: event.reason || "",
        wasClean: event.wasClean,
      });
      scheduleReconnect();
    });

    state.socket.addEventListener("error", (event) => {
      fail("WebSocket connection failed", event);
    });
  }

  function scheduleReconnect() {
    state.reconnectAttempt += 1;
    const delay = Math.min(CONFIG.reconnectBaseMs * 2 ** (state.reconnectAttempt - 1), CONFIG.reconnectMaxMs);
    window.clearTimeout(state.reconnectTimer);
    state.reconnectTimer = window.setTimeout(connect, delay);
  }

  function sendJson(payload) {
    const message = JSON.stringify(payload);
    if (!state.socket || state.socket.readyState !== WebSocket.OPEN) {
      state.queue.push({ message, type: payload.type, queuedAt: Date.now() });
      if (state.queue.length > CONFIG.maxQueue) {
        state.queue.shift();
      }
      fail("WebSocket is not open; queued message", { type: payload.type });
      connect();
      return;
    }

    state.socket.send(message);
  }

  function flushQueue() {
    if (!state.socket || state.socket.readyState !== WebSocket.OPEN) {
      return;
    }

    while (state.queue.length) {
      const item = state.queue.shift();
      state.socket.send(item.message);
      debug("Flushed queued message", {
        type: item.type,
        queuedForMs: Date.now() - item.queuedAt,
      });
    }
  }

  function handleServerMessage(raw) {
    let message;
    try {
      message = JSON.parse(String(raw));
    } catch (error) {
      fail("Server response was not JSON", raw);
      return;
    }

    log("Server response", message);

    if (message.type === "validation_failed" && message.retry_allowed !== false) {
      requestCorrection(
        "server:" + String(message.patch_id || "unknown"),
        "Local APOS validation failed.",
        {
          serverResponse: message,
        }
      );
      return;
    }

    if (message.type === "error") {
      fail("Server returned an error", message);
    }
  }

  function requestCorrection(key, reason, details) {
    const current = state.retryCounts.get(key) || 0;
    if (current >= CONFIG.maxAutoRetries) {
      fail("Automatic retry limit reached; human intervention required", {
        key,
        reason,
        details,
      });
      return;
    }

    const next = current + 1;
    state.retryCounts.set(key, next);
    injectPrompt(buildRetryPrompt(next, reason, details || {}));
  }

  function commitPatch(patchId) {
    const normalizedPatchId = String(patchId || "").trim();
    if (!normalizedPatchId) {
      fail("commitPatch requires a non-empty patchId");
      return false;
    }
    sendJson({
      type: "commit_patch",
      patch_id: normalizedPatchId,
    });
    return true;
  }

  function parseMetadataDefaults(details) {
    const defaults = {
      patch_id: "unique-patch-id",
      project_root: "<project_root>",
      target: "workspace/active_code.py",
      language: "python",
    };

    const metadata = details && details.metadata && typeof details.metadata === "object" ? details.metadata : null;
    if (metadata) {
      defaults.patch_id = String(metadata.patch_id || defaults.patch_id);
      defaults.project_root = String(metadata.project_root || defaults.project_root);
      defaults.target = String(metadata.target || defaults.target);
      defaults.language = String(metadata.language || defaults.language);
      return defaults;
    }

    const metadataText = details && typeof details.metadataText === "string" ? details.metadataText : "";
    if (!metadataText.trim()) {
      return defaults;
    }

    try {
      const parsed = JSON.parse(metadataText);
      if (parsed && typeof parsed === "object") {
        defaults.patch_id = String(parsed.patch_id || defaults.patch_id);
        defaults.project_root = String(parsed.project_root || defaults.project_root);
        defaults.target = String(parsed.target || defaults.target);
        defaults.language = String(parsed.language || defaults.language);
      }
    } catch (error) {
      debug("Retry prompt metadata parse failed", error);
    }

    return defaults;
  }

  function buildRetryPrompt(attempt, reason, details) {
    const response = details.serverResponse || null;
    const safeDetails = JSON.stringify(details, null, 2);
    const defaults = parseMetadataDefaults(details);
    return [
      "APOS local validation failed.",
      "Retry " + attempt + " of " + CONFIG.maxAutoRetries + ".",
      "",
      "Reason:",
      reason,
      "",
      "Reply with exactly two fenced code blocks and no extra prose.",
      "",
      "First block:",
      "```apos-patch",
      "{",
      '  "patch_id": ' + JSON.stringify(defaults.patch_id) + ",",
      '  "project_root": ' + JSON.stringify(defaults.project_root) + ",",
      '  "target": ' + JSON.stringify(defaults.target) + ",",
      '  "language": ' + JSON.stringify(defaults.language) + ",",
      '  "sha256": ""',
      "}",
      "```",
      "",
      "Second block:",
      "```python",
      "def main():",
      "    print(\"fixed\")",
      "```",
      "",
      "Server response:",
      "```json",
      JSON.stringify(response, null, 2),
      "```",
      "",
      "Debug details:",
      "```json",
      safeDetails,
      "```",
    ].join("\n");
  }

  function injectPrompt(text) {
    const target = findPromptInput();
    if (!target) {
      fail("Could not find a prompt input for automatic retry");
      return false;
    }

    focusElement(target);
    if (target.tagName && target.tagName.toLowerCase() === "textarea") {
      setNativeValue(target, text);
    } else {
      target.textContent = text;
    }

    dispatchInput(target);
    return true;
  }

  function findPromptInput() {
    const selectors = [
      "textarea",
      "[data-testid='prompt-textarea']",
      "[contenteditable='true']",
      "[role='textbox']",
    ];

    const candidates = [];
    for (const selector of selectors) {
      candidates.push(...Array.from(document.querySelectorAll(selector)));
    }

    return candidates
      .filter(isVisibleInput)
      .sort((a, b) => scoreInput(b) - scoreInput(a))[0] || null;
  }

  function isVisibleInput(element) {
    if (!(element instanceof Element)) {
      return false;
    }
    const style = window.getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return style.display !== "none" && style.visibility !== "hidden" && rect.width > 1 && rect.height > 1;
  }

  function scoreInput(element) {
    const rect = element.getBoundingClientRect();
    const testId = element.getAttribute("data-testid") || "";
    const role = element.getAttribute("role") || "";
    let score = 0;
    if (testId === "prompt-textarea") {
      score += 500;
    }
    if (role === "textbox") {
      score += 100;
    }
    if (element.tagName && element.tagName.toLowerCase() === "textarea") {
      score += 100;
    }
    score += Math.round(rect.bottom);
    return score;
  }

  function setNativeValue(element, value) {
    const descriptor = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value");
    if (descriptor && descriptor.set) {
      descriptor.set.call(element, value);
    } else {
      element.value = value;
    }
  }

  function focusElement(element) {
    try {
      element.focus({ preventScroll: false });
    } catch (error) {
      element.focus();
    }
  }

  function dispatchInput(element) {
    element.dispatchEvent(new InputEvent("input", { bubbles: true, composed: true, inputType: "insertText" }));
    element.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function describeBlock(code, index) {
    return {
      index,
      language: detectLanguage(code),
      apos: isAposPatchBlock(code),
      userAuthored: isUserAuthored(code),
      chars: getCodeText(code).length,
      preview: getCodeText(code).slice(0, 120).replace(/\s+/g, " "),
    };
  }

  function isAposPatchBlock(code) {
    return detectLanguage(code) === "apos-patch";
  }

  function detectLanguage(code) {
    if (!(code instanceof Element)) {
      return "";
    }
    const dataLanguage = code.getAttribute("data-language") || code.getAttribute("data-lang") || "";
    if (dataLanguage) {
      return normalizeLanguage(dataLanguage);
    }
    const className = code.getAttribute("class") || "";
    const match = className.match(/(?:^|\s)(?:language|lang)-([a-zA-Z0-9_-]+)/);
    return match ? normalizeLanguage(match[1]) : "";
  }

  function normalizeLanguage(language) {
    return String(language || "").trim().toLowerCase();
  }

  function getCodeText(code) {
    return code && code.textContent ? normalizeNewlines(code.textContent) : "";
  }

  function normalizeNewlines(text) {
    return String(text || "").replace(/\r\n?/g, "\n");
  }

  function isUserAuthored(element) {
    const container = element.closest && element.closest("[data-message-author-role]");
    return container && container.getAttribute("data-message-author-role") === "user";
  }

  function sameMessageScope(first, second) {
    const firstContainer = first.closest && first.closest("[data-message-author-role]");
    const secondContainer = second.closest && second.closest("[data-message-author-role]");
    if (!firstContainer || !secondContainer) {
      return true;
    }
    return firstContainer === secondContainer;
  }

  function isShaPlaceholder(value) {
    const normalized = String(value || "").trim().toLowerCase();
    return !normalized || normalized === "..." || normalized === "콘텐츠 해시" || normalized === "content hash";
  }

  async function sha256Hex(text) {
    const bytes = new TextEncoder().encode(text);
    const digest = await crypto.subtle.digest("SHA-256", bytes);
    return Array.from(new Uint8Array(digest))
      .map((byte) => byte.toString(16).padStart(2, "0"))
      .join("");
  }

  function shortHashSync(text) {
    let hash = 2166136261;
    const value = String(text || "");
    for (let index = 0; index < value.length; index += 1) {
      hash ^= value.charCodeAt(index);
      hash = Math.imul(hash, 16777619);
    }
    return (hash >>> 0).toString(16);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
