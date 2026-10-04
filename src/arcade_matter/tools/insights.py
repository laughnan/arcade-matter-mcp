"""Composite tools that answer common questions in a small, fixed number of requests.

Requests are issued one at a time so they stay under Matter's 5 requests/second burst limit
(the client waits out a short 429 if one happens anyway).
"""

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from arcade_mcp_server import Context, tool
from arcade_mcp_server.exceptions import RetryableToolError

from arcade_matter import shaping
from arcade_matter.client import client_from_context
from arcade_matter.tools._common import MAX_LIMIT, READ_ONLY, SECRETS, ItemId, validate_timestamp

DEFAULT_RECENT_DAYS = 7
DEFAULT_RECENT_ITEMS = 10
MAX_RECENT_ITEMS = 20
DEFAULT_READING_DAYS = 30
MAX_SESSION_PAGES = 4
# Beyond this many days, the per-day breakdown is left out to keep responses small.
MAX_DAILY_ROWS = 62

_ITEM_SUMMARY_KEYS = ("id", "title", "url", "author", "site", "status")


def _now() -> datetime:
    """The current time in UTC. Patched in tests."""
    return datetime.now(timezone.utc)


def _parse_instant(value: str | None) -> datetime | None:
    """Parse an ISO date or datetime from Matter or a caller; naive values are UTC."""
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _since(value: str | None, default_days: int) -> datetime:
    validated = validate_timestamp(value, "since")
    if validated is None:
        return _now() - timedelta(days=default_days)
    parsed = _parse_instant(validated)
    assert parsed is not None
    return parsed


def _item_summary(raw: dict[str, Any]) -> dict[str, Any]:
    shaped = shaping.item(raw)
    return {k: shaped[k] for k in _ITEM_SUMMARY_KEYS if k in shaped}


@tool(requires_secrets=SECRETS, metadata=READ_ONLY)
async def get_item_with_highlights(
    context: Context,
    item_id: ItemId,
) -> Annotated[dict, "The item's metadata and its highlights with notes"]:
    """Get an item together with every highlight and note on it (up to 100), in two
    requests. Use this to answer "what did I highlight in this article?"."""
    client = client_from_context(context)
    item = await client.get(f"/items/{item_id}")
    data = await client.get(f"/items/{item_id}/annotations", limit=MAX_LIMIT)
    result: dict[str, Any] = {
        "item": shaping.item(item),
        "highlights": [shaping.highlight(h) for h in data.get("results") or []],
    }
    if data.get("has_more"):
        result["more_highlights"] = True
    return result


@tool(requires_secrets=SECRETS, metadata=READ_ONLY)
async def list_recent_highlights(
    context: Context,
    since: Annotated[
        str | None,
        f"Only include highlights made or edited on or after this ISO date or datetime. "
        f"Defaults to {DEFAULT_RECENT_DAYS} days ago.",
    ] = None,
    max_items: Annotated[
        int,
        f"Maximum number of recently updated items to check (1-{MAX_RECENT_ITEMS}). Each "
        "one costs a request.",
    ] = DEFAULT_RECENT_ITEMS,
) -> Annotated[dict, "Recent highlights grouped by item, most recently updated item first"]:
    """List the highlights the user made recently, grouped by item. Use this to answer
    "what did I highlight this week?". Makes one request for recently updated items and one
    per item checked (at most 21 requests)."""
    start = _since(since, DEFAULT_RECENT_DAYS)
    count = max(1, min(int(max_items), MAX_RECENT_ITEMS))
    client = client_from_context(context)

    data = await client.get(
        "/items",
        status="all",
        updated_since=start.isoformat(),
        order="updated",
        limit=count,
    )
    items = data.get("results") or []

    groups = []
    for raw in items:
        page = await client.get(f"/items/{raw['id']}/annotations", limit=MAX_LIMIT)
        recent = [
            shaping.highlight(h)
            for h in page.get("results") or []
            if max(
                _parse_instant(h.get("created_at")) or start,
                _parse_instant(h.get("updated_at")) or start,
            )
            >= start
        ]
        if recent:
            groups.append({"item": _item_summary(raw), "highlights": recent})

    result: dict[str, Any] = {
        "since": start.isoformat(),
        "items_checked": len(items),
        "items": groups,
    }
    if data.get("has_more"):
        result["more_items"] = True
        result["note"] = (
            "More items were updated since then than were checked. Raise max_items or use a "
            "later since date to see the rest."
        )
    return result


def _streaks(days: list[date]) -> tuple[int, list[date]]:
    """Return the longest streak length and the run of days ending at the latest day."""
    longest = 0
    run: list[date] = []
    for day in sorted(days):
        if run and day - run[-1] == timedelta(days=1):
            run.append(day)
        else:
            run = [day]
        longest = max(longest, len(run))
    return longest, run


@tool(requires_secrets=SECRETS, metadata=READ_ONLY)
async def summarize_reading_time(
    context: Context,
    since: Annotated[
        str | None,
        f"Start of the period, as an ISO date (YYYY-MM-DD). Defaults to {DEFAULT_READING_DAYS} "
        "days ago.",
    ] = None,
    until: Annotated[
        str | None, "End of the period (inclusive), as an ISO date. Defaults to today."
    ] = None,
    timezone_name: Annotated[
        str,
        "IANA time zone used to assign sessions to days, e.g. 'America/Los_Angeles'. "
        "Defaults to UTC.",
    ] = "UTC",
) -> Annotated[dict, "Reading time totals, averages, streaks and a per-day breakdown"]:
    """Summarize how much the user read over a period: total and average minutes, days read,
    the longest and current streaks, and the busiest day. Use this to answer "how much have
    I read this month?". Makes up to 4 requests."""
    try:
        zone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        raise RetryableToolError(
            f"Unknown time zone '{timezone_name}'.",
            additional_prompt_content="Use an IANA time zone name such as 'Europe/London'.",
        ) from None

    today = _now().astimezone(zone).date()
    start_day = _date_param(since, "since") or today - timedelta(days=DEFAULT_READING_DAYS - 1)
    end_day = _date_param(until, "until") or today
    if end_day < start_day:
        raise RetryableToolError(
            "until is before since.",
            additional_prompt_content="Pass an until date on or after the since date.",
        )
    # Matter filters on a UTC instant; start at local midnight of the first day.
    start_instant = datetime.combine(start_day, datetime.min.time(), zone)

    client = client_from_context(context)
    minutes_by_day: dict[date, float] = defaultdict(float)
    sessions = 0
    cursor = None
    truncated = False
    for page_number in range(MAX_SESSION_PAGES):
        data = await client.get(
            "/reading_sessions",
            since=start_instant.astimezone(timezone.utc).isoformat(),
            limit=MAX_LIMIT,
            cursor=cursor,
        )
        for session in data.get("results") or []:
            started = _parse_instant(session.get("date"))
            if started is None:
                continue
            day = started.astimezone(zone).date()
            if start_day <= day <= end_day:
                minutes_by_day[day] += (session.get("seconds_read") or 0) / 60
                sessions += 1
        cursor = data.get("next_cursor")
        if not (data.get("has_more") and cursor):
            break
        if page_number == MAX_SESSION_PAGES - 1:
            truncated = True

    days_in_range = (end_day - start_day).days + 1
    total = sum(minutes_by_day.values())
    longest, last_run = _streaks(list(minutes_by_day))
    current = (
        len(last_run) if last_run and last_run[-1] >= min(end_day, today) - timedelta(days=1) else 0
    )

    result: dict[str, Any] = {
        "since": start_day.isoformat(),
        "until": end_day.isoformat(),
        "timezone": timezone_name,
        "total_minutes": round(total),
        "sessions": sessions,
        "days_read": len(minutes_by_day),
        "days_in_range": days_in_range,
        "average_minutes_per_day": round(total / days_in_range, 1),
        "average_minutes_per_reading_day": (
            round(total / len(minutes_by_day), 1) if minutes_by_day else 0
        ),
        "longest_streak_days": longest,
        "current_streak_days": current,
    }
    if minutes_by_day:
        busiest = max(minutes_by_day, key=lambda d: minutes_by_day[d])
        result["busiest_day"] = {
            "date": busiest.isoformat(),
            "minutes": round(minutes_by_day[busiest]),
        }
    if days_in_range <= MAX_DAILY_ROWS:
        result["daily_minutes"] = {
            day.isoformat(): round(minutes) for day, minutes in sorted(minutes_by_day.items())
        }
    if truncated:
        result["truncated"] = True
        result["note"] = (
            f"Only the most recent {MAX_SESSION_PAGES * MAX_LIMIT} sessions were counted; use "
            "a later since date for exact totals."
        )
    return result


def _date_param(value: str | None, name: str) -> date | None:
    validated = validate_timestamp(value, name)
    if validated is None:
        return None
    return date.fromisoformat(validated[:10])
