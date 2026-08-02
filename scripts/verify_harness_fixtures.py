#!/usr/bin/env python3
"""Validate and fingerprint the synthetic Harness compatibility fixtures.

This module is intentionally independent from the production Agent runtime. It
may inspect checked-in JSON/JSONL fixtures, but it never reads data/ sessions,
credentials, the network, or browser state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent.parent
HARNESS_FIXTURES = ROOT / "tests" / "fixtures" / "harness"
TRACE_SUITE_PATH = HARNESS_FIXTURES / "trace-suite.json"
COMPATIBILITY_DIR = HARNESS_FIXTURES / "compatibility"
INVENTORY_PATH = ROOT / "docs" / "harness" / "h0-1-fact-inventory.json"

FIXTURE_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
ISO_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")
SECRET_TEXT_PATTERNS = (
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{8,}", re.IGNORECASE),
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}", re.IGNORECASE),
    re.compile(r"\b(?:api[_ -]?key|access[_ -]?token)\s*[:=]\s*[^\s,}\]]+", re.IGNORECASE),
    re.compile(r"(?:[A-Za-z]:\\Users\\|/home/|/Users/)", re.IGNORECASE),
)
SENSITIVE_KEYS = {
    "apikey",
    "api_key",
    "accesstoken",
    "access_token",
    "authorization",
    "cookie",
    "cookies",
    "headers",
    "keys",
    "password",
}
ALLOWED_URL_SUFFIXES = (".example.test", ".example.invalid")
MAX_FIXTURE_STRING = 2_048


class FixtureValidationError(ValueError):
    """Raised when a checked-in Harness fixture violates the frozen format."""


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_hash(value) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load_trace_suite():
    return _load_json(TRACE_SUITE_PATH)


def known_agent_events() -> set[str]:
    inventory = _load_json(INVENTORY_PATH)
    return {item["type"] for item in inventory["agentRun"]["events"]}


def known_agent_statuses() -> set[str]:
    inventory = _load_json(INVENTORY_PATH)
    return {item["name"] for item in inventory["agentRun"]["statuses"]}


def _require(condition: bool, message: str):
    if not condition:
        raise FixtureValidationError(message)


def validate_trace_suite(suite=None) -> dict:
    suite = load_trace_suite() if suite is None else suite
    _require(isinstance(suite, dict), "trace suite must be an object")
    _require(suite.get("fixtureVersion") == 1, "fixtureVersion must be 1")
    _require(suite.get("source") == "synthetic", "trace suite must be synthetic")
    fixtures = suite.get("fixtures")
    _require(isinstance(fixtures, list), "fixtures must be a list")
    _require(len(fixtures) >= 10, "at least 10 trace fixtures are required")

    known_events = known_agent_events()
    known_statuses = known_agent_statuses()
    names = set()
    event_count = 0
    recovery_count = 0
    for fixture in fixtures:
        _require(isinstance(fixture, dict), "each trace fixture must be an object")
        name = fixture.get("name")
        _require(isinstance(name, str) and FIXTURE_NAME_RE.fullmatch(name), f"invalid fixture name: {name!r}")
        _require(name not in names, f"duplicate fixture name: {name}")
        names.add(name)
        _require(fixture.get("source") == "synthetic", f"{name}: source must be synthetic")

        initial = fixture.get("initialSnapshot")
        _require(isinstance(initial, dict), f"{name}: initialSnapshot must be an object")
        _require(initial.get("status") in known_statuses, f"{name}: unknown initial status")
        _require(initial.get("eventCursor") == 0, f"{name}: initial cursor must be zero")

        events = fixture.get("events")
        _require(isinstance(events, list) and events, f"{name}: events must be non-empty")
        sequences = []
        event_types = []
        for event in events:
            _require(isinstance(event, dict), f"{name}: event must be an object")
            _require(set(event) == {"seq", "type", "data", "createdAt"}, f"{name}: event envelope fields drifted")
            _require(isinstance(event["seq"], int) and event["seq"] > 0, f"{name}: invalid event seq")
            _require(event["type"] in known_events, f"{name}: unknown event {event['type']!r}")
            _require(isinstance(event["data"], dict), f"{name}: event data must be an object")
            _require(isinstance(event["createdAt"], str) and ISO_UTC_RE.fullmatch(event["createdAt"]), f"{name}: invalid createdAt")
            sequences.append(event["seq"])
            event_types.append(event["type"])
        _require(sequences == list(range(1, len(events) + 1)), f"{name}: seq must be contiguous from 1")
        event_count += len(events)

        checkpoints = fixture.get("checkpoints")
        _require(isinstance(checkpoints, list) and checkpoints, f"{name}: checkpoints must be non-empty")
        for checkpoint in checkpoints:
            after_seq = checkpoint.get("afterSeq")
            _require(after_seq in sequences, f"{name}: checkpoint references missing seq")
            expected_state = checkpoint.get("expectedState")
            _require(isinstance(expected_state, dict), f"{name}: expectedState must be an object")
            _require(expected_state.get("status") in known_statuses, f"{name}: checkpoint has unknown status")
            expected_timeline = checkpoint.get("expectedTimeline")
            _require(expected_timeline == event_types[:after_seq], f"{name}: checkpoint timeline does not match event prefix")

        terminal = fixture.get("expectedTerminal")
        _require(isinstance(terminal, dict), f"{name}: expectedTerminal must be an object")
        _require(terminal.get("status") in {"completed", "failed", "cancelled"}, f"{name}: invalid terminal status")
        _require(terminal.get("eventType") == event_types[-1], f"{name}: terminal event must be last")

        for recovery in fixture.get("recoveryPoints") or []:
            _require(recovery.get("afterSeq") in sequences, f"{name}: recovery point references missing seq")
            cursor = recovery.get("cursor")
            _require(isinstance(cursor, int) and 0 <= cursor <= recovery["afterSeq"], f"{name}: invalid recovery cursor")
            _require(recovery.get("kind") in {"page-refresh", "poll-disconnect", "service-restart"}, f"{name}: invalid recovery kind")
            recovery_count += 1

    return {
        "fixtureCount": len(fixtures),
        "eventCount": event_count,
        "recoveryPointCount": recovery_count,
        "suiteHash": canonical_hash(suite),
        "names": sorted(names),
    }


def _walk_values(value, path="$" ):
    if isinstance(value, dict):
        for key, child in value.items():
            yield f"{path}.{key}", key, child
            yield from _walk_values(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_values(child, f"{path}[{index}]")


def _scan_value(value, source: str) -> list[str]:
    findings = []
    for path, key, child in _walk_values(value):
        if str(key).lower() in SENSITIVE_KEYS:
            findings.append(f"{source}:{path}: sensitive key {key!r}")
        if not isinstance(child, str):
            continue
        if len(child) > MAX_FIXTURE_STRING:
            findings.append(f"{source}:{path}: string exceeds {MAX_FIXTURE_STRING} characters")
        for pattern in SECRET_TEXT_PATTERNS:
            if pattern.search(child):
                findings.append(f"{source}:{path}: sensitive text matched {pattern.pattern!r}")
        for url in re.findall(r"https?://[^\s\"'<>]+", child):
            hostname = (urlparse(url).hostname or "").lower()
            if not hostname.endswith(ALLOWED_URL_SUFFIXES):
                findings.append(f"{source}:{path}: non-example URL {url!r}")
    return findings


def load_compatibility_fixtures() -> dict[str, object]:
    fixtures = {}
    for path in sorted(COMPATIBILITY_DIR.iterdir()):
        if path.suffix == ".json":
            fixtures[path.name] = _load_json(path)
        elif path.suffix == ".jsonl":
            fixtures[path.name] = path.read_text(encoding="utf-8")
    return fixtures


def scan_sensitive_fixtures() -> list[str]:
    findings = _scan_value(load_trace_suite(), TRACE_SUITE_PATH.name)
    for name, value in load_compatibility_fixtures().items():
        if isinstance(value, str):
            for line_number, line in enumerate(value.splitlines(), start=1):
                if not line.strip():
                    continue
                try:
                    parsed = json.loads(line)
                except json.JSONDecodeError:
                    parsed = line
                findings.extend(_scan_value({"line": parsed}, f"{name}:{line_number}"))
        else:
            findings.extend(_scan_value(value, name))
    return findings


def trace_walk_hash(suite, event_target: int) -> str:
    """Return a deterministic hash for an event walk of the requested size.

    This is deliberately not called a production replay: H0 has no canonical
    reducer yet. It is the stable workload that later H2/H3 replay baselines
    must replace without changing the checked-in scenario facts.
    """
    fixtures = suite["fixtures"]
    source_events = [
        {"fixture": fixture["name"], **event}
        for fixture in fixtures
        for event in fixture["events"]
    ]
    walked = [source_events[index % len(source_events)] for index in range(event_target)]
    return canonical_hash(walked)


def benchmark_trace_walks(suite=None, sizes=(100, 1_000, 10_000)) -> list[dict]:
    suite = load_trace_suite() if suite is None else suite
    results = []
    for size in sizes:
        started = time.perf_counter()
        digest = trace_walk_hash(suite, size)
        elapsed_ms = (time.perf_counter() - started) * 1_000
        results.append({"events": size, "elapsedMs": round(elapsed_ms, 3), "hash": digest})
    return results


def validate_all() -> dict:
    summary = validate_trace_suite()
    findings = scan_sensitive_fixtures()
    if findings:
        raise FixtureValidationError("fixture sanitization failed:\n" + "\n".join(findings))
    compatibility = load_compatibility_fixtures()
    required = {
        "agent-run-v1.json",
        "agent-run-v2.json",
        "agent-run-v3.json",
        "session-legacy-partial.jsonl",
        "classic-frontend.json",
    }
    missing = required - compatibility.keys()
    _require(not missing, f"missing compatibility fixtures: {sorted(missing)}")
    summary["compatibilityFixtureCount"] = len(compatibility)
    return summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark", action="store_true", help="also time deterministic 100/1000/10000 event walks")
    args = parser.parse_args(argv)
    summary = validate_all()
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    if args.benchmark:
        print(json.dumps(benchmark_trace_walks(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
