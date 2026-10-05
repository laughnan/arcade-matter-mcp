"""Account and reading-history tools."""

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
    validate_timestamp,
)


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


@tool(requires_secrets=SECRETS, metadata=READ_ONLY)
async def list_reading_sessions(
    context: Context,
    since: Annotated[
        str | None, "Only return sessions on or after this ISO date or datetime."
    ] = None,
    limit: Limit = DEFAULT_LIMIT,
    cursor: Cursor = None,
) -> Annotated[dict, "Reading sessions (id, start time, seconds read), newest first"]:
    """List the user's reading sessions, newest first. Each session is one period of reading
    with its start time and duration in seconds; a day can have several."""
    data = await client_from_context(context).get(
        "/reading_sessions",
        since=validate_timestamp(since, "since"),
        limit=clamp_limit(limit),
        cursor=cursor,
    )
    return shaping.page(data, "sessions", shaping.reading_session)
