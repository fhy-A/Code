"""
P1 Concurrency Safety Tests — multi-thread writes, session atomicity, dispatcher limits.

Run: python -m pytest tests/test_concurrency.py -v
"""
import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server as server_mod


# ═══════════════════════════════════════════════════════════════════
# 1. write_json atomicity — heavy concurrency
# ═══════════════════════════════════════════════════════════════════

class TestWriteJsonAtomicity(unittest.TestCase):

    def test_20_threads_heavy_concurrency(self):
        """20 threads writing 50 messages each → file intact, no corruption."""
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "session.json"
            errors = []
            seen = set()

            def writer(index):
                try:
                    # Each thread writes a unique marker in the message list
                    msgs = [{"thread": index, "seq": i, "marker": f"t{index}-m{i}"} for i in range(50)]
                    server_mod.write_json(target, {
                        "id": "concurrent-test",
                        "writer": index,
                        "messages": msgs,
                    })
                    seen.add(index)
                except Exception as exc:
                    errors.append(str(exc))

            threads = [threading.Thread(target=writer, args=(i,)) for i in range(20)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            self.assertEqual(len(errors), 0, f"Errors during write: {errors}")
            self.assertTrue(target.exists())
            data = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(data["id"], "concurrent-test")
            self.assertEqual(len(data["messages"]), 50)
            self.assertGreaterEqual(len(seen), 18,
                                    f"At least 18 of 20 threads should succeed, only {len(seen)} did")

    def test_same_file_different_keys(self):
        """Concurrent writes to different keys in same JSON don't corrupt."""
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "multi.json"
            server_mod.write_json(target, {})

            def write_key(key, value):
                for _ in range(30):
                    try:
                        current = server_mod.read_json(target, {})
                        current[key] = value
                        server_mod.write_json(target, current)
                    except Exception:
                        pass

            threads = [
                threading.Thread(target=write_key, args=(f"k{i}", f"v{i}"))
                for i in range(8)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            data = server_mod.read_json(target, {})
            self.assertIsInstance(data, dict)
            # At least some keys should have survived
            self.assertGreater(len(data), 0)

    def test_permission_error_during_replace_is_retried(self):
        """A short Windows file lock should not fail an otherwise valid save."""
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "retry.json"
            original_replace = server_mod.os.replace
            attempts = []

            def flaky_replace(source, destination):
                attempts.append((source, destination))
                if len(attempts) < 3:
                    raise PermissionError("temporarily locked")
                return original_replace(source, destination)

            with mock.patch.object(server_mod.os, "replace", side_effect=flaky_replace), \
                    mock.patch.object(server_mod.time, "sleep") as sleep:
                server_mod.write_json(target, {"ok": True})

            self.assertEqual(server_mod.read_json(target, {}), {"ok": True})
            self.assertEqual(len(attempts), 3)
            self.assertEqual(sleep.call_count, 2)


# ═══════════════════════════════════════════════════════════════════
# 2. Concurrent file operations via route server
# ═══════════════════════════════════════════════════════════════════

class TestConcurrentFileOps(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp_root = Path(tempfile.mkdtemp(prefix="code_conc_root_"))
        cls.tmp_data = Path(tempfile.mkdtemp(prefix="code_conc_data_"))

        cls.tmp_data_subdirs = ["sessions", "memory", "skills", "attachments", "file-backups"]
        for sub in cls.tmp_data_subdirs:
            (cls.tmp_data / sub).mkdir(parents=True, exist_ok=True)

        # Create test files
        for i in range(10):
            (cls.tmp_root / f"file_{i}.txt").write_text(f"content-{i}\n", encoding="utf-8")

        config = {
            "projectRoot": str(cls.tmp_root),
            "newApiBaseUrl": "http://localhost:3000",
            "userHome": str(Path.home()),
        }
        (cls.tmp_data / "config.json").write_text(json.dumps(config), encoding="utf-8")

        # Patch server globals
        cls._patchers = [
            mock.patch.object(server_mod, "DATA_DIR", cls.tmp_data),
            mock.patch.object(server_mod, "CONFIG_PATH", cls.tmp_data / "config.json"),
            mock.patch.object(server_mod, "SESSIONS_DIR", cls.tmp_data / "sessions"),
            mock.patch.object(server_mod, "MEMORY_DIR", cls.tmp_data / "memory"),
            mock.patch.object(server_mod, "SKILLS_DIR", cls.tmp_data / "skills"),
            mock.patch.object(server_mod, "ATTACHMENTS_DIR", cls.tmp_data / "attachments"),
            mock.patch.object(server_mod, "FILE_BACKUP_DIR", cls.tmp_data / "file-backups"),
            mock.patch.object(server_mod, "APP_DIR", cls.tmp_root),
        ]
        for p in cls._patchers:
            p.start()

    @classmethod
    def tearDownClass(cls):
        for p in cls._patchers:
            p.stop()

    def _make_handler(self):
        h = object.__new__(server_mod.CodeHandler)
        h.send_json = mock.Mock()
        h.read_body_json = mock.Mock()
        return h

    def test_concurrent_reads_no_corruption(self):
        """10 threads reading different files simultaneously → all succeed."""
        errors = []

        def reader(i):
            try:
                h = self._make_handler()
                h.read_body_json.return_value = {"path": f"file_{i}.txt"}
                server_mod.CodeHandler.tool_read_file(h)
                data = h.send_json.call_args[0][0]
                if not data.get("ok"):
                    errors.append(f"Reader {i} failed: {data}")
            except Exception as e:
                errors.append(f"Reader {i} crashed: {e}")

        threads = [threading.Thread(target=reader, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Concurrent reads failed: {errors}")

    def test_concurrent_writes_no_corruption(self):
        """8 threads writing different files simultaneously → all succeed, files intact."""
        errors = []

        def writer(i):
            try:
                h = self._make_handler()
                h.read_body_json.return_value = {"path": f"written_{i}.txt", "content": f"thread-{i}"}
                server_mod.CodeHandler.tool_write_file(h)
                data = h.send_json.call_args[0][0]
                if not data.get("ok"):
                    errors.append(f"Writer {i} failed: {data}")
            except Exception as e:
                errors.append(f"Writer {i} crashed: {e}")

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Concurrent writes failed: {errors}")
        # Verify all files written correctly
        for i in range(8):
            path = self.tmp_root / f"written_{i}.txt"
            self.assertTrue(path.exists(), f"File {i} was not created")
            content = path.read_text(encoding="utf-8")
            self.assertEqual(content, f"thread-{i}")

    def test_concurrent_read_write_mix(self):
        """Mixed reads and writes → no deadlock, no corruption."""
        errors = []

        def mixed_worker(i):
            try:
                if i % 2 == 0:
                    h = self._make_handler()
                    h.read_body_json.return_value = {"path": f"file_{i % 5}.txt"}
                    server_mod.CodeHandler.tool_read_file(h)
                else:
                    h = self._make_handler()
                    h.read_body_json.return_value = {"path": f"mixed_{i}.txt", "content": f"mixed-{i}"}
                    server_mod.CodeHandler.tool_write_file(h)
            except Exception as e:
                errors.append(f"Worker {i} crashed: {e}")

        threads = [threading.Thread(target=mixed_worker, args=(i,)) for i in range(12)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Mixed operations failed: {errors}")

    def test_concurrent_mkdir_no_collision(self):
        """Concurrent mkdir to same parent → only one succeeds, no crash."""
        errors = []

        def mkdir_worker(i):
            try:
                h = self._make_handler()
                h.read_body_json.return_value = {"name": f"shared_dir_{i % 3}", "parent": ""}
                server_mod.CodeHandler.create_directory(h)
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=mkdir_worker, args=(i,)) for i in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Some will collide with "already exists", that's fine — no fatal errors
        self.assertLessEqual(len(errors), 4, f"Too many crashes: {errors}")


# ═══════════════════════════════════════════════════════════════════
# 3. Session concurrent save — data integrity
# ═══════════════════════════════════════════════════════════════════

class TestConcurrentSessionSaves(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp_root = Path(tempfile.mkdtemp(prefix="code_sess_"))
        cls.tmp_data = Path(tempfile.mkdtemp(prefix="code_sessd_"))
        (cls.tmp_data / "sessions").mkdir(parents=True)
        (cls.tmp_data / "file-backups").mkdir(parents=True)
        config = {
            "projectRoot": str(cls.tmp_root),
            "newApiBaseUrl": "http://localhost:3000",
            "userHome": str(Path.home()),
        }
        (cls.tmp_data / "config.json").write_text(json.dumps(config), encoding="utf-8")

        cls._patchers = [
            mock.patch.object(server_mod, "DATA_DIR", cls.tmp_data),
            mock.patch.object(server_mod, "CONFIG_PATH", cls.tmp_data / "config.json"),
            mock.patch.object(server_mod, "SESSIONS_DIR", cls.tmp_data / "sessions"),
            mock.patch.object(server_mod, "FILE_BACKUP_DIR", cls.tmp_data / "file-backups"),
            mock.patch.object(server_mod, "APP_DIR", cls.tmp_root),
        ]
        for p in cls._patchers:
            p.start()

    @classmethod
    def tearDownClass(cls):
        for p in cls._patchers:
            p.stop()

    def _make_handler(self):
        h = object.__new__(server_mod.CodeHandler)
        h.send_json = mock.Mock()
        h.read_body_json = mock.Mock()
        return h

    def test_create_many_sessions_concurrently(self):
        """Create 20 sessions at once → all get unique IDs, no crash."""
        session_ids = []
        lock = threading.Lock()

        def creator():
            h = self._make_handler()
            h.read_body_json.return_value = {
                "title": "concurrent session",
                "messages": [{"role": "user", "content": "test"}],
            }
            server_mod.CodeHandler.create_session(h)
            data = h.send_json.call_args[0][0]
            with lock:
                session_ids.append(data.get("id"))

        threads = [threading.Thread(target=creator) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All got unique IDs
        valid_ids = [s for s in session_ids if s]
        self.assertEqual(len(valid_ids), 20, f"Only {len(valid_ids)}/20 sessions created")
        self.assertEqual(len(set(valid_ids)), 20, "Session IDs must be unique")

    def test_save_same_session_concurrently(self):
        """Save the same session from multiple threads → final state is consistent."""
        h = self._make_handler()
        h.read_body_json.return_value = {
            "title": "single session",
            "messages": [{"role": "user", "content": "initial"}],
        }
        server_mod.CodeHandler.create_session(h)
        sid = h.send_json.call_args[0][0]["id"]
        written_counts = []
        errors = []
        lock = threading.Lock()

        def saver(msg_count):
            try:
                h2 = self._make_handler()
                h2.send_json = mock.Mock()
                h2.path = f"/api/sessions/{sid}"
                h2.read_body_json.return_value = {
                    "title": "saved by thread",
                    "messages": [
                        {"role": "user", "content": f"msg-{msg_count}-{i}"}
                        for i in range(msg_count)
                    ],
                }
                # Retry once on Windows where file locks can race between threads
                for attempt in range(2):
                    try:
                        server_mod.CodeHandler.save_session(h2, sid)
                        break
                    except OSError:
                        if attempt == 0:
                            time.sleep(0.15)
                        else:
                            raise
                with lock:
                    written_counts.append(msg_count)
            except Exception as exc:
                with lock:
                    errors.append(f"save {msg_count}: {exc}")

        thread_counts = [5, 8, 3, 10, 7, 12, 4, 6, 9, 2]
        threads = [threading.Thread(target=saver, args=(c,)) for c in thread_counts]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"Concurrent session saves failed: {errors}")
        self.assertEqual(len(written_counts), len(thread_counts))

        # The last save wins — but crucially, no corruption
        session_file = server_mod.session_path(sid)
        jsonl_file = server_mod.messages_path(sid)
        self.assertTrue(session_file.exists())
        self.assertTrue(jsonl_file.exists())
        # Messages are now in JSONL, not in the JSON metadata
        loaded_meta = json.loads(session_file.read_text(encoding="utf-8"))
        self.assertNotIn("messages", loaded_meta, "messages should be in JSONL, not meta JSON")
        messages = server_mod.read_jsonl(jsonl_file)
        self.assertIsInstance(messages, list)
        # Total messages should be one of the thread counts (the winner)
        msg_len = len(messages)
        self.assertIn(msg_len, thread_counts,
                      f"Message count {msg_len} should be one of {thread_counts}")


# ═══════════════════════════════════════════════════════════════════
# 4. Background dispatcher limits — source assertions on app.js
# ═══════════════════════════════════════════════════════════════════

class TestDispatcherLimits(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parent.parent
        cls.source = (root / "app.js").read_text(encoding="utf-8")
        cls.state_source = (root / "src" / "core" / "state.js").read_text(encoding="utf-8")
        cls.persistence_source = (root / "src" / "services" / "persistence.js").read_text(encoding="utf-8")
        cls.sessions_source = (root / "src" / "features" / "sessions.js").read_text(encoding="utf-8")

    def test_global_limit_enforced(self):
        self.assertIn('globalLimit: 3', self.state_source,
                      "Global background dispatch limit must be 3")
        self.assertIn('perSessionLimit: 2', self.state_source,
                      "Per-session dispatch limit must be 2")

    def test_bounded_dispatcher_loop(self):
        self.assertNotIn('async function mapWithConcurrency', self.source)
        self.assertIn('while (dispatcher.activeCount < dispatcher.globalLimit)', self.source)
        self.assertIn('dispatcher.activeCount', self.source,
                      "Must track active dispatch count")
        self.assertIn('dispatcher.globalLimit', self.source,
                      "Must check against global limit")
        self.assertIn('activeCount < dispatcher.globalLimit', self.source,
                      "Must enforce dispatch limit via activeCount check")

    def test_background_dispatch_queue_management(self):
        self.assertIn('function pumpBackgroundDispatcher()', self.source)
        self.assertIn('backgroundActiveForSession(candidate.sessionId)', self.source)
        self.assertIn('< dispatcher.perSessionLimit', self.source,
                      "Must enforce per-session limit")

    def test_session_save_chaining_prevents_races(self):
        self.assertIn('_sessionSaveChains: {}', self.state_source)
        self.assertIn('const previous = saveChains[sessionId] || Promise.resolve();', self.persistence_source)
        self.assertIn('saveChains[sessionId] = savePromise;', self.persistence_source)

    def test_detached_messages_not_leaked_to_model(self):
        self.assertIn('function isDetachedFromMainContext(msg)', self.source)
        self.assertIn('msg.meta?.detachedFromMain', self.source)
        self.assertIn('function getModelContextMessages(messages)', self.source)
        self.assertIn('.filter((msg) => !isDetachedFromMainContext(msg))', self.source)
        self.assertIn('getModelContextMessages(streamMessages)', self.source)

    def test_parallel_usage_ledger_isolation(self):
        self.assertIn('if (!ctx?.isSubAgent) setSessionStats(sessionId, stats);', self.source)
        self.assertIn('mergeBackgroundUsage(job.sessionId, sub.usage);', self.source)
        # Must NOT merge directly into parent context
        self.assertNotIn('mergeBackgroundUsage(sessionId, subCtx.stats);', self.source)

    def test_legacy_browser_usage_merger_is_removed(self):
        self.assertNotIn('function mergeDelegatedUsage(', self.source)
        self.assertNotIn('mergeDelegatedUsage(parentCtx, subCtx.taskUsage)', self.source)
        self.assertIn('mergeBackgroundUsage(job.sessionId, sub.usage);', self.source)

    def test_background_job_lifecycle(self):
        self.assertIn('backgroundDispatch: { id, status: "pending", agentRunId: "", parentTaskStartedAt }', self.source)
        self.assertIn('updateBackgroundJob(job, "running")', self.source)
        self.assertIn('const BACKGROUND_JOB_TIMEOUT_MS = 10 * 60 * 1000;', self.source)

    def test_abort_controller_per_job(self):
        self.assertIn('abortController: new AbortController()', self.source)

    def test_new_session_keeps_background_session_running(self):
        start = self.source.index('els.newChat.addEventListener("click"')
        end = self.source.index('els.exportChat.addEventListener', start)
        handler = self.source[start:end]
        navigation_start = self.sessions_source.index("function createSessionNavigation(")
        helper_start = self.sessions_source.index("function beginNewConversation(", navigation_start)
        helper_end = self.sessions_source.index("async function createSession(", helper_start)
        new_session_flow = handler + self.sessions_source[helper_start:helper_end]
        self.assertIn('view.cacheActiveSessionState();', new_session_flow)
        self.assertIn('invalidateForegroundSessionNavigation();', new_session_flow)
        self.assertIn('rememberWelcomeForeground();', new_session_flow)
        self.assertIn('view.syncActiveStreamingState();', new_session_flow)
        self.assertIn("beginNewConversation(projectIdForNewConversation());", handler)
        self.assertNotIn('state.isStreaming) { showToast', new_session_flow)
        self.assertNotIn('run.abortController.abort()', new_session_flow)
        self.assertNotIn('run.messageQueue = []', new_session_flow)

    def test_welcome_refresh_only_changes_foreground_navigation(self):
        navigation_start = self.sessions_source.index("function createSessionNavigation(")
        load_start = self.sessions_source.index('async function loadSession(sessionId)', navigation_start)
        load_end = self.sessions_source.index('return Object.freeze({', load_start)
        load_block = self.sessions_source[load_start:load_end]
        self.assertIn('foregroundNavigationSeq !== state._foregroundNavigationSeq', load_block)
        self.assertIn('rememberSessionForeground(session.id);', load_block)
        self.assertNotIn('abortController.abort()', load_block)
        self.assertNotIn('setStreaming(false', load_block)
        self.assertNotIn('run.messageQueue = []', load_block)

        startup_start = self.sessions_source.index("function createSessionStartup(")
        foreground_start = self.sessions_source.index("async function restoreForegroundSession()", startup_start)
        recovery_coordination_start = self.sessions_source.index("function startRecovery()", foreground_start)
        foreground_block = self.sessions_source[foreground_start:recovery_coordination_start]
        recovery_coordination = self.sessions_source[recovery_coordination_start:]
        self.assertIn('storage.getItem("code-foreground-view")', foreground_block)
        self.assertIn('foregroundView !== "welcome"', foreground_block)
        self.assertIn("await navigation.loadSession(lastId);", foreground_block)
        self.assertNotIn("navigation.loadSession(", recovery_coordination)

        init_start = self.source.index('async function init()')
        init_block = self.source[init_start:]
        self.assertIn("await sessionStartup.restoreForegroundSession();", init_block)
        self.assertNotIn('localStorage.getItem("code-foreground-view")', init_block)

        resume_start = self.source.index('async function resumePersistedRuns()')
        resume_end = self.source.index('function createModelRequestError', resume_start)
        resume_block = self.source[resume_start:resume_end]
        self.assertIn('resumePersistedSessionRun(session)', resume_block)
        self.assertNotIn('loadSession(', resume_block)
        self.assertNotIn('code-foreground-view', resume_block)
        self.assertNotIn('abortController.abort()', resume_block)


if __name__ == "__main__":
    unittest.main()
