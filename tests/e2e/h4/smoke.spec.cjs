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
const H4_7C_SEMANTIC_HASHES = Object.freeze({
  mainToolTrace: "6599ebee8ff79520ee51e2fa2fe2011ce6237091791282c02f6b5525092223c4",
  backgroundAgent: "1319a246751c8daa8c6546cfe1b8f2aab159bb00a11b01f908b5d20c7f414545",
  backgroundRuntime: "6b71bc4b26a681050327da18905949caaa9ae806dd78747dc9708bba1a5f76d1",
  sessionRoleContent: "9846dc82c8e7a82b181c41ee23ecc25b0ac6bf25df1fe0564e5fea8b605e9ab7",
  backgroundMeta: "e26b1c4a7e1a70f87ab60335fcd655331a2601f2a7dd6882e63821d2eb8d5baa",
  domOwnership: "0c317c7fffaaa70a224e2193072f71dfaac66f64f5f5b755d918abcca106d584",
  requestCounts: "e90926ff643c4cff6ab16720a27dedbd1b5f4561b874e7bbe4ef7d3e63eaba1e",
  refreshLifecycle: "0cb60f329ee95fbe0953c4712394e8aa085b7c83a13680c2ec444b8d1ce37681",
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
  h4.diagnosticSteps.push({
    step: "tiff-full-refresh-preview-requests",
    preRefreshGeneration,
    expectedReloadGeneration,
    requests: fullRefreshPreviewRequests.map((request) => ({ ...request })),
  });
  expect(fullRefreshPreviewRequests).toHaveLength(1);
  expect(fullRefreshPreviewRequests[0]).toMatchObject({
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
) {
  const source = Array.isArray(messages) ? messages : [];
  const roleContent = roleContentProjection(source);
  expect(roleContent.map((message) => message.role)).toEqual([
    "user",
    "assistant",
    "tool-call",
    "tool-result",
    "user",
    "assistant",
    "assistant",
  ]);
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
  expect(roleContent[4].content).toBe(PARALLEL_FAILURE_USER);
  expect(roleContent[5].content).toBe(PARALLEL_FAILURE_ERROR);
  expect(roleContent[6].content).toBe(TOOL_DETAILS_FINAL);

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

async function detachedParallelFailureDomEvidence(
  page,
  { finalVisible = false, terminal = false, tracePlacement = "" } = {},
) {
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
  const expectedTracePlacement = tracePlacement || (terminal ? "persistent" : "outside");
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

  const ordered = await page.evaluate((markers) => {
    const root = document.querySelector("#messages");
    const find = (selector, marker) => [...root.querySelectorAll(selector)]
      .find((element) => (element.textContent || "").includes(marker));
    const nodes = [
      find("article.msg.user", markers.mainUser),
      find("article.msg.assistant.agent-commentary", markers.mainStage),
      root.querySelector("article.tool-process"),
    ];
    const final = find("article.msg.assistant", markers.mainFinal);
    const detached = [
      find("article.msg.user", markers.backgroundUser),
      find("article.msg.assistant", markers.backgroundError),
    ];
    if (markers.terminal) {
      nodes.push(...detached);
      if (final) nodes.push(final);
    } else {
      if (final) nodes.push(final);
      nodes.push(...detached);
    }
    return nodes.every(Boolean) && nodes.slice(0, -1).every((node, index) => (
      Boolean(node.compareDocumentPosition(nodes[index + 1]) & Node.DOCUMENT_POSITION_FOLLOWING)
    ));
  }, {
    mainUser: TOOL_DETAILS_USER,
    mainStage: TOOL_DETAILS_STAGE,
    backgroundUser: PARALLEL_FAILURE_USER,
    backgroundError: PARALLEL_FAILURE_ERROR,
    mainFinal: TOOL_DETAILS_FINAL,
    terminal,
  });
  expect(ordered).toBe(true);

  return {
    toolDom,
    backgroundUser,
    backgroundAssistant,
    mainFinal,
    projection: {
      terminal,
      finalVisible,
      ordered,
      counts: {
        mainUser: await mainUser.count(),
        mainStage: await mainStage.count(),
        mainFinal: await mainFinal.count(),
        backgroundUser: await backgroundUser.count(),
        backgroundAssistant: await backgroundAssistant.count(),
        toolProcesses: await messages.locator("article.tool-process").count(),
        toolItems: await messages.locator("article.tool-process details.tool-process-item").count(),
        toolResults: await messages.locator("article.tool-process .tool-process-detail pre").count() - 1,
        completedStatuses: await messages.locator("[data-completed-run-status]").count(),
        primaryFooterTimers: terminal
          ? await mainFinal.locator(".response-info .run-time").count()
          : 0,
        backgroundFooterTimers: await backgroundAssistant
          .locator(".response-info .run-time").count(),
        backgroundReferences: await backgroundAssistant.locator("[data-background-reply-id]").count(),
      },
      processKey: toolDom.projection.processKey,
      toolOuterOpen: toolDom.projection.outerOpen,
      toolStage: toolDom.projection.stageClass.split(/\s+/).filter(Boolean).sort(),
      backgroundTracePlacement: {
        userPersistent: await backgroundUser.evaluate((element) => (
          element.classList.contains("execution-trace-persistent")
        )),
        assistantPersistent: await backgroundAssistant.evaluate((element) => (
          element.classList.contains("execution-trace-persistent")
        )),
        userTraceAncestors: await backgroundUser.locator(
          "xpath=ancestor::*[contains(concat(' ',normalize-space(@class),' '),' execution-trace ')]",
        ).count(),
        assistantTraceAncestors: await backgroundAssistant.locator(
          "xpath=ancestor::*[contains(concat(' ',normalize-space(@class),' '),' execution-trace ')]",
        ).count(),
      },
      backgroundOwnsCompletedStatus: false,
      backgroundInsideToolProcess: false,
    },
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

  const activeDom = await detachedParallelFailureDomEvidence(page);
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
  const preTerminalDom = await detachedParallelFailureDomEvidence(page, {
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
  const terminalDom = await detachedParallelFailureDomEvidence(page, {
    finalVisible: true,
    terminal: true,
  });
  expect(terminalDom.toolDom.projection.processKey).toBe(processKey);
  expect(terminalDom.toolDom.projection.outerOpen).toBe(false);
  expect(terminalDom.toolDom.projection.itemOpen).toBe(false);
  expect(terminalDom.toolDom.projection.stageClass.split(/\s+/)).toContain("succeeded");

  const terminalSession = await fetchProductionJson(
    page,
    `/api/sessions/${encodeURIComponent(sessionId)}`,
  );
  expect(terminalSession.status).toBe(200);
  expect(Array.isArray(terminalSession.body.runState?.backgroundRuns)
    ? terminalSession.body.runState.backgroundRuns
    : []).toEqual([]);
  const sessionEvidence = detachedParallelFailureSessionEvidence(
    terminalSession.body.messages,
    mainAgentRunId,
    backgroundAgentRunId,
    toolCallId,
  );

  const metricsBeforeReload = await h4.metrics();
  expect(metricsBeforeReload.chatRequests).toEqual([
    { scenario: "tool-detail-call", stream: true, hasToolResult: false },
    { scenario: "tool-detail-final", stream: true, hasToolResult: true },
    { scenario: "parallel-model-failure", stream: true, hasToolResult: false },
  ]);
  expect(metricsBeforeReload.toolExecutions).toEqual([
    { action: "read_file", path: "fixture.txt" },
  ]);
  expect(metricsBeforeReload.productionToolDelegations).toBe(1);
  expect(metricsBeforeReload.unsafeToolRequests).toBe(0);
  const requestsBeforeReload = h4.requestEvidenceSince(requestBoundary);
  expect(requestsBeforeReload.agentPost).toBe(2);
  expect(requestsBeforeReload.runtimePost).toBe(0);
  expect(requestsBeforeReload.agentDelete).toBe(0);

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
  const requestProjection = {
    agentRunPost: requestsBeforeReload.agentPost,
    runtimePost: requestsBeforeReload.runtimePost,
    chat: metricsBeforeReload.chatRequests.length,
    toolExecutions: metricsBeforeReload.toolExecutions.length,
    backgroundToolExecutions: 0,
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
  const restoredDom = await detachedParallelFailureDomEvidence(page, {
    finalVisible: true,
    terminal: true,
  });
  expect(restoredDom.projection).toEqual(terminalDom.projection);
  expect(restoredDom.toolDom.projection.processKey).toBe(processKey);

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
  expect(mainAfterReload.status).toBe(200);
  expect(backgroundAfterReload.status).toBe(200);
  expect(backgroundRuntimeAfterReload.status).toBe(200);
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

  const sessionAfterReload = await fetchProductionJson(
    page,
    `/api/sessions/${encodeURIComponent(sessionId)}`,
  );
  expect(sessionAfterReload.status).toBe(200);
  expect(Array.isArray(sessionAfterReload.body.runState?.backgroundRuns)
    ? sessionAfterReload.body.runState.backgroundRuns
    : []).toEqual([]);
  const restoredSessionEvidence = detachedParallelFailureSessionEvidence(
    sessionAfterReload.body.messages,
    mainAgentRunId,
    backgroundAgentRunId,
    toolCallId,
  );
  expect(restoredSessionEvidence.roleContent).toEqual(sessionEvidence.roleContent);
  expect(restoredSessionEvidence.backgroundMeta).toEqual(sessionEvidence.backgroundMeta);

  const metricsAfterReload = await h4.metrics();
  expect(metricsAfterReload.chatRequests).toEqual(metricsBeforeReload.chatRequests);
  expect(metricsAfterReload.toolExecutions).toEqual(metricsBeforeReload.toolExecutions);
  const refreshRequests = h4.requestEvidenceSince(refreshBoundary);
  const refreshSummary = h4.requestSummarySince(refreshBoundary);
  expect(refreshRequests.agentPost).toBe(0);
  expect(refreshRequests.runtimePost).toBe(0);
  expect(refreshRequests.agentDelete).toBe(0);
  expect(refreshSummary["POST /proxy/chat"] || 0).toBe(0);
  expect(Object.entries(refreshSummary).filter(([key]) => key.startsWith("POST /api/tools/")))
    .toEqual([]);
  expect(h4.controlIds().agentRunIds).toEqual([mainAgentRunId, backgroundAgentRunId]);
  expect(h4.pageErrors).toEqual([]);

  const refreshProjection = {
    mainAgentStable: mainAfterReload.body.agentRunId === mainAgentRunId,
    backgroundAgentStable: backgroundAfterReload.body.agentRunId === backgroundAgentRunId,
    backgroundRuntimeStable: backgroundRuntimeAfterReload.body.runId === backgroundRuntimeRunId,
    processKeyStable: restoredDom.toolDom.projection.processKey === processKey,
    sessionRoleContentStable: JSON.stringify(restoredSessionEvidence.roleContent)
      === JSON.stringify(sessionEvidence.roleContent),
    backgroundMetaStable: JSON.stringify(restoredSessionEvidence.backgroundMeta)
      === JSON.stringify(sessionEvidence.backgroundMeta),
    backgroundCheckpointCount: Array.isArray(sessionAfterReload.body.runState?.backgroundRuns)
      ? sessionAfterReload.body.runState.backgroundRuns.length
      : 0,
    domUnique: restoredDom.projection,
    requests: {
      agentRunPost: refreshRequests.agentPost,
      runtimePost: refreshRequests.runtimePost,
      chat: metricsAfterReload.chatRequests.length - metricsBeforeReload.chatRequests.length,
      toolExecutions: metricsAfterReload.toolExecutions.length - metricsBeforeReload.toolExecutions.length,
    },
  };
  const hashes = {
    mainToolTrace: canonicalHash(mainToolProjection),
    backgroundAgent: canonicalHash(backgroundAgentProjection),
    backgroundRuntime: canonicalHash(backgroundRuntimeProjection),
    sessionRoleContent: canonicalHash(sessionEvidence.roleContent),
    backgroundMeta: canonicalHash(sessionEvidence.backgroundMeta),
    domOwnership: canonicalHash(terminalDom.projection),
    requestCounts: canonicalHash(requestProjection),
    refreshLifecycle: canonicalHash(refreshProjection),
  };
  expect(hashes).toEqual(H4_7C_SEMANTIC_HASHES);
  h4.evidence(`${runtime}-detached-parallel-failure-isolation`, {
    runtime,
    identities: {
      mainAgentRunId: idHash(mainAgentRunId),
      backgroundAgentRunId: idHash(backgroundAgentRunId),
      backgroundRuntimeRunId: idHash(backgroundRuntimeRunId),
      toolCallId: idHash(toolCallId),
      jobId: idHash(sessionEvidence.jobId),
    },
    eventTypes: {
      main: completedMainAgent.body.events.map((event) => event.type),
      background: failedBackgroundAgent.body.events.map((event) => event.type),
    },
    runtime: backgroundRuntimeProjection,
    requests: requestProjection,
    refresh: refreshProjection.requests,
    dom: terminalDom.projection,
    hashes,
  });
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
  const {
    itemNode: firstItemNode,
    summaryNode: firstSummaryNode,
  } = await connectedToolItemAndDirectSummary(initialDom.item);
  await initialDom.item.locator(":scope > summary").click();
  await expect(initialDom.item).toHaveAttribute("open", "");
  const {
    itemNode: openedItemNode,
    summaryNode: openedSummaryNode,
  } = await connectedToolItemAndDirectSummary(initialDom.item);
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
  const {
    itemNode: currentItemNode,
    summaryNode: currentSummaryNode,
  } = await connectedToolItemAndDirectSummary(initialDom.item);
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
    await initialDom.item.locator(":scope > summary").click();
  } else {
    expect(openedItemConnectedBeforeSecond).toBe(false);
    expect(currentIsOpenedItem).toBe(false);
  }
  const {
    itemNode: closedItemNode,
    summaryNode: closedSummaryNode,
  } = await connectedToolItemAndDirectSummary(initialDom.item);
  const currentOpenAfterSecond = await closedItemNode.evaluate((item) => item.open);
  h4.diagnosticSteps.push({
    step: "failed-tool-item-second-click",
    openedItemConnectedBeforeSecond,
    currentIsOpenedItem,
    currentSummaryIsOpenedSummary,
    currentSummaryMatchesItem,
    currentOpenBeforeSecond,
    currentOpenAfterSecond,
    currentConnectedAfterSecond: await closedItemNode.evaluate((item) => item.isConnected),
    currentSummaryConnectedAfterSecond: await closedSummaryNode.evaluate((summary) => summary.isConnected),
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

function forcedFinalFailureSessionProjection(messages, contract, agentRunId) {
  const source = Array.isArray(messages) ? messages : [];
  expect(source.map((message) => message?.role)).toEqual(["user", "assistant"]);
  expect(source[0]?.content).toBe(contract.userMarker);
  expect(String(source[1]?.content || "")).toContain(PARALLEL_FAILURE_ERROR);
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

function forcedFinalFailureRunStateProjection(runState, agentRunId, runtimeRunIds) {
  const source = runState && typeof runState === "object" ? runState : {};
  expect(source).toMatchObject({
    status: "failed",
    phase: "model",
    executionOwner: "server-agent",
    agentRunId,
    agentEventCursor: 24,
    modelRound: 5,
  });
  expect(String(source.runtimeRunId || "")).toBe("");
  expect(String(source.lastError || "")).toContain(PARALLEL_FAILURE_ERROR);
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
  const user = messages.locator("article.msg.user").filter({ hasText: contract.userMarker });
  const errorAssistant = messages.locator("article.msg.assistant")
    .filter({ hasText: PARALLEL_FAILURE_ERROR });
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
  }, { userMarker: contract.userMarker, errorMarker: PARALLEL_FAILURE_ERROR });
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
  const terminalEventTypes = [...activeEventTypes, "failed"];
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
    forceFinalRound: true,
    errorCode: "upstream_error",
    eventTypes: terminalEventTypes,
  });
  expect(failedAgent.status).toBe(200);
  expect(failedAgent.body.pendingToolCalls).toEqual([]);
  expect(String(failedAgent.body.error || "")).toContain(PARALLEL_FAILURE_ERROR);
  expect((failedAgent.body.events || []).filter((event) => event.type === "model_completed"))
    .toHaveLength(contract.expectedResults.length);
  const failedTrace = durableFailedToolTraceEvidence(failedAgent.body, contract);
  expect(failedTrace.executionProjection).toEqual(activeTrace.executionProjection);
  expect(failedTrace.terminalEventCount).toBe(1);
  expect(failedTrace.eventProjection.at(-1)).toEqual({
    seq: terminalEventTypes.length,
    type: "failed",
    errorCode: "upstream_error",
    errorPresent: true,
  });

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
  const failedRuntime = terminalRuntimeResponses.at(-1);
  expect(failedRuntime).toMatchObject({
    runId: runtimeRunIds.at(-1),
    status: "failed",
    errorCode: "upstream_error",
    transient: true,
    upstreamStatus: 502,
    nextCursor: 0,
    events: [],
  });
  expect(String(failedRuntime.error || "")).toContain(PARALLEL_FAILURE_ERROR);
  expect(failedRuntime.result).toMatchObject({ content: "", reasoning: "", toolCalls: [] });
  const runtimeProjection = terminalRuntimeResponses.map((snapshot, index) => ({
    runtimeRunId: `runtime-${index + 1}`,
    status: String(snapshot.status || ""),
    nextCursor: Number(snapshot.nextCursor || 0),
    content: snapshot.result?.content === contract.stageMarker ? "stage" : "empty",
    ...(index === terminalRuntimeResponses.length - 1 ? {
      errorCode: String(snapshot.errorCode || ""),
      errorPresent: Boolean(String(snapshot.error || "").trim()),
      transient: snapshot.transient === true,
      upstreamStatus: Number(snapshot.upstreamStatus || 0),
      eventCount: (snapshot.events || []).length,
    } : {}),
  }));
  expect(runtimeProjection.map((snapshot) => snapshot.nextCursor)).toEqual([4, 3, 3, 3, 0]);

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
  }).toEqual({ roles: ["user", "assistant"], status: "failed", agentEventCursor: 24 });
  expect(sessionResponse.status).toBe(200);
  const sessionProjection = forcedFinalFailureSessionProjection(
    sessionResponse.body.messages,
    contract,
    agentRunId,
  );
  const sessionRunState = forcedFinalFailureRunStateProjection(
    sessionResponse.body.runState,
    agentRunId,
    runtimeRunIds,
  );

  const durable = await readDurableAgentRecord(h4, agentRunId);
  expect(durable.record).toMatchObject({
    status: "failed",
    nextSeq: terminalEventTypes.length + 1,
    forceFinalRound: true,
    errorCode: "upstream_error",
    pendingToolCalls: [],
  });
  expect(Object.prototype.hasOwnProperty.call(durable.record, "activeRuntimeRunId")).toBe(false);
  expect(String(durable.record.error || "")).toContain(PARALLEL_FAILURE_ERROR);
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
    before.agentRunId,
    before.runtimeRunIds,
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
