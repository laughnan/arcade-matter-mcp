"""Response-size limits. Bodies are streamed so oversized ones are never fully buffered."""

import gzip
import json

import httpx
import pytest
from arcade_mcp_server.exceptions import ToolExecutionError
from conftest import make_item

from arcade_matter import client as client_module
from arcade_matter.client import MatterClient
from arcade_matter.tools.items import get_item_content

LIMIT = 4_096


@pytest.fixture(autouse=True)
def small_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client_module, "MAX_RESPONSE_BYTES", LIMIT)


class TrackedStream(httpx.AsyncByteStream):
    """A chunked body that records how much was read and whether it was closed."""

    def __init__(self, chunks: list[bytes]) -> None:
        self.chunks = chunks
        self.sent = 0
        self.closed = False

    async def __aiter__(self):
        for chunk in self.chunks:
            self.sent += 1
            yield chunk

    async def aclose(self) -> None:
        self.closed = True


def serve(monkeypatch: pytest.MonkeyPatch, make_response) -> list[httpx.Request]:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return make_response(request)

    monkeypatch.setattr(client_module, "TRANSPORT", httpx.MockTransport(handler))
    return requests


async def test_normal_response_is_read(matter):
    matter.add("GET", "/items/itm_1", make_item())

    data = await MatterClient("t").get("/items/itm_1")

    assert data["id"] == "itm_1"


async def test_response_at_the_limit_is_read(monkeypatch):
    body = json.dumps({"pad": "x" * (LIMIT - 11)}).encode()
    assert len(body) == LIMIT
    serve(monkeypatch, lambda r: httpx.Response(200, content=body))

    assert (await MatterClient("t").get("/me"))["pad"]


async def test_declared_oversized_body_is_rejected_before_reading(monkeypatch):
    stream = TrackedStream([b"{}"])
    serve(
        monkeypatch,
        lambda r: httpx.Response(200, headers={"Content-Length": str(LIMIT + 1)}, stream=stream),
    )

    with pytest.raises(ToolExecutionError, match="larger than"):
        await MatterClient("t").get("/me")

    assert stream.sent == 0
    assert stream.closed


async def test_chunked_body_without_length_stops_at_the_limit(monkeypatch):
    # 2,000,000 characters of article in 1 KB chunks, with no Content-Length.
    chunks = [b"x" * 1024] * (2_000_000 // 1024)
    stream = TrackedStream(chunks)
    serve(monkeypatch, lambda r: httpx.Response(200, stream=stream))

    with pytest.raises(ToolExecutionError, match="larger than"):
        await MatterClient("t").get("/items/itm_1", include="markdown")

    assert stream.sent == LIMIT // 1024 + 1
    assert stream.closed


async def test_understated_content_length_is_still_enforced(monkeypatch):
    stream = TrackedStream([b"x" * 1024] * 10)
    serve(
        monkeypatch, lambda r: httpx.Response(200, headers={"Content-Length": "2"}, stream=stream)
    )

    with pytest.raises(ToolExecutionError, match="larger than"):
        await MatterClient("t").get("/me")

    assert stream.closed


async def test_limit_applies_to_decompressed_bytes(monkeypatch):
    compressed = gzip.compress(json.dumps({"pad": "x" * LIMIT * 4}).encode())
    assert len(compressed) < LIMIT
    serve(
        monkeypatch,
        lambda r: httpx.Response(200, headers={"Content-Encoding": "gzip"}, content=compressed),
    )

    with pytest.raises(ToolExecutionError, match="larger than"):
        await MatterClient("t").get("/me")


async def test_compressed_normal_response_is_decoded(monkeypatch):
    compressed = gzip.compress(json.dumps({"id": "act_1"}).encode())
    serve(
        monkeypatch,
        lambda r: httpx.Response(200, headers={"Content-Encoding": "gzip"}, content=compressed),
    )

    assert await MatterClient("t").get("/me") == {"id": "act_1"}


async def test_oversized_error_is_not_retryable(monkeypatch):
    serve(monkeypatch, lambda r: httpx.Response(500, content=b"x" * (LIMIT + 1)))

    with pytest.raises(ToolExecutionError) as excinfo:
        await MatterClient("t").get("/me")

    assert excinfo.value.can_retry is False


async def test_get_item_content_reports_oversized_article(matter, context):
    matter.add("GET", "/items/itm_1", make_item(markdown="x" * LIMIT * 2))

    with pytest.raises(ToolExecutionError, match="open its URL instead"):
        await get_item_content(context, "itm_1", max_chars=1_000)


async def test_get_item_content_paging_is_unchanged(matter, context):
    matter.add("GET", "/items/itm_1", make_item(markdown="y" * 3_000))

    result = await get_item_content(context, "itm_1", max_chars=1_000)

    assert len(result["content"]) == 1_000
    assert result["next_offset"] == 1_000
    assert result["total_chars"] == 3_000
