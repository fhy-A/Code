"""H3-2D1 seven-format production-chain image MIME evidence."""

import base64
import hashlib
import html
import io
import json
import re
import subprocess
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest import mock

from jsonschema import Draft202012Validator, FormatChecker
from PIL import Image

import server as server_mod


ROOT = Path(__file__).resolve().parent.parent
FIXTURE_DIR = ROOT / "tests" / "fixtures" / "harness"
SCHEMA_PATH = FIXTURE_DIR / "image-mime-preservation-evidence.schema.json"
FIXTURE_PATH = FIXTURE_DIR / "image-mime-preservation-evidence.json"
EXPECTED_FIXTURE_SHA256 = "8f3cdd6354987a977df545f5db1209e5f869924b01d8884c9e1b33784c5afad3"
PNG_SIGNATURE = bytes.fromhex("89504e470d0a1a0a")

EXPECTED_PROFILE = {
    "id": "h3-2d1-image-mime-preservation",
    "version": 1,
    "scope": "seven-format-production-chain",
    "caseOrder": ["png", "jpeg", "webp", "bmp", "gif", "ico", "tiff"],
    "passthroughCaseIds": ["png", "jpeg", "webp"],
    "convertedCaseIds": ["bmp", "gif", "ico", "tiff"],
}
EXPECTED_CASE_MATRIX = [
    {
        "id": "png",
        "format": "PNG",
        "mime": "image/png",
        "projectionKind": "passthrough",
        "framePolicy": "single-image",
    },
    {
        "id": "jpeg",
        "format": "JPEG",
        "mime": "image/jpeg",
        "projectionKind": "passthrough",
        "framePolicy": "single-image",
    },
    {
        "id": "webp",
        "format": "WEBP",
        "mime": "image/webp",
        "projectionKind": "passthrough",
        "framePolicy": "single-image",
    },
    {
        "id": "bmp",
        "format": "BMP",
        "mime": "image/bmp",
        "projectionKind": "convert-to-png",
        "framePolicy": "single-image",
    },
    {
        "id": "gif",
        "format": "GIF",
        "mime": "image/gif",
        "projectionKind": "convert-to-png",
        "framePolicy": "first-frame-only",
    },
    {
        "id": "ico",
        "format": "ICO",
        "mime": "image/x-icon",
        "projectionKind": "convert-to-png",
        "framePolicy": "single-size-only",
    },
    {
        "id": "tiff",
        "format": "TIFF",
        "mime": "image/tiff",
        "projectionKind": "convert-to-png",
        "framePolicy": "first-frame-only",
    },
]


SERIALIZE_SCRIPT = r"""
const fs = require("fs");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
let fetchCalls = 0;
global.fetch = () => {
  fetchCalls += 1;
  throw new Error("network access is forbidden in H3-2D1");
};
global.window = {Code: {services: {}}};
require("./src/services/persistence.js");
const {serializeSessionMessages, buildSessionSavePayload} = window.Code.services.persistence;
const sourceBefore = JSON.stringify(input.messages);
const serialized = serializeSessionMessages(input.messages, input.options);
const repeated = serializeSessionMessages(input.messages, input.options);
const savePayload = buildSessionSavePayload({
  title: "Synthetic seven-format evidence",
  stats: {},
  lastUsage: null,
  runState: {},
  persistMessages: true,
  messages: input.messages,
});
process.stdout.write(JSON.stringify({
  serialized,
  repeated,
  saveMessages: savePayload.messages,
  sourceUnchanged: sourceBefore === JSON.stringify(input.messages),
  fetchCalls,
}));
"""


UI_SCRIPT = r"""
const fs = require("fs");
const input = JSON.parse(fs.readFileSync(0, "utf8"));
let fetchCalls = 0;
global.fetch = () => {
  fetchCalls += 1;
  throw new Error("network access is forbidden in H3-2D1");
};
global.window = {Code: {ui: {}}};
require("./src/ui/messages.js");
const {createMessagesFeature} = window.Code.ui.messages;
const escapeHtml = (value) => String(value ?? "")
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;");
const feature = createMessagesFeature({
  escapeHtml,
  renderMarkdown: (value) => `<md>${escapeHtml(value)}</md>`,
  t: (key) => key,
  getMessageText: (message) => String(message?.content || ""),
});
const sourceBefore = JSON.stringify(input.messages);
const projections = input.messages.map((message, index) => {
  const renderUserHtml = feature.renderUserProjection(message, index);
  const repeatedRenderUserHtml = feature.renderUserProjection(message, index);
  const projectMessagesHtml = feature.projectMessages([message], {hasActiveRun: false});
  const repeatedProjectMessagesHtml = feature.projectMessages([message], {hasActiveRun: false});
  return {
    caseId: message.meta.evidenceCaseId,
    renderUserHtml,
    repeatedRenderUserHtml,
    projectMessagesHtml,
    repeatedProjectMessagesHtml,
    sourceImageCount: message._images.length,
  };
});
process.stdout.write(JSON.stringify({
  projections,
  sourceUnchanged: sourceBefore === JSON.stringify(input.messages),
  fetchCalls,
}));
"""


def canonical_hash(value):
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def text_hash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class EvidenceContractError(AssertionError):
    def __init__(self, path, expected, actual):
        super().__init__(f"{path}: expected {expected!r}, got {actual!r}")
        self.path = path
        self.expected = expected
        self.actual = actual


def first_difference(actual, expected, path):
    if type(actual) is not type(expected):
        return path, expected, actual
    if isinstance(expected, dict):
        for key in expected:
            child_path = f"{path}.{key}"
            if key not in actual:
                return child_path, expected[key], "<missing>"
            difference = first_difference(actual[key], expected[key], child_path)
            if difference:
                return difference
        for key in actual:
            if key not in expected:
                return f"{path}.{key}", "<absent>", actual[key]
        return None
    if isinstance(expected, list):
        for index, expected_item in enumerate(expected):
            child_path = f"{path}[{index}]"
            if index >= len(actual):
                return child_path, expected_item, "<missing>"
            difference = first_difference(actual[index], expected_item, child_path)
            if difference:
                return difference
        if len(actual) > len(expected):
            return f"{path}[{len(expected)}]", "<absent>", actual[len(expected)]
        return None
    if actual != expected:
        return path, expected, actual
    return None


def require_match(actual, expected, path):
    difference = first_difference(actual, expected, path)
    if difference:
        raise EvidenceContractError(*difference)


def load_fixture():
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def run_node(script, payload):
    completed = subprocess.run(
        ["node", "-e", script],
        cwd=ROOT,
        input=json.dumps(payload, ensure_ascii=False),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return json.loads(completed.stdout)


def case_matrix(fixture):
    return [
        {
            "id": case["id"],
            "format": case["source"]["format"],
            "mime": case["source"]["mime"],
            "projectionKind": case["projectionKind"],
            "framePolicy": case["framePolicy"],
        }
        for case in fixture["cases"]
    ]


def validate_profile_and_matrix(fixture):
    require_match(fixture["evidenceProfile"], EXPECTED_PROFILE, "$.evidenceProfile")
    require_match(case_matrix(fixture), EXPECTED_CASE_MATRIX, "$.cases")


def decode_selected_rgba(raw):
    try:
        with Image.open(io.BytesIO(raw)) as image:
            frame_count = int(getattr(image, "n_frames", 1))
            image.seek(0)
            selected = image.convert("RGBA")
            size = selected.size
            rgba = selected.tobytes()
            detected_format = str(image.format or "").upper()
    except Exception as exc:
        raise EvidenceContractError("$.source.decode", "valid image", str(exc)) from exc
    return {
        "frameCount": frame_count,
        "width": size[0],
        "height": size[1],
        "rgba": rgba,
        "rgbaSha256": hashlib.sha256(rgba).hexdigest(),
        "pilFormat": detected_format,
    }


def validate_source_contract(case, index):
    path = f"$.cases[{index}]"
    source = case["source"]
    message = case["sourceMessage"]
    images = message["_images"]
    if len(images) != 1:
        raise EvidenceContractError(f"{path}.sourceMessage._images", 1, len(images))
    image = images[0]
    if image["mime"] != source["mime"]:
        raise EvidenceContractError(
            f"{path}.sourceMessage._images[0].mime",
            source["mime"],
            image["mime"],
        )
    if image["name"] != source["fileName"]:
        raise EvidenceContractError(
            f"{path}.sourceMessage._images[0].name",
            source["fileName"],
            image["name"],
        )
    if message["meta"]["evidenceCaseId"] != case["id"]:
        raise EvidenceContractError(
            f"{path}.sourceMessage.meta.evidenceCaseId",
            case["id"],
            message["meta"]["evidenceCaseId"],
        )
    expected_url = f"data:{source['mime']};base64,{image['base64']}"
    actual_url = message["content"][1]["image_url"]["url"]
    if actual_url != expected_url:
        raise EvidenceContractError(
            f"{path}.sourceMessage.content[1].image_url.url",
            expected_url,
            actual_url,
        )
    raw = base64.b64decode(image["base64"], validate=True)
    detected_format, detected_mime = server_mod._sniff_model_image_format(raw)
    if detected_format != source["format"] or detected_mime != source["mime"]:
        raise EvidenceContractError(
            f"{path}.sourceMessage._images[0].base64",
            {"format": source["format"], "mime": source["mime"]},
            {"format": detected_format, "mime": detected_mime},
        )
    if len(raw) != source["byteLength"]:
        raise EvidenceContractError(
            f"{path}.source.byteLength",
            len(raw),
            source["byteLength"],
        )
    digest = hashlib.sha256(raw).hexdigest()
    if digest != source["sha256"]:
        raise EvidenceContractError(f"{path}.source.sha256", digest, source["sha256"])
    decoded = decode_selected_rgba(raw)
    expected_decoded = {
        "frameCount": source["frameCount"],
        "width": source["selectedWidth"],
        "height": source["selectedHeight"],
        "rgbaSha256": source["selectedFrameRgbaSha256"],
        "pilFormat": source["format"],
    }
    actual_decoded = {key: decoded[key] for key in expected_decoded}
    require_match(actual_decoded, expected_decoded, f"{path}.source")
    return {
        "raw": raw,
        "dataUrl": actual_url,
        "decoded": decoded,
    }


def extract_single_image_src(rendered_html, path):
    sources = re.findall(r'<img\b[^>]*\bsrc="([^"]+)"', rendered_html)
    if len(sources) != 1:
        raise EvidenceContractError(path, 1, len(sources))
    return html.unescape(sources[0])


def validate_round_trip_identity(case, message, source_fact, index):
    path = f"$.cases[{index}].roundTrip"
    actual_case_id = message.get("meta", {}).get("evidenceCaseId")
    if actual_case_id != case["id"]:
        raise EvidenceContractError(f"{path}.caseId", case["id"], actual_case_id)
    images = message.get("_images") or []
    if len(images) != 1:
        raise EvidenceContractError(f"{path}.imageCount", 1, len(images))
    if images[0].get("mime") != case["source"]["mime"]:
        raise EvidenceContractError(
            f"{path}.mime",
            case["source"]["mime"],
            images[0].get("mime"),
        )
    raw = base64.b64decode(images[0]["base64"], validate=True)
    digest = hashlib.sha256(raw).hexdigest()
    if digest != case["source"]["sha256"]:
        raise EvidenceContractError(f"{path}.sourceSha256", case["source"]["sha256"], digest)
    actual_url = message["content"][1]["image_url"]["url"]
    if actual_url != source_fact["dataUrl"]:
        raise EvidenceContractError(f"{path}.dataUrl", source_fact["dataUrl"], actual_url)


def project_case(case, message, source_fact, index):
    path = f"$.cases[{index}].expected.model"
    message_before = deepcopy(message)
    model_payload = {
        "model": message["_model"],
        "messages": [{"role": message["role"], "content": message["content"]}],
    }
    if model_payload["messages"][0]["content"] is not message["content"]:
        raise EvidenceContractError(f"{path}.contentIdentity", True, False)
    projected = server_mod._project_model_payload_images(model_payload)
    repeated = server_mod._project_model_payload_images(model_payload)
    output_url = projected["messages"][0]["content"][1]["image_url"]["url"]
    header, encoded = output_url.split(",", 1)
    output_mime = header[5:].split(";", 1)[0]
    output_bytes = base64.b64decode(encoded, validate=True)
    output_decoded = decode_selected_rgba(output_bytes)

    if case["projectionKind"] == "passthrough":
        if output_url != source_fact["dataUrl"]:
            raise EvidenceContractError(
                f"{path}.outputDataUrlSha256",
                text_hash(source_fact["dataUrl"]),
                text_hash(output_url),
            )
        if output_bytes != source_fact["raw"]:
            raise EvidenceContractError(
                f"{path}.outputByteSha256",
                hashlib.sha256(source_fact["raw"]).hexdigest(),
                hashlib.sha256(output_bytes).hexdigest(),
            )
        model_evidence = {
            "outputMime": output_mime,
            "bytePreserved": True,
            "outputByteSha256": hashlib.sha256(output_bytes).hexdigest(),
            "outputDataUrlSha256": text_hash(output_url),
            "pngSignatureHex": None,
            "selectedWidth": output_decoded["width"],
            "selectedHeight": output_decoded["height"],
            "sourceAndOutputRgbaEqual": None,
            "semanticPixelSha256": None,
        }
    else:
        if output_mime != "image/png" or not output_bytes.startswith(PNG_SIGNATURE):
            raise EvidenceContractError(
                f"{path}.pngSignatureHex",
                PNG_SIGNATURE.hex(),
                output_bytes[:8].hex(),
            )
        source_decoded = source_fact["decoded"]
        if (output_decoded["width"], output_decoded["height"]) != (
            source_decoded["width"],
            source_decoded["height"],
        ):
            raise EvidenceContractError(
                f"{path}.selectedWidth",
                (source_decoded["width"], source_decoded["height"]),
                (output_decoded["width"], output_decoded["height"]),
            )
        if output_decoded["rgba"] != source_decoded["rgba"]:
            raise EvidenceContractError(
                f"{path}.sourceAndOutputRgbaEqual",
                True,
                False,
            )
        # This hash is calculated only after direct dimensions and RGBA equality.
        semantic_hash = hashlib.sha256(source_decoded["rgba"]).hexdigest()
        model_evidence = {
            "outputMime": output_mime,
            "bytePreserved": False,
            "outputByteSha256": None,
            "outputDataUrlSha256": None,
            "pngSignatureHex": output_bytes[:8].hex(),
            "selectedWidth": output_decoded["width"],
            "selectedHeight": output_decoded["height"],
            "sourceAndOutputRgbaEqual": True,
            "semanticPixelSha256": semantic_hash,
        }
    return {
        "evidence": model_evidence,
        "outputUrl": output_url,
        "stable": projected == repeated,
        "sourceUnchanged": message == message_before,
        "diagnostic": {
            "encodedByteLength": len(output_bytes),
            "encodedSha256": hashlib.sha256(output_bytes).hexdigest(),
        },
    }


def collect_evidence(fixture):
    validate_profile_and_matrix(fixture)
    source_messages = [case["sourceMessage"] for case in fixture["cases"]]
    source_messages_before = deepcopy(source_messages)
    source_facts = [
        validate_source_contract(case, index)
        for index, case in enumerate(fixture["cases"])
    ]
    serialized_result = run_node(
        SERIALIZE_SCRIPT,
        {"messages": source_messages, "options": fixture["persistenceOptions"]},
    )
    serialized = serialized_result["serialized"]
    if len(serialized) != 7:
        raise EvidenceContractError("$.expectedAggregate.counts.messages", 7, len(serialized))

    with tempfile.TemporaryDirectory(prefix="h3_2d1_image_matrix_") as temp_name:
        temp_root = Path(temp_name)
        jsonl_path = temp_root / "evidence.jsonl"
        with (
            mock.patch.object(server_mod, "_agent_run_worker") as worker_mock,
            mock.patch.object(server_mod, "_create_model_runtime_run") as model_mock,
            mock.patch.object(server_mod, "_execute_agent_pending_tools") as pending_tools_mock,
            mock.patch.object(server_mod, "execute_registered_tool") as tool_mock,
            mock.patch.object(server_mod.request, "urlopen") as urlopen_mock,
            mock.patch.object(server_mod.request, "urlretrieve") as urlretrieve_mock,
            mock.patch.object(server_mod.webbrowser, "open") as browser_mock,
        ):
            server_mod.write_jsonl(jsonl_path, serialized)
            round_tripped = server_mod.read_jsonl(jsonl_path)
            if len(round_tripped) != 7:
                raise EvidenceContractError(
                    "$.expectedAggregate.counts.jsonlMessages",
                    7,
                    len(round_tripped),
                )
            round_trip_before_projection = deepcopy(round_tripped)
            projected_cases = []
            for index, (case, message, source_fact) in enumerate(
                zip(fixture["cases"], round_tripped, source_facts, strict=True)
            ):
                validate_round_trip_identity(case, message, source_fact, index)
                projected_cases.append(project_case(case, message, source_fact, index))

            ui_result = run_node(UI_SCRIPT, {"messages": round_tripped})
            temp_entries = sorted(
                str(path.relative_to(temp_root)).replace("\\", "/")
                for path in temp_root.rglob("*")
                if path.is_file()
            )
            python_side_effects = {
                "modelCalls": model_mock.call_count,
                "toolCalls": pending_tools_mock.call_count + tool_mock.call_count,
                "networkCalls": urlopen_mock.call_count + urlretrieve_mock.call_count,
                "browserCalls": browser_mock.call_count,
                "workerStarts": worker_mock.call_count,
            }

    ui_by_id = {item["caseId"]: item for item in ui_result["projections"]}
    evidence_cases = []
    diagnostics = {}
    for index, (case, message, source_fact, model_result) in enumerate(
        zip(fixture["cases"], round_tripped, source_facts, projected_cases, strict=True)
    ):
        ui = ui_by_id[case["id"]]
        render_src = extract_single_image_src(
            ui["renderUserHtml"],
            f"$.cases[{index}].expected.ui.renderUserImageSrcSha256",
        )
        project_src = extract_single_image_src(
            ui["projectMessagesHtml"],
            f"$.cases[{index}].expected.ui.projectMessagesImageSrcSha256",
        )
        original_url = source_fact["dataUrl"]
        if render_src != original_url or project_src != original_url:
            raise EvidenceContractError(
                f"$.cases[{index}].expected.ui.usesOriginalDataUrl",
                original_url,
                {"renderUser": render_src, "projectMessages": project_src},
            )
        converted = case["projectionKind"] == "convert-to-png"
        converted_absent = (
            model_result["outputUrl"] not in ui["renderUserHtml"]
            and model_result["outputUrl"] not in ui["projectMessagesHtml"]
        ) if converted else None
        evidence_cases.append({
            "persistence": {
                "sourceMessageSha256": canonical_hash(case["sourceMessage"]),
                "serializedMessageSha256": canonical_hash(serialized[index]),
                "roundTripMessageSha256": canonical_hash(message),
                "originalDataUrlSha256": text_hash(original_url),
                "roundTripCaseId": message["meta"]["evidenceCaseId"],
                "roundTripMime": message["_images"][0]["mime"],
                "roundTripSourceSha256": hashlib.sha256(
                    base64.b64decode(message["_images"][0]["base64"], validate=True)
                ).hexdigest(),
                "imageCount": len(message["_images"]),
            },
            "model": model_result["evidence"],
            "ui": {
                "renderUserImageSrcSha256": text_hash(render_src),
                "projectMessagesImageSrcSha256": text_hash(project_src),
                "renderUserHtmlSha256": text_hash(ui["renderUserHtml"]),
                "projectMessagesHtmlSha256": text_hash(ui["projectMessagesHtml"]),
                "usesOriginalDataUrl": True,
                "modelOutputUrlAbsentWhenConverted": converted_absent,
            },
            "stability": {
                "modelProjectionStable": model_result["stable"],
                "uiProjectionStable": (
                    ui["renderUserHtml"] == ui["repeatedRenderUserHtml"]
                    and ui["projectMessagesHtml"] == ui["repeatedProjectMessagesHtml"]
                ),
                "sourceMessageUnchanged": (
                    model_result["sourceUnchanged"]
                    and message == round_trip_before_projection[index]
                ),
                "sourceImageCount": ui["sourceImageCount"],
            },
        })
        diagnostics[case["id"]] = model_result["diagnostic"]

    aggregate = {
        "counts": {
            "cases": len(evidence_cases),
            "passthroughCases": sum(
                case["projectionKind"] == "passthrough" for case in fixture["cases"]
            ),
            "convertedCases": sum(
                case["projectionKind"] == "convert-to-png" for case in fixture["cases"]
            ),
            "messages": len(serialized),
            "contentImages": sum(
                part.get("type") == "image_url"
                for message in round_tripped
                for part in message["content"]
                if isinstance(part, dict)
            ),
            "sourceImages": sum(len(message["_images"]) for message in round_tripped),
            "jsonlMessages": len(round_tripped),
        },
        "executedCaseIds": [case["id"] for case in fixture["cases"]],
        "batchStability": {
            "serializationStable": serialized_result["repeated"] == serialized,
            "buildPayloadMatchesSerialization": serialized_result["saveMessages"] == serialized,
            "sourceMessagesUnchanged": (
                serialized_result["sourceUnchanged"]
                and ui_result["sourceUnchanged"]
                and source_messages == source_messages_before
            ),
        },
        "sideEffects": {
            "tempDiskEntries": temp_entries,
            "sessionApiCalls": serialized_result["fetchCalls"] + ui_result["fetchCalls"],
            **python_side_effects,
        },
    }
    return {"cases": evidence_cases, "aggregate": aggregate}, diagnostics


class TestHarnessImageMimePreservation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        cls.fixture = load_fixture()
        cls.validator = Draft202012Validator(
            cls.schema,
            format_checker=FormatChecker(),
        )

    def test_fixture_schema_hash_and_exact_case_matrix(self):
        errors = sorted(
            self.validator.iter_errors(self.fixture),
            key=lambda error: tuple(str(part) for part in error.absolute_path),
        )
        self.assertEqual(errors, [])
        self.assertEqual(
            hashlib.sha256(FIXTURE_PATH.read_bytes()).hexdigest(),
            EXPECTED_FIXTURE_SHA256,
        )
        validate_profile_and_matrix(self.fixture)
        for index, case in enumerate(self.fixture["cases"]):
            with self.subTest(case=case["id"]):
                validate_source_contract(case, index)

    def test_all_seven_cases_close_one_shared_production_chain_without_skips(self):
        collected, _diagnostics = collect_evidence(self.fixture)
        self.assertEqual(collected["aggregate"]["executedCaseIds"], EXPECTED_PROFILE["caseOrder"])
        self.assertEqual(len(collected["cases"]), 7)
        for index, (actual, case) in enumerate(
            zip(collected["cases"], self.fixture["cases"], strict=True)
        ):
            with self.subTest(case=case["id"]):
                require_match(actual, case["expected"], f"$.cases[{index}].expected")
        require_match(
            collected["aggregate"],
            self.fixture["expectedAggregate"],
            "$.expectedAggregate",
        )

    def test_profile_and_case_set_mutations_freeze_first_difference_paths(self):
        mutations = []

        profile = deepcopy(self.fixture)
        profile["evidenceProfile"]["version"] = 2
        mutations.append((profile, "$.evidenceProfile.version"))

        missing = deepcopy(self.fixture)
        missing["cases"].pop()
        mutations.append((missing, "$.cases[6]"))

        duplicate = deepcopy(self.fixture)
        duplicate["cases"][6] = deepcopy(duplicate["cases"][5])
        mutations.append((duplicate, "$.cases[6].id"))

        reordered = deepcopy(self.fixture)
        reordered["cases"][0], reordered["cases"][1] = (
            reordered["cases"][1],
            reordered["cases"][0],
        )
        mutations.append((reordered, "$.cases[0].id"))

        for mutated, expected_path in mutations:
            with self.subTest(path=expected_path):
                with self.assertRaises(EvidenceContractError) as caught:
                    validate_profile_and_matrix(mutated)
                self.assertEqual(caught.exception.path, expected_path)

    def test_source_and_format_link_mutations_freeze_first_difference_paths(self):
        mutations = []

        wrong_url = deepcopy(self.fixture)
        wrong_url["cases"][0]["sourceMessage"]["content"][1]["image_url"]["url"] = (
            "data:image/png;base64,AA=="
        )
        mutations.append((wrong_url, 0, "$.cases[0].sourceMessage.content[1].image_url.url"))

        wrong_mime = deepcopy(self.fixture)
        wrong_mime["cases"][3]["sourceMessage"]["_images"][0]["mime"] = "image/png"
        mutations.append((wrong_mime, 3, "$.cases[3].sourceMessage._images[0].mime"))

        wrong_source_hash = deepcopy(self.fixture)
        wrong_source_hash["cases"][6]["source"]["sha256"] = "0" * 64
        mutations.append((wrong_source_hash, 6, "$.cases[6].source.sha256"))

        format_cross_link = deepcopy(self.fixture)
        bmp_image = format_cross_link["cases"][3]["sourceMessage"]["_images"][0]
        gif_message = format_cross_link["cases"][4]["sourceMessage"]
        gif_message["_images"][0]["base64"] = bmp_image["base64"]
        gif_message["content"][1]["image_url"]["url"] = (
            f"data:image/gif;base64,{bmp_image['base64']}"
        )
        mutations.append((format_cross_link, 4, "$.cases[4].sourceMessage._images[0].base64"))

        for mutated, index, expected_path in mutations:
            with self.subTest(path=expected_path):
                with self.assertRaises(EvidenceContractError) as caught:
                    validate_source_contract(mutated["cases"][index], index)
                self.assertEqual(caught.exception.path, expected_path)

    def test_passthrough_conversion_ui_and_persistence_mutations_freeze_paths(self):
        collected, _diagnostics = collect_evidence(self.fixture)
        mutations = [
            (0, "model", "outputByteSha256", "0" * 64),
            (3, "model", "outputMime", "image/bmp"),
            (4, "model", "semanticPixelSha256", "0" * 64),
            (3, "ui", "renderUserImageSrcSha256", "0" * 64),
            (3, "ui", "modelOutputUrlAbsentWhenConverted", False),
            (6, "persistence", "roundTripMessageSha256", "0" * 64),
        ]
        for index, section, field, value in mutations:
            actual = deepcopy(collected["cases"][index])
            actual[section][field] = value
            expected_path = f"$.cases[{index}].expected.{section}.{field}"
            with self.subTest(path=expected_path):
                with self.assertRaises(EvidenceContractError) as caught:
                    require_match(
                        actual,
                        self.fixture["cases"][index]["expected"],
                        f"$.cases[{index}].expected",
                    )
                self.assertEqual(caught.exception.path, expected_path)

    def test_schema_rejects_profile_drift_missing_extra_and_unknown_cases(self):
        mutations = []

        profile = deepcopy(self.fixture)
        profile["evidenceProfile"]["scope"] = "single-synthetic-ico-production-chain"
        mutations.append((profile, ("evidenceProfile", "scope")))

        missing = deepcopy(self.fixture)
        missing["cases"].pop()
        mutations.append((missing, ("cases",)))

        extra = deepcopy(self.fixture)
        extra["cases"].append(deepcopy(extra["cases"][-1]))
        mutations.append((extra, ("cases",)))

        unknown = deepcopy(self.fixture)
        unknown["cases"][0]["unexpected"] = True
        mutations.append((unknown, ("cases", 0)))

        for mutated, expected_path in mutations:
            with self.subTest(path=expected_path):
                paths = {
                    tuple(error.absolute_path)
                    for error in self.validator.iter_errors(mutated)
                }
                self.assertIn(expected_path, paths)


if __name__ == "__main__":
    unittest.main()
