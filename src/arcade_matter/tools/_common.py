"""Shared secret, metadata and parameter helpers for Matter tools."""

import re
from datetime import date, datetime, time, timezone
from typing import Annotated

from arcade_mcp_server.exceptions import RetryableToolError
from arcade_mcp_server.metadata import (
    Behavior,
    Classification,
    Operation,
    ServiceDomain,
    ToolMetadata,
)

from arcade_matter.client import SECRET_NAME

# Pass as ``requires_secrets=SECRETS`` on every tool (see docs/SPEC.md, Authorization model).
SECRETS = [SECRET_NAME]

# Matter has no read-later domain in Arcade's taxonomy; DOCUMENTS is the closest.
_CLASSIFICATION = Classification(service_domains=[ServiceDomain.DOCUMENTS])

READ_ONLY = ToolMetadata(
    classification=_CLASSIFICATION,
    behavior=Behavior(
        operations=[Operation.READ],
        read_only=True,
        destructive=False,
        idempotent=True,
        open_world=True,
    ),
)


def _write(operation: Operation, *, idempotent: bool, destructive: bool = False) -> ToolMetadata:
    return ToolMetadata(
        classification=_CLASSIFICATION,
        behavior=Behavior(
            operations=[operation],
            read_only=False,
            destructive=destructive,
            idempotent=idempotent,
            open_world=True,
        ),
    )


# Saving a URL that's already in the library returns the existing item.
CREATES = _write(Operation.CREATE, idempotent=True)
UPDATES = _write(Operation.UPDATE, idempotent=True)
DELETES = _write(Operation.DELETE, idempotent=True, destructive=True)


DEFAULT_LIMIT = 25
MAX_LIMIT = 100

ItemId = Annotated[
    str, "The item ID (e.g. 'itm_r9f3a'). Use ListItems or SearchLibrary to find it."
]
HighlightId = Annotated[str, "The highlight ID (e.g. 'ann_x7y2z'). Use ListHighlights to find it."]
TagId = Annotated[str, "The tag ID (e.g. 'tag_n5j2x'). Use ListTags to find it."]
Limit = Annotated[int, f"Maximum number of results to return (1-{MAX_LIMIT})."]
Cursor = Annotated[
    str | None,
    "Opaque cursor from a previous response's next_cursor, to fetch the next page.",
]


def clamp_limit(limit: int) -> int:
    return max(1, min(int(limit), MAX_LIMIT))


def validate_timestamp(value: str | None, name: str) -> str | None:
    """Accept an ISO date or datetime and return a UTC ``YYYY-MM-DDTHH:MM:SSZ`` timestamp.

    Matter's timestamp filters are ``date-time`` values, so a bare date becomes midnight UTC
    and an offset is converted to UTC. A datetime without an offset is taken as UTC.
    """
    if value is None:
        return None
    text = value.strip()
    try:
        if len(text) == 10:
            parsed = datetime.combine(date.fromisoformat(text), time.min, timezone.utc)
        else:
            # Python < 3.11 doesn't parse a trailing "Z".
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise RetryableToolError(
            f"Invalid {name} '{value}'.",
            additional_prompt_content=(
                f"Use an ISO date (YYYY-MM-DD) or datetime (YYYY-MM-DDTHH:MM:SSZ) for {name}."
            ),
        ) from None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


_ID_PREFIXES = {"item": "itm", "highlight": "ann", "tag": "tag"}


def check_id(value: str, kind: str) -> str:
    """Return a Matter ID after checking it matches the documented pattern.

    IDs go into URL paths, so this keeps a value like ``itm_1/tags/tag_2`` from turning one
    call into a different endpoint.
    """
    prefix = _ID_PREFIXES[kind]
    text = (value or "").strip()
    if not re.fullmatch(rf"{prefix}_[0-9A-Za-z]+", text):
        raise RetryableToolError(
            f"'{value}' is not a valid Matter {kind} ID.",
            additional_prompt_content=(
                f"{kind.capitalize()} IDs look like '{prefix}_abc123'. Look the ID up with a "
                "list or search tool and retry."
            ),
        )
    return text


def require_text(value: str, name: str) -> str:
    text = (value or "").strip()
    if not text:
        raise RetryableToolError(
            f"{name} must not be empty.",
            additional_prompt_content=f"Pass a non-empty {name}.",
        )
    return text


def not_found(key: str, value: str) -> dict[str, object]:
    """Result for a delete whose target doesn't exist. Deletes are marked idempotent, so a
    repeat of a delete that already succeeded is reported, not raised."""
    return {
        "deleted": False,
        "not_found": True,
        key: value,
        "note": "Nothing with this ID exists; it may already have been deleted.",
    }
