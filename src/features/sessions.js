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

  features.sessions = Object.freeze({
    normalizeSessionMessages,
    collectPendingEdits,
    createSessionsFeature,
  });
})(window);
