import base64
import json

import httpx


def test_image_request_and_content():
    from image_clarus.providers.openai_compatible import OpenAICompatible

    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": " result \n"},
                        "finish_reason": "stop",
                    }
                ]
            },
        )

    adapter = OpenAICompatible(
        {
            "base_url": "https://example.test/v1/",
            "api_key": "dummy-key",
            "timeout_seconds": 7,
        },
        {"model_id": "vision"},
        transport=httpx.MockTransport(handler),
    )
    result = adapter.image(
        prompt="exact prompt\n", image_bytes=b"synthetic", suffix=".JPG"
    )
    assert result == " result \n"
    request = requests[0]
    assert str(request.url) == "https://example.test/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer dummy-key"
    assert (
        request.headers["accept"]
        == request.headers["content-type"]
        == "application/json"
    )
    body = json.loads(request.content)
    assert body == {
        "model": "vision",
        "messages": [
            {"role": "system", "content": "exact prompt\n"},
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "data:image/jpeg;base64,"
                            + base64.b64encode(b"synthetic").decode()
                        },
                    }
                ],
            },
        ],
        "stream": False,
        "n": 1,
    }
    assert request.extensions["timeout"] == dict.fromkeys(
        ("connect", "read", "write", "pool"), 7
    )


import logging
import traceback

import pytest

from image_clarus.providers.openai_compatible import OpenAICompatible, ProviderError


def response(content="ok"):
    return {
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ]
    }


def adapter(handler, provider=None, model=None, **kwargs):
    return OpenAICompatible(
        provider or {"base_url": "https://example.test/v1", "timeout_seconds": 2},
        model or {"model_id": "model"},
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


def test_json_parts_reasoning_and_retry_context():
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json=response("{}"))

    a = adapter(handler, model={"model_id": "json-model", "reasoning_effort": "high"})
    assert (
        a.structured(
            prompt="prompt\n",
            description="desc\n",
            schema={"$id": "urn:test", "type": "object"},
            effort="low",
            history=[("invalid", {"kind": "json_parse", "code": "invalid_json"})],
        )
        == "{}"
    )
    body = requests[0]
    assert body["model"] == "json-model"
    assert body["reasoning_effort"] == "low"
    assert body["response_format"] == {"type": "json_object"}
    assert body["messages"] == [
        {"role": "system", "content": "prompt\n"},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Persisted description:\ndesc\n"},
                {
                    "type": "text",
                    "text": 'Selected JSON Schema:\n{"$id": "urn:test", "type": "object"}',
                },
            ],
        },
        {"role": "assistant", "content": "invalid"},
        {"role": "user", "content": '{"kind": "json_parse", "code": "invalid_json"}'},
    ]


@pytest.mark.parametrize(
    ("suffix", "mime"),
    [
        (".jpeg", "image/jpeg"),
        (".png", "image/png"),
        (".WEBP", "image/webp"),
        (".tif", "image/tiff"),
        (".tiff", "image/tiff"),
    ],
)
def test_image_types(suffix, mime):
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json=response())

    assert (
        adapter(handler).image(prompt="p", image_bytes=b"bytes", suffix=suffix) == "ok"
    )
    assert (
        bodies[0]["messages"][1]["content"][0]["image_url"]["url"]
        == f"data:{mime};base64,Ynl0ZXM="
    )


def test_unknown_image_fails_before_request():
    a = adapter(lambda req: pytest.fail("unexpected request"))
    with pytest.raises(ProviderError) as exc:
        a.image(prompt="p", image_bytes=b"x", suffix=".gif")
    assert exc.value.category == "unsupported_image"


@pytest.mark.parametrize(
    ("status", "error", "category"),
    [
        (301, {}, "configuration"),
        (401, {}, "authentication"),
        (403, {}, "authentication"),
        (404, {"code": "model_not_found"}, "unknown_model"),
        (400, {"param": "model"}, "unknown_model"),
        (400, {"code": "invalid_image"}, "corrupt_image"),
        (400, {"code": "unsupported_image"}, "unsupported_image"),
        (413, {}, "unsupported_image"),
        (408, {}, "network_timeout"),
        (429, {}, "provider_unavailable"),
        (500, {}, "provider_unavailable"),
        (400, {"param": "response_format"}, "configuration"),
    ],
)
def test_status_mapping_and_no_retry(status, error, category):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(
            status, json={"error": error}, headers={"location": "https://other.test/"}
        )

    with pytest.raises(ProviderError) as exc:
        adapter(handler).image(prompt="p", image_bytes=b"x", suffix=".jpg")
    assert exc.value.category == category
    assert len(calls) == 1


@pytest.mark.parametrize(
    "payload",
    [
        b"not json",
        b'{"choices":[],"choices":[]}',
        b'{"choices":[],"x":NaN}',
        b'{"choices":[],"x":1e9999}',
        json.dumps({"choices": []}).encode(),
        json.dumps(
            {
                "choices": [
                    {
                        "index": 1,
                        "message": {"role": "assistant", "content": "x"},
                        "finish_reason": "stop",
                    }
                ]
            }
        ).encode(),
        json.dumps(
            {
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "user", "content": "x"},
                        "finish_reason": "stop",
                    }
                ]
            }
        ).encode(),
        json.dumps(
            {
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": None},
                        "finish_reason": "stop",
                    }
                ]
            }
        ).encode(),
        json.dumps(
            {
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "x",
                            "refusal": "private",
                        },
                        "finish_reason": "stop",
                    }
                ]
            }
        ).encode(),
        json.dumps(
            {
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": "x",
                            "tool_calls": [{}],
                        },
                        "finish_reason": "stop",
                    }
                ]
            }
        ).encode(),
        *[
            json.dumps(
                {
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": "x"},
                            "finish_reason": reason,
                        }
                    ]
                }
            ).encode()
            for reason in ("length", "tool_calls", "content_filter")
        ],
    ],
)
def test_invalid_envelopes(payload):
    with pytest.raises(ProviderError) as exc:
        adapter(
            lambda r: httpx.Response(
                200, content=payload, headers={"Content-Type": "application/json"}
            )
        ).image(prompt="p", image_bytes=b"x", suffix=".jpg")
    assert exc.value.category == "provider_unavailable"


def test_no_secret_in_errors_or_httpx_logs(caplog):
    secret = "dummy-secret-SENTINEL"

    def handler(request):
        assert request.headers["authorization"] == "Bearer " + secret
        raise httpx.ConnectError("sensitive exception " + secret, request=request)

    provider = {
        "base_url": "https://private-url.test/path-sentinel",
        "api_key": secret,
        "timeout_seconds": 2,
    }
    prompt = "prompt-sentinel"
    image = b"image-sentinel"
    with caplog.at_level(logging.DEBUG), pytest.raises(ProviderError) as exc:
        adapter(handler, provider).image(
            prompt=prompt, image_bytes=image, suffix=".jpg"
        )
    assert exc.value.category == "provider_unavailable"
    text = (
        "".join(traceback.format_exception(exc.value)) + caplog.text + repr(exc.value)
    )
    for value in (
        secret,
        "private-url.test",
        "path-sentinel",
        "prompt-sentinel",
        "image-sentinel",
        "sensitive exception",
    ):
        assert value not in text


@pytest.mark.parametrize(
    "url",
    [
        "relative",
        "http://example.test/v1",
        "https://user:pass@example.test/v1",
        "https://example.test/v1?",
        "https://example.test/v1#x",
        "https://example.test/v1/chat/completions",
        "ftp://localhost/v1",
    ],
)
def test_invalid_urls_no_request(url):
    a = adapter(
        lambda r: pytest.fail("request"), {"base_url": url, "timeout_seconds": 1}
    )
    with pytest.raises(ProviderError) as exc:
        a.image(prompt="p", image_bytes=b"x", suffix=".jpg")
    assert exc.value.category == "configuration"


def test_nonstring_endpoint_is_sanitized_without_transport():
    calls = []
    a = adapter(lambda request: calls.append(request), {"base_url": 12345})
    with pytest.raises(ProviderError) as exc:
        a.image(prompt="p", image_bytes=b"x", suffix=".jpg")
    assert exc.value.category == "configuration"
    assert exc.value.__context__ is None
    assert not calls


def test_invalid_httpx_url_is_sanitized_before_transport():
    url = "https://[v1.private-host-sentinel]/secret-path"
    calls = []
    a = adapter(lambda request: calls.append(request), {"base_url": url})
    with pytest.raises(ProviderError) as exc:
        a.image(prompt="p", image_bytes=b"x", suffix=".jpg")
    assert exc.value.category == "configuration"
    text = "".join(traceback.format_exception(exc.value))
    assert "private-host-sentinel" not in text and "secret-path" not in text
    assert not calls


def test_reasoning_mapping_precedence_and_omit():
    bodies = []

    def handler(r):
        bodies.append(json.loads(r.content))
        return httpx.Response(200, json=response())

    provider = {
        "base_url": "http://127.0.0.1/v1",
        "timeout_seconds": 1,
        "reasoning_effort_mapping": {
            "parameter": "provider_level",
            "values": {"high": "deep"},
        },
    }
    model = {
        "model_id": "m",
        "reasoning_effort": "high",
        "reasoning_effort_mapping": {
            "parameter": "model_level",
            "values": {"high": 42, "off": {"omit": True}},
        },
    }
    a = adapter(handler, provider, model)
    for effort in (None, "off", "default"):
        a.image(prompt="p", image_bytes=b"x", suffix=".jpg", effort=effort)
    assert bodies[0]["model_level"] == 42
    assert all("provider_level" not in b for b in bodies)
    assert all("model_level" not in b for b in bodies[1:])
    with pytest.raises(ProviderError) as exc:
        a.image(prompt="p", image_bytes=b"x", suffix=".jpg", effort="low")
    assert exc.value.category == "configuration"
    assert len(bodies) == 3


def test_missing_tls_ca_file_is_sanitized_before_network(tmp_path, monkeypatch, caplog):
    import socket

    path = tmp_path / "private-ca-path-sentinel"
    monkeypatch.setenv("SSL_CERT_FILE", str(path))
    monkeypatch.setattr(socket.socket, "connect", lambda *args: pytest.fail("network"))
    a = OpenAICompatible(
        {"base_url": "https://provider-sentinel.test", "api_key": "dummy-key-sentinel"},
        {"model_id": "model"},
    )
    prompt, image = "prompt-sentinel", b"image-sentinel"
    with caplog.at_level(logging.DEBUG), pytest.raises(ProviderError) as exc:
        a.image(prompt=prompt, image_bytes=image, suffix=".jpg")
    assert exc.value.category == "provider_unavailable"
    assert exc.value.__context__ is None
    text = "".join(traceback.format_exception(exc.value)) + caplog.text
    for sentinel in (
        "private-ca-path-sentinel",
        "provider-sentinel",
        "dummy-key-sentinel",
        "prompt-sentinel",
        "image-sentinel",
    ):
        assert sentinel not in text


def test_env_credential_missing_and_transport_timeout(monkeypatch):
    monkeypatch.delenv("DUMMY_PROVIDER_KEY", raising=False)
    provider = {
        "base_url": "https://example.test",
        "api_key_env": "DUMMY_PROVIDER_KEY",
        "timeout_seconds": 1,
    }
    calls = []

    def handler(r):
        calls.append(r)
        raise httpx.ReadTimeout("secret timeout", request=r)

    a = adapter(handler, provider)
    with pytest.raises(ProviderError) as exc:
        a.image(prompt="p", image_bytes=b"x", suffix=".jpg")
    assert exc.value.category == "authentication"
    assert not calls
    monkeypatch.setenv("DUMMY_PROVIDER_KEY", "dummy-key")
    with pytest.raises(ProviderError) as exc:
        a.image(prompt="p", image_bytes=b"x", suffix=".jpg")
    assert exc.value.category == "network_timeout"
    assert len(calls) == 1
    assert calls[0].headers["authorization"] == "Bearer dummy-key"
    assert exc.value.__context__ is None


def test_logs_suppressed_on_success_and_no_cross_request_leak(caplog):
    calls = []

    def handler(r):
        calls.append(r)
        return httpx.Response(200, json=response(""))

    with caplog.at_level(logging.DEBUG):
        a = adapter(
            handler,
            {
                "base_url": "https://secret-host.test/private-path",
                "api_key": "dummy-secret",
                "timeout_seconds": 1,
            },
            {"model_id": "one"},
        )
        b = adapter(
            handler,
            {"base_url": "https://second.test/v1", "timeout_seconds": 1},
            {"model_id": "two"},
        )
        assert a.image(prompt="secret-prompt", image_bytes=b"x", suffix=".jpg") == ""
        assert (
            b.structured(
                prompt="other",
                description="private-description",
                schema={"type": "object"},
            )
            == ""
        )
    assert "authorization" not in calls[1].headers
    assert json.loads(calls[0].content)["model"] == "one"
    assert json.loads(calls[1].content)["model"] == "two"
    assert all(
        x not in caplog.text
        for x in (
            "secret-host.test",
            "private-path",
            "dummy-secret",
            "secret-prompt",
            "private-description",
        )
    )


def test_httpcore_trace_filtered_only_during_provider_request(caplog):
    from httpcore._trace import Trace

    def handler(request):
        with Trace(
            "connect_tcp",
            logging.getLogger("httpcore.connection"),
            kwargs={"host": "trace-host-sentinel"},
        ):
            pass
        return httpx.Response(200, json=response())

    with caplog.at_level(logging.DEBUG):
        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            client.get("https://outside-sentinel.test/")
        assert "trace-host-sentinel" in caplog.text
        caplog.clear()
        assert (
            adapter(handler).image(prompt="p", image_bytes=b"x", suffix=".jpg") == "ok"
        )
        assert "trace-host-sentinel" not in caplog.text


def test_wrong_media_type_rejected():
    with pytest.raises(ProviderError) as exc:
        adapter(
            lambda r: httpx.Response(
                200,
                content=json.dumps(response()),
                headers={"content-type": "text/plain"},
            )
        ).image(prompt="p", image_bytes=b"x", suffix=".jpg")
    assert exc.value.category == "provider_unavailable"


def test_malformed_message_object_never_escapes_as_attribute_error():
    payload = {"choices": [{"index": 0, "message": [], "finish_reason": "stop"}]}
    with pytest.raises(ProviderError) as exc:
        adapter(lambda r: httpx.Response(200, json=payload)).image(
            prompt="p", image_bytes=b"x", suffix=".jpg"
        )
    assert exc.value.category == "provider_unavailable"


def test_error_exception_context_never_retains_provider_data():
    payload = b'{"choices": "private-body-sentinel"}'
    with pytest.raises(ProviderError) as exc:
        adapter(
            lambda r: httpx.Response(
                200, content=payload, headers={"content-type": "application/json"}
            )
        ).image(prompt="p", image_bytes=b"x", suffix=".jpg")
    assert exc.value.__context__ is None
