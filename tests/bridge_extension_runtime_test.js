const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { webcrypto } = require("node:crypto");

const REPO_ROOT = path.resolve(__dirname, "..");
const BRIDGE_UTILS_PATH = path.join(REPO_ROOT, "extension", "bridgeUtils.js");
const CONTENT_SCRIPT_PATH = path.join(REPO_ROOT, "extension", "contentScript.js");

class FakeElement {
  constructor(tagName, attributes = {}, textContent = "", rect = null) {
    this.tagName = String(tagName || "div").toUpperCase();
    this.attributes = { ...attributes };
    this.textContent = textContent;
    this.parentElement = null;
    this.children = [];
    this.rect = rect || { width: 120, height: 24, bottom: 24 };
    this.focused = false;
    this.lastEventType = null;
  }

  appendChild(child) {
    child.parentElement = this;
    this.children.push(child);
    return child;
  }

  getAttribute(name) {
    return Object.prototype.hasOwnProperty.call(this.attributes, name) ? this.attributes[name] : null;
  }

  setAttribute(name, value) {
    this.attributes[name] = String(value);
  }

  getBoundingClientRect() {
    return this.rect;
  }

  focus() {
    this.focused = true;
  }

  dispatchEvent(event) {
    this.lastEventType = event.type;
    return true;
  }

  closest(selector) {
    const selectors = String(selector || "").split(",").map((value) => value.trim()).filter(Boolean);
    let current = this;
    while (current) {
      if (selectors.some((item) => matchesSelector(current, item))) {
        return current;
      }
      current = current.parentElement;
    }
    return null;
  }
}

function matchesSelector(element, selector) {
  const tagName = element.tagName.toLowerCase();
  if (selector === "textarea") {
    return tagName === "textarea";
  }
  if (selector === "input") {
    return tagName === "input";
  }
  if (selector === "form") {
    return tagName === "form";
  }
  if (selector === "[data-message-author-role]") {
    return element.getAttribute("data-message-author-role") !== null;
  }
  if (selector === "[data-author-role]") {
    return element.getAttribute("data-author-role") !== null;
  }
  if (selector === "[data-utterance-author-role]") {
    return element.getAttribute("data-utterance-author-role") !== null;
  }
  if (selector === "[data-role]") {
    return element.getAttribute("data-role") !== null;
  }
  if (selector === "[contenteditable='true']") {
    return element.getAttribute("contenteditable") === "true";
  }
  if (selector === "[contenteditable='plaintext-only']") {
    return element.getAttribute("contenteditable") === "plaintext-only";
  }
  if (selector === "[role='textbox']") {
    return element.getAttribute("role") === "textbox";
  }
  if (selector === "[data-testid='prompt-textarea']") {
    return element.getAttribute("data-testid") === "prompt-textarea";
  }
  if (selector === "[data-testid*='composer']") {
    return String(element.getAttribute("data-testid") || "").includes("composer");
  }
  if (selector === "[data-testid*='prompt']") {
    return String(element.getAttribute("data-testid") || "").includes("prompt");
  }
  if (selector.startsWith("[data-language")) {
    return element.getAttribute("data-language") !== null || element.getAttribute("data-lang") !== null;
  }
  if (selector === "code[class*='language-']") {
    return tagName === "code" && /(?:^|\s)(?:language|lang)-/.test(String(element.getAttribute("class") || ""));
  }
  if (selector === "pre code") {
    return tagName === "code";
  }
  return false;
}

class FakeDocument {
  constructor(codeBlocks, promptInputs = []) {
    this.readyState = "complete";
    this._codeBlocks = codeBlocks;
    this._promptInputs = promptInputs;
    this.documentElement = new FakeElement("html");
    this.body = new FakeElement("body");
  }

  querySelectorAll(selector) {
    const normalized = String(selector || "");
    if (normalized.includes("pre code") || normalized.includes("code[data-language]") || normalized.includes("code[data-lang]") || normalized.includes("code[class*='language-']")) {
      return [...this._codeBlocks];
    }
    if (normalized.includes("textarea") || normalized.includes("prompt-textarea") || normalized.includes("contenteditable") || normalized.includes("role='textbox'")) {
      return [...this._promptInputs];
    }
    return [];
  }

  querySelector(selector) {
    return this.querySelectorAll(selector)[0] || null;
  }

  addEventListener() {}
}

class FakeMutationObserver {
  observe() {}
  disconnect() {}
}

class FakeWebSocket {
  constructor(url) {
    this.url = url;
    this.readyState = FakeWebSocket.OPEN;
    this.sent = [];
    this.listeners = new Map();
    FakeWebSocket.instances.push(this);
  }

  addEventListener(type, callback) {
    if (!this.listeners.has(type)) {
      this.listeners.set(type, []);
    }
    this.listeners.get(type).push(callback);
  }

  send(message) {
    this.sent.push(message);
  }

  emit(type, event) {
    for (const callback of this.listeners.get(type) || []) {
      callback(event || {});
    }
  }
}

FakeWebSocket.instances = [];
FakeWebSocket.OPEN = 1;
FakeWebSocket.CONNECTING = 0;
FakeWebSocket.CLOSED = 3;

function makeContainer(role) {
  return new FakeElement("div", { "data-message-author-role": role });
}

function makeCodeBlock(language, text, container) {
  const parent = container || makeContainer("assistant");
  const code = new FakeElement("code", { class: `language-${language}` }, text);
  parent.appendChild(code);
  return code;
}

function makePairedBlocks(role, metadataLanguage, metadataText, sourceLanguage, sourceText) {
  const container = makeContainer(role);
  return [
    makeCodeBlock(metadataLanguage, metadataText, container),
    makeCodeBlock(sourceLanguage, sourceText, container),
  ];
}

function loadRuntime({ codeBlocks, promptInputs = [] }) {
  FakeWebSocket.instances = [];
  const document = new FakeDocument(codeBlocks, promptInputs);
  const context = {
    console,
    setTimeout: () => 0,
    clearTimeout: () => {},
    crypto: webcrypto,
    TextEncoder,
    MutationObserver: FakeMutationObserver,
    WebSocket: FakeWebSocket,
    Element: FakeElement,
    HTMLTextAreaElement: FakeElement,
    InputEvent: class InputEvent {
      constructor(type, options) {
        this.type = type;
        this.options = options || {};
      }
    },
    Event: class Event {
      constructor(type, options) {
        this.type = type;
        this.options = options || {};
      }
    },
    document,
    window: null,
  };
  context.window = context;
  context.globalThis = context;
  context.getComputedStyle = () => ({ display: "block", visibility: "visible" });
  context.window.getComputedStyle = context.getComputedStyle;
  context.window.clearTimeout = context.clearTimeout;
  context.window.setTimeout = context.setTimeout;
  vm.createContext(context);
  vm.runInContext(fs.readFileSync(BRIDGE_UTILS_PATH, "utf8"), context, { filename: "bridgeUtils.js" });
  vm.runInContext(fs.readFileSync(CONTENT_SCRIPT_PATH, "utf8"), context, { filename: "contentScript.js" });
  return { context, socket: FakeWebSocket.instances[0] };
}

async function drainMicrotasks() {
  await new Promise((resolve) => setImmediate(resolve));
  await Promise.resolve();
}

async function testAposPatchFlow() {
  const metadata = '{"patch_id":"patch-1","project_root":"/tmp/project","target":"workspace/demo.py","language":"python","sha256":"..."}';
  const source = "print('hello world')\n";
  const [metadataBlock, sourceBlock] = makePairedBlocks("assistant", "apos-patch", metadata, "python", source);
  const { context, socket } = loadRuntime({
    codeBlocks: [metadataBlock, sourceBlock],
  });

  context.window.__APOS_V32__.scan();
  await drainMicrotasks();
  assert.equal(socket.sent.length, 1);

  context.window.__APOS_V32__.scan();
  await drainMicrotasks();
  assert.equal(socket.sent.length, 1);

  socket.emit("message", {
    data: JSON.stringify({
      type: "validation_passed",
      patch_id: "patch-1",
      target: "workspace/demo.py",
      item_id: "item-1",
    }),
  });

  assert.equal(context.window.__APOS_V32__.state.status.phase, "pending_registered");
  assert.equal(context.window.__APOS_V32__.state.pendingByPatchId.has("patch-1"), true);
}

async function testAssistantOnlyDetection() {
  const metadata = '{"patch_id":"patch-2","project_root":"/tmp/project","target":"workspace/ignored.py","language":"python","sha256":"..."}';
  const source = "print('ignored')\n";
  const [metadataBlock, sourceBlock] = makePairedBlocks("user", "apos-patch", metadata, "python", source);
  const { context, socket } = loadRuntime({
    codeBlocks: [metadataBlock, sourceBlock],
  });

  context.window.__APOS_V32__.scan();
  await drainMicrotasks();
  assert.equal(socket.sent.length, 0);
  assert.equal(context.window.__APOS_V32__.state.status.phase === "sent", false);
}

async function testNonAposCodeIgnored() {
  const container = makeContainer("assistant");
  const { context, socket } = loadRuntime({
    codeBlocks: [makeCodeBlock("javascript", "console.log('no-op');\n", container)],
  });

  context.window.__APOS_V32__.scan();
  await drainMicrotasks();
  assert.equal(socket.sent.length, 0);
}

async function testRetryLimitAndCleanup() {
  const invalidMetadata = '{"patch_id":"patch-3","project_root":"/tmp/project","target":"workspace/bad.py","language":"python","sha256":"..."';
  const source = "print('bad json')\n";
  const [metadataBlock, sourceBlock] = makePairedBlocks("assistant", "apos-patch", invalidMetadata, "python", source);
  const { context, socket } = loadRuntime({
    codeBlocks: [metadataBlock, sourceBlock],
  });

  context.window.__APOS_V32__.scan();
  await drainMicrotasks();
  context.window.__APOS_V32__.scan();
  await drainMicrotasks();
  context.window.__APOS_V32__.scan();
  await drainMicrotasks();

  assert.equal(socket.sent.length, 0);
  const retryKey = `client:metadata-json:${context.__APOS_BRIDGE__.shortHashSync(invalidMetadata.trim())}`;
  assert.equal(context.window.__APOS_V32__.state.retryCounts.get(retryKey).count, 2);
  assert.equal(context.window.__APOS_V32__.state.status.phase, "retry_exhausted");

  const entries = new Map([
    ["old", { lastSeen: 0 }],
    ["new", { lastSeen: Date.now() }],
  ]);
  const removed = context.__APOS_BRIDGE__.pruneTimedEntries(entries, 1000, 10, Date.now() + 500);
  assert.equal(removed, 1);
  assert.equal(entries.has("old"), false);
  assert.equal(entries.has("new"), true);
}

async function main() {
  await testAposPatchFlow();
  await testAssistantOnlyDetection();
  await testNonAposCodeIgnored();
  await testRetryLimitAndCleanup();
  process.stdout.write("bridge extension runtime tests passed\n");
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
