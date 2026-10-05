import pytest
from arcade_mcp_server.exceptions import RetryableToolError

from arcade_matter.tools._common import MAX_LIMIT, clamp_limit, validate_timestamp


@pytest.mark.parametrize(("value", "expected"), [(0, 1), (-5, 1), (25, 25), (1000, MAX_LIMIT)])
def test_clamp_limit(value, expected):
    assert clamp_limit(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("2026-10-01", "2026-10-01T00:00:00Z"),
        (" 2026-10-01 ", "2026-10-01T00:00:00Z"),
        ("2026-10-01T12:00:00Z", "2026-10-01T12:00:00Z"),
        ("2026-10-01T12:00:00.250Z", "2026-10-01T12:00:00Z"),
        ("2026-10-01T12:00:00+02:00", "2026-10-01T10:00:00Z"),
        ("2026-10-01T12:00:00", "2026-10-01T12:00:00Z"),
    ],
)
def test_validate_timestamp(value, expected):
    assert validate_timestamp(value, "since") == expected


@pytest.mark.parametrize("value", ["yesterday", "2026-13-01", "10/01/2026"])
def test_validate_timestamp_rejects(value):
    with pytest.raises(RetryableToolError, match="Invalid since"):
        validate_timestamp(value, "since")
