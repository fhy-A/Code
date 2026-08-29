import hashlib
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from scripts import install_locked_skill_wheels as installer


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "data" / "skills" / "ppt-master"
LOCK = SKILL / "dependency-lock.json"
RECEIPT = SKILL / "dependency-receipt.json"
MANAGED_PYTHON = ROOT / "data" / "runtime" / "python" / "Scripts" / "python.exe"


class TestPptMasterDependencyLock(unittest.TestCase):
    def test_lock_and_receipt_pin_only_the_two_admitted_wheels(self):
        lock = json.loads(LOCK.read_text(encoding="utf-8"))
        receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
        self.assertEqual(lock["skill"], "ppt-master")
        self.assertEqual(lock["capability"], "offline-core")
        self.assertEqual(receipt["lockSha256"], hashlib.sha256(LOCK.read_bytes()).hexdigest())
        expected = {"skia-pathops": "0.9.2", "uharfbuzz": "0.50.0"}
        self.assertEqual(
            {item["project"]: item["version"] for item in lock["wheels"]},
            expected,
        )
        self.assertEqual(
            {item["project"]: item["version"] for item in receipt["packages"]},
            expected,
        )
        self.assertEqual(lock["install"]["resolver"], False)
        self.assertEqual(lock["install"]["network"], False)
        self.assertEqual(
            set(lock["install"]["flags"]),
            {"--no-index", "--no-deps", "--only-binary=:all:", "--no-compile"},
        )
        self.assertEqual(receipt["isolation"]["changedDistributions"], sorted(expected))
        self.assertTrue(receipt["isolation"]["rollbackVerified"])
        self.assertTrue(receipt["isolation"]["reinstallVerified"])
        self.assertEqual(
            receipt["rollback"]["command"],
            "python scripts/install_locked_skill_wheels.py rollback",
        )

    def test_managed_runtime_metadata_matches_receipt_without_importing_candidates(self):
        self.assertTrue(MANAGED_PYTHON.is_file())
        program = r'''
import hashlib
import importlib.metadata as metadata
import json
import pathlib
rows = []
for name in ("skia-pathops", "uharfbuzz"):
    dist = metadata.distribution(name)
    record = pathlib.Path(dist._path) / "RECORD"
    rows.append({
        "project": name,
        "version": dist.version,
        "recordSha256": hashlib.sha256(record.read_bytes()).hexdigest(),
    })
print(json.dumps(rows, sort_keys=True))
'''
        completed = subprocess.run(
            [str(MANAGED_PYTHON), "-I", "-c", program],
            cwd=str(ROOT / "data" / "runtime"),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=True,
        )
        actual = json.loads(completed.stdout)
        receipt = json.loads(RECEIPT.read_text(encoding="utf-8"))
        expected = [
            {key: item[key] for key in ("project", "version", "recordSha256")}
            for item in receipt["packages"]
        ]
        self.assertEqual(actual, expected)

    def test_installer_is_fixed_to_managed_no_resolver_plan(self):
        source = (ROOT / "scripts" / "install_locked_skill_wheels.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("execute_dependency_operation_plan", source)
        self.assertIn('"--no-index", "--no-deps"', source)
        self.assertIn('"--only-binary=:all:"', source)
        self.assertNotIn("shell=True", source)
        self.assertNotIn("--index-url", source)
        self.assertNotIn("--upgrade", source)
        self.assertIn('if args.action == "install":', source)
        self.assertIn('wheels = []', source)

    def test_partial_install_failure_must_prove_exact_before_snapshot_restoration(self):
        lock = {
            "skill": "ppt-master",
            "capability": "offline-core",
            "wheels": [
                {"project": "skia-pathops", "version": "0.9.2"},
                {"project": "uharfbuzz", "version": "0.50.0"},
            ],
        }
        before = {
            "prefix": "managed",
            "basePrefix": "base",
            "distributions": [{"name": "pip", "version": "25", "recordSha256": "a"}],
        }
        polluted = {
            **before,
            "distributions": [
                *before["distributions"],
                {"name": "skia-pathops", "version": "0.9.2", "recordSha256": "partial"},
            ],
        }
        with mock.patch.object(sys, "argv", [
            "install_locked_skill_wheels.py", "install", "--wheel-root", "audited"
        ]), mock.patch.object(
            installer, "_safe_wheel_root", return_value=Path("audited")
        ), mock.patch.object(
            installer, "_load_lock", return_value=lock
        ), mock.patch.object(
            installer, "_load_install_contract", return_value=[Path("one.whl"), Path("two.whl")]
        ), mock.patch.object(
            installer, "_distribution_snapshot", side_effect=[before, polluted]
        ) as snapshots, mock.patch.object(
            installer, "_execute", side_effect=[
                {"ok": False, "error": "partial install"},
                {"ok": True},
            ]
        ) as execute:
            with self.assertRaises(installer.LockedInstallError) as raised:
                installer.main()
        self.assertEqual(snapshots.call_count, 2)
        self.assertEqual(execute.call_count, 2)
        self.assertIn("exact pre-install baseline", str(raised.exception))

    def test_failed_install_with_verified_cleanup_reports_restored_not_success(self):
        lock = {
            "skill": "ppt-master",
            "capability": "offline-core",
            "wheels": [
                {"project": "skia-pathops", "version": "0.9.2"},
                {"project": "uharfbuzz", "version": "0.50.0"},
            ],
        }
        before = {
            "prefix": "managed",
            "basePrefix": "base",
            "distributions": [{"name": "pip", "version": "25", "recordSha256": "a"}],
        }
        with mock.patch.object(sys, "argv", [
            "install_locked_skill_wheels.py", "install", "--wheel-root", "audited"
        ]), mock.patch.object(
            installer, "_safe_wheel_root", return_value=Path("audited")
        ), mock.patch.object(
            installer, "_load_lock", return_value=lock
        ), mock.patch.object(
            installer, "_load_install_contract", return_value=[Path("one.whl"), Path("two.whl")]
        ), mock.patch.object(
            installer, "_distribution_snapshot", side_effect=[before, before]
        ), mock.patch.object(
            installer, "_execute", side_effect=[
                {"ok": False, "error": "partial install"},
                {"ok": True},
            ]
        ):
            with self.assertRaises(installer.LockedInstallError) as raised:
                installer.main()
        self.assertIn("baseline was restored", str(raised.exception))

    def test_wheel_auditor_checks_record_license_paths_and_pe_imports(self):
        source = (ROOT / "scripts" / "audit_locked_python_wheels.py").read_text(
            encoding="utf-8"
        )
        for contract in (
            "PyPI SHA-256 mismatch",
            "RECORD digest mismatch",
            "symbolic link member",
            "packaged license file is absent",
            "unexplained PE imports",
            "wheel is not compatible with CPython 3.12",
        ):
            self.assertIn(contract, source)


if __name__ == "__main__":
    unittest.main()
