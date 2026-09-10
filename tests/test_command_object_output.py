"""Real, hidden PowerShell children in disposable workspaces; no user commands."""
import ast
import json
import os
import re
import subprocess
import tempfile
import threading
from pathlib import Path
from unittest import mock

import pytest
import server as s
from tests.test_reasoning_capabilities import runtime
from tests.test_workspace_prompt import facts


pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell executor contract")
BASELINE = "5682d472a705c4f086d6d3f598fd8b07b7023910"


@pytest.fixture
def project(monkeypatch):
    # A short path avoids incidental PowerShell table-width clipping.
    with tempfile.TemporaryDirectory(prefix="c71-") as root:
        path = Path(root) / "中文 空格"
        path.mkdir()
        monkeypatch.setattr(s, "_effective_agent_project_root", lambda: path)
        yield path
    assert not Path(root).exists()


@pytest.fixture(scope="module")
def wrappers():
    def assignment(source):
        tree = ast.parse(source)
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "execute_run_command_tool")
        node = next(node for node in ast.walk(function) if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "powershell_script" for target in node.targets))
        return compile(ast.Module(body=[node], type_ignores=[]), "powershell-wrapper", "exec")
    old = assignment(subprocess.check_output(["git", "show", BASELINE + ":server.py"], text=True, encoding="utf-8"))
    new = assignment(Path(s.__file__).read_text(encoding="utf-8"))
    def render(command, original=False):
        scope = {"command": command}
        exec(old if original else new, scope)
        return scope["powershell_script"]
    return render


def raw(script, cwd):
    return subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                          cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=12,
                          **s._hidden_subprocess_kwargs())


def test_original_object_loss_and_utf8_bytes_are_reproduced(project, wrappers):
    original = raw(wrappers("Get-Location", original=True), project)
    explicit = raw(wrappers("(Get-Location).Path", original=True), project)
    current = raw(wrappers("Get-Location"), project)
    assert original.returncode == explicit.returncode == current.returncode == 0
    assert original.stdout.strip() == b""
    code_page = int(raw("[Console]::OutputEncoding.CodePage", project).stdout.strip())
    encoding = {65001: "utf-8", 1200: "utf-16-le", 1201: "utf-16-be"}.get(code_page, f"cp{code_page}")
    assert str(project).encode(encoding, errors="replace") in explicit.stdout
    assert str(project) in current.stdout.decode("utf-8", errors="strict")
    assert not current.stdout.startswith(b"\xef\xbb\xbf")
    assert current.stderr == b""


@pytest.mark.parametrize("command,code,stdout,stderr", [
    ("'first'; 'second'", 0, "first\r\nsecond", ""),
    ("Write-Output $false", 0, "False", ""),
    ("cmd /d /c echo native", 0, "native", ""),
    ("cmd /d /c exit 7", 7, "", ""),
    ("cmd /d /c exit 7; 'after'", 7, "after", ""),
    ("throw 'synthetic-stop'", 1, "", "synthetic-stop"),
    ("Write-Error 'synthetic-error'", 0, "", "synthetic-error"),
    ("Write-Error 'synthetic-error'; 'after'", 0, "after", "synthetic-error"),
    ("Write-Error 'synthetic-stop' -ErrorAction Stop", 1, "", "synthetic-stop"),
    ("exit 4", 4, "", ""),
])
def test_registered_tool_keeps_original_exit_and_error_semantics(project, wrappers, command, code, stdout, stderr):
    original = raw(wrappers(command, original=True), project)
    result = s.execute_registered_tool("run_command", {"command": command})
    assert original.returncode == result["exitCode"] == code
    assert result["ok"] is (code == 0)
    assert not result["cancelled"] and not result["timedOut"]
    assert bool(original.stderr) == bool(result["stderr"])
    assert stdout in result["stdout"] and stderr in result["stderr"]
    if code == 0:
        assert result["error"] is None  # stderr and False output never imply failure.


@pytest.mark.parametrize("command,expected", [
    ("Get-Location", None),
    ("[pscustomobject]@{Name='alpha';Count=2}", "alpha"),
    ("Write-Output '中文输出'; [Console]::Error.WriteLine('中文错误')", "中文输出"),
    ("cmd /d /c echo 中文原生", "中文原生"),
])
def test_registered_object_table_string_and_native_unicode(project, command, expected):
    result = s.execute_registered_tool("run_command", {"command": command})
    assert result["ok"] and result["exitCode"] == 0
    assert (expected or str(project)) in result["stdout"]
    assert "�" not in result["stdout"] + result["stderr"]
    if "中文错误" in command:
        assert "中文错误" in result["stderr"]


def test_encoding_is_child_local_and_stream_limits_are_unchanged(project):
    before = raw("[Console]::OutputEncoding.WebName", project).stdout
    chunks = {"stdout": [], "stderr": []}
    processes = []
    tracked = set(s._command_processes)
    command = "Write-Output (('中' * 25000) + 'TAIL'); [Console]::Error.WriteLine(('错' * 24000) + 'END')"
    result = s.execute_run_command_tool({"command": command},
        output_callback=lambda stream, text: chunks[stream].append(text),
        process_callback=lambda process: processes.append(process))
    assert result["ok"]
    assert "".join(chunks["stdout"]) == "中" * 25000 + "TAIL\r\n"
    assert "".join(chunks["stderr"]) == "错" * 24000 + "END\r\n"
    for stream in ["stdout", "stderr"]:
        assert len(result[stream]) == 20000 and result[stream + "Truncated"]
        assert result[stream] == "".join(chunks[stream])[-20000:]
    assert processes[0].poll() == 0 and processes[-1] is None
    assert not any(thread.is_alive() for thread in processes[0]._code_output_readers)
    assert s._command_processes == tracked
    assert raw("[Console]::OutputEncoding.WebName", project).stdout == before


class OwnedChildHandle:
    def __init__(self, pid):
        import ctypes
        from ctypes import wintypes
        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        self.api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.api.OpenProcess.restype = wintypes.HANDLE
        self.api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.api.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        self.api.CloseHandle.argtypes = [wintypes.HANDLE]
        self.handle = self.api.OpenProcess(0x100001, False, pid)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())

    def exited(self):
        return self.api.WaitForSingleObject(self.handle, 2000) == 0

    def close(self):
        # A handle identifies this owned child even if its numeric PID is reused.
        if self.api.WaitForSingleObject(self.handle, 0) != 0:
            self.api.TerminateProcess(self.handle, 1)
            self.api.WaitForSingleObject(self.handle, 3000)
        self.api.CloseHandle(self.handle)


@pytest.mark.parametrize("cancel", [False, True])
def test_timeout_cancel_keep_live_output_and_close_owned_descendant(project, cancel):
    script = project / "owned-tree.py"
    script.write_text("import subprocess,sys,time\nchild=subprocess.Popen([sys.executable,'-c','import time;time.sleep(20)'])\nprint('CHILD='+str(child.pid),flush=True)\nprint('READY',flush=True)\nprint('partial-error',file=sys.stderr,flush=True)\ntime.sleep(20)\n", encoding="utf-8")
    event = threading.Event()
    child_handles, processes, chunks = {}, [], {"stdout": "", "stderr": ""}
    streamed_while_running = []
    def observe(stream, text):
        chunks[stream] += text
        if stream == "stdout":
            for match in re.finditer(r"CHILD=(\d+)\r?\n", chunks[stream]):
                pid = int(match[1])
                if pid not in child_handles:
                    child_handles[pid] = OwnedChildHandle(pid)
            if "READY" in chunks[stream]:
                streamed_while_running.append(processes[0].poll() is None)
                if cancel:
                    event.set()
    try:
        result = s.execute_run_command_tool({"command": "python owned-tree.py", "timeout": 3},
            cancel_event=event, output_callback=observe, process_callback=lambda process: processes.append(process))
        assert not result["ok"]
        assert result["cancelled"] is cancel and result["timedOut"] is (not cancel)
        assert "READY" in result["stdout"] and "CHILD=" in result["stdout"]
        if not cancel:
            assert "partial-error" in result["stderr"]
        assert streamed_while_running and all(streamed_while_running)
        assert len(child_handles) == 1 and all(handle.exited() for handle in child_handles.values())
        assert processes[0].poll() is not None and processes[-1] is None
        assert not any(thread.is_alive() for thread in processes[0]._code_output_readers)
        assert processes[0] not in s._command_processes
    finally:
        for handle in child_handles.values():
            handle.close()


def test_isolated_http_returns_actual_get_location_stdout(project):
    import requests
    host = s.ThreadingHTTPServer(("127.0.0.1", 0), s.CodeHandler)
    worker = threading.Thread(target=host.serve_forever, daemon=True)
    worker.start()
    try:
        response = requests.post(f"http://127.0.0.1:{host.server_port}/api/tools/run_command", json={"command": "Get-Location"}, timeout=12)
        result = response.json()
        assert response.status_code == 200 and result["ok"] and result["exitCode"] == 0
        assert str(project) in result["stdout"] and "�" not in result["stdout"]
    finally:
        host.shutdown()
        host.server_close()
        worker.join(timeout=2)
        assert not worker.is_alive()


def test_actual_agent_hint_command_stdout_and_returned_cwd_agree(runtime):
    fixture, harness = runtime
    with tempfile.TemporaryDirectory(prefix="c71-") as root:
        project = Path(root) / "中文 空格"
        project.mkdir()
        fixture.config_path.write_text(json.dumps({"projectRoot": str(project)}), encoding="utf-8")
        with harness._AgentUpstream.scripted_lock:
            harness._AgentUpstream.scripted_rounds = [
                [{"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "location-command", "type": "function", "function": {"name": "run_command", "arguments": '{"command":"Get-Location"}'}}]}, "finish_reason": "tool_calls"}]}],
                [{"choices": [{"delta": {"content": "directory verified from stdout"}, "finish_reason": "stop"}]}],
            ]
        run = s._create_agent_run("location-acceptance", {"model": "test-model", "messages": [{"role": "user", "content": "verify cwd with Get-Location"}]}, fixture.base_url, ["fixture-location-key"], allowed_tools=["run_command"], permission_profile="bypass")
        fixture._wait_terminal(run)
        fixture._wait_worker_idle(run)
        assert run["status"] == "completed" and harness._AgentUpstream.calls == 2
        assert len(run["tool_executions"]) == 1
        result = run["tool_executions"]["location-command"]["result"]
        assert result["ok"] and result["exitCode"] == 0
        for payload in harness._AgentUpstream.payloads:
            declared = facts(payload)["cwd"]
            assert declared == run["cwd"] == result["cwd"] == str(project)
            assert declared in result["stdout"]
        receipt = next(message for message in harness._AgentUpstream.payloads[1]["messages"] if message.get("role") == "tool")
        assert str(project) in json.loads(receipt["content"])["stdout"]
        assert not run.get("active_process")
    assert not Path(root).exists()
