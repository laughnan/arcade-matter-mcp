"""Full-text search."""

from enum import Enum
from typing import Annotated

from arcade_mcp_server import Context, tool
from arcade_mcp_server.exceptions import RetryableToolError

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


class SearchStatus(str, Enum):
    QUEUE = "queue"
    ARCHIVE = "archive"


@tool(requires_secrets=SECRETS, metadata=READ_ONLY)
async def search_library(
    context: Context,
    query: Annotated[
        str,
        'Search text, at least 2 characters. Supports operators: "exact phrase", -exclude, '
        "by:author, site:example.com and title:word.",
    ],
    status: Annotated[
        SearchStatus | None,
        "Only search the 'queue' or the 'archive'. Omit to search everything.",
    ] = None,
    limit: Limit = DEFAULT_LIMIT,
    cursor: Cursor = None,
) -> Annotated[dict, "Matching items, most relevant first"]:
    """Search the user's Matter library by full text, title, author or site, ranked by
    relevance."""
    text = query.strip()
    if len(text) < 2:
        raise RetryableToolError(
            "The search query must be at least 2 characters.",
            additional_prompt_content="Pass a longer search query.",
        )
    data = await client_from_context(context).get(
        "/search",
        query=text,
        type="items",
        status=status.value if status else None,
        limit=clamp_limit(limit),
        cursor=cursor,
    )
    return shaping.page(data.get("items") or {}, "items", shaping.item)
