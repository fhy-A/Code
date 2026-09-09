"""Bounded text reads, using only synthetic streams and temporary files."""
import io
import os
import tracemalloc
from pathlib import Path
from unittest import mock

import pytest
import server as server_mod


class CountedStream(io.BytesIO):
    def __init__(self, data, maximum=None):
        super().__init__(data)
        self.maximum = maximum
        self.total = 0

    def read(self, size=-1):
        assert 0 < size <= server_mod._TEXT_READ_CHUNK_BYTES
        data = super().read(min(size, self.maximum) if self.maximum else size)
        self.total += len(data)
        return data


def window(data, start=None, end=None, maximum=None):
    stream = CountedStream(data, maximum)
    result = server_mod._read_text_window(stream, len(data), start_line=start, end_line=end)
    assert stream.total <= len(data)
    return result


@pytest.mark.parametrize("maximum", [1, 2, 3, 7, 65536])
@pytest.mark.parametrize("text", [
    "a\r\n\nb\rc\nd", "\n\n",
    "α🙂\r\n中\v尾\f末\x1c分\x1d隔\x1e行\x85再\u2028二\u2029三",
    "\ufeffBOM\r\ntext", "last line",
])
def test_range_matches_splitlines_across_chunks(text, maximum):
    lines = text.splitlines()
    for start, end in [(1, 1), (1, None), (None, 2), (len(lines), len(lines) + 2)]:
        first = start or 1
        expected = "\n".join(lines[first - 1:end])
        assert window(text.encode(), start, end, maximum) == (
            expected, False, {"start": first, "end": min(end or len(lines), len(lines))},
        )


def test_late_range_skips_more_than_preview_without_truncation():
    data = ("x" * (server_mod.MAX_TOOL_READ_BYTES + 100) + "\n目标行\n结束\n").encode()
    assert window(data, 2, 3) == ("目标行\n结束", False, {"start": 2, "end": 3})


def test_default_preserves_newlines_and_complete_utf8(monkeypatch):
    monkeypatch.setattr(server_mod, "MAX_TOOL_READ_BYTES", 8)
    assert window("ab\r\n🙂Z".encode(), maximum=1) == ("ab\r\n🙂", True, None)
    assert window("ab\r\n🙂".encode(), maximum=1) == ("ab\r\n🙂", False, None)
    monkeypatch.setattr(server_mod, "MAX_TOOL_READ_BYTES", 7)
    assert window("ab\r\n🙂Z".encode()) == ("ab\r\n", True, None)


def test_empty_eof_reverse_and_existing_normalization():
    for start, end in [(None, None), (1, 1), (None, 8)]:
        assert window(b"", start, end) == ("", False, None)
    with pytest.raises(ValueError, match="文件为空"):
        window(b"", 2, None)
    with pytest.raises(ValueError, match="实际末行是 2"):
        window(b"a\nb\n", 3, 9)
    for data in [b"", b"a\nb"]:
        with pytest.raises(ValueError, match="不能小于"):
            window(data, 2, 1)
    assert window(b"a\nb", 0, 0) == ("a\nb", False, {"start": 1, "end": 2})
    assert window(b"a\nb", -4, 1) == ("a", False, {"start": 1, "end": 1})


def test_invalid_utf8_replacement_is_distinct_from_split_valid_codepoints():
    assert window(b"A\xff\n\xe4\xb8\xad\n\xf0\x9f", 1, 9, 1) == (
        "A�\n中\n�", False, {"start": 1, "end": 3},
    )


def test_classifier_prefix_reused_across_utf8_and_crlf_boundaries():
    data = "甲🙂\r\n\n乙\u2028末".encode()
    for prefix_size in range(len(data) + 1):
        stream = CountedStream(data[prefix_size:], maximum=1)
        assert server_mod._read_text_window(
            stream, len(data), data[:prefix_size], start_line=2, end_line=4,
        ) == ("\n乙\n末", False, {"start": 2, "end": 4})
        assert stream.total + prefix_size == len(data)


def test_long_selected_line_exact_limit_and_partial_last_line(monkeypatch):
    limit = server_mod.MAX_TOOL_READ_BYTES
    assert window(b"x" * (limit + 200) + b"\nlast", 1, 1) == (
        "x" * limit, True, {"start": 1, "end": 1},
    )
    for data, end in [(b"x" * limit + b"\nlast", 1), (b"x" * limit + b"\n", None)]:
        assert window(data, 1, end) == ("x" * limit, False, {"start": 1, "end": 1})
    monkeypatch.setattr(server_mod, "MAX_TOOL_READ_BYTES", 6)
    assert window("abc\n🙂".encode(), 1, 2) == ("abc", True, {"start": 1, "end": 1})
    assert window(b"abc\ndefgh", 1, 2) == ("abc\nde", True, {"start": 1, "end": 2})
    assert window(b"abc\n\n", 1, 2) == ("abc\n", False, {"start": 1, "end": 2})


class VirtualLongLine:
    def __init__(self, length, growth=False):
        self.length, self.growth = length, growth
        self.position = self.maximum_read = 0

    def read(self, size):
        assert 0 < size <= server_mod._TEXT_READ_CHUNK_BYTES
        self.maximum_read = max(self.maximum_read, size)
        if self.position < self.length:
            data = b"x" * min(size, self.length - self.position)
        else:
            offset = self.position - self.length
            data = b"\nTAIL"[offset:offset + size]
            if not data and self.growth:
                data = b"g" * size
        self.position += len(data)
        return data


def test_memory_does_not_grow_with_file_or_skipped_line_length():
    peaks = []
    for length in [1024 * 1024, 32 * 1024 * 1024]:
        stream = VirtualLongLine(length)
        tracemalloc.start()
        try:
            assert server_mod._read_text_window(stream, length + 5, start_line=2, end_line=2) == (
                "TAIL", False, {"start": 2, "end": 2},
            )
            peaks.append(tracemalloc.get_traced_memory()[1])
        finally:
            tracemalloc.stop()
        assert stream.position == length + 5
        assert stream.maximum_read <= 65536
    assert max(peaks) < 4 * 1024 * 1024
    assert peaks[1] < peaks[0] + 512 * 1024
    print("bounded-memory peaks:", peaks)


def test_scanner_never_follows_growth_beyond_initial_size():
    stream = VirtualLongLine(100000, growth=True)
    assert server_mod._read_text_window(stream, 100005, start_line=2) == (
        "TAIL", False, {"start": 2, "end": 2},
    )
    assert stream.position == 100005


def test_memory_does_not_grow_with_start_line():
    class ManyLines:
        def __init__(self, count):
            self.remaining = count * 2

        def read(self, size):
            assert 0 < size <= 65536
            count = min(size, self.remaining)
            self.remaining -= count
            return (b"x\n" * ((count + 1) // 2))[:count]

    peaks = []
    for count in [100000, 2000000]:
        stream = ManyLines(count)
        tracemalloc.start()
        try:
            assert server_mod._read_text_window(stream, count * 2, start_line=count) == (
                "x", False, {"start": count, "end": count},
            )
            peaks.append(tracemalloc.get_traced_memory()[1])
        finally:
            tracemalloc.stop()
    assert max(peaks) < 4 * 1024 * 1024
    assert peaks[1] < peaks[0] + 512 * 1024
    print("late-start memory peaks:", peaks)


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setattr(server_mod, "_effective_agent_project_root", lambda: tmp_path)
    attachments = tmp_path / "attachments"
    attachments.mkdir()
    monkeypatch.setattr(server_mod, "ATTACHMENTS_DIR", attachments)
    return tmp_path


def test_real_file_late_window_never_uses_read_bytes(project):
    target = project / "later.txt"
    target.write_bytes(b"x" * (server_mod.MAX_TOOL_READ_BYTES + 100) + "\n后段\n结束".encode())
    with mock.patch.object(Path, "read_bytes", side_effect=AssertionError("unbounded text read")):
        result = server_mod.execute_read_file_tool({"path": str(target), "startLine": 2, "endLine": 9})
    assert result["content"] == "后段\n结束"
    assert result["size"] == target.stat().st_size
    assert result["lineRange"] == {"start": 2, "end": 3}
    assert result["truncated"] is False


def test_attachment_default_and_original_binary_image_branches(project):
    (project / "attachments" / "sample.txt").write_bytes(b"one\r\ntwo")
    result = server_mod.execute_read_file_tool({"path": "attachments/sample.txt"})
    assert result["content"] == "one\r\ntwo"
    assert result["path"] == "attachments/sample.txt"
    (project / "binary.bin").write_bytes(b"\0binary")
    result = server_mod.execute_read_file_tool({"path": str(project / "binary.bin"), "startLine": 100})
    assert result["binary"] and not result["visual"] and result["size"] == 7
    svg = '<svg xmlns="http://www.w3.org/2000/svg"/>'
    (project / "picture.svg").write_text(svg, encoding="utf-8")
    result = server_mod.execute_read_file_tool({"path": str(project / "picture.svg"), "startLine": 100})
    assert result["visual"] and result["svgText"] == svg and result["mime"] == "image/svg+xml"


def test_http_late_empty_eof_and_bounded_default(project):
    import threading
    import requests
    target = project / "http-late.txt"
    source = ("首段\r\n" * 100000 + "后段\n尾部").encode()
    target.write_bytes(source)
    empty = project / "empty.txt"
    empty.write_bytes(b"")
    httpd = server_mod.ThreadingHTTPServer(("127.0.0.1", 0), server_mod.CodeHandler)
    worker = threading.Thread(target=httpd.serve_forever, daemon=True)
    worker.start()
    try:
        url = f"http://127.0.0.1:{httpd.server_port}/api/tools/read_file"
        cases = [
            ({"path": str(target), "startLine": 100001, "endLine": 999999}, 200),
            ({"path": str(target)}, 200),
            ({"path": str(empty), "startLine": 1, "endLine": 1}, 200),
            ({"path": str(target), "startLine": 100003}, 400),
            ({"path": str(empty), "startLine": 2}, 400),
            ({"path": str(target), "startLine": 2, "endLine": 1}, 400),
        ]
        results = []
        for body, status in cases:
            response = requests.post(url, json=body, timeout=10)
            assert response.status_code == status, response.text
            results.append(response.json())
        assert results[0]["content"] == "后段\n尾部"
        assert results[0]["lineRange"] == {"start": 100001, "end": 100002}
        assert results[0]["truncated"] is False
        assert len(results[1]["content"].encode()) <= server_mod.MAX_TOOL_READ_BYTES
        assert "\r\n" in results[1]["content"] and results[1]["truncated"]
        assert results[2]["content"] == "" and results[2]["lineRange"] is None
        assert results[2]["truncated"] is False
        assert "100002" in results[3]["error"]
        assert "文件为空" in results[4]["error"]
        assert "不能小于" in results[5]["error"]
        assert target.read_bytes() == source
    finally:
        httpd.shutdown()
        httpd.server_close()
        worker.join(timeout=2)
        assert not worker.is_alive()


@pytest.mark.parametrize("change", ["grow", "shrink", "replace", "grow_during_eof"])
def test_observed_file_change_discards_result(project, monkeypatch, change):
    target = project / "changing.txt"
    target.write_bytes(b"a\n" * 40000)
    replacement = project / "replacement.txt"
    replacement.write_bytes(b"b\n" * 40000)
    original_open = Path.open
    original_stat = Path.stat
    identity_changed = False

    class ChangingReader:
        def __init__(self, raw):
            self.raw, self.changed = raw, False

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.raw.close()

        def fileno(self):
            return self.raw.fileno()

        def read(self, size):
            nonlocal identity_changed
            assert 0 < size <= 65536
            data = self.raw.read(size)
            if not self.changed:
                self.changed = True
                if change.startswith("grow"):
                    with original_open(target, "ab") as writer:
                        writer.write(b"new\n")
                elif change == "shrink":
                    with original_open(target, "wb") as writer:
                        writer.write(b"changed")
                elif os.name == "nt":
                    # This environment rejected two actual replacements with
                    # WinError 5. Inject only the path identity after real reads;
                    # keep size and mtime identical to test the identity check.
                    identity_changed = True
                else:
                    os.replace(replacement, target)
            return data

    def opening(path, mode="r", *args, **kwargs):
        raw = original_open(path, mode, *args, **kwargs)
        return ChangingReader(raw) if path == target and mode == "rb" else raw

    def stat(path, *args, **kwargs):
        observed = original_stat(path, *args, **kwargs)
        if path == target and identity_changed:
            from types import SimpleNamespace
            return SimpleNamespace(st_dev=observed.st_dev, st_ino=observed.st_ino + 1,
                                   st_size=observed.st_size, st_mtime_ns=observed.st_mtime_ns)
        return observed

    monkeypatch.setattr(Path, "open", opening)
    monkeypatch.setattr(Path, "stat", stat)
    with pytest.raises(ValueError, match="文件读取期间发生变化"):
        server_mod.execute_read_file_tool({
            "path": str(target), "startLine": 50000 if change == "grow_during_eof" else 1,
        })
