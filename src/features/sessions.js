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
    if (options.streaming === true) {
      return Object.freeze({ kind: "running", text: "", label: String(options.runningLabel || "") });
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

  function createSessionsFeature({ requestJson }) {
    if (typeof requestJson !== "function") {
      throw new TypeError("Sessions feature requires a requestJson function");
    }

    function sessionUrl(sessionId) {
      const normalized = String(sessionId || "").trim();
      if (!normalized) throw new TypeError("Session id is required");
      return `/api/sessions/${encodeURIComponent(normalized)}`;
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

    return Object.freeze({
      listSessions,
      getSession,
      createSession,
      updateSession,
      deleteSession,
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
      recovery.restoreUserInputRequest(session.id, session.runState?.userInputRequest);
      recovery.restoreAuthorizationRequest(session.id, session.runState?.authorizationRequest);
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
    createSessionsFeature,
    createSessionNavigation,
    createSessionStartup,
  });
})(window);
