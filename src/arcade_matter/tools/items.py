"""Item tools: the articles, newsletters, podcasts, PDFs and tweets in the library."""

from enum import Enum
from typing import Annotated

from arcade_mcp_server import Context, tool

from arcade_matter import shaping
from arcade_matter.client import client_from_context
from arcade_matter.tools._common import (
    DEFAULT_LIMIT,
    READ_ONLY,
    SECRETS,
    Cursor,
    ItemId,
    Limit,
    clamp_limit,
    validate_timestamp,
)


class ItemStatus(str, Enum):
    QUEUE = "queue"
    INBOX = "inbox"
    ARCHIVE = "archive"
    ALL = "all"


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
        tag=tag_ids,
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
    data = await client_from_context(context).get(f"/items/{item_id}", include="markdown")
    item = shaping.item(data)
    header = {k: item[k] for k in ("id", "title", "url") if k in item}

    markdown = data.get("markdown")
    if not markdown:
        status = data.get("processing_status")
        reason = (
            "Matter is still extracting this item; try again in a minute."
            if status == "processing"
            else "Matter has no text for this item."
        )
        return {**header, "content": None, "note": reason}

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
