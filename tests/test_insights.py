from datetime import datetime, timezone

import pytest
from arcade_mcp_server.exceptions import RetryableToolError
from conftest import make_highlight, make_item, make_list

from arcade_matter.tools import insights
from arcade_matter.tools.insights import (
    get_item_with_highlights,
    list_recent_highlights,
    summarize_reading_time,
)

NOW = datetime(2026, 10, 4, 18, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def fixed_now(monkeypatch: pytest.MonkeyPatch) -> datetime:
    monkeypatch.setattr(insights, "_now", lambda: NOW)
    return NOW


def session(when: str, seconds: int) -> dict:
    return {"object": "reading_session", "id": f"rs_{when}", "date": when, "seconds_read": seconds}


# --- GetItemWithHighlights ---


async def test_get_item_with_highlights(matter, context):
    matter.add("GET", "/items/itm_1", make_item())
    matter.add("GET", "/items/itm_1/annotations", make_list([make_highlight()], "more"))

    result = await get_item_with_highlights(context, "itm_1")

    assert result["item"]["title"] == "Notes on Attention"
    assert [h["id"] for h in result["highlights"]] == ["ann_1"]
    assert result["more_highlights"] is True
    assert matter.last.url.params["limit"] == "100"
    assert len(matter.requests) == 2


# --- ListRecentHighlights ---


async def test_list_recent_highlights_groups_and_filters(matter, context):
    matter.add(
        "GET",
        "/items",
        make_list(
            [
                make_item(id="itm_1"),
                make_item(id="itm_2", title="Old Highlights Only"),
                make_item(id="itm_3", title="Note Edited"),
            ]
        ),
    )
    matter.add(
        "GET",
        "/items/itm_1/annotations",
        make_list(
            [
                make_highlight(
                    id="ann_new",
                    created_at="2026-10-02T09:00:00Z",
                    updated_at="2026-10-02T09:00:00Z",
                ),
                make_highlight(
                    id="ann_old",
                    created_at="2026-08-01T09:00:00Z",
                    updated_at="2026-08-01T09:00:00Z",
                ),
            ]
        ),
    )
    matter.add(
        "GET",
        "/items/itm_2/annotations",
        make_list(
            [
                make_highlight(
                    id="ann_x", created_at="2026-01-01T00:00:00Z", updated_at="2026-01-01T00:00:00Z"
                )
            ]
        ),
    )
    matter.add(
        "GET",
        "/items/itm_3/annotations",
        make_list(
            [
                make_highlight(
                    id="ann_edit",
                    created_at="2026-05-01T00:00:00Z",
                    updated_at="2026-10-03T00:00:00Z",
                    note="Revisited",
                )
            ]
        ),
    )

    result = await list_recent_highlights(context, since="2026-09-27")

    items_request = matter.requests[0]
    assert dict(items_request.url.params) == {
        "status": "all",
        "updated_since": "2026-09-27T00:00:00+00:00",
        "order": "updated",
        "limit": "10",
    }
    assert result["items_checked"] == 3
    assert [g["item"]["id"] for g in result["items"]] == ["itm_1", "itm_3"]
    assert [h["id"] for h in result["items"][0]["highlights"]] == ["ann_new"]
    assert result["items"][0]["item"] == {
        "id": "itm_1",
        "title": "Notes on Attention",
        "url": "https://example.com/attention",
        "author": "Ada Writer",
        "site": "Example Blog",
        "status": "queue",
    }
    assert "more_items" not in result


async def test_list_recent_highlights_defaults_and_caps(matter, context):
    matter.add("GET", "/items", make_list([], next_cursor="more"))

    result = await list_recent_highlights(context, max_items=500)

    params = matter.requests[0].url.params
    assert params["updated_since"] == "2026-09-27T18:00:00+00:00"
    assert params["limit"] == "20"
    assert result["more_items"] is True
    assert "max_items" in result["note"]


# --- SummarizeReadingTime ---


async def test_summarize_reading_time(matter, context):
    matter.add(
        "GET",
        "/reading_sessions",
        make_list(
            [
                session("2026-10-04T08:00:00Z", 600),
                session("2026-10-03T21:00:00Z", 1200),
                session("2026-10-03T07:00:00Z", 600),
                session("2026-10-01T12:00:00Z", 300),
                session("2026-09-30T12:00:00Z", 300),
            ]
        ),
    )

    result = await summarize_reading_time(context, since="2026-09-29")

    assert matter.last.url.params["since"] == "2026-09-29T00:00:00+00:00"
    assert result == {
        "since": "2026-09-29",
        "until": "2026-10-04",
        "timezone": "UTC",
        "total_minutes": 50,
        "sessions": 5,
        "days_read": 4,
        "days_in_range": 6,
        "average_minutes_per_day": 8.3,
        "average_minutes_per_reading_day": 12.5,
        "longest_streak_days": 2,
        "current_streak_days": 2,
        "busiest_day": {"date": "2026-10-03", "minutes": 30},
        "daily_minutes": {"2026-09-30": 5, "2026-10-01": 5, "2026-10-03": 30, "2026-10-04": 10},
    }


async def test_summarize_reading_time_uses_timezone(matter, context):
    # 03:00 UTC on Oct 3 is the evening of Oct 2 in Los Angeles.
    matter.add("GET", "/reading_sessions", make_list([session("2026-10-03T03:00:00Z", 600)]))

    result = await summarize_reading_time(
        context, since="2026-10-01", until="2026-10-02", timezone_name="America/Los_Angeles"
    )

    assert matter.last.url.params["since"] == "2026-10-01T07:00:00+00:00"
    assert result["daily_minutes"] == {"2026-10-02": 10}
    assert result["current_streak_days"] == 1


async def test_summarize_reading_time_excludes_sessions_after_until(matter, context):
    matter.add(
        "GET",
        "/reading_sessions",
        make_list([session("2026-10-04T08:00:00Z", 600), session("2026-09-15T08:00:00Z", 60)]),
    )

    result = await summarize_reading_time(context, since="2026-09-01", until="2026-09-30")

    assert result["total_minutes"] == 1
    assert result["current_streak_days"] == 0


async def test_summarize_reading_time_paginates_and_truncates(matter, context):
    for _ in range(insights.MAX_SESSION_PAGES):
        matter.add(
            "GET", "/reading_sessions", make_list([session("2026-10-04T08:00:00Z", 60)], "next")
        )

    result = await summarize_reading_time(context)

    assert len(matter.requests) == insights.MAX_SESSION_PAGES
    assert matter.last.url.params["cursor"] == "next"
    assert result["truncated"] is True
    assert result["sessions"] == insights.MAX_SESSION_PAGES


async def test_summarize_reading_time_empty(matter, context):
    matter.add("GET", "/reading_sessions", make_list([]))

    result = await summarize_reading_time(context)

    assert result["total_minutes"] == 0
    assert result["days_in_range"] == insights.DEFAULT_READING_DAYS
    assert "busiest_day" not in result


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"timezone_name": "Mars/Olympus"}, "Unknown time zone"),
        ({"since": "2026-10-04", "until": "2026-10-01"}, "until is before since"),
        ({"since": "last month"}, "Invalid since"),
    ],
)
async def test_summarize_reading_time_validates(matter, context, kwargs, message):
    with pytest.raises(RetryableToolError, match=message):
        await summarize_reading_time(context, **kwargs)

    assert matter.requests == []
