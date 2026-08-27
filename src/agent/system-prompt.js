(function initializeCodeSystemPrompt(global) {
  "use strict";

  const agent = global.Code && global.Code.agent;
  if (!agent) throw new Error("Code agent namespace must load before system prompt");

  const SYSTEM_PROMPT_SEGMENTS = Object.freeze([
    Object.freeze({ name: "security", input: "securityLayer", condition: "always", refresh: "static" }),
    Object.freeze({ name: "behavior", input: "behaviorInstruction", condition: "always", refresh: "task" }),
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

  agent.systemPrompt = Object.freeze({
    SYSTEM_PROMPT_SEGMENTS,
    buildSystemPromptSegments,
    createSystemPromptSnapshot,
    formatSystemPromptEnvironment,
    formatUtcOffset,
    getOrCreateSystemPromptSnapshot,
    resolveLocalTimeZoneName,
  });
})(typeof window !== "undefined" ? window : globalThis);
