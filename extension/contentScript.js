(() => {
  "use strict";

  const BRIDGE = globalThis.__APOS_BRIDGE__ || {};
  const CONFIG = Object.freeze({
    wsUrl: "ws://127.0.0.1:8765",
    scanDebounceMs: 600,
    reconnectBaseMs: 1000,
    reconnectMaxMs: 15000,
    maxQueue: 50,
    maxAutoRetries: 2,
    sentKeyTtlMs: 30 * 60 * 1000,
    retryTtlMs: 30 * 60 * 1000,
    queueTtlMs: 5 * 60 * 1000,
    maxSentKeys: 200,
    maxRetryEntries: 100,
  });

  const state = {
    socket: null,
    reconnectTimer: null,
    reconnectAttempt: 0,
    scanTimer: null,
    queue: [],
    sentKeys: new Map(),
    retryCounts: new Map(),
    observer: null,
    pendingByPatchId: new Map(),
    status: {
      phase: "idle",
      message: "APOS bridge is idle",
      details: {},
      updatedAt: Date.now(),
    },
    lastServerResponse: null,
    lastError: null,
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
    state.lastError = {
      message,
      details,
      at: Date.now(),
    };
    if (details === undefined) {
      console.error("[APOS Error] " + message);
    } else {
      console.error("[APOS Error] " + message, details);
    }
  }

  function setStatus(phase, message, details) {
    state.status = {
      phase,
      message,
      details: details || {},
      updatedAt: Date.now(),
    };
    state.lastStatus = state.status;
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
      reject: rejectPatch,
      connect,
      flushQueue,
      status: state.status,
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
      attributeFilter: ["class", "data-message-author-role", "data-author-role", "data-utterance-author-role"],
    });
  }

  function scheduleScan(reason) {
    window.clearTimeout(state.scanTimer);
    state.scanTimer = window.setTimeout(() => scan(reason), CONFIG.scanDebounceMs);
  }

  function collectCodeBlocks() {
    const selectors = [
      "pre code",
      "code[data-language]",
      "code[data-lang]",
      "code[class*='language-']",
    ];
    const seen = new Set();
    const blocks = [];
    for (const selector of selectors) {
      const matches = Array.from(document.querySelectorAll(selector));
      for (const block of matches) {
        if (!seen.has(block)) {
          seen.add(block);
          blocks.push(block);
        }
      }
    }
    return blocks;
  }

  function isVisibleCodeBlock(code) {
    if (!(code instanceof Element)) {
      return false;
    }
    return !BRIDGE.isEditableSurface(code) && BRIDGE.isAssistantAuthored(code) && !BRIDGE.isUserAuthored(code);
  }

  function scan(reason) {
    pruneState();
    const blocks = collectCodeBlocks();
    debug("Raw blocks", blocks.map(describeBlock));

    for (let index = 0; index < blocks.length; index += 1) {
      const metadataBlock = blocks[index];
      if (!BRIDGE.isAposPatchBlock(metadataBlock)) {
        continue;
      }

      if (!isVisibleCodeBlock(metadataBlock)) {
        debug("Skipping non-assistant apos-patch block", describeBlock(metadataBlock, index));
        continue;
      }

      const sourceBlock = blocks[index + 1];
      if (!sourceBlock) {
        requestCorrection(
          "client:missing-source:" + shortHashSync(getCodeText(metadataBlock)),
          "An apos-patch metadata block was found, but there was no immediately following source code block.",
          {
            metadataText: getCodeText(metadataBlock),
            nextBlock: null,
            reason,
            serverResponse: null,
          },
        );
        continue;
      }

      if (!sameMessageScope(metadataBlock, sourceBlock) || BRIDGE.isUserAuthored(sourceBlock)) {
        requestCorrection(
          "client:source-scope:" + shortHashSync(getCodeText(metadataBlock)),
          "The code block immediately after apos-patch was not in the same assistant message scope.",
          {
            metadataText: getCodeText(metadataBlock),
            nextBlock: describeBlock(sourceBlock, index + 1),
            reason,
            serverResponse: null,
          },
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
          reason,
          serverResponse: null,
        },
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
          reason,
          serverResponse: null,
        },
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
          reason,
          serverResponse: null,
        },
      );
      return;
    }

    const key = createKey(metadata);
    if (state.sentKeys.has(key) || queueHasKey(key)) {
      debug("Skipping duplicate apos-patch proposal", {
        key,
        patch_id: metadata.patch_id,
        target: metadata.target,
        blockIndex: index,
      });
      setStatus("duplicate_skipped", "Duplicate apos-patch proposal ignored", { key, patch_id: metadata.patch_id });
      return;
    }

    state.sentKeys.set(key, Date.now());
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
    sendJson(metadata, key);
  }

  function parseMetadata(text) {
    if (!text) {
      return { ok: false, message: "apos-patch metadata block is empty." };
    }

    const parsed = safeParseJsonObject(text);
    if (!parsed.ok) {
      return {
        ok: false,
        message: "apos-patch metadata JSON parsing failed: " + parsed.error,
      };
    }
    return { ok: true, value: parsed.value };
  }

  function validatePayloadShape(payload) {
    const validation = BRIDGE.validateBridgePayload ? BRIDGE.validateBridgePayload(payload) : null;
    if (validation) {
      return validation;
    }
    for (const key of ["patch_id", "project_root", "target", "language", "content", "sha256"]) {
      if (typeof payload[key] !== "string" || payload[key].length === 0) {
        return { ok: false, error: key + " is required and must be a non-empty string." };
      }
    }
    return { ok: true };
  }

  function createKey(payload) {
    if (BRIDGE.createBridgeKey) {
      return BRIDGE.createBridgeKey(payload);
    }
    return String(payload.patch_id || "") + ":" + String(payload.sha256 || "").trim().toLowerCase();
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
      setStatus("socket_error", "Unable to connect to local APOS server", { error: String(error) });
      scheduleReconnect();
      return;
    }

    state.socket.addEventListener("open", () => {
      state.reconnectAttempt = 0;
      log("Connected to local server");
      setStatus("connected", "Connected to local APOS server", { queued: state.queue.length });
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
      setStatus("disconnected", "Local APOS server disconnected", {
        code: event.code,
        reason: event.reason || "",
      });
      scheduleReconnect();
    });

    state.socket.addEventListener("error", (event) => {
      fail("WebSocket connection failed", event);
      setStatus("socket_error", "Local APOS server connection failed", { error: String(event && event.type ? event.type : "error") });
    });
  }

  function scheduleReconnect() {
    state.reconnectAttempt += 1;
    const delay = Math.min(CONFIG.reconnectBaseMs * 2 ** (state.reconnectAttempt - 1), CONFIG.reconnectMaxMs);
    window.clearTimeout(state.reconnectTimer);
    state.reconnectTimer = window.setTimeout(() => {
      state.reconnectTimer = null;
      connect();
    }, delay);
  }

  function queueHasKey(key) {
    return state.queue.some((item) => item.key === key);
  }

  function enqueuePayload(payload, key, reason) {
    const item = {
      key,
      payload,
      message: JSON.stringify(payload),
      queuedAt: Date.now(),
      attempts: 0,
      reason: reason || "queue",
    };
    state.queue.push(item);
    while (state.queue.length > CONFIG.maxQueue) {
      const dropped = state.queue.shift();
      if (dropped) {
        state.sentKeys.delete(dropped.key);
      }
    }
    setStatus("queued", "APOS patch proposal queued", { key, queueLength: state.queue.length });
    fail("WebSocket is not open; queued message", { type: payload.type, key });
    connect();
  }

  function sendJson(payload, key) {
    const message = JSON.stringify(payload);
    if (!state.socket || state.socket.readyState !== WebSocket.OPEN) {
      enqueuePayload(payload, key, "socket_not_open");
      return;
    }

    try {
      state.socket.send(message);
      state.pendingByPatchId.set(payload.patch_id, {
        key,
        sentAt: Date.now(),
        target: payload.target,
      });
      setStatus("sent", "APOS patch proposal sent", { key, patch_id: payload.patch_id, target: payload.target });
    } catch (error) {
      fail("WebSocket send failed", error);
      enqueuePayload(payload, key, "send_failed");
      scheduleReconnect();
    }
  }

  function flushQueue() {
    pruneState();
    if (!state.socket || state.socket.readyState !== WebSocket.OPEN) {
      return;
    }

    while (state.queue.length) {
      const item = state.queue.shift();
      if (!item) {
        continue;
      }
      if (Date.now() - item.queuedAt > CONFIG.queueTtlMs) {
        state.sentKeys.delete(item.key);
        continue;
      }
      try {
        item.attempts += 1;
        item.lastAttemptAt = Date.now();
        state.socket.send(item.message);
        state.pendingByPatchId.set(item.payload.patch_id, {
          key: item.key,
          sentAt: Date.now(),
          target: item.payload.target,
        });
        debug("Flushed queued message", {
          type: item.payload.type,
          patch_id: item.payload.patch_id,
          queuedForMs: Date.now() - item.queuedAt,
        });
        setStatus("sent", "Queued APOS patch proposal flushed", {
          key: item.key,
          patch_id: item.payload.patch_id,
          target: item.payload.target,
        });
      } catch (error) {
        fail("Failed to flush queued message", error);
        state.queue.unshift(item);
        scheduleReconnect();
        break;
      }
    }
  }

  function handleServerMessage(raw) {
    let message;
    try {
      message = JSON.parse(String(raw));
    } catch (error) {
      fail("Server response was not JSON", raw);
      setStatus("server_error", "Server response was not valid JSON", { raw: String(raw).slice(0, 400) });
      return;
    }

    state.lastServerResponse = message;
    log("Server response", message);

    if (message.type === "validation_passed") {
      if (message.patch_id) {
        state.pendingByPatchId.set(message.patch_id, {
          key: createKey(message),
          status: "pending_registered",
          target: message.target || "",
          item_id: message.item_id || null,
        });
      }
      setStatus("pending_registered", "Patch proposal registered in the approval queue", {
        patch_id: message.patch_id || null,
        target: message.target || null,
        item_id: message.item_id || null,
      });
      return;
    }

    if (message.type === "validation_failed") {
      setStatus("validation_failed", "Local APOS validation failed", {
        patch_id: message.patch_id || null,
        retry_allowed: message.retry_allowed !== false,
      });
      if (message.retry_allowed !== false) {
        requestCorrection(
          "server:" + String(message.patch_id || message.target || "unknown"),
          "Local APOS validation failed.",
          {
            serverResponse: message,
          },
        );
      }
      return;
    }

    if (message.type === "rejected") {
      if (message.patch_id) {
        state.pendingByPatchId.delete(message.patch_id);
      }
      setStatus("rejected", "Patch proposal was rejected", {
        patch_id: message.patch_id || null,
        item_id: message.item_id || null,
      });
      return;
    }

    if (message.type === "commit_succeeded") {
      setStatus("committed", "Patch commit succeeded", {
        patch_id: message.patch_id || null,
        item_id: message.item_id || null,
      });
      return;
    }

    if (message.type === "error") {
      fail("Server returned an error", message);
      setStatus("server_error", "Server returned an error", {
        error_kind: message.error_kind || null,
        patch_id: message.patch_id || null,
      });
      return;
    }

    setStatus("server_message", "Received server message", { type: message.type || null });
  }

  function requestCorrection(key, reason, details) {
    pruneState();
    const current = state.retryCounts.get(key) || { count: 0, lastSeen: 0 };
    if (current.count >= CONFIG.maxAutoRetries) {
      fail("Automatic retry limit reached; human intervention required", {
        key,
        reason,
        details,
      });
      setStatus("retry_exhausted", "Automatic retry limit reached", { key, reason });
      return false;
    }

    current.count += 1;
    current.lastSeen = Date.now();
    state.retryCounts.set(key, current);
    const prompt = buildRetryPrompt(current.count, reason, details || {});
    const injected = injectPrompt(prompt);
    if (!injected) {
      setStatus("retry_prompt_failed", "Automatic retry prompt could not be inserted", { key, reason });
      return false;
    }
    setStatus("retry_prompt", "Automatic retry prompt inserted", { key, reason, attempt: current.count });
    return true;
  }

  function commitPatch(patchId) {
    const normalizedPatchId = String(patchId || "").trim();
    if (!normalizedPatchId) {
      fail("commitPatch requires a non-empty patchId");
      return false;
    }
    sendJson(
      {
        type: "commit_patch",
        patch_id: normalizedPatchId,
      },
      "commit:" + normalizedPatchId,
    );
    setStatus("commit_requested", "Commit requested", { patch_id: normalizedPatchId });
    return true;
  }

  function rejectPatch(patchId, rejectedBy, reason) {
    const normalizedPatchId = String(patchId || "").trim();
    if (!normalizedPatchId) {
      fail("rejectPatch requires a non-empty patchId");
      return false;
    }
    sendJson(
      {
        type: "reject_patch",
        patch_id: normalizedPatchId,
        rejected_by: String(rejectedBy || "").trim() || undefined,
        reason: String(reason || "").trim() || undefined,
      },
      "reject:" + normalizedPatchId,
    );
    setStatus("rejection_requested", "Rejection requested", { patch_id: normalizedPatchId });
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

    const parsed = safeParseJsonObject(metadataText);
    if (parsed.ok) {
      defaults.patch_id = String(parsed.value.patch_id || defaults.patch_id);
      defaults.project_root = String(parsed.value.project_root || defaults.project_root);
      defaults.target = String(parsed.value.target || defaults.target);
      defaults.language = String(parsed.value.language || defaults.language);
    } else {
      debug("Retry prompt metadata parse failed", parsed.error);
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

    return candidates.filter(isVisibleInput).sort((a, b) => scoreInput(b) - scoreInput(a))[0] || null;
  }

  function isVisibleInput(element) {
    if (typeof Element !== "undefined" && !(element instanceof Element)) {
      return false;
    }
    if (!element || typeof element.getBoundingClientRect !== "function") {
      return false;
    }
    const style = window.getComputedStyle ? window.getComputedStyle(element) : { display: "block", visibility: "visible" };
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
    const prototype = typeof HTMLTextAreaElement !== "undefined" ? HTMLTextAreaElement.prototype : null;
    const descriptor = prototype ? Object.getOwnPropertyDescriptor(prototype, "value") : null;
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
      apos: BRIDGE.isAposPatchBlock ? BRIDGE.isAposPatchBlock(code) : detectLanguage(code) === "apos-patch",
      userAuthored: BRIDGE.isUserAuthored ? BRIDGE.isUserAuthored(code) : false,
      chars: getCodeText(code).length,
      preview: getCodeText(code).slice(0, 120).replace(/\s+/g, " "),
    };
  }

  function detectLanguage(code) {
    if (BRIDGE.getCodeLanguage) {
      return BRIDGE.getCodeLanguage(code);
    }
    if (!(typeof Element !== "undefined" && code instanceof Element)) {
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
    return BRIDGE.normalizeLanguage ? BRIDGE.normalizeLanguage(language) : String(language || "").trim().toLowerCase();
  }

  function getCodeText(code) {
    if (BRIDGE.getCodeText) {
      return BRIDGE.getCodeText(code);
    }
    return code && code.textContent ? normalizeNewlines(code.textContent) : "";
  }

  function normalizeNewlines(text) {
    return BRIDGE.normalizeNewlines ? BRIDGE.normalizeNewlines(text) : String(text || "").replace(/\r\n?/g, "\n");
  }

  function isShaPlaceholder(value) {
    if (BRIDGE.isShaPlaceholder) {
      return BRIDGE.isShaPlaceholder(value);
    }
    const normalized = String(value || "").trim().toLowerCase();
    return !normalized || normalized === "..." || normalized === "콘텐츠 해시" || normalized === "content hash";
  }

  function sameMessageScope(first, second) {
    if (BRIDGE.sameMessageScope) {
      return BRIDGE.sameMessageScope(first, second);
    }
    const firstContainer = first && first.closest ? first.closest("[data-message-author-role]") : null;
    const secondContainer = second && second.closest ? second.closest("[data-message-author-role]") : null;
    if (!firstContainer || !secondContainer) {
      return false;
    }
    return firstContainer === secondContainer;
  }

  function isUserAuthored(element) {
    if (BRIDGE.isUserAuthored) {
      return BRIDGE.isUserAuthored(element);
    }
    const container = element && element.closest ? element.closest("[data-message-author-role]") : null;
    return container && container.getAttribute("data-message-author-role") === "user";
  }

  function safeParseJsonObject(text) {
    if (BRIDGE.safeParseJsonObject) {
      return BRIDGE.safeParseJsonObject(text);
    }
    try {
      const parsed = JSON.parse(normalizeNewlines(text));
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        return { ok: false, error: "metadata must be a JSON object" };
      }
      return { ok: true, value: parsed };
    } catch (error) {
      return { ok: false, error: error instanceof Error ? error.message : String(error || "Invalid JSON") };
    }
  }

  function shortHashSync(text) {
    if (BRIDGE.shortHashSync) {
      return BRIDGE.shortHashSync(text);
    }
    let hash = 2166136261;
    const value = String(text || "");
    for (let index = 0; index < value.length; index += 1) {
      hash ^= value.charCodeAt(index);
      hash = Math.imul(hash, 16777619);
    }
    return (hash >>> 0).toString(16);
  }

  async function sha256Hex(text) {
    if (globalThis.crypto && globalThis.crypto.subtle) {
      const bytes = new TextEncoder().encode(text);
      const digest = await globalThis.crypto.subtle.digest("SHA-256", bytes);
      return Array.from(new Uint8Array(digest))
        .map((byte) => byte.toString(16).padStart(2, "0"))
        .join("");
    }

    if (typeof require === "function") {
      const { createHash } = require("node:crypto");
      return createHash("sha256").update(String(text || ""), "utf8").digest("hex");
    }

    throw new Error("SHA-256 is not available in this runtime");
  }

  function createKey(payload) {
    if (BRIDGE.createBridgeKey) {
      return BRIDGE.createBridgeKey(payload);
    }
    return String(payload.patch_id || "") + ":" + String(payload.sha256 || "").trim().toLowerCase();
  }

  function pruneState() {
    if (BRIDGE.pruneTimedEntries) {
      BRIDGE.pruneTimedEntries(state.sentKeys, CONFIG.sentKeyTtlMs, CONFIG.maxSentKeys);
      BRIDGE.pruneTimedEntries(state.retryCounts, CONFIG.retryTtlMs, CONFIG.maxRetryEntries);
    }
    pruneQueue();
  }

  function pruneQueue() {
    const now = Date.now();
    const kept = [];
    for (const item of state.queue) {
      if (now - item.queuedAt > CONFIG.queueTtlMs) {
        state.sentKeys.delete(item.key);
        continue;
      }
      kept.push(item);
    }
    while (kept.length > CONFIG.maxQueue) {
      const dropped = kept.shift();
      if (dropped) {
        state.sentKeys.delete(dropped.key);
      }
    }
    state.queue = kept;
  }

  function queueHasKey(key) {
    return state.queue.some((item) => item.key === key);
  }

  function flushPendingByPatchId(patchId) {
    if (!patchId) {
      return;
    }
    state.pendingByPatchId.set(patchId, {
      key: createKey({ patch_id: patchId, sha256: patchId }),
      status: "pending_registered",
      updatedAt: Date.now(),
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
