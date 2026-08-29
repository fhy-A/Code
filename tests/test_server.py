"""
Tests for server.py pure functions.
Run: python -m unittest tests.test_server -v
   or: python tests/test_server.py
"""
import base64
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import datetime as dt
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
import re
import socket
import sys
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server
import launcher


def _fake_pe_bytes(size=8192):
    payload = bytearray(max(size, 256))
    payload[:2] = b"MZ"
    payload[0x3C:0x40] = (0x80).to_bytes(4, "little")
    payload[0x80:0x84] = b"PE\0\0"
    return bytes(payload)


@contextmanager
def _update_http_fixture(payload, behaviors):
    state = {
        "payload": bytes(payload),
        "behaviors": list(behaviors),
        "requests": [],
        "active": 0,
        "peak": 0,
        "lock": threading.Lock(),
    }

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, _format, *_args):
            return

        def do_GET(self):
            with state["lock"]:
                state["active"] += 1
                state["peak"] = max(state["peak"], state["active"])
                behavior = state["behaviors"].pop(0) if state["behaviors"] else "normal"
            try:
                range_header = self.headers.get("Range", "")
                if_range = self.headers.get("If-Range", "")
                with state["lock"]:
                    state["requests"].append({
                        "range": range_header,
                        "ifRange": if_range,
                        "behavior": behavior,
                    })
                offset = 0
                match = re.fullmatch(r"bytes=(\d+)-", range_header)
                if match:
                    offset = int(match.group(1))
                ignored = behavior == "ignore_range" and offset > 0
                status = 200 if not offset or ignored else 206
                body = state["payload"] if ignored else state["payload"][offset:]
                self.send_response(status)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("ETag", '"fixture-etag"')
                self.send_header("Connection", "close")
                if status == 206:
                    start = offset + (1 if behavior == "bad_range" else 0)
                    self.send_header(
                        "Content-Range",
                        f"bytes {start}-{len(state['payload']) - 1}/{len(state['payload'])}",
                    )
                self.end_headers()
                if behavior in {"interrupt", "short"}:
                    cutoff = max(1, len(body) // 3)
                    self.wfile.write(body[:cutoff])
                    self.wfile.flush()
                    try:
                        self.connection.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
                    self.close_connection = True
                    return
                self.wfile.write(body)
                self.wfile.flush()
            finally:
                with state["lock"]:
                    state["active"] -= 1

    fixture = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=fixture.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{fixture.server_address[1]}/Code-v0.6.7.exe", state
    finally:
        fixture.shutdown()
        fixture.server_close()
        thread.join(timeout=2)


class _FaviconResponse:
    def __init__(self, status, *, headers=None, body=b""):
        self.status = status
        self._headers = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
        self._body = bytes(body)
        self._offset = 0
        self.read_calls = 0
        self.closed = False

    def getheader(self, name):
        return self._headers.get(str(name).lower())

    def read(self, size=-1):
        self.read_calls += 1
        if size is None or size < 0:
            size = len(self._body) - self._offset
        start = self._offset
        self._offset = min(len(self._body), start + size)
        return self._body[start:self._offset]

    def close(self):
        self.closed = True


class _FaviconConnection:
    def __init__(self, response):
        self.response = response
        self.method = None
        self.target = None
        self.headers = []
        self.closed = False
        self.sock = mock.Mock()
        self.sock.settimeout = mock.Mock()

    def putrequest(self, method, target, **kwargs):
        self.method = method
        self.target = target
        self.request_options = kwargs

    def putheader(self, name, value):
        self.headers.append((name, value))

    def endheaders(self):
        return None

    def getresponse(self):
        return self.response

    def close(self):
        self.closed = True


class TestFaviconProxySecurity(unittest.TestCase):
    PNG = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAFUlEQVR4nGNUqPjwn4GBgYEJRIAwACXYAoumRkB8AAAAAElFTkSuQmCC"
    )
    PLACEHOLDER_PNG = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Z1sYAAAAASUVORK5CYII="
    )
    PUBLIC_V4 = "93.184.216.34"
    PUBLIC_V6 = "2606:2800:220:1:248:1893:25c8:1946"

    @staticmethod
    def _record(ip, port=443):
        family = socket.AF_INET6 if ":" in ip else socket.AF_INET
        sockaddr = (ip, port, 0, 0) if family == socket.AF_INET6 else (ip, port)
        return (family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", sockaddr)

    def test_host_idna_and_candidate_validation(self):
        self.assertEqual(server._normalize_favicon_host("WWW.Example.COM."), "www.example.com")
        self.assertEqual(server._normalize_favicon_host("例子.测试"), "xn--fsqu00a.xn--0zwm56d")
        self.assertEqual(
            server._favicon_host_candidates("a.b.deepseek.com"),
            ("a.b.deepseek.com", "b.deepseek.com", "deepseek.com"),
        )
        self.assertEqual(
            server._favicon_host_candidates("b.baidu.com.cn"),
            ("b.baidu.com.cn", "baidu.com.cn"),
        )
        self.assertEqual(server._favicon_host_candidates("a.co.uk"), ("a.co.uk",))
        self.assertEqual(
            server._favicon_host_candidates("www.a.co.uk"),
            ("www.a.co.uk", "a.co.uk"),
        )
        urls = server._favicon_candidate_urls("https", "www.example.com")
        self.assertEqual(urls[0], "https://www.example.com/favicon.ico")
        direct_urls = [url for url in urls if server.parse.urlsplit(url).path == "/favicon.ico"]
        self.assertEqual(direct_urls, [
            "https://www.example.com/favicon.ico",
            "https://example.com/favicon.ico",
        ])
        first_provider = min(
            index for index, url in enumerate(urls)
            if server.parse.urlsplit(url).hostname in server._FAVICON_PROVIDER_HOSTS
        )
        self.assertGreaterEqual(first_provider, len(direct_urls))
        self.assertEqual(
            {server.parse.urlsplit(url).hostname for url in urls if "favicon.ico" not in url},
            set(server._FAVICON_PROVIDER_HOSTS),
        )
        for invalid in (
            "", "localhost", "printer", "example.local", "127.0.0.1",
            "[::1]", "example.com:443", "user@example.com", "example.com/path",
            "example.com?x=1", ".example.com", "bad_label.example",
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                server._normalize_favicon_host(invalid)

    def test_dns_requires_every_answer_to_be_public(self):
        public = [self._record(self.PUBLIC_V4), self._record(self.PUBLIC_V6)]
        self.assertEqual(
            len(server._public_favicon_addresses("example.com", 443, lambda *_args: public)),
            2,
        )
        blocked = (
            "127.0.0.1", "10.0.0.1", "169.254.1.1", "224.0.0.1",
            "0.0.0.0", "192.0.2.1", "::1", "fe80::1", "ff02::1",
        )
        for ip in blocked:
            with self.subTest(ip=ip), self.assertRaises(server._FaviconProxyError):
                server._public_favicon_addresses(
                    "example.com", 443, lambda *_args, value=ip: [self._record(value)],
                )
        with self.assertRaises(server._FaviconProxyError):
            server._public_favicon_addresses(
                "example.com",
                443,
                lambda *_args: [self._record(self.PUBLIC_V4), self._record("10.0.0.1")],
            )
        wrong_transport = (
            socket.AF_INET,
            socket.SOCK_DGRAM,
            socket.IPPROTO_UDP,
            "",
            (self.PUBLIC_V4, 443),
        )
        with self.assertRaises(server._FaviconProxyError):
            server._public_favicon_addresses("example.com", 443, lambda *_args: [wrong_transport])
        with self.assertRaises(server._FaviconProxyError):
            server._public_favicon_addresses(
                "example.com", 443, lambda *_args: [self._record(self.PUBLIC_V4, 80)],
            )

    def test_pinned_connection_uses_validated_sockaddr_and_tls_hostname(self):
        calls = {"connect": [], "tls": []}

        class FakeSocket:
            def __init__(self, *_args):
                self.peer = None

            def settimeout(self, timeout):
                calls["timeout"] = timeout

            def connect(self, sockaddr):
                self.peer = sockaddr
                calls["connect"].append(sockaddr)

            def getpeername(self):
                return self.peer

            def close(self):
                calls["closed"] = calls.get("closed", 0) + 1

        class FakeContext:
            def wrap_socket(self, sock, *, server_hostname):
                calls["tls"].append(server_hostname)
                return sock

        addresses = (self._record(self.PUBLIC_V4),)
        connection = server._PinnedHTTPConnection(
            "example.com",
            443,
            addresses,
            timeout=1.25,
            use_tls=True,
            socket_factory=FakeSocket,
            tls_context_factory=FakeContext,
        )
        connection.connect()
        self.assertEqual(calls["connect"], [(self.PUBLIC_V4, 443)])
        self.assertEqual(calls["tls"], ["example.com"])
        self.assertEqual(calls["timeout"], 1.25)

        class ChangedPeerSocket(FakeSocket):
            def getpeername(self):
                return ("142.250.72.36", 443)

        changed_peer = server._PinnedHTTPConnection(
            "example.com",
            443,
            addresses,
            timeout=1.25,
            use_tls=True,
            socket_factory=ChangedPeerSocket,
            tls_context_factory=FakeContext,
        )
        with self.assertRaisesRegex(server._FaviconProxyError, "connection failed"):
            changed_peer.connect()

    def _client(self, responses, *, resolver=None):
        connections = []
        queue = list(responses)

        def connection_factory(**kwargs):
            connection = _FaviconConnection(queue.pop(0))
            connection.factory_kwargs = kwargs
            connections.append(connection)
            return connection

        public_resolver = resolver or (
            lambda _host, port, *_args: [self._record(self.PUBLIC_V4, port)]
        )
        return server._FaviconHttpClient(
            resolver=public_resolver,
            connection_factory=connection_factory,
            clock=lambda: 10.0,
        ), connections

    def test_client_revalidates_redirects_and_sends_no_sensitive_headers(self):
        responses = [
            _FaviconResponse(302, headers={"Location": "https://cdn.example.net/icon.png"}),
            _FaviconResponse(200, headers={
                "Content-Type": "image/png",
                "Content-Length": str(len(self.PNG)),
            }, body=self.PNG),
        ]
        client, connections = self._client(responses)
        asset = client.fetch("https://example.com/favicon.ico", deadline=20.0)
        self.assertEqual(asset, (self.PNG, "image/png"))
        self.assertEqual([item.factory_kwargs["host"] for item in connections], [
            "example.com", "cdn.example.net",
        ])
        self.assertEqual(connections[0].target, "/favicon.ico")
        self.assertEqual(connections[1].target, "/icon.png")
        headers = {name.lower(): value for name, value in connections[0].headers}
        self.assertEqual(headers["host"], "example.com")
        self.assertFalse({"authorization", "cookie", "referer"} & set(headers))
        self.assertTrue(all(item.closed and item.response.closed for item in connections))

        downgrade_client, _ = self._client([
            _FaviconResponse(302, headers={"Location": "http://example.com/icon.png"}),
        ])
        with self.assertRaisesRegex(server._FaviconProxyError, "downgrade"):
            downgrade_client.fetch("https://example.com/favicon.ico", deadline=20.0)
        upgraded_then_downgraded, _ = self._client([
            _FaviconResponse(302, headers={"Location": "https://cdn.example.net/icon.png"}),
            _FaviconResponse(302, headers={"Location": "http://cdn.example.net/icon.png"}),
        ])
        with self.assertRaisesRegex(server._FaviconProxyError, "downgrade"):
            upgraded_then_downgraded.fetch("http://example.com/favicon.ico", deadline=20.0)

        loop_client, _ = self._client([
            _FaviconResponse(302, headers={"Location": "/favicon.ico"}),
        ])
        with self.assertRaisesRegex(server._FaviconProxyError, "loop"):
            loop_client.fetch("https://example.com/favicon.ico", deadline=20.0)
        redirect_limit_client, _ = self._client([
            _FaviconResponse(302, headers={"Location": f"https://cdn{index}.example.net/icon.png"})
            for index in range(server._FAVICON_MAX_REDIRECTS + 1)
        ])
        with self.assertRaisesRegex(server._FaviconProxyError, "limit"):
            redirect_limit_client.fetch("https://example.com/favicon.ico", deadline=20.0)
        for unsafe_url in (
            "https://user:secret@example.com/favicon.ico",
            "https://example.com:8443/favicon.ico",
            "https://127.0.0.1/favicon.ico",
        ):
            unsafe_client, _ = self._client([])
            with self.subTest(url=unsafe_url), self.assertRaises(server._FaviconProxyError):
                unsafe_client.fetch(unsafe_url, deadline=20.0)

    def test_redirect_private_mixed_dns_and_response_validation_fail_closed(self):
        def resolver(host, port, *_args):
            if host == "private.example.com":
                return [self._record("10.0.0.8", port)]
            if host == "mixed.example.com":
                return [self._record(self.PUBLIC_V4, port), self._record("192.168.1.8", port)]
            return [self._record(self.PUBLIC_V4, port)]

        for redirect_host in ("private.example.com", "mixed.example.com"):
            client, connections = self._client([
                _FaviconResponse(302, headers={"Location": f"https://{redirect_host}/icon.png"}),
            ], resolver=resolver)
            with self.subTest(host=redirect_host), self.assertRaises(server._FaviconProxyError):
                client.fetch("https://example.com/favicon.ico", deadline=20.0)
            self.assertEqual(len(connections), 1)

        bad_responses = (
            _FaviconResponse(200, headers={"Content-Type": "text/html"}, body=b"<html>no</html>"),
            _FaviconResponse(200, headers={"Content-Type": "image/svg+xml"}, body=b"<svg></svg>"),
            _FaviconResponse(200, headers={"Content-Type": "image/png"}, body=b"not-png"),
            _FaviconResponse(200, headers={
                "Content-Type": "image/png",
                "Content-Length": str(server._FAVICON_MAX_BYTES + 1),
            }, body=b""),
        )
        for response in bad_responses:
            client, _ = self._client([response])
            with self.assertRaises(server._FaviconProxyError):
                client.fetch("https://example.com/favicon.ico", deadline=20.0)
        with self.assertRaises(server._FaviconProxyError):
            server._validated_favicon_asset(
                self.PNG + b"x" * server._FAVICON_MAX_BYTES,
                "image/png",
            )

        timeout_client, timeout_connections = self._client([
            _FaviconResponse(200, headers={"Content-Type": "image/png"}, body=self.PNG),
        ])
        original_factory = timeout_client._connection_factory

        def timeout_factory(**kwargs):
            connection = original_factory(**kwargs)
            connection.endheaders = mock.Mock(side_effect=TimeoutError("timed out"))
            return connection

        timeout_client._connection_factory = timeout_factory
        with self.assertRaisesRegex(server._FaviconTransientError, "network"):
            timeout_client.fetch("https://example.com/favicon.ico", deadline=20.0)
        self.assertEqual(len(timeout_connections), 1)

        temporarily_unavailable, _ = self._client([_FaviconResponse(503)])
        with self.assertRaisesRegex(server._FaviconTransientError, "temporarily"):
            temporarily_unavailable.fetch("https://example.com/favicon.ico", deadline=20.0)
        permanently_missing, _ = self._client([_FaviconResponse(404)])
        with self.assertRaises(server._FaviconProxyError) as missing_error:
            permanently_missing.fetch("https://example.com/favicon.ico", deadline=20.0)
        self.assertNotIsInstance(missing_error.exception, server._FaviconTransientError)

    def test_degenerate_raster_dimensions_are_permanently_rejected(self):
        client, _ = self._client([
            _FaviconResponse(
                200,
                headers={"Content-Type": "image/png"},
                body=self.PLACEHOLDER_PNG,
            ),
        ])
        with self.assertRaisesRegex(server._FaviconProxyError, "dimensions") as error:
            client.fetch("https://example.com/favicon.ico", deadline=20.0)
        self.assertNotIsInstance(error.exception, server._FaviconTransientError)

    def test_degenerate_candidate_continues_to_valid_asset_and_only_valid_asset_is_cached(self):
        class PlaceholderThenValidClient:
            def __init__(self):
                self.calls = []

            def fetch(self, url, *, deadline):
                self.calls.append((url, deadline))
                payload = (
                    TestFaviconProxySecurity.PLACEHOLDER_PNG
                    if len(self.calls) == 1
                    else TestFaviconProxySecurity.PNG
                )
                return server._validated_favicon_asset(payload, "image/png")

        client = PlaceholderThenValidClient()
        proxy = server._FaviconProxy(http_client=client, clock=lambda: 100.0)
        key = ("https", "example.com")
        expected = (self.PNG, "image/png")
        self.assertEqual(proxy.get(*key), expected)
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(proxy._cache[key][1], expected)
        self.assertEqual(proxy.get(*key), expected)
        self.assertEqual(len(client.calls), 2)

    def test_all_degenerate_candidates_never_enter_positive_cache(self):
        class PlaceholderClient:
            def __init__(self):
                self.calls = []

            def fetch(self, url, *, deadline):
                self.calls.append((url, deadline))
                return server._validated_favicon_asset(
                    TestFaviconProxySecurity.PLACEHOLDER_PNG,
                    "image/png",
                )

        client = PlaceholderClient()
        proxy = server._FaviconProxy(
            http_client=client,
            clock=lambda: 100.0,
            positive_ttl=3600,
            negative_ttl=30,
        )
        key = ("https", "missing.example.com")
        self.assertIsNone(proxy.get(*key))
        self.assertEqual(
            len(client.calls),
            len(server._favicon_candidate_urls(*key)),
        )
        self.assertIn(key, proxy._cache)
        self.assertIsNone(proxy._cache[key][1])
        self.assertEqual(proxy._cache[key][0], 130.0)

    def test_slow_multichunk_response_cannot_exceed_total_deadline(self):
        clock = [0.0]

        class SlowResponse(_FaviconResponse):
            def __init__(self):
                super().__init__(200, headers={"Content-Type": "image/png"})
                payload = TestFaviconProxySecurity.PNG
                self.chunks = [payload[:8], payload[8:16], payload[16:]]
                self.connection = None

            def read(self, _size=-1):
                if not self.chunks:
                    return b""
                allowed = self.connection.sock.settimeout.call_args.args[0]
                delay = 0.4
                if allowed < delay:
                    clock[0] += allowed
                    raise TimeoutError("chunk exceeded remaining deadline")
                clock[0] += delay
                return self.chunks.pop(0)

        response = SlowResponse()
        connections = []

        def connection_factory(**_kwargs):
            connection = _FaviconConnection(response)
            response.connection = connection
            connections.append(connection)
            return connection

        client = server._FaviconHttpClient(
            resolver=lambda _host, port, *_args: [self._record(self.PUBLIC_V4, port)],
            connection_factory=connection_factory,
            clock=lambda: clock[0],
        )
        with self.assertRaisesRegex(server._FaviconTransientError, "network"):
            client.fetch("https://example.com/favicon.ico", deadline=1.0)
        self.assertEqual(len(connections), 1)
        observed = [call.args[0] for call in connections[0].sock.settimeout.call_args_list]
        self.assertEqual(len(observed), 4)  # headers, then each attempted body chunk
        self.assertAlmostEqual(observed[0], 1.0)
        self.assertAlmostEqual(observed[1], 1.0)
        self.assertAlmostEqual(observed[2], 0.6)
        self.assertAlmostEqual(observed[3], 0.2)
        self.assertAlmostEqual(clock[0], 1.0)

        detached_socket = mock.Mock()
        detached_socket.settimeout = mock.Mock()
        detached_connection = mock.Mock(sock=None)
        detached_response = mock.Mock()
        detached_response.fp.raw._sock = detached_socket
        remaining = client._tighten_socket_timeout(
            detached_connection,
            deadline=clock[0] + 0.5,
            response=detached_response,
        )
        self.assertAlmostEqual(remaining, 0.5)
        detached_socket.settimeout.assert_called_once_with(0.5)

    def test_connection_close_exact_content_length_succeeds_once_and_is_positive_cached(self):
        response = _FaviconResponse(200, headers={
            "Content-Type": "image/png",
            "Content-Length": str(len(self.PNG)),
            "Connection": "close",
        }, body=self.PNG)
        connections = []

        def connection_factory(**_kwargs):
            connection = _FaviconConnection(response)
            response_socket = connection.sock

            def getresponse():
                connection.sock = None
                response.fp = mock.Mock()
                response.fp.raw._sock = response_socket
                return response

            connection.getresponse = getresponse
            connections.append((connection, response_socket))
            return connection

        client = server._FaviconHttpClient(
            resolver=lambda _host, port, *_args: [self._record(self.PUBLIC_V4, port)],
            connection_factory=connection_factory,
        )
        proxy = server._FaviconProxy(http_client=client)
        expected = (self.PNG, "image/png")
        self.assertEqual(proxy.get("https", "example.com"), expected)
        self.assertEqual(proxy.get("https", "example.com"), expected)
        self.assertEqual(len(connections), 1)
        self.assertEqual(response.read_calls, 1)
        self.assertEqual(connections[0][1].settimeout.call_count, 2)  # headers + exact body
        cached = proxy._cache[("https", "example.com")]
        self.assertEqual(cached[1], expected)

    def test_content_length_early_eof_is_rejected(self):
        response = _FaviconResponse(200, headers={
            "Content-Type": "image/png",
            "Content-Length": str(len(self.PNG) + 5),
            "Connection": "close",
        }, body=self.PNG)
        client, connections = self._client([response])
        with self.assertRaisesRegex(server._FaviconTransientError, "before Content-Length"):
            client.fetch("https://example.com/favicon.ico", deadline=20.0)
        self.assertEqual(response.read_calls, 2)
        self.assertEqual(connections[0].sock.settimeout.call_count, 3)  # headers + body + EOF

    def test_chunked_multiblock_response_tightens_each_real_read_and_accepts_closed_frame(self):
        payload = self.PNG

        class ChunkedResponse(_FaviconResponse):
            def __init__(self):
                super().__init__(200, headers={"Content-Type": "image/png"})
                self.chunks = [payload[:8], payload[8:]]
                self.protocol_closed = False

            def read(self, _size=-1):
                self.read_calls += 1
                chunk = self.chunks.pop(0)
                if not self.chunks:
                    self.protocol_closed = True
                    self.fp = None
                return chunk

            def isclosed(self):
                return self.protocol_closed

        response = ChunkedResponse()
        client, connections = self._client([response])
        self.assertEqual(
            client.fetch("https://example.com/favicon.ico", deadline=20.0),
            (self.PNG, "image/png"),
        )
        self.assertEqual(response.read_calls, 2)
        self.assertEqual(connections[0].sock.settimeout.call_count, 3)  # headers + two chunks

    def test_handler_returns_binary_success_and_non_leaking_failures(self):
        class Output:
            def __init__(self):
                self.data = bytearray()

            def write(self, value):
                self.data.extend(value)

        class Handler:
            def __init__(self):
                self.status = None
                self.headers = []
                self.json = None
                self.wfile = Output()

            def send_response(self, status):
                self.status = status

            def send_header(self, name, value):
                self.headers.append((name, str(value)))

            def end_headers(self):
                return None

            def send_json(self, payload, status=200):
                self.json = payload
                self.status = status

        proxy = mock.Mock()
        proxy.get.return_value = (self.PNG, "image/png")
        handler = Handler()
        with mock.patch.object(server, "_favicon_proxy", proxy):
            server.CodeHandler.get_favicon(
                handler,
                {"scheme": ["https"], "host": ["example.com"]},
            )
        self.assertEqual(handler.status, 200)
        self.assertEqual(bytes(handler.wfile.data), self.PNG)
        self.assertIn(("Content-Type", "image/png"), handler.headers)
        self.assertIn(("X-Content-Type-Options", "nosniff"), handler.headers)
        proxy.get.assert_called_once_with("https", "example.com")

        proxy.get.return_value = None
        missing = Handler()
        with mock.patch.object(server, "_favicon_proxy", proxy):
            server.CodeHandler.get_favicon(
                missing,
                {"scheme": ["https"], "host": ["missing.example.com"]},
            )
        self.assertEqual(missing.status, 404)
        self.assertEqual(bytes(missing.wfile.data), b"")
        self.assertIn(("Cache-Control", "no-store"), missing.headers)

        proxy.get.side_effect = server._FaviconTransientError("temporary transport detail")
        transient = Handler()
        with mock.patch.object(server, "_favicon_proxy", proxy):
            server.CodeHandler.get_favicon(
                transient,
                {"scheme": ["https"], "host": ["temporary.example.com"]},
            )
        self.assertEqual(transient.status, 503)
        self.assertIn(("Cache-Control", "no-store"), transient.headers)
        self.assertIn(("Retry-After", "1"), transient.headers)
        self.assertEqual(bytes(transient.wfile.data), b"")

        invalid = Handler()
        server.CodeHandler.get_favicon(invalid, {"scheme": ["https", "http"], "host": ["example.com"]})
        self.assertEqual(invalid.status, 400)
        self.assertEqual(invalid.json, {"error": "invalid favicon request"})
        extra = Handler()
        server.CodeHandler.get_favicon(
            extra,
            {"scheme": ["https"], "host": ["example.com"], "url": ["https://internal/"]},
        )
        self.assertEqual(extra.status, 400)

        unexpected = Handler()
        proxy.get.side_effect = RuntimeError("SECRET_INTERNAL_UPSTREAM_DETAIL")
        with mock.patch.object(server, "_favicon_proxy", proxy):
            server.CodeHandler.get_favicon(
                unexpected,
                {"scheme": ["https"], "host": ["example.com"]},
            )
        self.assertEqual(unexpected.status, 502)
        self.assertEqual(unexpected.json, {"error": "favicon unavailable"})
        self.assertNotIn("SECRET_INTERNAL_UPSTREAM_DETAIL", json.dumps(unexpected.json))

    def test_cache_ttl_lru_and_same_host_requests_are_coalesced(self):
        clock_value = [100.0]

        class CountingClient:
            def __init__(self):
                self.calls = []
                self.release = threading.Event()
                self.entered = threading.Event()

            def fetch(self, url, *, deadline):
                self.calls.append(url)
                self.entered.set()
                self.release.wait(timeout=2)
                return (TestFaviconProxySecurity.PNG, "image/png")

        client = CountingClient()
        proxy = server._FaviconProxy(
            http_client=client,
            clock=lambda: clock_value[0],
            cache_capacity=2,
            positive_ttl=10,
            negative_ttl=3,
        )
        results = []
        threads = [
            threading.Thread(target=lambda: results.append(proxy.get("https", "example.com")))
            for _ in range(2)
        ]
        for thread in threads:
            thread.start()
        self.assertTrue(client.entered.wait(timeout=1))
        client.release.set()
        for thread in threads:
            thread.join(timeout=2)
        self.assertEqual(results, [(self.PNG, "image/png"), (self.PNG, "image/png")])
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(proxy.get("https", "example.com"), (self.PNG, "image/png"))
        self.assertEqual(len(client.calls), 1)

        proxy.get("https", "second.example.com")
        proxy.get("https", "example.com")
        proxy.get("https", "third.example.com")
        proxy.get("https", "second.example.com")
        self.assertEqual(len(client.calls), 4)  # second was the LRU eviction
        clock_value[0] += 11
        proxy.get("https", "example.com")
        self.assertEqual(len(client.calls), 5)

    def test_negative_cache_and_distinct_host_concurrency_are_bounded(self):
        clock_value = [50.0]

        class MissingClient:
            def __init__(self):
                self.calls = 0

            def fetch(self, _url, *, deadline):
                self.calls += 1
                raise server._FaviconProxyError("missing")

        missing = MissingClient()
        proxy = server._FaviconProxy(
            http_client=missing,
            clock=lambda: clock_value[0],
            negative_ttl=4,
        )
        self.assertIsNone(proxy.get("https", "missing.example.com"))
        calls_after_first = missing.calls
        self.assertIsNone(proxy.get("https", "missing.example.com"))
        self.assertEqual(missing.calls, calls_after_first)
        clock_value[0] += 5
        self.assertIsNone(proxy.get("https", "missing.example.com"))
        self.assertGreater(missing.calls, calls_after_first)

        active = 0
        maximum = 0
        lock = threading.Lock()

        class SlowClient:
            def fetch(self, _url, *, deadline):
                nonlocal active, maximum
                with lock:
                    active += 1
                    maximum = max(maximum, active)
                time.sleep(0.03)
                with lock:
                    active -= 1
                return (TestFaviconProxySecurity.PNG, "image/png")

        bounded = server._FaviconProxy(
            http_client=SlowClient(),
            semaphore=threading.BoundedSemaphore(1),
        )
        workers = [
            threading.Thread(target=bounded.get, args=("https", f"host{index}.example.com"))
            for index in range(3)
        ]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=2)
        self.assertEqual(maximum, 1)

    def test_transient_transport_failures_are_not_negative_cached(self):
        class RecoveringClient:
            def __init__(self):
                self.calls = 0
                self.transient = True

            def fetch(self, _url, *, deadline):
                self.calls += 1
                if self.transient:
                    raise server._FaviconTransientError("temporary network failure")
                return TestFaviconProxySecurity.PNG, "image/png"

        client = RecoveringClient()
        proxy = server._FaviconProxy(http_client=client)
        key = ("https", "temporary.example.com")
        with self.assertRaises(server._FaviconTransientError):
            proxy.get(*key)
        self.assertNotIn(key, proxy._cache)
        transient_calls = client.calls
        self.assertGreater(transient_calls, 0)

        client.transient = False
        self.assertEqual(proxy.get(*key), (self.PNG, "image/png"))
        self.assertGreater(client.calls, transient_calls)
        self.assertEqual(proxy._cache[key][1], (self.PNG, "image/png"))

    def test_capacity_rejection_is_transient_and_does_not_create_negative_cache(self):
        class SequenceSemaphore:
            def __init__(self):
                self.results = [False, True]
                self.releases = 0

            def acquire(self, *, timeout):
                self.last_timeout = timeout
                return self.results.pop(0)

            def release(self):
                self.releases += 1

        class SuccessClient:
            def __init__(self):
                self.calls = 0

            def fetch(self, _url, *, deadline):
                self.calls += 1
                return TestFaviconProxySecurity.PNG, "image/png"

        semaphore = SequenceSemaphore()
        client = SuccessClient()
        proxy = server._FaviconProxy(http_client=client, semaphore=semaphore)
        key = ("https", "capacity.example.com")
        with self.assertRaises(server._FaviconTransientError):
            proxy.get(*key)
        self.assertNotIn(key, proxy._cache)
        self.assertEqual(client.calls, 0)
        self.assertEqual(proxy.get(*key), (self.PNG, "image/png"))
        self.assertEqual(client.calls, 1)
        self.assertEqual(semaphore.releases, 1)
        self.assertIn(key, proxy._cache)


class TestSkillDependencyOperations(unittest.TestCase):
    def setUp(self):
        with server._dependency_operation_lock:
            server._dependency_operations.clear()

    def tearDown(self):
        with server._dependency_operation_lock:
            server._dependency_operations.clear()

    def _plan(self, fingerprint="plan-fingerprint"):
        return {
            "schemaVersion": 1,
            "skill": "demo",
            "capability": "runtime",
            "action": "install",
            "actionable": True,
            "noChanges": False,
            "blockedReasons": [],
            "requirements": [],
            "systemRequirements": [],
            "locations": {"python": r"C:\managed\python", "node": r"C:\managed\node"},
            "authorization": {
                "scope": "managed_runtime",
                "root": r"C:\managed",
                "systemPackageManagers": False,
                "pathChanges": False,
                "globalWrappers": False,
            },
            "steps": [{
                "id": "install-python-packages",
                "type": "python",
                "purpose": "install_packages",
                "displayCommand": "python -m pip install demo",
                "_argv": ["python", "-m", "pip", "install", "demo"],
            }],
            "commandSummaries": ["python -m pip install demo"],
            "fingerprint": fingerprint,
        }

    def test_operation_is_idempotent_tracks_progress_and_hides_argv(self):
        release = threading.Event()

        def execute(plan, *, cancel_event, progress_callback, process_callback, timeout_seconds):
            progress_callback({
                "phase": "install_packages",
                "currentStep": 1,
                "completedSteps": 0,
                "totalSteps": 1,
                "step": server.public_dependency_operation_plan(plan["steps"][0]),
            })
            release.wait(timeout=3)
            return {"ok": True, "completedSteps": 1, "totalSteps": 1}

        with (
            mock.patch.object(server, "preview_skill_dependency_operation", return_value=self._plan()) as preview,
            mock.patch.object(server, "execute_dependency_operation_plan", side_effect=execute),
            mock.patch.object(server, "get_single_skill_dependency_status", return_value={
                "name": "demo", "status": "ready", "capabilities": [],
            }),
        ):
            operation = server.create_skill_dependency_operation("demo", "runtime", "install", "plan-fingerprint")
            duplicate = server.create_skill_dependency_operation("demo", "runtime", "install", "plan-fingerprint")
            self.assertIs(operation, duplicate)
            with self.assertRaisesRegex(ValueError, "already running"):
                server.create_skill_dependency_operation("other", "runtime", "install", "plan-fingerprint")
            preview.assert_called_once_with("demo", "runtime", "install")
            deadline = time.time() + 2
            while operation["status"] == "pending" and time.time() < deadline:
                time.sleep(0.01)
            snapshot = server._dependency_operation_snapshot(operation)
            self.assertEqual(snapshot["status"], "running")
            self.assertEqual(snapshot["currentCommand"], "python -m pip install demo")
            self.assertNotIn("_argv", snapshot["plan"]["steps"][0])
            release.set()
            deadline = time.time() + 2
            while operation["status"] != "completed" and time.time() < deadline:
                time.sleep(0.01)

        self.assertEqual(operation["status"], "completed")
        self.assertEqual(operation["progress"], 100)
        self.assertEqual(operation["result"]["dependency"]["status"], "ready")
        dismissed = server.cancel_skill_dependency_operation(operation["id"])
        self.assertTrue(server._dependency_operation_snapshot(dismissed)["dismissed"])
        self.assertIsNone(server.get_skill_dependency_operation(operation["id"]))

    def test_cancellation_reaches_terminal_state_and_is_retryable(self):
        def execute(plan, *, cancel_event, progress_callback, process_callback, timeout_seconds):
            cancel_event.wait(timeout=3)
            return {"ok": False, "cancelled": True, "errorCode": "cancelled"}

        with (
            mock.patch.object(server, "preview_skill_dependency_operation", return_value=self._plan()),
            mock.patch.object(server, "execute_dependency_operation_plan", side_effect=execute),
        ):
            operation = server.create_skill_dependency_operation("demo", "runtime", "install", "plan-fingerprint")
            server.cancel_skill_dependency_operation(operation["id"])
            deadline = time.time() + 2
            while operation["status"] != "cancelled" and time.time() < deadline:
                time.sleep(0.01)

        snapshot = server._dependency_operation_snapshot(operation)
        self.assertEqual(snapshot["status"], "cancelled")
        self.assertTrue(snapshot["cancelRequested"])
        self.assertTrue(snapshot["retryable"])

    def test_failed_operation_keeps_safe_recovery_metadata(self):
        with (
            mock.patch.object(server, "preview_skill_dependency_operation", return_value=self._plan()),
            mock.patch.object(server, "execute_dependency_operation_plan", return_value={
                "ok": False,
                "errorCode": "process_failed",
                "error": "Dependency step failed with exit code 1.",
                "failedStep": {"id": "install-python-packages", "displayCommand": "python -m pip install demo"},
            }),
        ):
            operation = server.create_skill_dependency_operation("demo", "runtime", "install", "plan-fingerprint")
            deadline = time.time() + 2
            while operation["status"] not in server._DEPENDENCY_OPERATION_TERMINAL and time.time() < deadline:
                time.sleep(0.01)

        snapshot = server._dependency_operation_snapshot(operation)
        self.assertEqual(snapshot["status"], "failed")
        self.assertEqual(snapshot["errorCode"], "process_failed")
        self.assertTrue(snapshot["retryable"])
        self.assertNotIn("stdout", snapshot)
        self.assertNotIn("stderr", snapshot)


class TestUpdaterHelpers(unittest.TestCase):
    def setUp(self):
        server._reset_update_runtime_state_for_tests()

    def _descriptor(self, url, payload, *, digest=None, size=None):
        return {
            "version": "0.6.7",
            "name": "Code-v0.6.7.exe",
            "url": url,
            "size": len(payload) if size is None else size,
            "digest": digest or hashlib.sha256(payload).hexdigest(),
        }

    def _wait_for_terminal(self, job_id, timeout=5):
        deadline = time.time() + timeout
        snapshot = server._current_update_snapshot(job_id)
        while snapshot["status"] not in {"completed", "failed", "installing"} and time.time() < deadline:
            time.sleep(0.01)
            snapshot = server._current_update_snapshot(job_id)
        self.assertIn(snapshot["status"], {"completed", "failed", "installing"})
        return snapshot

    @contextmanager
    def _allow_local_descriptor(self):
        normalize = server._normalize_update_descriptor
        with mock.patch.object(
            server,
            "_normalize_update_descriptor",
            side_effect=lambda value, require_official=True: normalize(value, require_official=False),
        ):
            yield

    def test_update_start_is_single_flight_for_same_trusted_asset(self):
        descriptor = {
            "version": "0.6.7",
            "name": "Code-v0.6.7.exe",
            "url": "https://github.com/fhy-A/Code/releases/download/v0.6.7/Code-v0.6.7.exe",
            "size": 16,
            "digest": "a" * 64,
        }
        launches = []
        barrier = threading.Barrier(8)

        def start_once(target_dir):
            barrier.wait(timeout=2)
            return server._start_or_attach_update_job(descriptor, target_dir=target_dir)

        with tempfile.TemporaryDirectory() as temp_dir:
            server._reset_update_runtime_state_for_tests()
            with mock.patch.object(server, "_launch_update_worker", side_effect=lambda job: launches.append(job["jobId"])):
                with ThreadPoolExecutor(max_workers=8) as pool:
                    snapshots = list(pool.map(lambda _index: start_once(Path(temp_dir)), range(8)))

        self.assertEqual({item["jobId"] for item in snapshots}, {snapshots[0]["jobId"]})
        self.assertEqual(launches, [snapshots[0]["jobId"]])

    def test_interrupted_download_resumes_with_strict_range_and_etag(self):
        payload = _fake_pe_bytes(12 * 1024)
        identity = {"version": "0.6.7", "originalFilename": "Code-v0.6.7.exe", "productName": "Code"}
        with _update_http_fixture(payload, ["interrupt", "normal"]) as (url, fixture):
            descriptor = self._descriptor(url, payload)
            with tempfile.TemporaryDirectory() as temp_dir, self._allow_local_descriptor(), \
                 mock.patch.object(server, "_read_windows_file_identity", return_value=identity), \
                 mock.patch.object(server, "_UPDATE_RETRY_DELAYS", (0, 0)):
                started = server._start_or_attach_update_job(descriptor, target_dir=Path(temp_dir))
                result = self._wait_for_terminal(started["jobId"])
                final = Path(temp_dir) / descriptor["name"]
                self.assertEqual(result["status"], "completed")
                self.assertEqual(final.read_bytes(), payload)
                self.assertEqual(result["progress"], 100)
        self.assertEqual(len(fixture["requests"]), 2)
        self.assertEqual(fixture["requests"][0]["range"], "")
        self.assertRegex(fixture["requests"][1]["range"], r"^bytes=[1-9][0-9]*-$")
        self.assertEqual(fixture["requests"][1]["ifRange"], '"fixture-etag"')
        self.assertEqual(fixture["peak"], 1)

    def test_ignored_range_restarts_once_without_duplicate_bytes(self):
        payload = _fake_pe_bytes(12 * 1024)
        identity = {"version": "0.6.7", "originalFilename": "Code-v0.6.7.exe", "productName": "Code"}
        observed_progress = []
        set_state = server._set_update_job_state

        def capture_state(*args, **kwargs):
            result = set_state(*args, **kwargs)
            if result is not None:
                observed_progress.append(int(result.get("progress") or 0))
            return result

        with _update_http_fixture(payload, ["interrupt", "ignore_range", "normal"]) as (url, fixture):
            descriptor = self._descriptor(url, payload)
            with tempfile.TemporaryDirectory() as temp_dir, self._allow_local_descriptor(), \
                 mock.patch.object(server, "_read_windows_file_identity", return_value=identity), \
                 mock.patch.object(server, "_UPDATE_RETRY_DELAYS", (0, 0)), \
                 mock.patch.object(server, "_set_update_job_state", side_effect=capture_state):
                started = server._start_or_attach_update_job(descriptor, target_dir=Path(temp_dir))
                result = self._wait_for_terminal(started["jobId"])
                self.assertEqual(result["status"], "completed")
                self.assertEqual((Path(temp_dir) / descriptor["name"]).read_bytes(), payload)
        self.assertEqual([item["behavior"] for item in fixture["requests"]], ["interrupt", "ignore_range", "normal"])
        self.assertRegex(fixture["requests"][1]["range"], r"^bytes=[1-9][0-9]*-$")
        self.assertEqual(fixture["requests"][2]["range"], "")
        self.assertEqual(observed_progress, sorted(observed_progress))

    def test_invalid_content_range_fails_closed(self):
        payload = _fake_pe_bytes(12 * 1024)
        with _update_http_fixture(payload, ["interrupt", "bad_range"]) as (url, fixture):
            descriptor = self._descriptor(url, payload)
            with tempfile.TemporaryDirectory() as temp_dir, self._allow_local_descriptor(), \
                 mock.patch.object(server, "_UPDATE_RETRY_DELAYS", (0, 0)):
                started = server._start_or_attach_update_job(descriptor, target_dir=Path(temp_dir))
                result = self._wait_for_terminal(started["jobId"])
                self.assertEqual(result["status"], "failed")
                self.assertEqual(result["errorCode"], "upstream_protocol_invalid")
                self.assertFalse((Path(temp_dir) / f"{descriptor['name']}.part").exists())
                self.assertFalse((Path(temp_dir) / descriptor["name"]).exists())
        self.assertEqual(len(fixture["requests"]), 2)

    def test_short_read_is_bounded_and_retryable(self):
        payload = _fake_pe_bytes(12 * 1024)
        with _update_http_fixture(payload, ["short", "short", "short"]) as (url, fixture):
            descriptor = self._descriptor(url, payload)
            with tempfile.TemporaryDirectory() as temp_dir, self._allow_local_descriptor(), \
                 mock.patch.object(server, "_UPDATE_RETRY_DELAYS", (0, 0)):
                started = server._start_or_attach_update_job(descriptor, target_dir=Path(temp_dir))
                result = self._wait_for_terminal(started["jobId"])
                self.assertEqual(result["status"], "failed")
                self.assertEqual(result["errorCode"], "download_short_read")
                self.assertTrue(result["retryable"])
        self.assertEqual(len(fixture["requests"]), 3)

    def test_digest_and_pe_identity_mismatch_never_publish(self):
        payload = _fake_pe_bytes(8192)
        identity = {"version": "9.9.9", "originalFilename": "Wrong.exe", "productName": "Code"}
        cases = [
            ("0" * 64, {"version": "0.6.7", "originalFilename": "Code-v0.6.7.exe", "productName": "Code"}, "download_digest_mismatch"),
            (hashlib.sha256(payload).hexdigest(), identity, "download_pe_invalid"),
        ]
        for digest, observed_identity, expected_code in cases:
            with self.subTest(expected_code=expected_code), \
                 _update_http_fixture(payload, ["normal"]) as (url, _fixture), \
                 tempfile.TemporaryDirectory() as temp_dir, self._allow_local_descriptor(), \
                 mock.patch.object(server, "_read_windows_file_identity", return_value=observed_identity):
                server._reset_update_runtime_state_for_tests()
                descriptor = self._descriptor(url, payload, digest=digest)
                started = server._start_or_attach_update_job(descriptor, target_dir=Path(temp_dir))
                result = self._wait_for_terminal(started["jobId"])
                self.assertEqual(result["errorCode"], expected_code)
                self.assertFalse((Path(temp_dir) / descriptor["name"]).exists())

    def test_service_restart_restores_sidecar_and_resumes_same_job(self):
        payload = _fake_pe_bytes(12 * 1024)
        identity = {"version": "0.6.7", "originalFilename": "Code-v0.6.7.exe", "productName": "Code"}
        with _update_http_fixture(payload, ["normal"]) as (url, fixture):
            descriptor = self._descriptor(url, payload)
            with tempfile.TemporaryDirectory() as temp_dir, self._allow_local_descriptor(), \
                 mock.patch.object(server, "_read_windows_file_identity", return_value=identity), \
                 mock.patch.object(server, "_UPDATE_RETRY_DELAYS", (0, 0)):
                target = Path(temp_dir)
                partial = target / f"{descriptor['name']}.part"
                partial.write_bytes(payload[:3072])
                job_id = str(uuid.uuid4())
                metadata = {
                    "schema": server._UPDATE_JOB_SCHEMA,
                    "jobId": job_id,
                    "descriptor": descriptor,
                    "status": "downloading",
                    "stage": "downloading",
                    "progress": 25,
                    "downloaded": 3072,
                    "etag": '"fixture-etag"',
                    "errorCode": "",
                    "retryable": False,
                    "updatedAt": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
                }
                server._atomic_write_update_metadata(server._update_metadata_path(target, descriptor), metadata)
                server._reset_update_runtime_state_for_tests()
                restored = server._restore_update_jobs(target, trusted_descriptor=descriptor)
                self.assertEqual(restored[0]["jobId"], job_id)
                result = self._wait_for_terminal(job_id)
                self.assertEqual(result["status"], "completed")
                self.assertEqual((target / descriptor["name"]).read_bytes(), payload)
        self.assertEqual(fixture["requests"], [{"range": "bytes=3072-", "ifRange": '"fixture-etag"', "behavior": "normal"}])

    def test_corrupt_or_expired_sidecar_does_not_publish_or_touch_part(self):
        payload = _fake_pe_bytes(8192)
        descriptor = self._descriptor(
            "https://github.com/fhy-A/Code/releases/download/v0.6.7/Code-v0.6.7.exe",
            payload,
        )
        for expired in (False, True):
            with self.subTest(expired=expired), tempfile.TemporaryDirectory() as temp_dir:
                target = Path(temp_dir)
                partial = target / f"{descriptor['name']}.part"
                partial.write_bytes(payload[:512])
                metadata_path = server._update_metadata_path(target, descriptor)
                if expired:
                    metadata = {
                        "schema": server._UPDATE_JOB_SCHEMA,
                        "jobId": str(uuid.uuid4()),
                        "descriptor": descriptor,
                        "status": "downloading",
                        "stage": "downloading",
                        "progress": 1,
                        "downloaded": 512,
                        "etag": "",
                        "errorCode": "",
                        "retryable": False,
                        "updatedAt": "2020-01-01T00:00:00Z",
                    }
                    server._atomic_write_update_metadata(metadata_path, metadata)
                else:
                    metadata_path.write_text("{broken", encoding="utf-8")
                before = partial.read_bytes()
                self.assertEqual(
                    server._restore_update_jobs(target, trusted_descriptor=descriptor, start_workers=False),
                    [],
                )
                self.assertEqual(partial.read_bytes(), before)
                self.assertFalse((target / descriptor["name"]).exists())

    def test_restore_marks_already_running_verified_version_installed(self):
        payload = _fake_pe_bytes(8192)
        descriptor = self._descriptor(
            "https://github.com/fhy-A/Code/releases/download/v0.6.7/Code-v0.6.7.exe",
            payload,
        )
        identity = {"version": "0.6.7", "originalFilename": descriptor["name"], "productName": "Code"}
        with tempfile.TemporaryDirectory() as temp_dir, \
             mock.patch.object(server, "_read_windows_file_identity", return_value=identity), \
             mock.patch.object(server, "_read_version_file", return_value="0.6.7"):
            target = Path(temp_dir)
            (target / descriptor["name"]).write_bytes(payload)
            metadata = {
                "schema": server._UPDATE_JOB_SCHEMA,
                "jobId": str(uuid.uuid4()),
                "descriptor": descriptor,
                "status": "completed",
                "stage": "completed",
                "progress": 100,
                "downloaded": len(payload),
                "etag": '"fixture-etag"',
                "errorCode": "",
                "retryable": False,
                "updatedAt": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
            }
            server._atomic_write_update_metadata(server._update_metadata_path(target, descriptor), metadata)
            restored = server._restore_update_jobs(target, trusted_descriptor=descriptor, start_workers=False)
            self.assertEqual(restored[0]["status"], "installed")
            persisted = json.loads(server._update_metadata_path(target, descriptor).read_text(encoding="utf-8"))
            self.assertEqual(persisted["status"], "installed")

    def test_arbitrary_url_or_path_is_rejected_before_trusted_lookup(self):
        handler = object.__new__(server.CodeHandler)
        handler.send_json = mock.Mock()
        with mock.patch.object(server, "_get_trusted_update_descriptor") as trusted:
            handler._handle_download_update({"url": "https://evil.invalid/Code-v0.6.7.exe"})
            trusted.assert_not_called()
        self.assertEqual(handler.send_json.call_args.args[1], 400)
        self.assertEqual(handler.send_json.call_args.args[0]["errorCode"], "invalid_update_request")

        handler.send_json.reset_mock()
        with mock.patch.object(server, "_get_trusted_update_descriptor") as trusted:
            handler._handle_download_update({"path": r"C:\\Users\\Alice\\malware.exe"})
            trusted.assert_not_called()
        self.assertNotIn("Alice", json.dumps(handler.send_json.call_args.args[0]))

        handler.read_body_json = mock.Mock(return_value={"path": r"C:\\Users\\Alice\\malware.exe"})
        handler.send_json.reset_mock()
        with mock.patch.object(server.sys, "frozen", True, create=True):
            handler._handle_restart()
        self.assertEqual(handler.send_json.call_args.args[0]["errorCode"], "invalid_update_request")
        self.assertNotIn("Alice", json.dumps(handler.send_json.call_args.args[0]))

    def test_public_failure_is_sanitized_and_omits_paths_urls_and_digest(self):
        payload = _fake_pe_bytes(8192)
        with tempfile.TemporaryDirectory() as temp_dir, self._allow_local_descriptor(), \
             mock.patch.object(server, "_UPDATE_RETRY_DELAYS", (0, 0)), \
             mock.patch.object(
                 server.request,
                 "urlopen",
                 side_effect=OSError(r"C:\\Users\\Alice\\secret.part ?token=secret"),
             ):
            descriptor = self._descriptor("http://127.0.0.1:1/Code-v0.6.7.exe?token=secret", payload)
            started = server._start_or_attach_update_job(descriptor, target_dir=Path(temp_dir))
            result = self._wait_for_terminal(started["jobId"])
        serialized = json.dumps(result)
        self.assertEqual(result["errorCode"], "download_interrupted")
        self.assertNotIn("token", serialized)
        self.assertNotIn("secret", serialized)
        self.assertNotIn(temp_dir, serialized)
        self.assertNotIn("url", result)
        self.assertNotIn("digest", result)

    def test_size_mismatch_and_hardlinked_part_fail_before_publish(self):
        payload = _fake_pe_bytes(8192)
        descriptor = self._descriptor(
            "https://github.com/fhy-A/Code/releases/download/v0.6.7/Code-v0.6.7.exe",
            payload,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir)
            part = target / f"{descriptor['name']}.part"
            part.write_bytes(payload[:-1])
            with self.assertRaises(server._UpdateFailure) as size_error:
                server._validate_completed_update_file(part, descriptor, target, partial=True)
            self.assertEqual(size_error.exception.code, "download_size_mismatch")

            part.unlink()
            source = target / "source.bin"
            source.write_bytes(payload)
            os.link(source, part)
            with self.assertRaises(server._UpdateFailure) as link_error:
                server._validate_safe_update_file(
                    part, target, allowed_names={part.name}, required=True,
                )
            self.assertEqual(link_error.exception.code, "unsafe_update_path")

    def test_legacy_url_must_exactly_match_trusted_descriptor(self):
        payload = _fake_pe_bytes(8192)
        descriptor = self._descriptor(
            "https://github.com/fhy-A/Code/releases/download/v0.6.7/Code-v0.6.7.exe",
            payload,
        )
        handler = object.__new__(server.CodeHandler)
        handler.send_json = mock.Mock()
        attached = {
            "jobId": "job-1", "downloadId": "job-1", "version": "0.6.7",
            "name": descriptor["name"], "status": "downloading", "stage": "downloading",
            "progress": 1, "downloaded": 1, "total": len(payload), "done": False,
            "errorCode": None, "error": None, "retryable": False,
        }
        with mock.patch.object(server, "_get_trusted_update_descriptor", return_value=descriptor), \
             mock.patch.object(server, "_start_or_attach_update_job", return_value=attached) as start:
            handler._handle_download_update({"url": descriptor["url"]})
        start.assert_called_once_with(descriptor, retry=False)
        self.assertEqual(handler.send_json.call_args.args[0]["jobId"], "job-1")

        handler.send_json.reset_mock()
        with mock.patch.object(server, "_get_trusted_update_descriptor", return_value=descriptor), \
             mock.patch.object(server, "_start_or_attach_update_job") as start:
            handler._handle_download_update({
                "url": "https://github.com/fhy-A/Code/releases/download/v0.6.8/Code-v0.6.8.exe",
            })
        start.assert_not_called()
        self.assertEqual(handler.send_json.call_args.args[0]["errorCode"], "invalid_update_request")

    def test_repeated_restart_of_verified_job_launches_installer_once(self):
        payload = _fake_pe_bytes(8192)
        identity = {"version": "0.6.7", "originalFilename": "Code-v0.6.7.exe", "productName": "Code"}
        with _update_http_fixture(payload, ["normal"]) as (url, _fixture):
            descriptor = self._descriptor(url, payload)
            with tempfile.TemporaryDirectory() as temp_dir, self._allow_local_descriptor(), \
                 mock.patch.object(server, "_read_windows_file_identity", return_value=identity):
                started = server._start_or_attach_update_job(descriptor, target_dir=Path(temp_dir))
                completed = self._wait_for_terminal(started["jobId"])
                self.assertEqual(completed["status"], "completed")
                handler = object.__new__(server.CodeHandler)
                handler.read_body_json = mock.Mock(return_value={"jobId": completed["jobId"]})
                handler.send_json = mock.Mock()
                with mock.patch.object(server.sys, "frozen", True, create=True), \
                     mock.patch.object(server, "_build_update_script", return_value=Path(temp_dir) / "update.bat"), \
                     mock.patch.object(server.subprocess, "Popen") as popen, \
                     mock.patch.object(server.os, "_exit") as exit_process:
                    handler._handle_restart()
                    handler._handle_restart()
                self.assertEqual(popen.call_count, 1)
                self.assertEqual(exit_process.call_count, 1)
                self.assertEqual(server._current_update_snapshot(completed["jobId"])["status"], "installing")

    def test_remote_version_selects_matching_code_asset(self):
        download_url = "https://github.com/fhy-A/Code/releases/download/v0.5.4/Code-v0.5.4.exe"
        payload = {
            "tag_name": "v0.5.4",
            "assets": [
                {"name": "helper.exe", "browser_download_url": "https://example.test/helper.exe"},
                {
                    "name": "Code-v0.5.4.exe",
                    "browser_download_url": download_url,
                    "size": 1234,
                    "digest": "sha256:" + ("a" * 64),
                },
            ],
        }
        response = mock.Mock()
        response.read.return_value = json.dumps(payload).encode("utf-8")
        with mock.patch.object(server.request, "urlopen", return_value=response):
            version, url = server._read_remote_version()
        self.assertEqual(version, "0.5.4")
        self.assertEqual(url, download_url)

    def test_remote_version_rejects_asset_without_size_or_digest(self):
        payload = {
            "tag_name": "v0.5.4",
            "assets": [{
                "name": "Code-v0.5.4.exe",
                "browser_download_url": "https://github.com/fhy-A/Code/releases/download/v0.5.4/Code-v0.5.4.exe",
                "size": 1234,
            }],
        }
        response = mock.Mock()
        response.read.return_value = json.dumps(payload).encode("utf-8")
        with mock.patch.object(server.request, "urlopen", return_value=response):
            self.assertIsNone(server._read_remote_update())

    def test_valid_windows_executable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            exe = Path(temp_dir) / "Code-v1.2.3.exe"
            exe.write_bytes(_fake_pe_bytes())
            self.assertTrue(server._is_valid_windows_executable(exe))

    def test_rejects_incomplete_or_non_pe_download(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            bad = Path(temp_dir) / "Code-v1.2.3.exe.part"
            bad.write_text("<html>download failed</html>", encoding="utf-8")
            self.assertFalse(server._is_valid_windows_executable(bad))

    def test_update_script_keeps_new_version_and_removes_old_ones(self):
        target_dir = Path(r"C:\Code")
        new_exe = target_dir / "Code-v1.2.3.exe"
        partial_exe = target_dir / "Code-v1.2.3.exe.part"
        log_path = target_dir / "update.log"
        bat_path = server._build_update_script(target_dir, new_exe, partial_exe, log_path)
        script = Path(bat_path).read_text(encoding="utf-8")
        # Batch-file updater — uses findstr to match versioned Code-v*.exe processes
        self.assertIn("findstr /i Code-", script)
        self.assertIn("taskkill", script)
        self.assertIn("move /y", script)
        self.assertIn("del /f", script)
        self.assertIn('start "" "', script)
        self.assertIn("--reuse-browser", script)

    def test_update_script_findstr_matches_versioned_process(self):
        """The batch updater must find versioned names like Code-v0.5.24.exe."""
        target_dir = Path(r"C:\Code")
        new_exe = target_dir / "Code-v2.0.0.exe"
        bat_path = server._build_update_script(target_dir, new_exe, None, target_dir / "update.log")
        script = Path(bat_path).read_text(encoding="utf-8")
        # findstr /i Code- catches "Code-v0.5.24.exe", "Code-v1.0.0.exe", etc.
        self.assertIn("findstr /i Code-", script)
        # Must NOT use the old exact-match filter that only caught "Code.exe"
        self.assertNotIn("IMAGENAME eq Code.exe", script)

    def test_check_update_detects_newer_release(self):
        handler = object.__new__(server.CodeHandler)
        download_url = "https://github.com/fhy-A/Code/releases/download/v0.4.11/Code-v0.4.11.exe"
        descriptor = {
            "version": "0.4.11", "name": "Code-v0.4.11.exe", "url": download_url,
            "size": 1234, "digest": "a" * 64,
        }
        with mock.patch.object(server, "_read_version_file", return_value="0.4.10"), \
             mock.patch.object(server, "_get_trusted_update_descriptor", return_value=descriptor):
            result = handler._check_update()
        self.assertTrue(result["updateAvailable"])
        self.assertEqual(result["remoteVersion"], "0.4.11")
        self.assertTrue(result["downloadUrl"].endswith("/v0.4.11/Code-v0.4.11.exe"))

    def test_frontend_waits_for_new_version_before_cache_busting_reload(self):
        settings_js = (
            Path(__file__).resolve().parent.parent / "src" / "features" / "settings.js"
        ).read_text(encoding="utf-8")
        self.assertIn('versionInfo.localVersion !== remoteVersion) return;', settings_js)
        self.assertIn('cache: "no-store"', settings_js)
        self.assertIn(
            'refreshed.searchParams.set("updated", `${remoteVersion}-${Date.now()}`)',
            settings_js,
        )
        self.assertIn("global.location.replace(refreshed.toString())", settings_js)


class TestWorkbarAuthentication(unittest.TestCase):
    def make_handler(self, body):
        handler = object.__new__(server.CodeHandler)
        handler.read_body_json = mock.Mock(return_value=body)
        handler.send_json = mock.Mock()
        return handler

    def test_validate_code_auth_uses_fixed_workbar_endpoint(self):
        handler = self.make_handler({"token": "test-access-token", "userId": "42"})
        account_response = mock.MagicMock()
        account_response.read.return_value = json.dumps({
            "success": True,
            "data": {
                "id": 42,
                "username": "alice",
                "display_name": "Alice",
                "email": "alice@example.com",
                "group": "default",
                "quota": 123,
                "used_quota": 45,
                "request_count": 67,
            },
        }).encode("utf-8")
        account_response.__enter__.return_value = account_response
        status_response = mock.MagicMock()
        status_response.read.return_value = json.dumps({
            "success": True,
            "data": {
                "quota_per_unit": 500000,
                "quota_display_type": "CNY",
                "usd_exchange_rate": 7.2,
                "custom_currency_symbol": "",
                "custom_currency_exchange_rate": 1,
            },
        }).encode("utf-8")
        status_response.__enter__.return_value = status_response

        with mock.patch.object(server.request, "urlopen", side_effect=[account_response, status_response]) as urlopen:
            handler._handle_validate_code_auth()

        upstream = urlopen.call_args_list[0].args[0]
        self.assertEqual(upstream.full_url, "https://workbar.ai/api/user/self")
        self.assertEqual(upstream.get_header("Authorization"), "test-access-token")
        self.assertEqual(upstream.get_header("New-api-user"), "42")
        self.assertEqual(urlopen.call_args_list[1].args[0].full_url, "https://workbar.ai/api/status")
        handler.send_json.assert_called_once_with({
            "valid": True,
            "account": {
                "userId": "42",
                "username": "alice",
                "displayName": "Alice",
                "email": "alice@example.com",
                "group": "default",
                "quota": 123,
                "usedQuota": 45,
                "requestCount": 67,
                "quotaDisplay": {
                    "quotaPerUnit": 500000,
                    "type": "CNY",
                    "usdExchangeRate": 7.2,
                    "customCurrencySymbol": "",
                    "customCurrencyExchangeRate": 1,
                },
            },
        })

    def test_validate_code_auth_only_returns_allowlisted_account_fields(self):
        handler = self.make_handler({"token": "test-access-token", "userId": "42"})
        response = mock.MagicMock()
        response.read.return_value = json.dumps({
            "success": True,
            "data": {
                "id": 42,
                "username": "alice",
                "access_token": "must-not-leak",
                "stripe_customer": "cus_private",
                "permissions": {"admin": True},
            },
        }).encode("utf-8")
        response.__enter__.return_value = response

        with mock.patch.object(server.request, "urlopen", side_effect=[response, server.error.URLError("offline")]):
            handler._handle_validate_code_auth()

        result = handler.send_json.call_args.args[0]["account"]
        self.assertEqual(set(result), {
            "userId", "username", "displayName", "email", "group",
            "quota", "usedQuota", "requestCount", "quotaDisplay",
        })
        self.assertNotIn("must-not-leak", json.dumps(result))

    def test_validate_code_auth_rejects_invalid_or_mismatched_account(self):
        for payload in (
            {"success": False, "message": "invalid"},
            {"success": True, "data": {"id": 99, "username": "other"}},
        ):
            with self.subTest(payload=payload):
                handler = self.make_handler({"token": "test-access-token", "userId": "42"})
                response = mock.MagicMock()
                response.read.return_value = json.dumps(payload).encode("utf-8")
                response.__enter__.return_value = response
                with mock.patch.object(server.request, "urlopen", return_value=response):
                    handler._handle_validate_code_auth()
                self.assertEqual(handler.send_json.call_args.args[1], 401)

    def test_validate_code_auth_keeps_outage_separate_from_expiry(self):
        handler = self.make_handler({"token": "test-access-token", "userId": "42"})
        with mock.patch.object(server.request, "urlopen", side_effect=server.error.URLError("offline")):
            handler._handle_validate_code_auth()
        handler.send_json.assert_called_once_with({"error": "workbar is unavailable"}, 502)

    def test_sync_keys_uses_fixed_workbar_endpoint_and_normalizes_prefix(self):
        handler = self.make_handler({
            "token": "test-access-token",
            "userId": "42",
            "platformUrl": "https://untrusted.example",
        })
        token_response = mock.MagicMock()
        token_response.read.return_value = json.dumps({
            "data": {"items": [
                {"id": 7, "name": "first", "status": 1},
                {"id": 8, "name": "second", "status": 2},
                {"id": 9, "name": "masked", "status": 1},
            ]},
        }).encode("utf-8")
        token_response.__enter__.return_value = token_response
        key_response = mock.MagicMock()
        key_response.read.return_value = json.dumps({
            "data": {"keys": {"7": "full-value", "8": "sk-ready", "9": "sk-***mask"}},
        }).encode("utf-8")
        key_response.__enter__.return_value = key_response

        with mock.patch.object(
            server.request,
            "urlopen",
            side_effect=[token_response, key_response],
        ) as urlopen:
            handler._handle_sync_keys()

        requests = [call.args[0] for call in urlopen.call_args_list]
        self.assertEqual(requests[0].full_url, "https://workbar.ai/api/token/?p=0&size=100")
        self.assertEqual(requests[1].full_url, "https://workbar.ai/api/token/batch/keys")
        self.assertEqual(requests[1].get_method(), "POST")
        payload = handler.send_json.call_args.args[0]
        self.assertEqual(payload["keys"], {"7": "sk-full-value", "8": "sk-ready"})

    def test_sync_keys_preserves_local_auth_on_workbar_outage(self):
        handler = self.make_handler({"token": "test-access-token", "userId": "42"})
        with mock.patch.object(server.request, "urlopen", side_effect=server.error.URLError("offline")):
            handler._handle_sync_keys()
        handler.send_json.assert_called_once_with({
            "error": "workbar_sync_failed",
            "stage": "list_tokens",
            "kind": "network",
            "page": 0,
        }, 502)

    def test_sync_keys_reports_secret_free_stage_and_upstream_status(self):
        handler = self.make_handler({"token": "must-not-leak", "userId": "42"})
        upstream_error = server.error.HTTPError(
            "https://workbar.ai/api/token/?p=0&size=100",
            503,
            "secret upstream details",
            None,
            None,
        )
        with mock.patch.object(server.request, "urlopen", side_effect=upstream_error):
            handler._handle_sync_keys()

        payload, status = handler.send_json.call_args.args
        self.assertEqual(status, 502)
        self.assertEqual(payload, {
            "error": "workbar_sync_failed",
            "stage": "list_tokens",
            "kind": "http",
            "upstreamStatus": 503,
            "page": 0,
        })
        public_text = json.dumps(payload)
        self.assertNotIn("must-not-leak", public_text)
        self.assertNotIn("secret upstream details", public_text)

    def test_sync_keys_distinguishes_timeout_and_invalid_key_batch(self):
        timeout_handler = self.make_handler({
            "token": "test-access-token",
            "userId": "42",
        })
        with mock.patch.object(
            server.request, "urlopen", side_effect=TimeoutError("timed out"),
        ):
            timeout_handler._handle_sync_keys()
        timeout_handler.send_json.assert_called_once_with({
            "error": "workbar_sync_failed",
            "stage": "list_tokens",
            "kind": "timeout",
            "page": 0,
        }, 502)

        token_response = mock.MagicMock()
        token_response.read.return_value = json.dumps({
            "data": {"items": [{"id": 7, "name": "first"}]},
        }).encode("utf-8")
        token_response.__enter__.return_value = token_response
        invalid_response = mock.MagicMock()
        invalid_response.read.return_value = b"<html>private upstream error</html>"
        invalid_response.__enter__.return_value = invalid_response
        invalid_handler = self.make_handler({
            "token": "test-access-token",
            "userId": "42",
        })
        with mock.patch.object(
            server.request,
            "urlopen",
            side_effect=[token_response, invalid_response],
        ):
            invalid_handler._handle_sync_keys()
        invalid_handler.send_json.assert_called_once_with({
            "error": "workbar_sync_failed",
            "stage": "read_keys",
            "kind": "invalid_response",
            "batch": 1,
        }, 502)

    def test_sync_keys_keeps_authentication_failures_as_unauthorized(self):
        handler = self.make_handler({"token": "expired", "userId": "42"})
        upstream_error = server.error.HTTPError(
            "https://workbar.ai/api/token/?p=0&size=100",
            401,
            "unauthorized",
            None,
            None,
        )
        with mock.patch.object(server.request, "urlopen", side_effect=upstream_error):
            handler._handle_sync_keys()
        handler.send_json.assert_called_once_with({
            "error": "Platform authorization is invalid",
        }, 401)

    def test_sync_keys_paginates_and_batches_all_platform_keys(self):
        handler = self.make_handler({"token": "test-access-token", "userId": "42"})

        def response(payload):
            result = mock.MagicMock()
            result.read.return_value = json.dumps(payload).encode("utf-8")
            result.__enter__.return_value = result
            return result

        first_page = [{"id": key_id, "name": f"key-{key_id}", "status": 1} for key_id in range(1, 101)]
        second_page = [{"id": 101, "name": "key-101", "status": 1}]
        side_effects = [
            response({"data": {"items": first_page, "total": 101}}),
            response({"data": {"items": second_page, "total": 101}}),
            response({"data": {"keys": {str(key_id): f"value-{key_id}" for key_id in range(1, 101)}}}),
            response({"data": {"keys": {"101": "value-101"}}}),
        ]
        with mock.patch.object(server.request, "urlopen", side_effect=side_effects) as urlopen:
            handler._handle_sync_keys()

        requests = [call.args[0] for call in urlopen.call_args_list]
        self.assertEqual(requests[0].full_url, "https://workbar.ai/api/token/?p=0&size=100")
        self.assertEqual(requests[1].full_url, "https://workbar.ai/api/token/?p=1&size=100")
        self.assertEqual(json.loads(requests[2].data)["ids"], list(range(1, 101)))
        self.assertEqual(json.loads(requests[3].data)["ids"], [101])
        payload = handler.send_json.call_args.args[0]
        self.assertEqual(len(payload["tokens"]), 101)
        self.assertEqual(payload["keys"]["101"], "sk-value-101")


class TestTrayRestart(unittest.TestCase):
    def test_instance_settings_keep_packaged_release_on_port_3010(self):
        self.assertEqual(
            server._resolve_instance_settings({}, frozen=False),
            (3010, "release"),
        )
        self.assertEqual(
            server._resolve_instance_settings({
                "CODE_PORT": "3011",
                "CODE_INSTANCE_MODE": "dev",
            }, frozen=False),
            (3011, "dev"),
        )
        self.assertEqual(
            server._resolve_instance_settings({
                "CODE_PORT": "3011",
                "CODE_INSTANCE_MODE": "dev",
            }, frozen=True),
            (3010, "release"),
        )

    def test_instance_labels_distinguish_dev_without_changing_release(self):
        self.assertEqual(server._instance_labels(3010, "release"), {
            "product": "Code",
            "trayTitle": "Code",
            "open": "Open Code",
            "restart": "Restart Code",
            "exit": "Exit",
        })
        self.assertEqual(server._instance_labels(3011, "dev"), {
            "product": "Code Dev",
            "trayTitle": "Code Dev · 3011",
            "open": "Open Code Dev",
            "restart": "Restart Code Dev",
            "exit": "Exit Code Dev",
        })

    def test_source_restart_closes_server_and_relaunches_server_script(self):
        server_ref = mock.Mock()
        icon = mock.Mock()
        with mock.patch.object(server.subprocess, "Popen") as popen:
            server._restart_code_process(server_ref, icon)

        powershell = popen.call_args.args[0]
        self.assertEqual(powershell[:3], [
            "powershell", "-NoProfile", "-NonInteractive",
        ])
        encoded = powershell[powershell.index("-EncodedCommand") + 1]
        script = base64.b64decode(encoded).decode("utf-16-le")
        self.assertIn(f"Wait-Process -Id {os.getpid()}", script)
        self.assertIn(str((server.APP_DIR / "server.py").resolve()), script)
        server_ref.shutdown.assert_called_once_with()
        server_ref.server_close.assert_called_once_with()
        icon.stop.assert_called_once_with()

    def test_source_restart_uses_configured_dev_entry(self):
        server_ref = mock.Mock()
        icon = mock.Mock()
        with mock.patch.dict(
            server.os.environ,
            {"CODE_RESTART_ENTRY": "dev_server.py"},
        ), mock.patch.object(server.subprocess, "Popen") as popen:
            server._restart_code_process(server_ref, icon)

        powershell = popen.call_args.args[0]
        encoded = powershell[powershell.index("-EncodedCommand") + 1]
        script = base64.b64decode(encoded).decode("utf-16-le")
        self.assertIn(str((server.APP_DIR / "dev_server.py").resolve()), script)
        self.assertNotIn(str((server.APP_DIR / "server.py").resolve()), script)

    def test_source_restart_rejects_entry_outside_code_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            outside = Path(temp_dir) / "dev_server.py"
            outside.write_text("", encoding="utf-8")
            with mock.patch.dict(
                server.os.environ,
                {"CODE_RESTART_ENTRY": str(outside)},
            ):
                with self.assertRaisesRegex(
                    ValueError,
                    "must stay inside the Code directory",
                ):
                    server._restart_code_process()

    def test_source_restart_rejects_non_python_entry(self):
        with mock.patch.dict(
            server.os.environ,
            {"CODE_RESTART_ENTRY": "dev_server.bat"},
        ):
            with self.assertRaisesRegex(ValueError, "Invalid Code restart entry"):
                server._restart_code_process()

    def test_tray_menu_exposes_restart_action(self):
        source = Path(server.__file__).read_text(encoding="utf-8")
        self.assertIn('pystray.MenuItem(labels["restart"], on_restart)', source)

    def test_restart_cancels_waiter_if_current_server_cannot_stop(self):
        server_ref = mock.Mock()
        server_ref.shutdown.side_effect = RuntimeError("cannot stop")
        icon = mock.Mock()
        waiter = mock.Mock()
        with mock.patch.object(server.subprocess, "Popen", return_value=waiter):
            with self.assertRaisesRegex(RuntimeError, "cannot stop"):
                server._restart_code_process(server_ref, icon)
        waiter.terminate.assert_called_once_with()
        icon.stop.assert_not_called()


class TestSanitizeFilename(unittest.TestCase):
    def test_normal_name(self):
        self.assertEqual(server.sanitize_filename("hello.txt"), "hello.txt")

    def test_strips_path_separators(self):
        # Path().name extracts only the last component
        result = server.sanitize_filename(r"foo\bar/baz.txt")
        self.assertEqual(result, "baz.txt")

    def test_replaces_angle_brackets(self):
        self.assertEqual(server.sanitize_filename("<evil>.txt"), "_evil_.txt")

    def test_replaces_colon(self):
        # Path().name strips the drive letter prefix (C:)
        self.assertEqual(server.sanitize_filename("C:file.txt"), "file.txt")

    def test_replaces_quote_and_pipe(self):
        self.assertEqual(server.sanitize_filename('a"b|c.txt'), "a_b_c.txt")

    def test_replaces_question_mark(self):
        self.assertEqual(server.sanitize_filename("what?.txt"), "what_.txt")

    def test_replaces_asterisk(self):
        self.assertEqual(server.sanitize_filename("*.txt"), "_.txt")

    def test_truncates_long_name(self):
        long_name = "x" * 200 + ".txt"
        result = server.sanitize_filename(long_name)
        self.assertEqual(len(result), 120)
        # Truncation at 120 chars cuts the extension; only verify length

    def test_empty_returns_attachment(self):
        self.assertEqual(server.sanitize_filename(""), "attachment")

    def test_none_returns_attachment(self):
        self.assertEqual(server.sanitize_filename(None), "attachment")

    def test_whitespace_only(self):
        self.assertEqual(server.sanitize_filename("   "), "attachment")


class TestSafeMemoryName(unittest.TestCase):
    def test_valid_simple(self):
        self.assertEqual(server.safe_memory_name("my-config_v2"), "my-config_v2")

    def test_valid_only_letters(self):
        self.assertEqual(server.safe_memory_name("abcdef"), "abcdef")

    def test_valid_max_length(self):
        self.assertEqual(server.safe_memory_name("a" * 64), "a" * 64)

    def test_invalid_empty(self):
        with self.assertRaisesRegex(ValueError, "invalid memory name"):
            server.safe_memory_name("")

    def test_invalid_none(self):
        with self.assertRaisesRegex(ValueError, "invalid memory name"):
            server.safe_memory_name(None)

    def test_invalid_too_long(self):
        with self.assertRaisesRegex(ValueError, "invalid memory name"):
            server.safe_memory_name("a" * 65)

    def test_invalid_special_chars(self):
        with self.assertRaisesRegex(ValueError, "invalid memory name"):
            server.safe_memory_name("hello world")

    def test_invalid_dot(self):
        with self.assertRaisesRegex(ValueError, "invalid memory name"):
            server.safe_memory_name("file.md")


class TestSafeSessionId(unittest.TestCase):
    def test_valid_min_length(self):
        self.assertEqual(server.safe_session_id("abcd1234"), "abcd1234")

    def test_valid_long(self):
        self.assertEqual(server.safe_session_id("a" * 64), "a" * 64)

    def test_invalid_too_short(self):
        with self.assertRaisesRegex(ValueError, "invalid session id"):
            server.safe_session_id("abc")

    def test_invalid_empty(self):
        with self.assertRaisesRegex(ValueError, "invalid session id"):
            server.safe_session_id("")

    def test_invalid_none(self):
        with self.assertRaisesRegex(ValueError, "invalid session id"):
            server.safe_session_id(None)

    def test_invalid_special_chars(self):
        with self.assertRaisesRegex(ValueError, "invalid session id"):
            server.safe_session_id("session@id!")

    def test_invalid_too_long(self):
        with self.assertRaisesRegex(ValueError, "invalid session id"):
            server.safe_session_id("a" * 65)


class TestIsProbablyText(unittest.TestCase):
    def test_plain_text(self):
        self.assertTrue(server.is_probably_text(b"hello world"))

    def test_json_bytes(self):
        self.assertTrue(server.is_probably_text(b'{"key": "value"}'))

    def test_utf8_encoded(self):
        self.assertTrue(server.is_probably_text("你好世界".encode("utf-8")))

    def test_binary_null_early(self):
        self.assertFalse(server.is_probably_text(b"foo\x00bar"))

    def test_binary_null_at_4095(self):
        data = b"A" * 4095 + b"\x00"
        self.assertFalse(server.is_probably_text(data))

    def test_binary_null_at_4097(self):
        data = b"A" * 4097 + b"\x00"
        self.assertTrue(server.is_probably_text(data))

    def test_empty_bytes(self):
        self.assertTrue(server.is_probably_text(b""))


class TestIsSafeCommand(unittest.TestCase):
    def test_dir_is_safe(self):
        ok, _ = server.is_safe_command("dir")
        self.assertTrue(ok)

    def test_dir_with_path(self):
        ok, _ = server.is_safe_command("dir C:\\Users")
        self.assertTrue(ok)

    def test_git_status(self):
        ok, _ = server.is_safe_command("git status")
        self.assertTrue(ok)

    def test_git_log(self):
        ok, _ = server.is_safe_command("git log --oneline")
        self.assertTrue(ok)

    def test_docker_compose_ps(self):
        ok, _ = server.is_safe_command("docker compose ps")
        self.assertTrue(ok)

    def test_python_m_pytest(self):
        ok, _ = server.is_safe_command("python -m pytest tests/ -v")
        self.assertTrue(ok)

    def test_npm_test(self):
        ok, _ = server.is_safe_command("npm test")
        self.assertTrue(ok)

    def test_empty_is_unsafe(self):
        ok, msg = server.is_safe_command("")
        self.assertFalse(ok)
        self.assertIn("不能为空", msg)

    def test_del_is_blocked(self):
        ok, _ = server.is_safe_command("del file.txt")
        self.assertFalse(ok)

    def test_rm_is_blocked(self):
        ok, _ = server.is_safe_command("rm file.txt")
        self.assertFalse(ok)

    # ── Updated: pipe now allowed ──
    def test_pipe_is_allowed(self):
        ok, _ = server.is_safe_command("dir | findstr test")
        self.assertTrue(ok)

    def test_pipe_git_log(self):
        ok, _ = server.is_safe_command("git log --oneline | head -5")
        self.assertTrue(ok)

    # ── Updated: redirect now allowed ──
    def test_redirect_is_allowed(self):
        ok, _ = server.is_safe_command("dir > output.txt")
        self.assertTrue(ok)

    def test_append_redirect_allowed(self):
        ok, _ = server.is_safe_command("echo line >> log.txt")
        self.assertTrue(ok)

    # ── Semicolon: still blocks when combined with dangerous cmd ──
    def test_semicolon_with_del_still_blocked(self):
        ok, _ = server.is_safe_command("dir; del file.txt")
        self.assertFalse(ok)

    def test_semicolon_in_python_allowed(self):
        ok, _ = server.is_safe_command("python -c \"x=1; y=2; print(x+y)\"")
        self.assertTrue(ok)

    def test_semicolon_in_python_import_allowed(self):
        ok, _ = server.is_safe_command("python -c \"from docx import Document; print('ok')\"")
        self.assertTrue(ok)

    # ── Updated: python -c now allowed ──
    def test_python_c_is_allowed(self):
        ok, _ = server.is_safe_command("python -c 'print(1)'")
        self.assertTrue(ok)

    def test_python_c_multiline_allowed(self):
        ok, _ = server.is_safe_command("python -c \"for i in range(3):\\n print(i)\"")
        self.assertTrue(ok)

    # ── Updated: node -e now allowed ──
    def test_node_e_is_allowed(self):
        ok, _ = server.is_safe_command("node -e 'console.log(1)'")
        self.assertTrue(ok)

    # ── New: file write/create commands allowed ──
    def test_mkdir_allowed(self):
        ok, _ = server.is_safe_command("mkdir newdir")
        self.assertTrue(ok)

    def test_set_content_allowed(self):
        ok, _ = server.is_safe_command("set-content test.txt 'hello'")
        self.assertTrue(ok)

    def test_copy_item_allowed(self):
        ok, _ = server.is_safe_command("copy-item a.txt b.txt")
        self.assertTrue(ok)

    def test_move_item_allowed(self):
        ok, _ = server.is_safe_command("move-item a.txt b.txt")
        self.assertTrue(ok)

    def test_out_file_allowed(self):
        ok, _ = server.is_safe_command("out-file -FilePath out.txt")
        self.assertTrue(ok)

    def test_pip_install_allowed(self):
        ok, _ = server.is_safe_command("pip install requests")
        self.assertTrue(ok)

    def test_dependency_installs_are_classified_by_runtime_ownership(self):
        managed_cases = (
            "pip install requests",
            "python -m pip install requests",
            "python -m venv data/runtime/python",
            "npm install --prefix data/runtime/node lodash",
        )
        for command in managed_cases:
            with self.subTest(command=command):
                self.assertEqual(server.dependency_install_command_kind(command), "managed")
                self.assertTrue(server.command_requires_dependency_authorization(command))
        system_cases = (
            "winget install Poppler.Poppler",
            "choco install pandoc",
            "sudo apt-get install libreoffice",
            "python -c \"import subprocess; subprocess.run(['winget', 'install', 'Pandoc.Pandoc'])\"",
        )
        for command in system_cases:
            with self.subTest(command=command):
                self.assertEqual(server.dependency_install_command_kind(command), "system")
                self.assertFalse(server.command_requires_dependency_authorization(command))
        environment_cases = (
            '$old = [Environment]::GetEnvironmentVariable("Path", "User"); '
            '[Environment]::SetEnvironmentVariable("Path", "$old;C:\\Pandoc", "User")',
            '$p = "$env:APPDATA\\npm\\pandoc.cmd"; Set-Content -Path $p -Value "@echo off"',
            'setx PATH "%PATH%;C:\\Pandoc"',
        )
        for command in environment_cases:
            with self.subTest(command=command):
                self.assertEqual(server.dependency_install_command_kind(command), "environment")
                self.assertFalse(server.command_requires_dependency_authorization(command))
        self.assertFalse(server.command_requires_dependency_authorization("python -m pytest -q"))
        self.assertFalse(server.command_requires_dependency_authorization("npm test"))

    def test_dependency_install_classifier_reads_project_local_wrapper(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            script = root / "install_deps.py"
            script.write_text(
                "import subprocess\nsubprocess.run(['winget', 'install', 'Pandoc.Pandoc'])\n",
                encoding="utf-8",
            )
            kind = server.dependency_install_command_kind(
                "python install_deps.py",
                project_root=root,
            )

        self.assertEqual(kind, "system")

    def test_run_command_blocks_system_package_manager_install(self):
        with mock.patch.object(server.subprocess, "Popen") as popen_mock:
            result = server.execute_run_command_tool({
                "command": "winget install Pandoc.Pandoc",
                "timeout": 300,
            })

        popen_mock.assert_not_called()
        self.assertFalse(result["ok"])
        self.assertTrue(result["blocked"])
        self.assertTrue(result["userCooperationRequired"])
        self.assertEqual(result["dependencyInstallKind"], "system")

    def test_run_command_blocks_persistent_dependency_environment_changes(self):
        command = (
            '$p = "$env:APPDATA\\npm\\pdftoppm.cmd"; '
            'Set-Content -Path $p -Value "@echo off"'
        )
        with mock.patch.object(server.subprocess, "Popen") as popen_mock:
            result = server.execute_run_command_tool({"command": command})

        popen_mock.assert_not_called()
        self.assertFalse(result["ok"])
        self.assertTrue(result["blocked"])
        self.assertTrue(result["userCooperationRequired"])
        self.assertEqual(result["dependencyInstallKind"], "environment")
        self.assertIn("Do not modify PATH", result["error"])

    def test_repeated_command_guard_blocks_the_third_identical_attempt(self):
        run = {
            "tool_executions": {
                "one": {"name": "run_command", "command": "python -m pytest -q"},
                "two": {"name": "run_command", "command": "  PYTHON   -m pytest -q  "},
                "current": {"name": "run_command", "command": "python -m pytest -q"},
            },
        }
        count = server._agent_repeated_command_count(
            run,
            "python -m pytest -q",
            exclude_call_id="current",
        )
        self.assertEqual(count, 2)

    # ── New: expanded whitelist checks ──
    def test_curl_allowed(self):
        ok, _ = server.is_safe_command("curl https://example.com")
        self.assertTrue(ok)

    def test_cat_allowed(self):
        ok, _ = server.is_safe_command("cat file.txt")
        self.assertTrue(ok)

    def test_grep_allowed(self):
        ok, _ = server.is_safe_command("grep pattern file.txt")
        self.assertTrue(ok)

    def test_find_allowed(self):
        ok, _ = server.is_safe_command("find . -name '*.py'")
        self.assertTrue(ok)

    def test_wc_allowed(self):
        ok, _ = server.is_safe_command("wc -l file.txt")
        self.assertTrue(ok)

    def test_head_allowed(self):
        ok, _ = server.is_safe_command("head -10 file.txt")
        self.assertTrue(ok)

    def test_tail_allowed(self):
        ok, _ = server.is_safe_command("tail -20 file.txt")
        self.assertTrue(ok)

    def test_tasklist_allowed(self):
        ok, _ = server.is_safe_command("tasklist")
        self.assertTrue(ok)

    def test_netstat_allowed(self):
        ok, _ = server.is_safe_command("netstat -an")
        self.assertTrue(ok)

    def test_ipconfig_allowed(self):
        ok, _ = server.is_safe_command("ipconfig")
        self.assertTrue(ok)

    def test_ping_allowed(self):
        ok, _ = server.is_safe_command("ping localhost")
        self.assertTrue(ok)

    def test_git_branch_allowed(self):
        ok, _ = server.is_safe_command("git branch -a")
        self.assertTrue(ok)

    def test_git_stash_allowed(self):
        ok, _ = server.is_safe_command("git stash list")
        self.assertTrue(ok)

    def test_git_blame_allowed(self):
        ok, _ = server.is_safe_command("git blame server.py")
        self.assertTrue(ok)

    def test_docker_ps_allowed(self):
        ok, _ = server.is_safe_command("docker ps")
        self.assertTrue(ok)

    def test_get_process_allowed(self):
        ok, _ = server.is_safe_command("get-process")
        self.assertTrue(ok)

    def test_cargo_allowed(self):
        ok, _ = server.is_safe_command("cargo build")
        self.assertTrue(ok)

    def test_go_allowed(self):
        ok, _ = server.is_safe_command("go build ./...")
        self.assertTrue(ok)

    def test_tar_create_allowed(self):
        ok, _ = server.is_safe_command("tar -czf archive.tar.gz dir/")
        self.assertTrue(ok)

    # ── Deletion still blocked ──
    def test_del_is_blocked(self):
        ok, _ = server.is_safe_command("del file.txt")
        self.assertFalse(ok)

    def test_rm_is_blocked(self):
        ok, _ = server.is_safe_command("rm file.txt")
        self.assertFalse(ok)

    def test_rmdir_is_blocked(self):
        ok, _ = server.is_safe_command("rmdir somedir")
        self.assertFalse(ok)

    def test_remove_item_is_blocked(self):
        ok, _ = server.is_safe_command("remove-item file.txt")
        self.assertFalse(ok)

    def test_del_force_is_blocked(self):
        ok, _ = server.is_safe_command("del /f /s C:\\important.txt")
        self.assertFalse(ok)

    # ── System destruction still blocked ──
    def test_format_is_blocked(self):
        ok, _ = server.is_safe_command("format C:")
        self.assertFalse(ok)

    def test_shutdown_is_blocked(self):
        ok, _ = server.is_safe_command("shutdown /s")
        self.assertFalse(ok)

    def test_reg_is_blocked(self):
        ok, _ = server.is_safe_command("reg delete HKLM\\something")
        self.assertFalse(ok)

    def test_net_user_is_blocked(self):
        ok, _ = server.is_safe_command("net user admin password")
        self.assertFalse(ok)

    def test_net_start_is_blocked(self):
        ok, _ = server.is_safe_command("net start wuauserv")
        self.assertFalse(ok)

    def test_sc_is_blocked(self):
        ok, _ = server.is_safe_command("sc stop service")
        self.assertFalse(ok)

    def test_stop_process_is_blocked(self):
        ok, _ = server.is_safe_command("stop-process -Name chrome")
        self.assertFalse(ok)

    # ── Command chaining / escape still blocked ──
    def test_ampersand_chaining_blocked(self):
        ok, _ = server.is_safe_command("dir & del file.txt")
        self.assertFalse(ok)

    def test_backtick_escape_blocked(self):
        ok, _ = server.is_safe_command("dir `; del file.txt")
        self.assertFalse(ok)

    # ── Still unknown / edge cases ──
    def test_empty_is_unsafe(self):
        ok, msg = server.is_safe_command("")
        self.assertFalse(ok)
        self.assertIn("不能为空", msg)

    def test_unknown_prefix_is_unsafe(self):
        ok, _ = server.is_safe_command("sudo rm -rf /")
        self.assertFalse(ok)

    def test_findstr_is_safe(self):
        ok, _ = server.is_safe_command("findstr /n test server.py")
        self.assertTrue(ok)

    def test_get_childitem_is_safe(self):
        ok, _ = server.is_safe_command("Get-ChildItem . -Recurse")
        self.assertTrue(ok)

    def test_npx_is_safe(self):
        ok, _ = server.is_safe_command("npx jest")
        self.assertTrue(ok)


class TestParseMemoryFrontmatter(unittest.TestCase):
    def test_with_frontmatter(self):
        text = "---\nname: test-memory\ndescription: A test\n---\n\nThis is the body."
        meta, body = server.parse_memory_frontmatter(text)
        self.assertEqual(meta, {"name": "test-memory", "description": "A test"})
        self.assertEqual(body, "This is the body.")

    def test_no_frontmatter(self):
        text = "Just a plain body without frontmatter."
        meta, body = server.parse_memory_frontmatter(text)
        self.assertEqual(meta, {})
        self.assertEqual(body, text)

    def test_empty_frontmatter(self):
        # Adjacent --- with nothing between doesn't match the regex
        text = "---\n---\n\nBody here."
        meta, body = server.parse_memory_frontmatter(text)
        self.assertEqual(meta, {})
        self.assertEqual(body, text)

    def test_frontmatter_no_trailing_newline(self):
        text = "---\nkey: value\n---\nBody"
        meta, body = server.parse_memory_frontmatter(text)
        self.assertEqual(meta, {"key": "value"})
        self.assertEqual(body, "Body")

    def test_frontmatter_multiline_body(self):
        text = "---\ntitle: Multi\n---\n\nLine 1\nLine 2\n\nLine 3"
        meta, body = server.parse_memory_frontmatter(text)
        self.assertEqual(meta, {"title": "Multi"})
        self.assertIn("Line 1", body)
        self.assertIn("Line 3", body)

    def test_looks_like_frontmatter_but_not_at_start(self):
        text = "Some text\n---\nkey: value\n---\nBody"
        meta, body = server.parse_memory_frontmatter(text)
        self.assertEqual(meta, {})
        self.assertEqual(body, text)


class TestBuildMemoryFile(unittest.TestCase):
    def test_basic(self):
        result = server.build_memory_file(
            {"name": "test", "description": "A test memory"},
            "This is the body content."
        )
        expected = (
            "---\n"
            "name: test\n"
            "description: A test memory\n"
            "---\n"
            "\n"
            "This is the body content."
        )
        self.assertEqual(result, expected)

    def test_empty_meta(self):
        result = server.build_memory_file({}, "body")
        self.assertEqual(result, "---\n---\n\nbody")

    def test_empty_body(self):
        result = server.build_memory_file({"key": "val"}, "")
        self.assertEqual(result, "---\nkey: val\n---\n\n")

    def test_roundtrip(self):
        meta = {"name": "rt", "description": "roundtrip test", "type": "note"}
        body = "Line 1\nLine 2"
        built = server.build_memory_file(meta, body)
        parsed_meta, parsed_body = server.parse_memory_frontmatter(built)
        self.assertEqual(parsed_meta, meta)
        self.assertEqual(parsed_body, body)


class TestMakeUnifiedDiff(unittest.TestCase):
    def test_no_change(self):
        diff = server.make_unified_diff("abc", "abc", "file.txt")
        self.assertEqual(diff, "")

    def test_add_line(self):
        diff = server.make_unified_diff("line1\n", "line1\nline2\n", "test.txt")
        self.assertIn("+++ b/test.txt", diff)
        self.assertIn("+line2", diff)

    def test_remove_line(self):
        diff = server.make_unified_diff("line1\nline2\n", "line1\n", "test.txt")
        self.assertIn("--- a/test.txt", diff)
        self.assertIn("-line2", diff)

    def test_modify_line(self):
        diff = server.make_unified_diff("old\n", "new\n", "test.txt")
        self.assertIn("-old", diff)
        self.assertIn("+new", diff)

    def test_ignores_line_ending_style(self):
        diff = server.make_unified_diff("line1\r\nline2\r\n", "line1\nline2\n", "test.txt")
        self.assertEqual(diff, "")

    def test_ignores_final_newline_only(self):
        diff = server.make_unified_diff("line1", "line1\n", "test.txt")
        self.assertEqual(diff, "")

    def test_normalizes_accidentally_doubled_windows_newlines(self):
        source = "line1\r\r\nline2\r\r\n"
        self.assertEqual(server.normalize_text_newlines(source), "line1\nline2\n")

    def test_fuzzy_edit_remains_actionable_after_newline_normalization(self):
        old = server.normalize_text_newlines(
            'def greet(name):\r\r\n    return "Hello " + name\r\r\n\r\r\n'
            'def farewell(name):\r\r\n    return "Goodbye " + name\r\r\n'
        )
        old_fragment = 'def greet(name):\n    return "Hello " + name\n\ndef farewell(name):\n    return "Goodbye " + name'
        new_fragment = 'def greet(name):\n    return f"Hello {name}"\n\ndef farewell(name):\n    return f"Goodbye {name}"'
        found = server.CodeHandler._fuzzy_find(None, old, old_fragment)
        self.assertEqual(found, old_fragment)
        updated = old.replace(found, new_fragment, 1)
        diff = server.make_unified_diff(old, updated, "test_utils.py")
        self.assertIn('+    return f"Hello {name}"', diff)
        self.assertIn('+    return f"Goodbye {name}"', diff)


class TestNowIso(unittest.TestCase):
    def test_returns_string(self):
        self.assertIsInstance(server.now_iso(), str)

    def test_valid_iso_format(self):
        result = server.now_iso()
        self.assertIsNotNone(
            re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$", result),
            f"Expected ISO 8601 format, got: {result}"
        )


class TestToProjectRelative(unittest.TestCase):
    def test_posix_path(self):
        root = Path("/home/user/project")
        target = Path("/home/user/project/sub/dir/file.py")
        result = server.to_project_relative(root, target)
        self.assertEqual(result, "sub/dir/file.py")

    def test_same_directory(self):
        root = Path("/project")
        target = Path("/project")
        result = server.to_project_relative(root, target)
        self.assertEqual(result, ".")


# ─── 2026-07-07: security / performance regression tests ───

class TestSubprocessKwargs(unittest.TestCase):
    """Verify DETACHED_PROCESS is no longer used (breaks stdout capture)."""
    def test_no_detached_process_flag(self):
        kwargs = server._hidden_subprocess_kwargs()
        if not kwargs:  # non-Windows
            self.assertTrue(True)
            return
        flags = kwargs["creationflags"]
        DETACHED = 0x00000008
        CREATE_NO_WINDOW = 0x08000000
        self.assertEqual(flags, CREATE_NO_WINDOW,
                         f"DETACHED_PROCESS flag present! Got 0x{flags:08x}, expected 0x{CREATE_NO_WINDOW:08x}")
        self.assertFalse(flags & DETACHED,
                         f"DETACHED_PROCESS must not be set, got 0x{flags:08x}")


class TestSkipDirs(unittest.TestCase):
    """Verify expanded SKIP_DIRS covers common large directories."""
    def test_appdata_skipped(self):
        self.assertIn("AppData", server.SKIP_DIRS)

    def test_vscode_skipped(self):
        self.assertIn(".vscode", server.SKIP_DIRS)

    def test_node_modules_skipped(self):
        self.assertIn("node_modules", server.SKIP_DIRS)

    def test_one_drive_skipped(self):
        self.assertIn("OneDrive", server.SKIP_DIRS)

    def test_cookies_skipped(self):
        self.assertIn("Cookies", server.SKIP_DIRS)

    def test_npm_skipped(self):
        self.assertIn(".npm", server.SKIP_DIRS)

    def test_min_size(self):
        self.assertGreater(len(server.SKIP_DIRS), 50,
                           f"SKIP_DIRS only has {len(server.SKIP_DIRS)} entries, expected 50+")


class TestDeniedRuntimePattern(unittest.TestCase):
    """Verify DENIED_RUNTIME_PATTERN is disabled (python -c / node -e allowed)."""
    def test_denied_runtime_removed(self):
        self.assertFalse(hasattr(server, "DENIED_RUNTIME_PATTERN"),
                         "DENIED_RUNTIME_PATTERN should not exist — python -c / node -e must be allowed")


class TestDeniedCommandPattern(unittest.TestCase):
    """Verify DENIED_COMMAND_PATTERN correctly blocks/allows."""
    def test_does_not_block_semicolon_alone(self):
        # `;` should NOT be in the character class; only `&` and backtick
        self.assertFalse(server.DENIED_COMMAND_PATTERN.search("python -c a=1 print a"),  # no ;/&/` in this
                         "DENIED pattern should not match safe Python")

    def test_does_not_block_pipe(self):
        self.assertIsNone(server.DENIED_COMMAND_PATTERN.search("dir | findstr x"))

    def test_blocks_del(self):
        self.assertIsNotNone(server.DENIED_COMMAND_PATTERN.search("del file.txt"))

    def test_blocks_ampersand(self):
        self.assertIsNotNone(server.DENIED_COMMAND_PATTERN.search("dir & del"))

    def test_blocks_backtick(self):
        self.assertIsNotNone(server.DENIED_COMMAND_PATTERN.search("dir `; del"))


class TestSafeCommandPrefixes(unittest.TestCase):
    """Verify whitelist has expected entries."""
    def test_python_c_in_prefixes(self):
        self.assertIn("python -c ", server.SAFE_COMMAND_PREFIXES)

    def test_pip_in_prefixes(self):
        self.assertIn("pip ", server.SAFE_COMMAND_PREFIXES)

    def test_curl_in_prefixes(self):
        self.assertIn("curl ", server.SAFE_COMMAND_PREFIXES)

    def test_cat_in_prefixes(self):
        self.assertIn("cat ", server.SAFE_COMMAND_PREFIXES)

    def test_mkdir_in_prefixes(self):
        self.assertIn("mkdir ", server.SAFE_COMMAND_PREFIXES)

    def test_set_content_in_prefixes(self):
        self.assertIn("set-content ", server.SAFE_COMMAND_PREFIXES)

    def test_min_count(self):
        self.assertGreater(len(server.SAFE_COMMAND_PREFIXES), 100,
                           f"Only {len(server.SAFE_COMMAND_PREFIXES)} prefixes, expected 100+")


class TestLauncherInstall(unittest.TestCase):
    """Tests for launcher.py install and shortcut logic."""

    def test_get_code_home(self):
        result = launcher.get_code_home()
        self.assertEqual(result, Path.home() / ".code")

    def test_ensure_installed_noop_in_dev(self):
        """ensure_installed is a no-op when sys.frozen is False (dev mode)."""
        self.assertFalse(getattr(sys, "frozen", False),
                         "Test must run in dev mode for this assertion")
        # Should return immediately without raising
        launcher.ensure_installed()

    def test_create_desktop_shortcut_ps_script(self):
        """The PowerShell script embeds the correct target path."""
        exe = Path(r"C:\Users\Test\.code\Code-v9.9.9.exe")
        with mock.patch("subprocess.run") as mock_run, \
             mock.patch("launcher._append_log"):
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "ok"
            ok = launcher.create_desktop_shortcut(exe)
        self.assertTrue(ok)
        args = mock_run.call_args[0][0]
        self.assertEqual(args[0], "powershell")
        ps_script = args[4]
        self.assertIn(str(exe).replace("'", "''"), ps_script)
        self.assertIn("Code.lnk", ps_script)
        self.assertIn("WScript.Shell", ps_script)

    def test_create_desktop_shortcut_logs_on_failure(self):
        """Non-zero exit code or missing 'ok' result is logged."""
        exe = Path(r"C:\Users\Test\.code\Code-v9.9.9.exe")
        with mock.patch("subprocess.run") as mock_run, \
             mock.patch("launcher._append_log") as mock_log:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "error"
            ok = launcher.create_desktop_shortcut(exe)
        self.assertFalse(ok)
        # Verify _append_log was called with an error message
        self.assertTrue(mock_log.called)
        log_call_msg = mock_log.call_args[0][1]
        self.assertIn("Shortcut creation failed", log_call_msg)


class TestCodexImport(unittest.TestCase):
    """Tests for Codex session import (list, parse, convert, import)."""

    def _make_codex_jsonl(self, messages, session_id="019f91af-test-session",
                          created_at="2026-07-24T10:00:00Z"):
        """Build a Codex-format JSONL string from simplified message tuples.

        Each tuple: (role, text)  e.g. ("user", "hello")
        """
        lines = []
        # session_meta
        lines.append(json.dumps({
            "type": "session_meta",
            "timestamp": created_at,
            "payload": {"session_id": session_id, "timestamp": created_at,
                        "cwd": "/home/test", "originator": "codex-tui",
                        "cli_version": "0.145.0", "source": "cli",
                        "thread_source": "user", "model_provider": "custom",
                        "history_mode": "legacy"}
        }))
        # messages
        for role, text in messages:
            lines.append(json.dumps({
                "type": "response_item",
                "timestamp": created_at,
                "payload": {"type": "message", "role": role,
                            "content": [{"type": "input_text", "text": text}]}
            }))
        return "\n".join(lines) + "\n"

    def test_list_codex_sessions_detects_valid_file(self):
        """A valid Codex JSONL appears in the session list."""
        with tempfile.TemporaryDirectory() as td:
            codex_dir = Path(td) / "2026" / "07" / "24"
            codex_dir.mkdir(parents=True)
            jsonl = codex_dir / "test-session.jsonl"
            jsonl.write_text(self._make_codex_jsonl([
                ("user", "帮我写一个 Python 脚本"),
                ("assistant", "好的，这是脚本..."),
            ]), encoding="utf-8")
            with mock.patch.object(server, "CODEX_SESSIONS_DIR",
                                   Path(td)):
                sessions = server.list_codex_sessions()
        self.assertGreaterEqual(len(sessions), 1)
        self.assertIn("Python 脚本", sessions[0]["title"])
        self.assertGreater(sessions[0]["messageCount"], 0)  # estimated from file size
        self.assertEqual(sessions[0]["sourceId"], "test-session")
        self.assertEqual(sessions[0]["source"], "codex")
        self.assertEqual(
            sessions[0]["cwd"],
            server._normalize_local_path("/home/test"),
        )
        self.assertTrue(sessions[0]["sourcePath"].endswith(".jsonl"))

    def test_list_codex_sessions_search_by_filename(self):
        """Query parameter filters by filename."""
        with tempfile.TemporaryDirectory() as td:
            codex_dir = Path(td) / "2026" / "07" / "24"
            codex_dir.mkdir(parents=True)
            jsonl_a = codex_dir / "project-alpha.jsonl"
            jsonl_a.write_text(self._make_codex_jsonl([
                ("user", "Alpha project task"),
                ("assistant", "OK"),
            ], session_id="codex-alpha-session"), encoding="utf-8")
            jsonl_b = codex_dir / "project-beta.jsonl"
            jsonl_b.write_text(self._make_codex_jsonl([
                ("user", "Beta project task"),
                ("assistant", "OK"),
            ], session_id="codex-beta-session"), encoding="utf-8")
            with mock.patch.object(server, "CODEX_SESSIONS_DIR", Path(td)):
                all_sessions = server.list_codex_sessions()
                alpha_only = server.list_codex_sessions(query="alpha")
        self.assertEqual(len(all_sessions), 2)
        self.assertEqual(len(alpha_only), 1)
        self.assertIn("Alpha", alpha_only[0]["title"])

    def test_list_codex_sessions_empty_dir(self):
        """Empty or non-existent directory returns empty list."""
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(server, "CODEX_SESSIONS_DIR",
                                   Path(td) / "nonexistent"):
                sessions = server.list_codex_sessions()
        self.assertEqual(sessions, [])

    def test_codex_scanner_isolates_invalid_file(self):
        """One malformed source never hides other importable sessions."""
        with tempfile.TemporaryDirectory() as td:
            codex_dir = Path(td) / "2026" / "07" / "24"
            codex_dir.mkdir(parents=True)
            (codex_dir / "broken.jsonl").write_text(
                '{"type":"response_item"',
                encoding="utf-8",
            )
            (codex_dir / "healthy.jsonl").write_text(
                self._make_codex_jsonl([
                    ("user", "Healthy session"),
                    ("assistant", "OK"),
                ], session_id="healthy-source-session"),
                encoding="utf-8",
            )
            with mock.patch.object(server, "CODEX_SESSIONS_DIR", Path(td)):
                sessions = server.list_codex_sessions()
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["sourceId"], "healthy")

    def test_codex_scanner_deduplicates_stable_source_session_id(self):
        """The most complete copy wins when one source id has multiple files."""
        with tempfile.TemporaryDirectory() as td:
            codex_dir = Path(td) / "2026" / "07" / "24"
            codex_dir.mkdir(parents=True)
            source_id = "duplicate-source-session"
            older = codex_dir / "older-copy.jsonl"
            older.write_text(self._make_codex_jsonl([
                ("user", "Older copy"),
                ("assistant", "Old response"),
            ], session_id=source_id), encoding="utf-8")
            newer = codex_dir / "complete-copy.jsonl"
            newer.write_text(self._make_codex_jsonl([
                ("user", "Complete copy"),
                ("assistant", "First response"),
                ("user", "Later turn"),
                ("assistant", "Latest response"),
            ], session_id=source_id), encoding="utf-8")

            with mock.patch.object(server, "CODEX_SESSIONS_DIR", Path(td)):
                sessions = server.list_codex_sessions()
                hidden_alternate = server.list_codex_sessions(query="older-copy")

        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["duplicateCount"], 2)
        self.assertEqual(sessions[0]["title"], "Complete copy")
        self.assertEqual(
            Path(sessions[0]["sourcePath"]),
            newer.resolve(),
        )
        self.assertEqual(hidden_alternate, [])

    def test_read_codex_session_meta_extracts_title_and_count(self):
        """_read_codex_session_meta returns title and estimated count."""
        with tempfile.TemporaryDirectory() as td:
            jsonl = Path(td) / "test.jsonl"
            jsonl.write_text(self._make_codex_jsonl([
                ("user", "项目交接测试"),
                ("assistant", "收到，开始处理"),
                ("user", "第二步"),
                ("assistant", "好的"),
            ]), encoding="utf-8")
            meta = server._read_codex_session_meta(jsonl)
        self.assertEqual(meta["title"], "项目交接测试")
        self.assertGreater(meta["message_count"], 0)  # estimated from file size
        self.assertEqual(meta["cwd"], server._normalize_local_path("/home/test"))

    def test_codex_user_wrapper_sanitizer_retains_only_actual_request(self):
        ambient = (
            '<in-app-browser-context source="ambient-ui-state">\n'
            "# In app browser:\n- Current URL: http://127.0.0.1:3010/\n"
            "</in-app-browser-context>\n\n"
            "## My request for Codex:\nContinue the import task"
        )
        self.assertEqual(
            server._sanitize_codex_user_text(ambient),
            "Continue the import task",
        )
        injected_only = (
            "<recommended_plugins>\n- Example\n</recommended_plugins>"
            "# AGENTS.md instructions for C:\\workspace\n"
            "<INSTRUCTIONS>\nRules\n</INSTRUCTIONS>"
            "<environment_context>\n<cwd>C:\\workspace</cwd>\n</environment_context>"
        )
        self.assertEqual(server._sanitize_codex_user_text(injected_only), "")
        self.assertEqual(
            server._sanitize_codex_user_text(
                "<environment_context>\n<cwd>C:\\workspace</cwd>\n"
                "</environment_context>"
            ),
            "",
        )
        self.assertEqual(
            server._sanitize_codex_user_text("<turn_aborted>Stopped</turn_aborted>"),
            "",
        )
        self.assertEqual(
            server._sanitize_codex_user_text(
                "<command-name>/login</command-name>"
                "<command-message>login</command-message>"
                "<command-args></command-args>"
            ),
            "/login",
        )

    def test_read_codex_title_uses_request_inside_ambient_wrapper(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "wrapped.jsonl"
            source.write_text(self._make_codex_jsonl([
                (
                    "user",
                    '<in-app-browser-context source="ambient-ui-state">\n'
                    "browser state\n</in-app-browser-context>\n"
                    "## My request for Codex:\nActual imported title",
                ),
                ("assistant", "OK"),
            ]), encoding="utf-8")
            self.assertEqual(
                server._read_codex_title(source),
                "Actual imported title",
            )
            self.assertEqual(
                server._read_codex_session_meta(source)["title"],
                "Actual imported title",
            )

    def test_import_codex_session_creates_code_files(self):
        """Import creates .jsonl, .json, and updates index."""
        with tempfile.TemporaryDirectory() as td:
            codex_file = Path(td) / "codex-session.jsonl"
            codex_file.write_text(self._make_codex_jsonl([
                ("user", "这是第一条消息"),
                ("assistant", "这是回复"),
            ]), encoding="utf-8")
            sessions_dir = Path(td) / "code-sessions"
            sessions_dir.mkdir()
            idx = sessions_dir / "index.jsonl"
            idx.write_text("", encoding="utf-8")
            # import now uses created_at from messages (2026-07-24) for date_dir
            date_dir = sessions_dir / "2026" / "07" / "24"
            with mock.patch.object(server, "SESSIONS_DIR", sessions_dir):
                meta = server.import_codex_session(str(codex_file))

            self.assertEqual(meta["title"], "这是第一条消息")
            self.assertEqual(meta["messageCount"], 2)
            self.assertEqual(meta["source"], "codex")
            self.assertTrue(meta["sourceBadgeVisible"])
            self.assertEqual(meta["cwd"], server._normalize_local_path("/home/test"))
            self.assertIsNone(meta["projectId"])
            self.assertTrue(meta["id"])

            jsonl_files = list(date_dir.glob("*.jsonl"))
            json_files = list(date_dir.glob("*.json"))
            self.assertEqual(len(jsonl_files), 1)
            self.assertEqual(len(json_files), 1)

            msgs = server.read_jsonl(jsonl_files[0])
            self.assertEqual(len(msgs), 3)
            self.assertEqual(msgs[0]["role"], "system")
            self.assertEqual(msgs[0]["meta"]["kind"], "import-boundary")
            self.assertTrue(msgs[0]["meta"]["_system"])
            self.assertEqual(msgs[1]["role"], "user")
            self.assertEqual(msgs[1]["content"], "这是第一条消息")
            stored = server.read_json(json_files[0], {})
            self.assertNotIn("group", stored)
            index_entry = {
                item["id"]: item
                for item in (
                    json.loads(line)
                    for line in idx.read_text(encoding="utf-8").splitlines()
                    if line.strip()
                )
            }[meta["id"]]
            self.assertEqual(index_entry["source"], "codex")
            self.assertTrue(index_entry["sourceBadgeVisible"])
            self.assertNotIn("group", index_entry)
            self.assertNotIn("project", index_entry)

    def test_reimport_unchanged_codex_session_is_idempotent(self):
        """An unchanged source is a no-op and does not duplicate the index."""
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "codex-session.jsonl"
            source.write_text(self._make_codex_jsonl([
                ("user", "Initial request"),
                ("assistant", "Initial response"),
            ]), encoding="utf-8")
            sessions_dir = Path(td) / "sessions"
            sessions_dir.mkdir()
            index_path = sessions_dir / "index.jsonl"
            index_path.write_text("", encoding="utf-8")

            with mock.patch.object(server, "SESSIONS_DIR", sessions_dir):
                first = server.import_codex_session(str(source))
                index_after_first = index_path.read_text(encoding="utf-8")
                second = server.import_codex_session(str(source))

            self.assertEqual(first["importAction"], "created")
            self.assertEqual(second["importAction"], "unchanged")
            self.assertEqual(second["id"], first["id"])
            self.assertEqual(
                index_path.read_text(encoding="utf-8"),
                index_after_first,
            )
            stored_meta = server.read_json(
                next(sessions_dir.rglob(f"{first['id']}.json")),
                {},
            )
            self.assertEqual(stored_meta["importState"]["source"], "codex")
            self.assertEqual(len(stored_meta["importState"]["sourceSha256"]), 64)
            self.assertFalse(stored_meta["importState"]["codeModified"])
            self.assertTrue(second["sourceBadgeVisible"])
            self.assertEqual(
                len(list(sessions_dir.rglob(f"{first['id']}.json"))),
                1,
            )

    def test_reimport_updated_pristine_codex_session_refreshes_in_place(self):
        """A source update replaces a pristine imported snapshot in place."""
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "codex-session.jsonl"
            source.write_text(self._make_codex_jsonl([
                ("user", "Initial request"),
                ("assistant", "Initial response"),
            ]), encoding="utf-8")
            sessions_dir = Path(td) / "sessions"
            sessions_dir.mkdir()
            (sessions_dir / "index.jsonl").write_text("", encoding="utf-8")

            with mock.patch.object(server, "SESSIONS_DIR", sessions_dir):
                first = server.import_codex_session(str(source))
                source.write_text(self._make_codex_jsonl([
                    ("user", "Initial request"),
                    ("assistant", "Initial response"),
                    ("user", "Source follow-up"),
                    ("assistant", "Updated source response"),
                ]), encoding="utf-8")
                second = server.import_codex_session(str(source))

            self.assertEqual(second["importAction"], "updated")
            self.assertEqual(second["id"], first["id"])
            stored = server.read_jsonl(
                next(sessions_dir.rglob(f"{first['id']}.jsonl"))
            )
            self.assertIn(
                "Source follow-up",
                [item.get("content") for item in stored],
            )
            self.assertEqual(
                len(list(sessions_dir.rglob(f"{first['id']}.json"))),
                1,
            )

    def test_reimport_touched_codex_source_refreshes_locator_only(self):
        """Metadata-only source changes settle after one authoritative recheck."""
        with tempfile.TemporaryDirectory() as td:
            codex_dir = Path(td) / "codex"
            codex_dir.mkdir()
            source = codex_dir / "codex-session.jsonl"
            source.write_text(self._make_codex_jsonl([
                ("user", "Initial request"),
                ("assistant", "Initial response"),
            ]), encoding="utf-8")
            sessions_dir = Path(td) / "sessions"
            sessions_dir.mkdir()
            (sessions_dir / "index.jsonl").write_text("", encoding="utf-8")

            with mock.patch.object(server, "SESSIONS_DIR", sessions_dir), \
                 mock.patch.object(server, "CODEX_SESSIONS_DIR", codex_dir):
                first = server.import_codex_session(str(source))
                source_stat = source.stat()
                os.utime(
                    source,
                    ns=(source_stat.st_atime_ns, source_stat.st_mtime_ns + 1_000_000),
                )
                touched = server.list_codex_sessions()[0]
                second = server.import_codex_session(str(source))
                settled = server.list_codex_sessions()[0]

            self.assertEqual(touched["importStatus"], "update-available")
            self.assertEqual(second["importAction"], "unchanged")
            self.assertEqual(second["id"], first["id"])
            self.assertEqual(settled["importStatus"], "imported")
            self.assertFalse(settled["canImport"])

    def test_reimport_moved_codex_source_matches_stable_source_session_id(self):
        """Moving a source file does not create a second imported session."""
        with tempfile.TemporaryDirectory() as td:
            first_dir = Path(td) / "first"
            second_dir = Path(td) / "second"
            first_dir.mkdir()
            second_dir.mkdir()
            source = first_dir / "codex-session.jsonl"
            source.write_text(self._make_codex_jsonl([
                ("user", "Initial request"),
                ("assistant", "Initial response"),
            ]), encoding="utf-8")
            sessions_dir = Path(td) / "sessions"
            sessions_dir.mkdir()
            (sessions_dir / "index.jsonl").write_text("", encoding="utf-8")

            with mock.patch.object(server, "SESSIONS_DIR", sessions_dir):
                first = server.import_codex_session(str(source))
                moved = second_dir / source.name
                source.rename(moved)
                second = server.import_codex_session(str(moved))

            self.assertEqual(second["importAction"], "unchanged")
            self.assertEqual(second["id"], first["id"])
            self.assertEqual(
                second["importState"]["sourcePathKey"],
                server._path_identity(moved),
            )
            self.assertEqual(
                len(list(sessions_dir.rglob("codex-*.json"))),
                1,
            )

    def test_reimport_updated_continued_codex_session_creates_one_snapshot(self):
        """A source update never overwrites messages added later in Code."""
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "codex-session.jsonl"
            source.write_text(self._make_codex_jsonl([
                ("user", "Initial request"),
                ("assistant", "Initial response"),
            ]), encoding="utf-8")
            sessions_dir = Path(td) / "sessions"
            sessions_dir.mkdir()
            index_path = sessions_dir / "index.jsonl"
            index_path.write_text("", encoding="utf-8")

            with mock.patch.object(server, "SESSIONS_DIR", sessions_dir):
                first = server.import_codex_session(str(source))
                root_messages_path = next(
                    sessions_dir.rglob(f"{first['id']}.jsonl")
                )
                root_messages = server.read_jsonl(root_messages_path)
                root_messages.extend([
                    {"role": "user", "content": "Continued in Code"},
                    {"role": "assistant", "content": "Code-side response"},
                ])
                server.write_jsonl(root_messages_path, root_messages)

                unchanged = server.import_codex_session(str(source))
                self.assertEqual(unchanged["importAction"], "continued")
                self.assertFalse(unchanged["sourceBadgeVisible"])
                self.assertFalse(
                    server._read_session_index()[first["id"]][
                        "sourceBadgeVisible"
                    ]
                )

                source.write_text(self._make_codex_jsonl([
                    ("user", "Initial request"),
                    ("assistant", "Initial response"),
                    ("user", "New source turn"),
                    ("assistant", "New source response"),
                ]), encoding="utf-8")
                snapshot = server.import_codex_session(str(source))
                index_after_snapshot = index_path.read_text(encoding="utf-8")
                repeated = server.import_codex_session(str(source))

            self.assertEqual(snapshot["importAction"], "snapshot-created")
            self.assertTrue(snapshot["sourceBadgeVisible"])
            self.assertNotEqual(snapshot["id"], first["id"])
            self.assertEqual(snapshot["importRootSessionId"], first["id"])
            self.assertEqual(
                snapshot["importState"]["previousSessionId"],
                first["id"],
            )
            self.assertEqual(repeated["importAction"], "unchanged")
            self.assertEqual(repeated["id"], snapshot["id"])
            self.assertEqual(
                index_path.read_text(encoding="utf-8"),
                index_after_snapshot,
            )

            preserved_root = server.read_jsonl(root_messages_path)
            self.assertIn(
                "Continued in Code",
                [item.get("content") for item in preserved_root],
            )
            snapshot_messages = server.read_jsonl(
                next(sessions_dir.rglob(f"{snapshot['id']}.jsonl"))
            )
            snapshot_contents = [item.get("content") for item in snapshot_messages]
            self.assertIn("New source turn", snapshot_contents)
            self.assertNotIn("Continued in Code", snapshot_contents)

    def test_codex_import_listing_reports_repeated_import_state(self):
        """The picker distinguishes imported, continued, and conflict states."""
        with tempfile.TemporaryDirectory() as td:
            codex_dir = Path(td) / "codex"
            codex_dir.mkdir()
            source = codex_dir / "codex-session.jsonl"
            source.write_text(self._make_codex_jsonl([
                ("user", "Initial request"),
                ("assistant", "Initial response"),
            ]), encoding="utf-8")
            sessions_dir = Path(td) / "sessions"
            sessions_dir.mkdir()
            (sessions_dir / "index.jsonl").write_text("", encoding="utf-8")

            with mock.patch.object(server, "SESSIONS_DIR", sessions_dir), \
                 mock.patch.object(server, "CODEX_SESSIONS_DIR", codex_dir):
                before = server.list_codex_sessions()[0]
                imported = server.import_codex_session(str(source))
                after = server.list_codex_sessions()[0]

                meta_path = next(sessions_dir.rglob(f"{imported['id']}.json"))
                messages_path = meta_path.with_suffix(".jsonl")
                messages = server.read_jsonl(messages_path)
                messages.append({"role": "user", "content": "Continued in Code"})
                server.write_jsonl(messages_path, messages)
                meta = server.read_json(meta_path, {})
                server._refresh_import_divergence(meta, messages)
                server.write_json(meta_path, meta)
                continued = server.list_codex_sessions()[0]

                source.write_text(self._make_codex_jsonl([
                    ("user", "Initial request"),
                    ("assistant", "Initial response"),
                    ("user", "New source turn"),
                    ("assistant", "New source response"),
                ]), encoding="utf-8")
                conflict = server.list_codex_sessions()[0]

            self.assertEqual(before["importStatus"], "available")
            self.assertTrue(before["canImport"])
            self.assertEqual(after["importStatus"], "imported")
            self.assertFalse(after["canImport"])
            self.assertEqual(continued["importStatus"], "continued")
            self.assertFalse(continued["canImport"])
            self.assertEqual(conflict["importStatus"], "update-conflict")
            self.assertTrue(conflict["canImport"])

    def test_import_codex_preserves_safe_history_and_usage(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "codex-complex.jsonl"
            timestamp = "2026-07-24T10:00:00.123Z"
            image_data = "aGVsbG8="
            large_output = "HEAD-" + ("x" * 14000) + "-TAIL"
            records = [
                {
                    "type": "session_meta",
                    "timestamp": timestamp,
                    "payload": {"cwd": "/home/test/codex"},
                },
                {
                    "type": "turn_context",
                    "timestamp": timestamp,
                    "payload": {"model": "gpt-test"},
                },
                {
                    "type": "response_item",
                    "timestamp": timestamp,
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": "Inspect this image"},
                            {
                                "type": "input_image",
                                "image_url": f"data:image/png;base64,{image_data}",
                            },
                        ],
                    },
                },
                {
                    "type": "event_msg",
                    "timestamp": timestamp,
                    "payload": {"type": "agent_reasoning", "text": "Check the file first."},
                },
                {
                    "type": "response_item",
                    "timestamp": timestamp,
                    "payload": {
                        "type": "reasoning",
                        "summary": [{"type": "summary_text", "text": "Use a safe read."}],
                        "encrypted_content": "must-not-be-imported",
                    },
                },
                {
                    "type": "response_item",
                    "timestamp": timestamp,
                    "payload": {
                        "type": "function_call",
                        "name": "read_file",
                        "arguments": '{"path":"example.txt"}',
                        "call_id": "call-1",
                    },
                },
                {
                    "type": "response_item",
                    "timestamp": timestamp,
                    "payload": {
                        "type": "function_call_output",
                        "call_id": "call-1",
                        "output": large_output,
                    },
                },
                {
                    "type": "response_item",
                    "timestamp": timestamp,
                    "payload": {
                        "type": "message",
                        "role": "assistant",
                        "content": [{"type": "output_text", "text": "Inspection complete."}],
                    },
                },
                {
                    "type": "event_msg",
                    "timestamp": timestamp,
                    "payload": {
                        "type": "token_count",
                        "info": {
                            "total_token_usage": {
                                "input_tokens": 101,
                                "cached_input_tokens": 11,
                                "output_tokens": 20,
                            },
                            "last_token_usage": {
                                "input_tokens": 12,
                                "cached_input_tokens": 3,
                                "output_tokens": 4,
                            },
                        },
                    },
                },
            ]
            source.write_text(
                "\n".join(json.dumps(item) for item in records) + "\n",
                encoding="utf-8",
            )
            sessions_dir = Path(td) / "sessions"
            sessions_dir.mkdir()
            (sessions_dir / "index.jsonl").write_text("", encoding="utf-8")

            with mock.patch.object(server, "SESSIONS_DIR", sessions_dir):
                meta = server.import_codex_session(str(source))
                # Re-importing the same source replaces the deterministic target.
                server.import_codex_session(str(source))

            stored_path = next(sessions_dir.rglob(f"{meta['id']}.jsonl"))
            messages = server.read_jsonl(stored_path)
            boundaries = [
                item for item in messages
                if item.get("meta", {}).get("kind") == "import-boundary"
            ]
            self.assertEqual(len(boundaries), 1)
            self.assertIn("migrated from Codex", boundaries[0]["content"])
            self.assertIn(
                "using only the tools that Code currently makes available",
                boundaries[0]["content"],
            )

            user = next(item for item in messages if item.get("role") == "user")
            self.assertEqual(server._import_message_text(user), "Inspect this image")
            self.assertEqual(user["_model"], "gpt-test")
            self.assertEqual(user["_time"], timestamp)
            self.assertEqual(user["_images"][0]["base64"], image_data)
            self.assertEqual(user["content"][1]["type"], "image_url")

            call = next(item for item in messages if item.get("role") == "tool-call")
            result = next(item for item in messages if item.get("role") == "tool-result")
            for trace in (call, result):
                self.assertTrue(trace["meta"]["skipApi"])
                self.assertTrue(trace["meta"]["imported"])
                self.assertFalse(trace["meta"]["native"])
                self.assertFalse(trace["meta"]["replayable"])
                self.assertEqual(trace["meta"]["toolCallId"], "call-1")
            self.assertEqual(call["meta"]["action"], "read_file")
            self.assertTrue(result["meta"]["importedPayloadTruncated"])
            self.assertEqual(result["meta"]["importedOriginalChars"], len(large_output))
            self.assertEqual(len(result["meta"]["importedSha256"]), 64)
            self.assertIn("HEAD-", result["content"])
            self.assertIn("-TAIL", result["content"])
            self.assertNotIn("must-not-be-imported", json.dumps(messages))

            assistant = next(
                item for item in messages if item.get("role") == "assistant"
            )
            self.assertIn("Check the file first.", assistant["thought"])
            self.assertIn("Use a safe read.", assistant["thought"])
            self.assertEqual(
                assistant["meta"]["_usage"],
                {"input": 12, "output": 4, "cache": 3},
            )
            self.assertEqual(
                meta["stats"],
                {"input": 101, "output": 20, "cache": 11},
            )
            self.assertEqual(meta["lastUsage"], {"input": 12, "output": 4, "cache": 3})
            self.assertEqual(meta["messageCount"], len(messages) - 1)

    def test_import_codex_session_rejects_nonexistent_file(self):
        with self.assertRaises(server.ImportSourceError) as raised:
            server.import_codex_session("/nonexistent/path.jsonl")
        self.assertEqual(raised.exception.code, "import_source_missing")
        self.assertTrue(raised.exception.retryable)
        self.assertEqual(raised.exception.http_status, 404)

    def test_import_codex_session_rejects_empty(self):
        """A file with no valid messages raises ValueError."""
        with tempfile.TemporaryDirectory() as td:
            empty = Path(td) / "empty.jsonl"
            empty.write_text(
                '{"type":"session_meta","payload":{"session_id":"x"}}\n',
                encoding="utf-8")
            with self.assertRaises(ValueError):
                server.import_codex_session(str(empty))

    def test_import_codex_rejects_invalid_jsonl_without_persisting(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "broken.jsonl"
            source.write_text(
                self._make_codex_jsonl([
                    ("user", "Valid prefix"),
                    ("assistant", "Valid response"),
                ]) + '{"type":"response_item"\n',
                encoding="utf-8",
            )
            sessions_dir = Path(td) / "sessions"
            sessions_dir.mkdir()
            (sessions_dir / "index.jsonl").write_text("", encoding="utf-8")

            with mock.patch.object(server, "SESSIONS_DIR", sessions_dir), \
                 self.assertRaises(server.ImportSourceError) as raised:
                server.import_codex_session(str(source))

            self.assertEqual(
                raised.exception.code,
                "import_source_invalid_jsonl",
            )
            self.assertFalse(raised.exception.retryable)
            self.assertIn("line 4", str(raised.exception))
            self.assertEqual(list(sessions_dir.rglob("*.json")), [])
            self.assertEqual(
                (sessions_dir / "index.jsonl").read_text(encoding="utf-8"),
                "",
            )

    def test_import_codex_rejects_invalid_utf8(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "invalid-encoding.jsonl"
            source.write_bytes(b"\xff\xfe\x00")
            with self.assertRaises(server.ImportSourceError) as raised:
                server.import_codex_session(str(source))
        self.assertEqual(
            raised.exception.code,
            "import_source_invalid_encoding",
        )
        self.assertFalse(raised.exception.retryable)

    def test_import_codex_marks_incomplete_tail_as_retryable(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "still-writing.jsonl"
            source.write_text(
                self._make_codex_jsonl([
                    ("user", "Valid prefix"),
                    ("assistant", "Valid response"),
                ]) + '{"type":"response_item"',
                encoding="utf-8",
            )
            with self.assertRaises(server.ImportSourceError) as raised:
                server.import_codex_session(str(source))

        self.assertEqual(
            raised.exception.code,
            "import_source_incomplete_jsonl",
        )
        self.assertEqual(raised.exception.http_status, 409)
        self.assertTrue(raised.exception.retryable)

    def test_import_codex_classifies_permission_denied(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "permission.jsonl"
            source.write_text(self._make_codex_jsonl([
                ("user", "Permission test"),
                ("assistant", "OK"),
            ]), encoding="utf-8")
            real_open = open

            def guarded_open(path, *args, **kwargs):
                if Path(path).resolve() == source.resolve():
                    raise PermissionError("denied")
                return real_open(path, *args, **kwargs)

            with mock.patch("builtins.open", side_effect=guarded_open), \
                 self.assertRaises(server.ImportSourceError) as raised:
                server.import_codex_session(str(source))

        self.assertEqual(
            raised.exception.code,
            "import_source_permission_denied",
        )
        self.assertEqual(raised.exception.http_status, 403)
        self.assertFalse(raised.exception.retryable)

    def test_import_codex_rejects_source_changed_during_snapshot(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "changing.jsonl"
            source.write_text(self._make_codex_jsonl([
                ("user", "Changing source"),
                ("assistant", "OK"),
            ]), encoding="utf-8")
            with mock.patch.object(
                server,
                "_import_source_path_signature",
                return_value=(-1, -1, -1, -1),
            ), self.assertRaises(server.ImportSourceError) as raised:
                server.import_codex_session(str(source))

        self.assertEqual(raised.exception.code, "import_source_changed")
        self.assertEqual(raised.exception.http_status, 409)
        self.assertTrue(raised.exception.retryable)

    def test_import_codex_persists_the_parsed_snapshot_hash(self):
        """Persistence reuses the parsed snapshot instead of reopening source."""
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "single-read.jsonl"
            source.write_text(self._make_codex_jsonl([
                ("user", "Single read"),
                ("assistant", "OK"),
            ]), encoding="utf-8")
            expected_hash = hashlib.sha256(source.read_bytes()).hexdigest()
            sessions_dir = Path(td) / "sessions"
            sessions_dir.mkdir()
            (sessions_dir / "index.jsonl").write_text("", encoding="utf-8")

            with mock.patch.object(server, "SESSIONS_DIR", sessions_dir), \
                 mock.patch.object(
                     server,
                     "_import_source_state",
                     side_effect=AssertionError("source reopened"),
                 ):
                imported = server.import_codex_session(str(source))

        self.assertEqual(imported["importAction"], "created")
        self.assertEqual(
            imported["importState"]["sourceSha256"],
            expected_hash,
        )

    def test_import_api_source_path_must_stay_inside_runtime_root(self):
        with tempfile.TemporaryDirectory() as td:
            codex_root = Path(td) / "codex"
            codex_root.mkdir()
            outside = Path(td) / "outside.jsonl"
            outside.write_text(self._make_codex_jsonl([
                ("user", "Outside"),
                ("assistant", "OK"),
            ]), encoding="utf-8")

            with mock.patch.object(server, "CODEX_SESSIONS_DIR", codex_root), \
                 self.assertRaises(server.ImportSourceError) as raised:
                server.import_session("codex", str(outside))

        self.assertEqual(
            raised.exception.code,
            "import_source_outside_root",
        )
        self.assertEqual(raised.exception.http_status, 403)
        self.assertFalse(raised.exception.retryable)

    def test_import_api_returns_structured_source_error(self):
        handler = object.__new__(server.CodeHandler)
        handler.path = "/api/import/sessions"
        handler.read_body_json = mock.Mock(return_value={
            "source": "codex",
            "sourcePath": "C:/missing/session.jsonl",
        })
        handler.send_json = mock.Mock()
        failure = server.ImportSourceError(
            "import_source_changed",
            "source changed",
            retryable=True,
            http_status=409,
        )

        with mock.patch.object(server, "import_session", side_effect=failure):
            server.CodeHandler.do_POST(handler)

        payload, status = handler.send_json.call_args.args
        self.assertEqual(status, 409)
        self.assertEqual(payload["error"], "source changed")
        self.assertEqual(payload["errorCode"], "import_source_changed")
        self.assertTrue(payload["retryable"])

    def test_stable_import_source_spools_large_sessions(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "large.jsonl"
            source.write_text(self._make_codex_jsonl([
                ("user", "Large snapshot"),
                ("assistant", "x" * 2048),
            ]), encoding="utf-8")
            expected_hash = hashlib.sha256(source.read_bytes()).hexdigest()

            with mock.patch.object(server, "_IMPORT_SOURCE_MEMORY_LIMIT", 64):
                with server._stable_import_source(source, "Codex") as (
                    fh,
                    source_info,
                ):
                    records = list(server._iter_import_json_records(fh, "Codex"))
                    rolled_to_disk = bool(getattr(fh.buffer, "_rolled", False))

        self.assertTrue(rolled_to_disk)
        self.assertEqual(len(records), 3)
        self.assertEqual(source_info["sourceSha256"], expected_hash)

    def test_generate_import_id_is_stable(self):
        """Same path produces same import ID."""
        id1 = server._generate_codex_import_id(
            Path("C:/Users/Admin/.codex/sessions/2026/07/24/test.jsonl"))
        id2 = server._generate_codex_import_id(
            Path("C:/Users/Admin/.codex/sessions/2026/07/24/test.jsonl"))
        self.assertEqual(id1, id2)
        self.assertTrue(id1.startswith("codex-"))

    def test_list_codex_sessions_includes_small_files(self):
        """Even small Codex session files appear (count estimated from file size)."""
        with tempfile.TemporaryDirectory() as td:
            codex_dir = Path(td) / "2026" / "07" / "24"
            codex_dir.mkdir(parents=True)
            jsonl = codex_dir / "small.jsonl"
            jsonl.write_text(self._make_codex_jsonl([
                ("user", "hi"),
                ("assistant", "hello"),
            ]), encoding="utf-8")
            with mock.patch.object(server, "CODEX_SESSIONS_DIR", Path(td)):
                sessions = server.list_codex_sessions()
        self.assertEqual(len(sessions), 1)

    # ── Claude Code import tests ──

    def _make_claude_jsonl(self, messages):
        """Build a Claude Code-format JSONL from (role, text) tuples."""
        lines = []
        for role, text in messages:
            content = text if role == "user" else [{"type": "text", "text": text}]
            lines.append(json.dumps({
                "type": role,
                "message": {"role": role, "content": content},
                "timestamp": "2026-07-24T10:00:00.000Z",
                "sessionId": "test-claude-session",
                "cwd": "/home/test/project",
            }))
        return "\n".join(lines) + "\n"

    def test_list_claude_sessions(self):
        with tempfile.TemporaryDirectory() as td:
            proj = Path(td) / "my-project"
            proj.mkdir(parents=True)
            jsonl = proj / "abc123.jsonl"
            jsonl.write_text(self._make_claude_jsonl([
                ("user", "帮我优化数据库查询"),
                ("assistant", "好的，先看看现有代码"),
            ]), encoding="utf-8")
            with mock.patch.object(server, "CLAUDE_PROJECTS_DIR", Path(td)):
                sessions = server.list_claude_sessions()
        self.assertGreaterEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["title"], "帮我优化数据库查询")
        self.assertEqual(sessions[0]["messageCount"], 2)
        self.assertEqual(sessions[0]["project"], "my-project")
        self.assertEqual(sessions[0]["source"], "claude-code")
        self.assertEqual(
            sessions[0]["cwd"],
            server._normalize_local_path("/home/test/project"),
        )
        self.assertTrue(sessions[0]["id"].startswith("claude-"))

    def test_list_claude_sessions_excludes_sidechain_agent_files(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "my-project"
            project.mkdir(parents=True)
            main = project / "main-session.jsonl"
            main.write_text(self._make_claude_jsonl([
                ("user", "Main session"),
                ("assistant", "Main reply"),
            ]), encoding="utf-8")
            sidechain = project / "agent-worker.jsonl"
            sidechain.write_text(
                json.dumps({
                    "type": "user",
                    "isSidechain": True,
                    "agentId": "worker",
                    "message": {"role": "user", "content": "Worker task"},
                    "timestamp": "2026-07-24T10:00:00.000Z",
                }) + "\n",
                encoding="utf-8",
            )
            with mock.patch.object(server, "CLAUDE_PROJECTS_DIR", Path(td)):
                sessions = server.list_claude_sessions()
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["sourceId"], "main-session")

    def test_list_claude_sessions_deduplicates_source_session_id(self):
        with tempfile.TemporaryDirectory() as td:
            project = Path(td) / "my-project"
            project.mkdir(parents=True)
            (project / "short-copy.jsonl").write_text(
                self._make_claude_jsonl([
                    ("user", "Short copy"),
                    ("assistant", "Old response"),
                ]),
                encoding="utf-8",
            )
            complete = project / "complete-copy.jsonl"
            complete.write_text(
                self._make_claude_jsonl([
                    ("user", "Complete Claude copy"),
                    ("assistant", "First response"),
                    ("user", "Later turn"),
                    ("assistant", "Latest response"),
                ]),
                encoding="utf-8",
            )
            with mock.patch.object(server, "CLAUDE_PROJECTS_DIR", Path(td)):
                sessions = server.list_claude_sessions()

        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["duplicateCount"], 2)
        self.assertEqual(sessions[0]["title"], "Complete Claude copy")
        self.assertEqual(Path(sessions[0]["sourcePath"]), complete.resolve())

    def test_import_claude_session(self):
        with tempfile.TemporaryDirectory() as td:
            jsonl = Path(td) / "session.jsonl"
            jsonl.write_text(self._make_claude_jsonl([
                ("user", "Claude 导入测试"),
                ("assistant", "收到，这是回复"),
                ("user", "继续第二步"),
                ("assistant", "好的"),
            ]), encoding="utf-8")
            sessions_dir = Path(td) / "code-sessions"
            sessions_dir.mkdir()
            (sessions_dir / "index.jsonl").write_text("", encoding="utf-8")
            date_dir = sessions_dir / "2026" / "07" / "24"
            with mock.patch.object(server, "SESSIONS_DIR", sessions_dir):
                meta = server.import_claude_session(str(jsonl))
            self.assertEqual(meta["title"], "Claude 导入测试")
            self.assertEqual(meta["messageCount"], 4)
            self.assertEqual(meta["source"], "claude-code")
            self.assertEqual(
                meta["cwd"],
                server._normalize_local_path("/home/test/project"),
            )
            self.assertIsNone(meta["projectId"])
            # Find the created jsonl file (may be in any subdirectory)
            created = list(sessions_dir.rglob(f"{meta['id']}.jsonl"))
            self.assertEqual(len(created), 1,
                            f"Expected 1 jsonl for {meta['id']}, found {len(created)} in {list(sessions_dir.rglob('*'))}")
            stored_files = list(sessions_dir.rglob(f"{meta['id']}.json"))
            self.assertEqual(len(stored_files), 1)
            stored = server.read_json(stored_files[0], {})
            self.assertNotIn("group", stored)
            index_entry = {
                item["id"]: item
                for item in (
                    json.loads(line)
                    for line in (sessions_dir / "index.jsonl").read_text(
                        encoding="utf-8"
                    ).splitlines()
                    if line.strip()
                )
            }[meta["id"]]
            self.assertEqual(index_entry["source"], "claude-code")

    def test_reimport_claude_session_uses_shared_idempotent_flow(self):
        """Claude imports expose the same unchanged and update states as Codex."""
        with tempfile.TemporaryDirectory() as td:
            claude_dir = Path(td) / "claude" / "project"
            claude_dir.mkdir(parents=True)
            source = claude_dir / "session.jsonl"
            source.write_text(self._make_claude_jsonl([
                ("user", "Initial Claude request"),
                ("assistant", "Initial Claude response"),
            ]), encoding="utf-8")
            sessions_dir = Path(td) / "sessions"
            sessions_dir.mkdir()
            (sessions_dir / "index.jsonl").write_text("", encoding="utf-8")

            with mock.patch.object(server, "SESSIONS_DIR", sessions_dir), \
                 mock.patch.object(
                     server,
                     "CLAUDE_PROJECTS_DIR",
                     claude_dir.parent,
                 ):
                first = server.import_claude_session(str(source))
                unchanged = server.import_claude_session(str(source))
                imported_row = server.list_claude_sessions()[0]
                source.write_text(self._make_claude_jsonl([
                    ("user", "Initial Claude request"),
                    ("assistant", "Initial Claude response"),
                    ("user", "New Claude turn"),
                    ("assistant", "New Claude response"),
                ]), encoding="utf-8")
                update_row = server.list_claude_sessions()[0]
                updated = server.import_claude_session(str(source))
                settled_row = server.list_claude_sessions()[0]

            self.assertEqual(first["importAction"], "created")
            self.assertEqual(unchanged["importAction"], "unchanged")
            self.assertEqual(unchanged["id"], first["id"])
            self.assertEqual(imported_row["importStatus"], "imported")
            self.assertFalse(imported_row["canImport"])
            self.assertEqual(update_row["importStatus"], "update-available")
            self.assertTrue(update_row["canImport"])
            self.assertEqual(updated["importAction"], "updated")
            self.assertEqual(updated["id"], first["id"])
            self.assertEqual(settled_row["importStatus"], "imported")

    def test_import_claude_rejects_partial_invalid_jsonl(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "broken-claude.jsonl"
            source.write_text(
                self._make_claude_jsonl([
                    ("user", "Valid Claude prefix"),
                    ("assistant", "Valid response"),
                ]) + "not-json\n",
                encoding="utf-8",
            )
            with self.assertRaises(server.ImportSourceError) as raised:
                server.import_claude_session(str(source))

        self.assertEqual(
            raised.exception.code,
            "import_source_invalid_jsonl",
        )
        self.assertIn("line 3", str(raised.exception))

    def test_import_claude_preserves_main_trace_images_and_usage(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "claude-complex.jsonl"
            timestamp = "2026-07-24T10:00:00.000Z"
            records = [
                {
                    "type": "user",
                    "message": {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": (
                                    "<system-reminder>foreign rules</system-reminder>"
                                    "Claude image task"
                                ),
                            },
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/png",
                                    "data": "aW1hZ2U=",
                                },
                            },
                        ],
                    },
                    "timestamp": timestamp,
                    "cwd": "/home/test/claude",
                },
                {
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "model": "claude-test",
                        "content": [
                            {"type": "thinking", "thinking": "Read the request."},
                        ],
                    },
                    "timestamp": timestamp,
                    "cwd": "/home/test/claude",
                },
                {
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "model": "claude-test",
                        "content": [
                            {"type": "thinking", "thinking": "Inspect safely."},
                            {"type": "text", "text": "I will inspect it."},
                            {
                                "type": "tool_use",
                                "id": "tool-1",
                                "name": "Read",
                                "input": {"file_path": "example.txt"},
                            },
                        ],
                        "usage": {
                            "input_tokens": 12,
                            "output_tokens": 5,
                            "cache_read_input_tokens": 3,
                            "cache_creation_input_tokens": 2,
                        },
                    },
                    "timestamp": timestamp,
                    "cwd": "/home/test/claude",
                },
                {
                    "type": "user",
                    "message": {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": "tool-1",
                                "content": "file contents",
                                "is_error": False,
                            },
                        ],
                    },
                    "timestamp": timestamp,
                    "cwd": "/home/test/claude",
                },
                {
                    "type": "user",
                    "isSidechain": True,
                    "message": {"role": "user", "content": "sidechain must be skipped"},
                    "timestamp": timestamp,
                },
                {
                    "type": "user",
                    "isMeta": True,
                    "message": {"role": "user", "content": "meta must be skipped"},
                    "timestamp": timestamp,
                },
                {
                    "type": "assistant",
                    "message": {
                        "role": "assistant",
                        "model": "claude-test",
                        "content": [{"type": "text", "text": "Done."}],
                        "usage": {"input_tokens": 4, "output_tokens": 2},
                    },
                    "timestamp": timestamp,
                    "cwd": "/home/test/claude",
                },
            ]
            source.write_text(
                "\n".join(json.dumps(item) for item in records) + "\n",
                encoding="utf-8",
            )
            sessions_dir = Path(td) / "sessions"
            sessions_dir.mkdir()
            (sessions_dir / "index.jsonl").write_text("", encoding="utf-8")

            with mock.patch.object(server, "SESSIONS_DIR", sessions_dir):
                meta = server.import_claude_session(str(source))

            messages = server.read_jsonl(
                next(sessions_dir.rglob(f"{meta['id']}.jsonl"))
            )
            boundary = messages[0]
            self.assertEqual(boundary["meta"]["kind"], "import-boundary")
            self.assertEqual(boundary["meta"]["importSource"], "claude-code")
            self.assertIn("migrated from Claude Code", boundary["content"])
            serialized = json.dumps(messages)
            self.assertNotIn("foreign rules", serialized)
            self.assertNotIn("sidechain must be skipped", serialized)
            self.assertNotIn("meta must be skipped", serialized)

            user = next(item for item in messages if item.get("role") == "user")
            self.assertEqual(server._import_message_text(user), "Claude image task")
            self.assertEqual(user["_images"][0]["base64"], "aW1hZ2U=")
            assistant = next(
                item for item in messages
                if item.get("role") == "assistant" and item.get("thought")
            )
            self.assertEqual(
                assistant["thought"],
                "Read the request.\n\nInspect safely.",
            )
            self.assertEqual(
                assistant["meta"]["_usage"],
                {
                    "input": 17,
                    "output": 5,
                    "cache": 3,
                    "cacheWrite": 2,
                },
            )
            call = next(item for item in messages if item.get("role") == "tool-call")
            result = next(item for item in messages if item.get("role") == "tool-result")
            self.assertEqual(call["meta"]["action"], "Read")
            self.assertEqual(result["meta"]["action"], "Read")
            self.assertEqual(call["meta"]["toolCallId"], result["meta"]["toolCallId"])
            self.assertTrue(call["meta"]["skipApi"])
            self.assertTrue(result["meta"]["skipApi"])
            self.assertIn('"is_error": false', result["content"])
            self.assertEqual(
                meta["stats"],
                {
                    "input": 21,
                    "output": 7,
                    "cache": 3,
                    "cacheWrite": 2,
                },
            )
            self.assertEqual(meta["lastUsage"], {"input": 4, "output": 2, "cache": 0})
            self.assertEqual(meta["messageCount"], len(messages) - 1)

    def test_unified_list_api(self):
        """list_importable_sessions dispatches correctly."""
        with tempfile.TemporaryDirectory() as td:
            codex_dir = Path(td) / "2026" / "07" / "24"
            codex_dir.mkdir(parents=True)
            (codex_dir / "test.jsonl").write_text(self._make_codex_jsonl([
                ("user", "测试"), ("assistant", "好的")
            ]), encoding="utf-8")
            with mock.patch.object(server, "CODEX_SESSIONS_DIR", Path(td)):
                sessions = server.list_importable_sessions("codex")
            self.assertGreaterEqual(len(sessions), 1)
        # Unknown source
        with self.assertRaises(ValueError):
            server.list_importable_sessions("unknown-source")


class TestSessionRevisionCas(unittest.TestCase):
    class Handler:
        def __init__(self, body=None):
            self.body = body or {}
            self.responses = []

        def read_body_json(self):
            return self.body

        def send_json(self, payload, status=200):
            self.responses.append((status, payload))

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name) / "data"
        self.sessions_dir = self.data_dir / "sessions"
        self.sessions_dir.mkdir(parents=True)
        self.config_path = self.data_dir / "config.json"
        self.config_path.write_text(json.dumps({"projectRoot": ""}), encoding="utf-8")
        self.patchers = [
            mock.patch.object(server, "DATA_DIR", self.data_dir),
            mock.patch.object(server, "SESSIONS_DIR", self.sessions_dir),
            mock.patch.object(server, "CONFIG_PATH", self.config_path),
            mock.patch.object(server, "PROJECTS_PATH", self.data_dir / "projects.json"),
        ]
        for patcher in self.patchers:
            patcher.start()

    def tearDown(self):
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.temp_dir.cleanup()

    def create_session(self, body=None):
        handler = self.Handler(body or {"title": "Revision test"})
        server.CodeHandler.create_session(handler)
        status, payload = handler.responses[-1]
        self.assertEqual(status, 201)
        return payload

    def save_session(self, session_id, body):
        handler = self.Handler(body)
        server.CodeHandler.save_session(handler, session_id)
        self.assertTrue(handler.responses)
        return handler.responses[-1]

    def get_session(self, session_id):
        handler = self.Handler()
        server.CodeHandler.get_session(handler, session_id)
        self.assertTrue(handler.responses)
        return handler.responses[-1]

    def test_revision_roundtrip_success_stale_rejection_and_metadata_compatibility(self):
        created = self.create_session()
        session_id = created["id"]
        self.assertEqual(created["revision"], 0)

        status, saved = self.save_session(session_id, {
            "title": "First messages",
            "expectedRevision": 0,
            "messages": [{"role": "user", "content": "first"}],
            "runState": {"status": "running"},
        })
        self.assertEqual(status, 200)
        self.assertEqual(saved["revision"], 1)
        self.assertEqual(self.get_session(session_id)[1]["revision"], 1)

        meta_before = server.session_path(session_id).read_bytes()
        messages_before = server.messages_path(session_id).read_bytes()
        status, conflict = self.save_session(session_id, {
            "title": "Must not persist",
            "expectedRevision": 0,
            "messages": [{"role": "assistant", "content": "stale"}],
            "runState": {"status": "failed"},
        })
        self.assertEqual(status, 409)
        self.assertEqual(conflict, {
            "error": "Session revision conflict",
            "errorCode": "session_revision_conflict",
            "expectedRevision": 0,
            "currentRevision": 1,
        })
        self.assertEqual(server.session_path(session_id).read_bytes(), meta_before)
        self.assertEqual(server.messages_path(session_id).read_bytes(), messages_before)

        status, metadata = self.save_session(session_id, {
            "title": "Metadata rename",
            "runState": {"status": "completed"},
        })
        self.assertEqual(status, 200)
        self.assertEqual(metadata["revision"], 1)
        self.assertEqual(metadata["title"], "Metadata rename")
        self.assertEqual(metadata["messages"], [{"role": "user", "content": "first"}])

    def test_legacy_zero_upgrade_missing_expected_and_rollback_switch(self):
        created = self.create_session({
            "title": "Legacy",
            "messages": [{"role": "user", "content": "created history"}],
        })
        session_id = created["id"]
        self.assertEqual(created["revision"], 0)
        legacy_meta = server.read_json(server.session_path(session_id), {})
        legacy_meta.pop("revision", None)
        server.write_json(server.session_path(session_id), legacy_meta)
        self.assertNotIn("revision", server.read_json(server.session_path(session_id), {}))
        self.assertEqual(self.get_session(session_id)[1]["revision"], 0)

        status, upgraded = self.save_session(session_id, {
            "messages": [{"role": "user", "content": "legacy upgrade"}],
        })
        self.assertEqual(status, 200)
        self.assertEqual(upgraded["revision"], 1)

        status, rejected = self.save_session(session_id, {
            "messages": [{"role": "user", "content": "second legacy write"}],
        })
        self.assertEqual(status, 409)
        self.assertEqual(rejected["errorCode"], "session_revision_conflict")
        self.assertIsNone(rejected["expectedRevision"])
        self.assertEqual(rejected["currentRevision"], 1)

        with mock.patch.object(server, "_SESSION_REVISION_CAS_ENABLED", False):
            status, rolled_back = self.save_session(session_id, {
                "messages": [{"role": "user", "content": "rollback write"}],
            })
        self.assertEqual(status, 200)
        self.assertEqual(rolled_back["revision"], 2)

    def test_two_concurrent_expected_revisions_allow_only_one_message_write(self):
        created = self.create_session()
        session_id = created["id"]
        barrier = threading.Barrier(3)
        results = []
        result_lock = threading.Lock()

        def writer(label):
            handler = self.Handler({
                "expectedRevision": 0,
                "messages": [{"role": "user", "content": label}],
            })
            barrier.wait()
            server.CodeHandler.save_session(handler, session_id)
            with result_lock:
                results.append(handler.responses[-1])

        threads = [threading.Thread(target=writer, args=(label,)) for label in ("one", "two")]
        for thread in threads:
            thread.start()
        barrier.wait()
        for thread in threads:
            thread.join()

        self.assertEqual(sorted(status for status, _payload in results), [200, 409])
        terminal = self.get_session(session_id)[1]
        self.assertEqual(terminal["revision"], 1)
        self.assertIn(terminal["messages"][0]["content"], {"one", "two"})

    def test_invalid_expected_revision_is_rejected_without_mutation(self):
        created = self.create_session()
        session_id = created["id"]
        meta_before = server.session_path(session_id).read_bytes()
        messages_before = server.messages_path(session_id).read_bytes()
        status, invalid = self.save_session(session_id, {
            "expectedRevision": "0",
            "messages": [{"role": "user", "content": "invalid"}],
        })
        self.assertEqual(status, 400)
        self.assertEqual(invalid["errorCode"], "session_revision_invalid")
        self.assertEqual(server.session_path(session_id).read_bytes(), meta_before)
        self.assertEqual(server.messages_path(session_id).read_bytes(), messages_before)

    def test_revision_feature_switch_parser_defaults_fail_closed(self):
        self.assertTrue(server._resolve_session_revision_cas_enabled({}))
        self.assertTrue(server._resolve_session_revision_cas_enabled({
            "CODE_SESSION_REVISION_CAS": "on",
        }))
        self.assertFalse(server._resolve_session_revision_cas_enabled({
            "CODE_SESSION_REVISION_CAS": "off",
        }))
        self.assertTrue(server._resolve_session_revision_cas_enabled({
            "CODE_SESSION_REVISION_CAS": "unexpected",
        }))


class TestConnectionCentricRouteApi(unittest.TestCase):
    @staticmethod
    def handler(path, body):
        handler = object.__new__(server.CodeHandler)
        handler.path = path
        handler.read_body_json = mock.Mock(return_value=body)
        handler.send_json = mock.Mock()
        return handler

    @staticmethod
    def resolved():
        return type("Resolved", (), {
            "key": "sk-synthetic-runtime-only",
            "base_url": "https://synthetic.invalid",
            "catalog_revision": 7,
        })()

    def test_agent_run_route_ref_resolves_exact_connection_without_public_key(self):
        handler = self.handler("/api/agent/runs", {
            "sessionId": "session-route",
            "clientRequestId": "request-route",
            "payload": {"model": "shared-model", "messages": [{"role": "user", "content": "hi"}]},
            "routeRef": "mr1_opaque",
            "catalogRevision": 7,
            "allowedTools": [],
        })
        run = {"id": "agent-route", "status": "running", "client_request_id": "request-route"}
        with mock.patch.object(server, "_MODEL_ROUTE_REGISTRY_ENABLED", True), \
             mock.patch.object(server._model_route_registry, "resolve", return_value=self.resolved()) as resolve, \
             mock.patch.object(server, "_create_agent_run", return_value=run) as create:
            server.CodeHandler.do_POST(handler)

        resolve.assert_called_once_with("mr1_opaque", 7, "shared-model")
        args = create.call_args.args
        kwargs = create.call_args.kwargs
        self.assertEqual(args[2], "https://synthetic.invalid")
        self.assertEqual(args[3], ["sk-synthetic-runtime-only"])
        self.assertEqual(kwargs["route_ref"], "mr1_opaque")
        self.assertEqual(kwargs["catalog_revision"], 7)
        payload, status = handler.send_json.call_args.args
        self.assertEqual(status, 201)
        self.assertNotIn("key", json.dumps(payload).lower())
        self.assertNotIn("baseurl", json.dumps(payload).lower())

    def test_authoritative_empty_refresh_blocks_old_agent_run_route_before_creation(self):
        with tempfile.TemporaryDirectory() as tempdir:
            registry = server.ModelRouteRegistry(Path(tempdir) / "routes.json")
            first = registry.refresh(
                [{
                    "connectionId": "manual_11111111-1111-4111-8111-111111111111",
                    "source": "manual",
                    "group": "manual",
                    "label": "Synthetic",
                    "baseUrl": "https://synthetic.invalid",
                    "key": "sk-synthetic-runtime-only",
                    "enabled": True,
                }],
                lambda _connection: ["shared-model"],
            )
            old_route = first["routes"][0]
            cleared = registry.refresh([], lambda _connection: [])
            self.assertTrue(cleared["ok"])
            self.assertEqual(cleared["routes"], [])

            handler = self.handler("/api/agent/runs", {
                "sessionId": "session-route",
                "clientRequestId": "request-route",
                "payload": {
                    "model": "shared-model",
                    "messages": [{"role": "user", "content": "hi"}],
                },
                "routeRef": old_route["routeRef"],
                "catalogRevision": first["catalogRevision"],
                "allowedTools": [],
            })
            with mock.patch.object(server, "_MODEL_ROUTE_REGISTRY_ENABLED", True), \
                 mock.patch.object(server, "_model_route_registry", registry), \
                 mock.patch.object(server, "_create_agent_run") as create:
                server.CodeHandler.do_POST(handler)

            payload, status = handler.send_json.call_args.args
            self.assertEqual(status, 503)
            self.assertEqual(payload["errorCode"], "route_catalog_unavailable")
            create.assert_not_called()
            self.assertNotIn("synthetic", json.dumps(payload).lower())

    def test_runtime_route_ref_uses_same_mutual_exclusion_and_resolution(self):
        handler = self.handler("/api/runtime/runs", {
            "sessionId": "session-route",
            "payload": {"model": "shared-model", "messages": [{"role": "user", "content": "hi"}]},
            "routeRef": "mr1_opaque",
            "catalogRevision": 7,
        })
        with mock.patch.object(server, "_MODEL_ROUTE_REGISTRY_ENABLED", True), \
             mock.patch.object(server._model_route_registry, "resolve", return_value=self.resolved()) as resolve, \
             mock.patch.object(
                 server,
                 "_create_model_runtime_run",
                 return_value={"id": "runtime-route", "status": "running"},
             ) as create:
            server.CodeHandler.do_POST(handler)

        resolve.assert_called_once_with("mr1_opaque", 7, "shared-model")
        self.assertEqual(create.call_args.args[2], "https://synthetic.invalid")
        self.assertEqual(create.call_args.args[3], ["sk-synthetic-runtime-only"])
        self.assertEqual(create.call_args.kwargs, {
            "route_ref": "mr1_opaque",
            "catalog_revision": 7,
        })

        rejected = self.handler("/api/runtime/runs", {
            "payload": {"model": "shared-model", "messages": [{"role": "user", "content": "hi"}]},
            "routeRef": "mr1_opaque",
            "catalogRevision": 7,
            "keys": ["sk-must-not-mix"],
        })
        server.CodeHandler.do_POST(rejected)
        payload, status = rejected.send_json.call_args.args
        self.assertEqual(status, 400)
        self.assertEqual(payload["errorCode"], "route_model_mismatch")

    def test_routing_v2_rejects_legacy_credentials_for_new_runs_but_flag_off_allows_rollback(self):
        agent_payload = {
            "sessionId": "session-route",
            "payload": {"model": "shared-model", "messages": [{"role": "user", "content": "hi"}]},
            "keys": ["sk-synthetic-legacy"],
            "allowedTools": [],
        }
        rejected = self.handler("/api/agent/runs", agent_payload)
        with mock.patch.object(server, "_MODEL_ROUTE_REGISTRY_ENABLED", True), \
             mock.patch.object(server, "_create_agent_run") as create:
            server.CodeHandler.do_POST(rejected)
        payload, status = rejected.send_json.call_args.args
        self.assertEqual(status, 409)
        self.assertEqual(payload["errorCode"], "route_not_found")
        create.assert_not_called()

        accepted = self.handler("/api/agent/runs", agent_payload)
        legacy_run = {"id": "legacy-run", "status": "running", "client_request_id": ""}
        with mock.patch.object(server, "_MODEL_ROUTE_REGISTRY_ENABLED", False), \
             mock.patch.object(server, "_create_agent_run", return_value=legacy_run) as create:
            server.CodeHandler.do_POST(accepted)
        self.assertEqual(accepted.send_json.call_args.args[1], 201)
        self.assertEqual(create.call_args.args[3], ["sk-synthetic-legacy"])

        runtime_rejected = self.handler("/api/runtime/runs", {
            "sessionId": "session-route",
            "payload": {"model": "shared-model", "messages": [{"role": "user", "content": "hi"}]},
            "keys": ["sk-synthetic-legacy"],
        })
        with mock.patch.object(server, "_MODEL_ROUTE_REGISTRY_ENABLED", True), \
             mock.patch.object(server, "_create_model_runtime_run") as create_runtime:
            server.CodeHandler.do_POST(runtime_rejected)
        payload, status = runtime_rejected.send_json.call_args.args
        self.assertEqual(status, 409)
        self.assertEqual(payload["errorCode"], "route_not_found")
        create_runtime.assert_not_called()

        proxy_rejected = object.__new__(server.CodeHandler)
        proxy_rejected.headers = {"Content-Length": "0"}
        proxy_rejected.rfile = io.BytesIO(b"")
        proxy_rejected.send_json = mock.Mock()
        with mock.patch.object(server, "_MODEL_ROUTE_REGISTRY_ENABLED", True):
            server.CodeHandler.proxy(proxy_rejected, "POST", "/v1/chat/completions")
        payload, status = proxy_rejected.send_json.call_args.args
        self.assertEqual(status, 409)
        self.assertEqual(payload["errorCode"], "route_not_found")

        compact_rejected = object.__new__(server.CodeHandler)
        compact_rejected.headers = {}
        compact_rejected.read_body_json = mock.Mock(return_value={
            "model": "shared-model",
            "messages": [{"role": "user", "content": str(index)} for index in range(6)],
        })
        with mock.patch.object(server, "_MODEL_ROUTE_REGISTRY_ENABLED", True), \
             self.assertRaises(server.ModelRouteError) as captured:
            server.CodeHandler.compact(compact_rejected)
        self.assertEqual(captured.exception.code, "route_not_found")

    def test_existing_legacy_agent_run_can_resume_but_routed_run_requires_route_ref(self):
        legacy_run = {"id": "legacy-run", "request": {"model": "shared-model"}, "route_ref": ""}
        legacy = self.handler("/api/agent/runs/legacy-run/resume", {
            "keys": ["sk-synthetic-legacy"],
            "baseUrl": "https://synthetic.invalid",
        })
        with mock.patch.object(server, "_MODEL_ROUTE_REGISTRY_ENABLED", True), \
             mock.patch.object(server, "_get_agent_run", return_value=legacy_run), \
             mock.patch.object(server, "_resume_agent_run") as resume:
            server.CodeHandler.do_POST(legacy)
        resume.assert_called_once()

        routed_run = {"id": "routed-run", "request": {"model": "shared-model"}, "route_ref": "mr1_opaque"}
        rejected = self.handler("/api/agent/runs/routed-run/resume", {
            "keys": ["sk-synthetic-legacy"],
        })
        with mock.patch.object(server, "_MODEL_ROUTE_REGISTRY_ENABLED", True), \
             mock.patch.object(server, "_get_agent_run", return_value=routed_run), \
             mock.patch.object(server, "_resume_agent_run") as resume:
            server.CodeHandler.do_POST(rejected)
        payload, status = rejected.send_json.call_args.args
        self.assertEqual(status, 409)
        self.assertEqual(payload["errorCode"], "route_not_found")
        resume.assert_not_called()

    def test_routed_agent_run_persists_only_non_secret_route_identity(self):
        routed = {
            "id": "a" * 32,
            "session_id": "session-route",
            "status": "waiting_credentials",
            "route_ref": "mr1_opaque",
            "catalog_revision": 7,
            "base_url": "https://must-not-persist.invalid",
            "keys": ["sk-must-not-persist"],
            "request": {"model": "shared-model"},
        }
        record = server._agent_run_record(routed)
        self.assertEqual(record["routeRef"], "mr1_opaque")
        self.assertEqual(record["catalogRevision"], 7)
        self.assertEqual(record["request"]["model"], "shared-model")
        self.assertNotIn("baseUrl", record)
        self.assertNotIn("keys", record)
        self.assertNotIn("must-not-persist", json.dumps(record))

        legacy_record = {**record, "baseUrl": "https://legacy-read-only.invalid"}
        legacy_record.pop("routeRef", None)
        legacy_record.pop("catalogRevision", None)
        loaded = server._agent_run_from_record(legacy_record)
        self.assertEqual(loaded["base_url"], "https://legacy-read-only.invalid")
        rewritten = server._agent_run_record(loaded)
        self.assertNotIn("baseUrl", rewritten)
        self.assertNotIn("keys", rewritten)

    def test_connection_backend_collection_is_injectable_without_public_schema_changes(self):
        observed = {}

        def collect_custom(body, context):
            observed.update({
                "bodyKeys": sorted(body),
                "contextKeys": sorted(context),
            })
            return [{
                "connectionId": "custom_connection_1",
                "source": "custom-openai",
                "group": "internal-only",
                "label": "Future backend",
                "baseUrl": context["baseUrl"],
                "key": "sk-synthetic-runtime-only",
                "enabled": True,
            }]

        connections = server._model_route_connections(
            {"baseUrl": "https://synthetic.invalid", "future": True},
            backends=(("custom-openai", collect_custom),),
        )
        self.assertEqual(len(connections), 1)
        self.assertEqual(connections[0]["source"], "custom-openai")
        self.assertEqual(observed, {
            "bodyKeys": ["baseUrl", "future"],
            "contextKeys": ["baseUrl", "claimedKeys"],
        })

    def test_connection_backend_failures_are_isolated_and_sanitized(self):
        claimed_before_success = []

        def successful_backend(_body, context):
            claimed_before_success.append(set(context["claimedKeys"]))
            return [{
                "connectionId": "custom_connection_1",
                "source": "custom-openai",
                "group": "internal-only",
                "label": "Healthy connection",
                "baseUrl": context["baseUrl"],
                "key": "sk-synthetic-runtime-only",
                "enabled": True,
            }]

        def failing_backend(_body, context):
            context["claimedKeys"].add("sk-synthetic-must-rollback")
            raise server._WorkbarSyncFailure("tokens", "transport")

        for backends in (
            (("failing", failing_backend), ("healthy", successful_backend)),
            (("healthy", successful_backend), ("failing", failing_backend)),
        ):
            with self.subTest(order=[backend_id for backend_id, _collector in backends]):
                collection = server._model_route_connections(
                    {"baseUrl": "https://synthetic.invalid"},
                    backends=backends,
                    include_failures=True,
                )
                self.assertEqual(len(collection["connections"]), 1)
                self.assertEqual(
                    collection["connections"][0]["connectionId"],
                    "custom_connection_1",
                )
                self.assertNotIn("sk-synthetic-must-rollback", claimed_before_success[-1])
                self.assertEqual(collection["failures"], [{
                    "connectionId": "",
                    "code": "route_catalog_unavailable",
                }])
                serialized = json.dumps(collection["failures"])
                self.assertNotIn("workbar", serialized.lower())
                self.assertNotIn("transport", serialized.lower())
                self.assertNotIn("synthetic", serialized.lower())

        def auth_failure(_body, _context):
            raise server.error.HTTPError(
                "https://synthetic.invalid", 401, "secret upstream detail", None, None,
            )

        auth_collection = server._model_route_connections(
            {"baseUrl": "https://synthetic.invalid"},
            backends=(("auth", auth_failure),),
            include_failures=True,
        )
        self.assertEqual(auth_collection["connections"], [])
        self.assertEqual(auth_collection["failures"], [{
            "connectionId": "",
            "code": "route_credentials_unavailable",
        }])

    def test_real_workbar_and_manual_collectors_isolate_failures_both_directions(self):
        body = {
            "baseUrl": "https://synthetic.invalid",
            "platformAuth": {"token": "synthetic-auth", "userId": "7"},
            "manualConnections": [{
                "connectionId": "manual_11111111-1111-4111-8111-111111111111",
                "label": "Manual healthy",
                "key": "sk-synthetic-manual",
                "enabled": True,
            }],
        }
        with mock.patch.object(
            server,
            "_fetch_workbar_tokens_and_keys",
            side_effect=server._WorkbarSyncFailure("tokens", "transport"),
        ):
            manual_survives = server._model_route_connections(
                body,
                include_failures=True,
            )
        self.assertEqual(
            [item["source"] for item in manual_survives["connections"]],
            ["manual"],
        )
        self.assertEqual(manual_survives["failures"], [{
            "connectionId": "",
            "code": "route_catalog_unavailable",
        }])

        invalid_manual = {
            **body,
            "manualConnections": [{
                "connectionId": "invalid",
                "label": "Manual invalid",
                "key": "sk-synthetic-manual",
                "enabled": True,
            }],
        }
        with mock.patch.object(
            server,
            "_fetch_workbar_tokens_and_keys",
            return_value=([{
                "id": 42,
                "name": "workbar healthy",
                "group": "default",
                "status": 1,
                "model_limits_enabled": False,
            }], {"42": "sk-synthetic-workbar"}),
        ):
            workbar_survives = server._model_route_connections(
                invalid_manual,
                include_failures=True,
            )
        self.assertEqual(
            [item["source"] for item in workbar_survives["connections"]],
            ["workbar"],
        )
        self.assertEqual(workbar_survives["failures"], [{
            "connectionId": "",
            "code": "route_catalog_unavailable",
        }])

    def test_workbar_collector_honors_enabled_platform_token_ids(self):
        body = {
            "baseUrl": "https://synthetic.invalid",
            "platformAuth": {
                "token": "synthetic-auth",
                "userId": "7",
                "enabledTokenIds": ["42"],
            },
            "manualConnections": [],
        }
        with mock.patch.object(
            server,
            "_fetch_workbar_tokens_and_keys",
            return_value=([{
                "id": 42,
                "name": "kept",
                "group": "default",
                "status": 1,
                "model_limits_enabled": False,
            }, {
                "id": 43,
                "name": "revoked",
                "group": "default",
                "status": 1,
                "model_limits_enabled": False,
            }], {
                "42": "sk-synthetic-kept",
                "43": "sk-synthetic-revoked",
            }),
        ):
            collection = server._model_route_connections(
                body,
                include_failures=True,
            )

        self.assertEqual(collection["failures"], [])
        self.assertEqual(len(collection["connections"]), 1)
        self.assertEqual(collection["connections"][0]["label"], "kept")
        self.assertEqual(collection["connections"][0]["key"], "sk-synthetic-kept")

    def test_empty_enabled_platform_token_ids_clear_without_upstream_fetch(self):
        body = {
            "baseUrl": "https://synthetic.invalid",
            "platformAuth": {
                "token": "synthetic-auth",
                "userId": "7",
                "enabledTokenIds": [],
            },
            "manualConnections": [],
        }
        with mock.patch.object(
            server,
            "_fetch_workbar_tokens_and_keys",
            side_effect=AssertionError("empty platform selection must not fetch"),
        ) as fetch:
            collection = server._model_route_connections(
                body,
                include_failures=True,
            )

        fetch.assert_not_called()
        self.assertEqual(collection, {"connections": [], "failures": []})

    def test_model_route_refresh_empty_connections_authoritatively_clears_catalog(self):
        handler = self.handler("/api/model-routes/refresh", {
            "baseUrl": "https://synthetic.invalid",
            "manualConnections": [],
        })
        collection = {"connections": [], "failures": []}
        cleared = {
            "ok": True,
            "changed": True,
            "catalogRevision": 9,
            "routes": [],
            "successfulConnections": 0,
            "failedConnections": 0,
            "failures": [],
        }
        with mock.patch.object(server, "_MODEL_ROUTE_REGISTRY_ENABLED", True), \
             mock.patch.object(server, "_model_route_connections", return_value=collection), \
             mock.patch.object(server._model_route_registry, "refresh", return_value=cleared) as refresh:
            server.CodeHandler.do_POST(handler)

        refresh.assert_called_once()
        self.assertEqual(refresh.call_args.args[0], [])
        payload = handler.send_json.call_args.args[0]
        self.assertEqual(handler.send_json.call_args.kwargs, {})
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["routes"], [])
        self.assertEqual(payload["catalogRevision"], 9)

    def test_model_route_backend_failure_revokes_runtime_credentials(self):
        with tempfile.TemporaryDirectory() as tempdir:
            registry = server.ModelRouteRegistry(Path(tempdir) / "routes.json")
            first = registry.refresh(
                [{
                    "connectionId": "manual_11111111-1111-4111-8111-111111111111",
                    "source": "manual",
                    "group": "manual",
                    "label": "Synthetic",
                    "baseUrl": "https://synthetic.invalid",
                    "key": "sk-synthetic-secret",
                    "enabled": True,
                }],
                lambda _connection: ["model-a"],
            )
            route = first["routes"][0]
            handler = self.handler("/api/model-routes/refresh", {})
            collection = {
                "connections": [],
                "failures": [{"connectionId": "", "code": "route_catalog_unavailable"}],
            }
            with mock.patch.object(server, "_MODEL_ROUTE_REGISTRY_ENABLED", True), \
                 mock.patch.object(server, "_model_route_registry", registry), \
                 mock.patch.object(server, "_model_route_connections", return_value=collection):
                server.CodeHandler.do_POST(handler)

            payload, status = handler.send_json.call_args.args
            self.assertEqual(status, 503)
            self.assertEqual(payload["errorCode"], "route_catalog_unavailable")
            serialized = json.dumps(payload)
            self.assertNotIn("sk-synthetic-secret", serialized)
            self.assertNotIn("https://synthetic.invalid", serialized)
            with self.assertRaises(server.ModelRouteError) as captured:
                registry.resolve(route["routeRef"], first["catalogRevision"], "model-a")
            self.assertEqual(captured.exception.code, "route_credentials_unavailable")

    def test_model_route_refresh_partial_backend_failure_returns_healthy_catalog(self):
        handler = self.handler("/api/model-routes/refresh", {})
        collection = {
            "connections": [{"connectionId": "manual_healthy"}],
            "failures": [{"connectionId": "", "code": "route_catalog_unavailable"}],
            "claimedKeys": set(),
        }
        refreshed = {
            "ok": True,
            "catalogRevision": 8,
            "routes": [{"routeRef": "mr1_opaque"}],
            "failedConnections": 0,
            "failures": [],
        }
        with mock.patch.object(server, "_MODEL_ROUTE_REGISTRY_ENABLED", True), \
             mock.patch.object(server, "_model_route_connections", return_value=collection), \
             mock.patch.object(server._model_route_registry, "refresh", return_value=refreshed) as refresh:
            server.CodeHandler.do_POST(handler)

        refresh.assert_called_once()
        payload = handler.send_json.call_args.args[0]
        self.assertEqual(handler.send_json.call_args.kwargs, {})
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["failedConnections"], 1)
        self.assertEqual(payload["failures"], [{
            "connectionId": "",
            "code": "route_catalog_unavailable",
        }])
        self.assertNotIn("workbar", json.dumps(payload).lower())

    def test_model_route_refresh_all_backend_failures_remains_fail_closed(self):
        cases = (
            ([{"connectionId": "", "code": "route_catalog_unavailable"}], "route_catalog_unavailable"),
            ([{"connectionId": "", "code": "route_credentials_unavailable"}], "route_credentials_unavailable"),
        )
        for failures, expected_code in cases:
            with self.subTest(failures=failures):
                handler = self.handler("/api/model-routes/refresh", {})
                collection = {
                    "connections": [],
                    "failures": failures,
                }
                revoked = {
                    "version": 1,
                    "catalogRevision": 7,
                    "routes": [],
                }
                with mock.patch.object(server, "_MODEL_ROUTE_REGISTRY_ENABLED", True), \
                     mock.patch.object(server, "_model_route_connections", return_value=collection), \
                     mock.patch.object(server._model_route_registry, "refresh") as refresh, \
                     mock.patch.object(
                         server._model_route_registry,
                         "revoke_runtime_bindings",
                         return_value=revoked,
                     ) as revoke:
                    server.CodeHandler.do_POST(handler)

                refresh.assert_not_called()
                revoke.assert_called_once_with()
                payload, status = handler.send_json.call_args.args
                self.assertEqual(status, 503)
                self.assertEqual(payload["errorCode"], expected_code)
                self.assertTrue(payload["retryable"])
                self.assertNotIn("workbar", json.dumps(payload).lower())


if __name__ == "__main__":
    unittest.main()
