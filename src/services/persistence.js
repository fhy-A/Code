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

  function createSessionPersistence({ requestJson, saveChains }) {
    if (typeof requestJson !== "function") {
      throw new TypeError("Session persistence requires a requestJson function");
    }
    if (!saveChains || typeof saveChains !== "object") {
      throw new TypeError("Session persistence requires a save chain registry");
    }

    async function saveSession(sessionId, payload) {
      if (!sessionId) return undefined;
      const previous = saveChains[sessionId] || Promise.resolve();
      const savePromise = previous
        .catch(() => {})
        .then(() => requestJson(`/api/sessions/${encodeURIComponent(sessionId)}`, {
          method: "PUT",
          body: JSON.stringify(payload || {}),
        }));
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
    createSessionPersistence,
  });
})(window);
