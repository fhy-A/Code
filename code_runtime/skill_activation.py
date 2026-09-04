"""Canonical, bounded Skill activation for new foreground AgentRuns."""

from __future__ import annotations

import hashlib
from itertools import islice
import json
import os
from pathlib import Path
import re
import stat
from typing import Callable, Iterable

from code_runtime.skill_dependencies import (
    DependencyManifestError,
    resolve_skill_manifest,
)
from code_runtime.skill_registry import (
    MAX_SIDECAR_BYTES,
    MAX_SKILL_BYTES,
    SAFE_DIRECTORY_RE,
    SAFE_NAME_RE,
    SkillRegistryError,
    build_skill_registry_snapshot,
    parse_skill_document,
    project_skill_tools,
    resolve_skill_shadow,
)


ACTIVATION_PROTOCOL = "canonical-v1"
ACTIVATION_SCHEMA_VERSION = 1
SKILL_PROMPT_MARKER = "[[CODE_SKILL_ACTIVATION_CANONICAL_V1]]"
DELEGATION_BEGIN_MARKER = "[[CODE_TASK_DELEGATION_CANONICAL_V1_BEGIN]]"
DELEGATION_END_MARKER = "[[CODE_TASK_DELEGATION_CANONICAL_V1_END]]"

MAX_REGISTRY_ENTRIES = 256
MAX_REGISTRY_METADATA_BYTES = 512 * 1024
MAX_DISABLED_NAMES = 128
MAX_SELECTED_SKILLS = 2
MAX_REFERENCES = 2
MAX_BODY_BYTES = 64 * 1024
MAX_BODY_TOKENS = 12_000
MAX_INSTRUCTION_BYTES = 96 * 1024
MAX_INSTRUCTION_TOKENS = 20_000
MAX_EVIDENCE_BYTES = 64 * 1024

_DELEGATION_REQUEST_RE = re.compile(
    r"(?:子\s*agent|子任务|sub-?agents?|parallel\s+agents?|并行.{0,6}(?:agent|任务))",
    re.I,
)
_DEEP_AUDIT_RE = re.compile(
    r"(?:深度|全面|完整).{0,6}(?:审计|审查|调查)|"
    r"deep\s+(?:audit|review)|exhaustive\s+(?:audit|review)",
    re.I,
)


class SkillActivationError(ValueError):
    """Stable fail-closed error for canonical Skill activation."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = str(code)


def _sha256(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _unique_names(values: Iterable[str], *, limit: int) -> list[str]:
    names = []
    for value in values:
        if not isinstance(value, str):
            raise SkillActivationError("activation_intent_invalid", "Skill names must be strings")
        name = value.strip()
        if not SAFE_NAME_RE.fullmatch(name):
            raise SkillActivationError("activation_intent_invalid", "Skill name is invalid")
        if name not in names:
            names.append(name)
        if len(names) > limit:
            raise SkillActivationError("activation_intent_too_large", "Skill intent is too large")
    return names


def normalize_activation_request(value) -> dict:
    if not isinstance(value, dict) or set(value) != {
        "schemaVersion", "explicitSkill", "disabledNames",
    }:
        raise SkillActivationError(
            "activation_intent_invalid", "Skill activation request is invalid",
        )
    version = value.get("schemaVersion")
    if isinstance(version, bool) or not isinstance(version, int) or version != ACTIVATION_SCHEMA_VERSION:
        raise SkillActivationError(
            "activation_protocol_unsupported", "Skill activation protocol is unsupported",
        )
    explicit = value.get("explicitSkill")
    if not isinstance(explicit, str):
        raise SkillActivationError("activation_intent_invalid", "Explicit Skill must be text")
    explicit = explicit.strip()
    if explicit and not SAFE_NAME_RE.fullmatch(explicit):
        raise SkillActivationError("activation_intent_invalid", "Explicit Skill name is invalid")
    disabled = value.get("disabledNames")
    if not isinstance(disabled, list) or len(disabled) > MAX_DISABLED_NAMES:
        raise SkillActivationError(
            "activation_intent_too_large", "Disabled Skill names must be a bounded array",
        )
    return {
        "schemaVersion": ACTIVATION_SCHEMA_VERSION,
        "explicitSkill": explicit,
        "disabledNames": _unique_names(disabled, limit=MAX_DISABLED_NAMES),
    }


def normalize_allowed_tools_envelope(value) -> list[str]:
    if not isinstance(value, dict) or set(value) != {"schemaVersion", "names"}:
        raise SkillActivationError(
            "activation_tool_envelope_invalid", "Canonical allowedTools is invalid",
        )
    version = value.get("schemaVersion")
    names = value.get("names")
    if isinstance(version, bool) or not isinstance(version, int) or version != ACTIVATION_SCHEMA_VERSION:
        raise SkillActivationError(
            "activation_protocol_unsupported", "Skill activation protocol is unsupported",
        )
    if not isinstance(names, list) or len(names) > 128:
        raise SkillActivationError(
            "activation_tool_envelope_invalid", "Canonical allowedTools is invalid",
        )
    normalized = []
    for value in names:
        if not isinstance(value, str):
            raise SkillActivationError(
                "activation_tool_envelope_invalid", "Canonical tool names must be strings",
            )
        name = value.strip()
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", name):
            raise SkillActivationError(
                "activation_tool_envelope_invalid", "Canonical tool name is invalid",
            )
        if name not in normalized:
            normalized.append(name)
    return normalized


def _is_link_or_reparse(path: Path) -> bool:
    metadata = os.lstat(path)
    if stat.S_ISLNK(metadata.st_mode):
        return True
    attributes = int(getattr(metadata, "st_file_attributes", 0) or 0)
    reparse_flag = int(getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400) or 0x400)
    return bool(attributes & reparse_flag)


def _require_regular_file(path: Path, *, max_bytes: int, code: str) -> bytes:
    try:
        metadata = os.lstat(path)
        if (
            _is_link_or_reparse(path)
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_size > max_bytes
        ):
            raise OSError("unsafe or oversized file")
        return path.read_bytes()
    except OSError as exc:
        raise SkillActivationError(code, "Selected Skill changed or is unreadable") from exc


def _bounded_registry(installed_root: Path, bundled_root: Path) -> dict:
    try:
        if not installed_root.is_dir() or _is_link_or_reparse(installed_root):
            raise OSError("installed Skill root is unavailable")
    except OSError as exc:
        raise SkillActivationError(
            "activation_registry_unavailable", "Skill registry is unavailable",
        ) from exc
    roots = [installed_root]
    try:
        if installed_root.resolve() != bundled_root.resolve():
            roots.append(bundled_root)
    except OSError:
        roots.append(bundled_root)
    count = 0
    for root in roots:
        try:
            if root.is_dir() and not _is_link_or_reparse(root):
                count += sum(1 for _ in islice(root.iterdir(), MAX_REGISTRY_ENTRIES + 1 - count))
        except OSError as exc:
            raise SkillActivationError(
                "activation_registry_unavailable", "Skill registry is unavailable",
            ) from exc
        if count > MAX_REGISTRY_ENTRIES:
            raise SkillActivationError(
                "activation_registry_too_large", "Skill registry has too many entries",
            )
    try:
        snapshot = build_skill_registry_snapshot(installed_root, bundled_root)
    except (OSError, SkillRegistryError) as exc:
        raise SkillActivationError(
            "activation_registry_unavailable", "Skill registry is unavailable",
        ) from exc
    serialized = json.dumps(
        snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    if len(serialized) > MAX_REGISTRY_METADATA_BYTES:
        raise SkillActivationError(
            "activation_registry_too_large", "Skill registry metadata is too large",
        )
    return snapshot


def _capture_sidecar(skill_dir: Path, descriptor: dict, key: str, filename: str):
    summary = (descriptor.get("sidecars") or {}).get(key) or {}
    expected_state = str(summary.get("state") or "missing")
    path = skill_dir / filename
    if expected_state == "missing":
        try:
            os.lstat(path)
        except FileNotFoundError:
            return {"state": "missing"}, None
        except OSError as exc:
            raise SkillActivationError(
                "activation_skill_changed", "Selected Skill changed or is unreadable",
            ) from exc
        else:
            raise SkillActivationError("activation_skill_changed", "Selected Skill changed")
    raw = _require_regular_file(
        path,
        max_bytes=min(MAX_SIDECAR_BYTES, MAX_EVIDENCE_BYTES) if key == "evidence" else MAX_SIDECAR_BYTES,
        code="activation_skill_changed",
    )
    if expected_state != "ready" or _sha256(raw) != summary.get("contentHash"):
        raise SkillActivationError("activation_skill_changed", "Selected Skill changed")
    return {"state": "ready", "contentHash": summary["contentHash"]}, raw


def _capture_evidence(skill_dir: Path, descriptor: dict):
    identity, raw = _capture_sidecar(
        skill_dir, descriptor, "evidence", "evidence.json",
    )
    if raw is None:
        return None, identity
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SkillActivationError(
            "activation_evidence_invalid", "Selected Skill evidence contract is invalid",
        ) from exc
    if not isinstance(payload, dict):
        raise SkillActivationError(
            "activation_evidence_invalid", "Selected Skill evidence contract is invalid",
        )
    return payload, identity


def _capture_selected_skill(
    descriptor: dict,
    installed_root: Path,
    bundled_root: Path,
    estimate_tokens: Callable[[str], int],
) -> dict:
    source = descriptor.get("source") or {}
    directory = str(source.get("directory") or "")
    if (
        source.get("kind") != "installed"
        or not SAFE_DIRECTORY_RE.fullmatch(directory)
        or not descriptor.get("executableCandidate")
    ):
        raise SkillActivationError("activation_skill_unavailable", "Selected Skill is unavailable")
    skill_dir = installed_root / directory
    try:
        resolved_root = installed_root.resolve(strict=True)
        resolved_dir = skill_dir.resolve(strict=True)
        resolved_dir.relative_to(resolved_root)
        if _is_link_or_reparse(resolved_dir) or not resolved_dir.is_dir():
            raise OSError("unsafe Skill directory")
    except (OSError, ValueError) as exc:
        raise SkillActivationError(
            "activation_skill_unavailable", "Selected Skill is unavailable",
        ) from exc
    raw = _require_regular_file(
        resolved_dir / "SKILL.md",
        max_bytes=MAX_SKILL_BYTES,
        code="activation_skill_changed",
    )
    if _sha256(raw) != descriptor.get("contentHash"):
        raise SkillActivationError("activation_skill_changed", "Selected Skill changed")
    try:
        parsed = parse_skill_document(raw.decode("utf-8-sig"))
    except (UnicodeError, SkillRegistryError) as exc:
        raise SkillActivationError("activation_skill_invalid", "Selected Skill is invalid") from exc
    name = str((parsed.get("meta") or {}).get("name") or "").strip()
    body = str(parsed.get("body") or "").strip()
    if name != descriptor.get("name") or _sha256(body.encode("utf-8")) != descriptor.get("bodyHash"):
        raise SkillActivationError("activation_skill_changed", "Selected Skill changed")
    if len(body.encode("utf-8")) > MAX_BODY_BYTES or estimate_tokens(body) > MAX_BODY_TOKENS:
        raise SkillActivationError("activation_body_too_large", "Selected Skill body is too large")
    evidence, evidence_identity = _capture_evidence(resolved_dir, descriptor)
    try:
        manifest = resolve_skill_manifest(
            resolved_dir, bundled_skills_dir=bundled_root,
        )
    except DependencyManifestError as exc:
        raise SkillActivationError(
            "activation_dependencies_invalid", "Selected Skill dependencies are invalid",
        ) from exc
    _capture_sidecar(
        resolved_dir, descriptor, "dependencies", "dependencies.json",
    )
    resource_summary, _ = _capture_sidecar(
        resolved_dir, descriptor, "resources", "code-resources.json",
    )
    stable_raw = _require_regular_file(
        resolved_dir / "SKILL.md", max_bytes=MAX_SKILL_BYTES, code="activation_skill_changed",
    )
    if _sha256(stable_raw) != descriptor.get("contentHash"):
        raise SkillActivationError("activation_skill_changed", "Selected Skill changed")
    capability_ids = []
    for capability in (manifest or {}).get("capabilities") or []:
        capability_id = str(capability.get("id") or "").strip()
        if re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", capability_id):
            capability_ids.append(capability_id)
    dependency_identity = (
        {
            "state": "ready",
            "manifestHash": _sha256(json.dumps(
                manifest,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")),
            "capabilities": sorted(set(capability_ids)),
        }
        if manifest is not None
        else {"state": "missing", "capabilities": []}
    )
    return {
        "name": name,
        "body": body,
        "contentHash": descriptor["contentHash"],
        "descriptor": descriptor,
        "evidence": evidence,
        "sourceIdentity": {
            "kind": source["kind"],
            "directory": directory,
            "descriptorId": descriptor["descriptorId"],
        },
        "evidenceIdentity": evidence_identity,
        "dependencyIdentity": dependency_identity,
        "resourceIdentity": (
            {
                "state": "ready",
                "contractHash": resource_summary["contentHash"],
            }
            if resource_summary["state"] == "ready"
            else {"state": "missing"}
        ),
        "dependencyCapabilities": sorted(set(capability_ids)),
    }


def _format_skill(capture: dict) -> str:
    descriptor = capture["descriptor"]
    tools = [str(name) for name in descriptor.get("allowedTools") or [] if str(name)]
    capabilities = capture.get("dependencyCapabilities") or []
    dependency_policy = ""
    if capabilities:
        dependency_policy = "\n".join([
            f'Dependency gate: before first use of this Skill in the current task, call check_skill_dependencies with name "{capture["name"]}" as a standalone tool call. Available capabilities: {", ".join(capabilities)}.',
            (
                "Choose only the capability needed by the current task and pass it as capability. If the user only asked for a dependency report, omit capability, summarize the returned statuses, and stop. Never install every capability."
                if len(capabilities) > 1
                else f'Use capability "{capabilities[0]}" when checking or re-checking this Skill.'
            ),
            "If required Python or Node dependencies are missing, install only the declared items using the returned managed-runtime plan after authorization.",
            "System-command dependencies must be installed by the user outside Code. Present supplied installHints verbatim, but never execute them, modify PATH, or create global command wrappers with run_command, propose_edit, or write_file; explain the missing command and wait.",
            "Re-run check_skill_dependencies for the same selected capability after installation and continue only when that capability is ready.",
            "When the dependency result reports a managed runtime, execute Skill scripts with its Python executable or NODE_PATH instead of assuming the system runtime can import those packages.",
        ])
    return "\n".join(filter(None, [
        f"Preferred tools: {', '.join(tools)}" if tools else "",
        "Tool guidance only; this does not expand the current mode's permissions." if tools else "",
        "Do not call task unless it is listed above or the user explicitly requests delegation." if tools else "",
        dependency_policy,
        capture["body"],
    ]))


def _instruction(captures: list[dict], *, explicit: bool) -> str:
    if not captures:
        return ""
    if explicit:
        capture = captures[0]
        return (
            f'=== 已激活 Skill: {capture["name"]}（正文已加载，不要再次调用 use_skill） ===\n'
            f"{_format_skill(capture)}"
        )
    bodies = "\n\n---\n\n".join(
        f'[Skill: {capture["name"]}]\n{_format_skill(capture)}'
        for capture in captures
    )
    return f"=== 匹配的 Skill（正文已加载，不要再次调用 use_skill） ===\n{bodies}"


def _replace_segment(text: str, segment: str, replacement: str) -> str:
    middle = f"\n\n{segment}\n\n"
    if middle in text:
        return text.replace(middle, f"\n\n{replacement}\n\n" if replacement else "\n\n", 1)
    if text.startswith(segment + "\n\n"):
        return (replacement + "\n\n" if replacement else "") + text[len(segment) + 2:]
    if text.endswith("\n\n" + segment):
        return text[:-len(segment) - 2] + ("\n\n" + replacement if replacement else "")
    if text == segment:
        return replacement
    raise SkillActivationError(
        "activation_prompt_marker_invalid", "Canonical Skill prompt marker is invalid",
    )


def _apply_prompt(
    messages: list[dict], instruction: str, initial_tools: list[str], final_tools: list[str],
) -> list[dict]:
    frozen = json.loads(json.dumps(messages, ensure_ascii=False))
    if not frozen or frozen[0].get("role") != "system" or not isinstance(frozen[0].get("content"), str):
        raise SkillActivationError(
            "activation_prompt_marker_invalid", "Canonical Skill prompt must start with system text",
        )
    serialized = json.dumps(frozen, ensure_ascii=False, separators=(",", ":"))
    if serialized.count(SKILL_PROMPT_MARKER) != 1:
        raise SkillActivationError(
            "activation_prompt_marker_invalid", "Canonical Skill prompt marker is invalid",
        )
    frozen[0]["content"] = _replace_segment(
        frozen[0]["content"], SKILL_PROMPT_MARKER, instruction,
    )
    begin_count = serialized.count(DELEGATION_BEGIN_MARKER)
    end_count = serialized.count(DELEGATION_END_MARKER)
    if "task" not in initial_tools:
        if begin_count or end_count:
            raise SkillActivationError(
                "activation_delegation_marker_invalid", "Canonical delegation marker is invalid",
            )
        return frozen
    if begin_count != 1 or end_count != 1:
        raise SkillActivationError(
            "activation_delegation_marker_invalid", "Canonical delegation marker is invalid",
        )
    system = frozen[0]["content"]
    begin = system.find(DELEGATION_BEGIN_MARKER)
    end = system.find(DELEGATION_END_MARKER)
    if begin < 0 or end <= begin:
        raise SkillActivationError(
            "activation_delegation_marker_invalid", "Canonical delegation marker is invalid",
        )
    block = system[begin:end + len(DELEGATION_END_MARKER)]
    inner = system[begin + len(DELEGATION_BEGIN_MARKER):end]
    if not inner.startswith("\n") or not inner.endswith("\n"):
        raise SkillActivationError(
            "activation_delegation_marker_invalid", "Canonical delegation marker is invalid",
        )
    replacement = inner[1:-1] if "task" in final_tools else ""
    frozen[0]["content"] = _replace_segment(system, block, replacement)
    return frozen


def _brainstorming_budgets(active_names: list[str], user_message: str) -> list[dict]:
    if "brainstorming" not in active_names or _DEEP_AUDIT_RE.search(user_message):
        return []
    return [
        {
            "name": "brainstorming-discovery",
            "tools": ["search_files", "glob_files", "list_files"],
            "limit": 3,
            "exhaustedMessage": "已达到 brainstorming 的默认搜索预算。停止继续定位源码，使用已有证据汇总方案，并把缺失事实标为待验证。最终回答不得加入未实测的耗时、资源、规模阈值、优化倍数或性能排名。",
        },
        {
            "name": "brainstorming-reading",
            "tools": ["read_file"],
            "limit": 4,
            "exhaustedMessage": "已达到 brainstorming 的默认读取预算。停止继续读取文件，使用已有证据汇总方案，并把缺失事实标为待验证。最终回答不得加入未实测的耗时、资源、规模阈值、优化倍数或性能排名。",
        },
    ]


def prepare_skill_activation(
    *,
    messages: list[dict],
    user_message: str,
    request,
    installed_skills_dir,
    bundled_skills_dir,
    initial_tool_names: Iterable[str],
    available_input_tokens: int,
    estimate_tokens: Callable[[str], int],
) -> dict:
    """Resolve, capture, budget, and inject selected Skills exactly once."""
    intent = normalize_activation_request(request)
    installed_root = Path(installed_skills_dir)
    bundled_root = Path(bundled_skills_dir)
    registry = _bounded_registry(installed_root, bundled_root)
    try:
        resolution = resolve_skill_shadow(
            registry,
            str(user_message or ""),
            explicit_skill=intent["explicitSkill"],
            disabled_names=intent["disabledNames"],
        )
    except SkillRegistryError as exc:
        raise SkillActivationError("activation_resolution_failed", str(exc)) from exc
    owner = resolution.get("owner")
    if intent["explicitSkill"] and not owner:
        raise SkillActivationError(
            "activation_explicit_skill_unavailable", "Explicit Skill is unavailable",
        )
    descriptor_by_id = {
        descriptor.get("descriptorId"): descriptor
        for descriptor in registry.get("descriptors") or []
    }
    candidates = ([owner] if owner else []) + list(resolution.get("modifiers") or [])
    captures = []
    exclusions = []
    token_limit = min(
        MAX_INSTRUCTION_TOKENS,
        max(0, int(available_input_tokens or 0) // 4),
    )
    for index, candidate in enumerate(candidates[:MAX_SELECTED_SKILLS]):
        descriptor = descriptor_by_id.get((candidate or {}).get("descriptorId"))
        try:
            if not descriptor:
                raise SkillActivationError(
                    "activation_skill_unavailable", "Selected Skill is unavailable",
                )
            capture = _capture_selected_skill(
                descriptor, installed_root, bundled_root, estimate_tokens,
            )
            proposed = [*captures, capture]
            instruction = _instruction(proposed, explicit=bool(intent["explicitSkill"]))
            if (
                len(instruction.encode("utf-8")) > MAX_INSTRUCTION_BYTES
                or estimate_tokens(instruction) > token_limit
            ):
                raise SkillActivationError(
                    "activation_instruction_too_large", "Skill instruction exceeds its input budget",
                )
            captures = proposed
        except SkillActivationError as exc:
            if index == 0:
                raise
            exclusions.append({
                "name": str((candidate or {}).get("name") or ""),
                "reasonCode": exc.code,
            })
    active_names = [capture["name"] for capture in captures]
    initial_tools = []
    for name in initial_tool_names or []:
        name = str(name or "").strip()
        if name and name not in initial_tools:
            initial_tools.append(name)
    final_tools = list(initial_tools)
    for capture in captures:
        final_tools = project_skill_tools(capture["descriptor"], final_tools)["allowed"]
    if (
        captures
        and "task" in final_tools
        and not _DELEGATION_REQUEST_RE.search(str(user_message or ""))
        and not any("task" in (capture["descriptor"].get("allowedTools") or []) for capture in captures)
    ):
        final_tools.remove("task")
    instruction = _instruction(captures, explicit=bool(intent["explicitSkill"]))
    frozen_messages = _apply_prompt(messages, instruction, initial_tools, final_tools)
    return {
        "messages": frozen_messages,
        "activeSkillNames": active_names,
        "captures": captures,
        "dependencies": {
            capture["name"]: list(capture.get("dependencyCapabilities") or [])
            for capture in captures
        },
        "toolNames": final_tools,
        "toolBudgets": _brainstorming_budgets(active_names, str(user_message or "")),
        "references": [
            {
                "name": str(candidate.get("name") or ""),
                "source": str(candidate.get("source") or ""),
                "reasonCode": str(candidate.get("reasonCode") or ""),
            }
            for candidate in list(resolution.get("references") or [])[:MAX_REFERENCES]
        ],
        "exclusions": exclusions,
        "explicit": bool(intent["explicitSkill"]),
    }
