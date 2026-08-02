(function initializeCodeState(global) {
  "use strict";

  const core = global.Code && global.Code.core;
  if (!core) throw new Error("Code core namespace must load before state");

  function createAppState(storage = global.localStorage) {
    const getStoredValue = (key) => storage?.getItem?.(key) ?? null;
    return {
      sessionId: null,
      sessions: [],
      projects: [],
      projectsMap: {},
      pendingProjectId: null,
      messages: [],
      mode: "build",
      permissionProfile: getStoredValue("code-permission-profile") || "accept",
      currentDir: "",
      previewContent: "",
      previewPath: "",
      previewKind: "text",
      previewMode: "source",
      previewTable: null,
      previewImageScale: null,
      previewWidth: Number(getStoredValue("code-preview-width") || 420),
      sidebarSessionHeight: Number(getStoredValue("code-session-height") || 0),
      sidebarWidth: Number(getStoredValue("code-sidebar-width") || 264),
      lastUsage: null,
      responseUsage: null,
      abortController: null,
      isStreaming: false,
      streamingSessionId: null,
      branchPanelOpen: false,
      _sessionMsgs: {},
      _sessionRuns: {},
      _sessionRunStates: {},
      _sessionStats: {},
      _sessionLastUsage: {},
      _sessionSaveChains: {},
      _activeRun: null,
      _foregroundNavigationSeq: 0,
      _backgroundDispatcher: {
        jobs: [],
        activeCount: 0,
        globalLimit: 3,
        perSessionLimit: 2,
      },
      _queuedMessagePumps: new Set(),
      pendingEdits: {},
      authorizationRequests: [],
      userInputRequests: {},
      _userInputResolvers: new Map(),
      authorizationPanelCollapsed: false,
      confirmingEditId: null,
      renamingSessionId: null,
      projectContext: null,
      memoryContext: null,
      skills: [],
      explicitSkill: null,
      disabledSkills: new Set(JSON.parse(getStoredValue("code-disabled-skills") || "[]")),
      attachedImages: [],
      responseStartTime: null,
      lang: getStoredValue("code-lang") || "zh",
      modelKeyMap: {},
      modelKeysMap: {},
      modelCatalogModels: [],
      modelCatalogStatusKey: "",
      modelCatalogSource: "empty",
      stats: {
        input: 0,
        output: 0,
        cache: 0,
      },
    };
  }

  function createSessionStateAccessors(state) {
    if (!state || typeof state !== "object") {
      throw new TypeError("Session state accessors require an application state object");
    }

    function ensureSessionRun(sessionId) {
      if (!sessionId) return null;
      if (!state._sessionRuns[sessionId]) {
        state._sessionRuns[sessionId] = {
          sessionId,
          isStreaming: false,
          abortController: null,
          responseStartTime: null,
          taskStartTime: null,
          modelWaitStartedAt: null,
          modelResponseStarted: false,
          hasFirstModelResponseStarted: false,
          modelRound: 0,
          modelRecovery: null,
          timerInterval: null,
          timerDisplay: null,
          recovery: null,
          runtimeRunId: "",
          agentRunId: "",
          agentEventCursor: 0,
        };
      }
      return state._sessionRuns[sessionId];
    }

    function getSessionRunState(sessionId) {
      if (!sessionId) return {};
      return state._sessionRunStates[sessionId] || {};
    }

    function setSessionRunState(sessionId, runState) {
      if (!sessionId) return;
      const normalized = runState && Object.keys(runState).length ? { ...runState } : {};
      state._sessionRunStates[sessionId] = normalized;
      const local = state.sessions.find((session) => session.id === sessionId);
      if (local) local.runState = normalized;
    }

    function getBackgroundRunCheckpoints(sessionId) {
      const checkpoints = getSessionRunState(sessionId)?.backgroundRuns;
      return Array.isArray(checkpoints) ? checkpoints.filter((item) => item?.id) : [];
    }

    function setBackgroundRunCheckpoint(sessionId, checkpoint) {
      if (!sessionId || !checkpoint?.id) return;
      const previous = getSessionRunState(sessionId);
      const backgroundRuns = getBackgroundRunCheckpoints(sessionId)
        .filter((item) => item.id !== checkpoint.id);
      backgroundRuns.push({ ...checkpoint });
      setSessionRunState(sessionId, { ...previous, backgroundRuns });
    }

    function removeBackgroundRunCheckpoint(sessionId, jobId) {
      if (!sessionId || !jobId) return;
      const previous = getSessionRunState(sessionId);
      const backgroundRuns = getBackgroundRunCheckpoints(sessionId)
        .filter((item) => item.id !== jobId);
      const nextState = { ...previous };
      if (backgroundRuns.length) nextState.backgroundRuns = backgroundRuns;
      else delete nextState.backgroundRuns;
      setSessionRunState(sessionId, nextState);
    }

    function getQueuedMessageCheckpoints(sessionId) {
      const queuedMessages = getSessionRunState(sessionId)?.queuedMessages;
      return Array.isArray(queuedMessages) ? queuedMessages.filter((item) => item?.id) : [];
    }

    function setQueuedMessageCheckpoints(sessionId, queuedMessages) {
      if (!sessionId) return;
      const previous = getSessionRunState(sessionId);
      const nextState = { ...previous };
      const normalized = Array.isArray(queuedMessages)
        ? queuedMessages.filter((item) => item?.id).map((item) => ({ ...item }))
        : [];
      if (normalized.length) nextState.queuedMessages = normalized;
      else delete nextState.queuedMessages;
      setSessionRunState(sessionId, nextState);
    }

    function getSessionMessages(sessionId) {
      if (!sessionId) return state.messages;
      if (sessionId === state.sessionId) return state.messages;
      if (!state._sessionMsgs[sessionId]) state._sessionMsgs[sessionId] = [];
      return state._sessionMsgs[sessionId];
    }

    function setSessionMessages(sessionId, messages) {
      if (!sessionId) return;
      state._sessionMsgs[sessionId] = messages;
      if (sessionId === state.sessionId) state.messages = messages;
    }

    function appendSessionMessages(sessionId, ...messages) {
      if (!sessionId || messages.length === 0) return [];
      const target = getSessionMessages(sessionId);
      target.push(...messages.filter(Boolean));
      setSessionMessages(sessionId, target);
      return target;
    }

    function getSessionStats(sessionId) {
      if (!sessionId || sessionId === state.sessionId) return state.stats;
      if (!state._sessionStats[sessionId]) {
        state._sessionStats[sessionId] = { input: 0, output: 0, cache: 0, cost: 0 };
      }
      return state._sessionStats[sessionId];
    }

    function setSessionStats(sessionId, stats) {
      if (!sessionId) return;
      state._sessionStats[sessionId] = stats || { input: 0, output: 0, cache: 0, cost: 0 };
      if (sessionId === state.sessionId) state.stats = state._sessionStats[sessionId];
    }

    function getSessionLastUsage(sessionId = state.sessionId) {
      if (!sessionId) return state.lastUsage;
      return state._sessionLastUsage[sessionId] || null;
    }

    function setSessionLastUsage(sessionId, usage) {
      if (!sessionId) return;
      if (usage) state._sessionLastUsage[sessionId] = usage;
      else delete state._sessionLastUsage[sessionId];
      if (sessionId === state.sessionId) state.lastUsage = usage || null;
    }

    return Object.freeze({
      ensureSessionRun,
      getSessionRunState,
      setSessionRunState,
      getBackgroundRunCheckpoints,
      setBackgroundRunCheckpoint,
      removeBackgroundRunCheckpoint,
      getQueuedMessageCheckpoints,
      setQueuedMessageCheckpoints,
      getSessionMessages,
      setSessionMessages,
      appendSessionMessages,
      getSessionStats,
      setSessionStats,
      getSessionLastUsage,
      setSessionLastUsage,
    });
  }

  core.state = Object.freeze({
    createAppState,
    createSessionStateAccessors,
  });
})(window);
