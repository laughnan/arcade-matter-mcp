import pytest
from arcade_mcp_server.exceptions import ToolExecutionError

from arcade_matter.tools.account import get_account


async def test_get_account(matter, context):
    matter.add(
        "GET",
        "/me",
        {
            "object": "account",
            "id": "act_1",
            "name": "Sam Reader",
            "email": "sam@example.com",
            "created_at": "2024-01-01T00:00:00Z",
            "rate_limit": {"read": 120, "write": 30, "save": 10, "markdown": 20, "burst": 5},
        },
        headers={
            "X-RateLimit-Limit": "120",
            "X-RateLimit-Remaining": "87",
            "X-RateLimit-Reset": "1791144000",
        },
    )

    result = await get_account(context)

    assert result["name"] == "Sam Reader"
    assert result["rate_limits"]["markdown"] == 20
    assert result["read_quota"] == {
        "limit": 120,
        "remaining": 87,
        "resets_at": "2026-10-04T20:00:00Z",
    }
    assert matter.last.headers["Authorization"] == "Bearer mat_test"


async def test_get_account_without_rate_limit_headers(matter, context):
    matter.add("GET", "/me", {"object": "account", "id": "act_1", "name": "Sam Reader"})

    result = await get_account(context)

    assert "read_quota" not in result


async def test_get_account_pro_required(matter, context):
    matter.error("GET", "/me", 403, "forbidden", "Matter Pro required")

    with pytest.raises(ToolExecutionError, match="Matter Pro"):
        await get_account(context)
