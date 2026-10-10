#!/usr/bin/env python3
"""Check that a deployed Matter server refuses unauthenticated callers.

Sends requests with no credentials and reports which ones the server accepted. It never
sends a token or calls a tool, so it can't read or change the library.

    uv run scripts/check_unauthenticated_access.py https://<your-worker-url>

Exits 0 if every protected route refused the request, 1 if any accepted it.
"""

import sys

import httpx

# MCP needs an initialize handshake before tools/list.
_INITIALIZE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "unauthenticated-access-check", "version": "1"},
    },
}
_INITIALIZED = {"jsonrpc": "2.0", "method": "notifications/initialized"}
_TOOLS_LIST = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
_MCP_HEADERS = {"Accept": "application/json, text/event-stream"}


def _refused(status: int) -> bool:
    return status in (401, 403, 404, 405)


def check(base_url: str, client: httpx.Client) -> list[tuple[str, bool, str]]:
    """Return (check, passed, detail) rows."""
    base = base_url.rstrip("/")
    rows: list[tuple[str, bool, str]] = []

    health = client.get(f"{base}/worker/health")
    # Arcade documents the health route as unauthenticated, so it's informational only.
    rows.append(("GET /worker/health (may be public)", True, str(health.status_code)))

    tools = client.get(f"{base}/worker/tools")
    rows.append(("GET /worker/tools refused", _refused(tools.status_code), str(tools.status_code)))

    invoke = client.post(f"{base}/worker/tools/invoke", json={})
    rows.append(
        ("POST /worker/tools/invoke refused", _refused(invoke.status_code), str(invoke.status_code))
    )

    init = client.post(f"{base}/mcp/", json=_INITIALIZE, headers=_MCP_HEADERS)
    if _refused(init.status_code):
        rows.append(("MCP tools/list refused", True, f"initialize {init.status_code}"))
        return rows
    session = {**_MCP_HEADERS, "mcp-session-id": init.headers.get("mcp-session-id", "")}
    client.post(f"{base}/mcp/", json=_INITIALIZED, headers=session)
    listing = client.post(f"{base}/mcp/", json=_TOOLS_LIST, headers=session)
    exposed = listing.status_code == 200 and "Matter_" in listing.text
    rows.append(("MCP tools/list refused", not exposed, f"tools/list {listing.status_code}"))
    return rows


def main(argv: list[str]) -> int:
    url = argv[1] if len(argv) == 2 else ""
    local = url.startswith(("http://127.0.0.1", "http://localhost"))
    if not (url.startswith("https://") or local):
        print(__doc__)
        return 2
    with httpx.Client(timeout=15.0, follow_redirects=False) as client:
        rows = check(url, client)
    for name, passed, detail in rows:
        print(f"{'PASS' if passed else 'FAIL'}  {name}  ({detail})")
    return 0 if all(passed for _, passed, _ in rows) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
