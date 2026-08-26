(function registerPlatformCore(global) {
  "use strict";

  const Code = global.Code;
  if (!Code?.core) throw new Error("Code namespace must load before platform core");

  const WORKBAR_URL = "https://workbar.ai";
  const KEY_CONFIG_STORAGE_KEY = "code-key-config";
  const KEY_SYNC_EXCLUSIONS_STORAGE_KEY = "code-platform-key-exclusions";
  const LEGACY_KEY_STORAGE_KEYS = Object.freeze([
    "code-key",
    "agent-lite-key",
    "agent-lite-key-config",
  ]);

  function normalizePlatformTokenId(value) {
    const tokenId = String(value ?? "").trim();
    return /^\d+$/.test(tokenId) ? tokenId : "";
  }

  function normalizePlatformUserId(value) {
    const userId = String(value ?? "").trim();
    return /^\d+$/.test(userId) ? userId : "";
  }

  function normalizeManualConnectionId(value) {
    const connectionId = String(value ?? "").trim();
    return /^manual_[A-Za-z0-9_.:-]{8,152}$/.test(connectionId) ? connectionId : "";
  }

  function createManualConnectionId() {
    const randomUUID = global.crypto?.randomUUID?.bind(global.crypto);
    if (randomUUID) return `manual_${randomUUID()}`;
    const bytes = new Uint8Array(16);
    global.crypto?.getRandomValues?.(bytes);
    const suffix = [...bytes].map((value) => value.toString(16).padStart(2, "0")).join("");
    if (suffix && !/^0+$/.test(suffix)) return `manual_${suffix}`;
    return `manual_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 14)}`;
  }

  function normalizeKeyEntry(entry, defaultSource = "manual") {
    if (!entry || typeof entry !== "object") return null;
    const key = String(entry.key || "").trim();
    if (!key) return null;
    const normalized = {
      name: String(entry.name || "").trim(),
      key,
      enabled: entry.enabled !== false,
      source: entry.source === "platform" ? "platform" : defaultSource,
    };
    const platformTokenId = normalizePlatformTokenId(entry.platformTokenId);
    if (platformTokenId) normalized.platformTokenId = platformTokenId;
    const manualConnectionId = normalizeManualConnectionId(entry.connectionId);
    if (manualConnectionId) {
      normalized.connectionId = manualConnectionId;
    }
    return normalized;
  }

  function normalizeKeyConfig(config, defaultSource = "manual") {
    const seen = new Set();
    const normalized = [];
    for (const item of Array.isArray(config) ? config : []) {
      const entry = normalizeKeyEntry(item, defaultSource);
      if (!entry || seen.has(entry.key)) continue;
      seen.add(entry.key);
      normalized.push(entry);
    }
    return normalized;
  }

  function loadKeyConfig(storage = global.localStorage) {
    try {
      const parsed = JSON.parse(storage?.getItem(KEY_CONFIG_STORAGE_KEY) || "[]");
      const normalized = normalizeKeyConfig(parsed);
      let changed = false;
      const withConnectionIds = normalized.map((entry) => {
        if (entry.source === "platform" || entry.connectionId) return entry;
        changed = true;
        return { ...entry, connectionId: createManualConnectionId() };
      });
      if (changed) storage?.setItem(KEY_CONFIG_STORAGE_KEY, JSON.stringify(withConnectionIds));
      return withConnectionIds;
    } catch {
      return [];
    }
  }

  function saveKeyConfig(config, storage = global.localStorage) {
    const normalized = normalizeKeyConfig(config).map((entry) => (
      entry.source !== "platform" && !entry.connectionId
        ? { ...entry, connectionId: createManualConnectionId() }
        : entry
    ));
    storage?.setItem(KEY_CONFIG_STORAGE_KEY, JSON.stringify(normalized));
    LEGACY_KEY_STORAGE_KEYS.forEach((key) => storage?.removeItem?.(key));
    return normalized;
  }

  function migrateLegacyKeyConfig(storage = global.localStorage) {
    const currentRaw = storage?.getItem(KEY_CONFIG_STORAGE_KEY);
    let migrated = currentRaw == null ? null : loadKeyConfig(storage);

    if (currentRaw == null) {
      const legacyStructuredRaw = storage?.getItem("agent-lite-key-config");
      if (legacyStructuredRaw != null) {
        try {
          migrated = normalizeKeyConfig(JSON.parse(legacyStructuredRaw));
        } catch {
          migrated = null;
        }
      }
      if (migrated == null) {
        const legacyText = storage?.getItem("code-key") ?? storage?.getItem("agent-lite-key") ?? "";
        migrated = parseKeyText(legacyText).entries;
      }
    }

    return saveKeyConfig(migrated || [], storage);
  }

  function loadPlatformKeyExclusionState(storage = global.localStorage) {
    try {
      const parsed = JSON.parse(storage?.getItem(KEY_SYNC_EXCLUSIONS_STORAGE_KEY) || "null");
      const accounts = {};
      for (const [rawUserId, rawTokenIds] of Object.entries(parsed?.accounts || {})) {
        const userId = normalizePlatformUserId(rawUserId);
        if (!userId) continue;
        const tokenIds = [...new Set((Array.isArray(rawTokenIds) ? rawTokenIds : [])
          .map(normalizePlatformTokenId)
          .filter(Boolean))];
        if (tokenIds.length) accounts[userId] = tokenIds;
      }
      return { version: 1, accounts };
    } catch {
      return { version: 1, accounts: {} };
    }
  }

  function loadPlatformKeyExclusions(userId, storage = global.localStorage) {
    const normalizedUserId = normalizePlatformUserId(userId);
    if (!normalizedUserId) return new Set();
    const state = loadPlatformKeyExclusionState(storage);
    return new Set(state.accounts[normalizedUserId] || []);
  }

  function savePlatformKeyExclusions(userId, tokenIds, storage = global.localStorage) {
    const normalizedUserId = normalizePlatformUserId(userId);
    if (!normalizedUserId) return new Set();
    const state = loadPlatformKeyExclusionState(storage);
    const normalizedTokenIds = [...new Set(Array.from(tokenIds || [])
      .map(normalizePlatformTokenId)
      .filter(Boolean))]
      .sort((left, right) => Number(left) - Number(right));
    if (normalizedTokenIds.length) state.accounts[normalizedUserId] = normalizedTokenIds;
    else delete state.accounts[normalizedUserId];
    storage?.setItem(KEY_SYNC_EXCLUSIONS_STORAGE_KEY, JSON.stringify(state));
    return new Set(normalizedTokenIds);
  }

  function excludePlatformToken(userId, tokenId, storage = global.localStorage) {
    const normalizedTokenId = normalizePlatformTokenId(tokenId);
    if (!normalizedTokenId) return false;
    const exclusions = loadPlatformKeyExclusions(userId, storage);
    exclusions.add(normalizedTokenId);
    savePlatformKeyExclusions(userId, exclusions, storage);
    return true;
  }

  function normalizeSyncedKey(value) {
    const key = String(value || "").trim();
    if (!key || key.includes("***")) return "";
    return /^sk-/i.test(key) ? `sk-${key.slice(3)}` : `sk-${key}`;
  }

  function formatSyncedKeyLine(name, value) {
    const key = normalizeSyncedKey(value);
    if (!key) return "";
    const cleanName = String(name || "").replace(/[\r\n:]+/g, " ").trim();
    return cleanName ? `${cleanName}: ${key}` : key;
  }

  function maskSyncedKey(value) {
    const key = normalizeSyncedKey(value);
    if (!key) return "";
    const body = key.slice(3);
    const visible = body.length > 4 ? body.slice(-4) : body.slice(-1);
    return `sk-••••••••${visible}`;
  }

  function mergeSyncedKeys(config, tokens, fullKeys, options = {}) {
    const merged = normalizeKeyConfig(config).map((entry) => ({ ...entry }));
    const indexByKey = new Map(merged.map((entry, index) => [entry.key, index]));
    const excludedTokenIds = new Set(Array.from(options.excludedTokenIds || [])
      .map(normalizePlatformTokenId)
      .filter(Boolean));
    let imported = 0;
    let updated = 0;

    for (const token of Array.isArray(tokens) ? tokens : []) {
      const platformTokenId = normalizePlatformTokenId(token?.id);
      if (!platformTokenId || excludedTokenIds.has(platformTokenId)) continue;
      const key = normalizeSyncedKey(fullKeys?.[platformTokenId]);
      if (!key) continue;
      const enabled = token?.status == null || Number(token.status) === 1;
      const name = String(token?.name || "").trim();
      const existingIndex = indexByKey.get(key);
      if (existingIndex != null) {
        const existing = merged[existingIndex];
        if (existing.source === "platform") {
          merged[existingIndex] = {
            ...existing,
            name: name || existing.name,
            enabled,
            platformTokenId,
          };
          updated += 1;
        } else if (!existing.platformTokenId) {
          merged[existingIndex] = { ...existing, platformTokenId };
        }
        continue;
      }
      indexByKey.set(key, merged.length);
      merged.push({ name, key, enabled, source: "platform", platformTokenId });
      imported += 1;
    }

    return { entries: normalizeKeyConfig(merged), imported, updated };
  }

  function splitKeyLine(value) {
    const line = String(value || "").trim();
    if (!line) return null;

    const colonIndex = line.indexOf(":");
    if (colonIndex > 0) {
      return {
        name: line.slice(0, colonIndex).trim(),
        key: line.slice(colonIndex + 1).trim(),
      };
    }

    const spaced = line.match(/^(.+?)\s+(sk-\S+)$/i);
    if (spaced) return { name: spaced[1].trim(), key: spaced[2].trim() };
    return { name: "", key: line };
  }

  function parseKeyText(raw, config = []) {
    const existingByKey = new Map(normalizeKeyConfig(config).map((entry) => [entry.key, entry]));
    const seen = new Set();
    const duplicates = [];
    const entries = [];
    for (const line of String(raw || "").split("\n")) {
      const parsed = splitKeyLine(line);
      if (!parsed?.key) continue;
      if (seen.has(parsed.key)) {
        duplicates.push(parsed.name || parsed.key);
        continue;
      }
      seen.add(parsed.key);
      const existing = existingByKey.get(parsed.key);
      const entry = {
        name: parsed.name || existing?.name || "",
        key: parsed.key,
        enabled: existing?.enabled !== false,
        source: existing?.source === "platform" ? "platform" : "manual",
      };
      if (existing?.platformTokenId) entry.platformTokenId = existing.platformTokenId;
      if (existing?.connectionId) entry.connectionId = existing.connectionId;
      entries.push(entry);
    }
    return { entries, duplicates };
  }

  function serializeKeyEntries(config) {
    return normalizeKeyConfig(config).map((entry) => (
      entry.name ? `${entry.name}: ${entry.key}` : entry.key
    )).join("\n");
  }

  Code.core.platform = Object.freeze({
    KEY_CONFIG_STORAGE_KEY,
    KEY_SYNC_EXCLUSIONS_STORAGE_KEY,
    LEGACY_KEY_STORAGE_KEYS,
    WORKBAR_URL,
    excludePlatformToken,
    formatSyncedKeyLine,
    loadKeyConfig,
    loadPlatformKeyExclusions,
    maskSyncedKey,
    mergeSyncedKeys,
    migrateLegacyKeyConfig,
    normalizeKeyConfig,
    normalizeManualConnectionId,
    normalizePlatformTokenId,
    normalizeSyncedKey,
    parseKeyText,
    saveKeyConfig,
    serializeKeyEntries,
    splitKeyLine,
  });
})(window);
