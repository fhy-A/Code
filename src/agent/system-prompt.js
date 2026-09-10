(function initializeCodeSystemPrompt(global) {
  "use strict";

  const agent = global.Code && global.Code.agent;
  if (!agent) throw new Error("Code agent namespace must load before system prompt");

  const SYSTEM_PROMPT_SEGMENTS = Object.freeze([
    Object.freeze({ name: "security", input: "securityLayer", condition: "always", refresh: "static" }),
    Object.freeze({ name: "behavior", input: "behaviorInstruction", condition: "always", refresh: "task" }),
    Object.freeze({ name: "response-style", input: "responseStyleInstruction", condition: "explicit-preference", refresh: "task" }),
    Object.freeze({ name: "environment", input: "environmentInstruction", condition: "always", refresh: "task" }),
    Object.freeze({ name: "project-folders", input: "projectFoldersInstruction", condition: "multiple-roots", refresh: "task" }),
    Object.freeze({ name: "external-files", input: "externalFilesInstruction", condition: "always", refresh: "static" }),
    Object.freeze({ name: "delegation", input: "delegationInstruction", condition: "task-tool-enabled", refresh: "task" }),
    Object.freeze({ name: "response-language", input: "responseLanguageInstruction", condition: "non-chinese-user", refresh: "task" }),
    Object.freeze({ name: "project-context", input: "projectContextInstruction", condition: "project-context-found", refresh: "task" }),
    Object.freeze({ name: "memory", input: "memoryInstruction", condition: "memory-found", refresh: "task" }),
    Object.freeze({ name: "skill", input: "skillInstruction", condition: "skill-selected-or-matched", refresh: "task" }),
    Object.freeze({ name: "permission", input: "permissionInstruction", condition: "always", refresh: "task" }),
  ]);

  function normalizedText(value) {
    return typeof value === "string" ? value : String(value || "");
  }

  function buildSystemPromptSegments(values = {}) {
    const segments = [];
    for (const definition of SYSTEM_PROMPT_SEGMENTS) {
      const content = normalizedText(values[definition.input]);
      if (!content) continue;
      segments.push(Object.freeze({
        name: definition.name,
        condition: definition.condition,
        refresh: definition.refresh,
        content,
      }));
    }
    return Object.freeze(segments);
  }

  function createSystemPromptSnapshot(values = {}, metadata = {}) {
    const segments = buildSystemPromptSegments(values);
    const activeSkillNames = Array.isArray(metadata.activeSkillNames)
      ? metadata.activeSkillNames.map((name) => normalizedText(name)).filter(Boolean)
      : [];
    const activeSkillName = normalizedText(metadata.activeSkillName);
    return Object.freeze({
      prompt: segments.map((segment) => segment.content).join("\n\n"),
      segmentNames: Object.freeze(segments.map((segment) => segment.name)),
      activeSkillNames: Object.freeze(activeSkillNames),
      activeSkillName: activeSkillNames.length === 1 && activeSkillNames[0] === activeSkillName
        ? activeSkillName
        : "",
      capturedAt: normalizedText(metadata.capturedAt),
      timeZone: normalizedText(metadata.timeZone),
    });
  }

  function formatUtcOffset(offsetMinutes) {
    const numeric = Number(offsetMinutes);
    const safeMinutes = Number.isFinite(numeric) ? Math.trunc(numeric) : 0;
    const sign = safeMinutes >= 0 ? "+" : "-";
    const absolute = Math.abs(safeMinutes);
    const hours = String(Math.floor(absolute / 60)).padStart(2, "0");
    const minutes = String(absolute % 60).padStart(2, "0");
    return `UTC${sign}${hours}:${minutes}`;
  }

  function resolveLocalTimeZoneName(intl = Intl) {
    try {
      return String(intl?.DateTimeFormat?.().resolvedOptions?.().timeZone || "").trim();
    } catch {
      return "";
    }
  }

  function formatSystemPromptEnvironment({
    capturedAt,
    timeZoneName = "",
    utcOffsetMinutes,
    cwd = "",
    appVersion = "",
  } = {}) {
    const now = capturedAt instanceof Date
      ? new Date(capturedAt.getTime())
      : new Date(capturedAt);
    if (!Number.isFinite(now.getTime())) {
      throw new TypeError("capturedAt must be a valid date");
    }
    const dateStr = now.toLocaleDateString("zh-CN", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      weekday: "long",
    });
    const timeStr = now.toLocaleTimeString("zh-CN", {
      hour: "2-digit",
      minute: "2-digit",
    });
    const resolvedOffset = Number.isFinite(Number(utcOffsetMinutes))
      ? Number(utcOffsetMinutes)
      : -now.getTimezoneOffset();
    const zoneName = String(timeZoneName || "").trim() || "本地时区";
    const zoneLabel = `${zoneName} ${formatUtcOffset(resolvedOffset)}`;
    return {
      capturedAt: now.toISOString(),
      timeZone: zoneLabel,
      instruction: `当前时间：${dateStr} ${timeStr}（${zoneLabel}） · 当前工作目录：${String(cwd || "").trim() || "未设置"} · v${String(appVersion || "").trim() || "unknown"}`,
    };
  }

  function defineHidden(owner, name, value) {
    Object.defineProperty(owner, name, {
      configurable: true,
      enumerable: false,
      writable: true,
      value,
    });
  }

  async function getOrCreateSystemPromptSnapshot(owner, factory) {
    if (!owner || typeof owner !== "object") {
      return factory();
    }
    if (owner._systemPromptSnapshot?.prompt !== undefined) {
      return owner._systemPromptSnapshot;
    }
    if (!owner._systemPromptSnapshotPromise) {
      const pending = Promise.resolve()
        .then(factory)
        .then((snapshot) => {
          if (!snapshot || typeof snapshot.prompt !== "string") {
            throw new TypeError("system prompt snapshot must contain a prompt string");
          }
          defineHidden(owner, "_systemPromptSnapshot", snapshot);
          delete owner._systemPromptSnapshotPromise;
          return snapshot;
        })
        .catch((error) => {
          delete owner._systemPromptSnapshotPromise;
          throw error;
        });
      defineHidden(owner, "_systemPromptSnapshotPromise", pending);
    }
    return owner._systemPromptSnapshotPromise;
  }

  const RESPONSE_STYLE_KEY = "code-response-style";
  const RESPONSE_DETAILS = Object.freeze(["default", "concise", "detailed"]);
  const RESPONSE_TONES = Object.freeze(["default", "professional", "casual"]);

  function compileResponseStyle(detail, tone, version = 2) {
    if (!RESPONSE_DETAILS.includes(detail) || !RESPONSE_TONES.includes(tone)) {
      throw new TypeError("Invalid reply style preference");
    }
    if (detail === "default" && tone === "default") return "";
    const lines = [
      "[Reply preferences]",
      "Apply these preferences to explanations addressed to the user. The user's explicit request for detail, tone, format or artifact content takes precedence. Keep the engineering work complete, including required checks, error facts and permission confirmations. Preserve tool contracts, workspace rules, reasoning privacy and existing emoji rules. Keep the usual cadence of progress reporting and action names.",
    ];
    if (detail === "concise") lines.push(version === 1
      ? "Lead with the result. Keep explanations compact, with the essential conclusion and verification; trim preamble and repetition. Expand when the user asks for an explanation."
      : "Lead with the result and the essential conclusion and verification. For ordinary questions, aim for a short paragraph or a few focused points with the core explanation. Add further depth when the user explicitly requests a detailed explanation or more detail. Keep complex tasks complete while trimming preamble, repetition and tangents.");
    if (detail === "detailed") lines.push("Explain the result with the key evidence, tradeoffs and a useful example where appropriate. Add context that helps understanding; keep it relevant to the requested task. This overrides the default short-answer preference.");
    if (tone === "professional") lines.push("Use precise, measured language and a composed, professional tone.");
    if (tone === "casual") lines.push("Use natural, friendly conversational language, as with a colleague. Stay candid and accurate, with warmth and appropriate restraint.");
    return lines.join("\n");
  }

  function createResponseStyleSnapshot(preference = {}) {
    const detail = preference.detail ?? "default", tone = preference.tone ?? "default";
    return Object.freeze({ version: 2, detail, tone, instruction: compileResponseStyle(detail, tone) });
  }

  function restoreResponseStyleSnapshot(value) {
    // Absence belongs to a legacy task, never to today's UI preference.
    if (value == null) return null;
    if (typeof value !== "object" || Array.isArray(value)
        || Object.keys(value).sort().join(",") !== "detail,instruction,tone,version"
        || ![1, 2].includes(value.version) || !RESPONSE_DETAILS.includes(value.detail)
        || !RESPONSE_TONES.includes(value.tone)
        || !(value.instruction === compileResponseStyle(value.detail, value.tone, value.version)
          || (value.version === 1 && value.instruction === compileResponseStyle(value.detail, value.tone, 1)
            .replace("Keep the usual cadence of progress reporting and action names.", "Use the usual amount of progress reporting and action labels.")))) {
      const error = new Error("Cannot resume this task: invalid or unsupported reply style snapshot.");
      error.code = "response_style_snapshot_invalid";
      throw error;
    }
    return Object.freeze({ ...value });
  }

  function readResponseStylePreference(storage) {
    try {
      const raw = storage.getItem(RESPONSE_STYLE_KEY);
      if (raw === null) return { snapshot: createResponseStyleSnapshot(), error: "" };
      const value = JSON.parse(raw);
      if (!value || value.version !== 1 || Object.keys(value).sort().join(",") !== "detail,tone,version"
          || !RESPONSE_DETAILS.includes(value.detail) || !RESPONSE_TONES.includes(value.tone)) throw new Error();
      return { snapshot: createResponseStyleSnapshot(value), error: "" };
    } catch (_) {
      // Preserve damaged storage. Only an explicit successful save replaces it.
      return { snapshot: createResponseStyleSnapshot(), error: "responseStyleLoadFailed" };
    }
  }

  function saveResponseStylePreference(storage, preference) {
    const snapshot = createResponseStyleSnapshot(preference);
    storage.setItem(RESPONSE_STYLE_KEY, JSON.stringify({ version: 1, detail: snapshot.detail, tone: snapshot.tone }));
    return snapshot;
  }

  agent.systemPrompt = Object.freeze({
    RESPONSE_STYLE_KEY, RESPONSE_DETAILS, RESPONSE_TONES,
    createResponseStyleSnapshot, restoreResponseStyleSnapshot,
    readResponseStylePreference, saveResponseStylePreference,
    SYSTEM_PROMPT_SEGMENTS,
    buildSystemPromptSegments,
    createSystemPromptSnapshot,
    formatSystemPromptEnvironment,
    formatUtcOffset,
    getOrCreateSystemPromptSnapshot,
    resolveLocalTimeZoneName,
  });
})(typeof window !== "undefined" ? window : globalThis);
