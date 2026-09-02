"""Audit explicit local helper contracts in the current Code bundled Skills."""

from __future__ import annotations

import json
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
BUNDLED_SKILLS_DIR = APP_DIR / "data" / "skills"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from code_runtime.skill_resources import audit_bundled_skill_resources


def main():
    result = audit_bundled_skill_resources(BUNDLED_SKILLS_DIR)
    sys.stdout.write(json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
