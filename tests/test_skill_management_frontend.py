"""Asynchronous client identity guards independent of browser timing."""
from pathlib import Path
import subprocess
import json
import pytest

from tests.test_skill_management_api import service, _convert, _preview, _commit


def test_management_root_change_and_out_of_order_loads():
    root = Path(__file__).resolve().parents[1]
    script = r'''
const assert = require("node:assert/strict");
global.window = {Code: {features: {}}};
require("./src/features/skills-memory.js");
const pending = [];
const state = {};
const feature = window.Code.features.skillsMemory.createSkillsMemoryFeature({
  state, document: {getElementById: () => null}, storage: {},
  apiJson: (url) => new Promise((resolve, reject) => pending.push({url, resolve, reject})),
});
const snapshot = (id) => ({protocol: "skill-management/v1", mode: "managed-v2", serverInstanceId: "server",
  registry: {dataRootId: id, generation: 1}, admissionEnabled: true,
  installations: [{installationId: "install", revisionId: "revision", displayName: id, selected: true, enabled: true}],
});
(async () => {
  const first = feature.loadSkills();
  const second = feature.loadSkills();
  pending[1].resolve(snapshot("second")); await second;
  pending[0].resolve(snapshot("first")); await first;
  assert.equal(state.skills[0].name, "second");
  const detail = feature.ensureSkillBody(state.skills[0]);
  const third = feature.loadSkills();
  pending[3].resolve(snapshot("third")); await third;
  pending[2].resolve({dataRootId: "second", revisionId: "revision", body: "late body"});
  await assert.rejects(detail, /skillManagementChanged/);
  assert.equal(state.skills[0].name, "third");
  assert.equal(state.skills[0].body, undefined);
  const unavailable = feature.loadSkills();
  pending[4].reject(new Error("unavailable")); await unavailable;
  assert.equal(state.skillManagement.mode, "unavailable");
  assert.deepEqual(state.skills, []);
  assert.ok(pending.every(item => !item.url.startsWith("/api/skills")));
})();
'''
    subprocess.run(["node", "-e", script], cwd=root, check=True, capture_output=True, text=True, timeout=15)


TOGGLE_SCRIPT = r'''
const assert = require("node:assert/strict"), crypto = require("node:crypto");
const scenario = process.argv[1], real = process.argv[2] ? JSON.parse(process.argv[2]) : null;
global.window = {Code: {features: {}}, crypto: {subtle: crypto.webcrypto.subtle,
  randomUUID: () => real?.key || crypto.randomUUID()}, clearTimeout, confirm: () => true};
require("./src/features/skills-memory.js");
const nodes = new Map(); let visible = true;
const node = (id) => {
  if (!nodes.has(id)) nodes.set(id, {innerHTML: "", dataset: {}, value: "", handlers: {}, attrs: {},
    classList: {toggle() {}, add() {}, remove() {}}, focus() {},
    setAttribute(key, value) {this.attrs[key] = value;},
    addEventListener(name, handler) {this.handlers[name] = handler;},
    querySelector(selector) {return node(id + selector);}, querySelectorAll() {return [];},
    closest() {return node("layout");}});
  return nodes.get(id);
};
const digest = value => "sha256:" + crypto.createHash("sha256").update(value).digest("hex");
const snapshot = (generation = 7, enabled = true, root = "root-a", instance = "server-a") => ({
  protocol: "skill-management/v1", mode: "managed-v2", serverInstanceId: instance,
  registry: {schema: "code-skill-install-registry/v2", dataRootId: root, generation,
    registryHash: digest(root + generation)}, admissionEnabled: true, transactionState: "committed",
  capabilities: {write: true, read: true}, bindings: [],
  installations: ["alpha", "beta"].map(name => ({installationId: name, revisionId: "revision",
    displayName: name, description: "Description", selected: true, enabled: name === "alpha" ? enabled : true,
    uninstalled: false, retainedRevisionIds: ["revision"]})),
});
let authoritative = real?.initial || snapshot(), holdGet = false, heldGet, failGet = false;
const cards = authoritative.installations.map(item => node("card-" + item.installationId));
const toggles = authoritative.installations.map(item => node("toggle-" + item.installationId));
cards.forEach((card, i) => {card.dataset.installation = toggles[i].dataset.toggleInstallation = authoritative.installations[i].installationId;});
node("settingsSkillsSidebar").querySelectorAll = selector =>
  selector === "[data-installation]" ? cards : selector === "[data-toggle-installation]" ? toggles : [];
const state = {}, errors = [], ops = [], previews = [], commits = new Map(); let gets = 0, previewResolve, previewReject;
const feature = window.Code.features.skillsMemory.createSkillsMemoryFeature({
  state, document: {getElementById: id => visible ? node(id) : null}, storage: {}, showToast: message => errors.push(message),
  apiJson: (url, options) => {
    if (url.includes("/installations/")) {
      const id = url.split("/installations/")[1].split("?")[0], item = authoritative.installations.find(item => item.installationId === id);
      return Promise.resolve({dataRootId: authoritative.registry.dataRootId, revisionId: item.revisionId,
        description: "Description", document: "original", dependency: {capabilities: []}});
    }
    if (url.includes("/dependencies?")) return Promise.resolve({operation: null});
    if (options?.method === "POST") {
      const payload = JSON.parse(options.body);
      if (url.endsWith("/preview")) {
        previews.push(payload);
        return new Promise((resolve, reject) => {previewResolve = () => resolve(real?.preview || {base: payload.base,
          confirmationRequired: scenario === "confirm-cancel",
          request: {kind: payload.kind, installationId: payload.installationId, enabled: payload.enabled}}); previewReject = reject;});
      }
      return new Promise((resolve, reject) => ops.push({payload, resolve, reject}));
    }
    gets++;
    if (holdGet) {holdGet = false; return new Promise(resolve => {heldGet = resolve;});}
    if (failGet) return Promise.reject(new Error("read unavailable"));
    return Promise.resolve(structuredClone(authoritative));
  },
});
const settle = () => new Promise(resolve => setImmediate(resolve));
function commit(op) {
  if (commits.has(op.payload.operationKey)) return structuredClone(commits.get(op.payload.operationKey));
  const request = op.payload.request;
  authoritative = real?.result.snapshot || snapshot(8, false);
  const reply = real?.result || {protocol: "skill-management/v1", snapshot: structuredClone(authoritative), receipt: {
    kind: request.kind, operationId: "op2_" + crypto.createHash("sha256").update(JSON.stringify([
      "management-v2", op.payload.base.dataRootId, digest(op.payload.operationKey)])).digest("hex"),
    requestHash: digest(JSON.stringify({enabled: request.enabled, installationId: request.installationId, kind: request.kind})),
    appliedGeneration: 8, result: {installationId: request.installationId, revisionId: "revision"},
  }};
  commits.set(op.payload.operationKey, structuredClone(reply)); return structuredClone(reply);
}
(async () => {
  await feature.loadSkills(); feature.renderSkillsInSettings(node("container"));
  if (scenario === "confirm-cancel") {
    window.confirm = () => false; node("managedConvert").handlers.click(); previewResolve(); await settle();
    assert.equal(previews.length, 1); assert.equal(ops.length, 0); assert.equal(state.managedSkills[0].enabled, true); return;
  }
  if (["detail", "navigate", "leave"].includes(scenario)) {cards[0].handlers.click(); await settle();}
  let beforeGet;
  if (scenario === "earlier-get") {holdGet = true; beforeGet = feature.loadSkills();}
  const button = ["detail", "navigate", "leave"].includes(scenario) ? node("managedToggle") : toggles[0];
  const pending = button.handlers.click();
  assert.equal(button.disabled, true);
  assert.equal(button.attrs["aria-busy"], "true");
  assert.equal(button === toggles[0] ? button.querySelector("[data-toggle-label]").textContent : button.textContent, "skillManagementApplying");
  assert.equal(state.managedSkills[0].enabled, true); // before preview, no optimistic state
  const duplicate = button.handlers.click();
  assert.equal(previews.length, 1);
  if (scenario === "other-toggle") {
    await toggles[1].handlers.click(); assert.equal(previews.length, 1);
    assert.deepEqual(errors, ["skillManagementPending"]);
  }
  if (scenario === "preview-root-change") {
    authoritative = snapshot(1, true, "root-b"); await feature.loadSkills(); previewResolve();
    await Promise.all([pending, duplicate]); assert.equal(ops.length, 0);
    assert.equal(state.skillManagement.registry.dataRootId, "root-b"); return;
  }
  if (scenario === "preview-failure") {
    previewReject(new Error("preview failed")); await Promise.all([pending, duplicate]);
    assert.equal(ops.length, 0); assert.equal(state.managedSkills[0].enabled, true);
    assert.equal(button.attrs["aria-busy"], "false"); return;
  }
  previewResolve(); await settle(); assert.equal(ops.length, 1);
  let reply = commit(ops[0]);
  if (scenario === "response-lost") {
    ops[0].reject(new Error("response lost")); await Promise.all([pending, duplicate]);
    assert.equal(state.managedSkills[0].enabled, true);
    assert.match(node("settingsManagedActions").innerHTML, /managedRetry/);
    node("managedRetry").handlers.click(); node("managedRetry").handlers.click(); await settle();
    assert.equal(previews.length, 1); assert.equal(ops.length, 2);
    assert.deepEqual(ops[1].payload, ops[0].payload);
    ops[1].resolve(commit(ops[1]));
    for (let i = 0; i < 20 && state.managedSkills[0].enabled; i++) await settle();
    assert.equal(state.managedSkills[0].enabled, false); assert.equal(commits.size, 1); assert.equal(gets, 1); return;
  }
  if (scenario === "cas-failure") {
    ops[0].reject(new Error("registry_cas_conflict")); await Promise.all([pending, duplicate]);
    assert.equal(state.managedSkills[0].enabled, true); assert.equal(gets, 1);
    assert.match(node("settingsManagedActions").innerHTML, /managedRetry/); return;
  }
  if (scenario === "navigate") {cards[1].handlers.click(); await settle();}
  if (scenario === "leave") visible = false;
  if (scenario === "newer-generation") {authoritative = snapshot(9, true); await feature.loadSkills();}
  if (scenario === "later-snapshot") {authoritative = snapshot(9, true); reply.snapshot = structuredClone(authoritative);}
  if (["root-change", "instance-change"].includes(scenario)) {
    authoritative = snapshot(1, true, scenario === "root-change" ? "root-b" : "root-a", scenario === "instance-change" ? "server-b" : "server-a");
    await feature.loadSkills(); ops[0].resolve(reply); await Promise.all([pending, duplicate]);
    assert.deepEqual(state.skillManagement.registry, authoritative.registry);
    assert.equal(state.skillManagement.serverInstanceId, authoritative.serverInstanceId);
    assert.equal(state.managedSkills[0].enabled, true); assert.equal(gets, 2); return;
  }
  if (scenario === "later-get") {holdGet = true; beforeGet = feature.loadSkills();}
  if (scenario === "missing-snapshot") delete reply.snapshot;
  if (scenario === "wrong-protocol") reply.protocol = "future";
  if (scenario === "wrong-root") reply.snapshot.registry.dataRootId = "other";
  if (scenario === "wrong-instance") reply.snapshot.serverInstanceId = "other";
  if (scenario === "wrong-receipt") reply.receipt.operationId = "op2_" + "0".repeat(64);
  if (scenario === "wrong-request") reply.receipt.requestHash = "sha256:" + "0".repeat(64);
  if (scenario === "wrong-state") reply.snapshot.installations[0].enabled = true;
  if (scenario === "malformed-list") reply.snapshot.installations = null;
  if (scenario === "read-failure") {delete reply.snapshot; failGet = true;}
  ops[0].resolve(reply); await Promise.all([pending, duplicate]);
  if (beforeGet) {heldGet(snapshot()); await beforeGet;}
  if (scenario === "read-failure") {
    assert.equal(state.skillManagement.mode, "unavailable"); assert.deepEqual(state.skills, []);
    assert.deepEqual(errors, ["skillManagementRefreshFailed"]);
    assert.doesNotMatch(node("settingsManagedActions").innerHTML, /managedRetry/); return;
  }
  assert.equal(state.managedSkills[0].enabled, ["newer-generation", "later-snapshot"].includes(scenario));
  assert.equal(state.managedSkills[0].body, undefined);
  if (scenario === "navigate") assert.equal(node("settingsSkillsDetail").dataset.renderedInstallation, "beta");
  if (scenario === "detail") {await settle(); assert.equal(node("managedToggle").textContent, "skillEnableAction");}
  const fast = ["success", "detail", "navigate", "leave", "real", "other-toggle", "later-snapshot"].includes(scenario);
  assert.equal(gets, fast ? 1 : scenario === "newer-generation" || scenario === "later-get" ? 3 : 2);
  assert.equal(ops.length, 1); assert.equal(commits.size, 1);
  assert.equal(toggles[0].attrs["aria-busy"], scenario === "leave" ? "true" : "false");
})();
'''


@pytest.mark.parametrize("scenario", [
    "success", "detail", "navigate", "leave", "earlier-get", "later-get", "newer-generation",
    "root-change", "instance-change", "missing-snapshot", "wrong-protocol", "wrong-root", "wrong-instance",
    "wrong-receipt", "wrong-request", "wrong-state", "malformed-list", "read-failure",
    "response-lost", "cas-failure", "preview-failure",
    "confirm-cancel", "other-toggle", "preview-root-change", "later-snapshot",
])
def test_toggle_feedback_snapshot_and_retry_boundaries(scenario):
    subprocess.run(["node", "-e", TOGGLE_SCRIPT, scenario], cwd=Path(__file__).resolve().parents[1],
                   check=True, capture_output=True, text=True, timeout=15)


def test_toggle_reuses_real_management_service_response(service, tmp_path):
    _convert(service)
    initial = service.snapshot()
    item = initial["installations"][0]
    preview = _preview(service, "set-enabled", installationId=item["installationId"], enabled=False)
    result = _commit(service, preview, "frontend-toggle")
    payload = {"initial": initial, "preview": preview, "result": result, "key": "frontend-toggle"}
    (tmp_path / "frontend-toggle.json").write_text(json.dumps(payload), encoding="utf-8")
    subprocess.run(["node", "-e", TOGGLE_SCRIPT, "real", json.dumps(payload)],
                   cwd=Path(__file__).resolve().parents[1], check=True, capture_output=True, text=True, timeout=15)


def test_settings_description_cache_is_scoped_to_root_and_revision():
    root = Path(__file__).resolve().parents[1]
    script = r'''
const assert = require("node:assert/strict");
global.window = {Code: {features: {}}};
require("./src/features/skills-memory.js");
let rootId = "root-a", revisionId = "revision-a", serverInstanceId = "server-a";
const state = {};
const feature = window.Code.features.skillsMemory.createSkillsMemoryFeature({
  state, document: {getElementById: () => null}, storage: {},
  apiJson: async (url) => url.includes("/installations/")
    ? {dataRootId: rootId, revisionId, description: "Create presentations", body: "instructions"}
    : {protocol: "skill-management/v1", mode: "managed-v2", serverInstanceId,
      registry: {dataRootId: rootId}, admissionEnabled: true,
      installations: [{installationId: "install", revisionId, displayName: "deck", selected: true, enabled: true}]},
});
(async () => {
  await feature.loadSkills();
  await feature.ensureSkillBody(state.skills[0]);
  await feature.loadSkills();
  assert.equal(state.managedSkills[0].description, "Create presentations");
  assert.equal(state.managedSkills[0].body, undefined);
  assert.equal(window.Code.features.skillsMemory.filterSettingsSkills(state.managedSkills, "presentations").length, 1);
  revisionId = "revision-b";
  await feature.loadSkills();
  assert.equal(state.managedSkills[0].description, "");
  await feature.ensureSkillBody(state.skills[0]);
  rootId = "root-b";
  await feature.loadSkills();
  assert.equal(state.managedSkills[0].description, "");
  await feature.ensureSkillBody(state.skills[0]);
  serverInstanceId = "server-b";
  await feature.loadSkills();
  assert.equal(state.managedSkills[0].description, "");
})();
'''
    subprocess.run(["node", "-e", script], cwd=root, check=True, capture_output=True, text=True, timeout=15)


def test_overview_and_detail_share_reads_without_caching_enabled_state():
    root = Path(__file__).resolve().parents[1]
    script = r'''
const assert = require("node:assert/strict");
global.window = {Code: {features: {}}, crypto: require("node:crypto").webcrypto, clearTimeout};
require("./src/features/skills-memory.js");
const nodes = new Map();
const node = (id) => {
  if (!nodes.has(id)) nodes.set(id, {innerHTML: "", dataset: {}, value: "", handlers: {},
    classList: {toggle() {}, add() {}, remove() {}}, setAttribute() {}, focus() {},
    addEventListener(name, handler) {this.handlers[name] = handler;},
    querySelector() {return node("description");}, querySelectorAll() {return [];},
    closest() {return node("layout");}});
  return nodes.get(id);
};
const card = node("card"), toggle = node("toggle");
card.dataset.installation = toggle.dataset.toggleInstallation = "install";
node("settingsSkillsSidebar").querySelectorAll = (selector) =>
  selector === "[data-installation]" ? [card] : selector === "[data-toggle-installation]" ? [toggle] : [];
let enabled = true, reads = 0, resolveDetail, rejectOperation = false, projectedDescription = false;
const errors = [], posts = [];
const snapshot = () => ({protocol: "skill-management/v1", mode: "managed-v2", serverInstanceId: "server",
  registry: {dataRootId: "root", generation: enabled ? 1 : 2}, admissionEnabled: true, capabilities: {write: true},
  installations: [{installationId: "install", revisionId: projectedDescription ? "revision-b" : "revision",
    displayName: "deck", selected: true, enabled,
    ...(projectedDescription ? {description: "Projected description"} : {})}],
});
const state = {};
const feature = window.Code.features.skillsMemory.createSkillsMemoryFeature({
  state, document: {getElementById: node}, storage: {}, showToast: (message) => errors.push(message),
  apiJson: async (url, options) => {
    if (url.includes("/installations/")) {reads++; return new Promise(resolve => {resolveDetail = resolve;});}
    if (url.includes("/dependencies?")) return {operation: null};
    if (options?.method === "POST") {
      const payload = JSON.parse(options.body); posts.push({url, payload});
      if (url.endsWith("/preview")) return {base: payload.base, request: {kind: payload.kind,
        installationId: payload.installationId, enabled: payload.enabled}};
      if (rejectOperation) throw new Error("registry_cas_conflict");
      enabled = payload.request.enabled;
      return {receipt: {result: {installationId: "install"}}};
    }
    return snapshot();
  },
});
const settle = () => new Promise(resolve => setImmediate(resolve));
(async () => {
  await feature.loadSkills();
  feature.renderSkillsInSettings(node("container"));
  assert.match(node("settingsSkillsSidebar").innerHTML, /role="switch"/);
  assert.equal(node("settingsSkillsOverviewBtn").hidden, true);
  assert.match(node("settingsManagedActions").innerHTML, /managedImport/);
  assert.equal(reads, 1);
  card.handlers.click(); // Enter while the description request is still in flight.
  assert.equal(node("settingsSkillsOverviewBtn").hidden, false);
  assert.equal(node("settingsManagedActions").hidden, true);
  assert.doesNotMatch(node("settingsManagedActions").innerHTML, /managedImport|managedPreferences/);
  assert.equal(reads, 1);
  resolveDetail({dataRootId: "root", revisionId: "revision", enabled: true,
    description: "Create presentations", document: "original", dependency: {capabilities: []}});
  await settle();
  assert.match(node("settingsSkillsDetail").innerHTML, /skillManagementNoDependencies/);
  node("settingsSkillsOverviewBtn").handlers.click();
  await toggle.handlers.click();
  assert.equal(state.managedSkills[0].enabled, false);
  card.handlers.click(); await settle();
  assert.equal(reads, 1); // A same-revision refresh reuses only immutable display content.
  assert.match(node("settingsSkillsDetail").innerHTML, /id="managedToggle"[^>]*>skillEnableAction/);
  assert.equal(state.managedSkills[0].body, undefined); // UI prefetch does not load runtime instructions.
  assert.equal(posts.filter(item => item.url.endsWith("/operations")).length, 1);
  node("settingsSkillsOverviewBtn").handlers.click();
  rejectOperation = true;
  await toggle.handlers.click();
  assert.equal(state.managedSkills[0].enabled, false); // Failed writes do not optimistically flip the switch.
  assert.match(node("settingsManagedActions").innerHTML, /managedRetry/);
  assert.deepEqual(errors, ["skillManagementConflict"]);
  projectedDescription = true;
  await feature.loadSkills();
  feature.renderSkillsInSettings(node("container"));
  await settle();
  assert.equal(reads, 1); // New snapshots do not trigger per-card detail reads.
  assert.match(node("settingsSkillsSidebar").innerHTML, /Projected description/);
  assert.equal(state.managedSkills[0]._settingsDetail, undefined);
})();
'''
    subprocess.run(["node", "-e", script], cwd=root, check=True, capture_output=True, text=True, timeout=15)
