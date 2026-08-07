const base = require("@playwright/test");
const crypto = require("node:crypto");
const fs = require("node:fs/promises");
const path = require("node:path");
const { FIXTURE_CONTENT, startIsolatedHost } = require("./isolated-host.cjs");

const { expect } = base;
const MODEL_ID = "h4-e2e-model";
const STREAM_USER = "H4_STREAM_REFRESH_USER";
const STREAM_ONE = "H4_STREAM_ONE";
const STREAM_TWO = "H4_STREAM_TWO";
const STREAM_THREE = "H4_STREAM_THREE";
const STREAM_FINAL = `${STREAM_ONE} ${STREAM_TWO} ${STREAM_THREE}`;
const TOOL_DETAILS_USER = "H4_TOOL_DETAILS_USER";
const TOOL_DETAILS_STAGE = "H4_TOOL_DETAILS_STAGE";
const TOOL_DETAILS_FINAL = "H4_TOOL_DETAILS_FINAL";
const TOOL_FINAL_DELTA_GATE = "before-tool-final-delta";
const TOOL_TERMINAL_GATE = "before-tool-terminal";
const FRONTEND_BUNDLE_PATH = "/dist/frontend/code.bundle.js";
const CLASSIC_FALLBACK_PATH = "/dist/frontend/index.classic.html";
const H4_5B1_SEMANTIC_HASHES = Object.freeze({
  toolResult: "1895281c988e7a243d395e51f6d73137142dd155dd6e23e43bec4948d9fa691c",
  executionProjection: "1783025dc756f6fbb2f18544210aa491b4ae1535d02595e3527093ad0a15e9d9",
  eventProjection: "85dfc1ee8f8e43ef6d87fd6ea59bd289fd15830d5f729f5729266033373fda1e",
  durableProjection: "b1c30c051cd9b640f4efa72784d1dc7756042e2422d6f1facb82dfb2b28e6122",
  sessionRoleContent: "ecfbdadd2377ffc0f7c897b024dbd9aee7091c0375a3a48befe75c6a461c3a9a",
  sessionToolMeta: "587b9b6365a9811779ab0bac530de558af1dfca14d31c70ac2cce71ae0973fe9",
  domSemantic: "37d1870e896058e5f001c491a241353faa230e5b0a6fca9d487f8cf8bd058e91",
  finalResult: "e40fb4ba752c3fe25f985c5aa78152ee6ce0166330aa57ca7d67e8a68e24bdef",
});
const H4_6A_ACTIVE_TO_TERMINAL_HASHES = Object.freeze({
  lifecycle: "de27ce93297dad0a99c9215080d8ffd891d893ad30a2ed88884ecbeaeff31487",
  eventProjection: "36658361b00ce7bff3f3464099e27fe81273845e2ab85a62c0229814128b9d48",
  sessionRoleContent: "c6b7c90baeafb1c29e38d431bdbaf28a1ca282d54d47ac2d024601ad3d3e442a",
  terminalDom: "71a1ebdf6f609fc44a8408f20d15659626e8b6d11bf033b3665be510bf470712",
});
const H4_6A_TERMINAL_REFRESH_HASHES = Object.freeze({
  refreshLifecycle: "0712a70b1ad23f9d33ab31b780df8c48deebbeaae784e80a4976daf0e7452ec8",
  eventProjection: "36658361b00ce7bff3f3464099e27fe81273845e2ab85a62c0229814128b9d48",
  sessionRoleContent: "c6b7c90baeafb1c29e38d431bdbaf28a1ca282d54d47ac2d024601ad3d3e442a",
  sessionToolMeta: "587b9b6365a9811779ab0bac530de558af1dfca14d31c70ac2cce71ae0973fe9",
  terminalDom: "71a1ebdf6f609fc44a8408f20d15659626e8b6d11bf033b3665be510bf470712",
});

function idHash(value) {
  const raw = String(value || "");
  return raw ? crypto.createHash("sha256").update(raw).digest("hex").slice(0, 16) : "";
}

function canonicalHash(value) {
  return crypto.createHash("sha256").update(JSON.stringify(value)).digest("hex");
}

function roleContentProjection(messages) {
  return (Array.isArray(messages) ? messages : []).map((message) => ({
    role: String(message?.role || ""),
    content: message?.content ?? "",
  }));
}

function durableAgentEvidence(snapshot) {
  const events = Array.isArray(snapshot?.events) ? snapshot.events : [];
  const runtimeIds = events
    .filter((event) => ["model_started", "model_completed"].includes(event?.type))
    .map((event) => idHash(event?.data?.runtimeRunId || ""));
  return {
    agentRunId: idHash(snapshot?.agentRunId || ""),
    sessionId: idHash(snapshot?.sessionId || ""),
    clientRequestId: idHash(snapshot?.clientRequestId || ""),
    status: String(snapshot?.status || ""),
    nextCursor: Number(snapshot?.nextCursor || 0),
    eventTypes: events.map((event) => String(event?.type || "")),
    terminalEventCount: events.filter((event) => (
      event?.type === "completed" || event?.type === "failed" || event?.type === "cancelled"
    )).length,
    runtimeIds,
    resultHash: canonicalHash(snapshot?.result || {}),
  };
}

function parseToolArguments(value) {
  if (value && typeof value === "object") return value;
  try {
    return JSON.parse(String(value || "{}"));
  } catch {
    return String(value || "");
  }
}

function stableReadToolResult(result) {
  return {
    ok: result?.ok === true,
    action: String(result?.action || ""),
    path: String(result?.path || ""),
    content: String(result?.content || ""),
    size: Number(result?.size || 0),
    truncated: Boolean(result?.truncated),
    lineRange: result?.lineRange ?? null,
  };
}

function durableToolTraceEvidence(snapshot) {
  const events = Array.isArray(snapshot?.events) ? snapshot.events : [];
  const executions = Array.isArray(snapshot?.toolExecutions) ? snapshot.toolExecutions : [];
  const runtimeRunIds = events
    .filter((event) => event?.type === "model_started")
    .map((event) => String(event?.data?.runtimeRunId || ""));
  const runtimeAliases = new Map(runtimeRunIds.map((runId, index) => [runId, `runtime-${index + 1}`]));
  const toolCallIds = executions.map((execution) => String(execution?.toolCallId || ""));
  const toolAliases = new Map(toolCallIds.map((callId, index) => [callId, `tool-${index + 1}`]));
  const runtimeAlias = (runId) => runtimeAliases.get(String(runId || "")) || "";
  const toolAlias = (callId) => toolAliases.get(String(callId || "")) || "";
  const eventProjection = events.map((event) => {
    const data = event?.data || {};
    const projection = {
      seq: Number(event?.seq || 0),
      type: String(event?.type || ""),
    };
    if (data.round != null) projection.round = Number(data.round);
    if (data.runtimeRunId) projection.runtimeRunId = runtimeAlias(data.runtimeRunId);
    if (data.content != null) projection.content = String(data.content);
    if (data.finishReason != null) projection.finishReason = String(data.finishReason);
    if (data.outcome != null) projection.outcome = String(data.outcome);
    if (Array.isArray(data.toolCalls)) {
      projection.toolCalls = data.toolCalls.map((call) => ({
        toolCallId: toolAlias(call?.id),
        name: String(call?.function?.name || call?.name || ""),
        arguments: parseToolArguments(call?.function?.arguments ?? call?.arguments),
      }));
    }
    if (data.toolCallId) projection.toolCallId = toolAlias(data.toolCallId);
    if (data.name != null) projection.name = String(data.name);
    if (data.arguments != null) projection.arguments = parseToolArguments(data.arguments);
    if (data.replayed != null) projection.replayed = Boolean(data.replayed);
    if (data.result != null) projection.result = stableReadToolResult(data.result);
    return projection;
  });
  const executionProjection = executions.map((execution) => ({
    toolCallId: toolAlias(execution?.toolCallId),
    name: String(execution?.name || ""),
    arguments: parseToolArguments(execution?.arguments),
    status: String(execution?.status || ""),
    outcome: String(execution?.outcome || ""),
    result: stableReadToolResult(execution?.result),
  }));
  const resultProjection = {
    content: String(snapshot?.result?.content || ""),
    reasoning: String(snapshot?.result?.reasoning || ""),
    finishReason: String(snapshot?.result?.finishReason || ""),
  };
  return {
    agentRunId: idHash(snapshot?.agentRunId || ""),
    sessionId: idHash(snapshot?.sessionId || ""),
    clientRequestId: String(snapshot?.clientRequestId || ""),
    status: String(snapshot?.status || ""),
    round: Number(snapshot?.round || 0),
    nextCursor: Number(snapshot?.nextCursor || 0),
    pendingToolCallCount: Array.isArray(snapshot?.pendingToolCalls)
      ? snapshot.pendingToolCalls.length
      : -1,
    terminalEventCount: events.filter((event) => (
      event?.type === "completed" || event?.type === "failed" || event?.type === "cancelled"
    )).length,
    runtimeRunIds,
    runtimeIdHashes: runtimeRunIds.map(idHash),
    toolCallIds,
    toolCallIdHashes: toolCallIds.map(idHash),
    eventProjection,
    eventProjectionHash: canonicalHash(eventProjection),
    executionProjection,
    executionProjectionHash: canonicalHash(executionProjection),
    toolResultHash: canonicalHash(executionProjection[0]?.result || {}),
    resultProjection,
    resultHash: canonicalHash(resultProjection),
  };
}

function durableToolRecordProjection(record, traceEvidence) {
  return {
    version: Number(record?.version || 0),
    status: String(record?.status || ""),
    resumeStatus: String(record?.resumeStatus || ""),
    nextSeq: Number(record?.nextSeq || 0),
    roundCount: Array.isArray(record?.rounds) ? record.rounds.length : -1,
    pendingToolCallCount: Array.isArray(record?.pendingToolCalls)
      ? record.pendingToolCalls.length
      : -1,
    eventProjection: traceEvidence.eventProjection,
    executionProjection: traceEvidence.executionProjection,
    resultProjection: traceEvidence.resultProjection,
  };
}

function sessionToolMetaProjection(messages, agentRunId, toolCallId) {
  return (Array.isArray(messages) ? messages : [])
    .filter((message) => message?.role === "tool-call" || message?.role === "tool-result")
    .map((message) => {
      const meta = message?.meta || {};
      const result = meta.result && typeof meta.result === "object"
        ? stableReadToolResult(meta.result)
        : null;
      return {
        role: String(message.role),
        toolCallId: String(meta.toolCallId || "") === toolCallId ? "tool-1" : "mismatch",
        agentRunId: meta.agentRunId == null
          ? ""
          : (String(meta.agentRunId) === agentRunId ? "agent-1" : "mismatch"),
        agentEventType: String(meta.agentEventType || ""),
        agentEventSeq: Number(meta.agentEventSeq || 0),
        action: String(meta.action || ""),
        path: String(meta.path || meta.tool?.path || ""),
        native: meta.native === true,
        replayed: Boolean(meta.replayed),
        outcome: String(meta.outcome || ""),
        result,
      };
    });
}

async function readDurableAgentRecord(h4, agentRunId) {
  const recordPath = path.join(h4.host.dataDir, "agent-runs", `${agentRunId}.json`);
  const bytes = await fs.readFile(recordPath);
  return {
    record: JSON.parse(bytes.toString("utf8")),
    byteHash: crypto.createHash("sha256").update(bytes).digest("hex"),
  };
}

async function toolDomEvidence(page) {
  const user = page.locator("#messages article.msg.user").filter({ hasText: "H4_TOOL_USER" });
  const stage = page.locator("#messages article.msg.assistant.agent-commentary")
    .filter({ hasText: "H4_TOOL_STAGE" });
  const process = page.locator("#messages article.tool-process");
  const result = page.locator("#messages .tool-process-detail pre")
    .filter({ hasText: FIXTURE_CONTENT.trim() });
  const finalAnswer = page.locator("#messages article.msg.assistant")
    .filter({ hasText: "H4_TOOL_FINAL" });
  await expect(user).toHaveCount(1);
  await expect(stage).toHaveCount(1);
  await expect(process).toHaveCount(1);
  await expect(process.locator(".tool-process-item")).toHaveCount(1);
  await expect(process).toContainText("read_file");
  await expect(result).toHaveCount(1);
  await expect(finalAnswer).toHaveCount(1);
  const ordinaryAssistants = page.locator("#messages article.msg.assistant:not(.tool-process)");
  const allAssistants = page.locator("#messages article.msg.assistant");
  await expect(ordinaryAssistants).toHaveCount(2);
  await expect(allAssistants).toHaveCount(3);
  const ordered = await page.evaluate(({ userMarker, stageMarker, resultMarker, finalMarker }) => {
    const messages = document.querySelector("#messages");
    const find = (selector, marker) => [...messages.querySelectorAll(selector)]
      .find((element) => element.textContent.includes(marker));
    const nodes = [
      find("article.msg.user", userMarker),
      find("article.msg.assistant.agent-commentary", stageMarker),
      messages.querySelector("article.tool-process"),
      find(".tool-process-detail pre", resultMarker),
      find("article.msg.assistant", finalMarker),
    ];
    return nodes.every(Boolean) && nodes.slice(0, -1).every((node, index) => (
      node === nodes[index + 1]
      || Boolean(node.compareDocumentPosition(nodes[index + 1]) & Node.DOCUMENT_POSITION_FOLLOWING)
      || node.contains(nodes[index + 1])
    ));
  }, {
    userMarker: "H4_TOOL_USER",
    stageMarker: "H4_TOOL_STAGE",
    resultMarker: FIXTURE_CONTENT.trim(),
    finalMarker: "H4_TOOL_FINAL",
  });
  expect(ordered).toBe(true);
  const visibleText = await page.locator("#messages").textContent();
  expect(countOccurrences(visibleText, "H4_TOOL_USER")).toBe(1);
  expect(countOccurrences(visibleText, "H4_TOOL_STAGE")).toBe(1);
  expect(countOccurrences(visibleText, FIXTURE_CONTENT.trim())).toBe(1);
  expect(countOccurrences(visibleText, "H4_TOOL_FINAL")).toBe(1);
  const projection = {
    sequence: [
      "H4_TOOL_USER",
      "H4_TOOL_STAGE",
      "read_file",
      FIXTURE_CONTENT.trim(),
      "H4_TOOL_FINAL",
    ],
    counts: {
      user: 1,
      stage: 1,
      ordinaryAssistant: 2,
      assistantTotal: 3,
      toolProcess: 1,
      result: 1,
      final: 1,
    },
    ordered,
  };
  return { ...projection, semanticHash: canonicalHash(projection) };
}

async function toolDetailLifecycleDomEvidence(page) {
  const messages = page.locator("#messages");
  const user = messages.locator("article.msg.user").filter({ hasText: TOOL_DETAILS_USER });
  const commentary = messages.locator("article.msg.assistant.agent-commentary")
    .filter({ hasText: TOOL_DETAILS_STAGE });
  const process = messages.locator("article.tool-process");
  const outer = process.locator("details.tool-process-stage");
  const item = process.locator("details.tool-process-item");
  const finalAnswer = messages.locator("article.msg.assistant")
    .filter({ hasText: TOOL_DETAILS_FINAL });
  const details = process.locator(".tool-process-detail pre");
  const result = details.filter({ hasText: FIXTURE_CONTENT.trim() });
  await expect(user).toHaveCount(1);
  await expect(commentary).toHaveCount(1);
  await expect(process).toHaveCount(1);
  await expect(outer).toHaveCount(1);
  await expect(item).toHaveCount(1);
  await expect(result).toHaveCount(1);
  const detailTexts = await details.allTextContents();
  const argumentText = String(detailTexts[0] || "").trim();
  const resultText = String(detailTexts[1] || "").trim();
  const processKey = await outer.getAttribute("data-tool-process-key");
  const finalCount = await finalAnswer.count();
  const ordered = await page.evaluate(({ userMarker, stageMarker, finalMarker }) => {
    const root = document.querySelector("#messages");
    const find = (selector, marker) => [...root.querySelectorAll(selector)]
      .find((element) => element.textContent.includes(marker));
    const nodes = [
      find("article.msg.user", userMarker),
      find("article.msg.assistant.agent-commentary", stageMarker),
      root.querySelector("article.tool-process"),
    ];
    const final = find("article.msg.assistant", finalMarker);
    if (final) nodes.push(final);
    return nodes.every(Boolean) && nodes.slice(0, -1).every((node, index) => (
      Boolean(node.compareDocumentPosition(nodes[index + 1]) & Node.DOCUMENT_POSITION_FOLLOWING)
    ));
  }, {
    userMarker: TOOL_DETAILS_USER,
    stageMarker: TOOL_DETAILS_STAGE,
    finalMarker: TOOL_DETAILS_FINAL,
  });
  const projection = {
    sequence: finalCount
      ? [TOOL_DETAILS_USER, TOOL_DETAILS_STAGE, "read_file", FIXTURE_CONTENT.trim(), TOOL_DETAILS_FINAL]
      : [TOOL_DETAILS_USER, TOOL_DETAILS_STAGE, "read_file", FIXTURE_CONTENT.trim()],
    counts: {
      user: 1,
      commentary: 1,
      toolProcess: 1,
      toolItem: 1,
      result: 1,
      final: finalCount,
      ordinaryAssistant: await messages.locator("article.msg.assistant:not(.tool-process)").count(),
      assistantTotal: await messages.locator("article.msg.assistant").count(),
    },
    processKey: String(processKey || ""),
    outerOpen: await outer.evaluate((element) => element.open),
    itemOpen: await item.evaluate((element) => element.open),
    stageClass: String(await outer.getAttribute("class") || ""),
    currentAction: String(await outer.getAttribute("data-current-action") || ""),
    heading: String(await outer.locator(".tool-process-stage-heading").textContent() || "").trim(),
    argumentText,
    resultText,
    formattedResult: {
      pathPresent: resultText.includes("fixture.txt"),
      sizePresent: resultText.includes("26 B"),
      fixtureContentCount: countOccurrences(resultText, FIXTURE_CONTENT.trim()),
    },
    ordered,
  };
  return {
    process,
    outer,
    item,
    finalAnswer,
    projection,
    semanticHash: canonicalHash(projection),
  };
}

async function fetchProductionJson(page, pathName) {
  return page.evaluate(async (target) => {
    const response = await fetch(target);
    let body = null;
    try {
      body = await response.json();
    } catch {}
    return { status: response.status, body };
  }, pathName);
}

function describeLoopbackRequest(request) {
  const url = new URL(request.url());
  const method = request.method();
  const agentMatch = url.pathname.match(/^\/api\/agent\/runs\/([^/]+)$/);
  const runtimeMatch = url.pathname.match(/^\/api\/runtime\/runs\/([^/]+)$/);
  if (url.pathname === "/api/agent/runs") {
    return { at: Date.now(), method, path: "/api/agent/runs", kind: "agent", idHash: "", cursor: 0 };
  }
  if (url.pathname === "/api/runtime/runs") {
    return { at: Date.now(), method, path: "/api/runtime/runs", kind: "runtime", idHash: "", cursor: 0 };
  }
  if (agentMatch) {
    return {
      at: Date.now(),
      method,
      path: "/api/agent/runs/[id]",
      kind: "agent",
      idHash: idHash(decodeURIComponent(agentMatch[1])),
      cursor: Number(url.searchParams.get("cursor") || 0),
    };
  }
  if (runtimeMatch) {
    return {
      at: Date.now(),
      method,
      path: "/api/runtime/runs/[id]",
      kind: "runtime",
      idHash: idHash(decodeURIComponent(runtimeMatch[1])),
      cursor: Number(url.searchParams.get("cursor") || 0),
    };
  }
  return { at: Date.now(), method, path: url.pathname, kind: "other", idHash: "", cursor: 0 };
}

function refreshRequestEvidence(entries) {
  const selected = entries.filter((entry) => entry.kind === "agent" || entry.kind === "runtime");
  const count = (kind, method) => selected.filter((entry) => (
    entry.kind === kind && entry.method === method
  )).length;
  return {
    agentPost: selected.filter((entry) => entry.path === "/api/agent/runs" && entry.method === "POST").length,
    agentGet: count("agent", "GET"),
    agentDelete: count("agent", "DELETE"),
    runtimePost: selected.filter((entry) => entry.path === "/api/runtime/runs" && entry.method === "POST").length,
    runtimeGet: count("runtime", "GET"),
    agentIds: [...new Set(selected.filter((entry) => entry.kind === "agent" && entry.idHash).map((entry) => entry.idHash))],
    runtimeIds: [...new Set(selected.filter((entry) => entry.kind === "runtime" && entry.idHash).map((entry) => entry.idHash))],
    runtimeCursors: selected.filter((entry) => entry.kind === "runtime" && entry.method === "GET")
      .map((entry) => entry.cursor),
  };
}

function countOccurrences(text, marker) {
  return String(text).split(marker).length - 1;
}

function summarizeLoopbackRequests(entries) {
  const counts = {};
  for (const entry of entries) {
    const key = `${entry.method} ${entry.path}`;
    counts[key] = (counts[key] || 0) + 1;
  }
  return counts;
}

function elapsedSeconds(value) {
  const match = String(value || "").match(/^(\d+)s$/);
  return match ? Number(match[1]) : -1;
}

function productionTerminalEvidence(metrics) {
  const agentRun = metrics?.production?.agentRuns?.[0] || {};
  const runtimeRun = metrics?.production?.runtimeRuns?.[0] || {};
  const eventTypes = Array.isArray(agentRun.eventTypes) ? agentRun.eventTypes : [];
  return {
    agentRun: {
      status: String(agentRun.status || ""),
      nextCursor: Number(agentRun.nextCursor || 0),
      terminalEventPresent: eventTypes.some((eventType) => (
        eventType === "completed" || eventType === "failed" || eventType === "cancelled"
      )),
    },
    runtimeRun: {
      status: String(runtimeRun.status || ""),
      nextCursor: Number(runtimeRun.nextCursor || 0),
    },
  };
}

function metricsBreadcrumbs(sanitizedStderr) {
  const allowedPhases = new Set([
    "request_received",
    "metrics_snapshot_start",
    "metrics_snapshot_done",
    "gate_snapshots_start",
    "gate_snapshots_done",
    "production_snapshot_start",
    "production_snapshot_done",
    "session_jsonl_start",
    "session_jsonl_done",
    "response_emit_start",
    "response_emit_done",
  ]);
  const allowedOutcomes = new Set(["started", "succeeded", "failed"]);
  return String(sanitizedStderr || "")
    .split(/\r?\n/)
    .filter((line) => line.startsWith("H4_METRICS "))
    .slice(-200)
    .flatMap((line) => {
      try {
        const payload = JSON.parse(line.slice("H4_METRICS ".length));
        if (!allowedPhases.has(payload.phase) || !allowedOutcomes.has(payload.outcome)) return [];
        return [{
          seq: Number(payload.seq || 0),
          phase: payload.phase,
          elapsedMs: Number(payload.elapsedMs || 0),
          durationMs: Number(payload.durationMs || 0),
          outcome: payload.outcome,
        }];
      } catch {
        return [];
      }
    });
}

function summarizeMetricsBreadcrumbs(breadcrumbs) {
  const maxDurationMs = {};
  for (const item of breadcrumbs) {
    if (!item.phase.endsWith("_done")) continue;
    const phase = item.phase.slice(0, -"_done".length);
    maxDurationMs[phase] = Math.max(maxDurationMs[phase] || 0, item.durationMs);
  }
  return {
    requestCount: breadcrumbs.filter((item) => item.phase === "request_received").length,
    maxElapsedMs: Math.max(0, ...breadcrumbs.map((item) => item.elapsedMs)),
    maxDurationMs,
  };
}

async function assertFrontendRuntime(page, runtime) {
  const expected = runtime === "classic" ? "classic-fallback" : "bundle";
  await expect(page.locator("html")).toHaveAttribute("data-frontend-runtime", expected);
  if (runtime === "bundle") {
    await expect(page.locator("html")).toHaveAttribute("data-code-frontend-ready", "true");
  }
}

async function openAutomaticClassicFallback(h4, failureMode) {
  const { page, host } = h4;
  const expectedReason = failureMode === "load" ? "bundle-load" : "bundle-init";
  const bundleUrl = `${host.ready.codeUrl}${FRONTEND_BUNDLE_PATH}`;
  let injectionCount = 0;
  const expectedBundleFailures = [];
  const mainFrameNavigations = [];

  const onRequestFailed = (request) => {
    const url = new URL(request.url());
    if (url.origin !== host.ready.codeUrl || url.pathname !== FRONTEND_BUNDLE_PATH) return;
    expectedBundleFailures.push({
      event: "requestfailed",
      method: request.method(),
      path: url.pathname,
    });
  };
  const onFrameNavigated = (frame) => {
    if (frame !== page.mainFrame()) return;
    const url = new URL(frame.url());
    if (url.origin === host.ready.codeUrl) {
      mainFrameNavigations.push(`${url.pathname}${url.search}`);
    }
  };
  const faultHandler = async (route) => {
    injectionCount += 1;
    if (failureMode === "load") {
      await route.abort();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/javascript",
      body: "/* H4 inert bundle-init fault */\n",
    });
  };

  page.on("requestfailed", onRequestFailed);
  page.on("framenavigated", onFrameNavigated);
  await page.route(bundleUrl, faultHandler, { times: 1 });
  try {
    await page.goto(`${host.ready.codeUrl}/`, { waitUntil: "commit" });
    await page.waitForURL((url) => (
      url.pathname === CLASSIC_FALLBACK_PATH
      && url.searchParams.get("fallback") === expectedReason
    ), { waitUntil: "domcontentloaded" });
    await expect(page.locator("#modelPillBtn")).toHaveAttribute("data-model", MODEL_ID);
    await page.locator("#baseUrl").evaluate((element, fakeUrl) => {
      element.value = fakeUrl;
    }, host.ready.fakeUrl);

    const finalUrl = new URL(page.url());
    expect(injectionCount).toBe(1);
    expect(finalUrl.pathname).toBe(CLASSIC_FALLBACK_PATH);
    expect(finalUrl.searchParams.get("fallback")).toBe(expectedReason);
    expect([...finalUrl.searchParams]).toEqual([["fallback", expectedReason]]);
    await expect(page.locator("html")).toHaveAttribute("data-frontend-runtime", "classic-fallback");
    expect(await page.locator("html").getAttribute("data-code-frontend-ready")).toBeNull();
    expect(mainFrameNavigations).toEqual([
      "/",
      `${CLASSIC_FALLBACK_PATH}?fallback=${expectedReason}`,
    ]);
    if (failureMode === "load") {
      expect(expectedBundleFailures).toEqual([{
        event: "requestfailed",
        method: "GET",
        path: FRONTEND_BUNDLE_PATH,
      }]);
    } else {
      expect(expectedBundleFailures).toEqual([]);
    }

    return {
      failureMode,
      expectedReason,
      injectionCount,
      expectedBundleFailures,
      mainFrameNavigations,
    };
  } finally {
    page.off("requestfailed", onRequestFailed);
    page.off("framenavigated", onFrameNavigated);
    await page.unroute(bundleUrl, faultHandler);
  }
}

async function assertRefreshIdentityContract(h4, { cancelled = false } = {}) {
  const requests = h4.requestEvidence();
  const metrics = await h4.metrics();
  expect(requests.agentPost).toBe(1);
  expect(requests.runtimePost).toBe(0);
  expect(requests.agentDelete).toBe(cancelled ? 1 : 0);
  expect(requests.runtimeGet).toBeGreaterThan(0);
  expect(requests.agentIds).toHaveLength(1);
  expect(requests.runtimeIds).toHaveLength(1);
  expect(metrics.chatRequests).toEqual([
    { scenario: "stream-refresh", stream: true, hasToolResult: false },
  ]);
  expect(metrics.toolExecutions).toEqual([]);
  expect(metrics.unsafeToolRequests).toBe(0);
  expect(metrics.production.agentRuns).toHaveLength(1);
  expect(metrics.production.runtimeRuns).toHaveLength(1);
  expect(metrics.production.agentRuns[0].agentRunId).toBe(requests.agentIds[0]);
  expect(metrics.production.runtimeRuns[0].runtimeRunId).toBe(requests.runtimeIds[0]);
  return { requests, metrics };
}

async function attachTextBestEffort(testInfo, name, filePath, payload) {
  try {
    await fs.writeFile(filePath, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
    await testInfo.attach(name, { path: filePath, contentType: "application/json" });
  } catch {}
}

async function attachScreenshotBestEffort(testInfo, page, filePath) {
  if (!page) return;
  try {
    await page.screenshot({ path: filePath, fullPage: true });
    await testInfo.attach("failure-screenshot", { path: filePath, contentType: "image/png" });
  } catch {}
}

const test = base.test.extend({
  h4: async ({ browser }, use, testInfo) => {
    const host = await startIsolatedHost();
    let context = null;
    let page = null;
    let useCompleted = false;
    const consoleEntries = [];
    const pageErrors = [];
    const loopbackRequests = [];
    const blockedRequests = [];
    const diagnosticSteps = [];
    const domTimeline = [];
    const observedAgentRunIds = new Set();
    const observedRuntimeRunIds = new Set();
    const attachPageObservers = (targetPage) => {
      targetPage.on("console", (message) => {
        consoleEntries.push({ type: message.type(), text: host.sanitize(message.text()) });
      });
      targetPage.on("pageerror", (error) => {
        pageErrors.push(host.sanitize(error.stack || error.message));
      });
    };

    try {
      expect(host.ready.environment).toEqual({
        parentSentinelPresent: false,
        sensitiveNames: [],
        homeIsIsolated: true,
      });
      context = await browser.newContext();
      await context.exposeBinding("__h4RecordDomMutation", (_source, sample) => {
        if (domTimeline.length >= 400) return;
        const sanitized = {
          at: Number(sample?.at || 0),
          text: String(sample?.text || "").slice(0, 256),
          bannerVisible: Boolean(sample?.bannerVisible),
          stopEnabled: Boolean(sample?.stopEnabled),
          elapsed: String(sample?.elapsed || "").slice(0, 32),
        };
        const previous = domTimeline.at(-1);
        if (previous && JSON.stringify(previous).replace(/"at":\d+,?/, "")
          === JSON.stringify(sanitized).replace(/"at":\d+,?/, "")) return;
        domTimeline.push(sanitized);
      });
      await context.addInitScript(({ syntheticKey, platformToken, modelId }) => {
        class OfflineMarkedRenderer {}
        let markedOptions = {};
        window.marked = {
          Renderer: OfflineMarkedRenderer,
          setOptions(options) {
            markedOptions = options || {};
          },
          parse(source) {
            const text = String(source ?? "");
            return markedOptions.renderer?.paragraph
              ? markedOptions.renderer.paragraph({ text, tokens: [{ text }] })
              : text;
          },
        };
        localStorage.setItem("code-key-config", JSON.stringify([{
          name: "H4 synthetic",
          key: syntheticKey,
          enabled: true,
          source: "manual",
        }]));
        localStorage.setItem("code-platform-auth", JSON.stringify({
          token: platformToken,
          userId: "7",
          username: "h4-user",
        }));
        localStorage.setItem("code-model", modelId);
        localStorage.setItem("code-permission-profile", "read");
        localStorage.setItem("code-lang", "en");
        document.addEventListener("DOMContentLoaded", () => {
          let lastSignature = "";
          const capture = () => {
            const text = [...document.querySelectorAll("#messages article.msg.assistant")]
              .map((element) => element.textContent || "")
              .filter((value) => value.includes("H4_STREAM_"))
              .join("\n");
            const banner = document.querySelector("#activeRunBanner");
            const stop = document.querySelector("#stopBtn");
            const elapsed = document.querySelector("#activeRunBanner [data-task-elapsed]")?.textContent || "";
            const signature = JSON.stringify({
              text,
              bannerVisible: Boolean(banner?.classList.contains("visible")),
              stopEnabled: Boolean(stop && !stop.disabled),
              elapsed,
            });
            if (signature === lastSignature) return;
            lastSignature = signature;
            window.__h4RecordDomMutation({ at: Date.now(), ...JSON.parse(signature) });
          };
          new MutationObserver(capture).observe(document.documentElement, {
            subtree: true,
            childList: true,
            characterData: true,
            attributes: true,
            attributeFilter: ["class", "disabled"],
          });
          capture();
        }, { once: true });
      }, {
        syntheticKey: host.syntheticKey,
        platformToken: host.platformToken,
        modelId: MODEL_ID,
      });

      await context.route("**/*", async (route) => {
        const request = route.request();
        const url = new URL(request.url());
        const isLoopback = ["127.0.0.1", "localhost", "::1"].includes(url.hostname);
        if (!isLoopback) {
          blockedRequests.push({ method: request.method(), path: url.pathname, reason: "non-loopback" });
          await route.abort("blockedbyclient");
          return;
        }
        loopbackRequests.push(describeLoopbackRequest(request));
        const agentMatch = url.pathname.match(/^\/api\/agent\/runs\/([^/]+)$/);
        const runtimeMatch = url.pathname.match(/^\/api\/runtime\/runs\/([^/]+)$/);
        if (agentMatch) observedAgentRunIds.add(decodeURIComponent(agentMatch[1]));
        if (runtimeMatch) observedRuntimeRunIds.add(decodeURIComponent(runtimeMatch[1]));
        if (url.pathname === "/proxy/models") {
          await route.continue({
            headers: {
              ...request.headers(),
              "x-base-url": host.ready.fakeUrl,
            },
          });
          return;
        }
        await route.continue();
      });

      page = await context.newPage();
      attachPageObservers(page);

      const h4 = {
        page,
        host,
        consoleEntries,
        pageErrors,
        loopbackRequests,
        blockedRequests,
        diagnosticSteps,
        domTimeline,
        async open(runtime) {
          const target = runtime === "classic"
            ? `${host.ready.codeUrl}/dist/frontend/index.classic.html`
            : `${host.ready.codeUrl}/`;
          diagnosticSteps.push({ step: "navigate", runtime });
          await page.goto(target, { waitUntil: "domcontentloaded" });
          await expect(page.locator("#modelPillBtn")).toHaveAttribute("data-model", MODEL_ID);
          await page.locator("#baseUrl").evaluate((element, fakeUrl) => {
            element.value = fakeUrl;
          }, host.ready.fakeUrl);
        },
        async proveNonLoopbackBlocked() {
          const result = await page.evaluate(async () => {
            const scheme = ["ht", "tp"].join("");
            const hostParts = ["192", "0", "2", "1"];
            const target = `${scheme}://${hostParts.join(".")}/h4-block-probe`;
            try {
              await fetch(target);
              return "unexpected-success";
            } catch {
              return "blocked";
            }
          });
          expect(result).toBe("blocked");
          expect(blockedRequests.filter((entry) => entry.path === "/h4-block-probe")).toEqual([
            { method: "GET", path: "/h4-block-probe", reason: "non-loopback" },
          ]);
          expect(blockedRequests.every((entry) => entry.reason === "non-loopback")).toBe(true);
          diagnosticSteps.push({ step: "network-policy-probe", result, blockedCount: blockedRequests.length });
        },
        async submit(userMarker) {
          await page.locator("#prompt").fill(userMarker);
          await page.locator("#sendBtn").click();
          await expect(page.locator("#messages article.msg.user").filter({ hasText: userMarker })).toHaveCount(1);
          await expect(page.locator("#activeRunBanner.visible .active-run-line[role='status']")).toBeVisible();
          diagnosticSteps.push({ step: "running-state-observed", userMarker });
          await host.releaseModel();
        },
        async submitGated(userMarker = STREAM_USER) {
          await page.locator("#prompt").fill(userMarker);
          await page.locator("#sendBtn").click();
          await expect(page.locator("#messages article.msg.user").filter({ hasText: userMarker })).toHaveCount(1);
          await expect(page.locator("#activeRunBanner.visible .active-run-line[role='status']")).toBeVisible();
          diagnosticSteps.push({ step: "gated-running-state-observed", userMarker });
        },
        async waitGate(gate) {
          const gates = await host.waitRefreshGate(gate);
          diagnosticSteps.push({ step: "gate-reached", gate, state: gates[gate] });
          return gates;
        },
        async releaseGate(gate) {
          const gates = await host.releaseRefreshGate(gate);
          diagnosticSteps.push({ step: "gate-released", gate, state: gates[gate] });
          return gates;
        },
        async releaseAllRefreshGates() {
          return host.releaseAllRefreshGates();
        },
        async armModelCatalogGate() {
          const gate = await host.armModelCatalogGate();
          diagnosticSteps.push({ step: "model-catalog-gate-armed", state: gate });
          return gate;
        },
        async waitModelCatalogGate() {
          const gate = await host.waitModelCatalogGate();
          diagnosticSteps.push({ step: "model-catalog-gate-reached", state: gate });
          return gate;
        },
        async releaseModelCatalogGate() {
          const gate = await host.releaseModelCatalogGate();
          diagnosticSteps.push({ step: "model-catalog-gate-released", state: gate });
          return gate;
        },
        async reloadRuntime(runtime) {
          diagnosticSteps.push({ step: "reload-started", runtime, at: Date.now() });
          await page.reload({ waitUntil: "domcontentloaded" });
          await assertFrontendRuntime(page, runtime);
          const readyAt = Date.now();
          diagnosticSteps.push({ step: "reload-ready", runtime, at: readyAt });
          return readyAt;
        },
        async metrics() {
          return host.metrics();
        },
        requestEvidence() {
          return refreshRequestEvidence(loopbackRequests);
        },
        requestBoundary() {
          return loopbackRequests.length;
        },
        requestEvidenceSince(boundary) {
          return refreshRequestEvidence(loopbackRequests.slice(Number(boundary) || 0));
        },
        requestSummarySince(boundary) {
          return summarizeLoopbackRequests(loopbackRequests.slice(Number(boundary) || 0));
        },
        controlIds() {
          return {
            agentRunIds: [...observedAgentRunIds],
            runtimeRunIds: [...observedRuntimeRunIds],
          };
        },
        async replacePage() {
          if (page && !page.isClosed()) await page.close();
          page = await context.newPage();
          attachPageObservers(page);
          this.page = page;
          return page;
        },
        async restartGeneration(options = {}) {
          const transition = await host.restartGeneration(options);
          diagnosticSteps.push({
            step: "generation-restarted",
            generationNumber: transition.generationNumber,
            distinctPids: transition.previousPid !== transition.currentPid,
            previousPortsClosed: transition.previousCleanup.portsClosed,
            rootRetained: transition.previousCleanup.rootRetained,
          });
          return transition;
        },
        evidence(label, payload) {
          console.log(`H4_EVIDENCE ${JSON.stringify({ label, ...payload })}`);
        },
      };

      await use(h4);
      useCompleted = true;
    } finally {
      const failed = !useCompleted || Boolean(testInfo.error) || testInfo.status !== testInfo.expectedStatus;
      if (failed) {
        let failureMetrics = null;
        try {
          failureMetrics = await host.metrics();
        } catch {}
        const screenshotPath = path.join(host.artifactsDir, "failure.png");
        const consolePath = path.join(host.artifactsDir, "console.json");
        const diagnosticsPath = path.join(host.artifactsDir, "sanitized-diagnostics.json");
        await attachScreenshotBestEffort(testInfo, page, screenshotPath);
        await attachTextBestEffort(testInfo, "sanitized-console", consolePath, consoleEntries);
        await attachTextBestEffort(testInfo, "sanitized-diagnostics", diagnosticsPath, {
          diagnosticSteps,
          loopbackRequests: summarizeLoopbackRequests(loopbackRequests),
          blockedRequests,
          pageErrors,
          domTimeline,
          failureMetrics,
        });
      }
      let contextCloseError = null;
      try {
        if (context) await context.close();
      } catch (error) {
        contextCloseError = error;
      }
      const cleanup = await host.stop();
      const repeatedCleanup = await host.stop();
      const breadcrumbs = metricsBreadcrumbs(cleanup.sanitizedStderr);
      const isAutomaticFallback = testInfo.title.includes("automatically falls back to classic");
      if (cleanup.cleanupErrors.length > 0) {
        const diagnostic = {
          cleanupErrors: cleanup.cleanupErrors,
          metricsBreadcrumbs: breadcrumbs,
        };
        console.log(`H4_CLEANUP_DIAGNOSTIC ${JSON.stringify(diagnostic)}`);
        try {
          await testInfo.attach("sanitized-cleanup-diagnostics", {
            body: Buffer.from(`${JSON.stringify(diagnostic, null, 2)}\n`, "utf8"),
            contentType: "application/json",
          });
        } catch {}
      }
      console.log(`H4_CLEANUP ${JSON.stringify({
        title: testInfo.title,
        portsClosed: cleanup.portsClosed,
        rootRemoved: cleanup.rootRemoved,
        temporaryFiles: cleanup.temporaryFiles,
        childPidRecorded: Number.isInteger(cleanup.childPid),
        childExited: cleanup.childExited,
        activeChildCount: cleanup.activeChildCount,
        ...(isAutomaticFallback
          ? { metricsPhaseSummary: summarizeMetricsBreadcrumbs(breadcrumbs) }
          : {}),
      })}`);
      expect(repeatedCleanup).toBe(cleanup);
      expect(cleanup.childExited).toBe(true);
      expect(cleanup.activeChildCount).toBe(0);
      expect(cleanup.portsClosed).toEqual([true, true]);
      expect(cleanup.rootRemoved).toBe(true);
      expect(cleanup.cleanupErrors).toEqual([]);
      if (contextCloseError) throw contextCloseError;
    }
  },
});

test("default bundle completes first plain-text send", async ({ h4 }) => {
  const { page } = h4;
  await h4.open("bundle");
  await expect(page.locator("html")).toHaveAttribute("data-frontend-runtime", "bundle");
  await expect(page.locator("html")).toHaveAttribute("data-code-frontend-ready", "true");
  await h4.proveNonLoopbackBlocked();
  await h4.submit("H4_PLAIN_USER");

  const finalAnswer = page.locator("#messages article.msg.assistant").filter({ hasText: "H4_PLAIN_FINAL" });
  await expect(finalAnswer).toHaveCount(1);
  const text = await page.locator("#messages").textContent();
  expect(countOccurrences(text, "H4_PLAIN_USER")).toBe(1);
  expect(countOccurrences(text, "H4_PLAIN_FINAL")).toBe(1);
  const metrics = await h4.metrics();
  expect(metrics.chatRequests).toEqual([
    { scenario: "plain-text", stream: true, hasToolResult: false },
  ]);
  expect(metrics.toolExecutions).toEqual([]);
  expect(metrics.unsafeToolRequests).toBe(0);
  expect(h4.pageErrors).toEqual([]);
  h4.evidence("bundle-plain", {
    runtime: "bundle",
    ready: true,
    chatRequests: metrics.chatRequests.length,
    toolExecutions: 0,
    dom: { user: 1, final: 1, runningObserved: true },
    blockedNonLoopback: h4.blockedRequests.length,
  });
});

test("completed AgentRun reloads uniquely across real service processes", async ({ h4 }) => {
  let page = h4.page;
  const generationABoundary = h4.requestBoundary();
  await h4.open("bundle");
  await assertFrontendRuntime(page, "bundle");
  await h4.submit("H4_PLAIN_USER");

  const userA = page.locator("#messages article.msg.user").filter({ hasText: "H4_PLAIN_USER" });
  const assistantA = page.locator("#messages article.msg.assistant");
  const finalA = assistantA.filter({ hasText: "H4_PLAIN_FINAL" });
  await expect(userA).toHaveCount(1);
  await expect(assistantA).toHaveCount(1);
  await expect(finalA).toHaveCount(1);
  await expect(page.locator("#activeRunBanner.visible")).toHaveCount(0);

  const activeSession = page.locator("#sessionList .session-row.active button.session-main");
  await expect(activeSession).toHaveCount(1);
  const sessionId = await activeSession.getAttribute("data-session-id");
  expect(sessionId).toBeTruthy();

  await expect.poll(async () => {
    const metrics = await h4.metrics();
    return productionTerminalEvidence(metrics);
  }).toEqual({
    agentRun: { status: "completed", nextCursor: 4, terminalEventPresent: true },
    runtimeRun: { status: "completed", nextCursor: 3 },
  });

  const controlIds = h4.controlIds();
  expect(controlIds.agentRunIds).toHaveLength(1);
  expect(controlIds.runtimeRunIds).toHaveLength(1);
  const agentRunId = controlIds.agentRunIds[0];
  const runtimeRunId = controlIds.runtimeRunIds[0];

  const agentResponseA = await fetchProductionJson(
    page,
    `/api/agent/runs/${encodeURIComponent(agentRunId)}?cursor=0&wait=0`,
  );
  const runtimeResponseA = await fetchProductionJson(
    page,
    `/api/runtime/runs/${encodeURIComponent(runtimeRunId)}?cursor=0&wait=0`,
  );
  expect(agentResponseA.status).toBe(200);
  expect(runtimeResponseA.status).toBe(200);
  expect(agentResponseA.body.status).toBe("completed");
  expect(agentResponseA.body.result?.content).toBe("H4_PLAIN_FINAL");
  expect(agentResponseA.body.clientRequestId).toBe("");
  expect(runtimeResponseA.body.status).toBe("completed");
  expect(runtimeResponseA.body.result?.content).toBe("H4_PLAIN_FINAL");

  const agentEvidenceA = durableAgentEvidence(agentResponseA.body);
  expect(agentEvidenceA).toMatchObject({
    agentRunId: idHash(agentRunId),
    sessionId: idHash(sessionId),
    status: "completed",
    nextCursor: 4,
    eventTypes: ["created", "model_started", "model_completed", "completed"],
    terminalEventCount: 1,
  });
  expect(new Set(agentEvidenceA.runtimeIds)).toEqual(new Set([idHash(runtimeRunId)]));
  expect(agentEvidenceA.runtimeIds).toHaveLength(2);

  let sessionResponseA = null;
  await expect.poll(async () => {
    sessionResponseA = await fetchProductionJson(
      page,
      `/api/sessions/${encodeURIComponent(sessionId)}`,
    );
    const projection = roleContentProjection(sessionResponseA.body?.messages);
    return {
      status: sessionResponseA.status,
      roles: projection.map((message) => message.role),
      userCount: projection.filter((message) => message.content === "H4_PLAIN_USER").length,
      finalCount: projection.filter((message) => message.content === "H4_PLAIN_FINAL").length,
      runStateKeys: Object.keys(sessionResponseA.body?.runState || {}).sort(),
    };
  }).toEqual({
    status: 200,
    roles: ["user", "assistant"],
    userCount: 1,
    finalCount: 1,
    runStateKeys: [],
  });
  const sessionRoleContentHashA = canonicalHash(
    roleContentProjection(sessionResponseA.body.messages),
  );
  const metricsA = await h4.metrics();
  const requestsA = h4.requestEvidenceSince(generationABoundary);
  expect(requestsA.agentPost).toBe(1);
  expect(requestsA.runtimePost).toBe(0);
  expect(requestsA.agentIds).toEqual([idHash(agentRunId)]);
  expect(requestsA.runtimeIds).toEqual([idHash(runtimeRunId)]);
  expect(metricsA.chatRequests).toEqual([
    { scenario: "plain-text", stream: true, hasToolResult: false },
  ]);
  expect(metricsA.toolExecutions).toEqual([]);
  expect(metricsA.unsafeToolRequests).toBe(0);

  const processAPid = h4.host.childPid;
  await page.close();
  const generationBBoundary = h4.requestBoundary();
  const transition = await h4.restartGeneration();
  expect(transition.previousPid).toBe(processAPid);
  expect(transition.currentPid).not.toBe(transition.previousPid);
  expect(transition.previousCleanup.childExited).toBe(true);
  expect(transition.previousCleanup.portsClosed).toEqual([true, true]);
  expect(transition.previousCleanup.rootRetained).toBe(true);
  expect(transition.previousCleanup.rootRemoved).toBe(false);
  expect(transition.previousCleanup.cleanupErrors).toEqual([]);
  expect(h4.host.generationNumber).toBe(2);

  page = await h4.replacePage();
  await page.goto(`${h4.host.ready.codeUrl}/`, { waitUntil: "domcontentloaded" });
  await assertFrontendRuntime(page, "bundle");
  await expect(page.locator("#modelPillBtn")).toHaveAttribute("data-model", MODEL_ID);
  await page.locator("#baseUrl").evaluate((element, fakeUrl) => {
    element.value = fakeUrl;
  }, h4.host.ready.fakeUrl);

  const persistedSessionButton = page.locator("#sessionList button.session-main")
    .filter({ hasText: "H4_PLAIN_USER" });
  await expect(persistedSessionButton).toHaveCount(1);
  await expect(persistedSessionButton).toHaveAttribute("data-session-id", sessionId);
  await persistedSessionButton.click();

  const userB = page.locator("#messages article.msg.user").filter({ hasText: "H4_PLAIN_USER" });
  const assistantB = page.locator("#messages article.msg.assistant");
  const finalB = assistantB.filter({ hasText: "H4_PLAIN_FINAL" });
  await expect(userB).toHaveCount(1);
  await expect(assistantB).toHaveCount(1);
  await expect(finalB).toHaveCount(1);
  const visibleTextB = await page.locator("#messages").textContent();
  expect(countOccurrences(visibleTextB, "H4_PLAIN_USER")).toBe(1);
  expect(countOccurrences(visibleTextB, "H4_PLAIN_FINAL")).toBe(1);
  expect(countOccurrences(visibleTextB, "[Output paused]")).toBe(0);
  await expect(page.locator("#activeRunBanner.visible")).toHaveCount(0);
  await expect(page.locator("#stopBtn")).toBeDisabled();

  const agentResponseB = await fetchProductionJson(
    page,
    `/api/agent/runs/${encodeURIComponent(agentRunId)}?cursor=0&wait=0`,
  );
  const runtimeResponseB = await fetchProductionJson(
    page,
    `/api/runtime/runs/${encodeURIComponent(runtimeRunId)}?cursor=0&wait=0`,
  );
  const sessionResponseB = await fetchProductionJson(
    page,
    `/api/sessions/${encodeURIComponent(sessionId)}`,
  );
  expect(agentResponseB.status).toBe(200);
  expect(runtimeResponseB.status).toBe(404);
  expect(sessionResponseB.status).toBe(200);
  expect(agentResponseB.body.status).toBe("completed");
  expect(agentResponseB.body.result?.content).toBe("H4_PLAIN_FINAL");
  expect(agentResponseB.body.activeRuntimeRunId).toBe("");

  const agentEvidenceB = durableAgentEvidence(agentResponseB.body);
  expect(agentEvidenceB).toEqual(agentEvidenceA);
  const sessionRoleContentHashB = canonicalHash(
    roleContentProjection(sessionResponseB.body.messages),
  );
  expect(sessionRoleContentHashB).toBe(sessionRoleContentHashA);
  expect(roleContentProjection(sessionResponseB.body.messages)).toEqual(
    roleContentProjection(sessionResponseA.body.messages),
  );

  const metricsB = await h4.metrics();
  const requestsB = h4.requestEvidenceSince(generationBBoundary);
  expect(requestsB.agentPost).toBe(0);
  expect(requestsB.runtimePost).toBe(0);
  expect(requestsB.agentDelete).toBe(0);
  expect(requestsB.agentIds).toEqual([idHash(agentRunId)]);
  expect(requestsB.runtimeIds).toEqual([idHash(runtimeRunId)]);
  expect(metricsB.chatRequests).toEqual([]);
  expect(metricsB.toolExecutions).toEqual([]);
  expect(metricsB.unsafeToolRequests).toBe(0);
  expect(metricsB.production.agentRuns).toHaveLength(1);
  expect(metricsB.production.agentRuns[0]).toMatchObject({
    agentRunId: idHash(agentRunId),
    status: "completed",
    nextCursor: 4,
    eventTypes: ["created", "model_started", "model_completed", "completed"],
    activeRuntimeRunId: "",
  });
  expect(metricsB.production.runtimeRuns).toEqual([]);
  expect(h4.pageErrors).toEqual([]);

  h4.evidence("completed-agent-run-cross-process", {
    processBoundary: {
      distinctPids: transition.previousPid !== transition.currentPid,
      previousPortsClosed: transition.previousCleanup.portsClosed,
      rootRetained: transition.previousCleanup.rootRetained,
      generationNumber: transition.generationNumber,
    },
    generationA: {
      requests: requestsA,
      agent: agentEvidenceA,
      runtime: {
        id: idHash(runtimeRunId),
        status: runtimeResponseA.body.status,
        nextCursor: runtimeResponseA.body.nextCursor,
      },
      chatRequests: metricsA.chatRequests.length,
      toolExecutions: metricsA.toolExecutions.length,
      sessionRoleContentHash: sessionRoleContentHashA,
    },
    generationB: {
      requests: requestsB,
      agent: agentEvidenceB,
      oldRuntimeStatus: runtimeResponseB.status,
      chatRequests: metricsB.chatRequests.length,
      toolExecutions: metricsB.toolExecutions.length,
      sessionRoleContentHash: sessionRoleContentHashB,
    },
    dom: {
      user: 1,
      assistant: 1,
      final: 1,
      paused: 0,
      activeBanner: 0,
      stopDisabled: true,
    },
  });
});

test("completed AgentRun with tool trace reloads without tool re-execution across processes", async ({ h4 }) => {
  let page = h4.page;
  const generationABoundary = h4.requestBoundary();
  await h4.open("bundle");
  await assertFrontendRuntime(page, "bundle");
  await h4.proveNonLoopbackBlocked();
  await h4.submit("H4_TOOL_USER");

  const domA = await toolDomEvidence(page);
  await expect(page.locator("#activeRunBanner.visible")).toHaveCount(0);
  await expect(page.locator("#stopBtn")).toBeDisabled();

  const activeSession = page.locator("#sessionList .session-row.active button.session-main");
  await expect(activeSession).toHaveCount(1);
  const sessionId = await activeSession.getAttribute("data-session-id");
  expect(sessionId).toBeTruthy();

  await expect.poll(async () => {
    const metrics = await h4.metrics();
    const agentRun = metrics.production.agentRuns[0] || {};
    const runtimeRuns = metrics.production.runtimeRuns || [];
    return {
      agentRunCount: metrics.production.agentRuns.length,
      agentStatus: agentRun.status,
      agentNextCursor: agentRun.nextCursor,
      agentEventTypes: agentRun.eventTypes,
      runtimeRunCount: runtimeRuns.length,
      runtimeStatuses: runtimeRuns.map((run) => run.status).sort(),
    };
  }).toEqual({
    agentRunCount: 1,
    agentStatus: "completed",
    agentNextCursor: 9,
    agentEventTypes: [
      "created",
      "model_started",
      "model_completed",
      "tool_started",
      "tool_completed",
      "model_pending",
      "model_started",
      "model_completed",
      "completed",
    ],
    runtimeRunCount: 2,
    runtimeStatuses: ["completed", "completed"],
  });

  const controlIds = h4.controlIds();
  expect(controlIds.agentRunIds).toHaveLength(1);
  const agentRunId = controlIds.agentRunIds[0];
  const agentResponseA = await fetchProductionJson(
    page,
    `/api/agent/runs/${encodeURIComponent(agentRunId)}?cursor=0&wait=0`,
  );
  expect(agentResponseA.status).toBe(200);
  expect(agentResponseA.body.status).toBe("completed");
  expect(agentResponseA.body.result?.content).toBe("H4_TOOL_FINAL");
  expect(agentResponseA.body.activeRuntimeRunId).toBe("");
  expect(agentResponseA.body.pendingToolCalls).toEqual([]);
  expect(agentResponseA.body.nextCursor).toBe(9);
  expect(agentResponseA.body.round).toBe(2);

  const traceA = durableToolTraceEvidence(agentResponseA.body);
  expect(traceA).toMatchObject({
    agentRunId: idHash(agentRunId),
    sessionId: idHash(sessionId),
    status: "completed",
    round: 2,
    nextCursor: 9,
    pendingToolCallCount: 0,
    terminalEventCount: 1,
  });
  expect(traceA.runtimeRunIds).toHaveLength(2);
  expect(new Set(traceA.runtimeRunIds).size).toBe(2);
  expect(traceA.toolCallIds).toHaveLength(1);
  const toolCallId = traceA.toolCallIds[0];
  expect(toolCallId).toBeTruthy();
  expect(traceA.executionProjection).toEqual([{
    toolCallId: "tool-1",
    name: "read_file",
    arguments: { path: "fixture.txt" },
    status: "completed",
    outcome: "succeeded",
    result: {
      ok: true,
      action: "read_file",
      path: "fixture.txt",
      content: FIXTURE_CONTENT,
      size: 26,
      truncated: false,
      lineRange: null,
    },
  }]);
  expect(traceA.eventProjection.map((event) => event.type)).toEqual([
    "created",
    "model_started",
    "model_completed",
    "tool_started",
    "tool_completed",
    "model_pending",
    "model_started",
    "model_completed",
    "completed",
  ]);
  expect(traceA.eventProjection.filter((event) => event.type === "tool_started")).toHaveLength(1);
  expect(traceA.eventProjection.filter((event) => event.type === "tool_completed")).toEqual([{
    seq: 5,
    type: "tool_completed",
    outcome: "succeeded",
    toolCallId: "tool-1",
    name: "read_file",
    arguments: { path: "fixture.txt" },
    replayed: false,
    result: traceA.executionProjection[0].result,
  }]);
  expect(traceA.eventProjection.filter((event) => event.type === "model_started")).toHaveLength(2);
  expect(traceA.eventProjection.filter((event) => event.type === "model_completed")).toHaveLength(2);

  const runtimeEvidenceA = [];
  for (const [index, runtimeRunId] of traceA.runtimeRunIds.entries()) {
    const response = await fetchProductionJson(
      page,
      `/api/runtime/runs/${encodeURIComponent(runtimeRunId)}?cursor=0&wait=0`,
    );
    expect(response.status).toBe(200);
    expect(response.body.status).toBe("completed");
    runtimeEvidenceA.push({
      round: index + 1,
      runtimeRunId: idHash(runtimeRunId),
      status: response.body.status,
      nextCursor: response.body.nextCursor,
      content: response.body.result?.content,
    });
  }
  expect(runtimeEvidenceA).toEqual([
    {
      round: 1,
      runtimeRunId: traceA.runtimeIdHashes[0],
      status: "completed",
      nextCursor: 4,
      content: "H4_TOOL_STAGE",
    },
    {
      round: 2,
      runtimeRunId: traceA.runtimeIdHashes[1],
      status: "completed",
      nextCursor: 3,
      content: "H4_TOOL_FINAL",
    },
  ]);

  const durableA = await readDurableAgentRecord(h4, agentRunId);
  expect(durableA.record.id).toBe(agentRunId);
  expect(durableA.record.status).toBe("completed");
  expect(durableA.record.pendingToolCalls).toEqual([]);
  expect(durableA.record.nextSeq).toBe(10);
  expect(durableA.record.events).toHaveLength(9);
  expect(durableA.record.events.at(-1)?.seq).toBe(9);
  expect(Object.keys(durableA.record.toolExecutions || {})).toEqual([toolCallId]);
  const durableProjectionA = durableToolRecordProjection(durableA.record, traceA);
  const durableProjectionHashA = canonicalHash(durableProjectionA);

  let sessionResponseA = null;
  await expect.poll(async () => {
    sessionResponseA = await fetchProductionJson(
      page,
      `/api/sessions/${encodeURIComponent(sessionId)}`,
    );
    const messages = Array.isArray(sessionResponseA.body?.messages)
      ? sessionResponseA.body.messages
      : [];
    const projection = roleContentProjection(messages);
    const toolCalls = messages.filter((message) => message?.role === "tool-call");
    const toolResults = messages.filter((message) => message?.role === "tool-result");
    return {
      status: sessionResponseA.status,
      roles: projection.map((message) => message.role),
      userCount: projection.filter((message) => message.content === "H4_TOOL_USER").length,
      stageCount: projection.filter((message) => message.content === "H4_TOOL_STAGE").length,
      toolCallCount: toolCalls.length,
      toolResultCount: toolResults.length,
      toolCallMatches: toolCalls.filter((message) => (
        message?.meta?.toolCallId === toolCallId
        && message?.meta?.agentRunId === agentRunId
        && message?.meta?.action === "read_file"
        && message?.meta?.tool?.action === "read_file"
        && message?.meta?.tool?.path === "fixture.txt"
      )).length,
      toolResultMatches: toolResults.filter((message) => (
        message?.meta?.toolCallId === toolCallId
        && message?.meta?.agentRunId === agentRunId
        && message?.meta?.action === "read_file"
        && message?.meta?.path === "fixture.txt"
        && countOccurrences(message?.content, FIXTURE_CONTENT.trim()) === 1
      )).length,
      fixtureContentCount: countOccurrences(
        projection.map((message) => String(message.content || "")).join("\n"),
        FIXTURE_CONTENT.trim(),
      ),
      finalCount: projection.filter((message) => message.content === "H4_TOOL_FINAL").length,
      runStateKeys: Object.keys(sessionResponseA.body?.runState || {}).sort(),
    };
  }).toEqual({
    status: 200,
    roles: ["user", "assistant", "tool-call", "tool-result", "assistant"],
    userCount: 1,
    stageCount: 1,
    toolCallCount: 1,
    toolResultCount: 1,
    toolCallMatches: 1,
    toolResultMatches: 1,
    fixtureContentCount: 1,
    finalCount: 1,
    runStateKeys: [],
  });
  const sessionProjectionA = roleContentProjection(sessionResponseA.body.messages);
  const sessionRoleContentHashA = canonicalHash(sessionProjectionA);
  const sessionToolMetaA = sessionToolMetaProjection(
    sessionResponseA.body.messages,
    agentRunId,
    toolCallId,
  );
  expect(sessionToolMetaA).toEqual([
    {
      role: "tool-call",
      toolCallId: "tool-1",
      agentRunId: "agent-1",
      agentEventType: "tool_started",
      agentEventSeq: 4,
      action: "read_file",
      path: "fixture.txt",
      native: true,
      replayed: false,
      outcome: "",
      result: null,
    },
    {
      role: "tool-result",
      toolCallId: "tool-1",
      agentRunId: "agent-1",
      agentEventType: "tool_completed",
      agentEventSeq: 5,
      action: "read_file",
      path: "fixture.txt",
      native: true,
      replayed: false,
      outcome: "succeeded",
      result: traceA.executionProjection[0].result,
    },
  ]);
  const sessionToolMetaHashA = canonicalHash(sessionToolMetaA);

  const metricsA = await h4.metrics();
  const requestsA = h4.requestEvidenceSince(generationABoundary);
  expect(requestsA.agentPost).toBe(1);
  expect(requestsA.runtimePost).toBe(0);
  expect(requestsA.agentIds).toEqual([idHash(agentRunId)]);
  expect(new Set(requestsA.runtimeIds)).toEqual(new Set(traceA.runtimeIdHashes));
  expect(metricsA.chatRequests).toEqual([
    { scenario: "tool-call", stream: true, hasToolResult: false },
    { scenario: "tool-final", stream: true, hasToolResult: true },
  ]);
  expect(metricsA.toolExecutions).toEqual([{ action: "read_file", path: "fixture.txt" }]);
  expect(metricsA.unsafeToolRequests).toBe(0);

  const processAPid = h4.host.childPid;
  await page.close();
  const generationBBoundary = h4.requestBoundary();
  const transition = await h4.restartGeneration();
  expect(transition.previousPid).toBe(processAPid);
  expect(transition.currentPid).not.toBe(transition.previousPid);
  expect(transition.previousCleanup.childExited).toBe(true);
  expect(transition.previousCleanup.portsClosed).toEqual([true, true]);
  expect(transition.previousCleanup.rootRetained).toBe(true);
  expect(transition.previousCleanup.rootRemoved).toBe(false);
  expect(transition.previousCleanup.cleanupErrors).toEqual([]);
  expect(h4.host.generationNumber).toBe(2);

  page = await h4.replacePage();
  await page.goto(`${h4.host.ready.codeUrl}/`, { waitUntil: "domcontentloaded" });
  await assertFrontendRuntime(page, "bundle");
  await expect(page.locator("#modelPillBtn")).toHaveAttribute("data-model", MODEL_ID);
  await page.locator("#baseUrl").evaluate((element, fakeUrl) => {
    element.value = fakeUrl;
  }, h4.host.ready.fakeUrl);

  const persistedSessionButton = page.locator("#sessionList button.session-main")
    .filter({ hasText: "H4_TOOL_USER" });
  await expect(persistedSessionButton).toHaveCount(1);
  await expect(persistedSessionButton).toHaveAttribute("data-session-id", sessionId);
  await persistedSessionButton.click();

  const domB = await toolDomEvidence(page);
  expect(domB).toEqual(domA);
  const visibleTextB = await page.locator("#messages").textContent();
  expect(countOccurrences(visibleTextB, "[Output paused]")).toBe(0);
  await expect(page.locator("#activeRunBanner.visible")).toHaveCount(0);
  await expect(page.locator("#stopBtn")).toBeDisabled();

  const agentResponseB = await fetchProductionJson(
    page,
    `/api/agent/runs/${encodeURIComponent(agentRunId)}?cursor=0&wait=0`,
  );
  expect(agentResponseB.status).toBe(200);
  expect(agentResponseB.body.status).toBe("completed");
  expect(agentResponseB.body.activeRuntimeRunId).toBe("");
  expect(agentResponseB.body.clientRequestId).toBe(agentResponseA.body.clientRequestId);
  expect(agentResponseB.body.pendingToolCalls).toEqual([]);
  const traceB = durableToolTraceEvidence(agentResponseB.body);
  expect(traceB).toEqual(traceA);
  expect(traceB.toolCallIds).toEqual([toolCallId]);

  const oldRuntimeEvidenceB = [];
  for (const [index, runtimeRunId] of traceA.runtimeRunIds.entries()) {
    const response = await fetchProductionJson(
      page,
      `/api/runtime/runs/${encodeURIComponent(runtimeRunId)}?cursor=0&wait=0`,
    );
    oldRuntimeEvidenceB.push({
      round: index + 1,
      runtimeRunId: idHash(runtimeRunId),
      status: response.status,
    });
  }
  expect(oldRuntimeEvidenceB).toEqual([
    { round: 1, runtimeRunId: traceA.runtimeIdHashes[0], status: 404 },
    { round: 2, runtimeRunId: traceA.runtimeIdHashes[1], status: 404 },
  ]);

  const sessionResponseB = await fetchProductionJson(
    page,
    `/api/sessions/${encodeURIComponent(sessionId)}`,
  );
  expect(sessionResponseB.status).toBe(200);
  const sessionProjectionB = roleContentProjection(sessionResponseB.body.messages);
  const sessionRoleContentHashB = canonicalHash(sessionProjectionB);
  expect(sessionProjectionB).toEqual(sessionProjectionA);
  expect(sessionRoleContentHashB).toBe(sessionRoleContentHashA);
  const sessionToolMetaB = sessionToolMetaProjection(
    sessionResponseB.body.messages,
    agentRunId,
    toolCallId,
  );
  const sessionToolMetaHashB = canonicalHash(sessionToolMetaB);
  expect(sessionToolMetaB).toEqual(sessionToolMetaA);
  expect(sessionToolMetaHashB).toBe(sessionToolMetaHashA);

  const durableB = await readDurableAgentRecord(h4, agentRunId);
  const durableProjectionB = durableToolRecordProjection(durableB.record, traceB);
  expect(durableB.byteHash).toBe(durableA.byteHash);
  expect(durableB.record.nextSeq).toBe(10);
  expect(canonicalHash(durableProjectionB)).toBe(durableProjectionHashA);

  const metricsB = await h4.metrics();
  const requestsB = h4.requestEvidenceSince(generationBBoundary);
  expect(requestsB.agentPost).toBe(0);
  expect(requestsB.runtimePost).toBe(0);
  expect(requestsB.agentDelete).toBe(0);
  expect(requestsB.agentIds).toEqual([idHash(agentRunId)]);
  expect(new Set(requestsB.runtimeIds)).toEqual(new Set(traceA.runtimeIdHashes));
  expect(metricsB.chatRequests).toEqual([]);
  expect(metricsB.toolExecutions).toEqual([]);
  expect(metricsB.unsafeToolRequests).toBe(0);
  expect(metricsB.production.agentRuns).toHaveLength(1);
  expect(metricsB.production.agentRuns[0]).toMatchObject({
    agentRunId: idHash(agentRunId),
    status: "completed",
    nextCursor: 9,
    eventTypes: traceA.eventProjection.map((event) => event.type),
    activeRuntimeRunId: "",
  });
  expect(metricsB.production.runtimeRuns).toEqual([]);
  expect(h4.pageErrors).toEqual([]);

  const semanticHashes = {
    toolResult: traceA.toolResultHash,
    executionProjection: traceA.executionProjectionHash,
    eventProjection: traceA.eventProjectionHash,
    durableProjection: durableProjectionHashA,
    sessionRoleContent: sessionRoleContentHashA,
    sessionToolMeta: sessionToolMetaHashA,
    domSemantic: domA.semanticHash,
    finalResult: traceA.resultHash,
  };
  expect(semanticHashes).toEqual(H4_5B1_SEMANTIC_HASHES);

  h4.evidence("completed-tool-trace-cross-process", {
    processBoundary: {
      distinctPids: transition.previousPid !== transition.currentPid,
      previousPortsClosed: transition.previousCleanup.portsClosed,
      rootRetained: transition.previousCleanup.rootRetained,
      generationNumber: transition.generationNumber,
    },
    identity: {
      agentRunId: idHash(agentRunId),
      clientRequestId: traceA.clientRequestId,
      toolCallId: idHash(toolCallId),
      runtimeRunIds: traceA.runtimeIdHashes,
    },
    generationA: {
      requests: requestsA,
      chatRequests: metricsA.chatRequests.length,
      toolExecutions: metricsA.toolExecutions.length,
      status: traceA.status,
      nextCursor: traceA.nextCursor,
      nextSeq: durableA.record.nextSeq,
    },
    generationB: {
      requests: requestsB,
      chatRequests: metricsB.chatRequests.length,
      toolExecutions: metricsB.toolExecutions.length,
      oldRuntimes: oldRuntimeEvidenceB,
      status: traceB.status,
      nextCursor: traceB.nextCursor,
      nextSeq: durableB.record.nextSeq,
    },
    hashes: {
      ...semanticHashes,
      durableRecordBytes: durableA.byteHash,
    },
    events: traceA.eventProjection.map((event) => event.type),
    runtimeRounds: runtimeEvidenceA,
    dom: domA,
    completionBoundary: "terminal tool trace reloaded without process-B tool execution",
  });
});

test("default bundle executes one read-only tool without duplicate DOM", async ({ h4 }) => {
  const { page } = h4;
  await h4.open("bundle");
  await expect(page.locator("html")).toHaveAttribute("data-frontend-runtime", "bundle");
  await expect(page.locator("html")).toHaveAttribute("data-code-frontend-ready", "true");
  await h4.proveNonLoopbackBlocked();
  await h4.submit("H4_TOOL_USER");

  const finalAnswer = page.locator("#messages article.msg.assistant").filter({ hasText: "H4_TOOL_FINAL" });
  await expect(finalAnswer).toHaveCount(1);
  const stage = page.locator("#messages article.msg.assistant.agent-commentary").filter({ hasText: "H4_TOOL_STAGE" });
  const process = page.locator("#messages article.tool-process");
  const result = page.locator("#messages .tool-process-detail pre").filter({ hasText: FIXTURE_CONTENT.trim() });
  await expect(stage).toHaveCount(1);
  await expect(process).toHaveCount(1);
  await expect(process.locator(".tool-process-item")).toHaveCount(1);
  await expect(result).toHaveCount(1);
  const user = page.locator("#messages article.msg.user").filter({ hasText: "H4_TOOL_USER" });
  const ordered = await page.evaluate(({ userMarker, stageMarker, finalMarker }) => {
    const messages = document.querySelector("#messages");
    const find = (selector, marker) => [...messages.querySelectorAll(selector)]
      .find((element) => element.textContent.includes(marker));
    const nodes = [
      find("article.msg.user", userMarker),
      find("article.msg.assistant.agent-commentary", stageMarker),
      messages.querySelector("article.tool-process"),
      find("article.msg.assistant", finalMarker),
    ];
    return nodes.every(Boolean) && nodes.slice(0, -1).every((node, index) => (
      Boolean(node.compareDocumentPosition(nodes[index + 1]) & Node.DOCUMENT_POSITION_FOLLOWING)
    ));
  }, {
    userMarker: "H4_TOOL_USER",
    stageMarker: "H4_TOOL_STAGE",
    finalMarker: "H4_TOOL_FINAL",
  });
  expect(ordered).toBe(true);
  await expect(user).toHaveCount(1);
  const text = await page.locator("#messages").textContent();
  expect(countOccurrences(text, "H4_TOOL_STAGE")).toBe(1);
  expect(countOccurrences(text, FIXTURE_CONTENT.trim())).toBe(1);
  expect(countOccurrences(text, "H4_TOOL_FINAL")).toBe(1);
  const metrics = await h4.metrics();
  expect(metrics.chatRequests).toEqual([
    { scenario: "tool-call", stream: true, hasToolResult: false },
    { scenario: "tool-final", stream: true, hasToolResult: true },
  ]);
  expect(metrics.toolExecutions).toEqual([{ action: "read_file", path: "fixture.txt" }]);
  expect(metrics.unsafeToolRequests).toBe(0);
  expect(h4.pageErrors).toEqual([]);
  h4.evidence("bundle-read-tool", {
    runtime: "bundle",
    ready: true,
    chatRequests: metrics.chatRequests.length,
    toolExecutions: metrics.toolExecutions.length,
    dom: { user: 1, stage: 1, tool: 1, result: 1, final: 1, ordered },
    blockedNonLoopback: h4.blockedRequests.length,
  });
});

async function exerciseToolDetailActiveToTerminal(h4, runtime) {
  const { page } = h4;
  const requestBoundary = h4.requestBoundary();
  await h4.open(runtime);
  await assertFrontendRuntime(page, runtime);
  if (runtime === "classic") {
    expect(await page.locator("html").getAttribute("data-code-frontend-ready")).toBeNull();
  }
  await h4.proveNonLoopbackBlocked();
  await h4.submitGated(TOOL_DETAILS_USER);
  const firstGateSnapshot = await h4.waitGate(TOOL_FINAL_DELTA_GATE);

  const initialDom = await toolDetailLifecycleDomEvidence(page);
  expect(initialDom.projection).toMatchObject({
    counts: {
      user: 1,
      commentary: 1,
      toolProcess: 1,
      toolItem: 1,
      result: 1,
      final: 0,
      ordinaryAssistant: 1,
      assistantTotal: 2,
    },
    outerOpen: false,
    itemOpen: false,
    currentAction: "read_file",
    ordered: true,
  });
  expect(initialDom.projection.processKey).toBe("0:1");
  expect(initialDom.projection.stageClass.split(/\s+/)).toContain("running");
  expect(initialDom.projection.heading).toContain("Read File");
  expect(initialDom.projection.heading).toContain("fixture.txt");
  expect(initialDom.projection.argumentText).toContain('"path": "fixture.txt"');
  expect(initialDom.projection.formattedResult).toEqual({
    pathPresent: true,
    sizePresent: true,
    fixtureContentCount: 1,
  });
  expect(initialDom.projection.resultText).toContain(FIXTURE_CONTENT.trim());
  expect(firstGateSnapshot[TOOL_FINAL_DELTA_GATE]).toMatchObject({
    reached: true,
    released: false,
  });

  await expect.poll(() => h4.controlIds().agentRunIds.length).toBe(1);
  const agentRunId = h4.controlIds().agentRunIds[0];
  const activeAgent = await fetchProductionJson(
    page,
    `/api/agent/runs/${encodeURIComponent(agentRunId)}?cursor=0&wait=0`,
  );
  expect(activeAgent.status).toBe(200);
  expect(activeAgent.body.status).toBe("model");
  expect(typeof activeAgent.body.activeRuntimeRunId).toBe("string");
  expect(activeAgent.body.activeRuntimeRunId).not.toBe("");
  const activeModelStartedEvents = activeAgent.body.events.filter((event) => (
    event?.type === "model_started"
  ));
  expect(activeModelStartedEvents).toHaveLength(2);
  const firstRuntimeRunId = String(activeModelStartedEvents[0]?.data?.runtimeRunId || "");
  const secondRuntimeRunId = String(activeModelStartedEvents[1]?.data?.runtimeRunId || "");
  expect(firstRuntimeRunId).not.toBe("");
  expect(secondRuntimeRunId).not.toBe("");
  expect(secondRuntimeRunId).toBe(activeAgent.body.activeRuntimeRunId);
  expect(activeModelStartedEvents[1]?.data?.round).toBe(2);
  await expect.poll(() => ({
    agentRunIds: h4.controlIds().agentRunIds,
    runtimeRunIds: h4.controlIds().runtimeRunIds,
  })).toEqual({
    agentRunIds: [agentRunId],
    runtimeRunIds: [firstRuntimeRunId, secondRuntimeRunId],
  });
  const firstRuntime = await fetchProductionJson(
    page,
    `/api/runtime/runs/${encodeURIComponent(firstRuntimeRunId)}?cursor=0&wait=0`,
  );
  expect(firstRuntime.status).toBe(200);
  expect(firstRuntime.body).toMatchObject({
    runId: firstRuntimeRunId,
    sessionId: activeAgent.body.sessionId,
    status: "completed",
    nextCursor: 4,
  });
  expect(firstRuntime.body.result?.content).toBe(TOOL_DETAILS_STAGE);
  const secondRuntime = await fetchProductionJson(
    page,
    `/api/runtime/runs/${encodeURIComponent(secondRuntimeRunId)}?cursor=0&wait=0`,
  );
  expect(secondRuntime.status).toBe(200);
  expect(secondRuntime.body).toMatchObject({
    runId: secondRuntimeRunId,
    sessionId: activeAgent.body.sessionId,
    status: "running",
    nextCursor: 0,
  });
  expect(secondRuntime.body.events).toEqual([]);
  expect(secondRuntime.body.result?.content).toBe("");
  const activeTrace = durableToolTraceEvidence(activeAgent.body);
  expect(activeTrace.eventProjection.map((event) => event.type)).toEqual([
    "created",
    "model_started",
    "model_completed",
    "tool_started",
    "tool_completed",
    "model_pending",
    "model_started",
  ]);
  expect(activeTrace.toolCallIds).toHaveLength(1);
  const toolCallId = activeTrace.toolCallIds[0];
  expect(activeTrace.executionProjection).toEqual([{
    toolCallId: "tool-1",
    name: "read_file",
    arguments: { path: "fixture.txt" },
    status: "completed",
    outcome: "succeeded",
    result: {
      ok: true,
      action: "read_file",
      path: "fixture.txt",
      content: FIXTURE_CONTENT,
      size: 26,
      truncated: false,
      lineRange: null,
    },
  }]);

  const replacedStage = await initialDom.outer.elementHandle();
  await initialDom.outer.locator(":scope > summary.tool-process-stage-summary").click();
  await expect(initialDom.outer).toHaveAttribute("open", "");
  const openedKey = await initialDom.outer.getAttribute("data-tool-process-key");
  expect(openedKey).toBe(initialDom.projection.processKey);

  await h4.releaseGate(TOOL_FINAL_DELTA_GATE);
  await expect(initialDom.finalAnswer).toHaveCount(1);
  const terminalGateSnapshot = await h4.waitGate(TOOL_TERMINAL_GATE);
  expect(await replacedStage.evaluate((element) => element.isConnected)).toBe(false);
  const rerenderedDom = await toolDetailLifecycleDomEvidence(page);
  expect(rerenderedDom.projection.processKey).toBe(openedKey);
  expect(rerenderedDom.projection.outerOpen).toBe(true);
  expect(rerenderedDom.projection.counts).toMatchObject({
    toolProcess: 1,
    toolItem: 1,
    result: 1,
    final: 1,
    ordinaryAssistant: 2,
    assistantTotal: 3,
  });
  expect(rerenderedDom.projection.resultText).toBe(initialDom.projection.resultText);
  expect(rerenderedDom.projection.formattedResult).toEqual({
    pathPresent: true,
    sizePresent: true,
    fixtureContentCount: 1,
  });
  expect(terminalGateSnapshot[TOOL_TERMINAL_GATE]).toMatchObject({
    reached: true,
    released: false,
  });

  await h4.releaseGate(TOOL_TERMINAL_GATE);
  let completedAgent = null;
  await expect.poll(async () => {
    completedAgent = await fetchProductionJson(
      page,
      `/api/agent/runs/${encodeURIComponent(agentRunId)}?cursor=0&wait=0`,
    );
    return {
      status: completedAgent.body?.status,
      nextCursor: completedAgent.body?.nextCursor,
      eventTypes: (completedAgent.body?.events || []).map((event) => event.type),
    };
  }).toEqual({
    status: "completed",
    nextCursor: 9,
    eventTypes: [
      "created",
      "model_started",
      "model_completed",
      "tool_started",
      "tool_completed",
      "model_pending",
      "model_started",
      "model_completed",
      "completed",
    ],
  });
  expect(completedAgent.status).toBe(200);
  expect(completedAgent.body.activeRuntimeRunId).toBe("");
  await expect(page.locator("#activeRunBanner.visible")).toHaveCount(0);
  await expect(page.locator("#stopBtn")).toBeDisabled();
  await expect(page.locator("#messages .execution-trace.active")).toHaveCount(0);
  await expect(page.locator("#messages .execution-trace.completed")).toHaveCount(1);
  const terminalDom = await toolDetailLifecycleDomEvidence(page);
  expect(terminalDom.projection.processKey).toBe(openedKey);
  expect(terminalDom.projection.outerOpen).toBe(false);
  expect(terminalDom.projection.itemOpen).toBe(false);
  expect(terminalDom.projection.stageClass.split(/\s+/)).toContain("succeeded");
  expect(terminalDom.projection.heading).toBe("Inspected a file");
  expect(terminalDom.projection.resultText).toBe(initialDom.projection.resultText);
  expect(terminalDom.projection.formattedResult).toEqual({
    pathPresent: true,
    sizePresent: true,
    fixtureContentCount: 1,
  });

  const terminalTrace = page.locator("#messages .execution-trace.completed");
  await expect(terminalTrace).toHaveCount(1);
  await expect(terminalTrace).not.toHaveClass(/\bis-expanded\b/);
  const terminalTraceToggle = terminalTrace.locator(":scope > [data-execution-trace-toggle]");
  await expect(terminalTraceToggle).toHaveCount(1);
  await expect(terminalTraceToggle).toHaveAttribute("aria-expanded", "false");
  await terminalTraceToggle.click();
  await expect(terminalTrace).toHaveClass(/\bis-expanded\b/);
  await expect(terminalTraceToggle).toHaveAttribute("aria-expanded", "true");
  await expect(
    terminalDom.outer.locator(":scope > summary.tool-process-stage-summary"),
  ).toBeVisible();
  await terminalDom.outer.locator(":scope > summary.tool-process-stage-summary").click();
  await expect(terminalDom.outer).toHaveAttribute("open", "");
  await terminalDom.item.locator(":scope > summary").click();
  await expect(terminalDom.item).toHaveAttribute("open", "");
  await expect(terminalDom.process.locator(".tool-process-detail pre").first()).toBeVisible();
  await expect(terminalDom.process.locator(".tool-process-detail pre").first()).toContainText("fixture.txt");
  await expect(terminalDom.process.locator(".tool-process-detail pre").last()).toBeVisible();
  await expect(terminalDom.process.locator(".tool-process-detail pre").last()).toContainText("fixture.txt");
  await expect(terminalDom.process.locator(".tool-process-detail pre").last()).toContainText("26 B");
  await expect(terminalDom.process.locator(".tool-process-detail pre").last()).toContainText(FIXTURE_CONTENT.trim());
  expect(countOccurrences(
    await terminalDom.process.locator(".tool-process-detail pre").last().textContent(),
    FIXTURE_CONTENT.trim(),
  )).toBe(1);
  await terminalDom.item.locator(":scope > summary").click();
  await expect(terminalDom.item).not.toHaveAttribute("open", "");
  await terminalDom.outer.locator(":scope > summary.tool-process-stage-summary").click();
  await expect(terminalDom.outer).not.toHaveAttribute("open", "");
  await terminalTraceToggle.click();
  await expect(terminalTrace).not.toHaveClass(/\bis-expanded\b/);
  await expect(terminalTraceToggle).toHaveAttribute("aria-expanded", "false");

  const sessionButton = page.locator("#sessionList .session-row.active button.session-main");
  await expect(sessionButton).toHaveCount(1);
  const sessionId = await sessionButton.getAttribute("data-session-id");
  expect(sessionId).toBeTruthy();
  const sessionResponse = await fetchProductionJson(
    page,
    `/api/sessions/${encodeURIComponent(sessionId)}`,
  );
  expect(sessionResponse.status).toBe(200);
  const sessionProjection = roleContentProjection(sessionResponse.body.messages);
  expect(sessionProjection.map((message) => message.role)).toEqual([
    "user",
    "assistant",
    "tool-call",
    "tool-result",
    "assistant",
  ]);
  const completedTrace = durableToolTraceEvidence(completedAgent.body);
  expect(completedTrace.toolCallIds).toEqual([toolCallId]);
  expect(completedTrace.executionProjection).toEqual(activeTrace.executionProjection);
  const metrics = await h4.metrics();
  expect(metrics.chatRequests).toEqual([
    { scenario: "tool-detail-call", stream: true, hasToolResult: false },
    { scenario: "tool-detail-final", stream: true, hasToolResult: true },
  ]);
  expect(metrics.toolExecutions).toEqual([{ action: "read_file", path: "fixture.txt" }]);
  expect(metrics.unsafeToolRequests).toBe(0);
  const requests = h4.requestEvidenceSince(requestBoundary);
  expect(requests.agentPost).toBe(1);
  expect(requests.runtimePost).toBe(0);
  expect(requests.agentDelete).toBe(0);
  expect(h4.pageErrors).toEqual([]);

  const lifecycleProjection = {
    processKey: terminalDom.projection.processKey,
    openTransitions: ["closed", "open", "open-after-rerender", "closed-terminal", "open-inspect", "closed-inspect"],
    productionRerenderReplacedStage: true,
    eventTypes: completedTrace.eventProjection.map((event) => event.type),
    counts: terminalDom.projection.counts,
    ordered: terminalDom.projection.ordered,
    requests: {
      agentPost: requests.agentPost,
      runtimePost: requests.runtimePost,
      chat: metrics.chatRequests.length,
      tools: metrics.toolExecutions.length,
    },
  };
  const hashes = {
    lifecycle: canonicalHash(lifecycleProjection),
    eventProjection: completedTrace.eventProjectionHash,
    sessionRoleContent: canonicalHash(sessionProjection),
    terminalDom: terminalDom.semanticHash,
  };
  expect(hashes).toEqual(H4_6A_ACTIVE_TO_TERMINAL_HASHES);
  h4.evidence(
    runtime === "classic"
      ? "classic-tool-detail-active-to-terminal"
      : "tool-detail-active-to-terminal",
    {
    identity: {
      agentRunId: idHash(agentRunId),
      toolCallId: idHash(toolCallId),
      processKey: terminalDom.projection.processKey,
    },
    gateTimeline: metrics.refreshGateTimeline.filter((entry) => (
      entry.gate === TOOL_FINAL_DELTA_GATE || entry.gate === TOOL_TERMINAL_GATE
    )),
    lifecycle: lifecycleProjection,
    hashes,
    },
  );
}

test("bundle tool group keeps manual expansion through active rerender and collapses at terminal", async ({ h4 }) => {
  await exerciseToolDetailActiveToTerminal(h4, "bundle");
});

async function exerciseToolDetailTerminalRefresh(h4, runtime) {
  const { page } = h4;
  await h4.open(runtime);
  await assertFrontendRuntime(page, runtime);
  if (runtime === "classic") {
    expect(await page.locator("html").getAttribute("data-code-frontend-ready")).toBeNull();
  }
  await h4.proveNonLoopbackBlocked();
  await h4.submitGated(TOOL_DETAILS_USER);
  await h4.waitGate(TOOL_FINAL_DELTA_GATE);
  await h4.releaseGate(TOOL_FINAL_DELTA_GATE);
  await h4.waitGate(TOOL_TERMINAL_GATE);
  await h4.releaseGate(TOOL_TERMINAL_GATE);
  await expect(page.locator("#messages article.msg.assistant").filter({ hasText: TOOL_DETAILS_FINAL })).toHaveCount(1);
  await expect(page.locator("#activeRunBanner.visible")).toHaveCount(0);

  await expect.poll(() => h4.controlIds().agentRunIds.length).toBe(1);
  const agentRunId = h4.controlIds().agentRunIds[0];
  let agentBefore = null;
  await expect.poll(async () => {
    agentBefore = await fetchProductionJson(
      page,
      `/api/agent/runs/${encodeURIComponent(agentRunId)}?cursor=0&wait=0`,
    );
    return agentBefore.body?.status;
  }).toBe("completed");
  const traceBefore = durableToolTraceEvidence(agentBefore.body);
  expect(traceBefore.toolCallIds).toHaveLength(1);
  const toolCallId = traceBefore.toolCallIds[0];
  expect(traceBefore.eventProjection.map((event) => event.type)).toEqual([
    "created",
    "model_started",
    "model_completed",
    "tool_started",
    "tool_completed",
    "model_pending",
    "model_started",
    "model_completed",
    "completed",
  ]);

  const sessionButton = page.locator("#sessionList .session-row.active button.session-main");
  await expect(sessionButton).toHaveCount(1);
  const sessionId = await sessionButton.getAttribute("data-session-id");
  expect(sessionId).toBeTruthy();
  const sessionBefore = await fetchProductionJson(
    page,
    `/api/sessions/${encodeURIComponent(sessionId)}`,
  );
  expect(sessionBefore.status).toBe(200);
  const sessionProjectionBefore = roleContentProjection(sessionBefore.body.messages);
  expect(sessionProjectionBefore.map((message) => message.role)).toEqual([
    "user",
    "assistant",
    "tool-call",
    "tool-result",
    "assistant",
  ]);
  const toolMetaBefore = sessionToolMetaProjection(
    sessionBefore.body.messages,
    agentRunId,
    toolCallId,
  );
  expect(toolMetaBefore).toHaveLength(2);
  expect(toolMetaBefore.map((message) => message.role)).toEqual(["tool-call", "tool-result"]);
  expect(toolMetaBefore.every((message) => message.toolCallId === "tool-1")).toBe(true);
  expect(toolMetaBefore.at(-1)?.result).toEqual({
    ok: true,
    action: "read_file",
    path: "fixture.txt",
    content: FIXTURE_CONTENT,
    size: 26,
    truncated: false,
    lineRange: null,
  });

  const domBefore = await toolDetailLifecycleDomEvidence(page);
  expect(domBefore.projection.outerOpen).toBe(false);
  expect(domBefore.projection.itemOpen).toBe(false);
  expect(domBefore.projection.heading).toBe("Inspected a file");
  expect(domBefore.projection.formattedResult).toEqual({
    pathPresent: true,
    sizePresent: true,
    fixtureContentCount: 1,
  });
  const processKey = domBefore.projection.processKey;
  const traceBeforeReload = page.locator("#messages .execution-trace.completed");
  await expect(traceBeforeReload).toHaveCount(1);
  await expect(traceBeforeReload).not.toHaveClass(/\bis-expanded\b/);
  const traceToggleBeforeReload = traceBeforeReload.locator(
    ":scope > [data-execution-trace-toggle]",
  );
  await expect(traceToggleBeforeReload).toHaveCount(1);
  await expect(traceToggleBeforeReload).toHaveAttribute("aria-expanded", "false");
  await traceToggleBeforeReload.click();
  await expect(traceBeforeReload).toHaveClass(/\bis-expanded\b/);
  await expect(traceToggleBeforeReload).toHaveAttribute("aria-expanded", "true");
  await expect(
    domBefore.outer.locator(":scope > summary.tool-process-stage-summary"),
  ).toBeVisible();
  await domBefore.outer.locator(":scope > summary.tool-process-stage-summary").click();
  await domBefore.item.locator(":scope > summary").click();
  await expect(domBefore.outer).toHaveAttribute("open", "");
  await expect(domBefore.item).toHaveAttribute("open", "");

  const metricsBefore = await h4.metrics();
  const refreshBoundary = h4.requestBoundary();
  await page.reload({ waitUntil: "domcontentloaded" });
  await assertFrontendRuntime(page, runtime);
  if (runtime === "classic") {
    expect(await page.locator("html").getAttribute("data-code-frontend-ready")).toBeNull();
  }
  const persistedSession = page.locator(
    `#sessionList button.session-main[data-session-id="${sessionId}"]`,
  );
  await expect(persistedSession).toHaveCount(1);
  await persistedSession.click();

  const domAfter = await toolDetailLifecycleDomEvidence(page);
  expect(domAfter.projection.processKey).toBe(processKey);
  expect(domAfter.projection.outerOpen).toBe(false);
  expect(domAfter.projection.itemOpen).toBe(false);
  expect(domAfter.projection).toEqual(domBefore.projection);
  expect(domAfter.projection.formattedResult).toEqual({
    pathPresent: true,
    sizePresent: true,
    fixtureContentCount: 1,
  });
  const traceAfterReload = page.locator("#messages .execution-trace.completed");
  await expect(traceAfterReload).toHaveCount(1);
  await expect(traceAfterReload).not.toHaveClass(/\bis-expanded\b/);
  const traceToggleAfterReload = traceAfterReload.locator(
    ":scope > [data-execution-trace-toggle]",
  );
  await expect(traceToggleAfterReload).toHaveCount(1);
  await expect(traceToggleAfterReload).toHaveAttribute("aria-expanded", "false");
  await traceToggleAfterReload.click();
  await expect(traceAfterReload).toHaveClass(/\bis-expanded\b/);
  await expect(traceToggleAfterReload).toHaveAttribute("aria-expanded", "true");
  await expect(
    domAfter.outer.locator(":scope > summary.tool-process-stage-summary"),
  ).toBeVisible();
  await domAfter.outer.locator(":scope > summary.tool-process-stage-summary").click();
  await domAfter.item.locator(":scope > summary").click();
  await expect(domAfter.outer).toHaveAttribute("open", "");
  await expect(domAfter.item).toHaveAttribute("open", "");
  await expect(domAfter.process.locator(".tool-process-detail pre").last()).toContainText("fixture.txt");
  await expect(domAfter.process.locator(".tool-process-detail pre").last()).toContainText("26 B");
  await expect(domAfter.process.locator(".tool-process-detail pre").last()).toContainText(FIXTURE_CONTENT.trim());
  expect(countOccurrences(
    await domAfter.process.locator(".tool-process-detail pre").last().textContent(),
    FIXTURE_CONTENT.trim(),
  )).toBe(1);
  await domAfter.item.locator(":scope > summary").click();
  await expect(domAfter.item).not.toHaveAttribute("open", "");
  await domAfter.outer.locator(":scope > summary.tool-process-stage-summary").click();
  await expect(domAfter.outer).not.toHaveAttribute("open", "");
  await traceToggleAfterReload.click();
  await expect(traceAfterReload).not.toHaveClass(/\bis-expanded\b/);
  await expect(traceToggleAfterReload).toHaveAttribute("aria-expanded", "false");

  const agentAfter = await fetchProductionJson(
    page,
    `/api/agent/runs/${encodeURIComponent(agentRunId)}?cursor=0&wait=0`,
  );
  expect(agentAfter.status).toBe(200);
  const traceAfter = durableToolTraceEvidence(agentAfter.body);
  expect(traceAfter).toEqual(traceBefore);
  expect(traceAfter.toolCallIds).toEqual([toolCallId]);
  const sessionAfter = await fetchProductionJson(
    page,
    `/api/sessions/${encodeURIComponent(sessionId)}`,
  );
  expect(sessionAfter.status).toBe(200);
  const sessionProjectionAfter = roleContentProjection(sessionAfter.body.messages);
  expect(sessionProjectionAfter).toEqual(sessionProjectionBefore);
  const toolMetaAfter = sessionToolMetaProjection(
    sessionAfter.body.messages,
    agentRunId,
    toolCallId,
  );
  expect(toolMetaAfter).toEqual(toolMetaBefore);

  const metricsAfter = await h4.metrics();
  expect(metricsAfter.chatRequests).toEqual(metricsBefore.chatRequests);
  expect(metricsAfter.toolExecutions).toEqual(metricsBefore.toolExecutions);
  expect(metricsAfter.chatRequests).toEqual([
    { scenario: "tool-detail-call", stream: true, hasToolResult: false },
    { scenario: "tool-detail-final", stream: true, hasToolResult: true },
  ]);
  expect(metricsAfter.toolExecutions).toEqual([{ action: "read_file", path: "fixture.txt" }]);
  const refreshRequests = h4.requestEvidenceSince(refreshBoundary);
  expect(refreshRequests.agentPost).toBe(0);
  expect(refreshRequests.runtimePost).toBe(0);
  expect(refreshRequests.agentDelete).toBe(0);
  expect(h4.controlIds().agentRunIds).toEqual([agentRunId]);
  expect(h4.pageErrors).toEqual([]);

  const refreshProjection = {
    processKeyStable: domAfter.projection.processKey === domBefore.projection.processKey,
    agentRunStable: traceAfter.agentRunId === traceBefore.agentRunId,
    toolCallStable: traceAfter.toolCallIdHashes[0] === traceBefore.toolCallIdHashes[0],
    eventProjectionStable: traceAfter.eventProjectionHash === traceBefore.eventProjectionHash,
    sessionProjectionStable: JSON.stringify(sessionProjectionAfter) === JSON.stringify(sessionProjectionBefore),
    toolMetaStable: JSON.stringify(toolMetaAfter) === JSON.stringify(toolMetaBefore),
    refreshDefaultCollapsed: !domAfter.projection.outerOpen && !domAfter.projection.itemOpen,
    counts: domAfter.projection.counts,
    requests: {
      agentPost: refreshRequests.agentPost,
      runtimePost: refreshRequests.runtimePost,
      chatDelta: metricsAfter.chatRequests.length - metricsBefore.chatRequests.length,
      toolDelta: metricsAfter.toolExecutions.length - metricsBefore.toolExecutions.length,
    },
  };
  const hashes = {
    refreshLifecycle: canonicalHash(refreshProjection),
    eventProjection: traceBefore.eventProjectionHash,
    sessionRoleContent: canonicalHash(sessionProjectionBefore),
    sessionToolMeta: canonicalHash(toolMetaBefore),
    terminalDom: domBefore.semanticHash,
  };
  expect(hashes).toEqual(H4_6A_TERMINAL_REFRESH_HASHES);
  h4.evidence(
    runtime === "classic"
      ? "classic-tool-detail-terminal-refresh"
      : "tool-detail-terminal-refresh",
    {
    identity: {
      agentRunId: idHash(agentRunId),
      toolCallId: idHash(toolCallId),
      processKey,
    },
    refresh: refreshProjection,
    hashes,
    expansionBoundary: "page-local outer and item details reset to collapsed on full reload",
    },
  );
}

test("completed bundle tool details reload uniquely with default collapsed state", async ({ h4 }) => {
  await exerciseToolDetailTerminalRefresh(h4, "bundle");
});

test("classic tool group keeps manual expansion through active rerender and collapses at terminal", async ({ h4 }) => {
  await exerciseToolDetailActiveToTerminal(h4, "classic");
});

test("completed classic tool details reload uniquely with default collapsed state", async ({ h4 }) => {
  await exerciseToolDetailTerminalRefresh(h4, "classic");
});

test("classic fallback completes one plain-text task", async ({ h4 }) => {
  const { page } = h4;
  await h4.open("classic");
  await expect(page.locator("html")).toHaveAttribute("data-frontend-runtime", "classic-fallback");
  await h4.proveNonLoopbackBlocked();
  await h4.submit("H4_CLASSIC_USER");

  const finalAnswer = page.locator("#messages article.msg.assistant").filter({ hasText: "H4_CLASSIC_FINAL" });
  await expect(finalAnswer).toHaveCount(1);
  const text = await page.locator("#messages").textContent();
  expect(countOccurrences(text, "H4_CLASSIC_USER")).toBe(1);
  expect(countOccurrences(text, "H4_CLASSIC_FINAL")).toBe(1);
  const metrics = await h4.metrics();
  expect(metrics.chatRequests).toEqual([
    { scenario: "classic-text", stream: true, hasToolResult: false },
  ]);
  expect(metrics.toolExecutions).toEqual([]);
  expect(metrics.unsafeToolRequests).toBe(0);
  expect(h4.pageErrors).toEqual([]);
  h4.evidence("classic-plain", {
    runtime: "classic-fallback",
    chatRequests: metrics.chatRequests.length,
    toolExecutions: 0,
    dom: { user: 1, final: 1, runningObserved: true },
    blockedNonLoopback: h4.blockedRequests.length,
  });
});

for (const fallbackScenario of [
  {
    title: "bundle-load failure automatically falls back to classic",
    failureMode: "load",
    evidenceLabel: "automatic-classic-fallback-bundle-load",
  },
  {
    title: "bundle-init failure automatically falls back to classic",
    failureMode: "init",
    evidenceLabel: "automatic-classic-fallback-bundle-init",
  },
]) {
  test(fallbackScenario.title, async ({ h4 }) => {
    const { page } = h4;
    const fallback = await openAutomaticClassicFallback(h4, fallbackScenario.failureMode);
    await expect.poll(() => (
      summarizeLoopbackRequests(h4.loopbackRequests)["GET /api/sessions"] || 0
    )).toBe(1);
    await expect.poll(() => (
      summarizeLoopbackRequests(h4.loopbackRequests)["GET /proxy/models"] || 0
    )).toBe(1);
    const startupRequests = summarizeLoopbackRequests(h4.loopbackRequests);
    expect(startupRequests["GET /"]).toBe(1);
    expect(startupRequests[`GET ${CLASSIC_FALLBACK_PATH}`]).toBe(1);
    expect(startupRequests[`GET ${FRONTEND_BUNDLE_PATH}`] || 0).toBe(0);
    expect(startupRequests["GET /agent-runtime.js"]).toBe(1);
    expect(startupRequests["GET /app.js"]).toBe(1);
    expect(startupRequests["GET /api/sessions"]).toBe(1);
    expect(startupRequests["GET /proxy/models"]).toBe(1);
    await h4.proveNonLoopbackBlocked();

    await h4.submit("H4_PLAIN_USER");
    const user = page.locator("#messages article.msg.user").filter({ hasText: "H4_PLAIN_USER" });
    const assistant = page.locator("#messages article.msg.assistant");
    const finalAnswer = assistant.filter({ hasText: "H4_PLAIN_FINAL" });
    await expect(user).toHaveCount(1);
    await expect(assistant).toHaveCount(1);
    await expect(finalAnswer).toHaveCount(1);
    const text = await page.locator("#messages").textContent();
    expect(countOccurrences(text, "H4_PLAIN_USER")).toBe(1);
    expect(countOccurrences(text, "H4_PLAIN_FINAL")).toBe(1);

    const requests = h4.requestEvidence();
    const metrics = await h4.metrics();
    const finalRequests = summarizeLoopbackRequests(h4.loopbackRequests);
    expect(requests.agentPost).toBe(1);
    expect(requests.runtimePost).toBe(0);
    expect(requests.agentIds).toHaveLength(1);
    expect(requests.runtimeIds).toHaveLength(1);
    expect(metrics.chatRequests).toEqual([
      { scenario: "plain-text", stream: true, hasToolResult: false },
    ]);
    expect(metrics.toolExecutions).toEqual([]);
    expect(metrics.unsafeToolRequests).toBe(0);
    expect(metrics.production.agentRuns).toHaveLength(1);
    expect(metrics.production.runtimeRuns).toHaveLength(1);
    expect(metrics.production.agentRuns[0].agentRunId).toBe(requests.agentIds[0]);
    expect(metrics.production.runtimeRuns[0].runtimeRunId).toBe(requests.runtimeIds[0]);
    expect(finalRequests["POST /api/sessions"]).toBe(1);
    expect(finalRequests[`GET ${CLASSIC_FALLBACK_PATH}`]).toBe(1);
    expect(finalRequests["GET /agent-runtime.js"]).toBe(1);
    expect(finalRequests["GET /app.js"]).toBe(1);
    expect(finalRequests["GET /proxy/models"]).toBe(1);
    expect(h4.pageErrors).toEqual([]);
    h4.evidence(fallbackScenario.evidenceLabel, {
      fallback,
      requests,
      terminal: productionTerminalEvidence(metrics),
      startup: {
        rootDocuments: startupRequests["GET /"],
        classicDocuments: startupRequests[`GET ${CLASSIC_FALLBACK_PATH}`],
        modelCatalogRequests: startupRequests["GET /proxy/models"],
        sessionListRequests: startupRequests["GET /api/sessions"],
        appScripts: startupRequests["GET /app.js"],
        runtimeScripts: startupRequests["GET /agent-runtime.js"],
      },
      dom: { user: 1, assistant: 1, final: 1 },
      chatRequests: metrics.chatRequests.length,
      toolExecutions: metrics.toolExecutions.length,
      blockedNonLoopback: h4.blockedRequests.length,
    });
  });
}

async function exerciseRefreshBeforeFirst(h4, { runtime, evidenceLabel }) {
  const { page } = h4;
  await h4.open(runtime);
  await assertFrontendRuntime(page, runtime);
  await h4.submitGated();
  try {
    await h4.waitGate("before-first-delta");
    const before = await h4.metrics();
    expect(before.production.agentRuns).toHaveLength(1);
    expect(before.production.runtimeRuns).toHaveLength(1);
    expect(before.production.runtimeRuns[0].nextCursor).toBe(0);
    expect(before.sessionJsonl).toMatchObject({
      hasFirstChunk: false,
      hasSecondChunk: false,
      hasThirdChunk: false,
      hasStreamingField: false,
      hasStreamProjectionField: false,
    });

    const elapsedBefore = page.locator("#activeRunBanner [data-task-elapsed]");
    await expect(elapsedBefore).toHaveText(/^[1-9]\d*s$/);
    const beforeSeconds = elapsedSeconds(await elapsedBefore.textContent());
    const runtimeGetsBeforeReload = h4.requestEvidence().runtimeGet;
    await h4.armModelCatalogGate();
    const reloadReadyAt = await h4.reloadRuntime(runtime);
    const catalogGate = await h4.waitModelCatalogGate();
    expect(catalogGate).toMatchObject({ armed: true, reached: true, released: false });
    await expect.poll(() => h4.requestEvidence().runtimeGet).toBeGreaterThan(runtimeGetsBeforeReload);
    await expect(page.locator("#messages article.msg.user").filter({ hasText: STREAM_USER })).toHaveCount(1);
    await expect(page.locator("#activeRunBanner.visible .active-run-line[role='status']")).toBeVisible();
    await expect(page.locator("#stopBtn")).toBeEnabled();
    await expect(page.locator("#sendBtn.running")).toBeEnabled();
    const elapsedAfter = page.locator("#activeRunBanner [data-task-elapsed]");
    await expect(elapsedAfter).toHaveText(/^\d+s$/);
    expect(elapsedSeconds(await elapsedAfter.textContent())).toBeGreaterThanOrEqual(beforeSeconds);

    await h4.releaseGate("before-first-delta");
    await h4.waitGate("after-second-delta");
    const firstTwo = page.locator("#messages article.msg.assistant").filter({ hasText: `${STREAM_ONE} ${STREAM_TWO}` });
    await expect(firstTwo).toHaveCount(1);
    expect((await h4.metrics()).modelCatalogGate).toMatchObject({ reached: true, released: false });
    await h4.releaseModelCatalogGate();
    await h4.releaseGate("after-second-delta");
    await expect(page.locator("#messages article.msg.assistant").filter({ hasText: STREAM_FINAL })).toHaveCount(1);
    const terminalGate = (await h4.metrics()).refreshGates["before-terminal"];
    expect(terminalGate).toMatchObject({ reached: true, released: false });
    await h4.releaseGate("before-terminal");
    await expect(page.locator("#activeRunBanner.visible")).toHaveCount(0);

    const text = await page.locator("#messages").textContent();
    expect(countOccurrences(text, STREAM_USER)).toBe(1);
    expect(countOccurrences(text, STREAM_ONE)).toBe(1);
    expect(countOccurrences(text, STREAM_TWO)).toBe(1);
    expect(countOccurrences(text, STREAM_THREE)).toBe(1);
    const evidence = await assertRefreshIdentityContract(h4);
    expect(evidence.metrics.production.agentRuns[0].status).toBe("completed");
    expect(evidence.metrics.production.runtimeRuns[0].status).toBe("completed");
    expect(evidence.metrics.sessionJsonl).toMatchObject({
      hasFirstChunk: true,
      hasSecondChunk: true,
      hasThirdChunk: true,
      hasStreamingField: false,
      hasStreamProjectionField: false,
    });
    expect(h4.pageErrors).toEqual([]);
    h4.evidence(evidenceLabel, {
      entryRuntime: runtime,
      ids: {
        agent: evidence.requests.agentIds[0],
        runtime: evidence.requests.runtimeIds[0],
      },
      requests: evidence.requests,
      cursors: evidence.requests.runtimeCursors,
      reloadReadyAt,
      elapsed: { beforeSeconds, afterSeconds: elapsedSeconds(await elapsedAfter.textContent()) },
      jsonlBeforeDelta: before.sessionJsonl,
      modelCatalogGate: evidence.metrics.modelCatalogGate,
      gates: evidence.metrics.refreshGates,
      dom: { user: 1, final: 1, stopRestored: true },
    });
  } finally {
    await h4.releaseAllRefreshGates();
  }
}

async function exerciseRefreshAfterTwo(h4, { runtime, evidenceLabel }) {
  const { page } = h4;
  await h4.open(runtime);
  await assertFrontendRuntime(page, runtime);
  await h4.submitGated();
  try {
    await h4.waitGate("before-first-delta");
    await h4.releaseGate("before-first-delta");
    await h4.waitGate("after-second-delta");
    const firstTwo = page.locator("#messages article.msg.assistant").filter({ hasText: `${STREAM_ONE} ${STREAM_TWO}` });
    await expect(firstTwo).toHaveCount(1);
    const prefixBefore = (await firstTwo.textContent()).trim();
    const before = await h4.metrics();
    expect(before.production.runtimeRuns[0]).toMatchObject({
      nextCursor: 2,
      hasFirstChunk: true,
      hasSecondChunk: true,
      hasThirdChunk: false,
    });
    expect(before.sessionJsonl).toMatchObject({
      hasFirstChunk: false,
      hasSecondChunk: false,
      hasThirdChunk: false,
      hasStreamingField: false,
      hasStreamProjectionField: false,
    });

    const runtimeGetsBeforeReload = h4.requestEvidence().runtimeGet;
    await h4.armModelCatalogGate();
    const reloadReadyAt = await h4.reloadRuntime(runtime);
    const catalogGate = await h4.waitModelCatalogGate();
    expect(catalogGate).toMatchObject({ armed: true, reached: true, released: false });
    await expect.poll(() => h4.requestEvidence().runtimeGet).toBeGreaterThan(runtimeGetsBeforeReload);
    const caughtUp = page.locator("#messages article.msg.assistant").filter({ hasText: `${STREAM_ONE} ${STREAM_TWO}` });
    await expect(caughtUp).toHaveCount(1);
    expect((await caughtUp.textContent()).trim().startsWith(prefixBefore)).toBe(true);
    await h4.releaseGate("after-second-delta");
    const completeBody = page.locator("#messages article.msg.assistant").filter({ hasText: STREAM_FINAL });
    await expect(completeBody).toHaveCount(1);
    expect((await h4.metrics()).modelCatalogGate).toMatchObject({ reached: true, released: false });
    await h4.releaseModelCatalogGate();
    const terminalGate = (await h4.metrics()).refreshGates["before-terminal"];
    expect(terminalGate).toMatchObject({ reached: true, released: false });
    const thirdDomSample = h4.domTimeline.find((sample) => (
      sample.at >= reloadReadyAt && sample.text.includes(STREAM_THREE)
    ));
    expect(thirdDomSample).toBeTruthy();
    const nonEmptyAfterRefresh = h4.domTimeline.filter((sample) => (
      sample.at >= reloadReadyAt && sample.text.includes(STREAM_ONE)
    ));
    expect(nonEmptyAfterRefresh.length).toBeGreaterThan(0);
    const streamTextsAfterRefresh = nonEmptyAfterRefresh.map((sample) => sample.text.trim());
    expect(streamTextsAfterRefresh[0].startsWith(prefixBefore)).toBe(true);
    for (let index = 1; index < streamTextsAfterRefresh.length; index += 1) {
      expect(streamTextsAfterRefresh[index].startsWith(streamTextsAfterRefresh[index - 1])).toBe(true);
    }
    await h4.releaseGate("before-terminal");
    await expect(page.locator("#activeRunBanner.visible")).toHaveCount(0);

    const text = await page.locator("#messages").textContent();
    expect(countOccurrences(text, STREAM_USER)).toBe(1);
    expect(countOccurrences(text, STREAM_ONE)).toBe(1);
    expect(countOccurrences(text, STREAM_TWO)).toBe(1);
    expect(countOccurrences(text, STREAM_THREE)).toBe(1);
    const evidence = await assertRefreshIdentityContract(h4);
    expect(evidence.requests.runtimeCursors).toContain(2);
    expect(evidence.metrics.sessionJsonl).toMatchObject({
      hasFirstChunk: true,
      hasSecondChunk: true,
      hasThirdChunk: true,
      hasStreamingField: false,
      hasStreamProjectionField: false,
    });
    expect(h4.pageErrors).toEqual([]);
    h4.evidence(evidenceLabel, {
      entryRuntime: runtime,
      ids: {
        agent: evidence.requests.agentIds[0],
        runtime: evidence.requests.runtimeIds[0],
      },
      requests: evidence.requests,
      runtimeBeforeRefresh: before.production.runtimeRuns[0],
      jsonlAfterCompletion: evidence.metrics.sessionJsonl,
      modelCatalogGate: evidence.metrics.modelCatalogGate,
      domTimeline: nonEmptyAfterRefresh,
      thirdBeforeTerminalRelease: true,
    });
  } finally {
    await h4.releaseAllRefreshGates();
  }
}

async function exerciseRefreshThenCancel(h4, { runtime, evidenceLabel }) {
  const { page } = h4;
  await h4.open(runtime);
  await assertFrontendRuntime(page, runtime);
  await h4.submitGated();
  try {
    await h4.waitGate("before-first-delta");
    await h4.releaseGate("before-first-delta");
    await h4.waitGate("after-second-delta");
    const firstTwo = page.locator("#messages article.msg.assistant").filter({ hasText: `${STREAM_ONE} ${STREAM_TWO}` });
    await expect(firstTwo).toHaveCount(1);
    const runtimeGetsBeforeReload = h4.requestEvidence().runtimeGet;
    await h4.armModelCatalogGate();
    await h4.reloadRuntime(runtime);
    const catalogGate = await h4.waitModelCatalogGate();
    expect(catalogGate).toMatchObject({ armed: true, reached: true, released: false });
    await expect.poll(() => h4.requestEvidence().runtimeGet).toBeGreaterThan(runtimeGetsBeforeReload);
    await expect(page.locator("#messages article.msg.assistant").filter({ hasText: `${STREAM_ONE} ${STREAM_TWO}` })).toHaveCount(1);
    await expect(page.locator("#sendBtn.running")).toBeEnabled();

    const cancelStartedAt = Date.now();
    const cancelResponsePromise = page.waitForResponse((response) => (
      response.request().method() === "DELETE"
      && /^\/api\/agent\/runs\/[^/]+$/.test(new URL(response.url()).pathname)
    ));
    await page.locator("#sendBtn").click();
    await expect.poll(() => h4.requestEvidence().agentDelete).toBe(1);
    // The synthetic upstream is intentionally stopped inside a server-side
    // readline. Releasing its gates lets the already-issued Agent DELETE
    // finish without using a sleep or creating another request.
    await h4.releaseAllRefreshGates();
    const cancelResponse = await cancelResponsePromise;
    expect(cancelResponse.status()).toBe(200);
    const paused = page.locator("#messages article.msg.assistant").filter({ hasText: "[Output paused]" });
    await expect(paused).toHaveCount(1);
    const cancelLatencyMs = Date.now() - cancelStartedAt;
    expect(cancelLatencyMs).toBeLessThan(5_000);
    await expect(page.locator("#activeRunBanner.visible")).toHaveCount(0);

    const text = await page.locator("#messages").textContent();
    expect(countOccurrences(text, STREAM_USER)).toBe(1);
    expect(countOccurrences(text, STREAM_ONE)).toBe(1);
    expect(countOccurrences(text, STREAM_TWO)).toBe(1);
    expect(countOccurrences(text, "[Output paused]")).toBe(1);
    const evidence = await assertRefreshIdentityContract(h4, { cancelled: true });
    expect(evidence.metrics.production.agentRuns[0].status).toBe("cancelled");
    expect(evidence.metrics.production.runtimeRuns[0].status).toBe("cancelled");
    expect(evidence.metrics.production.agentRuns[0].eventTypes).not.toContain("model_completed");
    expect(evidence.metrics.sessionJsonl).toMatchObject({
      hasFirstChunk: true,
      hasSecondChunk: true,
      pausedOutputCount: 1,
      hasStreamingField: false,
      hasStreamProjectionField: false,
    });
    expect(h4.pageErrors).toEqual([]);
    h4.evidence(evidenceLabel, {
      entryRuntime: runtime,
      ids: {
        agent: evidence.requests.agentIds[0],
        runtime: evidence.requests.runtimeIds[0],
      },
      requests: evidence.requests,
      cancelLatencyMs,
      modelCatalogGate: evidence.metrics.modelCatalogGate,
      inFlightThirdPersisted: evidence.metrics.sessionJsonl.hasThirdChunk,
      dom: { user: 1, partialPreserved: true, paused: 1, successfulFinal: 0 },
    });
  } finally {
    await h4.releaseAllRefreshGates();
  }
}

test("bundle refresh before first model delta reattaches one live run", async ({ h4 }) => {
  await exerciseRefreshBeforeFirst(h4, {
    runtime: "bundle",
    evidenceLabel: "bundle-refresh-before-first",
  });
});

test("bundle refresh after two deltas catches up without DOM replay", async ({ h4 }) => {
  await exerciseRefreshAfterTwo(h4, {
    runtime: "bundle",
    evidenceLabel: "bundle-refresh-after-two",
  });
});

test("bundle refresh then cancel preserves partial body and pauses once", async ({ h4 }) => {
  await exerciseRefreshThenCancel(h4, {
    runtime: "bundle",
    evidenceLabel: "bundle-refresh-cancel",
  });
});

test("classic-refresh-before-first-delta", async ({ h4 }) => {
  await exerciseRefreshBeforeFirst(h4, {
    runtime: "classic",
    evidenceLabel: "classic-refresh-before-first-delta",
  });
});

test("classic-refresh-after-two-deltas", async ({ h4 }) => {
  await exerciseRefreshAfterTwo(h4, {
    runtime: "classic",
    evidenceLabel: "classic-refresh-after-two-deltas",
  });
});

test("classic-refresh-then-cancel", async ({ h4 }) => {
  await exerciseRefreshThenCancel(h4, {
    runtime: "classic",
    evidenceLabel: "classic-refresh-then-cancel",
  });
});
