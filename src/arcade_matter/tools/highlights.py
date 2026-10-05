"""Highlight tools. Matter's API calls highlights "annotations"."""

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
