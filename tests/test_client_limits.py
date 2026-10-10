"""Response-size limits. Bodies are streamed so oversized ones are never fully buffered."""

import gzip
import json

import httpx
import pytest
from arcade_mcp_server.exceptions import ToolExecutionError, UpstreamError
from conftest import make_item

from arcade_matter import client as client_module
from arcade_matter.client import MatterClient
from arcade_matter.tools.items import get_item_content

LIMIT = 4_096


@pytest.fixture(autouse=True)
def small_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(client_module, "MAX_RESPONSE_BYTES", LIMIT)
    # Small raw reads, so overshoot past the limit is at most one 1 KB read.
    monkeypatch.setattr(client_module, "READ_CHUNK_BYTES", 1024)


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


async def test_gzip_bomb_is_stopped_without_inflating_it(monkeypatch):
    # 64 MB of zeros compresses to about 64 KB, well under the limit's Content-Length check.
    # Sent as a real stream, so decompression happens inside the client.
    compressed = gzip.compress(b"0" * (64 * 1024 * 1024))
    assert len(compressed) < 1024 * 1024
    monkeypatch.setattr(client_module, "MAX_RESPONSE_BYTES", 1024 * 1024)
    stream = TrackedStream([compressed])
    serve(
        monkeypatch,
        lambda r: httpx.Response(
            200,
            headers={"Content-Encoding": "gzip", "Content-Length": str(len(compressed))},
            stream=stream,
        ),
    )
    inflated: list[int] = []
    real = client_module.zlib.decompressobj

    def tracking_decompressobj(*args):
        decoder = real(*args)

        class Tracked:
            unconsumed_tail = b""

            def decompress(self, data, max_length=0):
                out = decoder.decompress(data, max_length)
                self.unconsumed_tail = decoder.unconsumed_tail
                inflated.append(len(out))
                return out

            def flush(self):
                return decoder.flush()

        return Tracked()

    monkeypatch.setattr(client_module.zlib, "decompressobj", tracking_decompressobj)

    with pytest.raises(ToolExecutionError, match="larger than"):
        await MatterClient("t").get("/me")

    assert sum(inflated) <= 1024 * 1024 + 1
    assert max(inflated) <= 1024 * 1024 + 1
    assert stream.closed


async def test_streamed_gzip_response_is_decoded(monkeypatch):
    compressed = gzip.compress(json.dumps({"id": "act_1", "pad": "x" * 3000}).encode())
    # Split the compressed body so it decodes across several reads.
    chunks = [compressed[i : i + 100] for i in range(0, len(compressed), 100)]
    serve(
        monkeypatch,
        lambda r: httpx.Response(
            200, headers={"Content-Encoding": "gzip"}, stream=TrackedStream(chunks)
        ),
    )

    assert (await MatterClient("t").get("/me"))["id"] == "act_1"


async def test_requests_identity_encoding(matter):
    matter.add("GET", "/me", {"id": "act_1"})

    await MatterClient("t").get("/me")

    assert matter.last.headers["Accept-Encoding"] == "identity"


async def test_corrupt_gzip_is_an_upstream_error(monkeypatch):
    serve(
        monkeypatch,
        lambda r: httpx.Response(
            200, headers={"Content-Encoding": "gzip"}, stream=TrackedStream([b"not gzip"])
        ),
    )

    with pytest.raises(UpstreamError, match="unreadable"):
        await MatterClient("t").get("/me")


async def test_unknown_encoding_is_refused(monkeypatch):
    serve(
        monkeypatch,
        lambda r: httpx.Response(
            200, headers={"Content-Encoding": "br"}, stream=TrackedStream([b"x"])
        ),
    )

    with pytest.raises(UpstreamError, match="unsupported encoding"):
        await MatterClient("t").get("/me")


async def test_single_huge_identity_chunk_is_read_in_bounded_steps(monkeypatch):
    body = b"x" * (LIMIT * 64)
    stream = TrackedStream([body])
    serve(monkeypatch, lambda r: httpx.Response(200, stream=stream))

    with pytest.raises(ToolExecutionError, match="larger than"):
        await MatterClient("t").get("/me")

    assert stream.closed


async def test_oversized_error_is_not_retryable(monkeypatch):
    serve(monkeypatch, lambda r: httpx.Response(500, content=b"x" * (LIMIT + 1)))

    with pytest.raises(ToolExecutionError) as excinfo:
        await MatterClient("t").get("/me")

    assert excinfo.value.can_retry is False


async def test_get_item_content_reports_oversized_article(matter, context):
    matter.add("GET", "/items/itm_1", make_item(markdown="x" * LIMIT * 2))

    with pytest.raises(ToolExecutionError, match="open the item's URL instead"):
        await get_item_content(context, "itm_1", max_chars=1_000)


async def test_get_item_content_paging_is_unchanged(matter, context):
    matter.add("GET", "/items/itm_1", make_item(markdown="y" * 3_000))

    result = await get_item_content(context, "itm_1", max_chars=1_000)

    assert len(result["content"]) == 1_000
    assert result["next_offset"] == 1_000
    assert result["total_chars"] == 3_000
