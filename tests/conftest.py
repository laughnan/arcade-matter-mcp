"""Test fixtures: a fake Matter API served through httpx.MockTransport.

All data here is invented. Tests never call the real API.
"""

import json
from collections import deque
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from arcade_matter import client as client_module

API_PREFIX = "/public/v1"

Response = tuple[int, Any, dict[str, str]]


@dataclass
class FakeMatter:
    routes: dict[tuple[str, str, frozenset | None], deque[Response]] = field(default_factory=dict)
    requests: list[httpx.Request] = field(default_factory=list)

    def add(
        self,
        method: str,
        path: str,
        body: Any = None,
        *,
        status: int = 200,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
    ) -> None:
        """Register a response, sent as-is. ``None`` with status 204 sends no body.

        With ``params``, the route only matches requests with exactly those query params;
        otherwise it matches any query string. Adding the same route again queues another
        response; the last one repeats once the queue is drained.
        """
        key = (method.upper(), API_PREFIX + path, frozenset(params.items()) if params else None)
        self.routes.setdefault(key, deque()).append((status, body, headers or {}))

    def error(
        self, method: str, path: str, status: int, code: str, message: str, field: str = ""
    ) -> None:
        error: dict[str, str] = {"code": code, "message": message}
        if field:
            error["field"] = field
        self.add(method, path, {"error": error}, status=status)

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        exact = (request.method, request.url.path, frozenset(request.url.params.items()))
        fallback = (request.method, request.url.path, None)
        queue = self.routes.get(exact) or self.routes.get(fallback)
        if not queue:
            return httpx.Response(
                404, json={"error": {"code": "not_found", "message": f"no route {exact}"}}
            )
        status, body, headers = queue.popleft() if len(queue) > 1 else queue[0]
        content = b"" if body is None else json.dumps(body).encode()
        return httpx.Response(status, content=content, headers=headers)

    @property
    def last(self) -> httpx.Request:
        return self.requests[-1]

    def last_json(self) -> Any:
        return json.loads(self.last.content)


@pytest.fixture
def matter(monkeypatch: pytest.MonkeyPatch) -> FakeMatter:
    fake = FakeMatter()
    monkeypatch.setattr(client_module, "TRANSPORT", httpx.MockTransport(fake.handler))
    return fake


@pytest.fixture
def sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Record asyncio.sleep calls made by the client instead of sleeping."""
    calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        calls.append(seconds)

    monkeypatch.setattr(client_module.asyncio, "sleep", fake_sleep)
    return calls


def _secrets(values: dict[str, str]):
    def get_secret(key: str) -> str:
        if key not in values:
            raise ValueError(f"Secret {key} not found")
        return values[key]

    return get_secret


@pytest.fixture
def context() -> SimpleNamespace:
    """Stand-in for arcade_mcp_server.Context carrying the MATTER_API_TOKEN secret."""
    return SimpleNamespace(get_secret=_secrets({"MATTER_API_TOKEN": "mat_test"}))


# --- Sample entities (shapes follow Matter's OpenAPI schemas) ---


def make_tag(**overrides: Any) -> dict[str, Any]:
    tag = {
        "object": "tag",
        "id": "tag_ai",
        "name": "ai",
        "item_count": 12,
        "created_at": "2026-01-10T09:00:00Z",
    }
    tag.update(overrides)
    return tag


def make_item(**overrides: Any) -> dict[str, Any]:
    item = {
        "object": "item",
        "id": "itm_1",
        "title": "Notes on Attention",
        "url": "https://example.com/attention",
        "site_name": "Example Blog",
        "author": {"object": "author", "id": "aut_1", "name": "Ada Writer"},
        "status": "queue",
        "processing_status": "completed",
        "is_favorite": False,
        "content_type": "article",
        "word_count": 2400,
        "reading_progress": 0.25,
        "image_url": "https://example.com/cover.png",
        "excerpt": "A short look at how attention works.",
        "library_position": 1000,
        "inbox_position": None,
        "tags": [make_tag()],
        "updated_at": "2026-10-01T12:00:00Z",
    }
    item.update(overrides)
    return item


def make_highlight(**overrides: Any) -> dict[str, Any]:
    highlight = {
        "object": "annotation",
        "id": "ann_1",
        "item_id": "itm_1",
        "text": "Attention is a limited resource.",
        "note": None,
        "created_at": "2026-10-01T12:05:00Z",
        "updated_at": "2026-10-01T12:05:00Z",
    }
    highlight.update(overrides)
    return highlight


def make_list(results: list[Any], next_cursor: str | None = None) -> dict[str, Any]:
    return {
        "object": "list",
        "results": results,
        "has_more": next_cursor is not None,
        "next_cursor": next_cursor,
    }
