(function registerSkillsMemoryFeature(global) {
  "use strict";

  const Code = global.Code;
  if (!Code?.features) throw new Error("Code namespace must load before skills-memory feature");

  const EXPLICIT_ONLY_SKILLS = Object.freeze([
    "dispatching-parallel-agents",
    "subagent-driven-development",
    "executing-plans",
    "writing-plans",
  ]);
  const EXPLICIT_ONLY_SET = new Set(EXPLICIT_ONLY_SKILLS);
  const DEPENDENCY_CAPABILITY_KEYS = Object.freeze({
    "advanced-cli": "skillDepCapAdvancedCli",
    author: "skillDepCapAuthor",
    bundle: "skillDepCapBundle",
    charts: "skillDepCapCharts",
    create: "skillDepCapCreate",
    "create-edit": "skillDepCapCreateEdit",
    excel: "skillDepCapExcel",
    "extract-tables": "skillDepCapExtractTables",
    "image-editing": "skillDepCapImageEditing",
    image: "skillDepCapImage",
    inspect: "skillDepCapInspect",
    "node-server": "skillDepCapNodeServer",
    "node-runtime": "skillDepCapNodeRuntime",
    ocr: "skillDepCapOcr",
    pdf: "skillDepCapPdf",
    powerpoint: "skillDepCapPowerpoint",
    "python-server": "skillDepCapPythonServer",
    "python-runtime": "skillDepCapPythonRuntime",
    read: "skillDepCapRead",
    "read-edit": "skillDepCapReadEdit",
    render: "skillDepCapRender",
    scaffold: "skillDepCapScaffold",
    spreadsheet: "skillDepCapSpreadsheet",
    "command-runtime": "skillDepCapCommandRuntime",
    word: "skillDepCapWord",
  });
  const DEPENDENCY_ACTION_KEYS = Object.freeze({
    install: "skillDependencyInstall",
    repair: "skillDependencyRepair",
    uninstall: "skillDependencyUninstall",
  });
  const ACTIVE_DEPENDENCY_OPERATION_STATUSES = new Set(["pending", "running"]);

  function rankMatchedSkills(skills = [], disabledSkills = new Set(), userMessage = "") {
    if (!userMessage || skills.length === 0) return [];
    const text = Array.isArray(userMessage)
      ? (userMessage.find((content) => content.type === "text")?.text || "")
      : String(userMessage || "");
    const lower = text.toLowerCase();
    const candidates = skills
      .filter((skill) => !disabledSkills.has(skill.name) && !EXPLICIT_ONLY_SET.has(skill.name))
      .map((skill) => {
        const keywordScore = (skill.keywords || []).reduce((best, keyword) => {
          const parts = String(keyword || "").toLowerCase().split("+").map((part) => part.trim()).filter(Boolean);
          if (!parts.length || !parts.every((part) => lower.includes(part))) return best;
          return Math.max(best, 300 + parts.reduce((total, part) => total + part.length, 0));
        }, 0);
        if (keywordScore) return { skill, score: keywordScore };

        const name = (skill.name || "").toLowerCase();
        if (name.length >= 2 && lower.includes(name)) return { skill, score: 200 + name.length };

        return null;
      })
      .filter(Boolean);
    if (!candidates.length) return [];
    const bestScore = Math.max(...candidates.map((item) => item.score));
    return candidates
      .filter((item) => item.score === bestScore)
      .map((item) => item.skill)
      .slice(0, 3);
  }

  function applySkillTaskPolicy(
    allowedToolNames,
    skills = [],
    disabledSkills = new Set(),
    userMessage = "",
    explicitSkill = "",
  ) {
    const allowed = new Set(allowedToolNames || []);
    if (!allowed.has("task")) return allowed;
    const text = Array.isArray(userMessage)
      ? (userMessage.find((content) => content.type === "text")?.text || "")
      : String(userMessage || "");
    const userRequestedDelegation = /(?:子\s*agent|子任务|sub-?agents?|parallel\s+agents?|并行.{0,6}(?:agent|任务))/i.test(text);
    if (userRequestedDelegation) return allowed;

    const activeSkills = explicitSkill
      ? skills.filter((skill) => skill.name === explicitSkill && !disabledSkills.has(skill.name))
      : rankMatchedSkills(skills, disabledSkills, text);
    if (!activeSkills.length) return allowed;
    const taskDeclared = activeSkills.some((skill) => (
      Array.isArray(skill.tools) && skill.tools.includes("task")
    ));
    if (!taskDeclared) allowed.delete("task");
    return allowed;
  }

  function getSkillToolBudgets(
    skills = [],
    disabledSkills = new Set(),
    userMessage = "",
    explicitSkill = "",
  ) {
    const text = Array.isArray(userMessage)
      ? (userMessage.find((content) => content.type === "text")?.text || "")
      : String(userMessage || "");
    if (/(?:深度|全面|完整).{0,6}(?:审计|审查|调查)|deep\s+(?:audit|review)|exhaustive\s+(?:audit|review)/i.test(text)) {
      return [];
    }
    const activeSkills = explicitSkill
      ? skills.filter((skill) => skill.name === explicitSkill && !disabledSkills.has(skill.name))
      : rankMatchedSkills(skills, disabledSkills, text);
    if (!activeSkills.some((skill) => skill.name === "brainstorming")) return [];
    return [
      {
        name: "brainstorming-discovery",
        tools: ["search_files", "glob_files", "list_files"],
        limit: 3,
        exhaustedMessage: "已达到 brainstorming 的默认搜索预算。停止继续定位源码，使用已有证据汇总方案，并把缺失事实标为待验证。最终回答不得加入未实测的耗时、资源、规模阈值、优化倍数或性能排名。",
      },
      {
        name: "brainstorming-reading",
        tools: ["read_file"],
        limit: 4,
        exhaustedMessage: "已达到 brainstorming 的默认读取预算。停止继续读取文件，使用已有证据汇总方案，并把缺失事实标为待验证。最终回答不得加入未实测的耗时、资源、规模阈值、优化倍数或性能排名。",
      },
    ];
  }

  function formatSkillInstructions(skill) {
    const body = String(skill?.body || "").trim();
    const tools = Array.isArray(skill?.tools)
      ? skill.tools.map((tool) => String(tool || "").trim()).filter(Boolean)
      : [];
    const dependencyCapabilities = skill?.dependencyCapabilities || {};
    const dependencyCapabilityIds = Object.keys(dependencyCapabilities);
    const dependencyPolicy = dependencyCapabilityIds.length
      ? [
        `Dependency gate: before first use of this Skill in the current task, call check_skill_dependencies with name "${skill.name}" as a standalone tool call. Available capabilities: ${dependencyCapabilityIds.join(", ")}.`,
        dependencyCapabilityIds.length > 1
          ? "Choose only the capability needed by the current task and pass it as capability. If the user only asked for a dependency report, omit capability, summarize the returned statuses, and stop. Never install every capability."
          : `Use capability "${dependencyCapabilityIds[0]}" when checking or re-checking this Skill.`,
        "If required Python or Node dependencies are missing, install only the declared items using the returned managed-runtime plan after authorization.",
        "System-command dependencies must be installed by the user outside Code. Present supplied installHints verbatim, but never execute them, modify PATH, or create global command wrappers with run_command, propose_edit, or write_file; explain the missing command and wait.",
        "Re-run check_skill_dependencies for the same selected capability after installation and continue only when that capability is ready.",
        "When the dependency result reports a managed runtime, execute Skill scripts with its Python executable or NODE_PATH instead of assuming the system runtime can import those packages.",
      ].join("\n")
      : "";
    return [
      tools.length ? `Preferred tools: ${tools.join(", ")}` : "",
      tools.length ? "Tool guidance only; this does not expand the current mode's permissions." : "",
      tools.length ? "Do not call task unless it is listed above or the user explicitly requests delegation." : "",
      dependencyPolicy,
      body,
    ].filter(Boolean).join("\n");
  }

  const UI_SLASH_COMMANDS = Object.freeze([
    { name: "goal", descriptionKey: "cmdGoalDesc" },
    { name: "compact", descriptionKey: "cmdCompactDesc" },
    { name: "remember", descriptionKey: "cmdRememberDesc" },
    { name: "export", descriptionKey: "cmdExportDesc" },
    { name: "clear", descriptionKey: "cmdClearDesc" },
    { name: "branch", descriptionKey: "cmdBranchDesc" },
    { name: "parallel", descriptionKey: "cmdParallelDesc" },
    { name: "help", descriptionKey: "cmdHelpDesc" },
  ]);

  function getSlashSuggestionGroups(skills, disabledSkills, partial, t) {
    const normalizedPartial = String(partial || "").toLowerCase();
    const disabled = disabledSkills instanceof Set ? disabledSkills : new Set(disabledSkills || []);
    const commandItems = UI_SLASH_COMMANDS
      .filter((command) => command.name.startsWith(normalizedPartial))
      .map((command) => ({
        name: command.name,
        description: t(command.descriptionKey),
      }));
    const skillItems = (skills || [])
      .filter((skill) => !disabled.has(skill.name))
      .filter((skill) => skill.name.startsWith(normalizedPartial));

    return [
      { key: "commands", label: t("slashCommandsLabel"), items: commandItems },
      { key: "skills", label: t("slashSkillsLabel"), items: skillItems },
    ].filter((group) => group.items.length);
  }

  function classifyGoalControlInput(input) {
    const text = String(input || "").trim();
    if (!text) return null;
    const lower = text.toLowerCase();
    const exact = new Map([
      ["/goal", { kind: "query" }],
      ["/goal status", { kind: "query" }],
      ["/goal 状态", { kind: "query" }],
      ["goal status", { kind: "query" }],
      ["goal 状态", { kind: "query" }],
      ["查看 goal 状态", { kind: "query" }],
      ["/goal confirm", { kind: "confirm" }],
      ["/goal 确认", { kind: "confirm" }],
      ["confirm goal", { kind: "confirm" }],
      ["确认 goal", { kind: "confirm" }],
      ["/goal pause", { kind: "pause" }],
      ["/goal 暂停", { kind: "pause" }],
      ["pause goal", { kind: "pause" }],
      ["暂停 goal", { kind: "pause" }],
      ["/goal resume", { kind: "resume" }],
      ["/goal 恢复", { kind: "resume" }],
      ["resume goal", { kind: "resume" }],
      ["恢复 goal", { kind: "resume" }],
      ["/goal cancel", { kind: "proposal", proposal: { type: "cancel" } }],
      ["/goal 取消", { kind: "proposal", proposal: { type: "cancel" } }],
      ["cancel goal", { kind: "proposal", proposal: { type: "cancel" } }],
      ["取消 goal", { kind: "proposal", proposal: { type: "cancel" } }],
      ["/goal clear", { kind: "proposal", proposal: { type: "clear" } }],
      ["/goal 清除", { kind: "proposal", proposal: { type: "clear" } }],
      ["clear goal", { kind: "proposal", proposal: { type: "clear" } }],
      ["清除 goal", { kind: "proposal", proposal: { type: "clear" } }],
    ]);
    if (exact.has(lower)) return exact.get(lower);

    const prefixes = [
      [/^补充\s*goal\s*[:：]\s*(.+)$/is, (match) => ({
        kind: "proposal", proposal: { type: "supplement", text: match[1].trim() },
      })],
      [/^supplement\s+goal\s*:\s*(.+)$/is, (match) => ({
        kind: "proposal", proposal: { type: "supplement", text: match[1].trim() },
      })],
      [/^替换\s*goal\s*[:：]\s*(.+)$/is, (match) => ({
        kind: "proposal", proposal: { type: "revise", objective: match[1].trim() },
      })],
      [/^replace\s+goal\s*:\s*(.+)$/is, (match) => ({
        kind: "proposal", proposal: { type: "revise", objective: match[1].trim() },
      })],
      [/^修改\s*goal\s*[:：]\s*(.+)$/is, (match) => ({
        kind: "structured-revision", source: match[1].trim(),
      })],
      [/^revise\s+goal\s*:\s*(.+)$/is, (match) => ({
        kind: "structured-revision", source: match[1].trim(),
      })],
    ];
    for (const [pattern, create] of prefixes) {
      const match = text.match(pattern);
      if (match) return create(match);
    }
    const createMatch = text.match(/^\/goal(?:\s+([\s\S]+))?$/i);
    if (createMatch?.[1]?.trim()) return { kind: "create", objective: createMatch[1].trim() };
    return null;
  }

  function createGoalControlFeature(options = {}) {
    const apiJson = options.apiJson;
    const t = options.t || ((key) => key);
    const showToast = options.showToast || (() => {});
    const getSessionId = options.getSessionId || (() => "");
    const ensureSession = options.ensureSession || (async () => "");
    const getPermissionProfile = options.getPermissionProfile || (() => "accept");
    const getLanguage = options.getLanguage || (() => "zh");
    const confirmAction = options.confirm || global.confirm?.bind(global) || (() => false);
    const alertAction = options.alert || global.alert?.bind(global) || ((message) => showToast(message, "info"));
    let requestSequence = 0;
    let executionInFlight = false;

    if (typeof apiJson !== "function") throw new Error("Goal control feature requires apiJson");

    function requestKey(operation) {
      requestSequence += 1;
      return `goal-${operation}-${Date.now().toString(36)}-${requestSequence.toString(36)}`;
    }

    function goalUrl(sessionId, control = false) {
      return `/api/sessions/${encodeURIComponent(sessionId)}/goal${control ? "/control" : ""}`;
    }

    async function readGoal(sessionId) {
      const response = await apiJson(goalUrl(sessionId));
      return response?.data || response;
    }

    async function postControl(sessionId, body) {
      const response = await apiJson(goalUrl(sessionId, true), {
        method: "POST",
        body: JSON.stringify(body),
      });
      return response?.data || response;
    }

    function requireCurrentGoal(projection) {
      if (!projection?.goal) throw new Error(t("goalNoCurrent"));
      return projection.goal;
    }

    function formatGoal(projection) {
      if (!projection?.goal) return t("goalNoCurrent");
      const goal = projection.goal;
      const lines = [
        `Goal · ${goal.lifecycle} · r${projection.revision}`,
        goal.objective,
        "",
        ...goal.steps.flatMap((step, index) => [
          `${index + 1}. [${step.status}] ${step.description}`,
          ...(step.acceptanceCriteria || []).map((criterion) => (
            `   - [${criterion.kind}] ${criterion.description}`
          )),
        ]),
      ];
      return lines.join("\n");
    }

    function formatDraft(projection) {
      return `${t("goalDraftConfirm")}\n\n${formatGoal(projection)}`;
    }

    function formatProposal(proposed) {
      const diff = proposed?.diff || {};
      if (diff.type === "cancel") return t("goalCancelConfirm");
      if (diff.type === "clear") return t("goalClearConfirm");
      if (diff.type === "supplement") {
        return `${t("goalChangeConfirm")}\n\n+ ${diff.supplement}`;
      }
      const lines = [t("goalChangeConfirm")];
      if (diff.objective?.before !== diff.objective?.after) {
        lines.push("", `- ${diff.objective.before}`, `+ ${diff.objective.after}`);
      }
      if (diff.steps?.before && diff.steps?.after) {
        const formatSteps = (steps, prefix) => steps.flatMap((step, index) => [
          `${prefix} ${index + 1}. ${step.description}`,
          ...(step.acceptanceCriteria || []).map((criterion) => (
            `   ${prefix} [${criterion.kind}] ${criterion.description}`
          )),
        ]);
        lines.push(
          "",
          t("goalChangeBefore"),
          ...formatSteps(diff.steps.before, "-"),
          t("goalChangeAfter"),
          ...formatSteps(diff.steps.after, "+"),
        );
      }
      return lines.join("\n");
    }

    async function ensureGoalSession(objective) {
      let sessionId = String(getSessionId() || "");
      if (sessionId) return sessionId;
      await ensureSession(String(objective || "Goal").slice(0, 24));
      sessionId = String(getSessionId() || "");
      if (!sessionId) throw new Error(t("createSessionFirst"));
      return sessionId;
    }

    async function execute(action) {
      try {
        if (action.kind === "query") {
          const sessionId = String(getSessionId() || "");
          if (!sessionId) {
            alertAction(t("goalNoCurrent"));
            return;
          }
          alertAction(formatGoal(await readGoal(sessionId)));
          return;
        }

        if (action.kind === "structured-revision") {
          let parsed;
          try {
            parsed = JSON.parse(action.source);
          } catch (_) {
            throw new Error(t("goalStructuredRevisionInvalid"));
          }
          if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
            throw new Error(t("goalStructuredRevisionInvalid"));
          }
          action = { kind: "proposal", proposal: { ...parsed, type: "revise" } };
        }

        if (action.kind === "create") {
          const sessionId = await ensureGoalSession(action.objective);
          const current = await readGoal(sessionId);
          let draft;
          if (current?.goal?.lifecycle === "awaiting_confirmation") {
            if (current.goal.objective !== action.objective) {
              throw new Error(t("goalDraftAlreadyExists"));
            }
            draft = current;
          } else {
            if (current?.goal && !["completed", "cancelled"].includes(current.goal.lifecycle)) {
              throw new Error(t("goalAlreadyExists"));
            }
            draft = await postControl(sessionId, {
              operation: "create_draft",
              expectedRevision: current.revision,
              idempotencyKey: requestKey("draft"),
              objective: action.objective,
              permissionProfile: getPermissionProfile(),
              language: getLanguage() === "en" ? "en" : "zh",
            });
          }
          if (!confirmAction(formatDraft(draft))) {
            showToast(t("goalAwaitingConfirmation"), "info");
            return;
          }
          const activated = await postControl(sessionId, {
            operation: "confirm_draft",
            expectedRevision: draft.revision,
            idempotencyKey: requestKey("confirm"),
            goalId: draft.goal.goalId,
          });
          showToast(t("goalActivated"), "success");
          return activated;
        }

        const sessionId = String(getSessionId() || "");
        if (!sessionId) throw new Error(t("goalNoCurrent"));
        const current = await readGoal(sessionId);
        const goal = requireCurrentGoal(current);
        if (action.kind === "confirm" || action.kind === "pause" || action.kind === "resume") {
          const operation = action.kind === "confirm" ? "confirm_draft" : action.kind;
          const changed = await postControl(sessionId, {
            operation,
            expectedRevision: current.revision,
            idempotencyKey: requestKey(operation),
            goalId: goal.goalId,
          });
          const messageKey = action.kind === "confirm"
            ? "goalActivated"
            : (action.kind === "pause" ? "goalPaused" : "goalResumed");
          showToast(t(messageKey), "success");
          return changed;
        }

        if (action.kind === "proposal") {
          const proposed = await postControl(sessionId, {
            operation: "propose_change",
            expectedRevision: current.revision,
            goalId: goal.goalId,
            proposal: action.proposal,
          });
          if (!confirmAction(formatProposal(proposed))) {
            showToast(t("goalChangeNotApplied"), "info");
            return;
          }
          const changed = await postControl(sessionId, {
            operation: "confirm_change",
            expectedRevision: current.revision,
            idempotencyKey: requestKey("change"),
            goalId: goal.goalId,
            confirmationToken: proposed.confirmationToken,
          });
          showToast(t("goalChanged"), "success");
          return changed;
        }
      } catch (error) {
        showToast(t("goalActionFailed", { error: error?.message || String(error) }), "error");
      }
    }

    function handleInput(input) {
      const action = classifyGoalControlInput(input);
      if (!action) return false;
      if (executionInFlight) {
        showToast(t("goalActionInProgress"), "info");
        return true;
      }
      executionInFlight = true;
      void execute(action).finally(() => {
        executionInFlight = false;
      });
      return true;
    }

    return Object.freeze({ execute, handleInput, readGoal });
  }

  function createSkillsMemoryFeature(options = {}) {
    const state = options.state || {};
    const els = options.elements || {};
    const t = options.t || ((key) => key);
    const escapeHtml = options.escapeHtml || ((value) => String(value ?? ""));
    const apiJson = options.apiJson;
    const showToast = options.showToast || (() => {});
    const onPromptChanged = options.onPromptChanged || (() => {});
    const onMemoryChanged = options.onMemoryChanged || (() => {});
    const trashIcon = options.trashIcon || (() => "");
    const documentRef = options.document || global.document;
    const storage = options.storage || global.localStorage;

    if (typeof apiJson !== "function") throw new Error("skills-memory feature requires apiJson");
    if (!(state.disabledSkills instanceof Set)) state.disabledSkills = new Set(state.disabledSkills || []);

    let editingSkillName = null;
    let editingSkillDependencyOriginal = "";
    let editingSkillDependencySource = "";
    let settingsSelectedSkillName = null;
    let settingsMemoryRequestId = 0;
    let skillDependencySnapshot = null;
    let skillDependencyByName = new Map();
    let skillDependencyLoading = false;
    let skillDependencyError = "";
    let skillDependencyRequestId = 0;
    let skillDependencyOperationsLoaded = false;
    let skillDependencyOperationsLoading = false;
    let skillDependencyOperationByKey = new Map();
    let skillDependencyOperationPollers = new Set();
    let skillDependencyOperationRechecks = new Set();
    let skillDependencyPreview = null;
    let skillDependencyPreviewRequestId = 0;
    let bound = false;

    const byId = (id) => documentRef.getElementById(id);

    async function loadSkills() {
      try {
        const data = await apiJson("/api/skills?brief=1");
        state.skills = data.data || [];
      } catch {
        state.skills = [];
      }
      return state.skills;
    }

    async function ensureSkillBody(skill) {
      if (!skill || skill.body != null) return skill;
      try {
        const full = await apiJson(`/api/skills/${encodeURIComponent(skill.name)}`);
        skill.body = full.body || "";
        skill.path = full.path || "";
        skill.resources = full.resources || {};
        skill.dependencyCapabilities = full.dependencyCapabilities || {};
        skill.dependencyManifestSource = full.dependencyManifestSource || "";
        skill.dependencyDetectedFrom = full.dependencyDetectedFrom || [];
        skill.dependencyManifestError = full.dependencyManifestError || "";
      } catch {
        skill.body = "";
        skill.path = "";
        skill.resources = {};
        skill.dependencyCapabilities = {};
        skill.dependencyManifestSource = "";
        skill.dependencyDetectedFrom = [];
        skill.dependencyManifestError = "";
      }
      return skill;
    }

    async function getMatchedSkillPrompts(userMessage) {
      const matched = rankMatchedSkills(state.skills || [], state.disabledSkills, userMessage);
      if (!matched.length) return "";
      await Promise.all(matched.map(ensureSkillBody));
      matched.sort((a, b) => (a.body || "").length - (b.body || "").length);
      return matched.map((skill) => (
        `[Skill: ${skill.name}]\n${formatSkillInstructions(skill)}`
      )).join("\n\n---\n\n");
    }

    function toggleSkill(name) {
      if (state.disabledSkills.has(name)) state.disabledSkills.delete(name);
      else state.disabledSkills.add(name);
      storage?.setItem("code-disabled-skills", JSON.stringify([...state.disabledSkills]));
    }

    function showSkillsPanel() {
      byId("skillsModal")?.classList.remove("hidden");
      renderSkillsList();
      const first = state.skills?.[0];
      if (!first) {
        showSkillDetail(null);
        return;
      }
      const item = documentRef.querySelector(`.skill-list-item[data-skill-name="${escapeHtml(first.name)}"]`);
      if (item) {
        item.classList.add("active");
        showSkillDetail(first);
      } else {
        showSkillDetail(null);
      }
    }

    function sortedSkills() {
      const skills = state.skills || [];
      const active = skills.filter((skill) => !state.disabledSkills.has(skill.name));
      const disabled = skills.filter((skill) => state.disabledSkills.has(skill.name));
      return [...active, ...disabled];
    }

    function renderSkillsList() {
      const list = byId("skillsList");
      if (!list) return;
      const sorted = sortedSkills();
      list.innerHTML = sorted.length ? sorted.map((skill) => {
        const enabled = !state.disabledSkills.has(skill.name);
        const explicitOnly = EXPLICIT_ONLY_SET.has(skill.name);
        return `<div class="skill-list-item" data-skill-name="${escapeHtml(skill.name)}">
          <span class="dot ${enabled ? "on" : "off"}"></span>
          <span>${escapeHtml(skill.name)}</span>
          ${explicitOnly ? `<span class="skill-explicit-badge" title="${escapeHtml(t("explicitSkillTitle", { name: skill.name }))}">/</span>` : ""}
        </div>`;
      }).join("") : `<div class="muted-line" style="padding:12px; font-size:12px;">${t("noSkills")}</div>`;
      list.querySelectorAll(".skill-list-item").forEach((item) => {
        item.addEventListener("click", () => {
          list.querySelectorAll(".skill-list-item").forEach((element) => element.classList.remove("active"));
          item.classList.add("active");
          showSkillDetail(state.skills.find((skill) => skill.name === item.dataset.skillName));
        });
      });
    }

    function editIcon() {
      return '<svg class="icon" viewBox="0 0 1097 1024" width="14" height="14"><path d="M925.72 1024H161.13C72 1024 0 952.32 0 863.57V160.43C0 71.68 72 0 161.16 0h613.67c20.58 0 34.3 13.65 34.3 34.13s-13.72 34.14-34.3 34.14H161.16a91.99 91.99 0 00-92.55 92.16v699.73c0 54.61 41.13 95.57 92.55 95.57h764.59c51.44 0 92.57-40.96 92.57-92.16V337.92c0-20.48 13.7-34.13 34.28-34.13s34.28 13.65 34.28 34.13v525.65c3.41 88.75-72 160.43-161.16 160.43zM456 658.77c-10.29 0-17.14-3.41-24-10.24-13.72-13.65-13.72-34.13 0-47.78L1038.85 23.89a33.26 33.26 0 0148.03 0c13.7 13.66 13.7 34.14 0 47.79L479.96 648.53c-6.83 6.83-13.7 10.24-24 10.24z" fill="currentColor"/></svg>';
    }

    async function showSkillDetail(skill) {
      const panel = byId("skillsDetail");
      if (!panel) return;
      if (!skill) {
        panel.innerHTML = `<div class="skills-detail-empty">${t("selectSkillHint")}</div>`;
        return;
      }
      await ensureSkillBody(skill);
      const enabled = !state.disabledSkills.has(skill.name);
      panel.innerHTML = `<div class="skill-detail-head">
        <div class="skill-detail-name">${escapeHtml(skill.name)}</div>
        <div class="skill-detail-head-actions">
          <label class="toggle-switch" title="${enabled ? t("enabledStatus") : t("disabledStatus")}">
            <input type="checkbox" ${enabled ? "checked" : ""} id="skillToggleBtn" />
            <span class="toggle-track"><span class="toggle-thumb"></span></span>
          </label>
          <button class="skill-edit-icon" id="skillEditBtn" title="${t("edit")}">${editIcon()}</button>
        </div>
      </div>
      <div class="skill-detail-section"><div class="skill-detail-label">${t("skillDesc")}</div><div class="skill-detail-value">${escapeHtml(skill.description || "-")}</div></div>
      <div class="skill-detail-section"><div class="skill-detail-label">${t("skillKeywords")}</div><div class="skill-detail-value">${escapeHtml((skill.keywords || []).join(", ") || "-")}</div></div>
      <div class="skill-detail-section"><div class="skill-detail-label">${t("skillTools")}</div><div class="skill-detail-value">${escapeHtml((skill.tools || []).join(", ") || "-")}</div></div>
      <div class="skill-detail-section"><div class="skill-detail-label">${t("skillPathLabel")}</div><div class="skill-detail-value">${escapeHtml(skill.path || `data/skills/${skill.dir || skill.name}/SKILL.md`)}</div></div>
      <div class="skill-detail-actions"><button class="skill-delete-icon" id="skillDeleteBtn" title="${t("deleteSkill")}">${t("delete")}</button></div>`;
      byId("skillToggleBtn").addEventListener("change", () => {
        toggleSkill(skill.name);
        showSkillDetail(state.skills.find((item) => item.name === skill.name));
        renderSkillsList();
      });
      byId("skillEditBtn").addEventListener("click", () => openSkillEditor(skill));
      byId("skillDeleteBtn").addEventListener("click", () => deleteSkillConfirm(skill.name, "skillDeleteBtn"));
    }

    function openSkillEditor(skill) {
      editingSkillName = skill ? skill.name : null;
      byId("skillEditorTitle").textContent = skill ? `${t("editing")} ${skill.name}` : t("newSkill");
      byId("skillEditName").value = skill ? skill.name : "";
      byId("skillEditDesc").value = skill ? (skill.description || "") : "";
      byId("skillEditKeywords").value = skill ? (skill.keywords || []).join(", ") : "";
      byId("skillEditTools").value = skill ? (skill.tools || []).join(", ") : "";
      byId("skillEditBody").value = skill ? (skill.body || "") : "";
      const dependencies = skill?.dependencyCapabilities || {};
      const dependencyText = Object.keys(dependencies).length ? JSON.stringify(dependencies, null, 2) : "";
      editingSkillDependencyOriginal = dependencyText;
      editingSkillDependencySource = skill?.dependencyManifestSource || "";
      byId("skillEditDependencies").value = dependencyText;
      const dependencyEditor = byId("skillDependencyEditor");
      if (dependencyEditor) {
        dependencyEditor.open = Boolean(
          skill?.dependencyManifestError
          || (dependencyText && !["detected", "bundled"].includes(editingSkillDependencySource))
        );
      }
      const dependencyNotice = byId("skillDependencyEditorNotice");
      if (dependencyNotice) {
        const sources = Array.isArray(skill?.dependencyDetectedFrom)
          ? skill.dependencyDetectedFrom.join("、")
          : "";
        dependencyNotice.textContent = editingSkillDependencySource === "detected"
          ? t("skillDependencyDetectedEditorNotice", {
            sources: sources || t("skillDependencyDetectedSourceFallback"),
          })
          : "";
        dependencyNotice.classList.toggle("hidden", editingSkillDependencySource !== "detected");
      }
      const dependencyError = byId("skillDependencyEditorError");
      if (dependencyError) {
        dependencyError.textContent = skill?.dependencyManifestError
          ? t("skillDependencyManifestInvalid", { error: skill.dependencyManifestError })
          : "";
        dependencyError.classList.toggle("hidden", !skill?.dependencyManifestError);
      }
      byId("skillEditorModal").classList.remove("hidden");
    }

    function closeSkillEditor() {
      byId("skillEditorModal")?.classList.add("hidden");
      editingSkillName = null;
      editingSkillDependencyOriginal = "";
      editingSkillDependencySource = "";
    }

    async function saveSkillEdit() {
      const name = byId("skillEditName").value.trim();
      const description = byId("skillEditDesc").value.trim();
      const keywords = byId("skillEditKeywords").value.trim();
      const tools = byId("skillEditTools").value.trim();
      const body = byId("skillEditBody").value.trim();
      const dependencyText = byId("skillEditDependencies").value.trim();
      if (!name || !body) {
        showToast(t("fillRequired"), "error");
        return;
      }
      let dependencies = {};
      if (dependencyText) {
        try {
          dependencies = JSON.parse(dependencyText);
          if (!dependencies || Array.isArray(dependencies) || typeof dependencies !== "object") {
            throw new Error("capabilities must be an object");
          }
        } catch (error) {
          showToast(`${t("skillDependencyJsonInvalid")}：${error.message}`, "error");
          byId("skillDependencyEditor").open = true;
          byId("skillEditDependencies").focus();
          return;
        }
      }
      const conflict = state.skills.find((skill) => skill.name === name && skill.name !== editingSkillName);
      if (conflict) {
        showToast(t("nameConflict", { name }), "error");
        return;
      }
      try {
        const payload = {
          name,
          originalName: editingSkillName || "",
          description,
          keywords,
          tools,
          body,
        };
        const inheritedDependencySource = ["detected", "bundled"].includes(editingSkillDependencySource);
        if (!inheritedDependencySource || dependencyText !== editingSkillDependencyOriginal) {
          payload.dependencies = dependencies;
        }
        await apiJson("/api/skills", {
          method: "POST",
          body: JSON.stringify(payload),
        });
        if (editingSkillName && editingSkillName !== name && state.disabledSkills.has(editingSkillName)) {
          state.disabledSkills.delete(editingSkillName);
          state.disabledSkills.add(name);
          storage?.setItem("code-disabled-skills", JSON.stringify([...state.disabledSkills]));
        }
        skillDependencySnapshot = null;
        skillDependencyByName = new Map();
        skillDependencyError = "";
        await loadSkills();
        closeSkillEditor();
        renderSkillsList();
        settingsSelectedSkillName = name;
        renderSettingsSkillsSidebar(name);
        const updated = state.skills.find((skill) => skill.name === name);
        if (updated) {
          showSkillDetail(updated);
        } else {
          showSkillDetail(null);
        }
        if (byId("settingsSkillsDetail")) loadSkillDependencyStatus({ force: true });
      } catch (error) {
        showToast(`${t("saveFailed")}：${error.message}`, "error");
      }
    }

    async function deleteSkillConfirm(name, buttonId = "skillDeleteBtn") {
      const button = byId(buttonId);
      if (!button) return;
      button.closest(".skills-detail")?.querySelector(".key-delete-confirm")?.remove();
      const confirm = documentRef.createElement("div");
      confirm.className = "key-delete-confirm";
      confirm.innerHTML = `<span>${t("deleteConfirmMsg").replace("{name}", escapeHtml(name))}</span>
        <button class="key-confirm-yes" type="button">${t("confirmDelete")}</button>
        <button class="key-confirm-no" type="button">${t("cancel")}</button>`;
      button.closest(".skill-detail-actions")?.after(confirm);
      confirm.querySelector(".key-confirm-yes").addEventListener("click", async () => {
        confirm.remove();
        try {
          await apiJson(`/api/skills?name=${encodeURIComponent(name)}`, { method: "DELETE" });
          await loadSkills();
          renderSkillsList();
          if (settingsSelectedSkillName === name) settingsSelectedSkillName = null;
          renderSettingsSkillsSidebar();
          const remaining = state.skills.find((skill) => skill.name === name);
          if (remaining) {
            showSkillDetail(remaining);
          } else {
            showSkillDetail(null);
          }
        } catch (error) {
          showToast(`${t("deleteFailed")}：${error.message}`, "error");
        }
      });
      confirm.querySelector(".key-confirm-no").addEventListener("click", () => confirm.remove());
    }

    function showSlashSuggestions() {
      const existing = byId("slashSuggest");
      const value = els.prompt.value;
      // Only show suggestions while typing the command name (before any space).
      // Once a space appears, the command is locked — hide the list.
      if (value.includes(" ")) {
        existing?.remove();
        return;
      }
      if (!value.match(/^\/[\w-]*$/)) {
        existing?.remove();
        return;
      }
      const partial = value.slice(1).toLowerCase();
      const groups = getSlashSuggestionGroups(state.skills, state.disabledSkills, partial, t);
      const matches = groups.flatMap((group) => group.items);
      if (!matches.length) {
        existing?.remove();
        return;
      }
      if (!existing) {
        const dropdown = documentRef.createElement("div");
        dropdown.id = "slashSuggest";
        dropdown.className = "slash-suggest";
        els.chatForm.insertBefore(dropdown, els.prompt);
      }
      const dropdown = byId("slashSuggest");
      if (els.chatPane.classList.contains("empty-chat")) {
        const rect = els.prompt.getBoundingClientRect();
        dropdown.style.position = "fixed";
        dropdown.style.bottom = `${global.innerHeight - rect.top + 4}px`;
        dropdown.style.left = `${rect.left}px`;
        dropdown.style.right = `${global.innerWidth - rect.right}px`;
      } else {
        dropdown.style.position = "";
        dropdown.style.bottom = "";
        dropdown.style.left = "";
        dropdown.style.right = "";
      }
      let itemIndex = 0;
      dropdown.innerHTML = groups.map((group) => `<div class="slash-section" data-slash-section="${escapeHtml(group.key)}">
        <div class="slash-section-label">${escapeHtml(group.label)}</div>
        ${group.items.map((item) => {
          const index = itemIndex++;
          return `<div class="slash-item${index === 0 ? " slash-item--sel" : ""}" data-skill="${escapeHtml(item.name)}" data-index="${index}">
            <span class="slash-name">/${escapeHtml(item.name)}</span>
            <span class="slash-desc" title="${escapeHtml(item.description || "")}">${escapeHtml(item.description || "")}</span>
          </div>`;
        }).join("")}
      </div>`).join("");
      state._slashIndex = 0;
      state._slashCount = matches.length;

      dropdown.querySelectorAll(".slash-item").forEach((item) => {
        item.addEventListener("click", () => selectSlashItem(item.dataset.skill));
      });
    }

    function selectSlashItem(name) {
      const dropdown = byId("slashSuggest");
      els.prompt.value = `/${name} `;
      dropdown?.remove();
      els.prompt.focus();
      state._slashIndex = -1;
      onPromptChanged();
    }

    function navigateSlash(delta) {
      const dropdown = byId("slashSuggest");
      if (!dropdown || !state._slashCount) return;
      const prev = state._slashIndex;
      state._slashIndex = Math.max(0, Math.min(state._slashCount - 1, (prev || 0) + delta));
      if (state._slashIndex === prev) return;
      dropdown.querySelectorAll(".slash-item").forEach((el) => {
        el.classList.toggle("slash-item--sel", parseInt(el.dataset.index, 10) === state._slashIndex);
      });
      // scroll selected item into view
      const sel = dropdown.querySelector(".slash-item--sel");
      if (sel) sel.scrollIntoView({ block: "nearest" });
    }

    function commitSlashSelection() {
      const dropdown = byId("slashSuggest");
      if (!dropdown || !state._slashCount) return false;
      const sel = dropdown.querySelector(".slash-item--sel");
      if (sel) { selectSlashItem(sel.dataset.skill); return true; }
      return false;
    }

    async function loadMemoryContext() {
      try {
        state.memoryContext = await apiJson("/api/memory-context");
      } catch {
        state.memoryContext = { found: false, content: null };
      }
      updateMemoryContextIndicator();
      return state.memoryContext;
    }

    function updateMemoryContextIndicator() {
      const panel = byId("memoryContextInfo");
      if (!panel) return;
      const count = state.memoryContext?.count || 0;
      if (state.memoryContext?.found && count > 0) {
        panel.innerHTML = `<span class="ctx-badge ctx-memory">🧠 ${t("longTermMemory")}</span><span class="ctx-hint">${t("memoryContextCount", { count })}</span>`;
      } else {
        panel.innerHTML = `<span class="ctx-badge muted">${t("noMemoryContext")}</span><span class="ctx-hint">${t("memoryContextHint")}</span>`;
      }
      panel.style.display = "flex";
    }

    async function showMemoryPanel() {
      els.memoryModal.classList.remove("hidden");
      els.memoryName.value = "";
      els.memoryDesc.value = "";
      els.memoryBody.value = "";
      await renderMemoryList();
    }

    function hideMemoryPanel() {
      els.memoryModal.classList.add("hidden");
    }

    async function renderMemoryList() {
      try {
        const data = await apiJson("/api/memory");
        const memories = data.data || [];
        if (!memories.length) {
          els.memoryList.innerHTML = `<div class="muted-line" style="padding:12px;">${t("noMemory")}</div>`;
          return;
        }
        els.memoryList.innerHTML = memories.map((memory) => `<div class="memory-item">
          <span class="memory-item-name">${escapeHtml(memory.name)}</span>
          <button class="memory-item-btn" data-memory-edit="${escapeHtml(memory.name)}">${t("edit")}</button>
          <button class="memory-item-btn danger" data-memory-delete="${escapeHtml(memory.name)}">${t("delete")}</button>
          ${memory.description ? `<span class="memory-item-desc">${escapeHtml(memory.description)}</span>` : ""}
        </div>`).join("");
        els.memoryList.querySelectorAll("[data-memory-edit]").forEach((button) => {
          button.addEventListener("click", () => editMemory(button.dataset.memoryEdit));
        });
        els.memoryList.querySelectorAll("[data-memory-delete]").forEach((button) => {
          button.addEventListener("click", () => {
            documentRef.querySelector(".key-delete-confirm")?.remove();
            const name = button.dataset.memoryDelete;
            const confirm = documentRef.createElement("div");
            confirm.className = "key-delete-confirm";
            confirm.innerHTML = `<span>${t("deleteMemoryMsg").replace("{name}", escapeHtml(name))}</span>
              <button class="key-confirm-yes" type="button">${t("confirmDelete")}</button>
              <button class="key-confirm-no" type="button">${t("cancel")}</button>`;
            button.closest(".memory-item")?.after(confirm);
            confirm.querySelector(".key-confirm-yes").addEventListener("click", () => {
              confirm.remove();
              deleteMemory(name);
            });
            confirm.querySelector(".key-confirm-no").addEventListener("click", () => confirm.remove());
          });
        });
      } catch (error) {
        els.memoryList.innerHTML = `<div class="muted-line" style="padding:12px;">${t("loadFailed")}：${escapeHtml(error.message)}</div>`;
      }
    }

    async function editMemory(name) {
      try {
        const memory = await apiJson(`/api/memory?file=${encodeURIComponent(name)}`);
        els.memoryName.value = memory.name || "";
        els.memoryDesc.value = (memory.meta || {}).description || "";
        els.memoryBody.value = memory.body || "";
      } catch (error) {
        showToast(`${t("readMemoryFailed")}：${error.message}`, "error");
      }
    }

    async function deleteMemory(name) {
      try {
        await apiJson(`/api/memory?file=${encodeURIComponent(name)}`, { method: "DELETE" });
        await renderMemoryList();
        await loadMemoryContext();
        onMemoryChanged();
      } catch (error) {
        showToast(`${t("deleteFailed")}：${error.message}`, "error");
      }
    }

    async function saveMemorySubmit() {
      const name = els.memoryName.value.trim();
      const description = els.memoryDesc.value.trim();
      const body = els.memoryBody.value.trim();
      if (!name) {
        showToast(t("enterMemoryName"), "warning");
        return;
      }
      if (!body) {
        showToast(t("enterMemoryBody"), "warning");
        return;
      }
      try {
        await apiJson("/api/memory", {
          method: "POST",
          body: JSON.stringify({ name, meta: { description }, body }),
        });
        els.memoryName.value = "";
        els.memoryDesc.value = "";
        els.memoryBody.value = "";
        await renderMemoryList();
        await loadMemoryContext();
        onMemoryChanged();
      } catch (error) {
        showToast(`${t("saveFailed")}：${error.message}`, "error");
      }
    }

    function renderMemoryPanel(container) {
      state._editingMemory = null;
      container.innerHTML = `<h3 style="margin:0 0 14px" data-i18n="memory">${t("memory")}</h3><div id="settingsMemoryList" class="memory-list" style="max-height:300px; overflow:auto"></div>
        <div id="settingsMemoryForm" class="memory-form">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;height:24px">
            <span id="memFormLabel" style="font-weight:700;font-size:13px;color:var(--text)" data-i18n="newMemory">${t("newMemory")}</span>
            <button id="memCancelBtn" class="mini-btn" type="button" style="visibility:hidden" data-i18n="cancel">${t("cancel")}</button>
          </div>
          <input id="settingsMemName" placeholder="${t("memNamePlaceholder")}" data-i18n="memNamePlaceholder" autocomplete="off" />
          <input id="settingsMemDesc" placeholder="${t("memDescPlaceholder")}" data-i18n="memDescPlaceholder" autocomplete="off" />
          <textarea id="settingsMemBody" rows="5" placeholder="${t("memBodyPlaceholder")}" data-i18n="memBodyPlaceholder" spellcheck="false"></textarea>
          <div class="memory-form-actions"><button id="settingsSaveMem" class="mini-btn" type="button" data-i18n="save">${t("save")}</button></div>
        </div>`;
      refreshSettingsMemoryList();
      byId("settingsSaveMem").addEventListener("click", async () => {
        const name = byId("settingsMemName").value.trim();
        const description = byId("settingsMemDesc").value.trim();
        const body = byId("settingsMemBody").value.trim();
        if (!name || !body || !/^[a-zA-Z0-9_-]+$/.test(name)) {
          showToast(t("fillRequired"), "error");
          return;
        }
        if (state._editingMemory && state._editingMemory !== name) {
          try {
            await apiJson(`/api/memory?file=${encodeURIComponent(state._editingMemory)}`, { method: "DELETE" });
          } catch (_) { /* continue by creating the requested name */ }
        }
        await apiJson("/api/memory", {
          method: "POST",
          body: JSON.stringify({ name, meta: { description }, body }),
        });
        clearMemoryForm();
        refreshSettingsMemoryList();
        loadMemoryContext();
      });
      byId("memCancelBtn").addEventListener("click", clearMemoryForm);
    }

    function clearMemoryForm() {
      state._editingMemory = null;
      byId("settingsMemName").value = "";
      byId("settingsMemDesc").value = "";
      byId("settingsMemBody").value = "";
      byId("memFormLabel").dataset.i18n = "newMemory";
      byId("memFormLabel").textContent = t("newMemory");
      byId("memCancelBtn").style.visibility = "hidden";
      byId("settingsMemName").disabled = false;
    }

    async function refreshSettingsMemoryList() {
      const list = byId("settingsMemoryList");
      if (!list) return;
      const requestId = ++settingsMemoryRequestId;
      list.innerHTML = `<div class="settings-memory-state is-loading" role="status"><span class="settings-memory-spinner" aria-hidden="true"></span><span data-i18n="loadingMemories">${t("loadingMemories")}</span></div>`;
      try {
        const data = await apiJson("/api/memory");
        if (requestId !== settingsMemoryRequestId || byId("settingsMemoryList") !== list) return;
        const memories = data.data || [];
        list.innerHTML = memories.length ? memories.map((memory) => `<div class="memory-item ${state._editingMemory === memory.name ? "editing" : ""}" data-name="${escapeHtml(memory.name)}">
          <span class="memory-item-name">${escapeHtml(memory.name)}</span>
          ${memory.description ? `<span class="memory-item-desc">${escapeHtml(memory.description)}</span>` : "<span></span>"}
          <div class="memory-item-actions">
            <button class="memory-item-btn" data-edit="${escapeHtml(memory.name)}" title="${t("edit")}" data-i18n-title="edit">${editIcon()}</button>
            <button class="memory-item-btn danger" data-del="${escapeHtml(memory.name)}" title="${t("delete")}" data-i18n-title="delete">${trashIcon()}</button>
          </div>
        </div>`).join("") : `<div class="muted-line" style="padding:12px" data-i18n="noMemory">${t("noMemory")}</div>`;
        list.querySelectorAll("[data-edit]").forEach((button) => button.addEventListener("click", async () => {
          const memory = await apiJson(`/api/memory?file=${encodeURIComponent(button.dataset.edit)}`);
          state._editingMemory = memory.name;
          byId("settingsMemName").value = memory.name || "";
          byId("settingsMemName").disabled = true;
          byId("settingsMemDesc").value = (memory.meta || {}).description || "";
          byId("settingsMemBody").value = memory.body || "";
          byId("memFormLabel").removeAttribute("data-i18n");
          byId("memFormLabel").textContent = t("editingMemory", { name: memory.name });
          byId("memCancelBtn").style.visibility = "";
          list.querySelectorAll(".memory-item").forEach((element) => {
            element.classList.toggle("editing", element.dataset.name === memory.name);
          });
        }));
        list.querySelectorAll("[data-del]").forEach((button) => button.addEventListener("click", () => {
          const item = button.closest(".memory-item");
          const name = button.dataset.del;
          documentRef.querySelector(".key-delete-confirm")?.remove();
          const confirm = documentRef.createElement("div");
          confirm.className = "key-delete-confirm";
          confirm.innerHTML = `<span data-settings-delete-name="${escapeHtml(name)}">${t("deleteConfirmMsg", { name: escapeHtml(name) })}</span>
            <button class="key-confirm-yes" type="button" data-i18n="confirmDelete">${t("confirmDelete")}</button>
            <button class="key-confirm-no" type="button" data-i18n="cancel">${t("cancel")}</button>`;
          item.after(confirm);
          confirm.querySelector(".key-confirm-yes").addEventListener("click", async () => {
            confirm.remove();
            await apiJson(`/api/memory?file=${encodeURIComponent(name)}`, { method: "DELETE" });
            if (state._editingMemory === name) clearMemoryForm();
            refreshSettingsMemoryList();
            loadMemoryContext();
          });
          confirm.querySelector(".key-confirm-no").addEventListener("click", () => confirm.remove());
        }));
      } catch (error) {
        if (requestId !== settingsMemoryRequestId || byId("settingsMemoryList") !== list) return;
        list.innerHTML = `<div class="settings-memory-state is-error" role="alert"><span><span data-i18n="memoryLoadFailed">${t("memoryLoadFailed")}</span>：${escapeHtml(error.message || "")}</span><button id="settingsMemoryRetry" class="mini-btn" type="button" data-i18n="retry">${t("retry")}</button></div>`;
        byId("settingsMemoryRetry")?.addEventListener("click", refreshSettingsMemoryList);
      }
    }

    function renderSkillsInSettings(container) {
      container.innerHTML = `<div class="skills-panel-heading">
          <h3 data-i18n="skills">${t("skills")}</h3>
          <button id="settingsSkillDependencyRefresh" class="mini-btn skill-dependency-refresh" type="button" data-i18n="skillDependencyCheck">${t("skillDependencyCheck")}</button>
        </div>
        <div id="settingsSkillDependencyOverview" class="skill-dependency-overview" aria-live="polite"></div>
        <div class="skills-layout-inner">
          <div class="skills-sidebar-inner">
            <button id="settingsSkillAddBtn" style="display:flex;align-items:center;gap:4px;width:100%;padding:5px 12px;border:0;border-left:3px solid transparent;border-radius:0;background:transparent;color:var(--accent);font-size:13px;font-weight:600;cursor:pointer;flex-shrink:0" data-i18n="newSkill">+ 新建 Skill</button>
            <div id="settingsSkillsSidebar" class="skill-list-scroll" style="padding:4px 0"></div>
          </div>
          <div class="skills-detail-inner" id="settingsSkillsDetail"></div>
        </div>`;
      renderSkillDependencyOverview();
      renderSettingsSkillsSidebar();
      byId("settingsSkillAddBtn").addEventListener("click", () => openSkillEditor(null));
      byId("settingsSkillDependencyRefresh").addEventListener("click", () => {
        loadSkillDependencyStatus({ force: true });
      });
      if (!skillDependencySnapshot && !skillDependencyLoading) loadSkillDependencyStatus();
      loadSkillDependencyOperations();
    }

    function refreshSettingsLanguage(panel) {
      if (panel === "memory") {
        const label = byId("memFormLabel");
        if (label) {
          if (state._editingMemory) {
            label.removeAttribute("data-i18n");
            label.textContent = t("editingMemory", { name: state._editingMemory });
          } else {
            label.dataset.i18n = "newMemory";
            label.textContent = t("newMemory");
          }
        }
        return;
      }
      if (panel !== "skills") return;
      const sidebar = byId("settingsSkillsSidebar");
      const scrollTop = sidebar?.scrollTop || 0;
      renderSkillDependencyOverview();
      renderSettingsSkillsSidebar(settingsSelectedSkillName);
      if (sidebar) sidebar.scrollTop = scrollTop;
    }

    function dependencyStatusLabel(status) {
      if (status === "ready") return t("skillDependencyReady");
      if (status === "partial") return t("skillDependencyPartial");
      return t("skillDependencyUnavailable");
    }

    function dependencyCapabilityLabel(capabilityId) {
      if (capabilityId === "*") return t("skillDependencyAllCapabilities");
      const key = DEPENDENCY_CAPABILITY_KEYS[capabilityId];
      return key ? t(key) : capabilityId;
    }

    function renderSkillDependencyOverview() {
      const overview = byId("settingsSkillDependencyOverview");
      const refresh = byId("settingsSkillDependencyRefresh");
      if (!overview) return;
      if (refresh) refresh.disabled = skillDependencyLoading;
      if (skillDependencyLoading) {
        overview.className = "skill-dependency-overview is-loading";
        overview.textContent = t("skillDependencyChecking");
        return;
      }
      if (skillDependencyError) {
        overview.className = "skill-dependency-overview is-error";
        overview.textContent = t("skillDependencyProbeFailed", { error: skillDependencyError });
        return;
      }
      if (!skillDependencySnapshot) {
        overview.className = "skill-dependency-overview";
        overview.textContent = "";
        return;
      }
      const summary = skillDependencySnapshot.summary || {};
      overview.className = "skill-dependency-overview is-ready";
      overview.textContent = t("skillDependencySummary", {
        declared: summary.declared || 0,
        ready: summary.ready || 0,
        partial: summary.partial || 0,
        unavailable: summary.unavailable || 0,
      });
      const errorCount = Array.isArray(skillDependencySnapshot.errors) ? skillDependencySnapshot.errors.length : 0;
      if (errorCount) overview.textContent += ` · ${t("skillDependencyManifestErrors", { count: errorCount })}`;
    }

    function renderDependencyRequirement(requirement, optional) {
      const available = Boolean(requirement.available);
      const version = requirement.detectedVersion ? ` ${requirement.detectedVersion}` : "";
      const stateLabel = available ? t("skillDependencySatisfied") : t("skillDependencyMissing");
      const kindLabel = optional ? t("skillDependencyOptional") : t("skillDependencyRequired");
      const title = `${kindLabel} · ${stateLabel}`;
      return `<span class="skill-dependency-chip ${available ? "is-ready" : "is-missing"}${optional ? " is-optional" : ""}" title="${escapeHtml(title)}">
        <span class="skill-dependency-chip-name">${escapeHtml(requirement.name || requirement.id || "-")}</span>${version ? `<span class="skill-dependency-chip-version">${escapeHtml(version)}</span>` : ""}
      </span>`;
    }

    function dependencyOperationKey(skillName, capabilityId) {
      return `${skillName}\u0000${capabilityId}`;
    }

    function dependencyActionLabel(action) {
      return t(DEPENDENCY_ACTION_KEYS[action] || "skillDependencyInstall");
    }

    function isActiveDependencyOperation(operation) {
      return Boolean(operation && ACTIVE_DEPENDENCY_OPERATION_STATUSES.has(operation.status));
    }

    function activeDependencyOperation() {
      return [...skillDependencyOperationByKey.values()].find(isActiveDependencyOperation) || null;
    }

    function rememberDependencyOperation(operation) {
      if (!operation?.id || !operation.skill || !operation.capability) return;
      const key = dependencyOperationKey(operation.skill, operation.capability);
      const current = skillDependencyOperationByKey.get(key);
      if (
        current
        && current.id !== operation.id
        && String(current.createdAt || "") > String(operation.createdAt || "")
      ) return;
      if (current?.id === operation.id && Number(current.version || 0) > Number(operation.version || 0)) return;
      skillDependencyOperationByKey.set(key, operation);
    }

    function forgetDependencyOperation(operationId) {
      for (const [key, operation] of skillDependencyOperationByKey.entries()) {
        if (operation?.id === operationId) skillDependencyOperationByKey.delete(key);
      }
    }

    function dependencyOperationStatusLabel(operation) {
      if (operation?.phase === "cancelling") return t("skillDependencyOperationCancelling");
      if (operation?.phase === "rechecking") return t("skillDependencyOperationRechecking");
      if (operation?.status === "completed") return t("skillDependencyOperationCompleted");
      if (operation?.status === "failed") return t("statusFail");
      if (operation?.status === "cancelled") return t("skillDependencyOperationCancelled");
      if (operation?.status === "pending") return t("skillDependencyOperationPending");
      return t("skillDependencyOperationRunning");
    }

    function renderDependencySystemHints(required) {
      const missingCommands = required.filter((item) => item.type === "command" && !item.available);
      if (!missingCommands.length) return "";
      return `<div class="skill-dependency-system-hints">
        <div class="skill-dependency-system-title">${escapeHtml(t("skillDependencySystemHintTitle"))}</div>
        ${missingCommands.map((item) => `<div class="skill-dependency-system-hint">
          <span>${escapeHtml(item.name || item.id || "-")}</span>
          <code>${escapeHtml(item.installHint || t("skillDependencySystemHintFallback"))}</code>
        </div>`).join("")}
      </div>`;
    }

    function renderDependencyPlanPreview(skillName, capabilityId) {
      const preview = skillDependencyPreview;
      if (!preview || preview.skill !== skillName || preview.capability !== capabilityId) return "";
      const actionLabel = capabilityId === "*"
        ? t("skillDependencyInstallAll")
        : dependencyActionLabel(preview.action);
      if (preview.loading) {
        return `<div class="skill-dependency-operation-plan is-loading" role="status">${escapeHtml(t("skillDependencyPlanLoading"))}</div>`;
      }
      if (preview.error) {
        return `<div class="skill-dependency-operation-plan is-error" role="alert">
          <div>${escapeHtml(t("skillDependencyOperationFailed", { error: preview.error }))}</div>
          <div class="skill-dependency-operation-actions">
            <button class="mini-btn" type="button" data-dependency-plan-close>${escapeHtml(t("skillDependencyCancelAction"))}</button>
          </div>
        </div>`;
      }
      const plan = preview.plan;
      if (!plan) return "";
      const managedTypes = new Set((plan.requirements || [])
        .filter((item) => item.type === "python" || item.type === "node")
        .map((item) => item.type));
      const locations = [...managedTypes].map((type) => `<div><span>${type === "python" ? "Python" : "Node"}</span><code>${escapeHtml(plan.locations?.[type] || "-")}</code></div>`).join("");
      const commands = (plan.commandSummaries || []).map((command) => `<code>${escapeHtml(command)}</code>`).join("");
      const notice = plan.blockedReasons?.length
        ? `<div class="skill-dependency-plan-notice is-error">${escapeHtml(t("skillDependencyOperationBlocked"))}</div>`
        : (plan.noChanges ? `<div class="skill-dependency-plan-notice">${escapeHtml(t("skillDependencyNoManagedChanges"))}</div>` : "");
      return `<div class="skill-dependency-operation-plan">
        <div class="skill-dependency-operation-plan-head"><strong>${escapeHtml(t("skillDependencyPlanTitle"))}</strong><span>${escapeHtml(actionLabel)}</span></div>
        <dl>
          <div><dt>${escapeHtml(t("skillDependencyTargetCapability"))}</dt><dd>${escapeHtml(dependencyCapabilityLabel(capabilityId))}</dd></div>
          <div><dt>${escapeHtml(t("skillDependencyInstallLocation"))}</dt><dd class="skill-dependency-plan-locations">${locations || "-"}</dd></div>
          <div><dt>${escapeHtml(t("skillDependencyCommandSummary"))}</dt><dd class="skill-dependency-plan-commands">${commands || "-"}</dd></div>
          <div><dt>${escapeHtml(t("skillDependencyAuthorizationScope"))}</dt><dd>${escapeHtml(t("skillDependencyAuthorizationManagedOnly"))}</dd></div>
        </dl>
        ${preview.action === "uninstall" ? `<div class="skill-dependency-plan-notice">${escapeHtml(t("skillDependencySharedPreserved"))}</div>` : ""}
        ${capabilityId === "*" && (plan.systemRequirements || []).some((item) => !item.available) ? `<div class="skill-dependency-plan-notice">${escapeHtml(t("skillDependencySystemExcluded"))}</div>` : ""}
        ${notice}
        <div class="skill-dependency-operation-actions">
          <button class="mini-btn primary-btn" type="button" data-dependency-plan-confirm ${!plan.actionable || preview.confirming ? "disabled" : ""}>${escapeHtml(t("skillDependencyConfirmAction"))}</button>
          <button class="mini-btn" type="button" data-dependency-plan-close ${preview.confirming ? "disabled" : ""}>${escapeHtml(t("skillDependencyCancelAction"))}</button>
        </div>
      </div>`;
    }

    function renderDependencyOperationState(skillName, capabilityId) {
      const operation = skillDependencyOperationByKey.get(dependencyOperationKey(skillName, capabilityId));
      if (!operation) return "";
      const active = isActiveDependencyOperation(operation);
      const rechecking = skillDependencyOperationRechecks.has(operation.id);
      const progress = Math.max(0, Math.min(100, Number(operation.progress || 0)));
      const total = Number(operation.totalSteps || 0);
      const done = Number(operation.completedSteps || 0);
      const statusClass = active ? "is-running" : `is-${escapeHtml(operation.status || "failed")}`;
      const operationError = operation.errorCode === "operation_unavailable"
        ? t("skillDependencyOperationUnavailable")
        : (operation.error || operation.errorCode || t("statusFail"));
      const failure = operation.status === "failed"
        ? `<div class="skill-dependency-operation-error">${escapeHtml(t("skillDependencyOperationFailed", { error: operationError }))}</div>`
        : "";
      const recovery = operation.retryable
        ? `<div class="skill-dependency-recovery-hint">${escapeHtml(t("skillDependencyRecoveryHint"))}</div>`
        : "";
      return `<div class="skill-dependency-operation-state ${statusClass}" aria-live="polite">
        <div class="skill-dependency-operation-state-head">
          <strong>${escapeHtml(operation.capability === "*" ? t("skillDependencyInstallAll") : dependencyActionLabel(operation.action))}</strong>
          <span>${escapeHtml(dependencyOperationStatusLabel(operation))}</span>
        </div>
        <div class="skill-dependency-progress"><span style="width:${progress}%"></span></div>
        ${total ? `<div class="skill-dependency-operation-meta">${escapeHtml(t("skillDependencyOperationProgress", { done, total }))}</div>` : ""}
        ${operation.currentCommand ? `<code class="skill-dependency-current-command">${escapeHtml(operation.currentCommand)}</code>` : ""}
        ${failure}${recovery}
        <div class="skill-dependency-operation-actions">
          ${active ? `<button class="mini-btn" type="button" data-dependency-operation-cancel="${escapeHtml(operation.id)}" ${operation.cancelRequested ? "disabled" : ""}>${escapeHtml(t("skillDependencyCancelOperation"))}</button>` : ""}
          ${operation.retryable ? `<button class="mini-btn" type="button" data-dependency-operation-retry="${escapeHtml(operation.action)}">${escapeHtml(t("skillDependencyRetryOperation"))}</button>` : ""}
          ${!active ? `<button class="mini-btn" type="button" data-dependency-operation-recheck="${escapeHtml(operation.id)}" ${rechecking ? "disabled" : ""}>${escapeHtml(t(rechecking ? "skillDependencyChecking" : "skillDependencyCheck"))}</button>` : ""}
        </div>
      </div>`;
    }

    function renderSkillDependencySection(skillName) {
      const dependency = skillDependencyByName.get(skillName);
      if (!dependency) return "";
      const capabilities = Array.isArray(dependency.capabilities) ? dependency.capabilities : [];
      const allRequiredManaged = capabilities.flatMap((capability) => (
        Array.isArray(capability.required) ? capability.required : []
      )).filter((item) => item.type === "python" || item.type === "node");
      const allRequiredManagedMissing = allRequiredManaged.some((item) => !item.available);
      const operationRunning = Boolean(activeDependencyOperation());
      const detectedFrom = Array.isArray(dependency.detectedFrom) ? dependency.detectedFrom : [];
      const detectedTitle = detectedFrom.length
        ? t("skillDependencyDetectedFrom", { sources: detectedFrom.join("、") })
        : t("skillDependencyDetectedHint");
      return `<section class="skill-dependency-card">
        <div class="skill-dependency-card-head">
          <div class="skill-detail-label">${t("skillDependencyTitle")}</div>
          <div class="skill-dependency-card-meta">
            ${allRequiredManaged.length ? `<button class="mini-btn" type="button" data-dependency-install-all ${!allRequiredManagedMissing || operationRunning ? "disabled" : ""}>${escapeHtml(t(allRequiredManagedMissing ? "skillDependencyInstallAll" : "skillDependencyAllManagedReady"))}</button>` : ""}
            ${dependency.manifestSource === "detected" ? `<span class="skill-dependency-source" title="${escapeHtml(detectedTitle)}">${escapeHtml(t("skillDependencyDetected"))}</span>` : ""}
            <span class="skill-dependency-status is-${escapeHtml(dependency.status)}">${escapeHtml(dependencyStatusLabel(dependency.status))}</span>
          </div>
        </div>
        ${renderDependencyPlanPreview(skillName, "*")}
        ${renderDependencyOperationState(skillName, "*")}
        <div class="skill-capability-list">${capabilities.map((capability) => {
          const required = Array.isArray(capability.required) ? capability.required : [];
          const optional = Array.isArray(capability.optional) ? capability.optional : [];
          const managedRequirements = [...required, ...optional]
            .filter((item) => item.type === "python" || item.type === "node");
          const missingRequiredManaged = required
            .some((item) => (item.type === "python" || item.type === "node") && !item.available);
          const missingOptionalManaged = optional
            .some((item) => (item.type === "python" || item.type === "node") && !item.available);
          const missingManaged = missingRequiredManaged || missingOptionalManaged;
          const installActionKey = !missingRequiredManaged && missingOptionalManaged
            ? "skillDependencyInstallOptional"
            : "skillDependencyInstall";
          const managedInstalled = managedRequirements.some((item) => item.source === "managed");
          return `<div class="skill-capability-row" data-dependency-capability="${escapeHtml(capability.id)}">
            <div class="skill-capability-head">
              <span class="skill-capability-name">${escapeHtml(dependencyCapabilityLabel(capability.id))}</span>
              <span class="skill-capability-status is-${capability.status === "ready" ? "ready" : "unavailable"}">${escapeHtml(dependencyStatusLabel(capability.status))}</span>
            </div>
            <div class="skill-dependency-chips">
              ${required.map((item) => renderDependencyRequirement(item, false)).join("")}
              ${optional.map((item) => renderDependencyRequirement(item, true)).join("")}
            </div>
            ${renderDependencySystemHints([...required, ...optional])}
            ${managedRequirements.length ? `<div class="skill-dependency-capability-actions">
              <button class="mini-btn" type="button" data-dependency-action="install" ${!missingManaged || operationRunning ? "disabled" : ""}>${escapeHtml(t(installActionKey))}</button>
              <button class="mini-btn" type="button" data-dependency-action="repair" ${operationRunning ? "disabled" : ""}>${escapeHtml(t("skillDependencyRepair"))}</button>
              <button class="mini-btn danger" type="button" data-dependency-action="uninstall" ${!managedInstalled || operationRunning ? "disabled" : ""}>${escapeHtml(t("skillDependencyUninstall"))}</button>
            </div>` : ""}
            ${renderDependencyPlanPreview(skillName, capability.id)}
            ${renderDependencyOperationState(skillName, capability.id)}
          </div>`;
        }).join("")}</div>
      </section>`;
    }

    async function loadSkillDependencyStatus({ force = false } = {}) {
      if (skillDependencyLoading) return skillDependencySnapshot;
      if (skillDependencySnapshot && !force) return skillDependencySnapshot;
      const requestId = ++skillDependencyRequestId;
      skillDependencyLoading = true;
      skillDependencyError = "";
      renderSkillDependencyOverview();
      try {
        const snapshot = await apiJson("/api/skills/dependencies");
        if (requestId !== skillDependencyRequestId) return skillDependencySnapshot;
        if (!snapshot || !Array.isArray(snapshot.skills) || !snapshot.summary) {
          throw new Error(t("skillDependencyInvalidResponse"));
        }
        skillDependencySnapshot = snapshot;
        skillDependencyByName = new Map(snapshot.skills.map((item) => [item.name, item]));
      } catch (error) {
        if (requestId !== skillDependencyRequestId) return skillDependencySnapshot;
        skillDependencyError = error?.message || String(error || t("fetchFailed"));
      } finally {
        if (requestId === skillDependencyRequestId) {
          skillDependencyLoading = false;
          renderSkillDependencyOverview();
          renderSettingsSkillsSidebar(settingsSelectedSkillName);
        }
      }
      return skillDependencySnapshot;
    }

    function recalculateSkillDependencySummary() {
      if (!skillDependencySnapshot) return;
      const skills = Array.isArray(skillDependencySnapshot.skills) ? skillDependencySnapshot.skills : [];
      skillDependencySnapshot.summary = {
        declared: skills.length,
        ready: skills.filter((item) => item.status === "ready").length,
        partial: skills.filter((item) => item.status === "partial").length,
        unavailable: skills.filter((item) => item.status === "unavailable").length,
      };
    }

    function renderSelectedSkillDependencyDetail() {
      const skill = (state.skills || []).find((item) => item.name === settingsSelectedSkillName);
      if (skill) showSkillDetailInSettings(skill);
    }

    function applySingleSkillDependencyStatus(dependency) {
      if (!dependency?.name) return;
      skillDependencyByName.set(dependency.name, dependency);
      if (skillDependencySnapshot) {
        const skills = Array.isArray(skillDependencySnapshot.skills) ? skillDependencySnapshot.skills : [];
        const index = skills.findIndex((item) => item.name === dependency.name);
        if (index >= 0) skills[index] = dependency;
        else skills.push(dependency);
        skillDependencySnapshot.skills = skills;
        recalculateSkillDependencySummary();
      }
      renderSkillDependencyOverview();
      const sidebar = byId("settingsSkillsSidebar");
      const scrollTop = sidebar?.scrollTop || 0;
      renderSettingsSkillsSidebar(settingsSelectedSkillName);
      if (sidebar) sidebar.scrollTop = scrollTop;
    }

    async function refreshSingleSkillDependencyStatus(skillName) {
      try {
        const dependency = await apiJson(`/api/skills/${encodeURIComponent(skillName)}/dependencies`);
        applySingleSkillDependencyStatus(dependency);
        return dependency;
      } catch (error) {
        showToast(t("skillDependencyProbeFailed", { error: error?.message || String(error || "") }), "error");
        return null;
      }
    }

    async function pollSkillDependencyOperation(operationId) {
      if (!operationId || skillDependencyOperationPollers.has(operationId)) return;
      skillDependencyOperationPollers.add(operationId);
      try {
        let operation = [...skillDependencyOperationByKey.values()].find((item) => item.id === operationId);
        while (isActiveDependencyOperation(operation)) {
          try {
            const snapshot = await apiJson(`/api/skills/dependencies/operations/${encodeURIComponent(operationId)}?version=${Number(operation.version || 0)}&wait=20`);
            rememberDependencyOperation(snapshot);
            operation = snapshot;
            if (operation.skill === settingsSelectedSkillName) renderSelectedSkillDependencyDetail();
          } catch (_) {
            try {
              const response = await apiJson("/api/skills/dependencies/operations");
              const recovered = (response?.operations || []).find((item) => item.id === operationId);
              if (recovered) {
                rememberDependencyOperation(recovered);
                operation = recovered;
                continue;
              }
              operation = {
                ...operation,
                status: "failed",
                phase: "failed",
                retryable: true,
                errorCode: "operation_unavailable",
                error: "",
                version: Number(operation.version || 0) + 1,
              };
              rememberDependencyOperation(operation);
              renderSelectedSkillDependencyDetail();
              break;
            } catch (_) {
              await new Promise((resolve) => global.setTimeout(resolve, 1000));
            }
          }
        }
        if (operation?.result?.dependency) {
          applySingleSkillDependencyStatus(operation.result.dependency);
        } else if (operation?.skill) {
          await refreshSingleSkillDependencyStatus(operation.skill);
        }
      } finally {
        skillDependencyOperationPollers.delete(operationId);
      }
    }

    async function loadSkillDependencyOperations() {
      if (skillDependencyOperationsLoading || skillDependencyOperationsLoaded) return;
      skillDependencyOperationsLoading = true;
      try {
        const response = await apiJson("/api/skills/dependencies/operations");
        const operations = Array.isArray(response?.operations) ? response.operations : [];
        operations.forEach(rememberDependencyOperation);
        skillDependencyOperationsLoaded = true;
        renderSelectedSkillDependencyDetail();
        operations.filter(isActiveDependencyOperation).forEach((operation) => {
          pollSkillDependencyOperation(operation.id);
        });
      } catch (_) {
        skillDependencyOperationsLoaded = false;
      } finally {
        skillDependencyOperationsLoading = false;
      }
    }

    async function openSkillDependencyPlan(skillName, capability, action) {
      const requestId = ++skillDependencyPreviewRequestId;
      skillDependencyPreview = { skill: skillName, capability, action, loading: true, confirming: false };
      renderSelectedSkillDependencyDetail();
      try {
        const plan = await apiJson("/api/skills/dependencies/plan", {
          method: "POST",
          body: JSON.stringify({ skill: skillName, capability, action }),
        });
        if (requestId !== skillDependencyPreviewRequestId) return;
        skillDependencyPreview = { skill: skillName, capability, action, plan, loading: false, confirming: false };
      } catch (error) {
        if (requestId !== skillDependencyPreviewRequestId) return;
        skillDependencyPreview = {
          skill: skillName,
          capability,
          action,
          loading: false,
          confirming: false,
          error: error?.message || String(error || t("statusFail")),
        };
      }
      if (skillName === settingsSelectedSkillName) renderSelectedSkillDependencyDetail();
    }

    async function startSkillDependencyOperation() {
      const preview = skillDependencyPreview;
      if (!preview?.plan?.actionable || preview.confirming) return;
      preview.confirming = true;
      renderSelectedSkillDependencyDetail();
      try {
        const operation = await apiJson("/api/skills/dependencies/operations", {
          method: "POST",
          body: JSON.stringify({
            skill: preview.skill,
            capability: preview.capability,
            action: preview.action,
            fingerprint: preview.plan.fingerprint,
          }),
        });
        rememberDependencyOperation(operation);
        skillDependencyPreview = null;
        renderSelectedSkillDependencyDetail();
        pollSkillDependencyOperation(operation.id);
      } catch (error) {
        if (skillDependencyPreview === preview) {
          preview.confirming = false;
          preview.error = error?.message || String(error || t("statusFail"));
          renderSelectedSkillDependencyDetail();
        }
      }
    }

    async function cancelSkillDependencyOperation(operationId) {
      try {
        const operation = await apiJson(`/api/skills/dependencies/operations/${encodeURIComponent(operationId)}`, {
          method: "DELETE",
        });
        rememberDependencyOperation(operation);
        renderSelectedSkillDependencyDetail();
        pollSkillDependencyOperation(operation.id);
      } catch (error) {
        showToast(t("skillDependencyOperationFailed", { error: error?.message || String(error || "") }), "error");
      }
    }

    async function recheckAndDismissSkillDependencyOperation(skillName, operationId) {
      if (!operationId || skillDependencyOperationRechecks.has(operationId)) return;
      skillDependencyOperationRechecks.add(operationId);
      renderSelectedSkillDependencyDetail();
      try {
        const dependency = await refreshSingleSkillDependencyStatus(skillName);
        if (!dependency) return;
        const operation = await apiJson(`/api/skills/dependencies/operations/${encodeURIComponent(operationId)}`, {
          method: "DELETE",
        });
        if (operation.dismissed) forgetDependencyOperation(operationId);
      } catch (error) {
        showToast(t("skillDependencyOperationFailed", { error: error?.message || String(error || "") }), "error");
      } finally {
        skillDependencyOperationRechecks.delete(operationId);
        renderSelectedSkillDependencyDetail();
      }
    }

    function bindSkillDependencyInteractions(panel, skillName) {
      panel.querySelector("[data-dependency-install-all]")?.addEventListener("click", () => {
        openSkillDependencyPlan(skillName, "*", "install");
      });
      panel.querySelectorAll("[data-dependency-action]").forEach((button) => {
        button.addEventListener("click", () => {
          const capability = button.closest("[data-dependency-capability]")?.dataset.dependencyCapability;
          if (capability) openSkillDependencyPlan(skillName, capability, button.dataset.dependencyAction);
        });
      });
      panel.querySelector("[data-dependency-plan-close]")?.addEventListener("click", () => {
        skillDependencyPreviewRequestId += 1;
        skillDependencyPreview = null;
        renderSelectedSkillDependencyDetail();
      });
      panel.querySelector("[data-dependency-plan-confirm]")?.addEventListener("click", startSkillDependencyOperation);
      panel.querySelectorAll("[data-dependency-operation-cancel]").forEach((button) => {
        button.addEventListener("click", () => cancelSkillDependencyOperation(button.dataset.dependencyOperationCancel));
      });
      panel.querySelectorAll("[data-dependency-operation-retry]").forEach((button) => {
        button.addEventListener("click", () => {
          const capability = button.closest("[data-dependency-capability]")?.dataset.dependencyCapability;
          if (capability) openSkillDependencyPlan(skillName, capability, button.dataset.dependencyOperationRetry);
        });
      });
      panel.querySelectorAll("[data-dependency-operation-recheck]").forEach((button) => {
        button.addEventListener("click", () => recheckAndDismissSkillDependencyOperation(
          skillName,
          button.dataset.dependencyOperationRecheck,
        ));
      });
    }

    function renderSettingsSkillsSidebar(preferredName = settingsSelectedSkillName) {
      const sidebar = byId("settingsSkillsSidebar");
      if (!sidebar) return;
      const sorted = sortedSkills();
      const selectedSkill = sorted.find((skill) => skill.name === preferredName) || sorted[0] || null;
      settingsSelectedSkillName = selectedSkill?.name || null;
      sidebar.innerHTML = sorted.length ? sorted.map((skill) => {
        const enabled = !state.disabledSkills.has(skill.name);
        const dependency = skillDependencyByName.get(skill.name);
        return `<div class="skill-list-item${skill.name === settingsSelectedSkillName ? " active" : ""}" data-skill-name="${escapeHtml(skill.name)}">
          <span class="dot ${enabled ? "on" : "off"}"></span><span class="skill-list-name">${escapeHtml(skill.name)}</span>
          ${dependency ? `<span class="skill-dependency-sidebar-status is-${escapeHtml(dependency.status)}" title="${escapeHtml(`${t("skillDependencyTitle")} · ${dependencyStatusLabel(dependency.status)}`)}"></span>` : ""}
        </div>`;
      }).join("") : `<div class="muted-line" style="padding:12px;font-size:12px">${t("noSkills")}</div>`;
      sidebar.querySelectorAll(".skill-list-item").forEach((item) => {
        item.addEventListener("click", () => {
          settingsSelectedSkillName = item.dataset.skillName;
          sidebar.querySelectorAll(".skill-list-item").forEach((element) => element.classList.remove("active"));
          item.classList.add("active");
          showSkillDetailInSettings(state.skills.find((skill) => skill.name === item.dataset.skillName));
        });
      });
      showSkillDetailInSettings(selectedSkill);
    }

    async function showSkillDetailInSettings(skill) {
      const panel = byId("settingsSkillsDetail");
      if (!panel) return;
      if (!skill) {
        const hasSkills = (state.skills || []).length > 0;
        panel.innerHTML = hasSkills
          ? `<div class="skills-detail-empty">${t("selectSkillHint")}</div>`
          : `<div class="skills-detail-empty"><strong>${t("newSkill")}</strong>
            <span style="margin-top:6px">${t("skillEmptyHint")}</span>
            <button class="mini-btn primary-btn" style="margin-top:12px" id="settingsEmptyCreateBtn" data-i18n="newSkill">+ 新建 Skill</button>
            <span style="margin-top:4px;font-size:11px" data-i18n="skillCreateHint">将在 data/skills/ 下创建 SKILL.md 文件</span></div>`;
        if (!hasSkills) byId("settingsEmptyCreateBtn").addEventListener("click", () => openSkillEditor(null));
        return;
      }
      await ensureSkillBody(skill);
      if (skill.name !== settingsSelectedSkillName) return;
      const enabled = !state.disabledSkills.has(skill.name);
      panel.innerHTML = `<div class="skill-detail-head">
        <div class="skill-detail-name">${escapeHtml(skill.name)}</div>
        <div class="skill-detail-head-actions">
          <label class="toggle-switch" title="${enabled ? t("enabledStatus") : t("disabledStatus")}">
            <input type="checkbox" ${enabled ? "checked" : ""} id="settingsSkillToggle" />
            <span class="toggle-track"><span class="toggle-thumb"></span></span>
          </label>
          <button class="skill-edit-icon" id="settingsSkillEdit" title="${t("edit")}">${editIcon()}</button>
        </div>
      </div>
      ${EXPLICIT_ONLY_SET.has(skill.name) ? `<div class="skill-detail-note">${t("skillExplicitHint").replace("{name}", escapeHtml(skill.name))}</div>` : ""}
      ${renderSkillDependencySection(skill.name)}
      <div class="skill-detail-section"><div class="skill-detail-label">${t("skillDesc")}</div><div class="skill-detail-value">${escapeHtml(skill.description || "-")}</div></div>
      <div class="skill-detail-section"><div class="skill-detail-label">${t("skillKeywords")}</div><div class="skill-detail-value">${escapeHtml((skill.keywords || []).join(", ") || "-")}</div></div>
      <div class="skill-detail-section"><div class="skill-detail-label">${t("skillTools")}</div><div class="skill-detail-value">${escapeHtml((skill.tools || []).join(", ") || "-")}</div></div>
      <div class="skill-detail-section"><div class="skill-detail-label">${t("skillPathLabel")}</div><div class="skill-detail-value">${escapeHtml(skill.path || `data/skills/${skill.dir || skill.name}/SKILL.md`)}</div></div>
      <div class="skill-detail-actions"><button class="skill-delete-icon" id="settingsSkillDelete" title="${t("deleteSkill")}">${t("delete")}</button></div>`;
      byId("settingsSkillToggle").addEventListener("change", () => {
        toggleSkill(skill.name);
        renderSettingsSkillsSidebar(skill.name);
      });
      byId("settingsSkillEdit").addEventListener("click", () => openSkillEditor(skill));
      byId("settingsSkillDelete").addEventListener("click", () => deleteSkillConfirm(skill.name, "settingsSkillDelete"));
      bindSkillDependencyInteractions(panel, skill.name);
    }

    function bind() {
      if (bound) return;
      bound = true;
      byId("closeSkills")?.addEventListener("click", () => byId("skillsModal").classList.add("hidden"));
      byId("skillsModal")?.addEventListener("click", (event) => {
        if (event.target === event.currentTarget) event.currentTarget.classList.add("hidden");
      });
      byId("skillAddBtn")?.addEventListener("click", () => openSkillEditor(null));
      byId("closeSkillEditor")?.addEventListener("click", closeSkillEditor);
      byId("cancelSkillEdit")?.addEventListener("click", closeSkillEditor);
      byId("saveSkillEdit")?.addEventListener("click", saveSkillEdit);
      byId("skillDependencyTemplate")?.addEventListener("click", () => {
        const input = byId("skillEditDependencies");
        if (!input || input.value.trim()) return;
        input.value = JSON.stringify({
          default: {
            required: [{ type: "python", name: "package-name" }],
            optional: [{ type: "command", name: "command-name" }],
          },
        }, null, 2);
        byId("skillDependencyEditor").open = true;
        input.focus();
      });
      byId("skillEditorModal")?.addEventListener("click", (event) => {
        if (event.target === event.currentTarget) closeSkillEditor();
      });
      els.closeMemory?.addEventListener("click", hideMemoryPanel);
      els.cancelMemory?.addEventListener("click", hideMemoryPanel);
      els.memoryModal?.addEventListener("click", (event) => {
        if (event.target === els.memoryModal) hideMemoryPanel();
      });
      els.memoryForm?.addEventListener("submit", (event) => {
        event.preventDefault();
        saveMemorySubmit();
      });
    }

    return Object.freeze({
      bind,
      ensureSkillBody,
      formatSkillInstructions,
      getMatchedSkillPrompts,
      loadMemoryContext,
      loadSkills,
      navigateSlash,
      commitSlashSelection,
      openSkillEditor,
      renderMemoryPanel,
      renderSkillsInSettings,
      refreshSettingsLanguage,
      showMemoryPanel,
      showSkillsPanel,
      showSlashSuggestions,
      updateMemoryContextIndicator,
    });
  }

  Code.features.skillsMemory = Object.freeze({
    applySkillTaskPolicy,
    classifyGoalControlInput,
    createGoalControlFeature,
    EXPLICIT_ONLY_SKILLS,
    createSkillsMemoryFeature,
    formatSkillInstructions,
    getSlashSuggestionGroups,
    getSkillToolBudgets,
    rankMatchedSkills,
  });
})(window);
