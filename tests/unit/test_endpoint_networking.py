import json
import socket
import threading
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx
import pytest

from image_clarus.config import ConfigurationError, resolve_config
from image_clarus.endpoint import validate_base_url
from image_clarus.providers.openai_compatible import OpenAICompatible, ProviderError


def assert_rejected_by_config_and_adapter(raw, tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "providers": {"p": {"base_url": raw}},
                "models": {"m": {"provider": "p", "model_id": "m"}},
                "stages": {"desc": {"model": "m"}},
            }
        )
    )
    with pytest.raises(ConfigurationError):
        resolve_config(config_file=path, stages=("desc",))
    calls = []

    def handler(req):
        calls.append(req)
        return httpx.Response(500)

    adapter = OpenAICompatible(
        {"base_url": raw},
        {"model_id": "m"},
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ProviderError) as exc:
        adapter.image(prompt="p", image_bytes=b"x", suffix=".jpg")
    assert exc.value.category == "configuration"
    assert not calls


@pytest.mark.parametrize(
    "path", ["/v1/chat/completions/.", "/v1/chat/completions/extra/.."]
)
def test_normalized_complete_endpoint_is_rejected(path, tmp_path):
    assert_rejected_by_config_and_adapter("http://service.test" + path, tmp_path)


@pytest.mark.parametrize("raw", [r"http://bad\host/v1", r"https://bad\host:8080/v1"])
def test_backslash_in_authority_is_rejected(raw, tmp_path):
    assert_rejected_by_config_and_adapter(raw, tmp_path)


def test_http_dns_hostname_reaches_transport():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "ok"},
                        "finish_reason": "stop",
                    }
                ]
            },
        )

    adapter = OpenAICompatible(
        {"base_url": "http://service.test/v1"},
        {"model_id": "sample-model"},
        transport=httpx.MockTransport(handler),
    )
    assert adapter.image(prompt="p", image_bytes=b"x", suffix=".jpg") == "ok"
    assert str(requests[0].url) == "http://service.test/v1/chat/completions"


@pytest.mark.parametrize("scheme", ["http", "https"])
@pytest.mark.parametrize(
    "host",
    [
        "localhost",
        "service",
        "service.example.test",
        "service_name",
        "service.example.test.",
        "münchen.example",
        "-bad..host",
        "192.0.2.42",
        "[::1]",
        "[2001:db8::42]",
    ],
)
def test_endpoint_hosts_reach_mock_transport_without_dns(
    scheme, host, monkeypatch, tmp_path
):
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *a, **k: pytest.fail("DNS in preflight")
    )
    raw = f"{scheme}://{host}:8080/v1/"
    expected = raw.rstrip("/") + "/chat/completions"
    assert validate_base_url(raw) == expected
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "providers": {"p": {"base_url": raw}},
                "models": {"m": {"provider": "p", "model_id": "m"}},
                "stages": {"desc": {"model": "m"}},
            }
        )
    )
    config = resolve_config(config_file=config_path, stages=("desc",))
    assert config["providers"]["p"]["base_url"] == raw
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "ok"},
                        "finish_reason": "stop",
                    }
                ]
            },
        )

    a = OpenAICompatible(
        {"base_url": raw},
        {"model_id": "sample-model"},
        transport=httpx.MockTransport(handler),
    )
    assert a.image(prompt="p", image_bytes=b"x", suffix=".jpg") == "ok"
    assert str(requests[0].url) == str(httpx.URL(expected))


@pytest.mark.parametrize(
    "raw",
    [
        None,
        42,
        "relative",
        "ftp://service.test/v1",
        "http://user:secret@service.test/v1",
        "http://service.test/v1?",
        "http://service.test/v1#",
        "http://service.test/v1/chat/completions/",
        "http://service.test:abc/v1",
        "http://service.test:65536/v1",
        "http://service.test:１２/v1",
        "http://[v1.secret-host]/secret-path",
        "http://service.test/a b",
    ],
)
def test_invalid_url_is_static_and_never_requests(raw):
    with pytest.raises(ValueError) as exc:
        validate_base_url(raw)
    assert str(exc.value) == "Invalid provider base URL"
    assert exc.value.__context__ is None
    calls = []
    a = OpenAICompatible(
        {"base_url": raw},
        {"model_id": "sample-model"},
        transport=httpx.MockTransport(lambda req: calls.append(req)),
    )
    with pytest.raises(ProviderError) as exc:
        a.image(prompt="p", image_bytes=b"x", suffix=".jpg")
    assert exc.value.category == "configuration"
    assert exc.value.__context__ is None
    assert "secret" not in "".join(traceback.format_exception(exc.value))
    assert not calls


def test_port_zero_and_unicode_hostname_preserve_existing_syntax():
    assert (
        validate_base_url("http://service.test:0/v1")
        == "http://service.test:0/v1/chat/completions"
    )
    assert (
        validate_base_url("https://münchen.example/v1")
        == "https://münchen.example/v1/chat/completions"
    )


def clear_proxy_environment(monkeypatch):
    for key in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "NO_PROXY",
        "no_proxy",
    ):
        monkeypatch.delenv(key, raising=False)


def test_real_hostname_resolution_to_loopback_request(monkeypatch):
    clear_proxy_environment(monkeypatch)
    requests = []
    resolutions = []
    original = socket.getaddrinfo

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            requests.append(
                (
                    self.path,
                    self.headers["Host"],
                    self.rfile.read(int(self.headers["Content-Length"])),
                )
            )
            body = json.dumps(
                {
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": "ok"},
                            "finish_reason": "stop",
                        }
                    ]
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_port
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def resolver(host, requested_port, *args, **kwargs):
        assert host == "loopback.example.test"
        resolutions.append((host, requested_port))
        return original("127.0.0.1", requested_port, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", resolver)
    try:
        a = OpenAICompatible(
            {
                "base_url": f"http://loopback.example.test:{port}/v1",
                "timeout_seconds": 2,
            },
            {"model_id": "sample-model"},
        )
        assert a.image(prompt="p", image_bytes=b"x", suffix=".jpg") == "ok"
        assert resolutions == [("loopback.example.test", port)]
        assert len(requests) == 1
        assert requests[0][0] == "/v1/chat/completions"
        assert requests[0][1] == f"loopback.example.test:{port}"
        assert json.loads(requests[0][2])["model"] == "sample-model"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_request_time_dns_failure_is_provider_unavailable(monkeypatch):
    clear_proxy_environment(monkeypatch)
    calls = []

    def resolver(host, port, *args, **kwargs):
        calls.append(host)
        raise socket.gaierror("synthetic DNS failure")

    monkeypatch.setattr(socket, "getaddrinfo", resolver)
    a = OpenAICompatible(
        {"base_url": "http://missing.example.test/v1", "timeout_seconds": 2},
        {"model_id": "sample-model"},
    )
    with pytest.raises(ProviderError) as exc:
        a.image(prompt="p", image_bytes=b"x", suffix=".jpg")
    assert calls == ["missing.example.test"]
    assert exc.value.category == "provider_unavailable"
    assert exc.value.__context__ is None
    assert "synthetic DNS failure" not in "".join(traceback.format_exception(exc.value))
