(function initializeCodeBranches(global) {
  "use strict";

  const features = global.Code && global.Code.features;
  if (!features) throw new Error("Code features namespace must load before branches");

  function createBranchesFeature({
    state,
    elements,
    requestJson,
    stateAccessors,
    session,
    view,
    t,
    escapeHtml,
  }) {
    if (!state || typeof state !== "object") {
      throw new TypeError("Branches feature requires application state");
    }
    if (typeof requestJson !== "function") {
      throw new TypeError("Branches feature requires JSON request access");
    }
    if (!session?.loadSession || !session?.refreshSessions || !session?.archiveSession) {
      throw new TypeError("Branches feature requires session coordination");
    }

    const {
      getSessionLastUsage,
      getSessionStats,
      setSessionLastUsage,
      setSessionStats,
    } = stateAccessors;

    function buildBranchTree(focusSessionId) {
      if (!focusSessionId || !state.sessions.length) return null;
      const sessions = state.sessions;
      let current = sessions.find((item) => item.id === focusSessionId) || null;
      if (!current) return null;

      while (current._parentId) {
        const parent = sessions.find((item) => item.id === current._parentId) || null;
        if (!parent) break;
        current = parent;
      }
      const rootId = current.id;

      function makeNode(record) {
        const explicitBranchIds = Array.isArray(record._branches) ? record._branches : [];
        const derivedBranchIds = sessions
          .filter((item) => item._parentId === record.id)
          .map((item) => item.id);
        const branchIds = [...new Set([...explicitBranchIds, ...derivedBranchIds])];
        const children = branchIds
          .map((branchId) => sessions.find((item) => item.id === branchId) || null)
          .filter(Boolean)
          .map(makeNode);
        return {
          id: record.id,
          title: record.title || t("untitledSession"),
          depth: record._branchDepth || 0,
          isActive: record.id === state.sessionId,
          children,
        };
      }

      const root = sessions.find((item) => item.id === rootId);
      return root ? makeNode(root) : null;
    }

    async function switchToBranch(sessionId) {
      state._keepBranchOpen = true;
      await session.loadSession(sessionId);
      if (state.branchPanelOpen) renderBranchTree();
    }

    function renderBranchTree() {
      if (!elements.branchTree) return;
      const root = buildBranchTree(state.sessionId);
      if (!root) {
        elements.branchTree.innerHTML = `<div class="branch-empty">${t("noBranches")}</div>`;
        return;
      }

      function renderNode(node, depth) {
        const indent = depth * 20;
        const activeClass = node.isActive ? " active" : "";
        let html = `<div class="branch-node${activeClass}" data-session-id="${escapeHtml(node.id)}" style="padding-left:${indent + 12}px">`;
        html += `<span class="branch-title">${escapeHtml(node.title)}</span>`;
        html += `<button class="branch-archive-btn" data-session-id="${escapeHtml(node.id)}" title="${t("archiveSession")}" aria-label="${t("archiveSession")}"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 8v13H3V8"/><path d="M1 3h22v5H1z"/><path d="M10 12h4"/></svg></button>`;
        html += "</div>";
        for (const child of node.children) html += renderNode(child, depth + 1);
        return html;
      }

      elements.branchTree.innerHTML = renderNode(root, 0);
      elements.branchTree.querySelectorAll(".branch-node").forEach((node) => {
        node.addEventListener("click", (event) => {
          if (event.target.closest(".branch-archive-btn")) return;
          const sessionId = node.getAttribute("data-session-id");
          if (sessionId && sessionId !== state.sessionId) void switchToBranch(sessionId);
        });
      });
      elements.branchTree.querySelectorAll(".branch-archive-btn").forEach((button) => {
        button.addEventListener("click", (event) => {
          event.stopPropagation();
          const sessionId = button.getAttribute("data-session-id");
          if (sessionId) void session.archiveSession(sessionId);
        });
      });
    }

    async function createBranch(title) {
      if (!state.sessionId) {
        view.showToast(t("createSessionFirst"), "warning");
        return;
      }
      if (state.isStreaming) {
        view.showToast(t("stopBeforeBranch"), "warning");
        return;
      }

      const parentSessionId = state.sessionId;
      const parentStats = { ...(getSessionStats(parentSessionId) || {}) };
      const parentLastUsage = getSessionLastUsage(parentSessionId);
      let branchTitle = title;
      if (!branchTitle) {
        const current = state.sessions.find((item) => item.id === parentSessionId);
        branchTitle = t("branchTitleTemplate", { title: current?.title || "" });
      }

      try {
        const response = await requestJson(
          `/api/sessions/${encodeURIComponent(parentSessionId)}/branch`,
          {
            method: "POST",
            body: JSON.stringify({ title: branchTitle }),
          },
        );
        const inheritedStats = response.stats && Object.keys(response.stats).length
          ? { ...response.stats }
          : parentStats;
        setSessionStats(response.id, inheritedStats);
        setSessionLastUsage(response.id, response.lastUsage || parentLastUsage);
        await session.refreshSessions();
        state._keepBranchOpen = true;
        await session.loadSession(response.id);
        if (state.branchPanelOpen) renderBranchTree();
      } catch (error) {
        view.showToast(`${t("branchFailed")}: ${error.message || error}`, "error");
      }
    }

    function bind() {
      elements.createBranchBtn?.addEventListener("click", () => {
        void createBranch();
      });
    }

    return Object.freeze({
      buildBranchTree,
      renderBranchTree,
      createBranch,
      switchToBranch,
      bind,
    });
  }

  features.branches = Object.freeze({
    createBranchesFeature,
  });
})(window);
