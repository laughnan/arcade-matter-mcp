"""Account tools."""

from typing import Annotated

from arcade_mcp_server import Context, tool

from arcade_matter import shaping
from arcade_matter.client import client_from_context
from arcade_matter.tools._common import READ_ONLY, SECRETS


@tool(requires_secrets=SECRETS, metadata=READ_ONLY)
async def get_account(
    context: Context,
) -> Annotated[
    dict, "The Matter account's name, email, creation date, rate limits and read quota left"
]:
    """Get the Matter account the server is connected to, including its API rate limits
    (requests per minute for reads, writes, saves, searches and full-text fetches) and how
    many read requests are left in the current window."""
    client = client_from_context(context)
    data = await client.get("/me")
    result = shaping.account(data)
    quota = client.rate_limit_status()
    if quota:
        result["read_quota"] = quota
    return result
