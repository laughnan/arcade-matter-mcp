"""Account tools."""

from typing import Annotated

from arcade_mcp_server import Context, tool

from arcade_matter import shaping
from arcade_matter.client import client_from_context
from arcade_matter.tools._common import READ_ONLY, SECRETS


@tool(requires_secrets=SECRETS, metadata=READ_ONLY)
async def get_account(
    context: Context,
) -> Annotated[dict, "The Matter account's name, email, creation date and rate limits"]:
    """Get the Matter account the server is connected to, including its API rate limits
    (requests per minute for reads, writes, saves, searches and full-text fetches)."""
    data = await client_from_context(context).get("/me")
    return shaping.account(data)
