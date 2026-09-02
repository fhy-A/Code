import multiprocessing
import os
import queue
import subprocess
import sys
import tempfile
import textwrap
import threading
import unittest
from pathlib import Path

from code_runtime import data_dir_owner


def _hold_data_dir_owner(data_dir, ready):
    """Spawn-safe worker that stays alive until its parent terminates it."""
    owner = data_dir_owner.acquire_data_dir_owner(data_dir)
    ready.put("ready")
    threading.Event().wait()
    _ = owner


class DataDirOwnerTests(unittest.TestCase):
    def _start_owner(self, data_dir):
        context = multiprocessing.get_context("spawn")
        ready = context.Queue()
        process = context.Process(
            target=_hold_data_dir_owner,
            args=(str(data_dir), ready),
        )
        process.start()
        try:
            self.assertEqual(ready.get(timeout=15), "ready")
        except queue.Empty as exc:
            self._stop_process(process)
            self.fail(f"owner process did not become ready: {exc}")
        return process, ready

    @staticmethod
    def _stop_process(process):
        if process.is_alive():
            getattr(process, "kill", process.terminate)()
        process.join(15)

    def test_sidecar_does_not_create_target_and_persists_after_release(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "data"

            first = data_dir_owner.acquire_data_dir_owner(data_dir)
            self.assertFalse(data_dir.exists())
            self.assertTrue(first.lock_path.is_file())
            with self.assertRaises(data_dir_owner.DataDirInUseError):
                data_dir_owner.acquire_data_dir_owner(data_dir)
            first.release()
            self.assertTrue(first.released)
            first.release()
            self.assertTrue(first.lock_path.is_file())
            self.assertIsNone(first._file_obj)

            replacement = data_dir_owner.acquire_data_dir_owner(data_dir)
            replacement.release()

    def test_live_other_process_is_refused_for_same_data_dir(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "data"
            process, ready = self._start_owner(data_dir)
            try:
                with self.assertRaises(data_dir_owner.DataDirInUseError):
                    data_dir_owner.acquire_data_dir_owner(data_dir)
            finally:
                self._stop_process(process)
                ready.close()

    def test_kernel_releases_owner_after_abrupt_process_exit(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "data"
            process, ready = self._start_owner(data_dir)
            try:
                with self.assertRaises(data_dir_owner.DataDirInUseError):
                    data_dir_owner.acquire_data_dir_owner(data_dir)
                self._stop_process(process)
                self.assertFalse(process.is_alive())
                replacement = data_dir_owner.acquire_data_dir_owner(data_dir)
                replacement.release()
            finally:
                self._stop_process(process)
                ready.close()

    def test_distinct_data_directories_can_be_owned_in_parallel(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            first_dir = Path(temp_dir) / "data-one"
            second_dir = Path(temp_dir) / "data-two"
            first_process, first_ready = self._start_owner(first_dir)
            second_process, second_ready = self._start_owner(second_dir)
            try:
                with self.assertRaises(data_dir_owner.DataDirInUseError):
                    data_dir_owner.acquire_data_dir_owner(first_dir)
                with self.assertRaises(data_dir_owner.DataDirInUseError):
                    data_dir_owner.acquire_data_dir_owner(second_dir)
            finally:
                self._stop_process(first_process)
                self._stop_process(second_process)
                first_ready.close()
                second_ready.close()

    def test_unsafe_sidecar_path_is_rejected_without_open_handle(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "data"
            lock_path = data_dir_owner.lock_path_for(data_dir)
            lock_path.mkdir()

            with self.assertRaises(data_dir_owner.DataDirOwnerUnavailableError):
                data_dir_owner.acquire_data_dir_owner(data_dir)

            self.assertNotIn(
                data_dir_owner._owner_key(data_dir.resolve()),
                data_dir_owner._OWNERS,
            )

    def test_server_import_defers_data_catalog_construction_until_entry_owns_dir(self):
        script = textwrap.dedent(
            """
            import code_runtime.image_runtime as image_runtime
            import code_runtime.model_route_registry as model_route_registry

            class ForbiddenRegistry:
                def __init__(self, *args, **kwargs):
                    raise AssertionError("catalog constructor ran during import")

            image_runtime.ImageRouteRegistry = ForbiddenRegistry
            model_route_registry.ModelRouteRegistry = ForbiddenRegistry
            import server
            """
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            environment = os.environ.copy()
            environment["CODE_DATA_DIR"] = str(Path(temp_dir) / "data")
            result = subprocess.run(
                [sys.executable, "-c", script],
                cwd=Path(__file__).resolve().parents[1],
                env=environment,
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )

        self.assertEqual(
            result.returncode,
            0,
            f"stdout={result.stdout}\nstderr={result.stderr}",
        )
