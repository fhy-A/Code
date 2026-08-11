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
const FORCED_FINAL_MODEL_FAILURE_USER = "H4_FORCED_FINAL_MODEL_FAILURE_USER";
const FORCED_FINAL_UNUSABLE_TOOL_USER = "H4_FORCED_FINAL_UNUSABLE_TOOL_USER";
const FORCED_FINAL_UNUSABLE_TOOL_CALL_ID = "h4-forced-final-unusable-read-call-5";
const FORCED_FINAL_UNUSABLE_ERROR_MARKER = "Model did not provide a usable final response";
const ARGUMENT_ISOLATION_USER = "H4_ARGUMENT_ISOLATION_FAILURE_USER";
const ARGUMENT_ISOLATION_STAGE = "H4_ARGUMENT_ISOLATION_FAILURE_STAGE";
const ARGUMENT_ISOLATION_FINAL = "H4_ARGUMENT_ISOLATION_FAILURE_FINAL";
const SIGNATURE_ALTERNATION_USER = "H4_SIGNATURE_ALTERNATION_FAILURE_USER";
const SIGNATURE_ALTERNATION_STAGE = "H4_SIGNATURE_ALTERNATION_FAILURE_STAGE";
const SIGNATURE_ALTERNATION_FINAL = "H4_SIGNATURE_ALTERNATION_FAILURE_FINAL";
const SIGNATURE_ALTERNATION_READ_PATH = "h4-signature-alternation-fixture.txt";
const SUCCESS_RESET_USER = "H4_SUCCESS_RESET_FAILURE_USER";
const SUCCESS_RESET_STAGE = "H4_SUCCESS_RESET_FAILURE_STAGE";
const SUCCESS_RESET_FINAL = "H4_SUCCESS_RESET_FAILURE_FINAL";
const SUCCESS_RESET_READ_PATH = "h4-success-reset-fixture.txt";
const MISSING_FILE_USER = "H4_MISSING_FILE_FAILURE_USER";
const MISSING_FILE_STAGE = "H4_MISSING_FILE_FAILURE_STAGE";
const MISSING_FILE_FINAL = "H4_MISSING_FILE_FAILURE_FINAL";
const MISSING_READ_PATH = "h4-missing-fixture.txt";
const TIFF_IMAGE_USER = "H4_TIFF_IMAGE_USER";
const TIFF_IMAGE_FINAL = "H4_TIFF_IMAGE_FINAL";
const TIMING_MAIN_USER = "H4_TIMING_MAIN_USER";
const TIMING_MAIN_FINAL = "H4_TIMING_MAIN_FINAL";
const TIMING_PARALLEL_USER = "H4_TIMING_PARALLEL_USER";
const TIMING_PARALLEL_FINAL = "H4_TIMING_PARALLEL_FINAL";
const TIMING_QUEUE_USER = "H4_TIMING_QUEUE_USER";
const TIMING_QUEUE_FINAL = "H4_TIMING_QUEUE_FINAL";
const PARALLEL_FAILURE_USER = "H4_PARALLEL_MODEL_FAILURE_USER";
const PARALLEL_FAILURE_ERROR = "H4_PARALLEL_MODEL_FAILURE";
const PARALLEL_FAILURE_FOLLOWUP_USER = "H4_PARALLEL_FAILURE_FOLLOWUP_USER";
const PARALLEL_FAILURE_FOLLOWUP_FINAL = "H4_PARALLEL_FAILURE_FOLLOWUP_FINAL";
const QUESTIONNAIRE_USER = "H4_QUESTIONNAIRE_USER";
const QUEUE_QUESTIONNAIRE_USER = `${QUESTIONNAIRE_USER}_QUEUE`;
const QUESTIONNAIRE_FINAL = "H4_QUESTIONNAIRE_FINAL";
const QUESTIONNAIRE_TOOL_CALL_ID = "h4-questionnaire-call-1";
const QUESTIONNAIRE_REQUEST_ID = `user-input-${QUESTIONNAIRE_TOOL_CALL_ID}`;
const QUESTIONNAIRE_TITLE = "H4_QUESTIONNAIRE_TITLE";
const QUESTIONNAIRE_REASON = "H4_QUESTIONNAIRE_REASON";
const QUESTIONNAIRE_QUESTION_ID = "h4-questionnaire-choice";
const QUESTIONNAIRE_PROMPT = "H4_QUESTIONNAIRE_PROMPT";
const QUESTIONNAIRE_OPTION_A = Object.freeze({
  value: "h4-option-a",
  label: "H4_QUESTIONNAIRE_OPTION_A",
});
const QUESTIONNAIRE_OPTION_B = Object.freeze({
  value: "h4-option-b",
  label: "H4_QUESTIONNAIRE_OPTION_B",
});
const MIXED_QUESTIONNAIRE_USER = "H4_MIXED_QUESTIONNAIRE_USER";
const MIXED_QUESTIONNAIRE_FINAL = "H4_MIXED_QUESTIONNAIRE_FINAL";
const MIXED_QUESTIONNAIRE_TOOL_CALL_ID = "h4-mixed-questionnaire-call-1";
const MIXED_QUESTIONNAIRE_REQUEST_ID = `user-input-${MIXED_QUESTIONNAIRE_TOOL_CALL_ID}`;
const MIXED_QUESTIONNAIRE_TITLE = "H4_MIXED_QUESTIONNAIRE_TITLE";
const MIXED_QUESTIONNAIRE_REASON = "H4_MIXED_QUESTIONNAIRE_REASON";
const MIXED_QUESTIONNAIRE_OTHER = "H4_MIXED_MULTIPLE_OTHER";
const MIXED_QUESTIONNAIRE_TEXT = "H4_MIXED_TEXT_ANSWER";
const MIXED_QUESTIONNAIRE_CONTRACT = Object.freeze({
  userMarker: MIXED_QUESTIONNAIRE_USER,
  finalMarker: MIXED_QUESTIONNAIRE_FINAL,
  toolCallId: MIXED_QUESTIONNAIRE_TOOL_CALL_ID,
  requestId: MIXED_QUESTIONNAIRE_REQUEST_ID,
  title: MIXED_QUESTIONNAIRE_TITLE,
  reason: MIXED_QUESTIONNAIRE_REASON,
  questions: [
    {
      id: "h4-mixed-single",
      prompt: "H4_MIXED_SINGLE_PROMPT",
      type: "single",
      required: true,
      allowOther: false,
      options: [
        {
          value: "h4-mixed-single-a",
          label: "H4_MIXED_SINGLE_OPTION_A",
          description: "H4_MIXED_SINGLE_OPTION_A_DESCRIPTION",
        },
        {
          value: "h4-mixed-single-b",
          label: "H4_MIXED_SINGLE_OPTION_B",
          description: "H4_MIXED_SINGLE_OPTION_B_DESCRIPTION",
        },
      ],
      answer: {
        values: ["h4-mixed-single-b"],
        text: "",
        other: "",
        markers: ["H4_MIXED_SINGLE_OPTION_B"],
      },
    },
    {
      id: "h4-mixed-multiple",
      prompt: "H4_MIXED_MULTIPLE_PROMPT",
      type: "multiple",
      required: true,
      allowOther: true,
      options: [
        {
          value: "h4-mixed-multiple-a",
          label: "H4_MIXED_MULTIPLE_OPTION_A",
          description: "H4_MIXED_MULTIPLE_OPTION_A_DESCRIPTION",
        },
        {
          value: "h4-mixed-multiple-b",
          label: "H4_MIXED_MULTIPLE_OPTION_B",
          description: "H4_MIXED_MULTIPLE_OPTION_B_DESCRIPTION",
        },
        {
          value: "h4-mixed-multiple-c",
          label: "H4_MIXED_MULTIPLE_OPTION_C",
          description: "H4_MIXED_MULTIPLE_OPTION_C_DESCRIPTION",
        },
      ],
      answer: {
        values: ["h4-mixed-multiple-a", "h4-mixed-multiple-c"],
        text: "",
        other: MIXED_QUESTIONNAIRE_OTHER,
        markers: [
          "H4_MIXED_MULTIPLE_OPTION_A",
          "H4_MIXED_MULTIPLE_OPTION_C",
          MIXED_QUESTIONNAIRE_OTHER,
        ],
      },
    },
    {
      id: "h4-mixed-text",
      prompt: "H4_MIXED_TEXT_PROMPT",
      type: "text",
      required: true,
      allowOther: false,
      options: [],
      answer: {
        values: [],
        text: MIXED_QUESTIONNAIRE_TEXT,
        other: "",
        markers: [MIXED_QUESTIONNAIRE_TEXT],
      },
    },
  ],
});
const EDIT_AUTHORIZATION_TOOL_CALL_ID = "h4-propose-edit-call-1";
const EDIT_AUTHORIZATION_PATH = "h4-propose-edit-fixture.txt";
const EDIT_AUTHORIZATION_INITIAL = "H4_PROPOSE_EDIT_INITIAL";
const EDIT_AUTHORIZATION_TARGET = "H4_PROPOSE_EDIT_TARGET";
const EDIT_AUTHORIZATION_INITIAL_SHA256 = "f12af1cc9275e5511341e977ac8ad5b13050b8eb8951b4a78555018cdbcaebe3";
const EDIT_AUTHORIZATION_TARGET_SHA256 = "26ed22af144d40ac7a02a4a6087bbfa8bcb2024782e90fdac3ed6cb2abbbf3ef";
const EDIT_AUTHORIZATION_THIRD_PARTY_SHA256 = "3ca2970e23df18316faba0c55fde5881e36d215d02499ee36e3e257113ebe931";
const EDIT_AUTHORIZATION_STAGE = "H4_EDIT_AUTHORIZATION_STAGE";
const EDIT_AUTHORIZATION_CONTRACT = Object.freeze({
  toolCallId: EDIT_AUTHORIZATION_TOOL_CALL_ID,
  path: EDIT_AUTHORIZATION_PATH,
  arguments: {
    path: EDIT_AUTHORIZATION_PATH,
    oldText: EDIT_AUTHORIZATION_INITIAL,
    newText: EDIT_AUTHORIZATION_TARGET,
  },
  initialSha256: EDIT_AUTHORIZATION_INITIAL_SHA256,
  targetSha256: EDIT_AUTHORIZATION_TARGET_SHA256,
  stageMarker: EDIT_AUTHORIZATION_STAGE,
  branches: {
    approved: {
      userMarker: "H4_EDIT_AUTHORIZATION_APPROVE_USER",
      finalMarker: "H4_EDIT_AUTHORIZATION_APPROVE_FINAL",
      scenarioPrefix: "edit-authorization-approve",
      action: "approve",
      decision: "approved",
      resultAction: "apply_edit",
      resultOk: true,
      resultDiffPresent: true,
      expectedSha256: EDIT_AUTHORIZATION_TARGET_SHA256,
      applied: true,
      rejected: false,
      outcome: "succeeded",
      backupPresent: true,
      applyDelegations: 1,
      writes: 1,
      backups: 1,
    },
    rejected: {
      userMarker: "H4_EDIT_AUTHORIZATION_REJECT_USER",
      finalMarker: "H4_EDIT_AUTHORIZATION_REJECT_FINAL",
      scenarioPrefix: "edit-authorization-reject",
      action: "reject-all",
      decision: "rejected",
      resultAction: "propose_edit",
      resultOk: false,
      resultDiffPresent: false,
      expectedSha256: EDIT_AUTHORIZATION_INITIAL_SHA256,
      applied: false,
      rejected: true,
      outcome: "failed",
      backupPresent: false,
      applyDelegations: 0,
      writes: 0,
      backups: 0,
    },
  },
});
const EDIT_AUTHORIZATION_CONFLICT_CONTRACT = Object.freeze({
  userMarker: "H4_EDIT_AUTHORIZATION_CONFLICT_USER",
  finalMarker: "H4_EDIT_AUTHORIZATION_CONFLICT_FINAL",
  scenarioPrefix: "edit-authorization-conflict",
  action: "approve",
  decision: "approved",
  resultAction: "apply_edit",
  resultOk: false,
  resultDiffPresent: false,
  applied: false,
  rejected: true,
  resultRejected: false,
  outcome: "failed",
  backupPresent: false,
  applyDelegations: 1,
  writes: 0,
  backups: 0,
  conflict: true,
  errorPresent: true,
  conflictReason: "File modified by another session, please re-read.",
  expectedSha256: EDIT_AUTHORIZATION_THIRD_PARTY_SHA256,
});
const TIFF_ATTACHMENT_NAME = "h4-preview.tiff";
const TIFF_ATTACHMENT_BASE64 = "SUkqAFAAAACABUrsmBQSBwWEQeFQaGQmGwuHRGIROHxWJRaKReNRmORiPRuPx2QSORSWQyeSSiTSmWSuXSqYS2Yy+ZTWaTeZzmbTqcTKAgAKAAABAwABAAAAEgAAAAEBAwABAAAADAAAAAIBAwADAAAAzgAAAAMBAwABAAAABQAAAAYBAwABAAAAAgAAABEBBAABAAAACAAAABUBAwABAAAAAwAAABYBAwABAAAADAAAABcBBAABAAAARwAAABwBAwABAAAAAQAAAAAAAAAIAAgACAA=";
const TIFF_ATTACHMENT_SHA256 = "42e6678c560a178b49da1cbc67c4f75a7f545975edbb96f23500ff98066f0b73";
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
const H4_6L_SEMANTIC_HASHES = Object.freeze({
  eventProjection: "e14d928023c7e8b4b6361e21a298dbb3bb3e8f55e869e55e199463c9df19167f",
  argumentIsolationExecutionProjection: "aa850a56ead1282c75ecbe2307a48d321623495c9d9710ac79e148c79db735fa",
  modelToolReceiptProjection: "5ef5d2a1bb4e6724ec42b245ab0bb31dc58739de0946038cff95b2951384f3d4",
  normalFinalProjection: "be20dba411d3bd89097afd19589d2ebb98182a40d13218ee0fbd920047e23c7a",
  runtimeProjection: "53c3e16055adbbc77fc095010ce4b714fad3d7ef3b5b58078b122063c84624ff",
  sessionRoleContent: "3dfadda28fd29faf8cf684f9ef121feccc51b799fa7c0f21d344e2c21191f562",
  sessionToolMeta: "ac5326e2d5c5599424237d8f760a8302f76a6e2bc687bb630600260642187f7b",
  terminalDom: "1794c5f4551d5e05cf4dfd6b3bfd272427891dd76c8363285746fd18cbbf8707",
  refreshLifecycle: "5fc851eaa40059021056e2806c4dbb151f3eb9eb0ae5959487e927beac858f4c",
});
const H4_6M_SEMANTIC_HASHES = Object.freeze({
  eventProjection: "94bf1904972bf0cc12156a1e1b1cdf24e04fad550eb92f286431c4ee63737110",
  signatureAlternationExecutionProjection: "ad859f657b2dfce7f53a2d7689e776c6a09d7351e8685233a44ee31d9b2ff7de",
  modelToolReceiptProjection: "d5ba927a08330c188893534558772db52a96f26860aca7a075ae1fdc8adf4a96",
  normalFinalProjection: "5c37ad3dafd0bee531d31a9a2518151c119ccac5334d5bf50c2fbcd1c71a82d7",
  runtimeProjection: "53c3e16055adbbc77fc095010ce4b714fad3d7ef3b5b58078b122063c84624ff",
  sessionRoleContent: "1d3cbc5c75a4986aba24ae023342def9fe1eb4c56e6dd19e50f17b11832e39b8",
  sessionToolMeta: "3eb5bf4987dda86b75128849634c491c48f85202ef0b71dfb1ecc330f5ca5e59",
  terminalDom: "5f19d080ae18a0686a4f7e8bd110db2ee06098138345fafa46100f777e9cab09",
  refreshLifecycle: "9eed2e8243028245f646fc0d656840e948b4d1e3cf3bc6b330963b918df9ecb9",
});
const H4_6N_SEMANTIC_HASHES = Object.freeze({
  eventProjection: "b396c14c67535bb53f17151d50ce778bdbba80acb024a6e1a5bbafdb9abf3c54",
  successResetExecutionProjection: "2f8deb0062775cb9a354a981b5716672c341fb6b9f562b6a73bcf327ca190322",
  modelToolReceiptProjection: "1f86ca8012531c5aa0090128549596797d3d60a1a9abd70a120e1dfa6cc6e7af",
  normalFinalProjection: "40824ea79a03d0f8e82df043ee3030f20b901b9ebfa94b44995752fed1906b6d",
  runtimeProjection: "53c3e16055adbbc77fc095010ce4b714fad3d7ef3b5b58078b122063c84624ff",
  sessionRoleContent: "42f299dc94ade765e72e403dde767f6586285eda79fa7f73955f1662f23ed381",
  sessionToolMeta: "f4d120765d56b4fd397c01caefdb2c9ec0970fcce210a52481f61136d062331a",
  terminalDom: "0894c3038aae4180631183d1f6fc91822be44f06865f318041fb1f996f894229",
  refreshLifecycle: "d9ac00cdbf0bc758c39b7f47d1941ea36c2b2bc07f7f9e264301833308d35725",
});
const H4_6O_SEMANTIC_HASHES = Object.freeze({
  eventProjection: "86e0b2c456a1b3cc6733c5315a821f0bb353ed6cb3cc57cb1c38cb94ac0f7fc8",
  retryExecutionProjection: "c4f4a8432ad9be01f331e72be1c9b6bd709bb7eda508c3b00604a2967d8c31fe",
  modelToolReceiptProjection: "4d02940043fc3266a6e6bf6e2a94ab7e775dd539401e84f40255daa29ed1b721",
  forcedFinalFailureProjection: "e8711527a19fc4bb557ba5a70c5bd87ec0f42590feb3d4c495e55b4416dce2f2",
  runtimeProjection: "c5664f513a21625433061cae70db64840b791260fcc21a4d4812924312e5ee1e",
  sessionRoleContent: "431b4ed43aa1395a0c9b439806bcdc49d813b0cc0784d01086fccf64401d2e5b",
  sessionRunState: "eb9c72f48ea2c11e70730a1c1c87491d66fcbe7e822ac879101ee910f599da17",
  terminalDom: "aae2e342c398f0d712b92ff87c54f10dab19be7cc26fbcebfb67bb24f762ccdf",
  refreshLifecycle: "60b5a625b74c8855ddde66f04ff48057eb00146ceab75988db20144d2c067f78",
});
const H4_6P_SEMANTIC_HASHES = Object.freeze({
  eventProjection: "b5ccf4a622600108de56687485f17642caab530651f31b1679d31840d45f2de2",
  retryExecutionProjection: "c4f4a8432ad9be01f331e72be1c9b6bd709bb7eda508c3b00604a2967d8c31fe",
  modelToolReceiptProjection: "4d02940043fc3266a6e6bf6e2a94ab7e775dd539401e84f40255daa29ed1b721",
  forcedFinalUnusableProjection: "ca5df9b2f2375b7ccfca0d745b636c55e29224a28edad7d40aa08ca333baec0f",
  runtimeProjection: "5544f1eb37db1be95f38a7ac373a3a83b8b1490ff2760ad6fe18880cb7547186",
  sessionRoleContent: "431b4ed43aa1395a0c9b439806bcdc49d813b0cc0784d01086fccf64401d2e5b",
  sessionRunState: "c40a0bc4034901d0d0085d53f1d2bc3a144dd957b34e9c8cca87ac16543b5784",
  terminalDom: "3ede9770eb9cae435e6ad61a79676f550bae27c916a1aea6ad94742e8b533a06",
  refreshLifecycle: "60b5a625b74c8855ddde66f04ff48057eb00146ceab75988db20144d2c067f78",
});
const H4_7C_BASE_SEMANTIC_HASHES = Object.freeze({
  mainToolTrace: "6599ebee8ff79520ee51e2fa2fe2011ce6237091791282c02f6b5525092223c4",
  backgroundAgent: "1319a246751c8daa8c6546cfe1b8f2aab159bb00a11b01f908b5d20c7f414545",
  backgroundRuntime: "6b71bc4b26a681050327da18905949caaa9ae806dd78747dc9708bba1a5f76d1",
  backgroundMeta: "e26b1c4a7e1a70f87ab60335fcd655331a2601f2a7dd6882e63821d2eb8d5baa",
  requestCounts: "e90926ff643c4cff6ab16720a27dedbd1b5f4561b874e7bbe4ef7d3e63eaba1e",
});
const H4_SYNC_1_SEMANTIC_HASHES = Object.freeze({
  preParallelFence: "10b427d80882ae5a10fc84ca44f894afea07bccf3b9e1944bc0b3ae5552fcf47",
  terminalOrdering: "3639c2f18f3484e8a76ca8ef53b45a0b29ec1281a65943b75234cd55593744ee",
  followupRequestContext: "25f3d36ea8966773c131ff552dea9211c24deba88efd68e22ba796226508ac10",
  followupAgentRuntime: "b6d711c9ff9fcfb50b179aa03938c93eef6b741c971335310bee4a1ec8b875b3",
  followupSession: "e0dfc6865fab9ada4fc038598ad83e22b126cdbd8c2cb66d91952497cb5ce25d",
  followupDom: "b7b1505cf4fed62478c535a9ad86fab9291a26ac8318ac04d47ef0dc742fc8a6",
  requestCounts: "51357c34453ca7e453830920b00500004f0183b75bcf58b9e8e56121e52860fb",
  refreshLifecycle: "4f728a8ceb1d29f8c888e828cd1b27d21fbdb1508e030fa29a5aa3ffd4ba281f",
});
const H4_8A_SEMANTIC_HASHES = Object.freeze({
  waitingEventProjection: "6f07ddb587ba352d15f3b9d8608d3b89c475f3f3217ec713304b31b0e5a6da41",
  waitingSnapshot: "722b86175ddd43f7306b459d5f6410a0a7c8a8f3ad5b8075cfb6dd2bc8506c3b",
  inputSubmissionProjection: "1bc729f0df83ed708bbf5f1c397a6aaef4d73788d50ccfb7e45473859cd1bc27",
  runtimeProjection: "c828f32c0eef8d43d9464fce985d82603cc6817b9f1ce948be2fd343e8c4652c",
  sessionRoleContent: "ba570ba870a189929e69069ec42c83747102a292b8118a153900185c27686bf0",
  sessionInputMeta: "30fbb18d20b9db9ab076b932eb1fa9fc11aeaf11f61249f7248db17380234559",
  waitingDom: "f0586513d93fe803d143b3929fd4e56c13fa317de5dcd9dd6ce1d4f1fe351dad",
  terminalDom: "37c2441c6730d71c5b4af6e34798778c004c163686bb5fcee31179cf1fd69f8b",
  refreshLifecycle: "fe57c8d69de127f1cfd2b85d1bfb78878aaede36c381a19e2a1a616bba080629",
});
const H4_8B_SEMANTIC_HASHES = Object.freeze({
  waitingEventProjection: "0e66c7254f24708cf2f09c10ab2cc456a49954a0d691a9aaf61ce12d67d3184f",
  progressSnapshot: "372e17ded267937f8f1ca30c683cf7ce8b548af976c4979f617af8fa04d006aa",
  progressDom: "d635937b610a1e098910ed3ddb43c2f6ab734e349401d9336e812588b59a85e6",
  inputSubmissionProjection: "5082f9c4a6eded92d612adae0334717b94619f295eaaabf86708e4c9f0b68eb4",
  runtimeProjection: "7f4f58396717deb173b18dd703f2ff76557455cd4aee661cd71c3c4bc5aa1b31",
  sessionRoleContent: "ba570ba870a189929e69069ec42c83747102a292b8118a153900185c27686bf0",
  sessionInputMeta: "89823e3f8e29025bd03d50d33bd063f70ca68d6558a7f465ca5b83dd5591b820",
  terminalDom: "bcd0070502f78af981739b6116e93adbaa2d5f3c5f542f6d827de3c3eac7b7c1",
  refreshLifecycle: "12189043590d29b528a2beaac58e4f1c49f66d0d0a1e4ff2889c3dd7b69f612f",
});
const H4_8C_SEMANTIC_HASHES = Object.freeze({
  approved: Object.freeze({
    waitingEventProjection: "87a7ea23fa306ad3d2251d5245ed7e0ce8541971c944568def98b13b00fec4f3",
    waitingSnapshot: "9c19fd9e30893a77a584551ededdbe9ace115cf6fc5d928c3b7649e70ade07f2",
    waitingDom: "880e7bd7c6f2e62d84a0c8bcaf4ccdea7de3504ec0b36ca00063aa8ea75ba618",
    decisionSubmissionProjection: "10ee72f265dd84bd02f177a7ed8330f2b949f6a4c9bb57ee661381ded560179a",
    runtimeProjection: "b942ee79bdd556a07c170919de5e110853d0b0be853efeba554f364cc36f0540",
    sessionRoleContent: "f6ef57520b2b66ebb11473e695aa43897363bbf6876c62e652de04a6a792ebb0",
    sessionAuthorizationMeta: "817262e2d16999b26b98a8c25711160d387e238f5c62fa385e3132ff1382aac2",
    terminalDom: "30a687f6910faf0e82f18e0097187cd7b021957270c18370c7cab2774c65602d",
    refreshLifecycle: "8cd5d4b2c4c6de7fa02758a00429fcdca4877a25f6ae7e4b58fa24dc4ad67c04",
  }),
  rejected: Object.freeze({
    waitingEventProjection: "87a7ea23fa306ad3d2251d5245ed7e0ce8541971c944568def98b13b00fec4f3",
    waitingSnapshot: "9c19fd9e30893a77a584551ededdbe9ace115cf6fc5d928c3b7649e70ade07f2",
    waitingDom: "880e7bd7c6f2e62d84a0c8bcaf4ccdea7de3504ec0b36ca00063aa8ea75ba618",
    decisionSubmissionProjection: "2e4006664b0b78311fbb351d43957db74af5cea392479b9b5b3df69646faad3e",
    runtimeProjection: "b942ee79bdd556a07c170919de5e110853d0b0be853efeba554f364cc36f0540",
    sessionRoleContent: "f6ef57520b2b66ebb11473e695aa43897363bbf6876c62e652de04a6a792ebb0",
    sessionAuthorizationMeta: "789eb128e116eede40ace51e8118457fab6214bfb58692afe708cac7b3434275",
    terminalDom: "292de41a94f02fdbe4ba3a58cf6be4a9e218b34157a8fc191a240282cc18fb12",
    refreshLifecycle: "a020554dd7822809017c01e41e0fbcf85879e2ea019f9ad16670c76d0a599ed3",
  }),
});
const H4_8D_SEMANTIC_HASHES = Object.freeze({
  waitingEventProjection: "87a7ea23fa306ad3d2251d5245ed7e0ce8541971c944568def98b13b00fec4f3",
  waitingSnapshot: "9c19fd9e30893a77a584551ededdbe9ace115cf6fc5d928c3b7649e70ade07f2",
  waitingDom: "880e7bd7c6f2e62d84a0c8bcaf4ccdea7de3504ec0b36ca00063aa8ea75ba618",
  thirdPartyTransitionProjection: "07a021c9dedf08a455140666ebc27a063eb61d996fb71b8ead63b358dea10b1f",
  conflictSubmissionProjection: "6903528a33064bdbd1204523546ff9a4144083782e28452b9c7b9ee1a6948ac8",
  runtimeProjection: "b942ee79bdd556a07c170919de5e110853d0b0be853efeba554f364cc36f0540",
  sessionRoleContent: "f6ef57520b2b66ebb11473e695aa43897363bbf6876c62e652de04a6a792ebb0",
  sessionAuthorizationMeta: "b8b0df63df027b536446ed665706b7e87ac84e6e304c3fcebdbcbb444137240d",
  terminalDom: "b564237ff8ab8a1bf5578a8181f17a6c711d3b15789bbfecacefc8eff862389d",
  refreshLifecycle: "a349197ae9a3805e700b57bb13464687e37307f4b923f85f1426d6d4dc184f1a",
});
const H4_8E_SEMANTIC_HASH_KEYS = Object.freeze([
  "waitingEventProjection",
  "waitingQuestionnaireSnapshot",
  "queueSubmissionProjection",
  "waitingQueueSession",
  "waitingDom",
  "waitingRefreshLifecycle",
  "inputSubmissionProjection",
  "queuePromotionProjection",
  "runtimeProjection",
  "sessionRoleContent",
  "terminalDom",
  "refreshLifecycle",
]);
const H4_8E_SEMANTIC_HASHES = Object.freeze({
  waitingEventProjection: "6f07ddb587ba352d15f3b9d8608d3b89c475f3f3217ec713304b31b0e5a6da41",
  waitingQuestionnaireSnapshot: "722b86175ddd43f7306b459d5f6410a0a7c8a8f3ad5b8075cfb6dd2bc8506c3b",
  queueSubmissionProjection: "8fa3b6d9e440913edceefca2c9e1855e7b7be51341fb68faffe7fef9d0269556",
  waitingQueueSession: "225ef8c09bb0f7b09463209501568d754d2cd4a795bba060a7e667d2b8c01eeb",
  waitingDom: "499509b21abbc0a3f6805561df5918183df04267737159089aa56aee7010bff6",
  waitingRefreshLifecycle: "d114d05ecf65efe64f8c21b589dfde91e0f6dafd7c44616fa83eaeeb11076cd8",
  inputSubmissionProjection: "53765f8c4d304eeeb2db40c7d74404d1db3f8838450d862660a28cfa243b434b",
  queuePromotionProjection: "513394446016e85f76718ef0c65945b3f24a47867e39e04232f3968d4a18446a",
  runtimeProjection: "f7f333b2b0573c96ee9b2a489019f32d7724c5273a5963896884378e1a9eb7ba",
  sessionRoleContent: "e9a93e5e49bde42f63d3047001afa5f79c78373f1365378367311022d15f71ec",
  terminalDom: "d2dc405690fcf7c80ad84ffaca0496aba43b40e2ebd528971a462a82ba9da90d",
  refreshLifecycle: "1583ae3f119ccbc86c8ec055d7d486a7c3a607cfd79fd9728ecadd8907cf55e0",
});
const H4_8F_SEMANTIC_HASH_KEYS = Object.freeze([
  "waitingEventProjection",
  "waitingSnapshot",
  "waitingDom",
  "failedAttemptProjection",
  "retrySubmissionProjection",
  "runtimeProjection",
  "sessionRoleContent",
  "sessionAuthorizationMeta",
  "terminalDom",
  "refreshLifecycle",
]);
const H4_8F_SEMANTIC_HASHES = Object.freeze({
  waitingEventProjection: "87a7ea23fa306ad3d2251d5245ed7e0ce8541971c944568def98b13b00fec4f3",
  waitingSnapshot: "9c19fd9e30893a77a584551ededdbe9ace115cf6fc5d928c3b7649e70ade07f2",
  waitingDom: "880e7bd7c6f2e62d84a0c8bcaf4ccdea7de3504ec0b36ca00063aa8ea75ba618",
  failedAttemptProjection: "d906f98034b76a14083d4bd3bbe9f7e0d8cf05584de83eaf68ca20c20a636e70",
  retrySubmissionProjection: "5de63672ddec48bf0de379cf9f24abf06eff143b2309d73da2a3a70669694c13",
  runtimeProjection: "b942ee79bdd556a07c170919de5e110853d0b0be853efeba554f364cc36f0540",
  sessionRoleContent: "f6ef57520b2b66ebb11473e695aa43897363bbf6876c62e652de04a6a792ebb0",
  sessionAuthorizationMeta: "817262e2d16999b26b98a8c25711160d387e238f5c62fa385e3132ff1382aac2",
  terminalDom: "30a687f6910faf0e82f18e0097187cd7b021957270c18370c7cab2774c65602d",
  refreshLifecycle: "fc229f1032cb024b68f1b4755e69c590e58f2ad2a1a0ef7c604e8c38359403d3",
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

function stableSignatureAlternationResult(result) {
  const error = String(result?.error || "");
  return {
    ...stableRepeatedRangeFailureResult(result),
    missingFileError: error === "文件不存在",
  };
}

function stableSuccessResetResult(result) {
  const source = result && typeof result === "object" ? result : {};
  const error = String(source.error || "");
  const content = String(source.content || "");
  const failureCountPresent = Object.prototype.hasOwnProperty.call(source, "failureCount");
  const projection = {
    ok: source.ok === false ? false : source.ok,
    action: String(source.action || ""),
    path: String(source.path || ""),
    contentSha256: Object.prototype.hasOwnProperty.call(source, "content")
      ? crypto.createHash("sha256").update(content).digest("hex")
      : "",
    size: Object.prototype.hasOwnProperty.call(source, "size") ? Number(source.size) : null,
    truncated: Object.prototype.hasOwnProperty.call(source, "truncated")
      ? Boolean(source.truncated)
      : null,
    lineRangePresent: Object.prototype.hasOwnProperty.call(source, "lineRange"),
    lineRange: Object.prototype.hasOwnProperty.call(source, "lineRange")
      ? source.lineRange
      : null,
    errorCodePresent: Object.prototype.hasOwnProperty.call(source, "errorCode"),
    errorPresent: Boolean(error.trim()),
    missingFileError: error === "文件不存在",
    failureCountPresent,
    retryBlocked: Boolean(source.retryBlocked),
    retryLimitReached: Boolean(source.retryLimitReached),
  };
  if (failureCountPresent) projection.failureCount = Number(source.failureCount);
  return projection;
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
  scenarioPrefix: "repeated-range-failure",
  evidencePrefix: "repeated-range-failure",
  userMarker: REPEATED_RANGE_FAILURE_USER,
  stageMarker: REPEATED_RANGE_FAILURE_STAGE,
  finalMarker: REPEATED_RANGE_FAILURE_FINAL,
  arguments: Object.freeze({ path: "fixture.txt", startLine: 2, endLine: 1 }),
  callArguments: Object.freeze(Array.from(
    { length: 4 },
    () => Object.freeze({ path: "fixture.txt", startLine: 2, endLine: 1 }),
  )),
  expectedResults: EXPECTED_REPEATED_RANGE_RESULTS,
  executedArguments: Object.freeze(Array.from(
    { length: 3 },
    () => Object.freeze({ path: "fixture.txt", startLine: 2, endLine: 1 }),
  )),
  receiptMetric: "repeatedRangeFailureReceipts",
  finalMetric: "forcedFinal",
  executionHashKey: "retryExecutionProjection",
  finalHashKey: "forcedFinalProjection",
  activeForceFinalRound: true,
  finalMetricExpected: Object.freeze({
    toolsPresent: false,
    toolChoicePresent: false,
    recoveryInstructionPresent: true,
  }),
  expectedRetryBlockedEvents: Object.freeze([Object.freeze({
    seq: 20,
    type: "tool_retry_blocked",
    failureCount: 3,
    toolCallId: "tool-4",
    name: "read_file",
  })]),
  projectResult: stableRepeatedRangeFailureResult,
  hashes: H4_6K_SEMANTIC_HASHES,
});

const FORCED_FINAL_MODEL_FAILURE_CONTRACT = Object.freeze({
  ...REPEATED_RANGE_FAILURE_CONTRACT,
  key: "H4-6O",
  scenarioPrefix: "forced-final-model-failure",
  evidencePrefix: "forced-final-model-failure",
  userMarker: FORCED_FINAL_MODEL_FAILURE_USER,
  finalMarker: PARALLEL_FAILURE_ERROR,
  terminalStatus: "failed",
  finalHashKey: "forcedFinalFailureProjection",
  hashes: H4_6O_SEMANTIC_HASHES,
});

const FORCED_FINAL_UNUSABLE_TOOL_CONTRACT = Object.freeze({
  ...REPEATED_RANGE_FAILURE_CONTRACT,
  key: "H4-6P",
  scenarioPrefix: "forced-final-unusable-tool",
  evidencePrefix: "forced-final-unusable-tool",
  userMarker: FORCED_FINAL_UNUSABLE_TOOL_USER,
  terminalStatus: "failed",
  terminalFailureKind: "unusable-tool-response",
  terminalErrorCode: "repeated_tool_failure",
  terminalErrorMarker: FORCED_FINAL_UNUSABLE_ERROR_MARKER,
  terminalForceFinalRound: false,
  terminalEventTail: Object.freeze(["model_completed", "failed"]),
  terminalRuntimeStatus: "completed",
  terminalRuntimeCursors: Object.freeze([4, 3, 3, 3, 3]),
  terminalNextCursor: 25,
  unusableToolCallId: FORCED_FINAL_UNUSABLE_TOOL_CALL_ID,
  finalHashKey: "forcedFinalUnusableProjection",
  hashes: H4_6P_SEMANTIC_HASHES,
});

const ARGUMENT_ISOLATION_CALL_ARGUMENTS = Object.freeze([
  Object.freeze({ path: "fixture.txt", startLine: 2, endLine: 1 }),
  Object.freeze({ path: "fixture.txt", startLine: 3, endLine: 1 }),
  Object.freeze({ path: "fixture.txt", startLine: 2, endLine: 1 }),
]);
const EXPECTED_ARGUMENT_ISOLATION_RESULTS = Object.freeze([1, 1, 2].map((failureCount) => (
  Object.freeze({
    ok: false,
    action: "read_file",
    errorCode: "",
    errorPresent: true,
    startLineMentioned: true,
    endLineMentioned: true,
    failureCount,
    fieldErrorsPresent: false,
    retryBlocked: false,
    retryLimitReached: false,
  })
)));
const ARGUMENT_ISOLATION_FAILURE_CONTRACT = Object.freeze({
  key: "H4-6L",
  scenarioPrefix: "argument-isolation",
  evidencePrefix: "argument-isolation-failure",
  userMarker: ARGUMENT_ISOLATION_USER,
  stageMarker: ARGUMENT_ISOLATION_STAGE,
  finalMarker: ARGUMENT_ISOLATION_FINAL,
  arguments: ARGUMENT_ISOLATION_CALL_ARGUMENTS[0],
  callArguments: ARGUMENT_ISOLATION_CALL_ARGUMENTS,
  expectedResults: EXPECTED_ARGUMENT_ISOLATION_RESULTS,
  executedArguments: ARGUMENT_ISOLATION_CALL_ARGUMENTS,
  receiptMetric: "argumentIsolationReceipts",
  finalMetric: "normalFinal",
  executionHashKey: "argumentIsolationExecutionProjection",
  finalHashKey: "normalFinalProjection",
  activeForceFinalRound: false,
  finalMetricExpected: Object.freeze({
    toolsPresent: true,
    toolChoicePresent: true,
    recoveryInstructionPresent: false,
  }),
  expectedRetryBlockedEvents: Object.freeze([]),
  projectResult: stableRepeatedRangeFailureResult,
  hashes: H4_6L_SEMANTIC_HASHES,
});

const SIGNATURE_ALTERNATION_CALL_ARGUMENTS = Object.freeze(Array.from(
  { length: 3 },
  () => Object.freeze({
    path: SIGNATURE_ALTERNATION_READ_PATH,
    startLine: 2,
    endLine: 1,
  }),
));
const EXPECTED_SIGNATURE_ALTERNATION_RESULTS = Object.freeze([
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
    missingFileError: false,
  }),
  Object.freeze({
    ok: false,
    action: "read_file",
    errorCode: "",
    errorPresent: true,
    startLineMentioned: false,
    endLineMentioned: false,
    failureCount: 1,
    fieldErrorsPresent: false,
    retryBlocked: false,
    retryLimitReached: false,
    missingFileError: true,
  }),
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
    missingFileError: false,
  }),
]);
const SIGNATURE_ALTERNATION_FAILURE_CONTRACT = Object.freeze({
  key: "H4-6M",
  scenarioPrefix: "signature-alternation",
  evidencePrefix: "signature-alternation-failure",
  userMarker: SIGNATURE_ALTERNATION_USER,
  stageMarker: SIGNATURE_ALTERNATION_STAGE,
  finalMarker: SIGNATURE_ALTERNATION_FINAL,
  arguments: SIGNATURE_ALTERNATION_CALL_ARGUMENTS[0],
  callArguments: SIGNATURE_ALTERNATION_CALL_ARGUMENTS,
  expectedResults: EXPECTED_SIGNATURE_ALTERNATION_RESULTS,
  executedArguments: SIGNATURE_ALTERNATION_CALL_ARGUMENTS,
  receiptMetric: "signatureAlternationReceipts",
  finalMetric: "normalFinal",
  executionHashKey: "signatureAlternationExecutionProjection",
  finalHashKey: "normalFinalProjection",
  activeForceFinalRound: false,
  finalMetricExpected: Object.freeze({
    toolsPresent: true,
    toolChoicePresent: true,
    recoveryInstructionPresent: false,
  }),
  expectedRetryBlockedEvents: Object.freeze([]),
  projectResult: stableSignatureAlternationResult,
  hashes: H4_6M_SEMANTIC_HASHES,
});

const SUCCESS_RESET_CALL_ARGUMENTS = Object.freeze(Array.from(
  { length: 3 },
  () => Object.freeze({ path: SUCCESS_RESET_READ_PATH }),
));
const FIXTURE_CONTENT_SHA256 = crypto.createHash("sha256")
  .update(FIXTURE_CONTENT)
  .digest("hex");
const EXPECTED_SUCCESS_RESET_RESULTS = Object.freeze([
  Object.freeze({
    ok: false,
    action: "read_file",
    path: "",
    contentSha256: "",
    size: null,
    truncated: null,
    lineRangePresent: false,
    lineRange: null,
    errorCodePresent: false,
    errorPresent: true,
    missingFileError: true,
    failureCountPresent: true,
    retryBlocked: false,
    retryLimitReached: false,
    failureCount: 1,
  }),
  Object.freeze({
    ok: true,
    action: "read_file",
    path: SUCCESS_RESET_READ_PATH,
    contentSha256: FIXTURE_CONTENT_SHA256,
    size: Buffer.byteLength(FIXTURE_CONTENT, "utf8"),
    truncated: false,
    lineRangePresent: true,
    lineRange: null,
    errorCodePresent: false,
    errorPresent: false,
    missingFileError: false,
    failureCountPresent: false,
    retryBlocked: false,
    retryLimitReached: false,
  }),
  Object.freeze({
    ok: false,
    action: "read_file",
    path: "",
    contentSha256: "",
    size: null,
    truncated: null,
    lineRangePresent: false,
    lineRange: null,
    errorCodePresent: false,
    errorPresent: true,
    missingFileError: true,
    failureCountPresent: true,
    retryBlocked: false,
    retryLimitReached: false,
    failureCount: 1,
  }),
]);
const SUCCESS_RESET_FAILURE_CONTRACT = Object.freeze({
  key: "H4-6N",
  scenarioPrefix: "success-reset",
  evidencePrefix: "success-reset-failure",
  userMarker: SUCCESS_RESET_USER,
  stageMarker: SUCCESS_RESET_STAGE,
  finalMarker: SUCCESS_RESET_FINAL,
  arguments: SUCCESS_RESET_CALL_ARGUMENTS[0],
  callArguments: SUCCESS_RESET_CALL_ARGUMENTS,
  expectedResults: EXPECTED_SUCCESS_RESET_RESULTS,
  expectedOutcomes: Object.freeze(["failed", "succeeded", "failed"]),
  executedArguments: SUCCESS_RESET_CALL_ARGUMENTS,
  receiptMetric: "successResetReceipts",
  finalMetric: "normalFinal",
  executionHashKey: "successResetExecutionProjection",
  finalHashKey: "normalFinalProjection",
  activeForceFinalRound: false,
  finalMetricExpected: Object.freeze({
    toolsPresent: true,
    toolChoicePresent: true,
    recoveryInstructionPresent: false,
  }),
  expectedRetryBlockedEvents: Object.freeze([]),
  projectResult: stableSuccessResetResult,
  hashes: H4_6N_SEMANTIC_HASHES,
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
  if (contract.unusableToolCallId) {
    toolAliases.set(contract.unusableToolCallId, `tool-${baseEvidence.toolCallIds.length + 1}`);
  }
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
    if (data.errorCode != null) projection.errorCode = String(data.errorCode);
    if (data.error != null) projection.errorPresent = Boolean(String(data.error).trim());
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
  const agentActionMatch = url.pathname.match(
    /^\/api\/agent\/runs\/([^/]+)\/(input|resume|authorization)$/,
  );
  const agentMatch = url.pathname.match(/^\/api\/agent\/runs\/([^/]+)$/);
  const runtimeMatch = url.pathname.match(/^\/api\/runtime\/runs\/([^/]+)$/);
  if (url.pathname === "/api/agent/runs") {
    return { at: Date.now(), method, path: "/api/agent/runs", kind: "agent", idHash: "", cursor: 0 };
  }
  if (url.pathname === "/api/runtime/runs") {
    return { at: Date.now(), method, path: "/api/runtime/runs", kind: "runtime", idHash: "", cursor: 0 };
  }
  if (agentActionMatch) {
    const action = String(agentActionMatch[2] || "");
    return {
      at: Date.now(),
      method,
      path: `/api/agent/runs/[id]/${action}`,
      kind: `agent-${action}`,
      idHash: idHash(decodeURIComponent(agentActionMatch[1])),
      cursor: 0,
    };
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
    const cursorRaw = url.searchParams.get("cursor");
    const waitRaw = url.searchParams.get("wait");
    const cursorValid = /^\d+$/.test(String(cursorRaw ?? ""));
    const waitValid = /^\d+$/.test(String(waitRaw ?? ""));
    const wait = waitValid ? Number(waitRaw) : -1;
    return {
      at: Date.now(),
      method,
      path: "/api/runtime/runs/[id]",
      kind: "runtime",
      idHash: idHash(decodeURIComponent(runtimeMatch[1])),
      cursor: Number(url.searchParams.get("cursor") || 0),
      wait,
      queryShape: cursorValid && waitValid
        ? `cursor-number+wait-${wait > 0 ? "positive" : "zero"}`
        : "missing-or-invalid",
    };
  }
  return { at: Date.now(), method, path: url.pathname, kind: "other", idHash: "", cursor: 0 };
}

async function waitForFrontendRuntimeConsumer(h4, {
  runtimeRunId,
  requestBoundary,
  label,
}) {
  const targetIdHash = idHash(runtimeRunId);
  const boundary = Number(requestBoundary);
  expect(targetIdHash).not.toBe("");
  expect(Number.isSafeInteger(boundary)).toBe(true);
  expect(boundary).toBeGreaterThanOrEqual(0);

  let evidence = null;
  try {
    await expect.poll(() => {
      const candidates = h4.loopbackRequests.slice(boundary).filter((entry) => (
        entry.kind === "runtime"
        && entry.method === "GET"
        && entry.path === "/api/runtime/runs/[id]"
        && entry.idHash === targetIdHash
      ));
      const matches = candidates.filter((entry) => (
        entry.wait === 25 && entry.queryShape === "cursor-number+wait-positive"
      ));
      const boundedCandidates = candidates.slice(-4).map((entry) => ({
        method: entry.method,
        path: entry.path,
        idHash: entry.idHash,
        cursor: entry.cursor,
        wait: entry.wait,
        queryShape: entry.queryShape,
      }));
      evidence = {
        label,
        targetIdHash,
        candidateCount: candidates.length,
        matchedCount: matches.length,
        candidates: boundedCandidates,
        sampleHash: canonicalHash(boundedCandidates),
      };
      return matches.length > 0;
    }).toBe(true);
    return evidence;
  } finally {
    h4.diagnosticSteps.push({
      step: "frontend-runtime-consumer-fence",
      ...(evidence || {
        label,
        targetIdHash,
        candidateCount: 0,
        matchedCount: 0,
        candidates: [],
        sampleHash: canonicalHash([]),
      }),
    });
  }
}

async function waitForMessageProjection(h4, {
  label,
  sample,
  expected,
  sourceFacts = {},
}) {
  const recentSamples = [];
  let projection = null;
  const record = (value) => {
    const hash = canonicalHash(value);
    if (recentSamples.at(-1)?.hash !== hash) {
      recentSamples.push({ hash, projection: value });
      if (recentSamples.length > 4) recentSamples.shift();
    }
  };

  try {
    await expect.poll(async () => {
      projection = await h4.page.evaluate(sample, sourceFacts);
      record(projection);
      return projection;
    }).toEqual(expected);
    h4.diagnosticSteps.push({
      step: "message-projection-fence",
      label,
      expectedHash: canonicalHash(expected),
      sourceFactsHash: canonicalHash(sourceFacts),
      sampleCount: recentSamples.length,
      projectionHash: canonicalHash(projection),
    });
    return projection;
  } catch (error) {
    h4.diagnosticSteps.push({
      step: "message-projection-fence-failed",
      label,
      expectedHash: canonicalHash(expected),
      sourceFactsHash: canonicalHash(sourceFacts),
      samples: recentSamples,
    });
    throw error;
  }
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

async function dropTiffAttachment(page) {
  const dataTransfer = await page.evaluateHandle(({ base64, name }) => {
    const binary = atob(base64);
    const bytes = Uint8Array.from(binary, (character) => character.charCodeAt(0));
    const transfer = new DataTransfer();
    transfer.items.add(new File([bytes], name, { type: "image/tiff" }));
    return transfer;
  }, { base64: TIFF_ATTACHMENT_BASE64, name: TIFF_ATTACHMENT_NAME });
  try {
    await page.locator("#prompt").dispatchEvent("drop", { dataTransfer });
  } finally {
    await dataTransfer.dispose();
  }
}

async function expectDecodedImage(locator) {
  await expect(locator).toBeVisible();
  await expect.poll(async () => locator.evaluate((image) => ({
    complete: image.complete,
    naturalWidth: image.naturalWidth,
    naturalHeight: image.naturalHeight,
  }))).toEqual({ complete: true, naturalWidth: 18, naturalHeight: 12 });
}

function normalizedTiffPreviewMime(value) {
  const normalized = String(value || "").trim().toLowerCase();
  return ["image/tif", "image/x-tiff"].includes(normalized) ? "image/tiff" : normalized;
}

function previewRequestKeyHash(request, url) {
  if (request.method() === "GET") {
    const attachmentPath = String(url.searchParams.get("path") || "");
    return canonicalHash({ mime: "image/tiff", attachmentPath });
  }
  let payload = null;
  try {
    payload = JSON.parse(request.postData() || "null");
  } catch (_) {
    payload = null;
  }
  return canonicalHash({
    mime: normalizedTiffPreviewMime(payload?.mime),
    inlineContentHash: crypto.createHash("sha256")
      .update(String(payload?.contentBase64 || ""))
      .digest("hex"),
  });
}

async function completeTiffPreviewLifecycle(h4, runtime) {
  const { page } = h4;
  const previewRequests = [];
  let previewPhase = "initialization";
  let mainDocumentGeneration = 0;
  let expectedReloadGeneration = 0;
  let navigationStage = "before-navigation";
  const recordMainFrameNavigation = (frame) => {
    if (frame !== page.mainFrame()) return;
    mainDocumentGeneration += 1;
    navigationStage = expectedReloadGeneration > 0
      && mainDocumentGeneration >= expectedReloadGeneration
      ? "reload-document"
      : "initial-document";
    h4.diagnosticSteps.push({
      step: "tiff-main-document-generation",
      documentGeneration: mainDocumentGeneration,
      navigationStage,
    });
  };
  const recordPreviewRequest = (request) => {
    const url = new URL(request.url());
    if (url.pathname !== "/api/attachments/preview") return;
    let frameScope = "unavailable";
    try {
      frameScope = request.frame() === page.mainFrame() ? "main" : "subframe";
    } catch (_) {
      frameScope = "unavailable";
    }
    previewRequests.push({
      phase: previewPhase,
      method: request.method(),
      path: url.pathname,
      keyHash: previewRequestKeyHash(request, url),
      documentGeneration: mainDocumentGeneration,
      navigationStage,
      frameScope,
      initiator: request.resourceType(),
      navigationRequest: request.isNavigationRequest(),
    });
  };
  const previewRequestsFor = (phase, method) => previewRequests.filter((request) => (
    request.phase === phase
    && request.method === method
    && request.path === "/api/attachments/preview"
  ));
  page.on("framenavigated", recordMainFrameNavigation);
  page.on("request", recordPreviewRequest);
  await h4.open(runtime);
  expect(mainDocumentGeneration).toBeGreaterThan(0);
  await assertFrontendRuntime(page, runtime);
  if (runtime === "classic") {
    expect(new URL(page.url()).pathname).toBe(CLASSIC_FALLBACK_PATH);
    expect(new URL(page.url()).search).toBe("");
    expect(await page.locator("html").getAttribute("data-code-frontend-ready")).toBeNull();
  }

  previewPhase = "composer-success";
  await dropTiffAttachment(page);
  const initialComposerPreview = page.locator("#imageThumbs [data-composer-image-preview]");
  await expectDecodedImage(initialComposerPreview);
  expect(previewRequestsFor("composer-success", "POST")).toHaveLength(1);
  expect(await initialComposerPreview.getAttribute("src")).toMatch(/^blob:/);
  await expect(page.locator("#imageThumbs [data-composer-image-fallback]")).toBeHidden();
  await page.locator("#imageThumbs .img-thumb-remove").click();
  await expect(page.locator("#imageThumbs")).toHaveCount(0);

  let injectedPreviewFailures = 0;
  const previewPattern = "**/api/attachments/preview*";
  const failPreview = async (route) => {
    injectedPreviewFailures += 1;
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ error: "synthetic preview unavailable" }),
    });
  };
  await page.route(previewPattern, failPreview);
  previewPhase = "composer-failure";
  await dropTiffAttachment(page);
  await expect(page.locator("#imageThumbs [data-composer-image-fallback]")).toBeVisible();
  await expect(page.locator("#imageThumbs [data-composer-image-preview]")).toHaveCount(0);
  expect(previewRequestsFor("composer-failure", "POST")).toHaveLength(1);

  await page.locator("#prompt").fill(TIFF_IMAGE_USER);
  previewPhase = "message-initial";
  await page.locator("#sendBtn").click();
  const userMessage = page.locator("#messages article.msg.user").filter({ hasText: TIFF_IMAGE_USER });
  await expect(userMessage).toHaveCount(1);
  await expect(userMessage.locator("[data-message-image-fallback]")).toBeVisible();
  await expect.poll(() => previewRequestsFor("message-initial", "GET").length).toBe(1);
  await expect(page.locator("#activeRunBanner.visible .active-run-line[role='status']")).toBeVisible();
  previewPhase = "model-rerender";
  await h4.host.releaseModel();
  await expect(page.locator("#messages article.msg.assistant").filter({ hasText: TIFF_IMAGE_FINAL })).toHaveCount(1);
  expect(previewRequestsFor("model-rerender", "GET")).toHaveLength(0);
  expect(injectedPreviewFailures).toBe(2);

  const sessionButton = page.locator("#sessionList .session-row.active button.session-main");
  await expect(sessionButton).toHaveCount(1);
  const sessionId = await sessionButton.getAttribute("data-session-id");
  expect(sessionId).toBeTruthy();
  const sessionBefore = await fetchProductionJson(
    page,
    `/api/sessions/${encodeURIComponent(sessionId)}`,
  );
  expect(sessionBefore.status).toBe(200);
  const persistedUser = sessionBefore.body.messages.find((message) => message?.role === "user");
  const persistedImage = persistedUser?.content?.find((item) => item?.type === "image_url");
  const persistedDataUrl = String(persistedImage?.image_url?.url || "");
  expect(persistedDataUrl.startsWith("data:image/tiff;base64,")).toBe(true);
  expect(crypto.createHash("sha256").update(
    Buffer.from(persistedDataUrl.split(",", 2)[1], "base64"),
  ).digest("hex")).toBe(TIFF_ATTACHMENT_SHA256);
  expect(persistedUser?._images).toHaveLength(1);
  expect(persistedUser._images[0]).toMatchObject({
    name: TIFF_ATTACHMENT_NAME,
    mime: "image/tiff",
  });
  expect(String(persistedUser._images[0].path || "")).toMatch(/^attachments\//);
  const persistedPreviewKeyHash = canonicalHash({
    mime: normalizedTiffPreviewMime(persistedUser._images[0].mime),
    attachmentPath: String(persistedUser._images[0].path || ""),
  });
  expect(previewRequestsFor("message-initial", "GET")[0]).toMatchObject({
    keyHash: persistedPreviewKeyHash,
    documentGeneration: mainDocumentGeneration,
    navigationStage: "initial-document",
    frameScope: "main",
    initiator: "fetch",
    navigationRequest: false,
  });
  expect(JSON.stringify(sessionBefore.body)).not.toContain("_previewUrl");
  expect(JSON.stringify(sessionBefore.body)).not.toContain("_previewFailed");

  const metricsBefore = await h4.metrics();
  expect(metricsBefore.chatRequests).toEqual([{
    scenario: "tiff-image",
    stream: true,
    hasToolResult: false,
    imageProjection: {
      count: 1,
      images: [{ mime: "image/png", png: true, width: 18, height: 12 }],
      recognized: true,
    },
  }]);
  expect(metricsBefore.attachments).toEqual({
    fileCount: 1,
    files: [{
      size: Buffer.from(TIFF_ATTACHMENT_BASE64, "base64").length,
      sha256: TIFF_ATTACHMENT_SHA256,
      sourceFormat: "TIFF",
      mime: "image/tiff",
      suffix: ".tiff",
    }],
  });
  expect(metricsBefore.sessionJsonl.tiffMimeCount).toBeGreaterThanOrEqual(1);
  expect(metricsBefore.sessionJsonl.tiffDataUrlCount).toBeGreaterThanOrEqual(1);
  expect(metricsBefore.sessionJsonl.derivedPreviewFieldCount).toBe(0);
  const requestBoundary = h4.requestBoundary();

  await page.unroute(previewPattern, failPreview);
  previewPhase = "full-refresh";
  const preRefreshGeneration = mainDocumentGeneration;
  expectedReloadGeneration = preRefreshGeneration + 1;
  navigationStage = "reload-requested";
  await h4.reloadRuntime(runtime);
  expect(mainDocumentGeneration).toBe(expectedReloadGeneration);
  const restoredUser = page.locator("#messages article.msg.user").filter({ hasText: TIFF_IMAGE_USER });
  await expect(restoredUser).toHaveCount(1);
  const restoredPreview = restoredUser.locator("[data-message-image-preview]");
  await expectDecodedImage(restoredPreview);
  const fullRefreshPreviewRequests = previewRequestsFor("full-refresh", "GET");
  const disposedDocumentPreviewRequests = fullRefreshPreviewRequests.filter((request) => (
    request.documentGeneration === preRefreshGeneration
    && request.navigationStage === "reload-requested"
  ));
  const reloadDocumentPreviewRequests = fullRefreshPreviewRequests.filter((request) => (
    request.documentGeneration === expectedReloadGeneration
    && request.navigationStage === "reload-document"
  ));
  h4.diagnosticSteps.push({
    step: "tiff-full-refresh-preview-requests",
    preRefreshGeneration,
    expectedReloadGeneration,
    disposedDocumentGetCount: disposedDocumentPreviewRequests.length,
    reloadDocumentGetCount: reloadDocumentPreviewRequests.length,
    requests: fullRefreshPreviewRequests.map((request) => ({ ...request })),
  });
  expect(disposedDocumentPreviewRequests).toHaveLength(0);
  expect(reloadDocumentPreviewRequests).toHaveLength(1);
  expect(fullRefreshPreviewRequests).toHaveLength(1);
  expect(reloadDocumentPreviewRequests[0]).toMatchObject({
    keyHash: persistedPreviewKeyHash,
    documentGeneration: expectedReloadGeneration,
    navigationStage: "reload-document",
    frameScope: "main",
    initiator: "fetch",
    navigationRequest: false,
  });
  await expect(restoredUser.locator("[data-message-image-fallback]")).toBeHidden();

  const restoredUserHandle = await restoredUser.elementHandle();
  expect(restoredUserHandle).toBeTruthy();
  previewPhase = "post-refresh-rerender";
  const restoredLanguage = await page.locator("html").getAttribute("lang");
  expect(["en", "zh-CN"]).toContain(restoredLanguage);
  const originalLanguage = restoredLanguage === "zh-CN" ? "zh" : "en";
  const alternateLanguage = originalLanguage === "zh" ? "en" : "zh";
  await selectInterfaceLanguage(page, alternateLanguage);
  await expect.poll(() => restoredUserHandle.evaluate((node) => node.isConnected)).toBe(false);
  await restoredUserHandle.dispose();
  const rerenderedUser = page.locator("#messages article.msg.user").filter({ hasText: TIFF_IMAGE_USER });
  await expect(rerenderedUser).toHaveCount(1);
  const rerenderedPreview = rerenderedUser.locator("[data-message-image-preview]");
  await expectDecodedImage(rerenderedPreview);
  expect(previewRequestsFor("post-refresh-rerender", "GET")).toHaveLength(0);
  await selectInterfaceLanguage(page, originalLanguage);
  await expect(rerenderedUser).toHaveCount(1);
  await expectDecodedImage(rerenderedPreview);
  expect(previewRequestsFor("post-refresh-rerender", "GET")).toHaveLength(0);

  previewPhase = "overlay";
  await rerenderedPreview.click();
  const overlayImage = page.locator("#imageOverlay img");
  await expectDecodedImage(overlayImage);
  expect(previewRequestsFor("overlay", "GET")).toHaveLength(0);
  await page.locator("#imageOverlay").click();
  await expect(page.locator("#imageOverlay")).toHaveCount(0);

  const refreshRequests = h4.requestEvidenceSince(requestBoundary);
  expect(refreshRequests.agentPost).toBe(0);
  expect(refreshRequests.runtimePost).toBe(0);
  const metricsAfter = await h4.metrics();
  expect(metricsAfter.chatRequests).toEqual(metricsBefore.chatRequests);
  expect(metricsAfter.toolExecutions).toEqual([]);
  expect(metricsAfter.attachments).toEqual(metricsBefore.attachments);
  expect(await page.locator("#messages article.msg.user").filter({ hasText: TIFF_IMAGE_USER }).count()).toBe(1);
  expect(await page.locator("#messages article.msg.assistant").filter({ hasText: TIFF_IMAGE_FINAL }).count()).toBe(1);
  const previewRequestCounts = {
    composerSuccessPost: previewRequestsFor("composer-success", "POST").length,
    composerFailurePost: previewRequestsFor("composer-failure", "POST").length,
    messageInitialGet: previewRequestsFor("message-initial", "GET").length,
    modelRerenderGet: previewRequestsFor("model-rerender", "GET").length,
    fullRefreshGet: previewRequestsFor("full-refresh", "GET").length,
    postRefreshRerenderGet: previewRequestsFor("post-refresh-rerender", "GET").length,
    overlayGet: previewRequestsFor("overlay", "GET").length,
    total: previewRequests.length,
  };
  expect(previewRequestCounts).toEqual({
    composerSuccessPost: 1,
    composerFailurePost: 1,
    messageInitialGet: 1,
    modelRerenderGet: 0,
    fullRefreshGet: 1,
    postRefreshRerenderGet: 0,
    overlayGet: 0,
    total: 4,
  });
  page.off("request", recordPreviewRequest);
  page.off("framenavigated", recordMainFrameNavigation);

  h4.evidence(`${runtime}-tiff-derived-preview`, {
    runtime,
    originalSha256: TIFF_ATTACHMENT_SHA256,
    composerPreview: { width: 18, height: 12, mime: "image/png" },
    persisted: { mime: "image/tiff", attachmentFiles: 1, previewFields: 0 },
    modelProjectionRecognized: true,
    injectedPreviewFailures,
    previewRequestCounts,
    previewRequestIdentity: {
      persistedKeyHash: persistedPreviewKeyHash,
      initialDocumentGeneration: preRefreshGeneration,
      refreshDocumentGeneration: expectedReloadGeneration,
      disposedDocumentGetCount: 0,
      reloadDocumentGetCount: 1,
    },
    previewConversions: { succeeded: 2, interceptedFailures: 2 },
    refresh: { agentPost: 0, runtimePost: 0, chat: 0, tool: 0 },
  });
}

async function selectInterfaceLanguage(page, language) {
  await page.locator("#settingsMenuBtn").click();
  await expect(page.locator("#settingsPage")).not.toHaveClass(/hidden/);
  await page.locator(`[data-settings-lang="${language}"]`).click();
  await expect(page.locator("html")).toHaveAttribute("lang", language === "zh" ? "zh-CN" : "en");
  await page.locator("#closeSettingsPage").click();
  await expect(page.locator("#settingsPage")).toHaveClass(/hidden/);
}

async function completedTurnTimingDomEvidence(page, completedLabel = "用时") {
  const mainUser = page.locator("#messages article.msg.user").filter({ hasText: TIMING_MAIN_USER });
  const parallelUser = page.locator("#messages article.msg.user").filter({ hasText: TIMING_PARALLEL_USER });
  const queueUser = page.locator("#messages article.msg.user").filter({ hasText: TIMING_QUEUE_USER });
  const mainFinal = page.locator("#messages article.msg.assistant").filter({ hasText: TIMING_MAIN_FINAL });
  const parallelFinal = page.locator("#messages article.msg.assistant").filter({ hasText: TIMING_PARALLEL_FINAL });
  const queueFinal = page.locator("#messages article.msg.assistant").filter({ hasText: TIMING_QUEUE_FINAL });
  const mainHeader = mainUser.locator("xpath=following-sibling::*[1][@data-completed-run-status]");
  const parallelHeader = parallelUser.locator("xpath=following-sibling::*[1][@data-completed-run-status]");
  const queueHeader = queueUser.locator("xpath=following-sibling::*[1][@data-completed-run-status]");

  for (const locator of [mainUser, parallelUser, queueUser, mainFinal, parallelFinal, queueFinal]) {
    await expect(locator).toHaveCount(1);
  }
  await expect(page.locator("#messages [data-completed-run-status]")).toHaveCount(2);
  await expect(mainHeader).toHaveCount(1);
  await expect(queueHeader).toHaveCount(1);
  await expect(parallelHeader).toHaveCount(0);
  await expect(mainHeader.locator(".completed-run-label")).toHaveText(completedLabel);
  await expect(queueHeader.locator(".completed-run-label")).toHaveText(completedLabel);
  await expect(mainHeader.locator(".completed-run-timer")).toHaveText(/^\d+(?:s|m(?: \d+s)?|h(?: \d+m)?)$/);
  await expect(queueHeader.locator(".completed-run-timer")).toHaveText(/^\d+(?:s|m(?: \d+s)?|h(?: \d+m)?)$/);
  await expect(mainFinal.locator(".response-info .response-token")).toHaveCount(2);
  await expect(queueFinal.locator(".response-info .response-token")).toHaveCount(2);
  await expect(mainFinal.locator(".response-info .run-time")).toHaveCount(0);
  await expect(queueFinal.locator(".response-info .run-time")).toHaveCount(0);
  await expect(parallelFinal.locator(".response-info .run-time")).toHaveCount(1);
  await expect(page.locator("#messages article.msg.assistant .response-info .run-time")).toHaveCount(1);

  return {
    completedHeaders: 2,
    primaryFooterTimers: await mainFinal.locator(".response-info .run-time").count(),
    queuedFooterTimers: await queueFinal.locator(".response-info .run-time").count(),
    parallelFooterTimers: await parallelFinal.locator(".response-info .run-time").count(),
    primaryUsageTokens: await mainFinal.locator(".response-info .response-token").count(),
    queuedUsageTokens: await queueFinal.locator(".response-info .response-token").count(),
  };
}

async function waitForTimingQueueCheckpointConvergence(h4) {
  const { page } = h4;
  await expect.poll(() => {
    const controlIds = h4.controlIds();
    return {
      agentRunCount: controlIds.agentRunIds.length,
      runtimeRunCount: controlIds.runtimeRunIds.length,
    };
  }).toEqual({ agentRunCount: 1, runtimeRunCount: 1 });

  const controlIds = h4.controlIds();
  const agentRunId = controlIds.agentRunIds[0];
  const runtimeRunId = controlIds.runtimeRunIds[0];
  const sessionButton = page.locator("#sessionList .session-row.active button.session-main");
  await expect(sessionButton).toHaveCount(1);
  const sessionId = await sessionButton.getAttribute("data-session-id");
  expect(sessionId).toBeTruthy();

  let sessionProjection = null;
  await expect.poll(async () => {
    const response = await fetchProductionJson(
      page,
      `/api/sessions/${encodeURIComponent(sessionId)}`,
    );
    const runState = response.body?.runState || {};
    const messages = Array.isArray(response.body?.messages) ? response.body.messages : [];
    const queuedMessages = Array.isArray(runState.queuedMessages) ? runState.queuedMessages : [];
    sessionProjection = {
      status: response.status,
      runStatus: String(runState.status || ""),
      phase: String(runState.phase || ""),
      executionOwner: String(runState.executionOwner || ""),
      agentRunMatches: String(runState.agentRunId || "") === agentRunId,
      runtimeRunMatches: String(runState.runtimeRunId || "") === runtimeRunId,
      queueMarkerMessageCount: messages.filter((message) => {
        if (message?.role !== "user") return false;
        if (typeof message.content === "string") return message.content === TIMING_QUEUE_USER;
        if (!Array.isArray(message.content)) return false;
        return message.content.some((item) => item?.type === "text" && item.text === TIMING_QUEUE_USER);
      }).length,
      queuedCheckpointCount: queuedMessages.filter((item) => item?.userText === TIMING_QUEUE_USER).length,
    };
    return sessionProjection;
  }).toEqual({
    status: 200,
    runStatus: "running",
    phase: "model",
    executionOwner: "server-agent",
    agentRunMatches: true,
    runtimeRunMatches: true,
    queueMarkerMessageCount: 0,
    queuedCheckpointCount: 0,
  });

  const runtimeResponse = await fetchProductionJson(
    page,
    `/api/runtime/runs/${encodeURIComponent(runtimeRunId)}?cursor=0&wait=0`,
  );
  expect(runtimeResponse.status).toBe(200);
  expect(runtimeResponse.body).toMatchObject({ runId: runtimeRunId, status: "running" });
  const convergence = {
    agentRunIdHash: idHash(agentRunId),
    runtimeRunIdHash: idHash(runtimeRunId),
    session: { ...sessionProjection },
    runtime: {
      status: String(runtimeResponse.body.status || ""),
      nextCursor: Number(runtimeResponse.body.nextCursor || 0),
      eventCount: Array.isArray(runtimeResponse.body.events) ? runtimeResponse.body.events.length : 0,
    },
  };
  h4.diagnosticSteps.push({ step: "timing-queue-checkpoint-converged", state: convergence });
  return convergence;
}

async function submitTimingQueueWithCausalEvidence(h4) {
  const { page } = h4;
  const convergence = await waitForTimingQueueCheckpointConvergence(h4);
  const observationKey = "__h4TimingQueueSubmissionObservation";
  const sessionPutObservations = [];
  const onSessionPut = (request) => {
    if (request.method() !== "PUT") return;
    const requestUrl = new URL(request.url());
    if (!/^\/api\/sessions\/[^/]+$/.test(requestUrl.pathname)) return;

    let payload = null;
    try {
      payload = JSON.parse(request.postData() || "null");
    } catch (_) {
      payload = null;
    }
    const messages = Array.isArray(payload?.messages) ? payload.messages : [];
    const matchingMessages = messages.filter((message) => {
      if (message?.role !== "user") return false;
      if (typeof message.content === "string") return message.content === TIMING_QUEUE_USER;
      if (!Array.isArray(message.content)) return false;
      return message.content.some((item) => item?.type === "text" && item.text === TIMING_QUEUE_USER);
    });
    const queuedMessages = Array.isArray(payload?.runState?.queuedMessages)
      ? payload.runState.queuedMessages
      : [];
    const matchingCheckpoints = queuedMessages.filter((item) => item?.userText === TIMING_QUEUE_USER);
    const queuedDispatchCount = matchingMessages.filter((message) => (
      message?.meta?.queuedDispatch && typeof message.meta.queuedDispatch === "object"
    )).length;
    const queuedDispatchIds = matchingMessages
      .map((message) => String(message?.meta?.queuedDispatch?.id || ""))
      .filter(Boolean);
    const queuedCheckpointIds = matchingCheckpoints
      .map((item) => String(item?.id || ""))
      .filter(Boolean);
    const runState = payload?.runState || {};
    sessionPutObservations.push({
      sequence: sessionPutObservations.length + 1,
      stage: "queue-transition",
      method: "PUT",
      path: "/api/sessions/[id]",
      queueMarkerPresent: matchingMessages.length > 0 || matchingCheckpoints.length > 0,
      matchingMessageCount: matchingMessages.length,
      queuedDispatchCount,
      queuedCheckpointCount: matchingCheckpoints.length,
      queuedStatuses: matchingMessages
        .map((message) => String(message?.meta?.queuedDispatch?.status || ""))
        .filter(Boolean),
      queueIdentityMatches: queuedDispatchIds.length === 1
        && queuedCheckpointIds.length === 1
        && queuedDispatchIds[0] === queuedCheckpointIds[0],
      queueIdentityHash: queuedDispatchIds.length === 1 ? idHash(queuedDispatchIds[0]) : "",
      runState: {
        status: String(runState.status || ""),
        phase: String(runState.phase || ""),
        executionOwner: String(runState.executionOwner || ""),
        agentRunPresent: Boolean(String(runState.agentRunId || "")),
        runtimeRunPresent: Boolean(String(runState.runtimeRunId || "")),
        queuedMessageCount: Array.isArray(runState.queuedMessages) ? runState.queuedMessages.length : 0,
      },
    });
  };

  page.on("request", onSessionPut);
  try {
    await page.evaluate(({ key, expectedValue }) => {
      const previous = window[key];
      if (previous?.cleanup) previous.cleanup();
      const nodeIds = new WeakMap();
      let nextNodeId = 1;
      let nextSequence = 1;
      const timeline = [];
      const nodeId = (node) => {
        if (!node || (typeof node !== "object" && typeof node !== "function")) return "";
        if (!nodeIds.has(node)) nodeIds.set(node, `node-${nextNodeId++}`);
        return nodeIds.get(node);
      };
      const promptSnapshot = () => {
        const prompt = document.getElementById("prompt");
        const form = document.getElementById("chatForm");
        return {
          promptNodeId: nodeId(prompt),
          formNodeId: nodeId(form),
          promptConnected: Boolean(prompt?.isConnected),
          promptDisabled: Boolean(prompt?.disabled),
          activePrompt: document.activeElement === prompt,
          valueMatches: String(prompt?.value || "") === expectedValue,
        };
      };
      const onKeydown = (event) => {
        if (event.target?.id !== "prompt" || event.key !== "Enter") return;
        timeline.push({
          sequence: nextSequence++,
          type: "keydown",
          key: String(event.key || ""),
          ctrlKey: Boolean(event.ctrlKey),
          metaKey: Boolean(event.metaKey),
          shiftKey: Boolean(event.shiftKey),
          targetNodeId: nodeId(event.target),
          targetConnected: Boolean(event.target?.isConnected),
          targetDisabled: Boolean(event.target?.disabled),
          activePrompt: document.activeElement === event.target,
          valueMatches: String(event.target?.value || "") === expectedValue,
        });
      };
      const onSubmit = (event) => {
        if (event.target?.id !== "chatForm") return;
        const prompt = document.getElementById("prompt");
        timeline.push({
          sequence: nextSequence++,
          type: "submit",
          formNodeId: nodeId(event.target),
          formConnected: Boolean(event.target?.isConnected),
          promptNodeId: nodeId(prompt),
          promptConnected: Boolean(prompt?.isConnected),
          promptDisabled: Boolean(prompt?.disabled),
          activePrompt: document.activeElement === prompt,
          valueMatches: String(prompt?.value || "") === expectedValue,
        });
      };
      document.addEventListener("keydown", onKeydown, true);
      document.addEventListener("submit", onSubmit, true);
      window[key] = {
        timeline,
        promptSnapshot,
        cleanup() {
          document.removeEventListener("keydown", onKeydown, true);
          document.removeEventListener("submit", onSubmit, true);
        },
      };
    }, { key: observationKey, expectedValue: TIMING_QUEUE_USER });

    const prompt = page.locator("#prompt");
    await prompt.fill(TIMING_QUEUE_USER);
    await expect(prompt).toBeEnabled();
    await expect(prompt).toBeFocused();
    await expect(prompt).toHaveValue(TIMING_QUEUE_USER);
    const precondition = await page.evaluate((key) => window[key]?.promptSnapshot?.(), observationKey);
    expect(precondition).toEqual({
      promptNodeId: "node-1",
      formNodeId: "node-2",
      promptConnected: true,
      promptDisabled: false,
      activePrompt: true,
      valueMatches: true,
    });
    h4.diagnosticSteps.push({ step: "timing-queue-keyboard-precondition", state: precondition });

    await prompt.press("Control+Enter");
    const keyboardTimeline = await page.evaluate((key) => (
      Array.isArray(window[key]?.timeline) ? window[key].timeline.map((entry) => ({ ...entry })) : []
    ), observationKey);
    h4.diagnosticSteps.push({ step: "timing-queue-keyboard-events", timeline: keyboardTimeline });
    expect(keyboardTimeline).toEqual([
      {
        sequence: 1,
        type: "keydown",
        key: "Enter",
        ctrlKey: true,
        metaKey: false,
        shiftKey: false,
        targetNodeId: "node-1",
        targetConnected: true,
        targetDisabled: false,
        activePrompt: true,
        valueMatches: true,
      },
      {
        sequence: 2,
        type: "submit",
        formNodeId: "node-2",
        formConnected: true,
        promptNodeId: "node-1",
        promptConnected: true,
        promptDisabled: false,
        activePrompt: true,
        valueMatches: true,
      },
    ]);

    await expect.poll(() => sessionPutObservations.filter((entry) => entry.queueMarkerPresent)).toEqual([
      {
        sequence: expect.any(Number),
        stage: "queue-transition",
        method: "PUT",
        path: "/api/sessions/[id]",
        queueMarkerPresent: true,
        matchingMessageCount: 1,
        queuedDispatchCount: 1,
        queuedCheckpointCount: 1,
        queuedStatuses: ["pending"],
        queueIdentityMatches: true,
        queueIdentityHash: expect.stringMatching(/^[a-f0-9]{16}$/),
        runState: {
          status: "running",
          phase: "model",
          executionOwner: "server-agent",
          agentRunPresent: true,
          runtimeRunPresent: true,
          queuedMessageCount: 1,
        },
      },
    ]);
    const queueSave = sessionPutObservations.filter((entry) => entry.queueMarkerPresent)[0];
    h4.diagnosticSteps.push({
      step: "timing-queue-session-save",
      observation: { ...queueSave },
      observedSessionPuts: sessionPutObservations.map((entry) => ({ ...entry })),
    });

    const queuedUser = page.locator("#messages article.msg.user").filter({ hasText: TIMING_QUEUE_USER });
    await expect(queuedUser).toHaveCount(1);
    await expect(queuedUser).toHaveAttribute("data-queued-message-id", /.+/);
    h4.diagnosticSteps.push({ step: "timing-queue-dom-projected", count: 1 });

    return {
      checkpointConvergence: convergence,
      eventTypes: keyboardTimeline.map((entry) => entry.type),
      promptNodeStable: keyboardTimeline.every((entry) => (
        (entry.targetNodeId || entry.promptNodeId) === precondition.promptNodeId
      )),
      keydownCount: keyboardTimeline.filter((entry) => entry.type === "keydown").length,
      submitCount: keyboardTimeline.filter((entry) => entry.type === "submit").length,
      queueSaveCount: 1,
      queuedDispatchCount: queueSave.queuedDispatchCount,
      queuedCheckpointCount: queueSave.queuedCheckpointCount,
      queuedDomCount: 1,
    };
  } finally {
    const finalKeyboardTimeline = await page.evaluate((key) => (
      Array.isArray(window[key]?.timeline) ? window[key].timeline.map((entry) => ({ ...entry })) : []
    ), observationKey).catch(() => []);
    h4.diagnosticSteps.push({
      step: "timing-queue-causal-final",
      keyboardTimeline: finalKeyboardTimeline,
      sessionPuts: sessionPutObservations.map((entry) => ({ ...entry })),
    });
    await page.evaluate((key) => {
      const observation = window[key];
      if (observation?.cleanup) observation.cleanup();
      delete window[key];
    }, observationKey).catch(() => {});
    page.off("request", onSessionPut);
  }
}

async function completePrimaryTimingOwnershipLifecycle(h4, runtime) {
  const { page } = h4;
  await h4.open(runtime);
  await assertFrontendRuntime(page, runtime);
  if (runtime === "classic") {
    const currentUrl = new URL(page.url());
    expect(currentUrl.pathname).toBe(CLASSIC_FALLBACK_PATH);
    expect(currentUrl.search).toBe("");
    expect(await page.locator("html").getAttribute("data-code-frontend-ready")).toBeNull();
  }
  await selectInterfaceLanguage(page, "zh");

  await h4.submitGated(TIMING_MAIN_USER);
  await expect.poll(async () => (await h4.metrics()).chatRequests).toEqual([
    { scenario: "timing-main", stream: true, hasToolResult: false },
  ]);

  const queueSubmission = await submitTimingQueueWithCausalEvidence(h4);

  await page.locator("#prompt").fill(`/parallel ${TIMING_PARALLEL_USER}`);
  await page.locator("#sendBtn").click();
  const parallelFinal = page.locator("#messages article.msg.assistant").filter({ hasText: TIMING_PARALLEL_FINAL });
  await expect(parallelFinal).toHaveCount(1);
  await expect(parallelFinal.locator(".response-info .run-time")).toHaveCount(1);
  await expect(page.locator("#activeRunBanner.visible")).toHaveCount(1);

  await h4.host.releaseModel();
  await expect(page.locator("#messages article.msg.assistant").filter({ hasText: TIMING_MAIN_FINAL })).toHaveCount(1);
  await expect(page.locator("#messages article.msg.assistant").filter({ hasText: TIMING_QUEUE_FINAL })).toHaveCount(1);
  await expect(page.locator("#activeRunBanner.visible")).toHaveCount(0);
  await expect(page.locator("#stopBtn")).toBeDisabled();

  const beforeReloadDom = await completedTurnTimingDomEvidence(page);
  await selectInterfaceLanguage(page, "en");
  await expect(page.locator("#messages [data-completed-run-status] .completed-run-label")).toHaveText([
    "Worked for",
    "Worked for",
  ]);
  await expect(page.locator("#messages")).not.toContainText("用时");
  await selectInterfaceLanguage(page, "zh");
  await expect(page.locator("#messages [data-completed-run-status] .completed-run-label")).toHaveText([
    "用时",
    "用时",
  ]);

  const metricsBefore = await h4.metrics();
  expect(metricsBefore.chatRequests).toEqual([
    { scenario: "timing-main", stream: true, hasToolResult: false },
    { scenario: "timing-parallel", stream: true, hasToolResult: false },
    { scenario: "timing-queue", stream: true, hasToolResult: false },
  ]);
  expect(metricsBefore.toolExecutions).toEqual([]);
  expect(metricsBefore.unsafeToolRequests).toBe(0);
  const requestBoundary = h4.requestBoundary();

  await h4.reloadRuntime(runtime);
  if (runtime === "classic") {
    const restoredUrl = new URL(page.url());
    expect(restoredUrl.pathname).toBe(CLASSIC_FALLBACK_PATH);
    expect(restoredUrl.search).toBe("");
    expect(await page.locator("html").getAttribute("data-code-frontend-ready")).toBeNull();
  }
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  const afterReloadDom = await completedTurnTimingDomEvidence(page, "Worked for");
  expect(afterReloadDom).toEqual(beforeReloadDom);
  await selectInterfaceLanguage(page, "zh");
  expect(await completedTurnTimingDomEvidence(page)).toEqual(beforeReloadDom);

  const refreshRequests = h4.requestEvidenceSince(requestBoundary);
  const refreshSummary = h4.requestSummarySince(requestBoundary);
  expect(refreshRequests.agentPost).toBe(0);
  expect(refreshRequests.runtimePost).toBe(0);
  expect(refreshSummary["POST /proxy/chat"] || 0).toBe(0);
  expect(Object.entries(refreshSummary).filter(([key]) => key.startsWith("POST /api/tools/")).length).toBe(0);
  const metricsAfter = await h4.metrics();
  expect(metricsAfter.chatRequests).toEqual(metricsBefore.chatRequests);
  expect(metricsAfter.toolExecutions).toEqual([]);
  expect(h4.pageErrors).toEqual([]);

  h4.evidence(`${runtime}-primary-completed-timing-owner`, {
    runtime,
    dom: beforeReloadDom,
    language: { zh: "用时", en: "Worked for" },
    queueSubmission,
    chatScenarios: metricsBefore.chatRequests.map((request) => request.scenario),
    refresh: { agentPost: 0, runtimePost: 0, chatPost: 0, toolPost: 0 },
  });
}

function detachedParallelFailureSessionEvidence(
  messages,
  mainAgentRunId,
  backgroundAgentRunId,
  toolCallId,
  { includeFollowup = false } = {},
) {
  const source = Array.isArray(messages) ? messages : [];
  const roleContent = roleContentProjection(source);
  const expectedRoles = [
    "user",
    "assistant",
    "tool-call",
    "tool-result",
    "assistant",
    "user",
    "assistant",
  ];
  if (includeFollowup) expectedRoles.push("user", "assistant");
  expect(roleContent.map((message) => message.role)).toEqual(expectedRoles);
  expect(roleContent[0].content).toBe(TOOL_DETAILS_USER);
  expect(roleContent[1].content).toBe(TOOL_DETAILS_STAGE);
  expect(String(roleContent[2].content || "")).toContain("read_file");
  expect(String(roleContent[2].content || "")).toContain("fixture.txt");
  expect(countOccurrences(String(roleContent[2].content || ""), "fixture.txt")).toBe(1);
  expect(String(roleContent[3].content || "")).toContain("fixture.txt");
  expect(String(roleContent[3].content || "")).toContain("26 B");
  expect(String(roleContent[3].content || "")).toContain(FIXTURE_CONTENT.trim());
  expect(countOccurrences(
    String(roleContent[3].content || ""),
    FIXTURE_CONTENT.trim(),
  )).toBe(1);
  expect(roleContent[4].content).toBe(TOOL_DETAILS_FINAL);
  expect(roleContent[5].content).toBe(PARALLEL_FAILURE_USER);
  expect(roleContent[6].content).toBe(PARALLEL_FAILURE_ERROR);
  if (includeFollowup) {
    expect(roleContent[7].content).toBe(PARALLEL_FAILURE_FOLLOWUP_USER);
    expect(roleContent[8].content).toBe(PARALLEL_FAILURE_FOLLOWUP_FINAL);
  }

  const backgroundUser = source.find((message) => (
    message?.role === "user"
    && message?.content === PARALLEL_FAILURE_USER
    && message?.meta?.backgroundDispatch?.id
  ));
  const backgroundAssistant = source.find((message) => (
    message?.role === "assistant"
    && message?.content === PARALLEL_FAILURE_ERROR
    && message?.meta?.kind === "background-subagent"
  ));
  expect(backgroundUser).toBeTruthy();
  expect(backgroundAssistant).toBeTruthy();
  const jobId = String(backgroundUser.meta.backgroundDispatch.id || "");
  expect(jobId).not.toBe("");
  expect(backgroundUser.meta).toMatchObject({
    detachedFromMain: true,
    backgroundDispatch: {
      id: jobId,
      status: "failed",
      agentRunId: backgroundAgentRunId,
    },
  });
  expect(String(backgroundUser.meta.backgroundDispatch.detail || "")).toContain(
    PARALLEL_FAILURE_ERROR,
  );
  expect(Number(backgroundUser.meta.backgroundDispatch.parentTaskStartedAt || 0)).toBeGreaterThan(0);
  expect(backgroundAssistant.meta).toMatchObject({
    kind: "background-subagent",
    jobId,
    agentRunId: backgroundAgentRunId,
    error: true,
    detachedFromMain: true,
  });
  expect(Number(backgroundAssistant.meta.parentTaskStartedAt || 0)).toBeGreaterThan(0);
  expect(String(backgroundAssistant.meta._responseTime || "")).toMatch(/^\d+(?:s|m(?: \d+s)?|h(?: \d+m)?)$/);

  const mainToolMeta = sessionToolMetaProjection(source, mainAgentRunId, toolCallId);
  expect(mainToolMeta).toHaveLength(2);
  expect(mainToolMeta.map((message) => message.role)).toEqual(["tool-call", "tool-result"]);
  expect(mainToolMeta.every((message) => message.toolCallId === "tool-1")).toBe(true);
  expect(mainToolMeta.at(-1)?.result).toEqual({
    ok: true,
    action: "read_file",
    path: "fixture.txt",
    content: FIXTURE_CONTENT,
    size: 26,
    truncated: false,
    lineRange: null,
  });

  return {
    roleContent,
    jobId,
    mainToolMeta,
    backgroundMeta: {
      user: {
        detachedFromMain: backgroundUser.meta.detachedFromMain === true,
        status: String(backgroundUser.meta.backgroundDispatch.status || ""),
        jobIdLinked: String(backgroundUser.meta.backgroundDispatch.id || "") === jobId,
        agentRunLinked: String(backgroundUser.meta.backgroundDispatch.agentRunId || "")
          === backgroundAgentRunId,
        detailContainsFailure: String(backgroundUser.meta.backgroundDispatch.detail || "")
          .includes(PARALLEL_FAILURE_ERROR),
        parentTaskStartedAtPresent: Number(
          backgroundUser.meta.backgroundDispatch.parentTaskStartedAt || 0,
        ) > 0,
      },
      assistant: {
        kind: String(backgroundAssistant.meta.kind || ""),
        detachedFromMain: backgroundAssistant.meta.detachedFromMain === true,
        error: backgroundAssistant.meta.error === true,
        jobIdLinked: String(backgroundAssistant.meta.jobId || "") === jobId,
        agentRunLinked: String(backgroundAssistant.meta.agentRunId || "")
          === backgroundAgentRunId,
        responseTimePresent: Boolean(String(backgroundAssistant.meta._responseTime || "")),
        parentTaskStartedAtPresent: Number(backgroundAssistant.meta.parentTaskStartedAt || 0) > 0,
      },
      mainToolMeta,
    },
  };
}

function detachedParallelSessionSettlementProjection(response, { includeFollowup = false } = {}) {
  const roleContent = roleContentProjection(response?.body?.messages);
  const findIndex = (role, marker) => roleContent.findIndex((message) => (
    message.role === role && message.content === marker
  ));
  return {
    status: Number(response?.status || 0),
    messageCount: roleContent.length,
    roles: roleContent.map((message) => message.role),
    markerIndexes: {
      mainFinal: findIndex("assistant", TOOL_DETAILS_FINAL),
      detachedUser: findIndex("user", PARALLEL_FAILURE_USER),
      detachedError: findIndex("assistant", PARALLEL_FAILURE_ERROR),
      followupUser: findIndex("user", PARALLEL_FAILURE_FOLLOWUP_USER),
      followupFinal: findIndex("assistant", PARALLEL_FAILURE_FOLLOWUP_FINAL),
    },
    runStateKeys: Object.keys(response?.body?.runState || {}).sort(),
    includeFollowup,
  };
}

function primaryDetachedPreSubmissionProjectionExpected() {
  return {
    counts: {
      mainUser: 1,
      activeAnchor: 1,
      mainStage: 1,
      mainFinal: 0,
      toolProcesses: 1,
      toolItems: 1,
      toolDetails: 2,
      detachedUser: 0,
      detachedAssistant: 0,
      completedStatuses: 0,
      visiblePending: 0,
      activeBanners: 1,
      activeTraces: 0,
    },
    order: ["mainUser", "activeAnchor", "mainStage", "toolProcess"],
    tool: {
      processKey: "0:1",
      outerOpen: true,
      itemOpen: false,
      stageRunning: true,
      itemSucceeded: true,
      pathVisible: true,
      sizeVisible: true,
      fixtureContentCount: 1,
    },
    anchor: {
      ownsVisibleBanner: true,
      immediatelyAfterMainUser: true,
      insideActiveTrace: false,
    },
    stopEnabled: true,
  };
}

function samplePrimaryDetachedPreSubmissionProjection(sourceFacts) {
  const root = document.querySelector("#messages");
  const markerMatches = (selector, marker) => [...root.querySelectorAll(selector)]
    .filter((element) => (element.textContent || "").includes(marker));
  const mainUsers = markerMatches("article.msg.user", sourceFacts.mainUser);
  const mainStages = markerMatches(
    "article.msg.assistant.agent-commentary",
    sourceFacts.mainStage,
  );
  const mainUser = mainUsers[0] || null;
  const mainStage = mainStages[0] || null;
  const mainFinals = markerMatches("article.msg.assistant", sourceFacts.mainFinal);
  const detachedUsers = markerMatches("article.msg.user", sourceFacts.detachedUser);
  const detachedAssistants = markerMatches("article.msg.assistant", sourceFacts.detachedError);
  const activeAnchors = [...root.querySelectorAll("[data-active-run-anchor]")];
  const toolProcesses = [...root.querySelectorAll("article.tool-process")];
  const toolItems = [...root.querySelectorAll("article.tool-process details.tool-process-item")];
  const toolProcess = toolProcesses[0] || null;
  const toolOuter = toolProcess?.querySelector(":scope > details.tool-process-stage") || null;
  const toolItem = toolItems[0] || null;
  const toolText = toolProcess?.textContent || "";
  const orderedNodes = [
    { label: "mainUser", node: mainUser },
    { label: "activeAnchor", node: activeAnchors[0] || null },
    { label: "mainStage", node: mainStage },
    { label: "toolProcess", node: toolProcess },
  ].filter((entry) => entry.node);
  orderedNodes.sort((left, right) => (
    left.node.compareDocumentPosition(right.node) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1
  ));
  return {
    counts: {
      mainUser: mainUsers.length,
      activeAnchor: activeAnchors.length,
      mainStage: mainStages.length,
      mainFinal: mainFinals.length,
      toolProcesses: toolProcesses.length,
      toolItems: toolItems.length,
      toolDetails: root.querySelectorAll("article.tool-process .tool-process-detail pre").length,
      detachedUser: detachedUsers.length,
      detachedAssistant: detachedAssistants.length,
      completedStatuses: root.querySelectorAll("[data-completed-run-status]").length,
      visiblePending: root.querySelectorAll(
        'article.msg.assistant.is-streaming.is-pending[data-stream-kind="pending"]',
      ).length,
      activeBanners: document.querySelectorAll("#activeRunBanner.visible").length,
      activeTraces: root.querySelectorAll("section.execution-trace.active").length,
    },
    order: orderedNodes.map((entry) => entry.label),
    tool: {
      processKey: String(toolOuter?.getAttribute("data-tool-process-key") || ""),
      outerOpen: Boolean(toolOuter?.open),
      itemOpen: Boolean(toolItem?.open),
      stageRunning: Boolean(toolOuter?.classList.contains("running")),
      itemSucceeded: Boolean(toolItem?.classList.contains("succeeded")),
      pathVisible: toolText.includes("fixture.txt"),
      sizeVisible: toolText.includes("26 B"),
      fixtureContentCount: sourceFacts.fixtureContent
        ? toolText.split(sourceFacts.fixtureContent).length - 1
        : 0,
    },
    anchor: {
      ownsVisibleBanner: Boolean(
        activeAnchors[0]
        && document.querySelector("#activeRunBanner.visible")?.parentElement === activeAnchors[0]
      ),
      immediatelyAfterMainUser: mainUser?.nextElementSibling === activeAnchors[0],
      insideActiveTrace: Boolean(activeAnchors[0]?.closest("section.execution-trace.active")),
    },
    stopEnabled: !document.querySelector("#stopBtn")?.disabled,
  };
}

function detachedParallelFailureProjectionExpected({
  finalVisible = false,
  terminal = false,
  tracePlacement = "",
} = {}) {
  const expectedTracePlacement = tracePlacement || "outside";
  const counts = {
    mainUser: 1,
    mainStage: 1,
    mainFinal: finalVisible ? 1 : 0,
    visiblePending: 0,
    backgroundUser: 1,
    backgroundAssistant: 1,
    toolProcesses: 1,
    toolItems: 1,
    toolDetails: 2,
    completedStatuses: terminal ? 1 : 0,
    backgroundFooterTimers: 1,
    backgroundReferences: 1,
    assistantFooterTimers: 1,
  };
  if (terminal) {
    counts.primaryFooterTimers = 0;
    counts.primaryFooterTokens = 2;
  }
  const order = ["mainUser", "mainStage", "toolProcess"];
  if (finalVisible) order.push("mainFinal");
  order.push("backgroundUser", "backgroundAssistant");
  const expected = {
    counts,
    order,
    tool: {
      processKey: "0:1",
      outerOpen: !terminal,
      itemOpen: false,
      stageSucceeded: true,
      containsBackgroundUser: false,
      containsBackgroundError: false,
    },
    ownership: {
      backgroundUserRole: true,
      backgroundAssistantRole: true,
      visiblePendingHidden: true,
      backgroundInsideToolProcess: false,
      backgroundOwnsCompletedStatus: false,
    },
  };
  if (expectedTracePlacement !== "transitional") {
    const persistent = expectedTracePlacement === "persistent";
    expected.trace = {
      userPersistent: persistent,
      assistantPersistent: persistent,
      userTraceAncestors: persistent ? 1 : 0,
      assistantTraceAncestors: persistent ? 1 : 0,
    };
  }
  return expected;
}

function sampleDetachedParallelFailureProjection(sourceFacts) {
  const root = document.querySelector("#messages");
  const markerMatches = (selector, marker) => [...root.querySelectorAll(selector)]
    .filter((element) => (element.textContent || "").includes(marker));
  const mainUsers = markerMatches("article.msg.user", sourceFacts.mainUser);
  const mainStages = markerMatches(
    "article.msg.assistant.agent-commentary",
    sourceFacts.mainStage,
  );
  const mainFinals = markerMatches("article.msg.assistant", sourceFacts.mainFinal);
  const mainPendings = [...root.querySelectorAll(
    'article.msg.assistant.is-streaming.is-pending[data-stream-kind="pending"]',
  )];
  const backgroundUsers = markerMatches("article.msg.user", sourceFacts.backgroundUser);
  const backgroundAssistants = markerMatches(
    "article.msg.assistant",
    sourceFacts.backgroundError,
  );
  const toolProcesses = [...root.querySelectorAll("article.tool-process")];
  const toolItems = [...root.querySelectorAll(
    "article.tool-process details.tool-process-item",
  )];
  const mainFinal = mainFinals[0] || null;
  const backgroundUser = backgroundUsers[0] || null;
  const backgroundAssistant = backgroundAssistants[0] || null;
  const toolProcess = toolProcesses[0] || null;
  const toolItem = toolItems[0] || null;
  const ancestorCount = (element, className) => {
    let count = 0;
    for (let parent = element?.parentElement; parent; parent = parent.parentElement) {
      if (parent.classList.contains(className)) count += 1;
    }
    return count;
  };
  const orderedNodes = [
    { label: "mainUser", node: mainUsers[0] || null },
    { label: "mainStage", node: mainStages[0] || null },
    { label: "toolProcess", node: toolProcess },
    { label: "mainFinal", node: mainFinal },
    { label: "backgroundUser", node: backgroundUser },
    { label: "backgroundAssistant", node: backgroundAssistant },
  ].filter((entry) => entry.node);
  orderedNodes.sort((left, right) => {
    if (left.node === right.node) return 0;
    return left.node.compareDocumentPosition(right.node) & Node.DOCUMENT_POSITION_FOLLOWING
      ? -1
      : 1;
  });
  const counts = {
    mainUser: mainUsers.length,
    mainStage: mainStages.length,
    mainFinal: mainFinals.length,
    visiblePending: mainPendings.length,
    backgroundUser: backgroundUsers.length,
    backgroundAssistant: backgroundAssistants.length,
    toolProcesses: toolProcesses.length,
    toolItems: toolItems.length,
    toolDetails: root.querySelectorAll("article.tool-process .tool-process-detail pre").length,
    completedStatuses: root.querySelectorAll("[data-completed-run-status]").length,
    backgroundFooterTimers: backgroundAssistant
      ? backgroundAssistant.querySelectorAll(".response-info .run-time").length
      : 0,
    backgroundReferences: backgroundAssistant
      ? backgroundAssistant.querySelectorAll("[data-background-reply-id]").length
      : 0,
    assistantFooterTimers: root.querySelectorAll(
      "article.msg.assistant .response-info .run-time",
    ).length,
  };
  if (sourceFacts.terminal) {
    counts.primaryFooterTimers = mainFinal
      ? mainFinal.querySelectorAll(".response-info .run-time").length
      : 0;
    counts.primaryFooterTokens = mainFinal
      ? mainFinal.querySelectorAll(".response-info .response-token").length
      : 0;
  }
  const toolOuter = toolProcess?.querySelector(":scope > details.tool-process-stage") || null;
  const projection = {
    counts,
    order: orderedNodes.map((entry) => entry.label),
    tool: {
      processKey: String(toolOuter?.getAttribute("data-tool-process-key") || ""),
      outerOpen: Boolean(toolOuter?.open),
      itemOpen: Boolean(toolItem?.open),
      stageSucceeded: Boolean(toolOuter?.classList.contains("succeeded")),
      containsBackgroundUser: Boolean(
        toolProcess && (toolProcess.textContent || "").includes(sourceFacts.backgroundUser),
      ),
      containsBackgroundError: Boolean(
        toolProcess && (toolProcess.textContent || "").includes(sourceFacts.backgroundError),
      ),
    },
    ownership: {
      backgroundUserRole: Boolean(backgroundUser?.matches("article.msg.user")),
      backgroundAssistantRole: Boolean(backgroundAssistant?.matches("article.msg.assistant")),
      visiblePendingHidden: mainPendings.length === 0,
      backgroundInsideToolProcess: Boolean(
        ancestorCount(backgroundUser, "tool-process")
        || ancestorCount(backgroundAssistant, "tool-process"),
      ),
      backgroundOwnsCompletedStatus: Boolean(
        backgroundUser?.nextElementSibling?.hasAttribute("data-completed-run-status"),
      ),
    },
  };
  if (sourceFacts.tracePlacement !== "transitional") {
    projection.trace = {
      userPersistent: Boolean(backgroundUser?.classList.contains("execution-trace-persistent")),
      assistantPersistent: Boolean(
        backgroundAssistant?.classList.contains("execution-trace-persistent"),
      ),
      userTraceAncestors: ancestorCount(backgroundUser, "execution-trace"),
      assistantTraceAncestors: ancestorCount(backgroundAssistant, "execution-trace"),
    };
  }
  return projection;
}

function followupIsolationProjectionExpected() {
  return {
    counts: {
      mainUser: 1,
      mainStage: 1,
      mainFinal: 1,
      detachedUser: 1,
      detachedAssistant: 1,
      followupUser: 1,
      followupFinal: 1,
      toolProcesses: 1,
      toolItems: 1,
      toolDetails: 2,
      completedStatuses: 2,
      visiblePending: 0,
      streamingAssistants: 0,
      activeTraces: 0,
      activeBanners: 0,
      mainFooterTimers: 0,
      followupFooterTimers: 0,
      detachedFooterTimers: 1,
      assistantFooterTimers: 1,
      mainFooterTokens: 2,
      followupFooterTokens: 2,
      detachedReferences: 1,
    },
    order: [
      "mainUser",
      "mainStage",
      "toolProcess",
      "mainFinal",
      "detachedUser",
      "detachedAssistant",
      "followupUser",
      "followupFinal",
    ],
    tool: {
      processKey: "0:1",
      outerOpen: false,
      itemOpen: false,
      stageSucceeded: true,
      pathVisible: true,
      sizeVisible: true,
      fixtureContentCount: 1,
    },
    ownership: {
      detachedUserPersistent: false,
      detachedAssistantPersistent: false,
      detachedUserTraceAncestors: 0,
      detachedAssistantTraceAncestors: 0,
      detachedInsideToolProcess: false,
      detachedOwnsCompletedStatus: false,
      followupInsideTrace: false,
      mainOwnsCompletedStatus: true,
      followupOwnsCompletedStatus: true,
      foregroundErrorCount: 0,
    },
    stopDisabled: true,
  };
}

function sampleFollowupIsolationProjection(sourceFacts) {
  const root = document.querySelector("#messages");
  const markerMatches = (selector, marker) => [...root.querySelectorAll(selector)]
    .filter((element) => (element.textContent || "").includes(marker));
  const one = (selector, marker) => markerMatches(selector, marker)[0] || null;
  const mainUser = one("article.msg.user", sourceFacts.mainUser);
  const mainStage = one("article.msg.assistant.agent-commentary", sourceFacts.mainStage);
  const mainFinal = one("article.msg.assistant", sourceFacts.mainFinal);
  const detachedUser = one("article.msg.user", sourceFacts.detachedUser);
  const detachedAssistant = one("article.msg.assistant", sourceFacts.detachedError);
  const followupUser = one("article.msg.user", sourceFacts.followupUser);
  const followupFinal = one("article.msg.assistant", sourceFacts.followupFinal);
  const toolProcesses = [...root.querySelectorAll("article.tool-process")];
  const toolItems = [...root.querySelectorAll("article.tool-process details.tool-process-item")];
  const toolProcess = toolProcesses[0] || null;
  const toolOuter = toolProcess?.querySelector(":scope > details.tool-process-stage") || null;
  const toolItem = toolItems[0] || null;
  const toolText = toolProcess?.textContent || "";
  const ancestorCount = (element, className) => {
    let count = 0;
    for (let parent = element?.parentElement; parent; parent = parent.parentElement) {
      if (parent.classList.contains(className)) count += 1;
    }
    return count;
  };
  const orderedNodes = [
    { label: "mainUser", node: mainUser },
    { label: "mainStage", node: mainStage },
    { label: "toolProcess", node: toolProcess },
    { label: "mainFinal", node: mainFinal },
    { label: "detachedUser", node: detachedUser },
    { label: "detachedAssistant", node: detachedAssistant },
    { label: "followupUser", node: followupUser },
    { label: "followupFinal", node: followupFinal },
  ].filter((entry) => entry.node);
  orderedNodes.sort((left, right) => (
    left.node.compareDocumentPosition(right.node) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1
  ));
  const mainUsers = markerMatches("article.msg.user", sourceFacts.mainUser);
  const mainStages = markerMatches(
    "article.msg.assistant.agent-commentary",
    sourceFacts.mainStage,
  );
  const mainFinals = markerMatches("article.msg.assistant", sourceFacts.mainFinal);
  const detachedUsers = markerMatches("article.msg.user", sourceFacts.detachedUser);
  const detachedAssistants = markerMatches("article.msg.assistant", sourceFacts.detachedError);
  const followupUsers = markerMatches("article.msg.user", sourceFacts.followupUser);
  const followupFinals = markerMatches("article.msg.assistant", sourceFacts.followupFinal);
  return {
    counts: {
      mainUser: mainUsers.length,
      mainStage: mainStages.length,
      mainFinal: mainFinals.length,
      detachedUser: detachedUsers.length,
      detachedAssistant: detachedAssistants.length,
      followupUser: followupUsers.length,
      followupFinal: followupFinals.length,
      toolProcesses: toolProcesses.length,
      toolItems: toolItems.length,
      toolDetails: root.querySelectorAll("article.tool-process .tool-process-detail pre").length,
      completedStatuses: root.querySelectorAll("[data-completed-run-status]").length,
      visiblePending: root.querySelectorAll(
        'article.msg.assistant.is-streaming.is-pending[data-stream-kind="pending"]',
      ).length,
      streamingAssistants: root.querySelectorAll("article.msg.assistant.is-streaming").length,
      activeTraces: root.querySelectorAll(".execution-trace.active").length,
      activeBanners: document.querySelectorAll("#activeRunBanner.visible").length,
      mainFooterTimers: mainFinal?.querySelectorAll(".response-info .run-time").length || 0,
      followupFooterTimers: followupFinal?.querySelectorAll(".response-info .run-time").length || 0,
      detachedFooterTimers: detachedAssistant
        ?.querySelectorAll(".response-info .run-time").length || 0,
      assistantFooterTimers: root.querySelectorAll(
        "article.msg.assistant .response-info .run-time",
      ).length,
      mainFooterTokens: mainFinal?.querySelectorAll(".response-info .response-token").length || 0,
      followupFooterTokens: followupFinal
        ?.querySelectorAll(".response-info .response-token").length || 0,
      detachedReferences: detachedAssistant
        ?.querySelectorAll("[data-background-reply-id]").length || 0,
    },
    order: orderedNodes.map((entry) => entry.label),
    tool: {
      processKey: String(toolOuter?.getAttribute("data-tool-process-key") || ""),
      outerOpen: Boolean(toolOuter?.open),
      itemOpen: Boolean(toolItem?.open),
      stageSucceeded: Boolean(toolOuter?.classList.contains("succeeded")),
      pathVisible: toolText.includes("fixture.txt"),
      sizeVisible: toolText.includes("26 B"),
      fixtureContentCount: sourceFacts.fixtureContent
        ? toolText.split(sourceFacts.fixtureContent).length - 1
        : 0,
    },
    ownership: {
      detachedUserPersistent: Boolean(
        detachedUser?.classList.contains("execution-trace-persistent"),
      ),
      detachedAssistantPersistent: Boolean(
        detachedAssistant?.classList.contains("execution-trace-persistent"),
      ),
      detachedUserTraceAncestors: ancestorCount(detachedUser, "execution-trace"),
      detachedAssistantTraceAncestors: ancestorCount(detachedAssistant, "execution-trace"),
      detachedInsideToolProcess: Boolean(
        ancestorCount(detachedUser, "tool-process")
        || ancestorCount(detachedAssistant, "tool-process"),
      ),
      detachedOwnsCompletedStatus: Boolean(
        detachedUser?.nextElementSibling?.hasAttribute("data-completed-run-status"),
      ),
      followupInsideTrace: Boolean(
        ancestorCount(followupUser, "execution-trace")
        || ancestorCount(followupFinal, "execution-trace"),
      ),
      mainOwnsCompletedStatus: Boolean(
        mainUser?.nextElementSibling?.matches("section.execution-trace.completed")
        && mainUser.nextElementSibling.querySelectorAll(
          ":scope > .execution-trace-summary [data-completed-run-status]",
        ).length === 1
      ),
      followupOwnsCompletedStatus: Boolean(
        followupUser?.nextElementSibling?.hasAttribute("data-completed-run-status"),
      ),
      foregroundErrorCount: [mainFinal, followupFinal].filter((element) => (
        element?.classList.contains("error") || element?.getAttribute("data-error") === "true"
      )).length,
    },
    stopDisabled: Boolean(document.querySelector("#stopBtn")?.disabled),
  };
}

async function detachedParallelFailureDomEvidence(
  h4,
  { finalVisible = false, terminal = false, tracePlacement = "" } = {},
) {
  const { page } = h4;
  const expectedTracePlacement = tracePlacement || "outside";
  const sourceFacts = {
    mainUser: TOOL_DETAILS_USER,
    mainStage: TOOL_DETAILS_STAGE,
    backgroundUser: PARALLEL_FAILURE_USER,
    backgroundError: PARALLEL_FAILURE_ERROR,
    mainFinal: TOOL_DETAILS_FINAL,
    finalVisible,
    terminal,
    tracePlacement: expectedTracePlacement,
  };
  const semanticProjection = await waitForMessageProjection(h4, {
    label: `H4-7C-${terminal ? "terminal" : finalVisible ? "preterminal" : "active"}`,
    sample: sampleDetachedParallelFailureProjection,
    expected: detachedParallelFailureProjectionExpected({
      finalVisible,
      terminal,
      tracePlacement: expectedTracePlacement,
    }),
    sourceFacts,
  });
  const messages = page.locator("#messages");
  const mainUser = messages.locator("article.msg.user").filter({ hasText: TOOL_DETAILS_USER });
  const mainStage = messages.locator("article.msg.assistant.agent-commentary")
    .filter({ hasText: TOOL_DETAILS_STAGE });
  const mainFinal = messages.locator("article.msg.assistant").filter({ hasText: TOOL_DETAILS_FINAL });
  const backgroundUser = messages.locator("article.msg.user").filter({ hasText: PARALLEL_FAILURE_USER });
  const backgroundAssistant = messages.locator("article.msg.assistant")
    .filter({ hasText: PARALLEL_FAILURE_ERROR });
  const toolDom = await toolDetailLifecycleDomEvidence(page);

  for (const locator of [mainUser, mainStage, backgroundUser, backgroundAssistant]) {
    await expect(locator).toHaveCount(1);
  }
  await expect(mainFinal).toHaveCount(finalVisible ? 1 : 0);
  await expect(messages.locator("article.tool-process")).toHaveCount(1);
  await expect(messages.locator("article.tool-process details.tool-process-item")).toHaveCount(1);
  await expect(messages.locator("article.tool-process .tool-process-detail pre")).toHaveCount(2);
  await expect(toolDom.process).not.toContainText(PARALLEL_FAILURE_USER);
  await expect(toolDom.process).not.toContainText(PARALLEL_FAILURE_ERROR);
  if (expectedTracePlacement === "persistent") {
    await expect(backgroundUser).toHaveClass(/\bexecution-trace-persistent\b/);
    await expect(backgroundAssistant).toHaveClass(/\bexecution-trace-persistent\b/);
    await expect(backgroundUser.locator(
      "xpath=ancestor::*[contains(concat(' ',normalize-space(@class),' '),' execution-trace ')]",
    ))
      .toHaveCount(1);
    await expect(backgroundAssistant.locator(
      "xpath=ancestor::*[contains(concat(' ',normalize-space(@class),' '),' execution-trace ')]",
    ))
      .toHaveCount(1);
  } else if (expectedTracePlacement === "outside") {
    await expect(backgroundUser).not.toHaveClass(/\bexecution-trace-persistent\b/);
    await expect(backgroundAssistant).not.toHaveClass(/\bexecution-trace-persistent\b/);
    await expect(backgroundUser.locator(
      "xpath=ancestor::*[contains(concat(' ',normalize-space(@class),' '),' execution-trace ')]",
    ))
      .toHaveCount(0);
    await expect(backgroundAssistant.locator(
      "xpath=ancestor::*[contains(concat(' ',normalize-space(@class),' '),' execution-trace ')]",
    ))
      .toHaveCount(0);
  }
  await expect(backgroundAssistant.locator("[data-background-reply-id]")).toHaveCount(1);
  await expect(backgroundAssistant.locator(".response-info .run-time")).toHaveCount(1);
  await expect(backgroundUser.locator("xpath=following-sibling::*[1][@data-completed-run-status]"))
    .toHaveCount(0);
  await expect(messages.locator("[data-completed-run-status]")).toHaveCount(terminal ? 1 : 0);
  if (terminal) {
    await expect(mainFinal.locator(".response-info .run-time")).toHaveCount(0);
    await expect(mainFinal.locator(".response-info .response-token")).toHaveCount(2);
  }
  await expect(messages.locator("article.msg.assistant .response-info .run-time")).toHaveCount(1);

  return {
    toolDom,
    backgroundUser,
    backgroundAssistant,
    mainFinal,
    semanticProjection,
  };
}

async function exerciseDetachedParallelFailureIsolation(h4, runtime) {
  const { page } = h4;
  await h4.open(runtime);
  await assertFrontendRuntime(page, runtime);
  if (runtime === "classic") {
    const currentUrl = new URL(page.url());
    expect(currentUrl.pathname).toBe(CLASSIC_FALLBACK_PATH);
    expect(currentUrl.search).toBe("");
    expect(await page.locator("html").getAttribute("data-code-frontend-ready")).toBeNull();
  }
  const requestBoundary = h4.requestBoundary();
  await h4.submitGated(TOOL_DETAILS_USER);
  await h4.waitGate(TOOL_FINAL_DELTA_GATE);

  const initialToolDom = await toolDetailLifecycleDomEvidence(page);
  expect(initialToolDom.projection).toMatchObject({
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
    processKey: "0:1",
    outerOpen: false,
    itemOpen: false,
    ordered: true,
  });
  await initialToolDom.outer.locator(":scope > summary.tool-process-stage-summary").click();
  await expect(initialToolDom.outer).toHaveAttribute("open", "");
  const processKey = String(await initialToolDom.outer.getAttribute("data-tool-process-key") || "");
  expect(processKey).toBe("0:1");

  await expect.poll(() => h4.controlIds().agentRunIds.length).toBe(1);
  const mainAgentRunId = h4.controlIds().agentRunIds[0];
  const activeMainAgent = await fetchProductionJson(
    page,
    `/api/agent/runs/${encodeURIComponent(mainAgentRunId)}?cursor=0&wait=0`,
  );
  expect(activeMainAgent.status).toBe(200);
  expect(activeMainAgent.body).toMatchObject({
    agentRunId: mainAgentRunId,
    status: "model",
    nextCursor: 7,
  });
  expect(activeMainAgent.body.pendingToolCalls).toEqual([]);
  const activeMainTrace = durableToolTraceEvidence(activeMainAgent.body);
  expect(activeMainTrace.eventProjection.map((event) => event.type)).toEqual([
    "created",
    "model_started",
    "model_completed",
    "tool_started",
    "tool_completed",
    "model_pending",
    "model_started",
  ]);
  expect(activeMainTrace.toolCallIds).toHaveLength(1);
  const toolCallId = activeMainTrace.toolCallIds[0];
  expect(activeMainTrace.executionProjection).toEqual([{
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
  const mainRuntimeRunIds = activeMainAgent.body.events
    .filter((event) => event?.type === "model_started")
    .map((event) => String(event?.data?.runtimeRunId || ""));
  expect(mainRuntimeRunIds).toHaveLength(2);
  expect(mainRuntimeRunIds.every(Boolean)).toBe(true);
  expect(activeMainAgent.body.activeRuntimeRunId).toBe(mainRuntimeRunIds[1]);
  const mainRuntimeConsumer = await waitForFrontendRuntimeConsumer(h4, {
    runtimeRunId: mainRuntimeRunIds[1],
    requestBoundary,
    label: `H4-7C-${runtime}-main-round-2`,
  });
  expect(mainRuntimeConsumer.targetIdHash).toBe(idHash(mainRuntimeRunIds[1]));
  expect(mainRuntimeConsumer.matchedCount).toBeGreaterThan(0);
  const preParallelProjection = await waitForMessageProjection(h4, {
    label: `H4-SYNC-1-${runtime}-pre-parallel`,
    sample: samplePrimaryDetachedPreSubmissionProjection,
    expected: primaryDetachedPreSubmissionProjectionExpected(),
    sourceFacts: {
      mainUser: TOOL_DETAILS_USER,
      mainStage: TOOL_DETAILS_STAGE,
      mainFinal: TOOL_DETAILS_FINAL,
      detachedUser: PARALLEL_FAILURE_USER,
      detachedError: PARALLEL_FAILURE_ERROR,
      fixtureContent: FIXTURE_CONTENT.trim(),
    },
  });

  await page.locator("#prompt").fill(`/parallel ${PARALLEL_FAILURE_USER}`);
  await page.locator("#sendBtn").click();
  const backgroundAssistant = page.locator("#messages article.msg.assistant")
    .filter({ hasText: PARALLEL_FAILURE_ERROR });
  await expect(backgroundAssistant).toHaveCount(1);
  await expect.poll(() => h4.controlIds().agentRunIds.length).toBe(2);
  const backgroundAgentRunId = h4.controlIds().agentRunIds
    .find((agentRunId) => agentRunId !== mainAgentRunId);
  expect(backgroundAgentRunId).toBeTruthy();

  let failedBackgroundAgent = null;
  await expect.poll(async () => {
    failedBackgroundAgent = await fetchProductionJson(
      page,
      `/api/agent/runs/${encodeURIComponent(backgroundAgentRunId)}?cursor=0&wait=0`,
    );
    return {
      status: failedBackgroundAgent.body?.status,
      nextCursor: failedBackgroundAgent.body?.nextCursor,
      eventTypes: (failedBackgroundAgent.body?.events || []).map((event) => event.type),
    };
  }).toEqual({
    status: "failed",
    nextCursor: 3,
    eventTypes: ["created", "model_started", "failed"],
  });
  expect(failedBackgroundAgent.status).toBe(200);
  expect(failedBackgroundAgent.body).toMatchObject({
    agentRunId: backgroundAgentRunId,
    status: "failed",
    error: PARALLEL_FAILURE_ERROR,
    errorCode: "upstream_error",
    round: 0,
    activeRuntimeRunId: "",
    pendingToolCalls: [],
    toolExecutions: [],
  });
  expect(failedBackgroundAgent.body.events[1]).toMatchObject({
    seq: 2,
    type: "model_started",
    data: { round: 1 },
  });
  expect(failedBackgroundAgent.body.events[2]).toMatchObject({
    seq: 3,
    type: "failed",
    data: {
      error: PARALLEL_FAILURE_ERROR,
      errorCode: "upstream_error",
    },
  });
  const backgroundRuntimeRunId = String(
    failedBackgroundAgent.body.events[1]?.data?.runtimeRunId || "",
  );
  expect(backgroundRuntimeRunId).not.toBe("");
  const failedBackgroundRuntime = await fetchProductionJson(
    page,
    `/api/runtime/runs/${encodeURIComponent(backgroundRuntimeRunId)}?cursor=0&wait=0`,
  );
  expect(failedBackgroundRuntime.status).toBe(200);
  expect(failedBackgroundRuntime.body).toMatchObject({
    runId: backgroundRuntimeRunId,
    sessionId: activeMainAgent.body.sessionId,
    status: "failed",
    error: PARALLEL_FAILURE_ERROR,
    errorCode: "upstream_error",
    transient: true,
    upstreamStatus: 502,
    nextCursor: 0,
    events: [],
  });
  expect(failedBackgroundRuntime.body.result).toMatchObject({
    content: "",
    reasoning: "",
    toolCalls: [],
  });

  const stillActiveMainAgent = await fetchProductionJson(
    page,
    `/api/agent/runs/${encodeURIComponent(mainAgentRunId)}?cursor=0&wait=0`,
  );
  expect(stillActiveMainAgent.status).toBe(200);
  expect(stillActiveMainAgent.body).toMatchObject({
    status: "model",
    activeRuntimeRunId: mainRuntimeRunIds[1],
    nextCursor: 7,
  });
  expect(durableToolTraceEvidence(stillActiveMainAgent.body).executionProjection)
    .toEqual(activeMainTrace.executionProjection);
  await expect(page.locator("#activeRunBanner.visible")).toHaveCount(1);
  await expect(page.locator("#stopBtn")).toBeEnabled();

  const activeDom = await detachedParallelFailureDomEvidence(h4);
  expect(activeDom.toolDom.projection.processKey).toBe(processKey);
  expect(activeDom.toolDom.projection.outerOpen).toBe(true);
  expect(activeDom.toolDom.projection.stageClass.split(/\s+/)).toContain("succeeded");
  expect(activeDom.toolDom.projection.formattedResult).toEqual({
    pathPresent: true,
    sizePresent: true,
    fixtureContentCount: 1,
  });

  const sessionButton = page.locator("#sessionList .session-row.active button.session-main");
  await expect(sessionButton).toHaveCount(1);
  const sessionId = await sessionButton.getAttribute("data-session-id");
  expect(sessionId).toBe(activeMainAgent.body.sessionId);
  const activeSession = await fetchProductionJson(
    page,
    `/api/sessions/${encodeURIComponent(sessionId)}`,
  );
  expect(activeSession.status).toBe(200);
  expect(Array.isArray(activeSession.body.runState?.backgroundRuns)
    ? activeSession.body.runState.backgroundRuns
    : []).toEqual([]);
  const activeBackgroundMessages = activeSession.body.messages.filter((message) => (
    message?.meta?.kind === "background-subagent"
  ));
  expect(activeBackgroundMessages).toHaveLength(1);
  expect(activeBackgroundMessages[0].meta.agentRunId).toBe(backgroundAgentRunId);

  await h4.releaseGate(TOOL_FINAL_DELTA_GATE);
  await expect(page.locator("#messages article.msg.assistant").filter({ hasText: TOOL_DETAILS_FINAL }))
    .toHaveCount(1);
  await h4.waitGate(TOOL_TERMINAL_GATE);
  const preTerminalDom = await detachedParallelFailureDomEvidence(h4, {
    finalVisible: true,
    tracePlacement: "transitional",
  });
  expect(preTerminalDom.toolDom.projection.processKey).toBe(processKey);
  expect(preTerminalDom.toolDom.projection.outerOpen).toBe(true);
  expect(preTerminalDom.toolDom.projection.stageClass.split(/\s+/)).toContain("succeeded");

  await h4.releaseGate(TOOL_TERMINAL_GATE);
  let completedMainAgent = null;
  await expect.poll(async () => {
    completedMainAgent = await fetchProductionJson(
      page,
      `/api/agent/runs/${encodeURIComponent(mainAgentRunId)}?cursor=0&wait=0`,
    );
    return {
      status: completedMainAgent.body?.status,
      nextCursor: completedMainAgent.body?.nextCursor,
      eventTypes: (completedMainAgent.body?.events || []).map((event) => event.type),
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
  expect(completedMainAgent.body).toMatchObject({
    activeRuntimeRunId: "",
    pendingToolCalls: [],
    errorCode: "",
  });
  await expect(page.locator("#activeRunBanner.visible")).toHaveCount(0);
  await expect(page.locator("#stopBtn")).toBeDisabled();
  await expect(page.locator("#messages .execution-trace.active")).toHaveCount(0);
  await expect(page.locator("#messages .execution-trace.completed")).toHaveCount(1);
  const terminalDom = await detachedParallelFailureDomEvidence(h4, {
    finalVisible: true,
    terminal: true,
  });
  expect(terminalDom.toolDom.projection.processKey).toBe(processKey);
  expect(terminalDom.toolDom.projection.outerOpen).toBe(false);
  expect(terminalDom.toolDom.projection.itemOpen).toBe(false);
  expect(terminalDom.toolDom.projection.stageClass.split(/\s+/)).toContain("succeeded");

  let terminalSession = null;
  await expect.poll(async () => {
    terminalSession = await fetchProductionJson(
      page,
      `/api/sessions/${encodeURIComponent(sessionId)}`,
    );
    return detachedParallelSessionSettlementProjection(terminalSession);
  }).toEqual({
    status: 200,
    messageCount: 7,
    roles: ["user", "assistant", "tool-call", "tool-result", "assistant", "user", "assistant"],
    markerIndexes: {
      mainFinal: 4,
      detachedUser: 5,
      detachedError: 6,
      followupUser: -1,
      followupFinal: -1,
    },
    runStateKeys: [],
    includeFollowup: false,
  });
  const sessionEvidence = detachedParallelFailureSessionEvidence(
    terminalSession.body.messages,
    mainAgentRunId,
    backgroundAgentRunId,
    toolCallId,
  );

  const metricsAtTerminal = await h4.metrics();
  expect(metricsAtTerminal.chatRequests).toEqual([
    { scenario: "tool-detail-call", stream: true, hasToolResult: false },
    { scenario: "tool-detail-final", stream: true, hasToolResult: true },
    { scenario: "parallel-model-failure", stream: true, hasToolResult: false },
  ]);
  expect(metricsAtTerminal.toolExecutions).toEqual([
    { action: "read_file", path: "fixture.txt" },
  ]);
  expect(metricsAtTerminal.productionToolDelegations).toBe(1);
  expect(metricsAtTerminal.unsafeToolRequests).toBe(0);
  const requestsAtTerminal = h4.requestEvidenceSince(requestBoundary);
  expect(requestsAtTerminal.agentPost).toBe(2);
  expect(requestsAtTerminal.runtimePost).toBe(0);
  expect(requestsAtTerminal.agentDelete).toBe(0);

  const completedMainTrace = durableToolTraceEvidence(completedMainAgent.body);
  const mainToolProjection = {
    status: completedMainTrace.status,
    nextCursor: completedMainTrace.nextCursor,
    pendingToolCallCount: completedMainTrace.pendingToolCallCount,
    terminalEventCount: completedMainTrace.terminalEventCount,
    eventProjection: completedMainTrace.eventProjection,
    executionProjection: completedMainTrace.executionProjection,
    resultProjection: completedMainTrace.resultProjection,
  };
  const backgroundAgentProjection = {
    status: String(failedBackgroundAgent.body.status || ""),
    errorCode: String(failedBackgroundAgent.body.errorCode || ""),
    errorMarkerPresent: String(failedBackgroundAgent.body.error || "")
      .includes(PARALLEL_FAILURE_ERROR),
    round: Number(failedBackgroundAgent.body.round || 0),
    nextCursor: Number(failedBackgroundAgent.body.nextCursor || 0),
    activeRuntimeCleared: !failedBackgroundAgent.body.activeRuntimeRunId,
    pendingToolCallCount: failedBackgroundAgent.body.pendingToolCalls.length,
    toolExecutionCount: failedBackgroundAgent.body.toolExecutions.length,
    events: failedBackgroundAgent.body.events.map((event) => ({
      seq: Number(event.seq || 0),
      type: String(event.type || ""),
      ...(event?.data?.round != null ? { round: Number(event.data.round) } : {}),
      ...(event?.type === "model_started" ? { runtimeLinked: Boolean(event.data.runtimeRunId) } : {}),
      ...(event?.type === "failed" ? {
        errorCode: String(event.data.errorCode || ""),
        errorMarkerPresent: String(event.data.error || "").includes(PARALLEL_FAILURE_ERROR),
      } : {}),
    })),
  };
  const backgroundRuntimeProjection = {
    status: String(failedBackgroundRuntime.body.status || ""),
    errorCode: String(failedBackgroundRuntime.body.errorCode || ""),
    errorMarkerPresent: String(failedBackgroundRuntime.body.error || "")
      .includes(PARALLEL_FAILURE_ERROR),
    transient: failedBackgroundRuntime.body.transient === true,
    upstreamStatus: Number(failedBackgroundRuntime.body.upstreamStatus || 0),
    nextCursor: Number(failedBackgroundRuntime.body.nextCursor || 0),
    eventCount: failedBackgroundRuntime.body.events.length,
    result: {
      contentEmpty: !failedBackgroundRuntime.body.result?.content,
      reasoningEmpty: !failedBackgroundRuntime.body.result?.reasoning,
      toolCallCount: (failedBackgroundRuntime.body.result?.toolCalls || []).length,
    },
  };
  const terminalRequestProjection = {
    agentRunPost: requestsAtTerminal.agentPost,
    runtimePost: requestsAtTerminal.runtimePost,
    chat: metricsAtTerminal.chatRequests.length,
    toolExecutions: metricsAtTerminal.toolExecutions.length,
    backgroundToolExecutions: 0,
  };
  expect({
    mainToolTrace: canonicalHash(mainToolProjection),
    backgroundAgent: canonicalHash(backgroundAgentProjection),
    backgroundRuntime: canonicalHash(backgroundRuntimeProjection),
    backgroundMeta: canonicalHash(sessionEvidence.backgroundMeta),
    requestCounts: canonicalHash(terminalRequestProjection),
  }).toEqual({
    mainToolTrace: H4_7C_BASE_SEMANTIC_HASHES.mainToolTrace,
    backgroundAgent: H4_7C_BASE_SEMANTIC_HASHES.backgroundAgent,
    backgroundRuntime: H4_7C_BASE_SEMANTIC_HASHES.backgroundRuntime,
    backgroundMeta: H4_7C_BASE_SEMANTIC_HASHES.backgroundMeta,
    requestCounts: H4_7C_BASE_SEMANTIC_HASHES.requestCounts,
  });

  const followupBoundary = h4.requestBoundary();
  const prompt = page.locator("#prompt");
  const sendButton = page.locator("#sendBtn");
  await expect(page.locator("#activeRunBanner.visible")).toHaveCount(0);
  await expect(page.locator("#stopBtn")).toBeDisabled();
  await expect(prompt).toBeEnabled();
  await prompt.fill(PARALLEL_FAILURE_FOLLOWUP_USER);
  await expect(prompt).toHaveValue(PARALLEL_FAILURE_FOLLOWUP_USER);
  await expect(sendButton).toBeEnabled();
  await sendButton.click();
  const followupUser = page.locator("#messages article.msg.user")
    .filter({ hasText: PARALLEL_FAILURE_FOLLOWUP_USER });
  const followupFinal = page.locator("#messages article.msg.assistant")
    .filter({ hasText: PARALLEL_FAILURE_FOLLOWUP_FINAL });
  await expect(followupUser).toHaveCount(1);
  await expect(followupFinal).toHaveCount(1);
  await expect.poll(() => h4.controlIds().agentRunIds.length).toBe(3);
  const followupAgentRunId = h4.controlIds().agentRunIds.find((agentRunId) => (
    agentRunId !== mainAgentRunId && agentRunId !== backgroundAgentRunId
  ));
  expect(followupAgentRunId).toBeTruthy();

  let completedFollowupAgent = null;
  await expect.poll(async () => {
    completedFollowupAgent = await fetchProductionJson(
      page,
      `/api/agent/runs/${encodeURIComponent(followupAgentRunId)}?cursor=0&wait=0`,
    );
    return {
      status: completedFollowupAgent.body?.status,
      nextCursor: completedFollowupAgent.body?.nextCursor,
      eventTypes: (completedFollowupAgent.body?.events || []).map((event) => event.type),
    };
  }).toEqual({
    status: "completed",
    nextCursor: 4,
    eventTypes: ["created", "model_started", "model_completed", "completed"],
  });
  expect(completedFollowupAgent.status).toBe(200);
  expect(completedFollowupAgent.body).toMatchObject({
    agentRunId: followupAgentRunId,
    sessionId,
    status: "completed",
    nextCursor: 4,
    activeRuntimeRunId: "",
    pendingToolCalls: [],
    toolExecutions: [],
    errorCode: "",
  });
  const followupRuntimeRunId = String(
    completedFollowupAgent.body.events.find((event) => event?.type === "model_started")
      ?.data?.runtimeRunId || "",
  );
  expect(followupRuntimeRunId).not.toBe("");
  expect(completedFollowupAgent.body.events.map((event) => Number(event.seq || 0)))
    .toEqual([1, 2, 3, 4]);
  expect(completedFollowupAgent.body.events[1]).toMatchObject({
    type: "model_started",
    data: { round: 1, runtimeRunId: followupRuntimeRunId },
  });
  expect(completedFollowupAgent.body.events[2]).toMatchObject({
    type: "model_completed",
    data: { round: 1, runtimeRunId: followupRuntimeRunId },
  });
  expect(completedFollowupAgent.body.events[3]).toMatchObject({ type: "completed" });
  const completedFollowupRuntime = await fetchProductionJson(
    page,
    `/api/runtime/runs/${encodeURIComponent(followupRuntimeRunId)}?cursor=0&wait=0`,
  );
  expect(completedFollowupRuntime.status).toBe(200);
  expect(completedFollowupRuntime.body).toMatchObject({
    runId: followupRuntimeRunId,
    sessionId,
    status: "completed",
    nextCursor: 3,
  });
  expect(completedFollowupRuntime.body.result).toMatchObject({
    content: PARALLEL_FAILURE_FOLLOWUP_FINAL,
    toolCalls: [],
  });
  const expectedAgentRunIds = new Set([
    mainAgentRunId,
    backgroundAgentRunId,
    followupAgentRunId,
  ]);
  const expectedRuntimeRunIds = new Set([
    ...mainRuntimeRunIds,
    backgroundRuntimeRunId,
    followupRuntimeRunId,
  ]);
  expect(new Set(h4.controlIds().agentRunIds)).toEqual(expectedAgentRunIds);
  expect(new Set(h4.controlIds().runtimeRunIds)).toEqual(expectedRuntimeRunIds);

  const metricsAfterFollowup = await h4.metrics();
  const followupContext = {
    followupMarkerCount: 1,
    detachedUserMarkerCount: 0,
    detachedErrorMarkerCount: 0,
    detachedStateFieldCount: 0,
    mainlineKinds: [
      { role: "user", kind: "main-user" },
      { role: "assistant", kind: "main-tool-call" },
      { role: "tool", kind: "main-tool-receipt" },
      { role: "assistant", kind: "main-final" },
      { role: "user", kind: "followup-user" },
    ],
    unclassifiedNonSystemCount: 0,
    toolCall: {
      count: 1,
      matchingIdCount: 1,
      readFile: true,
      pathMatchesFixture: true,
      receiptLinked: true,
    },
    toolReceipt: {
      count: 1,
      contentPresent: true,
      pathMatchesFixture: true,
      contentMatchesFixture: true,
      sizeMatchesFixture: true,
    },
  };
  expect(metricsAfterFollowup.chatRequests).toEqual([
    { scenario: "tool-detail-call", stream: true, hasToolResult: false },
    { scenario: "tool-detail-final", stream: true, hasToolResult: true },
    { scenario: "parallel-model-failure", stream: true, hasToolResult: false },
    {
      scenario: "parallel-failure-followup",
      stream: true,
      hasToolResult: true,
      followupContext,
    },
  ]);
  expect(metricsAfterFollowup.toolExecutions).toEqual(metricsAtTerminal.toolExecutions);
  expect(metricsAfterFollowup.productionToolDelegations).toBe(1);
  expect(metricsAfterFollowup.unsafeToolRequests).toBe(0);
  const followupRequests = h4.requestEvidenceSince(followupBoundary);
  const followupSummary = h4.requestSummarySince(followupBoundary);
  expect(followupRequests.agentPost).toBe(1);
  expect(followupRequests.runtimePost).toBe(0);
  expect(followupRequests.agentDelete).toBe(0);
  const followupBrowserProxyChatPost = followupSummary["POST /proxy/chat"] || 0;
  const followupUpstreamChatDelta = metricsAfterFollowup.chatRequests.length
    - metricsAtTerminal.chatRequests.length;
  expect(followupBrowserProxyChatPost).toBe(0);
  expect(followupUpstreamChatDelta).toBe(1);
  expect(Object.entries(followupSummary).filter(([key]) => key.startsWith("POST /api/tools/")))
    .toEqual([]);
  const allRequests = h4.requestEvidenceSince(requestBoundary);
  expect(allRequests.agentPost).toBe(3);
  expect(allRequests.runtimePost).toBe(0);

  let followupSession = null;
  await expect.poll(async () => {
    followupSession = await fetchProductionJson(
      page,
      `/api/sessions/${encodeURIComponent(sessionId)}`,
    );
    return detachedParallelSessionSettlementProjection(followupSession, { includeFollowup: true });
  }).toEqual({
    status: 200,
    messageCount: 9,
    roles: [
      "user", "assistant", "tool-call", "tool-result", "assistant",
      "user", "assistant", "user", "assistant",
    ],
    markerIndexes: {
      mainFinal: 4,
      detachedUser: 5,
      detachedError: 6,
      followupUser: 7,
      followupFinal: 8,
    },
    runStateKeys: [],
    includeFollowup: true,
  });
  const followupSessionEvidence = detachedParallelFailureSessionEvidence(
    followupSession.body.messages,
    mainAgentRunId,
    backgroundAgentRunId,
    toolCallId,
    { includeFollowup: true },
  );
  const followupDomProjection = await waitForMessageProjection(h4, {
    label: `H4-SYNC-1-${runtime}-followup-terminal`,
    sample: sampleFollowupIsolationProjection,
    expected: followupIsolationProjectionExpected(),
    sourceFacts: {
      mainUser: TOOL_DETAILS_USER,
      mainStage: TOOL_DETAILS_STAGE,
      mainFinal: TOOL_DETAILS_FINAL,
      detachedUser: PARALLEL_FAILURE_USER,
      detachedError: PARALLEL_FAILURE_ERROR,
      followupUser: PARALLEL_FAILURE_FOLLOWUP_USER,
      followupFinal: PARALLEL_FAILURE_FOLLOWUP_FINAL,
      fixtureContent: FIXTURE_CONTENT.trim(),
    },
  });
  await expect(prompt).toBeEnabled();
  await expect(page.locator("#activeRunBanner.visible")).toHaveCount(0);
  await expect(page.locator("#stopBtn")).toBeDisabled();

  const followupAgentProjection = {
    status: String(completedFollowupAgent.body.status || ""),
    nextCursor: Number(completedFollowupAgent.body.nextCursor || 0),
    eventTypes: completedFollowupAgent.body.events.map((event) => String(event.type || "")),
    activeRuntimeCleared: !completedFollowupAgent.body.activeRuntimeRunId,
    pendingToolCallCount: completedFollowupAgent.body.pendingToolCalls.length,
    toolExecutionCount: completedFollowupAgent.body.toolExecutions.length,
    errorCode: String(completedFollowupAgent.body.errorCode || ""),
    events: completedFollowupAgent.body.events.map((event) => ({
      seq: Number(event.seq || 0),
      type: String(event.type || ""),
      ...(["model_started", "model_completed"].includes(event.type) ? {
        round: Number(event.data?.round || 0),
        runtimeLinked: String(event.data?.runtimeRunId || "") === followupRuntimeRunId,
      } : {}),
    })),
  };
  const followupRuntimeProjection = {
    status: String(completedFollowupRuntime.body.status || ""),
    nextCursor: Number(completedFollowupRuntime.body.nextCursor || 0),
    finalMarkerPresent: String(completedFollowupRuntime.body.result?.content || "")
      .includes(PARALLEL_FAILURE_FOLLOWUP_FINAL),
    toolCallCount: (completedFollowupRuntime.body.result?.toolCalls || []).length,
  };
  const followupRequestProjection = {
    initial: terminalRequestProjection,
    followup: {
      agentRunPost: followupRequests.agentPost,
      runtimePost: followupRequests.runtimePost,
      browserProxyChatPost: followupBrowserProxyChatPost,
      upstreamChatDelta: followupUpstreamChatDelta,
      toolExecutions: metricsAfterFollowup.toolExecutions.length
        - metricsAtTerminal.toolExecutions.length,
    },
    total: {
      agentRunPost: allRequests.agentPost,
      runtimePost: allRequests.runtimePost,
      chat: metricsAfterFollowup.chatRequests.length,
      toolExecutions: metricsAfterFollowup.toolExecutions.length,
    },
  };

  const refreshBoundary = h4.requestBoundary();
  await h4.reloadRuntime(runtime);
  if (runtime === "classic") {
    const restoredUrl = new URL(page.url());
    expect(restoredUrl.pathname).toBe(CLASSIC_FALLBACK_PATH);
    expect(restoredUrl.search).toBe("");
    expect(await page.locator("html").getAttribute("data-code-frontend-ready")).toBeNull();
  }
  const restoredSessionButton = page.locator(
    `#sessionList button.session-main[data-session-id="${sessionId}"]`,
  );
  await expect(restoredSessionButton).toHaveCount(1);
  await restoredSessionButton.click();
  const restoredDomProjection = await waitForMessageProjection(h4, {
    label: `H4-SYNC-1-${runtime}-followup-refresh`,
    sample: sampleFollowupIsolationProjection,
    expected: followupIsolationProjectionExpected(),
    sourceFacts: {
      mainUser: TOOL_DETAILS_USER,
      mainStage: TOOL_DETAILS_STAGE,
      mainFinal: TOOL_DETAILS_FINAL,
      detachedUser: PARALLEL_FAILURE_USER,
      detachedError: PARALLEL_FAILURE_ERROR,
      followupUser: PARALLEL_FAILURE_FOLLOWUP_USER,
      followupFinal: PARALLEL_FAILURE_FOLLOWUP_FINAL,
      fixtureContent: FIXTURE_CONTENT.trim(),
    },
  });
  expect(restoredDomProjection).toEqual(followupDomProjection);

  const mainAfterReload = await fetchProductionJson(
    page,
    `/api/agent/runs/${encodeURIComponent(mainAgentRunId)}?cursor=0&wait=0`,
  );
  const backgroundAfterReload = await fetchProductionJson(
    page,
    `/api/agent/runs/${encodeURIComponent(backgroundAgentRunId)}?cursor=0&wait=0`,
  );
  const backgroundRuntimeAfterReload = await fetchProductionJson(
    page,
    `/api/runtime/runs/${encodeURIComponent(backgroundRuntimeRunId)}?cursor=0&wait=0`,
  );
  const followupAfterReload = await fetchProductionJson(
    page,
    `/api/agent/runs/${encodeURIComponent(followupAgentRunId)}?cursor=0&wait=0`,
  );
  const followupRuntimeAfterReload = await fetchProductionJson(
    page,
    `/api/runtime/runs/${encodeURIComponent(followupRuntimeRunId)}?cursor=0&wait=0`,
  );
  expect(mainAfterReload.status).toBe(200);
  expect(backgroundAfterReload.status).toBe(200);
  expect(backgroundRuntimeAfterReload.status).toBe(200);
  expect(followupAfterReload.status).toBe(200);
  expect(followupRuntimeAfterReload.status).toBe(200);
  expect({
    status: durableToolTraceEvidence(mainAfterReload.body).status,
    nextCursor: durableToolTraceEvidence(mainAfterReload.body).nextCursor,
    pendingToolCallCount: durableToolTraceEvidence(mainAfterReload.body).pendingToolCallCount,
    terminalEventCount: durableToolTraceEvidence(mainAfterReload.body).terminalEventCount,
    eventProjection: durableToolTraceEvidence(mainAfterReload.body).eventProjection,
    executionProjection: durableToolTraceEvidence(mainAfterReload.body).executionProjection,
    resultProjection: durableToolTraceEvidence(mainAfterReload.body).resultProjection,
  }).toEqual(mainToolProjection);
  expect(backgroundAfterReload.body.agentRunId).toBe(backgroundAgentRunId);
  expect(backgroundAfterReload.body.status).toBe("failed");
  expect(backgroundAfterReload.body.events).toEqual(failedBackgroundAgent.body.events);
  expect(backgroundAfterReload.body.toolExecutions).toEqual([]);
  expect(backgroundRuntimeAfterReload.body).toEqual(failedBackgroundRuntime.body);
  expect(followupAfterReload.body).toEqual(completedFollowupAgent.body);
  expect(followupRuntimeAfterReload.body).toEqual(completedFollowupRuntime.body);

  let sessionAfterReload = null;
  await expect.poll(async () => {
    sessionAfterReload = await fetchProductionJson(
      page,
      `/api/sessions/${encodeURIComponent(sessionId)}`,
    );
    return detachedParallelSessionSettlementProjection(
      sessionAfterReload,
      { includeFollowup: true },
    );
  }).toEqual({
    status: 200,
    messageCount: 9,
    roles: [
      "user", "assistant", "tool-call", "tool-result", "assistant",
      "user", "assistant", "user", "assistant",
    ],
    markerIndexes: {
      mainFinal: 4,
      detachedUser: 5,
      detachedError: 6,
      followupUser: 7,
      followupFinal: 8,
    },
    runStateKeys: [],
    includeFollowup: true,
  });
  const restoredSessionEvidence = detachedParallelFailureSessionEvidence(
    sessionAfterReload.body.messages,
    mainAgentRunId,
    backgroundAgentRunId,
    toolCallId,
    { includeFollowup: true },
  );
  expect(restoredSessionEvidence.roleContent).toEqual(followupSessionEvidence.roleContent);
  expect(restoredSessionEvidence.backgroundMeta).toEqual(followupSessionEvidence.backgroundMeta);

  const metricsAfterReload = await h4.metrics();
  expect(metricsAfterReload.chatRequests).toEqual(metricsAfterFollowup.chatRequests);
  expect(metricsAfterReload.toolExecutions).toEqual(metricsAfterFollowup.toolExecutions);
  const refreshRequests = h4.requestEvidenceSince(refreshBoundary);
  const refreshSummary = h4.requestSummarySince(refreshBoundary);
  expect(refreshRequests.agentPost).toBe(0);
  expect(refreshRequests.runtimePost).toBe(0);
  expect(refreshRequests.agentDelete).toBe(0);
  const refreshBrowserProxyChatPost = refreshSummary["POST /proxy/chat"] || 0;
  const refreshUpstreamChatDelta = metricsAfterReload.chatRequests.length
    - metricsAfterFollowup.chatRequests.length;
  expect(refreshBrowserProxyChatPost).toBe(0);
  expect(refreshUpstreamChatDelta).toBe(0);
  expect(Object.entries(refreshSummary).filter(([key]) => key.startsWith("POST /api/tools/")))
    .toEqual([]);
  expect(new Set(h4.controlIds().agentRunIds)).toEqual(expectedAgentRunIds);
  expect(new Set(h4.controlIds().runtimeRunIds)).toEqual(expectedRuntimeRunIds);
  expect(h4.pageErrors).toEqual([]);

  const refreshProjection = {
    mainAgentStable: mainAfterReload.body.agentRunId === mainAgentRunId,
    backgroundAgentStable: backgroundAfterReload.body.agentRunId === backgroundAgentRunId,
    backgroundRuntimeStable: backgroundRuntimeAfterReload.body.runId === backgroundRuntimeRunId,
    followupAgentStable: followupAfterReload.body.agentRunId === followupAgentRunId,
    followupRuntimeStable: followupRuntimeAfterReload.body.runId === followupRuntimeRunId,
    processKeyStable: restoredDomProjection.tool.processKey === processKey,
    sessionRoleContentStable: JSON.stringify(restoredSessionEvidence.roleContent)
      === JSON.stringify(followupSessionEvidence.roleContent),
    backgroundMetaStable: JSON.stringify(restoredSessionEvidence.backgroundMeta)
      === JSON.stringify(followupSessionEvidence.backgroundMeta),
    backgroundCheckpointCount: Array.isArray(sessionAfterReload.body.runState?.backgroundRuns)
      ? sessionAfterReload.body.runState.backgroundRuns.length
      : 0,
    runStateCleared: Object.keys(sessionAfterReload.body.runState || {}).length === 0,
    domUnique: restoredDomProjection,
    requests: {
      agentRunPost: refreshRequests.agentPost,
      runtimePost: refreshRequests.runtimePost,
      browserProxyChatPost: refreshBrowserProxyChatPost,
      upstreamChatDelta: refreshUpstreamChatDelta,
      toolExecutions: metricsAfterReload.toolExecutions.length
        - metricsAfterFollowup.toolExecutions.length,
    },
  };
  const hashes = {
    preParallelFence: canonicalHash(preParallelProjection),
    terminalOrdering: canonicalHash({
      roleContent: sessionEvidence.roleContent,
      dom: terminalDom.semanticProjection,
    }),
    followupRequestContext: canonicalHash(followupContext),
    followupAgentRuntime: canonicalHash({
      agent: followupAgentProjection,
      runtime: followupRuntimeProjection,
    }),
    followupSession: canonicalHash({
      roleContent: followupSessionEvidence.roleContent,
      backgroundMeta: followupSessionEvidence.backgroundMeta,
      runState: { cleared: Object.keys(followupSession.body.runState || {}).length === 0 },
    }),
    followupDom: canonicalHash(followupDomProjection),
    requestCounts: canonicalHash(followupRequestProjection),
    refreshLifecycle: canonicalHash(refreshProjection),
  };
  if (Object.values(H4_SYNC_1_SEMANTIC_HASHES).every(Boolean)) {
    expect(hashes).toEqual(H4_SYNC_1_SEMANTIC_HASHES);
  } else {
    expect(runtime).toBe("bundle");
  }
  h4.evidence(`${runtime}-detached-parallel-failure-isolation`, {
    runtime,
    identities: {
      mainAgentRunId: idHash(mainAgentRunId),
      backgroundAgentRunId: idHash(backgroundAgentRunId),
      backgroundRuntimeRunId: idHash(backgroundRuntimeRunId),
      followupAgentRunId: idHash(followupAgentRunId),
      followupRuntimeRunId: idHash(followupRuntimeRunId),
      toolCallId: idHash(toolCallId),
      jobId: idHash(sessionEvidence.jobId),
    },
    eventTypes: {
      main: completedMainAgent.body.events.map((event) => event.type),
      background: failedBackgroundAgent.body.events.map((event) => event.type),
      followup: completedFollowupAgent.body.events.map((event) => event.type),
    },
    runtime: backgroundRuntimeProjection,
    requests: followupRequestProjection,
    refresh: refreshProjection.requests,
    terminalDom: terminalDom.semanticProjection,
    followupDom: followupDomProjection,
    hashes,
  });
}

function questionnaireArgumentsProjection(value) {
  const source = value && typeof value === "object" ? value : parseToolArguments(value);
  const questions = Array.isArray(source?.questions) ? source.questions : [];
  const question = questions[0] && typeof questions[0] === "object" ? questions[0] : {};
  const options = Array.isArray(question.options) ? question.options : [];
  return {
    titleMatches: String(source?.title || "") === QUESTIONNAIRE_TITLE,
    reasonMatches: String(source?.reason || "") === QUESTIONNAIRE_REASON,
    questionCount: questions.length,
    question: {
      idMatches: String(question.id || "") === QUESTIONNAIRE_QUESTION_ID,
      promptMatches: String(question.prompt || "") === QUESTIONNAIRE_PROMPT,
      type: String(question.type || ""),
      required: question.required === true,
      allowOther: question.allowOther === true,
      options: options.map((option) => ({
        value: String(option?.value || ""),
        labelMatches: [QUESTIONNAIRE_OPTION_A.label, QUESTIONNAIRE_OPTION_B.label]
          .includes(String(option?.label || "")),
        descriptionPresent: Boolean(String(option?.description || "").trim()),
      })),
    },
  };
}

function stableQuestionnaireResult(value) {
  const source = value && typeof value === "object" ? value : {};
  const answers = Array.isArray(source.answers) ? source.answers : [];
  const answer = answers[0] && typeof answers[0] === "object" ? answers[0] : {};
  const values = Array.isArray(answer.values) ? answer.values.map(String) : [];
  return {
    ok: source.ok === true,
    action: String(source.action || ""),
    requestIdMatches: String(source.requestId || "") === QUESTIONNAIRE_REQUEST_ID,
    titleMatches: String(source.title || "") === QUESTIONNAIRE_TITLE,
    answerCount: answers.length,
    answer: {
      idMatches: String(answer.id || "") === QUESTIONNAIRE_QUESTION_ID,
      promptMatches: String(answer.prompt || "") === QUESTIONNAIRE_PROMPT,
      type: String(answer.type || ""),
      status: String(answer.status || ""),
      values,
      selectedValueMatches: values.length === 1 && values[0] === QUESTIONNAIRE_OPTION_B.value,
      answerLabelMatches: String(answer.answer || "") === QUESTIONNAIRE_OPTION_B.label,
      otherEmpty: !String(answer.other || ""),
    },
    summaryMatches: String(source.summary || "").includes(QUESTIONNAIRE_PROMPT)
      && String(source.summary || "").includes(QUESTIONNAIRE_OPTION_B.label),
    failureCountAbsent: !Object.prototype.hasOwnProperty.call(source, "failureCount"),
    failureSignatureAbsent: !Object.prototype.hasOwnProperty.call(source, "failureSignature"),
    retryFieldsAbsent: !Object.prototype.hasOwnProperty.call(source, "retryBlocked")
      && !Object.prototype.hasOwnProperty.call(source, "retryLimitReached"),
  };
}

function questionnaireEventProjection(snapshot) {
  const events = Array.isArray(snapshot?.events) ? snapshot.events : [];
  const runtimeIds = events
    .filter((event) => event?.type === "model_started")
    .map((event) => String(event?.data?.runtimeRunId || ""));
  const runtimeAliases = new Map(runtimeIds.map((runId, index) => [runId, `runtime-${index + 1}`]));
  return events.map((event) => {
    const data = event?.data || {};
    const projected = {
      seq: Number(event?.seq || 0),
      type: String(event?.type || ""),
    };
    if (data.round != null) projected.round = Number(data.round);
    if (data.runtimeRunId) {
      projected.runtimeRunId = runtimeAliases.get(String(data.runtimeRunId)) || "mismatch";
    }
    if (data.content != null) {
      projected.content = String(data.content) === QUESTIONNAIRE_FINAL ? "final" : "empty";
    }
    if (data.finishReason != null) projected.finishReason = String(data.finishReason);
    if (Array.isArray(data.toolCalls)) {
      projected.toolCalls = data.toolCalls.map((call) => ({
        toolCallMatches: String(call?.id || "") === QUESTIONNAIRE_TOOL_CALL_ID,
        name: String(call?.function?.name || call?.name || ""),
        arguments: questionnaireArgumentsProjection(
          call?.function?.arguments ?? call?.arguments,
        ),
      }));
    }
    if (data.toolCallId) {
      projected.toolCallMatches = String(data.toolCallId) === QUESTIONNAIRE_TOOL_CALL_ID;
    }
    if (data.name != null) projected.name = String(data.name || "");
    if (data.arguments != null) projected.arguments = questionnaireArgumentsProjection(data.arguments);
    if (data.requestId != null) {
      projected.requestIdMatches = String(data.requestId) === QUESTIONNAIRE_REQUEST_ID;
    }
    if (Array.isArray(data.questions)) {
      projected.inputRequest = questionnaireArgumentsProjection({
        title: data.title,
        reason: data.reason,
        questions: data.questions,
      });
    }
    if (data.outcome != null) projected.outcome = String(data.outcome);
    if (data.replayed != null) projected.replayed = Boolean(data.replayed);
    if (data.result != null) projected.result = stableQuestionnaireResult(data.result);
    if (data.resumeStatus != null) projected.resumeStatus = String(data.resumeStatus);
    if (data.reason != null) projected.reason = String(data.reason);
    return projected;
  });
}

function questionnaireExecutionProjection(snapshot) {
  return (Array.isArray(snapshot?.toolExecutions) ? snapshot.toolExecutions : []).map((execution) => ({
    toolCallMatches: String(execution?.toolCallId || "") === QUESTIONNAIRE_TOOL_CALL_ID,
    name: String(execution?.name || ""),
    arguments: questionnaireArgumentsProjection(execution?.arguments),
    status: String(execution?.status || ""),
    outcome: String(execution?.outcome || ""),
    result: execution?.result == null ? null : stableQuestionnaireResult(execution.result),
    failureCountAbsent: !Object.prototype.hasOwnProperty.call(execution || {}, "failureCount"),
    failureSignatureAbsent: !Object.prototype.hasOwnProperty.call(execution || {}, "failureSignature"),
  }));
}

function questionnaireRunStateProjection(runState, agentRunId) {
  const source = runState && typeof runState === "object" ? runState : {};
  const request = source.userInputRequest && typeof source.userInputRequest === "object"
    ? source.userInputRequest
    : null;
  const question = request?.questions?.[0] || {};
  return {
    status: String(source.status || ""),
    phase: String(source.phase || ""),
    executionOwner: String(source.executionOwner || ""),
    agentRunMatches: String(source.agentRunId || "") === agentRunId,
    runtimeRunCleared: !String(source.runtimeRunId || ""),
    cursor: Number(source.agentEventCursor || 0),
    modelRound: Number(source.modelRound || 0),
    request: request ? {
      requestIdMatches: String(request.id || "") === QUESTIONNAIRE_REQUEST_ID,
      toolCallMatches: String(request.toolCallId || "") === QUESTIONNAIRE_TOOL_CALL_ID,
      agentRunMatches: String(request.agentRunId || "") === agentRunId,
      titleMatches: String(request.title || "") === QUESTIONNAIRE_TITLE,
      reasonMatches: String(request.reason || "") === QUESTIONNAIRE_REASON,
      status: String(request.status || ""),
      questionCount: Array.isArray(request.questions) ? request.questions.length : 0,
      question: {
        idMatches: String(question.id || "") === QUESTIONNAIRE_QUESTION_ID,
        type: String(question.type || ""),
        status: String(question.status || ""),
        selectedCount: Array.isArray(question.selected) ? question.selected.length : -1,
        optionValues: Array.isArray(question.options)
          ? question.options.map((option) => String(option?.value || ""))
          : [],
      },
    } : null,
  };
}

function questionnaireWaitingSnapshotProjection(snapshot, session, agentRunId) {
  const pending = snapshot?.pendingInput || {};
  const questions = Array.isArray(pending.questions) ? pending.questions : [];
  return {
    agent: {
      status: String(snapshot?.status || ""),
      nextCursor: Number(snapshot?.nextCursor || 0),
      round: Number(snapshot?.round || 0),
      activeRuntimeCleared: !String(snapshot?.activeRuntimeRunId || ""),
      pendingToolCallCount: Array.isArray(snapshot?.pendingToolCalls)
        ? snapshot.pendingToolCalls.length
        : -1,
      pendingInput: {
        requestIdMatches: String(pending.requestId || "") === QUESTIONNAIRE_REQUEST_ID,
        toolCallMatches: String(pending.toolCallId || "") === QUESTIONNAIRE_TOOL_CALL_ID,
        titleMatches: String(pending.title || "") === QUESTIONNAIRE_TITLE,
        reasonMatches: String(pending.reason || "") === QUESTIONNAIRE_REASON,
        questionCount: questions.length,
        question: questionnaireArgumentsProjection({ questions }).question,
      },
      executions: questionnaireExecutionProjection(snapshot),
    },
    session: {
      roles: (session?.messages || []).map((message) => String(message?.role || "")),
      runState: questionnaireRunStateProjection(session?.runState, agentRunId),
    },
  };
}

function questionnaireSessionRoleProjection(messages) {
  return (Array.isArray(messages) ? messages : []).map((message) => {
    const role = String(message?.role || "");
    const meta = message?.meta || {};
    let kind = "";
    if (role === "user" && message?.content === QUESTIONNAIRE_USER) kind = "initial-user";
    else if (role === "assistant" && message?.content === QUESTIONNAIRE_FINAL) kind = "final";
    else if (
      role === "assistant"
      && Array.isArray(meta.toolCalls)
      && meta.toolCalls.length > 0
    ) kind = "tool-owner";
    else if (role === "tool-call" && meta.action === "request_user_input") kind = "questionnaire-call";
    else if (meta.kind === "user-input-summary") kind = "input-summary";
    else if (role === "tool-result" && meta.action === "request_user_input") kind = "questionnaire-result";
    return { role, kind };
  });
}

function questionnaireSessionInputMetaProjection(messages, agentRunId) {
  return (Array.isArray(messages) ? messages : [])
    .filter((message) => (
      ["tool-call", "tool-result"].includes(message?.role)
      || message?.meta?.kind === "user-input-summary"
    ))
    .map((message) => {
      const meta = message?.meta || {};
      if (meta.kind === "user-input-summary") {
        const answer = Array.isArray(meta.answers) ? meta.answers[0] : null;
        return {
          role: String(message.role || ""),
          kind: "user-input-summary",
          system: meta._system === true,
          skipApi: meta.skipApi === true,
          requestIdMatches: String(meta.requestId || "") === QUESTIONNAIRE_REQUEST_ID,
          titleMatches: String(meta.title || "") === QUESTIONNAIRE_TITLE,
          answer: stableQuestionnaireResult({
            ok: true,
            action: "request_user_input",
            requestId: meta.requestId,
            title: meta.title,
            answers: answer ? [answer] : [],
            summary: message.content,
          }),
        };
      }
      const result = meta.result && typeof meta.result === "object"
        ? stableQuestionnaireResult(meta.result)
        : null;
      return {
        role: String(message.role || ""),
        toolCallMatches: String(meta.toolCallId || "") === QUESTIONNAIRE_TOOL_CALL_ID,
        agentRunMatches: String(meta.agentRunId || "") === agentRunId,
        eventType: String(meta.agentEventType || ""),
        eventSeq: Number(meta.agentEventSeq || 0),
        action: String(meta.action || ""),
        native: meta.native === true,
        replayed: Boolean(meta.replayed),
        outcome: String(meta.outcome || ""),
        arguments: message.role === "tool-call"
          ? questionnaireArgumentsProjection(meta.tool || {})
          : null,
        result,
      };
    });
}

function questionnaireRequestProjection(h4, boundary, beforeMetrics, afterMetrics) {
  const requests = h4.requestEvidenceSince(boundary);
  const summary = h4.requestSummarySince(boundary);
  return {
    agentRunPost: requests.agentPost,
    runtimePost: requests.runtimePost,
    agentDelete: requests.agentDelete,
    inputPost: summary["POST /api/agent/runs/[id]/input"] || 0,
    resumePost: summary["POST /api/agent/runs/[id]/resume"] || 0,
    browserProxyChatPost: summary["POST /proxy/chat"] || 0,
    browserToolPost: Object.entries(summary)
      .filter(([key]) => key.startsWith("POST /api/tools/"))
      .reduce((total, [, count]) => total + count, 0),
    upstreamChatDelta: afterMetrics.chatRequests.length - beforeMetrics.chatRequests.length,
    productionDelegationDelta: Number(afterMetrics.productionToolDelegations || 0)
      - Number(beforeMetrics.productionToolDelegations || 0),
    productionToolExecutionDelta: afterMetrics.toolExecutions.length
      - beforeMetrics.toolExecutions.length,
  };
}

async function questionnaireDomProjection(h4, phase) {
  const expected = phase === "waiting" ? {
    panel: { visible: true, cards: 1, questions: 1, options: 2, checked: 0, confirms: 1 },
    messages: { initialUser: 1, toolProcesses: 1, toolItems: 1, summaries: 0, finals: 0 },
    tool: { action: "request_user_input", argumentDetails: 1, resultDetails: 0 },
    order: ["initial-user", "tool-process"],
  } : {
    panel: { visible: false, cards: 0, questions: 0, options: 0, checked: 0, confirms: 0 },
    messages: { initialUser: 1, toolProcesses: 1, toolItems: 1, summaries: 1, finals: 1 },
    tool: { action: "request_user_input", argumentDetails: 1, resultDetails: 1 },
    order: ["initial-user", "tool-process", "input-summary", "final"],
  };
  return waitForMessageProjection(h4, {
    label: `questionnaire-${phase}`,
    expected,
    sourceFacts: {
      phase,
      userMarker: QUESTIONNAIRE_USER,
      finalMarker: QUESTIONNAIRE_FINAL,
      questionId: QUESTIONNAIRE_QUESTION_ID,
      promptMarker: QUESTIONNAIRE_PROMPT,
      selectedLabel: QUESTIONNAIRE_OPTION_B.label,
    },
    sample: (facts) => {
      const panel = document.querySelector("#userInputPanel");
      const root = document.querySelector("#messages");
      const users = [...root.querySelectorAll("article.msg.user")]
        .filter((node) => node.textContent.includes(facts.userMarker));
      const processStages = [...root.querySelectorAll(
        'article.tool-process > details.tool-process-stage[data-current-action="request_user_input"]',
      )];
      const processes = processStages.map((stage) => stage.closest("article.tool-process"));
      const process = processes[0] || null;
      const item = process?.querySelector("details.tool-process-item") || null;
      const details = item ? [...item.querySelectorAll(".tool-process-detail pre")] : [];
      const summaries = [...root.querySelectorAll("article.user-input-flow")]
        .filter((node) => (
          node.textContent.includes(facts.promptMarker)
          && node.textContent.includes(facts.selectedLabel)
        ));
      const finals = [...root.querySelectorAll("article.msg.assistant")]
        .filter((node) => node.textContent.includes(facts.finalMarker));
      const nodes = [
        { label: "initial-user", node: users[0] || null },
        { label: "tool-process", node: process },
        ...(facts.phase === "terminal" ? [
          { label: "input-summary", node: summaries[0] || null },
          { label: "final", node: finals[0] || null },
        ] : []),
      ].filter((entry) => entry.node);
      nodes.sort((left, right) => (
        left.node.compareDocumentPosition(right.node) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1
      ));
      return {
        panel: {
          visible: Boolean(panel && !panel.classList.contains("hidden")),
          cards: panel?.querySelectorAll(".user-input-card").length || 0,
          questions: panel?.querySelectorAll(`[data-question-id="${facts.questionId}"]`).length || 0,
          options: panel?.querySelectorAll('input[type="radio"]').length || 0,
          checked: panel?.querySelectorAll('input[type="radio"]:checked').length || 0,
          confirms: panel?.querySelectorAll('[data-user-input-action="confirm"]').length || 0,
        },
        messages: {
          initialUser: users.length,
          toolProcesses: processes.length,
          toolItems: process?.querySelectorAll("details.tool-process-item").length || 0,
          summaries: summaries.length,
          finals: finals.length,
        },
        tool: {
          action: String(process?.querySelector("details.tool-process-stage")?.dataset.currentAction || ""),
          argumentDetails: details.length > 0 ? 1 : 0,
          resultDetails: Math.max(0, details.length - 1),
        },
        order: nodes.map((entry) => entry.label),
      };
    },
  });
}

async function beginQuestionnaireLifecycle(h4, runtime, {
  userMarker,
  toolCallId,
  requestId,
  title,
  reason,
  assertToolArguments,
}) {
  const { page } = h4;
  await h4.open(runtime);
  await assertFrontendRuntime(page, runtime);
  if (runtime === "classic") {
    expect(await page.locator("html").getAttribute("data-code-frontend-ready")).toBeNull();
  }
  await h4.proveNonLoopbackBlocked();

  const lifecycleBoundary = h4.requestBoundary();
  const lifecycleMetricsBefore = await h4.metrics();
  await page.locator("#prompt").fill(userMarker);
  await page.locator("#sendBtn").click();
  await expect(page.locator("#messages article.msg.user").filter({ hasText: userMarker }))
    .toHaveCount(1);

  await expect.poll(() => h4.controlIds().agentRunIds.length).toBe(1);
  const agentRunId = h4.controlIds().agentRunIds[0];
  let waitingAgentResponse = null;
  await expect.poll(async () => {
    waitingAgentResponse = await fetchProductionJson(
      page,
      `/api/agent/runs/${encodeURIComponent(agentRunId)}?cursor=0&wait=0`,
    );
    return {
      status: waitingAgentResponse.body?.status,
      eventTypes: (waitingAgentResponse.body?.events || []).map((event) => event.type),
      requestIdMatches: waitingAgentResponse.body?.pendingInput?.requestId === requestId,
      executionStatuses: (waitingAgentResponse.body?.toolExecutions || [])
        .map((execution) => execution.status),
    };
  }).toEqual({
    status: "waiting_user_input",
    eventTypes: [
      "created",
      "model_started",
      "model_completed",
      "tool_started",
      "user_input_required",
    ],
    requestIdMatches: true,
    executionStatuses: ["waiting_user_input"],
  });
  expect(waitingAgentResponse.status).toBe(200);
  const waitingAgent = waitingAgentResponse.body;
  expect(waitingAgent.pendingInput).toMatchObject({
    requestId,
    toolCallId,
    title,
    reason,
  });
  expect(waitingAgent.pendingToolCalls).toHaveLength(1);
  expect(waitingAgent.activeRuntimeRunId).toBe("");
  assertToolArguments({
    title: waitingAgent.pendingInput.title,
    reason: waitingAgent.pendingInput.reason,
    questions: waitingAgent.pendingInput.questions,
  });

  const firstRuntimeRunId = String(
    waitingAgent.events.find((event) => event?.type === "model_started")?.data?.runtimeRunId || "",
  );
  expect(firstRuntimeRunId).not.toBe("");
  const firstRuntimeResponse = await fetchProductionJson(
    page,
    `/api/runtime/runs/${encodeURIComponent(firstRuntimeRunId)}?cursor=0&wait=0`,
  );
  expect(firstRuntimeResponse.status).toBe(200);
  expect(firstRuntimeResponse.body).toMatchObject({
    runId: firstRuntimeRunId,
    status: "completed",
  });
  expect(firstRuntimeResponse.body.nextCursor).toBeGreaterThan(0);
  expect(firstRuntimeResponse.body.events).toHaveLength(firstRuntimeResponse.body.nextCursor);
  expect(firstRuntimeResponse.body.result).toMatchObject({
    content: "",
    finishReason: "tool_calls",
  });
  expect(firstRuntimeResponse.body.result?.toolCalls).toHaveLength(1);
  expect(firstRuntimeResponse.body.result?.toolCalls?.[0]).toMatchObject({
    id: toolCallId,
    function: { name: "request_user_input" },
  });
  assertToolArguments(firstRuntimeResponse.body.result?.toolCalls?.[0]?.function?.arguments);

  const sessionButton = page.locator("#sessionList .session-row.active button.session-main");
  await expect(sessionButton).toHaveCount(1);
  const sessionId = await sessionButton.getAttribute("data-session-id");
  expect(sessionId).toBeTruthy();
  return {
    page,
    runtime,
    lifecycleBoundary,
    lifecycleMetricsBefore,
    agentRunId,
    waitingAgentResponse,
    waitingAgent,
    firstRuntimeRunId,
    firstRuntimeResponse,
    sessionId,
  };
}

async function completeQuestionnaireLifecycle(h4, started, {
  finalMarker,
  toolCallId,
  submissionBoundary,
  submissionMetricsBefore,
}) {
  const { page, agentRunId, sessionId } = started;
  const final = page.locator("#messages article.msg.assistant").filter({ hasText: finalMarker });
  await expect(final).toHaveCount(1);
  let completedAgentResponse = null;
  await expect.poll(async () => {
    completedAgentResponse = await fetchProductionJson(
      page,
      `/api/agent/runs/${encodeURIComponent(agentRunId)}?cursor=0&wait=0`,
    );
    return {
      status: completedAgentResponse.body?.status,
      eventTypes: (completedAgentResponse.body?.events || []).map((event) => event.type),
      pendingInput: completedAgentResponse.body?.pendingInput ?? null,
    };
  }).toEqual({
    status: "completed",
    eventTypes: [
      "created",
      "model_started",
      "model_completed",
      "tool_started",
      "user_input_required",
      "user_input_submitted",
      "tool_completed",
      "waiting_credentials",
      "resumed",
      "model_started",
      "model_completed",
      "completed",
    ],
    pendingInput: null,
  });
  expect(completedAgentResponse.status).toBe(200);
  const completedAgent = completedAgentResponse.body;
  expect(completedAgent.agentRunId).toBe(agentRunId);
  expect(completedAgent.activeRuntimeRunId).toBe("");
  expect(completedAgent.pendingToolCalls).toEqual([]);
  expect(completedAgent.result?.content).toBe(finalMarker);

  const runtimeRunIds = completedAgent.events
    .filter((event) => event?.type === "model_started")
    .map((event) => String(event?.data?.runtimeRunId || ""));
  expect(runtimeRunIds).toHaveLength(2);
  expect(new Set(runtimeRunIds).size).toBe(2);
  const runtimeSnapshots = [];
  for (const runtimeRunId of runtimeRunIds) {
    const response = await fetchProductionJson(
      page,
      `/api/runtime/runs/${encodeURIComponent(runtimeRunId)}?cursor=0&wait=0`,
    );
    expect(response.status).toBe(200);
    expect(response.body.status).toBe("completed");
    expect(response.body.nextCursor).toBeGreaterThan(0);
    expect(response.body.events).toHaveLength(response.body.nextCursor);
    runtimeSnapshots.push(response.body);
  }

  let terminalSessionResponse = null;
  await expect.poll(async () => {
    terminalSessionResponse = await fetchProductionJson(
      page,
      `/api/sessions/${encodeURIComponent(sessionId)}`,
    );
    return {
      status: terminalSessionResponse.status,
      roles: (terminalSessionResponse.body?.messages || []).map((message) => message.role),
      runStateKeys: Object.keys(terminalSessionResponse.body?.runState || {}).sort(),
    };
  }).toEqual({
    status: 200,
    roles: ["user", "assistant", "tool-call", "user", "tool-result", "assistant"],
    runStateKeys: [],
  });
  const terminalToolOwner = terminalSessionResponse.body.messages[1];
  expect(terminalToolOwner.meta?.toolCalls).toHaveLength(1);
  expect(terminalToolOwner.meta.toolCalls[0]).toMatchObject({
    id: toolCallId,
    function: { name: "request_user_input" },
  });
  const terminalFinalAssistant = terminalSessionResponse.body.messages[5];
  expect(terminalFinalAssistant).toMatchObject({ role: "assistant", content: finalMarker });
  expect(terminalFinalAssistant.meta?.toolCalls).toEqual([]);
  const metricsAtTerminal = await h4.metrics();
  const submissionRequests = questionnaireRequestProjection(
    h4,
    submissionBoundary,
    submissionMetricsBefore,
    metricsAtTerminal,
  );
  expect(submissionRequests).toEqual({
    agentRunPost: 0,
    runtimePost: 0,
    agentDelete: 0,
    inputPost: 1,
    resumePost: 1,
    browserProxyChatPost: 0,
    browserToolPost: 0,
    upstreamChatDelta: 1,
    productionDelegationDelta: 0,
    productionToolExecutionDelta: 0,
  });
  const totalRequests = questionnaireRequestProjection(
    h4,
    started.lifecycleBoundary,
    started.lifecycleMetricsBefore,
    metricsAtTerminal,
  );
  expect(totalRequests).toEqual({
    agentRunPost: 1,
    runtimePost: 0,
    agentDelete: 0,
    inputPost: 1,
    resumePost: 1,
    browserProxyChatPost: 0,
    browserToolPost: 0,
    upstreamChatDelta: 2,
    productionDelegationDelta: 0,
    productionToolExecutionDelta: 0,
  });
  return {
    final,
    completedAgentResponse,
    completedAgent,
    runtimeRunIds,
    runtimeSnapshots,
    terminalSessionResponse,
    terminalToolOwner,
    terminalFinalAssistant,
    metricsAtTerminal,
    submissionRequests,
    totalRequests,
  };
}

async function reloadCompletedQuestionnaireLifecycle(h4, started, completed) {
  const { page, runtime, agentRunId, sessionId } = started;
  const terminalRefreshBoundary = h4.requestBoundary();
  await h4.reloadRuntime(runtime);
  const agentAfterReload = await fetchProductionJson(
    page,
    `/api/agent/runs/${encodeURIComponent(agentRunId)}?cursor=0&wait=0`,
  );
  expect(agentAfterReload.status).toBe(200);
  expect(agentAfterReload.body.agentRunId).toBe(agentRunId);
  const sessionAfterReload = await fetchProductionJson(
    page,
    `/api/sessions/${encodeURIComponent(sessionId)}`,
  );
  expect(sessionAfterReload.status).toBe(200);
  expect(Object.keys(sessionAfterReload.body.runState || {})).toEqual([]);
  const runtimeSnapshotsAfterReload = [];
  for (const runtimeRunId of completed.runtimeRunIds) {
    const response = await fetchProductionJson(
      page,
      `/api/runtime/runs/${encodeURIComponent(runtimeRunId)}?cursor=0&wait=0`,
    );
    expect(response.status).toBe(200);
    expect(response.body.runId).toBe(runtimeRunId);
    runtimeSnapshotsAfterReload.push(response.body);
  }
  const metricsAfterTerminalReload = await h4.metrics();
  expect(metricsAfterTerminalReload.chatRequests).toEqual(
    completed.metricsAtTerminal.chatRequests,
  );
  expect(metricsAfterTerminalReload.toolExecutions).toEqual(
    completed.metricsAtTerminal.toolExecutions,
  );
  const terminalReloadRequests = questionnaireRequestProjection(
    h4,
    terminalRefreshBoundary,
    completed.metricsAtTerminal,
    metricsAfterTerminalReload,
  );
  expect(terminalReloadRequests).toEqual({
    agentRunPost: 0,
    runtimePost: 0,
    agentDelete: 0,
    inputPost: 0,
    resumePost: 0,
    browserProxyChatPost: 0,
    browserToolPost: 0,
    upstreamChatDelta: 0,
    productionDelegationDelta: 0,
    productionToolExecutionDelta: 0,
  });
  expect(new Set(h4.controlIds().agentRunIds)).toEqual(new Set([agentRunId]));
  expect(new Set(h4.controlIds().runtimeRunIds)).toEqual(
    new Set(completed.runtimeRunIds),
  );
  expect(h4.pageErrors).toEqual([]);
  return {
    terminalRefreshBoundary,
    agentAfterReload,
    sessionAfterReload,
    runtimeSnapshotsAfterReload,
    metricsAfterTerminalReload,
    terminalReloadRequests,
  };
}

function queueQuestionnaireMessageHasMarker(message, marker) {
  if (typeof message?.content === "string") return message.content === marker;
  return Array.isArray(message?.content)
    && message.content.some((item) => item?.type === "text" && item.text === marker);
}

function queueQuestionnaireSteerPostCount(entries) {
  return (Array.isArray(entries) ? entries : []).filter((entry) => (
    entry?.method === "POST"
    && /^\/api\/agent\/runs\/[^/]+\/steer$/.test(String(entry?.path || ""))
  )).length;
}

function queueQuestionnaireIdentity(session) {
  const messages = Array.isArray(session?.messages) ? session.messages : [];
  const runState = session?.runState && typeof session.runState === "object"
    ? session.runState
    : {};
  const queuedUsers = messages.filter((message) => (
    message?.role === "user"
    && queueQuestionnaireMessageHasMarker(message, TIMING_QUEUE_USER)
  ));
  const checkpoints = (Array.isArray(runState.queuedMessages) ? runState.queuedMessages : [])
    .filter((item) => item?.userText === TIMING_QUEUE_USER);
  return {
    queuedUsers,
    checkpoints,
    dispatchId: String(queuedUsers[0]?.meta?.queuedDispatch?.id || ""),
    checkpointId: String(checkpoints[0]?.id || ""),
    clientRequestId: String(checkpoints[0]?.clientRequestId || ""),
  };
}

function waitingQueueSessionProjection(session, mainAgentRunId, firstRuntimeRunId) {
  const identity = queueQuestionnaireIdentity(session);
  const runState = session?.runState || {};
  const forbiddenIdentities = new Set([
    String(mainAgentRunId || ""),
    String(firstRuntimeRunId || ""),
    QUESTIONNAIRE_REQUEST_ID,
    QUESTIONNAIRE_TOOL_CALL_ID,
  ].filter(Boolean));
  const queueIdentities = [identity.dispatchId, identity.checkpointId, identity.clientRequestId];
  return {
    roles: (session?.messages || []).map((message) => String(message?.role || "")),
    queue: {
      queuedUserCount: identity.queuedUsers.length,
      checkpointCount: identity.checkpoints.length,
      dispatchStatus: String(identity.queuedUsers[0]?.meta?.queuedDispatch?.status || ""),
      checkpointStatus: String(identity.checkpoints[0]?.status || ""),
      detachedFromMain: identity.queuedUsers[0]?.meta?.detachedFromMain === true,
      identityClosed: Boolean(identity.dispatchId)
        && queueIdentities.every((value) => value === identity.dispatchId),
      identityDisjoint: queueIdentities.every((value) => (
        Boolean(value) && !forbiddenIdentities.has(value)
      )),
    },
    runState: {
      status: String(runState.status || ""),
      phase: String(runState.phase || ""),
      executionOwner: String(runState.executionOwner || ""),
      mainAgentRunMatches: String(runState.agentRunId || "") === mainAgentRunId,
      runtimeRunCleared: !String(runState.runtimeRunId || ""),
      cursor: Number(runState.agentEventCursor || 0),
      modelRound: Number(runState.modelRound || 0),
      queueCount: Array.isArray(runState.queuedMessages) ? runState.queuedMessages.length : 0,
      questionnaireIdentityMatches: String(runState.userInputRequest?.id || "")
        === QUESTIONNAIRE_REQUEST_ID
        && String(runState.userInputRequest?.toolCallId || "") === QUESTIONNAIRE_TOOL_CALL_ID
        && String(runState.userInputRequest?.agentRunId || "") === mainAgentRunId,
    },
  };
}

function terminalQueueSessionProjection(session, queueItemId, queuedAgent) {
  const identity = queueQuestionnaireIdentity(session);
  const queuedFinals = (session?.messages || []).filter((message) => (
    message?.role === "assistant"
    && queueQuestionnaireMessageHasMarker(message, TIMING_QUEUE_FINAL)
  ));
  return {
    runStateCleared: Object.keys(session?.runState || {}).length === 0,
    queuedUserCount: identity.queuedUsers.length,
    queuedFinalCount: queuedFinals.length,
    checkpointCount: identity.checkpoints.length,
    dispatchStatus: String(identity.queuedUsers[0]?.meta?.queuedDispatch?.status || ""),
    detachedFromMain: identity.queuedUsers[0]?.meta?.detachedFromMain === true,
    queueIdentityRetained: Boolean(queueItemId) && identity.dispatchId === queueItemId,
    clientRequestMatches: Boolean(queueItemId)
      && String(queuedAgent?.clientRequestId || "") === queueItemId,
  };
}

function queueQuestionnaireSessionRoleProjection(messages) {
  const source = Array.isArray(messages) ? messages : [];
  const normalized = source.map((message) => (
    message?.role === "user"
      && queueQuestionnaireMessageHasMarker(message, QUEUE_QUESTIONNAIRE_USER)
      ? { ...message, content: QUESTIONNAIRE_USER }
      : message
  ));
  return questionnaireSessionRoleProjection(normalized).map((item, index) => {
    const message = source[index];
    if (message?.role === "user" && queueQuestionnaireMessageHasMarker(message, TIMING_QUEUE_USER)) {
      return { role: "user", kind: "queued-user" };
    }
    if (
      message?.role === "assistant"
      && queueQuestionnaireMessageHasMarker(message, TIMING_QUEUE_FINAL)
    ) {
      return { role: "assistant", kind: "queued-final" };
    }
    return item;
  });
}

async function queueQuestionnaireDomProjection(h4, phase) {
  const expected = phase === "waiting" ? {
    counts: {
      mainUser: 1,
      toolProcess: 1,
      inputSummary: 0,
      mainFinal: 0,
      queuedUser: 1,
      queuedFinal: 0,
      queuedDataId: 1,
    },
    order: ["main-user", "tool-process", "queued-user"],
  } : {
    counts: {
      mainUser: 1,
      toolProcess: 1,
      inputSummary: 1,
      mainFinal: 1,
      queuedUser: 1,
      queuedFinal: 1,
      queuedDataId: 1,
    },
    order: [
      "main-user",
      "tool-process",
      "input-summary",
      "main-final",
      "queued-user",
      "queued-final",
    ],
  };
  return waitForMessageProjection(h4, {
    label: `queue-questionnaire-${phase}`,
    expected,
    sourceFacts: {
      phase,
      mainUserMarker: QUEUE_QUESTIONNAIRE_USER,
      mainFinalMarker: QUESTIONNAIRE_FINAL,
      queuedUserMarker: TIMING_QUEUE_USER,
      queuedFinalMarker: TIMING_QUEUE_FINAL,
      promptMarker: QUESTIONNAIRE_PROMPT,
      selectedLabel: QUESTIONNAIRE_OPTION_B.label,
    },
    sample: (facts) => {
      const root = document.querySelector("#messages");
      const mainUsers = [...root.querySelectorAll("article.msg.user")]
        .filter((node) => node.textContent.includes(facts.mainUserMarker));
      const processes = [...root.querySelectorAll(
        'article.tool-process > details.tool-process-stage[data-current-action="request_user_input"]',
      )].map((stage) => stage.closest("article.tool-process"));
      const summaries = [...root.querySelectorAll("article.user-input-flow")]
        .filter((node) => (
          node.textContent.includes(facts.promptMarker)
          && node.textContent.includes(facts.selectedLabel)
        ));
      const mainFinals = [...root.querySelectorAll("article.msg.assistant")]
        .filter((node) => node.textContent.includes(facts.mainFinalMarker));
      const queuedUsers = [...root.querySelectorAll("article.msg.user")]
        .filter((node) => node.textContent.includes(facts.queuedUserMarker));
      const queuedFinals = [...root.querySelectorAll("article.msg.assistant")]
        .filter((node) => node.textContent.includes(facts.queuedFinalMarker));
      const nodes = [
        { label: "main-user", node: mainUsers[0] || null },
        { label: "tool-process", node: processes[0] || null },
        { label: "input-summary", node: summaries[0] || null },
        { label: "main-final", node: mainFinals[0] || null },
        { label: "queued-user", node: queuedUsers[0] || null },
        { label: "queued-final", node: queuedFinals[0] || null },
      ].filter((entry) => entry.node);
      nodes.sort((left, right) => (
        left.node.compareDocumentPosition(right.node) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1
      ));
      return {
        counts: {
          mainUser: mainUsers.length,
          toolProcess: processes.length,
          inputSummary: summaries.length,
          mainFinal: mainFinals.length,
          queuedUser: queuedUsers.length,
          queuedFinal: queuedFinals.length,
          queuedDataId: queuedUsers.filter((node) => Boolean(node.dataset.queuedMessageId)).length,
        },
        order: nodes.map((entry) => entry.label),
      };
    },
  });
}

async function submitQuestionnaireQueueBridge(h4, started, metricsBefore) {
  const { page, sessionId, agentRunId, firstRuntimeRunId } = started;
  const requestBoundary = h4.requestBoundary();
  const queueSaves = [];
  const recordSessionSave = (request) => {
    if (request.method() !== "PUT") return;
    if (!/^\/api\/sessions\/[^/]+$/.test(new URL(request.url()).pathname)) return;
    let payload = null;
    try {
      payload = JSON.parse(request.postData() || "null");
    } catch {}
    const identity = queueQuestionnaireIdentity(payload);
    if (!identity.queuedUsers.length && !identity.checkpoints.length) return;
    queueSaves.push({
      queuedUserCount: identity.queuedUsers.length,
      checkpointCount: identity.checkpoints.length,
      identityClosed: Boolean(identity.dispatchId)
        && identity.dispatchId === identity.checkpointId
        && identity.dispatchId === identity.clientRequestId,
      status: String(payload?.runState?.status || ""),
      phase: String(payload?.runState?.phase || ""),
      mainAgentRunMatches: String(payload?.runState?.agentRunId || "") === agentRunId,
    });
  };
  page.on("request", recordSessionSave);
  let sessionResponse = null;
  try {
    const prompt = page.locator("#prompt");
    await prompt.fill(TIMING_QUEUE_USER);
    await expect(prompt).toBeEnabled();
    await expect(prompt).toBeFocused();
    await expect(prompt).toHaveValue(TIMING_QUEUE_USER);
    await prompt.press("Control+Enter");
    const interaction = {
      source: "real-composer",
      chord: "Control+Enter",
      pressCount: 1,
    };

    let waitingProjection = null;
    await expect.poll(async () => {
      sessionResponse = await fetchProductionJson(
        page,
        `/api/sessions/${encodeURIComponent(sessionId)}`,
      );
      waitingProjection = waitingQueueSessionProjection(
        sessionResponse.body,
        agentRunId,
        firstRuntimeRunId,
      );
      return { status: sessionResponse.status, projection: waitingProjection };
    }).toEqual({
      status: 200,
      projection: {
        roles: ["user", "assistant", "tool-call", "user"],
        queue: {
          queuedUserCount: 1,
          checkpointCount: 1,
          dispatchStatus: "pending",
          checkpointStatus: "pending",
          detachedFromMain: true,
          identityClosed: true,
          identityDisjoint: true,
        },
        runState: {
          status: "waiting-user-input",
          phase: "tools",
          executionOwner: "server-agent",
          mainAgentRunMatches: true,
          runtimeRunCleared: true,
          cursor: started.waitingAgent.nextCursor,
          modelRound: 1,
          queueCount: 1,
          questionnaireIdentityMatches: true,
        },
      },
    });
    await expect.poll(() => queueSaves).toEqual([{
      queuedUserCount: 1,
      checkpointCount: 1,
      identityClosed: true,
      status: "waiting-user-input",
      phase: "tools",
      mainAgentRunMatches: true,
    }]);
    const identity = queueQuestionnaireIdentity(sessionResponse.body);
    expect(identity.dispatchId).not.toBe("");
    const queuedUser = page.locator("#messages article.msg.user")
      .filter({ hasText: TIMING_QUEUE_USER });
    await expect(queuedUser).toHaveCount(1);
    await expect(queuedUser).toHaveAttribute("data-queued-message-id", identity.dispatchId);

    const metricsAfter = await h4.metrics();
    expect(metricsAfter.chatRequests).toEqual(metricsBefore.chatRequests);
    expect(metricsAfter.toolExecutions).toEqual(metricsBefore.toolExecutions);
    const requests = questionnaireRequestProjection(
      h4,
      requestBoundary,
      metricsBefore,
      metricsAfter,
    );
    const steerPost = queueQuestionnaireSteerPostCount(
      h4.loopbackRequests.slice(requestBoundary),
    );
    expect(steerPost).toBe(0);
    expect(requests).toEqual({
      agentRunPost: 0,
      runtimePost: 0,
      agentDelete: 0,
      inputPost: 0,
      resumePost: 0,
      browserProxyChatPost: 0,
      browserToolPost: 0,
      upstreamChatDelta: 0,
      productionDelegationDelta: 0,
      productionToolExecutionDelta: 0,
    });
    expect(h4.controlIds()).toEqual({
      agentRunIds: [agentRunId],
      runtimeRunIds: [firstRuntimeRunId],
    });
    return {
      queueItemId: identity.dispatchId,
      sessionResponse,
      metricsAfter,
      projection: {
        interaction,
        saveCount: queueSaves.length,
        save: queueSaves[0],
        requests,
        steerPost,
        queue: waitingProjection.queue,
      },
      waitingSession: waitingProjection,
    };
  } finally {
    page.off("request", recordSessionSave);
    h4.diagnosticSteps.push({
      step: "questionnaire-queue-submit",
      saveCount: queueSaves.length,
      saves: queueSaves,
    });
  }
}

function startQuestionnaireQueuePromotionObservation(page) {
  const timeline = [];
  const counts = { checkpointClearedSaves: 0, queuePromotionPosts: 0 };
  const observeRequest = (request) => {
    const requestUrl = new URL(request.url());
    if (request.method() === "POST" && requestUrl.pathname === "/api/agent/runs") {
      counts.queuePromotionPosts += 1;
      timeline.push({ sequence: timeline.length + 1, type: "queue-promoted" });
      return;
    }
    if (request.method() !== "PUT" || !/^\/api\/sessions\/[^/]+$/.test(requestUrl.pathname)) {
      return;
    }
    let payload = null;
    try {
      payload = JSON.parse(request.postData() || "null");
    } catch {}
    const messages = Array.isArray(payload?.messages) ? payload.messages : [];
    const runState = payload?.runState || {};
    const mainFinalPresent = messages.some((message) => (
      message?.role === "assistant"
      && queueQuestionnaireMessageHasMarker(message, QUESTIONNAIRE_FINAL)
    ));
    const queuePending = (Array.isArray(runState.queuedMessages) ? runState.queuedMessages : [])
      .filter((item) => item?.userText === TIMING_QUEUE_USER && item?.status === "pending")
      .length === 1;
    const foregroundCleared = !String(runState.status || "")
      && !String(runState.agentRunId || "")
      && !String(runState.runtimeRunId || "");
    if (mainFinalPresent && queuePending && foregroundCleared) {
      counts.checkpointClearedSaves += 1;
      if (!timeline.some((entry) => entry.type === "main-terminal-checkpoint-cleared")) {
        timeline.push({
          sequence: timeline.length + 1,
          type: "main-terminal-checkpoint-cleared",
        });
      }
    }
  };
  page.on("request", observeRequest);
  return {
    timeline,
    counts,
    stop() {
      page.off("request", observeRequest);
    },
  };
}

function queuedAgentEventProjection(snapshot) {
  const events = Array.isArray(snapshot?.events) ? snapshot.events : [];
  const runtimeIds = events
    .filter((event) => event?.type === "model_started")
    .map((event) => String(event?.data?.runtimeRunId || ""));
  const runtimeAliases = new Map(runtimeIds.map((runId, index) => [runId, `runtime-${index + 1}`]));
  return events.map((event) => {
    const data = event?.data || {};
    const projected = { seq: Number(event?.seq || 0), type: String(event?.type || "") };
    if (data.round != null) projected.round = Number(data.round);
    if (data.runtimeRunId) {
      projected.runtimeRunId = runtimeAliases.get(String(data.runtimeRunId)) || "mismatch";
    }
    if (data.content != null) {
      projected.content = String(data.content) === TIMING_QUEUE_FINAL ? "queued-final" : "empty";
    }
    if (data.finishReason != null) projected.finishReason = String(data.finishReason || "");
    return projected;
  });
}

function queueQuestionnaireRuntimeProjection(entries) {
  return entries.map(({ owner, snapshot }, index) => ({
    runtime: `runtime-${index + 1}`,
    owner,
    status: String(snapshot?.status || ""),
    nextCursor: Number(snapshot?.nextCursor || 0),
    eventTypes: (snapshot?.events || []).map((event) => String(event?.type || "")),
    content: snapshot?.result?.content === QUESTIONNAIRE_FINAL
      ? "questionnaire-final"
      : snapshot?.result?.content === TIMING_QUEUE_FINAL
        ? "queued-final"
        : "empty",
    finishReason: String(snapshot?.result?.finishReason || ""),
    toolCalls: (snapshot?.result?.toolCalls || []).map((call) => ({
      toolCallMatches: String(call?.id || "") === QUESTIONNAIRE_TOOL_CALL_ID,
      name: String(call?.function?.name || ""),
      arguments: questionnaireArgumentsProjection(call?.function?.arguments),
    })),
  }));
}

async function exerciseQuestionnaireRefreshLifecycle(h4, runtime) {
  const started = await beginQuestionnaireLifecycle(h4, runtime, {
    userMarker: QUESTIONNAIRE_USER,
    toolCallId: QUESTIONNAIRE_TOOL_CALL_ID,
    requestId: QUESTIONNAIRE_REQUEST_ID,
    title: QUESTIONNAIRE_TITLE,
    reason: QUESTIONNAIRE_REASON,
    assertToolArguments: (value) => {
      expect(questionnaireArgumentsProjection(value)).toEqual({
        titleMatches: true,
        reasonMatches: true,
        questionCount: 1,
        question: {
          idMatches: true,
          promptMatches: true,
          type: "single",
          required: true,
          allowOther: false,
          options: [
            {
              value: QUESTIONNAIRE_OPTION_A.value,
              labelMatches: true,
              descriptionPresent: true,
            },
            {
              value: QUESTIONNAIRE_OPTION_B.value,
              labelMatches: true,
              descriptionPresent: true,
            },
          ],
        },
      });
    },
  });
  const {
    page,
    agentRunId,
    waitingAgent,
    sessionId,
  } = started;
  const waitingEvents = questionnaireEventProjection(waitingAgent);
  expect(waitingAgent.nextCursor).toBe(waitingEvents.at(-1)?.seq);
  expect(waitingEvents.map((event) => event.seq)).toEqual(
    waitingEvents.map((_, index) => index + 1),
  );
  const waitingExecution = questionnaireExecutionProjection(waitingAgent);
  expect(waitingExecution).toEqual([{
    toolCallMatches: true,
    name: "request_user_input",
    arguments: questionnaireArgumentsProjection({
      title: QUESTIONNAIRE_TITLE,
      reason: QUESTIONNAIRE_REASON,
      questions: waitingAgent.pendingInput.questions,
    }),
    status: "waiting_user_input",
    outcome: "",
    result: null,
    failureCountAbsent: true,
    failureSignatureAbsent: true,
  }]);

  const waitingDom = await questionnaireDomProjection(h4, "waiting");
  await expect(page.locator("#activeRunBanner.visible")).toHaveCount(1);
  await expect(page.locator("#stopBtn")).toBeEnabled();
  let waitingSessionResponse = null;
  await expect.poll(async () => {
    waitingSessionResponse = await fetchProductionJson(
      page,
      `/api/sessions/${encodeURIComponent(sessionId)}`,
    );
    return {
      status: waitingSessionResponse.status,
      roles: (waitingSessionResponse.body?.messages || []).map((message) => message.role),
      runStatus: waitingSessionResponse.body?.runState?.status,
      cursor: waitingSessionResponse.body?.runState?.agentEventCursor,
      requestId: waitingSessionResponse.body?.runState?.userInputRequest?.id,
    };
  }).toEqual({
    status: 200,
    roles: ["user", "assistant", "tool-call"],
    runStatus: "waiting-user-input",
    cursor: waitingAgent.nextCursor,
    requestId: QUESTIONNAIRE_REQUEST_ID,
  });
  const waitingSnapshot = questionnaireWaitingSnapshotProjection(
    waitingAgent,
    waitingSessionResponse.body,
    agentRunId,
  );
  expect(waitingSnapshot.agent.status).toBe("waiting_user_input");
  expect(waitingSnapshot.agent.pendingInput).toMatchObject({
    requestIdMatches: true,
    toolCallMatches: true,
    titleMatches: true,
    reasonMatches: true,
    questionCount: 1,
  });
  expect(waitingSnapshot.session.runState).toMatchObject({
    status: "waiting-user-input",
    phase: "tools",
    executionOwner: "server-agent",
    agentRunMatches: true,
    runtimeRunCleared: true,
    cursor: waitingAgent.nextCursor,
    modelRound: 1,
    request: {
      requestIdMatches: true,
      toolCallMatches: true,
      agentRunMatches: true,
      status: "pending",
      questionCount: 1,
    },
  });

  const metricsAtWaiting = await h4.metrics();
  expect(metricsAtWaiting.chatRequests).toEqual([{
    scenario: "questionnaire-call",
    stream: true,
    hasToolResult: false,
  }]);
  expect(metricsAtWaiting.toolExecutions).toEqual([]);
  expect(metricsAtWaiting.productionToolDelegations).toBe(0);
  expect(metricsAtWaiting.unsafeToolRequests).toBe(0);
  expect(metricsAtWaiting.production.agentRuns).toHaveLength(1);
  expect(metricsAtWaiting.production.runtimeRuns).toHaveLength(1);
  const waitingReloadBoundary = h4.requestBoundary();
  await h4.reloadRuntime(runtime);
  await page.locator("#baseUrl").evaluate((element, fakeUrl) => {
    element.value = fakeUrl;
  }, h4.host.ready.fakeUrl);
  await expect(page.locator("#baseUrl")).toHaveValue(h4.host.ready.fakeUrl);
  const restoredWaitingDom = await questionnaireDomProjection(h4, "waiting");
  expect(restoredWaitingDom).toEqual(waitingDom);
  await expect(page.locator("#activeRunBanner.visible")).toHaveCount(0);
  await expect(page.locator("#stopBtn")).toBeDisabled();
  const waitingAgentAfterReload = await fetchProductionJson(
    page,
    `/api/agent/runs/${encodeURIComponent(agentRunId)}?cursor=0&wait=0`,
  );
  expect(waitingAgentAfterReload.status).toBe(200);
  expect(questionnaireEventProjection(waitingAgentAfterReload.body)).toEqual(waitingEvents);
  expect(questionnaireExecutionProjection(waitingAgentAfterReload.body)).toEqual(waitingExecution);
  expect(waitingAgentAfterReload.body.pendingInput?.requestId).toBe(QUESTIONNAIRE_REQUEST_ID);
  const waitingSessionAfterReload = await fetchProductionJson(
    page,
    `/api/sessions/${encodeURIComponent(sessionId)}`,
  );
  expect(waitingSessionAfterReload.status).toBe(200);
  expect(questionnaireWaitingSnapshotProjection(
    waitingAgentAfterReload.body,
    waitingSessionAfterReload.body,
    agentRunId,
  )).toEqual(waitingSnapshot);
  const metricsAfterWaitingReload = await h4.metrics();
  expect(metricsAfterWaitingReload.chatRequests).toEqual(metricsAtWaiting.chatRequests);
  expect(metricsAfterWaitingReload.toolExecutions).toEqual(metricsAtWaiting.toolExecutions);
  expect(metricsAfterWaitingReload.productionToolDelegations)
    .toBe(metricsAtWaiting.productionToolDelegations);
  const waitingReloadRequests = questionnaireRequestProjection(
    h4,
    waitingReloadBoundary,
    metricsAtWaiting,
    metricsAfterWaitingReload,
  );
  expect(waitingReloadRequests).toEqual({
    agentRunPost: 0,
    runtimePost: 0,
    agentDelete: 0,
    inputPost: 0,
    resumePost: 0,
    browserProxyChatPost: 0,
    browserToolPost: 0,
    upstreamChatDelta: 0,
    productionDelegationDelta: 0,
    productionToolExecutionDelta: 0,
  });
  expect(waitingAgentAfterReload.body.toolExecutions).toHaveLength(1);

  const submissionBoundary = h4.requestBoundary();
  const option = page.locator(
    `#userInputPanel [data-question-id="${QUESTIONNAIRE_QUESTION_ID}"] input[type="radio"][value="${QUESTIONNAIRE_OPTION_B.value}"]`,
  );
  const confirm = page.locator(
    `#userInputPanel [data-question-id="${QUESTIONNAIRE_QUESTION_ID}"] [data-user-input-action="confirm"]`,
  );
  await expect(option).toHaveCount(1);
  await expect(option).not.toBeChecked();
  await option.check();
  await expect(option).toBeChecked();
  await expect(confirm).toHaveCount(1);
  await expect(confirm).toBeEnabled();
  await confirm.click();
  const completed = await completeQuestionnaireLifecycle(h4, started, {
    finalMarker: QUESTIONNAIRE_FINAL,
    toolCallId: QUESTIONNAIRE_TOOL_CALL_ID,
    submissionBoundary,
    submissionMetricsBefore: metricsAfterWaitingReload,
  });
  const {
    completedAgent,
    runtimeRunIds,
    runtimeSnapshots,
    terminalSessionResponse,
    metricsAtTerminal,
    submissionRequests,
    totalRequests,
  } = completed;
  const terminalEvents = questionnaireEventProjection(completedAgent);
  expect(completedAgent.nextCursor).toBe(terminalEvents.at(-1)?.seq);
  expect(terminalEvents.map((event) => event.seq)).toEqual(
    terminalEvents.map((_, index) => index + 1),
  );
  const terminalExecution = questionnaireExecutionProjection(completedAgent);
  expect(terminalExecution).toHaveLength(1);
  expect(terminalExecution[0]).toMatchObject({
    toolCallMatches: true,
    name: "request_user_input",
    status: "completed",
    outcome: "succeeded",
    failureCountAbsent: true,
    failureSignatureAbsent: true,
    result: {
      ok: true,
      action: "request_user_input",
      requestIdMatches: true,
      titleMatches: true,
      answerCount: 1,
      answer: {
        idMatches: true,
        promptMatches: true,
        type: "single",
        status: "resolved",
        values: [QUESTIONNAIRE_OPTION_B.value],
        selectedValueMatches: true,
        answerLabelMatches: true,
        otherEmpty: true,
      },
      summaryMatches: true,
      failureCountAbsent: true,
      failureSignatureAbsent: true,
      retryFieldsAbsent: true,
    },
  });
  const runtimeProjection = runtimeSnapshots.map((snapshot, index) => ({
    runtime: `runtime-${index + 1}`,
    status: String(snapshot.status || ""),
    nextCursor: Number(snapshot.nextCursor || 0),
    eventTypes: (snapshot.events || []).map((event) => String(event?.type || "")),
    content: snapshot.result?.content === QUESTIONNAIRE_FINAL ? "final" : "empty",
    finishReason: String(snapshot.result?.finishReason || ""),
    toolCalls: (snapshot.result?.toolCalls || []).map((call) => ({
      toolCallMatches: String(call?.id || "") === QUESTIONNAIRE_TOOL_CALL_ID,
      name: String(call?.function?.name || ""),
      arguments: questionnaireArgumentsProjection(call?.function?.arguments),
    })),
  }));
  expect(runtimeProjection[0]).toMatchObject({
    runtime: "runtime-1",
    status: "completed",
    content: "empty",
    finishReason: "tool_calls",
    toolCalls: [{ toolCallMatches: true, name: "request_user_input" }],
  });
  expect(runtimeProjection[1]).toMatchObject({
    runtime: "runtime-2",
    status: "completed",
    content: "final",
    finishReason: "stop",
    toolCalls: [],
  });

  const terminalDom = await questionnaireDomProjection(h4, "terminal");
  await expect(page.locator("#activeRunBanner.visible")).toHaveCount(0);
  await expect(page.locator("#stopBtn")).toBeDisabled();
  await expect(page.locator("#messages .execution-trace.active")).toHaveCount(0);
  await expect(page.locator("#messages .execution-trace.completed")).toHaveCount(1);
  const sessionRoleContent = questionnaireSessionRoleProjection(
    terminalSessionResponse.body.messages,
  );
  expect(sessionRoleContent).toEqual([
    { role: "user", kind: "initial-user" },
    { role: "assistant", kind: "tool-owner" },
    { role: "tool-call", kind: "questionnaire-call" },
    { role: "user", kind: "input-summary" },
    { role: "tool-result", kind: "questionnaire-result" },
    { role: "assistant", kind: "final" },
  ]);
  const sessionInputMeta = questionnaireSessionInputMetaProjection(
    terminalSessionResponse.body.messages,
    agentRunId,
  );
  expect(sessionInputMeta).toHaveLength(3);
  expect(sessionInputMeta.map((item) => item.role)).toEqual(["tool-call", "user", "tool-result"]);
  expect(sessionInputMeta[0]).toMatchObject({
    toolCallMatches: true,
    agentRunMatches: true,
    eventType: "tool_started",
    action: "request_user_input",
    native: true,
    replayed: false,
  });
  expect(sessionInputMeta[1]).toMatchObject({
    kind: "user-input-summary",
    system: true,
    skipApi: true,
    requestIdMatches: true,
    titleMatches: true,
  });
  expect(sessionInputMeta[2]).toMatchObject({
    toolCallMatches: true,
    agentRunMatches: true,
    eventType: "tool_completed",
    action: "request_user_input",
    native: true,
    replayed: false,
    outcome: "succeeded",
  });

  expect(metricsAtTerminal.chatRequests).toEqual([
    { scenario: "questionnaire-call", stream: true, hasToolResult: false },
    {
      scenario: "questionnaire-final",
      stream: true,
      hasToolResult: true,
      questionnaireReceipt: {
        receiptCount: 1,
        parseable: true,
        nameMatches: true,
        ok: true,
        actionMatches: true,
        requestIdMatches: true,
        titleMatches: true,
        answerCount: 1,
        questionIdMatches: true,
        promptMatches: true,
        singleChoice: true,
        resolved: true,
        valueCount: 1,
        selectedValueMatches: true,
        answerLabelMatches: true,
        otherEmpty: true,
        summaryMatches: true,
      },
    },
  ]);
  expect(metricsAtTerminal.toolExecutions).toEqual([]);
  expect(metricsAtTerminal.productionToolDelegations).toBe(0);
  expect(metricsAtTerminal.unsafeToolRequests).toBe(0);
  expect(metricsAtTerminal.production.agentRuns).toHaveLength(1);
  expect(metricsAtTerminal.production.runtimeRuns).toHaveLength(2);
  const terminalReload = await reloadCompletedQuestionnaireLifecycle(h4, started, completed);
  const restoredTerminalDom = await questionnaireDomProjection(h4, "terminal");
  expect(restoredTerminalDom).toEqual(terminalDom);
  const {
    agentAfterReload,
    sessionAfterReload,
    runtimeSnapshotsAfterReload,
    terminalReloadRequests,
  } = terminalReload;
  expect(questionnaireEventProjection(agentAfterReload.body)).toEqual(terminalEvents);
  expect(questionnaireExecutionProjection(agentAfterReload.body)).toEqual(terminalExecution);
  expect(questionnaireSessionRoleProjection(sessionAfterReload.body.messages))
    .toEqual(sessionRoleContent);
  expect(questionnaireSessionInputMetaProjection(sessionAfterReload.body.messages, agentRunId))
    .toEqual(sessionInputMeta);
  const runtimeProjectionAfterReload = runtimeSnapshotsAfterReload.map((snapshot) => ({
    status: String(snapshot?.status || ""),
    nextCursor: Number(snapshot?.nextCursor || 0),
    eventTypes: (snapshot?.events || []).map((event) => String(event?.type || "")),
    content: snapshot?.result?.content === QUESTIONNAIRE_FINAL ? "final" : "empty",
    finishReason: String(snapshot?.result?.finishReason || ""),
    toolCallCount: (snapshot?.result?.toolCalls || []).length,
  }));
  expect(runtimeProjectionAfterReload).toEqual(runtimeProjection.map((snapshot) => ({
    status: snapshot.status,
    nextCursor: snapshot.nextCursor,
    eventTypes: snapshot.eventTypes,
    content: snapshot.content,
    finishReason: snapshot.finishReason,
    toolCallCount: snapshot.toolCalls.length,
  })));

  const inputSubmissionProjection = {
    requests: submissionRequests,
    events: terminalEvents.slice(waitingEvents.length, 9),
    execution: terminalExecution,
    sameAgentRun: completedAgent.agentRunId === waitingAgent.agentRunId,
    interactionExecutionCount: completedAgent.toolExecutions.length,
  };
  const refreshLifecycle = {
    waiting: {
      sameAgentRun: waitingAgentAfterReload.body.agentRunId === agentRunId,
      sameRequest: waitingAgentAfterReload.body.pendingInput?.requestId === QUESTIONNAIRE_REQUEST_ID,
      sameSnapshot: JSON.stringify(questionnaireWaitingSnapshotProjection(
        waitingAgentAfterReload.body,
        waitingSessionAfterReload.body,
        agentRunId,
      )) === JSON.stringify(waitingSnapshot),
      dom: restoredWaitingDom,
      requests: waitingReloadRequests,
      interactionExecutionDelta: waitingAgentAfterReload.body.toolExecutions.length
        - waitingAgent.toolExecutions.length,
    },
    terminal: {
      sameAgentRun: agentAfterReload.body.agentRunId === agentRunId,
      sameEvents: JSON.stringify(questionnaireEventProjection(agentAfterReload.body))
        === JSON.stringify(terminalEvents),
      sameSession: JSON.stringify(questionnaireSessionRoleProjection(sessionAfterReload.body.messages))
        === JSON.stringify(sessionRoleContent),
      sameInputMeta: JSON.stringify(
        questionnaireSessionInputMetaProjection(sessionAfterReload.body.messages, agentRunId),
      ) === JSON.stringify(sessionInputMeta),
      dom: restoredTerminalDom,
      requests: terminalReloadRequests,
      interactionExecutionDelta: agentAfterReload.body.toolExecutions.length
        - completedAgent.toolExecutions.length,
    },
  };
  const hashes = {
    waitingEventProjection: canonicalHash(waitingEvents),
    waitingSnapshot: canonicalHash(waitingSnapshot),
    inputSubmissionProjection: canonicalHash(inputSubmissionProjection),
    runtimeProjection: canonicalHash(runtimeProjection),
    sessionRoleContent: canonicalHash(sessionRoleContent),
    sessionInputMeta: canonicalHash(sessionInputMeta),
    waitingDom: canonicalHash(waitingDom),
    terminalDom: canonicalHash(terminalDom),
    refreshLifecycle: canonicalHash(refreshLifecycle),
  };
  if (Object.values(H4_8A_SEMANTIC_HASHES).every(Boolean)) {
    expect(hashes).toEqual(H4_8A_SEMANTIC_HASHES);
  } else {
    expect(runtime).toBe("bundle");
  }
  h4.evidence(`${runtime}-questionnaire-refresh-submit-continue`, {
    runtime,
    counts: {
      agentRuns: metricsAtTerminal.production.agentRuns.length,
      runtimes: metricsAtTerminal.production.runtimeRuns.length,
      upstreamChat: metricsAtTerminal.chatRequests.length,
      inputPost: totalRequests.inputPost,
      resumePost: totalRequests.resumePost,
      registeredDelegations: metricsAtTerminal.productionToolDelegations,
      registeredExecutions: metricsAtTerminal.toolExecutions.length,
      interactionExecutions: completedAgent.toolExecutions.length,
    },
    events: terminalEvents.map((event) => event.type),
    runtimeCursors: runtimeProjection.map((snapshot) => snapshot.nextCursor),
    waitingReload: waitingReloadRequests,
    terminalReload: terminalReloadRequests,
    hashes,
  });
}

async function exerciseQuestionnaireQueueRefreshLifecycle(h4, runtime) {
  expect(Object.keys(H4_8E_SEMANTIC_HASHES)).toEqual(H4_8E_SEMANTIC_HASH_KEYS);
  const configuredHashes = Object.values(H4_8E_SEMANTIC_HASHES);
  const bootstrapMode = configuredHashes.every((value) => value === "");
  const frozenMode = configuredHashes.every((value) => /^[a-f0-9]{64}$/.test(value));
  expect(bootstrapMode || frozenMode).toBe(true);
  if (bootstrapMode) expect(runtime).toBe("bundle");

  const started = await beginQuestionnaireLifecycle(h4, runtime, {
    userMarker: QUEUE_QUESTIONNAIRE_USER,
    toolCallId: QUESTIONNAIRE_TOOL_CALL_ID,
    requestId: QUESTIONNAIRE_REQUEST_ID,
    title: QUESTIONNAIRE_TITLE,
    reason: QUESTIONNAIRE_REASON,
    assertToolArguments: (value) => {
      const projection = questionnaireArgumentsProjection(value);
      expect(projection).toMatchObject({
        titleMatches: true,
        reasonMatches: true,
        questionCount: 1,
        question: {
          idMatches: true,
          promptMatches: true,
          type: "single",
          required: true,
          allowOther: false,
        },
      });
      expect(projection.question.options).toHaveLength(2);
    },
  });
  const {
    page,
    agentRunId,
    firstRuntimeRunId,
    waitingAgent,
    sessionId,
  } = started;
  const waitingEvents = questionnaireEventProjection(waitingAgent);
  expect(waitingEvents.map((event) => event.type)).toEqual([
    "created",
    "model_started",
    "model_completed",
    "tool_started",
    "user_input_required",
  ]);
  expect(waitingAgent.nextCursor).toBe(waitingEvents.at(-1)?.seq);
  expect(waitingEvents.map((event) => event.seq)).toEqual(
    waitingEvents.map((_, index) => index + 1),
  );
  const waitingExecution = questionnaireExecutionProjection(waitingAgent);
  expect(waitingExecution).toEqual([{
    toolCallMatches: true,
    name: "request_user_input",
    arguments: questionnaireArgumentsProjection({
      title: QUESTIONNAIRE_TITLE,
      reason: QUESTIONNAIRE_REASON,
      questions: waitingAgent.pendingInput.questions,
    }),
    status: "waiting_user_input",
    outcome: "",
    result: null,
    failureCountAbsent: true,
    failureSignatureAbsent: true,
  }]);
  const waitingQuestionnaireDom = await questionnaireDomProjection(h4, "waiting");

  let waitingSessionResponse = null;
  await expect.poll(async () => {
    waitingSessionResponse = await fetchProductionJson(
      page,
      `/api/sessions/${encodeURIComponent(sessionId)}`,
    );
    return {
      status: waitingSessionResponse.status,
      roles: (waitingSessionResponse.body?.messages || []).map((message) => message.role),
      runStatus: waitingSessionResponse.body?.runState?.status,
      cursor: waitingSessionResponse.body?.runState?.agentEventCursor,
      requestId: waitingSessionResponse.body?.runState?.userInputRequest?.id,
    };
  }).toEqual({
    status: 200,
    roles: ["user", "assistant", "tool-call"],
    runStatus: "waiting-user-input",
    cursor: waitingAgent.nextCursor,
    requestId: QUESTIONNAIRE_REQUEST_ID,
  });
  const waitingQuestionnaireSnapshot = questionnaireWaitingSnapshotProjection(
    waitingAgent,
    waitingSessionResponse.body,
    agentRunId,
  );
  const initialQueueContext = {
    questionnaireUserCount: 1,
    questionnaireFinalCount: 0,
    queuedUserCount: 0,
    markerOrder: ["questionnaire-user"],
    mainFinalPrecedesQueuedUser: false,
  };
  const metricsAtWaiting = await h4.metrics();
  expect(metricsAtWaiting.chatRequests).toEqual([{
    scenario: "queue-questionnaire-call",
    stream: true,
    hasToolResult: false,
    queueContext: initialQueueContext,
  }]);

  const queueBridge = await submitQuestionnaireQueueBridge(h4, started, metricsAtWaiting);
  expect(await questionnaireDomProjection(h4, "waiting")).toEqual(waitingQuestionnaireDom);
  const waitingQueueDom = await queueQuestionnaireDomProjection(h4, "waiting");
  const waitingDom = {
    questionnaire: waitingQuestionnaireDom,
    queue: waitingQueueDom,
  };

  const waitingReloadBoundary = h4.requestBoundary();
  await h4.reloadRuntime(runtime);
  await page.locator("#baseUrl").evaluate((element, fakeUrl) => {
    element.value = fakeUrl;
  }, h4.host.ready.fakeUrl);
  await expect(page.locator("#baseUrl")).toHaveValue(h4.host.ready.fakeUrl);
  const restoredWaitingQuestionnaireDom = await questionnaireDomProjection(h4, "waiting");
  const restoredWaitingQueueDom = await queueQuestionnaireDomProjection(h4, "waiting");
  expect({
    questionnaire: restoredWaitingQuestionnaireDom,
    queue: restoredWaitingQueueDom,
  }).toEqual(waitingDom);
  await expect(page.locator("#activeRunBanner.visible")).toHaveCount(0);
  await expect(page.locator("#stopBtn")).toBeDisabled();

  const waitingAgentAfterReload = await fetchProductionJson(
    page,
    `/api/agent/runs/${encodeURIComponent(agentRunId)}?cursor=0&wait=0`,
  );
  expect(waitingAgentAfterReload.status).toBe(200);
  expect(questionnaireEventProjection(waitingAgentAfterReload.body)).toEqual(waitingEvents);
  expect(questionnaireExecutionProjection(waitingAgentAfterReload.body)).toEqual(waitingExecution);
  expect(waitingAgentAfterReload.body.pendingInput?.requestId).toBe(QUESTIONNAIRE_REQUEST_ID);
  const waitingSessionAfterReload = await fetchProductionJson(
    page,
    `/api/sessions/${encodeURIComponent(sessionId)}`,
  );
  expect(waitingSessionAfterReload.status).toBe(200);
  const restoredQueueIdentity = queueQuestionnaireIdentity(waitingSessionAfterReload.body);
  expect(restoredQueueIdentity.dispatchId).toBe(queueBridge.queueItemId);
  expect(restoredQueueIdentity.checkpointId).toBe(queueBridge.queueItemId);
  expect(restoredQueueIdentity.clientRequestId).toBe(queueBridge.queueItemId);
  const restoredWaitingQueueSession = waitingQueueSessionProjection(
    waitingSessionAfterReload.body,
    agentRunId,
    firstRuntimeRunId,
  );
  expect(restoredWaitingQueueSession).toEqual(queueBridge.waitingSession);
  const restoredQuestionnaireSnapshot = questionnaireWaitingSnapshotProjection(
    waitingAgentAfterReload.body,
    waitingSessionAfterReload.body,
    agentRunId,
  );
  expect(restoredQuestionnaireSnapshot.agent).toEqual(waitingQuestionnaireSnapshot.agent);
  expect(restoredQuestionnaireSnapshot.session.runState)
    .toEqual(waitingQuestionnaireSnapshot.session.runState);
  expect(restoredQuestionnaireSnapshot.session.roles)
    .toEqual(["user", "assistant", "tool-call", "user"]);
  const metricsAfterWaitingReload = await h4.metrics();
  expect(metricsAfterWaitingReload.chatRequests).toEqual(metricsAtWaiting.chatRequests);
  expect(metricsAfterWaitingReload.toolExecutions).toEqual(metricsAtWaiting.toolExecutions);
  const waitingReloadRequests = questionnaireRequestProjection(
    h4,
    waitingReloadBoundary,
    queueBridge.metricsAfter,
    metricsAfterWaitingReload,
  );
  expect(waitingReloadRequests).toEqual({
    agentRunPost: 0,
    runtimePost: 0,
    agentDelete: 0,
    inputPost: 0,
    resumePost: 0,
    browserProxyChatPost: 0,
    browserToolPost: 0,
    upstreamChatDelta: 0,
    productionDelegationDelta: 0,
    productionToolExecutionDelta: 0,
  });
  expect(h4.controlIds()).toEqual({
    agentRunIds: [agentRunId],
    runtimeRunIds: [firstRuntimeRunId],
  });
  const waitingRefreshLifecycle = {
    sameMainAgentRun: waitingAgentAfterReload.body.agentRunId === agentRunId,
    sameRequest: waitingAgentAfterReload.body.pendingInput?.requestId === QUESTIONNAIRE_REQUEST_ID,
    sameEvents: JSON.stringify(questionnaireEventProjection(waitingAgentAfterReload.body))
      === JSON.stringify(waitingEvents),
    sameQueueSession: JSON.stringify(restoredWaitingQueueSession)
      === JSON.stringify(queueBridge.waitingSession),
    sameDom: JSON.stringify({
      questionnaire: restoredWaitingQuestionnaireDom,
      queue: restoredWaitingQueueDom,
    }) === JSON.stringify(waitingDom),
    requests: waitingReloadRequests,
    counts: {
      agentRuns: metricsAfterWaitingReload.production.agentRuns.length,
      runtimes: metricsAfterWaitingReload.production.runtimeRuns.length,
      upstreamChat: metricsAfterWaitingReload.chatRequests.length,
      interactionExecutionDelta: waitingAgentAfterReload.body.toolExecutions.length
        - waitingAgent.toolExecutions.length,
      pendingQueue: restoredWaitingQueueSession.queue.checkpointCount,
      promotionDelta: 0,
    },
  };

  const submissionBoundary = h4.requestBoundary();
  const promotionObservation = startQuestionnaireQueuePromotionObservation(page);
  try {
    const option = page.locator(
      `#userInputPanel [data-question-id="${QUESTIONNAIRE_QUESTION_ID}"] input[type="radio"][value="${QUESTIONNAIRE_OPTION_B.value}"]`,
    );
    const confirm = page.locator(
      `#userInputPanel [data-question-id="${QUESTIONNAIRE_QUESTION_ID}"] [data-user-input-action="confirm"]`,
    );
    await expect(option).toHaveCount(1);
    await expect(option).not.toBeChecked();
    await option.check();
    await expect(option).toBeChecked();
    await expect(confirm).toHaveCount(1);
    await expect(confirm).toBeEnabled();
    await confirm.click();
    await expect(page.locator("#messages article.msg.assistant")
      .filter({ hasText: QUESTIONNAIRE_FINAL })).toHaveCount(1);
    await expect(page.locator("#messages article.msg.assistant")
      .filter({ hasText: TIMING_QUEUE_FINAL })).toHaveCount(1);
    await expect.poll(() => promotionObservation.timeline).toEqual([
      { sequence: 1, type: "main-terminal-checkpoint-cleared" },
      { sequence: 2, type: "queue-promoted" },
    ]);
    expect(promotionObservation.counts.checkpointClearedSaves).toBeGreaterThan(0);
    expect(promotionObservation.counts.queuePromotionPosts).toBe(1);
  } finally {
    promotionObservation.stop();
  }

  await expect.poll(() => {
    const ids = h4.controlIds();
    return { agentRuns: ids.agentRunIds.length, runtimes: ids.runtimeRunIds.length };
  }).toEqual({ agentRuns: 2, runtimes: 3 });
  const controlIds = h4.controlIds();
  const queuedAgentRunId = controlIds.agentRunIds.find((runId) => runId !== agentRunId);
  expect(queuedAgentRunId).toBeTruthy();
  expect(queuedAgentRunId).not.toBe(queueBridge.queueItemId);

  const mainAgentResponse = await fetchProductionJson(
    page,
    `/api/agent/runs/${encodeURIComponent(agentRunId)}?cursor=0&wait=0`,
  );
  const queuedAgentResponse = await fetchProductionJson(
    page,
    `/api/agent/runs/${encodeURIComponent(queuedAgentRunId)}?cursor=0&wait=0`,
  );
  expect(mainAgentResponse.status).toBe(200);
  expect(queuedAgentResponse.status).toBe(200);
  const completedMainAgent = mainAgentResponse.body;
  const completedQueuedAgent = queuedAgentResponse.body;
  expect(completedMainAgent).toMatchObject({
    agentRunId,
    status: "completed",
    activeRuntimeRunId: "",
    pendingInput: null,
    result: { content: QUESTIONNAIRE_FINAL },
  });
  expect(completedQueuedAgent).toMatchObject({
    agentRunId: queuedAgentRunId,
    clientRequestId: queueBridge.queueItemId,
    status: "completed",
    activeRuntimeRunId: "",
    pendingInput: null,
    result: { content: TIMING_QUEUE_FINAL },
  });
  const mainEvents = questionnaireEventProjection(completedMainAgent);
  expect(mainEvents.map((event) => event.type)).toEqual([
    "created",
    "model_started",
    "model_completed",
    "tool_started",
    "user_input_required",
    "user_input_submitted",
    "tool_completed",
    "waiting_credentials",
    "resumed",
    "model_started",
    "model_completed",
    "completed",
  ]);
  expect(mainEvents.map((event) => event.seq)).toEqual(
    mainEvents.map((_, index) => index + 1),
  );
  const mainExecution = questionnaireExecutionProjection(completedMainAgent);
  expect(mainExecution).toHaveLength(1);
  const queuedEvents = queuedAgentEventProjection(completedQueuedAgent);
  expect(queuedEvents.map((event) => event.seq)).toEqual(
    queuedEvents.map((_, index) => index + 1),
  );
  expect(queuedEvents.map((event) => event.type)).toEqual([
    "created",
    "model_started",
    "model_completed",
    "completed",
  ]);
  expect(queuedEvents[0]?.type).toBe("created");
  expect(queuedEvents.at(-1)?.type).toBe("completed");
  expect(queuedEvents.filter((event) => event.type === "model_started")).toHaveLength(1);
  expect(queuedEvents.filter((event) => event.type === "model_completed")).toHaveLength(1);
  expect(completedQueuedAgent.toolExecutions).toEqual([]);

  const mainRuntimeRunIds = completedMainAgent.events
    .filter((event) => event?.type === "model_started")
    .map((event) => String(event?.data?.runtimeRunId || ""));
  const queuedRuntimeRunIds = completedQueuedAgent.events
    .filter((event) => event?.type === "model_started")
    .map((event) => String(event?.data?.runtimeRunId || ""));
  expect(mainRuntimeRunIds).toHaveLength(2);
  expect(queuedRuntimeRunIds).toHaveLength(1);
  expect(new Set([...mainRuntimeRunIds, ...queuedRuntimeRunIds]).size).toBe(3);
  expect(new Set(controlIds.runtimeRunIds)).toEqual(
    new Set([...mainRuntimeRunIds, ...queuedRuntimeRunIds]),
  );
  const runtimeEntries = [];
  for (const [index, runtimeRunId] of mainRuntimeRunIds.entries()) {
    const response = await fetchProductionJson(
      page,
      `/api/runtime/runs/${encodeURIComponent(runtimeRunId)}?cursor=0&wait=0`,
    );
    expect(response.status).toBe(200);
    expect(response.body.status).toBe("completed");
    runtimeEntries.push({ owner: `main-${index + 1}`, snapshot: response.body });
  }
  const queuedRuntimeResponse = await fetchProductionJson(
    page,
    `/api/runtime/runs/${encodeURIComponent(queuedRuntimeRunIds[0])}?cursor=0&wait=0`,
  );
  expect(queuedRuntimeResponse.status).toBe(200);
  expect(queuedRuntimeResponse.body.status).toBe("completed");
  runtimeEntries.push({ owner: "queued", snapshot: queuedRuntimeResponse.body });
  const runtimeProjection = queueQuestionnaireRuntimeProjection(runtimeEntries);
  expect(runtimeProjection.map((entry) => ({
    owner: entry.owner,
    status: entry.status,
    content: entry.content,
    finishReason: entry.finishReason,
    toolCallCount: entry.toolCalls.length,
  }))).toEqual([
    {
      owner: "main-1",
      status: "completed",
      content: "empty",
      finishReason: "tool_calls",
      toolCallCount: 1,
    },
    {
      owner: "main-2",
      status: "completed",
      content: "questionnaire-final",
      finishReason: "stop",
      toolCallCount: 0,
    },
    {
      owner: "queued",
      status: "completed",
      content: "queued-final",
      finishReason: "stop",
      toolCallCount: 0,
    },
  ]);

  let terminalSessionResponse = null;
  await expect.poll(async () => {
    terminalSessionResponse = await fetchProductionJson(
      page,
      `/api/sessions/${encodeURIComponent(sessionId)}`,
    );
    return {
      status: terminalSessionResponse.status,
      roles: (terminalSessionResponse.body?.messages || []).map((message) => message.role),
      runStateKeys: Object.keys(terminalSessionResponse.body?.runState || {}).sort(),
    };
  }).toEqual({
    status: 200,
    roles: ["user", "assistant", "tool-call", "user", "tool-result", "assistant", "user", "assistant"],
    runStateKeys: [],
  });
  const sessionRoleContent = queueQuestionnaireSessionRoleProjection(
    terminalSessionResponse.body.messages,
  );
  expect(sessionRoleContent).toEqual([
    { role: "user", kind: "initial-user" },
    { role: "assistant", kind: "tool-owner" },
    { role: "tool-call", kind: "questionnaire-call" },
    { role: "user", kind: "input-summary" },
    { role: "tool-result", kind: "questionnaire-result" },
    { role: "assistant", kind: "final" },
    { role: "user", kind: "queued-user" },
    { role: "assistant", kind: "queued-final" },
  ]);
  const terminalQueueSession = terminalQueueSessionProjection(
    terminalSessionResponse.body,
    queueBridge.queueItemId,
    completedQueuedAgent,
  );
  expect(terminalQueueSession).toEqual({
    runStateCleared: true,
    queuedUserCount: 1,
    queuedFinalCount: 1,
    checkpointCount: 0,
    dispatchStatus: "completed",
    detachedFromMain: false,
    queueIdentityRetained: true,
    clientRequestMatches: true,
  });

  const terminalQuestionnaireDom = await questionnaireDomProjection(h4, "terminal");
  const terminalQueueDom = await queueQuestionnaireDomProjection(h4, "terminal");
  const terminalDom = {
    questionnaire: terminalQuestionnaireDom,
    queue: terminalQueueDom,
  };

  const completedQueueContext = {
    questionnaireUserCount: 1,
    questionnaireFinalCount: 1,
    queuedUserCount: 1,
    markerOrder: ["questionnaire-user", "questionnaire-final", "queued-user"],
    mainFinalPrecedesQueuedUser: true,
  };
  const metricsAtTerminal = await h4.metrics();
  expect(metricsAtTerminal.chatRequests.map((request) => ({
    scenario: request.scenario,
    hasToolResult: request.hasToolResult,
    queueContext: request.queueContext,
  }))).toEqual([
    {
      scenario: "queue-questionnaire-call",
      hasToolResult: false,
      queueContext: initialQueueContext,
    },
    {
      scenario: "queue-questionnaire-final",
      hasToolResult: true,
      queueContext: initialQueueContext,
    },
    {
      scenario: "queue-questionnaire-promoted",
      hasToolResult: true,
      queueContext: completedQueueContext,
    },
  ]);
  expect(metricsAtTerminal.chatRequests[1].questionnaireReceipt).toMatchObject({
    receiptCount: 1,
    parseable: true,
    selectedValueMatches: true,
  });
  expect(metricsAtTerminal.toolExecutions).toEqual([]);
  expect(metricsAtTerminal.productionToolDelegations).toBe(0);
  expect(metricsAtTerminal.unsafeToolRequests).toBe(0);
  expect(metricsAtTerminal.production.agentRuns).toHaveLength(2);
  expect(metricsAtTerminal.production.runtimeRuns).toHaveLength(3);
  const submissionRequests = questionnaireRequestProjection(
    h4,
    submissionBoundary,
    metricsAfterWaitingReload,
    metricsAtTerminal,
  );
  expect(submissionRequests).toEqual({
    agentRunPost: 1,
    runtimePost: 0,
    agentDelete: 0,
    inputPost: 1,
    resumePost: 1,
    browserProxyChatPost: 0,
    browserToolPost: 0,
    upstreamChatDelta: 2,
    productionDelegationDelta: 0,
    productionToolExecutionDelta: 0,
  });
  const totalRequests = questionnaireRequestProjection(
    h4,
    started.lifecycleBoundary,
    started.lifecycleMetricsBefore,
    metricsAtTerminal,
  );
  expect(totalRequests).toEqual({
    agentRunPost: 2,
    runtimePost: 0,
    agentDelete: 0,
    inputPost: 1,
    resumePost: 1,
    browserProxyChatPost: 0,
    browserToolPost: 0,
    upstreamChatDelta: 3,
    productionDelegationDelta: 0,
    productionToolExecutionDelta: 0,
  });
  const lifecycleSteerPost = queueQuestionnaireSteerPostCount(
    h4.loopbackRequests.slice(started.lifecycleBoundary),
  );
  expect(lifecycleSteerPost).toBe(0);

  const inputSubmissionProjection = {
    requests: {
      inputPost: submissionRequests.inputPost,
      resumePost: submissionRequests.resumePost,
      mainContinuationChat: 1,
    },
    events: mainEvents.slice(waitingEvents.length, 9),
    execution: mainExecution,
    sameMainAgentRun: completedMainAgent.agentRunId === agentRunId,
    interactionExecutionCount: completedMainAgent.toolExecutions.length,
    mainContinuationQueueMarkerCount: metricsAtTerminal.chatRequests[1]
      .queueContext.queuedUserCount,
  };
  const queuePromotionProjection = {
    requests: {
      agentRunPost: submissionRequests.agentRunPost,
      queuedUpstreamChat: submissionRequests.upstreamChatDelta - 1,
      steerPost: lifecycleSteerPost,
    },
    causalTimeline: promotionObservation.timeline,
    causalCounts: {
      mainTerminalCheckpointObserved: promotionObservation.counts.checkpointClearedSaves > 0,
      queuePromotionPosts: promotionObservation.counts.queuePromotionPosts,
    },
    mainCompletedBeforePromotion: promotionObservation.timeline.map((entry) => entry.type)
      .join(",") === "main-terminal-checkpoint-cleared,queue-promoted",
    identities: {
      distinctAgentRuns: completedQueuedAgent.agentRunId !== completedMainAgent.agentRunId,
      clientRequestMatchesQueue: completedQueuedAgent.clientRequestId === queueBridge.queueItemId,
      queueSeparateFromQuestionnaire: ![
        QUESTIONNAIRE_REQUEST_ID,
        QUESTIONNAIRE_TOOL_CALL_ID,
        agentRunId,
      ].includes(queueBridge.queueItemId),
    },
    queuedAgent: {
      status: String(completedQueuedAgent.status || ""),
      nextCursor: Number(completedQueuedAgent.nextCursor || 0),
      events: queuedEvents,
      executionCount: completedQueuedAgent.toolExecutions.length,
    },
    terminalQueueSession,
  };

  const terminalReloadBoundary = h4.requestBoundary();
  await h4.reloadRuntime(runtime);
  await page.locator("#baseUrl").evaluate((element, fakeUrl) => {
    element.value = fakeUrl;
  }, h4.host.ready.fakeUrl);
  const restoredTerminalQuestionnaireDom = await questionnaireDomProjection(h4, "terminal");
  const restoredTerminalQueueDom = await queueQuestionnaireDomProjection(h4, "terminal");
  expect({
    questionnaire: restoredTerminalQuestionnaireDom,
    queue: restoredTerminalQueueDom,
  }).toEqual(terminalDom);
  const mainAgentAfterReload = await fetchProductionJson(
    page,
    `/api/agent/runs/${encodeURIComponent(agentRunId)}?cursor=0&wait=0`,
  );
  const queuedAgentAfterReload = await fetchProductionJson(
    page,
    `/api/agent/runs/${encodeURIComponent(queuedAgentRunId)}?cursor=0&wait=0`,
  );
  const terminalSessionAfterReload = await fetchProductionJson(
    page,
    `/api/sessions/${encodeURIComponent(sessionId)}`,
  );
  expect(mainAgentAfterReload.status).toBe(200);
  expect(queuedAgentAfterReload.status).toBe(200);
  expect(terminalSessionAfterReload.status).toBe(200);
  expect(questionnaireEventProjection(mainAgentAfterReload.body)).toEqual(mainEvents);
  expect(questionnaireExecutionProjection(mainAgentAfterReload.body)).toEqual(mainExecution);
  expect(queuedAgentEventProjection(queuedAgentAfterReload.body)).toEqual(queuedEvents);
  expect(queueQuestionnaireSessionRoleProjection(terminalSessionAfterReload.body.messages))
    .toEqual(sessionRoleContent);
  expect(terminalQueueSessionProjection(
    terminalSessionAfterReload.body,
    queueBridge.queueItemId,
    queuedAgentAfterReload.body,
  )).toEqual(terminalQueueSession);

  const runtimeEntriesAfterReload = [];
  for (const [index, runtimeRunId] of mainRuntimeRunIds.entries()) {
    const response = await fetchProductionJson(
      page,
      `/api/runtime/runs/${encodeURIComponent(runtimeRunId)}?cursor=0&wait=0`,
    );
    expect(response.status).toBe(200);
    runtimeEntriesAfterReload.push({ owner: `main-${index + 1}`, snapshot: response.body });
  }
  const queuedRuntimeAfterReload = await fetchProductionJson(
    page,
    `/api/runtime/runs/${encodeURIComponent(queuedRuntimeRunIds[0])}?cursor=0&wait=0`,
  );
  expect(queuedRuntimeAfterReload.status).toBe(200);
  runtimeEntriesAfterReload.push({ owner: "queued", snapshot: queuedRuntimeAfterReload.body });
  expect(queueQuestionnaireRuntimeProjection(runtimeEntriesAfterReload)).toEqual(runtimeProjection);
  const metricsAfterTerminalReload = await h4.metrics();
  expect(metricsAfterTerminalReload.chatRequests).toEqual(metricsAtTerminal.chatRequests);
  expect(metricsAfterTerminalReload.toolExecutions).toEqual(metricsAtTerminal.toolExecutions);
  const terminalReloadRequests = questionnaireRequestProjection(
    h4,
    terminalReloadBoundary,
    metricsAtTerminal,
    metricsAfterTerminalReload,
  );
  expect(terminalReloadRequests).toEqual({
    agentRunPost: 0,
    runtimePost: 0,
    agentDelete: 0,
    inputPost: 0,
    resumePost: 0,
    browserProxyChatPost: 0,
    browserToolPost: 0,
    upstreamChatDelta: 0,
    productionDelegationDelta: 0,
    productionToolExecutionDelta: 0,
  });
  const terminalReloadSteerPost = queueQuestionnaireSteerPostCount(
    h4.loopbackRequests.slice(terminalReloadBoundary),
  );
  expect(terminalReloadSteerPost).toBe(0);
  expect(new Set(h4.controlIds().agentRunIds)).toEqual(
    new Set([agentRunId, queuedAgentRunId]),
  );
  expect(new Set(h4.controlIds().runtimeRunIds)).toEqual(
    new Set([...mainRuntimeRunIds, ...queuedRuntimeRunIds]),
  );
  expect(h4.pageErrors).toEqual([]);
  const refreshLifecycle = {
    sameAgents: questionnaireEventProjection(mainAgentAfterReload.body).length === mainEvents.length
      && queuedAgentEventProjection(queuedAgentAfterReload.body).length === queuedEvents.length,
    sameRuntimes: JSON.stringify(queueQuestionnaireRuntimeProjection(runtimeEntriesAfterReload))
      === JSON.stringify(runtimeProjection),
    sameSession: JSON.stringify(queueQuestionnaireSessionRoleProjection(
      terminalSessionAfterReload.body.messages,
    )) === JSON.stringify(sessionRoleContent),
    sameDom: JSON.stringify({
      questionnaire: restoredTerminalQuestionnaireDom,
      queue: restoredTerminalQueueDom,
    }) === JSON.stringify(terminalDom),
    requests: terminalReloadRequests,
    counts: {
      agentRuns: metricsAfterTerminalReload.production.agentRuns.length,
      runtimes: metricsAfterTerminalReload.production.runtimeRuns.length,
      upstreamChat: metricsAfterTerminalReload.chatRequests.length,
      inputDelta: 0,
      resumeDelta: 0,
      steerDelta: terminalReloadSteerPost,
      promotionDelta: terminalReloadRequests.agentRunPost,
      registeredToolDelta: metricsAfterTerminalReload.toolExecutions.length
        - metricsAtTerminal.toolExecutions.length,
      interactionExecutionDelta: mainAgentAfterReload.body.toolExecutions.length
        - completedMainAgent.toolExecutions.length,
    },
  };

  const hashes = {
    waitingEventProjection: canonicalHash(waitingEvents),
    waitingQuestionnaireSnapshot: canonicalHash(waitingQuestionnaireSnapshot),
    queueSubmissionProjection: canonicalHash(queueBridge.projection),
    waitingQueueSession: canonicalHash(queueBridge.waitingSession),
    waitingDom: canonicalHash(waitingDom),
    waitingRefreshLifecycle: canonicalHash(waitingRefreshLifecycle),
    inputSubmissionProjection: canonicalHash(inputSubmissionProjection),
    queuePromotionProjection: canonicalHash(queuePromotionProjection),
    runtimeProjection: canonicalHash(runtimeProjection),
    sessionRoleContent: canonicalHash(sessionRoleContent),
    terminalDom: canonicalHash(terminalDom),
    refreshLifecycle: canonicalHash(refreshLifecycle),
  };
  expect(Object.keys(hashes)).toEqual(H4_8E_SEMANTIC_HASH_KEYS);
  if (frozenMode) expect(hashes).toEqual(H4_8E_SEMANTIC_HASHES);

  h4.evidence(`${runtime}-questionnaire-queue-refresh-order`, {
    runtime,
    counts: {
      agentRuns: metricsAtTerminal.production.agentRuns.length,
      runtimes: metricsAtTerminal.production.runtimeRuns.length,
      upstreamChat: metricsAtTerminal.chatRequests.length,
      inputPost: totalRequests.inputPost,
      resumePost: totalRequests.resumePost,
      enqueue: queueBridge.projection.saveCount,
      promotion: submissionRequests.agentRunPost,
      interactionExecutions: completedMainAgent.toolExecutions.length,
      registeredDelegations: metricsAtTerminal.productionToolDelegations,
      registeredExecutions: metricsAtTerminal.toolExecutions.length,
    },
    agents: {
      main: { status: completedMainAgent.status, eventTypes: mainEvents.map((event) => event.type) },
      queued: { status: completedQueuedAgent.status, eventTypes: queuedEvents.map((event) => event.type) },
      distinct: completedMainAgent.agentRunId !== completedQueuedAgent.agentRunId,
      queueClientRequestClosed: completedQueuedAgent.clientRequestId === queueBridge.queueItemId,
    },
    runtimeCursors: runtimeProjection.map((snapshot) => snapshot.nextCursor),
    sessionOrder: sessionRoleContent,
    domOrder: terminalDom.queue.order,
    chatContexts: metricsAtTerminal.chatRequests.map((request) => request.queueContext),
    promotionCausality: promotionObservation.timeline,
    promotionObservationCounts: promotionObservation.counts,
    waitingReload: waitingReloadRequests,
    terminalReload: terminalReloadRequests,
    hashes,
  });
}

function mixedQuestionnaireQuestionDefinitionProjection(question, expected) {
  const source = question && typeof question === "object" ? question : {};
  const contract = expected && typeof expected === "object" ? expected : {};
  const options = Array.isArray(source.options) ? source.options : [];
  return {
    idMatches: String(source.id || "") === String(contract.id || ""),
    promptMatches: String(source.prompt || "") === String(contract.prompt || ""),
    type: String(source.type || ""),
    typeMatches: String(source.type || "") === String(contract.type || ""),
    requiredMatches: Boolean(source.required) === Boolean(contract.required),
    allowOtherMatches: Boolean(source.allowOther) === Boolean(contract.allowOther),
    optionCount: options.length,
    optionCountMatches: options.length === (contract.options?.length || 0),
    options: options.map((option, optionIndex) => {
      const expectedOption = contract.options?.[optionIndex] || {};
      return {
        valueMatches: String(option?.value || "") === String(expectedOption.value || ""),
        labelMatches: String(option?.label || "") === String(expectedOption.label || ""),
        descriptionMatches: String(option?.description || "")
          === String(expectedOption.description || ""),
      };
    }),
  };
}

function mixedQuestionnaireDefinitionProjection(value) {
  const source = value && typeof value === "object" ? value : parseToolArguments(value);
  const questions = Array.isArray(source?.questions) ? source.questions : [];
  return {
    titleMatches: String(source?.title || "") === MIXED_QUESTIONNAIRE_CONTRACT.title,
    reasonMatches: String(source?.reason || "") === MIXED_QUESTIONNAIRE_CONTRACT.reason,
    questionCount: questions.length,
    questions: questions.map((question, questionIndex) => (
      mixedQuestionnaireQuestionDefinitionProjection(
        question,
        MIXED_QUESTIONNAIRE_CONTRACT.questions[questionIndex],
      )
    )),
  };
}

function mixedQuestionnaireFieldShape(source, key) {
  if (!Object.prototype.hasOwnProperty.call(source || {}, key)) return "absent";
  if (source[key] == null) return "null";
  if (Array.isArray(source[key])) return "array";
  return typeof source[key];
}

function mixedQuestionnaireProgressFieldsAbsent(question) {
  const source = question && typeof question === "object" ? question : {};
  const fields = [
    "status",
    "selected",
    "text",
    "other",
    "answer",
    "value",
    "values",
    "checked",
    "resolved",
  ];
  const projection = Object.fromEntries(fields.map((field) => [
    field,
    !Object.prototype.hasOwnProperty.call(source, field),
  ]));
  return {
    ...projection,
    allAbsent: Object.values(projection).every(Boolean),
  };
}

function mixedQuestionnaireAnswerProjection(answer, answerIndex) {
  const source = answer && typeof answer === "object" ? answer : {};
  const expected = MIXED_QUESTIONNAIRE_CONTRACT.questions[answerIndex] || {};
  const values = Array.isArray(source.values) ? source.values.map(String) : [];
  const expectedValues = expected.answer?.values || [];
  const answerText = String(source.answer || "");
  const answerMarkers = expected.answer?.markers || [];
  const answerMarkerPositions = answerMarkers.map((marker) => answerText.indexOf(marker));
  return {
    idMatches: String(source.id || "") === String(expected.id || ""),
    promptMatches: String(source.prompt || "") === String(expected.prompt || ""),
    type: String(source.type || ""),
    status: String(source.status || ""),
    valuesField: mixedQuestionnaireFieldShape(source, "values"),
    valuesCount: values.length,
    valuesMatch: JSON.stringify(values) === JSON.stringify(expectedValues),
    textField: mixedQuestionnaireFieldShape(source, "text"),
    textMatches: String(source.text || "") === String(expected.answer?.text || ""),
    otherMatches: String(source.other || "") === String(expected.answer?.other || ""),
    answerMarkerCount: answerMarkers.length,
    answerMarkersMatch: answerMarkers.every((marker) => answerText.includes(marker)),
    answerMarkersExactOnce: answerMarkers.every((marker) => (
      answerText.split(marker).length - 1 === 1
    )),
    answerMarkerOrderMatches: answerMarkerPositions.every((position, markerIndex) => (
      markerIndex === 0
      || answerMarkerPositions[markerIndex - 1] < position
    )),
  };
}

function mixedQuestionnaireResultProjection(value) {
  const source = value && typeof value === "object" ? value : {};
  const answers = Array.isArray(source.answers) ? source.answers : [];
  const summaryLines = String(source.summary || "").split(/\r?\n/).filter(Boolean);
  return {
    ok: source.ok === true,
    action: String(source.action || ""),
    requestIdMatches: String(source.requestId || "") === MIXED_QUESTIONNAIRE_CONTRACT.requestId,
    titleMatches: String(source.title || "") === MIXED_QUESTIONNAIRE_CONTRACT.title,
    answerCount: answers.length,
    answers: answers.map(mixedQuestionnaireAnswerProjection),
    summaryLineCount: summaryLines.length,
    summaryMarkersMatch: MIXED_QUESTIONNAIRE_CONTRACT.questions.every((question, index) => {
      const line = String(summaryLines[index] || "");
      return line.includes(question.prompt)
        && question.answer.markers.every((marker) => line.includes(marker));
    }),
    summaryMarkersExactOnce: MIXED_QUESTIONNAIRE_CONTRACT.questions.every((question, index) => {
      const line = String(summaryLines[index] || "");
      return [question.prompt, ...question.answer.markers].every((marker) => (
        line.split(marker).length - 1 === 1
      ));
    }),
    summaryMarkerOrderMatches: MIXED_QUESTIONNAIRE_CONTRACT.questions.every((question, index) => {
      const line = String(summaryLines[index] || "");
      const markers = [question.prompt, ...question.answer.markers];
      return markers.every((marker, markerIndex) => (
        markerIndex === 0
        || line.indexOf(markers[markerIndex - 1]) < line.indexOf(marker)
      ));
    }),
    failureCountAbsent: !Object.prototype.hasOwnProperty.call(source, "failureCount"),
    failureSignatureAbsent: !Object.prototype.hasOwnProperty.call(source, "failureSignature"),
    retryFieldsAbsent: !Object.prototype.hasOwnProperty.call(source, "retryBlocked")
      && !Object.prototype.hasOwnProperty.call(source, "retryLimitReached"),
  };
}

function mixedQuestionnaireEventProjection(snapshot) {
  const events = Array.isArray(snapshot?.events) ? snapshot.events : [];
  const runtimeIds = events
    .filter((event) => event?.type === "model_started")
    .map((event) => String(event?.data?.runtimeRunId || ""));
  const runtimeAliases = new Map(
    runtimeIds.map((runId, index) => [runId, "runtime-" + (index + 1)]),
  );
  return events.map((event) => {
    const data = event?.data || {};
    const projected = {
      seq: Number(event?.seq || 0),
      type: String(event?.type || ""),
    };
    if (data.round != null) projected.round = Number(data.round);
    if (data.runtimeRunId) {
      projected.runtimeRunId = runtimeAliases.get(String(data.runtimeRunId)) || "mismatch";
    }
    if (data.content != null) {
      projected.content = String(data.content) === MIXED_QUESTIONNAIRE_CONTRACT.finalMarker
        ? "final"
        : "empty";
    }
    if (data.finishReason != null) projected.finishReason = String(data.finishReason);
    if (Array.isArray(data.toolCalls)) {
      projected.toolCalls = data.toolCalls.map((call) => ({
        toolCallMatches: String(call?.id || "") === MIXED_QUESTIONNAIRE_CONTRACT.toolCallId,
        name: String(call?.function?.name || call?.name || ""),
        arguments: mixedQuestionnaireDefinitionProjection(
          call?.function?.arguments ?? call?.arguments,
        ),
      }));
    }
    if (data.toolCallId) {
      projected.toolCallMatches = String(data.toolCallId)
        === MIXED_QUESTIONNAIRE_CONTRACT.toolCallId;
    }
    if (data.name != null) projected.name = String(data.name || "");
    if (data.arguments != null) {
      projected.arguments = mixedQuestionnaireDefinitionProjection(data.arguments);
    }
    if (data.requestId != null) {
      projected.requestIdMatches = String(data.requestId)
        === MIXED_QUESTIONNAIRE_CONTRACT.requestId;
    }
    if (Array.isArray(data.questions)) {
      projected.inputRequest = mixedQuestionnaireDefinitionProjection({
        title: data.title,
        reason: data.reason,
        questions: data.questions,
      });
    }
    if (data.outcome != null) projected.outcome = String(data.outcome);
    if (data.replayed != null) projected.replayed = Boolean(data.replayed);
    if (data.result != null) projected.result = mixedQuestionnaireResultProjection(data.result);
    if (data.resumeStatus != null) projected.resumeStatus = String(data.resumeStatus);
    if (data.reason != null) projected.reason = String(data.reason);
    return projected;
  });
}

function mixedQuestionnaireExecutionProjection(snapshot) {
  return (Array.isArray(snapshot?.toolExecutions) ? snapshot.toolExecutions : [])
    .map((execution) => ({
      toolCallMatches: String(execution?.toolCallId || "")
        === MIXED_QUESTIONNAIRE_CONTRACT.toolCallId,
      name: String(execution?.name || ""),
      arguments: mixedQuestionnaireDefinitionProjection(execution?.arguments),
      status: String(execution?.status || ""),
      outcome: String(execution?.outcome || ""),
      result: execution?.result == null
        ? null
        : mixedQuestionnaireResultProjection(execution.result),
      failureCountAbsent: !Object.prototype.hasOwnProperty.call(execution || {}, "failureCount"),
      failureSignatureAbsent: !Object.prototype.hasOwnProperty.call(
        execution || {},
        "failureSignature",
      ),
    }));
}

function mixedQuestionnaireProgressQuestionProjection(question, questionIndex) {
  const source = question && typeof question === "object" ? question : {};
  const expected = MIXED_QUESTIONNAIRE_CONTRACT.questions[questionIndex] || {};
  const selected = Array.isArray(source.selected) ? source.selected.map(String) : [];
  const resolved = String(source.status || "") === "resolved";
  return {
    definition: mixedQuestionnaireQuestionDefinitionProjection(source, expected),
    status: String(source.status || ""),
    selectedCount: selected.length,
    selectedMatches: JSON.stringify(selected)
      === JSON.stringify(resolved ? expected.answer?.values || [] : []),
    textMatches: String(source.text || "") === (resolved ? String(expected.answer?.text || "") : ""),
    otherMatches: String(source.other || "")
      === (resolved ? String(expected.answer?.other || "") : ""),
    answerNull: source.answer == null,
  };
}

function mixedQuestionnaireProgressSnapshot(agent, session, agentRunId) {
  const pending = agent?.pendingInput || {};
  const runState = session?.runState && typeof session.runState === "object"
    ? session.runState
    : {};
  const request = runState.userInputRequest && typeof runState.userInputRequest === "object"
    ? runState.userInputRequest
    : {};
  return {
    agent: {
      status: String(agent?.status || ""),
      nextCursor: Number(agent?.nextCursor || 0),
      round: Number(agent?.round || 0),
      activeRuntimeCleared: !String(agent?.activeRuntimeRunId || ""),
      pendingToolCallCount: Array.isArray(agent?.pendingToolCalls)
        ? agent.pendingToolCalls.length
        : -1,
      requestIdMatches: String(pending.requestId || "")
        === MIXED_QUESTIONNAIRE_CONTRACT.requestId,
      toolCallMatches: String(pending.toolCallId || "")
        === MIXED_QUESTIONNAIRE_CONTRACT.toolCallId,
      definition: mixedQuestionnaireDefinitionProjection({
        title: pending.title,
        reason: pending.reason,
        questions: pending.questions,
      }),
      pendingQuestionProgressFieldsAbsent: (Array.isArray(pending.questions)
        ? pending.questions
        : []).map(mixedQuestionnaireProgressFieldsAbsent),
      executions: mixedQuestionnaireExecutionProjection(agent),
    },
    session: {
      roles: (session?.messages || []).map((message) => String(message?.role || "")),
      runState: {
        status: String(runState.status || ""),
        phase: String(runState.phase || ""),
        executionOwner: String(runState.executionOwner || ""),
        runAgentRunMatches: String(runState.agentRunId || "") === agentRunId,
        runtimeRunCleared: !String(runState.runtimeRunId || ""),
        cursor: Number(runState.agentEventCursor || 0),
        modelRound: Number(runState.modelRound || 0),
        requestIdMatches: String(request.id || "") === MIXED_QUESTIONNAIRE_CONTRACT.requestId,
        toolCallMatches: String(request.toolCallId || "")
          === MIXED_QUESTIONNAIRE_CONTRACT.toolCallId,
        requestAgentRunMatches: String(request.agentRunId || "") === agentRunId,
        titleMatches: String(request.title || "") === MIXED_QUESTIONNAIRE_CONTRACT.title,
        reasonMatches: String(request.reason || "") === MIXED_QUESTIONNAIRE_CONTRACT.reason,
        requestStatus: String(request.status || ""),
        questionCount: Array.isArray(request.questions) ? request.questions.length : 0,
        questions: (Array.isArray(request.questions) ? request.questions : [])
          .map(mixedQuestionnaireProgressQuestionProjection),
      },
    },
  };
}

function mixedQuestionnaireSessionRoleProjection(messages) {
  return (Array.isArray(messages) ? messages : []).map((message) => {
    const role = String(message?.role || "");
    const meta = message?.meta || {};
    let kind = "";
    if (role === "user" && message?.content === MIXED_QUESTIONNAIRE_CONTRACT.userMarker) {
      kind = "initial-user";
    } else if (
      role === "assistant"
      && message?.content === MIXED_QUESTIONNAIRE_CONTRACT.finalMarker
    ) {
      kind = "final";
    } else if (
      role === "assistant"
      && Array.isArray(meta.toolCalls)
      && meta.toolCalls.length > 0
    ) {
      kind = "tool-owner";
    } else if (role === "tool-call" && meta.action === "request_user_input") {
      kind = "questionnaire-call";
    } else if (meta.kind === "user-input-summary") {
      kind = "input-summary";
    } else if (role === "tool-result" && meta.action === "request_user_input") {
      kind = "questionnaire-result";
    }
    return { role, kind };
  });
}

function mixedQuestionnaireSessionMetaProjection(messages, agentRunId) {
  return (Array.isArray(messages) ? messages : [])
    .filter((message) => (
      ["tool-call", "tool-result"].includes(message?.role)
      || message?.meta?.kind === "user-input-summary"
    ))
    .map((message) => {
      const meta = message?.meta || {};
      if (meta.kind === "user-input-summary") {
        return {
          role: String(message.role || ""),
          kind: "user-input-summary",
          system: meta._system === true,
          skipApi: meta.skipApi === true,
          requestIdMatches: String(meta.requestId || "")
            === MIXED_QUESTIONNAIRE_CONTRACT.requestId,
          titleMatches: String(meta.title || "") === MIXED_QUESTIONNAIRE_CONTRACT.title,
          result: mixedQuestionnaireResultProjection({
            ok: true,
            action: "request_user_input",
            requestId: meta.requestId,
            title: meta.title,
            answers: meta.answers,
            summary: message.content,
          }),
        };
      }
      return {
        role: String(message.role || ""),
        toolCallMatches: String(meta.toolCallId || "")
          === MIXED_QUESTIONNAIRE_CONTRACT.toolCallId,
        agentRunMatches: String(meta.agentRunId || "") === agentRunId,
        eventType: String(meta.agentEventType || ""),
        eventSeq: Number(meta.agentEventSeq || 0),
        action: String(meta.action || ""),
        native: meta.native === true,
        replayed: Boolean(meta.replayed),
        outcome: String(meta.outcome || ""),
        arguments: message.role === "tool-call"
          ? mixedQuestionnaireDefinitionProjection(meta.tool || {})
          : null,
        result: meta.result && typeof meta.result === "object"
          ? mixedQuestionnaireResultProjection(meta.result)
          : null,
      };
    });
}

function expectMixedQuestionnaireDefinition(projection) {
  expect(projection).toEqual({
    titleMatches: true,
    reasonMatches: true,
    questionCount: 3,
    questions: MIXED_QUESTIONNAIRE_CONTRACT.questions.map((question) => ({
      idMatches: true,
      promptMatches: true,
      type: question.type,
      typeMatches: true,
      requiredMatches: true,
      allowOtherMatches: true,
      optionCount: question.options.length,
      optionCountMatches: true,
      options: question.options.map(() => ({
        valueMatches: true,
        labelMatches: true,
        descriptionMatches: true,
      })),
    })),
  });
}

function expectMixedQuestionnaireResult(projection, fieldShapes) {
  expect(projection).toMatchObject({
    ok: true,
    action: "request_user_input",
    requestIdMatches: true,
    titleMatches: true,
    answerCount: 3,
    summaryLineCount: 3,
    summaryMarkersMatch: true,
    summaryMarkersExactOnce: true,
    summaryMarkerOrderMatches: true,
    failureCountAbsent: true,
    failureSignatureAbsent: true,
    retryFieldsAbsent: true,
  });
  expect(projection.answers).toHaveLength(3);
  projection.answers.forEach((answer, answerIndex) => {
    const expected = MIXED_QUESTIONNAIRE_CONTRACT.questions[answerIndex];
    expect(answer).toMatchObject({
      idMatches: true,
      promptMatches: true,
      type: expected.type,
      status: "resolved",
      valuesField: fieldShapes[answerIndex].values,
      valuesCount: expected.answer.values.length,
      valuesMatch: true,
      textField: fieldShapes[answerIndex].text,
      textMatches: true,
      otherMatches: true,
      answerMarkerCount: expected.answer.markers.length,
      answerMarkersMatch: true,
      answerMarkersExactOnce: true,
      answerMarkerOrderMatches: true,
    });
  });
}

function expectMixedQuestionnaireZeroRequests(projection) {
  expect(projection).toEqual({
    agentRunPost: 0,
    runtimePost: 0,
    agentDelete: 0,
    inputPost: 0,
    resumePost: 0,
    browserProxyChatPost: 0,
    browserToolPost: 0,
    upstreamChatDelta: 0,
    productionDelegationDelta: 0,
    productionToolExecutionDelta: 0,
  });
}

function mixedQuestionnaireActionTargetProjection(h4, boundary, agentRunId) {
  const targetHash = idHash(agentRunId);
  const requests = h4.loopbackRequests.slice(Number(boundary) || 0);
  const project = (kind) => {
    const matches = requests.filter((entry) => entry.kind === kind && entry.method === "POST");
    return {
      count: matches.length,
      allTargetRun: targetHash !== ""
        && matches.every((entry) => entry.idHash === targetHash),
    };
  };
  return {
    input: project("agent-input"),
    resume: project("agent-resume"),
  };
}

function expectMixedQuestionnaireActionTargets(projection, inputCount, resumeCount) {
  expect(projection).toEqual({
    input: { count: inputCount, allTargetRun: true },
    resume: { count: resumeCount, allTargetRun: true },
  });
}

function expectMixedQuestionnaireProgress(snapshot, statuses, waitingCursor) {
  expect(snapshot.agent).toMatchObject({
    status: "waiting_user_input",
    nextCursor: waitingCursor,
    round: 1,
    activeRuntimeCleared: true,
    pendingToolCallCount: 1,
    requestIdMatches: true,
    toolCallMatches: true,
  });
  expectMixedQuestionnaireDefinition(snapshot.agent.definition);
  expect(snapshot.agent.pendingQuestionProgressFieldsAbsent).toHaveLength(3);
  snapshot.agent.pendingQuestionProgressFieldsAbsent.forEach((projection) => {
    expect(projection).toEqual({
      status: true,
      selected: true,
      text: true,
      other: true,
      answer: true,
      value: true,
      values: true,
      checked: true,
      resolved: true,
      allAbsent: true,
    });
  });
  expect(snapshot.agent.executions).toHaveLength(1);
  expect(snapshot.agent.executions[0]).toMatchObject({
    toolCallMatches: true,
    name: "request_user_input",
    status: "waiting_user_input",
    outcome: "",
    result: null,
    failureCountAbsent: true,
    failureSignatureAbsent: true,
  });
  expectMixedQuestionnaireDefinition(snapshot.agent.executions[0].arguments);
  expect(snapshot.session.roles).toEqual(["user", "assistant", "tool-call"]);
  expect(snapshot.session.runState).toMatchObject({
    status: "waiting-user-input",
    phase: "tools",
    executionOwner: "server-agent",
    runAgentRunMatches: true,
    runtimeRunCleared: true,
    cursor: waitingCursor,
    modelRound: 1,
    requestIdMatches: true,
    toolCallMatches: true,
    requestAgentRunMatches: true,
    titleMatches: true,
    reasonMatches: true,
    requestStatus: "pending",
    questionCount: 3,
  });
  expect(snapshot.session.runState.questions.map((question) => question.status)).toEqual(statuses);
  snapshot.session.runState.questions.forEach((question, questionIndex) => {
    const resolved = statuses[questionIndex] === "resolved";
    const expected = MIXED_QUESTIONNAIRE_CONTRACT.questions[questionIndex];
    expect(question.definition).toEqual(
      mixedQuestionnaireQuestionDefinitionProjection(expected, expected),
    );
    expect(question).toMatchObject({
      selectedCount: resolved ? expected.answer.values.length : 0,
      selectedMatches: true,
      textMatches: true,
      otherMatches: true,
      answerNull: true,
    });
  });
}

async function mixedQuestionnaireDomProjection(h4, phase, currentIndex = -1) {
  const current = MIXED_QUESTIONNAIRE_CONTRACT.questions[currentIndex] || null;
  const expected = current ? {
    panel: {
      visible: true,
      cards: 1,
      questions: 1,
      progress: String(currentIndex + 1) + "/"
        + String(MIXED_QUESTIONNAIRE_CONTRACT.questions.length),
      currentQuestionMatches: true,
    },
    controls: {
      radios: current.type === "single"
        ? current.options.map((option) => ({
          value: option.value,
          checked: false,
          disabled: false,
        }))
        : [],
      checkboxes: current.type === "multiple"
        ? current.options.map((option) => ({
          value: option.value,
          checked: false,
          disabled: false,
        }))
        : [],
      text: {
        count: current.type === "text" ? 1 : 0,
        value: "",
        disabled: false,
      },
      other: {
        count: current.type !== "text" && current.allowOther ? 1 : 0,
        value: "",
        disabled: false,
      },
      confirm: { count: 1, disabled: false },
      cancel: { count: 1, disabled: false },
    },
    messages: {
      initialUser: 1,
      toolProcesses: 1,
      toolItems: 1,
      summaries: 0,
      summaryRows: 0,
      finals: 0,
    },
    summaryRowProjection: [],
    tool: { action: "request_user_input", argumentDetails: 1, resultDetails: 0 },
    order: ["initial-user", "tool-process"],
  } : {
    panel: {
      visible: false,
      cards: 0,
      questions: 0,
      progress: "",
      currentQuestionMatches: false,
    },
    controls: {
      radios: [],
      checkboxes: [],
      text: { count: 0, value: "", disabled: false },
      other: { count: 0, value: "", disabled: false },
      confirm: { count: 0, disabled: false },
      cancel: { count: 0, disabled: false },
    },
    messages: {
      initialUser: 1,
      toolProcesses: 1,
      toolItems: 1,
      summaries: 1,
      summaryRows: 3,
      finals: 1,
    },
    summaryRowProjection: MIXED_QUESTIONNAIRE_CONTRACT.questions.map((question) => ({
      promptMatches: true,
      answerMarkerCount: question.answer.markers.length,
      answerMarkersMatch: true,
      markersExactOnce: true,
      markerOrderMatches: true,
    })),
    tool: { action: "request_user_input", argumentDetails: 1, resultDetails: 1 },
    order: ["initial-user", "tool-process", "input-summary", "final"],
  };
  return waitForMessageProjection(h4, {
    label: "mixed-questionnaire-" + phase,
    expected,
    sourceFacts: {
      phase,
      userMarker: MIXED_QUESTIONNAIRE_CONTRACT.userMarker,
      finalMarker: MIXED_QUESTIONNAIRE_CONTRACT.finalMarker,
      currentQuestion: current ? {
        id: current.id,
        prompt: current.prompt,
      } : null,
      summaryMarkers: MIXED_QUESTIONNAIRE_CONTRACT.questions.flatMap((question) => [
        question.prompt,
        ...question.answer.markers,
      ]),
      summaryRowContracts: MIXED_QUESTIONNAIRE_CONTRACT.questions.map((question) => ({
        prompt: question.prompt,
        answerMarkers: question.answer.markers,
      })),
    },
    sample: (facts) => {
      const panel = document.querySelector("#userInputPanel");
      const root = document.querySelector("#messages");
      const currentQuestion = facts.currentQuestion
        ? panel?.querySelector('[data-question-id="' + facts.currentQuestion.id + '"]')
        : null;
      const radios = [...(currentQuestion?.querySelectorAll('input[type="radio"]') || [])];
      const checkboxes = [...(currentQuestion?.querySelectorAll('input[type="checkbox"]') || [])];
      const textInput = currentQuestion?.querySelector("[data-user-input-text]") || null;
      const otherInput = currentQuestion?.querySelector("[data-user-input-other]") || null;
      const confirm = currentQuestion?.querySelector('[data-user-input-action="confirm"]') || null;
      const cancel = currentQuestion?.querySelector('[data-user-input-action="cancel"]') || null;
      const users = [...root.querySelectorAll("article.msg.user")]
        .filter((node) => node.textContent.includes(facts.userMarker));
      const processStages = [...root.querySelectorAll(
        'article.tool-process > details.tool-process-stage[data-current-action="request_user_input"]',
      )];
      const processes = processStages.map((stage) => stage.closest("article.tool-process"));
      const process = processes[0] || null;
      const item = process?.querySelector("details.tool-process-item") || null;
      const details = item ? [...item.querySelectorAll(".tool-process-detail pre")] : [];
      const summaries = [...root.querySelectorAll("article.user-input-flow")]
        .filter((node) => facts.summaryMarkers.every((marker) => node.textContent.includes(marker)));
      const summaryRows = summaries[0]
        ? [...summaries[0].querySelectorAll(".msg-flow-body > span")]
        : [];
      const summaryRowProjection = summaryRows.map((row, rowIndex) => {
        const contract = facts.summaryRowContracts[rowIndex] || {
          prompt: "",
          answerMarkers: [],
        };
        const text = String(row.textContent || "");
        const markers = [contract.prompt, ...contract.answerMarkers];
        const positions = markers.map((marker) => text.indexOf(marker));
        return {
          promptMatches: Boolean(contract.prompt) && text.includes(contract.prompt),
          answerMarkerCount: contract.answerMarkers.length,
          answerMarkersMatch: contract.answerMarkers.every((marker) => text.includes(marker)),
          markersExactOnce: markers.every((marker) => text.split(marker).length - 1 === 1),
          markerOrderMatches: positions.every((position, markerIndex) => (
            markerIndex === 0 || positions[markerIndex - 1] < position
          )),
        };
      });
      const finals = [...root.querySelectorAll("article.msg.assistant")]
        .filter((node) => node.textContent.includes(facts.finalMarker));
      const nodes = [
        { label: "initial-user", node: users[0] || null },
        { label: "tool-process", node: process },
        ...(facts.phase === "terminal" ? [
          { label: "input-summary", node: summaries[0] || null },
          { label: "final", node: finals[0] || null },
        ] : []),
      ].filter((entry) => entry.node);
      nodes.sort((left, right) => (
        left.node.compareDocumentPosition(right.node) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1
      ));
      return {
        panel: {
          visible: Boolean(panel && !panel.classList.contains("hidden")),
          cards: panel?.querySelectorAll(".user-input-card").length || 0,
          questions: panel?.querySelectorAll("[data-question-id]").length || 0,
          progress: String(panel?.querySelector(".user-input-progress")?.textContent || "").trim(),
          currentQuestionMatches: Boolean(
            currentQuestion
            && currentQuestion.textContent.includes(facts.currentQuestion?.prompt || ""),
          ),
        },
        controls: {
          radios: radios.map((input) => ({
            value: String(input.value || ""),
            checked: input.checked === true,
            disabled: input.disabled === true,
          })),
          checkboxes: checkboxes.map((input) => ({
            value: String(input.value || ""),
            checked: input.checked === true,
            disabled: input.disabled === true,
          })),
          text: {
            count: textInput ? 1 : 0,
            value: String(textInput?.value || ""),
            disabled: textInput?.disabled === true,
          },
          other: {
            count: otherInput ? 1 : 0,
            value: String(otherInput?.value || ""),
            disabled: otherInput?.disabled === true,
          },
          confirm: { count: confirm ? 1 : 0, disabled: confirm?.disabled === true },
          cancel: { count: cancel ? 1 : 0, disabled: cancel?.disabled === true },
        },
        messages: {
          initialUser: users.length,
          toolProcesses: processes.length,
          toolItems: process?.querySelectorAll("details.tool-process-item").length || 0,
          summaries: summaries.length,
          summaryRows: summaryRows.length,
          finals: finals.length,
        },
        summaryRowProjection,
        tool: {
          action: String(process?.querySelector("details.tool-process-stage")?.dataset.currentAction || ""),
          argumentDetails: details.length > 0 ? 1 : 0,
          resultDetails: Math.max(0, details.length - 1),
        },
        order: nodes.map((entry) => entry.label),
      };
    },
  });
}

async function answerMixedQuestionnaireQuestion(page, questionIndex) {
  const question = MIXED_QUESTIONNAIRE_CONTRACT.questions[questionIndex];
  const root = page.locator(
    '#userInputPanel [data-question-id="' + question.id + '"]',
  );
  await expect(root).toHaveCount(1);
  if (question.type === "text") {
    const input = root.locator("[data-user-input-text]");
    await expect(input).toHaveCount(1);
    await input.fill(question.answer.text);
    await expect(input).toHaveValue(question.answer.text);
  } else {
    const inputType = question.type === "multiple" ? "checkbox" : "radio";
    for (const value of question.answer.values) {
      const option = root.locator(
        'input[type="' + inputType + '"][value="' + value + '"]',
      );
      await expect(option).toHaveCount(1);
      await option.check();
      await expect(option).toBeChecked();
    }
    if (question.allowOther) {
      const other = root.locator("[data-user-input-other]");
      await expect(other).toHaveCount(1);
      await other.fill(question.answer.other);
      await expect(other).toHaveValue(question.answer.other);
    }
  }
  const confirm = root.locator('[data-user-input-action="confirm"]');
  await expect(confirm).toHaveCount(1);
  await expect(confirm).toBeEnabled();
  await confirm.click();
}

async function exerciseMixedQuestionnaireProgressLifecycle(h4, runtime) {
  const started = await beginQuestionnaireLifecycle(h4, runtime, {
    userMarker: MIXED_QUESTIONNAIRE_CONTRACT.userMarker,
    toolCallId: MIXED_QUESTIONNAIRE_CONTRACT.toolCallId,
    requestId: MIXED_QUESTIONNAIRE_CONTRACT.requestId,
    title: MIXED_QUESTIONNAIRE_CONTRACT.title,
    reason: MIXED_QUESTIONNAIRE_CONTRACT.reason,
    assertToolArguments: (value) => {
      expectMixedQuestionnaireDefinition(mixedQuestionnaireDefinitionProjection(value));
    },
  });
  const {
    page,
    agentRunId,
    waitingAgent,
    firstRuntimeRunId,
    sessionId,
  } = started;
  const waitingEvents = mixedQuestionnaireEventProjection(waitingAgent);
  expect(waitingAgent.nextCursor).toBe(waitingEvents.at(-1)?.seq);
  expect(waitingEvents.map((event) => event.seq)).toEqual(
    waitingEvents.map((_, index) => index + 1),
  );
  const waitingDefinition = mixedQuestionnaireDefinitionProjection({
    title: waitingAgent.pendingInput.title,
    reason: waitingAgent.pendingInput.reason,
    questions: waitingAgent.pendingInput.questions,
  });
  expectMixedQuestionnaireDefinition(waitingDefinition);
  waitingEvents.forEach((event) => {
    (event.toolCalls || []).forEach((call) => expectMixedQuestionnaireDefinition(call.arguments));
    if (event.arguments) expectMixedQuestionnaireDefinition(event.arguments);
    if (event.inputRequest) expectMixedQuestionnaireDefinition(event.inputRequest);
  });
  const waitingExecution = mixedQuestionnaireExecutionProjection(waitingAgent);
  expect(waitingExecution).toHaveLength(1);
  expectMixedQuestionnaireDefinition(waitingExecution[0].arguments);

  const q1Dom = await mixedQuestionnaireDomProjection(h4, "q1", 0);
  await expect(page.locator("#activeRunBanner.visible")).toHaveCount(1);
  await expect(page.locator("#stopBtn")).toBeEnabled();

  async function waitForProgressSession(statuses) {
    let response = null;
    await expect.poll(async () => {
      response = await fetchProductionJson(
        page,
        `/api/sessions/${encodeURIComponent(sessionId)}`,
      );
      const request = response.body?.runState?.userInputRequest || {};
      return {
        status: response.status,
        roles: (response.body?.messages || []).map((message) => message.role),
        runStatus: response.body?.runState?.status,
        cursor: response.body?.runState?.agentEventCursor,
        requestIdMatches: request.id === MIXED_QUESTIONNAIRE_CONTRACT.requestId,
        questionStatuses: (request.questions || []).map((question) => question.status),
      };
    }).toEqual({
      status: 200,
      roles: ["user", "assistant", "tool-call"],
      runStatus: "waiting-user-input",
      cursor: waitingAgent.nextCursor,
      requestIdMatches: true,
      questionStatuses: statuses,
    });
    return response.body;
  }

  async function fetchWaitingAgent() {
    const response = await fetchProductionJson(
      page,
      `/api/agent/runs/${encodeURIComponent(agentRunId)}?cursor=0&wait=0`,
    );
    expect(response.status).toBe(200);
    return response.body;
  }

  const initialSession = await waitForProgressSession(["pending", "pending", "pending"]);
  const initialProgress = mixedQuestionnaireProgressSnapshot(
    waitingAgent,
    initialSession,
    agentRunId,
  );
  expectMixedQuestionnaireProgress(
    initialProgress,
    ["pending", "pending", "pending"],
    waitingAgent.nextCursor,
  );
  const metricsAtWaiting = await h4.metrics();
  expect(metricsAtWaiting.chatRequests).toEqual([{
    scenario: "mixed-questionnaire-call",
    stream: true,
    hasToolResult: false,
  }]);
  expect(metricsAtWaiting.toolExecutions).toEqual([]);
  expect(metricsAtWaiting.productionToolDelegations).toBe(0);
  expect(metricsAtWaiting.unsafeToolRequests).toBe(0);
  expect(metricsAtWaiting.production.agentRuns).toHaveLength(1);
  expect(metricsAtWaiting.production.runtimeRuns).toHaveLength(1);
  const waitingProductionIdentity = {
    agentRunIds: metricsAtWaiting.production.agentRuns.map((run) => run.agentRunId),
    runtimeRunIds: metricsAtWaiting.production.runtimeRuns.map((run) => run.runtimeRunId),
  };
  expect(waitingProductionIdentity).toEqual({
    agentRunIds: [idHash(agentRunId)],
    runtimeRunIds: [idHash(firstRuntimeRunId)],
  });
  const expectWaitingProductionIdentity = (metrics) => {
    expect(metrics.production.agentRuns).toHaveLength(1);
    expect(metrics.production.runtimeRuns).toHaveLength(1);
    expect({
      agentRunIds: metrics.production.agentRuns.map((run) => run.agentRunId),
      runtimeRunIds: metrics.production.runtimeRuns.map((run) => run.runtimeRunId),
    }).toEqual(waitingProductionIdentity);
  };

  const q1Boundary = h4.requestBoundary();
  await answerMixedQuestionnaireQuestion(page, 0);
  const q2Dom = await mixedQuestionnaireDomProjection(h4, "q2", 1);
  const q1Session = await waitForProgressSession(["resolved", "pending", "pending"]);
  const q1Agent = await fetchWaitingAgent();
  const q1Progress = mixedQuestionnaireProgressSnapshot(q1Agent, q1Session, agentRunId);
  expectMixedQuestionnaireProgress(
    q1Progress,
    ["resolved", "pending", "pending"],
    waitingAgent.nextCursor,
  );
  expect(mixedQuestionnaireEventProjection(q1Agent)).toEqual(waitingEvents);
  expect(mixedQuestionnaireExecutionProjection(q1Agent)).toEqual(waitingExecution);
  const metricsAfterQ1 = await h4.metrics();
  expectWaitingProductionIdentity(metricsAfterQ1);
  const q1Requests = questionnaireRequestProjection(
    h4,
    q1Boundary,
    metricsAtWaiting,
    metricsAfterQ1,
  );
  expectMixedQuestionnaireZeroRequests(q1Requests);
  const q1ActionTargets = mixedQuestionnaireActionTargetProjection(h4, q1Boundary, agentRunId);
  expectMixedQuestionnaireActionTargets(q1ActionTargets, 0, 0);

  const q2Boundary = h4.requestBoundary();
  await answerMixedQuestionnaireQuestion(page, 1);
  const q3Dom = await mixedQuestionnaireDomProjection(h4, "q3", 2);
  const q2Session = await waitForProgressSession(["resolved", "resolved", "pending"]);
  const q2Agent = await fetchWaitingAgent();
  const q2Progress = mixedQuestionnaireProgressSnapshot(q2Agent, q2Session, agentRunId);
  expectMixedQuestionnaireProgress(
    q2Progress,
    ["resolved", "resolved", "pending"],
    waitingAgent.nextCursor,
  );
  expect(mixedQuestionnaireEventProjection(q2Agent)).toEqual(waitingEvents);
  expect(mixedQuestionnaireExecutionProjection(q2Agent)).toEqual(waitingExecution);
  const metricsAfterQ2 = await h4.metrics();
  expectWaitingProductionIdentity(metricsAfterQ2);
  const q2Requests = questionnaireRequestProjection(
    h4,
    q2Boundary,
    metricsAfterQ1,
    metricsAfterQ2,
  );
  expectMixedQuestionnaireZeroRequests(q2Requests);
  const q2ActionTargets = mixedQuestionnaireActionTargetProjection(h4, q2Boundary, agentRunId);
  expectMixedQuestionnaireActionTargets(q2ActionTargets, 0, 0);

  const progressReloadBoundary = h4.requestBoundary();
  await h4.reloadRuntime(runtime);
  await page.locator("#baseUrl").evaluate((element, fakeUrl) => {
    element.value = fakeUrl;
  }, h4.host.ready.fakeUrl);
  await expect(page.locator("#baseUrl")).toHaveValue(h4.host.ready.fakeUrl);
  const restoredQ3Dom = await mixedQuestionnaireDomProjection(h4, "q3-reloaded", 2);
  expect(restoredQ3Dom).toEqual(q3Dom);
  await expect(page.locator("#activeRunBanner.visible")).toHaveCount(0);
  await expect(page.locator("#stopBtn")).toBeDisabled();
  const q2AgentAfterReload = await fetchWaitingAgent();
  const q2SessionAfterReload = await waitForProgressSession(["resolved", "resolved", "pending"]);
  const restoredProgress = mixedQuestionnaireProgressSnapshot(
    q2AgentAfterReload,
    q2SessionAfterReload,
    agentRunId,
  );
  expectMixedQuestionnaireProgress(
    restoredProgress,
    ["resolved", "resolved", "pending"],
    waitingAgent.nextCursor,
  );
  expect(restoredProgress).toEqual(q2Progress);
  expect(mixedQuestionnaireEventProjection(q2AgentAfterReload)).toEqual(waitingEvents);
  expect(mixedQuestionnaireExecutionProjection(q2AgentAfterReload)).toEqual(waitingExecution);
  const metricsAfterProgressReload = await h4.metrics();
  expectWaitingProductionIdentity(metricsAfterProgressReload);
  expect(metricsAfterProgressReload.chatRequests).toEqual(metricsAfterQ2.chatRequests);
  expect(metricsAfterProgressReload.toolExecutions).toEqual(metricsAfterQ2.toolExecutions);
  const progressReloadRequests = questionnaireRequestProjection(
    h4,
    progressReloadBoundary,
    metricsAfterQ2,
    metricsAfterProgressReload,
  );
  expectMixedQuestionnaireZeroRequests(progressReloadRequests);
  const progressReloadActionTargets = mixedQuestionnaireActionTargetProjection(
    h4,
    progressReloadBoundary,
    agentRunId,
  );
  expectMixedQuestionnaireActionTargets(progressReloadActionTargets, 0, 0);

  const submissionBoundary = h4.requestBoundary();
  await answerMixedQuestionnaireQuestion(page, 2);
  const completed = await completeQuestionnaireLifecycle(h4, started, {
    finalMarker: MIXED_QUESTIONNAIRE_CONTRACT.finalMarker,
    toolCallId: MIXED_QUESTIONNAIRE_CONTRACT.toolCallId,
    submissionBoundary,
    submissionMetricsBefore: metricsAfterProgressReload,
  });
  const {
    completedAgent,
    runtimeRunIds,
    runtimeSnapshots,
    terminalSessionResponse,
    metricsAtTerminal,
    submissionRequests,
    totalRequests,
  } = completed;
  const terminalEvents = mixedQuestionnaireEventProjection(completedAgent);
  expect(completedAgent.nextCursor).toBe(terminalEvents.at(-1)?.seq);
  expect(terminalEvents.map((event) => event.seq)).toEqual(
    terminalEvents.map((_, index) => index + 1),
  );
  terminalEvents.forEach((event) => {
    (event.toolCalls || []).forEach((call) => expectMixedQuestionnaireDefinition(call.arguments));
    if (event.arguments) expectMixedQuestionnaireDefinition(event.arguments);
    if (event.inputRequest) expectMixedQuestionnaireDefinition(event.inputRequest);
    if (event.result) {
      expectMixedQuestionnaireResult(event.result, [
        { values: "array", text: "null" },
        { values: "array", text: "null" },
        { values: "null", text: "string" },
      ]);
    }
  });
  const terminalExecution = mixedQuestionnaireExecutionProjection(completedAgent);
  expect(terminalExecution).toHaveLength(1);
  expect(terminalExecution[0]).toMatchObject({
    toolCallMatches: true,
    name: "request_user_input",
    status: "completed",
    outcome: "succeeded",
    failureCountAbsent: true,
    failureSignatureAbsent: true,
  });
  expectMixedQuestionnaireDefinition(terminalExecution[0].arguments);
  expectMixedQuestionnaireResult(terminalExecution[0].result, [
    { values: "array", text: "null" },
    { values: "array", text: "null" },
    { values: "null", text: "string" },
  ]);

  const runtimeProjection = runtimeSnapshots.map((snapshot, index) => ({
    runtime: "runtime-" + (index + 1),
    status: String(snapshot.status || ""),
    nextCursor: Number(snapshot.nextCursor || 0),
    eventTypes: (snapshot.events || []).map((event) => String(event?.type || "")),
    content: snapshot.result?.content === MIXED_QUESTIONNAIRE_CONTRACT.finalMarker
      ? "final"
      : "empty",
    finishReason: String(snapshot.result?.finishReason || ""),
    toolCalls: (snapshot.result?.toolCalls || []).map((call) => ({
      toolCallMatches: String(call?.id || "") === MIXED_QUESTIONNAIRE_CONTRACT.toolCallId,
      name: String(call?.function?.name || ""),
      arguments: mixedQuestionnaireDefinitionProjection(call?.function?.arguments),
    })),
  }));
  expect(runtimeProjection[0]).toMatchObject({
    runtime: "runtime-1",
    status: "completed",
    content: "empty",
    finishReason: "tool_calls",
    toolCalls: [{ toolCallMatches: true, name: "request_user_input" }],
  });
  expectMixedQuestionnaireDefinition(runtimeProjection[0].toolCalls[0].arguments);
  expect(runtimeProjection[1]).toMatchObject({
    runtime: "runtime-2",
    status: "completed",
    content: "final",
    finishReason: "stop",
    toolCalls: [],
  });

  const terminalDom = await mixedQuestionnaireDomProjection(h4, "terminal");
  await expect(page.locator("#activeRunBanner.visible")).toHaveCount(0);
  await expect(page.locator("#stopBtn")).toBeDisabled();
  await expect(page.locator("#messages .execution-trace.active")).toHaveCount(0);
  await expect(page.locator("#messages .execution-trace.completed")).toHaveCount(1);
  const sessionRoleContent = mixedQuestionnaireSessionRoleProjection(
    terminalSessionResponse.body.messages,
  );
  expect(sessionRoleContent).toEqual([
    { role: "user", kind: "initial-user" },
    { role: "assistant", kind: "tool-owner" },
    { role: "tool-call", kind: "questionnaire-call" },
    { role: "user", kind: "input-summary" },
    { role: "tool-result", kind: "questionnaire-result" },
    { role: "assistant", kind: "final" },
  ]);
  const sessionInputMeta = mixedQuestionnaireSessionMetaProjection(
    terminalSessionResponse.body.messages,
    agentRunId,
  );
  expect(sessionInputMeta).toHaveLength(3);
  expect(sessionInputMeta.map((item) => item.role)).toEqual(["tool-call", "user", "tool-result"]);
  expect(sessionInputMeta[0]).toMatchObject({
    toolCallMatches: true,
    agentRunMatches: true,
    eventType: "tool_started",
    action: "request_user_input",
    native: true,
    replayed: false,
  });
  expectMixedQuestionnaireDefinition(sessionInputMeta[0].arguments);
  expect(sessionInputMeta[1]).toMatchObject({
    kind: "user-input-summary",
    system: true,
    skipApi: true,
    requestIdMatches: true,
    titleMatches: true,
  });
  expectMixedQuestionnaireResult(sessionInputMeta[1].result, [
    { values: "array", text: "absent" },
    { values: "array", text: "absent" },
    { values: "absent", text: "string" },
  ]);
  expect(sessionInputMeta[2]).toMatchObject({
    toolCallMatches: true,
    agentRunMatches: true,
    eventType: "tool_completed",
    action: "request_user_input",
    native: true,
    replayed: false,
    outcome: "succeeded",
  });
  expectMixedQuestionnaireResult(sessionInputMeta[2].result, [
    { values: "array", text: "null" },
    { values: "array", text: "null" },
    { values: "null", text: "string" },
  ]);

  expect(metricsAtTerminal.chatRequests).toEqual([
    { scenario: "mixed-questionnaire-call", stream: true, hasToolResult: false },
    {
      scenario: "mixed-questionnaire-final",
      stream: true,
      hasToolResult: true,
      mixedQuestionnaireReceipt: {
        receiptCount: 1,
        parseable: true,
        nameMatches: true,
        ok: true,
        actionMatches: true,
        requestIdMatches: true,
        titleMatches: true,
        answerCount: 3,
        answerOrderMatches: true,
        allResolved: true,
        typesMatch: true,
        promptsMatch: true,
        singleValueCount: 1,
        singleSelectionMatches: true,
        singleAnswerMatches: true,
        singleOtherEmpty: true,
        multipleValueCount: 2,
        multipleSelectionsMatch: true,
        multipleOtherMatches: true,
        multipleAnswerMarkersMatch: true,
        textValuesAbsent: true,
        textMatches: true,
        textAnswerMatches: true,
        textOtherEmpty: true,
        summaryMarkersMatch: true,
      },
    },
  ]);
  expect(metricsAtTerminal.toolExecutions).toEqual([]);
  expect(metricsAtTerminal.productionToolDelegations).toBe(0);
  expect(metricsAtTerminal.unsafeToolRequests).toBe(0);
  expect(metricsAtTerminal.production.agentRuns).toHaveLength(1);
  expect(metricsAtTerminal.production.runtimeRuns).toHaveLength(2);
  const submissionActionTargets = mixedQuestionnaireActionTargetProjection(
    h4,
    submissionBoundary,
    agentRunId,
  );
  expectMixedQuestionnaireActionTargets(submissionActionTargets, 1, 1);
  const terminalReload = await reloadCompletedQuestionnaireLifecycle(h4, started, completed);
  const restoredTerminalDom = await mixedQuestionnaireDomProjection(h4, "terminal");
  expect(restoredTerminalDom).toEqual(terminalDom);
  const {
    terminalRefreshBoundary,
    agentAfterReload,
    sessionAfterReload,
    runtimeSnapshotsAfterReload,
    terminalReloadRequests,
  } = terminalReload;
  expect(mixedQuestionnaireEventProjection(agentAfterReload.body)).toEqual(terminalEvents);
  expect(mixedQuestionnaireExecutionProjection(agentAfterReload.body)).toEqual(terminalExecution);
  expect(mixedQuestionnaireSessionRoleProjection(sessionAfterReload.body.messages))
    .toEqual(sessionRoleContent);
  expect(mixedQuestionnaireSessionMetaProjection(sessionAfterReload.body.messages, agentRunId))
    .toEqual(sessionInputMeta);
  const runtimeProjectionAfterReload = runtimeSnapshotsAfterReload.map((snapshot) => ({
    status: String(snapshot?.status || ""),
    nextCursor: Number(snapshot?.nextCursor || 0),
    eventTypes: (snapshot?.events || []).map((event) => String(event?.type || "")),
    content: snapshot?.result?.content === MIXED_QUESTIONNAIRE_CONTRACT.finalMarker
      ? "final"
      : "empty",
    finishReason: String(snapshot?.result?.finishReason || ""),
    toolCallCount: (snapshot?.result?.toolCalls || []).length,
  }));
  expect(runtimeProjectionAfterReload).toEqual(runtimeProjection.map((snapshot) => ({
    status: snapshot.status,
    nextCursor: snapshot.nextCursor,
    eventTypes: snapshot.eventTypes,
    content: snapshot.content,
    finishReason: snapshot.finishReason,
    toolCallCount: snapshot.toolCalls.length,
  })));
  const terminalReloadActionTargets = mixedQuestionnaireActionTargetProjection(
    h4,
    terminalRefreshBoundary,
    agentRunId,
  );
  expectMixedQuestionnaireActionTargets(terminalReloadActionTargets, 0, 0);

  const progressSnapshots = [initialProgress, q1Progress, q2Progress, restoredProgress];
  const progressRequestFences = {
    q1: { requests: q1Requests, actionTargets: q1ActionTargets },
    q2: { requests: q2Requests, actionTargets: q2ActionTargets },
  };
  const progressDom = [q1Dom, q2Dom, q3Dom, restoredQ3Dom];
  const inputSubmissionProjection = {
    requests: submissionRequests,
    actionTargets: submissionActionTargets,
    events: terminalEvents.slice(waitingEvents.length, 9),
    execution: terminalExecution,
    sameAgentRun: completedAgent.agentRunId === waitingAgent.agentRunId,
    interactionExecutionCount: completedAgent.toolExecutions.length,
  };
  const refreshLifecycle = {
    progress: {
      sameAgentRun: q2AgentAfterReload.agentRunId === agentRunId,
      sameRequest: q2AgentAfterReload.pendingInput?.requestId
        === MIXED_QUESTIONNAIRE_CONTRACT.requestId,
      sameSnapshot: JSON.stringify(restoredProgress) === JSON.stringify(q2Progress),
      dom: restoredQ3Dom,
      requests: progressReloadRequests,
      actionTargets: progressReloadActionTargets,
      interactionExecutionDelta: q2AgentAfterReload.toolExecutions.length
        - q2Agent.toolExecutions.length,
    },
    terminal: {
      sameAgentRun: agentAfterReload.body.agentRunId === agentRunId,
      sameEvents: JSON.stringify(mixedQuestionnaireEventProjection(agentAfterReload.body))
        === JSON.stringify(terminalEvents),
      sameSession: JSON.stringify(
        mixedQuestionnaireSessionRoleProjection(sessionAfterReload.body.messages),
      ) === JSON.stringify(sessionRoleContent),
      sameInputMeta: JSON.stringify(
        mixedQuestionnaireSessionMetaProjection(sessionAfterReload.body.messages, agentRunId),
      ) === JSON.stringify(sessionInputMeta),
      dom: restoredTerminalDom,
      requests: terminalReloadRequests,
      actionTargets: terminalReloadActionTargets,
      interactionExecutionDelta: agentAfterReload.body.toolExecutions.length
        - completedAgent.toolExecutions.length,
    },
  };
  const hashes = {
    waitingEventProjection: canonicalHash(waitingEvents),
    progressSnapshot: canonicalHash({
      snapshots: progressSnapshots,
      requestFences: progressRequestFences,
    }),
    progressDom: canonicalHash(progressDom),
    inputSubmissionProjection: canonicalHash(inputSubmissionProjection),
    runtimeProjection: canonicalHash(runtimeProjection),
    sessionRoleContent: canonicalHash(sessionRoleContent),
    sessionInputMeta: canonicalHash(sessionInputMeta),
    terminalDom: canonicalHash(terminalDom),
    refreshLifecycle: canonicalHash(refreshLifecycle),
  };
  if (Object.values(H4_8B_SEMANTIC_HASHES).every(Boolean)) {
    expect(hashes).toEqual(H4_8B_SEMANTIC_HASHES);
  } else {
    expect(runtime).toBe("bundle");
  }
  h4.evidence(runtime + "-mixed-questionnaire-progress-reload", {
    runtime,
    counts: {
      agentRuns: metricsAtTerminal.production.agentRuns.length,
      runtimes: metricsAtTerminal.production.runtimeRuns.length,
      upstreamChat: metricsAtTerminal.chatRequests.length,
      inputPost: totalRequests.inputPost,
      resumePost: totalRequests.resumePost,
      registeredDelegations: metricsAtTerminal.productionToolDelegations,
      registeredExecutions: metricsAtTerminal.toolExecutions.length,
      interactionExecutions: completedAgent.toolExecutions.length,
    },
    progress: progressSnapshots.map((snapshot) => (
      snapshot.session.runState.questions.map((question) => question.status)
    )),
    events: terminalEvents.map((event) => event.type),
    runtimeCursors: runtimeProjection.map((snapshot) => snapshot.nextCursor),
    progressReload: progressReloadRequests,
    terminalReload: terminalReloadRequests,
    hashes,
  });
}

function editAuthorizationArgumentsProjection(value) {
  const source = value && typeof value === "object" ? value : parseToolArguments(value);
  return {
    keysExact: JSON.stringify(Object.keys(source || {}).sort())
      === JSON.stringify(["newText", "oldText", "path"]),
    pathMatches: String(source?.path || "") === EDIT_AUTHORIZATION_CONTRACT.path,
    oldTextMatches: String(source?.oldText || "") === EDIT_AUTHORIZATION_INITIAL,
    newTextMatches: String(source?.newText || "") === EDIT_AUTHORIZATION_TARGET,
  };
}

function editAuthorizationDiffProjection(value) {
  const diff = String(value || "").replace(/\r\n/g, "\n");
  const count = (marker) => diff.split(marker).length - 1;
  return {
    present: Boolean(diff),
    oldMarkerOnce: count(`-${EDIT_AUTHORIZATION_INITIAL}`) === 1,
    newMarkerOnce: count(`+${EDIT_AUTHORIZATION_TARGET}`) === 1,
    oldHeaderMatches: diff.includes(`--- a/${EDIT_AUTHORIZATION_CONTRACT.path}`),
    newHeaderMatches: diff.includes(`+++ b/${EDIT_AUTHORIZATION_CONTRACT.path}`),
  };
}

function editAuthorizationPendingProjection(value, authorizationId = "") {
  const source = value && typeof value === "object" ? value : {};
  const sourceAuthorizationId = String(source.authorizationId || "");
  const proposalId = String(source.proposalId || "");
  return {
    authorizationIdPresent: /^[0-9a-f]{64}$/.test(sourceAuthorizationId),
    authorizationIdMatches: Boolean(authorizationId)
      && sourceAuthorizationId === authorizationId,
    toolCallMatches: String(source.toolCallId || "")
      === EDIT_AUTHORIZATION_CONTRACT.toolCallId,
    action: String(source.action || ""),
    proposalIdPresent: /^[0-9a-f]{64}$/.test(proposalId),
    pathMatches: String(source.path || "") === EDIT_AUTHORIZATION_CONTRACT.path,
    diff: editAuthorizationDiffProjection(source.diff),
    decision: String(source.decision || ""),
    requestedAtPresent: Boolean(String(source.requestedAt || "")),
    privateFieldsAbsent: ["proposal", "newContent", "baseHash", "newHash"]
      .every((field) => !Object.prototype.hasOwnProperty.call(source, field)),
  };
}

function editAuthorizationResultProjection(value) {
  const source = value && typeof value === "object" ? value : {};
  const proposalId = String(source.proposalId || "");
  return {
    ok: source.ok === true,
    action: String(source.action || ""),
    proposalIdPresent: /^[0-9a-f]{64}$/.test(proposalId),
    pathMatches: String(source.path || "") === EDIT_AUTHORIZATION_CONTRACT.path,
    diff: editAuthorizationDiffProjection(source.diff),
    applied: source.applied === true,
    rejected: source.rejected === true,
    replayed: source.replayed === true,
    backupPresent: Boolean(String(source.backupPath || "")),
    conflict: source.conflict === true,
    errorPresent: Boolean(String(source.error || "")),
    privateFieldsAbsent: ["newContent", "baseHash", "newHash"]
      .every((field) => !Object.prototype.hasOwnProperty.call(source, field)),
    retryFieldsAbsent: ["failureCount", "failureSignature", "retryBlocked", "retryLimitReached"]
      .every((field) => !Object.prototype.hasOwnProperty.call(source, field)),
  };
}

function editAuthorizationEventProjection(snapshot, authorizationId) {
  const events = Array.isArray(snapshot?.events) ? snapshot.events : [];
  const runtimeIds = events
    .filter((event) => event?.type === "model_started")
    .map((event) => String(event?.data?.runtimeRunId || ""));
  const runtimeAliases = new Map(
    runtimeIds.map((runId, index) => [runId, `runtime-${index + 1}`]),
  );
  return events.map((event) => {
    const data = event?.data || {};
    const projected = {
      seq: Number(event?.seq || 0),
      type: String(event?.type || ""),
    };
    if (data.round != null) projected.round = Number(data.round);
    if (data.runtimeRunId) {
      projected.runtimeRunId = runtimeAliases.get(String(data.runtimeRunId)) || "mismatch";
    }
    if (data.content != null) {
      const content = String(data.content || "");
      projected.content = content === EDIT_AUTHORIZATION_CONTRACT.stageMarker
        ? "stage"
        : Object.values(EDIT_AUTHORIZATION_CONTRACT.branches)
          .some((branch) => branch.finalMarker === content)
          ? "final"
          : "empty";
    }
    if (data.finishReason != null) projected.finishReason = String(data.finishReason || "");
    if (Array.isArray(data.toolCalls)) {
      projected.toolCalls = data.toolCalls.map((call) => ({
        toolCallMatches: String(call?.id || "") === EDIT_AUTHORIZATION_CONTRACT.toolCallId,
        name: String(call?.function?.name || call?.name || ""),
        arguments: editAuthorizationArgumentsProjection(
          call?.function?.arguments ?? call?.arguments,
        ),
      }));
    }
    if (data.toolCallId != null) {
      projected.toolCallMatches = String(data.toolCallId || "")
        === EDIT_AUTHORIZATION_CONTRACT.toolCallId;
    }
    if (data.name != null) projected.name = String(data.name || "");
    if (data.arguments != null) {
      projected.arguments = editAuthorizationArgumentsProjection(data.arguments);
    }
    if (event?.type === "authorization_required") {
      projected.authorization = editAuthorizationPendingProjection(data, authorizationId);
    }
    if (event?.type === "authorization_submitted") {
      projected.authorizationIdMatches = Boolean(authorizationId)
        && String(data.authorizationId || "") === authorizationId;
      projected.decision = String(data.decision || "");
    }
    if (data.result != null) projected.result = editAuthorizationResultProjection(data.result);
    if (data.outcome != null) projected.outcome = String(data.outcome || "");
    if (data.replayed != null) projected.replayed = Boolean(data.replayed);
    if (data.resumeStatus != null) projected.resumeStatus = String(data.resumeStatus || "");
    if (data.status != null) projected.status = String(data.status || "");
    if (data.reason != null) projected.reason = String(data.reason || "");
    return projected;
  });
}

function editAuthorizationConflictEventProjection(snapshot, authorizationId) {
  const projected = editAuthorizationEventProjection(snapshot, authorizationId);
  const events = Array.isArray(snapshot?.events) ? snapshot.events : [];
  return projected.map((event, index) => (
    String(events[index]?.data?.content || "") === EDIT_AUTHORIZATION_CONFLICT_CONTRACT.finalMarker
      ? { ...event, content: "final" }
      : event
  ));
}

function editAuthorizationEventProjectionForBranch(snapshot, authorizationId, branch) {
  return branch?.conflict === true
    ? editAuthorizationConflictEventProjection(snapshot, authorizationId)
    : editAuthorizationEventProjection(snapshot, authorizationId);
}

function editAuthorizationExecutionProjection(snapshot) {
  return (Array.isArray(snapshot?.toolExecutions) ? snapshot.toolExecutions : [])
    .map((execution) => ({
      toolCallMatches: String(execution?.toolCallId || "")
        === EDIT_AUTHORIZATION_CONTRACT.toolCallId,
      name: String(execution?.name || ""),
      arguments: editAuthorizationArgumentsProjection(execution?.arguments),
      status: String(execution?.status || ""),
      outcome: String(execution?.outcome || ""),
      authorizationDecision: String(execution?.authorizationDecision || ""),
      result: execution?.result == null
        ? null
        : editAuthorizationResultProjection(execution.result),
      publicFailureCountAbsent: !Object.prototype.hasOwnProperty.call(
        execution || {}, "failureCount",
      ),
      publicFailureSignatureAbsent: !Object.prototype.hasOwnProperty.call(
        execution || {},
        "failureSignature",
      ),
    }));
}

function editAuthorizationSessionRoleProjection(messages, branch) {
  return (Array.isArray(messages) ? messages : []).map((message) => {
    const role = String(message?.role || "");
    const meta = message?.meta || {};
    let kind = "";
    if (role === "user" && message?.content === branch.userMarker) kind = "initial-user";
    else if (role === "assistant" && message?.content === branch.finalMarker) kind = "final";
    else if (role === "assistant" && Array.isArray(meta.toolCalls) && meta.toolCalls.length > 0) {
      kind = "tool-owner";
    } else if (role === "tool-call" && meta.action === "propose_edit") {
      kind = "edit-call";
    } else if (role === "tool-result" && meta.action === "propose_edit") {
      kind = "edit-result";
    }
    return { role, kind };
  });
}

function editAuthorizationSessionMetaProjection(messages, agentRunId, authorizationId) {
  return (Array.isArray(messages) ? messages : [])
    .filter((message) => ["tool-call", "tool-result"].includes(String(message?.role || "")))
    .map((message) => {
      const meta = message?.meta || {};
      const isResult = message.role === "tool-result";
      return {
        role: String(message.role || ""),
        toolCallMatches: String(meta.toolCallId || "")
          === EDIT_AUTHORIZATION_CONTRACT.toolCallId,
        agentRunMatches: String(meta.agentRunId || "") === agentRunId,
        eventType: String(meta.agentEventType || ""),
        eventSeq: Number(meta.agentEventSeq || 0),
        action: String(meta.action || ""),
        native: meta.native === true,
        serverManaged: meta.serverManaged === true,
        replayed: Boolean(meta.replayed),
        outcome: String(meta.outcome || ""),
        arguments: !isResult ? editAuthorizationArgumentsProjection({
          path: meta.tool?.path,
          oldText: meta.tool?.oldText,
          newText: meta.tool?.newText,
        }) : null,
        authorization: isResult ? {
          authorizationIdMatches: String(meta.authorizationId || "") === authorizationId,
          authorizationAction: String(meta.authorizationAction || ""),
          pendingEditPresent: Boolean(String(meta.pendingEditId || "")),
          pathMatches: String(meta.path || "") === EDIT_AUTHORIZATION_CONTRACT.path,
          decision: String(meta.authorizationDecision || ""),
          applied: meta.applied === true,
          rejected: meta.rejected === true,
          result: meta.result && typeof meta.result === "object"
            ? editAuthorizationResultProjection(meta.result)
            : null,
          authorizationResult: meta.authorizationResult && typeof meta.authorizationResult === "object"
            ? editAuthorizationResultProjection(meta.authorizationResult)
            : null,
        } : null,
      };
    });
}

function editAuthorizationSessionDiffProjection(messages, pendingAuthorization) {
  const source = pendingAuthorization && typeof pendingAuthorization === "object"
    ? pendingAuthorization
    : {};
  const matches = (Array.isArray(messages) ? messages : []).filter((message) => (
    message?.role === "tool-result"
    && message?.meta?.action === "propose_edit"
    && message?.meta?.serverManaged === true
  ));
  const message = matches[0] || {};
  const meta = message.meta || {};
  const proposalId = String(source.proposalId || "");
  return {
    resultCount: matches.length,
    content: editAuthorizationDiffProjection(message.content),
    pendingEditIdMatches: Boolean(proposalId)
      && String(meta.pendingEditId || "") === `server-edit-${proposalId}`,
    pathMatches: String(meta.path || "") === EDIT_AUTHORIZATION_CONTRACT.path,
    authorizationIdMatches: Boolean(String(source.authorizationId || ""))
      && String(meta.authorizationId || "") === String(source.authorizationId),
    toolCallMatches: String(meta.toolCallId || "")
      === EDIT_AUTHORIZATION_CONTRACT.toolCallId,
  };
}

function editAuthorizationRunStateProjection(runState, agentRunId, authorizationId, sessionId) {
  const source = runState && typeof runState === "object" ? runState : {};
  const request = source.authorizationRequest && typeof source.authorizationRequest === "object"
    ? source.authorizationRequest
    : {};
  const tool = request.tool && typeof request.tool === "object" ? request.tool : {};
  return {
    status: String(source.status || ""),
    phase: String(source.phase || ""),
    executionOwner: String(source.executionOwner || ""),
    permissionProfile: String(source.permissionProfile || ""),
    agentRunMatches: String(source.agentRunId || "") === agentRunId,
    runtimeRunCleared: !String(source.runtimeRunId || ""),
    cursor: Number(source.agentEventCursor || 0),
    modelRound: Number(source.modelRound || 0),
    request: {
      idMatches: String(request.id || "") === `server-authorization-${authorizationId}`,
      sessionIdMatches: String(request.sessionId || "") === sessionId,
      sourceKey: String(request.sourceKey || ""),
      sourceLabelPresent: Boolean(String(request.sourceLabel || "")),
      editIdMatches: String(request.editId || "")
        === `server-edit-${String(request.proposalId || "")}`,
      status: String(request.status || ""),
      selected: request.selected === true,
      serverAgent: request.serverAgent === true,
      detachedBackground: request.detachedBackground === true,
      backgroundJobCleared: !String(request.backgroundJobId || ""),
      agentRunMatches: String(request.agentRunId || "") === agentRunId,
      authorizationIdMatches: String(request.authorizationId || "") === authorizationId,
      proposalIdPresent: /^[0-9a-f]{64}$/.test(String(request.proposalId || "")),
      toolCallMatches: String(request.toolCallId || "")
        === EDIT_AUTHORIZATION_CONTRACT.toolCallId,
      tool: {
        action: String(tool.action || ""),
        pathMatches: String(tool.path || "") === EDIT_AUTHORIZATION_CONTRACT.path,
        commandEmpty: !String(tool.command || ""),
        descriptionEmpty: !String(tool.description || ""),
      },
      stats: {
        additions: Number(request.stats?.additions ?? -1),
        removals: Number(request.stats?.removals ?? -1),
      },
    },
  };
}

function editAuthorizationWaitingSnapshotProjection(agent, session, agentRunId, authorizationId) {
  return {
    agent: {
      status: String(agent?.status || ""),
      permissionProfile: String(agent?.permissionProfile || ""),
      nextCursor: Number(agent?.nextCursor || 0),
      round: Number(agent?.round || 0),
      activeRuntimeCleared: !String(agent?.activeRuntimeRunId || ""),
      pendingToolCallCount: Array.isArray(agent?.pendingToolCalls)
        ? agent.pendingToolCalls.length
        : -1,
      pendingAuthorization: editAuthorizationPendingProjection(
        agent?.pendingAuthorization,
        authorizationId,
      ),
      executions: editAuthorizationExecutionProjection(agent),
    },
    session: {
      roles: editAuthorizationSessionRoleProjection(
        session?.messages,
        EDIT_AUTHORIZATION_CONTRACT.branches.approved,
      ).map((item) => item.role),
      runState: editAuthorizationRunStateProjection(
        session?.runState,
        agentRunId,
        authorizationId,
        String(session?.id || ""),
      ),
      meta: editAuthorizationSessionMetaProjection(
        session?.messages,
        agentRunId,
        authorizationId,
      ),
      diff: editAuthorizationSessionDiffProjection(
        session?.messages,
        agent?.pendingAuthorization,
      ),
    },
  };
}

function editAuthorizationFileStateProjection(value) {
  const source = value && typeof value === "object" ? value : {};
  return {
    state: String(source.state || ""),
    exists: source.exists === true,
    initialHashMatches: source.initialHashMatches === true,
    targetHashMatches: source.targetHashMatches === true,
  };
}

function editAuthorizationMetricsProjection(metrics) {
  const source = metrics && typeof metrics === "object" ? metrics : {};
  return {
    counters: {
      registeredDelegations: Number(source.productionToolDelegations || 0),
      proposalDelegations: Number(source.productionEditProposalDelegations || 0),
      applyDelegations: Number(source.productionEditApplyDelegations || 0),
      writes: Number(source.productionEditWrites || 0),
      backups: Number(source.productionEditBackups || 0),
      unsafe: Number(source.unsafeToolRequests || 0),
    },
    registeredExecutions: (source.toolExecutions || []).map((execution) => ({
      action: String(execution?.action || ""),
      pathMatches: String(execution?.path || "") === EDIT_AUTHORIZATION_CONTRACT.path,
      payloadKeysMatch: execution?.payloadKeysMatch === true,
      payloadBytesMatch: execution?.payloadBytesMatch === true,
    })),
    proposalTimeline: (source.proposeEditProposalTimeline || []).map((item) => ({
      action: String(item?.action || ""),
      pathMatches: String(item?.path || "") === EDIT_AUTHORIZATION_CONTRACT.path,
      payloadKeysMatch: item?.payloadKeysMatch === true,
      payloadBytesMatch: item?.payloadBytesMatch === true,
      fileBefore: editAuthorizationFileStateProjection(item?.fileBefore),
      fileAfter: editAuthorizationFileStateProjection(item?.fileAfter),
      backupCountBefore: Number(item?.backupCountBefore || 0),
      backupCountAfter: Number(item?.backupCountAfter || 0),
      result: {
        shapeMatches: item?.result?.shapeMatches === true,
        ok: item?.result?.ok === true,
        actionMatches: item?.result?.actionMatches === true,
        pathMatches: item?.result?.pathMatches === true,
        proposalIdPresent: item?.result?.proposalIdPresent === true,
        baseHashMatches: item?.result?.baseHashMatches === true,
        newHashMatches: item?.result?.newHashMatches === true,
        newContentHashMatches: item?.result?.newContentHashMatches === true,
        applied: item?.result?.applied === true,
      },
    })),
    applyTimeline: (source.proposeEditApplyTimeline || []).map((item) => ({
      proposalShapeMatches: item?.proposalShapeMatches === true,
      fileBefore: editAuthorizationFileStateProjection(item?.fileBefore),
      fileAfter: editAuthorizationFileStateProjection(item?.fileAfter),
      result: {
        ok: item?.result?.ok === true,
        actionMatches: item?.result?.actionMatches === true,
        pathMatches: item?.result?.pathMatches === true,
        proposalIdMatches: item?.result?.proposalIdMatches === true,
        applied: item?.result?.applied === true,
        replayed: item?.result?.replayed === true,
        backupPresent: item?.result?.backupPresent === true,
      },
    })),
    writeTimeline: (source.proposeEditWriteTimeline || []).map((item) => ({
      fileBefore: editAuthorizationFileStateProjection(item?.fileBefore),
      fileAfter: editAuthorizationFileStateProjection(item?.fileAfter),
      writeObserved: item?.writeObserved === true,
      targetHashMatches: item?.targetHashMatches === true,
    })),
    backupTimeline: (source.proposeEditBackupTimeline || []).map((item) => ({
      beforeCount: Number(item?.beforeCount || 0),
      afterCount: Number(item?.afterCount || 0),
      delta: Number(item?.delta || 0),
      initialContentMatchDelta: Number(item?.initialContentMatchDelta || 0),
      backupObserved: item?.backupObserved === true,
    })),
  };
}

function editAuthorizationConflictFileStateProjection(value) {
  const source = value && typeof value === "object" ? value : {};
  return {
    ...editAuthorizationFileStateProjection(source),
    thirdPartyHashMatches: source.thirdPartyHashMatches === true,
  };
}

function editAuthorizationThirdPartyTransitionProjection(value) {
  const source = value && typeof value === "object" ? value : {};
  const callbacks = source.productionCallbacks && typeof source.productionCallbacks === "object"
    ? source.productionCallbacks
    : {};
  return {
    accepted: source.accepted === true,
    reason: String(source.reason || ""),
    commandKeysExact: source.commandKeysExact === true,
    attempt: Number(source.attempt || 0),
    pathMatches: String(source.path || "") === EDIT_AUTHORIZATION_CONTRACT.path,
    fileBefore: editAuthorizationConflictFileStateProjection(source.fileBefore),
    fileAfter: editAuthorizationConflictFileStateProjection(source.fileAfter),
    fixedBytes: {
      byteLength: Number(source.fixedBytes?.byteLength || 0),
      sha256Matches: String(source.fixedBytes?.sha256 || "")
        === EDIT_AUTHORIZATION_THIRD_PARTY_SHA256,
      hashMatches: source.fixedBytes?.hashMatches === true,
    },
    projectTreeUnchanged: source.projectTreeUnchanged === true,
    projectTreeChangedOnlyAtFixedPath: source.projectTreeChangedOnlyAtFixedPath === true,
    homeTreeUnchanged: source.homeTreeUnchanged === true,
    artifactsTreeUnchanged: source.artifactsTreeUnchanged === true,
    backupCountBefore: Number(source.backupCountBefore || 0),
    backupCountAfter: Number(source.backupCountAfter || 0),
    productionCallbacks: {
      registeredDelegations: Number(callbacks.registeredDelegations || 0),
      proposalDelegations: Number(callbacks.proposalDelegations || 0),
      applyDelegations: Number(callbacks.applyDelegations || 0),
      writes: Number(callbacks.writes || 0),
      backups: Number(callbacks.backups || 0),
      toolExecutions: Number(callbacks.toolExecutions || 0),
      runCommandAttempts: Number(callbacks.runCommandAttempts || 0),
    },
  };
}

function editAuthorizationConflictMetricsProjection(metrics) {
  const source = metrics && typeof metrics === "object" ? metrics : {};
  return {
    counters: {
      conflictObservations: Number(source.productionEditConflictObservations || 0),
      transitionAttempts: Number(source.proposeEditThirdPartyTransitionAttempts || 0),
      transitionWrites: Number(source.proposeEditThirdPartyTransitionWrites || 0),
      transitionRejections: Number(source.proposeEditThirdPartyTransitionRejections || 0),
    },
    transitionTimeline: (source.proposeEditThirdPartyTransitionTimeline || [])
      .map(editAuthorizationThirdPartyTransitionProjection),
    conflictTimeline: (source.proposeEditConflictTimeline || []).map((item) => ({
      observed: item?.observed === true,
      exceptionTypeMatches: item?.exceptionTypeMatches === true,
      fileBefore: editAuthorizationConflictFileStateProjection(item?.fileBefore),
      fileAfter: editAuthorizationConflictFileStateProjection(item?.fileAfter),
      fixturePreserved: item?.fixturePreserved === true,
      backupDelta: Number(item?.backupDelta || 0),
    })),
    applyTimeline: (source.proposeEditApplyTimeline || []).map((item) => ({
      proposalShapeMatches: item?.proposalShapeMatches === true,
      conflictObserved: item?.conflictObserved === true,
      fileBefore: editAuthorizationConflictFileStateProjection(item?.fileBefore),
      fileAfter: editAuthorizationConflictFileStateProjection(item?.fileAfter),
      resultPresent: Boolean(item?.result && (
        item.result.ok === true
        || item.result.actionMatches === true
        || item.result.pathMatches === true
        || item.result.proposalIdMatches === true
        || item.result.applied === true
        || item.result.replayed === true
        || item.result.backupPresent === true
      )),
    })),
    writeTimeline: (source.proposeEditWriteTimeline || []).map((item) => ({
      fileBefore: editAuthorizationConflictFileStateProjection(item?.fileBefore),
      fileAfter: editAuthorizationConflictFileStateProjection(item?.fileAfter),
      writeObserved: item?.writeObserved === true,
      targetHashMatches: item?.targetHashMatches === true,
    })),
    backupTimeline: (source.proposeEditBackupTimeline || []).map((item) => ({
      beforeCount: Number(item?.beforeCount || 0),
      afterCount: Number(item?.afterCount || 0),
      delta: Number(item?.delta || 0),
      initialContentMatchDelta: Number(item?.initialContentMatchDelta || 0),
      backupObserved: item?.backupObserved === true,
    })),
  };
}

function editAuthorizationConflictRawResultProjection(value, proposalId) {
  const source = value && typeof value === "object" ? value : {};
  return {
    keysExact: JSON.stringify(Object.keys(source).sort()) === JSON.stringify([
      "action",
      "applied",
      "conflict",
      "currentMtime",
      "error",
      "ok",
      "path",
      "proposalId",
    ]),
    ok: source.ok === true,
    action: String(source.action || ""),
    proposalIdMatches: Boolean(proposalId)
      && String(source.proposalId || "") === String(proposalId),
    pathMatches: String(source.path || "") === EDIT_AUTHORIZATION_CONTRACT.path,
    conflict: source.conflict === true,
    applied: source.applied === true,
    currentMtimePresent: Object.prototype.hasOwnProperty.call(source, "currentMtime")
      && Number.isInteger(source.currentMtime)
      && source.currentMtime > 0,
    errorPresent: Boolean(String(source.error || "").trim()),
    rejectedAbsent: !Object.prototype.hasOwnProperty.call(source, "rejected"),
    replayedAbsent: !Object.prototype.hasOwnProperty.call(source, "replayed"),
    backupPathAbsent: !Object.prototype.hasOwnProperty.call(source, "backupPath"),
  };
}

function editAuthorizationRequestProjection(h4, boundary, beforeMetrics, afterMetrics, agentRunId) {
  const requests = h4.requestEvidenceSince(boundary);
  const summary = h4.requestSummarySince(boundary);
  const entries = h4.loopbackRequests.slice(Number(boundary) || 0);
  const targetHash = idHash(agentRunId);
  const actionTarget = (kind) => {
    const matches = entries.filter((entry) => entry.kind === kind && entry.method === "POST");
    return {
      count: matches.length,
      allTargetRun: Boolean(targetHash) && matches.every((entry) => entry.idHash === targetHash),
    };
  };
  return {
    agentRunPost: requests.agentPost,
    runtimePost: requests.runtimePost,
    agentDelete: requests.agentDelete,
    authorizationPost: summary["POST /api/agent/runs/[id]/authorization"] || 0,
    resumePost: summary["POST /api/agent/runs/[id]/resume"] || 0,
    inputPost: summary["POST /api/agent/runs/[id]/input"] || 0,
    browserProxyChatPost: summary["POST /proxy/chat"] || 0,
    browserToolPost: Object.entries(summary)
      .filter(([key]) => key.startsWith("POST /api/tools/"))
      .reduce((total, [, count]) => total + count, 0),
    upstreamChatDelta: afterMetrics.chatRequests.length - beforeMetrics.chatRequests.length,
    registeredDelegationDelta: Number(afterMetrics.productionToolDelegations || 0)
      - Number(beforeMetrics.productionToolDelegations || 0),
    registeredExecutionDelta: afterMetrics.toolExecutions.length
      - beforeMetrics.toolExecutions.length,
    proposalDelegationDelta: Number(afterMetrics.productionEditProposalDelegations || 0)
      - Number(beforeMetrics.productionEditProposalDelegations || 0),
    applyDelegationDelta: Number(afterMetrics.productionEditApplyDelegations || 0)
      - Number(beforeMetrics.productionEditApplyDelegations || 0),
    writeDelta: Number(afterMetrics.productionEditWrites || 0)
      - Number(beforeMetrics.productionEditWrites || 0),
    backupDelta: Number(afterMetrics.productionEditBackups || 0)
      - Number(beforeMetrics.productionEditBackups || 0),
    unsafeDelta: Number(afterMetrics.unsafeToolRequests || 0)
      - Number(beforeMetrics.unsafeToolRequests || 0),
    targets: {
      authorization: actionTarget("agent-authorization"),
      resume: actionTarget("agent-resume"),
    },
  };
}

function editAuthorizationRetryRequestProjection(
  request,
  expectedUrl,
  agentRunId,
  authorizationId,
) {
  const url = new URL(request.url());
  let body = null;
  let bodyParseable = true;
  try {
    body = request.postDataJSON();
  } catch {
    bodyParseable = false;
  }
  const bodyObject = body && typeof body === "object" && !Array.isArray(body) ? body : {};
  const runMatch = url.pathname.match(/^\/api\/agent\/runs\/([^/]+)\/authorization$/);
  return {
    method: request.method(),
    exactUrl: request.url() === expectedUrl,
    targetRunMatches: Boolean(runMatch)
      && decodeURIComponent(runMatch[1]) === agentRunId,
    queryEmpty: url.search === "",
    hashEmpty: url.hash === "",
    body: {
      parseable: bodyParseable,
      keysExact: JSON.stringify(Object.keys(bodyObject).sort())
        === JSON.stringify(["authorizationId", "decision"]),
      authorizationIdMatches: String(bodyObject.authorizationId || "") === authorizationId,
      decision: String(bodyObject.decision || ""),
    },
  };
}

async function editAuthorizationRetryUiProjection(page) {
  return page.evaluate(() => {
    const panel = document.querySelector("#authorizationPanel");
    const row = panel?.querySelector(".authorization-row") || null;
    const selected = row?.querySelector("[data-auth-select]") || null;
    const approve = panel?.querySelector('[data-auth-action="approve"]') || null;
    const errorToasts = [...document.querySelectorAll("#toastContainer .toast.error")];
    return {
      panelVisible: Boolean(panel && !panel.classList.contains("hidden")),
      rowCount: panel?.querySelectorAll(".authorization-row").length || 0,
      rowSubmitting: Boolean(row?.classList.contains("is-submitting")),
      selected: Boolean(selected?.checked),
      selectionDisabled: Boolean(selected?.disabled),
      approveCount: panel?.querySelectorAll('[data-auth-action="approve"]').length || 0,
      approveEnabled: Boolean(approve && !approve.disabled),
      errorToastCount: errorToasts.length,
      errorToastVisible: errorToasts.some((toast) => {
        const style = getComputedStyle(toast);
        return style.display !== "none" && style.visibility !== "hidden" && style.opacity !== "0";
      }),
      errorToastNonEmpty: errorToasts.some((toast) => Boolean(toast.textContent.trim())),
    };
  });
}

function expectEditAuthorizationArguments(projection) {
  expect(projection).toEqual({
    keysExact: true,
    pathMatches: true,
    oldTextMatches: true,
    newTextMatches: true,
  });
}

function expectEditAuthorizationPending(projection) {
  expect(projection).toEqual({
    authorizationIdPresent: true,
    authorizationIdMatches: true,
    toolCallMatches: true,
    action: "apply_edit",
    proposalIdPresent: true,
    pathMatches: true,
    diff: {
      present: true,
      oldMarkerOnce: true,
      newMarkerOnce: true,
      oldHeaderMatches: true,
      newHeaderMatches: true,
    },
    decision: "pending",
    requestedAtPresent: true,
    privateFieldsAbsent: true,
  });
}

function expectEditAuthorizationResult(projection, branch, { proposal = false } = {}) {
  const resultRejected = Object.prototype.hasOwnProperty.call(branch, "resultRejected")
    ? branch.resultRejected
    : branch.rejected;
  const conflict = !proposal && branch.conflict === true;
  const errorPresent = !proposal && Object.prototype.hasOwnProperty.call(branch, "errorPresent")
    ? branch.errorPresent
    : (!proposal && branch.rejected);
  expect(projection).toEqual({
    ok: proposal ? true : branch.resultOk,
    action: proposal ? "propose_edit" : branch.resultAction,
    proposalIdPresent: true,
    pathMatches: true,
    diff: proposal || branch.resultDiffPresent ? {
      present: true,
      oldMarkerOnce: true,
      newMarkerOnce: true,
      oldHeaderMatches: true,
      newHeaderMatches: true,
    } : {
      present: false,
      oldMarkerOnce: false,
      newMarkerOnce: false,
      oldHeaderMatches: false,
      newHeaderMatches: false,
    },
    applied: proposal ? false : branch.applied,
    rejected: proposal ? false : resultRejected,
    replayed: false,
    backupPresent: proposal ? false : branch.backupPresent,
    conflict,
    errorPresent,
    privateFieldsAbsent: true,
    retryFieldsAbsent: true,
  });
}

function editAuthorizationReceiptExpectation(branch) {
  const resultRejected = Object.prototype.hasOwnProperty.call(branch, "resultRejected")
    ? branch.resultRejected
    : branch.rejected;
  const projection = {
    decision: branch.decision,
    receiptCount: 1,
    parseable: true,
    nameMatches: true,
    ok: branch.resultOk,
    actionMatches: true,
    pathMatches: true,
    applied: branch.applied,
    rejected: resultRejected,
    replayed: false,
    backupPresent: branch.backupPresent,
  };
  if (branch.conflict === true) {
    projection.conflict = true;
    projection.errorPresent = true;
  }
  return projection;
}

function expectEditAuthorizationZeroRequests(projection) {
  expect(projection).toEqual({
    agentRunPost: 0,
    runtimePost: 0,
    agentDelete: 0,
    authorizationPost: 0,
    resumePost: 0,
    inputPost: 0,
    browserProxyChatPost: 0,
    browserToolPost: 0,
    upstreamChatDelta: 0,
    registeredDelegationDelta: 0,
    registeredExecutionDelta: 0,
    proposalDelegationDelta: 0,
    applyDelegationDelta: 0,
    writeDelta: 0,
    backupDelta: 0,
    unsafeDelta: 0,
    targets: {
      authorization: { count: 0, allTargetRun: true },
      resume: { count: 0, allTargetRun: true },
    },
  });
}

function expectEditAuthorizationMetrics(projection, branch, phase) {
  const terminal = phase === "terminal";
  expect(projection.counters).toEqual({
    registeredDelegations: 1,
    proposalDelegations: 1,
    applyDelegations: terminal ? branch.applyDelegations : 0,
    writes: terminal ? branch.writes : 0,
    backups: terminal ? branch.backups : 0,
    unsafe: 0,
  });
  expect(projection.registeredExecutions).toEqual([{
    action: "propose_edit",
    pathMatches: true,
    payloadKeysMatch: true,
    payloadBytesMatch: true,
  }]);
  expect(projection.proposalTimeline).toHaveLength(1);
  expect(projection.proposalTimeline[0]).toEqual({
    action: "propose_edit",
    pathMatches: true,
    payloadKeysMatch: true,
    payloadBytesMatch: true,
    fileBefore: {
      state: "initial",
      exists: true,
      initialHashMatches: true,
      targetHashMatches: false,
    },
    fileAfter: {
      state: "initial",
      exists: true,
      initialHashMatches: true,
      targetHashMatches: false,
    },
    backupCountBefore: 0,
    backupCountAfter: 0,
    result: {
      shapeMatches: true,
      ok: true,
      actionMatches: true,
      pathMatches: true,
      proposalIdPresent: true,
      baseHashMatches: true,
      newHashMatches: true,
      newContentHashMatches: true,
      applied: false,
    },
  });
  const appliedTerminal = terminal && branch.applied;
  const conflictTerminal = terminal && branch.conflict === true;
  const applyAttempted = appliedTerminal || conflictTerminal;
  expect(projection.applyTimeline).toHaveLength(applyAttempted ? 1 : 0);
  expect(projection.writeTimeline).toHaveLength(applyAttempted ? 1 : 0);
  expect(projection.backupTimeline).toHaveLength(applyAttempted ? 1 : 0);
  if (conflictTerminal) {
    const thirdPartyState = {
      state: "third-party",
      exists: true,
      initialHashMatches: false,
      targetHashMatches: false,
    };
    expect(projection.applyTimeline[0]).toEqual({
      proposalShapeMatches: true,
      fileBefore: thirdPartyState,
      fileAfter: thirdPartyState,
      result: {
        ok: false,
        actionMatches: false,
        pathMatches: false,
        proposalIdMatches: false,
        applied: false,
        replayed: false,
        backupPresent: false,
      },
    });
    expect(projection.writeTimeline[0]).toEqual({
      fileBefore: thirdPartyState,
      fileAfter: thirdPartyState,
      writeObserved: false,
      targetHashMatches: false,
    });
    expect(projection.backupTimeline[0]).toEqual({
      beforeCount: 0,
      afterCount: 0,
      delta: 0,
      initialContentMatchDelta: 0,
      backupObserved: false,
    });
    return;
  }
  if (!appliedTerminal) return;
  const initialState = {
    state: "initial",
    exists: true,
    initialHashMatches: true,
    targetHashMatches: false,
  };
  const targetState = {
    state: "target",
    exists: true,
    initialHashMatches: false,
    targetHashMatches: true,
  };
  expect(projection.applyTimeline[0]).toEqual({
    proposalShapeMatches: true,
    fileBefore: initialState,
    fileAfter: targetState,
    result: {
      ok: true,
      actionMatches: true,
      pathMatches: true,
      proposalIdMatches: true,
      applied: true,
      replayed: false,
      backupPresent: true,
    },
  });
  expect(projection.writeTimeline[0]).toEqual({
    fileBefore: initialState,
    fileAfter: targetState,
    writeObserved: true,
    targetHashMatches: true,
  });
  expect(projection.backupTimeline[0]).toEqual({
    beforeCount: 0,
    afterCount: 1,
    delta: 1,
    initialContentMatchDelta: 1,
    backupObserved: true,
  });
}

async function restoreEditAuthorizationTestConfig(h4) {
  const { page } = h4;
  await page.locator("#baseUrl").evaluate((element, fakeUrl) => {
    element.value = fakeUrl;
  }, h4.host.ready.fakeUrl);
  await expect(page.locator("#baseUrl")).toHaveValue(h4.host.ready.fakeUrl);
  const permission = page.locator("#permPillBtn");
  if (await permission.getAttribute("data-value") !== "accept") {
    await permission.click();
    const option = page.locator('#permPillDropdown .model-pill-option[data-value="accept"]');
    await expect(option).toHaveCount(1);
    await expect(option).toBeVisible();
    await option.click();
  }
  await expect(permission).toHaveAttribute("data-value", "accept");
  expect(await page.evaluate(() => localStorage.getItem("code-permission-profile")))
    .toBe("accept");
}

async function editAuthorizationDomProjection(h4, phase, branch) {
  const waiting = phase === "waiting";
  const expected = {
    permission: { pill: "accept", stored: "accept" },
    panel: waiting ? {
      visible: true,
      cards: 1,
      groups: 1,
      rows: 1,
      selected: 1,
      disabled: 0,
      pathMatches: true,
      approveButtons: 1,
      approveEnabled: 1,
      rejectButtons: 1,
      rejectEnabled: 1,
      viewButtons: 1,
      statPairs: 1,
    } : {
      visible: false,
      cards: 0,
      groups: 0,
      rows: 0,
      selected: 0,
      disabled: 0,
      pathMatches: false,
      approveButtons: 0,
      approveEnabled: 0,
      rejectButtons: 0,
      rejectEnabled: 0,
      viewButtons: 0,
      statPairs: 0,
    },
    messages: {
      initialUsers: 1,
      stages: 1,
      toolProcesses: 1,
      toolItems: 1,
      editSuggestions: 1,
      finals: waiting ? 0 : 1,
    },
    tool: {
      action: "propose_edit",
      stageState: waiting ? "running" : branch.outcome,
      itemState: waiting ? "running" : branch.outcome,
      argumentDetails: 1,
      resultDetails: 1,
    },
    edit: {
      pathMatches: true,
      review: waiting,
      applied: !waiting && branch.applied,
      rejected: !waiting && branch.rejected,
      additions: 1,
      removals: 1,
    },
    order: waiting
      ? ["initial-user", "stage", "tool-process", "edit-suggestion"]
      : ["initial-user", "stage", "tool-process", "edit-suggestion", "final"],
  };
  return waitForMessageProjection(h4, {
    label: `edit-authorization-${branch.decision}-${phase}`,
    expected,
    sourceFacts: {
      phase,
      userMarker: branch.userMarker,
      stageMarker: EDIT_AUTHORIZATION_CONTRACT.stageMarker,
      finalMarker: branch.finalMarker,
      path: EDIT_AUTHORIZATION_CONTRACT.path,
    },
    sample: (facts) => {
      const panel = document.querySelector("#authorizationPanel");
      const root = document.querySelector("#messages");
      const users = [...root.querySelectorAll("article.msg.user")]
        .filter((node) => node.textContent.includes(facts.userMarker));
      const stages = [...root.querySelectorAll("article.msg.assistant.agent-commentary")]
        .filter((node) => node.textContent.includes(facts.stageMarker));
      const processStages = [...root.querySelectorAll(
        'article.tool-process > details.tool-process-stage[data-current-action="propose_edit"]',
      )];
      const processes = processStages.map((stage) => stage.closest("article.tool-process"));
      const process = processes[0] || null;
      const processStage = processStages[0] || null;
      const item = process?.querySelector("details.tool-process-item") || null;
      const details = item ? [...item.querySelectorAll(".tool-process-detail pre")] : [];
      const suggestions = [...root.querySelectorAll("article.msg.assistant.edit-suggestion")]
        .filter((node) => node.querySelector(".tool-edit-target")?.dataset.path === facts.path);
      const suggestion = suggestions[0] || null;
      const status = suggestion?.querySelector(".tool-edit-status") || null;
      const finals = [...root.querySelectorAll("article.msg.assistant")]
        .filter((node) => node.textContent.includes(facts.finalMarker));
      const row = panel?.querySelector(".authorization-row") || null;
      const approve = panel?.querySelector('[data-auth-action="approve"]') || null;
      const reject = panel?.querySelector('[data-auth-action="reject-all"]') || null;
      const ordered = [
        { label: "initial-user", node: users[0] || null },
        { label: "stage", node: stages[0] || null },
        { label: "tool-process", node: process },
        { label: "edit-suggestion", node: suggestion },
        ...(facts.phase === "terminal" ? [{ label: "final", node: finals[0] || null }] : []),
      ].filter((entry) => entry.node);
      ordered.sort((left, right) => (
        left.node.compareDocumentPosition(right.node) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1
      ));
      const classState = (node, values) => values.find((value) => node?.classList.contains(value)) || "";
      return {
        permission: {
          pill: String(document.querySelector("#permPillBtn")?.dataset.value || ""),
          stored: String(localStorage.getItem("code-permission-profile") || ""),
        },
        panel: {
          visible: Boolean(panel && !panel.classList.contains("hidden")),
          cards: panel?.querySelectorAll(".authorization-card").length || 0,
          groups: panel?.querySelectorAll(".authorization-group").length || 0,
          rows: panel?.querySelectorAll(".authorization-row").length || 0,
          selected: panel?.querySelectorAll("[data-auth-select]:checked").length || 0,
          disabled: panel?.querySelectorAll("[data-auth-select]:disabled").length || 0,
          pathMatches: row?.querySelector(".authorization-target")?.textContent.trim() === facts.path,
          approveButtons: panel?.querySelectorAll('[data-auth-action="approve"]').length || 0,
          approveEnabled: approve && !approve.disabled ? 1 : 0,
          rejectButtons: panel?.querySelectorAll('[data-auth-action="reject-all"]').length || 0,
          rejectEnabled: reject && !reject.disabled ? 1 : 0,
          viewButtons: panel?.querySelectorAll("[data-auth-view]").length || 0,
          statPairs: panel?.querySelectorAll(".authorization-stats").length || 0,
        },
        messages: {
          initialUsers: users.length,
          stages: stages.length,
          toolProcesses: processes.length,
          toolItems: process?.querySelectorAll("details.tool-process-item").length || 0,
          editSuggestions: suggestions.length,
          finals: finals.length,
        },
        tool: {
          action: String(processStage?.dataset.currentAction || ""),
          stageState: classState(processStage, ["running", "succeeded", "failed"]),
          itemState: classState(item, ["running", "succeeded", "failed"]),
          argumentDetails: details.length > 0 ? 1 : 0,
          resultDetails: details.length > 1 ? 1 : 0,
        },
        edit: {
          pathMatches: suggestion?.querySelector(".tool-edit-target")?.dataset.path === facts.path,
          review: Boolean(status?.classList.contains("is-review")),
          applied: Boolean(status?.classList.contains("is-applied")),
          rejected: Boolean(status?.classList.contains("is-rejected")),
          additions: suggestion?.querySelectorAll(".diff-line.diff-add").length || 0,
          removals: suggestion?.querySelectorAll(".diff-line.diff-remove").length || 0,
        },
        order: ordered.map((entry) => entry.label),
      };
    },
  });
}

async function beginEditAuthorizationLifecycle(h4, runtime, branchName, branchOverride = null) {
  const branch = branchOverride || EDIT_AUTHORIZATION_CONTRACT.branches[branchName];
  expect(branch).toBeTruthy();
  expect(h4.host.ready.proposeEditFixture).toEqual({
    path: EDIT_AUTHORIZATION_CONTRACT.path,
    initialSha256: EDIT_AUTHORIZATION_CONTRACT.initialSha256,
    targetSha256: EDIT_AUTHORIZATION_CONTRACT.targetSha256,
  });
  const { page } = h4;
  await h4.open(runtime);
  await assertFrontendRuntime(page, runtime);
  if (runtime === "classic") {
    expect(await page.locator("html").getAttribute("data-code-frontend-ready")).toBeNull();
  }
  await restoreEditAuthorizationTestConfig(h4);
  await h4.proveNonLoopbackBlocked();

  const lifecycleBoundary = h4.requestBoundary();
  const lifecycleMetricsBefore = await h4.metrics();
  await page.locator("#prompt").fill(branch.userMarker);
  await page.locator("#sendBtn").click();
  await expect(page.locator("#messages article.msg.user").filter({ hasText: branch.userMarker }))
    .toHaveCount(1);

  await expect.poll(() => h4.controlIds().agentRunIds.length).toBe(1);
  const agentRunId = h4.controlIds().agentRunIds[0];
  let waitingAgentResponse = null;
  await expect.poll(async () => {
    waitingAgentResponse = await fetchProductionJson(
      page,
      `/api/agent/runs/${encodeURIComponent(agentRunId)}?cursor=0&wait=0`,
    );
    return {
      status: waitingAgentResponse.body?.status,
      permissionProfile: waitingAgentResponse.body?.permissionProfile,
      eventTypes: (waitingAgentResponse.body?.events || []).map((event) => event.type),
      toolCallMatches: waitingAgentResponse.body?.pendingAuthorization?.toolCallId
        === EDIT_AUTHORIZATION_CONTRACT.toolCallId,
      action: waitingAgentResponse.body?.pendingAuthorization?.action,
      executionStatuses: (waitingAgentResponse.body?.toolExecutions || [])
        .map((execution) => execution.status),
    };
  }).toEqual({
    status: "waiting_authorization",
    permissionProfile: "accept",
    eventTypes: [
      "created",
      "model_started",
      "model_completed",
      "tool_started",
      "authorization_required",
    ],
    toolCallMatches: true,
    action: "apply_edit",
    executionStatuses: ["waiting_authorization"],
  });
  expect(waitingAgentResponse.status).toBe(200);
  const waitingAgent = waitingAgentResponse.body;
  const authorizationId = String(waitingAgent.pendingAuthorization?.authorizationId || "");
  expect(authorizationId).toMatch(/^[0-9a-f]{64}$/);
  expect(waitingAgent.agentRunId).toBe(agentRunId);
  expect(waitingAgent.pendingToolCalls).toHaveLength(1);
  expect(waitingAgent.activeRuntimeRunId).toBe("");
  expect(waitingAgent.allowedTools).toContain("propose_edit");
  expectEditAuthorizationPending(
    editAuthorizationPendingProjection(waitingAgent.pendingAuthorization, authorizationId),
  );

  const waitingEvents = editAuthorizationEventProjectionForBranch(
    waitingAgent,
    authorizationId,
    branch,
  );
  expect(waitingEvents.map((event) => event.seq)).toEqual([1, 2, 3, 4, 5]);
  expect(waitingAgent.nextCursor).toBe(5);
  expect(waitingEvents[1]).toMatchObject({
    type: "model_started",
    round: 1,
    runtimeRunId: "runtime-1",
  });
  expect(waitingEvents[2]).toMatchObject({
    type: "model_completed",
    content: "stage",
    finishReason: "tool_calls",
    toolCalls: [{ toolCallMatches: true, name: "propose_edit" }],
  });
  expectEditAuthorizationArguments(waitingEvents[2].toolCalls[0].arguments);
  expect(waitingEvents[3]).toMatchObject({
    type: "tool_started",
    toolCallMatches: true,
    name: "propose_edit",
  });
  expectEditAuthorizationArguments(waitingEvents[3].arguments);
  expectEditAuthorizationPending(waitingEvents[4].authorization);

  const waitingExecution = editAuthorizationExecutionProjection(waitingAgent);
  expect(waitingExecution).toHaveLength(1);
  expect(waitingExecution[0]).toMatchObject({
    toolCallMatches: true,
    name: "propose_edit",
    status: "waiting_authorization",
    outcome: "succeeded",
    authorizationDecision: "",
    publicFailureCountAbsent: true,
    publicFailureSignatureAbsent: true,
  });
  expectEditAuthorizationArguments(waitingExecution[0].arguments);
  expectEditAuthorizationResult(waitingExecution[0].result, branch, { proposal: true });

  const firstRuntimeRunId = String(
    waitingAgent.events.find((event) => event?.type === "model_started")?.data?.runtimeRunId || "",
  );
  expect(firstRuntimeRunId).not.toBe("");
  const firstRuntimeResponse = await fetchProductionJson(
    page,
    `/api/runtime/runs/${encodeURIComponent(firstRuntimeRunId)}?cursor=0&wait=0`,
  );
  expect(firstRuntimeResponse.status).toBe(200);
  expect(firstRuntimeResponse.body).toMatchObject({
    runId: firstRuntimeRunId,
    status: "completed",
  });
  expect(firstRuntimeResponse.body.nextCursor).toBeGreaterThan(0);
  expect(firstRuntimeResponse.body.events).toHaveLength(firstRuntimeResponse.body.nextCursor);
  expect(firstRuntimeResponse.body.result).toMatchObject({
    content: EDIT_AUTHORIZATION_CONTRACT.stageMarker,
    finishReason: "tool_calls",
  });
  expect(firstRuntimeResponse.body.result?.toolCalls).toHaveLength(1);
  expect(firstRuntimeResponse.body.result.toolCalls[0]).toMatchObject({
    id: EDIT_AUTHORIZATION_CONTRACT.toolCallId,
    function: { name: "propose_edit" },
  });
  expectEditAuthorizationArguments(editAuthorizationArgumentsProjection(
    firstRuntimeResponse.body.result.toolCalls[0].function.arguments,
  ));

  const sessionButton = page.locator("#sessionList .session-row.active button.session-main");
  await expect(sessionButton).toHaveCount(1);
  const sessionId = await sessionButton.getAttribute("data-session-id");
  expect(sessionId).toBeTruthy();
  let waitingSessionResponse = null;
  await expect.poll(async () => {
    waitingSessionResponse = await fetchProductionJson(
      page,
      `/api/sessions/${encodeURIComponent(sessionId)}`,
    );
    return {
      status: waitingSessionResponse.status,
      roles: (waitingSessionResponse.body?.messages || []).map((message) => message.role),
      runStatus: waitingSessionResponse.body?.runState?.status,
      permissionProfile: waitingSessionResponse.body?.runState?.permissionProfile,
      cursor: waitingSessionResponse.body?.runState?.agentEventCursor,
      authorizationMatches: waitingSessionResponse.body?.runState?.authorizationRequest
        ?.authorizationId === authorizationId,
    };
  }).toEqual({
    status: 200,
    roles: ["user", "assistant", "tool-call", "tool-result"],
    runStatus: "waiting-authorization",
    permissionProfile: "accept",
    cursor: waitingAgent.nextCursor,
    authorizationMatches: true,
  });
  const waitingSession = waitingSessionResponse.body;
  const waitingSnapshot = editAuthorizationWaitingSnapshotProjection(
    waitingAgent,
    waitingSession,
    agentRunId,
    authorizationId,
  );
  expect(waitingSnapshot.agent).toMatchObject({
    status: "waiting_authorization",
    permissionProfile: "accept",
    nextCursor: 5,
    round: 1,
    activeRuntimeCleared: true,
    pendingToolCallCount: 1,
  });
  expectEditAuthorizationPending(waitingSnapshot.agent.pendingAuthorization);
  expect(waitingSnapshot.session.roles).toEqual(["user", "assistant", "tool-call", "tool-result"]);
  expect(waitingSnapshot.session.runState).toEqual({
    status: "waiting-authorization",
    phase: "tools",
    executionOwner: "server-agent",
    permissionProfile: "accept",
    agentRunMatches: true,
    runtimeRunCleared: true,
    cursor: 5,
    modelRound: 1,
    request: {
      idMatches: true,
      sessionIdMatches: true,
      sourceKey: "main",
      sourceLabelPresent: true,
      editIdMatches: true,
      status: "pending",
      selected: true,
      serverAgent: true,
      detachedBackground: false,
      backgroundJobCleared: true,
      agentRunMatches: true,
      authorizationIdMatches: true,
      proposalIdPresent: true,
      toolCallMatches: true,
      tool: {
        action: "apply_edit",
        pathMatches: true,
        commandEmpty: true,
        descriptionEmpty: true,
      },
      stats: { additions: 1, removals: 1 },
    },
  });
  expect(waitingSnapshot.session.meta).toHaveLength(2);
  expect(waitingSnapshot.session.meta[0]).toMatchObject({
    role: "tool-call",
    toolCallMatches: true,
    agentRunMatches: true,
    eventType: "tool_started",
    eventSeq: 4,
    action: "propose_edit",
    native: true,
    serverManaged: false,
    replayed: false,
    outcome: "",
    authorization: null,
  });
  expectEditAuthorizationArguments(waitingSnapshot.session.meta[0].arguments);
  expect(waitingSnapshot.session.meta[1]).toEqual({
    role: "tool-result",
    toolCallMatches: true,
    agentRunMatches: true,
    eventType: "",
    eventSeq: 0,
    action: "propose_edit",
    native: true,
    serverManaged: true,
    replayed: false,
    outcome: "",
    arguments: null,
    authorization: {
      authorizationIdMatches: true,
      authorizationAction: "apply_edit",
      pendingEditPresent: true,
      pathMatches: true,
      decision: "",
      applied: false,
      rejected: false,
      result: null,
      authorizationResult: null,
    },
  });
  expect(waitingSnapshot.session.diff).toEqual({
    resultCount: 1,
    content: {
      present: true,
      oldMarkerOnce: true,
      newMarkerOnce: true,
      oldHeaderMatches: true,
      newHeaderMatches: true,
    },
    pendingEditIdMatches: true,
    pathMatches: true,
    authorizationIdMatches: true,
    toolCallMatches: true,
  });
  expect(waitingSnapshot.session.diff.content)
    .toEqual(waitingSnapshot.agent.pendingAuthorization.diff);
  const waitingRoleContent = editAuthorizationSessionRoleProjection(
    waitingSession.messages,
    branch,
  );
  expect(waitingRoleContent).toEqual([
    { role: "user", kind: "initial-user" },
    { role: "assistant", kind: "tool-owner" },
    { role: "tool-call", kind: "edit-call" },
    { role: "tool-result", kind: "edit-result" },
  ]);
  const waitingDom = await editAuthorizationDomProjection(h4, "waiting", branch);
  expect(waitingDom.edit).toEqual({
    pathMatches: true,
    review: true,
    applied: false,
    rejected: false,
    additions: 1,
    removals: 1,
  });
  await expect(page.locator("#activeRunBanner.visible")).toHaveCount(1);
  await expect(page.locator("#stopBtn")).toBeEnabled();

  const metricsAtWaiting = await h4.metrics();
  expect(metricsAtWaiting.chatRequests).toEqual([{
    scenario: `${branch.scenarioPrefix}-call`,
    stream: true,
    hasToolResult: false,
  }]);
  expect(metricsAtWaiting.production.agentRuns).toHaveLength(1);
  expect(metricsAtWaiting.production.runtimeRuns).toHaveLength(1);
  const waitingMetrics = editAuthorizationMetricsProjection(metricsAtWaiting);
  expectEditAuthorizationMetrics(waitingMetrics, branch, "waiting");

  return {
    page,
    runtime,
    branchName,
    branch,
    lifecycleBoundary,
    lifecycleMetricsBefore,
    agentRunId,
    authorizationId,
    sessionId,
    waitingAgent,
    waitingAgentResponse,
    waitingEvents,
    waitingExecution,
    firstRuntimeRunId,
    firstRuntimeResponse,
    waitingSession,
    waitingSessionResponse,
    waitingSnapshot,
    waitingRoleContent,
    waitingDom,
    metricsAtWaiting,
    waitingMetrics,
  };
}

async function reloadWaitingEditAuthorizationLifecycle(h4, started) {
  const {
    page,
    runtime,
    branch,
    agentRunId,
    authorizationId,
    sessionId,
    waitingEvents,
    waitingExecution,
    waitingSnapshot,
    waitingDom,
    metricsAtWaiting,
  } = started;
  const waitingReloadBoundary = h4.requestBoundary();
  await h4.reloadRuntime(runtime);
  await restoreEditAuthorizationTestConfig(h4);
  const restoredWaitingDom = await editAuthorizationDomProjection(h4, "waiting", branch);
  expect(restoredWaitingDom).toEqual(waitingDom);
  const permissionRestored = await page.locator("#permPillBtn").getAttribute("data-value")
    === "accept";
  expect(permissionRestored).toBe(true);
  await expect(page.locator("#activeRunBanner.visible")).toHaveCount(0);
  await expect(page.locator("#stopBtn")).toBeDisabled();
  const waitingAgentAfterReload = await fetchProductionJson(
    page,
    `/api/agent/runs/${encodeURIComponent(agentRunId)}?cursor=0&wait=0`,
  );
  expect(waitingAgentAfterReload.status).toBe(200);
  expect(waitingAgentAfterReload.body.agentRunId).toBe(agentRunId);
  expect(waitingAgentAfterReload.body.pendingAuthorization?.authorizationId).toBe(authorizationId);
  expect(editAuthorizationEventProjectionForBranch(
    waitingAgentAfterReload.body,
    authorizationId,
    branch,
  ))
    .toEqual(waitingEvents);
  expect(editAuthorizationExecutionProjection(waitingAgentAfterReload.body))
    .toEqual(waitingExecution);
  const waitingSessionAfterReload = await fetchProductionJson(
    page,
    `/api/sessions/${encodeURIComponent(sessionId)}`,
  );
  expect(waitingSessionAfterReload.status).toBe(200);
  expect(editAuthorizationWaitingSnapshotProjection(
    waitingAgentAfterReload.body,
    waitingSessionAfterReload.body,
    agentRunId,
    authorizationId,
  )).toEqual(waitingSnapshot);
  expect(editAuthorizationSessionDiffProjection(
    waitingSessionAfterReload.body.messages,
    waitingAgentAfterReload.body.pendingAuthorization,
  )).toEqual(waitingSnapshot.session.diff);
  const metricsAfterWaitingReload = await h4.metrics();
  expect(metricsAfterWaitingReload.chatRequests).toEqual(metricsAtWaiting.chatRequests);
  expect(editAuthorizationMetricsProjection(metricsAfterWaitingReload))
    .toEqual(editAuthorizationMetricsProjection(metricsAtWaiting));
  const waitingReloadRequests = editAuthorizationRequestProjection(
    h4,
    waitingReloadBoundary,
    metricsAtWaiting,
    metricsAfterWaitingReload,
    agentRunId,
  );
  expectEditAuthorizationZeroRequests(waitingReloadRequests);
  expect(new Set(h4.controlIds().agentRunIds)).toEqual(new Set([agentRunId]));
  expect(new Set(h4.controlIds().runtimeRunIds)).toEqual(new Set([started.firstRuntimeRunId]));
  expect(h4.pageErrors).toEqual([]);
  return {
    waitingReloadBoundary,
    restoredWaitingDom,
    waitingAgentAfterReload,
    waitingSessionAfterReload,
    metricsAfterWaitingReload,
    waitingReloadRequests,
    permissionRestored,
  };
}

async function completeEditAuthorizationLifecycle(h4, started, waitingReload) {
  const {
    page,
    branch,
    agentRunId,
    authorizationId,
    sessionId,
    waitingAgent,
    waitingEvents,
  } = started;
  const decisionBoundary = h4.requestBoundary();
  const decisionMetricsBefore = waitingReload.decisionMetricsBefore
    || waitingReload.metricsAfterWaitingReload;
  const row = page.locator("#authorizationPanel .authorization-row");
  const decisionButton = page.locator(
    `#authorizationPanel [data-auth-action="${branch.action}"]`,
  );
  await expect(row).toHaveCount(1);
  await expect(row.locator("[data-auth-select]")).toBeChecked();
  await expect(decisionButton).toHaveCount(1);
  await expect(decisionButton).toBeEnabled();
  await decisionButton.click();

  const final = page.locator("#messages article.msg.assistant")
    .filter({ hasText: branch.finalMarker });
  await expect(final).toHaveCount(1);
  let completedAgentResponse = null;
  await expect.poll(async () => {
    completedAgentResponse = await fetchProductionJson(
      page,
      `/api/agent/runs/${encodeURIComponent(agentRunId)}?cursor=0&wait=0`,
    );
    return {
      status: completedAgentResponse.body?.status,
      eventTypes: (completedAgentResponse.body?.events || []).map((event) => event.type),
      pendingAuthorization: completedAgentResponse.body?.pendingAuthorization ?? null,
    };
  }).toEqual({
    status: "completed",
    eventTypes: [
      "created",
      "model_started",
      "model_completed",
      "tool_started",
      "authorization_required",
      "authorization_submitted",
      "tool_completed",
      "waiting_credentials",
      "resumed",
      "model_started",
      "model_completed",
      "completed",
    ],
    pendingAuthorization: null,
  });
  expect(completedAgentResponse.status).toBe(200);
  const completedAgent = completedAgentResponse.body;
  expect(completedAgent.agentRunId).toBe(agentRunId);
  expect(completedAgent.permissionProfile).toBe("accept");
  expect(completedAgent.activeRuntimeRunId).toBe("");
  expect(completedAgent.pendingToolCalls).toEqual([]);
  expect(completedAgent.result?.content).toBe(branch.finalMarker);

  const terminalEvents = editAuthorizationEventProjectionForBranch(
    completedAgent,
    authorizationId,
    branch,
  );
  expect(terminalEvents.map((event) => event.seq)).toEqual(
    terminalEvents.map((_, index) => index + 1),
  );
  expect(terminalEvents).toHaveLength(12);
  expect(completedAgent.nextCursor).toBe(12);
  expect(terminalEvents.slice(0, waitingEvents.length)).toEqual(waitingEvents);
  expect(terminalEvents[5]).toMatchObject({
    type: "authorization_submitted",
    toolCallMatches: true,
    authorizationIdMatches: true,
    decision: branch.decision,
  });
  expect(terminalEvents[6]).toMatchObject({
    type: "tool_completed",
    toolCallMatches: true,
    name: "propose_edit",
    outcome: branch.outcome,
    replayed: false,
  });
  expectEditAuthorizationResult(terminalEvents[6].result, branch);
  expect(terminalEvents[7]).toMatchObject({
    type: "waiting_credentials",
    resumeStatus: "model",
    reason: "authorization_submitted",
  });
  expect(terminalEvents[8]).toMatchObject({ type: "resumed", status: "model" });
  expect(terminalEvents[9]).toMatchObject({
    type: "model_started",
    round: 2,
    runtimeRunId: "runtime-2",
  });
  expect(terminalEvents[10]).toMatchObject({
    type: "model_completed",
    content: "final",
    finishReason: "stop",
    toolCalls: [],
  });
  expect(terminalEvents[11]).toMatchObject({ type: "completed" });

  const terminalExecution = editAuthorizationExecutionProjection(completedAgent);
  expect(terminalExecution).toHaveLength(1);
  expect(terminalExecution[0]).toMatchObject({
    toolCallMatches: true,
    name: "propose_edit",
    status: "completed",
    outcome: branch.outcome,
    authorizationDecision: branch.decision,
    publicFailureCountAbsent: true,
    publicFailureSignatureAbsent: true,
  });
  expectEditAuthorizationArguments(terminalExecution[0].arguments);
  expectEditAuthorizationResult(terminalExecution[0].result, branch);

  const runtimeRunIds = completedAgent.events
    .filter((event) => event?.type === "model_started")
    .map((event) => String(event?.data?.runtimeRunId || ""));
  expect(runtimeRunIds).toHaveLength(2);
  expect(new Set(runtimeRunIds).size).toBe(2);
  const runtimeSnapshots = [];
  for (const runtimeRunId of runtimeRunIds) {
    const response = await fetchProductionJson(
      page,
      `/api/runtime/runs/${encodeURIComponent(runtimeRunId)}?cursor=0&wait=0`,
    );
    expect(response.status).toBe(200);
    expect(response.body.status).toBe("completed");
    expect(response.body.nextCursor).toBeGreaterThan(0);
    expect(response.body.events).toHaveLength(response.body.nextCursor);
    runtimeSnapshots.push(response.body);
  }
  const runtimeProjection = runtimeSnapshots.map((snapshot, index) => ({
    runtime: `runtime-${index + 1}`,
    status: String(snapshot.status || ""),
    nextCursor: Number(snapshot.nextCursor || 0),
    eventTypes: (snapshot.events || []).map((event) => String(event?.type || "")),
    content: snapshot.result?.content === EDIT_AUTHORIZATION_CONTRACT.stageMarker
      ? "stage"
      : snapshot.result?.content === branch.finalMarker
        ? "final"
        : "empty",
    finishReason: String(snapshot.result?.finishReason || ""),
    toolCalls: (snapshot.result?.toolCalls || []).map((call) => ({
      toolCallMatches: String(call?.id || "") === EDIT_AUTHORIZATION_CONTRACT.toolCallId,
      name: String(call?.function?.name || ""),
      arguments: editAuthorizationArgumentsProjection(call?.function?.arguments),
    })),
  }));
  expect(runtimeProjection[0]).toMatchObject({
    runtime: "runtime-1",
    status: "completed",
    content: "stage",
    finishReason: "tool_calls",
    toolCalls: [{ toolCallMatches: true, name: "propose_edit" }],
  });
  expectEditAuthorizationArguments(runtimeProjection[0].toolCalls[0].arguments);
  expect(runtimeProjection[1]).toMatchObject({
    runtime: "runtime-2",
    status: "completed",
    content: "final",
    finishReason: "stop",
    toolCalls: [],
  });

  let terminalSessionResponse = null;
  await expect.poll(async () => {
    terminalSessionResponse = await fetchProductionJson(
      page,
      `/api/sessions/${encodeURIComponent(sessionId)}`,
    );
    return {
      status: terminalSessionResponse.status,
      roles: (terminalSessionResponse.body?.messages || []).map((message) => message.role),
      runStateKeys: Object.keys(terminalSessionResponse.body?.runState || {}).sort(),
    };
  }).toEqual({
    status: 200,
    roles: ["user", "assistant", "tool-call", "tool-result", "assistant"],
    runStateKeys: [],
  });
  const terminalSession = terminalSessionResponse.body;
  const terminalToolOwner = terminalSession.messages[1];
  expect(terminalToolOwner.meta?.toolCalls).toHaveLength(1);
  expect(terminalToolOwner.meta.toolCalls[0]).toMatchObject({
    id: EDIT_AUTHORIZATION_CONTRACT.toolCallId,
    function: { name: "propose_edit" },
  });
  expectEditAuthorizationArguments(editAuthorizationArgumentsProjection(
    terminalToolOwner.meta.toolCalls[0].function.arguments,
  ));
  const terminalFinal = terminalSession.messages[4];
  expect(terminalFinal).toMatchObject({ role: "assistant", content: branch.finalMarker });
  expect(terminalFinal.meta?.toolCalls).toEqual([]);

  const sessionRoleContent = editAuthorizationSessionRoleProjection(
    terminalSession.messages,
    branch,
  );
  expect(sessionRoleContent).toEqual([
    { role: "user", kind: "initial-user" },
    { role: "assistant", kind: "tool-owner" },
    { role: "tool-call", kind: "edit-call" },
    { role: "tool-result", kind: "edit-result" },
    { role: "assistant", kind: "final" },
  ]);
  const sessionAuthorizationMeta = editAuthorizationSessionMetaProjection(
    terminalSession.messages,
    agentRunId,
    authorizationId,
  );
  expect(sessionAuthorizationMeta).toHaveLength(2);
  expect(sessionAuthorizationMeta[0]).toMatchObject({
    role: "tool-call",
    toolCallMatches: true,
    agentRunMatches: true,
    eventType: "tool_started",
    eventSeq: 4,
    action: "propose_edit",
    native: true,
    serverManaged: false,
    replayed: false,
    outcome: "",
    authorization: null,
  });
  expectEditAuthorizationArguments(sessionAuthorizationMeta[0].arguments);
  expect(sessionAuthorizationMeta[1]).toMatchObject({
    role: "tool-result",
    toolCallMatches: true,
    agentRunMatches: true,
    eventType: "tool_completed",
    eventSeq: 7,
    action: "propose_edit",
    native: true,
    serverManaged: true,
    replayed: false,
    outcome: branch.outcome,
    arguments: null,
    authorization: {
      authorizationIdMatches: true,
      authorizationAction: "apply_edit",
      pendingEditPresent: true,
      pathMatches: true,
      decision: branch.decision,
      applied: branch.applied,
      rejected: branch.rejected,
    },
  });
  expectEditAuthorizationResult(sessionAuthorizationMeta[1].authorization.result, branch);
  expectEditAuthorizationResult(
    sessionAuthorizationMeta[1].authorization.authorizationResult,
    branch,
  );

  const terminalDom = await editAuthorizationDomProjection(h4, "terminal", branch);
  await expect(page.locator("#activeRunBanner.visible")).toHaveCount(0);
  await expect(page.locator("#stopBtn")).toBeDisabled();
  await expect(page.locator("#messages .execution-trace.active")).toHaveCount(0);
  await expect(page.locator("#messages .execution-trace.completed")).toHaveCount(1);

  const metricsAtTerminal = await h4.metrics();
  expect(metricsAtTerminal.chatRequests).toEqual([
    { scenario: `${branch.scenarioPrefix}-call`, stream: true, hasToolResult: false },
    {
      scenario: `${branch.scenarioPrefix}-final`,
      stream: true,
      hasToolResult: true,
      editAuthorizationReceipt: editAuthorizationReceiptExpectation(branch),
    },
  ]);
  expect(metricsAtTerminal.production.agentRuns).toHaveLength(1);
  expect(metricsAtTerminal.production.runtimeRuns).toHaveLength(2);
  const terminalMetrics = editAuthorizationMetricsProjection(metricsAtTerminal);
  expectEditAuthorizationMetrics(terminalMetrics, branch, "terminal");

  const decisionRequests = editAuthorizationRequestProjection(
    h4,
    decisionBoundary,
    decisionMetricsBefore,
    metricsAtTerminal,
    agentRunId,
  );
  expect(decisionRequests).toEqual({
    agentRunPost: 0,
    runtimePost: 0,
    agentDelete: 0,
    authorizationPost: 1,
    resumePost: 1,
    inputPost: 0,
    browserProxyChatPost: 0,
    browserToolPost: 0,
    upstreamChatDelta: 1,
    registeredDelegationDelta: 0,
    registeredExecutionDelta: 0,
    proposalDelegationDelta: 0,
    applyDelegationDelta: branch.applyDelegations,
    writeDelta: branch.writes,
    backupDelta: branch.backups,
    unsafeDelta: 0,
    targets: {
      authorization: { count: 1, allTargetRun: true },
      resume: { count: 1, allTargetRun: true },
    },
  });
  const totalRequests = editAuthorizationRequestProjection(
    h4,
    started.lifecycleBoundary,
    started.lifecycleMetricsBefore,
    metricsAtTerminal,
    agentRunId,
  );
  expect(totalRequests).toEqual({
    agentRunPost: 1,
    runtimePost: 0,
    agentDelete: 0,
    authorizationPost: 1,
    resumePost: 1,
    inputPost: 0,
    browserProxyChatPost: 0,
    browserToolPost: 0,
    upstreamChatDelta: 2,
    registeredDelegationDelta: 1,
    registeredExecutionDelta: 1,
    proposalDelegationDelta: 1,
    applyDelegationDelta: branch.applyDelegations,
    writeDelta: branch.writes,
    backupDelta: branch.backups,
    unsafeDelta: 0,
    targets: {
      authorization: { count: 1, allTargetRun: true },
      resume: { count: 1, allTargetRun: true },
    },
  });
  expect(new Set(h4.controlIds().agentRunIds)).toEqual(new Set([agentRunId]));
  expect(new Set(h4.controlIds().runtimeRunIds)).toEqual(new Set(runtimeRunIds));
  expect(completedAgent.toolExecutions).toHaveLength(1);
  expect(waitingAgent.toolExecutions).toHaveLength(1);
  expect(h4.pageErrors).toEqual([]);
  return {
    decisionBoundary,
    final,
    completedAgentResponse,
    completedAgent,
    terminalEvents,
    terminalExecution,
    runtimeRunIds,
    runtimeSnapshots,
    runtimeProjection,
    terminalSessionResponse,
    terminalSession,
    sessionRoleContent,
    sessionAuthorizationMeta,
    terminalDom,
    metricsAtTerminal,
    terminalMetrics,
    decisionRequests,
    totalRequests,
  };
}

async function reloadCompletedEditAuthorizationLifecycle(h4, started, completed) {
  const {
    page,
    runtime,
    branch,
    agentRunId,
    authorizationId,
    sessionId,
  } = started;
  const terminalReloadBoundary = h4.requestBoundary();
  await h4.reloadRuntime(runtime);
  await restoreEditAuthorizationTestConfig(h4);
  const restoredTerminalDom = await editAuthorizationDomProjection(h4, "terminal", branch);
  expect(restoredTerminalDom).toEqual(completed.terminalDom);
  const permissionRestored = await page.locator("#permPillBtn").getAttribute("data-value")
    === "accept";
  expect(permissionRestored).toBe(true);
  const agentAfterReload = await fetchProductionJson(
    page,
    `/api/agent/runs/${encodeURIComponent(agentRunId)}?cursor=0&wait=0`,
  );
  expect(agentAfterReload.status).toBe(200);
  expect(agentAfterReload.body.agentRunId).toBe(agentRunId);
  expect(editAuthorizationEventProjectionForBranch(
    agentAfterReload.body,
    authorizationId,
    branch,
  ))
    .toEqual(completed.terminalEvents);
  expect(editAuthorizationExecutionProjection(agentAfterReload.body))
    .toEqual(completed.terminalExecution);
  const sessionAfterReload = await fetchProductionJson(
    page,
    `/api/sessions/${encodeURIComponent(sessionId)}`,
  );
  expect(sessionAfterReload.status).toBe(200);
  expect(Object.keys(sessionAfterReload.body.runState || {})).toEqual([]);
  expect(editAuthorizationSessionRoleProjection(sessionAfterReload.body.messages, branch))
    .toEqual(completed.sessionRoleContent);
  expect(editAuthorizationSessionMetaProjection(
    sessionAfterReload.body.messages,
    agentRunId,
    authorizationId,
  )).toEqual(completed.sessionAuthorizationMeta);
  const runtimeSnapshotsAfterReload = [];
  for (const runtimeRunId of completed.runtimeRunIds) {
    const response = await fetchProductionJson(
      page,
      `/api/runtime/runs/${encodeURIComponent(runtimeRunId)}?cursor=0&wait=0`,
    );
    expect(response.status).toBe(200);
    expect(response.body.runId).toBe(runtimeRunId);
    runtimeSnapshotsAfterReload.push(response.body);
  }
  const runtimeProjectionAfterReload = runtimeSnapshotsAfterReload.map((snapshot) => ({
    status: String(snapshot?.status || ""),
    nextCursor: Number(snapshot?.nextCursor || 0),
    eventTypes: (snapshot?.events || []).map((event) => String(event?.type || "")),
    content: snapshot?.result?.content === EDIT_AUTHORIZATION_CONTRACT.stageMarker
      ? "stage"
      : snapshot?.result?.content === branch.finalMarker
        ? "final"
        : "empty",
    finishReason: String(snapshot?.result?.finishReason || ""),
    toolCallCount: (snapshot?.result?.toolCalls || []).length,
  }));
  expect(runtimeProjectionAfterReload).toEqual(completed.runtimeProjection.map((snapshot) => ({
    status: snapshot.status,
    nextCursor: snapshot.nextCursor,
    eventTypes: snapshot.eventTypes,
    content: snapshot.content,
    finishReason: snapshot.finishReason,
    toolCallCount: snapshot.toolCalls.length,
  })));
  const metricsAfterTerminalReload = await h4.metrics();
  expect(metricsAfterTerminalReload.chatRequests).toEqual(completed.metricsAtTerminal.chatRequests);
  expect(editAuthorizationMetricsProjection(metricsAfterTerminalReload))
    .toEqual(completed.terminalMetrics);
  const terminalReloadRequests = editAuthorizationRequestProjection(
    h4,
    terminalReloadBoundary,
    completed.metricsAtTerminal,
    metricsAfterTerminalReload,
    agentRunId,
  );
  expectEditAuthorizationZeroRequests(terminalReloadRequests);
  expect(new Set(h4.controlIds().agentRunIds)).toEqual(new Set([agentRunId]));
  expect(new Set(h4.controlIds().runtimeRunIds)).toEqual(new Set(completed.runtimeRunIds));
  expect(h4.pageErrors).toEqual([]);
  return {
    terminalReloadBoundary,
    restoredTerminalDom,
    agentAfterReload,
    sessionAfterReload,
    runtimeSnapshotsAfterReload,
    runtimeProjectionAfterReload,
    metricsAfterTerminalReload,
    terminalReloadRequests,
    permissionRestored,
  };
}

async function exerciseEditAuthorizationLifecycle(h4, runtime, branchName) {
  const started = await beginEditAuthorizationLifecycle(h4, runtime, branchName);
  const waitingReload = await reloadWaitingEditAuthorizationLifecycle(h4, started);
  const completed = await completeEditAuthorizationLifecycle(h4, started, waitingReload);
  const terminalReload = await reloadCompletedEditAuthorizationLifecycle(
    h4,
    started,
    completed,
  );
  const { branch, agentRunId, authorizationId } = started;
  const decisionSubmissionProjection = {
    requests: completed.decisionRequests,
    events: completed.terminalEvents.slice(started.waitingEvents.length, 9),
    execution: completed.terminalExecution,
    sameAgentRun: completed.completedAgent.agentRunId === started.waitingAgent.agentRunId,
    authorizationCleared: completed.completedAgent.pendingAuthorization == null,
    fileEffects: {
      proposalDelegations: completed.terminalMetrics.counters.proposalDelegations,
      applyDelegations: completed.terminalMetrics.counters.applyDelegations,
      writes: completed.terminalMetrics.counters.writes,
      backups: completed.terminalMetrics.counters.backups,
    },
  };
  const refreshLifecycle = {
    waiting: {
      sameAgentRun: waitingReload.waitingAgentAfterReload.body.agentRunId === agentRunId,
      sameAuthorization: waitingReload.waitingAgentAfterReload.body.pendingAuthorization
        ?.authorizationId === authorizationId,
      sameSnapshot: JSON.stringify(editAuthorizationWaitingSnapshotProjection(
        waitingReload.waitingAgentAfterReload.body,
        waitingReload.waitingSessionAfterReload.body,
        agentRunId,
        authorizationId,
      )) === JSON.stringify(started.waitingSnapshot),
      dom: waitingReload.restoredWaitingDom,
      requests: waitingReload.waitingReloadRequests,
      permissionRestored: waitingReload.permissionRestored,
    },
    terminal: {
      sameAgentRun: terminalReload.agentAfterReload.body.agentRunId === agentRunId,
      sameEvents: JSON.stringify(editAuthorizationEventProjection(
        terminalReload.agentAfterReload.body,
        authorizationId,
      )) === JSON.stringify(completed.terminalEvents),
      sameSession: JSON.stringify(editAuthorizationSessionRoleProjection(
        terminalReload.sessionAfterReload.body.messages,
        branch,
      )) === JSON.stringify(completed.sessionRoleContent),
      sameAuthorizationMeta: JSON.stringify(editAuthorizationSessionMetaProjection(
        terminalReload.sessionAfterReload.body.messages,
        agentRunId,
        authorizationId,
      )) === JSON.stringify(completed.sessionAuthorizationMeta),
      dom: terminalReload.restoredTerminalDom,
      requests: terminalReload.terminalReloadRequests,
      permissionRestored: terminalReload.permissionRestored,
    },
  };
  expect(refreshLifecycle.waiting.permissionRestored).toBe(true);
  expect(refreshLifecycle.terminal.permissionRestored).toBe(true);
  const hashes = {
    waitingEventProjection: canonicalHash(started.waitingEvents),
    waitingSnapshot: canonicalHash(started.waitingSnapshot),
    waitingDom: canonicalHash(started.waitingDom),
    decisionSubmissionProjection: canonicalHash(decisionSubmissionProjection),
    runtimeProjection: canonicalHash(completed.runtimeProjection),
    sessionRoleContent: canonicalHash(completed.sessionRoleContent),
    sessionAuthorizationMeta: canonicalHash(completed.sessionAuthorizationMeta),
    terminalDom: canonicalHash(completed.terminalDom),
    refreshLifecycle: canonicalHash(refreshLifecycle),
  };
  const frozenHashKeys = Object.keys(hashes).sort();
  for (const branchHashes of Object.values(H4_8C_SEMANTIC_HASHES)) {
    expect(Object.keys(branchHashes).sort()).toEqual(frozenHashKeys);
    const branchHashValues = Object.values(branchHashes);
    const allEmpty = branchHashValues.every((value) => value === "");
    const allFrozen = branchHashValues.every((value) => /^[0-9a-f]{64}$/.test(value));
    expect(allEmpty || allFrozen).toBe(true);
  }
  const frozenHashes = H4_8C_SEMANTIC_HASHES[branchName];
  const frozenHashValues = Object.values(frozenHashes);
  const frozenReady = frozenHashValues.every((value) => /^[0-9a-f]{64}$/.test(value));
  if (frozenReady) {
    expect(hashes).toEqual(frozenHashes);
  } else {
    expect(frozenHashValues.every((value) => value === "")).toBe(true);
    expect(runtime).toBe("bundle");
  }
  h4.evidence(`${runtime}-edit-authorization-${branch.decision}-reload`, {
    runtime,
    decision: branch.decision,
    fixture: h4.host.ready.proposeEditFixture,
    identities: {
      agentRunId: idHash(agentRunId),
      authorizationId: idHash(authorizationId),
    },
    counts: {
      agentRuns: completed.metricsAtTerminal.production.agentRuns.length,
      runtimes: completed.metricsAtTerminal.production.runtimeRuns.length,
      upstreamChat: completed.metricsAtTerminal.chatRequests.length,
      agentRunPost: completed.totalRequests.agentRunPost,
      authorizationPost: completed.totalRequests.authorizationPost,
      resumePost: completed.totalRequests.resumePost,
      registeredDelegations: completed.terminalMetrics.counters.registeredDelegations,
      registeredExecutions: completed.terminalMetrics.registeredExecutions.length,
      proposalDelegations: completed.terminalMetrics.counters.proposalDelegations,
      applyDelegations: completed.terminalMetrics.counters.applyDelegations,
      writes: completed.terminalMetrics.counters.writes,
      backups: completed.terminalMetrics.counters.backups,
      unsafe: completed.terminalMetrics.counters.unsafe,
    },
    agentCursors: {
      waiting: started.waitingAgent.nextCursor,
      terminal: completed.completedAgent.nextCursor,
    },
    eventTypes: completed.terminalEvents.map((event) => event.type),
    runtimeCursors: completed.runtimeProjection.map((snapshot) => snapshot.nextCursor),
    waiting: {
      snapshot: started.waitingSnapshot,
      dom: started.waitingDom,
    },
    terminal: {
      sessionRoleContent: completed.sessionRoleContent,
      sessionAuthorizationMeta: completed.sessionAuthorizationMeta,
      dom: completed.terminalDom,
    },
    fileEffects: {
      registeredExecutions: completed.terminalMetrics.registeredExecutions,
      proposalTimeline: completed.terminalMetrics.proposalTimeline,
      applyTimeline: completed.terminalMetrics.applyTimeline,
      writeTimeline: completed.terminalMetrics.writeTimeline,
      backupTimeline: completed.terminalMetrics.backupTimeline,
    },
    decisionRequests: completed.decisionRequests,
    waitingReload: waitingReload.waitingReloadRequests,
    terminalReload: terminalReload.terminalReloadRequests,
    hashes,
  });
}

function expectEditAuthorizationConflictMetrics(projection, phase, transitionProjection = null) {
  const transitioned = phase !== "waiting";
  const terminal = phase === "terminal";
  expect(projection.counters).toEqual({
    conflictObservations: terminal ? 1 : 0,
    transitionAttempts: transitioned ? 1 : 0,
    transitionWrites: transitioned ? 1 : 0,
    transitionRejections: 0,
  });
  expect(projection.transitionTimeline).toHaveLength(transitioned ? 1 : 0);
  if (transitioned) expect(projection.transitionTimeline[0]).toEqual(transitionProjection);
  expect(projection.conflictTimeline).toHaveLength(terminal ? 1 : 0);
  expect(projection.applyTimeline).toHaveLength(terminal ? 1 : 0);
  expect(projection.writeTimeline).toHaveLength(terminal ? 1 : 0);
  expect(projection.backupTimeline).toHaveLength(terminal ? 1 : 0);
  if (!terminal) return;
  const thirdPartyState = {
    state: "third-party",
    exists: true,
    initialHashMatches: false,
    targetHashMatches: false,
    thirdPartyHashMatches: true,
  };
  expect(projection.conflictTimeline[0]).toEqual({
    observed: true,
    exceptionTypeMatches: true,
    fileBefore: thirdPartyState,
    fileAfter: thirdPartyState,
    fixturePreserved: true,
    backupDelta: 0,
  });
  expect(projection.applyTimeline[0]).toEqual({
    proposalShapeMatches: true,
    conflictObserved: true,
    fileBefore: thirdPartyState,
    fileAfter: thirdPartyState,
    resultPresent: false,
  });
  expect(projection.writeTimeline[0]).toEqual({
    fileBefore: thirdPartyState,
    fileAfter: thirdPartyState,
    writeObserved: false,
    targetHashMatches: false,
  });
  expect(projection.backupTimeline[0]).toEqual({
    beforeCount: 0,
    afterCount: 0,
    delta: 0,
    initialContentMatchDelta: 0,
    backupObserved: false,
  });
}

async function editAuthorizationConflictDomProjection(h4, projection, label) {
  const { page } = h4;
  const visibleConflict = await waitForMessageProjection(h4, {
    label,
    expected: {
      action: "propose_edit",
      pathMatches: true,
      stageFailed: true,
      itemFailed: true,
      resultDetails: 1,
      errorPresent: true,
      editReview: false,
      editApplied: false,
      editRejected: true,
      finals: 1,
    },
    sourceFacts: {
      path: EDIT_AUTHORIZATION_CONTRACT.path,
      finalMarker: EDIT_AUTHORIZATION_CONFLICT_CONTRACT.finalMarker,
    },
    sample: (facts) => {
      const root = document.querySelector("#messages");
      const stage = root?.querySelector(
        'article.tool-process > details.tool-process-stage[data-current-action="propose_edit"]',
      ) || null;
      const item = stage?.querySelector("details.tool-process-item") || null;
      const details = item ? [...item.querySelectorAll(".tool-process-detail pre")] : [];
      const suggestion = [...(root?.querySelectorAll(
        "article.msg.assistant.edit-suggestion",
      ) || [])].find((node) => (
        node.querySelector(".tool-edit-target")?.dataset.path === facts.path
      )) || null;
      const status = suggestion?.querySelector(".tool-edit-status") || null;
      const finals = [...(root?.querySelectorAll("article.msg.assistant") || [])]
        .filter((node) => node.textContent.includes(facts.finalMarker));
      return {
        action: String(stage?.dataset.currentAction || ""),
        pathMatches: suggestion?.querySelector(".tool-edit-target")?.dataset.path === facts.path,
        stageFailed: Boolean(stage?.classList.contains("failed")),
        itemFailed: Boolean(item?.classList.contains("failed")),
        resultDetails: details.length > 1 ? 1 : 0,
        errorPresent: Boolean(String(details[1]?.textContent || "").trim()),
        editReview: Boolean(status?.classList.contains("is-review")),
        editApplied: Boolean(status?.classList.contains("is-applied")),
        editRejected: Boolean(status?.classList.contains("is-rejected")),
        finals: finals.length,
      };
    },
  });
  const terminalTrace = page.locator("#messages .execution-trace.completed");
  await expect(terminalTrace).toHaveCount(1);
  await expect(terminalTrace).not.toHaveClass(/\bis-expanded\b/);
  const terminalTraceToggle = terminalTrace.locator(":scope > [data-execution-trace-toggle]");
  await expect(terminalTraceToggle).toHaveCount(1);
  await expect(terminalTraceToggle).toHaveAttribute("aria-expanded", "false");
  const stage = terminalTrace.locator(
    'article.tool-process > details.tool-process-stage[data-current-action="propose_edit"]',
  );
  await expect(stage).toHaveCount(1);
  const item = stage.locator("details.tool-process-item");
  await expect(item).toHaveCount(1);
  const resultDetails = item.locator(".tool-process-detail");
  await expect(resultDetails).toHaveCount(2);
  const resultRegion = resultDetails.nth(1);
  const resultPre = resultRegion.locator("pre");
  await expect(resultPre).toHaveCount(1);
  await expect(resultRegion).toBeHidden();
  await expect(resultPre).toBeHidden();

  await terminalTraceToggle.click();
  await expect(terminalTrace).toHaveClass(/\bis-expanded\b/);
  await expect(terminalTraceToggle).toHaveAttribute("aria-expanded", "true");
  await expect(stage.locator(":scope > summary.tool-process-stage-summary")).toBeVisible();
  await stage.locator(":scope > summary.tool-process-stage-summary").click();
  await expect(stage).toHaveAttribute("open", "");
  await expect(item.locator(":scope > summary")).toBeVisible();
  await item.locator(":scope > summary").click();
  await expect(item).toHaveAttribute("open", "");
  await expect(resultRegion).toBeVisible();
  await expect(resultPre).toBeVisible();
  await expect(resultPre).toHaveText(EDIT_AUTHORIZATION_CONFLICT_CONTRACT.conflictReason);
  const renderedResult = String(await resultPre.innerText()).trim();
  const resultVisible = await resultPre.isVisible();
  const conflictReasonMatches = renderedResult
    === EDIT_AUTHORIZATION_CONFLICT_CONTRACT.conflictReason
    && countOccurrences(
      renderedResult,
      EDIT_AUTHORIZATION_CONFLICT_CONTRACT.conflictReason,
    ) === 1;
  expect(resultVisible).toBe(true);
  expect(conflictReasonMatches).toBe(true);

  await item.locator(":scope > summary").click();
  await expect(item).not.toHaveAttribute("open", "");
  await stage.locator(":scope > summary.tool-process-stage-summary").click();
  await expect(stage).not.toHaveAttribute("open", "");
  await terminalTraceToggle.click();
  await expect(terminalTrace).not.toHaveClass(/\bis-expanded\b/);
  await expect(terminalTraceToggle).toHaveAttribute("aria-expanded", "false");
  await expect(resultPre).toBeHidden();
  return {
    ...projection,
    conflictVisible: visibleConflict,
    resultVisible,
    conflictReasonMatches,
  };
}

async function exerciseEditAuthorizationConflictLifecycle(h4, runtime) {
  const branch = EDIT_AUTHORIZATION_CONFLICT_CONTRACT;
  const started = await beginEditAuthorizationLifecycle(h4, runtime, "conflict", branch);
  const waitingReload = await reloadWaitingEditAuthorizationLifecycle(h4, started);
  const transitionReady = h4.host.ready.proposeEditThirdPartyTransition;
  expect(transitionReady).toEqual({
    command: "transition-propose-edit-third-party",
    path: EDIT_AUTHORIZATION_CONTRACT.path,
    expectedBeforeSha256: EDIT_AUTHORIZATION_CONTRACT.initialSha256,
    byteLength: 28,
    targetSha256: EDIT_AUTHORIZATION_THIRD_PARTY_SHA256,
  });

  const waitingConflictMetrics = editAuthorizationConflictMetricsProjection(
    waitingReload.metricsAfterWaitingReload,
  );
  expectEditAuthorizationConflictMetrics(waitingConflictMetrics, "waiting");
  const transitionBoundary = h4.requestBoundary();
  const transitionMetricsBefore = waitingReload.metricsAfterWaitingReload;
  const transitionResponse = await h4.host.command(transitionReady.command);
  expect(transitionResponse.ok).toBe(true);
  const transitionProjection = editAuthorizationThirdPartyTransitionProjection(
    transitionResponse.transition,
  );
  expect(transitionProjection).toEqual({
    accepted: true,
    reason: "",
    commandKeysExact: true,
    attempt: 1,
    pathMatches: true,
    fileBefore: {
      state: "initial",
      exists: true,
      initialHashMatches: true,
      targetHashMatches: false,
      thirdPartyHashMatches: false,
    },
    fileAfter: {
      state: "third-party",
      exists: true,
      initialHashMatches: false,
      targetHashMatches: false,
      thirdPartyHashMatches: true,
    },
    fixedBytes: {
      byteLength: 28,
      sha256Matches: true,
      hashMatches: true,
    },
    projectTreeUnchanged: false,
    projectTreeChangedOnlyAtFixedPath: true,
    homeTreeUnchanged: true,
    artifactsTreeUnchanged: true,
    backupCountBefore: 0,
    backupCountAfter: 0,
    productionCallbacks: {
      registeredDelegations: 0,
      proposalDelegations: 0,
      applyDelegations: 0,
      writes: 0,
      backups: 0,
      toolExecutions: 0,
      runCommandAttempts: 0,
    },
  });
  const metricsAfterTransition = await h4.metrics();
  expect(metricsAfterTransition.chatRequests).toEqual(transitionMetricsBefore.chatRequests);
  expect(editAuthorizationMetricsProjection(metricsAfterTransition))
    .toEqual(editAuthorizationMetricsProjection(transitionMetricsBefore));
  const transitionedConflictMetrics = editAuthorizationConflictMetricsProjection(
    metricsAfterTransition,
  );
  expectEditAuthorizationConflictMetrics(
    transitionedConflictMetrics,
    "transitioned",
    transitionProjection,
  );
  expect(metricsAfterTransition.production.agentRuns).toHaveLength(1);
  expect(metricsAfterTransition.production.runtimeRuns).toHaveLength(1);
  expect(new Set(h4.controlIds().agentRunIds)).toEqual(new Set([started.agentRunId]));
  expect(new Set(h4.controlIds().runtimeRunIds)).toEqual(new Set([started.firstRuntimeRunId]));
  const transitionRequests = editAuthorizationRequestProjection(
    h4,
    transitionBoundary,
    transitionMetricsBefore,
    metricsAfterTransition,
    started.agentRunId,
  );
  expectEditAuthorizationZeroRequests(transitionRequests);

  const completed = await completeEditAuthorizationLifecycle(h4, started, {
    ...waitingReload,
    decisionMetricsBefore: metricsAfterTransition,
  });
  expect(completed.runtimeProjection.map((snapshot) => snapshot.nextCursor)).toEqual([4, 3]);
  const terminalConflictMetrics = editAuthorizationConflictMetricsProjection(
    completed.metricsAtTerminal,
  );
  expectEditAuthorizationConflictMetrics(
    terminalConflictMetrics,
    "terminal",
    transitionProjection,
  );
  const terminalDom = await editAuthorizationConflictDomProjection(
    h4,
    completed.terminalDom,
    `${runtime}-edit-authorization-conflict-terminal`,
  );
  expect(terminalDom.conflictVisible).toEqual({
    action: "propose_edit",
    pathMatches: true,
    stageFailed: true,
    itemFailed: true,
    resultDetails: 1,
    errorPresent: true,
    editReview: false,
    editApplied: false,
    editRejected: true,
    finals: 1,
  });
  expect(terminalDom.resultVisible).toBe(true);
  expect(terminalDom.conflictReasonMatches).toBe(true);
  const terminalResultMeta = completed.sessionAuthorizationMeta[1].authorization;
  expect(terminalResultMeta).toMatchObject({
    decision: "approved",
    applied: false,
    rejected: true,
  });
  expectEditAuthorizationResult(terminalResultMeta.result, branch);
  expectEditAuthorizationResult(terminalResultMeta.authorizationResult, branch);
  const proposalId = String(started.waitingAgent.pendingAuthorization?.proposalId || "");
  expect(proposalId).toMatch(/^[0-9a-f]{64}$/);
  const rawConflictResult = editAuthorizationConflictRawResultProjection(
    completed.completedAgent.events[6]?.data?.result,
    proposalId,
  );
  expect(rawConflictResult).toEqual({
    keysExact: true,
    ok: false,
    action: "apply_edit",
    proposalIdMatches: true,
    pathMatches: true,
    conflict: true,
    applied: false,
    currentMtimePresent: true,
    errorPresent: true,
    rejectedAbsent: true,
    replayedAbsent: true,
    backupPathAbsent: true,
  });

  const terminalReload = await reloadCompletedEditAuthorizationLifecycle(
    h4,
    started,
    completed,
  );
  const restoredConflictDom = await editAuthorizationConflictDomProjection(
    h4,
    terminalReload.restoredTerminalDom,
    `${runtime}-edit-authorization-conflict-terminal-reload`,
  );
  expect(restoredConflictDom).toEqual(terminalDom);
  const reloadedConflictMetrics = editAuthorizationConflictMetricsProjection(
    terminalReload.metricsAfterTerminalReload,
  );
  expect(reloadedConflictMetrics).toEqual(terminalConflictMetrics);
  expectEditAuthorizationConflictMetrics(
    reloadedConflictMetrics,
    "terminal",
    transitionProjection,
  );
  const reloadedRawConflictResult = editAuthorizationConflictRawResultProjection(
    terminalReload.agentAfterReload.body.events[6]?.data?.result,
    proposalId,
  );
  expect(reloadedRawConflictResult).toEqual(rawConflictResult);

  const conflictSubmissionProjection = {
    requests: completed.decisionRequests,
    events: completed.terminalEvents.slice(started.waitingEvents.length, 9),
    execution: completed.terminalExecution,
    sameAgentRun: completed.completedAgent.agentRunId === started.waitingAgent.agentRunId,
    authorizationCleared: completed.completedAgent.pendingAuthorization == null,
    layers: {
      submittedDecision: completed.terminalEvents[5].decision,
      rawResult: rawConflictResult,
      eventResult: completed.terminalEvents[6].result,
      projectedDecision: terminalResultMeta.decision,
      projectedApplied: terminalResultMeta.applied,
      projectedRejected: terminalResultMeta.rejected,
    },
    fileEffects: {
      base: completed.terminalMetrics,
      conflict: terminalConflictMetrics,
    },
  };
  expect(conflictSubmissionProjection.layers).toEqual({
    submittedDecision: "approved",
    rawResult: {
      keysExact: true,
      ok: false,
      action: "apply_edit",
      proposalIdMatches: true,
      pathMatches: true,
      conflict: true,
      applied: false,
      currentMtimePresent: true,
      errorPresent: true,
      rejectedAbsent: true,
      replayedAbsent: true,
      backupPathAbsent: true,
    },
    eventResult: {
      ok: false,
      action: "apply_edit",
      proposalIdPresent: true,
      pathMatches: true,
      diff: {
        present: false,
        oldMarkerOnce: false,
        newMarkerOnce: false,
        oldHeaderMatches: false,
        newHeaderMatches: false,
      },
      applied: false,
      rejected: false,
      replayed: false,
      backupPresent: false,
      conflict: true,
      errorPresent: true,
      privateFieldsAbsent: true,
      retryFieldsAbsent: true,
    },
    projectedDecision: "approved",
    projectedApplied: false,
    projectedRejected: true,
  });

  const refreshLifecycle = {
    waiting: {
      sameAgentRun: waitingReload.waitingAgentAfterReload.body.agentRunId === started.agentRunId,
      sameAuthorization: waitingReload.waitingAgentAfterReload.body.pendingAuthorization
        ?.authorizationId === started.authorizationId,
      sameSnapshot: JSON.stringify(editAuthorizationWaitingSnapshotProjection(
        waitingReload.waitingAgentAfterReload.body,
        waitingReload.waitingSessionAfterReload.body,
        started.agentRunId,
        started.authorizationId,
      )) === JSON.stringify(started.waitingSnapshot),
      dom: waitingReload.restoredWaitingDom,
      requests: waitingReload.waitingReloadRequests,
      conflictMetrics: waitingConflictMetrics,
      permissionRestored: waitingReload.permissionRestored,
    },
    terminal: {
      sameAgentRun: terminalReload.agentAfterReload.body.agentRunId === started.agentRunId,
      sameEvents: JSON.stringify(editAuthorizationConflictEventProjection(
        terminalReload.agentAfterReload.body,
        started.authorizationId,
      )) === JSON.stringify(completed.terminalEvents),
      sameSession: JSON.stringify(editAuthorizationSessionRoleProjection(
        terminalReload.sessionAfterReload.body.messages,
        branch,
      )) === JSON.stringify(completed.sessionRoleContent),
      sameAuthorizationMeta: JSON.stringify(editAuthorizationSessionMetaProjection(
        terminalReload.sessionAfterReload.body.messages,
        started.agentRunId,
        started.authorizationId,
      )) === JSON.stringify(completed.sessionAuthorizationMeta),
      sameRawConflict: JSON.stringify(reloadedRawConflictResult)
        === JSON.stringify(rawConflictResult),
      resultVisible: restoredConflictDom.resultVisible,
      conflictReasonMatches: restoredConflictDom.conflictReasonMatches,
      dom: restoredConflictDom,
      requests: terminalReload.terminalReloadRequests,
      conflictMetrics: reloadedConflictMetrics,
      permissionRestored: terminalReload.permissionRestored,
    },
  };
  expect(refreshLifecycle.waiting).toMatchObject({
    sameAgentRun: true,
    sameAuthorization: true,
    sameSnapshot: true,
    permissionRestored: true,
  });
  expect(refreshLifecycle.terminal).toMatchObject({
    sameAgentRun: true,
    sameEvents: true,
    sameSession: true,
    sameAuthorizationMeta: true,
    sameRawConflict: true,
    resultVisible: true,
    conflictReasonMatches: true,
    permissionRestored: true,
  });
  const thirdPartyTransitionProjection = {
    ready: {
      commandMatches: transitionReady.command === "transition-propose-edit-third-party",
      pathMatches: transitionReady.path === EDIT_AUTHORIZATION_CONTRACT.path,
      initialHashMatches: transitionReady.expectedBeforeSha256
        === EDIT_AUTHORIZATION_CONTRACT.initialSha256,
      byteLength: Number(transitionReady.byteLength || 0),
      targetHashMatches: transitionReady.targetSha256
        === EDIT_AUTHORIZATION_THIRD_PARTY_SHA256,
    },
    transition: transitionProjection,
    metrics: transitionedConflictMetrics,
    requests: transitionRequests,
    sameAgentRun: metricsAfterTransition.production.agentRuns.length === 1
      && metricsAfterTransition.production.agentRuns[0]?.agentRunId
        === idHash(started.agentRunId),
    sameRuntime: metricsAfterTransition.production.runtimeRuns.length === 1
      && metricsAfterTransition.production.runtimeRuns[0]?.runtimeRunId
        === idHash(started.firstRuntimeRunId),
  };
  expect(thirdPartyTransitionProjection.ready).toEqual({
    commandMatches: true,
    pathMatches: true,
    initialHashMatches: true,
    byteLength: 28,
    targetHashMatches: true,
  });
  expect(thirdPartyTransitionProjection).toMatchObject({
    sameAgentRun: true,
    sameRuntime: true,
  });

  const hashes = {
    waitingEventProjection: canonicalHash(started.waitingEvents),
    waitingSnapshot: canonicalHash(started.waitingSnapshot),
    waitingDom: canonicalHash(started.waitingDom),
    thirdPartyTransitionProjection: canonicalHash(thirdPartyTransitionProjection),
    conflictSubmissionProjection: canonicalHash(conflictSubmissionProjection),
    runtimeProjection: canonicalHash(completed.runtimeProjection),
    sessionRoleContent: canonicalHash(completed.sessionRoleContent),
    sessionAuthorizationMeta: canonicalHash(completed.sessionAuthorizationMeta),
    terminalDom: canonicalHash(terminalDom),
    refreshLifecycle: canonicalHash(refreshLifecycle),
  };
  const frozenHashKeys = Object.keys(H4_8D_SEMANTIC_HASHES).sort();
  expect(Object.keys(hashes).sort()).toEqual(frozenHashKeys);
  const frozenHashValues = Object.values(H4_8D_SEMANTIC_HASHES);
  const allEmpty = frozenHashValues.every((value) => value === "");
  const allFrozen = frozenHashValues.every((value) => /^[0-9a-f]{64}$/.test(value));
  expect(allEmpty || allFrozen).toBe(true);
  if (allFrozen) {
    expect(hashes).toEqual(H4_8D_SEMANTIC_HASHES);
  } else {
    expect(allEmpty).toBe(true);
    expect(runtime).toBe("bundle");
  }

  h4.evidence(`${runtime}-edit-authorization-conflict-reload`, {
    runtime,
    decision: branch.decision,
    identities: {
      agentRunId: idHash(started.agentRunId),
      authorizationId: idHash(started.authorizationId),
    },
    counts: {
      agentRuns: completed.metricsAtTerminal.production.agentRuns.length,
      runtimes: completed.metricsAtTerminal.production.runtimeRuns.length,
      upstreamChat: completed.metricsAtTerminal.chatRequests.length,
      agentRunPost: completed.totalRequests.agentRunPost,
      authorizationPost: completed.totalRequests.authorizationPost,
      resumePost: completed.totalRequests.resumePost,
      registeredDelegations: completed.terminalMetrics.counters.registeredDelegations,
      registeredExecutions: completed.terminalMetrics.registeredExecutions.length,
      proposalDelegations: completed.terminalMetrics.counters.proposalDelegations,
      applyDelegations: completed.terminalMetrics.counters.applyDelegations,
      writes: completed.terminalMetrics.counters.writes,
      backups: completed.terminalMetrics.counters.backups,
      conflictObservations: terminalConflictMetrics.counters.conflictObservations,
      transitionAttempts: terminalConflictMetrics.counters.transitionAttempts,
      transitionWrites: terminalConflictMetrics.counters.transitionWrites,
      transitionRejections: terminalConflictMetrics.counters.transitionRejections,
      unsafe: completed.terminalMetrics.counters.unsafe,
    },
    agentCursors: {
      waiting: started.waitingAgent.nextCursor,
      terminal: completed.completedAgent.nextCursor,
    },
    eventTypes: completed.terminalEvents.map((event) => event.type),
    runtimeCursors: completed.runtimeProjection.map((snapshot) => snapshot.nextCursor),
    waiting: {
      snapshot: started.waitingSnapshot,
      dom: started.waitingDom,
    },
    transition: thirdPartyTransitionProjection,
    terminal: {
      layers: conflictSubmissionProjection.layers,
      sessionRoleContent: completed.sessionRoleContent,
      sessionAuthorizationMeta: completed.sessionAuthorizationMeta,
      dom: terminalDom,
    },
    fileEffects: terminalConflictMetrics,
    decisionRequests: completed.decisionRequests,
    waitingReload: waitingReload.waitingReloadRequests,
    terminalReload: terminalReload.terminalReloadRequests,
    hashes,
  });
}

async function exerciseEditAuthorizationRetryLifecycle(h4, runtime) {
  expect(Object.keys(H4_8F_SEMANTIC_HASHES)).toEqual(H4_8F_SEMANTIC_HASH_KEYS);
  const configuredHashes = Object.values(H4_8F_SEMANTIC_HASHES);
  const bootstrapMode = configuredHashes.every((value) => value === "");
  const frozenMode = configuredHashes.every((value) => /^[a-f0-9]{64}$/.test(value));
  expect(bootstrapMode || frozenMode).toBe(true);
  if (bootstrapMode) expect(runtime).toBe("bundle");

  const started = await beginEditAuthorizationLifecycle(h4, runtime, "approved");
  const waitingReload = await reloadWaitingEditAuthorizationLifecycle(h4, started);
  const {
    page,
    branch,
    agentRunId,
    authorizationId,
    sessionId,
  } = started;
  const authorizationUrl = new URL(
    `/api/agent/runs/${encodeURIComponent(agentRunId)}/authorization`,
    h4.host.ready.codeUrl,
  ).toString();
  const authorizationRequests = [];
  const authorizationFailures = [];
  const injectedRequests = [];
  let injectionCount = 0;
  let signalIntercepted = null;
  const firstIntercepted = new Promise((resolve) => {
    signalIntercepted = resolve;
  });
  let openAbortGate = null;
  let abortGateOpened = false;
  const abortGate = new Promise((resolve) => {
    openAbortGate = () => {
      if (abortGateOpened) return;
      abortGateOpened = true;
      resolve();
    };
  });
  const isAuthorizationRequest = (request) => {
    const url = new URL(request.url());
    return url.origin === new URL(h4.host.ready.codeUrl).origin
      && /^\/api\/agent\/runs\/[^/]+\/authorization$/.test(url.pathname)
      && request.method() === "POST";
  };
  const onRequest = (request) => {
    if (!isAuthorizationRequest(request)) return;
    authorizationRequests.push(editAuthorizationRetryRequestProjection(
      request,
      authorizationUrl,
      agentRunId,
      authorizationId,
    ));
  };
  const onRequestFailed = (request) => {
    if (!isAuthorizationRequest(request)) return;
    authorizationFailures.push({
      request: editAuthorizationRetryRequestProjection(
        request,
        authorizationUrl,
        agentRunId,
        authorizationId,
      ),
      errorPresent: Boolean(String(request.failure()?.errorText || "")),
    });
  };
  const faultHandler = async (route) => {
    injectionCount += 1;
    const projection = editAuthorizationRetryRequestProjection(
      route.request(),
      authorizationUrl,
      agentRunId,
      authorizationId,
    );
    injectedRequests.push(projection);
    signalIntercepted(projection);
    await abortGate;
    await route.abort("failed");
  };

  let requestListenerInstalled = false;
  let failedListenerInstalled = false;
  let routeInstalled = false;
  let firstClickPromise = null;
  try {
    page.on("request", onRequest);
    requestListenerInstalled = true;
    page.on("requestfailed", onRequestFailed);
    failedListenerInstalled = true;
    await page.route(authorizationUrl, faultHandler, { times: 1 });
    routeInstalled = true;

    const expectedRequest = {
      method: "POST",
      exactUrl: true,
      targetRunMatches: true,
      queryEmpty: true,
      hashEmpty: true,
      body: {
        parseable: true,
        keysExact: true,
        authorizationIdMatches: true,
        decision: "approved",
      },
    };
    const expectedUiBase = {
      panelVisible: true,
      rowCount: 1,
      selected: true,
      approveCount: 1,
    };
    expect(await editAuthorizationRetryUiProjection(page)).toEqual({
      ...expectedUiBase,
      rowSubmitting: false,
      selectionDisabled: false,
      approveEnabled: true,
      errorToastCount: 0,
      errorToastVisible: false,
      errorToastNonEmpty: false,
    });

    const failureBoundary = h4.requestBoundary();
    const failureMetricsBefore = await h4.metrics();
    const failureControlIdsBefore = h4.controlIds();
    const decisionButton = page.locator('#authorizationPanel [data-auth-action="approve"]');
    firstClickPromise = decisionButton.click();
    const interceptedProjection = await firstIntercepted;
    expect(injectionCount).toBe(1);
    expect(interceptedProjection).toEqual(expectedRequest);
    expect(injectedRequests).toEqual([expectedRequest]);
    await expect.poll(() => authorizationRequests.length).toBe(1);
    expect(authorizationRequests).toEqual([expectedRequest]);
    const submittingUi = await editAuthorizationRetryUiProjection(page);
    expect(submittingUi).toEqual({
      ...expectedUiBase,
      rowSubmitting: true,
      selectionDisabled: true,
      approveEnabled: false,
      errorToastCount: 0,
      errorToastVisible: false,
      errorToastNonEmpty: false,
    });

    openAbortGate();
    await firstClickPromise;
    firstClickPromise = null;
    await expect.poll(() => authorizationFailures.length).toBe(1);
    expect(authorizationFailures).toEqual([{
      request: expectedRequest,
      errorPresent: true,
    }]);
    let recoveredUi = null;
    await expect.poll(async () => {
      recoveredUi = await editAuthorizationRetryUiProjection(page);
      return recoveredUi;
    }).toEqual({
      ...expectedUiBase,
      rowSubmitting: false,
      selectionDisabled: false,
      approveEnabled: true,
      errorToastCount: 1,
      errorToastVisible: true,
      errorToastNonEmpty: true,
    });

    const failedAgentResponse = await fetchProductionJson(
      page,
      `/api/agent/runs/${encodeURIComponent(agentRunId)}?cursor=0&wait=0`,
    );
    expect(failedAgentResponse.status).toBe(200);
    expect(failedAgentResponse.body.agentRunId).toBe(agentRunId);
    expect(failedAgentResponse.body.status).toBe("waiting_authorization");
    expect(failedAgentResponse.body.nextCursor).toBe(5);
    expect(failedAgentResponse.body.pendingAuthorization?.authorizationId).toBe(authorizationId);
    expect(failedAgentResponse.body.pendingAuthorization?.decision).toBe("pending");
    const failedEvents = editAuthorizationEventProjection(
      failedAgentResponse.body,
      authorizationId,
    );
    expect(failedEvents).toEqual(started.waitingEvents);
    expect(failedEvents.map((event) => event.type)).toEqual([
      "created",
      "model_started",
      "model_completed",
      "tool_started",
      "authorization_required",
    ]);
    const failedExecution = editAuthorizationExecutionProjection(failedAgentResponse.body);
    expect(failedExecution).toEqual(started.waitingExecution);
    expect(failedExecution).toHaveLength(1);
    expect(failedExecution[0].authorizationDecision).toBe("");

    const failedSessionResponse = await fetchProductionJson(
      page,
      `/api/sessions/${encodeURIComponent(sessionId)}`,
    );
    expect(failedSessionResponse.status).toBe(200);
    const failedSnapshot = editAuthorizationWaitingSnapshotProjection(
      failedAgentResponse.body,
      failedSessionResponse.body,
      agentRunId,
      authorizationId,
    );
    expect(failedSnapshot).toEqual(started.waitingSnapshot);
    expect(editAuthorizationSessionDiffProjection(
      failedSessionResponse.body.messages,
      failedAgentResponse.body.pendingAuthorization,
    )).toEqual(started.waitingSnapshot.session.diff);
    const failedDom = await editAuthorizationDomProjection(h4, "waiting", branch);
    expect(failedDom).toEqual(started.waitingDom);

    const metricsAfterFailure = await h4.metrics();
    expect(metricsAfterFailure.chatRequests).toEqual(failureMetricsBefore.chatRequests);
    const failedMetrics = editAuthorizationMetricsProjection(metricsAfterFailure);
    expect(failedMetrics).toEqual(editAuthorizationMetricsProjection(failureMetricsBefore));
    expectEditAuthorizationMetrics(failedMetrics, branch, "waiting");
    const failureRequests = editAuthorizationRequestProjection(
      h4,
      failureBoundary,
      failureMetricsBefore,
      metricsAfterFailure,
      agentRunId,
    );
    expectEditAuthorizationZeroRequests(failureRequests);
    expect(authorizationRequests).toEqual([expectedRequest]);
    expect(authorizationFailures).toHaveLength(1);
    const failureControlIdsAfter = h4.controlIds();
    expect(failureControlIdsAfter).toEqual(failureControlIdsBefore);
    expect(new Set(failureControlIdsAfter.agentRunIds)).toEqual(new Set([agentRunId]));
    expect(new Set(failureControlIdsAfter.runtimeRunIds))
      .toEqual(new Set([started.firstRuntimeRunId]));

    const completed = await completeEditAuthorizationLifecycle(h4, started, {
      ...waitingReload,
      decisionMetricsBefore: metricsAfterFailure,
    });
    await expect.poll(() => authorizationRequests.length).toBe(2);
    expect(authorizationRequests).toEqual([expectedRequest, expectedRequest]);
    expect(authorizationFailures).toEqual([{
      request: expectedRequest,
      errorPresent: true,
    }]);
    expect(injectionCount).toBe(1);
    expect(completed.decisionRequests.authorizationPost).toBe(1);
    expect(completed.decisionRequests.resumePost).toBe(1);
    expect(completed.terminalEvents.filter((event) => event.type === "authorization_submitted"))
      .toHaveLength(1);
    expect(completed.terminalEvents.filter((event) => event.type === "resumed"))
      .toHaveLength(1);
    expect(completed.terminalExecution[0].result.replayed).toBe(false);
    expect(completed.terminalMetrics.counters).toMatchObject({
      applyDelegations: 1,
      writes: 1,
      backups: 1,
    });
    const terminalReload = await reloadCompletedEditAuthorizationLifecycle(
      h4,
      started,
      completed,
    );
    expect(authorizationRequests).toEqual([expectedRequest, expectedRequest]);
    expect(authorizationFailures).toHaveLength(1);

    const failedAttemptProjection = {
      transport: {
        attempts: 1,
        failed: 1,
        injected: injectionCount,
        forwarded: failureRequests.authorizationPost,
        request: authorizationRequests[0],
        failure: authorizationFailures[0],
      },
      ui: {
        submitting: submittingUi,
        recovered: recoveredUi,
      },
      durable: {
        status: String(failedAgentResponse.body.status || ""),
        cursor: Number(failedAgentResponse.body.nextCursor || 0),
        authorizationSubmitted: failedEvents
          .filter((event) => event.type === "authorization_submitted").length,
        resumed: failedEvents.filter((event) => event.type === "resumed").length,
        pendingDecision: String(
          failedAgentResponse.body.pendingAuthorization?.decision || "",
        ),
        executionDecisionEmpty: failedExecution[0].authorizationDecision === "",
        sameEvents: JSON.stringify(failedEvents) === JSON.stringify(started.waitingEvents),
        sameExecution: JSON.stringify(failedExecution)
          === JSON.stringify(started.waitingExecution),
      },
      state: {
        sameSnapshot: JSON.stringify(failedSnapshot) === JSON.stringify(started.waitingSnapshot),
        sameDom: JSON.stringify(failedDom) === JSON.stringify(started.waitingDom),
        sameControlIds: JSON.stringify(failureControlIdsAfter)
          === JSON.stringify(failureControlIdsBefore),
      },
      requests: failureRequests,
      fileEffects: {
        applyDelegations: failedMetrics.counters.applyDelegations,
        writes: failedMetrics.counters.writes,
        backups: failedMetrics.counters.backups,
        applyTimelineCount: failedMetrics.applyTimeline.length,
        writeTimelineCount: failedMetrics.writeTimeline.length,
        backupTimelineCount: failedMetrics.backupTimeline.length,
      },
    };
    const retrySubmissionProjection = {
      transport: {
        attempts: authorizationRequests.length,
        failed: authorizationFailures.length,
        injected: injectionCount,
        forwarded: completed.decisionRequests.authorizationPost,
        requests: authorizationRequests,
      },
      requests: completed.decisionRequests,
      events: completed.terminalEvents.slice(started.waitingEvents.length, 9),
      execution: completed.terminalExecution,
      sameAgentRun: completed.completedAgent.agentRunId === started.waitingAgent.agentRunId,
      authorizationCleared: completed.completedAgent.pendingAuthorization == null,
      durableAuthorizationCount: completed.terminalEvents
        .filter((event) => event.type === "authorization_submitted").length,
      resumeCount: completed.terminalEvents.filter((event) => event.type === "resumed").length,
      replayed: completed.terminalExecution[0].result.replayed,
      fileEffects: {
        applyDelegations: completed.terminalMetrics.counters.applyDelegations,
        writes: completed.terminalMetrics.counters.writes,
        backups: completed.terminalMetrics.counters.backups,
      },
    };
    const refreshLifecycle = {
      waiting: {
        sameAgentRun: waitingReload.waitingAgentAfterReload.body.agentRunId === agentRunId,
        sameAuthorization: waitingReload.waitingAgentAfterReload.body.pendingAuthorization
          ?.authorizationId === authorizationId,
        sameSnapshot: JSON.stringify(editAuthorizationWaitingSnapshotProjection(
          waitingReload.waitingAgentAfterReload.body,
          waitingReload.waitingSessionAfterReload.body,
          agentRunId,
          authorizationId,
        )) === JSON.stringify(started.waitingSnapshot),
        dom: waitingReload.restoredWaitingDom,
        requests: waitingReload.waitingReloadRequests,
        permissionRestored: waitingReload.permissionRestored,
      },
      terminal: {
        sameAgentRun: terminalReload.agentAfterReload.body.agentRunId === agentRunId,
        sameEvents: JSON.stringify(editAuthorizationEventProjection(
          terminalReload.agentAfterReload.body,
          authorizationId,
        )) === JSON.stringify(completed.terminalEvents),
        sameSession: JSON.stringify(editAuthorizationSessionRoleProjection(
          terminalReload.sessionAfterReload.body.messages,
          branch,
        )) === JSON.stringify(completed.sessionRoleContent),
        sameAuthorizationMeta: JSON.stringify(editAuthorizationSessionMetaProjection(
          terminalReload.sessionAfterReload.body.messages,
          agentRunId,
          authorizationId,
        )) === JSON.stringify(completed.sessionAuthorizationMeta),
        dom: terminalReload.restoredTerminalDom,
        requests: terminalReload.terminalReloadRequests,
        permissionRestored: terminalReload.permissionRestored,
      },
      transport: {
        attempts: authorizationRequests.length,
        failed: authorizationFailures.length,
        injected: injectionCount,
      },
    };
    expect(refreshLifecycle.waiting.permissionRestored).toBe(true);
    expect(refreshLifecycle.terminal.permissionRestored).toBe(true);
    const hashes = {
      waitingEventProjection: canonicalHash(started.waitingEvents),
      waitingSnapshot: canonicalHash(started.waitingSnapshot),
      waitingDom: canonicalHash(started.waitingDom),
      failedAttemptProjection: canonicalHash(failedAttemptProjection),
      retrySubmissionProjection: canonicalHash(retrySubmissionProjection),
      runtimeProjection: canonicalHash(completed.runtimeProjection),
      sessionRoleContent: canonicalHash(completed.sessionRoleContent),
      sessionAuthorizationMeta: canonicalHash(completed.sessionAuthorizationMeta),
      terminalDom: canonicalHash(completed.terminalDom),
      refreshLifecycle: canonicalHash(refreshLifecycle),
    };
    expect(Object.keys(hashes)).toEqual(H4_8F_SEMANTIC_HASH_KEYS);
    if (frozenMode) {
      expect(hashes).toEqual(H4_8F_SEMANTIC_HASHES);
    } else {
      expect(bootstrapMode).toBe(true);
      expect(runtime).toBe("bundle");
    }

    h4.evidence(`${runtime}-edit-authorization-pre-server-retry`, {
      runtime,
      transport: {
        attempts: authorizationRequests.length,
        failed: authorizationFailures.length,
        injected: injectionCount,
        forwarded: completed.decisionRequests.authorizationPost,
      },
      counts: {
        agentRuns: completed.metricsAtTerminal.production.agentRuns.length,
        runtimes: completed.metricsAtTerminal.production.runtimeRuns.length,
        upstreamChat: completed.metricsAtTerminal.chatRequests.length,
        authorizationPost: completed.totalRequests.authorizationPost,
        resumePost: completed.totalRequests.resumePost,
        registeredDelegations: completed.terminalMetrics.counters.registeredDelegations,
        registeredExecutions: completed.terminalMetrics.registeredExecutions.length,
        proposalDelegations: completed.terminalMetrics.counters.proposalDelegations,
        applyDelegations: completed.terminalMetrics.counters.applyDelegations,
        writes: completed.terminalMetrics.counters.writes,
        backups: completed.terminalMetrics.counters.backups,
      },
      failure: failedAttemptProjection,
      eventTypes: completed.terminalEvents.map((event) => event.type),
      runtimeCursors: completed.runtimeProjection.map((snapshot) => snapshot.nextCursor),
      retry: retrySubmissionProjection,
      terminal: {
        sessionRoleContent: completed.sessionRoleContent,
        sessionAuthorizationMeta: completed.sessionAuthorizationMeta,
        dom: completed.terminalDom,
      },
      waitingReload: waitingReload.waitingReloadRequests,
      terminalReload: terminalReload.terminalReloadRequests,
      hashes,
    });
  } finally {
    openAbortGate();
    if (firstClickPromise) await firstClickPromise.catch(() => {});
    if (requestListenerInstalled) page.off("request", onRequest);
    if (failedListenerInstalled) page.off("requestfailed", onRequestFailed);
    if (routeInstalled) await page.unroute(authorizationUrl, faultHandler);
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

test("bundle TIFF uses derived PNG preview while preserving the original attachment", async ({ h4 }) => {
  await completeTiffPreviewLifecycle(h4, "bundle");
});

test("direct classic TIFF uses derived PNG preview while preserving the original attachment", async ({ h4 }) => {
  await completeTiffPreviewLifecycle(h4, "classic");
});

test("bundle primary completion owns elapsed while queue and parallel remain distinct", async ({ h4 }) => {
  await completePrimaryTimingOwnershipLifecycle(h4, "bundle");
});

test("direct classic primary completion owns elapsed while queue and parallel remain distinct", async ({ h4 }) => {
  await completePrimaryTimingOwnershipLifecycle(h4, "classic");
});

test("bundle detached parallel model failure stays isolated and reloads uniquely", async ({ h4 }) => {
  await exerciseDetachedParallelFailureIsolation(h4, "bundle");
});

test("direct classic detached parallel model failure stays isolated and reloads uniquely", async ({ h4 }) => {
  await exerciseDetachedParallelFailureIsolation(h4, "classic");
});

test("bundle questionnaire survives reload, submits once, and resumes same AgentRun", async ({ h4 }) => {
  await exerciseQuestionnaireRefreshLifecycle(h4, "bundle");
});

test("direct classic questionnaire survives reload, submits once, and resumes same AgentRun", async ({ h4 }) => {
  await exerciseQuestionnaireRefreshLifecycle(h4, "classic");
});

test("bundle questionnaire queue survives waiting reload and promotes after main completion", async ({ h4 }) => {
  await exerciseQuestionnaireQueueRefreshLifecycle(h4, "bundle");
});

test("direct classic questionnaire queue survives waiting reload and promotes after main completion", async ({ h4 }) => {
  await exerciseQuestionnaireQueueRefreshLifecycle(h4, "classic");
});

test("bundle mixed questionnaire preserves progress across reload and submits once", async ({ h4 }) => {
  await exerciseMixedQuestionnaireProgressLifecycle(h4, "bundle");
});

test("direct classic mixed questionnaire preserves progress across reload and submits once", async ({ h4 }) => {
  await exerciseMixedQuestionnaireProgressLifecycle(h4, "classic");
});

test("bundle edit authorization approve survives reload and applies exactly once", async ({ h4 }) => {
  await exerciseEditAuthorizationLifecycle(h4, "bundle", "approved");
});

test("direct classic edit authorization approve survives reload and applies exactly once", async ({ h4 }) => {
  await exerciseEditAuthorizationLifecycle(h4, "classic", "approved");
});

test("bundle edit authorization reject survives reload without applying", async ({ h4 }) => {
  await exerciseEditAuthorizationLifecycle(h4, "bundle", "rejected");
});

test("direct classic edit authorization reject survives reload without applying", async ({ h4 }) => {
  await exerciseEditAuthorizationLifecycle(h4, "classic", "rejected");
});

test("bundle edit authorization retries once after pre-server failure and applies exactly once", async ({ h4 }) => {
  await exerciseEditAuthorizationRetryLifecycle(h4, "bundle");
});

test("direct classic edit authorization retries once after pre-server failure and applies exactly once", async ({ h4 }) => {
  await exerciseEditAuthorizationRetryLifecycle(h4, "classic");
});

test("bundle approved stale edit conflict preserves third-party content across reload", async ({ h4 }) => {
  await exerciseEditAuthorizationConflictLifecycle(h4, "bundle");
});

test("direct classic approved stale edit conflict preserves third-party content across reload", async ({ h4 }) => {
  await exerciseEditAuthorizationConflictLifecycle(h4, "classic");
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

async function connectedToolItemAndDirectSummary(itemLocator) {
  const itemNode = await itemLocator.elementHandle();
  expect(itemNode).not.toBeNull();
  const summaryNode = await itemNode.$(":scope > summary");
  expect(summaryNode).not.toBeNull();
  expect(await itemNode.evaluate((item, summary) => ({
    itemConnected: item.isConnected,
    summaryConnected: summary.isConnected,
    directOwner: summary.parentElement === item
      && item.querySelector(":scope > summary") === summary,
  }), summaryNode)).toEqual({
    itemConnected: true,
    summaryConnected: true,
    directOwner: true,
  });
  return { itemNode, summaryNode };
}

async function convergeToolProcessProjectionByLanguage(page, contract, initialDom) {
  const initialProcessKey = initialDom.projection.processKey;
  const initialLanguage = await page.locator("html").getAttribute("lang");
  expect(["en", "zh-CN"]).toContain(initialLanguage);
  const originalLanguage = initialLanguage === "zh-CN" ? "zh" : "en";
  const alternateLanguage = originalLanguage === "zh" ? "en" : "zh";
  const initialStage = await initialDom.outer.elementHandle();
  expect(initialStage).not.toBeNull();

  await selectInterfaceLanguage(page, alternateLanguage);
  expect(await initialStage.evaluate((stage) => stage.isConnected)).toBe(false);
  const alternateDom = await failedToolLifecycleDomEvidence(page, contract);
  expect(alternateDom.projection.processKey).toBe(initialProcessKey);
  expect(alternateDom.projection.outerOpen).toBe(true);
  expect(alternateDom.projection.itemOpen).toBe(false);
  expect(alternateDom.projection.outerState).toEqual({ running: true, failed: false });
  expect(alternateDom.projection.itemState).toEqual({ failed: true });
  const alternateStage = await alternateDom.outer.elementHandle();
  expect(alternateStage).not.toBeNull();

  await selectInterfaceLanguage(page, originalLanguage);
  expect(await alternateStage.evaluate((stage) => stage.isConnected)).toBe(false);
  const restoredDom = await failedToolLifecycleDomEvidence(page, contract);
  expect(restoredDom.projection.processKey).toBe(initialProcessKey);
  expect(restoredDom.projection.outerOpen).toBe(true);
  expect(restoredDom.projection.itemOpen).toBe(false);
  expect(restoredDom.projection.outerState).toEqual({ running: true, failed: false });
  expect(restoredDom.projection.itemState).toEqual({ failed: true });
  expect(await page.locator("html").getAttribute("lang")).toBe(initialLanguage);

  return {
    dom: restoredDom,
    evidence: {
      initialLanguage,
      alternateLanguage: alternateLanguage === "zh" ? "zh-CN" : "en",
      initialStageDisconnected: true,
      alternateStageDisconnected: true,
      processKeyStable: true,
      outerOpen: restoredDom.projection.outerOpen,
      itemOpen: restoredDom.projection.itemOpen,
    },
  };
}

async function createToolItemCollapseActionBoundary(page, processKey) {
  return page.evaluateHandle(({ expectedProcessKey }) => {
    const messages = document.querySelector("#messages");
    if (!messages) throw new Error("H4 messages root is unavailable");

    const generations = new WeakMap();
    let nextGeneration = 1;
    const generationFor = (node) => {
      if (!node) return 0;
      if (!generations.has(node)) generations.set(node, nextGeneration++);
      return generations.get(node);
    };
    const currentPair = () => {
      const stage = [...messages.querySelectorAll("details.tool-process-stage[data-tool-process-key]")]
        .find((element) => element.dataset.toolProcessKey === expectedProcessKey);
      const items = stage
        ? [...stage.querySelectorAll(":scope > .tool-process-stage-body .tool-process-list > details.tool-process-item")]
        : [];
      if (items.length !== 1) return null;
      const item = items[0];
      const summary = item.querySelector(":scope > summary");
      const rect = item.getBoundingClientRect();
      if (
        !summary
        || !item.isConnected
        || !summary.isConnected
        || summary.parentElement !== item
        || item.querySelector(":scope > summary") !== summary
        || rect.width <= 0
        || rect.height <= 0
      ) {
        return null;
      }
      return { item, summary };
    };

    const initialPair = currentPair();
    if (!initialPair) throw new Error("H4 current tool item is unavailable");
    const initialBefore = {
      generation: generationFor(initialPair.item),
      itemConnected: initialPair.item.isConnected,
      summaryConnected: initialPair.summary.isConnected,
      directOwner: initialPair.summary.parentElement === initialPair.item
        && initialPair.item.querySelector(":scope > summary") === initialPair.summary,
      itemOpen: initialPair.item.open,
    };
    const state = {
      initialGeneration: initialBefore.generation,
      lastItem: initialPair.item,
      lastSummary: initialPair.summary,
      mutationCount: 0,
      childListMutationCount: 0,
      openMutationCount: 0,
      replacementCount: 0,
      boundItem: null,
      boundSummary: null,
      boundGeneration: 0,
      boundBefore: null,
      clickCount: 0,
      toggleCount: 0,
      firstClick: null,
      firstToggle: null,
      resolveFirstToggle: null,
      firstToggleBoundary: null,
      clickListener: null,
      toggleListener: null,
    };
    const observer = new MutationObserver((records) => {
      state.mutationCount += records.length;
      state.childListMutationCount += records.filter((record) => record.type === "childList").length;
      state.openMutationCount += records.filter((record) => (
        record.type === "attributes" && record.attributeName === "open"
      )).length;
      const pair = currentPair();
      if (
        !pair
        || pair.item !== state.lastItem
        || pair.summary !== state.lastSummary
      ) {
        state.replacementCount += 1;
      }
      state.lastItem = pair?.item || null;
      state.lastSummary = pair?.summary || null;
      generationFor(pair?.item || null);
    });
    observer.observe(messages, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["open"],
    });

    const snapshot = () => {
      const pair = currentPair();
      return {
        performed: Boolean(state.boundItem),
        generation: state.boundGeneration,
        initial: initialBefore,
        before: state.boundBefore,
        mutationCount: state.mutationCount,
        childListMutationCount: state.childListMutationCount,
        openMutationCount: state.openMutationCount,
        replacementCount: state.replacementCount,
        clickCount: state.clickCount,
        toggleCount: state.toggleCount,
        firstClick: state.firstClick,
        firstToggle: state.firstToggle,
        after: {
          itemConnected: Boolean(state.boundItem?.isConnected),
          summaryConnected: Boolean(state.boundSummary?.isConnected),
          directOwner: Boolean(
            state.boundItem
            && state.boundSummary
            && state.boundSummary.parentElement === state.boundItem
            && state.boundItem.querySelector(":scope > summary") === state.boundSummary
          ),
          itemOpen: Boolean(state.boundItem?.open),
          sameCurrent: Boolean(
            pair
            && pair.item === state.boundItem
            && pair.summary === state.boundSummary
          ),
          currentGeneration: generationFor(pair?.item || null),
        },
      };
    };
    return {
      bind: (item, summary) => {
        if (state.boundItem || state.boundSummary) throw new Error("H4 tool item action boundary is already bound");
        const pair = currentPair();
        state.boundItem = item;
        state.boundSummary = summary;
        state.boundGeneration = generationFor(item);
        state.boundBefore = {
          itemConnected: item.isConnected,
          summaryConnected: summary.isConnected,
          directOwner: summary.parentElement === item
            && item.querySelector(":scope > summary") === summary,
          itemOpen: item.open,
          sameInitial: item === initialPair.item && summary === initialPair.summary,
          sameCurrent: Boolean(pair && pair.item === item && pair.summary === summary),
          currentGeneration: generationFor(pair?.item || null),
          replacementCount: state.replacementCount,
        };
        state.firstToggleBoundary = new Promise((resolve) => {
          state.resolveFirstToggle = resolve;
        });
        state.clickListener = (event) => {
          state.clickCount += 1;
          if (!state.firstClick) {
            state.firstClick = {
              generation: state.boundGeneration,
              trusted: event.isTrusted,
              currentTargetIsSummary: event.currentTarget === summary,
              summaryInPath: event.composedPath().includes(summary),
              itemConnected: item.isConnected,
              summaryConnected: summary.isConnected,
              directOwner: summary.parentElement === item
                && item.querySelector(":scope > summary") === summary,
              openAtClick: item.open,
            };
          }
        };
        state.toggleListener = (event) => {
          state.toggleCount += 1;
          if (!state.firstToggle) {
            state.firstToggle = {
              generation: state.boundGeneration,
              trusted: event.isTrusted,
              targetIsItem: event.target === item,
              itemConnected: item.isConnected,
              summaryConnected: summary.isConnected,
              directOwner: summary.parentElement === item
                && item.querySelector(":scope > summary") === summary,
              openAtToggle: item.open,
              oldState: typeof event.oldState === "string" ? event.oldState : "",
              newState: typeof event.newState === "string" ? event.newState : "",
            };
            state.resolveFirstToggle();
          }
        };
        summary.addEventListener("click", state.clickListener, { once: true });
        item.addEventListener("toggle", state.toggleListener, { once: true });
        return state.boundBefore;
      },
      waitForToggleBoundary: async () => {
        await state.firstToggleBoundary;
        await new Promise((resolve) => {
          queueMicrotask(() => requestAnimationFrame(() => queueMicrotask(resolve)));
        });
      },
      snapshot,
      cleanup: () => {
        observer.disconnect();
        if (state.boundSummary && state.clickListener) {
          state.boundSummary.removeEventListener("click", state.clickListener);
        }
        if (state.boundItem && state.toggleListener) {
          state.boundItem.removeEventListener("toggle", state.toggleListener);
        }
      },
    };
  }, { expectedProcessKey: processKey });
}

async function clickExactOpenToolItemSummary(actionBoundary, itemNode, summaryNode) {

  let clickError = null;
  try {
    const boundBefore = await actionBoundary.evaluate((action, { item, summary }) => (
      action.bind(item, summary)
    ), { item: itemNode, summary: summaryNode });
    expect(boundBefore).toEqual({
      itemConnected: true,
      summaryConnected: true,
      directOwner: true,
      itemOpen: true,
      sameInitial: true,
      sameCurrent: true,
      currentGeneration: 1,
      replacementCount: 0,
    });
    await summaryNode.click();
    await actionBoundary.evaluate((action) => action.waitForToggleBoundary());
  } catch (error) {
    clickError = error;
  }
  let evidence;
  try {
    evidence = await actionBoundary.evaluate((action) => action.snapshot());
    await actionBoundary.evaluate((action) => action.cleanup());
  } finally {
    await actionBoundary.dispose();
  }
  if (clickError) {
    const error = new Error(`H4 exact tool summary click failed: ${JSON.stringify(evidence)}`);
    error.cause = clickError;
    throw error;
  }
  return evidence;
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
  await initialDom.outer.locator(":scope > summary.tool-process-stage-summary").click();
  await expect(initialDom.outer).toHaveAttribute("open", "");
  const projectionConvergence = await convergeToolProcessProjectionByLanguage(
    page,
    contract,
    initialDom,
  );
  const activeDom = projectionConvergence.dom;
  h4.diagnosticSteps.push({
    step: "failed-tool-projection-preconverged",
    ...projectionConvergence.evidence,
  });
  const oldStage = await activeDom.outer.elementHandle();
  expect(oldStage).not.toBeNull();
  const {
    itemNode: firstItemNode,
    summaryNode: firstSummaryNode,
  } = await connectedToolItemAndDirectSummary(activeDom.item);
  await activeDom.item.locator(":scope > summary").click();
  await expect(activeDom.item).toHaveAttribute("open", "");
  const {
    itemNode: openedItemNode,
    summaryNode: openedSummaryNode,
  } = await connectedToolItemAndDirectSummary(activeDom.item);
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
    await expect(activeDom.details.first()).toContainText(marker);
  }
  for (const marker of contract.domArgumentMarkers) {
    await expect(activeDom.details.first()).toContainText(marker);
  }
  for (const marker of contract.domResultMarkers) {
    await expect(activeDom.details.last()).toContainText(marker);
  }
  const collapseActionBoundary = await createToolItemCollapseActionBoundary(
    page,
    initialDom.projection.processKey,
  );
  const {
    itemNode: currentItemNode,
    summaryNode: currentSummaryNode,
  } = await connectedToolItemAndDirectSummary(activeDom.item);
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
  expect({
    openedItemConnectedBeforeSecond,
    currentIsOpenedItem,
    currentSummaryIsOpenedSummary,
    currentSummaryMatchesItem,
    currentOpenBeforeSecond,
  }).toEqual({
    openedItemConnectedBeforeSecond: true,
    currentIsOpenedItem: true,
    currentSummaryIsOpenedSummary: true,
    currentSummaryMatchesItem: true,
    currentOpenBeforeSecond: true,
  });
  const openSummary = activeDom.process.locator(
    "details.tool-process-item[open]:visible > summary",
  );
  await expect(openSummary).toHaveCount(1);
  const actionSummaryNode = await openSummary.elementHandle();
  expect(actionSummaryNode).not.toBeNull();
  expect(await currentSummaryNode.evaluate(
    (summary, actionSummary) => summary === actionSummary,
    actionSummaryNode,
  )).toBe(true);
  const collapseAction = await clickExactOpenToolItemSummary(
    collapseActionBoundary,
    currentItemNode,
    actionSummaryNode,
  );
  const {
    mutationCount: rootMutationCount,
    childListMutationCount: rootChildListMutationCount,
    ...collapseActionCausalEvidence
  } = collapseAction;
  expect(Number.isSafeInteger(rootMutationCount)).toBe(true);
  expect(Number.isSafeInteger(rootChildListMutationCount)).toBe(true);
  expect(rootChildListMutationCount).toBeGreaterThanOrEqual(0);
  expect(rootMutationCount).toBe(
    collapseAction.openMutationCount + rootChildListMutationCount,
  );
  expect(collapseActionCausalEvidence).toEqual({
    performed: true,
    generation: 1,
    initial: {
      generation: 1,
      itemConnected: true,
      summaryConnected: true,
      directOwner: true,
      itemOpen: true,
    },
    before: {
      itemConnected: true,
      summaryConnected: true,
      directOwner: true,
      itemOpen: true,
      sameInitial: true,
      sameCurrent: true,
      currentGeneration: 1,
      replacementCount: 0,
    },
    openMutationCount: 1,
    replacementCount: 0,
    clickCount: 1,
    toggleCount: 1,
    firstClick: {
      generation: 1,
      trusted: true,
      currentTargetIsSummary: true,
      summaryInPath: true,
      itemConnected: true,
      summaryConnected: true,
      directOwner: true,
      openAtClick: true,
    },
    firstToggle: {
      generation: 1,
      trusted: true,
      targetIsItem: true,
      itemConnected: true,
      summaryConnected: true,
      directOwner: true,
      openAtToggle: false,
      oldState: "open",
      newState: "closed",
    },
    after: {
      itemConnected: true,
      summaryConnected: true,
      directOwner: true,
      itemOpen: false,
      sameCurrent: true,
      currentGeneration: 1,
    },
  });
  const {
    itemNode: closedItemNode,
    summaryNode: closedSummaryNode,
  } = await connectedToolItemAndDirectSummary(activeDom.item);
  const currentOpenAfterSecond = await closedItemNode.evaluate((item) => item.open);
  const actionItemIsCurrentAfterSecond = await currentItemNode.evaluate(
    (item, current) => item === current,
    closedItemNode,
  );
  const actionSummaryIsCurrentAfterSecond = await currentSummaryNode.evaluate(
    (summary, current) => summary === current,
    closedSummaryNode,
  );
  if (collapseAction.performed) {
    expect(actionItemIsCurrentAfterSecond).toBe(true);
    expect(actionSummaryIsCurrentAfterSecond).toBe(true);
  }
  h4.diagnosticSteps.push({
    step: "failed-tool-item-second-click",
    projectionConvergence: projectionConvergence.evidence,
    openedItemConnectedBeforeSecond,
    currentIsOpenedItem,
    currentSummaryIsOpenedSummary,
    currentSummaryMatchesItem,
    currentOpenBeforeSecond,
    currentOpenAfterSecond,
    collapseAction,
    actionItemIsCurrentAfterSecond,
    actionSummaryIsCurrentAfterSecond,
    currentConnectedAfterSecond: await closedItemNode.evaluate((item) => item.isConnected),
    currentSummaryConnectedAfterSecond: await closedSummaryNode.evaluate((summary) => summary.isConnected),
  });
  expect(currentOpenAfterSecond).toBe(false);
  await expect(activeDom.item).not.toHaveAttribute("open", "");

  await h4.releaseGate(TOOL_FINAL_DELTA_GATE);
  await expect(activeDom.finalAnswer).toHaveCount(1);
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

function repeatedRangeActiveEventTypes(contract) {
  const eventTypes = ["created"];
  for (const result of contract.expectedResults) {
    eventTypes.push("model_started", "model_completed", "tool_started");
    if (result.retryBlocked) eventTypes.push("tool_retry_blocked");
    eventTypes.push("tool_completed", "model_pending");
  }
  eventTypes.push("model_started");
  return eventTypes;
}

function expectedContractOutcome(contract, index) {
  return contract.expectedOutcomes?.[index] || "failed";
}

const REPEATED_RANGE_ACTIVE_EVENT_TYPES = Object.freeze(
  repeatedRangeActiveEventTypes(REPEATED_RANGE_FAILURE_CONTRACT),
);
const REPEATED_RANGE_TERMINAL_EVENT_TYPES = Object.freeze([
  ...REPEATED_RANGE_ACTIVE_EVENT_TYPES,
  "model_completed",
  "completed",
]);

function repeatedFailureSessionRoleContentProjection(
  messages,
  contract = REPEATED_RANGE_FAILURE_CONTRACT,
) {
  return (Array.isArray(messages) ? messages : []).map((message) => {
    const role = String(message?.role || "");
    const content = String(message?.content || "");
    if (role === "user") {
      return { role, marker: content === contract.userMarker ? "user" : "unexpected" };
    }
    if (role === "assistant") {
      if (content === contract.stageMarker) return { role, marker: "stage" };
      if (content === contract.finalMarker) return { role, marker: "final" };
      return { role, marker: "tool-round", contentPresent: Boolean(content.trim()) };
    }
    if (role === "tool-call") {
      return {
        role,
        contentPresent: Boolean(content.trim()),
        pathPresent: content.includes(contract.arguments.path),
        startLinePresent: content.includes("startLine"),
        endLinePresent: content.includes("endLine"),
      };
    }
    if (role === "tool-result") {
      let result = {};
      try {
        result = JSON.parse(content);
      } catch {}
      return { role, result: contract.projectResult(result) };
    }
    return { role, contentPresent: Boolean(content.trim()) };
  });
}

function repeatedFailureSessionMetaProjection(
  messages,
  agentRunId,
  toolCallIds,
  contract = REPEATED_RANGE_FAILURE_CONTRACT,
) {
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
          ? contract.projectResult(meta.result)
          : null,
      };
    });
}

async function repeatedFailureLifecycleDomEvidence(
  page,
  contract = REPEATED_RANGE_FAILURE_CONTRACT,
) {
  const messages = page.locator("#messages");
  const user = messages.locator("article.msg.user").filter({ hasText: contract.userMarker });
  const commentary = messages.locator("article.msg.assistant.agent-commentary")
    .filter({ hasText: contract.stageMarker });
  const process = messages.locator("article.tool-process");
  const outer = process.locator("details.tool-process-stage");
  const items = process.locator("details.tool-process-item");
  const finalAnswer = messages.locator("article.msg.assistant")
    .filter({ hasText: contract.finalMarker });
  await expect(user).toHaveCount(1);
  await expect(commentary).toHaveCount(1);
  await expect(process).toHaveCount(1);
  await expect(outer).toHaveCount(1);
  await expect(items).toHaveCount(contract.expectedResults.length);
  const itemLocators = await items.all();
  const itemProjections = [];
  for (const [index, item] of itemLocators.entries()) {
    const expectedOutcome = expectedContractOutcome(contract, index);
    await expect(item).toHaveClass(new RegExp(`\\b${expectedOutcome}\\b`));
    const details = item.locator(".tool-process-detail pre");
    await expect(details).toHaveCount(2);
    const texts = await details.allTextContents();
    const argumentText = String(texts[0] || "").trim();
    const resultText = String(texts[1] || "").trim();
    const expectedArguments = contract.callArguments[index];
    const expectedResult = contract.expectedResults[index];
    const argumentProjection = {
      pathPresent: argumentText.includes(`"path": "${expectedArguments.path}"`),
      startLinePresent: argumentText.includes(`"startLine": ${expectedArguments.startLine}`),
      endLinePresent: argumentText.includes(`"endLine": ${expectedArguments.endLine}`),
    };
    if (contract.key === "H4-6L" || contract.key === "H4-6M") {
      argumentProjection.startLine = argumentProjection.startLinePresent
        ? expectedArguments.startLine
        : null;
      argumentProjection.endLine = argumentProjection.endLinePresent
        ? expectedArguments.endLine
        : null;
    }
    const resultProjection = {
      nonEmpty: Boolean(resultText),
      rangeFailureVisible: resultText.includes("startLine") && resultText.includes("endLine"),
      repeatedFailureBlockedVisible: (
        /exact tool call was blocked after 3 identical failures/i.test(resultText)
        && /do not repeat it/i.test(resultText)
      ),
    };
    if (contract.key === "H4-6M") {
      resultProjection.missingFileFailureVisible = resultText.includes("文件不存在");
    }
    if (contract.key === "H4-6N") {
      resultProjection.missingFileFailureVisible = resultText.includes("文件不存在");
      resultProjection.successContentVisible = (
        resultText.includes(SUCCESS_RESET_READ_PATH)
        && resultText.includes("26 B")
        && countOccurrences(resultText, FIXTURE_CONTENT.trim()) === 1
      );
    }
    const projection = {
      tool: index + 1,
      failed: String(await item.getAttribute("class") || "").split(/\s+/).includes("failed"),
      open: await item.evaluate((element) => element.open),
      arguments: argumentProjection,
      result: resultProjection,
    };
    if (contract.key === "H4-6N") {
      projection.succeeded = String(await item.getAttribute("class") || "")
        .split(/\s+/).includes("succeeded");
      expect(projection.arguments).toEqual({
        pathPresent: true,
        startLinePresent: false,
        endLinePresent: false,
      });
    } else {
      expect(projection.arguments).toMatchObject({
        pathPresent: true,
        startLinePresent: true,
        endLinePresent: true,
      });
    }
    const expectedResultProjection = {
      nonEmpty: true,
      rangeFailureVisible: Boolean(
        expectedResult.startLineMentioned && expectedResult.endLineMentioned
      ),
      repeatedFailureBlockedVisible: expectedResult.retryBlocked,
    };
    if (contract.key === "H4-6M") {
      expectedResultProjection.missingFileFailureVisible = expectedResult.missingFileError;
    }
    if (contract.key === "H4-6N") {
      expectedResultProjection.missingFileFailureVisible = expectedResult.missingFileError;
      expectedResultProjection.successContentVisible = expectedOutcome === "succeeded";
    }
    expect(projection.result).toEqual(expectedResultProjection);
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
    userMarker: contract.userMarker,
    stageMarker: contract.stageMarker,
    finalMarker: contract.finalMarker,
  });
  const projection = {
    sequence: finalCount
      ? [
        contract.userMarker,
        contract.stageMarker,
        contract.key === "H4-6N"
          ? `read_file:mixed:${contract.expectedResults.length}`
          : `read_file:failed:${contract.expectedResults.length}`,
        contract.finalMarker,
      ]
      : [
        contract.userMarker,
        contract.stageMarker,
        contract.key === "H4-6N"
          ? `read_file:mixed:${contract.expectedResults.length}`
          : `read_file:failed:${contract.expectedResults.length}`,
      ],
    counts: {
      user: 1,
      commentary: 1,
      toolProcess: 1,
      toolItem: contract.expectedResults.length,
      result: contract.expectedResults.length,
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

function expectedRepeatedModelReceipts(
  count,
  contract = REPEATED_RANGE_FAILURE_CONTRACT,
) {
  return contract.expectedResults.slice(0, count).map((result, index) => ({
    role: "tool",
    toolCallId: `tool-${index + 1}`,
    name: "read_file",
    ...result,
  }));
}

async function controlledFixtureAudit(h4, contract) {
  if (contract.key !== "H4-6M" && contract.key !== "H4-6N") return null;
  const projectRoot = path.resolve(h4.host.projectDir);
  const target = path.resolve(projectRoot, contract.arguments.path);
  expect(path.dirname(target)).toBe(projectRoot);
  expect(path.relative(projectRoot, target)).toBe(contract.arguments.path);
  let bytes = null;
  try {
    bytes = await fs.readFile(target);
  } catch (error) {
    expect(error?.code).toBe("ENOENT");
  }
  return {
    insideProject: true,
    exists: bytes != null,
    hashMatches: bytes != null && crypto.createHash("sha256").update(bytes).digest("hex")
      === FIXTURE_CONTENT_SHA256,
  };
}

function forcedFinalTerminalErrorMarker(contract) {
  return contract.terminalErrorMarker || PARALLEL_FAILURE_ERROR;
}

function forcedFinalFailureSessionProjection(messages, contract, agentRunId) {
  const source = Array.isArray(messages) ? messages : [];
  const errorMarker = forcedFinalTerminalErrorMarker(contract);
  expect(source.map((message) => message?.role)).toEqual(["user", "assistant"]);
  expect(source[0]?.content).toBe(contract.userMarker);
  expect(String(source[1]?.content || "")).toContain(errorMarker);
  expect(source[1]?.meta).toMatchObject({ kind: "error-recovery" });
  expect(String(source[1]?.meta?._model || "")).not.toBe("");
  expect(Object.prototype.hasOwnProperty.call(source[1], "_responseTime")).toBe(false);
  expect(String(source[1]?.meta?._responseTime || ""))
    .toMatch(/^\d+(?:s|m(?: \d+s)?|h(?: \d+m)?)$/);
  expect(source.some((message) => ["tool-call", "tool-result"].includes(message?.role))).toBe(false);
  return [
    { role: "user", marker: "user" },
    {
      role: "assistant",
      marker: "error-recovery",
      errorMarkerPresent: true,
      agentRunIdAbsent: !source[1]?.meta?.agentRunId,
      elapsedPresent: Boolean(String(source[1]?.meta?._responseTime || "").trim()),
    },
  ];
}

function forcedFinalFailureRunStateProjection(runState, contract, agentRunId) {
  const source = runState && typeof runState === "object" ? runState : {};
  const terminalNextCursor = contract.terminalNextCursor || 24;
  const errorMarker = forcedFinalTerminalErrorMarker(contract);
  expect(source).toMatchObject({
    status: "failed",
    phase: "model",
    executionOwner: "server-agent",
    agentRunId,
    agentEventCursor: terminalNextCursor,
    modelRound: 5,
  });
  expect(String(source.runtimeRunId || "")).toBe("");
  expect(String(source.lastError || "")).toContain(errorMarker);
  return {
    status: String(source.status || ""),
    phase: String(source.phase || ""),
    executionOwner: String(source.executionOwner || ""),
    agentRunLinked: String(source.agentRunId || "") === agentRunId,
    agentEventCursor: Number(source.agentEventCursor || 0),
    runtimeRunCleared: !String(source.runtimeRunId || ""),
    modelRound: Number(source.modelRound || 0),
    lastErrorPresent: Boolean(String(source.lastError || "").trim()),
  };
}

async function forcedFinalFailureDomEvidence(page, contract) {
  const messages = page.locator("#messages");
  const errorMarker = forcedFinalTerminalErrorMarker(contract);
  const user = messages.locator("article.msg.user").filter({ hasText: contract.userMarker });
  const errorAssistant = messages.locator("article.msg.assistant")
    .filter({ hasText: errorMarker });
  const successfulFinal = messages.locator("article.msg.assistant")
    .filter({ hasText: REPEATED_RANGE_FAILURE_FINAL });
  await expect(user).toHaveCount(1);
  await expect(errorAssistant).toHaveCount(1);
  await expect(successfulFinal).toHaveCount(0);
  await expect(messages.locator("article.msg.user")).toHaveCount(1);
  await expect(messages.locator("article.msg.assistant")).toHaveCount(1);
  await expect(messages.locator("article.tool-process")).toHaveCount(0);
  await expect(messages.locator(".execution-trace")).toHaveCount(0);
  const completedStatus = messages.locator("[data-completed-run-status]");
  const completedTimer = completedStatus.locator(".completed-run-timer");
  await expect(completedStatus).toHaveCount(1);
  await expect(completedStatus.locator(".completed-run-label")).toHaveText(/\S+/);
  await expect(completedTimer).toHaveText(/^\d+(?:s|m(?: \d+s)?|h(?: \d+m)?)$/);
  await expect(errorAssistant.locator(".response-info .run-time")).toHaveCount(0);
  await expect(messages.locator("article.msg.assistant .response-info .run-time")).toHaveCount(0);
  const ordered = await page.evaluate(({ userMarker, errorMarker }) => {
    const root = document.querySelector("#messages");
    const userNode = [...root.querySelectorAll("article.msg.user")]
      .find((element) => element.textContent.includes(userMarker));
    const errorNode = [...root.querySelectorAll("article.msg.assistant")]
      .find((element) => element.textContent.includes(errorMarker));
    return Boolean(
      userNode
      && errorNode
      && (userNode.compareDocumentPosition(errorNode) & Node.DOCUMENT_POSITION_FOLLOWING),
    );
  }, { userMarker: contract.userMarker, errorMarker });
  expect(ordered).toBe(true);
  const projection = {
    sequence: [contract.userMarker, "error-recovery"],
    counts: {
      user: 1,
      assistant: 1,
      errorRecovery: 1,
      toolProcess: 0,
      executionTrace: 0,
      completedStatus: 1,
      footerTimer: 0,
      successfulFinal: 0,
    },
    elapsedPresent: Boolean(String(await completedTimer.textContent() || "").trim()),
    errorMarkerPresent: true,
    ordered,
  };
  return { user, errorAssistant, projection, semanticHash: canonicalHash(projection) };
}

function activeForcedFinalDomProjection(dom) {
  return {
    sequence: dom.projection.sequence,
    counts: dom.projection.counts,
    processKeyPresent: Boolean(dom.projection.processKey),
    outerOpen: dom.projection.outerOpen,
    itemOpen: dom.projection.itemOpen,
    outerState: dom.projection.outerState,
    currentAction: dom.projection.currentAction,
    items: dom.projection.items,
    ordered: dom.projection.ordered,
  };
}

async function completeForcedFinalModelFailureTerminal(h4, runtime, contract, context) {
  const {
    page,
    requestBoundary,
    agentRunId,
    activeTrace,
    activeEventTypes,
    runtimeRunIds,
    initialDom,
    oldStage,
    expectedChatRequests,
    retryBlockedEvents,
  } = context;
  const unusableToolResponse = contract.terminalFailureKind === "unusable-tool-response";
  const terminalEventTypes = [
    ...activeEventTypes,
    ...(contract.terminalEventTail || ["failed"]),
  ];
  const terminalErrorCode = contract.terminalErrorCode || "upstream_error";
  const terminalErrorMarker = forcedFinalTerminalErrorMarker(contract);
  const terminalForceFinalRound = contract.terminalForceFinalRound ?? true;
  let failedAgent = null;
  await expect.poll(async () => {
    failedAgent = await fetchProductionJson(
      page,
      `/api/agent/runs/${encodeURIComponent(agentRunId)}?cursor=0&wait=0`,
    );
    return {
      status: failedAgent.body?.status,
      nextCursor: failedAgent.body?.nextCursor,
      activeRuntimeRunId: failedAgent.body?.activeRuntimeRunId,
      forceFinalRound: failedAgent.body?.forceFinalRound,
      errorCode: failedAgent.body?.errorCode,
      eventTypes: (failedAgent.body?.events || []).map((event) => event.type),
    };
  }).toEqual({
    status: "failed",
    nextCursor: terminalEventTypes.length,
    activeRuntimeRunId: "",
    forceFinalRound: terminalForceFinalRound,
    errorCode: terminalErrorCode,
    eventTypes: terminalEventTypes,
  });
  expect(failedAgent.status).toBe(200);
  expect(failedAgent.body.pendingToolCalls).toEqual([]);
  expect(String(failedAgent.body.error || "")).toContain(terminalErrorMarker);
  expect((failedAgent.body.events || []).filter((event) => event.type === "model_completed"))
    .toHaveLength(contract.expectedResults.length + (unusableToolResponse ? 1 : 0));
  const failedTrace = durableFailedToolTraceEvidence(failedAgent.body, contract);
  expect(failedTrace.executionProjection).toEqual(activeTrace.executionProjection);
  expect(failedTrace.toolCallIds).toEqual(activeTrace.toolCallIds);
  expect(failedTrace.terminalEventCount).toBe(1);
  expect(failedTrace.eventProjection.at(-1)).toEqual({
    seq: terminalEventTypes.length,
    type: "failed",
    errorCode: terminalErrorCode,
    errorPresent: true,
  });
  if (unusableToolResponse) {
    const finalModelEvent = failedTrace.eventProjection.at(-2);
    expect(finalModelEvent).toMatchObject({
      seq: terminalEventTypes.length - 1,
      type: "model_completed",
      round: 5,
      runtimeRunId: "runtime-5",
      finishReason: "tool_calls",
      toolCalls: [{
        toolCallId: "tool-5",
        name: "read_file",
        arguments: contract.arguments,
      }],
    });
    expect(failedTrace.eventProjection.filter((event) => (
      ["tool_started", "tool_completed", "tool_retry_blocked"].includes(event.type)
      && event.toolCallId === "tool-5"
    ))).toEqual([]);
  }

  await expect.poll(async () => oldStage.evaluate((element) => element.isConnected).catch(() => false))
    .toBe(false);
  await expect(page.locator("#activeRunBanner.visible")).toHaveCount(0);
  await expect(page.locator("#stopBtn")).toBeDisabled();
  await expect(page.locator("#messages .execution-trace.active")).toHaveCount(0);
  await expect(page.locator("#messages .execution-trace.completed")).toHaveCount(0);
  const terminalDom = await forcedFinalFailureDomEvidence(page, contract);

  const terminalRuntimeResponses = [];
  for (const runtimeRunId of runtimeRunIds) {
    const response = await fetchProductionJson(
      page,
      `/api/runtime/runs/${encodeURIComponent(runtimeRunId)}?cursor=0&wait=0`,
    );
    expect(response.status).toBe(200);
    terminalRuntimeResponses.push(response.body);
  }
  expect(terminalRuntimeResponses.slice(0, -1).map((snapshot) => snapshot.status))
    .toEqual(Array(contract.expectedResults.length).fill("completed"));
  const terminalRuntime = terminalRuntimeResponses.at(-1);
  if (unusableToolResponse) {
    expect(terminalRuntime).toMatchObject({
      runId: runtimeRunIds.at(-1),
      status: "completed",
      errorCode: "",
      transient: false,
      nextCursor: 3,
    });
    expect(terminalRuntime.events).toHaveLength(3);
    expect(terminalRuntime.result).toMatchObject({
      content: "",
      reasoning: "",
      finishReason: "tool_calls",
      toolCalls: [{
        id: contract.unusableToolCallId,
        type: "function",
        function: {
          name: "read_file",
          arguments: JSON.stringify(contract.arguments),
        },
      }],
    });
  } else {
    expect(terminalRuntime).toMatchObject({
      runId: runtimeRunIds.at(-1),
      status: "failed",
      errorCode: "upstream_error",
      transient: true,
      upstreamStatus: 502,
      nextCursor: 0,
      events: [],
    });
    expect(String(terminalRuntime.error || "")).toContain(PARALLEL_FAILURE_ERROR);
    expect(terminalRuntime.result).toMatchObject({ content: "", reasoning: "", toolCalls: [] });
  }
  const runtimeProjection = terminalRuntimeResponses.map((snapshot, index) => ({
    runtimeRunId: `runtime-${index + 1}`,
    status: String(snapshot.status || ""),
    nextCursor: Number(snapshot.nextCursor || 0),
    content: snapshot.result?.content === contract.stageMarker ? "stage" : "empty",
    ...(index === terminalRuntimeResponses.length - 1 && !unusableToolResponse ? {
      errorCode: String(snapshot.errorCode || ""),
      errorPresent: Boolean(String(snapshot.error || "").trim()),
      transient: snapshot.transient === true,
      upstreamStatus: Number(snapshot.upstreamStatus || 0),
      eventCount: (snapshot.events || []).length,
    } : {}),
    ...(index === terminalRuntimeResponses.length - 1 && unusableToolResponse ? {
      finishReason: String(snapshot.result?.finishReason || ""),
      toolCalls: (snapshot.result?.toolCalls || []).map((call) => ({
        toolCallId: call?.id === contract.unusableToolCallId ? "tool-5" : "unexpected",
        name: String(call?.function?.name || ""),
        arguments: parseToolArguments(call?.function?.arguments),
      })),
      eventCount: (snapshot.events || []).length,
    } : {}),
  }));
  if (contract.terminalRuntimeCursors) {
    expect(runtimeProjection.map((snapshot) => snapshot.nextCursor))
      .toEqual(contract.terminalRuntimeCursors);
  } else if (unusableToolResponse) {
    expect(runtimeProjection.slice(0, -1).map((snapshot) => snapshot.nextCursor))
      .toEqual([4, 3, 3, 3]);
    expect(runtimeProjection.at(-1).nextCursor).toBeGreaterThan(0);
  } else {
    expect(runtimeProjection.map((snapshot) => snapshot.nextCursor)).toEqual([4, 3, 3, 3, 0]);
  }

  const sessionButton = page.locator("#sessionList .session-row.active button.session-main");
  await expect(sessionButton).toHaveCount(1);
  const sessionId = await sessionButton.getAttribute("data-session-id");
  expect(sessionId).toBeTruthy();
  let sessionResponse = null;
  await expect.poll(async () => {
    sessionResponse = await fetchProductionJson(
      page,
      `/api/sessions/${encodeURIComponent(sessionId)}`,
    );
    return {
      roles: (sessionResponse.body?.messages || []).map((message) => message.role),
      status: sessionResponse.body?.runState?.status,
      agentEventCursor: sessionResponse.body?.runState?.agentEventCursor,
    };
  }).toEqual({
    roles: ["user", "assistant"],
    status: "failed",
    agentEventCursor: terminalEventTypes.length,
  });
  expect(sessionResponse.status).toBe(200);
  const sessionProjection = forcedFinalFailureSessionProjection(
    sessionResponse.body.messages,
    contract,
    agentRunId,
  );
  const sessionRunState = forcedFinalFailureRunStateProjection(
    sessionResponse.body.runState,
    contract,
    agentRunId,
  );

  const durable = await readDurableAgentRecord(h4, agentRunId);
  expect(durable.record).toMatchObject({
    status: "failed",
    nextSeq: terminalEventTypes.length + 1,
    forceFinalRound: terminalForceFinalRound,
    errorCode: terminalErrorCode,
    pendingToolCalls: [],
  });
  expect(Object.prototype.hasOwnProperty.call(durable.record, "activeRuntimeRunId")).toBe(false);
  expect(String(durable.record.error || "")).toContain(terminalErrorMarker);
  expect(durable.record.events).toHaveLength(terminalEventTypes.length);
  expect(Object.keys(durable.record.toolExecutions || {})).toEqual(activeTrace.toolCallIds);

  const metrics = await h4.metrics();
  expect(metrics.chatRequests).toEqual(expectedChatRequests);
  expect(metrics.productionToolDelegations).toBe(3);
  expect(metrics.toolExecutions).toEqual(contract.executedArguments.map((argumentsValue) => ({
    action: "read_file",
    ...argumentsValue,
  })));
  expect(metrics.unsafeToolRequests).toBe(0);
  const requests = h4.requestEvidenceSince(requestBoundary);
  expect(requests.agentPost).toBe(1);
  expect(requests.runtimePost).toBe(0);
  expect(requests.agentDelete).toBe(0);
  expect(h4.pageErrors).toEqual([]);

  const executionProjection = failedTrace.executionProjection;
  const modelToolReceiptProjection = expectedRepeatedModelReceipts(
    contract.expectedResults.length,
    contract,
  );
  const finalProjection = {
    modelRequestCount: metrics.chatRequests.length,
    scenario: metrics.chatRequests.at(-1)?.scenario,
    ...metrics.chatRequests.at(-1)?.[contract.finalMetric],
    parentStatus: String(failedAgent.body.status || ""),
    parentErrorCode: String(failedAgent.body.errorCode || ""),
    parentErrorPresent: Boolean(String(failedAgent.body.error || "").trim()),
    forceFinalRound: Boolean(failedAgent.body.forceFinalRound),
    pendingToolCallCount: failedAgent.body.pendingToolCalls.length,
    durableExecutionCount: failedTrace.executionProjection.length,
    retryBlockedEventCount: retryBlockedEvents.length,
    productionToolDelegations: metrics.productionToolDelegations,
    toolExecutionCount: metrics.toolExecutions.length,
    activeDom: activeForcedFinalDomProjection(initialDom),
    ...(unusableToolResponse ? {
      finalModelToolCalls: failedTrace.eventProjection.at(-2)?.toolCalls || [],
      unusableToolAbsentFromExecutions: !failedTrace.executionProjection.some(
        (execution) => execution.toolCallId === "tool-5",
      ),
      unusableToolAbsentFromToolEvents: !failedTrace.eventProjection.some((event) => (
        ["tool_started", "tool_completed", "tool_retry_blocked"].includes(event.type)
        && event.toolCallId === "tool-5"
      )),
      terminalRuntimeStatus: String(terminalRuntime.status || ""),
      terminalRuntimeCursor: Number(terminalRuntime.nextCursor || 0),
    } : {}),
  };
  const hashes = {
    eventProjection: failedTrace.eventProjectionHash,
    [contract.executionHashKey]: canonicalHash(executionProjection),
    modelToolReceiptProjection: canonicalHash(modelToolReceiptProjection),
    [contract.finalHashKey]: canonicalHash(finalProjection),
    runtimeProjection: canonicalHash(runtimeProjection),
    sessionRoleContent: canonicalHash(sessionProjection),
    sessionRunState: canonicalHash(sessionRunState),
    terminalDom: terminalDom.semanticHash,
  };
  if (Object.keys(contract.hashes).length) {
    for (const [key, value] of Object.entries(hashes)) {
      expect(value, `${contract.key} ${key}`).toBe(contract.hashes[key]);
    }
  }
  h4.evidence(`${runtime === "classic" ? "classic-" : ""}${contract.evidencePrefix}-terminal`, {
    identity: {
      agentRunId: idHash(agentRunId),
      toolCallIds: activeTrace.toolCallIds.map(idHash),
      runtimeRunIds: runtimeRunIds.map(idHash),
    },
    counts: {
      modelRequests: metrics.chatRequests.length,
      productionToolDelegations: metrics.productionToolDelegations,
      toolExecutions: metrics.toolExecutions.length,
      durableExecutions: failedTrace.executionProjection.length,
      retryBlockedEvents: retryBlockedEvents.length,
    },
    runtimeProjection,
    finalProjection,
    sessionRunState,
    hashes,
  });
  return {
    page,
    agentRunId,
    sessionId,
    toolCallIds: activeTrace.toolCallIds,
    runtimeRunIds,
    failedTrace,
    sessionProjection,
    sessionRunState,
    terminalDom,
    metrics,
    hashes,
    contract,
  };
}

async function completeRepeatedRangeFailureLifecycle(
  h4,
  runtime,
  contract = REPEATED_RANGE_FAILURE_CONTRACT,
) {
  const { page } = h4;
  const requestBoundary = h4.requestBoundary();
  await h4.open(runtime);
  await assertFrontendRuntime(page, runtime);
  if (runtime === "classic") await assertDirectClassicEntry(page);
  await h4.proveNonLoopbackBlocked();
  await h4.submitGated(contract.userMarker);
  const finalDeltaGate = await h4.waitGate(TOOL_FINAL_DELTA_GATE);
  expect(finalDeltaGate[TOOL_FINAL_DELTA_GATE]).toMatchObject({ reached: true, released: false });

  await expect.poll(() => h4.controlIds().agentRunIds.length).toBe(1);
  const agentRunId = h4.controlIds().agentRunIds[0];
  const activeAgent = await fetchProductionJson(
    page,
    `/api/agent/runs/${encodeURIComponent(agentRunId)}?cursor=0&wait=0`,
  );
  expect(activeAgent.status).toBe(200);
  const activeEventTypes = repeatedRangeActiveEventTypes(contract);
  const terminalEventTypes = contract.terminalStatus === "failed"
    ? [...activeEventTypes, "failed"]
    : [...activeEventTypes, "model_completed", "completed"];
  expect(activeAgent.body).toMatchObject({
    status: "model",
    nextCursor: activeEventTypes.length,
    forceFinalRound: contract.activeForceFinalRound,
    errorCode: "",
    pendingToolCalls: [],
  });
  expect((activeAgent.body.events || []).map((event) => event.type))
    .toEqual(activeEventTypes);
  const activeTrace = durableFailedToolTraceEvidence(
    activeAgent.body,
    contract,
  );
  expect(activeTrace.toolCallIds).toHaveLength(contract.expectedResults.length);
  expect(new Set(activeTrace.toolCallIds).size).toBe(contract.expectedResults.length);
  expect(activeTrace.executionProjection).toEqual(contract.expectedResults.map((result, index) => ({
    toolCallId: `tool-${index + 1}`,
    name: "read_file",
    arguments: contract.callArguments[index],
    status: "completed",
    outcome: expectedContractOutcome(contract, index),
    result,
  })));
  const modelCompletedWithTools = activeTrace.eventProjection.filter((event) => (
    event.type === "model_completed" && Array.isArray(event.toolCalls) && event.toolCalls.length
  ));
  expect(modelCompletedWithTools).toHaveLength(contract.expectedResults.length);
  expect(modelCompletedWithTools.map((event) => event.toolCalls[0])).toEqual(
    contract.expectedResults.map((_, index) => ({
      toolCallId: `tool-${index + 1}`,
      name: "read_file",
      arguments: contract.callArguments[index],
    })),
  );
  const startedEvents = activeTrace.eventProjection.filter((event) => event.type === "tool_started");
  const completedEvents = activeTrace.eventProjection.filter((event) => event.type === "tool_completed");
  expect(startedEvents).toHaveLength(contract.expectedResults.length);
  expect(completedEvents).toHaveLength(contract.expectedResults.length);
  for (const [index, event] of startedEvents.entries()) {
    expect(event).toMatchObject({
      toolCallId: `tool-${index + 1}`,
      name: "read_file",
      arguments: contract.callArguments[index],
    });
  }
  for (const [index, event] of completedEvents.entries()) {
    expect(event).toMatchObject({
      toolCallId: `tool-${index + 1}`,
      name: "read_file",
      outcome: expectedContractOutcome(contract, index),
      result: contract.expectedResults[index],
    });
  }
  const retryBlockedEvents = activeTrace.eventProjection.filter((event) => event.type === "tool_retry_blocked");
  expect(retryBlockedEvents).toEqual(contract.expectedRetryBlockedEvents);

  const modelStartedEvents = activeAgent.body.events.filter((event) => event?.type === "model_started");
  expect(modelStartedEvents).toHaveLength(contract.expectedResults.length + 1);
  const runtimeRunIds = modelStartedEvents.map((event) => String(event?.data?.runtimeRunId || ""));
  expect(runtimeRunIds.every(Boolean)).toBe(true);
  expect(new Set(runtimeRunIds).size).toBe(contract.expectedResults.length + 1);
  expect(activeAgent.body.activeRuntimeRunId).toBe(runtimeRunIds.at(-1));
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
  expect(activeRuntimeResponses.slice(0, -1).map((snapshot) => snapshot.status))
    .toEqual(Array(contract.expectedResults.length).fill("completed"));
  expect(activeRuntimeResponses.at(-1).status).toBe("running");
  expect(activeRuntimeResponses.at(-1).events).toEqual([]);
  expect(activeRuntimeResponses.at(-1).result?.content).toBe("");
  expect(activeRuntimeResponses[0].result?.content).toBe(contract.stageMarker);
  expect(activeRuntimeResponses.slice(1, -1).map((snapshot) => snapshot.result?.content || ""))
    .toEqual(Array(Math.max(0, contract.expectedResults.length - 1)).fill(""));

  const metricsActive = await h4.metrics();
  const expectedChatRequests = contract.expectedResults.map((_, index) => ({
    scenario: `${contract.scenarioPrefix}-call-${index + 1}`,
    stream: true,
    hasToolResult: index > 0,
    [contract.receiptMetric]: expectedRepeatedModelReceipts(index, contract),
  }));
  expectedChatRequests.push({
    scenario: `${contract.scenarioPrefix}-final`,
    stream: true,
    hasToolResult: true,
    [contract.receiptMetric]: expectedRepeatedModelReceipts(contract.expectedResults.length, contract),
    [contract.finalMetric]: contract.finalMetricExpected,
  });
  expect(metricsActive.chatRequests).toEqual(expectedChatRequests);
  expect(metricsActive.productionToolDelegations).toBe(3);
  expect(metricsActive.toolExecutions).toEqual(contract.executedArguments.map((argumentsValue) => ({
    action: "read_file",
    ...argumentsValue,
  })));
  expect(metricsActive.unsafeToolRequests).toBe(0);

  const process = page.locator("#messages article.tool-process");
  await expect(process).toHaveCount(1);
  await expect(process.locator("details.tool-process-item")).toHaveCount(contract.expectedResults.length);
  await expect(process.locator("details.tool-process-item.failed")).toHaveCount(
    contract.expectedResults.filter((_, index) => (
      expectedContractOutcome(contract, index) === "failed"
    )).length,
  );
  await expect(process.locator("details.tool-process-item.succeeded")).toHaveCount(
    contract.expectedResults.filter((_, index) => (
      expectedContractOutcome(contract, index) === "succeeded"
    )).length,
  );
  const initialDom = await repeatedFailureLifecycleDomEvidence(page, contract);
  expect(initialDom.projection).toMatchObject({
    counts: {
      user: 1,
      commentary: 1,
      toolProcess: 1,
      toolItem: contract.expectedResults.length,
      result: contract.expectedResults.length,
      final: 0,
      ordinaryAssistant: 1,
      assistantTotal: 2,
    },
    outerOpen: false,
    itemOpen: Array(contract.expectedResults.length).fill(false),
    outerState: { running: true, failed: false },
    currentAction: "read_file",
    ordered: true,
  });
  expect(initialDom.projection.processKey).not.toBe("");
  const oldStage = await initialDom.outer.elementHandle();
  await initialDom.outer.locator(":scope > summary.tool-process-stage-summary").click();
  await expect(initialDom.outer).toHaveAttribute("open", "");

  await h4.releaseGate(TOOL_FINAL_DELTA_GATE);
  if (contract.terminalStatus === "failed") {
    return completeForcedFinalModelFailureTerminal(h4, runtime, contract, {
      page,
      requestBoundary,
      agentRunId,
      activeTrace,
      activeEventTypes,
      runtimeRunIds,
      initialDom,
      oldStage,
      expectedChatRequests,
      retryBlockedEvents,
    });
  }
  await expect(initialDom.finalAnswer).toHaveCount(1);
  const terminalGate = await h4.waitGate(TOOL_TERMINAL_GATE);
  expect(terminalGate[TOOL_TERMINAL_GATE]).toMatchObject({ reached: true, released: false });
  expect(await oldStage.evaluate((element) => element.isConnected)).toBe(false);
  const afterFinalDeltaDom = await repeatedFailureLifecycleDomEvidence(page, contract);
  expect(afterFinalDeltaDom.projection.processKey).toBe(initialDom.projection.processKey);
  expect(afterFinalDeltaDom.projection.outerOpen).toBe(true);
  expect(afterFinalDeltaDom.projection.itemOpen)
    .toEqual(Array(contract.expectedResults.length).fill(false));
  expect(afterFinalDeltaDom.projection.outerState).toEqual({ running: false, failed: true });
  expect(afterFinalDeltaDom.projection.counts).toMatchObject({
    user: 1,
    commentary: 1,
    toolProcess: 1,
    toolItem: contract.expectedResults.length,
    result: contract.expectedResults.length,
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
    nextCursor: terminalEventTypes.length,
    activeRuntimeRunId: "",
    forceFinalRound: false,
    errorCode: "",
    eventTypes: terminalEventTypes,
  });
  expect(completedAgent.status).toBe(200);
  expect(completedAgent.body.pendingToolCalls).toEqual([]);
  const completedTrace = durableFailedToolTraceEvidence(
    completedAgent.body,
    contract,
  );
  expect(completedTrace.executionProjection).toEqual(activeTrace.executionProjection);
  expect(completedTrace.terminalEventCount).toBe(1);
  await expect(page.locator("#activeRunBanner.visible")).toHaveCount(0);
  await expect(page.locator("#stopBtn")).toBeDisabled();
  await expect(page.locator("#messages .execution-trace.active")).toHaveCount(0);
  await expect(page.locator("#messages .execution-trace.completed")).toHaveCount(1);

  const terminalDom = await repeatedFailureLifecycleDomEvidence(page, contract);
  expect(terminalDom.projection.processKey).toBe(initialDom.projection.processKey);
  expect(terminalDom.projection.outerOpen).toBe(false);
  expect(terminalDom.projection.itemOpen)
    .toEqual(Array(contract.expectedResults.length).fill(false));
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
    .toEqual([
      contract.stageMarker,
      ...Array(Math.max(0, contract.expectedResults.length - 1)).fill(""),
      contract.finalMarker,
    ]);
  const runtimeProjection = terminalRuntimeResponses.map((snapshot, index) => ({
    runtimeRunId: `runtime-${index + 1}`,
    status: String(snapshot.status || ""),
    nextCursor: Number(snapshot.nextCursor || 0),
    content: snapshot.result?.content === contract.stageMarker
      ? "stage"
      : (snapshot.result?.content === contract.finalMarker ? "final" : "empty"),
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
  const expectedSessionRoles = ["user"];
  for (let index = 0; index < contract.expectedResults.length; index += 1) {
    expectedSessionRoles.push("assistant", "tool-call", "tool-result");
  }
  expectedSessionRoles.push("assistant");
  expect((sessionResponse.body.messages || []).map((message) => message.role))
    .toEqual(expectedSessionRoles);
  const sessionProjection = repeatedFailureSessionRoleContentProjection(
    sessionResponse.body.messages,
    contract,
  );
  const sessionToolMeta = repeatedFailureSessionMetaProjection(
    sessionResponse.body.messages,
    agentRunId,
    activeTrace.toolCallIds,
    contract,
  );
  expect(sessionToolMeta).toHaveLength(contract.expectedResults.length * 2);
  for (let index = 0; index < contract.expectedResults.length; index += 1) {
    expect(sessionToolMeta[index * 2]).toMatchObject({
      role: "tool-call",
      toolCallId: `tool-${index + 1}`,
      agentRunId: "agent-1",
      agentEventType: "tool_started",
      action: "read_file",
      arguments: contract.callArguments[index],
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
      outcome: expectedContractOutcome(contract, index),
      result: contract.expectedResults[index],
    });
    expect(sessionToolMeta[index * 2].agentEventSeq).toBe(startedEvents[index].seq);
    expect(sessionToolMeta[index * 2 + 1].agentEventSeq).toBe(completedEvents[index].seq);
  }

  const durable = await readDurableAgentRecord(h4, agentRunId);
  expect(durable.record).toMatchObject({
    status: "completed",
    nextSeq: terminalEventTypes.length + 1,
    forceFinalRound: false,
    pendingToolCalls: [],
  });
  expect(durable.record.events).toHaveLength(terminalEventTypes.length);
  expect(Object.keys(durable.record.toolExecutions || {})).toEqual(activeTrace.toolCallIds);
  for (const [index, toolCallId] of activeTrace.toolCallIds.entries()) {
    expect(contract.projectResult(durable.record.toolExecutions[toolCallId]?.result))
      .toEqual(contract.expectedResults[index]);
  }
  const durableExecutions = activeTrace.toolCallIds.map((toolCallId) => (
    durable.record.toolExecutions[toolCallId]
  ));
  let failureIdentityProjection = null;
  if (contract.key === "H4-6L") {
    const fingerprints = durableExecutions.map((execution) => String(execution?.fingerprint || ""));
    const failureSignatures = durableExecutions.map((execution) => (
      String(execution?.failureSignature || "")
    ));
    expect(fingerprints.every(Boolean)).toBe(true);
    expect(fingerprints[0]).toBe(fingerprints[2]);
    expect(fingerprints[1]).not.toBe(fingerprints[0]);
    expect(failureSignatures.every(Boolean)).toBe(true);
    expect(new Set(failureSignatures).size).toBe(1);
    failureIdentityProjection = {
      arguments: contract.callArguments.map((argumentsValue) => ({
        path: argumentsValue.path,
        startLine: argumentsValue.startLine,
        endLine: argumentsValue.endLine,
      })),
      fingerprintPattern: ["A", "B", "A"],
      firstAndThirdFingerprintEqual: fingerprints[0] === fingerprints[2],
      secondFingerprintIndependent: fingerprints[1] !== fingerprints[0],
      failureSignatureStable: new Set(failureSignatures).size === 1,
      failureCounts: contract.expectedResults.map((result) => result.failureCount),
      retryLimitReached: contract.expectedResults.map((result) => result.retryLimitReached),
      retryBlocked: contract.expectedResults.map((result) => result.retryBlocked),
    };
  }

  const metrics = await h4.metrics();
  expect(metrics).toMatchObject({
    productionToolDelegations: 3,
    unsafeToolRequests: 0,
  });
  expect(metrics.chatRequests).toEqual(expectedChatRequests);
  expect(metrics.toolExecutions).toHaveLength(3);
  const signatureFixtureAudit = await controlledFixtureAudit(h4, contract);
  if (contract.key === "H4-6M") {
    const fingerprints = durableExecutions.map((execution) => String(execution?.fingerprint || ""));
    const failureSignatures = durableExecutions.map((execution) => (
      String(execution?.failureSignature || "")
    ));
    expect(fingerprints.every(Boolean)).toBe(true);
    expect(new Set(fingerprints).size).toBe(1);
    expect(failureSignatures.every(Boolean)).toBe(true);
    expect(failureSignatures[0]).toBe(failureSignatures[2]);
    expect(failureSignatures[1]).not.toBe(failureSignatures[0]);
    expect(durableExecutions.map((execution) => parseToolArguments(execution?.arguments)))
      .toEqual(contract.callArguments);
    const fixtureTimeline = [
      {
        callNumber: 1,
        expectedState: "present",
        observedState: "present",
        exists: true,
        hashMatches: true,
        delegationCount: 1,
        executionCount: 1,
      },
      {
        callNumber: 2,
        expectedState: "missing",
        observedState: "missing",
        exists: false,
        hashMatches: false,
        delegationCount: 2,
        executionCount: 2,
      },
      {
        callNumber: 3,
        expectedState: "present",
        observedState: "present",
        exists: true,
        hashMatches: true,
        delegationCount: 3,
        executionCount: 3,
      },
    ];
    expect(metrics.signatureAlternationFixtureTimeline).toEqual(fixtureTimeline);
    expect(signatureFixtureAudit).toEqual({ insideProject: true, exists: true, hashMatches: true });
    failureIdentityProjection = {
      canonicalArguments: contract.callArguments.map((argumentsValue) => ({
        path: argumentsValue.path,
        startLine: argumentsValue.startLine,
        endLine: argumentsValue.endLine,
      })),
      fingerprintPattern: ["A", "A", "A"],
      fingerprintStable: new Set(fingerprints).size === 1,
      failureSignaturePattern: ["A", "B", "A"],
      firstAndThirdSignatureEqual: failureSignatures[0] === failureSignatures[2],
      middleSignatureIndependent: failureSignatures[1] !== failureSignatures[0],
      failureCounts: contract.expectedResults.map((result) => result.failureCount),
      retryLimitReached: contract.expectedResults.map((result) => result.retryLimitReached),
      retryBlocked: contract.expectedResults.map((result) => result.retryBlocked),
      fixtureStates: fixtureTimeline,
      fixtureRestored: signatureFixtureAudit,
    };
  }
  if (contract.key === "H4-6N") {
    const fingerprints = durableExecutions.map((execution) => String(execution?.fingerprint || ""));
    const failureSignaturePresent = durableExecutions.map((execution) => (
      Object.prototype.hasOwnProperty.call(execution || {}, "failureSignature")
    ));
    const failureSignatures = durableExecutions.map((execution) => (
      String(execution?.failureSignature || "")
    ));
    expect(fingerprints.every(Boolean)).toBe(true);
    expect(new Set(fingerprints).size).toBe(1);
    expect(durableExecutions.map((execution) => String(execution?.outcome || "")))
      .toEqual(["failed", "succeeded", "failed"]);
    expect(failureSignaturePresent).toEqual([true, false, true]);
    expect(failureSignatures[0]).not.toBe("");
    expect(failureSignatures[0]).toBe(failureSignatures[2]);
    const successFailureCountAbsent = (
      !Object.prototype.hasOwnProperty.call(durableExecutions[1] || {}, "failureCount")
      && !Object.prototype.hasOwnProperty.call(
        durableExecutions[1]?.result || {},
        "failureCount",
      )
    );
    expect(successFailureCountAbsent).toBe(true);
    expect(durableExecutions.map((execution) => parseToolArguments(execution?.arguments)))
      .toEqual(contract.callArguments);
    const fixtureTimeline = [
      {
        callNumber: 1,
        expectedState: "missing",
        observedState: "missing",
        exists: false,
        hashMatches: false,
        delegationCount: 1,
        executionCount: 1,
      },
      {
        callNumber: 2,
        expectedState: "present",
        observedState: "present",
        exists: true,
        hashMatches: true,
        delegationCount: 2,
        executionCount: 2,
      },
      {
        callNumber: 3,
        expectedState: "missing",
        observedState: "missing",
        exists: false,
        hashMatches: false,
        delegationCount: 3,
        executionCount: 3,
      },
    ];
    expect(metrics.successResetFixtureTimeline).toEqual(fixtureTimeline);
    expect(signatureFixtureAudit).toEqual({ insideProject: true, exists: false, hashMatches: false });
    failureIdentityProjection = {
      canonicalArguments: contract.callArguments.map((argumentsValue) => ({
        path: argumentsValue.path,
      })),
      fingerprintPattern: ["A", "A", "A"],
      fingerprintStable: new Set(fingerprints).size === 1,
      outcomePattern: ["failed", "succeeded", "failed"],
      failureSignaturePattern: ["A", "absent", "A"],
      firstAndThirdSignatureEqual: failureSignatures[0] === failureSignatures[2],
      successSignatureAbsent: !failureSignaturePresent[1],
      failureCountPattern: [1, "absent", 1],
      successFailureCountAbsent,
      retryLimitReached: contract.expectedResults.map((result) => result.retryLimitReached),
      retryBlocked: contract.expectedResults.map((result) => result.retryBlocked),
      fixtureStates: fixtureTimeline,
      fixtureMissingAfterFinal: signatureFixtureAudit,
    };
  }
  const requests = h4.requestEvidenceSince(requestBoundary);
  expect(requests.agentPost).toBe(1);
  expect(requests.runtimePost).toBe(0);
  expect(requests.agentDelete).toBe(0);
  expect(h4.pageErrors).toEqual([]);

  const executionProjection = completedTrace.executionProjection;
  const executionHashProjection = failureIdentityProjection == null
    ? executionProjection
    : { executions: executionProjection, identity: failureIdentityProjection };
  const modelToolReceiptProjection = expectedRepeatedModelReceipts(
    contract.expectedResults.length,
    contract,
  );
  const finalProjection = {
    modelRequestCount: metrics.chatRequests.length,
    scenario: metrics.chatRequests.at(-1)?.scenario,
    ...metrics.chatRequests.at(-1)?.[contract.finalMetric],
    parentStatus: completedAgent.body.status,
    parentErrorCode: String(completedAgent.body.errorCode || ""),
    forceFinalRound: Boolean(completedAgent.body.forceFinalRound),
    pendingToolCallCount: completedAgent.body.pendingToolCalls.length,
  };
  const hashes = {
    eventProjection: completedTrace.eventProjectionHash,
    [contract.executionHashKey]: canonicalHash(executionHashProjection),
    modelToolReceiptProjection: canonicalHash(modelToolReceiptProjection),
    [contract.finalHashKey]: canonicalHash(finalProjection),
    runtimeProjection: canonicalHash(runtimeProjection),
    sessionRoleContent: canonicalHash(sessionProjection),
    sessionToolMeta: canonicalHash(sessionToolMeta),
    terminalDom: terminalDom.semanticHash,
  };
  if (Object.keys(contract.hashes).length) {
    for (const [key, value] of Object.entries(hashes)) {
      expect(value, `${contract.key} ${key}`).toBe(contract.hashes[key]);
    }
  }
  h4.evidence(`${runtime === "classic" ? "classic-" : ""}${contract.evidencePrefix}-terminal`, {
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
    finalProjection,
    failureIdentityProjection,
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
    failureIdentityProjection,
    signatureFixtureAudit,
    hashes,
    contract,
  };
}

async function exerciseForcedFinalModelFailureRefresh(h4, runtime, before) {
  const refreshBoundary = h4.requestBoundary();
  const metricsBefore = await h4.metrics();
  await h4.reloadRuntime(runtime);
  if (runtime === "classic") await assertDirectClassicEntry(before.page);
  const persistedSession = before.page.locator(
    `#sessionList button.session-main[data-session-id="${before.sessionId}"]`,
  );
  await expect(persistedSession).toHaveCount(1);
  await persistedSession.click();
  await expect(before.page.locator("#activeRunBanner.visible")).toHaveCount(0);
  await expect(before.page.locator("#stopBtn")).toBeDisabled();
  await expect(before.page.locator("#messages .execution-trace")).toHaveCount(0);
  const domAfter = await forcedFinalFailureDomEvidence(before.page, before.contract);
  expect(domAfter.projection).toEqual(before.terminalDom.projection);

  const agentAfter = await fetchProductionJson(
    before.page,
    `/api/agent/runs/${encodeURIComponent(before.agentRunId)}?cursor=0&wait=0`,
  );
  expect(agentAfter.status).toBe(200);
  const failedTraceAfter = durableFailedToolTraceEvidence(agentAfter.body, before.contract);
  expect(failedTraceAfter).toEqual(before.failedTrace);
  expect(failedTraceAfter.toolCallIds).toEqual(before.toolCallIds);
  const sessionAfter = await fetchProductionJson(
    before.page,
    `/api/sessions/${encodeURIComponent(before.sessionId)}`,
  );
  expect(sessionAfter.status).toBe(200);
  const sessionProjectionAfter = forcedFinalFailureSessionProjection(
    sessionAfter.body.messages,
    before.contract,
    before.agentRunId,
  );
  const sessionRunStateAfter = forcedFinalFailureRunStateProjection(
    sessionAfter.body.runState,
    before.contract,
    before.agentRunId,
  );
  expect(sessionProjectionAfter).toEqual(before.sessionProjection);
  expect(sessionRunStateAfter).toEqual(before.sessionRunState);
  for (const runtimeRunId of before.runtimeRunIds) {
    const runtimeAfter = await fetchProductionJson(
      before.page,
      `/api/runtime/runs/${encodeURIComponent(runtimeRunId)}?cursor=0&wait=0`,
    );
    expect(runtimeAfter.status).toBe(200);
  }

  const metricsAfter = await h4.metrics();
  expect(metricsAfter.chatRequests).toEqual(metricsBefore.chatRequests);
  expect(metricsAfter.toolExecutions).toEqual(metricsBefore.toolExecutions);
  expect(metricsAfter.productionToolDelegations).toBe(3);
  expect(metricsAfter.unsafeToolRequests).toBe(0);
  const refreshRequests = h4.requestEvidenceSince(refreshBoundary);
  const refreshSummary = h4.requestSummarySince(refreshBoundary);
  expect(refreshRequests.agentPost).toBe(0);
  expect(refreshRequests.runtimePost).toBe(0);
  expect(refreshRequests.agentDelete).toBe(0);
  expect(refreshSummary["POST /proxy/chat"] || 0).toBe(0);
  expect(Object.entries(refreshSummary).filter(([key]) => key.startsWith("POST /api/tools/")))
    .toEqual([]);
  expect(h4.controlIds()).toEqual({
    agentRunIds: [before.agentRunId],
    runtimeRunIds: before.runtimeRunIds,
  });
  expect(h4.pageErrors).toEqual([]);
  const refreshProjection = {
    agentRunStable: failedTraceAfter.agentRunId === before.failedTrace.agentRunId,
    toolCallsStable: JSON.stringify(failedTraceAfter.toolCallIdHashes)
      === JSON.stringify(before.failedTrace.toolCallIdHashes),
    eventProjectionStable: failedTraceAfter.eventProjectionHash
      === before.failedTrace.eventProjectionHash,
    sessionProjectionStable: JSON.stringify(sessionProjectionAfter)
      === JSON.stringify(before.sessionProjection),
    sessionRunStateStable: JSON.stringify(sessionRunStateAfter)
      === JSON.stringify(before.sessionRunState),
    terminalDomStable: JSON.stringify(domAfter.projection)
      === JSON.stringify(before.terminalDom.projection),
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
  if (Object.keys(before.contract.hashes).length) {
    expect(hashes).toEqual(before.contract.hashes);
  }
  h4.evidence(`${runtime === "classic" ? "classic-" : ""}${before.contract.evidencePrefix}-refresh`, {
    identity: {
      agentRunId: idHash(before.agentRunId),
      toolCallIds: before.toolCallIds.map(idHash),
    },
    refresh: refreshProjection,
    hashes,
  });
}

async function exerciseRepeatedRangeFailureTerminalRefresh(
  h4,
  runtime,
  contract = REPEATED_RANGE_FAILURE_CONTRACT,
) {
  const before = await completeRepeatedRangeFailureLifecycle(h4, runtime, contract);
  if (contract.terminalStatus === "failed") {
    await exerciseForcedFinalModelFailureRefresh(h4, runtime, before);
    return;
  }
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
  const domAfter = await repeatedFailureLifecycleDomEvidence(before.page, contract);
  expect(domAfter.projection).toEqual(before.terminalDom.projection);
  expect(domAfter.projection.outerOpen).toBe(false);
  expect(domAfter.projection.itemOpen)
    .toEqual(Array(contract.expectedResults.length).fill(false));
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
    contract,
  );
  expect(completedTraceAfter).toEqual(before.completedTrace);
  expect(completedTraceAfter.toolCallIds).toEqual(before.toolCallIds);
  const sessionAfter = await fetchProductionJson(
    before.page,
    `/api/sessions/${encodeURIComponent(before.sessionId)}`,
  );
  expect(sessionAfter.status).toBe(200);
  const sessionProjectionAfter = repeatedFailureSessionRoleContentProjection(
    sessionAfter.body.messages,
    contract,
  );
  const sessionToolMetaAfter = repeatedFailureSessionMetaProjection(
    sessionAfter.body.messages,
    before.agentRunId,
    before.toolCallIds,
    contract,
  );
  expect(sessionProjectionAfter).toEqual(before.sessionProjection);
  expect(sessionToolMetaAfter).toEqual(before.sessionToolMeta);
  const metricsAfter = await h4.metrics();
  expect(metricsAfter.chatRequests).toEqual(metricsBefore.chatRequests);
  expect(metricsAfter.toolExecutions).toEqual(metricsBefore.toolExecutions);
  expect(metricsAfter.productionToolDelegations).toBe(contract.executedArguments.length);
  expect(metricsAfter.unsafeToolRequests).toBe(0);
  const signatureFixtureAuditAfter = await controlledFixtureAudit(h4, contract);
  if (contract.key === "H4-6M") {
    expect(metricsAfter.signatureAlternationFixtureTimeline)
      .toEqual(metricsBefore.signatureAlternationFixtureTimeline);
    expect(signatureFixtureAuditAfter).toEqual(before.signatureFixtureAudit);
  }
  if (contract.key === "H4-6N") {
    expect(metricsAfter.successResetFixtureTimeline)
      .toEqual(metricsBefore.successResetFixtureTimeline);
    expect(signatureFixtureAuditAfter).toEqual(before.signatureFixtureAudit);
  }
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
  if (contract.key === "H4-6M") {
    refreshProjection.signatureFixtureStable = (
      JSON.stringify(signatureFixtureAuditAfter) === JSON.stringify(before.signatureFixtureAudit)
    );
  }
  if (contract.key === "H4-6N") {
    refreshProjection.successResetFixtureStable = (
      JSON.stringify(signatureFixtureAuditAfter) === JSON.stringify(before.signatureFixtureAudit)
    );
  }
  const hashes = {
    ...before.hashes,
    refreshLifecycle: canonicalHash(refreshProjection),
  };
  if (Object.keys(contract.hashes).length) {
    expect(hashes).toEqual(contract.hashes);
  }
  h4.evidence(`${runtime === "classic" ? "classic-" : ""}${contract.evidencePrefix}-refresh`, {
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

test("bundle forced-final model failure rolls back uniquely without replay", async ({ h4 }) => {
  await exerciseRepeatedRangeFailureTerminalRefresh(
    h4,
    "bundle",
    FORCED_FINAL_MODEL_FAILURE_CONTRACT,
  );
});

test("direct classic forced-final model failure rolls back uniquely without replay", async ({ h4 }) => {
  await exerciseRepeatedRangeFailureTerminalRefresh(
    h4,
    "classic",
    FORCED_FINAL_MODEL_FAILURE_CONTRACT,
  );
});

test("bundle forced-final unusable tool response fails without execution and reloads uniquely", async ({ h4 }) => {
  await exerciseRepeatedRangeFailureTerminalRefresh(
    h4,
    "bundle",
    FORCED_FINAL_UNUSABLE_TOOL_CONTRACT,
  );
});

test("direct classic forced-final unusable tool response fails without execution and reloads uniquely", async ({ h4 }) => {
  await exerciseRepeatedRangeFailureTerminalRefresh(
    h4,
    "classic",
    FORCED_FINAL_UNUSABLE_TOOL_CONTRACT,
  );
});

test("bundle alternating read_file arguments isolate failure counts and reload uniquely", async ({ h4 }) => {
  await exerciseRepeatedRangeFailureTerminalRefresh(
    h4,
    "bundle",
    ARGUMENT_ISOLATION_FAILURE_CONTRACT,
  );
});

test("direct classic alternating read_file arguments isolate failure counts and reload uniquely", async ({ h4 }) => {
  await exerciseRepeatedRangeFailureTerminalRefresh(
    h4,
    "classic",
    ARGUMENT_ISOLATION_FAILURE_CONTRACT,
  );
});

test("bundle identical read_file fingerprint alternates failure signatures and reloads uniquely", async ({ h4 }) => {
  await exerciseRepeatedRangeFailureTerminalRefresh(
    h4,
    "bundle",
    SIGNATURE_ALTERNATION_FAILURE_CONTRACT,
  );
});

test("direct classic identical read_file fingerprint alternates failure signatures and reloads uniquely", async ({ h4 }) => {
  await exerciseRepeatedRangeFailureTerminalRefresh(
    h4,
    "classic",
    SIGNATURE_ALTERNATION_FAILURE_CONTRACT,
  );
});

test("bundle identical read_file failure chain resets after success and reloads uniquely", async ({ h4 }) => {
  await exerciseRepeatedRangeFailureTerminalRefresh(
    h4,
    "bundle",
    SUCCESS_RESET_FAILURE_CONTRACT,
  );
});

test("direct classic identical read_file failure chain resets after success and reloads uniquely", async ({ h4 }) => {
  await exerciseRepeatedRangeFailureTerminalRefresh(
    h4,
    "classic",
    SUCCESS_RESET_FAILURE_CONTRACT,
  );
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

  await initialDom.outer.locator(":scope > summary.tool-process-stage-summary").click();
  await expect(initialDom.outer).toHaveAttribute("open", "");
  const openedKey = await initialDom.outer.getAttribute("data-tool-process-key");
  expect(openedKey).toBe(initialDom.projection.processKey);

  await h4.releaseGate(SECOND_TOOL_EXECUTE_GATE);
  const finalDeltaGate = await h4.waitGate(TOOL_FINAL_DELTA_GATE);
  expect(finalDeltaGate[TOOL_FINAL_DELTA_GATE]).toMatchObject({ reached: true, released: false });
  await expect(secondActiveItem).toHaveClass(/\bsucceeded\b/);
  await expect(secondActiveDetails).toHaveCount(2);
  await expect(secondActiveDetails.nth(1)).toContainText(FIXTURE_CONTENT.trim());
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
