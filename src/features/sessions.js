(function initializeCodeSessions(global) {
  "use strict";

  const features = global.Code && global.Code.features;
  if (!features) throw new Error("Code features namespace must load before sessions");

  function normalizeSessionMessages(messages = []) {
    return (Array.isArray(messages) ? messages : []).map((message) => ({
      ...message,
      _images: message._images || undefined,
    }));
  }

  function collectPendingEdits(messages = []) {
    const pendingEdits = {};
    for (const message of Array.isArray(messages) ? messages : []) {
      if (message.role !== "tool-result" || !message.meta?.pendingEditId) continue;
      pendingEdits[message.meta.pendingEditId] = {
        path: message.meta.path,
        newContent: message.meta.newContent || "",
        applied: Boolean(message.meta.applied),
        rejected: Boolean(message.meta.rejected),
        resolved: Boolean(message.meta.applied || message.meta.rejected),
        serverManaged: Boolean(message.meta.serverManaged),
        mtime: message.meta.mtime || 0,
      };
    }
    return pendingEdits;
  }

  function sessionActivityTime(session = {}) {
    for (const value of [session.lastMessageTime, session.updatedAt, session.createdAt]) {
      const timestamp = String(value || "").trim();
      if (!/(?:Z|[+-]\d{2}:\d{2})$/i.test(timestamp)) continue;
      const parsed = Date.parse(timestamp);
      if (Number.isFinite(parsed)) return parsed;
    }
    return null;
  }

  function sessionRelativeTimeParts(session = {}, now = Date.now()) {
    const activityTime = sessionActivityTime(session);
    if (!Number.isFinite(activityTime)) return null;
    const elapsed = Math.max(0, Number(now) - activityTime);
    if (elapsed < 60_000) return Object.freeze({ unit: "now", count: 0 });
    if (elapsed < 3_600_000) {
      return Object.freeze({ unit: "minute", count: Math.floor(elapsed / 60_000) });
    }
    if (elapsed < 86_400_000) {
      return Object.freeze({ unit: "hour", count: Math.floor(elapsed / 3_600_000) });
    }
    return Object.freeze({ unit: "day", count: Math.floor(elapsed / 86_400_000) });
  }

  function formatSessionRelativeTime(session, translate, now = Date.now()) {
    const parts = sessionRelativeTimeParts(session, now);
    if (!parts || typeof translate !== "function") return "";
    const key = {
      now: "sessionRelativeNow",
      minute: "sessionRelativeMinutes",
      hour: "sessionRelativeHours",
      day: "sessionRelativeDays",
    }[parts.unit];
    return translate(key, { count: parts.count });
  }

  function resolveSessionStatus(session, options = {}) {
    if (options.active !== true && options.waitingUserInput === true) {
      return Object.freeze({
        kind: "waiting-user-input",
        text: "",
        label: String(options.waitingUserInputLabel || ""),
      });
    }
    if (options.active !== true && options.waitingAuthorization === true) {
      return Object.freeze({
        kind: "waiting-authorization",
        text: "",
        label: String(options.waitingAuthorizationLabel || ""),
      });
    }
    if (options.active !== true && options.waitingSkillEvidence === true) {
      return Object.freeze({
        kind: "waiting-skill-evidence",
        text: "",
        label: String(options.waitingSkillEvidenceLabel || ""),
      });
    }
    if (options.streaming === true) {
      return Object.freeze({ kind: "running", text: "", label: String(options.runningLabel || "") });
    }
    if (options.failed === true) {
      return Object.freeze({ kind: "failed", text: "", label: String(options.failedLabel || "") });
    }
    if (session?._unread === true) {
      return Object.freeze({ kind: "unread", text: "", label: String(options.unreadLabel || "") });
    }
    const text = formatSessionRelativeTime(session, options.translate, options.now);
    return Object.freeze({ kind: "idle", text, label: text });
  }

  function createSessionStatusTicker(options = {}) {
    const getRoot = options.getRoot || (() => null);
    const getSessions = options.getSessions || (() => []);
    const translate = options.translate || (() => "");
    const now = options.now || (() => Date.now());
    const schedule = options.setInterval || global.setInterval?.bind(global);
    const cancel = options.clearInterval || global.clearInterval?.bind(global);
    const onRefresh = options.onRefresh;
    let timerId = null;

    function refresh() {
      const root = getRoot();
      if (!root?.querySelectorAll) return 0;
      const sessions = new Map((getSessions() || [])
        .filter((session) => session?.id)
        .map((session) => [String(session.id), session]));
      let changes = 0;
      for (const slot of root.querySelectorAll(
        '.session-status-slot[data-session-status="idle"][data-session-id]',
      )) {
        const session = sessions.get(String(slot.dataset?.sessionId || ""));
        if (!session) continue;
        const text = formatSessionRelativeTime(session, translate, now());
        if (slot.textContent !== text) {
          slot.textContent = text;
          changes += 1;
        }
        if (text) slot.setAttribute?.("aria-label", text);
        else slot.removeAttribute?.("aria-label");
      }
      if (changes > 0 && typeof onRefresh === "function") onRefresh(changes);
      return changes;
    }

    function start() {
      if (timerId !== null || typeof schedule !== "function") return timerId;
      timerId = schedule(refresh, 60_000);
      return timerId;
    }

    function stop() {
      if (timerId === null) return false;
      if (typeof cancel === "function") cancel(timerId);
      timerId = null;
      return true;
    }

    return Object.freeze({ refresh, start, stop });
  }

  function createSessionTitleMarqueeController(options = {}) {
    const schedule = options.setTimeout || global.setTimeout?.bind(global);
    const cancel = options.clearTimeout || global.clearTimeout?.bind(global);
    const prefersReducedMotion = options.prefersReducedMotion || (() => (
      global.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches === true
    ));
    const hoverDelayMs = Math.max(0, Number(options.hoverDelayMs ?? 420) || 0);
    const pixelsPerSecond = Math.max(1, Number(options.pixelsPerSecond ?? 24) || 24);
    const endGapPx = Math.max(0, Number(options.endGapPx ?? 4) || 0);
    const innerSelector = String(
      options.innerSelector || ":scope > .session-title-scroll-text",
    );
    const getOperationSurfaceLeft = options.getOperationSurfaceLeft || ((title) => {
      const row = title?.closest?.(".session-row");
      const moreWrap = row?.querySelector?.(".session-more-wrap");
      const rect = moreWrap?.getBoundingClientRect?.();
      const left = Number(rect?.left);
      if (!Number.isFinite(left)) return Number.NaN;
      const computed = global.getComputedStyle?.(moreWrap);
      const coverInset = Math.max(
        0,
        Number.parseFloat(
          computed?.getPropertyValue?.("--session-more-cover-inset") || "0",
        ) || 0,
      );
      return left - coverInset;
    });
    let owner = null;
    let timerId = null;

    function innerFor(title) {
      return title?.querySelector?.(innerSelector) || null;
    }

    function clearTimer() {
      if (timerId !== null) {
        if (typeof cancel === "function") cancel(timerId);
        timerId = null;
      }
    }

    function clearMotion(title) {
      title?.classList?.remove("is-scrolling", "is-scroll-complete");
    }

    function clearMeasurement(title) {
      clearMotion(title);
      title?.classList?.remove("is-overflowing");
      title.style?.removeProperty("--session-title-scroll-distance");
      title.style?.removeProperty("--session-title-scroll-duration");
    }

    function measure(title, includeOperationSurface = false) {
      const inner = innerFor(title);
      let distance = Math.max(
        0,
        Math.ceil(Number(inner?.scrollWidth || 0) - Number(title?.clientWidth || 0)),
      );
      if (inner && includeOperationSurface) {
        const titleRect = title?.getBoundingClientRect?.();
        const innerRect = inner.getBoundingClientRect?.();
        const titleRight = Number(titleRect?.right);
        const innerRight = Number(innerRect?.right);
        const operationSurfaceLeft = Number(getOperationSurfaceLeft(title));
        if (
          Number.isFinite(titleRight)
          && Number.isFinite(innerRight)
          && Number.isFinite(operationSurfaceLeft)
        ) {
          const visibleRight = Math.min(
            titleRight,
            operationSurfaceLeft - endGapPx,
          );
          distance = Math.max(distance, Math.ceil(innerRight - visibleRight));
        }
      }
      if (!inner || distance <= 1) {
        clearMeasurement(title);
        return false;
      }
      const durationMs = Math.round((distance / pixelsPerSecond) * 1000);
      title.classList.add("is-overflowing");
      title.style.setProperty("--session-title-scroll-distance", `${distance}px`);
      title.style.setProperty("--session-title-scroll-duration", `${durationMs}ms`);
      return true;
    }

    function reset(title = owner) {
      if (!title) return false;
      if (owner === title) {
        clearTimer();
        owner = null;
      }
      clearMeasurement(title);
      return true;
    }

    function enter(title) {
      if (owner && owner !== title) leave(owner);
      else if (owner === title) {
        clearTimer();
        clearMotion(title);
      }
      if (!measure(title, true)) return false;

      owner = title;
      if (prefersReducedMotion() || typeof schedule !== "function") return true;

      timerId = schedule(() => {
        timerId = null;
        if (owner !== title) return;
        title.classList.add("is-scrolling");
      }, hoverDelayMs);
      return true;
    }

    function finish(title, event = {}) {
      if (
        owner !== title
        || event.target !== innerFor(title)
        || event.propertyName !== "transform"
        || !title.classList.contains("is-scrolling")
        || title.classList.contains("is-scroll-complete")
      ) return false;
      title.classList.add("is-scroll-complete");
      return true;
    }

    function leave(title) {
      if (owner !== title) return false;
      clearTimer();
      owner = null;
      clearMotion(title);
      measure(title);
      return true;
    }

    function refresh(titles = []) {
      if (owner) reset(owner);
      let marked = 0;
      for (const title of Array.from(titles || [])) {
        if (measure(title)) marked += 1;
      }
      return marked;
    }

    return Object.freeze({ enter, finish, leave, refresh, reset });
  }

  function compareSessionSearchRecords(left, right) {
    const leftTime = sessionActivityTime(left);
    const rightTime = sessionActivityTime(right);
    const normalizedLeft = Number.isFinite(leftTime) ? leftTime : Number.NEGATIVE_INFINITY;
    const normalizedRight = Number.isFinite(rightTime) ? rightTime : Number.NEGATIVE_INFINITY;
    if (normalizedLeft !== normalizedRight) return normalizedRight - normalizedLeft;
    const leftId = String(left?.id || "");
    const rightId = String(right?.id || "");
    if (leftId < rightId) return -1;
    if (leftId > rightId) return 1;
    return 0;
  }

  function selectSessionSearchResults(sessions, query = "", options = {}) {
    const normalizedQuery = String(query || "").trim().toLowerCase();
    const recentLimit = Math.max(0, Number(options.recentLimit ?? 10) || 0);
    const matches = (Array.isArray(sessions) ? sessions : [])
      .filter((session) => session && typeof session === "object" && String(session.id || "").trim())
      .filter((session) => {
        if (!normalizedQuery) return true;
        const title = String(session.title || "").toLowerCase();
        const sessionId = String(session.id || "").toLowerCase();
        return title.includes(normalizedQuery) || sessionId.includes(normalizedQuery);
      })
      .slice()
      .sort(compareSessionSearchRecords);
    return normalizedQuery ? matches : matches.slice(0, recentLimit);
  }

  function resolveSessionSearchStatus({ streaming = false } = {}) {
    return streaming === true ? "running" : "idle";
  }

  function createSessionSearchFeature(options = {}) {
    const state = options.state || {};
    const elements = options.elements || {};
    const t = options.t || ((key) => key);
    const escapeHtml = options.escapeHtml || ((value) => String(value ?? ""));
    const projectName = options.projectName || (() => "");
    const isSessionRunning = options.isSessionRunning || (() => false);
    const loadSession = options.loadSession;
    const documentRef = options.document || global.document;
    let trigger = null;
    let visibleResults = [];
    let bound = false;

    if (typeof loadSession !== "function") {
      throw new TypeError("Session search requires session navigation");
    }

    function isOpen() {
      return Boolean(elements.modal && !elements.modal.classList.contains("hidden"));
    }

    function resultButtons() {
      return Array.from(elements.results?.querySelectorAll(".session-search-result") || []);
    }

    function render() {
      if (!elements.results) return [];
      const query = String(elements.input?.value || "");
      visibleResults = selectSessionSearchResults(state.sessions, query);
      if (!visibleResults.length) {
        elements.results.innerHTML = `<div class="session-search-empty">${escapeHtml(t("sessionSearchNoResults"))}</div>`;
        return [];
      }
      elements.results.innerHTML = visibleResults.map((session) => {
        const title = String(session.title || "").trim() || t("untitledSession");
        const statusKind = resolveSessionSearchStatus({
          streaming: isSessionRunning(String(session.id || "")) === true,
        });
        const running = statusKind === "running";
        const status = t(running ? "sessionSearchRunning" : "sessionSearchIdle");
        const project = String(projectName(session) || "").trim() || t("sessionSearchNoProject");
        return `<button class="session-search-result" type="button" data-session-id="${escapeHtml(session.id)}">
          <span class="session-search-status${running ? " is-running" : ""}">${escapeHtml(status)}</span>
          <strong class="session-search-result-title">${escapeHtml(title)}</strong>
          <span class="session-search-result-project">${escapeHtml(project)}</span>
        </button>`;
      }).join("");
      return visibleResults.slice();
    }

    function open() {
      if (!elements.modal || !elements.input) return false;
      trigger = documentRef.activeElement || elements.trigger;
      elements.input.value = "";
      elements.modal.classList.remove("hidden");
      render();
      elements.input.focus();
      return true;
    }

    function close({ restoreFocus = true } = {}) {
      if (!isOpen()) return false;
      elements.modal.classList.add("hidden");
      elements.input.value = "";
      visibleResults = [];
      if (restoreFocus && typeof trigger?.focus === "function") trigger.focus();
      trigger = null;
      return true;
    }

    async function navigate(sessionId) {
      const normalized = String(sessionId || "").trim();
      if (!normalized || !visibleResults.some((session) => String(session.id) === normalized)) return false;
      close({ restoreFocus: false });
      await loadSession(normalized);
      return true;
    }

    function focusRelative(button, direction) {
      const buttons = resultButtons();
      const index = buttons.indexOf(button);
      if (index < 0) return;
      const target = buttons[index + direction];
      if (target) target.focus();
      else if (direction < 0) elements.input?.focus();
    }

    function trapTab(event) {
      if (event.key !== "Tab" || !isOpen()) return;
      const focusable = [elements.close, elements.input, ...resultButtons()].filter(Boolean);
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && documentRef.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && documentRef.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    function bind() {
      if (bound) return;
      bound = true;
      elements.trigger?.addEventListener("click", open);
      elements.close?.addEventListener("click", () => close());
      elements.modal?.addEventListener("click", (event) => {
        if (event.target === elements.modal) close();
      });
      elements.modal?.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
          event.preventDefault();
          event.stopPropagation();
          close();
          return;
        }
        trapTab(event);
      });
      elements.input?.addEventListener("input", render);
      elements.input?.addEventListener("keydown", (event) => {
        const buttons = resultButtons();
        if (event.key === "ArrowDown" && buttons[0]) {
          event.preventDefault();
          buttons[0].focus();
        } else if (event.key === "ArrowUp" && buttons[buttons.length - 1]) {
          event.preventDefault();
          buttons[buttons.length - 1].focus();
        } else if (event.key === "Enter" && buttons[0]) {
          event.preventDefault();
          buttons[0].click();
        }
      });
      elements.results?.addEventListener("click", (event) => {
        const button = event.target.closest(".session-search-result");
        if (button) void navigate(button.dataset.sessionId);
      });
      elements.results?.addEventListener("keydown", (event) => {
        const button = event.target.closest(".session-search-result");
        if (!button) return;
        if (event.key === "ArrowDown") {
          event.preventDefault();
          focusRelative(button, 1);
        } else if (event.key === "ArrowUp") {
          event.preventDefault();
          focusRelative(button, -1);
        } else if (event.key === "Enter") {
          event.preventDefault();
          button.click();
        }
      });
    }

    function refreshLanguage() {
      if (isOpen()) render();
    }

    return Object.freeze({ bind, close, isOpen, open, refresh: render, refreshLanguage });
  }

  function createSessionsFeature({ requestJson }) {
    if (typeof requestJson !== "function") {
      throw new TypeError("Sessions feature requires a requestJson function");
    }

    function sessionUrl(sessionId) {
      const normalized = String(sessionId || "").trim();
      if (!normalized) throw new TypeError("Session id is required");
      return `/api/sessions/${encodeURIComponent(normalized)}`;
    }

    function sessionArchiveUrl(sessionId, action = "") {
      const normalized = String(sessionId || "").trim();
      if (!normalized) throw new TypeError("Session id is required");
      const base = `/api/session-archive/${encodeURIComponent(normalized)}`;
      return action ? `${base}/${action}` : base;
    }

    async function listSessions() {
      const response = await requestJson("/api/sessions");
      return Array.isArray(response?.data) ? response.data : [];
    }

    function getSession(sessionId) {
      return requestJson(sessionUrl(sessionId));
    }

    function createSession(payload = {}) {
      return requestJson("/api/sessions", {
        method: "POST",
        body: JSON.stringify(payload || {}),
      });
    }

    function updateSession(sessionId, payload = {}) {
      return requestJson(sessionUrl(sessionId), {
        method: "PUT",
        body: JSON.stringify(payload || {}),
      });
    }

    function deleteSession(sessionId) {
      return requestJson(sessionUrl(sessionId), { method: "DELETE" });
    }

    async function listArchivedSessions() {
      const response = await requestJson("/api/session-archive");
      return Array.isArray(response?.data) ? response.data : [];
    }

    function archiveSession(sessionId, options = {}) {
      const signal = options && options.signal;
      const stopActiveWork = options && options.stopActiveWork === true;
      return requestJson(sessionArchiveUrl(sessionId, "archive"), {
        method: "POST",
        ...(signal ? { signal } : {}),
        ...(stopActiveWork
          ? { body: JSON.stringify({ stopActiveWork: true }) }
          : {}),
      });
    }

    function restoreArchivedSession(sessionId) {
      return requestJson(sessionArchiveUrl(sessionId, "restore"), { method: "POST" });
    }

    function deleteArchivedSession(sessionId, archiveToken) {
      const token = String(archiveToken || "").trim();
      if (!token) throw new TypeError("Archive token is required");
      return requestJson(
        `${sessionArchiveUrl(sessionId)}?archiveToken=${encodeURIComponent(token)}`,
        { method: "DELETE" },
      );
    }

    return Object.freeze({
      listSessions,
      getSession,
      createSession,
      updateSession,
      deleteSession,
      listArchivedSessions,
      archiveSession,
      restoreArchivedSession,
      deleteArchivedSession,
    });
  }

  function createSessionNavigation({
    state,
    elements,
    storage = global.localStorage,
    data,
    stateAccessors,
    project,
    branch,
    recovery,
    view,
    t,
  }) {
    if (!state || typeof state !== "object") {
      throw new TypeError("Session navigation requires application state");
    }
    if (!data?.createSession || !data?.getSession) {
      throw new TypeError("Session navigation requires session data access");
    }

    const {
      getSessionRunState,
      setSessionLastUsage,
      setSessionMessages,
      setSessionRunState,
      setSessionStats,
    } = stateAccessors;

    function invalidateForegroundSessionNavigation() {
      state._foregroundNavigationSeq = (state._foregroundNavigationSeq || 0) + 1;
    }

    function rememberWelcomeForeground() {
      storage.setItem("code-foreground-view", "welcome");
      storage.removeItem("code-last-session");
    }

    function rememberSessionForeground(sessionId) {
      if (!sessionId) return;
      storage.setItem("code-foreground-view", "session");
      storage.setItem("code-last-session", sessionId);
    }

    function beginNewConversation(projectId = null) {
      view.cacheActiveSessionState();
      invalidateForegroundSessionNavigation();
      state.pendingProjectId = projectId || null;
      state.sessionId = null;
      state.messages = [];
      state._lastRenderedHtml = null;
      state.stats = { input: 0, output: 0, cache: 0 };
      state.pendingEdits = {};
      elements.sessionTitle.value = "";
      rememberWelcomeForeground();
      view.syncActiveStreamingState();
      view.renderMessages();
      view.renderSessions();
      view.updateGroupBadge({});
      view.updateStatsPanel();
      view.updateSendButtonState();
      const primaryPath = project.getPrimaryPath(project.getById(projectId));
      if (primaryPath && !project.pathsEqual(primaryPath, project.getCurrentRoot())) {
        project.saveRoot(primaryPath, { syncSession: false }).catch((error) => {
          view.showToast(error.message || String(error), "error");
        });
      }
    }

    async function createSession(title = t("sessionTitleDefault"), options = {}) {
      view.cacheActiveSessionState();
      const initialMessages = Array.isArray(options.initialMessages)
        ? options.initialMessages
        : null;
      const body = { title };
      const projectId = state.pendingProjectId || project.getCurrentProject()?.id || null;
      if (projectId) {
        body.projectId = projectId;
        body.cwd = project.getPrimaryPath(project.getById(projectId));
      }
      const loadSeq = (state._sessionLoadSeq || 0) + 1;
      state._sessionLoadSeq = loadSeq;

      const session = await data.createSession(body);
      if (loadSeq !== state._sessionLoadSeq) return session;

      state.sessionId = session.id;
      state.pendingProjectId = session.projectId || null;
      state.sessionCreated = session.createdAt || "";
      state.sessionUpdated = session.lastMessageTime || session.updatedAt || "";
      state._sessionFilePath = session._filePath || "";
      state._sessionMessageFilePath = session._messageFilePath || "";
      view.updateGroupBadge(session);

      state.messages = initialMessages || session.messages || [];
      setSessionMessages(session.id, state.messages);
      setSessionRunState(session.id, session.runState || {});
      setSessionLastUsage(session.id, session.lastUsage || null);
      state.pendingEdits = {};
      state.stats = session.stats || { input: 0, output: 0, cache: 0 };
      setSessionStats(session.id, state.stats);
      view.resetRenderCache();
      elements.sessionTitle.value = session.title || t("sessionTitleDefault");
      rememberSessionForeground(session.id);

      if (options.deferSidebarRefresh === true) {
        state._deferredSessionRefreshId = session.id;
      }
      view.renderMessages();

      if (session.cwd) await project.saveRoot(session.cwd, { syncSession: false });
      if (options.deferSidebarRefresh !== true) {
        await view.refreshSessions();
      }

      view.syncActiveStreamingState();
      view.renderMessages();
      return session;
    }

    async function loadSession(sessionId, options = {}) {
      if (!sessionId) return;

      const userInitiated = options?.userInitiated !== false;
      if (userInitiated) {
        const now = Date.now();
        if (state._lastSwitchTime && now - state._lastSwitchTime < 300) return;
        state._lastSwitchTime = now;
      }

      const foregroundNavigationSeq = (state._foregroundNavigationSeq || 0) + 1;
      state._foregroundNavigationSeq = foregroundNavigationSeq;

      if (state.branchPanelOpen && !state._keepBranchOpen) {
        elements.branchPanel.classList.remove("open");
        elements.toggleBranches.classList.remove("active");
        state.branchPanelOpen = false;
      }
      state._keepBranchOpen = false;

      if (sessionId === state.sessionId) {
        const current = state.sessions.find((item) => item.id === sessionId);
        state.pendingProjectId = current?.projectId || null;
        if (current?.cwd && !project.pathsEqual(current.cwd, project.getCurrentRoot())) {
          await project.saveRoot(current.cwd, { syncSession: false });
        }
        rememberSessionForeground(sessionId);
        view.syncActiveStreamingState();
        view.resetRenderCache();
        view.renderMessages();
        view.scheduleMessagesScrollToBottom(sessionId);
        return;
      }

      const loadSeq = (state._sessionLoadSeq || 0) + 1;
      state._sessionLoadSeq = loadSeq;
      const previousSessionId = state.sessionId;
      const transitionToken = view.beginSessionTransition?.(sessionId) ?? null;
      view.cacheActiveSessionState();

      let session;
      try {
        session = await data.getSession(sessionId);
      } catch (error) {
        view.cancelSessionTransition?.(previousSessionId, transitionToken);
        throw error;
      }
      if (
        loadSeq !== state._sessionLoadSeq
        || foregroundNavigationSeq !== state._foregroundNavigationSeq
      ) return;

      if (previousSessionId && previousSessionId !== session.id) {
        const previous = state.sessions.find((item) => item.id === previousSessionId);
        const previousMessages = state._sessionMsgs[previousSessionId] || [];
        if (previous) {
          previous._seenCount = Math.max(previous._seenCount || 0, previousMessages.length);
          if (previousMessages.length > (previous._seenCount || 0)) previous._unread = true;
        }
      }
      const loaded = branch.syncMetadata(state.sessions, session);
      if (loaded) loaded._unread = false;

      state.sessionId = session.id;
      state.pendingProjectId = session.projectId || null;
      state.sessionCreated = session.createdAt || "";
      state.sessionUpdated = session.lastMessageTime || session.updatedAt || "";
      state._sessionFilePath = session._filePath || "";
      state._sessionMessageFilePath = session._messageFilePath || "";
      view.updateGroupBadge(session);

      const cached = state._sessionMsgs && state._sessionMsgs[session.id];
      state.messages = cached || normalizeSessionMessages(session.messages || []);
      setSessionMessages(session.id, state.messages);
      setSessionRunState(session.id, session.runState || getSessionRunState(session.id));
      await recovery.reconcilePersistedUserInputRequest(
        session.id,
        session.runState?.userInputRequest,
      );
      if (
        loadSeq !== state._sessionLoadSeq
        || foregroundNavigationSeq !== state._foregroundNavigationSeq
      ) return;
      recovery.restoreAuthorizationRequest(session.id, session.runState?.authorizationRequest);
      recovery.restoreSkillEvidenceRequest(session.id, session.runState?.skillEvidenceRequest);
      if (loaded) loaded._seenCount = state.messages.length;

      state.pendingEdits = collectPendingEdits(state.messages);
      state.stats = state._sessionStats[session.id]
        || session.stats
        || { input: 0, output: 0, cache: 0, cost: 0 };
      setSessionStats(session.id, state.stats);
      setSessionLastUsage(
        session.id,
        state._sessionLastUsage[session.id] || session.lastUsage || null,
      );
      view.resetRenderCache();
      elements.sessionTitle.value = session.title || t("untitledSession");
      rememberSessionForeground(session.id);

      if (session.cwd) await project.saveRoot(session.cwd, { syncSession: false });
      view.renderSessions();
      view.syncActiveStreamingState();
      view.renderMessages();
      view.scheduleMessagesScrollToBottom(session.id);
    }

    return Object.freeze({
      invalidateForegroundSessionNavigation,
      rememberWelcomeForeground,
      rememberSessionForeground,
      beginNewConversation,
      createSession,
      loadSession,
    });
  }

  function createSessionStartup({
    state,
    storage = global.localStorage,
    navigation,
    recovery,
    logger = global.console,
  }) {
    if (!state || typeof state !== "object") {
      throw new TypeError("Session startup requires application state");
    }
    if (!navigation?.loadSession || !navigation?.rememberWelcomeForeground) {
      throw new TypeError("Session startup requires session navigation");
    }
    if (
      !recovery?.resumePersistedRuns
      || !recovery?.resumePersistedQueuedMessages
      || !recovery?.resumePersistedBackgroundRuns
    ) {
      throw new TypeError("Session startup requires recovery coordination");
    }

    async function restoreForegroundSession() {
      const foregroundView = storage.getItem("code-foreground-view");
      const lastId = storage.getItem("code-last-session");

      if (
        foregroundView !== "welcome"
        && lastId
        && state.sessions.some((session) => session.id === lastId)
      ) {
        await navigation.loadSession(lastId, { userInitiated: false });
        return lastId;
      }
      if (foregroundView === "welcome" || !lastId) {
        navigation.rememberWelcomeForeground();
      }
      return null;
    }

    function startRecovery() {
      const foreground = recovery.resumePersistedRuns()
        .then(() => recovery.resumePersistedQueuedMessages())
        .catch((error) => {
          logger?.error?.("Failed to resume persisted runs or queued messages:", error);
        });
      const background = recovery.resumePersistedBackgroundRuns()
        .catch((error) => {
          logger?.error?.("Failed to resume persisted background runs:", error);
        });
      return Object.freeze({ foreground, background });
    }

    return Object.freeze({
      restoreForegroundSession,
      startRecovery,
    });
  }

  features.sessions = Object.freeze({
    normalizeSessionMessages,
    collectPendingEdits,
    sessionActivityTime,
    sessionRelativeTimeParts,
    formatSessionRelativeTime,
    resolveSessionStatus,
    createSessionStatusTicker,
    createSessionTitleMarqueeController,
    compareSessionSearchRecords,
    selectSessionSearchResults,
    resolveSessionSearchStatus,
    createSessionSearchFeature,
    createSessionsFeature,
    createSessionNavigation,
    createSessionStartup,
  });
})(window);
