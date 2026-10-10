#!/usr/bin/env python3
"""Check that a deployed Matter server refuses unauthenticated callers.

Sends requests with no credentials and reports which ones the server accepted. It never
sends a token or calls a tool, so it can't read or change the library.

    uv run scripts/check_unauthenticated_access.py https://<your-worker-url>

Exits 0 if the URL is a worker and every protected route refused the request, and 1
otherwise. Exit 0 only means these anonymous probes were refused. It doesn't show that only
the token owner can call the tools; that depends on the dashboard checks in
docs/security/live-verification.md.
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


# Statuses that mean a route refused an anonymous caller. 404 and 405 only count once
# /worker/health has shown the URL is really a worker, so a wrong host can't pass.
_REFUSED = (401, 403, 404, 405)


def check(base_url: str, client: httpx.Client) -> list[tuple[str, bool, str]]:
    """Return (check, passed, detail) rows."""
    base = base_url.rstrip("/")
    rows: list[tuple[str, bool, str]] = []

    # Arcade documents the health route as unauthenticated on a real worker, so it's the
    # liveness check: without it, a typo or a gateway URL would 404 everything and "pass".
    health = client.get(f"{base}/worker/health")
    is_worker = health.status_code == 200
    rows.append(
        ("GET /worker/health answers (this is a worker)", is_worker, str(health.status_code))
    )
    if not is_worker:
        return rows

    tools = client.get(f"{base}/worker/tools")
    rows.append(
        ("GET /worker/tools refused", tools.status_code in _REFUSED, str(tools.status_code))
    )

    invoke = client.post(f"{base}/worker/tools/invoke", json={})
    rows.append(
        (
            "POST /worker/tools/invoke refused",
            invoke.status_code in _REFUSED,
            str(invoke.status_code),
        )
    )

    # /mcp should be refused or not served at all. If it accepts an anonymous initialize,
    # it counts as exposed unless tools/list itself is refused: a 400, 406 or JSON-RPC
    # error after a successful initialize still means the route is reachable.
    init = client.post(f"{base}/mcp/", json=_INITIALIZE, headers=_MCP_HEADERS)
    if init.status_code in _REFUSED:
        rows.append(("MCP route refused", True, f"initialize {init.status_code}"))
        return rows
    session = {**_MCP_HEADERS, "mcp-session-id": init.headers.get("mcp-session-id", "")}
    client.post(f"{base}/mcp/", json=_INITIALIZED, headers=session)
    listing = client.post(f"{base}/mcp/", json=_TOOLS_LIST, headers=session)
    rows.append(
        (
            "MCP route refused",
            listing.status_code in _REFUSED,
            f"initialize {init.status_code}, tools/list {listing.status_code}",
        )
    )
    return rows


def main(argv: list[str]) -> int:
    url = argv[1] if len(argv) == 2 else ""
    local = url.startswith(("http://127.0.0.1", "http://localhost"))
    if not (url.startswith("https://") or local):
        print(__doc__)
        return 2
    try:
        with httpx.Client(timeout=15.0, follow_redirects=False) as client:
            rows = check(url, client)
    except httpx.HTTPError as exc:
        print(f"FAIL  could not reach {url}: {exc}")
        return 1
    for name, passed, detail in rows:
        print(f"{'PASS' if passed else 'FAIL'}  {name}  ({detail})")
    return 0 if all(passed for _, passed, _ in rows) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
