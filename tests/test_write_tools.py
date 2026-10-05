import pytest
from arcade_mcp_server.exceptions import RetryableToolError, ToolExecutionError
from conftest import make_highlight, make_item, make_tag

from arcade_matter.tools.highlights import delete_highlight, set_highlight_note
from arcade_matter.tools.items import TargetStatus, delete_item, save_item, update_item
from arcade_matter.tools.tags import add_tag, delete_tag, remove_tag, rename_tag

# --- SaveItem ---


async def test_save_item_defaults_to_queue(matter, context):
    matter.add(
        "POST",
        "/items",
        make_item(processing_status="processing", title=None, reading_progress=0.0),
        status=201,
    )

    result = await save_item(context, " https://example.com/attention ")

    assert matter.last_json() == {"url": "https://example.com/attention", "status": "queue"}
    assert result["processing_status"] == "processing"


async def test_save_item_to_archive(matter, context):
    matter.add("POST", "/items", make_item(status="archive"))

    await save_item(context, "http://example.com/a", TargetStatus.ARCHIVE)

    assert matter.last_json()["status"] == "archive"


@pytest.mark.parametrize("url", ["example.com/a", "ftp://example.com/a", "https://", ""])
async def test_save_item_rejects_non_http_urls(matter, context, url):
    with pytest.raises(RetryableToolError, match="not an http or https URL"):
        await save_item(context, url)

    assert matter.requests == []


# --- UpdateItem ---


async def test_update_item_sends_only_given_fields(matter, context):
    matter.add("PATCH", "/items/itm_1", make_item(status="archive", is_favorite=True))

    result = await update_item(context, "itm_1", status=TargetStatus.ARCHIVE, favorite=True)

    assert matter.last_json() == {"status": "archive", "is_favorite": True}
    assert result["status"] == "archive"
    assert result["favorite"] is True


async def test_update_item_converts_progress_percent(matter, context):
    matter.add("PATCH", "/items/itm_1", make_item(reading_progress=0.5))

    await update_item(context, "itm_1", progress_percent=50)

    assert matter.last_json() == {"reading_progress": 0.5}


async def test_update_item_can_unfavorite(matter, context):
    matter.add("PATCH", "/items/itm_1", make_item())

    await update_item(context, "itm_1", favorite=False)

    assert matter.last_json() == {"is_favorite": False}


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [({}, "No changes"), ({"progress_percent": 120}, "between 0 and 100")],
)
async def test_update_item_validates(matter, context, kwargs, message):
    with pytest.raises(RetryableToolError, match=message):
        await update_item(context, "itm_1", **kwargs)

    assert matter.requests == []


# --- Tags ---


async def test_add_tag(matter, context):
    matter.add("POST", "/items/itm_1/tags", make_tag(name="essays", id="tag_e"), status=201)

    result = await add_tag(context, "itm_1", "  essays ")

    assert matter.last_json() == {"name": "essays"}
    assert result == {
        "item_id": "itm_1",
        "tag": {
            "id": "tag_e",
            "name": "essays",
            "item_count": 12,
            "created_at": "2026-01-10T09:00:00Z",
        },
    }


async def test_remove_tag(matter, context):
    matter.add("DELETE", "/items/itm_1/tags/tag_ai", None, status=204)

    result = await remove_tag(context, "itm_1", "tag_ai")

    assert matter.last.method == "DELETE"
    assert result == {"removed": True, "item_id": "itm_1", "tag_id": "tag_ai"}


async def test_rename_tag(matter, context):
    matter.add("PATCH", "/tags/tag_ai", make_tag(name="machine-learning"))

    result = await rename_tag(context, "tag_ai", "machine-learning")

    assert matter.last_json() == {"name": "machine-learning"}
    assert result["name"] == "machine-learning"


async def test_rename_tag_conflict_is_retryable(matter, context):
    matter.error(
        "PATCH", "/tags/tag_ai", 409, "conflict", "A tag with this name already exists.", "name"
    )

    with pytest.raises(RetryableToolError, match="conflicts with existing"):
        await rename_tag(context, "tag_ai", "essays")


@pytest.mark.parametrize(("tool", "target"), [(add_tag, "itm_1"), (rename_tag, "tag_ai")])
async def test_tag_names_must_not_be_empty(matter, context, tool, target):
    with pytest.raises(RetryableToolError, match="name must not be empty"):
        await tool(context, target, "   ")

    assert matter.requests == []


# --- Highlight notes ---


async def test_set_highlight_note(matter, context):
    matter.add("PATCH", "/annotations/ann_1", make_highlight(note="Worth rereading"))

    result = await set_highlight_note(context, "ann_1", "Worth rereading")

    assert matter.last_json() == {"note": "Worth rereading"}
    assert result["note"] == "Worth rereading"


async def test_empty_note_clears_it(matter, context):
    matter.add("PATCH", "/annotations/ann_1", make_highlight())

    result = await set_highlight_note(context, "ann_1", "  ")

    assert matter.last_json() == {"note": None}
    assert "note" not in result


# --- Deletes ---


@pytest.mark.parametrize(
    ("tool", "path", "target", "expected"),
    [
        (delete_item, "/items/itm_1", "itm_1", {"deleted": True, "item_id": "itm_1"}),
        (
            delete_highlight,
            "/annotations/ann_1",
            "ann_1",
            {"deleted": True, "highlight_id": "ann_1"},
        ),
        (delete_tag, "/tags/tag_ai", "tag_ai", {"deleted": True, "tag_id": "tag_ai"}),
    ],
)
async def test_deletes(matter, context, tool, path, target, expected):
    matter.add("DELETE", path, None, status=204)

    result = await tool(context, target)

    assert matter.last.method == "DELETE"
    assert matter.last.url.path == "/public/v1" + path
    assert result == expected


@pytest.mark.parametrize(
    ("tool", "path", "target", "key"),
    [
        (delete_item, "/items/itm_gone", "itm_gone", "item_id"),
        (delete_highlight, "/annotations/ann_gone", "ann_gone", "highlight_id"),
        (delete_tag, "/tags/tag_gone", "tag_gone", "tag_id"),
    ],
)
async def test_delete_of_missing_target_is_not_an_error(matter, context, tool, path, target, key):
    matter.error("DELETE", path, 404, "not_found", "Not found")

    result = await tool(context, target)

    assert result["deleted"] is False
    assert result["not_found"] is True
    assert result[key] == target


async def test_remove_missing_tag_is_not_an_error(matter, context):
    matter.error("DELETE", "/items/itm_1/tags/tag_ai", 404, "not_found", "Not found")

    result = await remove_tag(context, "itm_1", "tag_ai")

    assert result["removed"] is False
    assert result["not_found"] is True


async def test_delete_still_raises_other_errors(matter, context):
    matter.error("DELETE", "/items/itm_1", 403, "forbidden", "Pro required")

    with pytest.raises(ToolExecutionError, match="Matter Pro"):
        await delete_item(context, "itm_1")


# --- SaveItem on a URL that's already saved ---


async def test_save_item_reports_existing_item(matter, context):
    matter.add("POST", "/items", make_item(status="queue"), status=200)

    result = await save_item(context, "https://example.com/attention")

    assert result["already_in_library"] is True
    assert "note" not in result


async def test_save_item_existing_with_different_status_points_to_update(matter, context):
    matter.add("POST", "/items", make_item(status="queue"), status=200)

    result = await save_item(context, "https://example.com/attention", TargetStatus.ARCHIVE)

    assert result["already_in_library"] is True
    assert "UpdateItem" in result["note"]


async def test_save_item_new_is_not_flagged(matter, context):
    matter.add("POST", "/items", make_item(), status=201)

    result = await save_item(context, "https://example.com/attention")

    assert "already_in_library" not in result


# --- ID validation on writes ---


@pytest.mark.parametrize(
    "call",
    [
        lambda ctx: delete_item(ctx, "itm_1/tags/tag_ai"),
        lambda ctx: delete_item(ctx, "ann_1"),
        lambda ctx: delete_highlight(ctx, "ann_1/../../items/itm_2"),
        lambda ctx: delete_tag(ctx, "itm_1"),
        lambda ctx: update_item(ctx, "itm_1?status=archive", favorite=True),
        lambda ctx: add_tag(ctx, "tag_ai", "essays"),
        lambda ctx: remove_tag(ctx, "itm_1", "tag_ai/x"),
        lambda ctx: rename_tag(ctx, "tag ai", "essays"),
        lambda ctx: set_highlight_note(ctx, "itm_1", "note"),
    ],
)
async def test_writes_reject_malformed_ids(matter, context, call):
    with pytest.raises(RetryableToolError, match="not a valid Matter"):
        await call(context)

    assert matter.requests == []
