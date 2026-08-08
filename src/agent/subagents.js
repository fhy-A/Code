(function initializeCodeAgentSubagents(global) {
  "use strict";

  const agent = global.Code && global.Code.agent;
  if (!agent) throw new Error("Code agent namespace must load before subagents");

  const BACKGROUND_JOB_TIMEOUT_MS = 10 * 60 * 1000;
  const SUBAGENT_DISABLED_TOOL_NAMES = Object.freeze(["task", "request_user_input"]);
  const SUBAGENT_PROJECTION_PRIVATE_FIELDS = Object.freeze([
    "_agentProjectionShadow",
    "_agentProjectionLegacyObservation",
    "_agentProjectionShadowArchived",
  ]);

  function buildSubAgentSystemPrompt({ securityLayer = "", cwd = "", primaryRoot = "" } = {}) {
    return [
      String(securityLayer || ""),
      "你是一个编程子 Agent，负责亲自完成主 Agent 分配的子任务。你只能使用主 Agent 当前权限策略开放给你的工具，不得尝试提升权限。",
      `环境：Windows + PowerShell。当前工作目录：${cwd || "未设置"}。主文件夹：${primaryRoot || cwd || "未设置"}。`,
      "禁止再次委派子 Agent。禁止用 JSON、代码块或文字模拟工具调用；需要操作时必须真正调用可用工具。",
      "完成前验证任务目标是否达成；完成后只返回简洁的结果摘要、验证结果和必要的路径。",
      "如果执行过程中遇到必须由用户决定的岔路口（如方案取舍、参数选择），你无法直接弹问卷。此时应停止操作，在结果中按以下格式输出：\n\n[DECISION_POINT]\n需要决定：<一句话描述>\n可选方案：\n- 方案A：<说明>\n- 方案B：<说明>\n推荐：<推荐哪个>\n\n主 Agent 看到后会接管并向用户询问。如果主 Agent 后续重新派发你来继续这个任务，它会在任务描述中附带用户的决定，你直接按决定执行，不要再上报同一个决策点。",
    ].join("\n\n");
  }

  function createSubAgentContext({
    parentContext = {},
    taskPrompt = "",
    securityLayer = "",
    authorizationId = "",
    tools = [],
  } = {}) {
    const prompt = String(taskPrompt || "").trim();
    const authorizationLabel = prompt.replace(/\s+/g, " ").slice(0, 24) || "子任务";
    const subSystem = buildSubAgentSystemPrompt({
      securityLayer,
      cwd: parentContext.cwd,
      primaryRoot: parentContext.primaryRoot,
    });
    const inheritedContext = { ...parentContext };
    for (const field of SUBAGENT_PROJECTION_PRIVATE_FIELDS) {
      delete inheritedContext[field];
    }
    return {
      ...inheritedContext,
      messages: [
        { role: "system", content: subSystem },
        { role: "user", content: taskPrompt },
      ],
      isSubAgent: true,
      authorizationId: String(authorizationId || ""),
      authorizationLabel,
      tools: (Array.isArray(tools) ? tools : []).filter((tool) => (
        !SUBAGENT_DISABLED_TOOL_NAMES.includes(tool?.function?.name)
      )),
      stats: { input: 0, output: 0, cache: 0 },
      taskUsage: { input: 0, output: 0, cache: 0 },
    };
  }

  function buildBackgroundTaskPrompt(currentTask, userText) {
    const task = String(currentTask || "");
    if (!task) return userText;
    return `[背景] 主 Agent 正在处理：${task.slice(0, 150)}\n\n[新请求] ${userText}\n\n你是一个后台子 Agent，收到了一条用户在等待中发送的新消息。请独立处理这条新请求。如果与主任务相关，直接处理新请求；如果无关，也独立完成。不要修改或中断主 Agent 的运行。完成后只输出结果。`;
  }

  function parseParallelCommand(text) {
    const match = String(text || "").match(/^\/parallel(?:\s+([\s\S]*))?$/i);
    if (!match) return null;
    return String(match[1] || "").trim();
  }

  function buildBackgroundJobCheckpoint(job, fallbackNow = 0) {
    const source = job || {};
    const now = Number(fallbackNow || 0);
    const rootPaths = source.rootPaths || source.parentCtx?.rootPaths;
    return {
      id: source.id,
      clientRequestId: source.clientRequestId || source.id,
      status: source.status,
      agentRunId: String(source.agentRunId || ""),
      cursor: Number(source.cursor || 0),
      userText: String(source.userText || ""),
      taskPrompt: String(source.taskPrompt || source.userText || ""),
      model: String(source.model || ""),
      permissionProfile: String(source.permissionProfile || "read"),
      toolPreset: String(source.toolPreset || "default"),
      thinkingLevel: String(source.thinkingLevel || "auto"),
      temperature: Number(source.temperature ?? 0.2),
      maxTokens: Number(source.maxTokens || 0),
      cwd: String(source.cwd || source.parentCtx?.cwd || ""),
      primaryRoot: String(source.primaryRoot || source.parentCtx?.primaryRoot || ""),
      rootPaths: Array.isArray(rootPaths) ? [...rootPaths] : [],
      parentTaskStartedAt: Number(source.parentTaskStartedAt || 0),
      queuedAt: Number(source.queuedAt || now),
      startedAt: Number(source.startedAt || 0),
      deadlineAt: Number(source.deadlineAt || (now + BACKGROUND_JOB_TIMEOUT_MS)),
    };
  }

  function buildRestoredBackgroundJobData(checkpoint, {
    sessionId = "",
    fallbackUserText = "",
    fallbackModel = "",
    fallbackQueuedAt = 0,
    fallbackDeadlineAt = 0,
  } = {}) {
    const source = checkpoint || {};
    const userText = String(source.userText || fallbackUserText || "");
    const normalized = buildBackgroundJobCheckpoint({
      ...source,
      userText,
      taskPrompt: source.taskPrompt || source.userText || fallbackUserText || "",
      model: source.model || fallbackModel || "",
      queuedAt: source.queuedAt || fallbackQueuedAt,
      deadlineAt: source.deadlineAt || fallbackDeadlineAt,
    });
    return {
      ...source,
      ...normalized,
      id: String(source.id || ""),
      clientRequestId: String(source.clientRequestId || source.id || ""),
      sessionId: String(sessionId || ""),
      status: "pending",
      restored: true,
    };
  }

  function hasBackgroundResult(messages, jobId) {
    return (Array.isArray(messages) ? messages : []).some((message) => (
      message?.role === "assistant"
      && message.meta?.kind === "background-subagent"
      && message.meta?.jobId === jobId
    ));
  }

  function buildBackgroundResultMessage(job, {
    content = "",
    error = false,
    model = "",
    timestamp = "",
    responseTime = "",
    usage,
    includeUsage = false,
  } = {}) {
    const source = job || {};
    const normalizedResponseTime = String(responseTime || "").trim();
    const meta = {
      kind: "background-subagent",
      jobId: source.id,
      agentRunId: source.agentRunId,
      error: Boolean(error),
      detachedFromMain: true,
      parentTaskStartedAt: Number(source.parentTaskStartedAt || 0),
      _responseTime: normalizedResponseTime,
    };
    if (includeUsage) {
      meta._usage = usage;
      meta._usageScope = "task";
    }
    return {
      role: "assistant",
      content,
      meta,
      _model: model,
      _time: timestamp,
      _responseTime: normalizedResponseTime,
    };
  }

  function mergeBackgroundUsageStats(currentStats, childStats) {
    const merged = { ...(currentStats || {}) };
    const child = childStats || {};
    for (const key of ["input", "output", "cache", "cost"]) {
      merged[key] = Number(merged[key] || 0) + Number(child[key] || 0);
    }
    if (Object.prototype.hasOwnProperty.call(child, "cacheWrite")) {
      merged.cacheWrite = Number(merged.cacheWrite || 0) + Number(child.cacheWrite || 0);
    }
    return merged;
  }

  function backgroundJobElapsedMs(job, finishedAt) {
    const submittedAt = Number(job?.queuedAt || job?.startedAt || finishedAt);
    return Math.max(0, Number(finishedAt) - submittedAt);
  }

  agent.subagents = Object.freeze({
    BACKGROUND_JOB_TIMEOUT_MS,
    backgroundJobElapsedMs,
    buildBackgroundJobCheckpoint,
    buildBackgroundResultMessage,
    buildBackgroundTaskPrompt,
    buildRestoredBackgroundJobData,
    buildSubAgentSystemPrompt,
    createSubAgentContext,
    hasBackgroundResult,
    mergeBackgroundUsageStats,
    parseParallelCommand,
  });
})(window);
