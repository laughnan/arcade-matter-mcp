from types import SimpleNamespace

import httpx
import pytest
from arcade_mcp_server.exceptions import (
    RetryableToolError,
    ToolExecutionError,
    UpstreamError,
    UpstreamRateLimitError,
)

from arcade_matter import client as client_module
from arcade_matter.client import MatterClient, client_from_context


async def test_sends_bearer_token_and_returns_body(matter):
    matter.add("GET", "/me", {"object": "account", "id": "act_1"})

    data = await MatterClient("mat_abc").get("/me")

    assert data == {"object": "account", "id": "act_1"}
    assert matter.last.headers["Authorization"] == "Bearer mat_abc"
    assert matter.last.url.host == "api.getmatter.com"
    assert matter.last.url.path == "/public/v1/me"


async def test_encodes_params(matter):
    matter.add("GET", "/items", {"object": "list", "results": []})

    await MatterClient("t").get(
        "/items", status=["queue", "archive"], is_favorite=True, cursor=None, tag=[], limit=10
    )

    assert dict(matter.last.url.params) == {
        "status": "queue,archive",
        "is_favorite": "true",
        "limit": "10",
    }


async def test_sends_json_body(matter):
    matter.add("PATCH", "/items/itm_1", {"object": "item", "id": "itm_1"})

    await MatterClient("t").patch("/items/itm_1", {"status": "archive"})

    assert matter.last_json() == {"status": "archive"}


async def test_no_content_returns_empty_dict(matter):
    matter.add("DELETE", "/tags/tag_1", None, status=204)

    assert await MatterClient("t").delete("/tags/tag_1") == {}


def test_client_from_context_reads_secret():
    context = SimpleNamespace(get_secret=lambda key: "mat_x" if key == "MATTER_API_TOKEN" else "")

    assert isinstance(client_from_context(context), MatterClient)


@pytest.mark.parametrize(
    "get_secret", [lambda key: "", lambda key: (_ for _ in ()).throw(ValueError)]
)
def test_missing_secret_raises(get_secret):
    with pytest.raises(ToolExecutionError, match="MATTER_API_TOKEN secret is not set"):
        client_from_context(SimpleNamespace(get_secret=get_secret))


@pytest.mark.parametrize(
    ("status", "code", "exc_type", "message"),
    [
        (400, "bad_request", RetryableToolError, "rejected the request: bad url"),
        (422, "validation_error", RetryableToolError, r"bad url \(field: url\)"),
        (401, "unauthorized", ToolExecutionError, "invalid or was revoked"),
        (403, "forbidden", ToolExecutionError, "Matter Pro"),
        (404, "not_found", RetryableToolError, "could not find"),
        (409, "conflict", RetryableToolError, "conflicts with existing"),
        (500, "internal_error", UpstreamError, r"returned an error \(500\)"),
    ],
)
async def test_error_mapping(matter, status, code, exc_type, message):
    field = "url" if status == 422 else ""
    matter.error("GET", "/me", status, code, "bad url", field)

    with pytest.raises(exc_type, match=message) as raised:
        await MatterClient("t").get("/me")

    assert code in (raised.value.developer_message or "")


async def test_auth_errors_are_not_retryable(matter):
    matter.error("GET", "/me", 401, "unauthorized", "nope")

    with pytest.raises(ToolExecutionError) as raised:
        await MatterClient("t").get("/me")

    assert not isinstance(raised.value, RetryableToolError)


async def test_short_rate_limit_waits_and_retries_once(matter, sleeps):
    matter.add(
        "GET", "/me", {"error": {"code": "rate_limited"}}, status=429, headers={"Retry-After": "1"}
    )
    matter.add("GET", "/me", {"object": "account", "id": "act_1"})

    data = await MatterClient("t").get("/me")

    assert data["id"] == "act_1"
    assert sleeps == [1.0]
    assert len(matter.requests) == 2


async def test_rate_limit_retries_only_once(matter, sleeps):
    matter.add(
        "GET", "/me", {"error": {"code": "rate_limited"}}, status=429, headers={"Retry-After": "2"}
    )

    with pytest.raises(UpstreamRateLimitError) as raised:
        await MatterClient("t").get("/me")

    assert raised.value.retry_after_ms == 2_000
    assert sleeps == [2.0]
    assert len(matter.requests) == 2


async def test_long_rate_limit_raises_without_waiting(matter, sleeps):
    matter.add(
        "GET", "/me", {"error": {"code": "rate_limited"}}, status=429, headers={"Retry-After": "45"}
    )

    with pytest.raises(UpstreamRateLimitError) as raised:
        await MatterClient("t").get("/me")

    assert raised.value.retry_after_ms == 45_000
    assert sleeps == []
    assert len(matter.requests) == 1


async def test_rate_limit_without_retry_after_uses_default(matter, sleeps):
    matter.add("GET", "/me", {"error": {"code": "rate_limited"}}, status=429)

    with pytest.raises(UpstreamRateLimitError) as raised:
        await MatterClient("t").get("/me")

    assert raised.value.retry_after_ms == client_module.DEFAULT_RETRY_AFTER_MS
    assert sleeps == []


@pytest.mark.parametrize("body", ["Service Unavailable", ["unexpected"], {"error": "oops"}])
async def test_unexpected_error_body(matter, body):
    matter.add("GET", "/me", body, status=503)

    with pytest.raises(UpstreamError, match=r"\(503\)"):
        await MatterClient("t").get("/me")


async def test_html_error_body(monkeypatch):
    monkeypatch.setattr(
        client_module,
        "TRANSPORT",
        httpx.MockTransport(lambda request: httpx.Response(502, text="<html>Bad Gateway</html>")),
    )

    with pytest.raises(UpstreamError, match=r"\(502\)"):
        await MatterClient("t").get("/me")


async def test_records_status_and_headers(matter):
    matter.add(
        "POST",
        "/items",
        {"object": "item", "id": "itm_1"},
        status=201,
        headers={"X-RateLimit-Remaining": "9"},
    )

    client = MatterClient("t")
    await client.post("/items", {"url": "https://example.com"})

    assert client.last_status == 201
    assert client.rate_limit_status() == {"remaining": 9}


async def test_non_json_success_body_is_upstream_error(monkeypatch):
    monkeypatch.setattr(
        client_module,
        "TRANSPORT",
        httpx.MockTransport(lambda request: httpx.Response(200, text="<html>Login</html>")),
    )

    with pytest.raises(UpstreamError, match="unreadable response"):
        await MatterClient("t").get("/me")
