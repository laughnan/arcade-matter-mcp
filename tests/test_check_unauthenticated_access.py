"""The live-verification script, against mocked servers. Nothing here hits the network."""

import importlib.util
from pathlib import Path

import httpx
import pytest

_PATH = Path(__file__).resolve().parents[1] / "scripts" / "check_unauthenticated_access.py"
_spec = importlib.util.spec_from_file_location("check_unauthenticated_access", _PATH)
assert _spec and _spec.loader
script = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(script)

LISTING = '{"jsonrpc":"2.0","id":2,"result":{"tools":[{"name":"Matter_GetAccount"}]}}'


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _results(handler) -> dict[str, bool]:
    with _client(handler) as client:
        return {name: passed for name, passed, _ in script.check("https://w.example", client)}


def test_protected_server_passes():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/worker/health":
            return httpx.Response(200, json={"status": "ok"})
        assert "authorization" not in request.headers
        return httpx.Response(401)

    assert all(_results(handler).values())


def test_worker_with_mcp_not_served_passes():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/worker/health":
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(404 if request.url.path == "/mcp/" else 401)

    assert all(_results(handler).values())


@pytest.mark.parametrize("status", [404, 502, 401])
def test_url_that_is_not_a_worker_fails(status):
    # A typo, a gateway URL or a worker without its routes 404s everything.
    with _client(lambda r: httpx.Response(status)) as client:
        rows = script.check("https://w.example", client)

    assert [passed for _, passed, _ in rows] == [False]


def test_open_worker_routes_fail():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404 if request.url.path == "/mcp/" else 200, json={})

    results = _results(handler)
    assert results["GET /worker/tools refused"] is False
    assert results["POST /worker/tools/invoke refused"] is False
    assert results["MCP route refused"] is True


def _mcp_handler(tools_list: httpx.Response, session_id: str | None = "s1"):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/worker/health":
            return httpx.Response(200, json={"status": "ok"})
        if request.url.path.startswith("/worker/"):
            return httpx.Response(401)
        if b"tools/list" in request.content:
            return tools_list
        headers = {"mcp-session-id": session_id} if session_id else {}
        return httpx.Response(200, headers=headers, json={})

    return handler


@pytest.mark.parametrize(
    "tools_list",
    [
        httpx.Response(200, text=LISTING),
        httpx.Response(200, text='{"result":{"tools":[{"name":"Matter.GetAccount"}]}}'),
        httpx.Response(200, json={"jsonrpc": "2.0", "id": 2, "error": {"code": -32600}}),
        httpx.Response(400, text="Missing session ID"),
        httpx.Response(406, text="Not Acceptable"),
    ],
)
def test_reachable_mcp_route_fails(tools_list):
    assert _results(_mcp_handler(tools_list))["MCP route refused"] is False


def test_reachable_mcp_route_without_session_fails():
    handler = _mcp_handler(httpx.Response(400), session_id=None)
    assert _results(handler)["MCP route refused"] is False


def test_mcp_refusing_tools_list_passes():
    assert _results(_mcp_handler(httpx.Response(401)))["MCP route refused"] is True


def test_main_rejects_plain_http_to_remote_hosts():
    assert script.main(["x", "http://w.example"]) == 2
    assert script.main(["x"]) == 2
