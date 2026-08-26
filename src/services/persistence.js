(function initializeCodePersistence(global) {
  "use strict";

  const services = global.Code && global.Code.services;
  if (!services) throw new Error("Code services namespace must load before persistence");

  function serializeSessionMessages(messages = [], options = {}) {
    const includeModel = options.includeModel === true;
    const includeTime = options.includeTime === true;
    return (Array.isArray(messages) ? messages : []).map((message) => ({
      id: message.id || undefined,
      role: message.role,
      content: message.content || "",
      thought: message.thought || "",
      meta: message.meta || {},
      _images: message._images || undefined,
      ...(includeModel ? { _model: message._model || undefined } : {}),
      ...(includeTime ? { _time: message._time || undefined } : {}),
    }));
  }

  function buildSessionSavePayload(options = {}) {
    const payload = {
      title: options.title || "Untitled",
      stats: { ...(options.stats || {}) },
      lastUsage: options.lastUsage || null,
      runState: { ...(options.runState || {}) },
    };
    if (options.persistMessages === true) {
      payload.messages = serializeSessionMessages(
        options.messages,
        { includeModel: true, includeTime: true },
      );
    }
    return payload;
  }

  function normalizeSessionRevision(value) {
    const revision = Number(value);
    return Number.isInteger(revision) && revision >= 0 ? revision : 0;
  }

  function isSessionRevisionConflict(error) {
    return Number(error?.status || 0) === 409
      && String(error?.data?.errorCode || "") === "session_revision_conflict";
  }

  function createSessionPersistence({
    requestJson,
    saveChains,
    getRevision = () => 0,
    setRevision = () => {},
    onRevisionConflict = null,
  }) {
    if (typeof requestJson !== "function") {
      throw new TypeError("Session persistence requires a requestJson function");
    }
    if (!saveChains || typeof saveChains !== "object") {
      throw new TypeError("Session persistence requires a save chain registry");
    }
    const saveGenerations = Object.create(null);
    const conflictSnapshots = Object.create(null);

    async function saveSession(sessionId, payload) {
      if (!sessionId) return undefined;
      const generation = Number(saveGenerations[sessionId] || 0);
      // Freeze the caller's semantic snapshot before entering the per-session
      // queue. Message metadata remains mutable while routing and AgentRun
      // recovery continue; cloning only when the queued callback starts lets a
      // later mutation rewrite the meaning of an already-enqueued save.
      const queuedPayload = JSON.parse(JSON.stringify(payload || {}));
      const previous = saveChains[sessionId] || Promise.resolve();
      const savePromise = previous
        .catch(() => {})
        .then(async () => {
          if (generation !== Number(saveGenerations[sessionId] || 0)) {
            return conflictSnapshots[sessionId];
          }
          const requestPayload = queuedPayload;
          if (Object.prototype.hasOwnProperty.call(requestPayload, "messages")) {
            requestPayload.expectedRevision = normalizeSessionRevision(getRevision(sessionId));
          }
          try {
            const savedSession = await requestJson(
              `/api/sessions/${encodeURIComponent(sessionId)}`,
              { method: "PUT", body: JSON.stringify(requestPayload) },
            );
            if (savedSession && Object.prototype.hasOwnProperty.call(savedSession, "revision")) {
              setRevision(sessionId, normalizeSessionRevision(savedSession.revision));
            }
            delete conflictSnapshots[sessionId];
            return savedSession;
          } catch (error) {
            if (!isSessionRevisionConflict(error) || typeof onRevisionConflict !== "function") {
              throw error;
            }
            saveGenerations[sessionId] = generation + 1;
            const authoritative = await onRevisionConflict({
              sessionId,
              error,
              payload: requestPayload,
            });
            if (authoritative && Object.prototype.hasOwnProperty.call(authoritative, "revision")) {
              setRevision(sessionId, normalizeSessionRevision(authoritative.revision));
            }
            conflictSnapshots[sessionId] = authoritative;
            return authoritative;
          }
        });
      saveChains[sessionId] = savePromise;

      try {
        return await savePromise;
      } finally {
        if (saveChains[sessionId] === savePromise) {
          delete saveChains[sessionId];
        }
      }
    }

    return Object.freeze({
      saveSession,
    });
  }

  services.persistence = Object.freeze({
    serializeSessionMessages,
    buildSessionSavePayload,
    normalizeSessionRevision,
    isSessionRevisionConflict,
    createSessionPersistence,
  });
})(window);
