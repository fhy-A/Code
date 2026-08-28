"""Isolated loopback host for H4 browser tests.

The Code side uses the production CodeHandler behavior through an H4-only
subclass that silences access logging so stdout remains the JSONL control
channel. This process otherwise only provides a deterministic loopback
upstream, test-side instrumentation, and lifecycle controls.
"""

from __future__ import annotations

import base64
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import sys
import threading
import time
from urllib import parse
import uuid


MODEL_ID = "h4-e2e-model"
TRUSTED_ROUTE_MODEL_ID = "h4-deepseek-trusted-route-model"
TRUSTED_ROUTE_USER = "H4_TRUSTED_MODEL_ROUTE_USER"
TRUSTED_ROUTE_FINAL = "H4_TRUSTED_MODEL_ROUTE_FINAL"
CONNECTION_SHARED_MODEL_ID = "h4-shared-connection-model"
CONNECTION_ROUTE_USER = "H4_CONNECTION_ROUTE_USER"
CONNECTION_ROUTE_FINAL = "H4_CONNECTION_ROUTE_FINAL"
TRUSTED_ROUTE_PRIMARY_KEY = "h4-synthetic-credential"
TRUSTED_ROUTE_SECONDARY_KEY = "h4-synthetic-route-credential"
TOOL_PROTOCOL_HISTORY_USER = "H4_TOOL_PROTOCOL_HISTORY_USER"
TOOL_PROTOCOL_CONTINUE_USER = "H4_TOOL_PROTOCOL_CONTINUE_USER"
TOOL_PROTOCOL_FINAL = "H4_TOOL_PROTOCOL_FINAL"
TOOL_PROTOCOL_CALL_ID = "h4-history-tool-call"
PARALLEL_VISUAL_PROTOCOL_USER = "H4_PARALLEL_VISUAL_PROTOCOL_USER"
PARALLEL_VISUAL_PROTOCOL_STAGE = "H4_PARALLEL_VISUAL_PROTOCOL_STAGE"
PARALLEL_VISUAL_PROTOCOL_FINAL = "H4_PARALLEL_VISUAL_PROTOCOL_FINAL"
PARALLEL_VISUAL_PROTOCOL_CALL_IDS = (
    "h4-parallel-visual-call-a",
    "h4-parallel-visual-call-b",
)
PARALLEL_VISUAL_PROTOCOL_PATHS = (
    "parallel-visual-a.png",
    "parallel-visual-b.png",
)
TOOL_PROTOCOL_ERROR_USER = "H4_TOOL_PROTOCOL_ERROR_USER"
RUNTIME_RECOVERY_USER = "H4_RUNTIME_RECOVERY_USER"
RUNTIME_RECOVERY_STAGE = "H4_RUNTIME_RECOVERY_STAGE"
RUNTIME_RECOVERY_PARTIAL_ONE = "H4_RUNTIME_RECOVERY_PARTIAL_ONE"
RUNTIME_RECOVERY_PARTIAL_TWO = "H4_RUNTIME_RECOVERY_PARTIAL_TWO"
RUNTIME_RECOVERY_FINAL = "H4_RUNTIME_RECOVERY_FINAL"
RUNTIME_RECOVERY_CALL_ID = "h4-runtime-recovery-read"
SKILL_EVIDENCE_USER = "H4_SKILL_EVIDENCE_USER"
SKILL_EVIDENCE_CANDIDATE = "H4_SKILL_EVIDENCE_CANDIDATE"
SKILL_EVIDENCE_FINAL = "H4_SKILL_EVIDENCE_FINAL"
SKILL_EVIDENCE_CALL_ID = "h4-skill-evidence-read"
IMAGE_MODEL_ID = "h4-image-model"
IMAGE_GENERATION_USER = "H4_IMAGE_GENERATION_USER"
IMAGE_GENERATION_FINAL = "H4_IMAGE_GENERATION_FINAL"
IMAGE_GENERATION_CALL_ID = "h4-image-generation-call"
IMAGE_BATCH_USER = "H4_IMAGE_BATCH_FULL_USER"
IMAGE_BATCH_FINAL = "H4_IMAGE_BATCH_FULL_FINAL"
IMAGE_BATCH_CALL_ID = "h4-image-batch-full-call"
IMAGE_BATCH_PARTIAL_USER = "H4_IMAGE_BATCH_PARTIAL_USER"
IMAGE_BATCH_PARTIAL_FINAL = "H4_IMAGE_BATCH_PARTIAL_FINAL"
IMAGE_BATCH_PARTIAL_CALL_ID = "h4-image-batch-partial-call"
IMAGE_EDIT_USER = "H4_IMAGE_EDIT_USER"
IMAGE_EDIT_FINAL = "H4_IMAGE_EDIT_FINAL"
IMAGE_EDIT_CALL_ID = "h4-image-edit-call"
IMAGE_EDIT_UNSUPPORTED_USER = "H4_IMAGE_EDIT_UNSUPPORTED_USER"
IMAGE_EDIT_UNSUPPORTED_FINAL = "H4_IMAGE_EDIT_UNSUPPORTED_FINAL"
IMAGE_EDIT_UNSUPPORTED_CALL_ID = "h4-image-edit-unsupported-call"
IMAGE_EDIT_UNSUPPORTED_RETRY_CALL_ID = "h4-image-edit-unsupported-retry-call"
PLAIN_USER = "H4_PLAIN_USER"
PLAIN_FINAL = "H4_PLAIN_FINAL"
AUTO_COMPACTION_SEED = "H4_AUTO_COMPACTION_SEED"
AUTO_COMPACTION_SEED_FINAL = "H4_AUTO_COMPACTION_SEED_FINAL"
AUTO_COMPACTION_USER = "H4_AUTO_COMPACTION_USER"
AUTO_COMPACTION_CHECKPOINT = "H4_CONTEXT_CHECKPOINT_INTERNAL"
AUTO_COMPACTION_FINAL = "H4_AUTO_COMPACTION_FINAL"
CONTEXT_CALIBRATION_USER = "H4_CONTEXT_CALIBRATION_USER"
CONTEXT_CALIBRATION_FINAL = "H4_CONTEXT_CALIBRATION_FINAL"
CONTEXT_CALIBRATION_UNUSED_KEY = "h4-context-calibration-unused-key"
FAVICON_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAFUlEQVR4nGNUqPjwn4GBgYEJRIAwACXYAoumRkB8AAAAAElFTkSuQmCC"
)
FAVICON_PLACEHOLDER_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Z1sYAAAAASUVORK5CYII="
)
TOOL_USER = "H4_TOOL_USER"
TOOL_STAGE = "H4_TOOL_STAGE"
TOOL_FINAL = "H4_TOOL_FINAL"
TOOL_DETAILS_USER = "H4_TOOL_DETAILS_USER"
TOOL_DETAILS_STAGE = "H4_TOOL_DETAILS_STAGE"
TOOL_DETAILS_FINAL = "H4_TOOL_DETAILS_FINAL"
MULTI_TOOL_USER = "H4_MULTI_TOOL_USER"
MULTI_TOOL_STAGE = "H4_MULTI_TOOL_STAGE"
MULTI_TOOL_FINAL = "H4_MULTI_TOOL_FINAL"
INVALID_TOOL_USER = "H4_INVALID_TOOL_ARGUMENTS_USER"
INVALID_TOOL_STAGE = "H4_INVALID_TOOL_ARGUMENTS_STAGE"
INVALID_TOOL_FINAL = "H4_INVALID_TOOL_ARGUMENTS_FINAL"
PARSE_ERROR_TOOL_USER = "H4_PARSE_ERROR_TOOL_ARGUMENTS_USER"
PARSE_ERROR_TOOL_STAGE = "H4_PARSE_ERROR_TOOL_ARGUMENTS_STAGE"
PARSE_ERROR_TOOL_FINAL = "H4_PARSE_ERROR_TOOL_ARGUMENTS_FINAL"
MISSING_PATH_TOOL_USER = "H4_MISSING_PATH_TOOL_ARGUMENTS_USER"
MISSING_PATH_TOOL_STAGE = "H4_MISSING_PATH_TOOL_ARGUMENTS_STAGE"
MISSING_PATH_TOOL_FINAL = "H4_MISSING_PATH_TOOL_ARGUMENTS_FINAL"
EXECUTOR_RANGE_USER = "H4_EXECUTOR_RANGE_FAILURE_USER"
EXECUTOR_RANGE_STAGE = "H4_EXECUTOR_RANGE_FAILURE_STAGE"
EXECUTOR_RANGE_FINAL = "H4_EXECUTOR_RANGE_FAILURE_FINAL"
REPEATED_RANGE_FAILURE_USER = "H4_REPEATED_RANGE_FAILURE_USER"
REPEATED_RANGE_FAILURE_STAGE = "H4_REPEATED_RANGE_FAILURE_STAGE"
REPEATED_RANGE_FAILURE_FINAL = "H4_REPEATED_RANGE_FAILURE_FINAL"
FORCED_FINAL_MODEL_FAILURE_USER = "H4_FORCED_FINAL_MODEL_FAILURE_USER"
FORCED_FINAL_UNUSABLE_TOOL_USER = "H4_FORCED_FINAL_UNUSABLE_TOOL_USER"
ARGUMENT_ISOLATION_USER = "H4_ARGUMENT_ISOLATION_FAILURE_USER"
ARGUMENT_ISOLATION_STAGE = "H4_ARGUMENT_ISOLATION_FAILURE_STAGE"
ARGUMENT_ISOLATION_FINAL = "H4_ARGUMENT_ISOLATION_FAILURE_FINAL"
SIGNATURE_ALTERNATION_USER = "H4_SIGNATURE_ALTERNATION_FAILURE_USER"
SIGNATURE_ALTERNATION_STAGE = "H4_SIGNATURE_ALTERNATION_FAILURE_STAGE"
SIGNATURE_ALTERNATION_FINAL = "H4_SIGNATURE_ALTERNATION_FAILURE_FINAL"
SUCCESS_RESET_USER = "H4_SUCCESS_RESET_FAILURE_USER"
SUCCESS_RESET_STAGE = "H4_SUCCESS_RESET_FAILURE_STAGE"
SUCCESS_RESET_FINAL = "H4_SUCCESS_RESET_FAILURE_FINAL"
MISSING_FILE_USER = "H4_MISSING_FILE_FAILURE_USER"
MISSING_FILE_STAGE = "H4_MISSING_FILE_FAILURE_STAGE"
MISSING_FILE_FINAL = "H4_MISSING_FILE_FAILURE_FINAL"
TIFF_IMAGE_USER = "H4_TIFF_IMAGE_USER"
TIFF_IMAGE_FINAL = "H4_TIFF_IMAGE_FINAL"
TIMING_MAIN_USER = "H4_TIMING_MAIN_USER"
TIMING_MAIN_FINAL = "H4_TIMING_MAIN_FINAL"
TIMING_PARALLEL_USER = "H4_TIMING_PARALLEL_USER"
TIMING_PARALLEL_FINAL = "H4_TIMING_PARALLEL_FINAL"
TIMING_QUEUE_USER = "H4_TIMING_QUEUE_USER"
TIMING_QUEUE_FINAL = "H4_TIMING_QUEUE_FINAL"
PARALLEL_FAILURE_USER = "H4_PARALLEL_MODEL_FAILURE_USER"
PARALLEL_FAILURE_ERROR = "H4_PARALLEL_MODEL_FAILURE"
PARALLEL_FAILURE_FOLLOWUP_USER = "H4_PARALLEL_FAILURE_FOLLOWUP_USER"
PARALLEL_FAILURE_FOLLOWUP_FINAL = "H4_PARALLEL_FAILURE_FOLLOWUP_FINAL"
QUESTIONNAIRE_USER = "H4_QUESTIONNAIRE_USER"
QUESTIONNAIRE_FINAL = "H4_QUESTIONNAIRE_FINAL"
QUEUE_QUESTIONNAIRE_USER = "H4_QUESTIONNAIRE_USER_QUEUE"
QUEUE_QUESTIONNAIRE_FINAL = QUESTIONNAIRE_FINAL
MIXED_QUESTIONNAIRE_USER = "H4_MIXED_QUESTIONNAIRE_USER"
MIXED_QUESTIONNAIRE_FINAL = "H4_MIXED_QUESTIONNAIRE_FINAL"
FIVE_QUESTIONNAIRE_USER = "H4_FIVE_QUESTIONNAIRE_USER"
FIVE_QUESTIONNAIRE_FINAL = "H4_FIVE_QUESTIONNAIRE_FINAL"
TERMINAL_QUESTIONNAIRE_USER = "H4_TERMINAL_QUESTIONNAIRE_USER"
TERMINAL_QUESTIONNAIRE_FINAL = "H4_TERMINAL_QUESTIONNAIRE_FINAL"
CLASSIC_USER = "H4_CLASSIC_USER"
CLASSIC_FINAL = "H4_CLASSIC_FINAL"
GOAL_V2_EXPLICIT_USER = "/goal H4_GOAL_V2_EXPLICIT"
GOAL_V2_EXPLICIT_FINAL = "H4_GOAL_V2_EXPLICIT_FINAL"
GOAL_V2_CANCEL_DRAFT_USER = "/goal H4_GOAL_V2_CANCEL_DRAFT"
GOAL_V2_CANCEL_DRAFT_FINAL = "H4_GOAL_V2_CANCEL_DRAFT_FINAL"
GOAL_V2_CANCEL_USER = "H4_GOAL_V2_CANCEL_CURRENT_GOAL"
GOAL_V2_CANCEL_FINAL = "H4_GOAL_V2_CANCEL_FINAL"
GOAL_V2_CANCEL_CALL_ID = "h4-goal-v2-cancel-1"
GOAL_V2_PUBLIC_COMMENTARY = "H4_GOAL_V2_PUBLIC_PROCESS_COMMENTARY"
GOAL_V2_PRIVATE_REASONING = "H4_GOAL_V2_PRIVATE_REASONING_MUST_NOT_PROJECT"
GOAL_V2_AUTONOMOUS_USER = "H4_GOAL_V2_AUTONOMOUS"
GOAL_V2_AUTONOMOUS_FINAL = "H4_GOAL_V2_AUTONOMOUS_FINAL"
GOAL_V2_AUTONOMOUS_COMPLETE_USER = "H4_GOAL_V2_AUTONOMOUS_COMPLETE"
GOAL_V2_AUTONOMOUS_COMPLETE_FINAL = "H4_GOAL_V2_AUTONOMOUS_COMPLETE_FINAL"
GOAL_V2_CONTINUATION_USER = "/goal H4_GOAL_V2_CONTINUATION"
GOAL_V2_CONTINUATION_STAGE = "H4_GOAL_V2_CONTINUATION_PUBLIC_STAGE"
GOAL_V2_CONTINUATION_FINAL = "H4_GOAL_V2_CONTINUATION_FINAL"
GOAL_V2_CONTINUATION_ROOT_CALL_IDS = tuple(
    f"h4-goal-v2-continuation-root-{index}" for index in range(1, 41)
)
GOAL_V2_CONTINUATION_NEXT_CALL_IDS = tuple(
    f"h4-goal-v2-continuation-next-{index}" for index in range(1, 6)
)
GOAL_V2_HARD_LIMIT_USER = "/goal H4_GOAL_V2_HARD_LIMIT"
GOAL_V2_HARD_LIMIT_STAGE = "H4_GOAL_V2_HARD_LIMIT_PUBLIC_STAGE"
GOAL_V2_HARD_LIMIT_CALL_IDS = tuple(
    f"h4-goal-v2-hard-limit-{index}" for index in range(1, 51)
)
GOAL_V2_EXPLICIT_CALL_IDS = tuple(
    f"h4-goal-v2-explicit-{index}" for index in range(1, 5)
)
GOAL_V2_AUTONOMOUS_CALL_IDS = tuple(
    f"h4-goal-v2-autonomous-{index}" for index in range(1, 6)
)
GOAL_V2_AUTONOMOUS_COMPLETE_CALL_IDS = tuple(
    f"h4-goal-v2-autonomous-complete-{index}" for index in range(1, 9)
)
GOAL_V2_ACCEPT_SETUP_USER = "/goal H4_GOAL_V2_ACCEPT_SETUP"
GOAL_V2_ACCEPT_SETUP_FINAL = "H4_GOAL_V2_ACCEPT_SETUP_FINAL"
GOAL_V2_FINAL_STAGE_SUMMARY = "H4_GOAL_V2_FINAL_STAGE_SUMMARY"
GOAL_V2_FINAL_SUMMARY_ONE = "H4_GOAL_V2_FINAL_SUMMARY_ONE"
GOAL_V2_FINAL_SUMMARY_TWO = "H4_GOAL_V2_FINAL_SUMMARY_TWO"
GOAL_V2_ACCEPT_SETUP_CALL_IDS = tuple(
    f"h4-goal-v2-accept-setup-{index}" for index in range(1, 8)
)
GOAL_V2_GATE_SETUP_USER = "/goal H4_GOAL_V2_GATE_SETUP"
GOAL_V2_GATE_SETUP_FINAL = "H4_GOAL_V2_GATE_SETUP_FINAL"
GOAL_V2_GATE_REQUEST = "H4_GOAL_V2_GATE_REQUEST_REGION"
GOAL_V2_GATE_SETUP_CALL_IDS = tuple(
    f"h4-goal-v2-gate-setup-{index}" for index in range(1, 9)
)
GOAL_V2_GATE_USER = "H4_GOAL_V2_GATE_USER_ACCEPTED"
GOAL_V2_GATE_FAILURE_USER = "H4_GOAL_V2_GATE_SUPPLEMENT_FAIL_REGION"
GOAL_V2_GATE_RETRY_USER = "H4_GOAL_V2_GATE_SUPPLEMENT_RETRY_REGION"
GOAL_V2_GATE_FAILURE_ERROR = "H4_GOAL_V2_GATE_SUPPLEMENT_UPSTREAM_FAILURE"
GOAL_V2_GATE_FINAL = "H4_GOAL_V2_GATE_FINAL"
GOAL_V2_GATE_CALL_IDS = tuple(
    f"h4-goal-v2-gate-complete-{index}" for index in range(1, 3)
)
STREAM_USER = "H4_STREAM_REFRESH_USER"
STREAM_ONE = "H4_STREAM_ONE "
STREAM_TWO = "H4_STREAM_TWO "
STREAM_THREE = "H4_STREAM_THREE"
TOOL_CALL_ID = "h4-read-call-1"
MULTI_TOOL_CALL_IDS = ("h4-multi-read-call-1", "h4-multi-read-call-2")
INVALID_TOOL_CALL_ID = "h4-invalid-read-call-1"
PARSE_ERROR_TOOL_CALL_ID = "h4-parse-error-read-call-1"
MISSING_PATH_TOOL_CALL_ID = "h4-missing-path-read-call-1"
EXECUTOR_RANGE_TOOL_CALL_ID = "h4-executor-range-read-call-1"
REPEATED_RANGE_FAILURE_TOOL_CALL_IDS = tuple(
    f"h4-repeated-range-read-call-{index}" for index in range(1, 5)
)
FORCED_FINAL_UNUSABLE_TOOL_CALL_ID = "h4-forced-final-unusable-read-call-5"
ARGUMENT_ISOLATION_TOOL_CALL_IDS = tuple(
    f"h4-argument-isolation-read-call-{index}" for index in range(1, 4)
)
SIGNATURE_ALTERNATION_TOOL_CALL_IDS = tuple(
    f"h4-signature-alternation-read-call-{index}" for index in range(1, 4)
)
SUCCESS_RESET_TOOL_CALL_IDS = tuple(
    f"h4-success-reset-read-call-{index}" for index in range(1, 4)
)
MISSING_FILE_TOOL_CALL_ID = "h4-missing-file-read-call-1"
QUESTIONNAIRE_TOOL_CALL_ID = "h4-questionnaire-call-1"
QUESTIONNAIRE_TITLE = "H4_QUESTIONNAIRE_TITLE"
QUESTIONNAIRE_REASON = "H4_QUESTIONNAIRE_REASON"
QUESTIONNAIRE_QUESTION_ID = "h4-questionnaire-choice"
QUESTIONNAIRE_PROMPT = "H4_QUESTIONNAIRE_PROMPT"
LEGACY_QUESTIONNAIRE_USER = "H4_LEGACY_QUESTIONNAIRE_USER"
LEGACY_QUESTIONNAIRE_FINAL = "H4_LEGACY_QUESTIONNAIRE_FINAL"
LEGACY_QUESTIONNAIRE_TOOL_CALL_ID = "h4-legacy-questionnaire-call-1"
LEGACY_QUESTIONNAIRE_REQUEST_ID = f"user-input-{LEGACY_QUESTIONNAIRE_TOOL_CALL_ID}"
LEGACY_QUESTIONNAIRE_TITLE = "H4_LEGACY_QUESTIONNAIRE_TITLE"
LEGACY_QUESTIONNAIRE_REASON = "H4_LEGACY_QUESTIONNAIRE_REASON"
LEGACY_QUESTIONNAIRE_QUESTION_ID = "h4-legacy-questionnaire-text"
LEGACY_QUESTIONNAIRE_PROMPT = "H4_LEGACY_QUESTIONNAIRE_PROMPT"
QUESTIONNAIRE_OPTIONS = (
    {
        "value": "h4-option-a",
        "label": "H4_QUESTIONNAIRE_OPTION_A",
        "description": "H4_QUESTIONNAIRE_OPTION_A_DESCRIPTION",
        "recommended": True,
    },
    {
        "value": "h4-option-b",
        "label": "H4_QUESTIONNAIRE_OPTION_B",
        "description": "H4_QUESTIONNAIRE_OPTION_B_DESCRIPTION",
        "recommended": False,
    },
)
QUESTIONNAIRE_SELECTED_OPTION = QUESTIONNAIRE_OPTIONS[1]
MIXED_QUESTIONNAIRE_TOOL_CALL_ID = "h4-mixed-questionnaire-call-1"
MIXED_QUESTIONNAIRE_TITLE = "H4_MIXED_QUESTIONNAIRE_TITLE"
MIXED_QUESTIONNAIRE_REASON = "H4_MIXED_QUESTIONNAIRE_REASON"
MIXED_QUESTIONNAIRE_SINGLE_ID = "h4-mixed-single"
MIXED_QUESTIONNAIRE_SINGLE_PROMPT = "H4_MIXED_SINGLE_PROMPT"
MIXED_QUESTIONNAIRE_SINGLE_OPTIONS = (
    {
        "value": "h4-mixed-single-a",
        "label": "H4_MIXED_SINGLE_OPTION_A",
        "description": "H4_MIXED_SINGLE_OPTION_A_DESCRIPTION",
        "recommended": True,
    },
    {
        "value": "h4-mixed-single-b",
        "label": "H4_MIXED_SINGLE_OPTION_B",
        "description": "H4_MIXED_SINGLE_OPTION_B_DESCRIPTION",
        "recommended": False,
    },
)
MIXED_QUESTIONNAIRE_MULTIPLE_ID = "h4-mixed-multiple"
MIXED_QUESTIONNAIRE_MULTIPLE_PROMPT = "H4_MIXED_MULTIPLE_PROMPT"
MIXED_QUESTIONNAIRE_MULTIPLE_OPTIONS = (
    {
        "value": "h4-mixed-multiple-a",
        "label": "H4_MIXED_MULTIPLE_OPTION_A",
        "description": "H4_MIXED_MULTIPLE_OPTION_A_DESCRIPTION",
        "recommended": True,
    },
    {
        "value": "h4-mixed-multiple-b",
        "label": "H4_MIXED_MULTIPLE_OPTION_B",
        "description": "H4_MIXED_MULTIPLE_OPTION_B_DESCRIPTION",
        "recommended": False,
    },
    {
        "value": "h4-mixed-multiple-c",
        "label": "H4_MIXED_MULTIPLE_OPTION_C",
        "description": "H4_MIXED_MULTIPLE_OPTION_C_DESCRIPTION",
        "recommended": False,
    },
)
MIXED_QUESTIONNAIRE_OTHER = "H4_MIXED_MULTIPLE_OTHER"
MIXED_QUESTIONNAIRE_TEXT_ID = "h4-mixed-text"
MIXED_QUESTIONNAIRE_TEXT_PROMPT = "H4_MIXED_TEXT_PROMPT"
MIXED_QUESTIONNAIRE_TEXT_ANSWER = "H4_MIXED_TEXT_ANSWER"
MIXED_QUESTIONNAIRE_TEXT_OPTIONS = (
    {
        "value": "h4-mixed-text-a",
        "label": "H4_MIXED_TEXT_OPTION_A",
        "description": "H4_MIXED_TEXT_OPTION_A_DESCRIPTION",
        "recommended": True,
    },
    {
        "value": "h4-mixed-text-b",
        "label": "H4_MIXED_TEXT_OPTION_B",
        "description": "H4_MIXED_TEXT_OPTION_B_DESCRIPTION",
        "recommended": False,
    },
)
FIVE_QUESTIONNAIRE_TOOL_CALL_ID = "h4-five-questionnaire-call-1"
FIVE_QUESTIONNAIRE_TITLE = "H4_FIVE_QUESTIONNAIRE_TITLE"
FIVE_QUESTIONNAIRE_REASON = "H4_FIVE_QUESTIONNAIRE_REASON"
FIVE_QUESTIONNAIRE_QUESTIONS = tuple(
    {
        "id": f"h4-five-question-{index}",
        "prompt": f"H4_FIVE_QUESTIONNAIRE_PROMPT_{index}",
        "type": "single",
        "required": True,
        "allowOther": True,
        "options": list(QUESTIONNAIRE_OPTIONS),
    }
    for index in range(1, 6)
)
TERMINAL_QUESTIONNAIRE_OPTIONS = (
    {
        "value": "h4-terminal-suggested",
        "label": "H4_TERMINAL_SUGGESTED",
        "description": "H4_TERMINAL_RECOMMENDATION_REASON",
        "recommended": True,
    },
    {
        "value": "h4-terminal-alternative",
        "label": "H4_TERMINAL_ALTERNATIVE",
        "description": "H4_TERMINAL_ALTERNATIVE_REASON",
        "recommended": False,
    },
)
TERMINAL_QUESTIONNAIRE_TOOL_CALL_ID = "h4-terminal-questionnaire-call-1"
TERMINAL_QUESTIONNAIRE_TITLE = "H4_TERMINAL_QUESTIONNAIRE_TITLE"
TERMINAL_QUESTIONNAIRE_REASON = "H4_TERMINAL_QUESTIONNAIRE_REASON"
TERMINAL_QUESTIONNAIRE_FIRST_ID = "h4-terminal-questionnaire-first"
TERMINAL_QUESTIONNAIRE_SECOND_ID = "h4-terminal-questionnaire-second"
EDIT_AUTHORIZATION_APPROVE_USER = "H4_EDIT_AUTHORIZATION_APPROVE_USER"
EDIT_AUTHORIZATION_REJECT_USER = "H4_EDIT_AUTHORIZATION_REJECT_USER"
EDIT_AUTHORIZATION_CONFLICT_USER = "H4_EDIT_AUTHORIZATION_CONFLICT_USER"
EDIT_AUTHORIZATION_STAGE = "H4_EDIT_AUTHORIZATION_STAGE"
EDIT_AUTHORIZATION_APPROVE_FINAL = "H4_EDIT_AUTHORIZATION_APPROVE_FINAL"
EDIT_AUTHORIZATION_REJECT_FINAL = "H4_EDIT_AUTHORIZATION_REJECT_FINAL"
EDIT_AUTHORIZATION_CONFLICT_FINAL = "H4_EDIT_AUTHORIZATION_CONFLICT_FINAL"
PROPOSE_EDIT_TOOL_CALL_ID = "h4-propose-edit-call-1"
PROPOSE_EDIT_PATH = "h4-propose-edit-fixture.txt"
PROPOSE_EDIT_OLD_TEXT = "H4_PROPOSE_EDIT_INITIAL"
PROPOSE_EDIT_NEW_TEXT = "H4_PROPOSE_EDIT_TARGET"
PROPOSE_EDIT_INITIAL_CONTENT = f"{PROPOSE_EDIT_OLD_TEXT}\n"
PROPOSE_EDIT_TARGET_CONTENT = f"{PROPOSE_EDIT_NEW_TEXT}\n"
PROPOSE_EDIT_INITIAL_SHA256 = (
    "f12af1cc9275e5511341e977ac8ad5b13050b8eb8951b4a78555018cdbcaebe3"
)
PROPOSE_EDIT_TARGET_SHA256 = (
    "26ed22af144d40ac7a02a4a6087bbfa8bcb2024782e90fdac3ed6cb2abbbf3ef"
)
PROPOSE_EDIT_THIRD_PARTY_CONTENT = "H4_PROPOSE_EDIT_THIRD_PARTY\n"
PROPOSE_EDIT_THIRD_PARTY_SHA256 = (
    "3ca2970e23df18316faba0c55fde5881e36d215d02499ee36e3e257113ebe931"
)
PROPOSE_EDIT_THIRD_PARTY_TRANSITION_COMMAND = (
    "transition-propose-edit-third-party"
)
PROPOSE_EDIT_TOOL_ARGUMENTS = {
    "path": PROPOSE_EDIT_PATH,
    "oldText": PROPOSE_EDIT_OLD_TEXT,
    "newText": PROPOSE_EDIT_NEW_TEXT,
}
READ_PATH = "fixture.txt"
FIXTURE_CONTENT = "H4_SYNTHETIC_FILE_CONTENT\n"
MISSING_READ_PATH = "h4-missing-fixture.txt"
SIGNATURE_ALTERNATION_READ_PATH = "h4-signature-alternation-fixture.txt"
SUCCESS_RESET_READ_PATH = "h4-success-reset-fixture.txt"
MALFORMED_TOOL_ARGUMENTS = '{"path":"fixture.txt"'
ARGUMENT_ISOLATION_TOOL_ARGUMENTS = (
    {"path": READ_PATH, "startLine": 2, "endLine": 1},
    {"path": READ_PATH, "startLine": 3, "endLine": 1},
    {"path": READ_PATH, "startLine": 2, "endLine": 1},
)
SIGNATURE_ALTERNATION_TOOL_ARGUMENTS = {
    "path": SIGNATURE_ALTERNATION_READ_PATH,
    "startLine": 2,
    "endLine": 1,
}
SUCCESS_RESET_TOOL_ARGUMENTS = {"path": SUCCESS_RESET_READ_PATH}
REFRESH_GATE_NAMES = (
    "before-first-delta",
    "after-second-delta",
    "before-terminal",
    "before-tool-final-delta",
    "before-tool-terminal",
    "before-second-tool-execute",
    "goal-final-after-first-delta",
    "context-compaction-after-first-delta",
)


class MetricState:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._data = {
            "fakeRequests": [],
            "faviconFetches": [],
            "explorerRequests": [],
            "defaultOpenRequests": [],
            "chatRequests": [],
            "imageRequests": [],
            "imageRequestCompletions": [],
            "toolExecutions": [],
            "productionToolDelegations": 0,
            "productionEditProposalDelegations": 0,
            "productionEditApplyDelegations": 0,
            "productionEditWrites": 0,
            "productionEditBackups": 0,
            "productionEditConflictObservations": 0,
            "runCommandAttempts": [],
            "proposeEditProposalTimeline": [],
            "proposeEditApplyTimeline": [],
            "proposeEditWriteTimeline": [],
            "proposeEditBackupTimeline": [],
            "proposeEditConflictTimeline": [],
            "proposeEditThirdPartyTransitionAttempts": 0,
            "proposeEditThirdPartyTransitionWrites": 0,
            "proposeEditThirdPartyTransitionRejections": 0,
            "proposeEditThirdPartyTransitionTimeline": [],
            "signatureAlternationFixtureTimeline": [],
            "successResetFixtureTimeline": [],
            "unsafeToolRequests": 0,
            "modelGateWaits": 0,
            "modelCatalogGateTimeline": [],
            "modelRouteRequests": [],
            "refreshGateTimeline": [],
        }

    def append(self, key: str, value: dict) -> None:
        with self._lock:
            self._data[key].append(value)

    def increment(self, key: str) -> None:
        with self._lock:
            self._data[key] += 1

    def snapshot(self) -> dict:
        with self._lock:
            return deepcopy(self._data)


METRICS = MetricState()
MODEL_GATE = threading.Event()


class ImageBatchFixtureState:
    def __init__(self) -> None:
        self._condition = threading.Condition(threading.RLock())
        self._active = {}
        self._completed = {}

    def begin(self, kind: str, batch_index: int) -> int:
        with self._condition:
            active = int(self._active.get(kind) or 0) + 1
            self._active[kind] = active
            self._condition.notify_all()
            return active

    def wait_for_later_completion(self, kind: str, batch_index: int) -> None:
        if batch_index % 2:
            return
        with self._condition:
            completed = self._completed.setdefault(kind, set())
            if not self._condition.wait_for(
                lambda: batch_index + 1 in completed,
                timeout=15.0,
            ):
                raise RuntimeError("image batch fixture did not observe paired completion")

    def finish(self, kind: str, batch_index: int) -> None:
        with self._condition:
            self._completed.setdefault(kind, set()).add(int(batch_index))
            self._active[kind] = max(0, int(self._active.get(kind) or 0) - 1)
            self._condition.notify_all()


IMAGE_BATCH_FIXTURE = ImageBatchFixtureState()


class ModelRouteFixtureState:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._catalog_outage = False

    def set_catalog_outage(self, enabled: bool) -> dict:
        with self._lock:
            self._catalog_outage = bool(enabled)
            return {"catalogOutage": self._catalog_outage}

    def snapshot(self) -> dict:
        with self._lock:
            return {"catalogOutage": self._catalog_outage}


MODEL_ROUTE_FIXTURE = ModelRouteFixtureState()


class ModelCatalogGateState:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._armed = False
        self._reached = threading.Event()
        self._released = threading.Event()
        self._reached_at = 0
        self._released_at = 0

    @staticmethod
    def _now_ms() -> int:
        return time.time_ns() // 1_000_000

    def arm(self) -> None:
        with self._lock:
            self._armed = True
            self._reached = threading.Event()
            self._released = threading.Event()
            self._reached_at = 0
            self._released_at = 0
        METRICS.append("modelCatalogGateTimeline", {
            "event": "armed",
            "at": self._now_ms(),
        })

    def reach_and_wait(self, timeout: float = 15.0) -> bool:
        with self._lock:
            if not self._armed:
                return True
            if not self._reached_at:
                self._reached_at = self._now_ms()
            self._reached.set()
            reached_at = self._reached_at
            released = self._released
        METRICS.append("modelCatalogGateTimeline", {
            "event": "reached",
            "at": int(reached_at or 0),
        })
        continued = released.wait(timeout=timeout)
        METRICS.append("modelCatalogGateTimeline", {
            "event": "continued" if continued else "timed-out",
            "at": self._now_ms(),
        })
        return continued

    def wait_until_reached(self, timeout: float = 5.0) -> bool:
        return self._reached.wait(timeout=timeout)

    def release(self) -> None:
        with self._lock:
            if not self._released_at:
                self._released_at = self._now_ms()
            self._released.set()
            released_at = self._released_at
        METRICS.append("modelCatalogGateTimeline", {
            "event": "released",
            "at": int(released_at or 0),
        })

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "armed": bool(self._armed),
                "reached": bool(self._reached.is_set()),
                "released": bool(self._released.is_set()),
                "reachedAt": int(self._reached_at or 0),
                "releasedAt": int(self._released_at or 0),
            }


MODEL_CATALOG_GATE = ModelCatalogGateState()


class RefreshGateState:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._states = {
            name: {
                "reached": threading.Event(),
                "released": threading.Event(),
                "reachedAt": 0,
                "releasedAt": 0,
            }
            for name in REFRESH_GATE_NAMES
        }

    @staticmethod
    def _now_ms() -> int:
        return time.time_ns() // 1_000_000

    def reach_and_wait(self, name: str, timeout: float = 15.0) -> bool:
        state = self._states[name]
        with self._lock:
            if not state["reachedAt"]:
                state["reachedAt"] = self._now_ms()
            state["reached"].set()
        METRICS.append("refreshGateTimeline", {
            "event": "reached",
            "gate": name,
            "at": int(state["reachedAt"] or 0),
        })
        released = state["released"].wait(timeout=timeout)
        METRICS.append("refreshGateTimeline", {
            "event": "continued" if released else "timed-out",
            "gate": name,
            "at": self._now_ms(),
        })
        return released

    def release(self, name: str) -> None:
        state = self._states[name]
        with self._lock:
            if not state["releasedAt"]:
                state["releasedAt"] = self._now_ms()
            state["released"].set()
        METRICS.append("refreshGateTimeline", {
            "event": "released",
            "gate": name,
            "at": int(state["releasedAt"] or 0),
        })

    def release_all(self, exclude: set[str] | None = None) -> None:
        excluded = exclude or set()
        for name in REFRESH_GATE_NAMES:
            if name in excluded:
                continue
            self.release(name)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                name: {
                    "reached": bool(state["reached"].is_set()),
                    "released": bool(state["released"].is_set()),
                    "reachedAt": int(state["reachedAt"] or 0),
                    "releasedAt": int(state["releasedAt"] or 0),
                }
                for name, state in self._states.items()
            }


REFRESH_GATES = RefreshGateState()


def _message_text(message: dict) -> str:
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            str(item.get("text") or "")
            for item in content
            if isinstance(item, dict) and item.get("type") == "text"
        )
    return str(content or "")


def _questionnaire_scenario(
    messages: list,
    user_text: str,
    user_marker: str,
    tool_call_id: str,
    scenario_prefix: str,
) -> tuple[str, bool] | None:
    if user_marker not in user_text:
        return None
    has_receipt = any(
        isinstance(message, dict)
        and message.get("role") == "tool"
        and str(message.get("tool_call_id") or "") == tool_call_id
        for message in messages
    )
    return (
        f"{scenario_prefix}-final" if has_receipt else f"{scenario_prefix}-call",
        has_receipt,
    )


def _parallel_visual_protocol_projection(payload: dict) -> dict:
    messages = [
        message for message in (payload.get("messages") or [])
        if isinstance(message, dict)
    ]
    assistant_indexes = []
    for index, message in enumerate(messages):
        if message.get("role") != "assistant":
            continue
        ids = [
            str(call.get("id") or "")
            for call in (message.get("tool_calls") or [])
            if isinstance(call, dict)
        ]
        if ids == list(PARALLEL_VISUAL_PROTOCOL_CALL_IDS):
            assistant_indexes.append(index)
    tool_indexes = {
        call_id: [
            index for index, message in enumerate(messages)
            if message.get("role") == "tool"
            and str(message.get("tool_call_id") or "") == call_id
        ]
        for call_id in PARALLEL_VISUAL_PROTOCOL_CALL_IDS
    }
    visual_indexes = {}
    for path in PARALLEL_VISUAL_PROTOCOL_PATHS:
        visual_indexes[path] = [
            index for index, message in enumerate(messages)
            if message.get("role") == "user"
            and path in _message_text(message)
            and any(
                isinstance(part, dict) and part.get("type") == "image_url"
                for part in (
                    message.get("content")
                    if isinstance(message.get("content"), list)
                    else []
                )
            )
        ]
    assistant_index = assistant_indexes[0] if len(assistant_indexes) == 1 else -1
    ordered_tool_indexes = [
        tool_indexes[call_id][0]
        if len(tool_indexes[call_id]) == 1 else -1
        for call_id in PARALLEL_VISUAL_PROTOCOL_CALL_IDS
    ]
    ordered_visual_indexes = [
        visual_indexes[path][0]
        if len(visual_indexes[path]) == 1 else -1
        for path in PARALLEL_VISUAL_PROTOCOL_PATHS
    ]
    strict_order = (
        assistant_index >= 0
        and ordered_tool_indexes == [assistant_index + 1, assistant_index + 2]
        and ordered_visual_indexes[0] > ordered_tool_indexes[-1]
        and ordered_visual_indexes[1] > ordered_visual_indexes[0]
    )
    return {
        "assistantBatchCount": len(assistant_indexes),
        "toolResultCounts": [
            len(tool_indexes[call_id])
            for call_id in PARALLEL_VISUAL_PROTOCOL_CALL_IDS
        ],
        "visualCounts": [
            len(visual_indexes[path])
            for path in PARALLEL_VISUAL_PROTOCOL_PATHS
        ],
        "strictOrder": strict_order,
        "toolBlockRoles": (
            [messages[index]["role"] for index in range(
                assistant_index,
                min(len(messages), assistant_index + 5),
            )]
            if assistant_index >= 0 else []
        ),
    }


def _scenario_for(payload: dict) -> tuple[str, bool]:
    messages = payload.get("messages") or []
    user_text = ""
    user_texts = []
    has_tool_result = False
    completed_tool_call_ids = set()
    for message in messages:
        if not isinstance(message, dict):
            continue
        if message.get("role") == "user":
            user_text = _message_text(message)
            user_texts.append(user_text)
        if message.get("role") == "tool" or message.get("tool_call_id") in {
            TOOL_CALL_ID, INVALID_TOOL_CALL_ID, PARSE_ERROR_TOOL_CALL_ID,
            MISSING_PATH_TOOL_CALL_ID,
            EXECUTOR_RANGE_TOOL_CALL_ID,
            MISSING_FILE_TOOL_CALL_ID,
            *REPEATED_RANGE_FAILURE_TOOL_CALL_IDS,
            *ARGUMENT_ISOLATION_TOOL_CALL_IDS,
            *SIGNATURE_ALTERNATION_TOOL_CALL_IDS,
            *SUCCESS_RESET_TOOL_CALL_IDS,
            *MULTI_TOOL_CALL_IDS,
            QUESTIONNAIRE_TOOL_CALL_ID,
            LEGACY_QUESTIONNAIRE_TOOL_CALL_ID,
            MIXED_QUESTIONNAIRE_TOOL_CALL_ID,
            FIVE_QUESTIONNAIRE_TOOL_CALL_ID,
            TERMINAL_QUESTIONNAIRE_TOOL_CALL_ID,
            PROPOSE_EDIT_TOOL_CALL_ID,
            RUNTIME_RECOVERY_CALL_ID,
            SKILL_EVIDENCE_CALL_ID,
        }:
            has_tool_result = True
        if message.get("role") == "tool":
            completed_tool_call_ids.add(str(message.get("tool_call_id") or ""))
    joined_user_text = "\n".join(user_texts)
    if IMAGE_BATCH_PARTIAL_USER in joined_user_text:
        completed = IMAGE_BATCH_PARTIAL_CALL_ID in completed_tool_call_ids
        return (
            "image-batch-partial-final" if completed else "image-batch-partial-call",
            completed,
        )
    if IMAGE_BATCH_USER in joined_user_text:
        completed = IMAGE_BATCH_CALL_ID in completed_tool_call_ids
        return (
            "image-batch-final" if completed else "image-batch-call",
            completed,
        )
    if IMAGE_EDIT_UNSUPPORTED_USER in joined_user_text:
        image_edit_completed = IMAGE_EDIT_UNSUPPORTED_CALL_ID in completed_tool_call_ids
        image_edit_retry_completed = (
            IMAGE_EDIT_UNSUPPORTED_RETRY_CALL_ID in completed_tool_call_ids
        )
        return (
            "image-edit-unsupported-final" if image_edit_retry_completed
            else (
                "image-edit-unsupported-retry" if image_edit_completed
                else "image-edit-unsupported-call"
            ),
            image_edit_completed or image_edit_retry_completed,
        )
    if IMAGE_EDIT_USER in joined_user_text:
        image_edit_completed = IMAGE_EDIT_CALL_ID in completed_tool_call_ids
        return (
            "image-edit-final" if image_edit_completed else "image-edit-call",
            image_edit_completed,
        )
    if IMAGE_GENERATION_USER in joined_user_text:
        image_generation_completed = IMAGE_GENERATION_CALL_ID in completed_tool_call_ids
        return (
            "image-generation-final" if image_generation_completed else "image-generation-call",
            image_generation_completed,
        )
    if TRUSTED_ROUTE_USER in joined_user_text:
        return "trusted-model-route", has_tool_result
    if CONNECTION_ROUTE_USER in joined_user_text:
        return "connection-route", has_tool_result
    if TOOL_PROTOCOL_CONTINUE_USER in joined_user_text:
        return "tool-protocol-history", has_tool_result
    if TOOL_PROTOCOL_ERROR_USER in joined_user_text:
        return "tool-protocol-error", has_tool_result
    if RUNTIME_RECOVERY_USER in joined_user_text:
        recovery_text = "\n".join(
            _message_text(message)
            for message in messages
            if isinstance(message, dict) and message.get("role") == "system"
        )
        completed = any(
            isinstance(message, dict)
            and message.get("role") == "tool"
            and str(message.get("tool_call_id") or "") == RUNTIME_RECOVERY_CALL_ID
            for message in messages
        )
        if not completed:
            return "runtime-recovery-call", False
        if RUNTIME_RECOVERY_PARTIAL_TWO in recovery_text:
            return "runtime-recovery-final", True
        if RUNTIME_RECOVERY_PARTIAL_ONE in recovery_text:
            return "runtime-recovery-partial-two", True
        return "runtime-recovery-partial-one", True
    if SKILL_EVIDENCE_USER in joined_user_text:
        completed = any(
            isinstance(message, dict)
            and message.get("role") == "tool"
            and str(message.get("tool_call_id") or "") == SKILL_EVIDENCE_CALL_ID
            for message in messages
        )
        if completed:
            return "skill-evidence-final", True
        continued = any(
            isinstance(message, dict)
            and message.get("role") == "system"
            and "[Server-owned Skill evidence continuation]" in _message_text(message)
            for message in messages
        )
        return ("skill-evidence-call" if continued else "skill-evidence-candidate"), False
    if PARALLEL_VISUAL_PROTOCOL_USER in joined_user_text:
        completed = {
            str(message.get("tool_call_id") or "")
            for message in messages
            if isinstance(message, dict) and message.get("role") == "tool"
        } & set(PARALLEL_VISUAL_PROTOCOL_CALL_IDS)
        return (
            "parallel-visual-protocol-final"
            if len(completed) == len(PARALLEL_VISUAL_PROTOCOL_CALL_IDS)
            else "parallel-visual-protocol-call",
            bool(completed),
        )
    if any(
        isinstance(message, dict)
        and message.get("role") == "system"
        and "creating a context checkpoint" in _message_text(message).lower()
        for message in messages
    ):
        return "context-compaction", False
    if AUTO_COMPACTION_USER in joined_user_text:
        return "context-compaction-final", False
    if AUTO_COMPACTION_SEED in joined_user_text:
        return "context-compaction-seed", False
    if CONTEXT_CALIBRATION_USER in joined_user_text:
        return "context-calibration", False
    if (
        "goal_agent_continuation_v1" in joined_user_text
        and "H4_GOAL_V2_CONTINUATION" in joined_user_text
    ):
        completed = {
            str(message.get("tool_call_id") or "")
            for message in messages
            if isinstance(message, dict) and message.get("role") == "tool"
        } & set(GOAL_V2_CONTINUATION_NEXT_CALL_IDS)
        if len(completed) >= len(GOAL_V2_CONTINUATION_NEXT_CALL_IDS):
            return "goal-v2-continuation-next-final", True
        return f"goal-v2-continuation-next-call-{len(completed) + 1}", bool(completed)
    if GOAL_V2_CONTINUATION_USER in user_text:
        completed = {
            str(message.get("tool_call_id") or "")
            for message in messages
            if isinstance(message, dict) and message.get("role") == "tool"
        } & set(GOAL_V2_CONTINUATION_ROOT_CALL_IDS)
        if len(completed) >= len(GOAL_V2_CONTINUATION_ROOT_CALL_IDS):
            return "goal-v2-continuation-root-final", True
        return f"goal-v2-continuation-root-call-{len(completed) + 1}", bool(completed)
    if GOAL_V2_HARD_LIMIT_USER in user_text:
        completed = {
            str(message.get("tool_call_id") or "")
            for message in messages
            if isinstance(message, dict) and message.get("role") == "tool"
        } & set(GOAL_V2_HARD_LIMIT_CALL_IDS)
        return f"goal-v2-hard-limit-call-{len(completed) + 1}", bool(completed)
    if GOAL_V2_GATE_FAILURE_USER in user_text:
        return "goal-v2-gate-supplement-failure", False
    if GOAL_V2_CANCEL_USER in user_text:
        cancelled = any(
            isinstance(message, dict)
            and message.get("role") == "tool"
            and str(message.get("tool_call_id") or "") == GOAL_V2_CANCEL_CALL_ID
            for message in messages
        )
        return (
            "goal-v2-cancel-final" if cancelled else "goal-v2-cancel-call",
            cancelled,
        )
    if GOAL_V2_CANCEL_DRAFT_USER in user_text:
        return "goal-v2-cancel-draft-final", False
    for marker, prefix, call_ids in (
        (GOAL_V2_EXPLICIT_USER, "goal-v2-explicit", GOAL_V2_EXPLICIT_CALL_IDS),
        (GOAL_V2_AUTONOMOUS_COMPLETE_USER, "goal-v2-autonomous-complete", GOAL_V2_AUTONOMOUS_COMPLETE_CALL_IDS),
        (GOAL_V2_AUTONOMOUS_USER, "goal-v2-autonomous", GOAL_V2_AUTONOMOUS_CALL_IDS),
        (GOAL_V2_ACCEPT_SETUP_USER, "goal-v2-accept-setup", GOAL_V2_ACCEPT_SETUP_CALL_IDS),
        (GOAL_V2_GATE_SETUP_USER, "goal-v2-gate-setup", GOAL_V2_GATE_SETUP_CALL_IDS),
        (GOAL_V2_GATE_USER, "goal-v2-gate-complete", GOAL_V2_GATE_CALL_IDS),
        (GOAL_V2_GATE_RETRY_USER, "goal-v2-gate-complete", GOAL_V2_GATE_CALL_IDS),
    ):
        if marker not in user_text:
            continue
        completed = {
            str(message.get("tool_call_id") or "")
            for message in messages
            if isinstance(message, dict) and message.get("role") == "tool"
        } & set(call_ids)
        if len(completed) >= len(call_ids):
            return f"{prefix}-final", True
        return f"{prefix}-call-{len(completed) + 1}", bool(completed)
    queue_questionnaire_scenario = _questionnaire_scenario(
        messages,
        "\n".join(user_texts),
        QUEUE_QUESTIONNAIRE_USER,
        QUESTIONNAIRE_TOOL_CALL_ID,
        "queue-questionnaire",
    )
    if queue_questionnaire_scenario:
        if any(TIMING_QUEUE_USER in text for text in user_texts):
            return "queue-questionnaire-promoted", has_tool_result
        return queue_questionnaire_scenario
    for questionnaire_contract in (
        (
            LEGACY_QUESTIONNAIRE_USER,
            LEGACY_QUESTIONNAIRE_TOOL_CALL_ID,
            "legacy-questionnaire",
        ),
        (
            MIXED_QUESTIONNAIRE_USER,
            MIXED_QUESTIONNAIRE_TOOL_CALL_ID,
            "mixed-questionnaire",
        ),
        (
            FIVE_QUESTIONNAIRE_USER,
            FIVE_QUESTIONNAIRE_TOOL_CALL_ID,
            "five-questionnaire",
        ),
        (
            TERMINAL_QUESTIONNAIRE_USER,
            TERMINAL_QUESTIONNAIRE_TOOL_CALL_ID,
            "terminal-questionnaire",
        ),
        (QUESTIONNAIRE_USER, QUESTIONNAIRE_TOOL_CALL_ID, "questionnaire"),
    ):
        questionnaire_scenario = _questionnaire_scenario(
            messages, user_text, *questionnaire_contract,
        )
        if questionnaire_scenario:
            return questionnaire_scenario
    for user_marker, scenario_prefix in (
        (EDIT_AUTHORIZATION_APPROVE_USER, "edit-authorization-approve"),
        (EDIT_AUTHORIZATION_REJECT_USER, "edit-authorization-reject"),
        (EDIT_AUTHORIZATION_CONFLICT_USER, "edit-authorization-conflict"),
    ):
        if user_marker in user_text:
            return (
                f"{scenario_prefix}-final" if has_tool_result
                else f"{scenario_prefix}-call",
                has_tool_result,
            )
    if SUCCESS_RESET_USER in user_text:
        completed_calls = {
            str(message.get("tool_call_id") or "")
            for message in messages
            if isinstance(message, dict) and message.get("role") == "tool"
        } & set(SUCCESS_RESET_TOOL_CALL_IDS)
        receipt_count = len(completed_calls)
        if receipt_count >= len(SUCCESS_RESET_TOOL_CALL_IDS):
            return "success-reset-final", True
        return f"success-reset-call-{receipt_count + 1}", receipt_count > 0
    if SIGNATURE_ALTERNATION_USER in user_text:
        completed_calls = {
            str(message.get("tool_call_id") or "")
            for message in messages
            if isinstance(message, dict) and message.get("role") == "tool"
        } & set(SIGNATURE_ALTERNATION_TOOL_CALL_IDS)
        receipt_count = len(completed_calls)
        if receipt_count >= len(SIGNATURE_ALTERNATION_TOOL_CALL_IDS):
            return "signature-alternation-final", True
        return f"signature-alternation-call-{receipt_count + 1}", receipt_count > 0
    if ARGUMENT_ISOLATION_USER in user_text:
        completed_calls = {
            str(message.get("tool_call_id") or "")
            for message in messages
            if isinstance(message, dict) and message.get("role") == "tool"
        } & set(ARGUMENT_ISOLATION_TOOL_CALL_IDS)
        receipt_count = len(completed_calls)
        if receipt_count >= len(ARGUMENT_ISOLATION_TOOL_CALL_IDS):
            return "argument-isolation-final", True
        return f"argument-isolation-call-{receipt_count + 1}", receipt_count > 0
    if FORCED_FINAL_MODEL_FAILURE_USER in user_text:
        completed_calls = {
            str(message.get("tool_call_id") or "")
            for message in messages
            if isinstance(message, dict) and message.get("role") == "tool"
        } & set(REPEATED_RANGE_FAILURE_TOOL_CALL_IDS)
        receipt_count = len(completed_calls)
        if receipt_count >= len(REPEATED_RANGE_FAILURE_TOOL_CALL_IDS):
            return "forced-final-model-failure-final", True
        return f"forced-final-model-failure-call-{receipt_count + 1}", receipt_count > 0
    if FORCED_FINAL_UNUSABLE_TOOL_USER in user_text:
        completed_calls = {
            str(message.get("tool_call_id") or "")
            for message in messages
            if isinstance(message, dict) and message.get("role") == "tool"
        } & set(REPEATED_RANGE_FAILURE_TOOL_CALL_IDS)
        receipt_count = len(completed_calls)
        if receipt_count >= len(REPEATED_RANGE_FAILURE_TOOL_CALL_IDS):
            return "forced-final-unusable-tool-final", True
        return f"forced-final-unusable-tool-call-{receipt_count + 1}", receipt_count > 0
    if REPEATED_RANGE_FAILURE_USER in user_text:
        completed_calls = {
            str(message.get("tool_call_id") or "")
            for message in messages
            if isinstance(message, dict) and message.get("role") == "tool"
        } & set(REPEATED_RANGE_FAILURE_TOOL_CALL_IDS)
        receipt_count = len(completed_calls)
        if receipt_count >= len(REPEATED_RANGE_FAILURE_TOOL_CALL_IDS):
            return "repeated-range-failure-final", True
        return f"repeated-range-failure-call-{receipt_count + 1}", receipt_count > 0
    if PARALLEL_FAILURE_FOLLOWUP_USER in user_text:
        return "parallel-failure-followup", has_tool_result
    if PARALLEL_FAILURE_USER in user_text:
        return "parallel-model-failure", has_tool_result
    if INVALID_TOOL_USER in user_text:
        return ("invalid-tool-final" if has_tool_result else "invalid-tool-call", has_tool_result)
    if PARSE_ERROR_TOOL_USER in user_text:
        return (
            "parse-error-tool-final" if has_tool_result else "parse-error-tool-call",
            has_tool_result,
        )
    if MISSING_PATH_TOOL_USER in user_text:
        return (
            "missing-path-tool-final" if has_tool_result else "missing-path-tool-call",
            has_tool_result,
        )
    if EXECUTOR_RANGE_USER in user_text:
        return (
            "executor-range-final" if has_tool_result else "executor-range-call",
            has_tool_result,
        )
    if MISSING_FILE_USER in user_text:
        return (
            "missing-file-final" if has_tool_result else "missing-file-call",
            has_tool_result,
        )
    if MULTI_TOOL_USER in user_text:
        return ("multi-tool-detail-final" if has_tool_result else "multi-tool-detail-call", has_tool_result)
    if TOOL_DETAILS_USER in user_text:
        return ("tool-detail-final" if has_tool_result else "tool-detail-call", has_tool_result)
    if TOOL_USER in user_text:
        return ("tool-final" if has_tool_result else "tool-call", has_tool_result)
    if STREAM_USER in user_text:
        return "stream-refresh", has_tool_result
    if TIFF_IMAGE_USER in user_text:
        return "tiff-image", has_tool_result
    if TIMING_PARALLEL_USER in user_text:
        return "timing-parallel", has_tool_result
    if TIMING_QUEUE_USER in user_text:
        return "timing-queue", has_tool_result
    if TIMING_MAIN_USER in user_text:
        return "timing-main", has_tool_result
    if CLASSIC_USER in user_text:
        return "classic-text", has_tool_result
    return "plain-text", has_tool_result


def _detached_edit_artifact_count(payload: dict) -> int:
    messages = payload.get("messages")
    messages = messages if isinstance(messages, list) else []
    serialized_messages = json.dumps(
        messages,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    artifacts = (
        EDIT_AUTHORIZATION_APPROVE_USER,
        EDIT_AUTHORIZATION_STAGE,
        EDIT_AUTHORIZATION_APPROVE_FINAL,
        PROPOSE_EDIT_TOOL_CALL_ID,
        PROPOSE_EDIT_PATH,
        PROPOSE_EDIT_OLD_TEXT,
        PROPOSE_EDIT_NEW_TEXT,
    )
    return sum(serialized_messages.count(artifact) for artifact in artifacts)


def _parallel_failure_followup_context_projection(payload: dict) -> dict:
    messages = [
        message
        for message in (payload.get("messages") or [])
        if isinstance(message, dict)
    ]
    detached_state_keys = {
        "backgroundDispatch", "backgroundJobId", "detached", "detachedFromMain", "jobId",
    }
    mainline_kinds = []
    unclassified_non_system = 0
    stage_tool_calls = []
    matching_receipts = []

    for message in messages:
        role = str(message.get("role") or "")
        text = _message_text(message)
        kind = ""
        if role == "user" and TOOL_DETAILS_USER in text:
            kind = "main-user"
        elif role == "assistant" and TOOL_DETAILS_STAGE in text:
            kind = "main-tool-call"
            for tool_call in message.get("tool_calls") or []:
                if not isinstance(tool_call, dict):
                    continue
                function = tool_call.get("function")
                function = function if isinstance(function, dict) else {}
                try:
                    arguments = json.loads(str(function.get("arguments") or "{}"))
                except (TypeError, ValueError, json.JSONDecodeError):
                    arguments = {}
                stage_tool_calls.append({
                    "matchesKnownId": str(tool_call.get("id") or "") == TOOL_CALL_ID,
                    "name": str(function.get("name") or ""),
                    "arguments": arguments if isinstance(arguments, dict) else {},
                })
        elif role == "tool" and str(message.get("tool_call_id") or "") == TOOL_CALL_ID:
            kind = "main-tool-receipt"
            matching_receipts.append(_message_text(message))
        elif role == "assistant" and TOOL_DETAILS_FINAL in text:
            kind = "main-final"
        elif role == "user" and PARALLEL_FAILURE_FOLLOWUP_USER in text:
            kind = "followup-user"
        elif role != "system":
            unclassified_non_system += 1
        if kind:
            mainline_kinds.append({"role": role, "kind": kind})

    receipt_text = matching_receipts[0] if len(matching_receipts) == 1 else ""
    matching_tool_calls = [
        tool_call for tool_call in stage_tool_calls if tool_call["matchesKnownId"]
    ]
    matching_tool_call = matching_tool_calls[0] if len(matching_tool_calls) == 1 else {}
    return {
        "followupMarkerCount": sum(
            1
            for message in messages
            if message.get("role") == "user"
            and PARALLEL_FAILURE_FOLLOWUP_USER in _message_text(message)
        ),
        "detachedUserMarkerCount": sum(
            1
            for message in messages
            if message.get("role") == "user"
            and PARALLEL_FAILURE_USER in _message_text(message)
        ),
        "detachedErrorMarkerCount": sum(
            1
            for message in messages
            if message.get("role") == "assistant"
            and PARALLEL_FAILURE_ERROR in _message_text(message)
        ),
        "detachedStateFieldCount": sum(
            1
            for message in messages
            if detached_state_keys.intersection(message)
            or (
                isinstance(message.get("meta"), dict)
                and detached_state_keys.intersection(message["meta"])
            )
        ),
        "mainlineKinds": mainline_kinds,
        "unclassifiedNonSystemCount": unclassified_non_system,
        "toolCall": {
            "count": len(stage_tool_calls),
            "matchingIdCount": len(matching_tool_calls),
            "readFile": str(matching_tool_call.get("name") or "") == "read_file",
            "pathMatchesFixture": str(
                (matching_tool_call.get("arguments") or {}).get("path") or ""
            ) == READ_PATH,
            "receiptLinked": len(matching_tool_calls) == 1 and len(matching_receipts) == 1,
        },
        "toolReceipt": {
            "count": len(matching_receipts),
            "contentPresent": bool(receipt_text.strip()),
            "pathMatchesFixture": READ_PATH in receipt_text,
            "contentMatchesFixture": FIXTURE_CONTENT.strip() in receipt_text,
            "sizeMatchesFixture": "26 B" in receipt_text,
        },
    }


def _queue_questionnaire_context_projection(payload: dict) -> dict:
    marker_contract = (
        ("questionnaire-user", "user", QUEUE_QUESTIONNAIRE_USER),
        ("questionnaire-final", "assistant", QUEUE_QUESTIONNAIRE_FINAL),
        ("queued-user", "user", TIMING_QUEUE_USER),
    )
    marker_order = []
    marker_positions = {alias: [] for alias, _, _ in marker_contract}
    for message_index, message in enumerate(payload.get("messages") or []):
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "")
        text = _message_text(message)
        for alias, expected_role, marker in marker_contract:
            if role == expected_role and marker in text:
                marker_order.append(alias)
                marker_positions[alias].append(message_index)

    questionnaire_final_positions = marker_positions["questionnaire-final"]
    queued_user_positions = marker_positions["queued-user"]
    return {
        "questionnaireUserCount": len(marker_positions["questionnaire-user"]),
        "questionnaireFinalCount": len(questionnaire_final_positions),
        "queuedUserCount": len(queued_user_positions),
        "markerOrder": marker_order,
        "mainFinalPrecedesQueuedUser": (
            len(questionnaire_final_positions) == 1
            and len(queued_user_positions) == 1
            and questionnaire_final_positions[0] < queued_user_positions[0]
        ),
    }


def _questionnaire_call_contract(scenario: str) -> tuple[str, dict]:
    if scenario in ("questionnaire-call", "queue-questionnaire-call"):
        return QUESTIONNAIRE_TOOL_CALL_ID, {
            "title": QUESTIONNAIRE_TITLE,
            "reason": QUESTIONNAIRE_REASON,
            "questions": [{
                "id": QUESTIONNAIRE_QUESTION_ID,
                "prompt": QUESTIONNAIRE_PROMPT,
                "type": "single",
                "required": True,
                "allowOther": True,
                "options": list(QUESTIONNAIRE_OPTIONS),
            }],
        }
    if scenario == "mixed-questionnaire-call":
        return MIXED_QUESTIONNAIRE_TOOL_CALL_ID, {
            "title": MIXED_QUESTIONNAIRE_TITLE,
            "reason": MIXED_QUESTIONNAIRE_REASON,
            "questions": [
                {
                    "id": MIXED_QUESTIONNAIRE_SINGLE_ID,
                    "prompt": MIXED_QUESTIONNAIRE_SINGLE_PROMPT,
                    "type": "single",
                    "required": True,
                    "allowOther": True,
                    "options": list(MIXED_QUESTIONNAIRE_SINGLE_OPTIONS),
                },
                {
                    "id": MIXED_QUESTIONNAIRE_MULTIPLE_ID,
                    "prompt": MIXED_QUESTIONNAIRE_MULTIPLE_PROMPT,
                    "type": "multiple",
                    "required": True,
                    "allowOther": True,
                    "options": list(MIXED_QUESTIONNAIRE_MULTIPLE_OPTIONS),
                },
                {
                    "id": MIXED_QUESTIONNAIRE_TEXT_ID,
                    "prompt": MIXED_QUESTIONNAIRE_TEXT_PROMPT,
                    "type": "single",
                    "required": True,
                    "allowOther": True,
                    "options": list(MIXED_QUESTIONNAIRE_TEXT_OPTIONS),
                },
            ],
        }
    if scenario == "five-questionnaire-call":
        return FIVE_QUESTIONNAIRE_TOOL_CALL_ID, {
            "title": FIVE_QUESTIONNAIRE_TITLE,
            "reason": FIVE_QUESTIONNAIRE_REASON,
            "questions": list(FIVE_QUESTIONNAIRE_QUESTIONS),
        }
    if scenario == "terminal-questionnaire-call":
        return TERMINAL_QUESTIONNAIRE_TOOL_CALL_ID, {
            "title": TERMINAL_QUESTIONNAIRE_TITLE,
            "reason": TERMINAL_QUESTIONNAIRE_REASON,
            "questions": [
                {
                    "id": TERMINAL_QUESTIONNAIRE_FIRST_ID,
                    "prompt": "What should Code find?",
                    "type": "single",
                    "required": True,
                    "allowOther": True,
                    "options": list(TERMINAL_QUESTIONNAIRE_OPTIONS),
                },
                {
                    "id": TERMINAL_QUESTIONNAIRE_SECOND_ID,
                    "prompt": "Which URL should Code use?",
                    "type": "single",
                    "required": True,
                    "allowOther": True,
                    "options": list(TERMINAL_QUESTIONNAIRE_OPTIONS),
                },
            ],
        }
    raise ValueError(f"unsupported questionnaire scenario: {scenario}")


def _questionnaire_receipt_result(
    payload: dict, tool_call_id: str,
) -> tuple[list, bool, dict]:
    receipts = [
        message
        for message in (payload.get("messages") or [])
        if isinstance(message, dict)
        and message.get("role") == "tool"
        and str(message.get("tool_call_id") or "") == tool_call_id
    ]
    parsed = False
    result = {}
    if len(receipts) == 1:
        try:
            candidate = json.loads(str(receipts[0].get("content") or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            candidate = {}
        if isinstance(candidate, dict):
            result = candidate
            parsed = True
    return receipts, parsed, result


def _markers_once_in_order(value: object, markers: tuple[str, ...]) -> bool:
    text = str(value or "")
    positions = [text.find(marker) for marker in markers]
    return (
        all(position >= 0 for position in positions)
        and positions == sorted(positions)
        and all(text.count(marker) == 1 for marker in markers)
    )


def _questionnaire_receipt_projection(payload: dict) -> dict:
    receipts, parsed, result = _questionnaire_receipt_result(
        payload, QUESTIONNAIRE_TOOL_CALL_ID,
    )
    answers = result.get("answers") if isinstance(result.get("answers"), list) else []
    answer = answers[0] if len(answers) == 1 and isinstance(answers[0], dict) else {}
    values = answer.get("values") if isinstance(answer.get("values"), list) else []
    summary = str(result.get("summary") or "")
    expected_request_id = f"user-input-{QUESTIONNAIRE_TOOL_CALL_ID}"
    return {
        "receiptCount": len(receipts),
        "parseable": parsed,
        "nameMatches": len(receipts) == 1
        and str(receipts[0].get("name") or "") == "request_user_input",
        "ok": result.get("ok") is True,
        "actionMatches": str(result.get("action") or "") == "request_user_input",
        "requestIdMatches": str(result.get("requestId") or "") == expected_request_id,
        "titleMatches": str(result.get("title") or "") == QUESTIONNAIRE_TITLE,
        "answerCount": len(answers),
        "questionIdMatches": str(answer.get("id") or "") == QUESTIONNAIRE_QUESTION_ID,
        "promptMatches": str(answer.get("prompt") or "") == QUESTIONNAIRE_PROMPT,
        "singleChoice": str(answer.get("type") or "") == "single",
        "resolved": str(answer.get("status") or "") == "resolved",
        "valueCount": len(values),
        "selectedValueMatches": values == [QUESTIONNAIRE_SELECTED_OPTION["value"]],
        "answerLabelMatches": str(answer.get("answer") or "")
        == QUESTIONNAIRE_SELECTED_OPTION["label"],
        "otherEmpty": not str(answer.get("other") or ""),
        "summaryMatches": QUESTIONNAIRE_PROMPT in summary
        and QUESTIONNAIRE_SELECTED_OPTION["label"] in summary,
    }


def _edit_authorization_receipt_projection(payload: dict, *, approved: bool) -> dict:
    receipts, parsed, result = _questionnaire_receipt_result(
        payload, PROPOSE_EDIT_TOOL_CALL_ID,
    )
    expected_action = "apply_edit" if approved else "propose_edit"
    return {
        "decision": "approved" if approved else "rejected",
        "receiptCount": len(receipts),
        "parseable": parsed,
        "nameMatches": len(receipts) == 1
        and str(receipts[0].get("name") or "") == "propose_edit",
        "ok": result.get("ok") is True,
        "actionMatches": str(result.get("action") or "") == expected_action,
        "pathMatches": str(result.get("path") or "") == PROPOSE_EDIT_PATH,
        "applied": result.get("applied") is True,
        "rejected": result.get("rejected") is True,
        "replayed": result.get("replayed") is True,
        "backupPresent": bool(str(result.get("backupPath") or "")),
    }


def _edit_authorization_conflict_receipt_projection(payload: dict) -> dict:
    receipts, parsed, result = _questionnaire_receipt_result(
        payload, PROPOSE_EDIT_TOOL_CALL_ID,
    )
    return {
        "decision": "approved",
        "receiptCount": len(receipts),
        "parseable": parsed,
        "nameMatches": len(receipts) == 1
        and str(receipts[0].get("name") or "") == "propose_edit",
        "ok": result.get("ok") is True,
        "actionMatches": str(result.get("action") or "") == "apply_edit",
        "pathMatches": str(result.get("path") or "") == PROPOSE_EDIT_PATH,
        "applied": result.get("applied") is True,
        "rejected": result.get("rejected") is True,
        "replayed": result.get("replayed") is True,
        "backupPresent": bool(str(result.get("backupPath") or "")),
        "conflict": result.get("conflict") is True,
        "errorPresent": bool(str(result.get("error") or "")),
    }


def _mixed_questionnaire_receipt_projection(payload: dict) -> dict:
    receipts, parsed, result = _questionnaire_receipt_result(
        payload, MIXED_QUESTIONNAIRE_TOOL_CALL_ID,
    )
    answers = result.get("answers") if isinstance(result.get("answers"), list) else []
    answer_by_id = {
        str(answer.get("id") or ""): answer
        for answer in answers
        if isinstance(answer, dict)
    }
    single = answer_by_id.get(MIXED_QUESTIONNAIRE_SINGLE_ID, {})
    multiple = answer_by_id.get(MIXED_QUESTIONNAIRE_MULTIPLE_ID, {})
    text_answer = answer_by_id.get(MIXED_QUESTIONNAIRE_TEXT_ID, {})
    single_values = (
        single.get("values") if isinstance(single.get("values"), list) else []
    )
    multiple_values = (
        multiple.get("values")
        if isinstance(multiple.get("values"), list)
        else []
    )
    custom_values = (
        text_answer.get("values")
        if isinstance(text_answer.get("values"), list)
        else []
    )
    multiple_answer_markers = (
        MIXED_QUESTIONNAIRE_MULTIPLE_OPTIONS[0]["label"],
        MIXED_QUESTIONNAIRE_MULTIPLE_OPTIONS[2]["label"],
        MIXED_QUESTIONNAIRE_OTHER,
    )
    summary_markers = (
        MIXED_QUESTIONNAIRE_SINGLE_PROMPT,
        MIXED_QUESTIONNAIRE_SINGLE_OPTIONS[1]["label"],
        MIXED_QUESTIONNAIRE_MULTIPLE_PROMPT,
        *multiple_answer_markers,
        MIXED_QUESTIONNAIRE_TEXT_PROMPT,
        MIXED_QUESTIONNAIRE_TEXT_ANSWER,
    )
    expected_ids = [
        MIXED_QUESTIONNAIRE_SINGLE_ID,
        MIXED_QUESTIONNAIRE_MULTIPLE_ID,
        MIXED_QUESTIONNAIRE_TEXT_ID,
    ]
    return {
        "receiptCount": len(receipts),
        "parseable": parsed,
        "nameMatches": len(receipts) == 1
        and str(receipts[0].get("name") or "") == "request_user_input",
        "ok": result.get("ok") is True,
        "actionMatches": str(result.get("action") or "") == "request_user_input",
        "requestIdMatches": str(result.get("requestId") or "")
        == f"user-input-{MIXED_QUESTIONNAIRE_TOOL_CALL_ID}",
        "titleMatches": str(result.get("title") or "")
        == MIXED_QUESTIONNAIRE_TITLE,
        "answerCount": len(answers),
        "answerOrderMatches": [
            str(answer.get("id") or "")
            for answer in answers
            if isinstance(answer, dict)
        ] == expected_ids,
        "allResolved": all(
            str(answer_by_id.get(question_id, {}).get("status") or "")
            == "resolved"
            for question_id in expected_ids
        ),
        "typesMatch": [
            str(answer_by_id.get(question_id, {}).get("type") or "")
            for question_id in expected_ids
        ] == ["single", "multiple", "single"],
        "promptsMatch": [
            str(answer_by_id.get(question_id, {}).get("prompt") or "")
            for question_id in expected_ids
        ] == [
            MIXED_QUESTIONNAIRE_SINGLE_PROMPT,
            MIXED_QUESTIONNAIRE_MULTIPLE_PROMPT,
            MIXED_QUESTIONNAIRE_TEXT_PROMPT,
        ],
        "singleValueCount": len(single_values),
        "singleSelectionMatches": single_values
        == [MIXED_QUESTIONNAIRE_SINGLE_OPTIONS[1]["value"]],
        "singleAnswerMatches": str(single.get("answer") or "")
        == MIXED_QUESTIONNAIRE_SINGLE_OPTIONS[1]["label"],
        "singleOtherEmpty": not str(single.get("other") or ""),
        "multipleValueCount": len(multiple_values),
        "multipleSelectionsMatch": multiple_values == [
            MIXED_QUESTIONNAIRE_MULTIPLE_OPTIONS[0]["value"],
            MIXED_QUESTIONNAIRE_MULTIPLE_OPTIONS[2]["value"],
        ],
        "multipleOtherMatches": str(multiple.get("other") or "")
        == MIXED_QUESTIONNAIRE_OTHER,
        "multipleAnswerMarkersMatch": _markers_once_in_order(
            multiple.get("answer"), multiple_answer_markers,
        ),
        "customValueCount": len(custom_values),
        "customTextAbsent": text_answer.get("text") is None,
        "customOtherMatches": str(text_answer.get("other") or "")
        == MIXED_QUESTIONNAIRE_TEXT_ANSWER,
        "customAnswerMatches": str(text_answer.get("answer") or "")
        == MIXED_QUESTIONNAIRE_TEXT_ANSWER,
        "summaryMarkersMatch": _markers_once_in_order(
            result.get("summary"), summary_markers,
        ),
    }


def _tiff_model_image_projection(payload: dict) -> dict:
    from PIL import Image

    images = []
    for message in payload.get("messages") or []:
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict) or part.get("type") != "image_url":
                continue
            image_url = part.get("image_url")
            value = image_url.get("url") if isinstance(image_url, dict) else image_url
            value = str(value or "")
            prefix = "data:image/png;base64,"
            if not value.startswith(prefix):
                images.append({"mime": "unexpected", "png": False, "width": 0, "height": 0})
                continue
            try:
                raw = base64.b64decode(value[len(prefix):], validate=True)
                with Image.open(io.BytesIO(raw)) as image:
                    width, height = image.size
                    image_format = image.format
            except Exception:
                raw = b""
                width, height = 0, 0
                image_format = ""
            images.append({
                "mime": "image/png",
                "png": raw.startswith(bytes.fromhex("89504e470d0a1a0a")) and image_format == "PNG",
                "width": width,
                "height": height,
            })
    return {
        "count": len(images),
        "images": images,
        "recognized": len(images) == 1 and images[0] == {
            "mime": "image/png",
            "png": True,
            "width": 18,
            "height": 12,
        },
    }


def _invalid_tool_receipt_projection(payload: dict) -> dict | None:
    for message in payload.get("messages") or []:
        if not isinstance(message, dict) or message.get("role") != "tool":
            continue
        if str(message.get("tool_call_id") or "") != INVALID_TOOL_CALL_ID:
            continue
        try:
            result = json.loads(str(message.get("content") or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            result = {}
        if not isinstance(result, dict):
            result = {}
        return {
            "role": "tool",
            "toolCallId": "tool-1",
            "name": str(message.get("name") or ""),
            "ok": result.get("ok"),
            "action": str(result.get("action") or ""),
            "errorCode": str(result.get("errorCode") or ""),
            "errorPresent": bool(str(result.get("error") or "").strip()),
            "failureCount": int(result.get("failureCount") or 0),
            "fieldErrors": [
                {
                    "field": str(item.get("field") or ""),
                    "reason": str(item.get("reason") or ""),
                }
                for item in (result.get("fieldErrors") or [])
                if isinstance(item, dict)
            ],
        }
    return None


def _parse_error_tool_receipt_projection(payload: dict) -> dict | None:
    for message in payload.get("messages") or []:
        if not isinstance(message, dict) or message.get("role") != "tool":
            continue
        if str(message.get("tool_call_id") or "") != PARSE_ERROR_TOOL_CALL_ID:
            continue
        try:
            result = json.loads(str(message.get("content") or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            result = {}
        if not isinstance(result, dict):
            result = {}
        return {
            "role": "tool",
            "toolCallId": "tool-1",
            "name": str(message.get("name") or ""),
            "ok": result.get("ok"),
            "action": str(result.get("action") or ""),
            "errorCode": str(result.get("errorCode") or ""),
            "errorPresent": bool(str(result.get("error") or "").strip()),
            "failureCount": int(result.get("failureCount") or 0),
            "fieldErrors": [
                {
                    "field": str(item.get("field") or ""),
                    "reason": str(item.get("reason") or ""),
                }
                for item in (result.get("fieldErrors") or [])
                if isinstance(item, dict)
            ],
        }
    return None


def _missing_path_tool_receipt_projection(payload: dict) -> dict | None:
    for message in payload.get("messages") or []:
        if not isinstance(message, dict) or message.get("role") != "tool":
            continue
        if str(message.get("tool_call_id") or "") != MISSING_PATH_TOOL_CALL_ID:
            continue
        try:
            result = json.loads(str(message.get("content") or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            result = {}
        if not isinstance(result, dict):
            result = {}
        return {
            "role": "tool",
            "toolCallId": "tool-1",
            "name": str(message.get("name") or ""),
            "ok": result.get("ok"),
            "action": str(result.get("action") or ""),
            "errorCode": str(result.get("errorCode") or ""),
            "errorPresent": bool(str(result.get("error") or "").strip()),
            "failureCount": int(result.get("failureCount") or 0),
            "fieldErrors": [
                {
                    "field": str(item.get("field") or ""),
                    "reason": str(item.get("reason") or ""),
                }
                for item in (result.get("fieldErrors") or [])
                if isinstance(item, dict)
            ],
        }
    return None


def _executor_range_receipt_projection(payload: dict) -> dict | None:
    for message in payload.get("messages") or []:
        if not isinstance(message, dict) or message.get("role") != "tool":
            continue
        if str(message.get("tool_call_id") or "") != EXECUTOR_RANGE_TOOL_CALL_ID:
            continue
        try:
            result = json.loads(str(message.get("content") or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            result = {}
        if not isinstance(result, dict):
            result = {}
        error = str(result.get("error") or "")
        return {
            "role": "tool",
            "toolCallId": "tool-1",
            "name": str(message.get("name") or ""),
            "ok": result.get("ok"),
            "action": str(result.get("action") or ""),
            "errorCodePresent": "errorCode" in result,
            "errorPresent": bool(error.strip()),
            "startLineMentioned": "startLine" in error,
            "endLineMentioned": "endLine" in error,
            "failureCount": int(result.get("failureCount") or 0),
            "fieldErrorsPresent": "fieldErrors" in result,
            "retryBlocked": bool(result.get("retryBlocked")),
            "retryLimitReached": bool(result.get("retryLimitReached")),
        }
    return None


def _range_failure_receipt_projection(
    payload: dict, tool_call_ids: tuple[str, ...], *, include_missing_file_error=False,
) -> list[dict]:
    aliases = {
        tool_call_id: f"tool-{index + 1}"
        for index, tool_call_id in enumerate(tool_call_ids)
    }
    projections = []
    for message in payload.get("messages") or []:
        if not isinstance(message, dict) or message.get("role") != "tool":
            continue
        tool_call_id = str(message.get("tool_call_id") or "")
        alias = aliases.get(tool_call_id)
        if not alias:
            continue
        try:
            result = json.loads(str(message.get("content") or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            result = {}
        if not isinstance(result, dict):
            result = {}
        error = str(result.get("error") or "")
        projection = {
            "role": "tool",
            "toolCallId": alias,
            "name": str(message.get("name") or ""),
            "ok": result.get("ok"),
            "action": str(result.get("action") or ""),
            "errorCode": str(result.get("errorCode") or ""),
            "errorPresent": bool(error.strip()),
            "startLineMentioned": "startLine" in error,
            "endLineMentioned": "endLine" in error,
            "failureCount": int(result.get("failureCount") or 0),
            "fieldErrorsPresent": "fieldErrors" in result,
            "retryBlocked": bool(result.get("retryBlocked")),
            "retryLimitReached": bool(result.get("retryLimitReached")),
        }
        if include_missing_file_error:
            projection["missingFileError"] = error == "文件不存在"
        projections.append(projection)
    return projections


def _repeated_range_failure_receipt_projection(payload: dict) -> list[dict]:
    return _range_failure_receipt_projection(
        payload, REPEATED_RANGE_FAILURE_TOOL_CALL_IDS,
    )


def _argument_isolation_receipt_projection(payload: dict) -> list[dict]:
    return _range_failure_receipt_projection(
        payload, ARGUMENT_ISOLATION_TOOL_CALL_IDS,
    )


def _signature_alternation_receipt_projection(payload: dict) -> list[dict]:
    return _range_failure_receipt_projection(
        payload,
        SIGNATURE_ALTERNATION_TOOL_CALL_IDS,
        include_missing_file_error=True,
    )


def _success_reset_receipt_projection(payload: dict) -> list[dict]:
    aliases = {
        tool_call_id: f"tool-{index + 1}"
        for index, tool_call_id in enumerate(SUCCESS_RESET_TOOL_CALL_IDS)
    }
    projections = []
    for message in payload.get("messages") or []:
        if not isinstance(message, dict) or message.get("role") != "tool":
            continue
        tool_call_id = str(message.get("tool_call_id") or "")
        alias = aliases.get(tool_call_id)
        if not alias:
            continue
        try:
            result = json.loads(str(message.get("content") or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            result = {}
        if not isinstance(result, dict):
            result = {}
        error = str(result.get("error") or "")
        content = str(result.get("content") or "")
        failure_count_present = "failureCount" in result
        projection = {
            "role": "tool",
            "toolCallId": alias,
            "name": str(message.get("name") or ""),
            "ok": result.get("ok"),
            "action": str(result.get("action") or ""),
            "path": str(result.get("path") or ""),
            "contentSha256": (
                hashlib.sha256(content.encode("utf-8")).hexdigest()
                if "content" in result else ""
            ),
            "size": int(result.get("size") or 0) if "size" in result else None,
            "truncated": bool(result.get("truncated")) if "truncated" in result else None,
            "lineRangePresent": "lineRange" in result,
            "lineRange": result.get("lineRange") if "lineRange" in result else None,
            "errorCodePresent": "errorCode" in result,
            "errorPresent": bool(error.strip()),
            "missingFileError": error == "文件不存在",
            "failureCountPresent": failure_count_present,
            "retryBlocked": bool(result.get("retryBlocked")),
            "retryLimitReached": bool(result.get("retryLimitReached")),
        }
        if failure_count_present:
            projection["failureCount"] = int(result.get("failureCount") or 0)
        projections.append(projection)
    return projections


def _missing_file_receipt_projection(payload: dict) -> dict | None:
    for message in payload.get("messages") or []:
        if not isinstance(message, dict) or message.get("role") != "tool":
            continue
        if str(message.get("tool_call_id") or "") != MISSING_FILE_TOOL_CALL_ID:
            continue
        try:
            result = json.loads(str(message.get("content") or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            result = {}
        if not isinstance(result, dict):
            result = {}
        error = str(result.get("error") or "")
        return {
            "role": "tool",
            "toolCallId": "tool-1",
            "name": str(message.get("name") or ""),
            "ok": result.get("ok"),
            "action": str(result.get("action") or ""),
            "errorCodePresent": "errorCode" in result,
            "codePresent": "code" in result,
            "missingFileError": error == "文件不存在",
            "failureCount": int(result.get("failureCount") or 0),
            "fieldErrorsPresent": "fieldErrors" in result,
            "retryBlocked": bool(result.get("retryBlocked")),
            "retryLimitReached": bool(result.get("retryLimitReached")),
        }
    return None


def _chunk(delta: dict, finish_reason=None, usage=None) -> dict:
    frame = {
        "id": "h4-chat",
        "object": "chat.completion.chunk",
        "created": 1_700_000_000,
        "model": MODEL_ID,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }
    if usage is not None:
        frame["usage"] = usage
    return frame


def _sse_payload(frames: list[dict]) -> bytes:
    lines = [f"data: {json.dumps(frame, separators=(',', ':'))}\n\n" for frame in frames]
    lines.append("data: [DONE]\n\n")
    return "".join(lines).encode("utf-8")


def _synthetic_key_group(authorization: str) -> str:
    value = str(authorization or "")
    if value == f"Bearer {TRUSTED_ROUTE_PRIMARY_KEY}":
        return "primary"
    if value == f"Bearer {TRUSTED_ROUTE_SECONDARY_KEY}":
        return "trusted-route"
    if value == f"Bearer {CONTEXT_CALIBRATION_UNUSED_KEY}":
        return "calibration-fallback"
    return "unknown"


class FakeUpstreamHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, _format: str, *_args) -> None:
        return

    def _read_json(self) -> dict:
        return json.loads(self._read_body().decode("utf-8"))

    def _read_body(self) -> bytes:
        size = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(size) if size else b"{}"

    def _record(self, kind: str) -> None:
        route = parse.urlparse(self.path).path
        METRICS.append("fakeRequests", {
            "method": self.command,
            "path": route,
            "kind": kind,
            "authorizationPresent": bool(self.headers.get("Authorization")),
        })

    def _send_json(self, payload: dict, status: int = 200) -> None:
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        route = parse.urlparse(self.path).path
        if route == "/__h4/refresh-gates":
            self._send_json({"ok": True, "gates": REFRESH_GATES.snapshot()})
            return
        if route == "/v1/models":
            self._record("models")
            if not MODEL_CATALOG_GATE.reach_and_wait():
                self._send_json({"error": "model catalog gate timeout"}, 504)
                return
            key_group = _synthetic_key_group(self.headers.get("Authorization", ""))
            route_state = MODEL_ROUTE_FIXTURE.snapshot()
            METRICS.append("modelRouteRequests", {
                "kind": "catalog",
                "keyGroup": key_group,
                "catalogOutage": route_state["catalogOutage"],
            })
            if route_state["catalogOutage"]:
                self._send_json({"error": "synthetic catalog unavailable"}, 503)
                return
            models = {
                "primary": [MODEL_ID, CONNECTION_SHARED_MODEL_ID],
                "trusted-route": [TRUSTED_ROUTE_MODEL_ID, CONNECTION_SHARED_MODEL_ID],
                "calibration-fallback": [MODEL_ID],
            }.get(key_group, [])
            self._send_json({
                "object": "list",
                "data": [{"id": model, "object": "model"} for model in models],
            })
            return
        if route == "/api/token/":
            self._record("platform-sync")
            self._send_json({"data": {"items": [], "total": 0}})
            return
        if route == "/api/user/self":
            self._record("platform-auth")
            self._send_json({"data": {"id": 7, "username": "h4-user"}})
            return
        self._record("unexpected")
        self._send_json({"error": "not found"}, 404)

    def do_POST(self) -> None:
        route = parse.urlparse(self.path).path
        if route.startswith("/__h4/refresh-gates/"):
            gate_name = route.rsplit("/", 1)[-1]
            if gate_name == "release-all":
                REFRESH_GATES.release_all()
                MODEL_CATALOG_GATE.release()
                self._send_json({"ok": True, "gates": REFRESH_GATES.snapshot()})
                return
            if gate_name in REFRESH_GATE_NAMES:
                REFRESH_GATES.release(gate_name)
                self._send_json({"ok": True, "gates": REFRESH_GATES.snapshot()})
                return
            self._send_json({"ok": False, "error": "unknown refresh gate"}, 400)
            return
        if route == "/api/token/batch/keys":
            self._read_json()
            self._record("platform-sync")
            self._send_json({"data": {"keys": {}}})
            return
        if route in {"/v1/images/generations", "/v1/images/edits"}:
            is_edit = route.endswith("/edits")
            unsupported_edit = False
            if is_edit:
                raw_body = self._read_body()
                unsupported_edit = b"H4_UNSUPPORTED_IMAGE_EDIT" in raw_body
                model_matches = f'name="model"\r\n\r\n{IMAGE_MODEL_ID}'.encode() in raw_body
                request_contract = {
                    "modelMatches": model_matches,
                    "multipart": "multipart/form-data" in str(self.headers.get("Content-Type") or ""),
                    "referencePresent": b'name="image"' in raw_body,
                    "responseFormatPresent": b'name="response_format"' in raw_body,
                    "sizePresent": b'name="size"' in raw_body,
                    "qualityPresent": b'name="quality"' in raw_body,
                    "outputFormatPresent": b'name="output_format"' in raw_body,
                }
            else:
                payload = self._read_json()
                prompt = str(payload.get("prompt") or "")
                batch_kind = (
                    "partial" if IMAGE_BATCH_PARTIAL_USER in prompt
                    else ("full" if IMAGE_BATCH_USER in prompt else "")
                )
                request_contract = {
                    "modelMatches": payload.get("model") == IMAGE_MODEL_ID,
                    "count": int(payload.get("n") or 0),
                    "responseFormat": str(payload.get("response_format") or ""),
                    "sizePresent": "size" in payload,
                    "qualityPresent": "quality" in payload,
                    "outputFormat": str(payload.get("output_format") or ""),
                }
            if is_edit:
                batch_kind = ""
            batch_index = -1
            active_at_admission = 0
            idempotency_key = str(self.headers.get("Idempotency-Key") or "")
            if batch_kind:
                match = re.search(r"\.([0-3])$", idempotency_key)
                if not match:
                    self._send_json({"error": "batch item identity missing"}, 400)
                    return
                batch_index = int(match.group(1))
                active_at_admission = IMAGE_BATCH_FIXTURE.begin(batch_kind, batch_index)
            self._record("image-edit" if is_edit else "image-generation")
            image_metric = {
                "kind": "edit" if is_edit else "generation",
                "authorizationPresent": bool(self.headers.get("Authorization")),
                "idempotencyPresent": bool(self.headers.get("Idempotency-Key")),
                "contract": request_contract,
            }
            if batch_kind:
                image_metric.update({
                    "batchKind": batch_kind,
                    "batchIndex": batch_index,
                    "activeAtAdmission": active_at_admission,
                    "idempotencyKey": idempotency_key,
                })
            METRICS.append("imageRequests", image_metric)
            if unsupported_edit:
                self._send_json({"error": "image edit endpoint is unsupported"}, 404)
                return
            try:
                if batch_kind:
                    IMAGE_BATCH_FIXTURE.wait_for_later_completion(batch_kind, batch_index)
                if batch_kind == "partial" and batch_index == 2:
                    self._send_json({"error": "synthetic ordinary item failure"}, 400)
                    completion_status = 400
                else:
                    self._send_json({
                        "created": 1,
                        "data": [{"b64_json": base64.b64encode(FAVICON_PNG).decode("ascii")}],
                    })
                    completion_status = 200
            finally:
                if batch_kind:
                    IMAGE_BATCH_FIXTURE.finish(batch_kind, batch_index)
                    METRICS.append("imageRequestCompletions", {
                        "batchKind": batch_kind,
                        "batchIndex": batch_index,
                        "idempotencyKey": idempotency_key,
                        "status": completion_status if "completion_status" in locals() else 500,
                    })
            return
        if route != "/v1/chat/completions":
            self._record("unexpected")
            self._send_json({"error": "not found"}, 404)
            return

        payload = self._read_json()
        if payload.get("stream") is not True:
            self._record("unexpected-nonstream-chat")
            METRICS.append("chatRequests", {"scenario": "unexpected-nonstream", "stream": False})
            self._send_json({
                "choices": [{"message": {"role": "assistant", "content": "H4_TITLE"}}],
            })
            return

        scenario, has_tool_result = _scenario_for(payload)
        self._record("agent-chat")
        chat_metric = {
            "scenario": scenario,
            "stream": True,
            "hasToolResult": has_tool_result,
        }
        tool_protocol_rejected = False
        if scenario == "trusted-model-route":
            key_group = _synthetic_key_group(self.headers.get("Authorization", ""))
            chat_metric["trustedRoute"] = {
                "keyGroup": key_group,
                "modelMatches": payload.get("model") == TRUSTED_ROUTE_MODEL_ID,
                "authorized": key_group == "trusted-route",
            }
            METRICS.append("modelRouteRequests", {
                "kind": "chat",
                "keyGroup": key_group,
                "modelMatches": payload.get("model") == TRUSTED_ROUTE_MODEL_ID,
            })
        if scenario == "connection-route":
            key_group = _synthetic_key_group(self.headers.get("Authorization", ""))
            chat_metric["connectionRoute"] = {
                "keyGroup": key_group,
                "modelMatches": payload.get("model") == CONNECTION_SHARED_MODEL_ID,
                "authorized": key_group == "trusted-route",
            }
        if scenario == "tool-protocol-history":
            projected_messages = [
                message for message in (payload.get("messages") or [])
                if isinstance(message, dict)
            ]
            assistant_indexes = [
                index for index, message in enumerate(projected_messages)
                if message.get("role") == "assistant"
                and any(
                    str(call.get("id") or "") == TOOL_PROTOCOL_CALL_ID
                    for call in (message.get("tool_calls") or [])
                    if isinstance(call, dict)
                )
            ]
            tool_indexes = [
                index for index, message in enumerate(projected_messages)
                if message.get("role") == "tool"
                and str(message.get("tool_call_id") or "") == TOOL_PROTOCOL_CALL_ID
            ]
            steer_indexes = [
                index for index, message in enumerate(projected_messages)
                if message.get("role") == "user"
                and "H4_TOOL_PROTOCOL_STEER" in _message_text(message)
            ]
            chat_metric["toolProtocol"] = {
                "assistantCallCount": len(assistant_indexes),
                "toolResultCount": len(tool_indexes),
                "steerCount": len(steer_indexes),
                "pairedOrder": bool(
                    len(assistant_indexes) == 1
                    and len(tool_indexes) == 1
                    and len(steer_indexes) == 1
                    and assistant_indexes[0] < tool_indexes[0] < steer_indexes[0]
                ),
                "orphanToolCount": sum(
                    1 for index in tool_indexes
                    if not any(assistant_index < index for assistant_index in assistant_indexes)
                ),
            }
        if scenario == "parallel-visual-protocol-final":
            projection = _parallel_visual_protocol_projection(payload)
            chat_metric["parallelVisualProtocol"] = projection
            tool_protocol_rejected = not projection["strictOrder"]
        if scenario == "runtime-recovery-final":
            projected_messages = [
                message for message in (payload.get("messages") or [])
                if isinstance(message, dict)
            ]
            chat_metric["runtimeRecovery"] = {
                "originalUserCount": sum(
                    1 for message in projected_messages
                    if message.get("role") == "user"
                    and RUNTIME_RECOVERY_USER in _message_text(message)
                ),
                "toolReceiptCount": sum(
                    1 for message in projected_messages
                    if message.get("role") == "tool"
                    and str(message.get("tool_call_id") or "")
                    == RUNTIME_RECOVERY_CALL_ID
                ),
                "recoveryInstructionPresent": any(
                    message.get("role") == "system"
                    and "[System recovery]" in _message_text(message)
                    and RUNTIME_RECOVERY_PARTIAL_TWO in _message_text(message)
                    for message in projected_messages
                ),
            }
        if scenario.startswith("skill-evidence-"):
            projected_messages = [
                message for message in (payload.get("messages") or [])
                if isinstance(message, dict)
            ]
            chat_metric["skillEvidence"] = {
                "originalUserCount": sum(
                    1 for message in projected_messages
                    if message.get("role") == "user"
                    and SKILL_EVIDENCE_USER in _message_text(message)
                ),
                "continuationCount": sum(
                    1 for message in projected_messages
                    if message.get("role") == "system"
                    and "[Server-owned Skill evidence continuation]" in _message_text(message)
                ),
                "toolReceiptCount": sum(
                    1 for message in projected_messages
                    if message.get("role") == "tool"
                    and str(message.get("tool_call_id") or "") == SKILL_EVIDENCE_CALL_ID
                ),
            }
        if scenario.startswith("image-"):
            tool_names = [
                str((item.get("function") or {}).get("name") or "")
                for item in (payload.get("tools") or [])
                if isinstance(item, dict)
            ]
            system_text = "\n".join(
                _message_text(message)
                for message in (payload.get("messages") or [])
                if isinstance(message, dict) and message.get("role") == "system"
            )
            public_tool_names = [
                name for name in tool_names
                if not name.startswith("goal_")
            ]
            generate_image = next((
                item for item in (payload.get("tools") or [])
                if isinstance(item, dict)
                and str((item.get("function") or {}).get("name") or "") == "generate_image"
            ), {})
            image_properties = (
                (((generate_image.get("function") or {}).get("parameters") or {}).get("properties") or {})
                if isinstance(generate_image, dict)
                else {}
            )
            chat_metric["imageToolContract"] = {
                "generateImageAvailable": "generate_image" in public_tool_names,
                "executionControlsAbsent": not any(
                    name in image_properties
                    for name in ("size", "quality", "outputFormat")
                ),
                "imagegenSkillPresent": (
                    "[Skill: imagegen]" in system_text
                    or "\u5df2\u6fc0\u6d3b Skill: imagegen" in system_text
                ),
                "localChartSkillAbsent": "[Skill: image-generation]" not in system_text,
            }
        if scenario == "context-calibration":
            chat_metric["usedContextCalibrationUnusedKey"] = (
                self.headers.get("Authorization", "")
                == f"Bearer {CONTEXT_CALIBRATION_UNUSED_KEY}"
            )
        if scenario == "invalid-tool-final":
            chat_metric["invalidReceipt"] = _invalid_tool_receipt_projection(payload)
        if scenario == "parse-error-tool-final":
            chat_metric["parseErrorReceipt"] = _parse_error_tool_receipt_projection(payload)
        if scenario == "missing-path-tool-final":
            chat_metric["missingPathReceipt"] = _missing_path_tool_receipt_projection(payload)
        if scenario == "executor-range-final":
            chat_metric["executorRangeReceipt"] = _executor_range_receipt_projection(payload)
        if scenario.startswith("repeated-range-failure-") \
                or scenario.startswith("forced-final-model-failure-") \
                or scenario.startswith("forced-final-unusable-tool-"):
            chat_metric["repeatedRangeFailureReceipts"] = (
                _repeated_range_failure_receipt_projection(payload)
            )
        if scenario.startswith("argument-isolation-"):
            chat_metric["argumentIsolationReceipts"] = (
                _argument_isolation_receipt_projection(payload)
            )
        if scenario.startswith("signature-alternation-"):
            chat_metric["signatureAlternationReceipts"] = (
                _signature_alternation_receipt_projection(payload)
            )
        if scenario.startswith("success-reset-"):
            chat_metric["successResetReceipts"] = (
                _success_reset_receipt_projection(payload)
            )
        if scenario in {
            "repeated-range-failure-final",
            "forced-final-model-failure-final",
            "forced-final-unusable-tool-final",
        }:
            chat_metric["forcedFinal"] = {
                "toolsPresent": bool(payload.get("tools")),
                "toolChoicePresent": "tool_choice" in payload,
                "recoveryInstructionPresent": any(
                    isinstance(message, dict)
                    and message.get("role") == "system"
                    and "identical tool call was blocked" in str(
                        message.get("content") or ""
                    )
                    for message in (payload.get("messages") or [])
                ),
            }
        if scenario in {
            "argument-isolation-final",
            "signature-alternation-final",
            "success-reset-final",
        }:
            chat_metric["normalFinal"] = {
                "toolsPresent": bool(payload.get("tools")),
                "toolChoicePresent": "tool_choice" in payload,
                "recoveryInstructionPresent": any(
                    isinstance(message, dict)
                    and message.get("role") == "system"
                    and "identical tool call was blocked" in str(
                        message.get("content") or ""
                    )
                    for message in (payload.get("messages") or [])
                ),
            }
        if scenario == "goal-v2-accept-setup-final":
            chat_metric["goalTerminalResponse"] = {
                "toolsPresent": bool(payload.get("tools")),
                "toolChoicePresent": "tool_choice" in payload,
                "terminalInstructionPresent": any(
                    isinstance(message, dict)
                    and message.get("role") == "system"
                    and "one complete, self-contained user-facing final answer"
                    in str(message.get("content") or "")
                    and "Do not say that the summary is above"
                    in str(message.get("content") or "")
                    for message in (payload.get("messages") or [])
                ),
            }
        if scenario in {"goal-v2-cancel-call", "goal-v2-cancel-final"}:
            tool_names = {
                str((item.get("function") or {}).get("name") or "")
                for item in (payload.get("tools") or [])
                if isinstance(item, dict)
            }
            chat_metric["goalCancelContract"] = {
                "toolPresent": "goal_cancel" in tool_names,
                "questionnairePresent": "request_user_input" in tool_names,
                "directInstructionPresent": any(
                    isinstance(message, dict)
                    and message.get("role") == "system"
                    and "goal_cancel" in _message_text(message)
                    and "不得重复问卷" in _message_text(message)
                    for message in (payload.get("messages") or [])
                ),
            }
        if scenario == "missing-file-final":
            chat_metric["missingFileReceipt"] = _missing_file_receipt_projection(payload)
        if scenario == "tiff-image":
            chat_metric["imageProjection"] = _tiff_model_image_projection(payload)
        if scenario == "parallel-failure-followup":
            followup_context = _parallel_failure_followup_context_projection(payload)
            if METRICS.snapshot()["productionEditProposalDelegations"] > 0:
                followup_context["detachedEditArtifactCount"] = (
                    _detached_edit_artifact_count(payload)
                )
            chat_metric["followupContext"] = followup_context
        if scenario == "questionnaire-final":
            chat_metric["questionnaireReceipt"] = (
                _questionnaire_receipt_projection(payload)
            )
        if scenario in {
            "queue-questionnaire-call",
            "queue-questionnaire-final",
            "queue-questionnaire-promoted",
        }:
            chat_metric["queueContext"] = (
                _queue_questionnaire_context_projection(payload)
            )
        if scenario == "queue-questionnaire-final":
            chat_metric["questionnaireReceipt"] = (
                _questionnaire_receipt_projection(payload)
            )
        if scenario == "mixed-questionnaire-final":
            chat_metric["mixedQuestionnaireReceipt"] = (
                _mixed_questionnaire_receipt_projection(payload)
            )
        if scenario in {
            "edit-authorization-approve-final",
            "edit-authorization-reject-final",
        }:
            chat_metric["editAuthorizationReceipt"] = (
                _edit_authorization_receipt_projection(
                    payload,
                    approved=scenario == "edit-authorization-approve-final",
                )
            )
        if scenario == "edit-authorization-conflict-final":
            chat_metric["editAuthorizationReceipt"] = (
                _edit_authorization_conflict_receipt_projection(payload)
            )
        METRICS.append("chatRequests", chat_metric)
        if scenario == "tool-protocol-error":
            self._send_json({
                "error": {
                    "message": (
                        "An assistant message with 'tool_calls' must be followed by "
                        "tool messages responding to each 'tool_call_id'."
                    ),
                    "code": "insufficient_tool_messages_following_tool_calls_message",
                },
            }, 400)
            return
        if tool_protocol_rejected:
            self._send_json({
                "error": {
                    "message": (
                        "An assistant message with 'tool_calls' must be followed by "
                        "tool messages responding to each 'tool_call_id'."
                    ),
                    "code": "insufficient_tool_messages_following_tool_calls_message",
                },
            }, 400)
            return
        if scenario == "context-calibration":
            calibration_attempts = sum(
                1 for item in METRICS.snapshot()["chatRequests"]
                if item.get("scenario") == "context-calibration"
            )
            if calibration_attempts == 1:
                self._send_json({
                    "error": {
                        "message": (
                            "maximum context length is 64000 tokens; "
                            "requested 90000 tokens; request id 20260821"
                        ),
                        "code": "context_length_exceeded",
                        "max_context_tokens": 64000,
                    },
                }, 400)
                return
        if scenario == "parallel-model-failure":
            self._send_json({"error": {"message": PARALLEL_FAILURE_ERROR}}, 502)
            return
        if scenario == "goal-v2-gate-supplement-failure":
            self._send_json({"error": {"message": GOAL_V2_GATE_FAILURE_ERROR}}, 502)
            return
        if scenario == "forced-final-model-failure-final":
            if not REFRESH_GATES.reach_and_wait("before-tool-final-delta"):
                return
            self._send_json({"error": {"message": PARALLEL_FAILURE_ERROR}}, 502)
            return
        if scenario == "forced-final-unusable-tool-final":
            if not REFRESH_GATES.reach_and_wait("before-tool-final-delta"):
                return
            data = _sse_payload([
                _chunk({"role": "assistant", "tool_calls": [{
                    "index": 0,
                    "id": FORCED_FINAL_UNUSABLE_TOOL_CALL_ID,
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": json.dumps(
                            {"path": READ_PATH, "startLine": 2, "endLine": 1},
                            separators=(",", ":"),
                        ),
                    },
                }]}),
                _chunk(
                    {},
                    "tool_calls",
                    {"prompt_tokens": 13, "completion_tokens": 5, "total_tokens": 18},
                ),
            ])
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(data)
            self.wfile.flush()
            return
        if scenario in {"runtime-recovery-partial-one", "runtime-recovery-partial-two"}:
            partial_text = (
                RUNTIME_RECOVERY_PARTIAL_ONE
                if scenario == "runtime-recovery-partial-one"
                else RUNTIME_RECOVERY_PARTIAL_TWO
            )
            frame = _chunk({
                "role": "assistant",
                "content": partial_text,
                "reasoning_content": "H4_PRIVATE_RECOVERY_REASONING",
            })
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            try:
                self.wfile.write(
                    f"data: {json.dumps(frame, separators=(',', ':'))}\n\n".encode("utf-8")
                )
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            self.close_connection = True
            return
        current_chat_count = len(METRICS.snapshot()["chatRequests"])
        if (
            scenario not in (
                "stream-refresh", "tool-detail-call", "multi-tool-detail-call",
                "invalid-tool-call", "parse-error-tool-call", "missing-path-tool-call",
                "executor-range-call", "missing-file-call", "questionnaire-call",
                "mixed-questionnaire-call", "five-questionnaire-call",
                "terminal-questionnaire-call",
                "queue-questionnaire-call",
                "edit-authorization-approve-call",
                "edit-authorization-reject-call", "edit-authorization-conflict-call",
                "runtime-recovery-call",
            )
            and not scenario.startswith("repeated-range-failure-call-")
            and not scenario.startswith("forced-final-model-failure-call-")
            and not scenario.startswith("forced-final-unusable-tool-call-")
            and not scenario.startswith("argument-isolation-call-")
            and not scenario.startswith("signature-alternation-call-")
            and not scenario.startswith("success-reset-call-")
            and current_chat_count == 1
        ):
            METRICS.increment("modelGateWaits")
            if not MODEL_GATE.wait(timeout=10):
                self._send_json({"error": "model gate timeout"}, 504)
                return

        if scenario == "stream-refresh":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()

            def write_frame(frame) -> bool:
                value = frame if isinstance(frame, str) else json.dumps(frame, separators=(",", ":"))
                try:
                    self.wfile.write(f"data: {value}\n\n".encode("utf-8"))
                    self.wfile.flush()
                    METRICS.append("refreshGateTimeline", {
                        "event": "frame-written",
                        "gate": "",
                        "at": RefreshGateState._now_ms(),
                    })
                    return True
                except (BrokenPipeError, ConnectionResetError, OSError):
                    METRICS.append("refreshGateTimeline", {
                        "event": "frame-write-failed",
                        "gate": "",
                        "at": RefreshGateState._now_ms(),
                    })
                    return False

            if not REFRESH_GATES.reach_and_wait("before-first-delta"):
                return
            if not write_frame(_chunk({"role": "assistant", "content": STREAM_ONE})):
                return
            if not write_frame(_chunk({"content": STREAM_TWO})):
                return
            if not REFRESH_GATES.reach_and_wait("after-second-delta"):
                return
            if not write_frame(_chunk({"content": STREAM_THREE})):
                return
            if not REFRESH_GATES.reach_and_wait("before-terminal"):
                return
            if not write_frame(_chunk(
                {},
                "stop",
                {"prompt_tokens": 17, "completion_tokens": 7, "total_tokens": 24},
            )):
                return
            write_frame("[DONE]")
            return

        if scenario in (
            "tool-detail-final", "multi-tool-detail-final", "invalid-tool-final",
            "parse-error-tool-final", "missing-path-tool-final", "executor-range-final",
            "missing-file-final", "repeated-range-failure-final", "argument-isolation-final",
            "signature-alternation-final", "success-reset-final",
        ):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()

            def write_tool_detail_frame(frame) -> bool:
                value = frame if isinstance(frame, str) else json.dumps(frame, separators=(",", ":"))
                try:
                    self.wfile.write(f"data: {value}\n\n".encode("utf-8"))
                    self.wfile.flush()
                    return True
                except (BrokenPipeError, ConnectionResetError, OSError):
                    return False

            if not REFRESH_GATES.reach_and_wait("before-tool-final-delta"):
                return
            final_text = {
                "multi-tool-detail-final": MULTI_TOOL_FINAL,
                "invalid-tool-final": INVALID_TOOL_FINAL,
                "parse-error-tool-final": PARSE_ERROR_TOOL_FINAL,
                "missing-path-tool-final": MISSING_PATH_TOOL_FINAL,
                "executor-range-final": EXECUTOR_RANGE_FINAL,
                "missing-file-final": MISSING_FILE_FINAL,
                "repeated-range-failure-final": REPEATED_RANGE_FAILURE_FINAL,
                "argument-isolation-final": ARGUMENT_ISOLATION_FINAL,
                "signature-alternation-final": SIGNATURE_ALTERNATION_FINAL,
                "success-reset-final": SUCCESS_RESET_FINAL,
            }.get(scenario, TOOL_DETAILS_FINAL)
            if not write_tool_detail_frame(_chunk({
                "role": "assistant",
                "content": final_text,
            })):
                return
            if not REFRESH_GATES.reach_and_wait("before-tool-terminal"):
                return
            if not write_tool_detail_frame(_chunk(
                {},
                "stop",
                {"prompt_tokens": 13, "completion_tokens": 5, "total_tokens": 18},
            )):
                return
            write_tool_detail_frame("[DONE]")
            return

        if scenario in (
            "questionnaire-call", "mixed-questionnaire-call",
            "five-questionnaire-call", "terminal-questionnaire-call",
            "queue-questionnaire-call",
        ):
            questionnaire_tool_call_id, questionnaire_arguments = (
                _questionnaire_call_contract(scenario)
            )
            frames = [
                _chunk({
                    "role": "assistant",
                    "tool_calls": [{
                        "index": 0,
                        "id": questionnaire_tool_call_id,
                        "type": "function",
                        "function": {
                            "name": "request_user_input",
                            "arguments": json.dumps(
                                questionnaire_arguments, separators=(",", ":"),
                            ),
                        },
                    }],
                }),
                _chunk(
                    {},
                    "tool_calls",
                    {"prompt_tokens": 11, "completion_tokens": 3, "total_tokens": 14},
                ),
            ]
        elif scenario in (
            "tool-call", "tool-detail-call", "multi-tool-detail-call", "invalid-tool-call",
            "parse-error-tool-call", "missing-path-tool-call", "executor-range-call",
            "missing-file-call", "edit-authorization-approve-call",
            "edit-authorization-reject-call", "edit-authorization-conflict-call",
            "parallel-visual-protocol-call",
            "runtime-recovery-call",
            "skill-evidence-call",
            "image-generation-call",
            "image-batch-call", "image-batch-partial-call",
            "image-edit-call",
            "image-edit-unsupported-call",
            "image-edit-unsupported-retry",
        ) or scenario.startswith("repeated-range-failure-call-") \
                or scenario.startswith("forced-final-model-failure-call-") \
                or scenario.startswith("forced-final-unusable-tool-call-") \
                or scenario.startswith("argument-isolation-call-") \
                or scenario.startswith("signature-alternation-call-") \
                or scenario.startswith("success-reset-call-") \
                or scenario.startswith("goal-v2-explicit-call-") \
                or scenario.startswith("goal-v2-autonomous-complete-call-") \
                or scenario.startswith("goal-v2-autonomous-call-") \
                or scenario.startswith("goal-v2-accept-setup-call-") \
                or scenario.startswith("goal-v2-gate-setup-call-") \
                or scenario.startswith("goal-v2-gate-complete-call-") \
                or scenario.startswith("goal-v2-continuation-root-call-") \
                or scenario.startswith("goal-v2-continuation-next-call-") \
                or scenario.startswith("goal-v2-hard-limit-call-") \
                or scenario == "goal-v2-cancel-call":
            stage_text = {
                "tool-call": TOOL_STAGE,
                "tool-detail-call": TOOL_DETAILS_STAGE,
                "multi-tool-detail-call": MULTI_TOOL_STAGE,
                "invalid-tool-call": INVALID_TOOL_STAGE,
                "parse-error-tool-call": PARSE_ERROR_TOOL_STAGE,
                "missing-path-tool-call": MISSING_PATH_TOOL_STAGE,
                "executor-range-call": EXECUTOR_RANGE_STAGE,
                "missing-file-call": MISSING_FILE_STAGE,
                "edit-authorization-approve-call": EDIT_AUTHORIZATION_STAGE,
                "edit-authorization-reject-call": EDIT_AUTHORIZATION_STAGE,
                "edit-authorization-conflict-call": EDIT_AUTHORIZATION_STAGE,
                "parallel-visual-protocol-call": PARALLEL_VISUAL_PROTOCOL_STAGE,
                "runtime-recovery-call": RUNTIME_RECOVERY_STAGE,
                "skill-evidence-call": "",
                "image-generation-call": "",
                "image-batch-call": "",
                "image-batch-partial-call": "",
                "image-edit-call": "",
                "image-edit-unsupported-call": "",
                "image-edit-unsupported-retry": "",
            }.get(scenario, "")
            tool_calls = [{
                "index": 0,
                "id": TOOL_CALL_ID,
                "type": "function",
                "function": {
                    "name": "read_file",
                    "arguments": json.dumps({"path": READ_PATH}, separators=(",", ":")),
                },
            }]
            if scenario == "parallel-visual-protocol-call":
                tool_calls = [
                    {
                        "index": index,
                        "id": PARALLEL_VISUAL_PROTOCOL_CALL_IDS[index],
                        "type": "function",
                        "function": {
                            "name": "read_file",
                            "arguments": json.dumps(
                                {"path": PARALLEL_VISUAL_PROTOCOL_PATHS[index]},
                                separators=(",", ":"),
                            ),
                        },
                    }
                    for index in range(len(PARALLEL_VISUAL_PROTOCOL_CALL_IDS))
                ]
            elif scenario == "runtime-recovery-call":
                tool_calls = [{
                    "index": 0,
                    "id": RUNTIME_RECOVERY_CALL_ID,
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": json.dumps(
                            {"path": READ_PATH}, separators=(",", ":"),
                        ),
                    },
                }]
            elif scenario == "skill-evidence-call":
                tool_calls = [{
                    "index": 0,
                    "id": SKILL_EVIDENCE_CALL_ID,
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": json.dumps(
                            {"path": READ_PATH}, separators=(",", ":"),
                        ),
                    },
                }]
            elif scenario in {
                "image-generation-call", "image-edit-call", "image-edit-unsupported-call",
                "image-edit-unsupported-retry", "image-batch-call", "image-batch-partial-call",
            }:
                is_edit_scenario = scenario in {
                    "image-edit-call", "image-edit-unsupported-call",
                    "image-edit-unsupported-retry",
                }
                if scenario == "image-batch-partial-call":
                    call_id = IMAGE_BATCH_PARTIAL_CALL_ID
                    prompt = IMAGE_BATCH_PARTIAL_USER
                elif scenario == "image-batch-call":
                    call_id = IMAGE_BATCH_CALL_ID
                    prompt = IMAGE_BATCH_USER
                elif scenario == "image-edit-unsupported-retry":
                    call_id = IMAGE_EDIT_UNSUPPORTED_RETRY_CALL_ID
                    prompt = "H4_UNSUPPORTED_IMAGE_EDIT_RETRY_MUST_BE_BLOCKED"
                elif scenario == "image-edit-unsupported-call":
                    call_id = IMAGE_EDIT_UNSUPPORTED_CALL_ID
                    prompt = "H4_UNSUPPORTED_IMAGE_EDIT"
                elif scenario == "image-edit-call":
                    call_id = IMAGE_EDIT_CALL_ID
                    prompt = "Turn the supplied image into a blue geometric icon"
                else:
                    call_id = IMAGE_GENERATION_CALL_ID
                    prompt = "A small blue geometric icon on a transparent background"
                arguments = {
                    "prompt": prompt,
                    "size": "1024x1024",
                    "quality": "hd",
                    "count": 4 if scenario in {"image-batch-call", "image-batch-partial-call"} else 1,
                    "outputFormat": "webp" if scenario == "image-edit-unsupported-retry" else "png",
                }
                if is_edit_scenario:
                    serialized_messages = json.dumps(
                        payload.get("messages") or [], ensure_ascii=False,
                    )
                    asset_match = re.search(r"ga1_[A-Za-z0-9_-]{32,96}", serialized_messages)
                    if asset_match:
                        arguments["reference"] = {
                            "type": "generated_asset",
                            "id": asset_match.group(0),
                        }
                tool_calls = [{
                    "index": 0,
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": "generate_image",
                        "arguments": json.dumps(arguments, separators=(",", ":")),
                    },
                }]
            elif scenario == "multi-tool-detail-call":
                tool_calls = [
                    {
                        "index": 0,
                        "id": MULTI_TOOL_CALL_IDS[0],
                        "type": "function",
                        "function": {
                            "name": "read_file",
                            "arguments": json.dumps(
                                {"path": READ_PATH}, separators=(",", ":"),
                            ),
                        },
                    },
                    {
                        "index": 1,
                        "id": MULTI_TOOL_CALL_IDS[1],
                        "type": "function",
                        "function": {
                            "name": "read_file",
                            "arguments": json.dumps(
                                {"path": READ_PATH, "startLine": 1, "endLine": 1},
                                separators=(",", ":"),
                            ),
                        },
                    },
                ]
            elif scenario == "invalid-tool-call":
                tool_calls = [{
                    "index": 0,
                    "id": INVALID_TOOL_CALL_ID,
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": json.dumps(
                            {"path": READ_PATH, "unexpected": True},
                            separators=(",", ":"),
                        ),
                    },
                }]
            elif scenario == "parse-error-tool-call":
                tool_calls = [{
                    "index": 0,
                    "id": PARSE_ERROR_TOOL_CALL_ID,
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": MALFORMED_TOOL_ARGUMENTS,
                    },
                }]
            elif scenario == "missing-path-tool-call":
                tool_calls = [{
                    "index": 0,
                    "id": MISSING_PATH_TOOL_CALL_ID,
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": "{}",
                    },
                }]
            elif scenario == "executor-range-call":
                tool_calls = [{
                    "index": 0,
                    "id": EXECUTOR_RANGE_TOOL_CALL_ID,
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": json.dumps(
                            {"path": READ_PATH, "startLine": 2, "endLine": 1},
                            separators=(",", ":"),
                        ),
                    },
                }]
            elif scenario == "missing-file-call":
                tool_calls = [{
                    "index": 0,
                    "id": MISSING_FILE_TOOL_CALL_ID,
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": json.dumps(
                            {"path": MISSING_READ_PATH}, separators=(",", ":"),
                        ),
                    },
                }]
            elif scenario in {
                "edit-authorization-approve-call",
                "edit-authorization-reject-call",
                "edit-authorization-conflict-call",
            }:
                tool_calls = [{
                    "index": 0,
                    "id": PROPOSE_EDIT_TOOL_CALL_ID,
                    "type": "function",
                    "function": {
                        "name": "propose_edit",
                        "arguments": json.dumps(
                            PROPOSE_EDIT_TOOL_ARGUMENTS, separators=(",", ":"),
                        ),
                    },
                }]
            elif scenario.startswith("repeated-range-failure-call-") \
                    or scenario.startswith("forced-final-model-failure-call-") \
                    or scenario.startswith("forced-final-unusable-tool-call-"):
                call_number = int(scenario.rsplit("-", 1)[-1])
                tool_calls = [{
                    "index": 0,
                    "id": REPEATED_RANGE_FAILURE_TOOL_CALL_IDS[call_number - 1],
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": json.dumps(
                            {"path": READ_PATH, "startLine": 2, "endLine": 1},
                            separators=(",", ":"),
                        ),
                    },
                }]
                if call_number == 1:
                    stage_text = REPEATED_RANGE_FAILURE_STAGE
            elif scenario.startswith("argument-isolation-call-"):
                call_number = int(scenario.rsplit("-", 1)[-1])
                tool_calls = [{
                    "index": 0,
                    "id": ARGUMENT_ISOLATION_TOOL_CALL_IDS[call_number - 1],
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": json.dumps(
                            ARGUMENT_ISOLATION_TOOL_ARGUMENTS[call_number - 1],
                            separators=(",", ":"),
                        ),
                    },
                }]
                if call_number == 1:
                    stage_text = ARGUMENT_ISOLATION_STAGE
            elif scenario.startswith("signature-alternation-call-"):
                call_number = int(scenario.rsplit("-", 1)[-1])
                tool_calls = [{
                    "index": 0,
                    "id": SIGNATURE_ALTERNATION_TOOL_CALL_IDS[call_number - 1],
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": json.dumps(
                            SIGNATURE_ALTERNATION_TOOL_ARGUMENTS,
                            separators=(",", ":"),
                        ),
                    },
                }]
                if call_number == 1:
                    stage_text = SIGNATURE_ALTERNATION_STAGE
            elif scenario.startswith("success-reset-call-"):
                call_number = int(scenario.rsplit("-", 1)[-1])
                tool_calls = [{
                    "index": 0,
                    "id": SUCCESS_RESET_TOOL_CALL_IDS[call_number - 1],
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": json.dumps(
                            SUCCESS_RESET_TOOL_ARGUMENTS,
                            separators=(",", ":"),
                        ),
                    },
                }]
                if call_number == 1:
                    stage_text = SUCCESS_RESET_STAGE
            elif scenario == "goal-v2-cancel-call":
                tool_calls = [{
                    "index": 0,
                    "id": GOAL_V2_CANCEL_CALL_ID,
                    "type": "function",
                    "function": {
                        "name": "goal_cancel",
                        "arguments": json.dumps({
                            "reason": "The user explicitly cancelled the current Goal",
                        }, separators=(",", ":")),
                    },
                }]
            elif scenario.startswith("goal-v2-"):
                call_number = int(scenario.rsplit("-", 1)[-1])
                autonomous_complete = scenario.startswith("goal-v2-autonomous-complete-")
                autonomous = scenario.startswith("goal-v2-autonomous-")
                acceptance_setup = scenario.startswith("goal-v2-accept-setup-")
                gate_setup = scenario.startswith("goal-v2-gate-setup-")
                gate_complete = scenario.startswith("goal-v2-gate-complete-")
                continuation_root = scenario.startswith("goal-v2-continuation-root-")
                continuation_next = scenario.startswith("goal-v2-continuation-next-")
                hard_limit = scenario.startswith("goal-v2-hard-limit-")
                if continuation_root:
                    call_ids = GOAL_V2_CONTINUATION_ROOT_CALL_IDS
                elif continuation_next:
                    call_ids = GOAL_V2_CONTINUATION_NEXT_CALL_IDS
                elif hard_limit:
                    call_ids = GOAL_V2_HARD_LIMIT_CALL_IDS
                elif autonomous_complete:
                    call_ids = GOAL_V2_AUTONOMOUS_COMPLETE_CALL_IDS
                elif autonomous:
                    call_ids = GOAL_V2_AUTONOMOUS_CALL_IDS
                elif acceptance_setup:
                    call_ids = GOAL_V2_ACCEPT_SETUP_CALL_IDS
                elif gate_setup:
                    call_ids = GOAL_V2_GATE_SETUP_CALL_IDS
                elif gate_complete:
                    call_ids = GOAL_V2_GATE_CALL_IDS
                else:
                    call_ids = GOAL_V2_EXPLICIT_CALL_IDS
                plan = [
                    {
                        "id": f"h4-goal-step-{index}",
                        "description": f"H4 Goal stage {index}",
                        "acceptanceCriteria": [{
                            "id": f"h4-goal-criterion-{index}",
                            "kind": "machine",
                            "description": f"H4 Goal evidence {index}",
                        }],
                    }
                    for index in range(1, 4)
                ]
                operations = []
                if continuation_root:
                    if call_number == 1:
                        name, arguments = "goal_set_plan", {"steps": plan}
                    elif call_number == 2:
                        name, arguments = "goal_start_step", {"stepId": "h4-goal-step-1"}
                    else:
                        name, arguments = "read_file", {"path": READ_PATH}
                        if call_number == 3:
                            stage_text = GOAL_V2_CONTINUATION_STAGE
                    tool_calls = [{
                        "index": 0,
                        "id": call_ids[call_number - 1],
                        "type": "function",
                        "function": {
                            "name": name,
                            "arguments": json.dumps(arguments, separators=(",", ":")),
                        },
                    }]
                    operations = None
                elif hard_limit:
                    if call_number == 1:
                        name, arguments = "goal_set_plan", {"steps": plan}
                    elif call_number == 2:
                        name, arguments = "goal_start_step", {"stepId": "h4-goal-step-1"}
                    elif call_number == 3:
                        name, arguments = "goal_raise_gate", {
                            "gateType": "waiting_user",
                            "summary": "H4 hard-limit fallback keeps the active step gated",
                        }
                    else:
                        name, arguments = "read_file", {"path": READ_PATH}
                        if call_number == 4:
                            stage_text = GOAL_V2_HARD_LIMIT_STAGE
                    tool_calls = [{
                        "index": 0,
                        "id": call_ids[call_number - 1],
                        "type": "function",
                        "function": {
                            "name": name,
                            "arguments": json.dumps(arguments, separators=(",", ":")),
                        },
                    }]
                    operations = None
                elif continuation_next:
                    operations.extend([
                        (
                            "goal_complete_step",
                            {
                                "stepId": "h4-goal-step-1",
                                "evidence": [{
                                    "criterionId": "h4-goal-criterion-1",
                                    "kind": "machine",
                                    "summary": "The first stage survived the soft handoff",
                                }],
                            },
                        ),
                        ("goal_start_step", {"stepId": "h4-goal-step-2"}),
                        (
                            "goal_complete_step",
                            {
                                "stepId": "h4-goal-step-2",
                                "evidence": [{
                                    "criterionId": "h4-goal-criterion-2",
                                    "kind": "machine",
                                    "summary": "The successor continued the second stage",
                                }],
                            },
                        ),
                        ("goal_start_step", {"stepId": "h4-goal-step-3"}),
                        (
                            "goal_complete_step",
                            {
                                "stepId": "h4-goal-step-3",
                                "evidence": [{
                                    "criterionId": "h4-goal-criterion-3",
                                    "kind": "machine",
                                    "summary": "The successor completed the Goal",
                                }],
                            },
                        ),
                    ])
                elif autonomous:
                    operations.append((
                        "goal_create",
                        {"objective": (
                            GOAL_V2_AUTONOMOUS_COMPLETE_USER
                            if autonomous_complete
                            else GOAL_V2_AUTONOMOUS_USER
                        )},
                    ))
                if continuation_root or continuation_next or hard_limit:
                    pass
                elif gate_complete:
                    operations.extend([
                        ("goal_clear_gate", {}),
                        (
                            "goal_complete_step",
                            {
                                "stepId": "h4-goal-step-3",
                                "evidence": [{
                                    "criterionId": "h4-goal-criterion-3",
                                    "kind": "user",
                                    "summary": "The user accepted the concrete final step",
                                }],
                            },
                        ),
                    ])
                elif autonomous_complete:
                    operations.append(("goal_set_plan", {"steps": plan}))
                    for index in range(1, 4):
                        operations.extend([
                            ("goal_start_step", {"stepId": f"h4-goal-step-{index}"}),
                            (
                                "goal_complete_step",
                                {
                                    "stepId": f"h4-goal-step-{index}",
                                    "evidence": [{
                                        "criterionId": f"h4-goal-criterion-{index}",
                                        "kind": "machine",
                                        "summary": f"H4 autonomous Goal stage {index} passed",
                                    }],
                                },
                            ),
                        ])
                elif gate_setup:
                    plan[-1]["acceptanceCriteria"][0]["kind"] = "user"
                    operations.append(("goal_set_plan", {"steps": plan}))
                    for index in range(1, 3):
                        operations.append((
                            "goal_start_step",
                            {"stepId": f"h4-goal-step-{index}"},
                        ))
                        if index == 1:
                            operations.append(("read_file", {"path": READ_PATH}))
                        operations.append((
                            "goal_complete_step",
                            {
                                "stepId": f"h4-goal-step-{index}",
                                "evidence": [{
                                    "criterionId": f"h4-goal-criterion-{index}",
                                    "kind": "machine",
                                    "summary": f"H4 Goal stage {index} passed",
                                }],
                            },
                        ))
                    operations.extend([
                        ("goal_start_step", {"stepId": "h4-goal-step-3"}),
                        (
                            "goal_raise_gate",
                            {
                                "gateType": "waiting_user",
                                "summary": "The final step needs user acceptance",
                            },
                        ),
                    ])
                elif acceptance_setup:
                    operations.append(("goal_set_plan", {"steps": plan}))
                    for index in range(1, 4):
                        operations.extend([
                            ("goal_start_step", {"stepId": f"h4-goal-step-{index}"}),
                            (
                                "goal_complete_step",
                                {
                                    "stepId": f"h4-goal-step-{index}",
                                    "evidence": [{
                                        "criterionId": f"h4-goal-criterion-{index}",
                                        "kind": "machine",
                                        "summary": f"H4 Goal stage {index} passed",
                                    }],
                                },
                            ),
                        ])
                else:
                    operations.extend([
                        ("goal_set_plan", {"steps": plan}),
                        ("goal_start_step", {"stepId": "h4-goal-step-1"}),
                        (
                            "goal_complete_step",
                            {
                                "stepId": "h4-goal-step-1",
                                "evidence": [{
                                    "criterionId": "h4-goal-criterion-1",
                                    "kind": "machine",
                                    "summary": "H4 Goal stage 1 passed",
                                }],
                            },
                        ),
                        ("goal_start_step", {"stepId": "h4-goal-step-2"}),
                    ])
                if operations is not None:
                    name, arguments = operations[call_number - 1]
                    tool_calls = [{
                        "index": 0,
                        "id": call_ids[call_number - 1],
                        "type": "function",
                        "function": {
                            "name": name,
                            "arguments": json.dumps(arguments, separators=(",", ":")),
                        },
                    }]
                    if (
                        acceptance_setup
                        and call_number == len(call_ids)
                        and name == "goal_complete_step"
                    ):
                        stage_text = GOAL_V2_FINAL_STAGE_SUMMARY
                if (
                    call_number == 1
                    and tool_calls
                    and str(tool_calls[0].get("function", {}).get("name", "")).startswith("goal_")
                ):
                    # This is intentionally public model content paired only
                    # with an internal Goal operation. It remains visible as
                    # task commentary while the internal operation itself is
                    # omitted from the user-facing tool projection.
                    stage_text = GOAL_V2_PUBLIC_COMMENTARY
            frames = []
            if stage_text in {
                GOAL_V2_PUBLIC_COMMENTARY,
                GOAL_V2_FINAL_STAGE_SUMMARY,
            }:
                midpoint = max(1, len(stage_text) // 2)
                if stage_text == GOAL_V2_PUBLIC_COMMENTARY:
                    frames.append(_chunk({
                        "role": "assistant",
                        "reasoning_content": GOAL_V2_PRIVATE_REASONING,
                    }))
                frames.extend([
                    _chunk({"role": "assistant", "content": stage_text[:midpoint]}),
                    _chunk({"content": stage_text[midpoint:]}),
                ])
            elif stage_text:
                frames.append(_chunk({"role": "assistant", "content": stage_text}))
            frames.extend([
                _chunk({"tool_calls": tool_calls}),
                _chunk({}, "tool_calls", {"prompt_tokens": 11, "completion_tokens": 3, "total_tokens": 14}),
            ])
        else:
            final_text = {
                "plain-text": PLAIN_FINAL,
                "trusted-model-route": TRUSTED_ROUTE_FINAL,
                "connection-route": CONNECTION_ROUTE_FINAL,
                "tool-protocol-history": TOOL_PROTOCOL_FINAL,
                "parallel-visual-protocol-final": PARALLEL_VISUAL_PROTOCOL_FINAL,
                "classic-text": CLASSIC_FINAL,
                "context-compaction": AUTO_COMPACTION_CHECKPOINT,
                "context-compaction-seed": AUTO_COMPACTION_SEED_FINAL,
                "context-compaction-final": AUTO_COMPACTION_FINAL,
                "context-calibration": CONTEXT_CALIBRATION_FINAL,
                "runtime-recovery-final": RUNTIME_RECOVERY_FINAL,
                "skill-evidence-candidate": SKILL_EVIDENCE_CANDIDATE,
                "skill-evidence-final": SKILL_EVIDENCE_FINAL,
                "image-generation-final": IMAGE_GENERATION_FINAL,
                "image-batch-final": IMAGE_BATCH_FINAL,
                "image-batch-partial-final": IMAGE_BATCH_PARTIAL_FINAL,
                "image-edit-final": IMAGE_EDIT_FINAL,
                "image-edit-unsupported-final": IMAGE_EDIT_UNSUPPORTED_FINAL,
                "tiff-image": TIFF_IMAGE_FINAL,
                "timing-main": TIMING_MAIN_FINAL,
                "timing-parallel": TIMING_PARALLEL_FINAL,
                "timing-queue": TIMING_QUEUE_FINAL,
                "parallel-failure-followup": PARALLEL_FAILURE_FOLLOWUP_FINAL,
                "questionnaire-final": QUESTIONNAIRE_FINAL,
                "legacy-questionnaire-final": LEGACY_QUESTIONNAIRE_FINAL,
                "queue-questionnaire-final": QUEUE_QUESTIONNAIRE_FINAL,
                "queue-questionnaire-promoted": TIMING_QUEUE_FINAL,
                "mixed-questionnaire-final": MIXED_QUESTIONNAIRE_FINAL,
                "five-questionnaire-final": FIVE_QUESTIONNAIRE_FINAL,
                "terminal-questionnaire-final": TERMINAL_QUESTIONNAIRE_FINAL,
                "edit-authorization-approve-final": EDIT_AUTHORIZATION_APPROVE_FINAL,
                "edit-authorization-reject-final": EDIT_AUTHORIZATION_REJECT_FINAL,
                "edit-authorization-conflict-final": EDIT_AUTHORIZATION_CONFLICT_FINAL,
                "tool-final": TOOL_FINAL,
                "goal-v2-explicit-final": GOAL_V2_EXPLICIT_FINAL,
                "goal-v2-cancel-draft-final": GOAL_V2_CANCEL_DRAFT_FINAL,
                "goal-v2-cancel-final": GOAL_V2_CANCEL_FINAL,
                "goal-v2-autonomous-final": GOAL_V2_AUTONOMOUS_FINAL,
                "goal-v2-autonomous-complete-final": GOAL_V2_AUTONOMOUS_COMPLETE_FINAL,
                "goal-v2-accept-setup-final": GOAL_V2_ACCEPT_SETUP_FINAL,
                "goal-v2-gate-setup-final": (
                    GOAL_V2_GATE_SETUP_FINAL + " " + GOAL_V2_GATE_REQUEST
                ),
                "goal-v2-gate-complete-final": GOAL_V2_GATE_FINAL,
                "goal-v2-continuation-next-final": GOAL_V2_CONTINUATION_FINAL,
            }[scenario]
            if scenario == "goal-v2-continuation-next-final":
                # Keep the successor visibly in flight long enough for the H4
                # browser assertion to prove that the parent handoff footer is
                # suppressed until this user turn reaches its real terminal.
                time.sleep(1.0)
            if scenario == "goal-v2-accept-setup-final":
                frames = [
                    _chunk({
                        "role": "assistant",
                        "content": GOAL_V2_FINAL_SUMMARY_ONE + " ",
                    }),
                    _chunk({"content": GOAL_V2_FINAL_SUMMARY_TWO + " "}),
                    _chunk({"content": final_text}),
                    _chunk({}, "stop", {
                        "prompt_tokens": 13,
                        "completion_tokens": 5,
                        "total_tokens": 18,
                    }),
                ]
            else:
                frames = [
                    _chunk({"role": "assistant", "content": final_text}),
                    _chunk({}, "stop", {"prompt_tokens": 13, "completion_tokens": 5, "total_tokens": 18}),
                ]

        if scenario == "goal-v2-accept-setup-final":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            for frame_index, frame in enumerate(frames):
                try:
                    self.wfile.write(
                        f"data: {json.dumps(frame, separators=(',', ':'))}\n\n".encode("utf-8")
                    )
                    self.wfile.flush()
                    if (
                        frame_index == 0
                        and not REFRESH_GATES.reach_and_wait(
                            "goal-final-after-first-delta"
                        )
                    ):
                        return
                except (BrokenPipeError, ConnectionResetError, OSError):
                    return
            try:
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            return

        if scenario == "context-compaction":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            for frame_index, frame in enumerate(frames):
                try:
                    self.wfile.write(
                        f"data: {json.dumps(frame, separators=(',', ':'))}\n\n".encode("utf-8")
                    )
                    self.wfile.flush()
                    if (
                        frame_index == 0
                        and not REFRESH_GATES.reach_and_wait(
                            "context-compaction-after-first-delta"
                        )
                    ):
                        return
                except (BrokenPipeError, ConnectionResetError, OSError):
                    return
            try:
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            return

        data = _sse_payload(frames)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(data)
        self.wfile.flush()


OUTPUT_LOCK = threading.RLock()
METRICS_BREADCRUMB_SEQUENCE = 0


def _json_line(payload: dict) -> None:
    with OUTPUT_LOCK:
        print(json.dumps(payload, separators=(",", ":")), flush=True)


def _metrics_breadcrumb(
    phase: str,
    request_started: float,
    phase_started: float,
    outcome: str,
) -> None:
    global METRICS_BREADCRUMB_SEQUENCE
    METRICS_BREADCRUMB_SEQUENCE += 1
    now = time.monotonic()
    payload = {
        "seq": METRICS_BREADCRUMB_SEQUENCE,
        "phase": str(phase),
        "elapsedMs": max(0, round((now - request_started) * 1000)),
        "durationMs": max(0, round((now - phase_started) * 1000)),
        "outcome": str(outcome),
    }
    print(
        "H4_METRICS " + json.dumps(payload, separators=(",", ":")),
        file=sys.stderr,
        flush=True,
    )


def _run_metrics_phase(phase: str, request_started: float, operation):
    phase_started = time.monotonic()
    _metrics_breadcrumb(f"{phase}_start", request_started, phase_started, "started")
    try:
        result = operation()
    except Exception:
        _metrics_breadcrumb(f"{phase}_done", request_started, phase_started, "failed")
        raise
    _metrics_breadcrumb(f"{phase}_done", request_started, phase_started, "succeeded")
    return result


def _safe_id(value) -> str:
    raw = str(value or "")
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16] if raw else ""


def _production_snapshot(code_server) -> dict:
    agent_runs = []
    for run in list(code_server._agent_runs.values()):
        with run["condition"]:
            events = list(run.get("events") or [])
            agent_runs.append({
                "agentRunId": _safe_id(run.get("id")),
                "status": str(run.get("status") or ""),
                "nextCursor": int(events[-1].get("seq") or 0) if events else 0,
                "eventTypes": [str(event.get("type") or "") for event in events],
                "activeRuntimeRunId": _safe_id(run.get("active_runtime_id")),
            })
    runtime_runs = []
    with code_server._model_runtime_lock:
        candidates = list(code_server._model_runtime_runs.values())
    for run in candidates:
        with run["condition"]:
            events = list(run.get("events") or [])
            result = code_server._runtime_result_snapshot(run)
            runtime_runs.append({
                "runtimeRunId": _safe_id(run.get("id")),
                "status": str(run.get("status") or ""),
                "nextCursor": int(events[-1].get("seq") or 0) if events else 0,
                "eventCount": len(events),
                "contentLength": len(str(result.get("content") or "")),
                "hasFirstChunk": STREAM_ONE.strip() in str(result.get("content") or ""),
                "hasSecondChunk": STREAM_TWO.strip() in str(result.get("content") or ""),
                "hasThirdChunk": STREAM_THREE in str(result.get("content") or ""),
            })
    goal_events = []
    goal_root = code_server.goal_v2_runtime().service.root
    for path in sorted(goal_root.glob("*.jsonl")) if goal_root.exists() else []:
        try:
            events = code_server.read_jsonl(path)
        except (OSError, ValueError):
            continue
        if not events:
            continue
        goal_events.append({
            "sessionId": _safe_id(events[0].get("sessionId")),
            "goalId": _safe_id(events[0].get("goalId")),
            "revision": int(events[-1].get("revision") or 0),
            "eventTypes": [str(event.get("type") or "") for event in events],
        })
    return {
        "agentRuns": sorted(agent_runs, key=lambda item: item["agentRunId"]),
        "runtimeRuns": sorted(runtime_runs, key=lambda item: item["runtimeRunId"]),
        "goalEvents": sorted(goal_events, key=lambda item: item["sessionId"]),
    }


def _session_jsonl_evidence(code_server) -> dict:
    paths = sorted(code_server.SESSIONS_DIR.rglob("*.jsonl"))
    bodies = []
    for path in paths:
        try:
            bodies.append(path.read_text(encoding="utf-8"))
        except OSError:
            continue
    combined = "\n".join(bodies)
    return {
        "fileCount": len(bodies),
        "hasFirstChunk": STREAM_ONE.strip() in combined,
        "hasSecondChunk": STREAM_TWO.strip() in combined,
        "hasThirdChunk": STREAM_THREE in combined,
        "pausedOutputCount": combined.count("[Output paused]"),
        "hasStreamingField": '"streaming"' in combined,
        "hasStreamProjectionField": '"_streamProjection"' in combined,
        "tiffMimeCount": combined.count("image/tiff"),
        "tiffDataUrlCount": combined.count("data:image/tiff;base64,"),
        "derivedPreviewFieldCount": combined.count("_previewUrl") + combined.count("_previewFailed"),
    }


def _attachment_evidence(code_server) -> dict:
    files = []
    for path in sorted(code_server.ATTACHMENTS_DIR.iterdir()):
        if not path.is_file():
            continue
        raw = path.read_bytes()
        source_format, mime = code_server._sniff_model_image_format(raw)
        files.append({
            "size": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "sourceFormat": source_format,
            "mime": mime,
            "suffix": path.suffix.lower(),
        })
    return {"fileCount": len(files), "files": files}


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: isolated_host.py <temporary-root>")
    root = Path(sys.argv[1]).resolve()
    data_dir = (root / "data").resolve()
    project_dir = (root / "project").resolve()
    artifacts_dir = (root / "artifacts").resolve()
    for candidate in (data_dir, project_dir, artifacts_dir):
        if root not in candidate.parents:
            raise RuntimeError("temporary path escaped the owned root")
        candidate.mkdir(parents=True, exist_ok=True)

    missing_relative = Path(MISSING_READ_PATH)
    if missing_relative.is_absolute() or ".." in missing_relative.parts:
        raise RuntimeError("H4 missing-file fixture path is not a safe relative path")
    missing_project_target = (project_dir / missing_relative).resolve()
    isolated_home = (root / "home").resolve()
    missing_home_target = (isolated_home / missing_relative).resolve()
    if project_dir not in missing_project_target.parents:
        raise RuntimeError("H4 missing-file fixture escaped the project root")
    if isolated_home not in missing_home_target.parents:
        raise RuntimeError("H4 missing-file home audit escaped the isolated home")
    if missing_project_target.exists():
        raise RuntimeError("H4 missing-file fixture unexpectedly exists in the project root")
    if missing_home_target.exists():
        raise RuntimeError("H4 missing-file fixture unexpectedly exists in the isolated home")

    fixture_bytes = (project_dir / READ_PATH).read_bytes()
    fixture_sha256 = hashlib.sha256(fixture_bytes).hexdigest()
    propose_edit_initial_bytes = PROPOSE_EDIT_INITIAL_CONTENT.encode("utf-8")
    propose_edit_target_bytes = PROPOSE_EDIT_TARGET_CONTENT.encode("utf-8")
    propose_edit_third_party_bytes = PROPOSE_EDIT_THIRD_PARTY_CONTENT.encode("utf-8")
    if hashlib.sha256(propose_edit_initial_bytes).hexdigest() != PROPOSE_EDIT_INITIAL_SHA256:
        raise RuntimeError("H4 propose_edit initial fixture hash changed")
    if hashlib.sha256(propose_edit_target_bytes).hexdigest() != PROPOSE_EDIT_TARGET_SHA256:
        raise RuntimeError("H4 propose_edit target fixture hash changed")
    if (
        hashlib.sha256(propose_edit_third_party_bytes).hexdigest()
        != PROPOSE_EDIT_THIRD_PARTY_SHA256
    ):
        raise RuntimeError("H4 propose_edit third-party fixture hash changed")
    controlled_fixture_lock = threading.RLock()
    controlled_fixture_invocations = {
        SIGNATURE_ALTERNATION_READ_PATH: 0,
        SUCCESS_RESET_READ_PATH: 0,
    }

    def controlled_fixture_target(relative_path: str) -> Path:
        relative = Path(relative_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise RuntimeError("H4 controlled fixture is not a safe relative path")
        target = (project_dir / relative).resolve()
        if project_dir not in target.parents:
            raise RuntimeError("H4 controlled fixture escaped the project root")
        return target

    controlled_fixture_targets = {
        relative_path: controlled_fixture_target(relative_path)
        for relative_path in controlled_fixture_invocations
    }
    if any(target.exists() for target in controlled_fixture_targets.values()):
        raise RuntimeError("H4 controlled fixture unexpectedly exists")

    propose_edit_target = controlled_fixture_target(PROPOSE_EDIT_PATH)
    if not propose_edit_target.exists():
        propose_edit_target.write_bytes(propose_edit_initial_bytes)
    if not propose_edit_target.is_file():
        raise RuntimeError("H4 propose_edit fixture is not a file")

    def propose_edit_fixture_state() -> dict:
        if not propose_edit_target.exists():
            return {
                "state": "missing",
                "exists": False,
                "initialHashMatches": False,
                "targetHashMatches": False,
                "thirdPartyHashMatches": False,
            }
        if not propose_edit_target.is_file():
            return {
                "state": "not-file",
                "exists": True,
                "initialHashMatches": False,
                "targetHashMatches": False,
                "thirdPartyHashMatches": False,
            }
        observed_sha256 = hashlib.sha256(propose_edit_target.read_bytes()).hexdigest()
        initial_matches = observed_sha256 == PROPOSE_EDIT_INITIAL_SHA256
        target_matches = observed_sha256 == PROPOSE_EDIT_TARGET_SHA256
        third_party_matches = observed_sha256 == PROPOSE_EDIT_THIRD_PARTY_SHA256
        return {
            "state": (
                "initial" if initial_matches
                else "target" if target_matches
                else "third-party" if third_party_matches
                else "unexpected"
            ),
            "exists": True,
            "initialHashMatches": initial_matches,
            "targetHashMatches": target_matches,
            "thirdPartyHashMatches": third_party_matches,
        }

    if propose_edit_fixture_state()["state"] not in {"initial", "target"}:
        raise RuntimeError("H4 propose_edit fixture bytes changed")

    def controlled_fixture_state(target: Path) -> dict:
        exists = target.exists()
        hash_matches = (
            exists
            and target.is_file()
            and hashlib.sha256(target.read_bytes()).hexdigest()
            == fixture_sha256
        )
        return {
            "observedState": "present" if exists else "missing",
            "exists": exists,
            "hashMatches": hash_matches,
        }

    fake_server = ThreadingHTTPServer(("127.0.0.1", 0), FakeUpstreamHandler)
    fake_server.daemon_threads = True
    fake_port = fake_server.server_address[1]
    fake_url = f"http://127.0.0.1:{fake_port}"
    fake_thread = threading.Thread(target=fake_server.serve_forever, daemon=True)
    fake_thread.start()

    os.environ["CODE_DATA_DIR"] = str(data_dir)
    os.environ["CODE_PORT"] = "0"
    os.environ["CODE_INSTANCE_MODE"] = "release"
    os.environ["CODE_AGENT_PROTOCOL_SHADOW"] = "0"
    os.environ["CODE_AGENT_PROJECTION_SHADOW"] = "0"
    os.environ["CODE_AGENT_EVENT_PROTOCOL_V1"] = "1"
    os.environ["NEW_API_BASE_URL"] = fake_url
    os.environ["NO_PROXY"] = "127.0.0.1,localhost"

    repo_root = Path(__file__).resolve().parents[3]
    imagegen_source = repo_root / "data" / "skills" / "imagegen"
    if not imagegen_source.is_dir():
        raise RuntimeError("H4 imagegen Skill source is missing")
    shutil.copytree(
        imagegen_source,
        data_dir / "skills" / "imagegen",
        dirs_exist_ok=True,
    )

    code_review_dir = data_dir / "skills" / "code-review"
    code_review_dir.mkdir(parents=True, exist_ok=True)
    (code_review_dir / "SKILL.md").write_text(
        "---\nname: code-review\ndescription: H4 explicit evidence pilot\n"
        "keywords: h4+skill+evidence\ntools: read_file\n---\n\n"
        "Use read_file once before the final review answer.\n",
        encoding="utf-8",
    )
    (code_review_dir / "evidence.json").write_text(json.dumps({
        "schemaVersion": 1,
        "requirements": [{
            "id": "inspect-source",
            "type": "tool_execution",
            "tool": "read_file",
            "minCount": 1,
        }],
        "enforcement": {"schemaVersion": 1, "mode": "explicit_only"},
    }, separators=(",", ":")), encoding="utf-8")

    sys.path.insert(0, str(repo_root))
    import server as code_server

    class H4FaviconHttpClient:
        """No-network transport under the production candidate/cache/endpoint layers."""

        def __init__(self):
            self._attempts = {}

        def fetch(self, url: str, *, deadline: float):
            parsed_url = parse.urlsplit(url)
            request_key = (parsed_url.scheme, parsed_url.hostname, parsed_url.path, parsed_url.query)
            attempt = self._attempts.get(request_key, 0) + 1
            self._attempts[request_key] = attempt
            METRICS.append("faviconFetches", {
                "scheme": parsed_url.scheme,
                "host": parsed_url.hostname,
                "path": parsed_url.path,
                "query": parsed_url.query,
                "attempt": attempt,
                "deadlinePresent": deadline > 0,
            })
            if (
                parsed_url.scheme == "https"
                and parsed_url.hostname in {"yuanbao.tencent.com", "mistral.ai"}
                and parsed_url.path == "/favicon.ico"
                and not parsed_url.query
            ):
                if parsed_url.hostname == "mistral.ai" and attempt == 1:
                    raise code_server._FaviconTransientError("H4 deterministic transient favicon miss")
                return code_server._validated_favicon_asset(FAVICON_PNG, "image/png")
            if (
                parsed_url.hostname == "api.faviconkit.com"
                and "xinghuo.xfyun.cn" in parsed_url.path
            ):
                return code_server._validated_favicon_asset(
                    FAVICON_PLACEHOLDER_PNG,
                    "image/png",
                )
            if (
                parsed_url.hostname == "www.google.com"
                and "domain=xinghuo.xfyun.cn" in parsed_url.query
            ):
                return code_server._validated_favicon_asset(FAVICON_PNG, "image/png")
            raise code_server._FaviconProxyError("H4 deterministic favicon miss")

    code_server._favicon_proxy = code_server._FaviconProxy(
        http_client=H4FaviconHttpClient(),
        positive_ttl=3600,
        negative_ttl=3600,
    )

    class H4CodeHandler(code_server.CodeHandler):
        def log_message(self, _format: str, *_args) -> None:
            return

    code_server.WORKBAR_URL = fake_url
    code_server.CODEX_SESSIONS_DIR = root / "home" / ".codex" / "sessions"
    code_server.CLAUDE_PROJECTS_DIR = root / "home" / ".claude" / "projects"
    code_server._read_remote_version = lambda: (None, None)
    code_server.write_json(code_server.CONFIG_PATH, {
        "projectRoot": str(project_dir),
        "newApiBaseUrl": fake_url,
    })

    def seed_legacy_questionnaire() -> dict:
        """Persist a pre-v2 text questionnaire without invoking current tool validation."""
        timestamp = code_server._session_now_iso()
        session_id = uuid.uuid4().hex[:16]
        legacy_question = {
            "id": LEGACY_QUESTIONNAIRE_QUESTION_ID,
            "prompt": LEGACY_QUESTIONNAIRE_PROMPT,
            "type": "text",
            "required": True,
            "allowOther": False,
            "options": [],
        }
        tool_arguments = {
            "title": LEGACY_QUESTIONNAIRE_TITLE,
            "reason": LEGACY_QUESTIONNAIRE_REASON,
            "questions": [legacy_question],
        }
        encoded_arguments = json.dumps(
            tool_arguments,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        tool_call = {
            "id": LEGACY_QUESTIONNAIRE_TOOL_CALL_ID,
            "type": "function",
            "function": {
                "name": "request_user_input",
                "arguments": encoded_arguments,
            },
        }
        run = code_server._create_agent_run(
            session_id,
            {
                "model": MODEL_ID,
                "messages": [{"role": "user", "content": LEGACY_QUESTIONNAIRE_USER}],
                "stream": True,
            },
            fake_url,
            [],
            allowed_tools=["request_user_input"],
            permission_profile="read",
            cwd=str(project_dir),
            workspace_roots=[str(project_dir)],
            run_kind="foreground",
            start_worker=False,
        )
        pending_input = {
            "requestId": LEGACY_QUESTIONNAIRE_REQUEST_ID,
            "toolCallId": LEGACY_QUESTIONNAIRE_TOOL_CALL_ID,
            "title": LEGACY_QUESTIONNAIRE_TITLE,
            "reason": LEGACY_QUESTIONNAIRE_REASON,
            "questions": [legacy_question],
            "createdAt": timestamp,
        }
        with run["condition"]:
            run["messages"].append({
                "role": "assistant",
                "content": "",
                "tool_calls": [tool_call],
            })
            run["pending_tool_calls"] = [tool_call]
            run["pending_input"] = pending_input
            run["tool_executions"][LEGACY_QUESTIONNAIRE_TOOL_CALL_ID] = {
                "name": "request_user_input",
                "arguments": encoded_arguments,
                "argumentAliases": [],
                "fingerprint": "h4-legacy-questionnaire",
                "status": "waiting_user_input",
                "outcome": "",
                "result": None,
                "error": "",
                "startedAt": timestamp,
                "completedAt": "",
            }
            code_server._append_agent_event_locked(run, "tool_started", {
                "toolCallId": LEGACY_QUESTIONNAIRE_TOOL_CALL_ID,
                "name": "request_user_input",
                "arguments": encoded_arguments,
                "argumentAliases": [],
            })
            code_server._append_agent_event_locked(run, "user_input_required", pending_input)
            run["status"] = "waiting_user_input"
            run["resume_status"] = ""
            run["keys"] = []
            run["updated_at"] = timestamp
            cursor = run["next_seq"] - 1
        code_server._persist_agent_run(run)

        saved_question = {
            **legacy_question,
            "status": "pending",
            "selected": [],
            "text": "",
            "other": "",
            "answer": None,
        }
        saved_request = {
            "id": LEGACY_QUESTIONNAIRE_REQUEST_ID,
            "sessionId": session_id,
            "toolCallId": LEGACY_QUESTIONNAIRE_TOOL_CALL_ID,
            "agentRunId": run["id"],
            "title": LEGACY_QUESTIONNAIRE_TITLE,
            "reason": LEGACY_QUESTIONNAIRE_REASON,
            "questions": [saved_question],
            "status": "pending",
            "createdAt": timestamp,
        }
        messages = [{
            "role": "user",
            "content": LEGACY_QUESTIONNAIRE_USER,
            "_time": timestamp,
        }]
        meta = {
            "id": session_id,
            "title": "H4 legacy persisted questionnaire",
            "createdAt": timestamp,
            "updatedAt": timestamp,
            "stats": code_server._merge_session_stats({}, {}),
            "lastUsage": None,
            "runState": {
                "status": "waiting-user-input",
                "phase": "tools",
                "executionOwner": "server-agent",
                "agentRunId": run["id"],
                "runtimeRunId": "",
                "agentEventCursor": cursor,
                "modelRound": 1,
                "model": MODEL_ID,
                "permissionProfile": "read",
                "startedAt": timestamp,
                "updatedAt": timestamp,
                "userInputRequest": saved_request,
            },
            "messageCount": len(messages),
            "lastMessageTime": timestamp,
            "projectId": None,
            "cwd": str(project_dir),
            "source": "code",
        }
        code_server.write_json(code_server.session_path(session_id), meta)
        code_server.write_jsonl(code_server.messages_path(session_id), messages)
        code_server._write_session_index_entry(
            session_id,
            meta["title"],
            timestamp,
            len(messages),
            project_id=None,
            cwd=str(project_dir),
            source="code",
            last_message_time=timestamp,
        )
        return {
            "sessionId": session_id,
            "agentRunId": run["id"],
            "requestId": LEGACY_QUESTIONNAIRE_REQUEST_ID,
            "toolCallId": LEGACY_QUESTIONNAIRE_TOOL_CALL_ID,
            "cursor": cursor,
        }

    def seed_tool_protocol_history() -> dict:
        """Persist the historic assistant/steer/visual-call/result ordering."""
        timestamp = code_server._session_now_iso()
        session_id = uuid.uuid4().hex[:16]
        history_run_id = "h4-tool-protocol-history-run"
        tool_call = {
            "id": TOOL_PROTOCOL_CALL_ID,
            "type": "function",
            "function": {
                "name": "read_file",
                "arguments": json.dumps(
                    {"path": READ_PATH}, separators=(",", ":"),
                ),
            },
        }
        messages = [
            {
                "role": "user",
                "content": TOOL_PROTOCOL_HISTORY_USER,
                "_time": timestamp,
            },
            {
                "role": "assistant",
                "content": "H4_TOOL_PROTOCOL_ASSISTANT_CALL",
                "meta": {
                    "agentRunId": history_run_id,
                    "toolCalls": [tool_call],
                },
                "_time": timestamp,
            },
            {
                "role": "user",
                "content": "H4_TOOL_PROTOCOL_STEER",
                "meta": {
                    "steerDispatch": {
                        "agentRunId": history_run_id,
                        "status": "accepted",
                    },
                },
                "_time": timestamp,
            },
            {
                "role": "tool-call",
                "content": "read_file",
                "meta": {
                    "agentRunId": history_run_id,
                    "toolCallId": TOOL_PROTOCOL_CALL_ID,
                    "action": "read_file",
                    "tool": {"action": "read_file", "path": READ_PATH},
                },
                "_time": timestamp,
            },
            {
                "role": "tool-result",
                "content": FIXTURE_CONTENT.strip(),
                "meta": {
                    "agentRunId": history_run_id,
                    "toolCallId": TOOL_PROTOCOL_CALL_ID,
                    "action": "read_file",
                },
                "_time": timestamp,
            },
        ]
        meta = {
            "id": session_id,
            "title": "H4 historic paired tool protocol",
            "createdAt": timestamp,
            "updatedAt": timestamp,
            "stats": code_server._merge_session_stats({}, {}),
            "lastUsage": None,
            "runState": {},
            "messageCount": len(messages),
            "lastMessageTime": timestamp,
            "projectId": None,
            "cwd": str(project_dir),
            "source": "code",
        }
        code_server.write_json(code_server.session_path(session_id), meta)
        code_server.write_jsonl(code_server.messages_path(session_id), messages)
        code_server._write_session_index_entry(
            session_id,
            meta["title"],
            timestamp,
            len(messages),
            project_id=None,
            cwd=str(project_dir),
            source="code",
            last_message_time=timestamp,
        )
        return {"sessionId": session_id, "toolCallId": TOOL_PROTOCOL_CALL_ID}

    def h4_project_relative(target) -> str:
        resolved = Path(target).resolve()
        if resolved != project_dir and project_dir not in resolved.parents:
            raise RuntimeError("H4 external open target escaped the project root")
        return str(resolved.relative_to(project_dir)).replace("\\", "/") or "."

    def h4_open_path_in_explorer(target, *, select_file, allowed_root):
        resolved_root = Path(allowed_root).resolve()
        if resolved_root != project_dir:
            raise RuntimeError("H4 Explorer allowed root changed")
        relative = h4_project_relative(target)
        target_path = Path(target).resolve()
        METRICS.append("explorerRequests", {
            "path": relative,
            "selectFile": bool(select_file),
            "targetExists": target_path.exists(),
            "targetKind": (
                "file" if target_path.is_file()
                else "directory" if target_path.is_dir()
                else "missing"
            ),
        })
        degraded = not bool(select_file)
        return {
            "ok": True,
            "action": "select_file" if select_file else "open_folder",
            "selected": bool(select_file and target_path.is_file()),
            "degraded": degraded,
            "degradedReasons": ["foreground_not_granted"] if degraded else [],
            "foreground": "not_foreground" if degraded else "foreground",
            "restored": False,
            "topmostPulse": False,
        }

    def h4_startfile(target):
        METRICS.append("defaultOpenRequests", {
            "path": h4_project_relative(target),
        })

    code_server.windows_explorer.open_path_in_explorer = h4_open_path_in_explorer
    code_server.os.startfile = h4_startfile

    original_execute_registered_tool = code_server.execute_registered_tool
    original_execute_apply_edit_proposal = code_server.execute_apply_edit_proposal
    original_execute_run_command_tool = code_server.execute_run_command_tool
    expected_proposal_keys = {
        "ok", "action", "proposalId", "path", "diff", "newContent",
        "mtime", "baseHash", "newHash", "applied",
    }
    expected_proposal_diff = code_server.make_unified_diff(
        PROPOSE_EDIT_INITIAL_CONTENT,
        PROPOSE_EDIT_TARGET_CONTENT,
        PROPOSE_EDIT_PATH,
    )
    if code_server._edit_content_hash(
        PROPOSE_EDIT_INITIAL_CONTENT,
    ) != PROPOSE_EDIT_INITIAL_SHA256:
        raise RuntimeError("H4 propose_edit production base hash changed")
    if code_server._edit_content_hash(
        PROPOSE_EDIT_TARGET_CONTENT,
    ) != PROPOSE_EDIT_TARGET_SHA256:
        raise RuntimeError("H4 propose_edit production target hash changed")

    def propose_edit_backup_state() -> dict:
        backups = sorted(
            path for path in code_server.FILE_BACKUP_DIR.rglob("*.bak")
            if path.is_file()
        )
        return {
            "count": len(backups),
            "initialContentMatches": sum(
                hashlib.sha256(path.read_bytes()).hexdigest()
                == PROPOSE_EDIT_INITIAL_SHA256
                for path in backups
            ),
        }

    def owned_tree_entries(base: Path) -> list[dict]:
        entries = []
        for candidate in sorted(base.rglob("*")):
            if candidate.is_symlink():
                raise RuntimeError("H4 owned tree contains an unexpected symlink")
            relative = candidate.relative_to(base).as_posix()
            if candidate.is_dir():
                entries.append({
                    "path": relative,
                    "kind": "directory",
                    "size": 0,
                    "sha256": "",
                })
            elif candidate.is_file():
                raw = candidate.read_bytes()
                entries.append({
                    "path": relative,
                    "kind": "file",
                    "size": len(raw),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                })
            else:
                raise RuntimeError("H4 owned tree contains an unsupported entry")
        return entries

    def owned_tree_fingerprint(base: Path) -> dict:
        entries = owned_tree_entries(base)
        encoded = json.dumps(
            entries,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return {
            "entryCount": len(entries),
            "fingerprint": hashlib.sha256(encoded).hexdigest(),
        }

    def production_callback_delta(before: dict, after: dict) -> dict:
        return {
            "registeredDelegations": (
                after["productionToolDelegations"]
                - before["productionToolDelegations"]
            ),
            "proposalDelegations": (
                after["productionEditProposalDelegations"]
                - before["productionEditProposalDelegations"]
            ),
            "applyDelegations": (
                after["productionEditApplyDelegations"]
                - before["productionEditApplyDelegations"]
            ),
            "writes": (
                after["productionEditWrites"]
                - before["productionEditWrites"]
            ),
            "backups": (
                after["productionEditBackups"]
                - before["productionEditBackups"]
            ),
            "toolExecutions": (
                len(after["toolExecutions"])
                - len(before["toolExecutions"])
            ),
            "runCommandAttempts": (
                len(after["runCommandAttempts"])
                - len(before["runCommandAttempts"])
            ),
        }

    def fixed_third_party_tree_transition(before: list[dict], after: list[dict]) -> bool:
        before_by_path = {entry["path"]: entry for entry in before}
        after_by_path = {entry["path"]: entry for entry in after}
        if set(before_by_path) != set(after_by_path):
            return False
        for relative_path in before_by_path:
            if relative_path == PROPOSE_EDIT_PATH:
                continue
            if before_by_path[relative_path] != after_by_path[relative_path]:
                return False
        return before_by_path.get(PROPOSE_EDIT_PATH) == {
            "path": PROPOSE_EDIT_PATH,
            "kind": "file",
            "size": len(propose_edit_initial_bytes),
            "sha256": PROPOSE_EDIT_INITIAL_SHA256,
        } and after_by_path.get(PROPOSE_EDIT_PATH) == {
            "path": PROPOSE_EDIT_PATH,
            "kind": "file",
            "size": len(propose_edit_third_party_bytes),
            "sha256": PROPOSE_EDIT_THIRD_PARTY_SHA256,
        }

    def transition_propose_edit_third_party(command: dict) -> dict:
        with controlled_fixture_lock:
            metrics_before = METRICS.snapshot()
            file_before = propose_edit_fixture_state()
            backups_before = propose_edit_backup_state()
            project_entries_before = owned_tree_entries(project_dir)
            home_tree_before = owned_tree_fingerprint(isolated_home)
            artifacts_tree_before = owned_tree_fingerprint(artifacts_dir)
            attempt = metrics_before["proposeEditThirdPartyTransitionAttempts"] + 1
            METRICS.increment("proposeEditThirdPartyTransitionAttempts")

            accepted = False
            reason = ""
            command_keys_exact = set(command) == {"id", "command"}
            proposal_ready = (
                metrics_before["productionEditProposalDelegations"] == 1
                and len(metrics_before["proposeEditProposalTimeline"]) == 1
                and metrics_before["productionEditApplyDelegations"] == 0
                and metrics_before["productionEditWrites"] == 0
                and metrics_before["productionEditBackups"] == 0
            )
            already_transitioned = (
                metrics_before["proposeEditThirdPartyTransitionWrites"] != 0
            )
            if not command_keys_exact:
                reason = "payload-not-allowed"
            elif already_transitioned:
                reason = "already-transitioned"
            elif not proposal_ready:
                reason = "proposal-precondition-not-ready"
            elif file_before["state"] != "initial":
                reason = "fixture-precondition-changed"
            elif backups_before["count"] != 0:
                reason = "backup-precondition-changed"
            else:
                propose_edit_target.write_bytes(propose_edit_third_party_bytes)
                METRICS.increment("proposeEditThirdPartyTransitionWrites")
                accepted = True

            if not accepted:
                METRICS.increment("proposeEditThirdPartyTransitionRejections")

            file_after = propose_edit_fixture_state()
            backups_after = propose_edit_backup_state()
            project_entries_after = owned_tree_entries(project_dir)
            home_tree_after = owned_tree_fingerprint(isolated_home)
            artifacts_tree_after = owned_tree_fingerprint(artifacts_dir)
            metrics_after = METRICS.snapshot()
            production_callbacks = production_callback_delta(
                metrics_before, metrics_after,
            )
            project_tree_unchanged = project_entries_after == project_entries_before
            project_tree_changed_only_at_fixed_path = fixed_third_party_tree_transition(
                project_entries_before, project_entries_after,
            )
            home_tree_unchanged = home_tree_after == home_tree_before
            artifacts_tree_unchanged = artifacts_tree_after == artifacts_tree_before
            backup_count_unchanged = backups_after == backups_before
            fixed_bytes_match = (
                file_after["state"] == "third-party"
                and file_after["thirdPartyHashMatches"] is True
                and propose_edit_target.stat().st_size
                == len(propose_edit_third_party_bytes)
            )

            if any(production_callbacks.values()):
                raise RuntimeError("H4 third-party transition invoked production callbacks")
            if not home_tree_unchanged or not artifacts_tree_unchanged:
                raise RuntimeError("H4 third-party transition escaped the project tree")
            if not backup_count_unchanged:
                raise RuntimeError("H4 third-party transition changed edit backups")
            if accepted and (
                not fixed_bytes_match or not project_tree_changed_only_at_fixed_path
            ):
                raise RuntimeError("H4 third-party transition changed unexpected bytes")
            if not accepted and (
                not project_tree_unchanged or file_after != file_before
            ):
                raise RuntimeError("H4 rejected third-party transition changed the fixture")

            timeline_item = {
                "accepted": accepted,
                "reason": reason,
                "commandKeysExact": command_keys_exact,
                "attempt": attempt,
                "path": PROPOSE_EDIT_PATH,
                "fileBefore": file_before,
                "fileAfter": file_after,
                "fixedBytes": {
                    "byteLength": len(propose_edit_third_party_bytes),
                    "sha256": PROPOSE_EDIT_THIRD_PARTY_SHA256,
                    "hashMatches": fixed_bytes_match,
                },
                "projectTreeUnchanged": project_tree_unchanged,
                "projectTreeChangedOnlyAtFixedPath": (
                    project_tree_changed_only_at_fixed_path
                ),
                "homeTreeUnchanged": home_tree_unchanged,
                "artifactsTreeUnchanged": artifacts_tree_unchanged,
                "backupCountBefore": backups_before["count"],
                "backupCountAfter": backups_after["count"],
                "productionCallbacks": production_callbacks,
            }
            METRICS.append(
                "proposeEditThirdPartyTransitionTimeline", timeline_item,
            )
            return timeline_item

    def proposal_shape_matches(proposal) -> bool:
        if not isinstance(proposal, dict) or set(proposal) != expected_proposal_keys:
            return False
        mtime = proposal.get("mtime")
        if isinstance(mtime, bool) or not isinstance(mtime, int) or mtime < 0:
            return False
        expected_id = hashlib.sha256(
            (
                f"{PROPOSE_EDIT_PATH}\0{mtime}\0{PROPOSE_EDIT_INITIAL_SHA256}"
                f"\0{PROPOSE_EDIT_TARGET_SHA256}"
            ).encode("utf-8")
        ).hexdigest()
        return (
            proposal.get("ok") is True
            and str(proposal.get("action") or "") == "propose_edit"
            and str(proposal.get("proposalId") or "") == expected_id
            and str(proposal.get("path") or "") == PROPOSE_EDIT_PATH
            and str(proposal.get("diff") or "") == expected_proposal_diff
            and str(proposal.get("newContent") or "") == PROPOSE_EDIT_TARGET_CONTENT
            and str(proposal.get("baseHash") or "") == PROPOSE_EDIT_INITIAL_SHA256
            and str(proposal.get("newHash") or "") == PROPOSE_EDIT_TARGET_SHA256
            and proposal.get("applied") is False
        )

    def proposal_result_projection(proposal) -> dict:
        proposal = proposal if isinstance(proposal, dict) else {}
        proposal_id = str(proposal.get("proposalId") or "")
        return {
            "shapeMatches": proposal_shape_matches(proposal),
            "ok": proposal.get("ok") is True,
            "actionMatches": str(proposal.get("action") or "") == "propose_edit",
            "pathMatches": str(proposal.get("path") or "") == PROPOSE_EDIT_PATH,
            "proposalIdPresent": bool(re.fullmatch(r"[0-9a-f]{64}", proposal_id)),
            "baseHashMatches": str(proposal.get("baseHash") or "")
            == PROPOSE_EDIT_INITIAL_SHA256,
            "newHashMatches": str(proposal.get("newHash") or "")
            == PROPOSE_EDIT_TARGET_SHA256,
            "newContentHashMatches": hashlib.sha256(
                str(proposal.get("newContent") or "").encode("utf-8")
            ).hexdigest() == PROPOSE_EDIT_TARGET_SHA256,
            "applied": proposal.get("applied") is True,
        }

    def apply_result_projection(result, proposal) -> dict:
        result = result if isinstance(result, dict) else {}
        return {
            "ok": result.get("ok") is True,
            "actionMatches": str(result.get("action") or "") == "apply_edit",
            "pathMatches": str(result.get("path") or "") == PROPOSE_EDIT_PATH,
            "proposalIdMatches": str(result.get("proposalId") or "")
            == str((proposal or {}).get("proposalId") or ""),
            "applied": result.get("applied") is True,
            "replayed": result.get("replayed") is True,
            "backupPresent": bool(str(result.get("backupPath") or "")),
        }

    def delegate_propose_edit_to_production(action, payload, *, _arguments_validated):
        file_before = propose_edit_fixture_state()
        backups_before = propose_edit_backup_state()
        METRICS.append("toolExecutions", {
            "action": "propose_edit",
            "path": PROPOSE_EDIT_PATH,
            "payloadKeysMatch": set(payload) == set(PROPOSE_EDIT_TOOL_ARGUMENTS),
            "payloadBytesMatch": payload == PROPOSE_EDIT_TOOL_ARGUMENTS,
        })
        METRICS.increment("productionToolDelegations")
        METRICS.increment("productionEditProposalDelegations")
        result = None
        try:
            result = original_execute_registered_tool(
                action,
                payload,
                _arguments_validated=_arguments_validated,
            )
            return result
        finally:
            file_after = propose_edit_fixture_state()
            backups_after = propose_edit_backup_state()
            METRICS.append("proposeEditProposalTimeline", {
                "action": "propose_edit",
                "path": PROPOSE_EDIT_PATH,
                "payloadKeysMatch": set(payload) == set(PROPOSE_EDIT_TOOL_ARGUMENTS),
                "payloadBytesMatch": payload == PROPOSE_EDIT_TOOL_ARGUMENTS,
                "fileBefore": file_before,
                "fileAfter": file_after,
                "backupCountBefore": backups_before["count"],
                "backupCountAfter": backups_after["count"],
                "result": proposal_result_projection(result),
            })
            if result is not None and not proposal_shape_matches(result):
                raise RuntimeError("H4 production propose_edit result changed contract")
            if file_after != file_before or backups_after != backups_before:
                raise RuntimeError("H4 propose_edit generated a write or backup")

    def counted_execute_apply_edit_proposal(proposal):
        if not proposal_shape_matches(proposal):
            METRICS.increment("unsafeToolRequests")
            raise ValueError("H4 apply_edit proposal escaped the fixed synthetic contract")
        file_before = propose_edit_fixture_state()
        backups_before = propose_edit_backup_state()
        transition_metrics = METRICS.snapshot()
        accepted_transitions = [
            item
            for item in transition_metrics["proposeEditThirdPartyTransitionTimeline"]
            if item.get("accepted") is True
        ]
        fixed_third_party_transition = (
            file_before["state"] == "third-party"
            and transition_metrics["proposeEditThirdPartyTransitionWrites"] == 1
            and len(accepted_transitions) == 1
        )
        if (
            file_before["state"] not in {"initial", "target"}
            and not fixed_third_party_transition
        ):
            METRICS.increment("unsafeToolRequests")
            raise ValueError("H4 apply_edit fixture precondition changed")
        METRICS.increment("productionEditApplyDelegations")
        result = None
        conflict_observed = False
        try:
            result = original_execute_apply_edit_proposal(proposal)
            return result
        except code_server.EditConflictError:
            conflict_observed = True
            METRICS.increment("productionEditConflictObservations")
            raise
        finally:
            file_after = propose_edit_fixture_state()
            backups_after = propose_edit_backup_state()
            write_observed = (
                file_before["state"] == "initial"
                and file_after["state"] == "target"
            )
            backup_delta = backups_after["count"] - backups_before["count"]
            initial_backup_delta = (
                backups_after["initialContentMatches"]
                - backups_before["initialContentMatches"]
            )
            if write_observed:
                METRICS.increment("productionEditWrites")
            for _ in range(max(0, backup_delta)):
                METRICS.increment("productionEditBackups")
            METRICS.append("proposeEditApplyTimeline", {
                "proposalShapeMatches": proposal_shape_matches(proposal),
                "fileBefore": file_before,
                "fileAfter": file_after,
                "conflictObserved": conflict_observed,
                "result": apply_result_projection(result, proposal),
            })
            METRICS.append("proposeEditWriteTimeline", {
                "fileBefore": file_before,
                "fileAfter": file_after,
                "writeObserved": write_observed,
                "targetHashMatches": file_after["targetHashMatches"],
            })
            METRICS.append("proposeEditBackupTimeline", {
                "beforeCount": backups_before["count"],
                "afterCount": backups_after["count"],
                "delta": backup_delta,
                "initialContentMatchDelta": initial_backup_delta,
                "backupObserved": backup_delta == 1 and initial_backup_delta == 1,
            })
            if conflict_observed:
                METRICS.append("proposeEditConflictTimeline", {
                    "observed": True,
                    "exceptionTypeMatches": True,
                    "fileBefore": file_before,
                    "fileAfter": file_after,
                    "fixturePreserved": file_after == file_before,
                    "backupDelta": backup_delta,
                })

    def counted_execute_registered_tool(action, payload, *, _arguments_validated=False):
        if action == "propose_edit":
            if (
                not isinstance(payload, dict)
                or set(payload) != set(PROPOSE_EDIT_TOOL_ARGUMENTS)
                or payload != PROPOSE_EDIT_TOOL_ARGUMENTS
            ):
                METRICS.increment("unsafeToolRequests")
                raise ValueError("H4 propose_edit request changed the exact fixed payload")
            if propose_edit_fixture_state()["state"] != "initial":
                METRICS.increment("unsafeToolRequests")
                raise ValueError("H4 propose_edit fixture precondition changed")
            return delegate_propose_edit_to_production(
                action,
                payload,
                _arguments_validated=_arguments_validated,
            )
        if action != "read_file":
            METRICS.increment("unsafeToolRequests")
            raise ValueError("H4 tool action is outside the read-only fixture contract")
        requested = str((payload or {}).get("path") or "")
        payload_keys = set((payload or {}).keys())
        is_missing_read = requested == MISSING_READ_PATH
        is_signature_alternation_read = requested == SIGNATURE_ALTERNATION_READ_PATH
        is_success_reset_read = requested == SUCCESS_RESET_READ_PATH
        is_parallel_visual_read = requested in set(PARALLEL_VISUAL_PROTOCOL_PATHS)
        if requested not in {
            READ_PATH,
            MISSING_READ_PATH,
            SIGNATURE_ALTERNATION_READ_PATH,
            SUCCESS_RESET_READ_PATH,
            *PARALLEL_VISUAL_PROTOCOL_PATHS,
        }:
            METRICS.increment("unsafeToolRequests")
            raise ValueError("H4 read_file request escaped the fixed synthetic fixture")
        if is_missing_read and payload_keys != {"path"}:
            METRICS.increment("unsafeToolRequests")
            raise ValueError("H4 missing-file request changed the exact fixed payload")
        if is_parallel_visual_read and payload_keys != {"path"}:
            METRICS.increment("unsafeToolRequests")
            raise ValueError("H4 parallel visual request changed the exact fixed payload")
        if is_missing_read and (
            missing_project_target.exists() or missing_home_target.exists()
        ):
            METRICS.increment("unsafeToolRequests")
            raise ValueError("H4 missing-file fixture precondition changed")
        if is_signature_alternation_read and (
            payload_keys != set(SIGNATURE_ALTERNATION_TOOL_ARGUMENTS)
            or payload != SIGNATURE_ALTERNATION_TOOL_ARGUMENTS
        ):
            METRICS.increment("unsafeToolRequests")
            raise ValueError("H4 signature-alternation request changed the fixed payload")
        if is_success_reset_read and (
            payload_keys != set(SUCCESS_RESET_TOOL_ARGUMENTS)
            or payload != SUCCESS_RESET_TOOL_ARGUMENTS
        ):
            METRICS.increment("unsafeToolRequests")
            raise ValueError("H4 success-reset request changed the fixed payload")
        start_line = (payload or {}).get("startLine")
        end_line = (payload or {}).get("endLine")
        is_second_multi_read = start_line == 1 and end_line == 1
        if is_second_multi_read and not REFRESH_GATES.reach_and_wait(
            "before-second-tool-execute",
        ):
            raise TimeoutError("H4 second read_file execution gate timed out")
        def delegate_to_production():
            execution_metric = {
                "action": "read_file",
                "path": requested,
            }
            if start_line is not None:
                execution_metric["startLine"] = start_line
            if end_line is not None:
                execution_metric["endLine"] = end_line
            METRICS.append("toolExecutions", execution_metric)
            METRICS.increment("productionToolDelegations")
            return original_execute_registered_tool(
                action,
                payload,
                _arguments_validated=_arguments_validated,
            )

        if is_signature_alternation_read or is_success_reset_read:
            with controlled_fixture_lock:
                controlled_fixture_invocations[requested] += 1
                call_number = controlled_fixture_invocations[requested]
                if call_number not in (1, 2, 3):
                    METRICS.increment("unsafeToolRequests")
                    raise ValueError("H4 controlled fixture call count exceeded the contract")
                target = controlled_fixture_targets[requested]
                if is_signature_alternation_read:
                    expected_state = "missing" if call_number == 2 else "present"
                    timeline_metric = "signatureAlternationFixtureTimeline"
                else:
                    expected_state = "present" if call_number == 2 else "missing"
                    timeline_metric = "successResetFixtureTimeline"
                if expected_state == "present":
                    target.write_bytes(fixture_bytes)
                elif target.exists():
                    if not target.is_file():
                        raise RuntimeError("H4 controlled fixture removal target is not a file")
                    target.unlink()
                state = controlled_fixture_state(target)
                if state["observedState"] != expected_state:
                    raise RuntimeError("H4 controlled fixture state switch did not converge")
                if expected_state == "present" and not state["hashMatches"]:
                    raise RuntimeError("H4 controlled fixture bytes changed")
                try:
                    return delegate_to_production()
                finally:
                    counters = METRICS.snapshot()
                    state_after = controlled_fixture_state(target)
                    METRICS.append(timeline_metric, {
                        "callNumber": call_number,
                        "expectedState": expected_state,
                        **state_after,
                        "delegationCount": counters["productionToolDelegations"],
                        "executionCount": len(counters["toolExecutions"]),
                    })

        try:
            return delegate_to_production()
        finally:
            if is_missing_read and (
                missing_project_target.exists() or missing_home_target.exists()
            ):
                raise RuntimeError("H4 missing-file fixture was created during execution")

    def rejected_execute_run_command_tool(
        body,
        *,
        cancel_event=None,
        output_callback=None,
        process_callback=None,
    ):
        payload = body if isinstance(body, dict) else {}
        METRICS.increment("unsafeToolRequests")
        METRICS.append("runCommandAttempts", {
            "payloadIsObject": isinstance(body, dict),
            "keyCount": len(payload),
            "commandPresent": bool(str(payload.get("command") or "").strip()),
            "cancelEventPresent": cancel_event is not None,
            "outputCallbackPresent": callable(output_callback),
            "processCallbackPresent": callable(process_callback),
        })
        raise ValueError("H4 run_command is outside the isolated fixture contract")

    def probe_tool_boundary():
        before = METRICS.snapshot()
        rejected_action = False
        rejected_path = False
        try:
            counted_execute_registered_tool("list_files", {"path": ""})
        except ValueError:
            rejected_action = True
        try:
            counted_execute_registered_tool("read_file", {"path": "../outside.txt"})
        except ValueError:
            rejected_path = True
        allowed_result = counted_execute_registered_tool("read_file", {"path": READ_PATH})
        after_read = METRICS.snapshot()

        rejected_write = False
        rejected_delete = False
        try:
            counted_execute_registered_tool("write_file", {"path": PROPOSE_EDIT_PATH})
        except ValueError:
            rejected_write = True
        try:
            counted_execute_registered_tool("delete_file", {"path": PROPOSE_EDIT_PATH})
        except ValueError:
            rejected_delete = True
        after_registry_rejections = METRICS.snapshot()

        edit_before = after_registry_rejections
        rejected_proposal_path = False
        rejected_proposal_keys = False
        rejected_proposal_bytes = False
        for field, invalid_payload in (
            (
                "path",
                {**PROPOSE_EDIT_TOOL_ARGUMENTS, "path": "../outside.txt"},
            ),
            (
                "keys",
                {**PROPOSE_EDIT_TOOL_ARGUMENTS, "unexpected": True},
            ),
            (
                "bytes",
                {**PROPOSE_EDIT_TOOL_ARGUMENTS, "oldText": "H4_WRONG_BYTES"},
            ),
        ):
            try:
                counted_execute_registered_tool("propose_edit", invalid_payload)
            except ValueError:
                if field == "path":
                    rejected_proposal_path = True
                elif field == "keys":
                    rejected_proposal_keys = True
                else:
                    rejected_proposal_bytes = True

        edit_file_before = propose_edit_fixture_state()
        edit_backups_before = propose_edit_backup_state()
        allowed_proposal = counted_execute_registered_tool(
            "propose_edit",
            dict(PROPOSE_EDIT_TOOL_ARGUMENTS),
        )

        rejected_apply_action = False
        rejected_apply_path = False
        rejected_apply_keys = False
        rejected_apply_bytes = False
        invalid_proposals = []
        for field, replacement in (
            ("action", {"action": "apply_edit"}),
            ("path", {"path": "../outside.txt"}),
            ("keys", {"unexpected": True}),
            ("bytes", {"newContent": "H4_WRONG_BYTES\n"}),
        ):
            candidate = deepcopy(allowed_proposal)
            candidate.update(replacement)
            invalid_proposals.append((field, candidate))
        for field, invalid_proposal in invalid_proposals:
            try:
                counted_execute_apply_edit_proposal(invalid_proposal)
            except ValueError:
                if field == "action":
                    rejected_apply_action = True
                elif field == "path":
                    rejected_apply_path = True
                elif field == "keys":
                    rejected_apply_keys = True
                else:
                    rejected_apply_bytes = True
        edit_file_after = propose_edit_fixture_state()
        edit_backups_after = propose_edit_backup_state()
        edit_after = METRICS.snapshot()

        run_trees_before = {
            "project": owned_tree_fingerprint(project_dir),
            "home": owned_tree_fingerprint(isolated_home),
            "artifacts": owned_tree_fingerprint(artifacts_dir),
        }
        run_before = edit_after
        output_callbacks = []
        process_callbacks = []
        rejected_run_command = False
        try:
            code_server.execute_run_command_tool(
                {"command": "H4_RUN_COMMAND_MUST_NOT_EXECUTE"},
                output_callback=lambda *_args: output_callbacks.append(True),
                process_callback=lambda *_args: process_callbacks.append(True),
            )
        except ValueError:
            rejected_run_command = True
        run_after = METRICS.snapshot()
        run_trees_after = {
            "project": owned_tree_fingerprint(project_dir),
            "home": owned_tree_fingerprint(isolated_home),
            "artifacts": owned_tree_fingerprint(artifacts_dir),
        }
        reject_stub_symbols = {
            *rejected_execute_run_command_tool.__code__.co_names,
            *rejected_execute_run_command_tool.__code__.co_freevars,
            *rejected_execute_run_command_tool.__code__.co_cellvars,
        }

        return {
            "rejectedAction": rejected_action,
            "rejectedPath": rejected_path,
            "allowedRead": bool(allowed_result.get("ok")),
            "unsafeDelta": (
                after_read["unsafeToolRequests"] - before["unsafeToolRequests"]
            ),
            "delegationDelta": (
                after_read["productionToolDelegations"]
                - before["productionToolDelegations"]
            ),
            "toolExecutionDelta": (
                len(after_read["toolExecutions"])
                - len(before["toolExecutions"])
            ),
            "registryMutationActions": {
                "rejectedWrite": rejected_write,
                "rejectedDelete": rejected_delete,
                "unsafeDelta": (
                    after_registry_rejections["unsafeToolRequests"]
                    - after_read["unsafeToolRequests"]
                ),
                "delegationDelta": (
                    after_registry_rejections["productionToolDelegations"]
                    - after_read["productionToolDelegations"]
                ),
                "toolExecutionDelta": (
                    len(after_registry_rejections["toolExecutions"])
                    - len(after_read["toolExecutions"])
                ),
            },
            "proposeEdit": {
                "rejectedPathEscape": rejected_proposal_path,
                "rejectedKeys": rejected_proposal_keys,
                "rejectedBytes": rejected_proposal_bytes,
                "rejectedApplyAction": rejected_apply_action,
                "rejectedApplyPathEscape": rejected_apply_path,
                "rejectedApplyKeys": rejected_apply_keys,
                "rejectedApplyBytes": rejected_apply_bytes,
                "allowedProposal": proposal_shape_matches(allowed_proposal),
                "proposalApplied": allowed_proposal.get("applied") is True,
                "initialFilePreserved": (
                    edit_file_before["state"] == "initial"
                    and edit_file_after == edit_file_before
                ),
                "backupCountUnchanged": edit_backups_after == edit_backups_before,
                "unsafeDelta": (
                    edit_after["unsafeToolRequests"]
                    - edit_before["unsafeToolRequests"]
                ),
                "delegationDelta": (
                    edit_after["productionToolDelegations"]
                    - edit_before["productionToolDelegations"]
                ),
                "toolExecutionDelta": (
                    len(edit_after["toolExecutions"])
                    - len(edit_before["toolExecutions"])
                ),
                "proposalDelegationDelta": (
                    edit_after["productionEditProposalDelegations"]
                    - edit_before["productionEditProposalDelegations"]
                ),
                "applyDelegationDelta": (
                    edit_after["productionEditApplyDelegations"]
                    - edit_before["productionEditApplyDelegations"]
                ),
                "writeDelta": (
                    edit_after["productionEditWrites"]
                    - edit_before["productionEditWrites"]
                ),
                "backupDelta": (
                    edit_after["productionEditBackups"]
                    - edit_before["productionEditBackups"]
                ),
                "proposalTimelineDelta": (
                    len(edit_after["proposeEditProposalTimeline"])
                    - len(edit_before["proposeEditProposalTimeline"])
                ),
                "applyTimelineDelta": (
                    len(edit_after["proposeEditApplyTimeline"])
                    - len(edit_before["proposeEditApplyTimeline"])
                ),
                "writeTimelineDelta": (
                    len(edit_after["proposeEditWriteTimeline"])
                    - len(edit_before["proposeEditWriteTimeline"])
                ),
                "backupTimelineDelta": (
                    len(edit_after["proposeEditBackupTimeline"])
                    - len(edit_before["proposeEditBackupTimeline"])
                ),
            },
            "runCommand": {
                "rejectedRunCommand": rejected_run_command,
                "attemptDelta": (
                    len(run_after["runCommandAttempts"])
                    - len(run_before["runCommandAttempts"])
                ),
                "unsafeDelta": (
                    run_after["unsafeToolRequests"]
                    - run_before["unsafeToolRequests"]
                ),
                "entryIsRejectStub": (
                    code_server.execute_run_command_tool
                    is rejected_execute_run_command_tool
                ),
                "capturedOriginalCallable": callable(original_execute_run_command_tool),
                "stubReferencesOriginal": any(
                    name in reject_stub_symbols
                    for name in (
                        "original_execute_run_command_tool",
                        "delegate_run_command_to_production",
                    )
                ),
                "outputCallbackDelta": len(output_callbacks),
                "processCallbackDelta": len(process_callbacks),
                "projectTreeUnchanged": (
                    run_trees_after["project"] == run_trees_before["project"]
                ),
                "homeTreeUnchanged": (
                    run_trees_after["home"] == run_trees_before["home"]
                ),
                "artifactsTreeUnchanged": (
                    run_trees_after["artifacts"] == run_trees_before["artifacts"]
                ),
                "allTreesUnchanged": run_trees_after == run_trees_before,
            },
        }

    code_server.execute_registered_tool = counted_execute_registered_tool
    code_server.execute_apply_edit_proposal = counted_execute_apply_edit_proposal
    code_server.execute_run_command_tool = rejected_execute_run_command_tool
    code_server.ThreadingHTTPServer.daemon_threads = True
    code_server._migrate_sessions_to_hierarchy()
    code_server._migrate_codex_project_sessions_support()
    code_server._migrate_project_root_paths()
    code_httpd = code_server.ThreadingHTTPServer(("127.0.0.1", 0), H4CodeHandler)
    code_httpd.daemon_threads = True
    code_port = code_httpd.server_address[1]
    code_thread = threading.Thread(target=code_httpd.serve_forever, daemon=True)
    code_thread.start()

    sensitive_environment_names = sorted(
        name
        for name in os.environ
        if re.search(r"(?:KEY|TOKEN|SECRET|PASSWORD|COOKIE|AUTH)", name, re.IGNORECASE)
    )
    _json_line({
        "type": "ready",
        "codeUrl": f"http://127.0.0.1:{code_port}",
        "fakeUrl": fake_url,
        "codePort": code_port,
        "fakePort": fake_port,
        "fixtureSha256": fixture_sha256,
        "proposeEditFixture": {
            "path": PROPOSE_EDIT_PATH,
            "initialSha256": PROPOSE_EDIT_INITIAL_SHA256,
            "targetSha256": PROPOSE_EDIT_TARGET_SHA256,
        },
        "proposeEditThirdPartyTransition": {
            "command": PROPOSE_EDIT_THIRD_PARTY_TRANSITION_COMMAND,
            "path": PROPOSE_EDIT_PATH,
            "expectedBeforeSha256": PROPOSE_EDIT_INITIAL_SHA256,
            "byteLength": len(propose_edit_third_party_bytes),
            "targetSha256": PROPOSE_EDIT_THIRD_PARTY_SHA256,
        },
        "environment": {
            "parentSentinelPresent": "H4_PARENT_SECRET_SENTINEL" in os.environ,
            "sensitiveNames": sensitive_environment_names,
            "homeIsIsolated": Path.home().resolve() == (root / "home").resolve(),
        },
    })

    try:
        for raw_line in sys.stdin:
            try:
                command = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            request_id = command.get("id")
            operation = command.get("command")
            if operation == "release-model-response":
                MODEL_GATE.set()
                _json_line({
                    "type": "response",
                    "id": request_id,
                    "ok": True,
                    "modelGateReleased": MODEL_GATE.is_set(),
                    "modelCatalogGate": MODEL_CATALOG_GATE.snapshot(),
                })
                continue
            if operation == "release-model":
                MODEL_GATE.set()
                REFRESH_GATES.release_all(exclude={"goal-final-after-first-delta"})
                MODEL_CATALOG_GATE.release()
                _json_line({"type": "response", "id": request_id, "ok": True})
                continue
            if operation == "arm-model-catalog":
                MODEL_CATALOG_GATE.arm()
                _json_line({
                    "type": "response",
                    "id": request_id,
                    "ok": True,
                    "gate": MODEL_CATALOG_GATE.snapshot(),
                })
                continue
            if operation == "wait-model-catalog":
                reached = MODEL_CATALOG_GATE.wait_until_reached(timeout=5.0)
                _json_line({
                    "type": "response",
                    "id": request_id,
                    "ok": reached,
                    "gate": MODEL_CATALOG_GATE.snapshot(),
                })
                continue
            if operation == "release-model-catalog":
                MODEL_CATALOG_GATE.release()
                _json_line({
                    "type": "response",
                    "id": request_id,
                    "ok": True,
                    "gate": MODEL_CATALOG_GATE.snapshot(),
                })
                continue
            if operation == "metrics":
                request_started = time.monotonic()
                _metrics_breadcrumb(
                    "request_received",
                    request_started,
                    request_started,
                    "started",
                )
                metrics = _run_metrics_phase(
                    "metrics_snapshot",
                    request_started,
                    METRICS.snapshot,
                )

                def gate_snapshots():
                    return {
                        "modelCatalogGate": MODEL_CATALOG_GATE.snapshot(),
                        "refreshGates": REFRESH_GATES.snapshot(),
                    }

                gates = _run_metrics_phase(
                    "gate_snapshots",
                    request_started,
                    gate_snapshots,
                )
                metrics.update(gates)
                metrics["production"] = _run_metrics_phase(
                    "production_snapshot",
                    request_started,
                    lambda: _production_snapshot(code_server),
                )
                metrics["sessionJsonl"] = _run_metrics_phase(
                    "session_jsonl",
                    request_started,
                    lambda: _session_jsonl_evidence(code_server),
                )
                metrics["attachments"] = _run_metrics_phase(
                    "attachments",
                    request_started,
                    lambda: _attachment_evidence(code_server),
                )
                response = {
                    "type": "response",
                    "id": request_id,
                    "ok": True,
                    "metrics": metrics,
                }
                _run_metrics_phase(
                    "response_emit",
                    request_started,
                    lambda: _json_line(response),
                )
                continue
            if operation == "probe-tool-boundary":
                _json_line({
                    "type": "response",
                    "id": request_id,
                    "ok": True,
                    "contract": probe_tool_boundary(),
                })
                continue
            if operation == "seed-legacy-questionnaire":
                legacy_questionnaire = seed_legacy_questionnaire()
                _json_line({
                    "type": "response",
                    "id": request_id,
                    "ok": True,
                    "legacyQuestionnaire": legacy_questionnaire,
                })
                continue
            if operation == "seed-tool-protocol-history":
                seeded_history = seed_tool_protocol_history()
                _json_line({
                    "type": "response",
                    "id": request_id,
                    "ok": True,
                    "toolProtocolHistory": seeded_history,
                })
                continue
            if operation == "set-model-route-catalog-outage":
                route_state = MODEL_ROUTE_FIXTURE.set_catalog_outage(
                    bool(command.get("enabled")),
                )
                _json_line({
                    "type": "response",
                    "id": request_id,
                    "ok": True,
                    "modelRoute": route_state,
                })
                continue
            if operation == PROPOSE_EDIT_THIRD_PARTY_TRANSITION_COMMAND:
                transition = transition_propose_edit_third_party(command)
                _json_line({
                    "type": "response",
                    "id": request_id,
                    "ok": transition["accepted"],
                    "transition": transition,
                })
                continue
            if operation == "shutdown":
                _json_line({"type": "response", "id": request_id, "ok": True})
                break
            _json_line({"type": "response", "id": request_id, "ok": False})
    finally:
        MODEL_GATE.set()
        MODEL_CATALOG_GATE.release()
        REFRESH_GATES.release_all()
        try:
            code_httpd.shutdown()
            fake_server.shutdown()
            code_httpd.server_close()
            fake_server.server_close()
            code_thread.join(timeout=3)
            fake_thread.join(timeout=3)
        finally:
            with controlled_fixture_lock:
                for controlled_target in controlled_fixture_targets.values():
                    if controlled_target.exists():
                        controlled_target.unlink()
                    if controlled_target.exists():
                        raise RuntimeError("H4 controlled fixture cleanup failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
