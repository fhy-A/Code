(function registerMessagesUi(global) {
  "use strict";

  const Code = global.Code;
  if (!Code?.ui) throw new Error("Code namespace must load before messages UI");

  const COPY_SVG = '<svg width="14" height="14" viewBox="0 0 1024 1024" fill="currentColor" xmlns="http://www.w3.org/2000/svg"><path d="M761.088 715.3152a38.7072 38.7072 0 0 1 0-77.4144 37.4272 37.4272 0 0 0 37.4272-37.4272V265.0112a37.4272 37.4272 0 0 0-37.4272-37.4272H425.6256a37.4272 37.4272 0 0 0-37.4272 37.4272 38.7072 38.7072 0 1 1-77.4144 0 115.0976 115.0976 0 0 1 114.8416-114.8416h335.4624a115.0976 115.0976 0 0 1 114.8416 114.8416v335.4624a115.0976 115.0976 0 0 1-114.8416 114.8416z"/><path d="M589.4656 883.0976H268.1856a121.1392 121.1392 0 0 1-121.2928-121.2928v-322.56a121.1392 121.1392 0 0 1 121.2928-121.344h321.28a121.1392 121.1392 0 0 1 121.2928 121.2928v322.56c1.28 67.1232-54.1696 121.344-121.2928 121.344zM268.1856 395.3152a43.52 43.52 0 0 0-43.8784 43.8784v322.56a43.52 43.52 0 0 0 43.8784 43.8784h321.28a43.52 43.52 0 0 0 43.8784-43.8784v-322.56a43.52 43.52 0 0 0-43.8784-43.8784z"/></svg>';
  const COPY_DONE = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>';

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
    const cacheRead = firstReportedToken(usage, [
      "cache",
      "prompt_cache_hit_tokens",
      "cache_read_tokens",
      "cache_read_input_tokens",
      "cached_input_tokens",
    ]) || tokenCount(
      usage.prompt_tokens_details?.cached_tokens
      ?? usage.input_tokens_details?.cached_tokens,
    );
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

  function createMessagesFeature(options = {}) {
    const escapeHtml = options.escapeHtml || ((value) => String(value ?? ""));
    const formatCompact = options.formatCompact || ((value) => String(value ?? 0));
    const renderMarkdown = options.renderMarkdown || ((value) => escapeHtml(value));
    const t = options.t || ((key) => key);
    const getMessageText = options.getMessageText || ((msg) => String(msg?.content || ""));
    const getBackgroundJob = options.getBackgroundJob || (() => null);
    const getMessages = options.getMessages || (() => []);
    const getSessionId = options.getSessionId || (() => "");
    const getSelectedModel = options.getSelectedModel || (() => "");
    const renderNetworkRecoveryStatus = options.renderNetworkRecoveryStatus || (() => "");
    const renderAssistantContent = options.renderAssistantContent || ((content) => renderMarkdown(content));
    const renderCompactSummary = options.renderCompactSummary || (() => "");
    const renderBranchFlow = options.renderBranchFlow || (() => "");
    const isEditSuggestionMessage = options.isEditSuggestionMessage || (() => false);
    const renderEditSuggestion = options.renderEditSuggestion || (() => "");

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

    function renderCopyButton(text) {
      if (!text || !text.trim()) return "";
      return `<button class="msg-copy-btn" type="button" title="${t("copy")}" aria-label="${t("copy")}" data-copy-text="${escapeHtml(text)}" onclick="copyMessageText(this)">${COPY_SVG}</button>`;
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

    function renderUserProjection(msg, index) {
      const text = Array.isArray(msg.content)
        ? (msg.content.find((item) => item.type === "text")?.text || "")
        : getMessageText(msg);
      const images = msg._images || [];
      const time = formatMessageTime(msg._time);
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
      const queuedStatusValue = String(msg.meta?.queuedDispatch?.status || "");
      const queuedStatus = queuedStatusValue === "pending"
        ? `<span class="queued-message-status pending"><span class="queued-message-dot"></span>${t("queuedMessagePending")}<button class="queued-message-cancel" type="button" data-queue-item-id="${escapeHtml(queueItemId)}" title="${escapeHtml(t("cancelQueuedMessage"))}" aria-label="${escapeHtml(t("cancelQueuedMessage"))}">×</button></span>`
        : queuedStatusValue === "running"
          ? `<span class="queued-message-status running"><span class="queued-message-dot"></span>${t("queuedMessageRunning")}</span>`
          : queuedStatusValue === "canceled"
            ? `<span class="queued-message-status canceled"><span class="queued-message-dot"></span>${t("queuedMessageCanceled")}</span>`
            : "";
      const dispatchStatus = queuedStatus || backgroundStatus;
      const imageArticles = images.map((image, imageIndex) => {
        const src = image.path
          ? `/api/file?path=${encodeURIComponent(image.path)}&raw=1`
          : `data:${image.mime || "image/png"};base64,${image.base64}`;
        const onLoad = image.path ? ` onload="const el=document.querySelector('.messages');if(el)el.scrollTop=el.scrollHeight"` : "";
        return `<article class="msg user msg-image" data-msg-index="${index}" data-img="${imageIndex}"${dispatchAttr}>
          <div class="bubble bubble-img">
            <img class="msg-img msg-img-clickable" src="${src}" alt="${escapeHtml(image.name || "image")}"${onLoad} onclick="showImageOverlay(this.src)" title="Click to enlarge">
          </div>
        </article>`;
      }).join("");
      if (!text && images.length === 0) return "";
      const textArticle = text
        ? `<article class="msg user" data-msg-index="${index}"${dispatchAttr}><div class="user-message-hover-area"><div class="bubble">${renderMarkdown(text)}</div><div class="msg-meta">${dispatchStatus}${time} ${renderCopyButton(text)}</div></div></article>`
        : "";
      const imageOnlyStatus = !text && dispatchStatus
        ? `<article class="msg user msg-dispatch-meta" data-msg-index="${index}"${dispatchAttr}><div class="msg-meta">${dispatchStatus}${time}</div></article>`
        : "";
      return textArticle + imageArticles + imageOnlyStatus;
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

    function renderThinkingProjection(items, serial) {
      const summaries = items
        .map((item) => ({
          ...item,
          text: String(item.text || "").replace(/\r\n?/g, "\n").trim(),
        }))
        .filter((item) => item.text || item.streaming);
      if (!summaries.length) return "";
      const streamingItem = summaries.find((item) => item.streaming);
      const hasVisibleSummary = summaries.some((item) => item.text);
      if (!hasVisibleSummary) return "";
      const streamAttrs = streamingItem
        ? ` data-msg-index="${streamingItem.index}" data-streaming-message="true" data-stream-session="${escapeHtml(getSessionId() || "")}" data-stream-kind="thinking"`
        : "";
      const MAX_SUMMARY_LEN = 500;
      return `
        <article class="msg assistant thinking-process${streamingItem ? " is-streaming" : ""}" data-thinking-block="${serial}"${streamAttrs}>
          <div class="thinking-summary-list">
            ${summaries.map((item) => {
              const text = item.text || "";
              const isLong = text.length > MAX_SUMMARY_LEN && !item.streaming;
              if (isLong) {
                const preview = text.slice(0, MAX_SUMMARY_LEN) + "…";
                return `<details class="thinking-summary-item thinking-summary-fold"><summary>${renderMarkdown(preview)}<span class="thinking-expand-hint">（点击展开全部 ${text.length} 字）</span></summary><div class="thinking-summary-full">${renderMarkdown(text)}</div></details>`;
              }
              return `<div class="thinking-summary-item${item.streaming ? " is-streaming" : ""}"${item.streaming ? ' data-stream-part="summary"' : ""}>${item.text ? renderMarkdown(text) : ""}</div>`;
            }).join("")}
          </div>
        </article>
      `;
    }

    function renderAssistantResponseInfo(msg) {
      const meta = msg.meta || {};
      const usage = meta._usage || msg._usage || null;
      const elapsed = msg._responseTime || meta._responseTime || "";
      if (!hasUsageStats(usage) && !elapsed) return "";
      return `<div class="response-info">${renderCompletedRunStatus(meta._model || msg._model || "", elapsed, usage)}</div>`;
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

    function renderFinalAssistantProjection(msg, index) {
      const model = msg._model || msg.meta?._model || getSelectedModel() || "Agent";
      const content = (getMessageText(msg) || "").trim();
      if (msg.streaming) {
        const hasVisibleContent = content && !isToolPlanningPlaceholder(content);
        const streamKind = msg._streamProjection === "answer" ? "answer" : "pending";
        const showContent = streamKind === "answer" && hasVisibleContent;
        const showModel = showContent;
        return `
          <article class="msg assistant is-streaming${streamKind === "pending" ? " is-pending" : ""}" data-msg-index="${index}" data-streaming-message="true" data-stream-session="${escapeHtml(getSessionId() || "")}" data-stream-kind="${streamKind}">
            <div class="role streaming-answer-role${showModel ? "" : " is-empty"}" data-stream-role>${escapeHtml(model)}</div>
            <div class="bubble streaming-answer-output${showContent ? "" : " is-empty"}" data-stream-part="answer">${showContent ? renderMarkdown(content) : ""}</div>
            ${renderNetworkRecoveryStatus(getSessionId())}
          </article>
        `;
      }
      if (!content || isToolPlanningPlaceholder(content)) return "";
      const responseInfo = renderAssistantResponseInfo(msg);
      const replyReference = renderBackgroundReplyReference(msg);
      const copyButton = renderCopyButton(content);
      const time = formatMessageTime(msg._time);
      return `
        <article class="msg assistant" data-msg-index="${index}">
          <div class="role">${escapeHtml(model)}</div>
          ${replyReference}
          ${renderAssistantContent(content)}
          <div class="msg-footer">${responseInfo}<span class="msg-footer-hover">${copyButton}${time ? `<span class="msg-time">${time}</span>` : ""}</span></div>
        </article>
      `;
    }

    function projectMessages(messages = [], projection = {}) {
      const hasActiveRun = Boolean(projection.hasActiveRun);
      const branchMarker = projection.branchMarker || null;
      const rows = [];
      const queuedTailMessages = [];
      let pendingThoughts = [];
      let thoughtSerial = 0;
      let activeUserIndex = -1;
      if (hasActiveRun) {
        for (let index = messages.length - 1; index >= 0; index -= 1) {
          const message = messages[index];
          if (message?.role === "user"
              && message.meta?.queuedDispatch?.status !== "pending"
              && !message.meta?.detachedFromMain
              && !isInternalMessage(message)) {
            activeUserIndex = index;
            break;
          }
        }
      }
      let activeRunAnchorInserted = false;
      const branchBoundary = branchMarker
        ? (branchMarker.messageCount > messages.length ? 0 : branchMarker.messageCount)
        : -1;
      let branchMarkerInserted = false;

      const insertActiveRunAnchor = () => {
        if (!hasActiveRun || activeRunAnchorInserted) return;
        rows.push('<div class="active-run-anchor msg" data-active-run-anchor></div>');
        activeRunAnchorInserted = true;
      };
      const flushThoughts = () => {
        if (!pendingThoughts.length) return false;
        thoughtSerial += 1;
        rows.push(renderThinkingProjection(pendingThoughts, thoughtSerial));
        pendingThoughts = [];
        return true;
      };
      const insertBranchMarker = () => {
        if (!branchMarker || branchMarkerInserted) return;
        flushThoughts();
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
          flushThoughts();
          rows.push(renderCompactSummary(msg, index));
          continue;
        }
        if (msg.meta?.kind === "user-input-summary") {
          flushThoughts();
          rows.push(renderUserInputSummaryProjection(msg, index));
          continue;
        }
        if (isInternalMessage(msg)) continue;
        if (msg.role === "assistant") {
          const streamingToolRound = msg.streaming && msg._streamProjection === "thinking";
          if (msg.meta?.toolCalls?.length || streamingToolRound) {
            const summary = (getMessageText(msg) || "").trim();
            if (streamingToolRound && (!summary || isToolPlanningPlaceholder(summary))) {
              pendingThoughts.push({ index, text: "", streaming: true });
            } else if (summary && !isToolPlanningPlaceholder(summary)) {
              pendingThoughts.push({ index, text: summary, streaming: streamingToolRound });
            }
            continue;
          }
          flushThoughts();
          rows.push(renderFinalAssistantProjection(msg, index));
          continue;
        }
        if (msg.role === "user") {
          flushThoughts();
          rows.push(renderUserProjection(msg, index));
          if (index === activeUserIndex) insertActiveRunAnchor();
          continue;
        }
        if (isEditSuggestionMessage(msg)) {
          flushThoughts();
          rows.push(renderEditSuggestion(msg, index));
        }
      }
      flushThoughts();
      if (hasActiveRun && !activeRunAnchorInserted) insertActiveRunAnchor();
      insertBranchMarker();
      queuedTailMessages.forEach(({ msg, index }) => {
        rows.push(renderUserProjection(msg, index));
      });
      return rows.filter(Boolean).join("");
    }

    return Object.freeze({
      copyMessageText,
      formatMessageTime,
      hasUsageStats,
      isInternalMessage,
      isToolPlanningPlaceholder,
      normalizeResponseUsage,
      projectMessages,
      renderAssistantResponseInfo,
      renderBackgroundReplyReference,
      renderCompletedRunStatus,
      renderCopyButton,
      renderCopyIconSvg,
      renderFinalAssistantProjection,
      renderThinkingProjection,
      renderUserInputSummaryProjection,
      renderUserProjection,
      resetIconCopyButton,
      showIconCopyFeedback,
    });
  }

  Code.ui.messages = Object.freeze({
    createMessagesFeature,
    hasUsageStats,
    isInternalMessage,
    isToolPlanningPlaceholder,
    normalizeResponseUsage,
  });
})(window);
