import pytest
from arcade_mcp_server.exceptions import RetryableToolError
from conftest import make_highlight, make_item, make_list, make_tag

from arcade_matter.tools.account import list_reading_sessions
from arcade_matter.tools.highlights import list_highlights
from arcade_matter.tools.items import (
    ItemOrder,
    ItemStatus,
    get_item,
    get_item_content,
    list_items,
)
from arcade_matter.tools.search import SearchScope, search_library
from arcade_matter.tools.tags import list_tags

# --- ListItems ---


async def test_list_items_defaults_to_queue(matter, context):
    matter.add("GET", "/items", make_list([make_item()], next_cursor="cur_2"))

    result = await list_items(context)

    assert dict(matter.last.url.params) == {"status": "queue", "order": "updated", "limit": "25"}
    assert result["items"][0]["title"] == "Notes on Attention"
    assert result["next_cursor"] == "cur_2"


async def test_list_items_filters(matter, context):
    matter.add("GET", "/items", make_list([]))

    result = await list_items(
        context,
        status=ItemStatus.ARCHIVE,
        favorites_only=True,
        tag_ids=["tag_a", "tag_b"],
        content_types=["article", "podcast"],
        updated_since="2026-09-01",
        order=ItemOrder.LIBRARY_POSITION,
        limit=500,
        cursor="cur_1",
    )

    assert dict(matter.last.url.params) == {
        "status": "archive",
        "is_favorite": "true",
        "tag": "tag_a,tag_b",
        "content_type": "article,podcast",
        "updated_since": "2026-09-01T00:00:00Z",
        "order": "library_position",
        "limit": "100",
        "cursor": "cur_1",
    }
    assert result == {"items": []}


async def test_list_items_rejects_bad_date(matter, context):
    with pytest.raises(RetryableToolError, match="Invalid updated_since"):
        await list_items(context, updated_since="last week")

    assert matter.requests == []


# --- GetItem / GetItemContent ---


async def test_get_item(matter, context):
    matter.add("GET", "/items/itm_1", make_item(processing_status="processing"))

    result = await get_item(context, "itm_1")

    assert result["id"] == "itm_1"
    assert result["processing_status"] == "processing"
    assert "include" not in matter.last.url.params


async def test_get_item_content_requests_markdown(matter, context):
    matter.add("GET", "/items/itm_1", make_item(markdown="# Title\n\nBody text."))

    result = await get_item_content(context, "itm_1")

    assert matter.last.url.params["include"] == "markdown"
    assert result == {
        "id": "itm_1",
        "title": "Notes on Attention",
        "url": "https://example.com/attention",
        "content": "# Title\n\nBody text.",
        "offset": 0,
        "total_chars": 19,
        "truncated": False,
    }


async def test_get_item_content_pages_long_text(matter, context):
    text = "a" * 2500
    matter.add("GET", "/items/itm_1", make_item(markdown=text))

    first = await get_item_content(context, "itm_1", max_chars=1000)
    last = await get_item_content(context, "itm_1", max_chars=1000, offset=2000)

    assert len(first["content"]) == 1000
    assert first["truncated"] is True
    assert first["next_offset"] == 1000
    assert len(last["content"]) == 500
    assert last["truncated"] is False
    assert "next_offset" not in last


async def test_get_item_content_clamps_max_chars(matter, context):
    matter.add("GET", "/items/itm_1", make_item(markdown="b" * 5000))

    result = await get_item_content(context, "itm_1", max_chars=10)

    assert len(result["content"]) == 1000


@pytest.mark.parametrize(
    ("status", "note"),
    [
        ("processing", "still extracting"),
        ("failed", "couldn't extract"),
        ("completed", "no text"),
    ],
)
async def test_get_item_content_without_markdown(matter, context, status, note):
    matter.add("GET", "/items/itm_1", make_item(processing_status=status))

    result = await get_item_content(context, "itm_1")

    assert result["content"] is None
    assert note in result["note"]


# --- SearchLibrary ---


async def test_search_library(matter, context):
    matter.add(
        "GET",
        "/search",
        {"object": "search_results", "items": make_list([make_item()], next_cursor="s2")},
    )

    result = await search_library(context, '  "attention" site:example.com ', SearchScope.QUEUE)

    assert dict(matter.last.url.params) == {
        "query": '"attention" site:example.com',
        "type": "items",
        "status": "queue",
        "limit": "25",
    }
    assert result["items"][0]["id"] == "itm_1"
    assert result["next_cursor"] == "s2"


async def test_search_library_handles_missing_items_key(matter, context):
    matter.add("GET", "/search", {"object": "search_results"})

    assert await search_library(context, "ai") == {"items": []}


async def test_search_library_rejects_short_query(matter, context):
    with pytest.raises(RetryableToolError, match="at least 2 characters"):
        await search_library(context, " a ")

    assert matter.requests == []


# --- Highlights, tags, reading sessions ---


async def test_list_highlights(matter, context):
    matter.add("GET", "/items/itm_1/annotations", make_list([make_highlight(note="Yes")]))

    result = await list_highlights(context, "itm_1", limit=10)

    assert matter.last.url.params["limit"] == "10"
    assert result == {
        "highlights": [
            {
                "id": "ann_1",
                "item_id": "itm_1",
                "text": "Attention is a limited resource.",
                "note": "Yes",
                "created_at": "2026-10-01T12:05:00Z",
                "updated_at": "2026-10-01T12:05:00Z",
            }
        ]
    }


async def test_list_tags(matter, context):
    matter.add("GET", "/tags", make_list([make_tag(), make_tag(id="tag_x", name="essays")]))

    result = await list_tags(context)

    assert [t["name"] for t in result["tags"]] == ["ai", "essays"]


async def test_list_reading_sessions(matter, context):
    matter.add(
        "GET",
        "/reading_sessions",
        make_list(
            [
                {
                    "object": "reading_session",
                    "id": "rs_1",
                    "date": "2026-10-03T08:00:00Z",
                    "seconds_read": 600,
                }
            ]
        ),
    )

    result = await list_reading_sessions(context, since="2026-10-01T00:00:00Z")

    assert matter.last.url.params["since"] == "2026-10-01T00:00:00Z"
    assert result == {
        "sessions": [{"id": "rs_1", "started_at": "2026-10-03T08:00:00Z", "seconds_read": 600}]
    }


async def test_not_found_is_retryable(matter, context):
    matter.error("GET", "/items/itm_missing", 404, "not_found", "Item not found")

    with pytest.raises(RetryableToolError, match="could not find"):
        await get_item(context, "itm_missing")


# --- Review follow-ups: content status, search scope, ID validation ---


async def test_get_item_content_reports_processing_status(matter, context):
    matter.add("GET", "/items/itm_1", make_item(processing_status="failed"))

    result = await get_item_content(context, "itm_1")

    assert result["processing_status"] == "failed"


@pytest.mark.parametrize(
    ("scope", "status"),
    [
        (SearchScope.LIBRARY, "queue,archive"),
        (SearchScope.ARCHIVE, "archive"),
        (SearchScope.EVERYTHING, None),
    ],
)
async def test_search_scope(matter, context, scope, status):
    matter.add("GET", "/search", {"object": "search_results", "items": make_list([])})

    await search_library(context, "ai", scope)

    assert matter.last.url.params.get("status") == status


async def test_search_marks_unsaved_hits(matter, context):
    unsaved = make_item(id="itm_9", status=None, library_position=None)
    matter.add(
        "GET",
        "/search",
        {"object": "search_results", "items": make_list([make_item(), unsaved])},
    )

    result = await search_library(context, "ai", SearchScope.EVERYTHING)

    assert "in_library" not in result["items"][0]
    assert result["items"][1]["in_library"] is False


@pytest.mark.parametrize(
    "call",
    [
        lambda ctx: get_item(ctx, "itm_1/tags/tag_ai"),
        lambda ctx: get_item(ctx, "../me"),
        lambda ctx: get_item_content(ctx, "tag_ai"),
        lambda ctx: list_highlights(ctx, "itm_1?x=1"),
        lambda ctx: list_items(ctx, tag_ids=["tag_ok", "tag/bad"]),
    ],
)
async def test_rejects_malformed_ids(matter, context, call):
    with pytest.raises(RetryableToolError, match="not a valid Matter"):
        await call(context)

    assert matter.requests == []


async def test_strips_whitespace_around_ids(matter, context):
    matter.add("GET", "/items/itm_1", make_item())

    await get_item(context, " itm_1 ")

    assert matter.last.url.path == "/public/v1/items/itm_1"
