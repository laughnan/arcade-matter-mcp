"""The live-verification script, against mocked servers. Nothing here hits the network."""

import importlib.util
from pathlib import Path

import httpx

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


def test_open_worker_routes_fail():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404 if request.url.path == "/mcp/" else 200, json={})

    results = _results(handler)
    assert results["GET /worker/tools refused"] is False
    assert results["POST /worker/tools/invoke refused"] is False
    assert results["MCP tools/list refused"] is True


def test_open_mcp_tool_listing_fails():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/worker/") and request.url.path != "/worker/health":
            return httpx.Response(401)
        if b"tools/list" in request.content:
            return httpx.Response(200, text=LISTING)
        return httpx.Response(200, headers={"mcp-session-id": "s1"}, json={})

    assert _results(handler)["MCP tools/list refused"] is False


def test_main_rejects_plain_http_to_remote_hosts(capsys):
    assert script.main(["x", "http://w.example"]) == 2
    assert script.main(["x"]) == 2
