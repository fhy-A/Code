(function registerSettingsFeature(global) {
  "use strict";

  const Code = global.Code;
  if (!Code?.features) throw new Error("Code namespace must load before settings feature");
  const platform = Code.core?.platform;
  if (!platform) throw new Error("Platform core must load before settings feature");

  const { WORKBAR_URL } = platform;

  function buildPlatformLoginUrl(location = global.location) {
    const callbackUrl = new global.URL("/", location.href).href;
    return `${WORKBAR_URL}/code/connect?callback=${encodeURIComponent(callbackUrl)}`;
  }

  const UPDATE_NOTICE_STORAGE_KEYS = Object.freeze({
    settings: "code-update-seen-settings",
    page: "code-update-seen-page",
  });
  const FOLLOW_UP_BEHAVIOR_STORAGE_KEY = "code-follow-up-behavior";
  const FOLLOW_UP_BEHAVIORS = Object.freeze(["steer", "queue"]);

  function normalizeFollowUpBehavior(value) {
    return value === "queue" ? "queue" : "steer";
  }

  function loadFollowUpBehavior(storage = global.localStorage) {
    return normalizeFollowUpBehavior(storage?.getItem(FOLLOW_UP_BEHAVIOR_STORAGE_KEY));
  }

  function saveFollowUpBehavior(value, storage = global.localStorage) {
    const normalized = normalizeFollowUpBehavior(value);
    storage?.setItem(FOLLOW_UP_BEHAVIOR_STORAGE_KEY, normalized);
    return normalized;
  }

  function oppositeFollowUpBehavior(value) {
    return normalizeFollowUpBehavior(value) === "steer" ? "queue" : "steer";
  }

  function loadKeyConfig(storage = global.localStorage) {
    return platform.loadKeyConfig(storage);
  }

  function createSettingsFeature(options = {}) {
    const state = options.state || {};
    const els = options.elements || {};
    const t = options.t || ((key) => key);
    const escapeHtml = options.escapeHtml || ((value) => String(value ?? ""));
    const apiJson = options.apiJson;
    const showToast = options.showToast || (() => {});
    const applyI18n = options.applyI18n || (() => {});
    const setLang = options.setLang || (() => {});
    const refreshModels = options.refreshModels || (async () => {});
    const saveLocalSettings = options.saveLocalSettings || (() => {});
    const updateContextBudgetStatus = options.updateContextBudgetStatus || (() => {});
    const saveSystemPrompt = options.saveSystemPrompt || (() => {});
    const renderMemoryPanel = options.renderMemoryPanel || (() => {});
    const renderSkillsInSettings = options.renderSkillsInSettings || (() => {});
    const refreshSkillsMemorySettingsLanguage = options.refreshSkillsMemorySettingsLanguage || (() => {});
    const getDefaultSystemPrompt = options.getDefaultSystemPrompt || (() => "");
    const onPlatformLogout = options.onPlatformLogout || (() => {});
    const onKeyConfigChanged = options.onKeyConfigChanged || (() => {});
    const trashIcon = options.trashIcon || (() => "");
    const documentRef = options.document || global.document;
    const storage = options.storage || global.localStorage;
    const fetchFn = options.fetch || global.fetch?.bind(global);
    const navigatorRef = options.navigator || global.navigator;

    if (typeof apiJson !== "function") throw new Error("settings feature requires apiJson");

    const byId = (id) => documentRef.getElementById(id);
    let bound = false;

    function saveKeyConfig(config) {
      const saved = platform.saveKeyConfig(config, storage);
      onKeyConfigChanged(saved);
      return saved;
    }

    function parseKeyLines(raw, notifyDuplicates = true) {
      if (!raw) return [];
      const config = loadKeyConfig(storage);
      const { entries, duplicates } = platform.parseKeyText(raw, config);
      if (notifyDuplicates && duplicates.length) showToast(t("ignoredDuplicateKeys", { count: duplicates.length }), "warning");
      return entries.length ? entries : [{ name: "", key: "", enabled: true, source: "manual" }];
    }

    function serializeKeys(entries) {
      return platform.serializeKeyEntries(entries);
    }

    function eyeIcon() {
      return '<svg width="14" height="14" viewBox="0 0 1024 1024" fill="currentColor"><path d="M942.2 486.2C847.4 286.5 704.1 186 512 186c-192.2 0-335.4 100.5-430.2 300.3-7.7 16.2-7.7 35.2 0 51.5C176.6 737.5 319.9 838 512 838c192.2 0 335.4-100.5 430.2-300.3 7.7-16.2 7.7-35 0-51.5zM512 766c-161.3 0-279.4-81.8-362.7-254C232.6 339.8 350.7 258 512 258c161.3 0 279.4 81.8 362.7 254C791.5 684.2 673.4 766 512 766z"/><path d="M508 336c-97.2 0-176 78.8-176 176s78.8 176 176 176 176-78.8 176-176-78.8-176-176-176zm0 288c-61.9 0-112-50.1-112-112s50.1-112 112-112 112 50.1 112 112-50.1 112-112 112z"/></svg>';
    }

    function eyeOffIcon() {
      return '<svg width="14" height="14" viewBox="0 0 1024 1024" fill="currentColor"><path d="M913.86 396.86c11.76-14.71 9.36-36.18-5.33-47.94-14.72-11.77-36.14-9.34-47.97 5.33-1.23 1.57-128.74 157.74-348.56 157.74-218.58 0-347.36-156.22-348.56-157.74-11.79-14.67-33.21-17.12-47.97-5.33-14.69 11.76-17.09 33.23-5.33 47.94 2.11 2.64 21.66 26.32 56.68 55.72l-59.81 72.89 52.73 43.27 61.98-75.53c25.71 16.71 55.66 33.14 89.71 47.2l-34.34 95.02 64.16 23.18 34.82-96.36c31.36 8.41 65.38 14.16 101.82 16.5v103.8h68.22V578.72c37.15-2.39 71.75-8.36 103.61-17.04l35.19 96.27 64.06-23.44-34.65-94.79c32.3-13.47 60.72-29.1 85.46-45l61.61 76.04 53-42.95-59.44-73.37c36.44-30.26 56.71-54.82 58.87-57.58z"/></svg>';
    }

    function keyNormalActions(entry, index) {
      return `<div class="key-actions">
        <button class="key-act-btn key-eye" type="button" title="${t("toggleVisibility")}" data-i18n-title="toggleVisibility" data-idx="${index}">${eyeIcon()}</button>
        <label class="toggle-switch key-enable" title="${entry.enabled !== false ? t("enabledStatus") : t("disabledStatus")}" data-key-enabled="${entry.enabled !== false}">
          <input type="checkbox" ${entry.enabled !== false ? "checked" : ""} data-idx="${index}" />
          <span class="toggle-track"><span class="toggle-thumb"></span></span>
        </label>
        <button class="key-act-btn key-trash" type="button" title="${t("delete")}" data-i18n-title="delete" data-idx="${index}">${trashIcon()}</button>
      </div>`;
    }

    function keyConfirmActions(index) {
      return `<div class="key-actions">
        <button class="key-act-btn key-confirm" type="button" title="${t("save")}" data-i18n-title="save" data-idx="${index}"><svg width="14" height="14" viewBox="0 0 14 14"><path d="M3 7l2.5 2.5L11 4" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg></button>
        <button class="key-act-btn key-cancel" type="button" title="${t("cancel")}" data-i18n-title="cancel" data-idx="${index}"><svg width="14" height="14" viewBox="0 0 14 14"><path d="M3 3l8 8M11 3L3 11" stroke="currentColor" stroke-width="1.5" fill="none" stroke-linecap="round"/></svg></button>
      </div>`;
    }

    function renderKeyEditor(raw, newRow = false) {
      const entries = parseKeyLines(raw);
      if (!entries.length) entries.push({ name: "", key: "", enabled: true });
      return entries.map((entry, index) => {
        const isNew = newRow && index === entries.length - 1;
        return `<div class="key-row ${entry.enabled === false && !isNew ? "disabled" : ""}" data-idx="${index}" data-source="${entry.source === "platform" ? "platform" : "manual"}" data-platform-token-id="${escapeHtml(entry.platformTokenId || "")}">
          <span class="key-drag-handle" title="${t("dragSort")}" data-i18n-title="dragSort" draggable="true">⠿</span>
          <div class="key-main">
            <input class="key-name-input" placeholder="${t("keyNamePlaceholder")}" data-i18n="keyNamePlaceholder" value="${escapeHtml(entry.name)}" data-idx="${index}" />
            <div class="key-value-wrap"><input class="key-value-input" type="password" value="${escapeHtml(entry.key)}" data-idx="${index}" /></div>
          </div>
          ${isNew ? keyConfirmActions(index) : keyNormalActions(entry, index)}
        </div>`;
      }).join("");
    }

    function collectKeyEntries(container) {
      const entries = [];
      container?.querySelectorAll(".key-row").forEach((row) => {
        const name = row.querySelector(".key-name-input")?.value || "";
        const key = row.querySelector(".key-value-input")?.value || "";
        const enabled = row.querySelector(".key-enable input")?.checked !== false;
        const source = row.dataset.source === "platform" ? "platform" : "manual";
        const platformTokenId = platform.normalizePlatformTokenId(row.dataset.platformTokenId);
        if (key.trim()) {
          const entry = { name: name.trim(), key: key.trim(), enabled, source };
          if (platformTokenId) entry.platformTokenId = platformTokenId;
          entries.push(entry);
        }
      });
      return entries;
    }

    function persistKeyEntries(container, saveSettings = true) {
      const entries = collectKeyEntries(container);
      els.apiKey.value = serializeKeys(entries);
      saveKeyConfig(entries);
      if (saveSettings) saveLocalSettings();
      return entries;
    }

    function syncKeyEditorFromStorage() {
      const config = loadKeyConfig(storage);
      els.apiKey.value = serializeKeys(config);
      const keyList = byId("settingsKeyList");
      if (!keyList) return config;
      keyList.innerHTML = renderKeyEditor(els.apiKey.value);
      bindKeyEditorEvents(keyList);
      return config;
    }

    function showInlineKeyDeleteConfirm(row, name, onConfirm) {
      documentRef.querySelector(".key-delete-confirm")?.remove();
      const confirm = documentRef.createElement("div");
      confirm.className = "key-delete-confirm";
      const shortName = name.slice(0, 20);
      confirm.innerHTML = `<span data-settings-delete-name="${escapeHtml(shortName)}">${t("deleteConfirmMsg", { name: shortName })}</span>
        <button class="key-confirm-yes" type="button" data-i18n="confirmDelete">${t("confirmDelete")}</button>
        <button class="key-confirm-no" type="button" data-i18n="cancel">${t("cancel")}</button>`;
      row.after(confirm);
      confirm.querySelector(".key-confirm-yes").addEventListener("click", () => {
        confirm.remove();
        onConfirm();
      });
      confirm.querySelector(".key-confirm-no").addEventListener("click", () => confirm.remove());
    }

    function bindKeyEditorEvents(container) {
      if (!container) return;
      let dragSource = null;
      container.querySelectorAll(".key-drag-handle").forEach((handle) => {
        handle.addEventListener("dragstart", (event) => {
          dragSource = handle.closest(".key-row");
          dragSource.classList.add("dragging");
          event.dataTransfer.effectAllowed = "move";
        });
        handle.addEventListener("dragend", () => {
          dragSource?.classList.remove("dragging");
          dragSource = null;
          container.querySelectorAll(".key-row").forEach((row) => row.classList.remove("drag-over"));
        });
      });
      container.querySelectorAll(".key-row").forEach((row) => {
        row.addEventListener("dragover", (event) => {
          event.preventDefault();
          event.dataTransfer.dropEffect = "move";
          row.classList.add("drag-over");
        });
        row.addEventListener("dragleave", () => row.classList.remove("drag-over"));
        row.addEventListener("drop", (event) => {
          event.preventDefault();
          row.classList.remove("drag-over");
          if (!dragSource || dragSource === row) return;
          const rows = [...container.querySelectorAll(".key-row")];
          if (rows.indexOf(dragSource) < rows.indexOf(row)) row.after(dragSource);
          else row.before(dragSource);
          dragSource.classList.remove("dragging");
          dragSource = null;
          persistKeyEntries(container);
        });
      });
      container.querySelectorAll(".key-name-input, .key-value-input").forEach((input) => {
        input.addEventListener("change", () => persistKeyEntries(container));
      });
      container.querySelectorAll(".key-eye").forEach((button) => {
        button.addEventListener("click", () => {
          const input = button.closest(".key-row").querySelector(".key-value-input");
          const showing = input.type === "text";
          input.type = showing ? "password" : "text";
          button.innerHTML = showing ? eyeIcon() : eyeOffIcon();
        });
      });
      container.querySelectorAll(".key-enable input").forEach((checkbox) => {
        checkbox.addEventListener("change", () => {
          const row = checkbox.closest(".key-row");
          row?.classList.toggle("disabled", !checkbox.checked);
          if (checkbox.closest(".key-enable")) checkbox.closest(".key-enable").title = checkbox.checked ? t("enabledStatus") : t("disabledStatus");
          persistKeyEntries(container);
        });
      });
      container.querySelectorAll(".key-confirm").forEach((button) => {
        button.addEventListener("click", () => {
          persistKeyEntries(container);
          container.innerHTML = renderKeyEditor(els.apiKey.value);
          bindKeyEditorEvents(container);
        });
      });
      container.querySelectorAll(".key-cancel").forEach((button) => {
        button.addEventListener("click", () => {
          button.closest(".key-row").remove();
          persistKeyEntries(container, false);
        });
      });
      container.querySelectorAll(".key-trash").forEach((button) => {
        button.addEventListener("click", () => {
          const row = button.closest(".key-row");
          const name = row.querySelector(".key-name-input")?.value || "未命名";
          showInlineKeyDeleteConfirm(row, name, () => {
            const key = row.querySelector(".key-value-input")?.value?.trim() || "";
            const storedEntry = loadKeyConfig(storage).find((entry) => entry.key === key);
            const platformTokenId = platform.normalizePlatformTokenId(
              row.dataset.platformTokenId || storedEntry?.platformTokenId,
            );
            const auth = getPlatformAuth();
            if (auth?.userId && platformTokenId) {
              platform.excludePlatformToken(auth.userId, platformTokenId, storage);
            }
            row.remove();
            persistKeyEntries(container);
          });
        });
      });

      const detail = byId("settingsDetail");
      if (!detail || detail._keyDelegationBound) return;
      detail._keyDelegationBound = true;
      detail.addEventListener("click", (event) => {
        if (event.target.id !== "settingsKeyAddRow" && !event.target.closest("#settingsKeyAddRow")) return;
        const area = byId("settingsKeyAddArea");
        area.innerHTML = `<textarea id="keyBulkInput" class="key-bulk-input" placeholder="${t("keyBulkPlaceholder")}" data-i18n="keyBulkPlaceholder" rows="5"></textarea>
          <div class="key-bulk-actions"><button id="keyBulkSave" class="mini-btn" type="button" data-i18n="save">${t("save")}</button><button id="keyBulkCancel" class="mini-btn" type="button" data-i18n="cancel">${t("cancel")}</button></div>`;
        const bulkInput = byId("keyBulkInput");
        const bulkSave = byId("keyBulkSave");
        bulkInput.addEventListener("input", () => bulkSave.classList.toggle("primary-btn", bulkInput.value.trim().length > 0));
        byId("keyBulkCancel").addEventListener("click", () => {
          area.innerHTML = `<button id="settingsKeyAddRow" class="key-add-btn" type="button" data-i18n="addKey">${t("addKey")}</button>`;
        });
        bulkSave.addEventListener("click", () => {
          const lines = bulkInput.value.split("\n").map((line) => line.trim()).filter(Boolean);
          if (!lines.length) return;
          const additions = platform.parseKeyText(lines.join("\n")).entries.map((entry) => ({ ...entry, source: "manual" }));
          const keyList = byId("settingsKeyList");
          const merged = [...collectKeyEntries(keyList), ...additions];
          els.apiKey.value = serializeKeys(merged);
          saveKeyConfig(merged);
          saveLocalSettings();
          keyList.innerHTML = renderKeyEditor(els.apiKey.value);
          bindKeyEditorEvents(keyList);
          area.innerHTML = `<button id="settingsKeyAddRow" class="key-add-btn" type="button" data-i18n="addKey">${t("addKey")}</button>`;
        });
      });
    }

    function getPlatformUrl() {
      return WORKBAR_URL;
    }

    function getPlatformAuth() {
      try {
        return JSON.parse(storage?.getItem("code-platform-auth") || "null");
      } catch {
        return null;
      }
    }

    function savePlatformAuth(data) {
      storage?.setItem("code-platform-auth", JSON.stringify(data));
    }

    function clearPlatformAuth() {
      storage?.removeItem("code-platform-auth");
      storage?.removeItem("agent-lite-platform-auth");
    }

    function mergePlatformAccount(auth, account) {
      const merged = { ...auth };
      ["username", "displayName", "email", "group", "quota", "usedQuota", "requestCount", "quotaDisplay"].forEach((key) => {
        if (account?.[key] !== undefined) merged[key] = account[key];
      });
      merged.userId = String(account?.userId || auth?.userId || "");
      return merged;
    }

    function openPlatformLogin() {
      global.open(buildPlatformLoginUrl(), "_blank");
    }

    function showPlatformAuthGate(reason = "missing") {
      byId("platformAuthGate")?.remove();
      const validating = reason === "validating";
      const unavailable = reason === "unavailable";
      const expired = reason === "expired";
      const description = expired
        ? t("workbarSessionExpired")
        : unavailable
          ? t("workbarUnavailable")
          : `<span>${t("connectWorkbarDescPrimary")}</span><span>${t("connectWorkbarDescSecondary")}</span>`;
      const overlay = documentRef.createElement("div");
      overlay.id = "platformAuthGate";
      overlay.className = "platform-auth-gate";
      overlay.innerHTML = `<section class="platform-auth-card" role="dialog" aria-modal="true" aria-labelledby="platformAuthTitle">
        <div class="platform-auth-brand"><span class="platform-auth-mark" aria-hidden="true">W</span><span>workbar</span></div>
        <h1 id="platformAuthTitle">${t("connectWorkbarTitle")}</h1>
        <p class="${expired || unavailable ? "" : "platform-auth-description"}">${description}</p>
        ${validating ? `<div class="platform-auth-progress"><span class="platform-auth-spinner" aria-hidden="true"></span>${t("validatingWorkbar")}</div>` : `<button id="platformAuthAction" class="platform-auth-action" type="button">${unavailable ? t("retryValidation") : t("connectWorkbarAction")}</button>`}
        <small>${t("workbarAuthHint")}</small>
      </section>`;
      documentRef.body.appendChild(overlay);
      byId("platformAuthAction")?.addEventListener("click", () => {
        if (unavailable) global.location.reload();
        else openPlatformLogin();
      });
    }

    function hidePlatformAuthGate() {
      byId("platformAuthGate")?.remove();
    }

    async function initializePlatformAuth() {
      const callbackHandled = await checkCodeCallback();
      const auth = getPlatformAuth();
      if (!auth?.token || !auth?.userId) {
        clearPlatformAuth();
        showPlatformAuthGate("missing");
        return false;
      }
      if (!callbackHandled) {
        hidePlatformAuthGate();
        return true;
      }
      showPlatformAuthGate("validating");
      try {
        const response = await fetchFn("/api/code/auth/validate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token: auth.token, userId: auth.userId }),
        });
        if (response.status === 401 || response.status === 403) {
          clearPlatformAuth();
          showPlatformAuthGate("expired");
          return false;
        }
        if (!response.ok) {
          showPlatformAuthGate("unavailable");
          return false;
        }
        const data = await response.json();
        if (!data.valid) {
          clearPlatformAuth();
          showPlatformAuthGate("expired");
          return false;
        }
        savePlatformAuth(mergePlatformAccount(auth, data.account));
        hidePlatformAuthGate();
        return true;
      } catch {
        showPlatformAuthGate("unavailable");
        return false;
      }
    }

    const themeEngine = Code.core?.theme;
    const DEFAULT_LIGHT = "codex";
    const DEFAULT_DARK = "codex";

    function getThemePrefs() {
      return {
        mode: storage?.getItem("code-theme-mode") || "light",
        lightVariant: storage?.getItem("code-theme-light") || DEFAULT_LIGHT,
        darkVariant: storage?.getItem("code-theme-dark") || DEFAULT_DARK,
      };
    }

    function saveThemePrefs(mode, lightVariant, darkVariant) {
      storage?.setItem("code-theme-mode", mode);
      storage?.setItem("code-theme", mode);  // backward compat
      if (lightVariant !== undefined) storage?.setItem("code-theme-light", lightVariant);
      if (darkVariant !== undefined) storage?.setItem("code-theme-dark", darkVariant);
    }

    function applyTheme(mode, lightVariant, darkVariant) {
      const prefs = getThemePrefs();
      const m = mode || prefs.mode;
      const lv = lightVariant !== undefined ? lightVariant : prefs.lightVariant;
      const dv = darkVariant !== undefined ? darkVariant : prefs.darkVariant;
      saveThemePrefs(m, lv, dv);
      if (themeEngine) {
        themeEngine.activateTheme(m, lv, dv);
      } else {
        // fallback: old behaviour
        const systemDark = global.matchMedia?.("(prefers-color-scheme: dark)")?.matches;
        documentRef.body.classList.toggle("theme-dark", m === "dark" || (m === "system" && systemDark));
      }
      updateThemeButtons();
    }

    function updateThemeButtons() {
      const prefs = getThemePrefs();
      // sidebar toggle buttons
      documentRef.querySelectorAll(".theme-opt[data-theme]").forEach((btn) => {
        btn.classList.toggle("active", btn.dataset.theme === prefs.mode);
      });
    }

    function showSettings(open = true) {
      els.settingsModal?.classList.toggle("hidden", !open);
    }

    function closeDropdown() {
      byId("settingsDropdown")?.classList.add("hidden");
    }

    function renderedModelCount() {
      return (String(els.modelListBox?.innerHTML || "").match(/class="model-name-tag"/g) || []).length;
    }

    function updateSettingsModelSnapshot() {
      const list = byId("settingsModelList");
      const count = renderedModelCount();
      const canonicalHtml = String(els.modelListBox?.innerHTML || "");
      const hasCatalogState = canonicalHtml.includes('class="model-list-state');
      const countBadge = byId("settingsModelCount");
      if (countBadge) countBadge.textContent = String(count);
      if (!list) return count;
      if (count > 0 || hasCatalogState) {
        list.innerHTML = canonicalHtml;
      } else {
        const hasEnabledKey = loadKeyConfig(storage).some((entry) => entry.enabled !== false && String(entry.key || "").trim());
        const emptyKey = hasEnabledKey ? "noModelsFound" : "enterApiKey";
        list.innerHTML = `<div class="model-list-empty" data-i18n="${emptyKey}">${t(emptyKey)}</div>`;
      }
      return count;
    }

    async function refreshSettingsModelList() {
      const button = byId("settingsRefreshModels");
      if (button) {
        button.disabled = true;
        button.classList.add("is-loading");
        button.title = t("detectingModels");
      }
      try {
        await refreshModels();
      } finally {
        updateSettingsModelSnapshot();
        if (button) {
          button.disabled = false;
          button.classList.remove("is-loading");
          button.title = t("detectAvailableModels");
        }
      }
    }

    function renderModelsPanel(container) {
      const keyConfig = loadKeyConfig(storage);
      els.apiKey.value = serializeKeys(keyConfig);
      const modelCount = renderedModelCount();
      const canonicalModels = String(els.modelListBox?.innerHTML || "");
      const initialModels = modelCount > 0 || canonicalModels.includes('class="model-list-state')
        ? canonicalModels
        : (() => {
          const emptyKey = keyConfig.some((entry) => entry.enabled !== false && String(entry.key || "").trim()) ? "noModelsFound" : "enterApiKey";
          return `<div class="model-list-empty" data-i18n="${emptyKey}">${t(emptyKey)}</div>`;
        })();
      container.innerHTML = `<h3 style="margin:0 0 14px" data-i18n="models">${t("models")}</h3>
        <div class="field"><div class="key-field-heading"><span data-i18n="apiKeys">${t("apiKeys")}</span><button id="settingsConnectPlatform" class="key-workbar-btn" type="button" title="${t("getFromWorkbar")}" data-i18n-title="getFromWorkbar"><svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true"><path d="M7 1.5v7m0 0L4.5 6M7 8.5L9.5 6M2 10.5v1.25c0 .41.34.75.75.75h8.5c.41 0 .75-.34.75-.75V10.5" fill="none" stroke="currentColor" stroke-width="1.35" stroke-linecap="round" stroke-linejoin="round"/></svg><span data-i18n="getFromWorkbar">${t("getFromWorkbar")}</span></button></div>
          <div class="key-list" id="settingsKeyList">${renderKeyEditor(els.apiKey.value)}</div>
          <div id="settingsKeyAddArea"><button id="settingsKeyAddRow" class="key-add-btn" type="button" data-i18n="addKey">${t("addKey")}</button></div>
        </div>
        <div class="model-list-header"><div class="model-list-title"><span data-i18n="availableModels">${t("availableModels")}</span><span id="settingsModelCount" class="model-count-badge">${modelCount}</span></div><button id="settingsRefreshModels" class="model-refresh-btn" type="button" title="${t("detectAvailableModels")}" data-i18n-title="detectAvailableModels" aria-label="${t("detectAvailableModels")}"><svg width="15" height="15" viewBox="0 0 14 14" aria-hidden="true"><path d="M1 7a6 6 0 0111.1-3.5M13 7a6 6 0 01-11.1 3.5" stroke="currentColor" stroke-width="1.4" fill="none" stroke-linecap="round"/><path d="M12 1v3H9M2 13v-3h3" stroke="currentColor" stroke-width="1.4" fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg></button></div>
        <div id="settingsModelList" class="model-list-display">${initialModels}</div>
        <div class="context-settings-primary">
          <label class="field"><span data-i18n="temperature">${t("temperature")}</span><input id="settingsTemperature" type="number" min="0" max="2" step="0.1" value="${els.temperature.value}" /></label>
          <label class="field"><span data-i18n="maxTokens">${t("maxTokens")}</span><select id="settingsMaxTokens">${els.maxTokens.innerHTML}</select></label>
        </div>
        <label class="field context-budget-field"><span data-i18n="contextBudget">${t("contextBudget")}</span><input id="settingsContextBudget" type="text" inputmode="text" autocomplete="off" placeholder="${escapeHtml(t("contextBudgetPlaceholder"))}" value="${escapeHtml(els.contextBudget.value)}" /><small id="settingsContextBudgetStatus" class="field-hint" hidden></small></label>`;

      byId("settingsConnectPlatform")?.addEventListener("click", () => {
        if (!getPlatformAuth()) {
          showToast(t("loginFirst"), "warning");
          return;
        }
        syncKeysFromPlatform();
      });
      byId("settingsRefreshModels")?.addEventListener("click", refreshSettingsModelList);
      byId("settingsTemperature")?.addEventListener("change", (event) => {
        els.temperature.value = event.currentTarget.value;
        saveLocalSettings();
      });
      const settingsMaxTokens = byId("settingsMaxTokens");
      if (settingsMaxTokens) settingsMaxTokens.value = els.maxTokens.value;
      settingsMaxTokens?.addEventListener("change", (event) => {
        els.maxTokens.value = event.currentTarget.value;
        saveLocalSettings();
        event.currentTarget.value = els.maxTokens.value;
      });
      const settingsContextBudget = byId("settingsContextBudget");
      if (settingsContextBudget) settingsContextBudget.value = els.contextBudget.value;
      byId("settingsContextBudget")?.addEventListener("change", (event) => {
        els.contextBudget.value = event.currentTarget.value;
        saveLocalSettings({ contextBudgetReportAdjustment: true });
        event.currentTarget.value = els.contextBudget.value;
      });
      updateContextBudgetStatus();

      const keyList = byId("settingsKeyList");
      bindKeyEditorEvents(keyList);
      const keyToggle = byId("settingsKeyToggle");
      let keyVisible = false;
      keyToggle?.addEventListener("click", () => {
        keyVisible = !keyVisible;
        keyList.querySelectorAll(".key-value-input").forEach((input) => { input.type = keyVisible ? "text" : "password"; });
        keyToggle.textContent = keyVisible ? t("hide") : t("show");
      });
      keyList?.addEventListener("dblclick", () => {
        keyVisible = true;
        keyList.querySelectorAll(".key-value-input").forEach((input) => { input.type = "text"; });
        if (keyToggle) keyToggle.textContent = t("hide");
      });
    }

    function renderSystemPanel(container) {
      container.innerHTML = `<h3 style="margin:0 0 14px" data-i18n="system">${t("system")}</h3>
        <textarea id="settingsSystemText" class="system-prompt-text" style="height:400px" spellcheck="false">${escapeHtml(els.systemPromptText.value)}</textarea>
        <div class="panel-actions" style="margin-top:8px"><span data-i18n="systemPromptHint">${t("systemPromptHint")}</span><button id="settingsResetSystem" class="mini-btn" type="button" data-i18n="resetDefault">${t("resetDefault")}</button></div>`;
      byId("settingsSystemText").addEventListener("change", (event) => {
        els.systemPromptText.value = event.currentTarget.value;
        saveSystemPrompt();
      });
      byId("settingsResetSystem").addEventListener("click", () => {
        const value = getDefaultSystemPrompt();
        els.systemPromptText.value = value;
        byId("settingsSystemText").value = value;
        saveSystemPrompt();
      });
    }

    function renderEditorPanel(container) {
      const current = loadFollowUpBehavior(storage);
      const options = FOLLOW_UP_BEHAVIORS.map((behavior) => (
        `<button class="follow-up-behavior-option${behavior === current ? " active" : ""}" type="button" role="radio" aria-checked="${behavior === current}" data-follow-up-behavior="${behavior}">${t(behavior === "steer" ? "followUpSteer" : "followUpQueue")}</button>`
      )).join("");
      container.innerHTML = `<h3 class="settings-section-title" data-i18n="editorSettings">${t("editorSettings")}</h3>
        <div class="settings-lite-page editor-settings-panel">
          <section class="settings-lite-card follow-up-behavior-card">
            <div class="follow-up-behavior-copy">
              <strong data-i18n="followUpBehavior">${t("followUpBehavior")}</strong>
              <span data-i18n="followUpBehaviorHint">${t("followUpBehaviorHint")}</span>
            </div>
            <div class="follow-up-behavior-options" role="radiogroup" aria-label="${t("followUpBehavior")}">${options}</div>
          </section>
        </div>`;
      container.querySelectorAll("[data-follow-up-behavior]").forEach((button) => {
        button.addEventListener("click", () => {
          saveFollowUpBehavior(button.dataset.followUpBehavior, storage);
          renderEditorPanel(container);
        });
      });
    }

    function updateLanguageControls() {
      const current = state.lang || "zh";
      documentRef.querySelectorAll("[data-settings-lang]").forEach((button) => {
        const active = button.dataset.settingsLang === current;
        button.classList.toggle("active", active);
        button.setAttribute("aria-pressed", String(active));
      });
    }

    function renderThemePanel(container) {
      if (!themeEngine) { container.innerHTML = "<p>Theme engine not loaded</p>"; return; }
      const prefs = getThemePrefs();
      const systemDark = global.matchMedia?.("(prefers-color-scheme: dark)")?.matches === true;
      const resolvedMode = prefs.mode === "system" ? (systemDark ? "dark" : "light") : prefs.mode;
      const renderSwatch = (surface, ink) =>
        `<span class="tp-swatch" style="background:${surface};color:${ink}" title="${surface}">Aa</span>`;

      const renderVariantRow = (mode, id, base, isSelected) => {
        const name = id === "vscode-plus" ? "vscode+" : id;
        return `<button class="tp-row ${isSelected ? "tp-row--sel" : ""}" type="button" role="radio" aria-checked="${isSelected}" data-tp-variant="${id}" data-tp-variant-mode="${mode}">
          ${renderSwatch(base.surface, base.ink)}
          <span class="tp-name">${name}</span>
          <span class="tp-check" aria-hidden="true">✓</span>
        </button>`;
      };

      const renderVariantGroup = (mode) => {
        const variants = mode === "dark" ? themeEngine.DARK_THEMES : themeEngine.LIGHT_THEMES;
        const selectedVariant = mode === "dark" ? prefs.darkVariant : prefs.lightVariant;
        const options = Object.entries(variants)
          .map(([id, base]) => renderVariantRow(mode, id, base, id === selectedVariant)).join("");
        return `<section class="tp-variant-group" data-tp-variant-group="${mode}">
          <div class="tp-picker-head">
            <div class="tp-picker-title"><strong>${t("themeSchemes")}</strong><span>${t(mode)}</span></div>
            <span class="tp-picker-count">${t("themeSchemeCount", { count: Object.keys(variants).length })}</span>
          </div>
          <div class="tp-variants" role="radiogroup" aria-label="${t(mode)}${t("themeSchemes")}">${options}</div>
        </section>`;
      };

      const modeOptions = [
        ["light", "light"],
        ["dark", "dark"],
        ["system", "followSystem"],
      ].map(([mode, label]) => `<button class="tp-mode-btn ${prefs.mode === mode ? "active" : ""}" type="button" role="radio" aria-checked="${prefs.mode === mode}" data-tp-mode="${mode}">${t(label)}</button>`).join("");
      const visibleModes = prefs.mode === "system" ? ["light", "dark"] : [resolvedMode];
      const variantGroups = visibleModes.map(renderVariantGroup).join("");

      container.innerHTML = `<h3 style="margin:0 0 14px">${t("theme")}</h3>
        <div class="tp-picker">
          <div class="tp-picker-label">${t("themeMode")}</div>
          <div class="tp-mode-switch" role="radiogroup" aria-label="${t("themeMode")}">${modeOptions}</div>
          ${variantGroups}
        </div>`;

      /* event listeners */
      container.querySelectorAll("[data-tp-mode]").forEach((button) => {
        button.addEventListener("click", () => {
          applyTheme(button.dataset.tpMode);
          renderThemePanel(container);
        });
      });
      container.querySelectorAll("[data-tp-variant]").forEach((button) => {
        button.addEventListener("click", () => {
          const variant = button.dataset.tpVariant;
          const variantMode = button.dataset.tpVariantMode;
          applyTheme(prefs.mode, variantMode === "light" ? variant : undefined, variantMode === "dark" ? variant : undefined);
          renderThemePanel(container);
        });
      });
    }

    function formatAccountNumber(value, maximumFractionDigits = 0) {
      const number = Number(value);
      if (!Number.isFinite(number)) return "—";
      return new Intl.NumberFormat(state.lang === "en" ? "en-US" : "zh-CN", { maximumFractionDigits }).format(number);
    }

    function formatAccountQuota(value, display = {}) {
      const raw = Number(value);
      if (!Number.isFinite(raw)) return "—";
      const type = String(display?.type || "").toUpperCase();
      const quotaPerUnit = Number(display?.quotaPerUnit);
      if (!type || !Number.isFinite(quotaPerUnit) || quotaPerUnit <= 0) return "—";
      if (type === "TOKENS") return formatAccountNumber(raw);
      const amountUsd = raw / quotaPerUnit;
      if (type === "CNY") {
        const rate = Number(display?.usdExchangeRate);
        return `¥${formatAccountNumber(amountUsd * (Number.isFinite(rate) ? rate : 1), 2)}`;
      }
      if (type === "CUSTOM") {
        const rate = Number(display?.customCurrencyExchangeRate);
        const symbol = display?.customCurrencySymbol || "";
        return `${escapeHtml(symbol)}${formatAccountNumber(amountUsd * (Number.isFinite(rate) ? rate : 1), 2)}`;
      }
      return `$${formatAccountNumber(amountUsd, 2)}`;
    }

    function accountPanelIsActive(container) {
      return byId("settingsDetail") === container
        && documentRef.querySelector('.settings-nav-item.active')?.dataset.panel === "account";
    }

    async function refreshPlatformAccount(container, auth) {
      try {
        const response = await fetchFn("/api/code/auth/validate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token: auth.token, userId: auth.userId }),
        });
        if (response.status === 401 || response.status === 403) {
          clearPlatformAuth();
          if (accountPanelIsActive(container)) renderAccountPanel(container, { refresh: false });
          showPlatformAuthGate("expired");
          return;
        }
        if (!response.ok) throw new Error(t("accountRefreshFailed"));
        const data = await response.json();
        if (!data.valid) throw new Error(t("accountRefreshFailed"));
        savePlatformAuth(mergePlatformAccount(auth, data.account));
        if (accountPanelIsActive(container)) renderAccountPanel(container, { refresh: false });
      } catch {
        if (!accountPanelIsActive(container)) return;
        const refreshState = byId("accountRefreshState");
        if (!refreshState) return;
        refreshState.className = "account-refresh-state is-error";
        refreshState.innerHTML = `<span data-i18n="accountRefreshFailed">${t("accountRefreshFailed")}</span><button id="accountRefreshRetry" class="text-btn" type="button" data-i18n="retry">${t("retry")}</button>`;
        byId("accountRefreshRetry")?.addEventListener("click", () => {
          refreshState.className = "account-refresh-state is-loading";
          refreshState.innerHTML = `<span data-i18n="accountLoading">${t("accountLoading")}</span>`;
          refreshPlatformAccount(container, getPlatformAuth());
        });
      }
    }

    function renderAccountPanel(container, { refresh = true } = {}) {
      const auth = getPlatformAuth();
      if (auth) {
        const displayName = auth.displayName || auth.username || "Unknown";
        const username = auth.username || "";
        const secondaryName = username ? `@${username}` : "workbar";
        const email = auth.email
          ? `<strong>${escapeHtml(auth.email)}</strong>`
          : `<strong data-i18n="notSet">${t("notSet")}</strong>`;
        const group = auth.group
          ? `<strong>${escapeHtml(auth.group)}</strong>`
          : `<strong data-i18n="notSet">${t("notSet")}</strong>`;
        container.innerHTML = `<h3 class="settings-section-title" data-i18n="platformAccount">${t("platformAccount")}</h3>
          <div class="settings-lite-page account-panel">
            <section class="settings-lite-card account-identity-card">
              <div class="account-avatar">${escapeHtml(displayName[0].toUpperCase())}</div>
              <div class="account-info">
                <div class="account-name">${escapeHtml(displayName)}</div>
                <div class="account-handle">${escapeHtml(secondaryName)}</div>
                <div class="account-connection"><span class="account-connection-dot" aria-hidden="true"></span><span data-i18n="accountLoggedIn">${t("accountLoggedIn")}</span></div>
              </div>
              <button id="accountLogout" class="mini-btn account-logout" type="button" data-i18n="logout">${t("logout")}</button>
            </section>
            <div class="account-stats-grid">
              <section class="account-stat-card"><span data-i18n="accountBalance">${t("accountBalance")}</span><strong id="accountBalanceValue">${formatAccountQuota(auth.quota, auth.quotaDisplay)}</strong></section>
              <section class="account-stat-card"><span data-i18n="accountUsedQuota">${t("accountUsedQuota")}</span><strong id="accountUsedQuotaValue">${formatAccountQuota(auth.usedQuota, auth.quotaDisplay)}</strong></section>
              <section class="account-stat-card"><span data-i18n="accountRequests">${t("accountRequests")}</span><strong id="accountRequestsValue">${formatAccountNumber(auth.requestCount)}</strong></section>
            </div>
            <section class="settings-lite-card account-details-card">
              <div class="account-detail-row"><span data-i18n="accountEmail">${t("accountEmail")}</span>${email}</div>
              <div class="account-detail-row"><span data-i18n="accountGroup">${t("accountGroup")}</span>${group}</div>
              <div class="account-detail-row"><span data-i18n="accountUserId">${t("accountUserId")}</span><strong>${escapeHtml(auth.userId || "—")}</strong></div>
            </section>
            <div class="account-refresh-state${refresh ? " is-loading" : ""}" id="accountRefreshState">${refresh ? `<span data-i18n="accountLoading">${t("accountLoading")}</span>` : ""}</div>
          </div>`;
        byId("accountLogout").addEventListener("click", () => {
          clearPlatformAuth();
          onPlatformLogout();
          showToast(t("loggedOut"), "warning");
          showPlatformAuthGate("missing");
        });
        if (refresh) refreshPlatformAccount(container, auth);
        return;
      }
      container.innerHTML = `<h3 class="settings-section-title" data-i18n="platformAccount">${t("platformAccount")}</h3>
        <div class="settings-lite-page"><section class="settings-lite-card settings-empty-card"><p data-i18n="notLoggedIn">${t("notLoggedIn")}</p>
          <button id="accountLoginNow" class="mini-btn primary-btn" type="button" data-i18n="loginPlatform">${t("loginPlatform")}</button></section></div>`;
      byId("accountLoginNow").addEventListener("click", () => {
        openPlatformLogin();
      });
    }

    function isUpdateNoticeUnread(target, version) {
      return Boolean(version) && storage?.getItem(UPDATE_NOTICE_STORAGE_KEYS[target]) !== version;
    }

    function markUpdateNoticeSeen(target) {
      const version = state.updateInfo?.updateAvailable ? state.updateInfo.remoteVersion : "";
      const key = UPDATE_NOTICE_STORAGE_KEYS[target];
      if (!version || !key) return;
      storage?.setItem(key, version);
      byId(target === "settings" ? "settingsUpdateDot" : "settingsPageUpdateDot")?.classList.add("hidden");
    }

    function setUpdateNotice(data) {
      state.updateInfo = data || null;
      const remoteVersion = data?.remoteVersion || "";
      const available = Boolean(data?.updateAvailable && remoteVersion);
      byId("settingsUpdateDot")?.classList.toggle("hidden", !available || !isUpdateNoticeUnread("settings", remoteVersion));
      byId("settingsPageUpdateDot")?.classList.toggle("hidden", !available || !isUpdateNoticeUnread("page", remoteVersion));
      const badge = byId("settingsPageUpdateVersion");
      if (badge) {
        badge.textContent = available ? `v${remoteVersion}` : "";
        badge.classList.toggle("hidden", !available);
        badge.title = available ? `${t("updateAvailable")} (v${remoteVersion})` : "";
      }
      const button = byId("settingsMenuBtn");
      if (button) {
        button.classList.toggle("has-update", available);
        button.title = available ? `${t("updateAvailable")} (v${remoteVersion})` : t("settingsBtn");
      }
    }

    async function checkForUpdates({ silent = true } = {}) {
      if (state._updateCheckPromise) return state._updateCheckPromise;
      state._updateCheckPromise = (async () => {
        try {
          const data = await apiJson("/api/check-update");
          setUpdateNotice(data);
          return data;
        } catch (error) {
          if (!silent) throw error;
          return null;
        } finally {
          state._updateCheckPromise = null;
        }
      })();
      return state._updateCheckPromise;
    }

    function renderUpdatePanel(container) {
      const currentVersion = state.appVersion || "unknown";
      let remoteVersion = null;
      let downloadUrl = null;
      const status = (key, tone = "neutral", suffix = "") => {
        const element = byId("updateStatus");
        if (!element) return;
        element.innerHTML = `<span data-i18n="${key}">${t(key)}</span>${suffix ? `<span>${escapeHtml(suffix)}</span>` : ""}`;
        element.dataset.tone = tone;
      };
      const actions = (html) => { const element = byId("updateActions"); if (element) element.innerHTML = html; };
      container.innerHTML = `<h3 class="settings-section-title" data-i18n="update">${t("update")}</h3>
        <div class="settings-lite-page update-panel">
          <section class="settings-lite-card update-overview-card">
            <div class="update-app-mark" aria-hidden="true"><svg viewBox="0 0 160 160" fill="none"><path d="M80 13A40 40 0 0 1 80 93"/><path d="M80 147A40 40 0 0 1 80 67"/></svg></div>
            <div class="update-overview-copy">
              <div class="update-product-name">Code</div>
              <div class="update-ver-row"><span data-i18n="currentVersion">${t("currentVersion")}</span><strong class="update-ver-val" id="updateCurVer">v${escapeHtml(currentVersion)}</strong></div>
              <div class="update-status-row"><span id="updateStatus" data-tone="neutral"><span data-i18n="updateReadyHint">${t("updateReadyHint")}</span></span></div>
            </div>
            <div class="update-actions" id="updateActions"><button id="updateCheckBtn" class="mini-btn primary-btn" type="button" data-i18n="checkUpdate">${t("checkUpdate")}</button></div>
          </section>
          <div class="update-progress-wrap hidden" id="updateProgressWrap"><div class="update-progress-bg"><div class="update-progress-fill" id="updateBar"></div></div><span class="update-progress-txt" id="updatePct">0%</span></div>
        </div>`;
      apiJson("/api/version").then((version) => {
        const element = byId("updateCurVer");
        if (version?.localVersion && element) element.textContent = `v${version.localVersion}`;
      }).catch(() => {});
      byId("updateCheckBtn").addEventListener("click", async () => {
        status("checkingUpdate", "loading");
        actions("");
        try {
          const data = await checkForUpdates({ silent: false });
          if (data.updateAvailable) {
            remoteVersion = data.remoteVersion;
            downloadUrl = data.downloadUrl;
            status("updateAvailable", "success", ` (v${remoteVersion})`);
            if (data.isFrozen && downloadUrl) {
              actions(`<button id="updateDlBtn" class="mini-btn primary-btn" type="button"><span data-i18n="downloadUpdate">${t("downloadUpdate")}</span> <span>v${escapeHtml(remoteVersion)}</span></button>`);
              byId("updateDlBtn").addEventListener("click", startDownload);
            } else {
              actions(`<a href="https://github.com/fhy-A/Code/releases/latest" target="_blank" class="mini-btn" data-i18n="openDownloadPage">${t("openDownloadPage")}</a>`);
            }
          } else {
            status("upToDate", "success");
            actions(`<button id="updateCheckBtn2" class="mini-btn primary-btn" type="button" data-i18n="checkUpdate">${t("checkUpdate")}</button>`);
            byId("updateCheckBtn2").addEventListener("click", () => renderUpdatePanel(container));
          }
        } catch (error) {
          status("updateFailed", "error", `: ${error.message || ""}`);
          actions(`<button id="updateCheckBtn3" class="mini-btn primary-btn" type="button" data-i18n="checkUpdate">${t("checkUpdate")}</button>`);
          byId("updateCheckBtn3").addEventListener("click", () => renderUpdatePanel(container));
        }
      });

      async function startDownload() {
        status("downloading", "loading");
        byId("updateProgressWrap").classList.remove("hidden");
        actions("");
        let downloadId;
        let newExePath;
        try {
          const result = await apiJson("/api/download-update", { method: "POST", body: JSON.stringify({ url: downloadUrl }) });
          downloadId = result.downloadId;
          newExePath = result.path;
        } catch (error) {
          status("updateFailed", "error", `: ${error.message}`);
          return;
        }
        const poll = global.setInterval(async () => {
          try {
            const progress = await apiJson(`/api/download-progress?id=${encodeURIComponent(downloadId)}`);
            byId("updateBar").style.width = `${progress.progress}%`;
            byId("updatePct").textContent = `${progress.progress}%`;
            if (progress.error) {
              global.clearInterval(poll);
              status("updateFailed", "error", `: ${progress.error}`);
            }
            if (!progress.done) return;
            global.clearInterval(poll);
            byId("updateProgressWrap").classList.add("hidden");
            status("readyToInstall", "success");
            actions(`<button id="updateRestartBtn" class="mini-btn primary-btn" type="button" data-i18n="installRestart">${t("installRestart")}</button>`);
            byId("updateRestartBtn").addEventListener("click", async () => {
              status("restarting", "loading");
              actions("");
              try { await apiJson("/api/restart", { method: "POST", body: JSON.stringify({ path: newExePath }) }); } catch {}
              showToast(t("restarting"), "success");
              global.setTimeout(() => {
                const check = global.setInterval(() => {
                  fetchFn(`/api/version?_=${Date.now()}`, { cache: "no-store" })
                    .then((response) => response.json())
                    .then((versionInfo) => {
                      if (versionInfo.localVersion !== remoteVersion) return;
                      global.clearInterval(check);
                      const refreshed = new global.URL(global.location.href);
                      refreshed.searchParams.set("updated", `${remoteVersion}-${Date.now()}`);
                      global.location.replace(refreshed.toString());
                    })
                    .catch(() => {});
                }, 800);
              }, 3000);
            });
          } catch { /* server may have restarted */ }
        }, 500);
      }
    }

    function workbarSyncFailureMessage(payload, responseStatus) {
      if (payload?.error !== "workbar_sync_failed") {
        return payload?.error || `Sync failed (${responseStatus})`;
      }
      const stage = payload.stage === "list_tokens"
        ? t("syncStageListTokens")
        : payload.stage === "read_keys"
          ? t("syncStageReadKeys")
          : t("syncStageUnknown");
      const position = Number.isInteger(payload.page)
        ? t("syncPositionPage", { index: payload.page + 1 })
        : Number.isInteger(payload.batch)
          ? t("syncPositionBatch", { index: payload.batch })
          : "";
      const args = {
        stage,
        position,
        status: payload.upstreamStatus || responseStatus,
      };
      switch (payload.kind) {
        case "http": return t("syncFailureHttp", args);
        case "timeout": return t("syncFailureTimeout", args);
        case "network": return t("syncFailureNetwork", args);
        case "invalid_response": return t("syncFailureInvalidResponse", args);
        default: return t("syncFailureUnknown", args);
      }
    }

    function inspectPlatformKeyPayload(tokens, fullKeys) {
      const tokenEntries = Array.isArray(tokens) ? tokens : [];
      const readableItems = [];
      let unreadableKeyCount = 0;
      for (const tokenEntry of tokenEntries) {
        const platformTokenId = platform.normalizePlatformTokenId(tokenEntry?.id);
        const key = platform.normalizeSyncedKey(platformTokenId ? fullKeys?.[platformTokenId] : "");
        if (!key) {
          unreadableKeyCount += 1;
          continue;
        }
        readableItems.push({ tokenEntry, platformTokenId, key });
      }
      return {
        tokenCount: tokenEntries.length,
        readableKeyCount: readableItems.length,
        unreadableKeyCount,
        readableItems,
      };
    }

    async function syncKeysFromPlatform({ interactive = true } = {}) {
      const auth = getPlatformAuth();
      if (!auth) {
        if (interactive) showToast(t("loginFirst"));
        return { ok: false, authRequired: true };
      }
      const button = interactive ? byId("settingsConnectPlatform") : null;
      if (button) {
        button.disabled = true;
        const label = button.querySelector("span");
        if (label) label.textContent = t("fetchingKeys");
      }
      try {
        const response = await fetchFn("/api/code/sync-keys", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token: auth.token, userId: auth.userId }),
        });
        if (response.status === 401 || response.status === 403) {
          clearPlatformAuth();
          showPlatformAuthGate("expired");
          if (interactive) showToast(t("loginExpired"), "error");
          return { ok: false, authExpired: true };
        }
        let data = null;
        try {
          data = await response.json();
        } catch {
          if (!response.ok) throw new Error(`Sync failed (${response.status})`);
          throw new Error(t("syncFailureInvalidResponse", {
            stage: t("syncStageUnknown"),
            position: "",
          }));
        }
        if (!response.ok) {
          throw new Error(workbarSyncFailureMessage(data, response.status));
        }
        if (data.error) throw new Error(data.error);
        const tokens = Array.isArray(data.tokens) ? data.tokens : [];
        const fullKeys = data.keys && typeof data.keys === "object" && !Array.isArray(data.keys) ? data.keys : {};
        const localConfig = loadKeyConfig(storage);
        const snapshot = inspectPlatformKeyPayload(tokens, fullKeys);
        if (snapshot.tokenCount === 0) {
          if (interactive) showToast(t("noPlatformTokens"), "warning");
          return {
            ok: true,
            status: "no-platform-tokens",
            imported: 0,
            updated: 0,
            tokenCount: 0,
            readableKeyCount: 0,
            unreadableKeyCount: 0,
            preservedLocalCount: localConfig.length,
          };
        }
        if (snapshot.readableKeyCount === 0) {
          if (interactive) showToast(t("platformKeysUnreadable", { count: snapshot.tokenCount }), "warning");
          return {
            ok: true,
            status: "keys-unreadable",
            imported: 0,
            updated: 0,
            tokenCount: snapshot.tokenCount,
            readableKeyCount: 0,
            unreadableKeyCount: snapshot.unreadableKeyCount,
            preservedLocalCount: localConfig.length,
          };
        }
        if (interactive) {
          const presentation = showKeySyncModal(snapshot);
          return { ok: true, ...presentation };
        }
        const excludedTokenIds = platform.loadPlatformKeyExclusions(auth.userId, storage);
        const result = platform.mergeSyncedKeys(localConfig, tokens, fullKeys, { excludedTokenIds });
        const saved = saveKeyConfig(result.entries);
        els.apiKey.value = serializeKeys(saved);
        saveLocalSettings();
        return {
          ok: true,
          status: snapshot.unreadableKeyCount > 0 ? "partial" : result.imported > 0 ? "synced" : "unchanged",
          imported: result.imported,
          updated: result.updated,
          tokenCount: snapshot.tokenCount,
          readableKeyCount: snapshot.readableKeyCount,
          unreadableKeyCount: snapshot.unreadableKeyCount,
          preservedLocalCount: localConfig.length,
        };
      } catch (error) {
        const message = error.message || String(error);
        if (interactive) showToast(t("syncFailed", { message }), "error");
        return { ok: false, error: message };
      } finally {
        if (button) {
          button.disabled = false;
          const label = button.querySelector("span");
          if (label) label.textContent = t("getFromWorkbar");
        }
      }
    }

    async function syncPlatformKeysSilently() {
      return syncKeysFromPlatform({ interactive: false });
    }

    function showKeySyncModal(snapshot) {
      byId("keySyncOverlay")?.remove();
      const existingKeys = new Set(loadKeyConfig(storage)
        .map((entry) => platform.normalizeSyncedKey(entry.key))
        .filter(Boolean));
      const auth = getPlatformAuth();
      const excludedTokenIds = platform.loadPlatformKeyExclusions(auth?.userId, storage);
      const seen = new Set();
      const items = [];
      for (const readable of snapshot.readableItems) {
        const { tokenEntry, platformTokenId, key } = readable;
        if (seen.has(key)) continue;
        seen.add(key);
        const name = String(tokenEntry?.name || "").trim();
        items.push({
          name,
          key,
          line: platform.formatSyncedKeyLine(name, key),
          preview: platform.maskSyncedKey(key),
          exists: existingKeys.has(key),
          excluded: excludedTokenIds.has(platformTokenId),
          enabled: tokenEntry?.status == null || Number(tokenEntry.status) === 1,
        });
      }
      if (!items.length) {
        return {
          status: "keys-unreadable",
          presented: 0,
          tokenCount: snapshot.tokenCount,
          readableKeyCount: 0,
          unreadableKeyCount: snapshot.unreadableKeyCount,
        };
      }

      const copyLines = items.map((item) => item.enabled ? item.line : "");
      const enabledItems = items.filter((item) => item.enabled);
      const allText = enabledItems.map((item) => item.line).join("\n");
      const newCount = enabledItems.filter((item) => !item.exists && !item.excluded).length;
      const excludedCount = enabledItems.filter((item) => !item.exists && item.excluded).length;
      const disabledCount = items.length - enabledItems.length;
      const unreadableCount = snapshot.unreadableKeyCount;
      const rows = items.map((item, index) => {
        const badges = [
          item.exists ? `<span class="key-sync-badge">${t("alreadyAdded")}</span>` : "",
          !item.exists && item.excluded ? `<span class="key-sync-badge key-sync-excluded-badge">${t("removedFromCode")}</span>` : "",
          !item.enabled ? `<span class="key-sync-badge key-sync-disabled-badge">${t("disabledStatus")}</span>` : "",
        ].join("");
        const copyButton = item.enabled
          ? `<button class="mini-btn key-copy-one" data-copy-index="${index}" type="button">${t("copy")}</button>`
          : "";
        const displayName = item.name || t("unnamed");
        return `<div class="key-sync-row${item.exists ? " key-sync-exists" : ""}${item.excluded && !item.exists ? " key-sync-excluded" : ""}${item.enabled ? "" : " key-sync-disabled"}"><span class="key-sync-name" title="${escapeHtml(displayName)}">${escapeHtml(displayName)}</span><span class="key-sync-key">${escapeHtml(item.preview)}</span><span class="key-sync-actions">${badges}${copyButton}</span></div>`;
      }).join("");
      const overlay = documentRef.createElement("div");
      overlay.id = "keySyncOverlay";
      overlay.className = "modal-overlay";
      const summaryParts = [
        t("keyCount", { count: snapshot.tokenCount }),
        newCount > 0 && newCount < enabledItems.length ? t("newKeyCount", { count: newCount }) : "",
        excludedCount > 0 ? t("removedKeyCount", { count: excludedCount }) : "",
        disabledCount > 0 ? t("disabledKeyCount", { count: disabledCount }) : "",
        unreadableCount > 0 ? t("unreadableKeyCount", { count: unreadableCount }) : "",
      ].filter(Boolean);
      const footerKey = enabledItems.length === 0
        ? "noEnabledPlatformKeys"
        : unreadableCount > 0 && newCount === 0 && excludedCount === 0
          ? "partialKeysUnreadable"
          : newCount === 0 && excludedCount === 0
            ? "allKeysAdded"
            : newCount === 0
              ? "removedKeysHint"
              : "pasteKeysHint";
      overlay.innerHTML = `<div class="modal-card key-sync-card">
        <header><h3>${t("syncKeysTitle")}</h3><button class="icon-btn key-sync-close" type="button">&times;</button></header>
        <div class="key-sync-summary"><span>${summaryParts.join(t("keySummarySeparator"))}</span><button id="keySyncCopyAll" class="mini-btn primary" type="button"${enabledItems.length ? "" : " disabled"}>${t("copyAll")}</button></div>
        <div class="key-sync-list">${rows}</div>
        <div class="key-sync-footer"><span class="key-sync-note${footerKey === "allKeysAdded" ? " is-complete" : ""}">${t(footerKey)}</span></div>
      </div>`;
      documentRef.body.appendChild(overlay);
      overlay.querySelector(".key-sync-close").addEventListener("click", () => overlay.remove());
      overlay.addEventListener("click", (event) => { if (event.target === overlay) overlay.remove(); });
      const copyAllButton = overlay.querySelector("#keySyncCopyAll");
      copyAllButton?.addEventListener("click", () => {
        if (!allText) return;
        navigatorRef.clipboard.writeText(allText.trim()).then(() => {
          copyAllButton.textContent = t("copied");
          global.setTimeout(() => { copyAllButton.textContent = t("copyAll"); }, 1500);
        }).catch(() => showToast(t("copyFailed")));
      });
      overlay.querySelectorAll(".key-copy-one").forEach((button) => {
        button.addEventListener("click", () => {
          const line = copyLines[Number(button.dataset.copyIndex)] || "";
          navigatorRef.clipboard.writeText(line).then(() => {
            button.textContent = t("copied");
            global.setTimeout(() => { button.textContent = t("copy"); }, 1500);
          }).catch(() => showToast(t("copyFailed")));
        });
      });
      return {
        status: unreadableCount > 0
          ? "partial"
          : enabledItems.length === 0
            ? "no-enabled-keys"
            : newCount === 0 && excludedCount === 0
              ? "all-added"
              : newCount > 0
                ? "new-keys"
                : "excluded",
        presented: items.length,
        tokenCount: snapshot.tokenCount,
        readableKeyCount: snapshot.readableKeyCount,
        unreadableKeyCount: unreadableCount,
      };
    }

    async function checkCodeCallback() {
      const params = new global.URLSearchParams(global.location.search);
      const token = params.get("code_token");
      const userId = params.get("user_id");
      const username = params.get("username");
      if (!token || !userId) return false;
      global.history.replaceState(null, "", "/");
      const decodedUsername = decodeURIComponent(username || "");
      savePlatformAuth({ token, userId, username: decodedUsername });
      showToast(t("loggedInAs", { name: decodedUsername }), "warning");
      const detail = byId("settingsDetail");
      if (detail?.children.length) renderModelsPanel(detail);
      return true;
    }

    function switchSettingsPanel(panel) {
      documentRef.querySelectorAll(".settings-nav-item").forEach((element) => {
        element.classList.toggle("active", element.dataset.panel === panel);
      });
      const detail = byId("settingsDetail");
      if (!detail) return;
      switch (panel) {
        case "models":
          renderModelsPanel(detail);
          break;
        case "account": renderAccountPanel(detail); break;
        case "memory": renderMemoryPanel(detail); break;
        case "skills": renderSkillsInSettings(detail); break;
        case "system": renderSystemPanel(detail); break;
        case "editor": renderEditorPanel(detail); break;
        case "theme": renderThemePanel(detail); break;
        case "update": renderUpdatePanel(detail); break;
        default: return;
      }
      applyI18n();
    }

    function refreshActiveSettingsLanguage(panel) {
      const detail = byId("settingsDetail");
      if (!detail || !panel) return;
      switch (panel) {
        case "account": {
          const auth = getPlatformAuth();
          if (auth) {
            const balance = byId("accountBalanceValue");
            const used = byId("accountUsedQuotaValue");
            const requests = byId("accountRequestsValue");
            if (balance) balance.textContent = formatAccountQuota(auth.quota, auth.quotaDisplay);
            if (used) used.textContent = formatAccountQuota(auth.usedQuota, auth.quotaDisplay);
            if (requests) requests.textContent = formatAccountNumber(auth.requestCount);
          }
          break;
        }
        case "memory":
        case "skills":
          refreshSkillsMemorySettingsLanguage(panel);
          break;
        case "theme":
          renderThemePanel(detail);
          break;
        case "editor":
          renderEditorPanel(detail);
          break;
        case "models": {
          const refreshButton = byId("settingsRefreshModels");
          if (refreshButton) {
            const refreshKey = refreshButton.classList.contains("is-loading") ? "detectingModels" : "detectAvailableModels";
            refreshButton.title = t(refreshKey);
            refreshButton.setAttribute("aria-label", t(refreshKey));
          }
          detail.querySelectorAll(".key-enable").forEach((label) => {
            const enabled = label.querySelector("input")?.checked !== false;
            label.dataset.keyEnabled = String(enabled);
            label.title = t(enabled ? "enabledStatus" : "disabledStatus");
          });
          break;
        }
        default:
          break;
      }
      detail.querySelectorAll("[data-settings-delete-name]").forEach((element) => {
        element.textContent = t("deleteConfirmMsg", { name: element.dataset.settingsDeleteName || "" });
      });
      setUpdateNotice(state.updateInfo);
      applyI18n();
    }

    function openSettingsPage(panel = "models") {
      byId("settingsPage")?.classList.remove("hidden");
      switchSettingsPanel(panel);
    }

    function bind() {
      if (bound) return;
      bound = true;
      global.matchMedia?.("(prefers-color-scheme: dark)")?.addEventListener("change", () => {
        if ((storage?.getItem("code-theme-mode") || storage?.getItem("code-theme") || "light") !== "system") return;
        applyTheme("system");
        const panel = byId("settingsDetail");
        if (panel?.querySelector(".tp-picker")) renderThemePanel(panel);
      });
      byId("settingsMenuBtn")?.addEventListener("click", () => {
        markUpdateNoticeSeen("settings");
        openSettingsPage("models");
      });
      byId("settingsNav")?.addEventListener("click", (event) => {
        const item = event.target.closest(".settings-nav-item");
        if (!item) return;
        if (item.dataset.panel === "update") markUpdateNoticeSeen("page");
        switchSettingsPanel(item.dataset.panel);
      });
      byId("settingsLanguageSwitch")?.addEventListener("click", (event) => {
        const button = event.target.closest("[data-settings-lang]");
        if (!button || button.dataset.settingsLang === (state.lang || "zh")) return;
        const activePanel = documentRef.querySelector(".settings-nav-item.active")?.dataset.panel;
        setLang(button.dataset.settingsLang);
        updateLanguageControls();
        refreshActiveSettingsLanguage(activePanel);
      });
      updateLanguageControls();
      byId("closeSettingsPage")?.addEventListener("click", () => byId("settingsPage")?.classList.add("hidden"));
      byId("settingsPage")?.addEventListener("click", (event) => {
        if (event.target === event.currentTarget) event.currentTarget.classList.add("hidden");
      });
      [["settingsModels", "models"], ["settingsMemory", "memory"], ["settingsSkills", "skills"], ["settingsSystem", "system"]].forEach(([id, panel]) => {
        byId(id)?.addEventListener("click", () => {
          closeDropdown();
          openSettingsPage(panel);
        });
      });
      byId("closeSystemPrompt")?.addEventListener("click", () => byId("systemPromptModal")?.classList.add("hidden"));
      byId("systemPromptModal")?.addEventListener("click", (event) => {
        if (event.target === event.currentTarget) event.currentTarget.classList.add("hidden");
      });
      documentRef.querySelectorAll(".theme-opt").forEach((button) => {
        button.addEventListener("click", () => applyTheme(button.dataset.theme));
      });
      documentRef.addEventListener("click", (event) => {
        if (!event.target.closest(".settings-dropdown")) closeDropdown();
      });
      global.addEventListener?.("storage", (event) => {
        if (event.key === "code-platform-auth") {
          global.location.reload();
          return;
        }
        if (event.key !== platform.KEY_CONFIG_STORAGE_KEY) return;
        const config = syncKeyEditorFromStorage();
        onKeyConfigChanged(config);
      });
      global.addEventListener?.("pageshow", syncKeyEditorFromStorage);
      els.closeSettings?.addEventListener("click", () => showSettings(false));
      els.settingsModal?.addEventListener("click", (event) => {
        if (event.target === els.settingsModal) showSettings(false);
      });
    }

    /* public helpers reachable from inline onclick handlers */
    function _selectTheme(mode, lightVariant, darkVariant) {
      const prefs = getThemePrefs();
      const lv = lightVariant === "_pair" ? prefs.lightVariant : lightVariant;
      const dv = darkVariant === "_pair" ? prefs.darkVariant : darkVariant;
      applyTheme(mode, lv, dv);
      const panel = byId("settingsDetail");
      if (panel && panel.querySelector(".tp-picker")) renderThemePanel(panel);
    }

    function _setMode(mode) {
      applyTheme(mode);
      const panel = byId("settingsDetail");
      if (panel && panel.querySelector(".tp-picker")) renderThemePanel(panel);
    }

    return Object.freeze({
      applyTheme,
      _selectTheme,
      _setMode,
      bind,
      checkCodeCallback,
      checkForUpdates,
      closeDropdown,
      loadKeyConfig: () => loadKeyConfig(storage),
      initializePlatformAuth,
      parseKeyLines,
      saveKeyConfig,
      serializeKeys,
      openSettingsPage,
      syncKeysFromPlatform,
      syncPlatformKeysSilently,
      switchSettingsPanel,
      updateThemeButtons,
    });
  }

  Code.features.settings = Object.freeze({
    FOLLOW_UP_BEHAVIORS,
    FOLLOW_UP_BEHAVIOR_STORAGE_KEY,
    UPDATE_NOTICE_STORAGE_KEYS,
    WORKBAR_URL,
    buildPlatformLoginUrl,
    createSettingsFeature,
    loadKeyConfig,
    loadFollowUpBehavior,
    normalizeFollowUpBehavior,
    oppositeFollowUpBehavior,
    saveFollowUpBehavior,
  });
})(window);
