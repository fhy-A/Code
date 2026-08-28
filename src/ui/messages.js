(function registerMessagesUi(global) {
  "use strict";

  const Code = global.Code;
  if (!Code?.ui) throw new Error("Code namespace must load before messages UI");

  const COPY_SVG = '<svg width="14" height="14" viewBox="0 0 1024 1024" fill="currentColor" xmlns="http://www.w3.org/2000/svg"><path d="M761.088 715.3152a38.7072 38.7072 0 0 1 0-77.4144 37.4272 37.4272 0 0 0 37.4272-37.4272V265.0112a37.4272 37.4272 0 0 0-37.4272-37.4272H425.6256a37.4272 37.4272 0 0 0-37.4272 37.4272 38.7072 38.7072 0 1 1-77.4144 0 115.0976 115.0976 0 0 1 114.8416-114.8416h335.4624a115.0976 115.0976 0 0 1 114.8416 114.8416v335.4624a115.0976 115.0976 0 0 1-114.8416 114.8416z"/><path d="M589.4656 883.0976H268.1856a121.1392 121.1392 0 0 1-121.2928-121.2928v-322.56a121.1392 121.1392 0 0 1 121.2928-121.344h321.28a121.1392 121.1392 0 0 1 121.2928 121.2928v322.56c1.28 67.1232-54.1696 121.344-121.2928 121.344zM268.1856 395.3152a43.52 43.52 0 0 0-43.8784 43.8784v322.56a43.52 43.52 0 0 0 43.8784 43.8784h321.28a43.52 43.52 0 0 0 43.8784-43.8784v-322.56a43.52 43.52 0 0 0-43.8784-43.8784z"/></svg>';
  const COPY_DONE = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>';
  const INTERNAL_GOAL_TOOL_NAMES = new Set([
    "goal_create",
    "goal_set_plan",
    "goal_revise_plan",
    "goal_start_step",
    "goal_complete_step",
    "goal_raise_gate",
    "goal_clear_gate",
    "goal_ready_for_acceptance",
    "goal_complete",
    "goal_cancel",
  ]);

  function projectedToolName(value) {
    return String(
      value?.function?.name
      || value?.name
      || value?.action
      || value?.meta?.action
      || value?.meta?.tool?.action
      || "",
    );
  }

  function isInternalGoalTool(value) {
    return INTERNAL_GOAL_TOOL_NAMES.has(projectedToolName(value));
  }

  function createMessageScrollController(options = {}) {
    const container = options.container;
    const content = options.content || container;
    const button = options.button || null;
    const focusTarget = options.focusTarget || null;
    const bottomTolerance = Number(options.bottomTolerance ?? 2);
    const revealThreshold = Number(options.revealThreshold ?? 160);
    const requestFrame = options.requestAnimationFrame
      || global.requestAnimationFrame?.bind(global)
      || ((callback) => global.setTimeout(callback, 0));
    const cancelFrame = options.cancelAnimationFrame
      || global.cancelAnimationFrame?.bind(global)
      || global.clearTimeout?.bind(global)
      || (() => {});
    const setTimer = options.setTimeout
      || global.setTimeout?.bind(global)
      || ((callback) => { callback(); return null; });
    const clearTimer = options.clearTimeout
      || global.clearTimeout?.bind(global)
      || (() => {});
    const userScrollIntentLeaseMs = Math.max(
      80,
      Number(options.userScrollIntentLeaseMs ?? 280),
    );
    const ResizeObserverClass = options.ResizeObserver || global.ResizeObserver;
    const getLabel = options.getLabel || ((key) => key);
    const isCompactViewport = options.isCompactViewport
      || (() => Boolean(global.matchMedia?.("(max-width: 900px)")?.matches));
    const findAnchorElement = options.findAnchorElement || ((messageIndex) => (
      content?.querySelector?.(`.msg.user[data-msg-index="${messageIndex}"]`) || null
    ));
    const measureAnchorTop = options.measureAnchorTop || ((element) => {
      if (!element || !container) return null;
      const elementRect = element.getBoundingClientRect?.();
      const containerRect = container.getBoundingClientRect?.();
      if (elementRect && containerRect) {
        return Number(container.scrollTop || 0) + Number(elementRect.top || 0) - Number(containerRect.top || 0);
      }
      const offsetTop = Number(element.offsetTop);
      return Number.isFinite(offsetTop) ? offsetTop : null;
    });
    const applyAnchorReserve = options.applyAnchorReserve || ((pixels) => {
      const next = `${Math.max(0, Math.round(Number(pixels || 0)))}px`;
      content?.style?.setProperty?.("--message-reading-anchor-space", next);
      content?.classList?.toggle?.("has-reading-anchor-space", Number(pixels || 0) > 0);
    });
    let sessionId = String(options.sessionId || "");
    let following = true;
    let visible = false;
    let suppressed = false;
    let running = false;
    let frameId = null;
    let resizeObserver = null;
    let connected = false;
    let preservedScrollTop = Number(container?.scrollTop || 0);
    let userScrollIntentActive = false;
    let userScrollIntentDirection = 0;
    let userScrollIntentEpoch = 0;
    let userScrollIntentTimer = null;
    let touchStartY = null;
    let scrollbarIntent = false;
    let readingAnchor = null;
    let lastObservedScrollTop = Number(container?.scrollTop || 0);
    let programmaticScrollTarget = null;
    const passiveListenerOptions = { passive: true };

    function hasUserScrollOwnership() {
      return userScrollIntentActive || touchStartY != null || scrollbarIntent;
    }

    function recordUserScrollPosition() {
      const current = Number(container?.scrollTop || 0);
      preservedScrollTop = current;
      lastObservedScrollTop = current;
      return current;
    }

    function clearUserScrollIntent() {
      userScrollIntentEpoch += 1;
      userScrollIntentActive = false;
      userScrollIntentDirection = 0;
      if (userScrollIntentTimer != null) clearTimer(userScrollIntentTimer);
      userScrollIntentTimer = null;
    }

    function renewUserScrollIntent(direction = 0) {
      const nextDirection = Math.sign(Number(direction || 0));
      if (nextDirection) userScrollIntentDirection = nextDirection;
      userScrollIntentActive = true;
      const epoch = ++userScrollIntentEpoch;
      if (userScrollIntentTimer != null) clearTimer(userScrollIntentTimer);
      userScrollIntentTimer = setTimer(() => {
        if (epoch !== userScrollIntentEpoch) return;
        userScrollIntentTimer = null;
        userScrollIntentActive = false;
        userScrollIntentDirection = 0;
        recordUserScrollPosition();
        if (following && !hasUserScrollOwnership()) scheduleFollow();
        reconcile();
      }, userScrollIntentLeaseMs);
      cancelScheduledFrame();
      programmaticScrollTarget = null;
      return epoch;
    }

    function maxScrollTop() {
      if (!container) return 0;
      return Math.max(0, Number(container.scrollHeight || 0) - Number(container.clientHeight || 0));
    }

    function distanceToBottom() {
      if (!container) return 0;
      const physicalDistance = Math.max(0, maxScrollTop() - Number(container.scrollTop || 0));
      const consumedReadingDistance = Number(readingAnchor?.userConsumedReserve || 0);
      return Math.max(0, physicalDistance + consumedReadingDistance);
    }

    function realContentDistanceToBottom() {
      if (!container) return 0;
      const temporaryReserve = Number(readingAnchor?.remainingReserve || 0);
      const realContentBottom = Math.max(
        0,
        Number(container.scrollHeight || 0) - temporaryReserve,
      );
      const viewportBottom = Number(container.scrollTop || 0) + Number(container.clientHeight || 0);
      return Math.max(0, realContentBottom - viewportBottom);
    }

    function writeScrollTop(value) {
      if (!container) return;
      const next = Math.max(0, Number(value || 0));
      programmaticScrollTarget = next;
      container.scrollTop = next;
      lastObservedScrollTop = Number(container.scrollTop || next);
      preservedScrollTop = lastObservedScrollTop;
    }

    function setAnchorReserve(value) {
      if (!readingAnchor) return 0;
      const next = Math.max(0, Math.round(Number(value || 0)));
      readingAnchor.remainingReserve = next;
      applyAnchorReserve(next);
      return next;
    }

    function clearReadingAnchor() {
      if (readingAnchor) setAnchorReserve(0);
      readingAnchor = null;
      applyAnchorReserve(0);
    }

    function anchorOffset() {
      return isCompactViewport() ? 20 : 32;
    }

    function reconcileReadingAnchor(initialize = false) {
      if (!readingAnchor || !container) return false;
      const element = findAnchorElement(readingAnchor.messageIndex);
      const measuredTop = measureAnchorTop(element);
      if (!Number.isFinite(measuredTop)) {
        clearReadingAnchor();
        return false;
      }
      const currentReserve = Number(readingAnchor.remainingReserve || 0);
      const realScrollHeight = Math.max(0, Number(container.scrollHeight || 0) - currentReserve);
      const desiredTop = Math.max(0, Math.round(measuredTop - anchorOffset()));
      const requiredReserve = Math.max(
        0,
        Math.round(desiredTop + Number(container.clientHeight || 0) - realScrollHeight),
      );
      const nextReserve = initialize
        ? requiredReserve
        : Math.min(currentReserve, requiredReserve);
      setAnchorReserve(nextReserve);
      readingAnchor.targetScrollTop = Math.min(desiredTop, maxScrollTop());
      readingAnchor.initialized = true;
      return true;
    }

    function captureAnchorLayoutAdjustment() {
      if (!readingAnchor || hasUserScrollOwnership() || !container) return;
      const currentScrollTop = Number(container.scrollTop || 0);
      if (Math.abs(currentScrollTop - lastObservedScrollTop) <= bottomTolerance) return;
      programmaticScrollTarget = Number(readingAnchor.targetScrollTop || currentScrollTop);
      lastObservedScrollTop = currentScrollTop;
      preservedScrollTop = currentScrollTop;
    }

    function beginReadingAnchor(ownerSessionId, messageIndex) {
      if (String(ownerSessionId || "") !== sessionId || !Number.isInteger(Number(messageIndex))) return false;
      cancelScheduledFrame();
      clearReadingAnchor();
      readingAnchor = {
        initialized: false,
        messageIndex: Number(messageIndex),
        remainingReserve: 0,
        targetScrollTop: 0,
        userConsumedReserve: 0,
      };
      following = true;
      visible = false;
      clearUserScrollIntent();
      if (!reconcileReadingAnchor(true)) {
        scheduleFollow();
        return false;
      }
      writeScrollTop(readingAnchor.targetScrollTop);
      updateButton();
      scheduleFollow();
      return true;
    }

    function consumeAnchorReserveForUpwardScroll(distance) {
      if (!readingAnchor) return 0;
      const consumed = Math.min(
        Number(readingAnchor.remainingReserve || 0),
        Math.max(0, Number(distance || 0)),
      );
      if (consumed <= 0) return 0;
      readingAnchor.userConsumedReserve += consumed;
      setAnchorReserve(readingAnchor.remainingReserve - consumed);
      return consumed;
    }

    function releaseReadingAnchorForDownwardIntent() {
      if (!readingAnchor || following) return false;
      clearReadingAnchor();
      programmaticScrollTarget = null;
      recordUserScrollPosition();
      const distance = distanceToBottom();
      if (distance <= bottomTolerance) {
        following = true;
        if (!hasUserScrollOwnership()) scheduleFollow();
      } else {
        following = false;
      }
      reconcile();
      return true;
    }

    function beginDownwardUserScroll() {
      renewUserScrollIntent(1);
      if (!readingAnchor && distanceToBottom() <= bottomTolerance) return false;
      releaseReadingAnchorForDownwardIntent();
      return true;
    }

    function updateButton() {
      if (!button) return;
      const presented = visible && !suppressed;
      const labelKey = running ? "scrollToLatestRunning" : "scrollToLatest";
      const label = getLabel(labelKey);
      button.classList.toggle("visible", presented);
      button.classList.toggle("is-running", running);
      button.setAttribute("aria-hidden", String(!presented));
      button.tabIndex = presented ? 0 : -1;
      button.dataset.i18nTitle = labelKey;
      button.dataset.i18nAriaLabel = labelKey;
      button.title = label;
      button.setAttribute("aria-label", label);
    }

    function cancelScheduledFrame() {
      if (frameId == null) return;
      cancelFrame(frameId);
      frameId = null;
    }

    function relinquishFollowingForUpwardIntent() {
      if (maxScrollTop() <= bottomTolerance) return false;
      renewUserScrollIntent(-1);
      if (!following && !readingAnchor) {
        recordUserScrollPosition();
        reconcile();
        return true;
      }
      if (following) following = false;
      recordUserScrollPosition();
      reconcile();
      return true;
    }

    function onWheelIntent(event) {
      const deltaX = Number(event?.deltaX || 0);
      const deltaY = Number(event?.deltaY || 0);
      if (event?.ctrlKey || Math.abs(deltaY) <= Math.abs(deltaX)) return;
      if (deltaY < 0) relinquishFollowingForUpwardIntent();
      else if (deltaY > 0) beginDownwardUserScroll();
    }

    function clearTouchIntent() {
      touchStartY = null;
    }

    function onTouchStart(event) {
      const touches = event?.touches;
      if (Number(touches?.length || 0) !== 1) {
        clearTouchIntent();
        return;
      }
      const clientY = Number(touches[0]?.clientY);
      touchStartY = Number.isFinite(clientY) ? clientY : null;
      if (touchStartY != null) renewUserScrollIntent(0);
    }

    function onTouchMove(event) {
      if (touchStartY == null) return;
      const touches = event?.touches;
      if (Number(touches?.length || 0) !== 1) {
        clearTouchIntent();
        return;
      }
      const selection = global.getSelection?.();
      if (selection?.isCollapsed === false) {
        clearTouchIntent();
        return;
      }
      const clientY = Number(touches[0]?.clientY);
      if (!Number.isFinite(clientY)) return;
      const delta = clientY - touchStartY;
      if (delta > bottomTolerance) relinquishFollowingForUpwardIntent();
      else if (delta < -bottomTolerance) beginDownwardUserScroll();
      else return;
      touchStartY = clientY;
    }

    function isEditableScrollTarget(target) {
      const tagName = String(target?.tagName || "").toLowerCase();
      return tagName === "input" || tagName === "textarea" || target?.isContentEditable === true;
    }

    function onKeyDownIntent(event) {
      if (event?.altKey || event?.ctrlKey || event?.metaKey || isEditableScrollTarget(event?.target)) return;
      const key = String(event?.key || "");
      if (["ArrowUp", "PageUp", "Home"].includes(key)) {
        relinquishFollowingForUpwardIntent();
      } else if (["ArrowDown", "PageDown", "End"].includes(key)) {
        beginDownwardUserScroll();
      }
    }

    function onPointerDownIntent(event) {
      if (Number(event?.button ?? 0) !== 0 || event?.target !== container) return;
      const rect = container?.getBoundingClientRect?.();
      const clientX = Number(event?.clientX);
      if (!rect || !Number.isFinite(clientX) || maxScrollTop() <= bottomTolerance) return;
      const nativeGutter = Math.max(
        0,
        Number(container?.offsetWidth || rect.width || 0) - Number(container?.clientWidth || 0),
      );
      const intentWidth = Math.max(12, nativeGutter);
      scrollbarIntent = clientX >= Number(rect.right || 0) - intentWidth;
      if (scrollbarIntent) renewUserScrollIntent(0);
    }

    function clearPointerIntent() {
      scrollbarIntent = false;
    }

    function reconcile() {
      const realContentDistance = realContentDistanceToBottom();
      if (following || realContentDistance <= bottomTolerance) {
        visible = false;
      } else if (!visible && realContentDistance >= revealThreshold) {
        visible = true;
      }
      updateButton();
    }

    function scheduleFollow() {
      if (!container || !following || hasUserScrollOwnership() || frameId != null) return;
      frameId = requestFrame(() => {
        frameId = null;
        if (!following || hasUserScrollOwnership()) return;
        if (readingAnchor) reconcileReadingAnchor(false);
        const target = readingAnchor?.remainingReserve > 0
          ? Number(readingAnchor.targetScrollTop || 0)
          : maxScrollTop();
        writeScrollTop(target);
        reconcile();
      });
    }

    function resetForSession(nextSessionId) {
      cancelScheduledFrame();
      clearReadingAnchor();
      sessionId = String(nextSessionId || "");
      following = true;
      visible = false;
      suppressed = false;
      running = false;
      clearUserScrollIntent();
      preservedScrollTop = Number(container?.scrollTop || 0);
      lastObservedScrollTop = preservedScrollTop;
      programmaticScrollTarget = null;
      clearTouchIntent();
      clearPointerIntent();
      updateButton();
    }

    function ensureSession(nextSessionId) {
      const next = String(nextSessionId || "");
      if (next === sessionId) return false;
      resetForSession(next);
      return true;
    }

    function onUserScroll() {
      const currentScrollTop = Number(container?.scrollTop || 0);
      const hadProgrammaticScrollTarget = programmaticScrollTarget != null;
      if (
        hadProgrammaticScrollTarget
        && Math.abs(currentScrollTop - programmaticScrollTarget) <= bottomTolerance
      ) {
        programmaticScrollTarget = null;
        lastObservedScrollTop = currentScrollTop;
        preservedScrollTop = currentScrollTop;
        reconcile();
        return;
      }
      if (
        hadProgrammaticScrollTarget
        && readingAnchor
        && currentScrollTop < programmaticScrollTarget - bottomTolerance
      ) {
        lastObservedScrollTop = Number(programmaticScrollTarget);
      }
      programmaticScrollTarget = null;
      const delta = currentScrollTop - lastObservedScrollTop;
      const scrollbarUpwardIntent = scrollbarIntent && delta < -bottomTolerance;
      const scrollbarDownwardIntent = scrollbarIntent && delta > bottomTolerance;
      if (hasUserScrollOwnership() && Math.abs(delta) > bottomTolerance) {
        renewUserScrollIntent(delta < 0 ? -1 : 1);
      }
      const userOwnsScroll = hasUserScrollOwnership();
      if (scrollbarUpwardIntent) {
        following = false;
        cancelScheduledFrame();
      }
      if (
        readingAnchor
        && !hadProgrammaticScrollTarget
        && userOwnsScroll
        && delta < -bottomTolerance
      ) {
        following = false;
        cancelScheduledFrame();
        consumeAnchorReserveForUpwardScroll(-delta);
      } else if (
        readingAnchor
        && !following
        && scrollbarDownwardIntent
      ) {
        releaseReadingAnchorForDownwardIntent();
        return;
      }
      if (userOwnsScroll) {
        const distance = distanceToBottom();
        recordUserScrollPosition();
        if (distance <= bottomTolerance) {
          following = true;
        } else if (userScrollIntentDirection < 0 || !following) {
          following = false;
          cancelScheduledFrame();
        }
        reconcile();
        return;
      }
      if (
        !following
        && !hadProgrammaticScrollTarget
      ) {
        // Preserve an intentional reading position when browser anchoring or
        // a late layout change emits a scroll event without user input.
        writeScrollTop(Math.min(preservedScrollTop, maxScrollTop()));
        reconcile();
        return;
      }
      const distance = distanceToBottom();
      preservedScrollTop = Number(container?.scrollTop || 0);
      lastObservedScrollTop = preservedScrollTop;
      if (distance <= bottomTolerance) {
        if (following) scheduleFollow();
      } else {
        // DOM patches and late layout (images, tables, ResizeObserver) can
        // move scrollTop without user input. Keep following and settle back to
        // the newest content on the next coalesced frame.
        following = true;
        scheduleFollow();
      }
      reconcile();
    }

    function onContentChanged(ownerSessionId = sessionId) {
      ensureSession(ownerSessionId);
      if (hasUserScrollOwnership()) {
        recordUserScrollPosition();
        reconcile();
        return;
      }
      if (readingAnchor) {
        reconcileReadingAnchor(false);
        captureAnchorLayoutAdjustment();
      }
      if (following) scheduleFollow();
      else if (readingAnchor) reconcile();
      else {
        writeScrollTop(Math.min(preservedScrollTop, maxScrollTop()));
        reconcile();
      }
    }

    function onViewportChanged(ownerSessionId = sessionId) {
      if (String(ownerSessionId || "") !== sessionId) return;
      if (hasUserScrollOwnership()) {
        recordUserScrollPosition();
        reconcile();
        return;
      }
      if (readingAnchor) {
        reconcileReadingAnchor(false);
        captureAnchorLayoutAdjustment();
      }
      if (following) scheduleFollow();
      else if (readingAnchor) reconcile();
      else {
        writeScrollTop(Math.min(preservedScrollTop, maxScrollTop()));
        reconcile();
      }
    }

    function forceToLatest(nextSessionId = sessionId) {
      ensureSession(nextSessionId);
      clearReadingAnchor();
      clearUserScrollIntent();
      following = true;
      visible = false;
      updateButton();
      if (container) {
        writeScrollTop(maxScrollTop());
      }
      scheduleFollow();
    }

    function jumpToLatest() {
      forceToLatest(sessionId);
      if (focusTarget?.focus) focusTarget.focus({ preventScroll: true });
    }

    function setSuppressed(nextSuppressed) {
      suppressed = Boolean(nextSuppressed);
      if (!suppressed) reconcile();
      else updateButton();
    }

    function setRunning(nextRunning, ownerSessionId = sessionId) {
      if (String(ownerSessionId || "") !== sessionId) return false;
      running = Boolean(nextRunning);
      updateButton();
      return true;
    }

    function setSession(nextSessionId) {
      ensureSession(nextSessionId);
    }

    function connect() {
      if (connected || !container?.addEventListener) return false;
      connected = true;
      container.addEventListener("scroll", onUserScroll, passiveListenerOptions);
      container.addEventListener("wheel", onWheelIntent, passiveListenerOptions);
      container.addEventListener("touchstart", onTouchStart, passiveListenerOptions);
      container.addEventListener("touchmove", onTouchMove, passiveListenerOptions);
      container.addEventListener("touchend", clearTouchIntent, passiveListenerOptions);
      container.addEventListener("touchcancel", clearTouchIntent, passiveListenerOptions);
      container.addEventListener("keydown", onKeyDownIntent);
      container.addEventListener("pointerdown", onPointerDownIntent, passiveListenerOptions);
      container.addEventListener("pointerup", clearPointerIntent, passiveListenerOptions);
      container.addEventListener("pointercancel", clearPointerIntent, passiveListenerOptions);
      button?.addEventListener?.("click", jumpToLatest);
      if (typeof ResizeObserverClass === "function") {
        resizeObserver = new ResizeObserverClass(() => onViewportChanged(sessionId));
        resizeObserver.observe(container);
        if (content && content !== container) resizeObserver.observe(content);
      }
      updateButton();
      return true;
    }

    function disconnect() {
      clearUserScrollIntent();
      clearReadingAnchor();
      if (!connected) return;
      connected = false;
      cancelScheduledFrame();
      programmaticScrollTarget = null;
      clearTouchIntent();
      clearPointerIntent();
      container?.removeEventListener?.("scroll", onUserScroll, passiveListenerOptions);
      container?.removeEventListener?.("wheel", onWheelIntent, passiveListenerOptions);
      container?.removeEventListener?.("touchstart", onTouchStart, passiveListenerOptions);
      container?.removeEventListener?.("touchmove", onTouchMove, passiveListenerOptions);
      container?.removeEventListener?.("touchend", clearTouchIntent, passiveListenerOptions);
      container?.removeEventListener?.("touchcancel", clearTouchIntent, passiveListenerOptions);
      container?.removeEventListener?.("keydown", onKeyDownIntent);
      container?.removeEventListener?.("pointerdown", onPointerDownIntent, passiveListenerOptions);
      container?.removeEventListener?.("pointerup", clearPointerIntent, passiveListenerOptions);
      container?.removeEventListener?.("pointercancel", clearPointerIntent, passiveListenerOptions);
      button?.removeEventListener?.("click", jumpToLatest);
      resizeObserver?.disconnect?.();
      resizeObserver = null;
    }

    function snapshot() {
      return Object.freeze({
        sessionId,
        following,
        visible,
        suppressed,
        running,
        userScrollIntentActive: hasUserScrollOwnership(),
        userScrollIntentDirection,
        userScrollIntentEpoch,
        readingAnchor: readingAnchor ? Object.freeze({ ...readingAnchor }) : null,
        framePending: frameId != null,
        distance: distanceToBottom(),
        realContentDistance: realContentDistanceToBottom(),
      });
    }

    return Object.freeze({
      connect,
      beginReadingAnchor,
      disconnect,
      forceToLatest,
      jumpToLatest,
      onContentChanged,
      onUserScroll,
      onViewportChanged,
      setRunning,
      setSession,
      setSuppressed,
      snapshot,
    });
  }

  function createLongTextDisplayController(options = {}) {
    const root = options.root || null;
    const textarea = options.textarea || null;
    const composerToggle = options.composerToggle || null;
    const getLabel = options.getLabel || ((key) => key);
    const onLayoutChange = options.onLayoutChange || (() => {});
    const getStyle = options.getComputedStyle
      || global.getComputedStyle?.bind(global)
      || (() => ({}));
    const getViewportHeight = options.getViewportHeight
      || (() => Number(global.innerHeight || 0));
    const overflowTolerance = Number(options.overflowTolerance ?? 1);
    const compactLines = Number(options.compactLines ?? 5);
    const expandedComposerMax = Number(options.expandedComposerMax ?? 420);
    const expandedComposerViewportRatio = Number(options.expandedComposerViewportRatio ?? 0.45);
    let sessionId = String(options.sessionId || "");
    let composerExpanded = false;
    let connected = false;
    let pendingComposerSelection = null;
    const expandedUserMessages = new Set();

    function numberStyle(style, property) {
      const value = Number.parseFloat(style?.[property] || 0);
      return Number.isFinite(value) ? value : 0;
    }

    function compactComposerHeight() {
      if (!textarea) return 0;
      const style = getStyle(textarea) || {};
      const lineHeight = numberStyle(style, "lineHeight") || 24;
      const padding = numberStyle(style, "paddingTop") + numberStyle(style, "paddingBottom");
      const cssThreshold = Number.parseFloat(
        style.getPropertyValue?.("--composer-compact-max-height") || "",
      );
      return Number.isFinite(cssThreshold) && cssThreshold > 0
        ? cssThreshold
        : lineHeight * compactLines + padding;
    }

    function composerHasCompactOverflow() {
      if (!textarea) return false;
      return Number(textarea.scrollHeight || 0) > compactComposerHeight() + overflowTolerance;
    }

    function setTextareaHeight(value) {
      if (!textarea?.style) return;
      if (!value && typeof textarea.style.removeProperty === "function") {
        textarea.style.removeProperty("height");
        return;
      }
      textarea.style.height = value || "";
    }

    function updateComposerToggle(overflowing) {
      if (!composerToggle) return;
      const labelKey = composerExpanded ? "collapseComposerInput" : "expandComposerInput";
      const label = getLabel(labelKey);
      composerToggle.hidden = !overflowing;
      composerToggle.dataset.i18n = labelKey;
      composerToggle.dataset.i18nTitle = labelKey;
      composerToggle.dataset.i18nAriaLabel = labelKey;
      composerToggle.textContent = label;
      composerToggle.title = label;
      composerToggle.setAttribute("aria-expanded", String(composerExpanded));
      composerToggle.setAttribute("aria-label", label);
    }

    function refreshComposer(refreshOptions = {}) {
      if (!textarea) return false;
      if (refreshOptions.resetExpanded) composerExpanded = false;
      const overflowing = composerHasCompactOverflow();
      if (!overflowing) composerExpanded = false;
      textarea.classList.toggle("is-expanded", composerExpanded);
      if (composerExpanded) {
        setTextareaHeight("auto");
        const viewportLimit = Math.max(0, getViewportHeight() * expandedComposerViewportRatio);
        const maxHeight = viewportLimit > 0
          ? Math.min(expandedComposerMax, viewportLimit)
          : expandedComposerMax;
        setTextareaHeight(`${Math.min(Number(textarea.scrollHeight || 0), maxHeight)}px`);
      } else {
        setTextareaHeight("");
      }
      updateComposerToggle(overflowing);
      return overflowing;
    }

    function captureComposerSelection() {
      if (!textarea) return null;
      return {
        start: Number(textarea.selectionStart || 0),
        end: Number(textarea.selectionEnd || 0),
        direction: textarea.selectionDirection || "none",
        scrollTop: Number(textarea.scrollTop || 0),
      };
    }

    function restoreComposerSelection(selection) {
      if (!textarea || !selection) return;
      textarea.focus?.({ preventScroll: true });
      textarea.setSelectionRange?.(selection.start, selection.end, selection.direction);
      textarea.scrollTop = selection.scrollTop;
    }

    function onComposerMouseDown(event) {
      pendingComposerSelection = captureComposerSelection();
      event?.preventDefault?.();
    }

    function toggleComposer() {
      if (!textarea || composerToggle?.hidden) return false;
      const selection = pendingComposerSelection || captureComposerSelection();
      pendingComposerSelection = null;
      composerExpanded = !composerExpanded;
      refreshComposer();
      restoreComposerSelection(selection);
      onLayoutChange();
      return true;
    }

    function messageParts(wrapper) {
      const key = String(wrapper?.dataset?.userMessageText || "");
      const button = wrapper?.parentElement?.querySelector?.(`[data-user-message-toggle="${key}"]`)
        || null;
      return { key, button };
    }

    function updateUserMessage(wrapper) {
      if (!wrapper) return false;
      const { key, button } = messageParts(wrapper);
      if (!key || !button) return false;
      const previousOverflow = wrapper.classList.contains("is-overflowing");
      const previousExpanded = wrapper.classList.contains("is-expanded");
      wrapper.classList.add("is-collapsed");
      wrapper.classList.remove("is-expanded");
      const overflowing = Number(wrapper.scrollHeight || 0)
        > Number(wrapper.clientHeight || 0) + overflowTolerance;
      if (!overflowing) expandedUserMessages.delete(key);
      const expanded = overflowing && expandedUserMessages.has(key);
      wrapper.classList.toggle("is-overflowing", overflowing);
      wrapper.classList.toggle("is-collapsed", !expanded);
      wrapper.classList.toggle("is-expanded", expanded);
      const labelKey = expanded ? "collapseUserMessage" : "expandUserMessage";
      const label = getLabel(labelKey);
      button.hidden = !overflowing;
      button.dataset.i18n = labelKey;
      button.dataset.i18nTitle = labelKey;
      button.dataset.i18nAriaLabel = labelKey;
      button.textContent = label;
      button.title = label;
      button.setAttribute("aria-expanded", String(expanded));
      button.setAttribute("aria-label", label);
      return previousOverflow !== overflowing || previousExpanded !== expanded;
    }

    function syncUserMessages(nextSessionId = sessionId) {
      setSession(nextSessionId);
      if (!root?.querySelectorAll) return false;
      let changed = false;
      root.querySelectorAll("[data-user-message-text]").forEach((wrapper) => {
        changed = updateUserMessage(wrapper) || changed;
      });
      return changed;
    }

    function findUserMessage(key) {
      if (!root?.querySelectorAll) return null;
      return Array.from(root.querySelectorAll("[data-user-message-text]"))
        .find((wrapper) => String(wrapper.dataset?.userMessageText || "") === key) || null;
    }

    function toggleUserMessage(key) {
      const normalized = String(key || "");
      const wrapper = findUserMessage(normalized);
      if (!wrapper?.classList.contains("is-overflowing")) return false;
      if (expandedUserMessages.has(normalized)) expandedUserMessages.delete(normalized);
      else expandedUserMessages.add(normalized);
      updateUserMessage(wrapper);
      onLayoutChange();
      return true;
    }

    function onRootClick(event) {
      const button = event.target?.closest?.("[data-user-message-toggle]");
      if (!button || (root?.contains && !root.contains(button))) return;
      toggleUserMessage(button.dataset.userMessageToggle || "");
    }

    function setSession(nextSessionId) {
      const next = String(nextSessionId || "");
      if (next === sessionId) return false;
      sessionId = next;
      expandedUserMessages.clear();
      composerExpanded = false;
      refreshComposer({ resetExpanded: true });
      return true;
    }

    function resetComposer() {
      composerExpanded = false;
      pendingComposerSelection = null;
      refreshComposer({ resetExpanded: true });
    }

    function onResize() {
      refreshComposer();
      syncUserMessages(sessionId);
      onLayoutChange();
    }

    function connect() {
      if (connected) return false;
      connected = true;
      root?.addEventListener?.("click", onRootClick);
      textarea?.addEventListener?.("input", refreshComposer);
      composerToggle?.addEventListener?.("mousedown", onComposerMouseDown);
      composerToggle?.addEventListener?.("click", toggleComposer);
      global.addEventListener?.("resize", onResize);
      refreshComposer();
      syncUserMessages(sessionId);
      return true;
    }

    function disconnect() {
      if (!connected) return;
      connected = false;
      root?.removeEventListener?.("click", onRootClick);
      textarea?.removeEventListener?.("input", refreshComposer);
      composerToggle?.removeEventListener?.("mousedown", onComposerMouseDown);
      composerToggle?.removeEventListener?.("click", toggleComposer);
      global.removeEventListener?.("resize", onResize);
      pendingComposerSelection = null;
      expandedUserMessages.clear();
    }

    function snapshot() {
      return Object.freeze({
        sessionId,
        composerExpanded,
        expandedUserMessages: Object.freeze([...expandedUserMessages]),
      });
    }

    return Object.freeze({
      connect,
      disconnect,
      refreshComposer,
      resetComposer,
      setSession,
      snapshot,
      syncUserMessages,
      toggleComposer,
      toggleUserMessage,
    });
  }

  function tokenCount(value) {
    const count = Number(value);
    return Number.isFinite(count) ? Math.max(0, count) : 0;
  }

  function firstReportedToken(usage, keys) {
    for (const key of keys) {
      if (usage?.[key] != null) return tokenCount(usage[key]);
    }
    return 0;
  }

  function hasReportedToken(usage, keys) {
    return keys.some((key) => usage?.[key] != null);
  }

  function normalizeResponseUsage(usage) {
    if (!usage) return null;
    const cacheKeys = [
      "cache",
      "prompt_cache_hit_tokens",
      "cache_read_tokens",
      "cache_read_input_tokens",
      "cached_input_tokens",
    ];
    const cacheRead = firstReportedToken(usage, cacheKeys) || tokenCount(
      usage.prompt_tokens_details?.cached_tokens
      ?? usage.input_tokens_details?.cached_tokens,
    );
    const hasCacheReported = hasReportedToken(usage, cacheKeys)
      || usage.prompt_tokens_details?.cached_tokens != null
      || usage.input_tokens_details?.cached_tokens != null;
    const cacheWriteKeys = [
      "cacheWrite",
      "cache_creation_input_tokens",
      "cache_write_input_tokens",
      "cache_write_tokens",
    ];
    const cacheWriteReported = hasReportedToken(usage, cacheWriteKeys);
    const cacheWrite = firstReportedToken(usage, cacheWriteKeys);
    let input;
    if (usage.input != null) {
      input = tokenCount(usage.input);
    } else if (usage.prompt_tokens != null) {
      // OpenAI-compatible prompt_tokens already includes cached input.
      input = tokenCount(usage.prompt_tokens);
    } else {
      const rawInput = tokenCount(usage.input_tokens);
      const anthropicBreakdown = hasReportedToken(usage, [
        "cache_read_input_tokens",
        "cache_creation_input_tokens",
      ]);
      input = anthropicBreakdown
        ? rawInput + cacheRead + cacheWrite
        : rawInput;
    }
    const normalized = {
      input,
      output: firstReportedToken(usage, ["output", "completion_tokens", "output_tokens"]),
      cache: cacheRead,
      hasCacheReported,
    };
    if (cacheWriteReported) normalized.cacheWrite = cacheWrite;
    return normalized;
  }

  function hasUsageStats(usage) {
    const normalized = normalizeResponseUsage(usage);
    return !!(
      normalized
      && (
        normalized.input
        || normalized.output
        || normalized.cache
        || normalized.cacheWrite
      )
    );
  }

  function isInternalMessage(msg) {
    if (!msg) return true;
    if (msg.meta?._system) return true;
    if (msg.meta?.kind === "key-fallback") return true;
    if (msg.meta?.kind === "tool-round-limit") return true;
    return false;
  }

  function isToolPlanningPlaceholder(text) {
    const value = String(text || "").trim();
    if (!value) return true;
    if (/^准备调用\s*\d*\s*个?工具/.test(value)) return true;
    if (/^准备调用工具/.test(value)) return true;
    if (/^Preparing\s+to\s+call\s+\d*\s*tools?/i.test(value)) return true;
    if (/^Calling\s+\d*\s*tools?/i.test(value)) return true;
    return false;
  }

  function isOperationalToolNotice(text) {
    const lines = String(text || "")
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean);
    if (!lines.length) return false;
    return lines.every((line) => (
      line.length <= 220
      && (
        /^正在.+(?:…|\.{3})$/.test(line)
        || /^(?:Listing|Reading|Searching|Running|Executing|Checking|Inspecting|Viewing|Editing|Writing|Creating|Deleting|Opening|Calling|Waiting)\b.+(?:…|\.{3})$/i.test(line)
        || /^→\s*request_user_input$/.test(line)
      )
    ));
  }

  function syncProjectedElement(current, projected, options = {}) {
    if (!current || !projected) return false;
    const preserveChildren = options.preserveChildren === true;
    const preservePointerFocus = current.classList?.contains?.("is-pointer-focus") === true;
    const currentNames = typeof current.getAttributeNames === "function"
      ? current.getAttributeNames()
      : Array.from(current.attributes || [], (attribute) => attribute.name);
    const projectedNames = typeof projected.getAttributeNames === "function"
      ? projected.getAttributeNames()
      : Array.from(projected.attributes || [], (attribute) => attribute.name);
    const projectedSet = new Set(projectedNames);
    currentNames.forEach((name) => {
      if (!projectedSet.has(name)) current.removeAttribute?.(name);
    });
    projectedNames.forEach((name) => {
      const value = projected.getAttribute?.(name);
      if (current.getAttribute?.(name) !== value) current.setAttribute?.(name, value);
    });
    if (!preserveChildren && typeof current.replaceChildren === "function") {
      current.replaceChildren(...Array.from(projected.childNodes || []));
    }
    if (preservePointerFocus) current.classList?.add?.("is-pointer-focus");
    return true;
  }

  function reconcileToolProcessItem(currentItem, projectedItem) {
    if (!currentItem || !projectedItem) return false;
    const currentSummary = currentItem.querySelector?.(":scope > summary") || null;
    const projectedSummary = projectedItem.querySelector?.(":scope > summary") || null;
    const currentBody = currentItem.querySelector?.(":scope > .tool-process-body") || null;
    const projectedBody = projectedItem.querySelector?.(":scope > .tool-process-body") || null;
    syncProjectedElement(currentItem, projectedItem, { preserveChildren: true });
    syncProjectedElement(currentSummary, projectedSummary);
    syncProjectedElement(currentBody, projectedBody);
    return true;
  }

  function reconcileToolProcessNodes(currentRoot, projectedRoot) {
    if (!currentRoot?.querySelectorAll || !projectedRoot?.querySelectorAll) {
      return { traces: 0, groups: 0, items: 0 };
    }
    const currentStages = new Map();
    Array.from(currentRoot.querySelectorAll(
      "details.tool-process-stage[data-tool-process-id]",
    )).forEach((stage) => {
      const processId = String(stage.dataset?.toolProcessId || "");
      if (processId && !currentStages.has(processId)) currentStages.set(processId, stage);
    });

    let groups = 0;
    let items = 0;
    Array.from(projectedRoot.querySelectorAll("article.tool-process")).forEach((projectedArticle) => {
      const projectedStage = projectedArticle.querySelector?.(
        "details.tool-process-stage[data-tool-process-id]",
      );
      const processId = String(projectedStage?.dataset?.toolProcessId || "");
      const currentStage = processId ? currentStages.get(processId) : null;
      const currentArticle = currentStage?.closest?.("article.tool-process") || null;
      if (!currentArticle || !projectedStage) return;

      const currentItems = new Map();
      Array.from(currentStage.querySelectorAll(
        "details.tool-process-item[data-tool-process-item-key]",
      )).forEach((item) => {
        const itemKey = String(item.dataset?.toolProcessItemKey || "");
        if (itemKey && !currentItems.has(itemKey)) currentItems.set(itemKey, item);
      });
      Array.from(projectedStage.querySelectorAll(
        "details.tool-process-item[data-tool-process-item-key]",
      )).forEach((projectedItem) => {
        const itemKey = String(projectedItem.dataset?.toolProcessItemKey || "");
        const currentItem = itemKey ? currentItems.get(itemKey) : null;
        if (!currentItem) return;
        reconcileToolProcessItem(currentItem, projectedItem);
        projectedItem.replaceWith?.(currentItem);
        items += 1;
      });

      const currentSummary = currentStage.querySelector?.(
        ":scope > summary.tool-process-stage-summary",
      ) || null;
      const projectedSummary = projectedStage.querySelector?.(
        ":scope > summary.tool-process-stage-summary",
      ) || null;
      const currentBody = currentStage.querySelector?.(
        ":scope > .tool-process-stage-body",
      ) || null;
      const projectedBody = projectedStage.querySelector?.(
        ":scope > .tool-process-stage-body",
      ) || null;
      syncProjectedElement(currentArticle, projectedArticle, { preserveChildren: true });
      syncProjectedElement(currentStage, projectedStage, { preserveChildren: true });
      syncProjectedElement(currentSummary, projectedSummary);
      syncProjectedElement(currentBody, projectedBody);
      projectedArticle.replaceWith?.(currentArticle);
      groups += 1;
    });

    const currentTraces = new Map();
    Array.from(currentRoot.querySelectorAll(
      "section.execution-trace[data-execution-trace]",
    )).forEach((trace) => {
      const traceId = String(trace.dataset?.executionTrace || "");
      if (traceId && !currentTraces.has(traceId)) currentTraces.set(traceId, trace);
    });
    let traces = 0;
    Array.from(projectedRoot.querySelectorAll(
      "section.execution-trace[data-execution-trace]",
    )).forEach((projectedTrace) => {
      const traceId = String(projectedTrace.dataset?.executionTrace || "");
      const currentTrace = traceId ? currentTraces.get(traceId) : null;
      if (!currentTrace) return;
      const currentSummary = currentTrace.querySelector?.(
        ":scope > .execution-trace-summary",
      ) || null;
      const projectedSummary = projectedTrace.querySelector?.(
        ":scope > .execution-trace-summary",
      ) || null;
      const currentBody = currentTrace.querySelector?.(
        ":scope > .execution-trace-body",
      ) || null;
      const projectedBody = projectedTrace.querySelector?.(
        ":scope > .execution-trace-body",
      ) || null;
      syncProjectedElement(currentTrace, projectedTrace, { preserveChildren: true });
      syncProjectedElement(currentSummary, projectedSummary);
      syncProjectedElement(currentBody, projectedBody);
      projectedTrace.replaceWith?.(currentTrace);
      traces += 1;
    });
    return { traces, groups, items };
  }

  function createMessagesFeature(options = {}) {
    const escapeHtml = options.escapeHtml || ((value) => String(value ?? ""));
    const formatCompact = options.formatCompact || ((value) => String(value ?? 0));
    const formatSize = options.formatSize || ((value) => String(value ?? 0));
    const renderMarkdown = options.renderMarkdown || ((value) => escapeHtml(value));
    const renderAssistantMarkdown = options.renderAssistantMarkdown || renderMarkdown;
    const t = options.t || ((key) => key);
    const getMessageText = options.getMessageText || ((msg) => String(msg?.content || ""));
    const getBackgroundJob = options.getBackgroundJob || (() => null);
    const getMessages = options.getMessages || (() => []);
    const getSessionId = options.getSessionId || (() => "");
    const getSelectedModel = options.getSelectedModel || (() => "");
    const renderNetworkRecoveryStatus = options.renderNetworkRecoveryStatus || (() => "");
    const renderAssistantContent = options.renderAssistantContent || ((content) => renderMarkdown(content));
    const renderBranchFlow = options.renderBranchFlow || (() => "");
    const isEditSuggestionMessage = options.isEditSuggestionMessage || (() => false);
    const renderEditSuggestion = options.renderEditSuggestion || (() => "");
    const getToolActionLabel = options.getToolActionLabel || ((action) => String(action || "tool"));
    const hasImagePreviewSource = typeof options.getImagePreviewSource === "function";
    const getImagePreviewSource = options.getImagePreviewSource || ((image = {}) => (
      image.path
        ? `/api/file?path=${encodeURIComponent(image.path)}&raw=1`
        : `data:${image.mime || "image/png"};base64,${image.base64}`
    ));
    const onImagePreview = options.onImagePreview || (() => {});
    const onImageLoad = options.onImageLoad || (() => {});
    const onLayoutChange = options.onLayoutChange || (() => {});
    const onManualCompactionRetry = options.onManualCompactionRetry || (() => false);
    const boundInteractionRoots = new WeakSet();

    function visibleAssistantToolCalls(msg) {
      return (Array.isArray(msg?.meta?.toolCalls) ? msg.meta.toolCalls : []).filter((call) => (
        !isInternalGoalTool(call)
      ));
    }

    function isInternalGoalOnlyAssistant(msg) {
      const calls = Array.isArray(msg?.meta?.toolCalls) ? msg.meta.toolCalls : [];
      return calls.length > 0 && calls.every(isInternalGoalTool);
    }

    function isPublicProcessCommentary(msg) {
      return msg?.meta?.publicProcessCommentary === true;
    }

    function isVisibleToolProjectionMessage(msg) {
      if (msg?.role === "assistant") return visibleAssistantToolCalls(msg).length > 0;
      if (!["tool-call", "tool-result"].includes(String(msg?.role || ""))) return false;
      return !isInternalGoalTool(msg);
    }

    function renderCopyIconSvg() {
      return `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>`;
    }

    function resetIconCopyButton(btn, label = "Copy") {
      if (!btn) return;
      btn.classList.remove("copied", "failed");
      btn.innerHTML = renderCopyIconSvg();
      btn.title = label;
      btn.setAttribute("aria-label", label);
    }

    function showIconCopyFeedback(btn, ok) {
      if (!btn) return;
      const label = ok ? t("copiedLabel") : t("failedBtn");
      btn.classList.toggle("copied", ok);
      btn.classList.toggle("failed", !ok);
      btn.innerHTML = ok
        ? `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6L9 17l-5-5"/></svg>`
        : `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 6L6 18M6 6l12 12"/></svg>`;
      btn.title = label;
      btn.setAttribute("aria-label", label);
      setTimeout(() => resetIconCopyButton(btn), 1200);
    }

    async function copyMessageText(btn) {
      if (!btn) return;
      const original = btn.innerHTML;
      try {
        const text = btn.dataset.copyText || "";
        await global.navigator.clipboard.writeText(text);
        btn.innerHTML = COPY_DONE;
        btn.classList.add("copied");
        btn.title = t("copied");
        btn.setAttribute("aria-label", t("copied"));
      } catch (_) {
        btn.classList.add("failed");
        btn.title = t("copyFailed");
        btn.setAttribute("aria-label", t("copyFailed"));
      }
      setTimeout(() => {
        btn.innerHTML = original;
        btn.classList.remove("copied", "failed");
        btn.title = t("copy");
        btn.setAttribute("aria-label", t("copy"));
      }, 1500);
    }

    function bindInteractions(root) {
      if (!root || typeof root.addEventListener !== "function" || boundInteractionRoots.has(root)) return false;
      boundInteractionRoots.add(root);
      const foldControlSelector = [
        "[data-execution-trace-toggle]",
        ".tool-process-stage > summary",
        ".tool-process-item > summary",
      ].join(", ");

      root.addEventListener("mousedown", (event) => {
        if (event.button !== 0) return;
        const foldControl = event.target?.closest?.(foldControlSelector);
        if (!foldControl || (root.contains && !root.contains(foldControl))) return;
        const nestedInteractive = event.target?.closest?.(
          "a, button, input, textarea, select, [contenteditable='true']",
        );
        if (nestedInteractive && nestedInteractive !== foldControl
            && (!foldControl.contains || foldControl.contains(nestedInteractive))) return;
        event.preventDefault();
        foldControl.classList?.add("is-pointer-focus");
        try {
          foldControl.focus?.({ preventScroll: true });
        } catch (_) {
          foldControl.focus?.();
        }
      });

      root.addEventListener("focusout", (event) => {
        const foldControl = event.target?.closest?.(foldControlSelector);
        if (!foldControl || (root.contains && !root.contains(foldControl))) return;
        const ownerDocument = foldControl.ownerDocument || root.ownerDocument || global.document;
        const relatedTarget = event.relatedTarget || null;
        const defer = typeof global.queueMicrotask === "function"
          ? global.queueMicrotask.bind(global)
          : (callback) => Promise.resolve().then(callback);
        defer(() => {
          if (!foldControl.classList?.contains?.("is-pointer-focus")) return;
          const documentFocused = typeof ownerDocument?.hasFocus === "function"
            ? ownerDocument.hasFocus()
            : true;
          if (!documentFocused) return;
          const activeElement = ownerDocument?.activeElement || null;
          const relatedWithinDocument = Boolean(
            relatedTarget && relatedTarget.ownerDocument === ownerDocument,
          );
          const activeMovedWithinDocument = Boolean(
            activeElement
            && activeElement !== foldControl
            && activeElement !== ownerDocument?.body
            && activeElement !== ownerDocument?.documentElement,
          );
          if (relatedWithinDocument || activeMovedWithinDocument) {
            foldControl.classList.remove("is-pointer-focus");
          }
        });
      });

      root.addEventListener("click", (event) => {
        const traceToggle = event.target?.closest?.("[data-execution-trace-toggle]");
        if (traceToggle && (!root.contains || root.contains(traceToggle))) {
          const trace = traceToggle.closest("[data-execution-trace]");
          const expanded = Boolean(trace?.classList.toggle("is-expanded"));
          traceToggle.setAttribute("aria-expanded", String(expanded));
          onLayoutChange();
          return;
        }
        const copyButton = event.target?.closest?.(".msg-copy-btn");
        if (copyButton && (!root.contains || root.contains(copyButton))) {
          void copyMessageText(copyButton);
          return;
        }
        const compactionRetry = event.target?.closest?.("[data-manual-compaction-retry]");
        if (compactionRetry && (!root.contains || root.contains(compactionRetry))) {
          compactionRetry.disabled = true;
          Promise.resolve(onManualCompactionRetry(
            compactionRetry.dataset.manualCompactionRetry || "",
          )).finally(() => { compactionRetry.disabled = false; });
          return;
        }
        const image = event.target?.closest?.("[data-message-image-preview]");
        if (image && (!root.contains || root.contains(image))) {
          onImagePreview(image.currentSrc || image.src || "");
          return;
        }
        const generatedPreview = event.target?.closest?.("[data-generated-image-preview]");
        if (generatedPreview && (!root.contains || root.contains(generatedPreview))) {
          const source = String(generatedPreview.dataset.generatedImagePreview || "");
          const gallery = generatedPreview.closest?.("[data-generated-image-gallery]");
          const previews = gallery
            ? [...gallery.querySelectorAll("[data-generated-image-preview]")]
            : [generatedPreview];
          const sources = previews
            .map((node) => String(node.dataset.generatedImagePreview || ""))
            .filter(Boolean);
          onImagePreview(source, {
            sources,
            index: Math.max(0, previews.indexOf(generatedPreview)),
          });
        }
      });

      root.addEventListener("load", (event) => {
        const image = event.target?.closest?.("[data-message-scroll-on-load]");
        if (image && (!root.contains || root.contains(image))) onImageLoad(image);
      }, true);
      root.addEventListener("toggle", (event) => {
        if (event.target?.matches?.("details") && (!root.contains || root.contains(event.target))) {
          onLayoutChange();
        }
      }, true);
      root.addEventListener("error", (event) => {
        const image = event.target?.closest?.("[data-message-image-preview]")
          || event.target?.closest?.("[data-generated-image-preview-img]");
        if (!image || (root.contains && !root.contains(image))) return;
        const fallback = image.parentElement?.querySelector?.("[data-message-image-fallback]")
          || image.parentElement?.querySelector?.("[data-generated-image-fallback]");
        if (!fallback) return;
        image.hidden = true;
        fallback.hidden = false;
      }, true);
      root.addEventListener("keydown", (event) => {
        const foldControl = event.target?.closest?.(foldControlSelector);
        if (foldControl && (!root.contains || root.contains(foldControl))) {
          foldControl.classList?.remove("is-pointer-focus");
        }
        if (!["Enter", " "].includes(event.key)) return;
        const traceToggle = event.target?.closest?.("[data-execution-trace-toggle]");
        if (!traceToggle || (root.contains && !root.contains(traceToggle))) return;
        event.preventDefault();
        traceToggle.click();
      });
      return true;
    }

    function renderCopyButton(text) {
      if (!text || !text.trim()) return "";
      return `<button class="msg-copy-btn" type="button" title="${t("copy")}" aria-label="${t("copy")}" data-copy-text="${escapeHtml(text)}">${COPY_SVG}</button>`;
    }

    function renderUserTextProjection(text, index) {
      if (!text) return "";
      const key = String(index);
      const contentId = `user-message-text-${key}`;
      return `<div class="user-message-text is-collapsed" id="${contentId}" data-user-message-text="${key}"><div class="bubble">${renderMarkdown(text)}</div></div><button class="user-message-toggle" type="button" hidden data-user-message-toggle="${key}" data-i18n="expandUserMessage" data-i18n-title="expandUserMessage" data-i18n-aria-label="expandUserMessage" aria-controls="${contentId}" aria-expanded="false" aria-label="${t("expandUserMessage")}" title="${t("expandUserMessage")}">${t("expandUserMessage")}</button>`;
    }

    function formatMessageTime(isoString) {
      if (!isoString) return "";
      const date = new Date(isoString);
      if (Number.isNaN(date.getTime())) return "";
      const hh = String(date.getHours()).padStart(2, "0");
      const mm = String(date.getMinutes()).padStart(2, "0");
      const now = new Date();
      const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
      const messageDay = new Date(date.getFullYear(), date.getMonth(), date.getDate());
      const diffDays = Math.round((today - messageDay) / 86400000);
      if (diffDays === 0) return `${hh}:${mm}`;
      if (diffDays === 1) return `${t("yesterday")} ${hh}:${mm}`;
      const month = String(date.getMonth() + 1).padStart(2, "0");
      const day = String(date.getDate()).padStart(2, "0");
      return date.getFullYear() === now.getFullYear()
        ? `${month}-${day} ${hh}:${mm}`
        : `${date.getFullYear()}-${month}-${day} ${hh}:${mm}`;
    }

    function renderUserMessageTime(isoString) {
      const time = formatMessageTime(isoString);
      if (!time) return "";
      return `<time class="msg-time user-message-time" datetime="${escapeHtml(String(isoString))}">${escapeHtml(time)}</time>`;
    }

    function renderUsageParts(usage) {
      const normalized = normalizeResponseUsage(usage);
      if (!normalized) return [];
      const parts = [];
      if (normalized.input) parts.push(`<span class="response-token" data-usage-kind="input" title="${escapeHtml(t("statInputTitle"))}"><svg class="stat-icon stat-arrow-svg" viewBox="0 0 1024 1024" width="14" height="14"><path d="M478.3 927.5V175.2L259 394.5c-10.7 10.7-28.1 10.7-38.7 0l-6.5-6.5c-10.7-10.7-10.7-28.1 0-38.7L481.6 81.4c4.5-9.2 13.4-16 23.9-17.6 7.1-1.5 14.7-0.1 21 4 4 2.4 7.5 5.6 10.1 9.4l0.5 0.5c2.6 2.6 4.6 5.6 5.9 8.8l266.7 266.7c10.7 10.7 10.7 28.1 0 38.7l-6.5 6.5c-10.7 10.7-28.1 10.7-38.7 0l-222.3-222v751.1c0 17.6-14.4 32-32 32-17.5 0-31.9-14.4-31.9-32z" fill="currentColor"/></svg>${formatCompact(normalized.input)}</span>`);
      if (normalized.output) parts.push(`<span class="response-token" data-usage-kind="output" title="${escapeHtml(t("statOutputTitle"))}"><svg class="stat-icon stat-arrow-svg" viewBox="0 0 1024 1024" width="14" height="14"><path d="M512 858.7a32 32 0 01-32-32V124.8a32 32 0 1164 0v701.9a32 32 0 01-32 32z" fill="currentColor"/><path d="M512 901.7L234.9 624.6a32 32 0 1145.3-45.3L512 811.2l231.8-231.8a32 32 0 0145.3 45.3z" fill="currentColor"/></svg>${formatCompact(normalized.output)}</span>`);
      if (normalized.cache) parts.push(`<span class="response-token" data-usage-kind="cache-read" title="${escapeHtml(t("statCacheTitle"))}"><svg class="stat-icon stat-cache-svg" viewBox="0 0 1024 1024" width="14" height="14"><path d="M241.8 881.5a127 127 0 01-127-127v-85.3a13 13 0 0113-13h14.3a13 13 0 0113 13v85.3a86.6 86.6 0 0086.5 86.5h540.4a86.6 86.6 0 0086.5-86.5v-85.4a13 13 0 0113-13H896a13 13 0 0113 13v85.4a127 127 0 01-126.9 126.9zM273.4 455.7a13 13 0 010-18.5l10.2-10.3a13 13 0 0118.5 0l164.9 164.3a15.4 15.4 0 0026.2-10.9v-404.5a13 13 0 0113-13h14.3a13 13 0 0113 13v404.5a15.4 15.4 0 009.5 14.2 15.4 15.4 0 0016.7-3.3l166.3-164.6a13 13 0 0118.5 0l10.2 10.2a13 13 0 010 18.5L512 695z" fill="currentColor"/></svg>${formatCompact(normalized.cache)}</span>`);
      if (normalized.cacheWrite) parts.push(`<span class="response-token" data-usage-kind="cache-write" title="${escapeHtml(t("statCacheWriteTitle"))}"><svg class="stat-icon stat-cache-svg" viewBox="0 0 1024 1024" width="14" height="14"><path d="M241.8 881.5a127 127 0 01-127-127v-85.3a13 13 0 0113-13h14.3a13 13 0 0113 13v85.3a86.6 86.6 0 0086.5 86.5h540.4a86.6 86.6 0 0086.5-86.5v-85.4a13 13 0 0113-13H896a13 13 0 0113 13v85.4a127 127 0 01-126.9 126.9zM273.4 455.7a13 13 0 010-18.5l10.2-10.3a13 13 0 0118.5 0l164.9 164.3a15.4 15.4 0 0026.2-10.9v-404.5a13 13 0 0113-13h14.3a13 13 0 0113 13v404.5a15.4 15.4 0 009.5 14.2 15.4 15.4 0 0016.7-3.3l166.3-164.6a13 13 0 0118.5 0l10.2 10.2a13 13 0 010 18.5L512 695z" fill="currentColor"/></svg>${formatCompact(normalized.cacheWrite)}</span>`);
      return parts;
    }

    function renderCompletedRunStatus(_model, elapsed, usage = null) {
      const usageHtml = renderUsageParts(usage).join(`<span class="run-separator">·</span>`);
      const elapsedHtml = elapsed
        ? `<span class="run-time"><svg class="stat-icon stat-time-svg" viewBox="0 0 1024 1024" width="13" height="13"><path d="M711.7 655.4c-5.1 0-10.2-1.5-14.8-4.1l-199.7-112.6c-9.7-5.6-15.9-15.9-15.9-26.6V276.5c0-16.9 13.8-30.7 30.7-30.7s30.7 13.8 30.7 30.7v217.6l183.8 103.9c14.8 8.2 20 27.1 11.8 42-5.6 9.7-15.9 15.4-26.6 15.4z" fill="currentColor"/><circle cx="512" cy="512" r="378.9" fill="none" stroke="currentColor" stroke-width="61.4"/></svg>${escapeHtml(elapsed)}</span>`
        : "";
      const separator = usageHtml && elapsedHtml ? `<span class="run-separator">·</span>` : "";
      return `<span class="run-status completed">${usageHtml}${separator}${elapsedHtml}</span>`;
    }

    function getResponseElapsed(msg) {
      return String(msg?._responseTime || msg?.meta?._responseTime || "").trim();
    }

    function isDetachedProjectionMessage(msg) {
      return Boolean(
        msg?.meta?.detachedFromMain
        || msg?.meta?.kind === "background-subagent",
      );
    }

    function isSteerProjectionMessage(msg) {
      return Boolean(
        msg?.role === "user"
        && String(msg.meta?.steerDispatch?.agentRunId || ""),
      );
    }

    function renderCompletedRunHeader(elapsed) {
      if (!elapsed) return "";
      return `<div class="completed-run-status msg" data-completed-run-status>
        <span class="completed-run-line">
          <span class="completed-run-label">${escapeHtml(t("completedElapsedLabel"))}</span>
          <span class="completed-run-timer" title="${escapeHtml(t("taskElapsedTitle"))}">${escapeHtml(elapsed)}</span>
        </span>
      </div>`;
    }

    function collectCompletedTurnStatuses(messages) {
      const statuses = new Map();
      let userIndex = -1;
      messages.forEach((msg, index) => {
        if (!msg || isInternalMessage(msg)) return;
        if (msg.role === "user"
            && !isSteerProjectionMessage(msg)
            && !["pending", "canceled"].includes(msg.meta?.queuedDispatch?.status)
            && !msg.meta?.detachedFromMain) {
          userIndex = index;
          return;
        }
        if (userIndex < 0
            || msg.role !== "assistant"
            || msg.streaming
            || msg.meta?.kind === "auto-context-compaction"
            || isDetachedProjectionMessage(msg)) return;
        const elapsed = getResponseElapsed(msg);
        if (elapsed) statuses.set(userIndex, elapsed);
      });
      return statuses;
    }

    function collectExecutionTraceTurns(messages) {
      const turns = new Set();
      let userIndex = -1;
      messages.forEach((msg, index) => {
        if (!msg || isInternalMessage(msg)) return;
        if (msg.role === "user"
            && !isSteerProjectionMessage(msg)
            && !["pending", "canceled"].includes(msg.meta?.queuedDispatch?.status)
            && !msg.meta?.detachedFromMain) {
          userIndex = index;
          return;
        }
        if (userIndex < 0 || isDetachedProjectionMessage(msg)) return;
        if (msg.meta?.kind === "auto-context-compaction") {
          turns.add(userIndex);
          return;
        }
        if (msg.role === "tool-call" || msg.role === "tool-result") {
          turns.add(userIndex);
          return;
        }
        if (msg.role !== "assistant") return;
        const content = (getMessageText(msg) || "").trim();
        if (isPublicProcessCommentary(msg)
            || msg.meta?.toolCalls?.length
            || (msg._streamProjection === "thinking"
              && content
              && !isToolPlanningPlaceholder(content)
              && !isOperationalToolNotice(content))) {
          turns.add(userIndex);
        }
      });
      return turns;
    }

    function renderUserProjection(msg, index, options = {}) {
      const text = Array.isArray(msg.content)
        ? (msg.content.find((item) => item.type === "text")?.text || "")
        : getMessageText(msg);
      const images = msg._images || [];
      const time = renderUserMessageTime(msg._time);
      const dispatchId = msg.meta?.backgroundDispatch?.id;
      const queueItemId = msg.meta?.queuedDispatch?.id;
      const dispatchAttr = [
        dispatchId ? ` data-background-message-id="${escapeHtml(dispatchId)}"` : "",
        queueItemId ? ` data-queued-message-id="${escapeHtml(queueItemId)}"` : "",
      ].join("");
      const dispatchJob = dispatchId ? getBackgroundJob(dispatchId) : null;
      const backgroundStatus = dispatchJob?.status === "pending"
        ? `<span class="background-dispatch-status pending"><span class="background-dispatch-dot"></span>${t("backgroundPending")}</span>`
        : dispatchJob?.status === "running"
          ? `<span class="background-dispatch-status running"><span class="background-dispatch-dot"></span>${t("backgroundRunning")}</span>`
          : "";
      const dispatchStatus = backgroundStatus;
      const goalOrigin = msg.meta?.goalOrigin;
      const confirmedGoalOrigin = Boolean(
        goalOrigin?.confirmed === true
        && String(msg.id || "")
        && String(goalOrigin.messageId || "") === String(msg.id || "")
        && String(goalOrigin.goalId || "")
        && String(goalOrigin.sourceKind || "") === "explicit"
      );
      const goalMarker = confirmedGoalOrigin
        ? `<span class="goal-message-marker" data-goal-id="${escapeHtml(goalOrigin.goalId)}" title="${escapeHtml(t("goalMessageMarkerTitle"))}">${escapeHtml(t("goalMessageMarker"))}</span>`
        : "";
      const traceClass = options.tracePersistent ? " execution-trace-persistent" : "";
      const imageItems = images.map((image, imageIndex) => {
        const src = getImagePreviewSource(image);
        const onLoad = image.path ? " data-message-scroll-on-load" : "";
        const mime = String(image?.mime || "").trim().toLowerCase();
        const usesDerivedTiffPreview = hasImagePreviewSource && ["image/tiff", "image/tif"].includes(mime);
        if (!usesDerivedTiffPreview) {
          return `<img class="msg-img msg-img-clickable" src="${src}" alt="${escapeHtml(image.name || "image")}" data-img="${imageIndex}"${onLoad} data-message-image-preview title="Click to enlarge">`;
        }
        const preview = src
          ? `<img class="msg-img msg-img-clickable" src="${escapeHtml(src)}" alt="${escapeHtml(image.name || "image")}" data-img="${imageIndex}"${onLoad} data-message-image-preview title="Click to enlarge">`
          : "";
        const hidden = src ? " hidden" : "";
        const name = escapeHtml(image.name || "image.tiff");
        const fallback = `<div class="image-attachment-card message-image-attachment-card" data-message-image-fallback${hidden} role="img" aria-label="${name}"><span class="image-attachment-card-type">IMAGE</span><span class="image-attachment-card-name">${name}</span></div>`;
        return `<span class="message-image-preview-shell">${preview}${fallback}</span>`;
      }).join("");
      if (!text && images.length === 0) return "";
      if (images.length) {
        const imageGroup = `<div class="bubble bubble-img msg-image-group">${imageItems}</div>`;
        const textBubble = renderUserTextProjection(text, index);
        const batchMeta = text
          ? `<div class="msg-meta">${goalMarker}${dispatchStatus}${time}${renderCopyButton(text)}</div>`
          : (goalMarker || dispatchStatus)
            ? `<div class="msg-meta">${goalMarker}${dispatchStatus}${time}</div>`
            : "";
        return `<article class="msg user msg-image-batch${traceClass}" data-msg-index="${index}"${dispatchAttr}><div class="user-message-hover-area user-message-batch">${imageGroup}${textBubble}${batchMeta}</div></article>`;
      }
      const textArticle = text
        ? `<article class="msg user${traceClass}" data-msg-index="${index}"${dispatchAttr}><div class="user-message-hover-area">${renderUserTextProjection(text, index)}<div class="msg-meta">${goalMarker}${dispatchStatus}${time}${renderCopyButton(text)}</div></div></article>`
        : "";
      return textArticle;
    }

    function renderUserInputSummaryProjection(msg, index) {
      const answers = Array.isArray(msg.meta?.answers) ? msg.meta.answers : [];
      return `<article class="msg msg-flow-event user-input-flow" data-msg-index="${index}">
        <span class="msg-flow-icon" aria-hidden="true">?</span>
        <div class="msg-flow-body">
          <strong>${escapeHtml(msg.meta?.title || t("questionnaireSummary"))}</strong>
          ${answers.map((answer) => `<span><b>${escapeHtml(answer.prompt || "")}</b> ${escapeHtml(answer.answer || t("questionCanceled"))}</span>`).join("")}
        </div>
      </article>`;
    }

    function compactProcessText(value, limit = 600) {
      const text = String(value || "").replace(/\s+/g, " ").trim();
      if (!text || isToolPlanningPlaceholder(text)) return "";
      return text.length > limit ? `${text.slice(0, limit)}…` : text;
    }

    function parseToolArguments(value) {
      if (value && typeof value === "object" && !Array.isArray(value)) return value;
      try {
        const parsed = JSON.parse(String(value || "{}"));
        return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
      } catch (_) {
        return {};
      }
    }

    function toolCallDetails(call) {
      const native = call?.function || {};
      const metaTool = call?.meta?.tool || {};
      const args = Object.keys(metaTool).length
        ? metaTool
        : parseToolArguments(native.arguments ?? call?.arguments);
      const action = String(
        call?.meta?.action
        || args.action
        || native.name
        || call?.name
        || "",
      );
      return {
        id: String(call?.meta?.toolCallId || call?.id || ""),
        action,
        args,
      };
    }

    function toolTarget(args = {}, result = {}) {
      const candidates = [
        result.path,
        args.path,
        args.dir,
        args.directory,
        args.query,
        args.pattern,
        args.command,
        args.url,
        args.skill,
        args.name,
        args.task,
      ];
      const value = candidates.find((candidate) => String(candidate || "").trim());
      return compactProcessText(value, 110);
    }

    function toolResultError(result = {}) {
      const direct = result.error || result.stderr || result.message || "";
      if (direct) return compactProcessText(direct, 220);
      if (Array.isArray(result.fieldErrors) && result.fieldErrors.length) {
        return compactProcessText(result.fieldErrors
          .map((item) => item?.message || item?.path || "")
          .filter(Boolean)
          .join("；"), 220);
      }
      return "";
    }

    function collectToolProcess(items) {
      const calls = [];
      const callsById = new Map();

      const ensureCall = (rawCall, fallbackId, agentRunId = "") => {
        const details = toolCallDetails(rawCall);
        if (isInternalGoalTool({ name: details.action })) return null;
        const id = details.id || fallbackId;
        const runId = String(agentRunId || "");
        const identity = `${runId}\u0000${id}`;
        let entry = callsById.get(identity);
        if (!entry) {
          entry = {
            id,
            agentRunId: runId,
            action: details.action,
            args: details.args,
            started: false,
            result: null,
            resultMessage: null,
          };
          callsById.set(identity, entry);
          calls.push(entry);
        } else {
          if (details.action) entry.action = details.action;
          if (Object.keys(details.args).length) entry.args = details.args;
        }
        return entry;
      };

      items.forEach(({ msg, index }, itemIndex) => {
        if (msg.role === "assistant") {
          visibleAssistantToolCalls(msg).forEach((call, callIndex) => {
            ensureCall(call, `assistant-${index}-${callIndex}`, msg.meta?.agentRunId);
          });
          return;
        }
        if (msg.role === "tool-call") {
          if (isInternalGoalTool(msg)) return;
          const entry = ensureCall(msg, `call-${index}-${itemIndex}`, msg.meta?.agentRunId);
          if (!entry) return;
          entry.started = true;
          entry.callMessage = msg;
          return;
        }
        if (msg.role === "tool-result") {
          if (isInternalGoalTool(msg)) return;
          const id = String(msg.meta?.toolCallId || `result-${index}-${itemIndex}`);
          const entry = ensureCall({
            id,
            name: msg.meta?.action || "",
            arguments: {},
          }, id, msg.meta?.agentRunId);
          if (!entry) return;
          entry.resultMessage = msg;
          entry.result = msg.meta?.result || msg.meta?.authorizationResult || null;
        }
      });

      return { calls };
    }

    function getProcessCallView(call) {
      const result = call.result && typeof call.result === "object" ? call.result : {};
      const declaredOutcome = String(call.resultMessage?.meta?.outcome || "");
      let outcome = declaredOutcome;
      if (!outcome && call.result) outcome = result.ok === false ? "failed" : "succeeded";
      if (!outcome && call.resultMessage?.meta?.applied) outcome = "succeeded";
      if (!outcome && call.resultMessage?.meta?.rejected) outcome = "failed";
      if (!outcome && call.resultMessage?.meta?.pendingEditId) outcome = "running";
      if (!outcome && call.resultMessage) outcome = "completed";
      if (!outcome) outcome = call.started ? "running" : "pending";
      if (result.cancelled) outcome = "cancelled";
      const target = toolTarget(call.args, result);
      const error = outcome === "failed"
        ? toolResultError(result) || compactProcessText(call.resultMessage?.content, 220)
        : "";
      return {
        ...call,
        outcome,
        target,
        error,
        errorCode: String(result.errorCode || ""),
      };
    }

    function processOutcomeLabel(outcome) {
      if (outcome === "failed") return t("toolProcessFailed");
      if (outcome === "succeeded") return t("toolProcessSucceeded");
      if (outcome === "completed") return t("toolProcessCompleted");
      if (outcome === "cancelled") return t("toolProcessCancelled");
      if (outcome === "running") return t("toolProcessRunning");
      return t("toolProcessPending");
    }

    function boundedProcessDetail(value, maxLength = 1600) {
      if (value == null || value === "") return "";
      let text = "";
      if (typeof value === "string") {
        text = value;
      } else {
        try {
          text = JSON.stringify(value, null, 2);
        } catch (_) {
          text = String(value);
        }
      }
      const normalized = text.trim();
      if (normalized.length <= maxLength) return normalized;
      return `${normalized.slice(0, maxLength)}\n…`;
    }

    function processCallArguments(call) {
      if (!call?.args || !Object.keys(call.args).length) return "";
      if (call.action === "generate_image") {
        return boundedProcessDetail({
          size: String(call.args.size || "auto"),
          quality: String(call.args.quality || "auto"),
          count: Math.max(1, Number(call.args.count || 1)),
          outputFormat: String(call.args.outputFormat || "png"),
          hasReference: Boolean(call.args.reference),
        }, 400);
      }
      return boundedProcessDetail(call.args, 1200);
    }

    function processCallResult(call) {
      if (call?.error) return boundedProcessDetail(call.error);
      if (call?.action === "generate_image") {
        if (call?.result?.ok === false) {
          return boundedProcessDetail(
            String(call.result.errorCode || call.result.error || t("toolProcessFailed")),
            240,
          );
        }
        const count = generatedAssetsForCall(call).length || Number(call?.result?.count || 0);
        return count > 0 ? t("imageAssetsGenerated", { count }) : "";
      }
      const content = getMessageText(call?.resultMessage);
      if (content) return boundedProcessDetail(content);
      if (call?.result) return boundedProcessDetail(call.result);
      return "";
    }

    function generatedAssetExtension(mimeType) {
      if (mimeType === "image/png") return "png";
      if (mimeType === "image/jpeg") return "jpg";
      if (mimeType === "image/webp") return "webp";
      return "";
    }

    function generatedAssetsForCall(call) {
      if (call?.action !== "generate_image" || call?.result?.ok === false) return [];
      const sessionId = String(getSessionId() || "");
      if (!sessionId) return [];
      return (Array.isArray(call?.result?.assets) ? call.result.assets : [])
        .map((asset) => {
          const assetId = String(asset?.assetId || "");
          const mimeType = String(asset?.mimeType || "").toLowerCase();
          const extension = generatedAssetExtension(mimeType);
          const width = Number(asset?.width);
          const height = Number(asset?.height);
          const byteLength = Number(asset?.byteLength);
          if (
            !/^ga1_[A-Za-z0-9_-]{32,96}$/.test(assetId)
            || !extension
            || !Number.isInteger(width)
            || width <= 0
            || !Number.isInteger(height)
            || height <= 0
            || !Number.isInteger(byteLength)
            || byteLength <= 0
          ) return null;
          return {
            assetId,
            mimeType,
            extension,
            width,
            height,
            byteLength,
            url: `/api/sessions/${encodeURIComponent(sessionId)}/generated-assets/${encodeURIComponent(assetId)}`,
          };
        })
        .filter(Boolean);
    }

    function renderGeneratedAssetGallery(call) {
      const assets = generatedAssetsForCall(call);
      if (!assets.length) return "";
      return `<section class="generated-image-result" data-generated-image-gallery>
        <strong>${escapeHtml(t("imageAssetsGenerated", { count: assets.length }))}</strong>
        <div class="generated-image-grid">
          ${assets.map((asset, index) => `<article class="generated-image-card">
            <button class="generated-image-preview" type="button" data-generated-image-preview="${escapeHtml(asset.url)}" aria-label="${escapeHtml(t("imageAssetPreview"))}">
              <img src="${escapeHtml(asset.url)}" alt="${escapeHtml(t("imageAssetPreview"))}" loading="lazy" data-generated-image-preview-img />
              <span class="generated-image-fallback" data-generated-image-fallback hidden>${escapeHtml(t("imageReadFailed"))}</span>
            </button>
            <div class="generated-image-meta">
              <span>${escapeHtml(t("imageAssetMeta", { width: asset.width, height: asset.height, format: asset.mimeType.replace("image/", "").toUpperCase(), size: formatSize(asset.byteLength) }))}</span>
              <a class="generated-image-download" href="${escapeHtml(asset.url)}" download="generated-image-${index + 1}.${asset.extension}">${escapeHtml(t("imageAssetDownload"))}</a>
            </div>
          </article>`).join("")}
        </div>
      </section>`;
    }

    function currentProcessCall(calls) {
      return calls.find((call) => call.outcome === "running")
        || calls.find((call) => call.outcome === "pending")
        || calls[calls.length - 1]
        || null;
    }

    function processSummaryFamily(action) {
      if (action === "run_command") return "command";
      if (["propose_edit", "apply_edit", "write_file"].includes(action)) return "edit";
      if (action === "delete_file") return "delete";
      if (["read_file", "list_files", "search_files", "glob_files"].includes(action)) return "inspect";
      if (action === "request_user_input") return "questionnaire";
      return "tool";
    }

    function hasMultipleProcessSubjects(family, calls) {
      if (family === "command" || family === "tool") return calls.length > 1;
      const targets = new Set(calls.map((call) => String(call.target || "").trim()).filter(Boolean));
      return (targets.size || calls.length) > 1;
    }

    function completedProcessSummary(calls) {
      const families = new Map();
      calls.forEach((call) => {
        const family = processSummaryFamily(call.action);
        if (!families.has(family)) families.set(family, []);
        families.get(family).push(call);
      });
      const keys = {
        command: ["toolProcessRanCommand", "toolProcessRanCommands"],
        edit: ["toolProcessEditedFile", "toolProcessEditedFiles"],
        inspect: ["toolProcessInspectedFile", "toolProcessInspectedFiles"],
        delete: ["toolProcessDeletedFile", "toolProcessDeletedFiles"],
        questionnaire: ["toolProcessAskedUser", "toolProcessAskedUserMultiple"],
        tool: ["toolProcessUsedTool", "toolProcessUsedTools"],
      };
      return [...families.entries()]
        .map(([family, familyCalls]) => t(keys[family][hasMultipleProcessSubjects(family, familyCalls) ? 1 : 0]))
        .join(" · ");
    }

    function stageProcessOutcome(calls) {
      if (calls.some((call) => call.outcome === "running")) return "running";
      if (calls.some((call) => call.outcome === "pending")) return "pending";
      if (calls.some((call) => call.outcome === "failed")) return "failed";
      if (calls.some((call) => call.outcome === "cancelled")) return "cancelled";
      if (calls.every((call) => call.outcome === "succeeded")) return "succeeded";
      return "completed";
    }

    function renderToolProcessProjection(items, serial, options = {}) {
      const { calls } = collectToolProcess(items);
      const visibleCalls = calls.map(getProcessCallView);
      if (!visibleCalls.length) return "";
      const currentCall = currentProcessCall(visibleCalls);
      const detectedOutcome = stageProcessOutcome(visibleCalls);
      const singleToolStage = visibleCalls.length === 1;
      const toolIsActive = detectedOutcome === "running" || detectedOutcome === "pending";
      const stageIsActive = Boolean(options.activeStage)
        || toolIsActive;
      const processOutcome = stageIsActive ? "running" : detectedOutcome;
      const headingText = singleToolStage
        ? getToolActionLabel(currentCall.action)
        : stageIsActive
        ? getToolActionLabel(currentCall.action)
        : completedProcessSummary(visibleCalls);
      const headingTarget = singleToolStage || stageIsActive ? currentCall.target : "";
      const stageClasses = [
        processOutcome,
        toolIsActive ? "tool-active" : "",
        singleToolStage ? "single-tool" : "",
      ].filter(Boolean).join(" ");
      const processKey = String(options.processKey || serial);
      const firstToolCallId = String(visibleCalls.find((call) => call.id)?.id || processKey);
      const firstAgentRunId = String(visibleCalls.find((call) => call.agentRunId)?.agentRunId || "");
      const legacyProcessId = `${String(getSessionId() || "")}:${firstToolCallId}`;
      const processId = firstAgentRunId
        ? `${String(getSessionId() || "")}:${firstAgentRunId}:${firstToolCallId}`
        : legacyProcessId;
      const expandedToolProcesses = options.expandedToolProcesses instanceof Set
        ? options.expandedToolProcesses
        : new Set(options.expandedToolProcesses || []);
      const expandedToolItems = options.expandedToolItems instanceof Set
        ? options.expandedToolItems
        : new Set(options.expandedToolItems || []);
      const hasGeneratedAssets = visibleCalls.some((call) => generatedAssetsForCall(call).length > 0);
      const open = (
        options.open
        || hasGeneratedAssets
        || (
          options.allowExpanded
          && (
            expandedToolProcesses.has(processId)
            || expandedToolProcesses.has(legacyProcessId)
            || expandedToolProcesses.has(processKey)
          )
        )
      ) ? " open" : "";

      return `
        <article class="msg assistant tool-process" data-tool-process-block="${serial}">
          <details class="tool-process-stage ${escapeHtml(stageClasses)}" data-current-action="${escapeHtml(currentCall.action)}" data-tool-process-key="${escapeHtml(processKey)}" data-tool-process-id="${escapeHtml(processId)}"${open}>
            <summary class="tool-process-stage-summary">
              <span class="tool-process-stage-heading"><strong>${escapeHtml(headingText)}</strong>${headingTarget ? `<code>${escapeHtml(headingTarget)}</code>` : ""}</span>
              <span class="tool-process-stage-chevron" aria-hidden="true"></span>
            </summary>
            <div class="tool-process-stage-body">
              <div class="tool-process-list">
                ${visibleCalls.map((call) => {
                  const action = getToolActionLabel(call.action);
                  const argumentsText = processCallArguments(call);
                  const resultText = processCallResult(call);
                  const toolCallId = String(call.id || "");
                  const itemKey = `${processId}:${String(call.agentRunId || "")}:${toolCallId}`;
                  const legacyItemKey = `${legacyProcessId}:${toolCallId}`;
                  const itemOpen = options.allowExpanded
                    && (
                      expandedToolItems.has(itemKey)
                      || expandedToolItems.has(legacyItemKey)
                      || expandedToolItems.has(toolCallId)
                    )
                    ? " open"
                    : (generatedAssetsForCall(call).length ? " open" : "");
                  return `<details class="tool-process-item ${escapeHtml(call.outcome)}" data-tool-call-id="${escapeHtml(toolCallId)}" data-agent-run-id="${escapeHtml(call.agentRunId || "")}" data-tool-process-item-key="${escapeHtml(itemKey)}"${itemOpen}>
                    <summary>
                      <span class="tool-process-indicator ${escapeHtml(call.outcome)}" aria-hidden="true"></span>
                      <span class="tool-process-row-heading"><strong>${escapeHtml(action)}</strong>${call.target ? `<code>${escapeHtml(call.target)}</code>` : ""}</span>
                      <span class="tool-process-outcome">${escapeHtml(processOutcomeLabel(call.outcome))}</span>
                      <span class="tool-process-chevron" aria-hidden="true"></span>
                    </summary>
                    <div class="tool-process-body">
                      ${argumentsText ? `<section class="tool-process-detail"><strong>${escapeHtml(t("toolProcessArguments"))}</strong><pre>${escapeHtml(argumentsText)}</pre></section>` : ""}
                      ${resultText ? `<section class="tool-process-detail"><strong>${escapeHtml(t("toolProcessResult"))}</strong><pre>${escapeHtml(resultText)}</pre></section>` : ""}
                      ${renderGeneratedAssetGallery(call)}
                    </div>
                  </details>`;
                }).join("")}
              </div>
            </div>
          </details>
        </article>
      `;
    }

    function collectAgentResponseInfoProjection(messages) {
      const groups = new Map();
      messages.forEach((message, index) => {
        if (message?.role !== "assistant") return;
        const meta = message.meta || {};
        const usageGroupId = String(meta.agentUsageGroupId || "");
        const runId = String(meta.agentRunId || meta.agentClientRequestId || "");
        const key = usageGroupId
          ? `turn:${usageGroupId}`
          : (runId ? `run:${runId}` : "");
        if (!key) return;
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push({ message, index });
      });

      const projection = new Map();
      groups.forEach((entries) => {
        const usageEntries = entries.filter(({ message }) => (
          hasUsageStats(message?.meta?._usage || message?._usage)
        ));
        if (!usageEntries.length) return;
        entries.forEach(({ index }) => projection.set(index, { suppressResponseInfo: true }));

        const hasManagedTerminal = usageEntries.some(({ message }) => (
          Object.prototype.hasOwnProperty.call(message?.meta || {}, "_usageGroupTerminal")
        ));
        const groupTerminal = !hasManagedTerminal || usageEntries.some(({ message }) => (
          message?.meta?._usageGroupTerminal === true
        ));
        if (!groupTerminal) return;

        const taskEntriesByRun = new Map();
        usageEntries.forEach((entry) => {
          const meta = entry.message?.meta || {};
          if (meta._usageScope !== "task") return;
          const runKey = String(
            meta.agentRunId
            || meta._usageOwner
            || meta.agentClientRequestId
            || `message:${entry.index}`,
          );
          taskEntriesByRun.set(runKey, entry);
        });
        const aggregateEntries = taskEntriesByRun.size
          ? [...taskEntriesByRun.values()]
          : usageEntries;
        const usage = { input: 0, output: 0, cache: 0 };
        aggregateEntries.forEach(({ message }) => {
            const part = normalizeResponseUsage(message?.meta?._usage || message?._usage);
            if (!part) return;
            usage.input += Number(part.input || 0);
            usage.output += Number(part.output || 0);
            usage.cache += Number(part.cache || 0);
            if (Object.prototype.hasOwnProperty.call(part, "cacheWrite")) {
              usage.cacheWrite = Number(usage.cacheWrite || 0) + Number(part.cacheWrite || 0);
            }
        });
        const target = [...entries].reverse().find(({ message }) => {
          if (message.streaming
              || isInternalGoalOnlyAssistant(message)
              || isPublicProcessCommentary(message)) return false;
          if (visibleAssistantToolCalls(message).length) return false;
          const content = (getMessageText(message) || "").trim();
          return Boolean(
            content
            && !isToolPlanningPlaceholder(content)
            && !isOperationalToolNotice(content)
          );
        }) || [...entries].reverse().find(({ message }) => {
          if (message.streaming
              || isInternalGoalOnlyAssistant(message)
              || isPublicProcessCommentary(message)) return false;
          const content = (getMessageText(message) || "").trim();
          return Boolean(
            content
            && !isToolPlanningPlaceholder(content)
            && !isOperationalToolNotice(content)
          );
        });
        if (target && hasUsageStats(usage)) {
          projection.set(target.index, {
            suppressResponseInfo: false,
            responseUsage: usage,
          });
        }
      });
      return projection;
    }

    function renderAssistantResponseInfo(msg, options = {}) {
      if (options.suppressResponseInfo) return "";
      const meta = msg.meta || {};
      const usage = Object.prototype.hasOwnProperty.call(options, "responseUsage")
        ? options.responseUsage
        : (meta._usage || msg._usage || null);
      const elapsed = options.includeElapsed === false ? "" : getResponseElapsed(msg);
      if (!hasUsageStats(usage) && !elapsed) return "";
      return `<div class="response-info">${renderCompletedRunStatus(meta._model || msg._model || "", elapsed, usage)}</div>`;
    }

    function formatGoalCompletionDuration(milliseconds) {
      const seconds = Math.max(0, Math.floor(Number(milliseconds || 0) / 1000));
      if (seconds < 60) return `${seconds}s`;
      const minutes = Math.floor(seconds / 60);
      const remainingSeconds = seconds % 60;
      if (minutes < 60) return `${minutes}m ${remainingSeconds}s`;
      const hours = Math.floor(minutes / 60);
      return `${hours}h ${minutes % 60}m ${remainingSeconds}s`;
    }

    function renderGoalCompletionMarker(msg) {
      const marker = msg?.meta?.goalCompletion;
      if (
        marker?.confirmed !== true
        || marker.sourceKind !== "explicit"
        || !String(marker.goalId || "")
        || !String(marker.sourceRunId || "")
        || String(msg?.meta?.agentRunId || "") !== String(marker.sourceRunId || "")
        || msg?.meta?._agentRunTerminal !== true
      ) return "";
      const createdAt = Date.parse(String(marker.createdAt || ""));
      const completedAt = Date.parse(String(marker.completedAt || ""));
      if (!Number.isFinite(createdAt) || !Number.isFinite(completedAt) || completedAt < createdAt) {
        return "";
      }
      const duration = formatGoalCompletionDuration(completedAt - createdAt);
      return `<div class="goal-completion-marker">${escapeHtml(t("goalCompletionMarker", { duration }))}</div>`;
    }

    function renderAssistantFooter(msg, options = {}, trailing = "") {
      const responseInfo = renderAssistantResponseInfo(msg, options);
      const completionMarker = renderGoalCompletionMarker(msg);
      if (!responseInfo && !completionMarker && !trailing) return "";
      return `<div class="msg-footer"><div class="msg-footer-status">${responseInfo}${completionMarker}${trailing}</div></div>`;
    }

    function renderAutoContextCompaction(msg, index) {
      const status = ["running", "completed", "failed"].includes(msg.meta?.status)
        ? msg.meta.status
        : "completed";
      const manual = msg.meta?.kind === "manual-context-compaction";
      if (manual && msg.meta?.persistenceStatus === "failed") {
        const compactionId = String(msg.meta?.compactionId || "");
        const retry = /^[a-f0-9-]{8,64}$/i.test(compactionId)
          ? `<button class="mini-btn" type="button" data-manual-compaction-retry="${escapeHtml(compactionId)}">${escapeHtml(t("manualCompactRetrySave"))}</button>`
          : "";
        const persistenceLabel = status === "failed"
          ? "manualCompactFailurePersistenceFailed"
          : "manualCompactPersistenceFailed";
        return `<div class="context-compaction-row msg ${escapeHtml(status)} warning" data-msg-index="${index}" data-context-compaction data-context-compaction-mode="manual">
          <span class="context-compaction-icon" aria-hidden="true"></span>
          <span>${escapeHtml(t(persistenceLabel))}</span>${retry}
        </div>`;
      }
      if (manual && msg.meta?.archiveStatus === "failed") {
        return `<div class="context-compaction-row msg completed warning" data-msg-index="${index}" data-context-compaction data-context-compaction-mode="manual">
          <span class="context-compaction-icon" aria-hidden="true"></span>
          <span>${escapeHtml(t("manualCompactArchiveWarning"))}</span>
        </div>`;
      }
      const labelKey = manual
        ? (status === "running"
            ? "manualCompactingContext"
            : (status === "failed" ? "manualCompactContextFailed" : "manualCompactedContext"))
        : (status === "running"
            ? "autoCompactingContext"
            : (status === "failed" ? "autoCompactContextFailed" : "autoCompactedContext"));
      return `<div class="context-compaction-row msg ${escapeHtml(status)}" data-msg-index="${index}" data-context-compaction data-context-compaction-mode="${manual ? "manual" : "auto"}">
        <span class="context-compaction-icon" aria-hidden="true"></span>
        <span>${escapeHtml(t(labelKey))}</span>
      </div>`;
    }

    function renderBackgroundReplyReference(msg) {
      if (msg.meta?.kind !== "background-subagent" || !msg.meta?.jobId) return "";
      const jobId = String(msg.meta.jobId);
      const target = getMessages().find((message) => (
        message?.role === "user" && String(message.meta?.backgroundDispatch?.id || "") === jobId
      ));
      const rawPreview = (getMessageText(target) || "").replace(/\s+/g, " ").trim();
      if (!rawPreview) return "";
      const preview = rawPreview.length > 56 ? `${rawPreview.slice(0, 56)}…` : rawPreview;
      return `<button class="background-reply-reference" type="button" data-background-reply-id="${escapeHtml(jobId)}" title="${escapeHtml(rawPreview)}"><span class="background-reply-arrow" aria-hidden="true">↳</span><span class="background-reply-label">${t("backgroundReply")}</span><span class="background-reply-preview">${escapeHtml(preview)}</span></button>`;
    }

    function renderFinalAssistantProjection(msg, index, options = {}) {
      const model = msg._model || msg.meta?._model || getSelectedModel() || "Agent";
      const content = (getMessageText(msg) || "").trim();
      const traceClass = options.tracePersistent ? " execution-trace-persistent" : "";
      if (msg.streaming) {
        const hasVisibleContent = content && !isToolPlanningPlaceholder(content);
        const streamKind = msg._streamProjection === "thinking"
          ? "thinking"
          : (msg._streamProjection === "answer" ? "answer" : "pending");
        const showContent = (
          streamKind !== "pending"
          && hasVisibleContent
          && !(streamKind === "thinking" && isOperationalToolNotice(content))
        );
        const showModel = showContent;
        return `
          <article class="msg assistant is-streaming${streamKind === "pending" ? " is-pending" : ""}${streamKind === "thinking" ? " agent-commentary" : ""}${traceClass}" data-msg-index="${index}" data-streaming-message="true" data-stream-session="${escapeHtml(getSessionId() || "")}" data-stream-kind="${streamKind}">
            ${streamKind === "thinking" ? "" : `<div class="role streaming-answer-role${showModel ? "" : " is-empty"}" data-stream-role>${escapeHtml(model)}</div>`}
            <div class="bubble streaming-answer-output${showContent ? "" : " is-empty"}" data-stream-part="answer">${showContent ? renderAssistantMarkdown(content) : ""}</div>
            ${renderNetworkRecoveryStatus(getSessionId())}
          </article>
        `;
      }
      if (!content
          || isToolPlanningPlaceholder(content)
          || (isInternalGoalOnlyAssistant(msg) && !isPublicProcessCommentary(msg))) return "";
      const isCommentary = isPublicProcessCommentary(msg)
        || visibleAssistantToolCalls(msg).length > 0;
      if (isCommentary && isOperationalToolNotice(content)) return "";
      if (isCommentary) {
        return `
          <article class="msg assistant agent-commentary${traceClass}" data-msg-index="${index}">
            ${renderAssistantContent(content)}
            ${renderAssistantFooter(msg, options)}
          </article>
        `;
      }
      const replyReference = renderBackgroundReplyReference(msg);
      const copyButton = renderCopyButton(content);
      const time = formatMessageTime(msg._time);
      return `
        <article class="msg assistant${isCommentary ? " agent-commentary" : ""}${traceClass}" data-msg-index="${index}">
          <div class="role">${escapeHtml(model)}</div>
          ${replyReference}
          ${renderAssistantContent(content)}
          ${renderAssistantFooter(msg, options, `<span class="msg-footer-hover">${copyButton}${time ? `<span class="msg-time">${time}</span>` : ""}</span>`)}
        </article>
      `;
    }

    function projectMessages(messages = [], projection = {}) {
      const hasActiveRun = Boolean(projection.hasActiveRun);
      const branchMarker = projection.branchMarker || null;
      const completedTurnStatuses = collectCompletedTurnStatuses(messages);
      const executionTraceTurns = collectExecutionTraceTurns(messages);
      const expandedExecutionTraces = projection.expandedExecutionTraces instanceof Set
        ? projection.expandedExecutionTraces
        : new Set(projection.expandedExecutionTraces || []);
      const collapsedExecutionTraces = projection.collapsedExecutionTraces instanceof Set
        ? projection.collapsedExecutionTraces
        : new Set(projection.collapsedExecutionTraces || []);
      const expandedToolProcesses = projection.expandedToolProcesses instanceof Set
        ? projection.expandedToolProcesses
        : new Set(projection.expandedToolProcesses || []);
      const expandedToolItems = projection.expandedToolItems instanceof Set
        ? projection.expandedToolItems
        : new Set(projection.expandedToolItems || []);
      const responseInfoProjection = collectAgentResponseInfoProjection(messages);
      const rows = [];
      const queuedTailMessages = [];
      const claimedToolResultIndexes = new Set();
      const toolResultsByIdentity = new Map();
      messages.forEach((message, index) => {
        if (message?.role !== "tool-result" || !message.meta?.toolCallId || isInternalGoalTool(message)) return;
        const identity = `${String(message.meta?.agentRunId || "")}\u0000${String(message.meta.toolCallId)}`;
        if (!toolResultsByIdentity.has(identity)) toolResultsByIdentity.set(identity, []);
        toolResultsByIdentity.get(identity).push({ msg: message, index });
      });
      let pendingProcess = [];
      let pendingProcessAfterRows = [];
      let processSerial = 0;
      let activeUserIndex = -1;
      let currentUserIndex = -1;
      let openExecutionTraceUserIndex = -1;
      if (hasActiveRun) {
        for (let index = messages.length - 1; index >= 0; index -= 1) {
          const message = messages[index];
          if (message?.role === "user"
              && !isSteerProjectionMessage(message)
              && message.meta?.queuedDispatch?.status !== "pending"
              && !message.meta?.detachedFromMain
              && !isInternalMessage(message)) {
            activeUserIndex = index;
            break;
          }
        }
      }
      let activeForegroundToolTailIndex = -1;
      if (activeUserIndex >= 0) {
        for (let index = messages.length - 1; index > activeUserIndex; index -= 1) {
          const message = messages[index];
          if (!message || isInternalMessage(message) || isDetachedProjectionMessage(message)) continue;
          if (
            isVisibleToolProjectionMessage(message)
          ) {
            activeForegroundToolTailIndex = index;
            break;
          }
        }
      }
      let activeRunAnchorInserted = false;
      const branchBoundary = branchMarker
        ? (branchMarker.messageCount > messages.length ? 0 : branchMarker.messageCount)
        : -1;
      let branchMarkerInserted = false;

      const takeActiveRunAnchor = () => {
        if (!hasActiveRun || activeRunAnchorInserted) return "";
        activeRunAnchorInserted = true;
        return '<div class="active-run-anchor msg" data-active-run-anchor></div>';
      };
      const insertActiveRunAnchor = () => {
        const anchor = takeActiveRunAnchor();
        if (anchor) rows.push(anchor);
      };
      const flushProcess = (options = {}) => {
        if (!pendingProcess.length) return false;
        const existingIndexes = new Set(pendingProcess.map((item) => item.index));
        const callIdentities = new Set();
          pendingProcess.forEach(({ msg }) => {
            if (msg?.role === "assistant") {
            visibleAssistantToolCalls(msg).forEach((call) => {
              if (call?.id) {
                callIdentities.add(`${String(msg.meta?.agentRunId || "")}\u0000${String(call.id)}`);
              }
            });
          } else if (msg?.role === "tool-call" && msg.meta?.toolCallId) {
            callIdentities.add(`${String(msg.meta?.agentRunId || "")}\u0000${String(msg.meta.toolCallId)}`);
          }
        });
        callIdentities.forEach((identity) => {
          const resultEntry = (toolResultsByIdentity.get(identity) || []).find((entry) => (
            !existingIndexes.has(entry.index) && !claimedToolResultIndexes.has(entry.index)
          ));
          if (!resultEntry) return;
          pendingProcess.push(resultEntry);
          claimedToolResultIndexes.add(resultEntry.index);
        });
        const activeForegroundStage = hasActiveRun
          && currentUserIndex === activeUserIndex
          && pendingProcess.some(({ index }) => index === activeForegroundToolTailIndex)
          && pendingProcess.every(({ msg }) => !isDetachedProjectionMessage(msg));
        processSerial += 1;
        const processKey = `${currentUserIndex}:${processSerial}`;
        rows.push(renderToolProcessProjection(pendingProcess, processSerial, {
          ...options,
          processKey,
          activeStage: Boolean(options.activeStage) || activeForegroundStage,
          allowExpanded: hasActiveRun,
          expandedToolProcesses,
          expandedToolItems,
        }));
        if (pendingProcessAfterRows.length) rows.push(...pendingProcessAfterRows);
        pendingProcess = [];
        pendingProcessAfterRows = [];
        return true;
      };
      const openCompletedExecutionTrace = (userIndex, elapsed) => {
        const expanded = expandedExecutionTraces.has(String(userIndex));
        rows.push(`<section class="execution-trace completed${expanded ? " is-expanded" : ""}" data-execution-trace="${userIndex}">
          <div class="execution-trace-summary" role="button" tabindex="0" aria-expanded="${expanded}" data-execution-trace-toggle>
            ${renderCompletedRunHeader(elapsed)}
            <span class="execution-trace-chevron" aria-hidden="true"></span>
          </div>
          <div class="execution-trace-body">`);
        openExecutionTraceUserIndex = userIndex;
      };
      const openActiveExecutionTrace = (userIndex) => {
        const expanded = !collapsedExecutionTraces.has(String(userIndex));
        rows.push(`<section class="execution-trace active${expanded ? " is-expanded" : ""}" data-execution-trace="${userIndex}">
          <div class="execution-trace-summary" role="button" tabindex="0" aria-expanded="${expanded}" data-execution-trace-toggle>
            ${takeActiveRunAnchor()}
            <span class="execution-trace-chevron" aria-hidden="true"></span>
          </div>
          <div class="execution-trace-body">`);
        openExecutionTraceUserIndex = userIndex;
      };
      const closeExecutionTrace = (options = {}) => {
        flushProcess(options);
        if (openExecutionTraceUserIndex < 0) return;
        rows.push("</div></section>");
        openExecutionTraceUserIndex = -1;
      };
      const insertBranchMarker = () => {
        if (!branchMarker || branchMarkerInserted) return;
        flushProcess();
        rows.push(renderBranchFlow(branchMarker.parentTitle));
        branchMarkerInserted = true;
      };

      for (let index = 0; index < messages.length; index += 1) {
        if (index === branchBoundary) insertBranchMarker();
        const msg = messages[index];
        if (!msg) continue;
        if (msg.role === "user" && ["pending", "canceled"].includes(msg.meta?.queuedDispatch?.status)) {
          queuedTailMessages.push({ msg, index });
          continue;
        }
        if (msg.meta?.kind === "compact-summary") {
          flushProcess();
          continue;
        }
        if (msg.meta?.kind === "manual-context-compaction") {
          closeExecutionTrace();
          rows.push(renderAutoContextCompaction(msg, index));
          continue;
        }
        if (msg.meta?.kind === "auto-context-compaction") {
          flushProcess();
          rows.push(renderAutoContextCompaction(msg, index));
          continue;
        }
        if (msg.meta?.kind === "user-input-summary") {
          flushProcess();
          rows.push(renderUserInputSummaryProjection(msg, index));
          continue;
        }
        if (isInternalMessage(msg)) continue;
        if (isEditSuggestionMessage(msg)) {
          if (msg.role === "tool-result" && !claimedToolResultIndexes.has(index)) {
            pendingProcess.push({ msg, index });
          }
          flushProcess();
          rows.push(renderEditSuggestion(msg, index));
          continue;
        }
        if (msg.role === "assistant") {
          const streamingProcessRound = msg.streaming
            && ["pending", "thinking"].includes(msg._streamProjection);
          const toolCommentary = (getMessageText(msg) || "").trim();
          const hasMeaningfulToolCommentary = Boolean(
            toolCommentary
            && !isToolPlanningPlaceholder(toolCommentary)
            && !isOperationalToolNotice(toolCommentary)
          );
          const completedHeaderVisible = (
            currentUserIndex >= 0
            && currentUserIndex !== activeUserIndex
            && completedTurnStatuses.has(currentUserIndex)
          );
          const detachedProjection = isDetachedProjectionMessage(msg);
          const assistantOptions = {
            includeElapsed: !completedHeaderVisible || detachedProjection,
            tracePersistent: detachedProjection && openExecutionTraceUserIndex >= 0,
            ...(responseInfoProjection.get(index) || {}),
          };
          if (isInternalGoalOnlyAssistant(msg) && !isPublicProcessCommentary(msg)) continue;
          if (visibleAssistantToolCalls(msg).length) {
            if (hasMeaningfulToolCommentary) {
              flushProcess();
              rows.push(renderFinalAssistantProjection(msg, index, assistantOptions));
            }
            pendingProcess.push({
              msg: { ...msg, content: "" },
              index,
            });
            continue;
          }
          if (streamingProcessRound) {
            if (hasMeaningfulToolCommentary) {
              flushProcess();
              rows.push(renderFinalAssistantProjection(msg, index, assistantOptions));
            }
            continue;
          }
          if (isPublicProcessCommentary(msg)) {
            if (hasMeaningfulToolCommentary) {
              flushProcess();
              rows.push(renderFinalAssistantProjection(msg, index, assistantOptions));
            }
            continue;
          }
          if (detachedProjection) {
            flushProcess();
            rows.push(renderFinalAssistantProjection(msg, index, assistantOptions));
            continue;
          }
          closeExecutionTrace();
          rows.push(renderFinalAssistantProjection(msg, index, assistantOptions));
          continue;
        }
        if (msg.role === "user" && isSteerProjectionMessage(msg) && currentUserIndex >= 0) {
          const steerRow = renderUserProjection(msg, index, {
            tracePersistent: openExecutionTraceUserIndex >= 0,
          });
          if (pendingProcess.length) pendingProcessAfterRows.push(steerRow);
          else rows.push(steerRow);
          continue;
        }
        if (msg.role === "user" && isDetachedProjectionMessage(msg)) {
          flushProcess();
          rows.push(renderUserProjection(msg, index, {
            tracePersistent: openExecutionTraceUserIndex >= 0,
          }));
          continue;
        }
        if (msg.role === "user") {
          closeExecutionTrace();
          currentUserIndex = index;
          rows.push(renderUserProjection(msg, index));
          if (index === activeUserIndex) {
            if (executionTraceTurns.has(index)) {
              openActiveExecutionTrace(index);
            } else {
              insertActiveRunAnchor();
            }
          } else {
            const elapsed = completedTurnStatuses.get(index);
            if (elapsed && executionTraceTurns.has(index)) {
              openCompletedExecutionTrace(index, elapsed);
            } else {
              rows.push(renderCompletedRunHeader(elapsed));
            }
          }
          continue;
        }
        if (msg.role === "tool-call" || msg.role === "tool-result") {
          if (isInternalGoalTool(msg)) continue;
          if (msg.role === "tool-result" && claimedToolResultIndexes.has(index)) continue;
          pendingProcess.push({ msg, index });
        }
      }
      closeExecutionTrace({
        activeStage: hasActiveRun && currentUserIndex === activeUserIndex,
      });
      if (hasActiveRun && !activeRunAnchorInserted) insertActiveRunAnchor();
      insertBranchMarker();
      queuedTailMessages.forEach(({ msg, index }) => {
        rows.push(renderUserProjection(msg, index));
      });
      return rows.filter(Boolean).join("");
    }

    return Object.freeze({
      bindInteractions,
      formatMessageTime,
      hasUsageStats,
      isInternalMessage,
      isOperationalToolNotice,
      isToolPlanningPlaceholder,
      normalizeResponseUsage,
      projectMessages,
      renderAssistantResponseInfo,
      renderBackgroundReplyReference,
      renderCompletedRunStatus,
      renderCopyButton,
      renderCopyIconSvg,
      renderFinalAssistantProjection,
      reconcileToolProcessNodes,
      renderToolProcessProjection,
      renderUserInputSummaryProjection,
      renderUserProjection,
      resetIconCopyButton,
      showIconCopyFeedback,
    });
  }

  Code.ui.messages = Object.freeze({
    createLongTextDisplayController,
    createMessageScrollController,
    createMessagesFeature,
    hasUsageStats,
    isInternalMessage,
    isOperationalToolNotice,
    isToolPlanningPlaceholder,
    normalizeResponseUsage,
    reconcileToolProcessNodes,
  });
})(window);
