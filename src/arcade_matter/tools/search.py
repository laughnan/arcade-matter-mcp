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


class SearchScope(str, Enum):
    LIBRARY = "library"
    QUEUE = "queue"
    ARCHIVE = "archive"
    EVERYTHING = "everything"


# Matter's search `status` filter. Omitting it searches all of Matter, including content
# the user hasn't saved.
_SCOPE_STATUS = {
    SearchScope.LIBRARY: "queue,archive",
    SearchScope.QUEUE: "queue",
    SearchScope.ARCHIVE: "archive",
    SearchScope.EVERYTHING: None,
}


@tool(requires_secrets=SECRETS, metadata=READ_ONLY)
async def search_library(
    context: Context,
    query: Annotated[
        str,
        'Search text, at least 2 characters. Supports operators: "exact phrase", -exclude, '
        "by:author, site:example.com and title:word.",
    ],
    scope: Annotated[
        SearchScope,
        "What to search: 'library' (the user's saved queue and archive), 'queue', 'archive', "
        "or 'everything' (all of Matter, including content the user hasn't saved).",
    ] = SearchScope.LIBRARY,
    limit: Limit = DEFAULT_LIMIT,
    cursor: Cursor = None,
) -> Annotated[dict, "Matching items, most relevant first"]:
    """Search the user's Matter library by full text, title, author or site, ranked by
    relevance. Results marked in_library: false aren't saved, so item tools can't use them."""
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
        status=_SCOPE_STATUS[scope],
        limit=clamp_limit(limit),
        cursor=cursor,
    )
    return shaping.page(data.get("items") or {}, "items", shaping.item)
