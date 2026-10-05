"""Item tools: the articles, newsletters, podcasts, PDFs and tweets in the library."""

from enum import Enum
from typing import Annotated
from urllib.parse import urlparse

from arcade_mcp_server import Context, tool
from arcade_mcp_server.exceptions import RetryableToolError

from arcade_matter import shaping
from arcade_matter.client import client_from_context
from arcade_matter.tools._common import (
    CREATES,
    DEFAULT_LIMIT,
    DELETES,
    READ_ONLY,
    SECRETS,
    UPDATES,
    Cursor,
    ItemId,
    Limit,
    check_id,
    clamp_limit,
    not_found,
    validate_timestamp,
)


class ItemStatus(str, Enum):
    QUEUE = "queue"
    INBOX = "inbox"
    ARCHIVE = "archive"
    ALL = "all"


class TargetStatus(str, Enum):
    """Statuses an item can be saved or moved to. Matter can't move items to the inbox."""

    QUEUE = "queue"
    ARCHIVE = "archive"


class ItemOrder(str, Enum):
    UPDATED = "updated"
    LIBRARY_POSITION = "library_position"
    INBOX_POSITION = "inbox_position"


DEFAULT_CONTENT_CHARS = 20_000
MIN_CONTENT_CHARS = 1_000
MAX_CONTENT_CHARS = 100_000


@tool(requires_secrets=SECRETS, metadata=READ_ONLY)
async def list_items(
    context: Context,
    status: Annotated[
        ItemStatus,
        "Which part of the library: 'queue' (the reading list), 'inbox' (feeds and "
        "newsletters), 'archive' (finished) or 'all'.",
    ] = ItemStatus.QUEUE,
    favorites_only: Annotated[bool, "Only return favorited items."] = False,
    tag_ids: Annotated[
        list[str] | None,
        "Only return items with any of these tag IDs (e.g. 'tag_k3m9p'). Use ListTags to "
        "find them.",
    ] = None,
    content_types: Annotated[
        list[str] | None,
        "Only return these content types, e.g. ['article', 'podcast', 'video', 'pdf', "
        "'tweet', 'newsletter'].",
    ] = None,
    updated_since: Annotated[
        str | None,
        "Only return items changed after this ISO date or datetime. Highlights and tag "
        "changes count as updates.",
    ] = None,
    order: Annotated[
        ItemOrder,
        "Sort order: 'updated' (most recently changed first), 'library_position' (the "
        "user's queue order) or 'inbox_position' (newest in the inbox first).",
    ] = ItemOrder.UPDATED,
    limit: Limit = DEFAULT_LIMIT,
    cursor: Cursor = None,
) -> Annotated[dict, "Items (id, title, url, author, status, progress, tags, excerpt)"]:
    """List items in the user's Matter library, filtered by status, favorites, tags or content
    type. Use SearchLibrary to find items by words in their text, title, author or site."""
    data = await client_from_context(context).get(
        "/items",
        status=status.value,
        is_favorite=True if favorites_only else None,
        tag=[check_id(t, "tag") for t in tag_ids or []],
        content_type=content_types,
        updated_since=validate_timestamp(updated_since, "updated_since"),
        order=order.value,
        limit=clamp_limit(limit),
        cursor=cursor,
    )
    return shaping.page(data, "items", shaping.item)


@tool(requires_secrets=SECRETS, metadata=READ_ONLY)
async def get_item(
    context: Context,
    item_id: ItemId,
) -> Annotated[dict, "One item with its metadata, tags and processing status"]:
    """Get a single item's metadata by ID. Use GetItemContent for the full text."""
    item_id = check_id(item_id, "item")
    data = await client_from_context(context).get(f"/items/{item_id}")
    return shaping.item(data)


@tool(requires_secrets=SECRETS, metadata=READ_ONLY)
async def get_item_content(
    context: Context,
    item_id: ItemId,
    max_chars: Annotated[
        int,
        f"Maximum characters of text to return ({MIN_CONTENT_CHARS}-{MAX_CONTENT_CHARS}).",
    ] = DEFAULT_CONTENT_CHARS,
    offset: Annotated[
        int,
        "Character offset to start from. Pass a previous response's next_offset to continue "
        "reading.",
    ] = 0,
) -> Annotated[dict, "The item's text as Markdown, with paging details"]:
    """Get an item's full text as Markdown, in chunks of up to max_chars. Matter allows only
    20 full-text fetches per minute, so use excerpts from ListItems or GetItem when they're
    enough."""
    item_id = check_id(item_id, "item")
    data = await client_from_context(context).get(f"/items/{item_id}", include="markdown")
    item = shaping.item(data)
    header = {k: item[k] for k in ("id", "title", "url") if k in item}

    markdown = data.get("markdown")
    if not markdown:
        status = data.get("processing_status")
        if status == "processing":
            reason = "Matter is still extracting this item; try again in a minute."
        elif status == "failed":
            reason = (
                "Matter couldn't extract this item's text. Open the URL instead, or save it "
                "again later."
            )
        else:
            reason = "Matter has no text for this item (for example a podcast or video)."
        return {**header, "processing_status": status, "content": None, "note": reason}

    size = max(MIN_CONTENT_CHARS, min(int(max_chars), MAX_CONTENT_CHARS))
    start = max(0, int(offset))
    end = min(start + size, len(markdown))
    result: dict = {
        **header,
        "content": markdown[start:end],
        "offset": start,
        "total_chars": len(markdown),
        "truncated": end < len(markdown),
    }
    if end < len(markdown):
        result["next_offset"] = end
    return result


@tool(requires_secrets=SECRETS, metadata=CREATES)
async def save_item(
    context: Context,
    url: Annotated[str, "The http:// or https:// URL to save."],
    status: Annotated[
        TargetStatus, "Where to put it: 'queue' (the reading list) or 'archive'."
    ] = TargetStatus.QUEUE,
) -> Annotated[dict, "The saved item, with processing_status while extraction runs"]:
    """Save a URL to the user's Matter library. Matter extracts the content in the
    background, usually within a minute; check GetItem later if processing_status is
    'processing'. If the URL is already saved, the existing item is returned unchanged with
    already_in_library: true; use UpdateItem to move it."""
    target = url.strip()
    parsed = urlparse(target)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise RetryableToolError(
            f"'{url}' is not an http or https URL.",
            additional_prompt_content="Pass a full URL starting with http:// or https://.",
        )
    client = client_from_context(context)
    data = await client.post("/items", {"url": target, "status": status.value})
    result = shaping.item(data)
    # Matter answers 201 for a new save and 200 with the existing item, which it doesn't move.
    if client.last_status == 200:
        result["already_in_library"] = True
        current = data.get("status")
        if current and current != status.value:
            result["note"] = (
                f"This URL was already saved with status '{current}' and was not moved. "
                f"Use UpdateItem with status '{status.value}' to move it."
            )
    return result


@tool(requires_secrets=SECRETS, metadata=UPDATES)
async def update_item(
    context: Context,
    item_id: ItemId,
    status: Annotated[
        TargetStatus | None,
        "Move the item to 'queue' or 'archive'. Items can't be moved back to the inbox.",
    ] = None,
    favorite: Annotated[bool | None, "True to favorite the item, false to unfavorite it."] = None,
    progress_percent: Annotated[float | None, "Reading progress from 0 to 100 percent."] = None,
) -> Annotated[dict, "The updated item"]:
    """Archive or re-queue an item, favorite or unfavorite it, or set its reading progress.
    Pass at least one change."""
    item_id = check_id(item_id, "item")
    body: dict = {}
    if status is not None:
        body["status"] = status.value
    if favorite is not None:
        body["is_favorite"] = favorite
    if progress_percent is not None:
        if not 0 <= progress_percent <= 100:
            raise RetryableToolError(
                "progress_percent must be between 0 and 100.",
                additional_prompt_content="Pass a reading progress from 0 to 100.",
            )
        body["reading_progress"] = round(progress_percent / 100, 4)
    if not body:
        raise RetryableToolError(
            "No changes were given.",
            additional_prompt_content="Pass status, favorite or progress_percent.",
        )
    data = await client_from_context(context).patch(f"/items/{item_id}", body)
    return shaping.item(data)


@tool(requires_secrets=SECRETS, metadata=DELETES)
async def delete_item(
    context: Context,
    item_id: ItemId,
) -> Annotated[dict, "Confirmation of the deleted item ID"]:
    """Permanently delete an item from the user's Matter library, along with its highlights.
    Its tags are only removed from this item; the tags themselves are kept (use DeleteTag to
    delete a tag). This can't be undone; to keep it out of the queue, archive it with
    UpdateItem instead."""
    item_id = check_id(item_id, "item")
    if await client_from_context(context).delete(f"/items/{item_id}", missing_ok=True) is None:
        return not_found("item_id", item_id)
    return {"deleted": True, "item_id": item_id}
