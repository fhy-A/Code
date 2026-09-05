"""Asynchronous client identity guards independent of browser timing."""
from pathlib import Path
import subprocess


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
