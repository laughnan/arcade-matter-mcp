"""Tag tools."""

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
    ItemId,
    Limit,
    TagId,
    check_id,
    clamp_limit,
    not_found,
    require_text,
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


@tool(requires_secrets=SECRETS, metadata=UPDATES)
async def add_tag(
    context: Context,
    item_id: ItemId,
    name: Annotated[
        str, "The tag name. Case-insensitive; an existing tag is reused, otherwise it's created."
    ],
) -> Annotated[dict, "The tag that is now on the item"]:
    """Tag an item by tag name, creating the tag if it doesn't exist yet."""
    item_id = check_id(item_id, "item")
    data = await client_from_context(context).post(
        f"/items/{item_id}/tags", {"name": require_text(name, "name")}
    )
    return {"item_id": item_id, "tag": shaping.tag(data)}


@tool(requires_secrets=SECRETS, metadata=UPDATES)
async def remove_tag(
    context: Context,
    item_id: ItemId,
    tag_id: TagId,
) -> Annotated[dict, "Confirmation that the tag was removed from the item"]:
    """Remove a tag from one item. The tag itself and its other items are kept."""
    item_id = check_id(item_id, "item")
    tag_id = check_id(tag_id, "tag")
    path = f"/items/{item_id}/tags/{tag_id}"
    if await client_from_context(context).delete(path, missing_ok=True) is None:
        return {
            "removed": False,
            "not_found": True,
            "item_id": item_id,
            "tag_id": tag_id,
            "note": "The item doesn't exist or doesn't have this tag; nothing was changed.",
        }
    return {"removed": True, "item_id": item_id, "tag_id": tag_id}


@tool(requires_secrets=SECRETS, metadata=UPDATES)
async def rename_tag(
    context: Context,
    tag_id: TagId,
    name: Annotated[str, "The new tag name. It must not already be used by another tag."],
) -> Annotated[dict, "The renamed tag"]:
    """Rename a tag everywhere it's used."""
    tag_id = check_id(tag_id, "tag")
    data = await client_from_context(context).patch(
        f"/tags/{tag_id}", {"name": require_text(name, "name")}
    )
    return shaping.tag(data)


@tool(requires_secrets=SECRETS, metadata=DELETES)
async def delete_tag(
    context: Context,
    tag_id: TagId,
) -> Annotated[dict, "Confirmation of the deleted tag ID"]:
    """Permanently delete a tag and remove it from every item. The items are kept. This can't
    be undone; to untag a single item, use RemoveTag instead."""
    tag_id = check_id(tag_id, "tag")
    if await client_from_context(context).delete(f"/tags/{tag_id}", missing_ok=True) is None:
        return not_found("tag_id", tag_id)
    return {"deleted": True, "tag_id": tag_id}
