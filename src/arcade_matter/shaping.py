"""Turn raw Matter API objects into compact, model-friendly dicts.

Rules applied everywhere:
- Every object's ``object`` field is dropped, along with fields agents don't need
  (``image_url``, ``library_position``, ``inbox_position``).
- Nested objects are flattened: ``author`` becomes the author's name and ``tags`` a list of
  ``{id, name}``.
- Matter's API calls highlights "annotations"; shaped output uses the app's term.
- ``reading_progress`` (0.0-1.0) becomes ``progress_percent`` (0-100).
- Keys with ``None`` values are omitted, and flags like ``favorite`` only appear when true.
"""

from collections.abc import Callable
from typing import Any

Raw = dict[str, Any]

EXCERPT_CHARS = 300


def compact(d: Raw) -> Raw:
    return {k: v for k, v in d.items() if v is not None}


def truncate(text: str | None, limit: int) -> str | None:
    if text is None or len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def tag(raw: Raw) -> Raw:
    return compact(
        {
            "id": raw.get("id"),
            "name": raw.get("name"),
            "item_count": raw.get("item_count"),
            "created_at": raw.get("created_at"),
        }
    )


def item(raw: Raw) -> Raw:
    author = raw.get("author")
    progress = raw.get("reading_progress")
    processing = raw.get("processing_status")
    return compact(
        {
            "id": raw.get("id"),
            "title": raw.get("title"),
            "url": raw.get("url"),
            "site": raw.get("site_name"),
            "author": author.get("name") if isinstance(author, dict) else None,
            "status": raw.get("status"),
            # Only worth mentioning while extraction is unfinished.
            "processing_status": processing if processing != "completed" else None,
            "content_type": raw.get("content_type"),
            "word_count": raw.get("word_count"),
            "progress_percent": round(progress * 100) if progress is not None else None,
            "favorite": True if raw.get("is_favorite") else None,
            "tags": [{"id": t.get("id"), "name": t.get("name")} for t in raw.get("tags") or []]
            or None,
            "excerpt": truncate(raw.get("excerpt"), EXCERPT_CHARS),
            "updated_at": raw.get("updated_at"),
        }
    )


def highlight(raw: Raw) -> Raw:
    return compact(
        {
            "id": raw.get("id"),
            "item_id": raw.get("item_id"),
            "text": raw.get("text"),
            "note": raw.get("note"),
            "created_at": raw.get("created_at"),
            "updated_at": raw.get("updated_at"),
        }
    )


def reading_session(raw: Raw) -> Raw:
    # Matter's ``date`` is when one reading period started, not a calendar day.
    return compact(
        {
            "id": raw.get("id"),
            "started_at": raw.get("date"),
            "seconds_read": raw.get("seconds_read"),
        }
    )


def account(raw: Raw) -> Raw:
    rate_limit = raw.get("rate_limit")
    return compact(
        {
            "id": raw.get("id"),
            "name": raw.get("name"),
            "email": raw.get("email"),
            "created_at": raw.get("created_at"),
            "rate_limits": rate_limit if isinstance(rate_limit, dict) else None,
        }
    )


def page(data: Raw, key: str, shape: Callable[[Raw], Raw]) -> Raw:
    """Shape a list envelope as ``{key: [...], next_cursor?}``."""
    out: Raw = {key: [shape(r) for r in data.get("results") or []]}
    if data.get("has_more") and data.get("next_cursor"):
        out["next_cursor"] = data["next_cursor"]
    return out
