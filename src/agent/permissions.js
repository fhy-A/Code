(function initializeCodeAgentPermissions(global) {
  "use strict";

  const agent = global.Code && global.Code.agent;
  if (!agent) throw new Error("Code agent namespace must load before permissions");

  const PERMISSION_INSTRUCTIONS = Object.freeze({
    read: "权限策略：只读分析。只能列出、读取和搜索项目文件；遇到无法从上下文或文件中确认的关键决策时可以向用户提问。不能写入、删除、运行命令、访问网络或启动子 Agent。",
    plan: "权限策略：计划模式。可读取、搜索、生成修改方案，但不能运行命令或直接写入文件。",
    accept: "权限策略：接受编辑模式。可执行命令和写入文件，但操作前需用户确认。",
    bypass: "权限策略：自动模式。当前允许的操作会自动执行，不再逐项请求授权；自动模式不保证完全安全。工作区是默认操作范围而非硬边界，用户明确提供的工作区外路径可在任务需要时访问。除非用户明确要求，不得自行扩张到父目录、相邻目录、用户主目录或磁盘根，也不得为寻找工具、依赖或 Skill 脚本递归扫描用户主目录或磁盘根。对工作区外的写入、覆盖或删除必须有明确用户意图。发现范围风险时先缩小范围或改用更安全的策略；仍无法完成时在最终回答中说明，不得调用 request_user_input 等方式中断自动任务。危险命令、系统安装、破坏性 Git 及其他服务端安全限制仍然生效。",
  });

  const AUTO_PERMISSION_ACK_KEY = "code-auto-permission-risk-ack";
  const AUTO_PERMISSION_ACK_VERSION = "v1";
  const PERMISSION_PROFILE_KEY = "code-permission-profile";
  const PERMISSION_PROFILES = Object.freeze(["read", "plan", "accept", "bypass"]);

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
      "generate_image",
      "manage_generated_image",
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
      "generate_image",
      "manage_generated_image",
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

  function createAutoPermissionRiskGate(options = {}) {
    const storage = options.storage || global.localStorage;
    const getProfile = typeof options.getProfile === "function"
      ? options.getProfile
      : () => storage?.getItem?.(PERMISSION_PROFILE_KEY) || "accept";
    const onProfileCommitted = typeof options.onProfileCommitted === "function"
      ? options.onProfileCommitted
      : () => {};
    const requestConfirmation = typeof options.requestConfirmation === "function"
      ? options.requestConfirmation
      : async () => false;
    const onStorageError = typeof options.onStorageError === "function"
      ? options.onStorageError
      : () => {};
    let pendingConfirmation = null;

    const profile = () => {
      const value = String(getProfile() || "accept");
      return PERMISSION_PROFILES.includes(value) ? value : "accept";
    };
    const storedAcknowledgement = () => String(
      storage?.getItem?.(AUTO_PERMISSION_ACK_KEY) || "",
    );

    function isAutoAcknowledged() {
      return profile() === "bypass"
        && storedAcknowledgement() === AUTO_PERMISSION_ACK_VERSION;
    }

    function requiresDispatchConfirmation() {
      return profile() === "bypass" && !isAutoAcknowledged();
    }

    function restoreStorageValue(key, value) {
      if (value == null) storage?.removeItem?.(key);
      else storage?.setItem?.(key, value);
    }

    function commitProfile(nextProfile, { acknowledged = false } = {}) {
      const normalized = String(nextProfile || "");
      if (!PERMISSION_PROFILES.includes(normalized)) return false;
      if (normalized === "bypass" && acknowledged !== true) return false;

      const previousProfile = storage?.getItem?.(PERMISSION_PROFILE_KEY) ?? null;
      const previousAcknowledgement = storage?.getItem?.(AUTO_PERMISSION_ACK_KEY) ?? null;
      try {
        if (normalized === "bypass") {
          storage?.setItem?.(AUTO_PERMISSION_ACK_KEY, AUTO_PERMISSION_ACK_VERSION);
          storage?.setItem?.(PERMISSION_PROFILE_KEY, normalized);
        } else {
          storage?.setItem?.(PERMISSION_PROFILE_KEY, normalized);
          storage?.removeItem?.(AUTO_PERMISSION_ACK_KEY);
        }
      } catch (error) {
        try {
          restoreStorageValue(PERMISSION_PROFILE_KEY, previousProfile);
          restoreStorageValue(AUTO_PERMISSION_ACK_KEY, previousAcknowledgement);
        } catch (_) {}
        onStorageError(error);
        return false;
      }
      onProfileCommitted(normalized);
      return true;
    }

    function confirm(reason) {
      if (pendingConfirmation) return pendingConfirmation;
      pendingConfirmation = Promise.resolve()
        .then(() => requestConfirmation({ reason }))
        .then(Boolean)
        .catch(() => false)
        .finally(() => {
          pendingConfirmation = null;
        });
      return pendingConfirmation;
    }

    async function requestProfileTransition(nextProfile) {
      const normalized = String(nextProfile || "");
      if (!PERMISSION_PROFILES.includes(normalized)) return false;
      if (normalized !== "bypass") return commitProfile(normalized);
      if (isAutoAcknowledged()) return true;
      if (!await confirm("selection")) return false;
      return commitProfile("bypass", { acknowledged: true });
    }

    async function ensureDispatchConfirmed() {
      if (!requiresDispatchConfirmation()) return true;
      if (await confirm("legacy-dispatch")) {
        return commitProfile("bypass", { acknowledged: true });
      }
      commitProfile("accept");
      return false;
    }

    function reconcileInactiveAcknowledgement() {
      if (profile() === "bypass" || !storedAcknowledgement()) return;
      try {
        storage?.removeItem?.(AUTO_PERMISSION_ACK_KEY);
      } catch (error) {
        onStorageError(error);
      }
    }

    return Object.freeze({
      ensureDispatchConfirmed,
      isAutoAcknowledged,
      reconcileInactiveAcknowledgement,
      requestProfileTransition,
      requiresDispatchConfirmation,
    });
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
    AUTO_PERMISSION_ACK_KEY,
    AUTO_PERMISSION_ACK_VERSION,
    createAutoPermissionRiskGate,
    executionOwnerForPermissionProfile,
    filterPendingAuthorizations,
    getAllowedToolNamesForProfile,
    getPermissionInstruction,
    groupAuthorizations,
    serializeAuthorizationRequest,
  });
})(window);
