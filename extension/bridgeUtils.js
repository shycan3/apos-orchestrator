(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
  const target = root || (typeof globalThis !== "undefined" ? globalThis : {});
  target.__APOS_BRIDGE__ = Object.assign(target.__APOS_BRIDGE__ || {}, api);
})(typeof globalThis !== "undefined" ? globalThis : typeof window !== "undefined" ? window : undefined, function () {
  function normalizeNewlines(text) {
    return String(text || "").replace(/\r\n?/g, "\n");
  }

  function normalizeLanguage(language) {
    return String(language || "").trim().toLowerCase();
  }

  function getCodeText(code) {
    return code && code.textContent ? normalizeNewlines(code.textContent) : "";
  }

  function getAttribute(element, names) {
    if (!element || typeof element.getAttribute !== "function") {
      return "";
    }
    for (const name of names) {
      const value = element.getAttribute(name);
      if (value) {
        return value;
      }
    }
    return "";
  }

  function getCodeLanguage(code) {
    if (!code || typeof code.getAttribute !== "function") {
      return "";
    }
    const fromAttribute = getAttribute(code, ["data-language", "data-lang", "lang"]);
    if (fromAttribute) {
      return normalizeLanguage(fromAttribute);
    }
    const className = code.getAttribute("class") || "";
    const classMatch = className.match(/(?:^|\s)(?:language|lang)-([a-zA-Z0-9_-]+)/);
    if (classMatch) {
      return normalizeLanguage(classMatch[1]);
    }
    const ariaLabel = getAttribute(code, ["aria-label", "data-code-language"]);
    if (ariaLabel) {
      const labelMatch = ariaLabel.match(/\b([a-zA-Z0-9_-]+)\b/);
      return labelMatch ? normalizeLanguage(labelMatch[1]) : "";
    }
    return "";
  }

  function isAposPatchBlock(code) {
    return getCodeLanguage(code) === "apos-patch";
  }

  function findMessageContainer(element) {
    if (!element || typeof element.closest !== "function") {
      return null;
    }
    return (
      element.closest("[data-message-author-role]") ||
      element.closest("[data-author-role]") ||
      element.closest("[data-utterance-author-role]") ||
      element.closest("[data-role]") ||
      null
    );
  }

  function getMessageRole(element) {
    const container = findMessageContainer(element);
    if (!container || typeof container.getAttribute !== "function") {
      return "";
    }
    return normalizeLanguage(
      getAttribute(container, ["data-message-author-role", "data-author-role", "data-utterance-author-role", "data-role"]),
    );
  }

  function isAssistantRole(role) {
    const normalized = normalizeLanguage(role);
    return ["assistant", "model", "assistant_message", "assistant-response", "response"].includes(normalized);
  }

  function isUserRole(role) {
    const normalized = normalizeLanguage(role);
    return ["user", "human", "prompt"].includes(normalized);
  }

  function isAssistantAuthored(element) {
    return isAssistantRole(getMessageRole(element));
  }

  function isUserAuthored(element) {
    return isUserRole(getMessageRole(element));
  }

  function isEditableSurface(element) {
    if (!element || typeof element.closest !== "function") {
      return false;
    }
    return Boolean(
      element.closest(
        "textarea,input,[contenteditable='true'],[contenteditable='plaintext-only'],[role='textbox'],form,[data-testid*='composer'],[data-testid*='prompt']",
      ),
    );
  }

  function sameMessageScope(first, second) {
    const firstContainer = findMessageContainer(first);
    const secondContainer = findMessageContainer(second);
    if (!firstContainer || !secondContainer) {
      return false;
    }
    return firstContainer === secondContainer;
  }

  function isShaPlaceholder(value) {
    const normalized = normalizeLanguage(value);
    return !normalized || normalized === "..." || normalized === "콘텐츠 해시" || normalized === "content hash";
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

  function safeParseJsonObject(text) {
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

  function createBridgeKey(metadata) {
    const patchId = String(metadata && metadata.patch_id ? metadata.patch_id : "").trim();
    const sha256 = String(metadata && metadata.sha256 ? metadata.sha256 : "").trim().toLowerCase();
    return `${patchId}:${sha256}`;
  }

  function validateBridgePayload(payload) {
    const requiredFields = ["patch_id", "project_root", "target", "language", "content", "sha256"];
    for (const field of requiredFields) {
      if (typeof payload[field] !== "string" || !payload[field].trim()) {
        return { ok: false, error: `missing or invalid ${field}` };
      }
    }
    if (payload.type && normalizeLanguage(payload.type) !== "propose_patch") {
      return { ok: false, error: "unsupported bridge message type" };
    }
    return { ok: true };
  }

  function pruneTimedEntries(map, ttlMs, maxEntries, now = Date.now()) {
    if (!map || typeof map.delete !== "function" || typeof map.entries !== "function") {
      return 0;
    }
    let removed = 0;
    for (const [key, value] of map.entries()) {
      const timestamp = typeof value === "number" ? value : value && typeof value.lastSeen === "number" ? value.lastSeen : 0;
      if (ttlMs > 0 && timestamp >= 0 && now - timestamp > ttlMs) {
        map.delete(key);
        removed += 1;
      }
    }
    if (maxEntries > 0 && map.size > maxEntries) {
      const entries = Array.from(map.entries()).sort((left, right) => {
        const leftTime = typeof left[1] === "number" ? left[1] : left[1] && typeof left[1].lastSeen === "number" ? left[1].lastSeen : 0;
        const rightTime = typeof right[1] === "number" ? right[1] : right[1] && typeof right[1].lastSeen === "number" ? right[1].lastSeen : 0;
        return leftTime - rightTime;
      });
      while (map.size > maxEntries && entries.length) {
        const [key] = entries.shift();
        if (map.delete(key)) {
          removed += 1;
        }
      }
    }
    return removed;
  }

  return {
    createBridgeKey,
    findMessageContainer,
    getCodeLanguage,
    getCodeText,
    getMessageRole,
    isAposPatchBlock,
    isAssistantAuthored,
    isAssistantRole,
    isEditableSurface,
    isShaPlaceholder,
    isUserAuthored,
    isUserRole,
    normalizeLanguage,
    normalizeNewlines,
    pruneTimedEntries,
    sameMessageScope,
    safeParseJsonObject,
    shortHashSync,
    validateBridgePayload,
  };
});
