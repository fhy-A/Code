(function initializeCodeAgentPermissions(global) {
  "use strict";

  const agent = global.Code && global.Code.agent;
  if (!agent) throw new Error("Code agent namespace must load before permissions");

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

  agent.permissions = Object.freeze({
    executionOwnerForPermissionProfile,
    getAllowedToolNamesForProfile,
  });
})(window);
