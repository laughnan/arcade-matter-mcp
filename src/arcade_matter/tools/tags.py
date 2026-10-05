"""Tag tools."""

from typing import Annotated

from arcade_mcp_server import Context, tool

from arcade_matter import shaping
from arcade_matter.client import client_from_context
from arcade_matter.tools._common import (
    DEFAULT_LIMIT,
    READ_ONLY,
    SECRETS,
    Cursor,
    Limit,
    clamp_limit,
)


@tool(requires_secrets=SECRETS, metadata=READ_ONLY)
async def list_tags(
    context: Context,
    limit: Limit = DEFAULT_LIMIT,
    cursor: Cursor = None,
) -> Annotated[dict, "Tags with their IDs and item counts"]:
    """List the user's Matter tags with how many items each one is on."""
    data = await client_from_context(context).get("/tags", limit=clamp_limit(limit), cursor=cursor)
    return shaping.page(data, "tags", shaping.tag)
