"""Highlight tools. Matter's API calls highlights "annotations"."""

from typing import Annotated

from arcade_mcp_server import Context, tool

from arcade_matter import shaping
from arcade_matter.client import client_from_context
from arcade_matter.tools._common import (
    DEFAULT_LIMIT,
    DELETES,
    READ_ONLY,
    SECRETS,
    UPDATES,
    Cursor,
    HighlightId,
    ItemId,
    Limit,
    check_id,
    clamp_limit,
)


@tool(requires_secrets=SECRETS, metadata=READ_ONLY)
async def list_highlights(
    context: Context,
    item_id: ItemId,
    limit: Limit = DEFAULT_LIMIT,
    cursor: Cursor = None,
) -> Annotated[dict, "The item's highlights with their text and notes"]:
    """List the passages the user highlighted in one item, with any notes they added."""
    item_id = check_id(item_id, "item")
    data = await client_from_context(context).get(
        f"/items/{item_id}/annotations", limit=clamp_limit(limit), cursor=cursor
    )
    return shaping.page(data, "highlights", shaping.highlight)


@tool(requires_secrets=SECRETS, metadata=UPDATES)
async def set_highlight_note(
    context: Context,
    highlight_id: HighlightId,
    note: Annotated[str, "The note text. Pass an empty string to remove the note."],
) -> Annotated[dict, "The updated highlight"]:
    """Add, replace or remove the note on a highlight. Matter's API can't create highlights."""
    data = await client_from_context(context).patch(
        f"/annotations/{highlight_id}", {"note": note.strip() or None}
    )
    return shaping.highlight(data)


@tool(requires_secrets=SECRETS, metadata=DELETES)
async def delete_highlight(
    context: Context,
    highlight_id: HighlightId,
) -> Annotated[dict, "Confirmation of the deleted highlight ID"]:
    """Permanently delete a highlight and its note. This can't be undone."""
    await client_from_context(context).delete(f"/annotations/{highlight_id}")
    return {"deleted": True, "highlight_id": highlight_id}
