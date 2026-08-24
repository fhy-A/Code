(function initializeCodeGoalFeature(global) {
  "use strict";

  const features = global.Code && global.Code.features;
  if (!features) throw new Error("Code features namespace must load before Goal");

  const QUERY_INPUTS = new Set([
    "/goal", "/goal status", "/goal 状态", "goal status", "goal 状态", "查看 goal 状态",
  ]);
  const STEP_STATUSES = new Set(["pending", "in_progress", "completed"]);

  function classifyGoalInput(input) {
    const text = String(input || "").trim();
    if (!text) return null;
    if (QUERY_INPUTS.has(text.toLowerCase())) return { kind: "query" };
    const create = text.match(/^\/goal\s+([\s\S]+)$/i);
    if (create?.[1]?.trim()) return { kind: "create", objective: create[1].trim() };
    return null;
  }

  function goalLifecyclePhase(lifecycle) {
    return {
      draft: "draft",
      active: "active",
      paused: "paused",
      ready_for_acceptance: "ready",
      completed: "completed",
      cancelled: "cancelled",
    }[String(lifecycle || "")] || "unavailable";
  }

  function phaseLabelKey(phase) {
    return {
      draft: "goalProgressDraft",
      active: "goalProgressActive",
      paused: "goalProgressPaused",
      ready: "goalProgressReady",
      completed: "goalProgressCompleted",
      cancelled: "goalProgressCancelled",
      unavailable: "goalProgressUnavailable",
    }[phase] || "goalProgressUnavailable";
  }

  function createGoalFeature(options = {}) {
    const apiJson = options.apiJson;
    const t = options.t || ((key) => key);
    const escapeHtml = options.escapeHtml || ((value) => String(value ?? ""));
    const showToast = options.showToast || (() => {});
    const getSessionId = options.getSessionId || (() => "");
    const getMessages = options.getMessages || (() => []);
    const renderMessages = options.renderMessages || (() => {});
    const elements = options.elements || {};
    const documentRef = options.document || global.document;
    let currentSessionId = "";
    let cached = null;
    let requestSequence = 0;
    let transitionSequence = 0;
    let sessionTransition = null;
    let destroyed = false;
    let detailsPinned = false;
    let listenersBound = false;
    let pointerStartedInside = false;

    if (typeof apiJson !== "function") throw new Error("Goal feature requires apiJson");

    function goalUrl(sessionId, control = false) {
      return `/api/sessions/${encodeURIComponent(sessionId)}/goal-v2${control ? "/control" : ""}`;
    }

    function trustedGoal(data = cached) {
      if (!data || data.health !== "healthy" || !data.goal) return null;
      return data.goal;
    }

    function setDetailsVisible(visible) {
      const summary = elements.goalProgressSummary;
      const details = elements.goalProgressDetails;
      if (!summary || !details) return;
      details.hidden = !visible;
      summary.setAttribute("aria-expanded", String(Boolean(visible)));
    }

    function dismissDetails({ restoreFocus = false } = {}) {
      detailsPinned = false;
      setDetailsVisible(false);
      if (restoreFocus) elements.goalProgressSummary?.focus?.({ preventScroll: true });
    }

    function handleSummaryClick() {
      detailsPinned = !detailsPinned;
      setDetailsVisible(detailsPinned);
    }

    function handlePointerEnter() {
      setDetailsVisible(true);
    }

    function handlePointerLeave() {
      const root = elements.goalProgress;
      if (!detailsPinned && !root?.contains(documentRef?.activeElement)) setDetailsVisible(false);
    }

    function handleFocusIn() {
      setDetailsVisible(true);
    }

    function handleFocusOut(event) {
      const root = elements.goalProgress;
      if (!root?.contains(event.relatedTarget) && !pointerStartedInside) dismissDetails();
    }

    function handleKeyDown(event) {
      if (event.key !== "Escape") return;
      dismissDetails({ restoreFocus: true });
      event.preventDefault();
    }

    function handleDocumentPointerDown(event) {
      const root = elements.goalProgress;
      const details = elements.goalProgressDetails;
      pointerStartedInside = Boolean(root?.contains(event.target));
      if (!root || !details || root.hidden || details.hidden || pointerStartedInside) return;
      dismissDetails();
    }

    function handleDocumentPointerEnd() {
      pointerStartedInside = false;
    }

    function handleDocumentClick(event) {
      const root = elements.goalProgress;
      const details = elements.goalProgressDetails;
      if (root && details && !root.hidden && !details.hidden && !root.contains(event.target)) {
        dismissDetails();
      }
      pointerStartedInside = false;
    }

    function bindInteractions() {
      if (destroyed || listenersBound || !elements.goalProgressSummary || !elements.goalProgress) return;
      listenersBound = true;
      const root = elements.goalProgress;
      const summary = elements.goalProgressSummary;
      summary.addEventListener("click", handleSummaryClick);
      root.addEventListener("pointerenter", handlePointerEnter);
      root.addEventListener("pointerleave", handlePointerLeave);
      root.addEventListener("focusin", handleFocusIn);
      root.addEventListener("focusout", handleFocusOut);
      root.addEventListener("keydown", handleKeyDown);
      documentRef?.addEventListener?.("pointerdown", handleDocumentPointerDown, true);
      documentRef?.addEventListener?.("pointerup", handleDocumentPointerEnd, true);
      documentRef?.addEventListener?.("pointercancel", handleDocumentPointerEnd, true);
      documentRef?.addEventListener?.("click", handleDocumentClick, true);
    }

    function unbindInteractions() {
      if (!listenersBound) return;
      listenersBound = false;
      const root = elements.goalProgress;
      const summary = elements.goalProgressSummary;
      summary?.removeEventListener?.("click", handleSummaryClick);
      root?.removeEventListener?.("pointerenter", handlePointerEnter);
      root?.removeEventListener?.("pointerleave", handlePointerLeave);
      root?.removeEventListener?.("focusin", handleFocusIn);
      root?.removeEventListener?.("focusout", handleFocusOut);
      root?.removeEventListener?.("keydown", handleKeyDown);
      documentRef?.removeEventListener?.("pointerdown", handleDocumentPointerDown, true);
      documentRef?.removeEventListener?.("pointerup", handleDocumentPointerEnd, true);
      documentRef?.removeEventListener?.("pointercancel", handleDocumentPointerEnd, true);
      documentRef?.removeEventListener?.("click", handleDocumentClick, true);
      pointerStartedInside = false;
    }

    function syncConfirmedOrigin(data = cached) {
      const goal = trustedGoal(data);
      if (!goal || goal.sourceKind !== "explicit") return false;
      const messageId = String(goal.originMessageId || "");
      const goalId = String(goal.goalId || "");
      if (!messageId || !goalId) return false;
      const message = getMessages().find((item) => (
        item?.role === "user" && String(item.id || "") === messageId
      ));
      if (!message) return false;
      const current = message.meta?.goalOrigin || {};
      const next = {
        messageId,
        clientRequestId: String(goal.clientRequestId || current.clientRequestId || ""),
        goalId,
        sourceKind: String(goal.sourceKind || ""),
        confirmedRevision: Number(data.revision || 0),
        confirmed: true,
      };
      if (JSON.stringify(current) === JSON.stringify(next)) return false;
      message.meta = { ...(message.meta || {}), goalOrigin: next };
      renderMessages();
      return true;
    }

    function render(data = cached) {
      cached = data;
      bindInteractions();
      const root = elements.goalProgress;
      const summary = elements.goalProgressSummary;
      const objectiveNode = elements.goalProgressObjective;
      const phaseNode = elements.goalProgressPhase;
      const countNode = elements.goalProgressCount;
      const details = elements.goalProgressDetails;
      if (!root || !summary || !objectiveNode || !phaseNode || !countNode || !details) return;

      const goal = data?.goal || null;
      // The origin marker is historical evidence and remains visible even
      // after the active composer projection has reached its terminal state.
      syncConfirmedOrigin(data);
      const visible = Boolean(
        currentSessionId
        && data?.exists
        && goal
        && goal.lifecycle !== "completed"
      );
      root.classList.toggle("hidden", !visible);
      root.hidden = !visible;
      root.setAttribute("aria-hidden", String(!visible));
      if (!visible) {
        dismissDetails();
        objectiveNode.textContent = "";
        phaseNode.textContent = "";
        countNode.textContent = "";
        details.innerHTML = "";
        return;
      }

      const healthy = data.health === "healthy";
      const phase = healthy ? goalLifecyclePhase(goal.lifecycle) : "unavailable";
      const steps = Array.isArray(goal.steps) ? goal.steps.slice(0, 8) : [];
      const normalizedSteps = steps.map((step) => ({
        ...step,
        status: STEP_STATUSES.has(step?.status) ? step.status : "pending",
      }));
      const completed = normalizedSteps.filter((step) => step.status === "completed").length;
      const inProgressIndexes = normalizedSteps.reduce((indexes, step, index) => {
        if (step.status === "in_progress") indexes.push(index);
        return indexes;
      }, []);
      const progress = inProgressIndexes.length === 1
        ? inProgressIndexes[0] + 1
        : completed;
      const currentStep = normalizedSteps.find((step) => (
        String(step.id || "") === String(goal.currentStepId || "")
      )) || normalizedSteps.find((step) => step.status === "in_progress") || null;
      const phaseText = t(phaseLabelKey(phase));
      objectiveNode.textContent = String(goal.objective || t("goalProgressUntitled"));
      phaseNode.textContent = phaseText;
      phaseNode.className = `goal-progress-phase is-${phase}`;
      countNode.textContent = t("goalProgressCount", {
        current: progress,
        total: normalizedSteps.length,
      });
      summary.setAttribute("aria-label", t("goalProgressAriaLabel", {
        objective: goal.objective || t("goalProgressUntitled"),
        phase: phaseText,
        current: progress,
        total: normalizedSteps.length,
      }));
      root.dataset.lifecycle = String(goal.lifecycle || "");
      root.dataset.health = String(data.health || "unavailable");

      const stepHtml = normalizedSteps.map((step, index) => {
        const current = step === currentStep;
        return `<li class="goal-progress-step is-${escapeHtml(step.status)}${current ? " is-current" : ""}">
          <div class="goal-progress-step-line">
            <span class="goal-progress-step-index">${index + 1}</span>
            <span class="goal-progress-step-status">${escapeHtml(t(`goalStep_${step.status}`))}</span>
            <span class="goal-progress-step-description">${escapeHtml(step.description || "")}</span>
          </div>
        </li>`;
      }).join("");
      details.innerHTML = `<div class="goal-progress-detail-objective">${escapeHtml(goal.objective || t("goalProgressUntitled"))}</div>
        ${stepHtml ? `<ol class="goal-progress-steps">${stepHtml}</ol>` : `<div class="goal-progress-empty">${escapeHtml(t("goalProgressNoPlan"))}</div>`}`;
      if (!detailsPinned && !root.matches?.(":hover") && !root.contains(documentRef?.activeElement)) {
        setDetailsVisible(false);
      }
    }

    async function refresh(sessionId = getSessionId(), { quiet = false } = {}) {
      const normalized = String(sessionId || "");
      if (sessionTransition) return null;
      const sequence = ++requestSequence;
      if (!normalized) {
        currentSessionId = "";
        cached = null;
        render(null);
        return null;
      }
      currentSessionId = normalized;
      try {
        const response = await apiJson(goalUrl(normalized));
        if (destroyed || sequence !== requestSequence || normalized !== currentSessionId) return null;
        cached = response?.data || response;
        render(cached);
        return cached;
      } catch (error) {
        if (destroyed || sequence !== requestSequence || normalized !== currentSessionId) return null;
        cached = null;
        render(null);
        if (!quiet) showToast(t("goalActionFailed", { error: error?.message || String(error) }), "error");
        return null;
      }
    }

    function setSession(sessionId) {
      const normalized = String(sessionId || "");
      if (sessionTransition) {
        if (normalized === sessionTransition.targetSessionId) {
          sessionTransition = null;
        } else if (normalized === currentSessionId) {
          render(null);
          return;
        } else {
          sessionTransition = null;
        }
      }
      if (normalized === currentSessionId) {
        render(cached);
        return;
      }
      requestSequence += 1;
      currentSessionId = normalized;
      cached = null;
      dismissDetails();
      render(null);
      if (normalized) void refresh(normalized, { quiet: true });
    }

    function beginSessionTransition(sessionId) {
      const normalized = String(sessionId || "");
      if (!normalized || normalized === currentSessionId) return null;
      const token = ++transitionSequence;
      sessionTransition = {
        token,
        targetSessionId: normalized,
        sourceSessionId: currentSessionId,
        sourceProjection: cached,
      };
      requestSequence += 1;
      cached = null;
      dismissDetails();
      render(null);
      return token;
    }

    function cancelSessionTransition(sessionId, token) {
      if (!sessionTransition || token !== sessionTransition.token) return false;
      const sourceSessionId = sessionTransition.sourceSessionId || String(sessionId || "");
      const sourceProjection = sessionTransition.sourceProjection;
      sessionTransition = null;
      requestSequence += 1;
      currentSessionId = sourceSessionId;
      cached = sourceProjection || null;
      dismissDetails();
      render(cached);
      if (currentSessionId && !cached) void refresh(currentSessionId, { quiet: true });
      return true;
    }

    async function prepareExplicitGoal(input = {}) {
      const sessionId = String(input.sessionId || getSessionId() || "");
      const objective = String(input.objective || "").trim();
      if (!sessionId || !objective) throw new Error(t("goalExplicitInvalid"));
      let projection = sessionId === currentSessionId ? cached : null;
      if (!projection) projection = await refresh(sessionId, { quiet: true });
      const body = {
        operation: "explicit_create",
        objective,
        expectedRevision: Number(projection?.revision || 0),
        idempotencyKey: `explicit-${String(input.clientRequestId || "")}`,
        messageId: String(input.messageId || ""),
        clientRequestId: String(input.clientRequestId || ""),
        permissionProfile: String(input.permissionProfile || "accept"),
      };
      const response = await apiJson(goalUrl(sessionId, true), {
        method: "POST",
        body: JSON.stringify(body),
      });
      const result = response?.data || response;
      if (sessionId === currentSessionId) {
        cached = result;
        render(cached);
        await refresh(sessionId, { quiet: true });
      }
      return result;
    }

    function handleSlash(input) {
      const action = classifyGoalInput(input);
      if (!action || action.kind === "create") return false;
      void refresh(getSessionId(), { quiet: false }).then((projection) => {
        if (!projection?.goal) showToast(t("goalProgressNoCurrent"), "info");
      });
      return true;
    }

    function destroy() {
      destroyed = true;
      requestSequence += 1;
      sessionTransition = null;
      currentSessionId = "";
      cached = null;
      dismissDetails();
      unbindInteractions();
      render(null);
    }

    return Object.freeze({
      classifyGoalInput,
      beginSessionTransition,
      cancelSessionTransition,
      destroy,
      getCached: () => cached,
      handleOrdinary: () => false,
      handleSlash,
      prepareExplicitGoal,
      refresh,
      render,
      setSession,
    });
  }

  features.goal = Object.freeze({
    classifyGoalInput,
    createGoalFeature,
    goalLifecyclePhase,
  });
})(window);
