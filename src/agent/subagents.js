(function initializeCodeAgentSubagents(global) {
  "use strict";

  const agent = global.Code && global.Code.agent;
  if (!agent) throw new Error("Code agent namespace must load before subagents");

  const SUBAGENT_DISABLED_TOOL_NAMES = Object.freeze(["task", "request_user_input"]);

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
    return {
      ...parentContext,
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

  agent.subagents = Object.freeze({
    buildBackgroundTaskPrompt,
    buildSubAgentSystemPrompt,
    createSubAgentContext,
    parseParallelCommand,
  });
})(window);
