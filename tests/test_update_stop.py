"""Bounded updater fence tests; no installed application or upstream access."""
import threading
import time
import unittest
import subprocess
import sys
from unittest import mock

import server


class TestUpdateStopFence(unittest.TestCase):
    def setUp(self):
        self.patches = [mock.patch.dict(server._agent_runs, {}, clear=True),
                        mock.patch.dict(server._model_runtime_runs, {}, clear=True),
                        mock.patch.dict(server._dependency_operations, {}, clear=True),
                        mock.patch.object(server, "_command_processes", set()),
                        mock.patch.dict(server._update_pending_save_runs, {}, clear=True),
                        mock.patch.object(server, "_update_execution_requests", 0)]
        for patch in self.patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.assertIsNone(server._update_stop_owner)

    def test_window_blocks_all_worker_admission_and_task_http_then_releases(self):
        called = []

        @server._update_admission
        def admission():
            called.append(True)

        @server._update_execution_request
        def request(handler):
            called.append(True)

        with server._update_install_window():
            with self.assertRaises(server._UpdateFailure):
                admission()
            for path in ("/api/agent/runs", "/api/runtime/runs", "/api/tools/run_command", "/api/sessions/test", "/proxy/chat"):
                handler = mock.Mock(path=path)
                request(handler)
                self.assertEqual(handler.send_json.call_args.args[1], 409)
            self.assertEqual(called, [])
        admission()
        self.assertEqual(called, [True])

    def test_inflight_direct_request_is_drained_not_assumed_cancelled(self):
        entered, leave = threading.Event(), threading.Event()

        @server._update_execution_request
        def request(handler):
            entered.set()
            leave.wait(2)

        worker = threading.Thread(target=request, args=(mock.Mock(path="/api/tools/run_command"),))
        worker.start()
        self.assertTrue(entered.wait(1))
        timer = threading.Timer(.1, leave.set)
        timer.start()
        try:
            with server._update_install_window():
                worker.join(1)
                self.assertFalse(worker.is_alive())
                self.assertEqual(server._update_execution_requests, 0)
        finally:
            leave.set()
            worker.join(2)
            timer.join(2)

    def test_timeout_does_not_release_fence_while_late_save_is_running(self):
        entered, leave = threading.Event(), threading.Event()

        def blocked_save(deadline):
            entered.set()
            leave.wait(2)

        with mock.patch.object(server, "_stop_update_work", side_effect=blocked_save), \
             mock.patch.object(server, "_UPDATE_STOP_TIMEOUT_SECONDS", .05):
            try:
                with self.assertRaises(server._UpdateFailure):
                    with server._update_install_window():
                        self.fail("must not enter installation")
                self.assertTrue(entered.is_set())
                self.assertIsNotNone(server._update_stop_owner)
                with self.assertRaises(server._UpdateFailure):
                    with server._update_install_window():
                        self.fail("late writer must retain ownership")
            finally:
                leave.set()
                deadline = time.monotonic() + 2
                while server._update_stop_owner is not None and time.monotonic() < deadline:
                    time.sleep(.01)
        self.assertIsNone(server._update_stop_owner)

    def test_stop_or_save_failure_never_enters_installation(self):
        for failure in (OSError("save failed"), RuntimeError("cancel failed")):
            with self.subTest(failure=type(failure).__name__), \
                 mock.patch.object(server, "_stop_update_work", side_effect=failure):
                with self.assertRaises(server._UpdateFailure):
                    with server._update_install_window():
                        self.fail("must not install")
                self.assertIsNone(server._update_stop_owner)

    def test_stop_endpoint_emits_one_error_response_and_source_mode_refuses(self):
        handler = object.__new__(server.CodeHandler)
        handler.path = "/api/update-stop"
        handler.read_body_json = mock.Mock(return_value={})
        handler.send_json, handler.send_error = mock.Mock(), mock.Mock()
        with mock.patch.object(server.sys, "frozen", True, create=True), \
             mock.patch.object(server, "_stop_update_work", side_effect=OSError("save failed")):
            handler.do_POST()
        handler.send_json.assert_called_once()
        self.assertEqual(handler.send_json.call_args.args[1], 409)
        handler.send_error.assert_not_called()
        handler.send_json.reset_mock()
        with mock.patch.object(server.sys, "frozen", False, create=True), \
             mock.patch.object(server, "_stop_update_work") as stop:
            handler.do_POST()
            stop.assert_not_called()
        self.assertEqual(handler.send_json.call_args.args[1], 400)

    def test_active_dependency_operation_fails_closed(self):
        server._dependency_operations["fixture"] = {"status": "running"}
        with self.assertRaises(server._UpdateFailure):
            with server._update_install_window():
                self.fail("unsupported active work must block installation")
        self.assertIsNone(server._update_stop_owner)

    def test_terminal_process_with_live_output_reader_blocks_retries(self):
        leave = threading.Event()
        reader = threading.Thread(target=lambda: leave.wait(2))
        reader.start()
        process = mock.Mock()
        process.poll.return_value = 0
        process._code_output_readers = [reader]
        server._command_processes.add(process)
        try:
            for _ in range(2):
                with self.assertRaises(server._UpdateFailure):
                    with server._update_install_window():
                        self.fail("a terminal parent is not a drained command")
        finally:
            leave.set()
            reader.join(2)
        with server._update_install_window():
            self.assertEqual(server._command_processes, set())

    def test_failed_terminal_save_must_be_retried_before_installation(self):
        run = {"id": "pending-save", "status": "cancelled", "cancel_event": threading.Event()}
        server._update_pending_save_runs[run["id"]] = run
        with mock.patch.object(server, "_persist_agent_run", side_effect=OSError("save failed")):
            with self.assertRaises(server._UpdateFailure):
                with server._update_install_window():
                    self.fail("failed save must block")
        self.assertIn(run["id"], server._update_pending_save_runs)
        with mock.patch.object(server, "_persist_agent_run") as save:
            with server._update_install_window():
                save.assert_called_once_with(run)
                self.assertEqual(server._update_pending_save_runs, {})

    def test_real_exited_parent_with_child_holding_pipe_blocks_install(self):
        # The child inherits stdout but outlives its parent. A parent exit alone
        # cannot establish command completion, including on Windows brokers.
        child_code = "import time; time.sleep(2)"
        parent_code = f"import subprocess,sys; subprocess.Popen([sys.executable,'-c',{child_code!r}])"
        process = subprocess.Popen([sys.executable, "-c", parent_code], stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, **server._hidden_subprocess_kwargs())
        reader = threading.Thread(target=process.stdout.read)
        reader.start()
        process._code_output_readers = [reader]
        server._command_processes.add(process)
        try:
            process.wait(timeout=3)
            self.assertTrue(reader.is_alive())
            for _ in range(2):
                with self.assertRaises(server._UpdateFailure):
                    with server._update_install_window():
                        self.fail("child-owned pipe is still live")
        finally:
            process.wait(timeout=5)
            reader.join(5)
            process.stdout.close()
        self.assertFalse(reader.is_alive())
        with server._update_install_window():
            self.assertEqual(server._command_processes, set())
