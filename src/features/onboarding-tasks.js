(function registerOnboardingTasksFeature(global) {
  "use strict";

  const Code = global.Code;
  if (!Code?.features) throw new Error("Code namespace must load before onboarding tasks feature");

  const ONBOARDING_STORAGE_KEY = "code-onboarding-tasks-v1";
  const ONBOARDING_VERSION = 2;
  const ONBOARDING_TASK_IDS = Object.freeze(["workbar", "key", "first-task"]);
  const LEGACY_V1_TASK_IDS = Object.freeze(["workbar", "key", "model", "first-task"]);
  const FIRST_TASK_EXAMPLE_KEYS = Object.freeze([
    "onboardingExampleProjectStructure",
    "onboardingExampleAnalyzeProblems",
    "onboardingExampleSmallChange",
  ]);

  function freshState() {
    return { version: ONBOARDING_VERSION, completedTaskIds: [], completed: false };
  }

  function cloneState(state) {
    return {
      version: state.version,
      completedTaskIds: [...state.completedTaskIds],
      completed: state.completed,
    };
  }

  function isOrderedPrefix(ids, taskIds) {
    return ids.length <= taskIds.length
      && ids.every((id, index) => id === taskIds[index]);
  }

  function normalizeStoredState(value) {
    if (!value || typeof value !== "object" || Array.isArray(value)) return null;
    if (value.version !== ONBOARDING_VERSION || !Array.isArray(value.completedTaskIds)) return null;
    const ids = value.completedTaskIds.map((id) => String(id || ""));
    if (!isOrderedPrefix(ids, ONBOARDING_TASK_IDS)) return null;
    const completed = value.completed === true;
    if (completed !== (ids.length === ONBOARDING_TASK_IDS.length)) return null;
    return { version: ONBOARDING_VERSION, completedTaskIds: ids, completed };
  }

  function migrateLegacyV1State(value) {
    if (!value || typeof value !== "object" || Array.isArray(value)) return null;
    if (value.version !== 1 || !Array.isArray(value.completedTaskIds)) return null;
    if (typeof value.collapsed !== "boolean") return null;
    const ids = value.completedTaskIds.map((id) => String(id || ""));
    if (!isOrderedPrefix(ids, LEGACY_V1_TASK_IDS)) return null;
    const completed = value.completed === true;
    if (completed !== (ids.length === LEGACY_V1_TASK_IDS.length)) return null;
    if (completed) {
      return {
        version: ONBOARDING_VERSION,
        completedTaskIds: [...ONBOARDING_TASK_IDS],
        completed: true,
      };
    }
    return {
      version: ONBOARDING_VERSION,
      completedTaskIds: ids.slice(0, 2),
      completed: false,
    };
  }

  function createOnboardingStateMachine(options = {}) {
    const storage = options.storage || global.localStorage;
    const storageKey = options.storageKey || ONBOARDING_STORAGE_KEY;
    const onStorageError = options.onStorageError || (() => {});
    const nonceFactory = options.nonceFactory || (() => {
      if (global.crypto?.randomUUID) return global.crypto.randomUUID();
      return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    });
    let state = freshState();
    let intent = null;
    let defaultExempt = false;

    function persist(candidate) {
      try {
        storage?.setItem(storageKey, JSON.stringify(candidate));
        return true;
      } catch (error) {
        onStorageError(error);
        return false;
      }
    }

    function initialize({ hasExistingSessions = false } = {}) {
      let parsed = null;
      let migrated = false;
      try {
        const raw = storage?.getItem(storageKey);
        if (raw != null) {
          const value = JSON.parse(raw);
          parsed = normalizeStoredState(value);
          if (!parsed) {
            parsed = migrateLegacyV1State(value);
            migrated = Boolean(parsed);
          }
        }
      } catch {
        parsed = null;
      }
      defaultExempt = !parsed && Boolean(hasExistingSessions);
      state = parsed || freshState();
      intent = null;
      if (migrated || (!parsed && !defaultExempt)) persist(state);
      return cloneState(state);
    }

    function currentTaskId() {
      if (state.completed) return null;
      return ONBOARDING_TASK_IDS[state.completedTaskIds.length] || null;
    }

    function beginIntent(taskId) {
      const normalized = String(taskId || "");
      if (normalized !== currentTaskId()) return null;
      if (intent?.taskId === normalized) return intent.id;
      intent = { id: `onboarding-${nonceFactory()}`, taskId: normalized, claimed: false };
      return intent.id;
    }

    function claimIntent(taskId) {
      if (!intent || intent.taskId !== String(taskId || "") || intent.claimed) return null;
      intent.claimed = true;
      return intent.id;
    }

    function resolveIntent(intentId, success) {
      if (!intent || intent.id !== String(intentId || "")) return false;
      const resolved = intent;
      intent = null;
      if (!success || resolved.taskId !== currentTaskId()) return false;
      const completedTaskIds = [...state.completedTaskIds, resolved.taskId];
      const candidate = {
        version: ONBOARDING_VERSION,
        completedTaskIds,
        completed: completedTaskIds.length === ONBOARDING_TASK_IDS.length,
      };
      if (!persist(candidate)) return false;
      state = candidate;
      return true;
    }

    function cancelIntent(intentId) {
      if (!intent || (intentId && intent.id !== String(intentId))) return false;
      intent = null;
      return true;
    }

    function reopen() {
      const candidate = freshState();
      if (!persist(candidate)) return false;
      state = candidate;
      defaultExempt = false;
      intent = null;
      return true;
    }

    return Object.freeze({
      beginIntent,
      cancelIntent,
      claimIntent,
      currentTaskId,
      initialize,
      isDefaultExempt: () => defaultExempt,
      migrateLegacyV1State,
      normalizeStoredState,
      pendingIntent: (taskId = "") => (
        intent && (!taskId || intent.taskId === String(taskId)) ? { ...intent } : null
      ),
      reopen,
      resolveIntent,
      snapshot: () => cloneState(state),
    });
  }

  function createOnboardingTasksFeature(options = {}) {
    const root = options.root;
    const t = options.t || ((key) => key);
    const escapeHtml = options.escapeHtml || ((value) => String(value ?? ""));
    const actions = options.actions || {};
    const hasEnabledKey = options.hasEnabledKey || (() => false);
    const getSelectedModel = options.getSelectedModel || (() => "");
    const onExampleSelected = options.onExampleSelected || (() => {});
    const onFirstTaskReady = options.onFirstTaskReady || (() => {});
    const onLayoutChange = options.onLayoutChange || (() => {});
    const onError = options.onError || (() => {});
    const completionDurationMs = Number.isFinite(Number(options.completionDurationMs))
      ? Number(options.completionDurationMs)
      : 1800;
    const machine = createOnboardingStateMachine({
      storage: options.storage || global.localStorage,
      storageKey: options.storageKey || ONBOARDING_STORAGE_KEY,
      nonceFactory: options.nonceFactory,
      onStorageError: () => onError("storage"),
    });
    let initialized = false;
    let bound = false;
    let busyTaskId = "";
    let celebrating = false;
    let completionTimer = null;
    let welcomeVisible = false;
    let firstTaskReady = false;

    const taskDefinitions = Object.freeze({
      workbar: ["onboardingWorkbarTitle", "onboardingWorkbarDescription", "onboardingVerifyWorkbar"],
      key: ["onboardingKeyTitle", "onboardingKeyDescription", "onboardingSetUpKey"],
      "first-task": ["onboardingFirstTaskTitle", "onboardingFirstTaskDescription", "onboardingChooseModel"],
    });

    function actionLabelKey(taskId) {
      if (taskId === "key" && hasEnabledKey()) return "onboardingConfirmKey";
      if (taskId === "first-task" && getSelectedModel()) return "onboardingConfirmModel";
      return taskDefinitions[taskId]?.[2] || "onboardingContinue";
    }

    function notifyLayoutChange() {
      onLayoutChange();
      global.requestAnimationFrame?.(() => onLayoutChange());
    }

    function renderExamples() {
      if (!firstTaskReady || machine.currentTaskId() !== "first-task") return "";
      const buttons = FIRST_TASK_EXAMPLE_KEYS.map((key, index) => (
        `<button class="onboarding-example" type="button" data-onboarding-example="${index}">${escapeHtml(t(key))}</button>`
      )).join("");
      return `<div class="onboarding-examples" role="group" aria-labelledby="onboardingExamplesTitle">
        <strong id="onboardingExamplesTitle">${escapeHtml(t("onboardingExamplesTitle"))}</strong>
        <span>${escapeHtml(t("onboardingExamplesHint"))}</span>
        <div class="onboarding-example-list">${buttons}</div>
      </div>`;
    }

    function render() {
      if (!root || !initialized) return;
      const state = machine.snapshot();
      const defaultExempt = machine.isDefaultExempt();
      const showTasks = welcomeVisible && !defaultExempt && !state.completed;
      const visible = celebrating || showTasks;
      root.classList.toggle("hidden", !visible);
      root.dataset.onboardingState = celebrating
        ? "complete"
        : showTasks
          ? "active"
          : defaultExempt
            ? "exempt"
            : state.completed
              ? "hidden"
              : "waiting-welcome";
      if (!visible) {
        root.innerHTML = "";
        notifyLayoutChange();
        return;
      }
      if (celebrating) {
        root.innerHTML = `<div class="onboarding-complete" role="status" data-onboarding-complete>
          <span class="onboarding-complete-mark" aria-hidden="true">✓</span>
          <span><strong>${escapeHtml(t("onboardingCompleteTitle"))}</strong><small>${escapeHtml(t("onboardingCompleteDescription"))}</small></span>
        </div>`;
        notifyLayoutChange();
        return;
      }

      const currentTaskId = machine.currentTaskId();
      const completed = new Set(state.completedTaskIds);
      const rows = ONBOARDING_TASK_IDS.map((taskId, index) => {
        const [titleKey, descriptionKey] = taskDefinitions[taskId];
        const isCompleted = completed.has(taskId);
        const isCurrent = currentTaskId === taskId;
        const pending = machine.pendingIntent(taskId);
        const marker = isCompleted ? "✓" : String(index + 1);
        const disabled = busyTaskId === taskId ? " disabled" : "";
        const actionKey = busyTaskId === taskId || (pending && taskId !== "first-task")
          ? "onboardingWaitingAction"
          : actionLabelKey(taskId);
        const showAction = isCurrent && !(taskId === "first-task" && firstTaskReady);
        const action = showAction
          ? `<button class="onboarding-task-action" type="button" data-onboarding-task-action="${taskId}"${disabled}>${escapeHtml(t(actionKey))}</button>`
          : "";
        return `<li class="onboarding-task${isCompleted ? " is-completed" : ""}${isCurrent ? " is-current" : " is-future"}" data-onboarding-task="${taskId}"${isCurrent ? ' aria-current="step"' : ""}>
          <span class="onboarding-task-marker" aria-hidden="true">${marker}</span>
          <span class="onboarding-task-copy"><strong>${escapeHtml(t(titleKey))}</strong><small>${escapeHtml(t(descriptionKey))}</small></span>
          ${action}
        </li>`;
      }).join("");
      root.innerHTML = `<section class="onboarding-card" aria-labelledby="onboardingTasksTitle">
        <header class="onboarding-card-header">
          <span><strong id="onboardingTasksTitle">${escapeHtml(t("onboardingTitle"))}</strong><small>${escapeHtml(t("onboardingProgress", { done: state.completedTaskIds.length, total: ONBOARDING_TASK_IDS.length }))}</small></span>
        </header>
        <ol class="onboarding-task-list" aria-label="${escapeHtml(t("onboardingTaskListLabel"))}">${rows}</ol>
        ${renderExamples()}
      </section>`;
      notifyLayoutChange();
    }

    function celebrateCompletion() {
      celebrating = true;
      firstTaskReady = false;
      render();
      if (completionTimer != null) global.clearTimeout(completionTimer);
      completionTimer = global.setTimeout(() => {
        completionTimer = null;
        celebrating = false;
        render();
      }, Math.max(0, completionDurationMs));
    }

    function completeIntent(intentId) {
      const completed = machine.resolveIntent(intentId, true);
      if (!completed) {
        render();
        return false;
      }
      if (machine.snapshot().completed) celebrateCompletion();
      else render();
      return true;
    }

    function confirmFirstTaskModel() {
      if (!machine.pendingIntent("first-task") || machine.currentTaskId() !== "first-task") return false;
      firstTaskReady = true;
      render();
      onFirstTaskReady();
      return true;
    }

    async function runAction(taskId) {
      if (busyTaskId) return;
      const intentId = machine.beginIntent(taskId);
      if (!intentId) return;
      busyTaskId = taskId;
      render();
      try {
        const result = await actions[taskId]?.({ intentId, taskId });
        if (result?.success === true) completeIntent(intentId);
        else if (result?.pending === true && result?.ready === true && taskId === "first-task") {
          confirmFirstTaskModel();
        } else if (result?.pending !== true) {
          machine.cancelIntent(intentId);
        }
      } catch {
        machine.cancelIntent(intentId);
        onError("action");
      } finally {
        busyTaskId = "";
        render();
      }
    }

    function bind() {
      if (!root || bound) return;
      bound = true;
      root.addEventListener("click", (event) => {
        const exampleButton = event.target.closest("[data-onboarding-example]");
        if (exampleButton && firstTaskReady && machine.currentTaskId() === "first-task") {
          const index = Number(exampleButton.dataset.onboardingExample);
          const key = FIRST_TASK_EXAMPLE_KEYS[index];
          if (key) onExampleSelected(t(key));
          return;
        }
        const taskId = event.target.closest("[data-onboarding-task-action]")?.dataset.onboardingTaskAction;
        if (taskId) void runAction(taskId);
      });
    }

    function initialize({ hasExistingSessions = false, isWelcomeVisible = false } = {}) {
      machine.initialize({ hasExistingSessions });
      initialized = true;
      welcomeVisible = Boolean(isWelcomeVisible);
      firstTaskReady = false;
      render();
      return machine.snapshot();
    }

    function setWelcomeVisible(visible) {
      const next = Boolean(visible);
      if (!next) {
        const pending = machine.pendingIntent("first-task");
        if (pending && !pending.claimed) {
          machine.cancelIntent(pending.id);
          firstTaskReady = false;
        }
      }
      welcomeVisible = next;
      render();
    }

    function reopen() {
      if (!machine.reopen()) {
        onError("storage");
        return false;
      }
      celebrating = false;
      firstTaskReady = false;
      if (completionTimer != null) global.clearTimeout(completionTimer);
      completionTimer = null;
      initialized = true;
      render();
      return true;
    }

    return Object.freeze({
      bind,
      cancelIntent: (intentId) => {
        const cancelled = machine.cancelIntent(intentId);
        if (cancelled) firstTaskReady = false;
        render();
        return cancelled;
      },
      claimFirstTaskIntent: () => (
        firstTaskReady ? machine.claimIntent("first-task") : null
      ),
      completeIntent,
      completePending: (taskId) => {
        const pending = machine.pendingIntent(taskId);
        return pending ? completeIntent(pending.id) : false;
      },
      confirmFirstTaskModel,
      initialize,
      isPending: (taskId) => Boolean(machine.pendingIntent(taskId)),
      refreshLanguage: render,
      reopen,
      setWelcomeVisible,
      snapshot: () => machine.snapshot(),
    });
  }

  Code.features.onboardingTasks = Object.freeze({
    FIRST_TASK_EXAMPLE_KEYS,
    LEGACY_V1_TASK_IDS,
    ONBOARDING_STORAGE_KEY,
    ONBOARDING_TASK_IDS,
    ONBOARDING_VERSION,
    createOnboardingStateMachine,
    createOnboardingTasksFeature,
    migrateLegacyV1State,
    normalizeStoredState,
  });
})(window);
