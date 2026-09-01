"""Unified read-only verification entry point."""

from __future__ import annotations

import sys

from devtools.verification import run_doctor, run_profile


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("Usage: python verify.py doctor|quick|ui|runtime|release")
        return 2
    if args[0] == "doctor":
        return run_doctor()
    return run_profile(args[0])


if __name__ == "__main__":
    raise SystemExit(main())
