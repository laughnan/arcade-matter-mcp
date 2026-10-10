"""Thin async client for the Matter public API.

Every tool builds a client from its ``Context`` so the ``MATTER_API_TOKEN`` secret is used.
Non-2xx responses are translated into Arcade errors with messages a model can act on.
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, NoReturn

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
# The most response body (after decompression) read from Matter. Bodies are streamed and
# the read stops as soon as this is passed, so an oversized or endless response can't
# exhaust memory. Output limits such as GetItemContent's max_chars apply afterwards and
# bound what the model sees, not what the server buffers. 10 MiB fits a book-length
# article's Markdown with room to spare.
MAX_RESPONSE_BYTES = 10 * 1024 * 1024

# Overridden in tests with an httpx.MockTransport; None means real network access.
TRANSPORT: httpx.AsyncBaseTransport | None = None


class MatterClient:
    def __init__(self, token: str) -> None:
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "User-Agent": "arcade-matter-mcp",
        }
        # Status code and headers of the most recent response. Tools read these for things
        # the body doesn't carry: created vs existing (201/200) and rate-limit headroom.
        self.last_status: int | None = None
        self.last_headers: httpx.Headers = httpx.Headers()

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
        once; anything longer raises ``UpstreamRateLimitError``. A body larger than
        ``MAX_RESPONSE_BYTES`` raises ``ToolExecutionError`` without being fully read.
        """
        query = _encode_params(params)
        async with httpx.AsyncClient(
            base_url=BASE_URL,
            headers=self._headers,
            timeout=TIMEOUT_SECONDS,
            transport=TRANSPORT,
        ) as client:
            request = client.build_request(method, path, params=query, json=json)
            response = await _send_limited(client, request)
            if response.status_code == 429:
                wait_ms = _retry_after_ms(response)
                if wait_ms <= MAX_INLINE_RETRY_SECONDS * 1000:
                    await asyncio.sleep(wait_ms / 1000)
                    request = client.build_request(method, path, params=query, json=json)
                    response = await _send_limited(client, request)
        self.last_status = response.status_code
        self.last_headers = response.headers
        if response.is_error:
            _raise_for_error(response)
        if response.status_code == 204 or not response.content:
            return {}
        try:
            body = response.json()
        except ValueError:
            request = response.request
            raise UpstreamError(
                f"Matter returned an unreadable response ({response.status_code}).",
                developer_message=(
                    f"Matter {request.method} {request.url.path} -> {response.status_code} "
                    "with a non-JSON body"
                ),
                status_code=response.status_code,
            ) from None
        return body if isinstance(body, dict) else {}

    def rate_limit_status(self) -> dict[str, Any] | None:
        """The rate-limit bucket the last request counted against, from its headers."""
        headers = self.last_headers
        if "X-RateLimit-Remaining" not in headers:
            return None
        status: dict[str, Any] = {}
        for key, header in (("limit", "X-RateLimit-Limit"), ("remaining", "X-RateLimit-Remaining")):
            try:
                status[key] = int(headers[header])
            except (KeyError, ValueError):
                continue
        try:
            reset = datetime.fromtimestamp(int(headers["X-RateLimit-Reset"]), timezone.utc)
            status["resets_at"] = reset.strftime("%Y-%m-%dT%H:%M:%SZ")
        except (KeyError, ValueError, OverflowError, OSError):
            pass
        return status or None

    async def get(self, path: str, **params: Any) -> dict[str, Any]:
        return await self.request("GET", path, params=params)

    async def post(self, path: str, json: dict[str, Any]) -> dict[str, Any]:
        return await self.request("POST", path, json=json)

    async def patch(self, path: str, json: dict[str, Any]) -> dict[str, Any]:
        return await self.request("PATCH", path, json=json)

    async def delete(self, path: str, *, missing_ok: bool = False) -> dict[str, Any] | None:
        """DELETE ``path``. With ``missing_ok``, a 404 returns ``None`` instead of raising, so
        repeating a delete that already succeeded isn't reported as a failure."""
        try:
            return await self.request("DELETE", path)
        except RetryableToolError:
            if missing_ok and self.last_status == 404:
                return None
            raise


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


async def _send_limited(client: httpx.AsyncClient, request: httpx.Request) -> httpx.Response:
    """Send ``request`` and read at most ``MAX_RESPONSE_BYTES`` of its decoded body.

    Returns a fully read response. Raises ``ToolExecutionError`` as soon as the declared
    Content-Length or the bytes actually received pass the limit; the connection is closed
    either way.
    """
    response = await client.send(request, stream=True)
    chunks: list[bytes] = []
    try:
        declared = response.headers.get("Content-Length", "")
        # Content-Length counts encoded bytes, so it can only prove a body is too big.
        if declared.isdigit() and int(declared) > MAX_RESPONSE_BYTES:
            _raise_too_large(request, response.status_code, f"Content-Length {declared}")
        received = 0
        async for chunk in response.aiter_bytes():
            received += len(chunk)
            if received > MAX_RESPONSE_BYTES:
                _raise_too_large(request, response.status_code, f"over {received} bytes")
            chunks.append(chunk)
    finally:
        await response.aclose()
    # The chunks are already decoded, so drop the headers that describe the encoded body.
    headers = [
        (k, v)
        for k, v in response.headers.multi_items()
        if k.lower() not in ("content-encoding", "content-length", "transfer-encoding")
    ]
    return httpx.Response(
        response.status_code, headers=headers, content=b"".join(chunks), request=request
    )


def _raise_too_large(request: httpx.Request, status: int, detail: str) -> NoReturn:
    limit_mb = MAX_RESPONSE_BYTES // (1024 * 1024)
    # Not retryable: the same request would return the same oversized body.
    raise ToolExecutionError(
        f"Matter's response was larger than {limit_mb} MB, so it wasn't loaded. For an "
        "item's text, open its URL instead.",
        developer_message=(
            f"Matter {request.method} {request.url.path} -> {status}: response body "
            f"exceeds MAX_RESPONSE_BYTES={MAX_RESPONSE_BYTES} ({detail})"
        ),
    )


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
