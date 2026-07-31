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

    async function loadSession(sessionId) {
      if (!sessionId) return;

      const now = Date.now();
      if (state._lastSwitchTime && now - state._lastSwitchTime < 300) return;
      state._lastSwitchTime = now;

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
      view.cacheActiveSessionState();

      const session = await data.getSession(sessionId);
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

  features.sessions = Object.freeze({
    normalizeSessionMessages,
    collectPendingEdits,
    createSessionsFeature,
    createSessionNavigation,
  });
})(window);
