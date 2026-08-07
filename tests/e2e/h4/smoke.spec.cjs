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
const MULTI_TOOL_USER = "H4_MULTI_TOOL_USER";
const MULTI_TOOL_STAGE = "H4_MULTI_TOOL_STAGE";
const MULTI_TOOL_FINAL = "H4_MULTI_TOOL_FINAL";
const INVALID_TOOL_USER = "H4_INVALID_TOOL_ARGUMENTS_USER";
const INVALID_TOOL_STAGE = "H4_INVALID_TOOL_ARGUMENTS_STAGE";
const INVALID_TOOL_FINAL = "H4_INVALID_TOOL_ARGUMENTS_FINAL";
const PARSE_ERROR_TOOL_USER = "H4_PARSE_ERROR_TOOL_ARGUMENTS_USER";
const PARSE_ERROR_TOOL_STAGE = "H4_PARSE_ERROR_TOOL_ARGUMENTS_STAGE";
const PARSE_ERROR_TOOL_FINAL = "H4_PARSE_ERROR_TOOL_ARGUMENTS_FINAL";
const MALFORMED_TOOL_ARGUMENTS = '{"path":"fixture.txt"';
const MISSING_PATH_TOOL_USER = "H4_MISSING_PATH_TOOL_ARGUMENTS_USER";
const MISSING_PATH_TOOL_STAGE = "H4_MISSING_PATH_TOOL_ARGUMENTS_STAGE";
const MISSING_PATH_TOOL_FINAL = "H4_MISSING_PATH_TOOL_ARGUMENTS_FINAL";
const MISSING_PATH_TOOL_ARGUMENTS = "{}";
const EXECUTOR_RANGE_USER = "H4_EXECUTOR_RANGE_FAILURE_USER";
const EXECUTOR_RANGE_STAGE = "H4_EXECUTOR_RANGE_FAILURE_STAGE";
const EXECUTOR_RANGE_FINAL = "H4_EXECUTOR_RANGE_FAILURE_FINAL";
const REPEATED_RANGE_FAILURE_USER = "H4_REPEATED_RANGE_FAILURE_USER";
const REPEATED_RANGE_FAILURE_STAGE = "H4_REPEATED_RANGE_FAILURE_STAGE";
const REPEATED_RANGE_FAILURE_FINAL = "H4_REPEATED_RANGE_FAILURE_FINAL";
const MISSING_FILE_USER = "H4_MISSING_FILE_FAILURE_USER";
const MISSING_FILE_STAGE = "H4_MISSING_FILE_FAILURE_STAGE";
const MISSING_FILE_FINAL = "H4_MISSING_FILE_FAILURE_FINAL";
const MISSING_READ_PATH = "h4-missing-fixture.txt";
const TOOL_FINAL_DELTA_GATE = "before-tool-final-delta";
const TOOL_TERMINAL_GATE = "before-tool-terminal";
const SECOND_TOOL_EXECUTE_GATE = "before-second-tool-execute";
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
const H4_6C_ACTIVE_TO_TERMINAL_HASHES = Object.freeze({
  lifecycle: "f5445145789b337ffba49dcec350a483981be281d52e9144f23fefd8cde3307d",
  eventProjection: "6e81cc9ad5662a25862ffd3384de2d53481d75e427695391eedd4e8a7aac1342",
  receiptProjection: "35e8de4147a9991325091f30dedb701ab0676979af6db122ccee9ed3e56042c1",
  sessionRoleContent: "033743ab31d1b95e7e33aefc1c74515a01cc2fb65cebd4830b2099f2c6a4e2f7",
  sessionToolMeta: "23956f1cd5fdb148e94f6c224e7dff3326ec0e4f6aff01342512fa9fc8ab842e",
  activeDom: "3fd7fd4774195b01136297bb63f88e348b18eac5fac40ace73ffe8f88c1ca0d0",
  terminalDom: "9efb0070a8125ede3c69abf4f4c530ac5076979d480febd63d5df7a7230753cb",
});
const H4_6C_TERMINAL_REFRESH_HASHES = Object.freeze({
  refreshLifecycle: "9421bf68cdb674d5dff228bb173db82772af2806f9881f52437d60b763e673de",
  eventProjection: "6e81cc9ad5662a25862ffd3384de2d53481d75e427695391eedd4e8a7aac1342",
  receiptProjection: "35e8de4147a9991325091f30dedb701ab0676979af6db122ccee9ed3e56042c1",
  sessionRoleContent: "033743ab31d1b95e7e33aefc1c74515a01cc2fb65cebd4830b2099f2c6a4e2f7",
  sessionToolMeta: "23956f1cd5fdb148e94f6c224e7dff3326ec0e4f6aff01342512fa9fc8ab842e",
  terminalDom: "9efb0070a8125ede3c69abf4f4c530ac5076979d480febd63d5df7a7230753cb",
});
const H4_6E_SEMANTIC_HASHES = Object.freeze({
  eventProjection: "860e9f45fe924f5a8a94ca031d2839264fd550dfcbef0c4a9a1bb89393bd6ef4",
  invalidReceiptProjection: "bf4ec29db9ac54505687e3fb3c2040ff5f4fa17aed715700c958317a3aa6c776",
  modelToolReceiptProjection: "1b94536a4cc63c2bc3b98c54eb14c329ac585b5ec65bf85c1ca7bbd080ab6c80",
  sessionRoleContent: "cbdcb15dad4b61b34bdf89556131827fc7fd973f88b9b9368e329bf61b1821fb",
  sessionToolMeta: "c62eca9c84fb4d3c94968c2423f8db13cff6ca254fd90eba9bb225c87d438285",
  activeDom: "3f718cb47d5fb90dcdc0bbc3a425718a43f1c0fe6ee082ce53e90a22cabc2ad4",
  terminalDom: "4cdf1271fd50f4060b985a2c9b579bad19b075e0b562881337cd2ddab42b161d",
  refreshLifecycle: "04f95460a984cf77cd07b7287db22363a38ee6201d164282f932aee10250d3a4",
});
const H4_6G_SEMANTIC_HASHES = Object.freeze({
  eventProjection: "05679b66e0b8957455b7a57dde5cc6455948ef69a609772ad33f57489bf0d08d",
  executorReceiptProjection: "3a1b994b1fe398c83cb8adfcf7e71e2b2a98309b5e16cd0b8924420e719396a5",
  modelToolReceiptProjection: "60e752356006ec8f15d661edd9724ebdf24c7a0c1633af5bdf37e75a28a5f0c8",
  sessionRoleContent: "75ae4df19c62ebff5c92cc14b04015238de0a5d4b4a7789d0da50dd965c60e1e",
  sessionToolMeta: "d7ec6a76b4b67e204a24b508b6e548a46e2d92fe9ef8575d6a30bc8b5c5fc500",
  activeDom: "53db0899dd213b606bd89904aa7f4df93cf6270a535648b812b6cb7c2e7da425",
  terminalDom: "92162bb8446b0556cb897912ea0aa0db129b9682a8a071b96ad07795c335299c",
  refreshLifecycle: "04f95460a984cf77cd07b7287db22363a38ee6201d164282f932aee10250d3a4",
});
const H4_6H_SEMANTIC_HASHES = Object.freeze({
  eventProjection: "4dd3fb7c43cbe9bcc0fb95b5df7e4cf794f35f4e3a9eb2c8d388c2e7389314f2",
  missingFileReceiptProjection: "bef7e2038ec8d5a56437dbdeef1b43a73b7553d67fe637ae3fb26d9ae1a8b498",
  modelToolReceiptProjection: "4204a133ea7a8e74a5981668a013feb29d86b7bc492941b4e25c6a64652a2b8d",
  sessionRoleContent: "450f53474e8c9fe65b71409b7efb6c3a222e5f4629bd8dbbc89d6d3b6a05c923",
  sessionToolMeta: "d8e40c3d2d303c0e4c4c6394dde046869f7ffaee8414f960d54dbc3261cb2c7e",
  activeDom: "b6ae61b6e790e68c2c2d0586fb0d5a62d2074b88d4f6203a35760a78ced8c983",
  terminalDom: "2aed54d3a2fdb4e76d6c0fe53e4a223992c116adda0826b08334e1a44d54848f",
  refreshLifecycle: "04f95460a984cf77cd07b7287db22363a38ee6201d164282f932aee10250d3a4",
});
const H4_6I_SEMANTIC_HASHES = Object.freeze({
  eventProjection: "7bd9960cdce1fe4e6cc79c96ebdb6201ecf36e34a3886415b20490268d5dbff6",
  parseErrorReceiptProjection: "4408c0eff96e0b57d370df9d6d04ab341c3f8d1d512aab9f5abeefd7f2603558",
  modelToolReceiptProjection: "d86effa558f902e0c15442c8bfe6de8127f7a33178ad77791b5671b432788e5a",
  sessionRoleContent: "dc6b9beeac5d404fd7fd7ff147e4cfb4bd8fdb9eef4fceebb399bbb93cb16497",
  sessionToolMeta: "f460fea9ea4f5fe16f53bace264c0ab3904b5fe5610ac8d82dcb824068f6c1da",
  activeDom: "e54e3de59dc8d46a78a819ae0b5b65d791462444e1b592cff96bff71c0226cac",
  terminalDom: "0c10ac9845c8e616e880ef9f693636390fffe942d390201d775d343ac0ab72e3",
  refreshLifecycle: "04f95460a984cf77cd07b7287db22363a38ee6201d164282f932aee10250d3a4",
});
const H4_6J_SEMANTIC_HASHES = Object.freeze({
  eventProjection: "8e0d1a69b13eb0c91eaea433f851f8c1ac4e6ce2e1561f2045bbfab19f846ce5",
  missingPathReceiptProjection: "989616f6ead8ea168f0f785627866befd8960d4221be83a36c2b6558764afda7",
  modelToolReceiptProjection: "027989be15a449c7cf563e2238404c093361ac7db5ef8dad367b1f6875c6e497",
  sessionRoleContent: "73166b500f99d97a978f7d5c8e057a50d3aa0ea44c062de8e12e13909f2d524b",
  sessionToolMeta: "b912f584b5b211e7b79d2ae517529bc89bbd4dcd77dfd5258b9c9434d5d3a6da",
  activeDom: "30ec16a776f8ecf36035827abb24185ec2d34050288f1db31ebbaf5f625c72da",
  terminalDom: "ee55a3e8a0629a776a81e4a411261227a9a708314f40a7bbcc5c01ce4b3b9c88",
  refreshLifecycle: "04f95460a984cf77cd07b7287db22363a38ee6201d164282f932aee10250d3a4",
});
const H4_6K_SEMANTIC_HASHES = Object.freeze({
  eventProjection: "1d02e735ad701d3394a2dae9eec019d4d22e97fb6fb111de1b90eaf09096aa07",
  retryExecutionProjection: "c4f4a8432ad9be01f331e72be1c9b6bd709bb7eda508c3b00604a2967d8c31fe",
  modelToolReceiptProjection: "4d02940043fc3266a6e6bf6e2a94ab7e775dd539401e84f40255daa29ed1b721",
  forcedFinalProjection: "30387bd58028a9ceef0f9d0cae7b9421c283570773270c995cf972e60e088ced",
  runtimeProjection: "cfe81b1df3da02903778c0c761e9efed2ce3464788c50d7d0af5231517315c1c",
  sessionRoleContent: "b9a2d2b56e618c0b939b4bd29690bcf20580cba69954aaf8cf704dd31f1367a2",
  sessionToolMeta: "76c4d8cfbc85aefd48242eedea1a13b66314430e17860a837b345142e7e6b211",
  terminalDom: "062793b9555a641084d28f70b8b3028af45ed40847f60ac547222c85dcba36f7",
  refreshLifecycle: "ae09c60e831dec8ffd7295e9baef598b898a1061ac85250d61e2e1936cc6fc44",
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

function stableInvalidToolResult(result) {
  return {
    ok: result?.ok === false ? false : result?.ok,
    action: String(result?.action || ""),
    errorCode: String(result?.errorCode || ""),
    errorPresent: Boolean(String(result?.error || "").trim()),
    failureCount: Number(result?.failureCount || 0),
    fieldErrors: (Array.isArray(result?.fieldErrors) ? result.fieldErrors : []).map((item) => ({
      field: String(item?.field || ""),
      reason: String(item?.reason || ""),
    })),
  };
}

function stableExecutorRangeToolResult(result) {
  const error = String(result?.error || "");
  return {
    ok: result?.ok === false ? false : result?.ok,
    action: String(result?.action || ""),
    errorCodePresent: Object.prototype.hasOwnProperty.call(result || {}, "errorCode"),
    errorPresent: Boolean(error.trim()),
    startLineMentioned: error.includes("startLine"),
    endLineMentioned: error.includes("endLine"),
    failureCount: Number(result?.failureCount || 0),
    fieldErrorsPresent: Object.prototype.hasOwnProperty.call(result || {}, "fieldErrors"),
    retryBlocked: Boolean(result?.retryBlocked),
    retryLimitReached: Boolean(result?.retryLimitReached),
  };
}

function stableRepeatedRangeFailureResult(result) {
  const error = String(result?.error || "");
  return {
    ok: result?.ok === false ? false : result?.ok,
    action: String(result?.action || ""),
    errorCode: String(result?.errorCode || ""),
    errorPresent: Boolean(error.trim()),
    startLineMentioned: error.includes("startLine"),
    endLineMentioned: error.includes("endLine"),
    failureCount: Number(result?.failureCount || 0),
    fieldErrorsPresent: Object.prototype.hasOwnProperty.call(result || {}, "fieldErrors"),
    retryBlocked: Boolean(result?.retryBlocked),
    retryLimitReached: Boolean(result?.retryLimitReached),
  };
}

const EXPECTED_REPEATED_RANGE_RESULTS = Object.freeze([
  Object.freeze({
    ok: false,
    action: "read_file",
    errorCode: "",
    errorPresent: true,
    startLineMentioned: true,
    endLineMentioned: true,
    failureCount: 1,
    fieldErrorsPresent: false,
    retryBlocked: false,
    retryLimitReached: false,
  }),
  Object.freeze({
    ok: false,
    action: "read_file",
    errorCode: "",
    errorPresent: true,
    startLineMentioned: true,
    endLineMentioned: true,
    failureCount: 2,
    fieldErrorsPresent: false,
    retryBlocked: false,
    retryLimitReached: false,
  }),
  Object.freeze({
    ok: false,
    action: "read_file",
    errorCode: "",
    errorPresent: true,
    startLineMentioned: true,
    endLineMentioned: true,
    failureCount: 3,
    fieldErrorsPresent: false,
    retryBlocked: false,
    retryLimitReached: true,
  }),
  Object.freeze({
    ok: false,
    action: "read_file",
    errorCode: "repeated_tool_failure",
    errorPresent: true,
    startLineMentioned: false,
    endLineMentioned: false,
    failureCount: 3,
    fieldErrorsPresent: false,
    retryBlocked: true,
    retryLimitReached: false,
  }),
]);

const REPEATED_RANGE_FAILURE_CONTRACT = Object.freeze({
  key: "H4-6K",
  userMarker: REPEATED_RANGE_FAILURE_USER,
  stageMarker: REPEATED_RANGE_FAILURE_STAGE,
  finalMarker: REPEATED_RANGE_FAILURE_FINAL,
  arguments: Object.freeze({ path: "fixture.txt", startLine: 2, endLine: 1 }),
  projectResult: stableRepeatedRangeFailureResult,
  hashes: H4_6K_SEMANTIC_HASHES,
});

function stableMissingFileToolResult(result) {
  const error = String(result?.error || "");
  return {
    ok: result?.ok === false ? false : result?.ok,
    action: String(result?.action || ""),
    errorCodePresent: Object.prototype.hasOwnProperty.call(result || {}, "errorCode"),
    codePresent: Object.prototype.hasOwnProperty.call(result || {}, "code"),
    missingFileError: error === "文件不存在",
    failureCount: Number(result?.failureCount || 0),
    fieldErrorsPresent: Object.prototype.hasOwnProperty.call(result || {}, "fieldErrors"),
    retryBlocked: Boolean(result?.retryBlocked),
    retryLimitReached: Boolean(result?.retryLimitReached),
  };
}

const EXPECTED_INVALID_TOOL_RESULT = Object.freeze({
  ok: false,
  action: "read_file",
  errorCode: "invalid_tool_arguments",
  errorPresent: true,
  failureCount: 1,
  fieldErrors: [{ field: "unexpected", reason: "additional_property" }],
});

const EXPECTED_PARSE_ERROR_TOOL_RESULT = Object.freeze({
  ok: false,
  action: "read_file",
  errorCode: "invalid_tool_arguments",
  errorPresent: true,
  failureCount: 1,
  fieldErrors: [],
});

const EXPECTED_MISSING_PATH_TOOL_RESULT = Object.freeze({
  ok: false,
  action: "read_file",
  errorCode: "invalid_tool_arguments",
  errorPresent: true,
  failureCount: 1,
  fieldErrors: [{ field: "path", reason: "required" }],
});

const EXPECTED_EXECUTOR_RANGE_RESULT = Object.freeze({
  ok: false,
  action: "read_file",
  errorCodePresent: false,
  errorPresent: true,
  startLineMentioned: true,
  endLineMentioned: true,
  failureCount: 1,
  fieldErrorsPresent: false,
  retryBlocked: false,
  retryLimitReached: false,
});

const EXPECTED_MISSING_FILE_RESULT = Object.freeze({
  ok: false,
  action: "read_file",
  errorCodePresent: false,
  codePresent: false,
  missingFileError: true,
  failureCount: 1,
  fieldErrorsPresent: false,
  retryBlocked: false,
  retryLimitReached: false,
});

const INVALID_TOOL_FAILURE_CONTRACT = Object.freeze({
  key: "H4-6E",
  userMarker: INVALID_TOOL_USER,
  stageMarker: INVALID_TOOL_STAGE,
  finalMarker: INVALID_TOOL_FINAL,
  arguments: Object.freeze({ path: "fixture.txt", unexpected: true }),
  projectResult: stableInvalidToolResult,
  expectedResult: EXPECTED_INVALID_TOOL_RESULT,
  receiptHashKey: "invalidReceiptProjection",
  chatCallScenario: "invalid-tool-call",
  chatFinalScenario: "invalid-tool-final",
  chatReceiptKey: "invalidReceipt",
  expectedDelegations: 0,
  expectedToolExecutions: Object.freeze([]),
  assertRawResult() {},
  hashes: H4_6E_SEMANTIC_HASHES,
  evidenceStem: "invalid-tool-arguments",
  domArgumentMarkers: Object.freeze(["unexpected"]),
  domResultMarkers: Object.freeze(["unexpected"]),
  expectedDomArguments: Object.freeze({
    pathPresent: true,
    unexpectedPresent: true,
    unexpectedCount: 1,
  }),
  expectedDomResult: Object.freeze({ present: true, unexpectedCount: 1, nonEmpty: true }),
  expectedSessionProjection: Object.freeze([
    { role: "user", marker: "user" },
    { role: "assistant", marker: "stage" },
    { role: "tool-call", contentPresent: true },
    { role: "tool-result", contentPresent: true, unexpectedCount: 1 },
    { role: "assistant", marker: "final" },
  ]),
  get expectedSessionToolMeta() {
    return [
      {
        role: "tool-call",
        toolCallId: "tool-1",
        agentRunId: "agent-1",
        agentEventType: "tool_started",
        agentEventSeq: 4,
        action: "read_file",
        arguments: this.arguments,
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
        arguments: null,
        native: true,
        replayed: false,
        outcome: "failed",
        result: this.expectedResult,
      },
    ];
  },
  sessionResultProjection(content) {
    return {
      contentPresent: Boolean(content.trim()),
      unexpectedCount: countOccurrences(content, "unexpected"),
    };
  },
  sessionArgumentsProjection(tool) {
    return { path: String(tool.path || ""), unexpected: tool.unexpected === true };
  },
  domArgumentsProjection(text) {
    return {
      pathPresent: text.includes('"path": "fixture.txt"'),
      unexpectedPresent: text.includes('"unexpected": true'),
      unexpectedCount: countOccurrences(text, "unexpected"),
    };
  },
  domResultProjection(text) {
    return {
      present: Boolean(text),
      unexpectedCount: countOccurrences(text, "unexpected"),
      nonEmpty: Boolean(text.trim()),
    };
  },
});

const PARSE_ERROR_TOOL_FAILURE_CONTRACT = Object.freeze({
  key: "H4-6I",
  userMarker: PARSE_ERROR_TOOL_USER,
  stageMarker: PARSE_ERROR_TOOL_STAGE,
  finalMarker: PARSE_ERROR_TOOL_FINAL,
  arguments: MALFORMED_TOOL_ARGUMENTS,
  projectResult: stableInvalidToolResult,
  expectedResult: EXPECTED_PARSE_ERROR_TOOL_RESULT,
  receiptHashKey: "parseErrorReceiptProjection",
  chatCallScenario: "parse-error-tool-call",
  chatFinalScenario: "parse-error-tool-final",
  chatReceiptKey: "parseErrorReceipt",
  expectedDelegations: 0,
  expectedToolExecutions: Object.freeze([]),
  assertRawResult(result) {
    expect(result).toMatchObject({
      ok: false,
      action: "read_file",
      errorCode: "invalid_tool_arguments",
      fieldErrors: [],
      failureCount: 1,
    });
    expect(String(result?.error || "").trim()).not.toBe("");
  },
  hashes: H4_6I_SEMANTIC_HASHES,
  runtimeCursors: Object.freeze({
    firstActive: 4,
    secondActive: 0,
    firstCompleted: 4,
    secondCompleted: 3,
  }),
  evidenceStem: "parse-error-tool-arguments",
  domPrimaryArgumentMarkers: Object.freeze([]),
  domArgumentMarkers: Object.freeze([]),
  domResultMarkers: Object.freeze([]),
  expectedDomArguments: Object.freeze({
    actionPresent: true,
    pathPresent: false,
    malformedRawPresent: false,
  }),
  expectedDomResult: Object.freeze({
    present: true,
    malformedRawPresent: false,
    nonEmpty: true,
  }),
  expectedSessionProjection: Object.freeze([
    { role: "user", marker: "user" },
    { role: "assistant", marker: "stage" },
    {
      role: "tool-call",
      contentPresent: true,
      pathPresent: false,
      malformedRawPresent: false,
    },
    {
      role: "tool-result",
      contentPresent: true,
      malformedRawPresent: false,
    },
    { role: "assistant", marker: "final" },
  ]),
  get expectedSessionToolMeta() {
    return [
      {
        role: "tool-call",
        toolCallId: "tool-1",
        agentRunId: "agent-1",
        agentEventType: "tool_started",
        agentEventSeq: 4,
        action: "read_file",
        arguments: {
          action: "read_file",
          pathPresent: false,
          malformedRawPresent: false,
        },
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
        arguments: null,
        native: true,
        replayed: false,
        outcome: "failed",
        result: this.expectedResult,
      },
    ];
  },
  sessionCallProjection(content) {
    return {
      contentPresent: Boolean(content.trim()),
      pathPresent: content.includes("fixture.txt"),
      malformedRawPresent: content.includes(MALFORMED_TOOL_ARGUMENTS),
    };
  },
  sessionResultProjection(content) {
    return {
      contentPresent: Boolean(content.trim()),
      malformedRawPresent: content.includes(MALFORMED_TOOL_ARGUMENTS),
    };
  },
  sessionArgumentsProjection(tool) {
    return {
      action: String(tool.action || ""),
      pathPresent: Object.prototype.hasOwnProperty.call(tool, "path"),
      malformedRawPresent: JSON.stringify(tool).includes(MALFORMED_TOOL_ARGUMENTS),
    };
  },
  domArgumentsProjection(text) {
    return {
      actionPresent: text.includes('"action": "read_file"'),
      pathPresent: text.includes("fixture.txt"),
      malformedRawPresent: text.includes(MALFORMED_TOOL_ARGUMENTS),
    };
  },
  domResultProjection(text) {
    return {
      present: Boolean(text),
      malformedRawPresent: text.includes(MALFORMED_TOOL_ARGUMENTS),
      nonEmpty: Boolean(text.trim()),
    };
  },
});

const MISSING_PATH_TOOL_FAILURE_CONTRACT = Object.freeze({
  key: "H4-6J",
  userMarker: MISSING_PATH_TOOL_USER,
  stageMarker: MISSING_PATH_TOOL_STAGE,
  finalMarker: MISSING_PATH_TOOL_FINAL,
  arguments: Object.freeze({}),
  rawArguments: MISSING_PATH_TOOL_ARGUMENTS,
  projectResult: stableInvalidToolResult,
  expectedResult: EXPECTED_MISSING_PATH_TOOL_RESULT,
  receiptHashKey: "missingPathReceiptProjection",
  chatCallScenario: "missing-path-tool-call",
  chatFinalScenario: "missing-path-tool-final",
  chatReceiptKey: "missingPathReceipt",
  expectedDelegations: 0,
  expectedToolExecutions: Object.freeze([]),
  assertRawResult(result) {
    expect(result).toMatchObject({
      ok: false,
      action: "read_file",
      errorCode: "invalid_tool_arguments",
      failureCount: 1,
    });
    expect(result?.fieldErrors).toEqual([{
      field: "path",
      reason: "required",
      message: "is required",
    }]);
    expect(String(result?.error || "").trim()).not.toBe("");
  },
  hashes: H4_6J_SEMANTIC_HASHES,
  runtimeCursors: Object.freeze({
    firstActive: 4,
    secondActive: 0,
    firstCompleted: 4,
    secondCompleted: 3,
  }),
  evidenceStem: "missing-path-tool-arguments",
  domPrimaryArgumentMarkers: Object.freeze([]),
  domArgumentMarkers: Object.freeze([]),
  domResultMarkers: Object.freeze(["required"]),
  expectedDomArguments: Object.freeze({
    actionPresent: true,
    pathPresent: false,
  }),
  expectedDomResult: Object.freeze({
    present: true,
    requiredFieldPresent: true,
    requiredReasonPresent: true,
    additionalPropertyPresent: false,
    nonEmpty: true,
  }),
  expectedSessionProjection: Object.freeze([
    { role: "user", marker: "user" },
    { role: "assistant", marker: "stage" },
    { role: "tool-call", contentPresent: true, actionPresent: true, pathPresent: false },
    {
      role: "tool-result",
      contentPresent: true,
      requiredFieldPresent: true,
      requiredReasonPresent: true,
      additionalPropertyPresent: false,
    },
    { role: "assistant", marker: "final" },
  ]),
  get expectedSessionToolMeta() {
    return [
      {
        role: "tool-call",
        toolCallId: "tool-1",
        agentRunId: "agent-1",
        agentEventType: "tool_started",
        agentEventSeq: 4,
        action: "read_file",
        arguments: { action: "read_file", pathPresent: false },
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
        arguments: null,
        native: true,
        replayed: false,
        outcome: "failed",
        result: this.expectedResult,
      },
    ];
  },
  sessionCallProjection(content) {
    return {
      contentPresent: Boolean(content.trim()),
      actionPresent: content.includes("read_file"),
      pathPresent: /[\"']?path[\"']?\s*:/.test(content),
    };
  },
  sessionResultProjection(content) {
    return {
      contentPresent: Boolean(content.trim()),
      requiredFieldPresent: /\bpath\b/.test(content),
      requiredReasonPresent: /\brequired\b/.test(content),
      additionalPropertyPresent: content.includes("additional_property"),
    };
  },
  sessionArgumentsProjection(tool) {
    return {
      action: String(tool.action || ""),
      pathPresent: Object.prototype.hasOwnProperty.call(tool, "path"),
    };
  },
  domArgumentsProjection(text) {
    return {
      actionPresent: text.includes('"action": "read_file"'),
      pathPresent: /[\"']?path[\"']?\s*:/.test(text),
    };
  },
  domResultProjection(text) {
    return {
      present: Boolean(text),
      requiredFieldPresent: /\bpath\b/.test(text),
      requiredReasonPresent: /\brequired\b/.test(text),
      additionalPropertyPresent: text.includes("additional_property"),
      nonEmpty: Boolean(text.trim()),
    };
  },
});

const EXECUTOR_RANGE_FAILURE_CONTRACT = Object.freeze({
  key: "H4-6G",
  userMarker: EXECUTOR_RANGE_USER,
  stageMarker: EXECUTOR_RANGE_STAGE,
  finalMarker: EXECUTOR_RANGE_FINAL,
  arguments: Object.freeze({ path: "fixture.txt", startLine: 2, endLine: 1 }),
  projectResult: stableExecutorRangeToolResult,
  expectedResult: EXPECTED_EXECUTOR_RANGE_RESULT,
  receiptHashKey: "executorReceiptProjection",
  chatCallScenario: "executor-range-call",
  chatFinalScenario: "executor-range-final",
  chatReceiptKey: "executorRangeReceipt",
  expectedDelegations: 1,
  expectedToolExecutions: Object.freeze([{
    action: "read_file",
    path: "fixture.txt",
    startLine: 2,
    endLine: 1,
  }]),
  assertRawResult(result) {
    expect(Object.prototype.hasOwnProperty.call(result || {}, "errorCode")).toBe(false);
    expect(Object.prototype.hasOwnProperty.call(result || {}, "fieldErrors")).toBe(false);
    expect(Object.prototype.hasOwnProperty.call(result || {}, "retryBlocked")).toBe(false);
    expect(Object.prototype.hasOwnProperty.call(result || {}, "retryLimitReached")).toBe(false);
    const error = String(result?.error || "");
    expect(error.trim()).not.toBe("");
    expect(error).toContain("startLine");
    expect(error).toContain("endLine");
  },
  hashes: H4_6G_SEMANTIC_HASHES,
  evidenceStem: "executor-range-failure",
  domArgumentMarkers: Object.freeze(["startLine", "endLine"]),
  domResultMarkers: Object.freeze(["startLine", "endLine"]),
  expectedDomArguments: Object.freeze({
    pathPresent: true,
    startLinePresent: true,
    endLinePresent: true,
  }),
  expectedDomResult: Object.freeze({
    present: true,
    startLineMentioned: true,
    endLineMentioned: true,
    nonEmpty: true,
  }),
  expectedSessionProjection: Object.freeze([
    { role: "user", marker: "user" },
    { role: "assistant", marker: "stage" },
    { role: "tool-call", contentPresent: true },
    {
      role: "tool-result",
      contentPresent: true,
      startLineMentioned: true,
      endLineMentioned: true,
    },
    { role: "assistant", marker: "final" },
  ]),
  get expectedSessionToolMeta() {
    return [
      {
        role: "tool-call",
        toolCallId: "tool-1",
        agentRunId: "agent-1",
        agentEventType: "tool_started",
        agentEventSeq: 4,
        action: "read_file",
        arguments: this.arguments,
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
        arguments: null,
        native: true,
        replayed: false,
        outcome: "failed",
        result: this.expectedResult,
      },
    ];
  },
  sessionResultProjection(content) {
    return {
      contentPresent: Boolean(content.trim()),
      startLineMentioned: content.includes("startLine"),
      endLineMentioned: content.includes("endLine"),
    };
  },
  sessionArgumentsProjection(tool) {
    return {
      path: String(tool.path || ""),
      startLine: tool.startLine ?? null,
      endLine: tool.endLine ?? null,
    };
  },
  domArgumentsProjection(text) {
    return {
      pathPresent: text.includes('"path": "fixture.txt"'),
      startLinePresent: text.includes('"startLine": 2'),
      endLinePresent: text.includes('"endLine": 1'),
    };
  },
  domResultProjection(text) {
    return {
      present: Boolean(text),
      startLineMentioned: text.includes("startLine"),
      endLineMentioned: text.includes("endLine"),
      nonEmpty: Boolean(text.trim()),
    };
  },
});

const MISSING_FILE_FAILURE_CONTRACT = Object.freeze({
  key: "H4-6H",
  userMarker: MISSING_FILE_USER,
  stageMarker: MISSING_FILE_STAGE,
  finalMarker: MISSING_FILE_FINAL,
  arguments: Object.freeze({ path: MISSING_READ_PATH }),
  projectResult: stableMissingFileToolResult,
  expectedResult: EXPECTED_MISSING_FILE_RESULT,
  receiptHashKey: "missingFileReceiptProjection",
  chatCallScenario: "missing-file-call",
  chatFinalScenario: "missing-file-final",
  chatReceiptKey: "missingFileReceipt",
  expectedDelegations: 1,
  expectedToolExecutions: Object.freeze([{
    action: "read_file",
    path: MISSING_READ_PATH,
  }]),
  assertRawResult(result) {
    expect(result).toEqual({
      ok: false,
      action: "read_file",
      error: "文件不存在",
      failureCount: 1,
    });
  },
  hashes: H4_6H_SEMANTIC_HASHES,
  runtimeCursors: Object.freeze({
    firstActive: 4,
    secondActive: 0,
    firstCompleted: 4,
    secondCompleted: 3,
  }),
  evidenceStem: "missing-file-executor-failure",
  missingReadPath: MISSING_READ_PATH,
  domArgumentMarkers: Object.freeze([MISSING_READ_PATH]),
  domResultMarkers: Object.freeze(["文件不存在"]),
  expectedDomArguments: Object.freeze({
    pathPresent: true,
  }),
  expectedDomResult: Object.freeze({
    present: true,
    missingFileErrorCount: 1,
    nonEmpty: true,
  }),
  expectedSessionProjection: Object.freeze([
    { role: "user", marker: "user" },
    { role: "assistant", marker: "stage" },
    { role: "tool-call", contentPresent: true },
    { role: "tool-result", contentPresent: true, missingFileErrorCount: 1 },
    { role: "assistant", marker: "final" },
  ]),
  get expectedSessionToolMeta() {
    return [
      {
        role: "tool-call",
        toolCallId: "tool-1",
        agentRunId: "agent-1",
        agentEventType: "tool_started",
        agentEventSeq: 4,
        action: "read_file",
        arguments: this.arguments,
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
        arguments: null,
        native: true,
        replayed: false,
        outcome: "failed",
        result: this.expectedResult,
      },
    ];
  },
  sessionResultProjection(content) {
    return {
      contentPresent: Boolean(content.trim()),
      missingFileErrorCount: countOccurrences(content, "文件不存在"),
    };
  },
  sessionArgumentsProjection(tool) {
    return { path: String(tool.path || "") };
  },
  domArgumentsProjection(text) {
    return {
      pathPresent: text.includes(`"path": "${MISSING_READ_PATH}"`),
    };
  },
  domResultProjection(text) {
    return {
      present: Boolean(text),
      missingFileErrorCount: countOccurrences(text, "文件不存在"),
      nonEmpty: Boolean(text.trim()),
    };
  },
});

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

function durableFailedToolTraceEvidence(snapshot, contract) {
  const baseEvidence = durableToolTraceEvidence(snapshot);
  const events = Array.isArray(snapshot?.events) ? snapshot.events : [];
  const executions = Array.isArray(snapshot?.toolExecutions) ? snapshot.toolExecutions : [];
  const runtimeAliases = new Map(
    baseEvidence.runtimeRunIds.map((runId, index) => [runId, `runtime-${index + 1}`]),
  );
  const toolAliases = new Map(
    baseEvidence.toolCallIds.map((toolCallId, index) => [toolCallId, `tool-${index + 1}`]),
  );
  const runtimeAlias = (runId) => runtimeAliases.get(String(runId || "")) || "";
  const toolAlias = (toolCallId) => toolAliases.get(String(toolCallId || "")) || "";
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
    if (data.failureCount != null) projection.failureCount = Number(data.failureCount);
    if (data.forcedFinal != null) projection.forcedFinal = Boolean(data.forcedFinal);
    if (data.result != null) projection.result = contract.projectResult(data.result);
    return projection;
  });
  const executionProjection = executions.map((execution) => ({
    toolCallId: toolAlias(execution?.toolCallId),
    name: String(execution?.name || ""),
    arguments: parseToolArguments(execution?.arguments),
    status: String(execution?.status || ""),
    outcome: String(execution?.outcome || ""),
    result: contract.projectResult(execution?.result),
  }));
  return {
    ...baseEvidence,
    eventProjection,
    eventProjectionHash: canonicalHash(eventProjection),
    executionProjection,
    executionProjectionHash: canonicalHash(executionProjection),
  };
}

function assertFailureContractRawArguments(snapshot, contract) {
  if (contract.rawArguments == null) return;
  const events = Array.isArray(snapshot?.events) ? snapshot.events : [];
  const modelCompleted = events.find((event) => event?.type === "model_completed");
  const toolStarted = events.find((event) => event?.type === "tool_started");
  const toolCompleted = events.find((event) => event?.type === "tool_completed");
  const executions = Array.isArray(snapshot?.toolExecutions) ? snapshot.toolExecutions : [];
  expect(modelCompleted?.data?.toolCalls?.[0]?.function?.arguments).toBe(contract.rawArguments);
  expect(toolStarted?.data?.arguments).toBe(contract.rawArguments);
  expect(toolCompleted?.data?.arguments).toBe(contract.rawArguments);
  expect(executions).toHaveLength(1);
  expect(executions[0]?.arguments).toBe(contract.rawArguments);
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

function multiSessionToolMetaProjection(messages, agentRunId, toolCallIds) {
  const aliases = new Map(toolCallIds.map((toolCallId, index) => [toolCallId, `tool-${index + 1}`]));
  return (Array.isArray(messages) ? messages : [])
    .filter((message) => message?.role === "tool-call" || message?.role === "tool-result")
    .map((message) => {
      const meta = message?.meta || {};
      const tool = meta.tool && typeof meta.tool === "object" ? meta.tool : {};
      const result = meta.result && typeof meta.result === "object"
        ? stableReadToolResult(meta.result)
        : null;
      return {
        role: String(message.role),
        toolCallId: aliases.get(String(meta.toolCallId || "")) || "mismatch",
        agentRunId: meta.agentRunId == null
          ? ""
          : (String(meta.agentRunId) === agentRunId ? "agent-1" : "mismatch"),
        agentEventType: String(meta.agentEventType || ""),
        agentEventSeq: Number(meta.agentEventSeq || 0),
        action: String(meta.action || ""),
        arguments: message.role === "tool-call" ? {
          path: String(tool.path || ""),
          startLine: tool.startLine ?? null,
          endLine: tool.endLine ?? null,
        } : null,
        path: String(meta.path || tool.path || ""),
        native: meta.native === true,
        replayed: Boolean(meta.replayed),
        outcome: String(meta.outcome || ""),
        result,
      };
    });
}

function failedToolSessionRoleContentProjection(messages, contract) {
  return (Array.isArray(messages) ? messages : []).map((message) => {
    const role = String(message?.role || "");
    const content = String(message?.content || "");
    if (role === "user") {
      return { role, marker: content === contract.userMarker ? "user" : "unexpected" };
    }
    if (role === "assistant") {
      return {
        role,
        marker: content === contract.stageMarker
          ? "stage"
          : (content === contract.finalMarker ? "final" : "unexpected"),
      };
    }
    if (role === "tool-call") {
      return contract.sessionCallProjection
        ? { role, ...contract.sessionCallProjection(content) }
        : { role, contentPresent: Boolean(content.trim()) };
    }
    if (role === "tool-result") {
      return { role, ...contract.sessionResultProjection(content) };
    }
    return { role, contentPresent: Boolean(content.trim()) };
  });
}

function failedToolSessionMetaProjection(messages, agentRunId, toolCallId, contract) {
  return (Array.isArray(messages) ? messages : [])
    .filter((message) => message?.role === "tool-call" || message?.role === "tool-result")
    .map((message) => {
      const meta = message?.meta || {};
      const tool = meta.tool && typeof meta.tool === "object" ? meta.tool : {};
      return {
        role: String(message.role),
        toolCallId: String(meta.toolCallId || "") === toolCallId ? "tool-1" : "mismatch",
        agentRunId: meta.agentRunId == null
          ? ""
          : (String(meta.agentRunId) === agentRunId ? "agent-1" : "mismatch"),
        agentEventType: String(meta.agentEventType || ""),
        agentEventSeq: Number(meta.agentEventSeq || 0),
        action: String(meta.action || ""),
        arguments: message.role === "tool-call"
          ? contract.sessionArgumentsProjection(tool)
          : null,
        native: meta.native === true,
        replayed: Boolean(meta.replayed),
        outcome: String(meta.outcome || ""),
        result: meta.result && typeof meta.result === "object"
          ? contract.projectResult(meta.result)
          : null,
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

async function failedToolLifecycleDomEvidence(page, contract) {
  const messages = page.locator("#messages");
  const user = messages.locator("article.msg.user").filter({ hasText: contract.userMarker });
  const commentary = messages.locator("article.msg.assistant.agent-commentary")
    .filter({ hasText: contract.stageMarker });
  const process = messages.locator("article.tool-process");
  const outer = process.locator("details.tool-process-stage");
  const item = process.locator("details.tool-process-item");
  const finalAnswer = messages.locator("article.msg.assistant")
    .filter({ hasText: contract.finalMarker });
  const details = item.locator(".tool-process-detail pre");
  await expect(user).toHaveCount(1);
  await expect(commentary).toHaveCount(1);
  await expect(process).toHaveCount(1);
  await expect(outer).toHaveCount(1);
  await expect(item).toHaveCount(1);
  await expect(details).toHaveCount(2);
  const detailTexts = await details.allTextContents();
  const argumentText = String(detailTexts[0] || "").trim();
  const resultText = String(detailTexts[1] || "").trim();
  const finalCount = await finalAnswer.count();
  const processKey = String(await outer.getAttribute("data-tool-process-key") || "");
  const outerClass = String(await outer.getAttribute("class") || "");
  const itemClass = String(await item.getAttribute("class") || "");
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
    userMarker: contract.userMarker,
    stageMarker: contract.stageMarker,
    finalMarker: contract.finalMarker,
  });
  const projection = {
    sequence: finalCount
      ? [contract.userMarker, contract.stageMarker, "read_file:failed", contract.finalMarker]
      : [contract.userMarker, contract.stageMarker, "read_file:failed"],
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
    processKey,
    outerOpen: await outer.evaluate((element) => element.open),
    itemOpen: await item.evaluate((element) => element.open),
    outerState: {
      running: outerClass.split(/\s+/).includes("running"),
      failed: outerClass.split(/\s+/).includes("failed"),
    },
    itemState: {
      failed: itemClass.split(/\s+/).includes("failed"),
    },
    currentAction: String(await outer.getAttribute("data-current-action") || ""),
    arguments: contract.domArgumentsProjection(argumentText),
    result: contract.domResultProjection(resultText),
    ordered,
  };
  return {
    process,
    outer,
    item,
    finalAnswer,
    details,
    projection,
    semanticHash: canonicalHash(projection),
  };
}

async function multiToolDetailLifecycleDomEvidence(page) {
  const messages = page.locator("#messages");
  const user = messages.locator("article.msg.user").filter({ hasText: MULTI_TOOL_USER });
  const commentary = messages.locator("article.msg.assistant.agent-commentary")
    .filter({ hasText: MULTI_TOOL_STAGE });
  const process = messages.locator("article.tool-process");
  const outer = process.locator("details.tool-process-stage");
  const items = process.locator("details.tool-process-item");
  const finalAnswer = messages.locator("article.msg.assistant")
    .filter({ hasText: MULTI_TOOL_FINAL });
  await expect(user).toHaveCount(1);
  await expect(commentary).toHaveCount(1);
  await expect(process).toHaveCount(1);
  await expect(outer).toHaveCount(1);
  await expect(items).toHaveCount(2);
  const itemLocators = await items.all();
  const itemProjections = [];
  for (const [index, item] of itemLocators.entries()) {
    const detailTexts = await item.locator(".tool-process-detail pre").allTextContents();
    const argumentText = String(detailTexts[0] || "").trim();
    const resultText = String(detailTexts[1] || "").trim();
    itemProjections.push({
      order: index + 1,
      className: String(await item.getAttribute("class") || ""),
      open: await item.evaluate((element) => element.open),
      heading: String(await item.locator(":scope > summary .tool-process-row-heading").textContent() || "").trim(),
      outcome: String(await item.locator(":scope > summary .tool-process-outcome").textContent() || "").trim(),
      argumentText,
      resultText,
      arguments: {
        pathPresent: argumentText.includes('"path": "fixture.txt"'),
        startLinePresent: argumentText.includes('"startLine": 1'),
        endLinePresent: argumentText.includes('"endLine": 1'),
      },
      formattedResult: {
        present: Boolean(resultText),
        pathPresent: resultText.includes("fixture.txt"),
        sizePresent: resultText.includes("26 B"),
        fixtureContentCount: countOccurrences(resultText, FIXTURE_CONTENT.trim()),
      },
    });
  }
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
    userMarker: MULTI_TOOL_USER,
    stageMarker: MULTI_TOOL_STAGE,
    finalMarker: MULTI_TOOL_FINAL,
  });
  const projection = {
    sequence: finalCount
      ? [MULTI_TOOL_USER, MULTI_TOOL_STAGE, "read_file:1", "read_file:2", MULTI_TOOL_FINAL]
      : [MULTI_TOOL_USER, MULTI_TOOL_STAGE, "read_file:1", "read_file:2"],
    counts: {
      user: 1,
      commentary: 1,
      toolProcess: 1,
      toolItems: itemProjections.length,
      results: itemProjections.filter((item) => item.formattedResult.present).length,
      final: finalCount,
      ordinaryAssistant: await messages.locator("article.msg.assistant:not(.tool-process)").count(),
      assistantTotal: await messages.locator("article.msg.assistant").count(),
    },
    processKey: String(processKey || ""),
    outerOpen: await outer.evaluate((element) => element.open),
    stageClass: String(await outer.getAttribute("class") || ""),
    currentAction: String(await outer.getAttribute("data-current-action") || ""),
    heading: String(await outer.locator(".tool-process-stage-heading").textContent() || "").trim(),
    items: itemProjections,
    ordered,
  };
  return {
    process,
    outer,
    items: itemLocators,
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

async function assertDirectClassicEntry(page) {
  await expect(page.locator("html")).toHaveAttribute("data-frontend-runtime", "classic-fallback");
  expect(await page.locator("html").getAttribute("data-code-frontend-ready")).toBeNull();
  const currentUrl = new URL(page.url());
  expect(currentUrl.pathname).toBe(CLASSIC_FALLBACK_PATH);
  expect(currentUrl.search).toBe("");
}

async function pathIsMissing(filePath) {
  try {
    await fs.stat(filePath);
    return false;
  } catch (error) {
    if (error?.code === "ENOENT") return true;
    throw error;
  }
}

async function assertFailureContractFilesystem(h4, contract) {
  if (!contract.missingReadPath) return null;
  expect(path.isAbsolute(contract.missingReadPath)).toBe(false);
  expect(contract.missingReadPath.split(/[\\/]+/)).not.toContain("..");
  const projectRoot = path.resolve(h4.host.projectDir);
  const projectTarget = path.resolve(projectRoot, contract.missingReadPath);
  const isolatedHome = path.resolve(h4.host.root, "home");
  const homeTarget = path.resolve(isolatedHome, contract.missingReadPath);
  expect(path.dirname(projectTarget)).toBe(projectRoot);
  expect(path.dirname(homeTarget)).toBe(isolatedHome);
  const audit = {
    safeRelativePath: true,
    projectTargetMissing: await pathIsMissing(projectTarget),
    isolatedHomeTargetMissing: await pathIsMissing(homeTarget),
  };
  expect(audit).toEqual({
    safeRelativePath: true,
    projectTargetMissing: true,
    isolatedHomeTargetMissing: true,
  });
  return audit;
}

async function completeToolFailureLifecycle(h4, runtime, contract) {
  const { page } = h4;
  const requestBoundary = h4.requestBoundary();
  await h4.open(runtime);
  await assertFrontendRuntime(page, runtime);
  if (runtime === "classic") await assertDirectClassicEntry(page);
  await h4.proveNonLoopbackBlocked();
  const pathAuditBefore = await assertFailureContractFilesystem(h4, contract);
  await h4.submitGated(contract.userMarker);
  const finalDeltaGate = await h4.waitGate(TOOL_FINAL_DELTA_GATE);
  expect(finalDeltaGate[TOOL_FINAL_DELTA_GATE]).toMatchObject({
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
  expect(activeAgent.body.pendingToolCalls).toEqual([]);
  const activeTrace = durableFailedToolTraceEvidence(activeAgent.body, contract);
  assertFailureContractRawArguments(activeAgent.body, contract);
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
    arguments: contract.arguments,
    status: "completed",
    outcome: "failed",
    result: contract.expectedResult,
  }]);
  expect(activeTrace.eventProjection[2]?.toolCalls).toEqual([{
    toolCallId: "tool-1",
    name: "read_file",
    arguments: contract.arguments,
  }]);
  expect(activeTrace.eventProjection[3]).toMatchObject({
    type: "tool_started",
    toolCallId: "tool-1",
    name: "read_file",
    arguments: contract.arguments,
  });
  expect(activeTrace.eventProjection[4]).toMatchObject({
    type: "tool_completed",
    toolCallId: "tool-1",
    name: "read_file",
    outcome: "failed",
    result: contract.expectedResult,
  });
  contract.assertRawResult(activeAgent.body.toolExecutions?.[0]?.result);
  contract.assertRawResult(activeAgent.body.events?.[4]?.data?.result);

  const modelStartedEvents = activeAgent.body.events.filter((event) => event?.type === "model_started");
  expect(modelStartedEvents).toHaveLength(2);
  const firstRuntimeRunId = String(modelStartedEvents[0]?.data?.runtimeRunId || "");
  const secondRuntimeRunId = String(modelStartedEvents[1]?.data?.runtimeRunId || "");
  expect(firstRuntimeRunId).not.toBe("");
  expect(secondRuntimeRunId).not.toBe("");
  expect(activeAgent.body.activeRuntimeRunId).toBe(secondRuntimeRunId);
  const firstRuntimeActive = await fetchProductionJson(
    page,
    `/api/runtime/runs/${encodeURIComponent(firstRuntimeRunId)}?cursor=0&wait=0`,
  );
  const secondRuntimeActive = await fetchProductionJson(
    page,
    `/api/runtime/runs/${encodeURIComponent(secondRuntimeRunId)}?cursor=0&wait=0`,
  );
  expect(firstRuntimeActive.status).toBe(200);
  expect(firstRuntimeActive.body).toMatchObject({
    runId: firstRuntimeRunId,
    sessionId: activeAgent.body.sessionId,
    status: "completed",
  });
  expect(firstRuntimeActive.body.result?.content).toBe(contract.stageMarker);
  expect(secondRuntimeActive.status).toBe(200);
  expect(secondRuntimeActive.body).toMatchObject({
    runId: secondRuntimeRunId,
    sessionId: activeAgent.body.sessionId,
    status: "running",
  });
  expect(secondRuntimeActive.body.events).toEqual([]);
  expect(secondRuntimeActive.body.result?.content).toBe("");
  const expectedRuntimeCursors = contract.runtimeCursors === null
    ? null
    : (contract.runtimeCursors || {
      firstActive: 4,
      secondActive: 0,
      firstCompleted: 4,
      secondCompleted: 3,
    });
  if (expectedRuntimeCursors) {
    expect(Number(firstRuntimeActive.body.nextCursor || 0)).toBe(expectedRuntimeCursors.firstActive);
    expect(Number(secondRuntimeActive.body.nextCursor || 0)).toBe(expectedRuntimeCursors.secondActive);
  }
  expect(h4.controlIds()).toEqual({
    agentRunIds: [agentRunId],
    runtimeRunIds: [firstRuntimeRunId, secondRuntimeRunId],
  });

  const process = page.locator("#messages article.tool-process");
  const items = process.locator("details.tool-process-item");
  await expect(process).toHaveCount(1);
  await expect(items).toHaveCount(1);
  await expect(items).toHaveClass(/\bfailed\b/);
  await expect(items.locator(".tool-process-detail pre")).toHaveCount(2);
  for (const marker of contract.domPrimaryArgumentMarkers || ["fixture.txt"]) {
    await expect(items.locator(".tool-process-detail pre").first()).toContainText(marker);
  }
  for (const marker of contract.domArgumentMarkers) {
    await expect(items.locator(".tool-process-detail pre").first()).toContainText(marker);
  }
  for (const marker of contract.domResultMarkers) {
    await expect(items.locator(".tool-process-detail pre").last()).toContainText(marker);
  }
  const initialDom = await failedToolLifecycleDomEvidence(page, contract);
  expect(String(await initialDom.outer.locator(".tool-process-stage-heading").textContent() || "").trim())
    .not.toBe("");
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
    outerState: { running: true, failed: false },
    itemState: { failed: true },
    currentAction: "read_file",
    arguments: contract.expectedDomArguments,
    result: contract.expectedDomResult,
    ordered: true,
  });
  expect(initialDom.projection.processKey).toBe("0:1");
  const oldStage = await initialDom.outer.elementHandle();
  await initialDom.outer.locator(":scope > summary.tool-process-stage-summary").click();
  await expect(initialDom.outer).toHaveAttribute("open", "");
  const firstItemNode = await initialDom.item.elementHandle();
  const firstSummaryNode = await initialDom.item.locator(":scope > summary").elementHandle();
  expect(firstItemNode).not.toBeNull();
  expect(firstSummaryNode).not.toBeNull();
  expect(await firstItemNode.evaluate((item, summary) => (
    item.querySelector(":scope > summary") === summary
  ), firstSummaryNode)).toBe(true);
  await initialDom.item.locator(":scope > summary").click();
  await expect(initialDom.item).toHaveAttribute("open", "");
  const openedItemNode = await initialDom.item.elementHandle();
  const openedSummaryNode = await initialDom.item.locator(":scope > summary").elementHandle();
  expect(openedItemNode).not.toBeNull();
  expect(openedSummaryNode).not.toBeNull();
  const capturedItemConnectedAfterFirst = await firstItemNode.evaluate((item) => item.isConnected);
  const openedItemIsCapturedItem = await firstItemNode.evaluate(
    (item, opened) => item === opened,
    openedItemNode,
  );
  const firstOpenImmediately = await openedItemNode.evaluate((item) => item.open);
  h4.diagnosticSteps.push({
    step: "failed-tool-item-first-click",
    capturedItemConnectedAfterFirst,
    capturedSummaryConnectedAfterFirst: await firstSummaryNode.evaluate((summary) => summary.isConnected),
    openedItemIsCapturedItem,
    openedSummaryMatchesItem: await openedItemNode.evaluate((item, summary) => (
      item.querySelector(":scope > summary") === summary
    ), openedSummaryNode),
    openImmediately: firstOpenImmediately,
  });
  expect(firstOpenImmediately).toBe(true);
  for (const marker of contract.domPrimaryArgumentMarkers || ["fixture.txt"]) {
    await expect(initialDom.details.first()).toContainText(marker);
  }
  for (const marker of contract.domArgumentMarkers) {
    await expect(initialDom.details.first()).toContainText(marker);
  }
  for (const marker of contract.domResultMarkers) {
    await expect(initialDom.details.last()).toContainText(marker);
  }
  const currentItemNode = await initialDom.item.elementHandle();
  const currentSummaryNode = await initialDom.item.locator(":scope > summary").elementHandle();
  expect(currentItemNode).not.toBeNull();
  expect(currentSummaryNode).not.toBeNull();
  const openedItemConnectedBeforeSecond = await openedItemNode.evaluate((item) => item.isConnected);
  const currentIsOpenedItem = await openedItemNode.evaluate((item, current) => item === current, currentItemNode);
  const currentSummaryIsOpenedSummary = await openedSummaryNode.evaluate(
    (summary, current) => summary === current,
    currentSummaryNode,
  );
  const currentOpenBeforeSecond = await currentItemNode.evaluate((item) => item.open);
  const currentSummaryMatchesItem = await currentItemNode.evaluate((item, summary) => (
    item.querySelector(":scope > summary") === summary
  ), currentSummaryNode);
  if (currentOpenBeforeSecond) {
    await currentSummaryNode.click();
  } else {
    expect(openedItemConnectedBeforeSecond).toBe(false);
    expect(currentIsOpenedItem).toBe(false);
  }
  const currentOpenAfterSecond = await currentItemNode.evaluate((item) => item.open);
  h4.diagnosticSteps.push({
    step: "failed-tool-item-second-click",
    openedItemConnectedBeforeSecond,
    currentIsOpenedItem,
    currentSummaryIsOpenedSummary,
    currentSummaryMatchesItem,
    currentOpenBeforeSecond,
    currentOpenAfterSecond,
    currentConnectedAfterSecond: await currentItemNode.evaluate((item) => item.isConnected),
    currentSummaryConnectedAfterSecond: await currentSummaryNode.evaluate((summary) => summary.isConnected),
  });
  expect(currentOpenAfterSecond).toBe(false);
  await expect(initialDom.item).not.toHaveAttribute("open", "");

  await h4.releaseGate(TOOL_FINAL_DELTA_GATE);
  await expect(initialDom.finalAnswer).toHaveCount(1);
  const terminalGate = await h4.waitGate(TOOL_TERMINAL_GATE);
  expect(terminalGate[TOOL_TERMINAL_GATE]).toMatchObject({ reached: true, released: false });
  expect(await oldStage.evaluate((element) => element.isConnected)).toBe(false);
  const afterFinalDeltaDom = await failedToolLifecycleDomEvidence(page, contract);
  expect(afterFinalDeltaDom.projection.processKey).toBe(initialDom.projection.processKey);
  expect(afterFinalDeltaDom.projection.outerOpen).toBe(true);
  expect(afterFinalDeltaDom.projection.itemOpen).toBe(false);
  expect(afterFinalDeltaDom.projection.outerState).toEqual({ running: false, failed: true });
  expect(afterFinalDeltaDom.projection.itemState).toEqual({ failed: true });
  expect(afterFinalDeltaDom.projection.counts).toMatchObject({
    user: 1,
    commentary: 1,
    toolProcess: 1,
    toolItem: 1,
    result: 1,
    final: 1,
    ordinaryAssistant: 2,
    assistantTotal: 3,
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
      activeRuntimeRunId: completedAgent.body?.activeRuntimeRunId,
      eventTypes: (completedAgent.body?.events || []).map((event) => event.type),
    };
  }).toEqual({
    status: "completed",
    nextCursor: 9,
    activeRuntimeRunId: "",
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
  expect(completedAgent.body.pendingToolCalls).toEqual([]);
  const completedTrace = durableFailedToolTraceEvidence(completedAgent.body, contract);
  assertFailureContractRawArguments(completedAgent.body, contract);
  expect(completedTrace.executionProjection).toEqual(activeTrace.executionProjection);
  expect(completedTrace.terminalEventCount).toBe(1);
  await expect(page.locator("#activeRunBanner.visible")).toHaveCount(0);
  await expect(page.locator("#stopBtn")).toBeDisabled();
  await expect(page.locator("#messages .execution-trace.active")).toHaveCount(0);
  await expect(page.locator("#messages .execution-trace.completed")).toHaveCount(1);

  const terminalDom = await failedToolLifecycleDomEvidence(page, contract);
  expect(String(await terminalDom.outer.locator(".tool-process-stage-heading").textContent() || "").trim())
    .not.toBe("");
  expect(terminalDom.projection.processKey).toBe(initialDom.projection.processKey);
  expect(terminalDom.projection.outerOpen).toBe(false);
  expect(terminalDom.projection.itemOpen).toBe(false);
  expect(terminalDom.projection.outerState).toEqual({ running: false, failed: true });
  expect(terminalDom.projection.itemState).toEqual({ failed: true });
  expect(terminalDom.projection.counts).toMatchObject({
    user: 1,
    commentary: 1,
    toolProcess: 1,
    toolItem: 1,
    result: 1,
    final: 1,
    ordinaryAssistant: 2,
    assistantTotal: 3,
  });

  const completedTraceElement = page.locator("#messages .execution-trace.completed");
  const completedTraceToggle = completedTraceElement.locator(":scope > [data-execution-trace-toggle]");
  await expect(completedTraceElement).not.toHaveClass(/\bis-expanded\b/);
  await expect(completedTraceToggle).toHaveAttribute("aria-expanded", "false");
  await completedTraceToggle.click();
  await expect(completedTraceElement).toHaveClass(/\bis-expanded\b/);
  await expect(completedTraceToggle).toHaveAttribute("aria-expanded", "true");
  await terminalDom.outer.locator(":scope > summary.tool-process-stage-summary").click();
  await expect(terminalDom.outer).toHaveAttribute("open", "");
  await terminalDom.item.locator(":scope > summary").click();
  await expect(terminalDom.item).toHaveAttribute("open", "");
  for (const marker of contract.domPrimaryArgumentMarkers || ["fixture.txt"]) {
    await expect(terminalDom.details.first()).toContainText(marker);
  }
  for (const marker of contract.domArgumentMarkers) {
    await expect(terminalDom.details.first()).toContainText(marker);
  }
  for (const marker of contract.domResultMarkers) {
    await expect(terminalDom.details.last()).toContainText(marker);
  }
  await terminalDom.item.locator(":scope > summary").click();
  await expect(terminalDom.item).not.toHaveAttribute("open", "");
  await terminalDom.outer.locator(":scope > summary.tool-process-stage-summary").click();
  await expect(terminalDom.outer).not.toHaveAttribute("open", "");
  await completedTraceToggle.click();
  await expect(completedTraceElement).not.toHaveClass(/\bis-expanded\b/);
  await expect(completedTraceToggle).toHaveAttribute("aria-expanded", "false");

  const firstRuntimeCompleted = await fetchProductionJson(
    page,
    `/api/runtime/runs/${encodeURIComponent(firstRuntimeRunId)}?cursor=0&wait=0`,
  );
  const secondRuntimeCompleted = await fetchProductionJson(
    page,
    `/api/runtime/runs/${encodeURIComponent(secondRuntimeRunId)}?cursor=0&wait=0`,
  );
  expect(firstRuntimeCompleted.status).toBe(200);
  expect(secondRuntimeCompleted.status).toBe(200);
  expect(firstRuntimeCompleted.body.status).toBe("completed");
  expect(secondRuntimeCompleted.body.status).toBe("completed");
  if (expectedRuntimeCursors) {
    expect(Number(firstRuntimeCompleted.body.nextCursor || 0)).toBe(expectedRuntimeCursors.firstCompleted);
    expect(Number(secondRuntimeCompleted.body.nextCursor || 0)).toBe(expectedRuntimeCursors.secondCompleted);
  }
  expect(firstRuntimeCompleted.body.result?.content).toBe(contract.stageMarker);
  expect(secondRuntimeCompleted.body.result?.content).toBe(contract.finalMarker);

  const sessionButton = page.locator("#sessionList .session-row.active button.session-main");
  await expect(sessionButton).toHaveCount(1);
  const sessionId = await sessionButton.getAttribute("data-session-id");
  expect(sessionId).toBeTruthy();
  const sessionResponse = await fetchProductionJson(
    page,
    `/api/sessions/${encodeURIComponent(sessionId)}`,
  );
  expect(sessionResponse.status).toBe(200);
  expect((sessionResponse.body.messages || []).map((message) => message.role)).toEqual([
    "user",
    "assistant",
    "tool-call",
    "tool-result",
    "assistant",
  ]);
  const sessionProjection = failedToolSessionRoleContentProjection(
    sessionResponse.body.messages,
    contract,
  );
  expect(sessionProjection).toEqual(contract.expectedSessionProjection);
  const sessionToolMeta = failedToolSessionMetaProjection(
    sessionResponse.body.messages,
    agentRunId,
    toolCallId,
    contract,
  );
  expect(sessionToolMeta).toEqual(contract.expectedSessionToolMeta);

  const durable = await readDurableAgentRecord(h4, agentRunId);
  expect(durable.record.status).toBe("completed");
  expect(durable.record.nextSeq).toBe(10);
  expect(durable.record.pendingToolCalls).toEqual([]);
  expect(durable.record.events).toHaveLength(9);
  expect(Object.keys(durable.record.toolExecutions || {})).toEqual([toolCallId]);
  if (contract.rawArguments != null) {
    expect(durable.record.toolExecutions[toolCallId]?.arguments).toBe(contract.rawArguments);
  }
  expect(contract.projectResult(durable.record.toolExecutions[toolCallId]?.result)).toEqual(
    contract.expectedResult,
  );
  contract.assertRawResult(durable.record.toolExecutions[toolCallId]?.result);

  const metrics = await h4.metrics();
  const expectedModelReceipt = {
    role: "tool",
    toolCallId: "tool-1",
    name: "read_file",
    ...contract.expectedResult,
  };
  expect(metrics.chatRequests).toEqual([
    { scenario: contract.chatCallScenario, stream: true, hasToolResult: false },
    {
      scenario: contract.chatFinalScenario,
      stream: true,
      hasToolResult: true,
      [contract.chatReceiptKey]: expectedModelReceipt,
    },
  ]);
  expect(metrics.toolExecutions).toEqual(contract.expectedToolExecutions);
  expect(metrics.productionToolDelegations).toBe(contract.expectedDelegations);
  expect(metrics.unsafeToolRequests).toBe(0);
  const pathAuditAfterExecution = await assertFailureContractFilesystem(h4, contract);
  const requests = h4.requestEvidenceSince(requestBoundary);
  expect(requests.agentPost).toBe(1);
  expect(requests.runtimePost).toBe(0);
  expect(requests.agentDelete).toBe(0);
  expect(h4.pageErrors).toEqual([]);

  const hashes = {
    eventProjection: completedTrace.eventProjectionHash,
    [contract.receiptHashKey]: completedTrace.executionProjectionHash,
    modelToolReceiptProjection: canonicalHash(expectedModelReceipt),
    sessionRoleContent: canonicalHash(sessionProjection),
    sessionToolMeta: canonicalHash(sessionToolMeta),
    activeDom: afterFinalDeltaDom.semanticHash,
    terminalDom: terminalDom.semanticHash,
  };
  if (Object.keys(contract.hashes).length) {
    for (const [key, value] of Object.entries(hashes)) {
      expect(value, `${contract.key} ${key}`).toBe(contract.hashes[key]);
    }
  }
  h4.evidence(
    `${runtime === "classic" ? "classic-" : ""}${contract.evidenceStem}-active-to-terminal`,
    {
      identity: {
        agentRunId: idHash(agentRunId),
        toolCallId: idHash(toolCallId),
        runtimeRunIds: [idHash(firstRuntimeRunId), idHash(secondRuntimeRunId)],
        processKey: terminalDom.projection.processKey,
      },
      runtimeCursors: {
        firstActive: Number(firstRuntimeActive.body.nextCursor || 0),
        secondActive: Number(secondRuntimeActive.body.nextCursor || 0),
        firstCompleted: Number(firstRuntimeCompleted.body.nextCursor || 0),
        secondCompleted: Number(secondRuntimeCompleted.body.nextCursor || 0),
      },
      receipt: contract.expectedResult,
      modelToolReceipt: expectedModelReceipt,
      requests: {
        agentPost: requests.agentPost,
        runtimePost: requests.runtimePost,
        chat: metrics.chatRequests.length,
        productionToolDelegations: metrics.productionToolDelegations,
        toolExecutions: metrics.toolExecutions.length,
      },
      pathAudit: pathAuditAfterExecution,
      hashes,
    },
  );
  return {
    page,
    agentRunId,
    toolCallId,
    sessionId,
    firstRuntimeRunId,
    secondRuntimeRunId,
    completedTrace,
    sessionProjection,
    sessionToolMeta,
    terminalDom,
    metrics,
    hashes,
    pathAuditBefore,
    pathAuditAfterExecution,
  };
}

test("invalid read_file arguments fail before execution and complete with final answer", async ({ h4 }) => {
  await completeToolFailureLifecycle(h4, "bundle", INVALID_TOOL_FAILURE_CONTRACT);
});

test("classic invalid read_file arguments fail before execution and complete with final answer", async ({ h4 }) => {
  await completeToolFailureLifecycle(h4, "classic", INVALID_TOOL_FAILURE_CONTRACT);
});

async function exerciseToolFailureTerminalRefresh(h4, runtime, contract) {
  const before = await completeToolFailureLifecycle(h4, runtime, contract);
  const refreshBoundary = h4.requestBoundary();
  const metricsBefore = await h4.metrics();
  await before.page.reload({ waitUntil: "domcontentloaded" });
  await assertFrontendRuntime(before.page, runtime);
  if (runtime === "classic") await assertDirectClassicEntry(before.page);
  const persistedSession = before.page.locator(
    `#sessionList button.session-main[data-session-id="${before.sessionId}"]`,
  );
  await expect(persistedSession).toHaveCount(1);
  await persistedSession.click();

  await expect(before.page.locator("#activeRunBanner.visible")).toHaveCount(0);
  await expect(before.page.locator("#stopBtn")).toBeDisabled();
  await expect(before.page.locator("#messages .execution-trace.active")).toHaveCount(0);
  await expect(before.page.locator("#messages .execution-trace.completed")).toHaveCount(1);
  const domAfter = await failedToolLifecycleDomEvidence(before.page, contract);
  expect(domAfter.projection).toEqual(before.terminalDom.projection);
  expect(domAfter.projection.outerOpen).toBe(false);
  expect(domAfter.projection.itemOpen).toBe(false);
  expect(domAfter.projection.outerState).toEqual({ running: false, failed: true });
  expect(domAfter.projection.itemState).toEqual({ failed: true });

  const traceAfterReload = before.page.locator("#messages .execution-trace.completed");
  const traceToggleAfterReload = traceAfterReload.locator(":scope > [data-execution-trace-toggle]");
  await expect(traceAfterReload).not.toHaveClass(/\bis-expanded\b/);
  await expect(traceToggleAfterReload).toHaveAttribute("aria-expanded", "false");
  await traceToggleAfterReload.click();
  await expect(traceAfterReload).toHaveClass(/\bis-expanded\b/);
  await domAfter.outer.locator(":scope > summary.tool-process-stage-summary").click();
  await expect(domAfter.outer).toHaveAttribute("open", "");
  await domAfter.item.locator(":scope > summary").click();
  await expect(domAfter.item).toHaveAttribute("open", "");
  for (const marker of contract.domPrimaryArgumentMarkers || ["fixture.txt"]) {
    await expect(domAfter.details.first()).toContainText(marker);
  }
  for (const marker of contract.domArgumentMarkers) {
    await expect(domAfter.details.first()).toContainText(marker);
  }
  for (const marker of contract.domResultMarkers) {
    await expect(domAfter.details.last()).toContainText(marker);
  }
  await domAfter.item.locator(":scope > summary").click();
  await domAfter.outer.locator(":scope > summary.tool-process-stage-summary").click();
  await traceToggleAfterReload.click();
  await expect(traceAfterReload).not.toHaveClass(/\bis-expanded\b/);
  await expect(traceToggleAfterReload).toHaveAttribute("aria-expanded", "false");

  const agentAfter = await fetchProductionJson(
    before.page,
    `/api/agent/runs/${encodeURIComponent(before.agentRunId)}?cursor=0&wait=0`,
  );
  expect(agentAfter.status).toBe(200);
  const completedTraceAfter = durableFailedToolTraceEvidence(agentAfter.body, contract);
  expect(completedTraceAfter).toEqual(before.completedTrace);
  expect(completedTraceAfter.toolCallIds).toEqual([before.toolCallId]);
  const sessionAfter = await fetchProductionJson(
    before.page,
    `/api/sessions/${encodeURIComponent(before.sessionId)}`,
  );
  expect(sessionAfter.status).toBe(200);
  const sessionProjectionAfter = failedToolSessionRoleContentProjection(
    sessionAfter.body.messages,
    contract,
  );
  const sessionToolMetaAfter = failedToolSessionMetaProjection(
    sessionAfter.body.messages,
    before.agentRunId,
    before.toolCallId,
    contract,
  );
  expect(sessionProjectionAfter).toEqual(before.sessionProjection);
  expect(sessionToolMetaAfter).toEqual(before.sessionToolMeta);

  const metricsAfter = await h4.metrics();
  expect(metricsAfter.chatRequests).toEqual(metricsBefore.chatRequests);
  expect(metricsAfter.toolExecutions).toEqual(contract.expectedToolExecutions);
  expect(metricsAfter.productionToolDelegations).toBe(contract.expectedDelegations);
  expect(metricsAfter.unsafeToolRequests).toBe(0);
  const pathAuditAfterRefresh = await assertFailureContractFilesystem(h4, contract);
  const refreshRequests = h4.requestEvidenceSince(refreshBoundary);
  expect(refreshRequests.agentPost).toBe(0);
  expect(refreshRequests.runtimePost).toBe(0);
  expect(refreshRequests.agentDelete).toBe(0);
  expect(h4.controlIds()).toEqual({
    agentRunIds: [before.agentRunId],
    runtimeRunIds: [before.firstRuntimeRunId, before.secondRuntimeRunId],
  });
  expect(h4.pageErrors).toEqual([]);

  const refreshProjection = {
    agentRunStable: completedTraceAfter.agentRunId === before.completedTrace.agentRunId,
    toolCallStable: completedTraceAfter.toolCallIdHashes[0]
      === before.completedTrace.toolCallIdHashes[0],
    eventProjectionStable: completedTraceAfter.eventProjectionHash
      === before.completedTrace.eventProjectionHash,
    sessionProjectionStable: JSON.stringify(sessionProjectionAfter)
      === JSON.stringify(before.sessionProjection),
    sessionToolMetaStable: JSON.stringify(sessionToolMetaAfter)
      === JSON.stringify(before.sessionToolMeta),
    processKeyStable: domAfter.projection.processKey === before.terminalDom.projection.processKey,
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
    ...before.hashes,
    refreshLifecycle: canonicalHash(refreshProjection),
  };
  if (Object.keys(contract.hashes).length) {
    expect(hashes).toEqual(contract.hashes);
  }
  h4.evidence(
    `${runtime === "classic" ? "classic-" : ""}${contract.evidenceStem}-terminal-refresh`,
    {
      identity: {
        agentRunId: idHash(before.agentRunId),
        toolCallId: idHash(before.toolCallId),
        processKey: domAfter.projection.processKey,
      },
      refresh: refreshProjection,
      pathAudit: pathAuditAfterRefresh,
      hashes,
    },
  );
}

test("completed invalid read_file receipt reloads uniquely without execution", async ({ h4 }) => {
  await exerciseToolFailureTerminalRefresh(h4, "bundle", INVALID_TOOL_FAILURE_CONTRACT);
});

test("completed classic invalid read_file receipt reloads uniquely without execution", async ({ h4 }) => {
  await exerciseToolFailureTerminalRefresh(h4, "classic", INVALID_TOOL_FAILURE_CONTRACT);
});

test("bundle executor-range failure lifecycle and reload", async ({ h4 }) => {
  await exerciseToolFailureTerminalRefresh(h4, "bundle", EXECUTOR_RANGE_FAILURE_CONTRACT);
});

test("direct classic executor-range failure lifecycle and reload", async ({ h4 }) => {
  await exerciseToolFailureTerminalRefresh(h4, "classic", EXECUTOR_RANGE_FAILURE_CONTRACT);
});

test("bundle missing read_file executor failure lifecycle and reload", async ({ h4 }) => {
  await exerciseToolFailureTerminalRefresh(h4, "bundle", MISSING_FILE_FAILURE_CONTRACT);
});

test("direct classic missing read_file executor failure lifecycle and reload", async ({ h4 }) => {
  await exerciseToolFailureTerminalRefresh(h4, "classic", MISSING_FILE_FAILURE_CONTRACT);
});

test("bundle malformed read_file arguments parse failure lifecycle and reload", async ({ h4 }) => {
  await exerciseToolFailureTerminalRefresh(h4, "bundle", PARSE_ERROR_TOOL_FAILURE_CONTRACT);
});

test("direct classic malformed read_file arguments parse failure lifecycle and reload", async ({ h4 }) => {
  await exerciseToolFailureTerminalRefresh(h4, "classic", PARSE_ERROR_TOOL_FAILURE_CONTRACT);
});

test("bundle missing read_file path schema failure lifecycle and reload", async ({ h4 }) => {
  await exerciseToolFailureTerminalRefresh(h4, "bundle", MISSING_PATH_TOOL_FAILURE_CONTRACT);
});

test("direct classic missing read_file path schema failure lifecycle and reload", async ({ h4 }) => {
  await exerciseToolFailureTerminalRefresh(h4, "classic", MISSING_PATH_TOOL_FAILURE_CONTRACT);
});

const REPEATED_RANGE_ACTIVE_EVENT_TYPES = Object.freeze([
  "created",
  "model_started", "model_completed", "tool_started", "tool_completed", "model_pending",
  "model_started", "model_completed", "tool_started", "tool_completed", "model_pending",
  "model_started", "model_completed", "tool_started", "tool_completed", "model_pending",
  "model_started", "model_completed", "tool_started", "tool_retry_blocked", "tool_completed", "model_pending",
  "model_started",
]);
const REPEATED_RANGE_TERMINAL_EVENT_TYPES = Object.freeze([
  ...REPEATED_RANGE_ACTIVE_EVENT_TYPES,
  "model_completed",
  "completed",
]);

function repeatedFailureSessionRoleContentProjection(messages) {
  return (Array.isArray(messages) ? messages : []).map((message) => {
    const role = String(message?.role || "");
    const content = String(message?.content || "");
    if (role === "user") {
      return { role, marker: content === REPEATED_RANGE_FAILURE_USER ? "user" : "unexpected" };
    }
    if (role === "assistant") {
      if (content === REPEATED_RANGE_FAILURE_STAGE) return { role, marker: "stage" };
      if (content === REPEATED_RANGE_FAILURE_FINAL) return { role, marker: "final" };
      return { role, marker: "tool-round", contentPresent: Boolean(content.trim()) };
    }
    if (role === "tool-call") {
      return {
        role,
        contentPresent: Boolean(content.trim()),
        pathPresent: content.includes("fixture.txt"),
        startLinePresent: content.includes("startLine"),
        endLinePresent: content.includes("endLine"),
      };
    }
    if (role === "tool-result") {
      let result = {};
      try {
        result = JSON.parse(content);
      } catch {}
      return { role, result: stableRepeatedRangeFailureResult(result) };
    }
    return { role, contentPresent: Boolean(content.trim()) };
  });
}

function repeatedFailureSessionMetaProjection(messages, agentRunId, toolCallIds) {
  const aliases = new Map(toolCallIds.map((toolCallId, index) => [toolCallId, `tool-${index + 1}`]));
  return (Array.isArray(messages) ? messages : [])
    .filter((message) => message?.role === "tool-call" || message?.role === "tool-result")
    .map((message) => {
      const meta = message?.meta || {};
      const tool = meta.tool && typeof meta.tool === "object" ? meta.tool : {};
      return {
        role: String(message.role),
        toolCallId: aliases.get(String(meta.toolCallId || "")) || "mismatch",
        agentRunId: meta.agentRunId == null
          ? ""
          : (String(meta.agentRunId) === agentRunId ? "agent-1" : "mismatch"),
        agentEventType: String(meta.agentEventType || ""),
        agentEventSeq: Number(meta.agentEventSeq || 0),
        action: String(meta.action || ""),
        arguments: message.role === "tool-call" ? {
          path: String(tool.path || ""),
          startLine: tool.startLine ?? null,
          endLine: tool.endLine ?? null,
        } : null,
        native: meta.native === true,
        replayed: Boolean(meta.replayed),
        outcome: String(meta.outcome || ""),
        result: meta.result && typeof meta.result === "object"
          ? stableRepeatedRangeFailureResult(meta.result)
          : null,
      };
    });
}

async function repeatedFailureLifecycleDomEvidence(page) {
  const messages = page.locator("#messages");
  const user = messages.locator("article.msg.user").filter({ hasText: REPEATED_RANGE_FAILURE_USER });
  const commentary = messages.locator("article.msg.assistant.agent-commentary")
    .filter({ hasText: REPEATED_RANGE_FAILURE_STAGE });
  const process = messages.locator("article.tool-process");
  const outer = process.locator("details.tool-process-stage");
  const items = process.locator("details.tool-process-item");
  const finalAnswer = messages.locator("article.msg.assistant")
    .filter({ hasText: REPEATED_RANGE_FAILURE_FINAL });
  await expect(user).toHaveCount(1);
  await expect(commentary).toHaveCount(1);
  await expect(process).toHaveCount(1);
  await expect(outer).toHaveCount(1);
  await expect(items).toHaveCount(4);
  const itemLocators = await items.all();
  const itemProjections = [];
  for (const [index, item] of itemLocators.entries()) {
    await expect(item).toHaveClass(/\bfailed\b/);
    const details = item.locator(".tool-process-detail pre");
    await expect(details).toHaveCount(2);
    const texts = await details.allTextContents();
    const argumentText = String(texts[0] || "").trim();
    const resultText = String(texts[1] || "").trim();
    const projection = {
      tool: index + 1,
      failed: String(await item.getAttribute("class") || "").split(/\s+/).includes("failed"),
      open: await item.evaluate((element) => element.open),
      arguments: {
        pathPresent: argumentText.includes('"path": "fixture.txt"'),
        startLinePresent: argumentText.includes('"startLine": 2'),
        endLinePresent: argumentText.includes('"endLine": 1'),
      },
      result: {
        nonEmpty: Boolean(resultText),
        rangeFailureVisible: resultText.includes("startLine") && resultText.includes("endLine"),
        repeatedFailureBlockedVisible: (
          /exact tool call was blocked after 3 identical failures/i.test(resultText)
          && /do not repeat it/i.test(resultText)
        ),
      },
    };
    expect(projection.arguments).toEqual({
      pathPresent: true,
      startLinePresent: true,
      endLinePresent: true,
    });
    expect(projection.result).toEqual({
      nonEmpty: true,
      rangeFailureVisible: index < 3,
      repeatedFailureBlockedVisible: index === 3,
    });
    itemProjections.push(projection);
  }
  const finalCount = await finalAnswer.count();
  const outerClass = String(await outer.getAttribute("class") || "");
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
    userMarker: REPEATED_RANGE_FAILURE_USER,
    stageMarker: REPEATED_RANGE_FAILURE_STAGE,
    finalMarker: REPEATED_RANGE_FAILURE_FINAL,
  });
  const projection = {
    sequence: finalCount
      ? [REPEATED_RANGE_FAILURE_USER, REPEATED_RANGE_FAILURE_STAGE, "read_file:failed:4", REPEATED_RANGE_FAILURE_FINAL]
      : [REPEATED_RANGE_FAILURE_USER, REPEATED_RANGE_FAILURE_STAGE, "read_file:failed:4"],
    counts: {
      user: 1,
      commentary: 1,
      toolProcess: 1,
      toolItem: 4,
      result: 4,
      final: finalCount,
      ordinaryAssistant: await messages.locator("article.msg.assistant:not(.tool-process)").count(),
      assistantTotal: await messages.locator("article.msg.assistant").count(),
    },
    processKey: String(await outer.getAttribute("data-tool-process-key") || ""),
    outerOpen: await outer.evaluate((element) => element.open),
    itemOpen: await Promise.all(itemLocators.map((item) => item.evaluate((element) => element.open))),
    outerState: {
      running: outerClass.split(/\s+/).includes("running"),
      failed: outerClass.split(/\s+/).includes("failed"),
    },
    currentAction: String(await outer.getAttribute("data-current-action") || ""),
    items: itemProjections,
    ordered,
  };
  return {
    process,
    outer,
    items: itemLocators,
    finalAnswer,
    projection,
    semanticHash: canonicalHash(projection),
  };
}

function expectedRepeatedModelReceipts(count) {
  return EXPECTED_REPEATED_RANGE_RESULTS.slice(0, count).map((result, index) => ({
    role: "tool",
    toolCallId: `tool-${index + 1}`,
    name: "read_file",
    ...result,
  }));
}

async function completeRepeatedRangeFailureLifecycle(h4, runtime) {
  const { page } = h4;
  const requestBoundary = h4.requestBoundary();
  await h4.open(runtime);
  await assertFrontendRuntime(page, runtime);
  if (runtime === "classic") await assertDirectClassicEntry(page);
  await h4.proveNonLoopbackBlocked();
  await h4.submitGated(REPEATED_RANGE_FAILURE_USER);
  const finalDeltaGate = await h4.waitGate(TOOL_FINAL_DELTA_GATE);
  expect(finalDeltaGate[TOOL_FINAL_DELTA_GATE]).toMatchObject({ reached: true, released: false });

  await expect.poll(() => h4.controlIds().agentRunIds.length).toBe(1);
  const agentRunId = h4.controlIds().agentRunIds[0];
  const activeAgent = await fetchProductionJson(
    page,
    `/api/agent/runs/${encodeURIComponent(agentRunId)}?cursor=0&wait=0`,
  );
  expect(activeAgent.status).toBe(200);
  expect(activeAgent.body).toMatchObject({
    status: "model",
    nextCursor: REPEATED_RANGE_ACTIVE_EVENT_TYPES.length,
    forceFinalRound: true,
    errorCode: "",
    pendingToolCalls: [],
  });
  expect((activeAgent.body.events || []).map((event) => event.type))
    .toEqual(REPEATED_RANGE_ACTIVE_EVENT_TYPES);
  const activeTrace = durableFailedToolTraceEvidence(
    activeAgent.body,
    REPEATED_RANGE_FAILURE_CONTRACT,
  );
  expect(activeTrace.toolCallIds).toHaveLength(4);
  expect(new Set(activeTrace.toolCallIds).size).toBe(4);
  expect(activeTrace.executionProjection).toEqual(EXPECTED_REPEATED_RANGE_RESULTS.map((result, index) => ({
    toolCallId: `tool-${index + 1}`,
    name: "read_file",
    arguments: REPEATED_RANGE_FAILURE_CONTRACT.arguments,
    status: "completed",
    outcome: "failed",
    result,
  })));
  const modelCompletedWithTools = activeTrace.eventProjection.filter((event) => (
    event.type === "model_completed" && Array.isArray(event.toolCalls) && event.toolCalls.length
  ));
  expect(modelCompletedWithTools).toHaveLength(4);
  expect(modelCompletedWithTools.map((event) => event.toolCalls[0])).toEqual(
    EXPECTED_REPEATED_RANGE_RESULTS.map((_, index) => ({
      toolCallId: `tool-${index + 1}`,
      name: "read_file",
      arguments: REPEATED_RANGE_FAILURE_CONTRACT.arguments,
    })),
  );
  const startedEvents = activeTrace.eventProjection.filter((event) => event.type === "tool_started");
  const completedEvents = activeTrace.eventProjection.filter((event) => event.type === "tool_completed");
  expect(startedEvents).toHaveLength(4);
  expect(completedEvents).toHaveLength(4);
  for (const [index, event] of startedEvents.entries()) {
    expect(event).toMatchObject({
      toolCallId: `tool-${index + 1}`,
      name: "read_file",
      arguments: REPEATED_RANGE_FAILURE_CONTRACT.arguments,
    });
  }
  for (const [index, event] of completedEvents.entries()) {
    expect(event).toMatchObject({
      toolCallId: `tool-${index + 1}`,
      name: "read_file",
      outcome: "failed",
      result: EXPECTED_REPEATED_RANGE_RESULTS[index],
    });
  }
  const retryBlockedEvents = activeTrace.eventProjection.filter((event) => event.type === "tool_retry_blocked");
  expect(retryBlockedEvents).toEqual([{
    seq: 20,
    type: "tool_retry_blocked",
    failureCount: 3,
    toolCallId: "tool-4",
    name: "read_file",
  }]);

  const modelStartedEvents = activeAgent.body.events.filter((event) => event?.type === "model_started");
  expect(modelStartedEvents).toHaveLength(5);
  const runtimeRunIds = modelStartedEvents.map((event) => String(event?.data?.runtimeRunId || ""));
  expect(runtimeRunIds.every(Boolean)).toBe(true);
  expect(new Set(runtimeRunIds).size).toBe(5);
  expect(activeAgent.body.activeRuntimeRunId).toBe(runtimeRunIds[4]);
  await expect.poll(() => h4.controlIds()).toEqual({
    agentRunIds: [agentRunId],
    runtimeRunIds,
  });
  const activeRuntimeResponses = [];
  for (const runtimeRunId of runtimeRunIds) {
    const response = await fetchProductionJson(
      page,
      `/api/runtime/runs/${encodeURIComponent(runtimeRunId)}?cursor=0&wait=0`,
    );
    expect(response.status).toBe(200);
    activeRuntimeResponses.push(response.body);
  }
  expect(activeRuntimeResponses.slice(0, 4).map((snapshot) => snapshot.status))
    .toEqual(["completed", "completed", "completed", "completed"]);
  expect(activeRuntimeResponses[4].status).toBe("running");
  expect(activeRuntimeResponses[4].events).toEqual([]);
  expect(activeRuntimeResponses[4].result?.content).toBe("");
  expect(activeRuntimeResponses[0].result?.content).toBe(REPEATED_RANGE_FAILURE_STAGE);
  expect(activeRuntimeResponses.slice(1, 4).map((snapshot) => snapshot.result?.content || ""))
    .toEqual(["", "", ""]);

  const metricsActive = await h4.metrics();
  const expectedChatRequests = [0, 1, 2, 3].map((receiptCount, index) => ({
    scenario: `repeated-range-failure-call-${index + 1}`,
    stream: true,
    hasToolResult: receiptCount > 0,
    repeatedRangeFailureReceipts: expectedRepeatedModelReceipts(receiptCount),
  }));
  expectedChatRequests.push({
    scenario: "repeated-range-failure-final",
    stream: true,
    hasToolResult: true,
    repeatedRangeFailureReceipts: expectedRepeatedModelReceipts(4),
    forcedFinal: {
      toolsPresent: false,
      toolChoicePresent: false,
      recoveryInstructionPresent: true,
    },
  });
  expect(metricsActive.chatRequests).toEqual(expectedChatRequests);
  expect(metricsActive.productionToolDelegations).toBe(3);
  expect(metricsActive.toolExecutions).toEqual([1, 2, 3].map(() => ({
    action: "read_file",
    path: "fixture.txt",
    startLine: 2,
    endLine: 1,
  })));
  expect(metricsActive.unsafeToolRequests).toBe(0);

  const process = page.locator("#messages article.tool-process");
  await expect(process).toHaveCount(1);
  await expect(process.locator("details.tool-process-item")).toHaveCount(4);
  await expect(process.locator("details.tool-process-item.failed")).toHaveCount(4);
  const initialDom = await repeatedFailureLifecycleDomEvidence(page);
  expect(initialDom.projection).toMatchObject({
    counts: {
      user: 1,
      commentary: 1,
      toolProcess: 1,
      toolItem: 4,
      result: 4,
      final: 0,
      ordinaryAssistant: 1,
      assistantTotal: 2,
    },
    outerOpen: false,
    itemOpen: [false, false, false, false],
    outerState: { running: true, failed: false },
    currentAction: "read_file",
    ordered: true,
  });
  expect(initialDom.projection.processKey).not.toBe("");
  const oldStage = await initialDom.outer.elementHandle();
  await initialDom.outer.locator(":scope > summary.tool-process-stage-summary").click();
  await expect(initialDom.outer).toHaveAttribute("open", "");

  await h4.releaseGate(TOOL_FINAL_DELTA_GATE);
  await expect(initialDom.finalAnswer).toHaveCount(1);
  const terminalGate = await h4.waitGate(TOOL_TERMINAL_GATE);
  expect(terminalGate[TOOL_TERMINAL_GATE]).toMatchObject({ reached: true, released: false });
  expect(await oldStage.evaluate((element) => element.isConnected)).toBe(false);
  const afterFinalDeltaDom = await repeatedFailureLifecycleDomEvidence(page);
  expect(afterFinalDeltaDom.projection.processKey).toBe(initialDom.projection.processKey);
  expect(afterFinalDeltaDom.projection.outerOpen).toBe(true);
  expect(afterFinalDeltaDom.projection.itemOpen).toEqual([false, false, false, false]);
  expect(afterFinalDeltaDom.projection.outerState).toEqual({ running: false, failed: true });
  expect(afterFinalDeltaDom.projection.counts).toMatchObject({
    user: 1,
    commentary: 1,
    toolProcess: 1,
    toolItem: 4,
    result: 4,
    final: 1,
    ordinaryAssistant: 2,
    assistantTotal: 3,
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
      activeRuntimeRunId: completedAgent.body?.activeRuntimeRunId,
      forceFinalRound: completedAgent.body?.forceFinalRound,
      errorCode: completedAgent.body?.errorCode,
      eventTypes: (completedAgent.body?.events || []).map((event) => event.type),
    };
  }).toEqual({
    status: "completed",
    nextCursor: REPEATED_RANGE_TERMINAL_EVENT_TYPES.length,
    activeRuntimeRunId: "",
    forceFinalRound: false,
    errorCode: "",
    eventTypes: REPEATED_RANGE_TERMINAL_EVENT_TYPES,
  });
  expect(completedAgent.status).toBe(200);
  expect(completedAgent.body.pendingToolCalls).toEqual([]);
  const completedTrace = durableFailedToolTraceEvidence(
    completedAgent.body,
    REPEATED_RANGE_FAILURE_CONTRACT,
  );
  expect(completedTrace.executionProjection).toEqual(activeTrace.executionProjection);
  expect(completedTrace.terminalEventCount).toBe(1);
  await expect(page.locator("#activeRunBanner.visible")).toHaveCount(0);
  await expect(page.locator("#stopBtn")).toBeDisabled();
  await expect(page.locator("#messages .execution-trace.active")).toHaveCount(0);
  await expect(page.locator("#messages .execution-trace.completed")).toHaveCount(1);

  const terminalDom = await repeatedFailureLifecycleDomEvidence(page);
  expect(terminalDom.projection.processKey).toBe(initialDom.projection.processKey);
  expect(terminalDom.projection.outerOpen).toBe(false);
  expect(terminalDom.projection.itemOpen).toEqual([false, false, false, false]);
  expect(terminalDom.projection.outerState).toEqual({ running: false, failed: true });
  const completedTraceElement = page.locator("#messages .execution-trace.completed");
  const completedTraceToggle = completedTraceElement.locator(":scope > [data-execution-trace-toggle]");
  await expect(completedTraceElement).not.toHaveClass(/\bis-expanded\b/);
  await expect(completedTraceToggle).toHaveAttribute("aria-expanded", "false");
  await completedTraceToggle.click();
  await expect(completedTraceElement).toHaveClass(/\bis-expanded\b/);
  await terminalDom.outer.locator(":scope > summary.tool-process-stage-summary").click();
  await expect(terminalDom.outer).toHaveAttribute("open", "");
  for (const item of terminalDom.items) {
    await item.locator(":scope > summary").click();
    await expect(item).toHaveAttribute("open", "");
    await expect(item.locator(".tool-process-detail pre")).toHaveCount(2);
  }
  for (const item of [...terminalDom.items].reverse()) {
    await item.locator(":scope > summary").click();
    await expect(item).not.toHaveAttribute("open", "");
  }
  await terminalDom.outer.locator(":scope > summary.tool-process-stage-summary").click();
  await expect(terminalDom.outer).not.toHaveAttribute("open", "");
  await completedTraceToggle.click();
  await expect(completedTraceElement).not.toHaveClass(/\bis-expanded\b/);
  await expect(completedTraceToggle).toHaveAttribute("aria-expanded", "false");

  const terminalRuntimeResponses = [];
  for (const runtimeRunId of runtimeRunIds) {
    const response = await fetchProductionJson(
      page,
      `/api/runtime/runs/${encodeURIComponent(runtimeRunId)}?cursor=0&wait=0`,
    );
    expect(response.status).toBe(200);
    expect(response.body.status).toBe("completed");
    terminalRuntimeResponses.push(response.body);
  }
  expect(terminalRuntimeResponses.map((snapshot) => snapshot.result?.content || ""))
    .toEqual([REPEATED_RANGE_FAILURE_STAGE, "", "", "", REPEATED_RANGE_FAILURE_FINAL]);
  const runtimeProjection = terminalRuntimeResponses.map((snapshot, index) => ({
    runtimeRunId: `runtime-${index + 1}`,
    status: String(snapshot.status || ""),
    nextCursor: Number(snapshot.nextCursor || 0),
    content: snapshot.result?.content === REPEATED_RANGE_FAILURE_STAGE
      ? "stage"
      : (snapshot.result?.content === REPEATED_RANGE_FAILURE_FINAL ? "final" : "empty"),
  }));

  const sessionButton = page.locator("#sessionList .session-row.active button.session-main");
  await expect(sessionButton).toHaveCount(1);
  const sessionId = await sessionButton.getAttribute("data-session-id");
  expect(sessionId).toBeTruthy();
  const sessionResponse = await fetchProductionJson(
    page,
    `/api/sessions/${encodeURIComponent(sessionId)}`,
  );
  expect(sessionResponse.status).toBe(200);
  expect((sessionResponse.body.messages || []).map((message) => message.role)).toEqual([
    "user",
    "assistant", "tool-call", "tool-result",
    "assistant", "tool-call", "tool-result",
    "assistant", "tool-call", "tool-result",
    "assistant", "tool-call", "tool-result",
    "assistant",
  ]);
  const sessionProjection = repeatedFailureSessionRoleContentProjection(sessionResponse.body.messages);
  const sessionToolMeta = repeatedFailureSessionMetaProjection(
    sessionResponse.body.messages,
    agentRunId,
    activeTrace.toolCallIds,
  );
  expect(sessionToolMeta).toHaveLength(8);
  for (let index = 0; index < 4; index += 1) {
    expect(sessionToolMeta[index * 2]).toMatchObject({
      role: "tool-call",
      toolCallId: `tool-${index + 1}`,
      agentRunId: "agent-1",
      agentEventType: "tool_started",
      action: "read_file",
      arguments: REPEATED_RANGE_FAILURE_CONTRACT.arguments,
      native: true,
      replayed: false,
      outcome: "",
      result: null,
    });
    expect(sessionToolMeta[index * 2 + 1]).toMatchObject({
      role: "tool-result",
      toolCallId: `tool-${index + 1}`,
      agentRunId: "agent-1",
      agentEventType: "tool_completed",
      action: "read_file",
      arguments: null,
      native: true,
      replayed: false,
      outcome: "failed",
      result: EXPECTED_REPEATED_RANGE_RESULTS[index],
    });
    expect(sessionToolMeta[index * 2].agentEventSeq).toBe(startedEvents[index].seq);
    expect(sessionToolMeta[index * 2 + 1].agentEventSeq).toBe(completedEvents[index].seq);
  }

  const durable = await readDurableAgentRecord(h4, agentRunId);
  expect(durable.record).toMatchObject({
    status: "completed",
    nextSeq: REPEATED_RANGE_TERMINAL_EVENT_TYPES.length + 1,
    forceFinalRound: false,
    pendingToolCalls: [],
  });
  expect(durable.record.events).toHaveLength(REPEATED_RANGE_TERMINAL_EVENT_TYPES.length);
  expect(Object.keys(durable.record.toolExecutions || {})).toEqual(activeTrace.toolCallIds);
  for (const [index, toolCallId] of activeTrace.toolCallIds.entries()) {
    expect(stableRepeatedRangeFailureResult(durable.record.toolExecutions[toolCallId]?.result))
      .toEqual(EXPECTED_REPEATED_RANGE_RESULTS[index]);
  }

  const metrics = await h4.metrics();
  expect(metrics).toMatchObject({
    productionToolDelegations: 3,
    unsafeToolRequests: 0,
  });
  expect(metrics.chatRequests).toEqual(expectedChatRequests);
  expect(metrics.toolExecutions).toHaveLength(3);
  const requests = h4.requestEvidenceSince(requestBoundary);
  expect(requests.agentPost).toBe(1);
  expect(requests.runtimePost).toBe(0);
  expect(requests.agentDelete).toBe(0);
  expect(h4.pageErrors).toEqual([]);

  const retryExecutionProjection = completedTrace.executionProjection;
  const modelToolReceiptProjection = expectedRepeatedModelReceipts(4);
  const forcedFinalProjection = {
    modelRequestCount: metrics.chatRequests.length,
    scenario: metrics.chatRequests[4]?.scenario,
    ...metrics.chatRequests[4]?.forcedFinal,
    parentStatus: completedAgent.body.status,
    parentErrorCode: String(completedAgent.body.errorCode || ""),
    forceFinalRound: Boolean(completedAgent.body.forceFinalRound),
    pendingToolCallCount: completedAgent.body.pendingToolCalls.length,
  };
  const hashes = {
    eventProjection: completedTrace.eventProjectionHash,
    retryExecutionProjection: canonicalHash(retryExecutionProjection),
    modelToolReceiptProjection: canonicalHash(modelToolReceiptProjection),
    forcedFinalProjection: canonicalHash(forcedFinalProjection),
    runtimeProjection: canonicalHash(runtimeProjection),
    sessionRoleContent: canonicalHash(sessionProjection),
    sessionToolMeta: canonicalHash(sessionToolMeta),
    terminalDom: terminalDom.semanticHash,
  };
  if (Object.keys(H4_6K_SEMANTIC_HASHES).length) {
    for (const [key, value] of Object.entries(hashes)) {
      expect(value, `H4-6K ${key}`).toBe(H4_6K_SEMANTIC_HASHES[key]);
    }
  }
  h4.evidence(`${runtime === "classic" ? "classic-" : ""}repeated-range-failure-terminal`, {
    identity: {
      agentRunId: idHash(agentRunId),
      toolCallIds: activeTrace.toolCallIds.map(idHash),
      runtimeRunIds: runtimeRunIds.map(idHash),
      processKey: terminalDom.projection.processKey,
    },
    counts: {
      modelRequests: metrics.chatRequests.length,
      productionToolDelegations: metrics.productionToolDelegations,
      toolExecutions: metrics.toolExecutions.length,
      durableExecutions: completedTrace.executionProjection.length,
      retryBlockedEvents: retryBlockedEvents.length,
    },
    runtimeProjection,
    forcedFinalProjection,
    hashes,
  });
  return {
    page,
    agentRunId,
    sessionId,
    toolCallIds: activeTrace.toolCallIds,
    runtimeRunIds,
    completedTrace,
    sessionProjection,
    sessionToolMeta,
    terminalDom,
    metrics,
    hashes,
  };
}

async function exerciseRepeatedRangeFailureTerminalRefresh(h4, runtime) {
  const before = await completeRepeatedRangeFailureLifecycle(h4, runtime);
  const refreshBoundary = h4.requestBoundary();
  const metricsBefore = await h4.metrics();
  await before.page.reload({ waitUntil: "domcontentloaded" });
  await assertFrontendRuntime(before.page, runtime);
  if (runtime === "classic") await assertDirectClassicEntry(before.page);
  const persistedSession = before.page.locator(
    `#sessionList button.session-main[data-session-id="${before.sessionId}"]`,
  );
  await expect(persistedSession).toHaveCount(1);
  await persistedSession.click();
  await expect(before.page.locator("#activeRunBanner.visible")).toHaveCount(0);
  await expect(before.page.locator("#stopBtn")).toBeDisabled();
  await expect(before.page.locator("#messages .execution-trace.active")).toHaveCount(0);
  await expect(before.page.locator("#messages .execution-trace.completed")).toHaveCount(1);
  const domAfter = await repeatedFailureLifecycleDomEvidence(before.page);
  expect(domAfter.projection).toEqual(before.terminalDom.projection);
  expect(domAfter.projection.outerOpen).toBe(false);
  expect(domAfter.projection.itemOpen).toEqual([false, false, false, false]);
  const traceAfterReload = before.page.locator("#messages .execution-trace.completed");
  const traceToggleAfterReload = traceAfterReload.locator(":scope > [data-execution-trace-toggle]");
  await expect(traceAfterReload).not.toHaveClass(/\bis-expanded\b/);
  await expect(traceToggleAfterReload).toHaveAttribute("aria-expanded", "false");
  await traceToggleAfterReload.click();
  await domAfter.outer.locator(":scope > summary.tool-process-stage-summary").click();
  for (const item of domAfter.items) {
    await item.locator(":scope > summary").click();
    await expect(item).toHaveAttribute("open", "");
    await expect(item.locator(".tool-process-detail pre")).toHaveCount(2);
  }
  for (const item of [...domAfter.items].reverse()) {
    await item.locator(":scope > summary").click();
  }
  await domAfter.outer.locator(":scope > summary.tool-process-stage-summary").click();
  await traceToggleAfterReload.click();
  await expect(traceAfterReload).not.toHaveClass(/\bis-expanded\b/);
  await expect(traceToggleAfterReload).toHaveAttribute("aria-expanded", "false");

  const agentAfter = await fetchProductionJson(
    before.page,
    `/api/agent/runs/${encodeURIComponent(before.agentRunId)}?cursor=0&wait=0`,
  );
  expect(agentAfter.status).toBe(200);
  const completedTraceAfter = durableFailedToolTraceEvidence(
    agentAfter.body,
    REPEATED_RANGE_FAILURE_CONTRACT,
  );
  expect(completedTraceAfter).toEqual(before.completedTrace);
  expect(completedTraceAfter.toolCallIds).toEqual(before.toolCallIds);
  const sessionAfter = await fetchProductionJson(
    before.page,
    `/api/sessions/${encodeURIComponent(before.sessionId)}`,
  );
  expect(sessionAfter.status).toBe(200);
  const sessionProjectionAfter = repeatedFailureSessionRoleContentProjection(sessionAfter.body.messages);
  const sessionToolMetaAfter = repeatedFailureSessionMetaProjection(
    sessionAfter.body.messages,
    before.agentRunId,
    before.toolCallIds,
  );
  expect(sessionProjectionAfter).toEqual(before.sessionProjection);
  expect(sessionToolMetaAfter).toEqual(before.sessionToolMeta);
  const metricsAfter = await h4.metrics();
  expect(metricsAfter.chatRequests).toEqual(metricsBefore.chatRequests);
  expect(metricsAfter.toolExecutions).toEqual(metricsBefore.toolExecutions);
  expect(metricsAfter.productionToolDelegations).toBe(3);
  expect(metricsAfter.unsafeToolRequests).toBe(0);
  const refreshRequests = h4.requestEvidenceSince(refreshBoundary);
  expect(refreshRequests.agentPost).toBe(0);
  expect(refreshRequests.runtimePost).toBe(0);
  expect(refreshRequests.agentDelete).toBe(0);
  expect(h4.controlIds()).toEqual({
    agentRunIds: [before.agentRunId],
    runtimeRunIds: before.runtimeRunIds,
  });
  expect(h4.pageErrors).toEqual([]);
  const refreshProjection = {
    agentRunStable: completedTraceAfter.agentRunId === before.completedTrace.agentRunId,
    toolCallsStable: JSON.stringify(completedTraceAfter.toolCallIdHashes)
      === JSON.stringify(before.completedTrace.toolCallIdHashes),
    eventProjectionStable: completedTraceAfter.eventProjectionHash
      === before.completedTrace.eventProjectionHash,
    sessionProjectionStable: JSON.stringify(sessionProjectionAfter)
      === JSON.stringify(before.sessionProjection),
    sessionToolMetaStable: JSON.stringify(sessionToolMetaAfter)
      === JSON.stringify(before.sessionToolMeta),
    processKeyStable: domAfter.projection.processKey === before.terminalDom.projection.processKey,
    refreshDefaultCollapsed: !domAfter.projection.outerOpen
      && domAfter.projection.itemOpen.every((value) => !value),
    counts: domAfter.projection.counts,
    requests: {
      agentPost: refreshRequests.agentPost,
      runtimePost: refreshRequests.runtimePost,
      chatDelta: metricsAfter.chatRequests.length - metricsBefore.chatRequests.length,
      toolDelta: metricsAfter.toolExecutions.length - metricsBefore.toolExecutions.length,
    },
  };
  const hashes = {
    ...before.hashes,
    refreshLifecycle: canonicalHash(refreshProjection),
  };
  if (Object.keys(H4_6K_SEMANTIC_HASHES).length) {
    expect(hashes).toEqual(H4_6K_SEMANTIC_HASHES);
  }
  h4.evidence(`${runtime === "classic" ? "classic-" : ""}repeated-range-failure-refresh`, {
    identity: {
      agentRunId: idHash(before.agentRunId),
      toolCallIds: before.toolCallIds.map(idHash),
      processKey: domAfter.projection.processKey,
    },
    refresh: refreshProjection,
    hashes,
  });
}

test("bundle identical read_file executor failures are bounded and reload uniquely", async ({ h4 }) => {
  await exerciseRepeatedRangeFailureTerminalRefresh(h4, "bundle");
});

test("direct classic identical read_file executor failures are bounded and reload uniquely", async ({ h4 }) => {
  await exerciseRepeatedRangeFailureTerminalRefresh(h4, "classic");
});

async function startMultiToolDetailAtSecondExecute(h4, runtime) {
  const { page } = h4;
  const requestBoundary = h4.requestBoundary();
  await h4.open(runtime);
  await assertFrontendRuntime(page, runtime);
  if (runtime === "classic") {
    expect(await page.locator("html").getAttribute("data-code-frontend-ready")).toBeNull();
  }
  await h4.proveNonLoopbackBlocked();
  await h4.submitGated(MULTI_TOOL_USER);
  const gateSnapshot = await h4.waitGate(SECOND_TOOL_EXECUTE_GATE);
  expect(gateSnapshot[SECOND_TOOL_EXECUTE_GATE]).toMatchObject({
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
  expect(activeAgent.body.status).toBe("tools");
  const activeTrace = durableToolTraceEvidence(activeAgent.body);
  expect(activeTrace.eventProjection.map((event) => event.type)).toEqual([
    "created",
    "model_started",
    "model_completed",
    "tool_started",
    "tool_completed",
    "tool_started",
  ]);
  expect(activeTrace.pendingToolCallCount).toBe(1);
  expect(activeTrace.toolCallIds).toHaveLength(2);
  const [firstToolCallId, secondToolCallId] = activeTrace.toolCallIds;
  expect(activeTrace.eventProjection[2].toolCalls).toEqual([
    { toolCallId: "tool-1", name: "read_file", arguments: { path: "fixture.txt" } },
    {
      toolCallId: "tool-2",
      name: "read_file",
      arguments: { path: "fixture.txt", startLine: 1, endLine: 1 },
    },
  ]);
  expect(activeTrace.executionProjection[0]).toEqual({
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
  });
  expect(activeTrace.executionProjection[1]).toMatchObject({
    toolCallId: "tool-2",
    name: "read_file",
    arguments: { path: "fixture.txt", startLine: 1, endLine: 1 },
    status: "running",
    outcome: "",
  });
  const firstRuntimeRunId = String(activeAgent.body.events.find((event) => (
    event?.type === "model_started"
  ))?.data?.runtimeRunId || "");
  expect(firstRuntimeRunId).not.toBe("");
  await expect.poll(() => h4.controlIds()).toEqual({
    agentRunIds: [agentRunId],
    runtimeRunIds: [firstRuntimeRunId],
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
  expect(firstRuntime.body.result?.content).toBe(MULTI_TOOL_STAGE);
  const metricsAtGate = await h4.metrics();
  expect(metricsAtGate.chatRequests).toEqual([
    { scenario: "multi-tool-detail-call", stream: true, hasToolResult: false },
  ]);
  expect(metricsAtGate.toolExecutions).toEqual([
    { action: "read_file", path: "fixture.txt" },
  ]);
  expect(metricsAtGate.unsafeToolRequests).toBe(0);
  return {
    page,
    requestBoundary,
    agentRunId,
    activeAgent,
    activeTrace,
    firstToolCallId,
    secondToolCallId,
    firstRuntimeRunId,
    metricsAtGate,
  };
}

async function waitForMultiToolTerminal(h4, agentRunId) {
  const { page } = h4;
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
    nextCursor: 11,
    eventTypes: [
      "created",
      "model_started",
      "model_completed",
      "tool_started",
      "tool_completed",
      "tool_started",
      "tool_completed",
      "model_pending",
      "model_started",
      "model_completed",
      "completed",
    ],
  });
  expect(completedAgent.body.activeRuntimeRunId).toBe("");
  expect(completedAgent.body.pendingToolCalls).toEqual([]);
  await expect(page.locator("#activeRunBanner.visible")).toHaveCount(0);
  await expect(page.locator("#stopBtn")).toBeDisabled();
  await expect(page.locator("#messages .execution-trace.active")).toHaveCount(0);
  await expect(page.locator("#messages .execution-trace.completed")).toHaveCount(1);
  return completedAgent;
}

function expectedMultiToolExecutionProjection() {
  return [
    {
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
    },
    {
      toolCallId: "tool-2",
      name: "read_file",
      arguments: { path: "fixture.txt", startLine: 1, endLine: 1 },
      status: "completed",
      outcome: "succeeded",
      result: {
        ok: true,
        action: "read_file",
        path: "fixture.txt",
        content: FIXTURE_CONTENT.trim(),
        size: 26,
        truncated: false,
        lineRange: { start: 1, end: 1 },
      },
    },
  ];
}

async function assertMultiToolCompletedInteraction(page, dom) {
  const terminalTrace = page.locator("#messages .execution-trace.completed");
  await expect(terminalTrace).toHaveCount(1);
  await expect(terminalTrace).not.toHaveClass(/\bis-expanded\b/);
  const traceToggle = terminalTrace.locator(":scope > [data-execution-trace-toggle]");
  await expect(traceToggle).toHaveCount(1);
  await expect(traceToggle).toHaveAttribute("aria-expanded", "false");
  await traceToggle.click();
  await expect(terminalTrace).toHaveClass(/\bis-expanded\b/);
  await expect(traceToggle).toHaveAttribute("aria-expanded", "true");
  await expect(dom.outer.locator(":scope > summary.tool-process-stage-summary")).toBeVisible();
  await dom.outer.locator(":scope > summary.tool-process-stage-summary").click();
  await expect(dom.outer).toHaveAttribute("open", "");
  for (const item of dom.items) {
    await item.locator(":scope > summary").click();
    await expect(item).toHaveAttribute("open", "");
  }
  for (const [index, item] of dom.items.entries()) {
    const details = item.locator(".tool-process-detail pre");
    await expect(details).toHaveCount(2);
    await expect(details.first()).toContainText("fixture.txt");
    if (index === 1) {
      await expect(details.first()).toContainText('"startLine": 1');
      await expect(details.first()).toContainText('"endLine": 1');
    }
    await expect(details.last()).toContainText("fixture.txt");
    await expect(details.last()).toContainText("26 B");
    await expect(details.last()).toContainText(FIXTURE_CONTENT.trim());
    expect(countOccurrences(await details.last().textContent(), FIXTURE_CONTENT.trim())).toBe(1);
  }
  for (const item of [...dom.items].reverse()) {
    await item.locator(":scope > summary").click();
    await expect(item).not.toHaveAttribute("open", "");
  }
  await dom.outer.locator(":scope > summary.tool-process-stage-summary").click();
  await expect(dom.outer).not.toHaveAttribute("open", "");
  await traceToggle.click();
  await expect(terminalTrace).not.toHaveClass(/\bis-expanded\b/);
  await expect(traceToggle).toHaveAttribute("aria-expanded", "false");
}

async function exerciseMultiToolDetailActiveToTerminal(h4, runtime) {
  const started = await startMultiToolDetailAtSecondExecute(h4, runtime);
  const activeProcess = started.page.locator("#messages article.tool-process");
  await expect(activeProcess).toHaveCount(1);
  const activeItems = activeProcess.locator("details.tool-process-item");
  await expect(activeItems).toHaveCount(2);
  const firstActiveItem = activeItems.nth(0);
  const secondActiveItem = activeItems.nth(1);
  await expect(firstActiveItem).toHaveClass(/\bsucceeded\b/);
  await expect(secondActiveItem).toHaveClass(/\brunning\b/);
  const firstActiveDetails = firstActiveItem.locator(".tool-process-detail pre");
  const secondActiveDetails = secondActiveItem.locator(".tool-process-detail pre");
  await expect(firstActiveDetails).toHaveCount(2);
  await expect(firstActiveDetails.nth(1)).toContainText("fixture.txt");
  await expect(firstActiveDetails.nth(1)).toContainText("26 B");
  await expect(firstActiveDetails.nth(1)).toContainText(FIXTURE_CONTENT.trim());
  expect(countOccurrences(
    await firstActiveDetails.nth(1).textContent(),
    FIXTURE_CONTENT.trim(),
  )).toBe(1);
  await expect(secondActiveDetails).toHaveCount(1);
  const initialDom = await multiToolDetailLifecycleDomEvidence(started.page);
  expect(initialDom.projection).toMatchObject({
    counts: {
      user: 1,
      commentary: 1,
      toolProcess: 1,
      toolItems: 2,
      results: 1,
      final: 0,
      ordinaryAssistant: 1,
      assistantTotal: 2,
    },
    outerOpen: false,
    currentAction: "read_file",
    ordered: true,
  });
  expect(initialDom.projection.processKey).toBe("0:1");
  expect(initialDom.projection.stageClass.split(/\s+/)).toContain("running");
  expect(initialDom.projection.items[0]).toMatchObject({
    order: 1,
    open: false,
    arguments: { pathPresent: true, startLinePresent: false, endLinePresent: false },
    formattedResult: { present: true, pathPresent: true, sizePresent: true, fixtureContentCount: 1 },
  });
  expect(initialDom.projection.items[0].className.split(/\s+/)).toContain("succeeded");
  expect(initialDom.projection.items[1]).toMatchObject({
    order: 2,
    open: false,
    arguments: { pathPresent: true, startLinePresent: true, endLinePresent: true },
    formattedResult: { present: false, pathPresent: false, sizePresent: false, fixtureContentCount: 0 },
  });
  expect(initialDom.projection.items[1].className.split(/\s+/)).toContain("running");

  const replacedStage = await initialDom.outer.elementHandle();
  await initialDom.outer.locator(":scope > summary.tool-process-stage-summary").click();
  await expect(initialDom.outer).toHaveAttribute("open", "");
  const openedKey = await initialDom.outer.getAttribute("data-tool-process-key");
  expect(openedKey).toBe(initialDom.projection.processKey);

  await h4.releaseGate(SECOND_TOOL_EXECUTE_GATE);
  const finalDeltaGate = await h4.waitGate(TOOL_FINAL_DELTA_GATE);
  expect(finalDeltaGate[TOOL_FINAL_DELTA_GATE]).toMatchObject({ reached: true, released: false });
  expect(await replacedStage.evaluate((element) => element.isConnected)).toBe(false);
  const afterSecondToolDom = await multiToolDetailLifecycleDomEvidence(started.page);
  expect(afterSecondToolDom.projection.processKey).toBe(openedKey);
  expect(afterSecondToolDom.projection.outerOpen).toBe(true);
  expect(afterSecondToolDom.projection.counts).toMatchObject({ toolProcess: 1, toolItems: 2, results: 2, final: 0 });
  expect(afterSecondToolDom.projection.items.map((item) => item.className.split(/\s+/).includes("succeeded")))
    .toEqual([true, true]);
  expect(afterSecondToolDom.projection.items.map((item) => item.formattedResult.fixtureContentCount))
    .toEqual([1, 1]);
  const metricsAfterSecond = await h4.metrics();
  expect(metricsAfterSecond.toolExecutions).toEqual([
    { action: "read_file", path: "fixture.txt" },
    { action: "read_file", path: "fixture.txt", startLine: 1, endLine: 1 },
  ]);

  await h4.releaseGate(TOOL_FINAL_DELTA_GATE);
  await expect(afterSecondToolDom.finalAnswer).toHaveCount(1);
  const terminalGate = await h4.waitGate(TOOL_TERMINAL_GATE);
  expect(terminalGate[TOOL_TERMINAL_GATE]).toMatchObject({ reached: true, released: false });
  const afterFinalDeltaDom = await multiToolDetailLifecycleDomEvidence(started.page);
  expect(afterFinalDeltaDom.projection.processKey).toBe(openedKey);
  expect(afterFinalDeltaDom.projection.outerOpen).toBe(true);
  expect(afterFinalDeltaDom.projection.counts.final).toBe(1);

  const completedAgent = await waitForMultiToolTerminal(h4, started.agentRunId);
  const completedTrace = durableToolTraceEvidence(completedAgent.body);
  expect(completedTrace.pendingToolCallCount).toBe(0);
  expect(completedTrace.terminalEventCount).toBe(1);
  expect(completedTrace.toolCallIds).toEqual([started.firstToolCallId, started.secondToolCallId]);
  expect(completedTrace.executionProjection).toEqual(expectedMultiToolExecutionProjection());
  const terminalDom = await multiToolDetailLifecycleDomEvidence(started.page);
  expect(terminalDom.projection.processKey).toBe(openedKey);
  expect(terminalDom.projection.outerOpen).toBe(false);
  expect(terminalDom.projection.items.map((item) => item.open)).toEqual([false, false]);
  expect(terminalDom.projection.stageClass.split(/\s+/)).toContain("succeeded");
  expect(terminalDom.projection.heading).toBe("Inspected a file");
  await assertMultiToolCompletedInteraction(started.page, terminalDom);

  const sessionButton = started.page.locator("#sessionList .session-row.active button.session-main");
  await expect(sessionButton).toHaveCount(1);
  const sessionId = await sessionButton.getAttribute("data-session-id");
  expect(sessionId).toBeTruthy();
  const sessionResponse = await fetchProductionJson(
    started.page,
    `/api/sessions/${encodeURIComponent(sessionId)}`,
  );
  expect(sessionResponse.status).toBe(200);
  const sessionProjection = roleContentProjection(sessionResponse.body.messages);
  expect(sessionProjection.map((message) => message.role)).toEqual([
    "user", "assistant", "tool-call", "tool-result", "tool-call", "tool-result", "assistant",
  ]);
  const sessionToolMeta = multiSessionToolMetaProjection(
    sessionResponse.body.messages,
    started.agentRunId,
    completedTrace.toolCallIds,
  );
  expect(sessionToolMeta.map((message) => [message.role, message.toolCallId])).toEqual([
    ["tool-call", "tool-1"],
    ["tool-result", "tool-1"],
    ["tool-call", "tool-2"],
    ["tool-result", "tool-2"],
  ]);
  expect(sessionToolMeta.map((message) => message.agentRunId)).toEqual([
    "agent-1", "agent-1", "agent-1", "agent-1",
  ]);
  expect(sessionToolMeta[0].arguments).toEqual({ path: "fixture.txt", startLine: null, endLine: null });
  expect(sessionToolMeta[1].result).toEqual(expectedMultiToolExecutionProjection()[0].result);
  expect(sessionToolMeta[2].arguments).toEqual({ path: "fixture.txt", startLine: 1, endLine: 1 });
  expect(sessionToolMeta[3].result).toEqual(expectedMultiToolExecutionProjection()[1].result);

  const metrics = await h4.metrics();
  expect(metrics.chatRequests).toEqual([
    { scenario: "multi-tool-detail-call", stream: true, hasToolResult: false },
    { scenario: "multi-tool-detail-final", stream: true, hasToolResult: true },
  ]);
  expect(metrics.toolExecutions).toEqual([
    { action: "read_file", path: "fixture.txt" },
    { action: "read_file", path: "fixture.txt", startLine: 1, endLine: 1 },
  ]);
  expect(metrics.unsafeToolRequests).toBe(0);
  const requests = h4.requestEvidenceSince(started.requestBoundary);
  expect(requests.agentPost).toBe(1);
  expect(requests.runtimePost).toBe(0);
  expect(requests.agentDelete).toBe(0);
  expect(h4.pageErrors).toEqual([]);
  const lifecycleProjection = {
    processKey: terminalDom.projection.processKey,
    openTransitions: ["closed", "open", "open-after-second-result", "open-after-final-delta", "closed-terminal"],
    itemOutcomes: terminalDom.projection.items.map((item) => item.className.split(/\s+/).at(-1)),
    eventTypes: completedTrace.eventProjection.map((event) => event.type),
    counts: terminalDom.projection.counts,
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
    receiptProjection: completedTrace.executionProjectionHash,
    sessionRoleContent: canonicalHash(sessionProjection),
    sessionToolMeta: canonicalHash(sessionToolMeta),
    activeDom: afterSecondToolDom.semanticHash,
    terminalDom: terminalDom.semanticHash,
  };
  if (Object.keys(H4_6C_ACTIVE_TO_TERMINAL_HASHES).length) {
    expect(hashes).toEqual(H4_6C_ACTIVE_TO_TERMINAL_HASHES);
  }
  h4.evidence(
    runtime === "classic"
      ? "classic-multi-tool-detail-active-to-terminal"
      : "multi-tool-detail-active-to-terminal",
    {
    identity: {
      agentRunId: idHash(started.agentRunId),
      toolCallIds: completedTrace.toolCallIdHashes,
      runtimeRunIds: completedTrace.runtimeIdHashes,
      processKey: terminalDom.projection.processKey,
    },
    gateTimeline: metrics.refreshGateTimeline.filter((entry) => (
      [SECOND_TOOL_EXECUTE_GATE, TOOL_FINAL_DELTA_GATE, TOOL_TERMINAL_GATE].includes(entry.gate)
    )),
    lifecycle: lifecycleProjection,
    hashes,
    },
  );
}

test("bundle same-round two read_file tools keep order and expansion through terminal", async ({ h4 }) => {
  await exerciseMultiToolDetailActiveToTerminal(h4, "bundle");
});

test("classic same-round two read_file tools keep order and expansion through terminal", async ({ h4 }) => {
  await exerciseMultiToolDetailActiveToTerminal(h4, "classic");
});

async function exerciseMultiToolDetailTerminalRefresh(h4, runtime) {
  const started = await startMultiToolDetailAtSecondExecute(h4, runtime);
  await h4.releaseGate(SECOND_TOOL_EXECUTE_GATE);
  await h4.waitGate(TOOL_FINAL_DELTA_GATE);
  await h4.releaseGate(TOOL_FINAL_DELTA_GATE);
  await h4.waitGate(TOOL_TERMINAL_GATE);
  const completedAgent = await waitForMultiToolTerminal(h4, started.agentRunId);
  const traceBefore = durableToolTraceEvidence(completedAgent.body);
  expect(traceBefore.executionProjection).toEqual(expectedMultiToolExecutionProjection());

  const sessionButton = started.page.locator("#sessionList .session-row.active button.session-main");
  await expect(sessionButton).toHaveCount(1);
  const sessionId = await sessionButton.getAttribute("data-session-id");
  expect(sessionId).toBeTruthy();
  const sessionBefore = await fetchProductionJson(
    started.page,
    `/api/sessions/${encodeURIComponent(sessionId)}`,
  );
  expect(sessionBefore.status).toBe(200);
  const sessionProjectionBefore = roleContentProjection(sessionBefore.body.messages);
  expect(sessionProjectionBefore.map((message) => message.role)).toEqual([
    "user", "assistant", "tool-call", "tool-result", "tool-call", "tool-result", "assistant",
  ]);
  const toolMetaBefore = multiSessionToolMetaProjection(
    sessionBefore.body.messages,
    started.agentRunId,
    traceBefore.toolCallIds,
  );
  expect(toolMetaBefore.map((message) => [message.role, message.toolCallId])).toEqual([
    ["tool-call", "tool-1"],
    ["tool-result", "tool-1"],
    ["tool-call", "tool-2"],
    ["tool-result", "tool-2"],
  ]);
  const domBefore = await multiToolDetailLifecycleDomEvidence(started.page);
  expect(domBefore.projection.outerOpen).toBe(false);
  expect(domBefore.projection.items.map((item) => item.open)).toEqual([false, false]);
  const processKey = domBefore.projection.processKey;
  const traceBeforeReload = started.page.locator("#messages .execution-trace.completed");
  const traceToggleBefore = traceBeforeReload.locator(":scope > [data-execution-trace-toggle]");
  await traceToggleBefore.click();
  await domBefore.outer.locator(":scope > summary.tool-process-stage-summary").click();
  for (const item of domBefore.items) await item.locator(":scope > summary").click();
  await expect(traceBeforeReload).toHaveClass(/\bis-expanded\b/);
  await expect(domBefore.outer).toHaveAttribute("open", "");
  for (const item of domBefore.items) await expect(item).toHaveAttribute("open", "");

  const metricsBefore = await h4.metrics();
  const refreshBoundary = h4.requestBoundary();
  await started.page.reload({ waitUntil: "domcontentloaded" });
  await assertFrontendRuntime(started.page, runtime);
  if (runtime === "classic") {
    expect(await started.page.locator("html").getAttribute("data-code-frontend-ready")).toBeNull();
  }
  const persistedSession = started.page.locator(
    `#sessionList button.session-main[data-session-id="${sessionId}"]`,
  );
  await expect(persistedSession).toHaveCount(1);
  await persistedSession.click();

  const domAfter = await multiToolDetailLifecycleDomEvidence(started.page);
  expect(domAfter.projection.processKey).toBe(processKey);
  expect(domAfter.projection.outerOpen).toBe(false);
  expect(domAfter.projection.items.map((item) => item.open)).toEqual([false, false]);
  expect(domAfter.projection).toEqual(domBefore.projection);
  const traceAfterReload = started.page.locator("#messages .execution-trace.completed");
  await expect(traceAfterReload).not.toHaveClass(/\bis-expanded\b/);
  const traceToggleAfter = traceAfterReload.locator(":scope > [data-execution-trace-toggle]");
  await expect(traceToggleAfter).toHaveAttribute("aria-expanded", "false");
  await assertMultiToolCompletedInteraction(started.page, domAfter);

  const agentAfter = await fetchProductionJson(
    started.page,
    `/api/agent/runs/${encodeURIComponent(started.agentRunId)}?cursor=0&wait=0`,
  );
  expect(agentAfter.status).toBe(200);
  const traceAfter = durableToolTraceEvidence(agentAfter.body);
  expect(traceAfter).toEqual(traceBefore);
  const sessionAfter = await fetchProductionJson(
    started.page,
    `/api/sessions/${encodeURIComponent(sessionId)}`,
  );
  expect(sessionAfter.status).toBe(200);
  const sessionProjectionAfter = roleContentProjection(sessionAfter.body.messages);
  expect(sessionProjectionAfter).toEqual(sessionProjectionBefore);
  const toolMetaAfter = multiSessionToolMetaProjection(
    sessionAfter.body.messages,
    started.agentRunId,
    traceAfter.toolCallIds,
  );
  expect(toolMetaAfter).toEqual(toolMetaBefore);
  const metricsAfter = await h4.metrics();
  expect(metricsAfter.chatRequests).toEqual(metricsBefore.chatRequests);
  expect(metricsAfter.toolExecutions).toEqual(metricsBefore.toolExecutions);
  const refreshRequests = h4.requestEvidenceSince(refreshBoundary);
  expect(refreshRequests.agentPost).toBe(0);
  expect(refreshRequests.runtimePost).toBe(0);
  expect(refreshRequests.agentDelete).toBe(0);
  expect(h4.controlIds().agentRunIds).toEqual([started.agentRunId]);
  expect(h4.pageErrors).toEqual([]);
  const refreshProjection = {
    processKeyStable: domAfter.projection.processKey === domBefore.projection.processKey,
    agentRunStable: traceAfter.agentRunId === traceBefore.agentRunId,
    toolCallsStable: JSON.stringify(traceAfter.toolCallIdHashes) === JSON.stringify(traceBefore.toolCallIdHashes),
    eventProjectionStable: traceAfter.eventProjectionHash === traceBefore.eventProjectionHash,
    receiptProjectionStable: traceAfter.executionProjectionHash === traceBefore.executionProjectionHash,
    sessionProjectionStable: JSON.stringify(sessionProjectionAfter) === JSON.stringify(sessionProjectionBefore),
    toolMetaStable: JSON.stringify(toolMetaAfter) === JSON.stringify(toolMetaBefore),
    refreshDefaultCollapsed: !domAfter.projection.outerOpen && domAfter.projection.items.every((item) => !item.open),
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
    receiptProjection: traceBefore.executionProjectionHash,
    sessionRoleContent: canonicalHash(sessionProjectionBefore),
    sessionToolMeta: canonicalHash(toolMetaBefore),
    terminalDom: domBefore.semanticHash,
  };
  if (Object.keys(H4_6C_TERMINAL_REFRESH_HASHES).length) {
    expect(hashes).toEqual(H4_6C_TERMINAL_REFRESH_HASHES);
  }
  h4.evidence(
    runtime === "classic"
      ? "classic-multi-tool-detail-terminal-refresh"
      : "multi-tool-detail-terminal-refresh",
    {
    identity: {
      agentRunId: idHash(started.agentRunId),
      toolCallIds: traceBefore.toolCallIdHashes,
      processKey,
    },
    refresh: refreshProjection,
    hashes,
    expansionBoundary: "page-local completed trace, group, and two item details reset on full reload",
    },
  );
}

test("completed bundle same-round two read_file tools reload uniquely without re-execution", async ({ h4 }) => {
  await exerciseMultiToolDetailTerminalRefresh(h4, "bundle");
});

test("completed classic same-round two read_file tools reload uniquely without re-execution", async ({ h4 }) => {
  await exerciseMultiToolDetailTerminalRefresh(h4, "classic");
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
