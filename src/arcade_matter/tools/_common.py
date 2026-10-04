"""Shared secret, metadata and parameter helpers for Matter tools."""

from datetime import date, datetime
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

Limit = Annotated[int, f"Maximum number of results to return (1-{MAX_LIMIT})."]
Cursor = Annotated[
    str | None,
    "Opaque cursor from a previous response's next_cursor, to fetch the next page.",
]


def clamp_limit(limit: int) -> int:
    return max(1, min(int(limit), MAX_LIMIT))


def validate_timestamp(value: str | None, name: str) -> str | None:
    """Accept an ISO date or datetime and return it in ISO 8601 form."""
    if value is None:
        return None
    text = value.strip()
    try:
        if len(text) == 10:
            return date.fromisoformat(text).isoformat()
        # Python < 3.11 doesn't parse a trailing "Z".
        return datetime.fromisoformat(text.replace("Z", "+00:00")).isoformat()
    except ValueError:
        raise RetryableToolError(
            f"Invalid {name} '{value}'.",
            additional_prompt_content=(
                f"Use an ISO date (YYYY-MM-DD) or datetime (YYYY-MM-DDTHH:MM:SSZ) for {name}."
            ),
        ) from None
