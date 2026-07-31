(function initializeCodeAgentPermissions(global) {
  "use strict";

  const agent = global.Code && global.Code.agent;
  if (!agent) throw new Error("Code agent namespace must load before permissions");

  const PERMISSION_INSTRUCTIONS = Object.freeze({
    read: "权限策略：只读分析。只能列出、读取和搜索项目文件；遇到无法从上下文或文件中确认的关键决策时可以向用户提问。不能写入、删除、运行命令、访问网络或启动子 Agent。",
    plan: "权限策略：计划模式。可读取、搜索、生成修改方案，但不能运行命令或直接写入文件。",
    accept: "权限策略：接受编辑模式。可执行命令和写入文件，但操作前需用户确认。",
    bypass: "权限策略：自动模式。所有操作自动执行，无需确认。",
  });

  const TOOL_POLICY = Object.freeze({
    read: Object.freeze([
      "request_user_input",
      "list_files",
      "read_file",
      "search_files",
      "glob_files",
      "check_skill_dependencies",
    ]),
    plan: Object.freeze([
      "request_user_input",
      "list_files",
      "read_file",
      "search_files",
      "glob_files",
      "web_fetch",
      "propose_edit",
      "task",
      "use_skill",
      "check_skill_dependencies",
      "read_skill_resource",
    ]),
    accept: Object.freeze([
      "request_user_input",
      "list_files",
      "read_file",
      "search_files",
      "glob_files",
      "web_fetch",
      "propose_edit",
      "run_command",
      "task",
      "use_skill",
      "check_skill_dependencies",
      "write_file",
      "delete_file",
      "save_memory",
      "read_skill_resource",
    ]),
    bypass: Object.freeze([
      "request_user_input",
      "list_files",
      "read_file",
      "search_files",
      "glob_files",
      "web_fetch",
      "propose_edit",
      "run_command",
      "task",
      "use_skill",
      "check_skill_dependencies",
      "write_file",
      "delete_file",
      "save_memory",
      "read_skill_resource",
    ]),
  });

  const SERVER_EXECUTION_PROFILES = Object.freeze(["read", "plan", "accept", "bypass"]);

  function executionOwnerForPermissionProfile(permissionProfile) {
    return SERVER_EXECUTION_PROFILES.includes(permissionProfile) ? "server-agent" : "browser";
  }

  function getAllowedToolNamesForProfile(permissionProfile, toolPreset = "default") {
    const base = new Set(TOOL_POLICY[permissionProfile] || TOOL_POLICY.accept);
    if (toolPreset === "full" && ["accept", "bypass"].includes(permissionProfile)) {
      base.add("run_command");
    }
    return base;
  }

  function getPermissionInstruction(permissionProfile) {
    return PERMISSION_INSTRUCTIONS[permissionProfile];
  }

  function serializeAuthorizationRequest(request) {
    if (!request) return null;
    const {
      resolve, abortSignal, abortHandler, submitDecision, _finishing, error, ...serializable
    } = request;
    return JSON.parse(JSON.stringify(serializable));
  }

  function filterPendingAuthorizations(items, sessionId) {
    return items.filter((item) => item.status === "pending" && item.sessionId === sessionId);
  }

  function groupAuthorizations(items) {
    const groups = [];
    const byKey = new Map();
    for (const item of items) {
      let group = byKey.get(item.sourceKey);
      if (!group) {
        group = { key: item.sourceKey, label: item.sourceLabel, items: [] };
        byKey.set(item.sourceKey, group);
        groups.push(group);
      }
      group.items.push(item);
    }
    return groups;
  }

  agent.permissions = Object.freeze({
    executionOwnerForPermissionProfile,
    filterPendingAuthorizations,
    getAllowedToolNamesForProfile,
    getPermissionInstruction,
    groupAuthorizations,
    serializeAuthorizationRequest,
  });
})(window);
