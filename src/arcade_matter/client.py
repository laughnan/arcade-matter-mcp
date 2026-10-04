"""Thin async client for the Matter public API.

Every tool builds a client from its ``Context`` so the ``MATTER_API_TOKEN`` secret is used.
Non-2xx responses are translated into Arcade errors with messages a model can act on.
"""

import asyncio
from typing import Any

import httpx
from arcade_mcp_server.exceptions import (
    RetryableToolError,
    ToolExecutionError,
    UpstreamError,
    UpstreamRateLimitError,
)

BASE_URL = "https://api.getmatter.com/public/v1"
SECRET_NAME = "MATTER_API_TOKEN"
TIMEOUT_SECONDS = 30.0
DEFAULT_RETRY_AFTER_MS = 60_000
# A 429 asking us to wait this long or less is the 5 requests/second burst limit; wait it
# out once. Longer waits are per-minute buckets and are surfaced to the caller.
MAX_INLINE_RETRY_SECONDS = 5.0

# Overridden in tests with an httpx.MockTransport; None means real network access.
TRANSPORT: httpx.AsyncBaseTransport | None = None


class MatterClient:
    def __init__(self, token: str) -> None:
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "arcade-matter-mcp",
        }

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send a request and return the decoded JSON body (``{}`` for 204 No Content).

        Honours ``Retry-After``: a short wait is slept through and the request retried
        once; anything longer raises ``UpstreamRateLimitError``.
        """
        query = _encode_params(params)
        async with httpx.AsyncClient(
            base_url=BASE_URL,
            headers=self._headers,
            timeout=TIMEOUT_SECONDS,
            transport=TRANSPORT,
        ) as client:
            response = await client.request(method, path, params=query, json=json)
            if response.status_code == 429:
                wait_ms = _retry_after_ms(response)
                if wait_ms <= MAX_INLINE_RETRY_SECONDS * 1000:
                    await asyncio.sleep(wait_ms / 1000)
                    response = await client.request(method, path, params=query, json=json)
        if response.is_error:
            _raise_for_error(response)
        if response.status_code == 204 or not response.content:
            return {}
        body = response.json()
        return body if isinstance(body, dict) else {}

    async def get(self, path: str, **params: Any) -> dict[str, Any]:
        return await self.request("GET", path, params=params)

    async def post(self, path: str, json: dict[str, Any]) -> dict[str, Any]:
        return await self.request("POST", path, json=json)

    async def patch(self, path: str, json: dict[str, Any]) -> dict[str, Any]:
        return await self.request("PATCH", path, json=json)

    async def delete(self, path: str) -> dict[str, Any]:
        return await self.request("DELETE", path)


def client_from_context(context: Any) -> MatterClient:
    try:
        token = context.get_secret(SECRET_NAME)
    except ValueError:
        token = ""
    if not token:
        raise ToolExecutionError(
            f"The {SECRET_NAME} secret is not set.",
            developer_message=(
                f"Set {SECRET_NAME} in .env for local runs, or run "
                f"`arcade secret set {SECRET_NAME}=mat_...` for the deployed server."
            ),
        )
    return MatterClient(token)


def _encode_params(params: dict[str, Any] | None) -> dict[str, str]:
    """Drop ``None`` values, lowercase booleans and comma-join lists (Matter's OR syntax)."""
    out: dict[str, str] = {}
    for key, value in (params or {}).items():
        if value is None:
            continue
        if isinstance(value, bool):
            out[key] = "true" if value else "false"
        elif isinstance(value, (list, tuple)):
            if value:
                out[key] = ",".join(str(v) for v in value)
        else:
            out[key] = str(value)
    return out


def _error_details(response: httpx.Response) -> tuple[str, str, str]:
    """Return Matter's (code, message, field) error triple, tolerating non-JSON bodies."""
    try:
        body = response.json()
    except ValueError:
        body = None
    error = body.get("error") if isinstance(body, dict) else None
    if not isinstance(error, dict):
        error = {}
    return (
        str(error.get("code") or response.status_code),
        str(error.get("message") or ""),
        str(error.get("field") or ""),
    )


def _raise_for_error(response: httpx.Response) -> None:
    # Matter's docs and OpenAPI examples disagree on error codes, so key on HTTP status.
    status = response.status_code
    code, message, field = _error_details(response)
    request = response.request
    dev = f"Matter {request.method} {request.url.path} -> {status} {code}: {message}"
    if field:
        dev += f" (field: {field})"

    if status in (400, 422):
        detail = f"{message} (field: {field})" if field else message
        raise RetryableToolError(
            f"Matter rejected the request: {detail or 'validation failed'}",
            developer_message=dev,
            additional_prompt_content="Fix the invalid parameters described above and retry.",
        )
    if status == 401:
        raise ToolExecutionError(
            "Matter rejected the API token. It is invalid or was revoked (generating a new "
            f"token revokes the old one). Update the {SECRET_NAME} secret.",
            developer_message=dev,
        )
    if status == 403:
        raise ToolExecutionError(
            "Matter refused the request. The API needs an active Matter Pro subscription.",
            developer_message=dev,
        )
    if status == 404:
        raise RetryableToolError(
            f"Matter could not find that resource: {message or 'not found'}",
            developer_message=dev,
            additional_prompt_content=(
                "Check the IDs used. List or search items, highlights or tags to find valid "
                "IDs, then retry."
            ),
        )
    if status == 409:
        raise RetryableToolError(
            f"That conflicts with existing Matter data: {message or 'conflict'}",
            developer_message=dev,
            additional_prompt_content="Choose a different value (for example a new tag name).",
        )
    if status == 429:
        raise UpstreamRateLimitError(
            "Matter's rate limit was reached. Wait before making more Matter requests.",
            retry_after_ms=_retry_after_ms(response),
            developer_message=dev,
        )
    raise UpstreamError(
        f"Matter returned an error ({status}): {message or 'unexpected error'}",
        developer_message=dev,
        status_code=status,
    )


def _retry_after_ms(response: httpx.Response) -> int:
    try:
        return max(0, int(float(response.headers["Retry-After"]) * 1000))
    except (KeyError, ValueError):
        return DEFAULT_RETRY_AFTER_MS
