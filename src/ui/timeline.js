(function registerTimelineUi(global) {
  "use strict";

  const Code = global.Code;
  if (!Code?.ui) throw new Error("Code namespace must load before timeline UI");

  const FALLBACK_MAX_VISIBLE_MARKERS = 36;
  const DEFAULT_WHEEL_STEP = 3;
  const DEFAULT_MIN_TIMELINE_WIDTH = 560;
  const TIMELINE_MARKER_HEIGHT = 7;
  const TIMELINE_MARKER_GAP = 2;
  const TIMELINE_MARKER_PITCH = TIMELINE_MARKER_HEIGHT + TIMELINE_MARKER_GAP;
  const TIMELINE_MAX_VIEWPORT_RATIO = 0.7;
  const TIMELINE_TITLE_LIMIT = 48;
  const TIMELINE_ANSWER_LIMIT = 360;
  const TIMELINE_ANSWER_LINES = 3;

  function defaultMessageText(msg) {
    if (Array.isArray(msg?.content)) {
      return msg.content.find((item) => item?.type === "text")?.text || "";
    }
    return String(msg?.content || "");
  }

  function isTimelineInternalMessage(msg) {
    if (!msg) return true;
    if (msg.meta?._system) return true;
    if (msg.meta?.kind === "key-fallback") return true;
    if (msg.meta?.kind === "tool-round-limit") return true;
    return false;
  }

  function isTimelinePlanningPlaceholder(text) {
    const value = String(text || "").trim();
    if (!value) return true;
    if (/^Preparing\s+to\s+call\s+\d*\s*tools?/i.test(value)) return true;
    if (/^Calling\s+\d*\s*tools?/i.test(value)) return true;
    return false;
  }

  function normalizeTimelinePreview(value, limit = 0) {
    const normalized = String(value || "").replace(/\s+/g, " ").trim();
    if (!limit || normalized.length <= limit) return normalized;
    return `${normalized.slice(0, Math.max(1, limit - 1)).trimEnd()}…`;
  }

  function timelineMarkdownToPlainText(value) {
    const lines = String(value || "").replace(/\r\n?/g, "\n").split("\n");
    let fenceMarker = "";
    const plainLines = [];

    for (const sourceLine of lines) {
      const fenceMatch = sourceLine.match(/^\s*(`{3,}|~{3,})/);
      if (fenceMatch) {
        const marker = fenceMatch[1][0];
        if (!fenceMarker) fenceMarker = marker;
        else if (fenceMarker === marker) fenceMarker = "";
        continue;
      }

      let line = sourceLine;
      if (!fenceMarker) {
        if (/^\s{0,3}(?:[-*_]\s*){3,}$/.test(line)) {
          plainLines.push("");
          continue;
        }
        if (/^\s*\[[^\]]+\]:\s+\S+/.test(line)) continue;
        line = line
          .replace(/^\s{0,3}#{1,6}\s+/, "")
          .replace(/\s+#+\s*$/, "")
          .replace(/^\s{0,3}(?:>\s*)+/, "")
          .replace(/^\s{0,3}(?:[-+*]|\d+[.)])\s+/, "")
          .replace(/^\[[ xX]\]\s+/, "");
      }

      line = line
        .replace(/!\[([^\]]*)\]\((?:\\.|[^)])*\)/g, "$1")
        .replace(/\[([^\]]+)\]\((?:\\.|[^)])*\)/g, "$1")
        .replace(/\[([^\]]+)\]\[[^\]]*\]/g, "$1")
        .replace(/<((?:https?:\/\/|mailto:)[^>]+)>/gi, "$1")
        .replace(/`{1,3}([^`]+?)`{1,3}/g, "$1")
        .replace(/(\*\*\*|___)(.+?)\1/g, "$2")
        .replace(/(\*\*|__|~~)(.+?)\1/g, "$2")
        .replace(/(^|[\s([{])([*_])([^*_\n]+?)\2(?=$|[\s)\]},.!?:;])/g, "$1$3")
        .replace(/\\([\\`*_{}[\]()#+\-.!>])/g, "$1")
        .replace(/<[^>]+>/g, "")
        .trim();
      plainLines.push(line);
    }

    return plainLines.join("\n");
  }

  function normalizeTimelineAnswerPreview(value) {
    const lines = timelineMarkdownToPlainText(value)
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean);
    if (!lines.length) return "";
    let preview = lines.slice(0, TIMELINE_ANSWER_LINES).join("\n");
    const omittedLines = lines.length > TIMELINE_ANSWER_LINES;
    const omittedCharacters = preview.length > TIMELINE_ANSWER_LIMIT;
    if (omittedCharacters) {
      preview = preview.slice(0, TIMELINE_ANSWER_LIMIT - 1).trimEnd();
    }
    if ((omittedLines || omittedCharacters) && !preview.endsWith("…")) {
      preview += "…";
    }
    return preview;
  }

  function projectTimelineNodes(
    messages = [],
    getMessageText = defaultMessageText,
    predicates = {},
  ) {
    const nodes = [];
    const isInternalMessage = predicates.isInternalMessage || isTimelineInternalMessage;
    const isPlanningPlaceholder = predicates.isPlanningPlaceholder
      || isTimelinePlanningPlaceholder;
    let currentNode = null;
    for (let index = 0; index < messages.length; index += 1) {
      const msg = messages[index];
      if (!msg || isInternalMessage(msg)) continue;
      if (msg.role === "user") {
        const label = normalizeTimelinePreview(getMessageText(msg), TIMELINE_TITLE_LIMIT);
        currentNode = {
          index,
          label,
          assistantPreview: "",
          type: "user",
        };
        nodes.push(currentNode);
        continue;
      }
      if (
        msg.role !== "assistant"
        || !currentNode
        || msg.streaming
        || msg.meta?.toolCalls?.length
      ) {
        continue;
      }
      const answer = String(getMessageText(msg) || "").trim();
      if (!answer || isPlanningPlaceholder(answer)) continue;
      currentNode.assistantPreview = normalizeTimelineAnswerPreview(answer);
    }
    return nodes;
  }

  function syncSessionBranchMetadata(sessions = [], session = {}) {
    const summary = sessions.find((item) => item?.id === session?.id);
    if (!summary) return null;
    for (const key of ["_parentId", "_branchDepth", "_branches", "_branchMsgCount"]) {
      if (Object.prototype.hasOwnProperty.call(session, key)) summary[key] = session[key];
    }
    return summary;
  }

  function createTimelineFeature(options = {}) {
    const escapeHtml = options.escapeHtml || ((value) => String(value ?? ""));
    const t = options.t || ((key) => key);
    const getMessageText = options.getMessageText || defaultMessageText;
    const getMessages = options.getMessages || (() => []);
    const getSessions = options.getSessions || (() => []);
    const getSessionId = options.getSessionId || (() => "");
    const getTimelineElement = options.getTimelineElement || (() => null);
    const getMessageContainer = options.getMessageContainer || (() => null);
    const isInternalMessage = options.isInternalMessage
      || Code.ui.messages?.isInternalMessage
      || isTimelineInternalMessage;
    const isPlanningPlaceholder = options.isToolPlanningPlaceholder
      || Code.ui.messages?.isToolPlanningPlaceholder
      || isTimelinePlanningPlaceholder;
    const requestFrame = options.requestAnimationFrame
      || global.requestAnimationFrame
      || ((callback) => {
        callback();
        return 0;
      });
    const requestedMaxVisibleMarkers = Number(options.maxVisibleMarkers);
    const maxVisibleMarkerCeiling = Number.isFinite(requestedMaxVisibleMarkers)
      ? Math.max(4, Math.trunc(requestedMaxVisibleMarkers))
      : Number.POSITIVE_INFINITY;
    const requestedWheelStep = Number(options.wheelStep);
    const wheelStep = Number.isFinite(requestedWheelStep)
      ? Math.max(1, Math.trunc(requestedWheelStep))
      : DEFAULT_WHEEL_STEP;
    const requestedMinTimelineWidth = Number(options.minTimelineWidth);
    const minTimelineWidth = Number.isFinite(requestedMinTimelineWidth)
      ? Math.max(320, Math.trunc(requestedMinTimelineWidth))
      : DEFAULT_MIN_TIMELINE_WIDTH;
    const TimelineResizeObserver = options.ResizeObserver || global.ResizeObserver;
    const getViewportHeight = options.getViewportHeight
      || (() => Number(global.innerHeight) || 0);
    let timelineEntries = [];
    let timelineSignature = "";
    let timelineWindowStart = 0;
    let activeTimelinePosition = 0;
    let visibleTimelinePositions = new Set();
    let timelinePositionByMessageIndex = new Map();
    let visibleMarkerLimit = FALLBACK_MAX_VISIBLE_MARKERS;
    let renderedTimelineMarkup = "";
    let boundScrollContainer = null;
    let boundTimelineElement = null;
    let observedWidthContainer = null;
    let timelineResizeObserver = null;
    let scrollUpdatePending = false;

    function getBranchFlowMarker() {
      const sessions = getSessions();
      const sessionId = getSessionId();
      const current = sessions.find((session) => session.id === sessionId);
      if (!current || current._branchMsgCount == null) return null;
      const rawCount = Number(current._branchMsgCount);
      if (!Number.isFinite(rawCount) || rawCount < 0) return null;
      const parent = sessions.find((session) => session.id === current._parentId)
        || sessions.find((session) => Array.isArray(session._branches) && session._branches.includes(sessionId));
      if (!parent) return null;
      return {
        messageCount: Math.max(0, Math.trunc(rawCount)),
        parentTitle: parent.title || "",
      };
    }

    function renderBranchFlowProjection(parentTitle) {
      const label = t("branchedFromHere", { title: parentTitle || "" });
      return `<article class="msg branch-indicator"><div class="branch-indicator-bar"><span class="branch-indicator-icon" aria-hidden="true"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="6" y1="3" x2="6" y2="15"/><circle cx="18" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M18 9a9 9 0 0 1-9 9"/></svg></span><span>${escapeHtml(label)}</span></div></article>`;
    }

    function messageOffsetTop(target, container) {
      if (!target || !container) return Number.NaN;
      if (Number.isFinite(Number(target.offsetTop))) {
        let top = 0;
        let current = target;
        let guard = 0;
        while (current && current !== container && guard < 32) {
          top += Number(current.offsetTop) || 0;
          current = current.offsetParent;
          guard += 1;
        }
        return top;
      }
      if (target.getBoundingClientRect && container.getBoundingClientRect) {
        const targetRect = target.getBoundingClientRect();
        const containerRect = container.getBoundingClientRect();
        return (Number(container.scrollTop) || 0) + targetRect.top - containerRect.top;
      }
      return Number.NaN;
    }

    function clampTimelineWindowStart(start) {
      const lastStart = Math.max(0, timelineEntries.length - visibleMarkerLimit);
      return Math.max(0, Math.min(lastStart, Math.trunc(Number(start) || 0)));
    }

    function centeredTimelineWindowStart(position) {
      return clampTimelineWindowStart(position - Math.floor(visibleMarkerLimit / 2));
    }

    function calculateVisibleMarkerLimit() {
      const timeline = getTimelineElement();
      const timelineHeight = Math.max(0, Number(timeline?.clientHeight) || 0);
      const viewportHeight = Math.max(0, Number(getViewportHeight()) || 0);
      const heightLimits = [];
      if (timelineHeight) heightLimits.push(timelineHeight);
      if (viewportHeight) heightLimits.push(viewportHeight * TIMELINE_MAX_VIEWPORT_RATIO);
      if (!heightLimits.length) {
        return Math.min(FALLBACK_MAX_VISIBLE_MARKERS, maxVisibleMarkerCeiling);
      }
      const availableHeight = Math.min(...heightLimits);
      const calculated = Math.max(
        4,
        Math.floor((availableHeight + TIMELINE_MARKER_GAP) / TIMELINE_MARKER_PITCH),
      );
      return Math.min(calculated, maxVisibleMarkerCeiling);
    }

    function syncTimelineMarkerStates() {
      const timeline = getTimelineElement();
      const activeEntry = timelineEntries[activeTimelinePosition];
      if (!timeline || !activeEntry) return;
      timeline.querySelectorAll(".tl-marker").forEach((marker) => {
        const position = timelinePositionByMessageIndex.get(String(marker.dataset.index));
        const active = position === activeTimelinePosition;
        const visible = visibleTimelinePositions.has(position);
        marker.classList.toggle("is-visible", visible);
        marker.classList.toggle("is-active", active);
        if (active) marker.setAttribute("aria-current", "location");
        else marker.removeAttribute("aria-current");
      });
    }

    function syncTimelineHoverCascade(hoveredMarker = null) {
      const timeline = getTimelineElement();
      if (!timeline) return;
      const markers = Array.from(timeline.querySelectorAll(".tl-marker"));
      const hoveredIndex = hoveredMarker ? markers.indexOf(hoveredMarker) : -1;
      markers.forEach((marker, index) => {
        const distance = hoveredIndex < 0 ? Number.POSITIVE_INFINITY : Math.abs(index - hoveredIndex);
        marker.classList.toggle("is-hover-main", distance === 0);
        marker.classList.toggle("is-hover-near-1", distance === 1);
        marker.classList.toggle("is-hover-near-2", distance === 2);
      });
    }

    function findActiveTimelinePosition() {
      const container = getMessageContainer();
      if (!container || !timelineEntries.length) return 0;
      const scrollTop = Math.max(0, Number(container.scrollTop) || 0);
      const viewportHeight = Math.max(1, Number(container.clientHeight) || 1);
      const focusLine = scrollTop + viewportHeight * 0.32;
      let activePosition = 0;
      for (let position = 0; position < timelineEntries.length; position += 1) {
        const entry = timelineEntries[position];
        const top = messageOffsetTop(entry.target, container);
        if (!Number.isFinite(top)) continue;
        if (top <= focusLine) activePosition = position;
        else break;
      }
      return activePosition;
    }

    function findVisibleTimelinePositions() {
      const container = getMessageContainer();
      const positions = new Set();
      if (!container || !timelineEntries.length) return positions;
      const viewportStart = Math.max(0, Number(container.scrollTop) || 0);
      const viewportHeight = Math.max(1, Number(container.clientHeight) || 1);
      const viewportEnd = viewportStart + viewportHeight;
      const scrollHeight = Math.max(viewportEnd, Number(container.scrollHeight) || 0);
      for (let position = 0; position < timelineEntries.length; position += 1) {
        const start = messageOffsetTop(timelineEntries[position].target, container);
        if (!Number.isFinite(start)) continue;
        const nextStart = position + 1 < timelineEntries.length
          ? messageOffsetTop(timelineEntries[position + 1].target, container)
          : Math.max(scrollHeight, start + 1);
        const end = Number.isFinite(nextStart) ? Math.max(start + 1, nextStart) : start + 1;
        if (start < viewportEnd && end > viewportStart) positions.add(position);
        if (start >= viewportEnd) break;
      }
      return positions;
    }

    function renderTimelineWindow() {
      const timeline = getTimelineElement();
      if (!timeline || !timelineEntries.length) return;
      timelineWindowStart = clampTimelineWindowStart(timelineWindowStart);
      const visibleEntries = timelineEntries.slice(
        timelineWindowStart,
        timelineWindowStart + visibleMarkerLimit,
      );
      const markers = visibleEntries.map((entry, visiblePosition) => {
        const title = entry.node.label || t("timelineUntitled");
        const answer = entry.node.assistantPreview || t("timelineNoFinalAnswer");
        const answerClass = `tl-bubble-answer${entry.node.assistantPreview ? "" : " is-empty"}`;
        const absolutePosition = timelineWindowStart + visiblePosition;
        const edgeClass = visiblePosition < 2
          ? " is-edge-start"
          : (visiblePosition >= visibleEntries.length - 2 ? " is-edge-end" : "");
        const previewId = `timeline-preview-${entry.node.index}`;
        return `<button class="tl-marker${edgeClass}" type="button" role="listitem" data-index="${entry.node.index}" aria-setsize="${timelineEntries.length}" aria-posinset="${absolutePosition + 1}" aria-label="${escapeHtml(t("timelineJumpTo", { title }))}" aria-describedby="${previewId}"><span class="tl-line" aria-hidden="true"></span><span class="tl-bubble" id="${previewId}" role="tooltip"><strong class="tl-bubble-title">${escapeHtml(title)}</strong><span class="${answerClass}">${escapeHtml(answer)}</span></span></button>`;
      }).join("");
      const overflowClasses = [
        timelineWindowStart > 0 ? "has-before" : "",
        timelineWindowStart + visibleEntries.length < timelineEntries.length ? "has-after" : "",
      ].filter(Boolean).join(" ");
      const trackClass = `tl-track${overflowClasses ? ` ${overflowClasses}` : ""}`;
      const windowHeight = Math.max(
        TIMELINE_MARKER_HEIGHT,
        visibleEntries.length * TIMELINE_MARKER_PITCH - TIMELINE_MARKER_GAP,
      );
      const markup = `<div class="${trackClass}" role="list" data-window-start="${timelineWindowStart}" style="--timeline-visible-count:${visibleEntries.length};--timeline-window-height:${windowHeight}px">${markers}</div>`;
      const shouldReplace = markup !== renderedTimelineMarkup
        || timeline.querySelectorAll(".tl-marker").length !== visibleEntries.length;
      if (shouldReplace) {
        timeline.innerHTML = markup;
        renderedTimelineMarkup = markup;
        timeline.querySelectorAll(".tl-marker").forEach((marker) => {
          marker.addEventListener("mouseenter", () => {
            syncTimelineHoverCascade(marker);
          });
          marker.addEventListener("mouseleave", () => {
            syncTimelineHoverCascade();
          });
          marker.addEventListener("click", () => {
            const position = timelineEntries.findIndex(
              (entry) => String(entry.node.index) === String(marker.dataset.index),
            );
            if (position >= 0) {
              activeTimelinePosition = position;
              visibleTimelinePositions.add(position);
            }
            syncTimelineMarkerStates();
            const currentTarget = getMessageContainer()
              ?.querySelector(`[data-msg-index="${marker.dataset.index}"]`);
            currentTarget?.scrollIntoView({ behavior: "smooth", block: "start" });
          });
        });
      }
      timeline.classList.add("visible");
      syncTimelineMarkerStates();
    }

    function updateActiveTimelineMarker() {
      if (!timelineEntries.length) return;
      activeTimelinePosition = findActiveTimelinePosition();
      visibleTimelinePositions = findVisibleTimelinePositions();
      if (!visibleTimelinePositions.size) visibleTimelinePositions.add(activeTimelinePosition);
      const windowEnd = timelineWindowStart + visibleMarkerLimit;
      if (
        activeTimelinePosition < timelineWindowStart
        || activeTimelinePosition >= windowEnd
      ) {
        timelineWindowStart = centeredTimelineWindowStart(activeTimelinePosition);
        renderTimelineWindow();
        return;
      }
      syncTimelineMarkerStates();
    }

    function scheduleActiveTimelineMarker() {
      if (scrollUpdatePending) return;
      scrollUpdatePending = true;
      requestFrame(() => {
        scrollUpdatePending = false;
        updateActiveTimelineMarker();
      });
    }

    function bindTimelineScroll() {
      const container = getMessageContainer();
      if (!container || container === boundScrollContainer) return;
      boundScrollContainer?.removeEventListener?.("scroll", scheduleActiveTimelineMarker);
      container.addEventListener?.("scroll", scheduleActiveTimelineMarker, { passive: true });
      boundScrollContainer = container;
    }

    function handleTimelineWheel(event) {
      if (timelineEntries.length <= visibleMarkerLimit) return;
      const direction = Math.sign(Number(event?.deltaY) || 0);
      if (!direction) return;
      event.preventDefault?.();
      event.stopPropagation?.();
      const nextStart = clampTimelineWindowStart(
        timelineWindowStart + direction * wheelStep,
      );
      if (nextStart === timelineWindowStart) return;
      timelineWindowStart = nextStart;
      renderTimelineWindow();
    }

    function bindTimelineWheel() {
      const timeline = getTimelineElement();
      if (!timeline || timeline === boundTimelineElement) return;
      boundTimelineElement?.removeEventListener?.("wheel", handleTimelineWheel);
      timeline.addEventListener?.("wheel", handleTimelineWheel, { passive: false });
      boundTimelineElement = timeline;
    }

    function updateTimelineLayoutState() {
      const timeline = getTimelineElement();
      const container = getMessageContainer();
      if (!timeline || !container) return;
      const width = Number(container.clientWidth) || 0;
      const constrained = width > 0 && width < minTimelineWidth;
      timeline.classList.toggle?.("is-space-constrained", constrained);
      if (constrained) timeline.setAttribute?.("aria-hidden", "true");
      else timeline.removeAttribute?.("aria-hidden");
      activeTimelinePosition = findActiveTimelinePosition();
      visibleTimelinePositions = findVisibleTimelinePositions();
      if (!visibleTimelinePositions.size && timelineEntries.length) {
        visibleTimelinePositions.add(activeTimelinePosition);
      }
      const nextVisibleMarkerLimit = calculateVisibleMarkerLimit();
      if (nextVisibleMarkerLimit === visibleMarkerLimit) {
        syncTimelineMarkerStates();
        return;
      }
      visibleMarkerLimit = nextVisibleMarkerLimit;
      timelineWindowStart = centeredTimelineWindowStart(activeTimelinePosition);
      renderedTimelineMarkup = "";
      if (timelineEntries.length) renderTimelineWindow();
    }

    function bindTimelineResize() {
      const container = getMessageContainer();
      if (!container) return;
      if (container !== observedWidthContainer) {
        timelineResizeObserver?.disconnect?.();
        observedWidthContainer = container;
        if (typeof TimelineResizeObserver === "function") {
          timelineResizeObserver = new TimelineResizeObserver(updateTimelineLayoutState);
          timelineResizeObserver.observe?.(container);
        }
      }
      updateTimelineLayoutState();
    }

    function clearTimeline() {
      const timeline = getTimelineElement();
      if (!timeline) return;
      timeline.innerHTML = "";
      timeline.classList.remove("visible");
      timelineEntries = [];
      timelineSignature = "";
      timelineWindowStart = 0;
      activeTimelinePosition = 0;
      visibleTimelinePositions = new Set();
      timelinePositionByMessageIndex = new Map();
      renderedTimelineMarkup = "";
    }

    function renderTimeline() {
      const timeline = getTimelineElement();
      if (!timeline) return;
      const nodes = projectTimelineNodes(getMessages(), getMessageText, {
        isInternalMessage,
        isPlanningPlaceholder,
      });
      if (nodes.length < 2) {
        clearTimeline();
        return;
      }
      const nextSignature = nodes.map((node) => (
        JSON.stringify([node.index, node.label, node.assistantPreview])
      )).join("\n");
      const signatureChanged = nextSignature !== timelineSignature;
      const nextVisibleMarkerLimit = calculateVisibleMarkerLimit();
      const visibleLimitChanged = nextVisibleMarkerLimit !== visibleMarkerLimit;
      visibleMarkerLimit = nextVisibleMarkerLimit;
      timelineEntries = nodes.map((node) => ({
        node,
        target: getMessageContainer()?.querySelector(`[data-msg-index="${node.index}"]`),
      }));
      timelinePositionByMessageIndex = new Map(
        timelineEntries.map((entry, position) => [String(entry.node.index), position]),
      );
      activeTimelinePosition = findActiveTimelinePosition();
      visibleTimelinePositions = findVisibleTimelinePositions();
      if (!visibleTimelinePositions.size) visibleTimelinePositions.add(activeTimelinePosition);
      if (signatureChanged || visibleLimitChanged) {
        timelineSignature = nextSignature;
        timelineWindowStart = centeredTimelineWindowStart(activeTimelinePosition);
        renderedTimelineMarkup = "";
      }
      renderTimelineWindow();
      bindTimelineScroll();
      bindTimelineWheel();
      bindTimelineResize();
      updateActiveTimelineMarker();
    }

    return Object.freeze({
      clearTimeline,
      getBranchFlowMarker,
      projectTimelineNodes: (messages) => projectTimelineNodes(messages, getMessageText, {
        isInternalMessage,
        isPlanningPlaceholder,
      }),
      renderBranchFlowProjection,
      renderTimeline,
      updateActiveTimelineMarker,
    });
  }

  Code.ui.timeline = Object.freeze({
    createTimelineFeature,
    DEFAULT_MIN_TIMELINE_WIDTH,
    TIMELINE_MARKER_PITCH,
    TIMELINE_MAX_VIEWPORT_RATIO,
    projectTimelineNodes,
    syncSessionBranchMetadata,
  });
})(window);
