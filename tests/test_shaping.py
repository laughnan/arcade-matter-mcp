from conftest import make_highlight, make_item, make_list, make_tag

from arcade_matter import shaping


def test_item_is_compact_and_flattened():
    shaped = shaping.item(make_item())

    assert shaped == {
        "id": "itm_1",
        "title": "Notes on Attention",
        "url": "https://example.com/attention",
        "site": "Example Blog",
        "author": "Ada Writer",
        "status": "queue",
        "content_type": "article",
        "word_count": 2400,
        "progress_percent": 25,
        "tags": [{"id": "tag_ai", "name": "ai"}],
        "excerpt": "A short look at how attention works.",
        "updated_at": "2026-10-01T12:00:00Z",
    }


def test_item_flags_and_processing_status():
    shaped = shaping.item(
        make_item(is_favorite=True, processing_status="processing", author=None, tags=[])
    )

    assert shaped["favorite"] is True
    assert shaped["processing_status"] == "processing"
    assert "author" not in shaped
    assert "tags" not in shaped


def test_item_truncates_long_excerpt():
    shaped = shaping.item(make_item(excerpt="word " * 200))

    assert len(shaped["excerpt"]) == shaping.EXCERPT_CHARS
    assert shaped["excerpt"].endswith("…")


def test_item_progress_rounds_and_keeps_zero():
    assert shaping.item(make_item(reading_progress=0.0))["progress_percent"] == 0
    assert shaping.item(make_item(reading_progress=0.996))["progress_percent"] == 100


def test_highlight_and_tag():
    assert shaping.highlight(make_highlight(note="Key idea")) == {
        "id": "ann_1",
        "item_id": "itm_1",
        "text": "Attention is a limited resource.",
        "note": "Key idea",
        "created_at": "2026-10-01T12:05:00Z",
        "updated_at": "2026-10-01T12:05:00Z",
    }
    assert shaping.tag(make_tag()) == {
        "id": "tag_ai",
        "name": "ai",
        "item_count": 12,
        "created_at": "2026-01-10T09:00:00Z",
    }


def test_account_keeps_rate_limits():
    shaped = shaping.account(
        {
            "object": "account",
            "id": "act_1",
            "name": "Sam Reader",
            "email": "sam@example.com",
            "created_at": "2024-01-01T00:00:00Z",
            "rate_limit": {"read": 120, "write": 30},
        }
    )

    assert shaped["rate_limits"] == {"read": 120, "write": 30}
    assert "object" not in shaped


def test_page_includes_cursor_only_when_more():
    more = shaping.page(make_list([make_tag()], next_cursor="abc"), "tags", shaping.tag)
    last = shaping.page(make_list([make_tag()]), "tags", shaping.tag)

    assert more["next_cursor"] == "abc"
    assert len(more["tags"]) == 1
    assert "next_cursor" not in last
