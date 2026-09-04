"""Maintain the checked-in, content-addressed bundled Skill catalog."""
from __future__ import annotations
import argparse
import os
from pathlib import Path
import sys
import tempfile
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from code_runtime import skill_revisions as revisions  # noqa: E402

def _mapping(values):
    result = {}
    for value in values:
        left, separator, right = str(value).partition("=")
        if not separator or not left or not right or left in result:
            raise revisions.SkillRevisionError("catalog_assignment_invalid", f"Invalid assignment: {value}")
        result[left] = right
    return result
def _atomic_write(path, text):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", delete=False,
            dir=path.parent, prefix=f".{path.name}.", suffix=".tmp",
        ) as stream:
            temporary = Path(stream.name)
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="rewrite revision IDs atomically")
    parser.add_argument("--assign", action="append", default=[], metavar="DIR=SKILL_ID")
    parser.add_argument("--drop", action="append", default=[], metavar="DIR")
    args = parser.parse_args(argv)
    root = ROOT / "data" / "skills"
    path = root / revisions.CATALOG_FILENAME
    catalog = revisions.load_bundled_catalog(path)
    assignments = {item["directory"]: item["skillId"] for item in catalog["skills"]}
    for directory in args.drop:
        if directory not in assignments:
            raise revisions.SkillRevisionError("catalog_assignment_invalid", f"Unknown catalog directory: {directory}")
        del assignments[directory]
    requested = _mapping(args.assign)
    for directory, skill_id in requested.items():
        if directory in assignments and assignments[directory] != skill_id:
            raise revisions.SkillRevisionError(
                "catalog_skill_id_reassignment",
                f"Stable Skill id cannot be reassigned for: {directory}",
            )
    assignments.update(requested)
    if args.write:
        catalog = revisions.build_bundled_catalog(root, assignments)
        _atomic_write(path, revisions.render_bundled_catalog(catalog))
    result = revisions.validate_bundled_catalog(root, catalog)
    print(
        f"SKILL_CATALOG status=passed skills={result['skillCount']} "
        f"hash={result['catalogHash']} mode={'write' if args.write else 'check'}"
    )
    return 0
if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except revisions.SkillRevisionError as exc:
        print(f"SKILL_CATALOG status=failed code={exc.code} error={exc}", file=sys.stderr)
        raise SystemExit(1)
