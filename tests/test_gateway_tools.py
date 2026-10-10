"""Keeps the gateway tool lists in docs/security/gateways.md in step with tool metadata."""

import re
from pathlib import Path

from arcade_matter.server import app

DOC = Path(__file__).resolve().parents[1] / "docs" / "security" / "gateways.md"


def _documented(section: str) -> set[str]:
    text = DOC.read_text()
    match = re.search(rf"<!-- {section}:start -->(.*?)<!-- {section}:end -->", text, re.S)
    assert match, f"{section} list missing from {DOC.name}"
    return set(re.findall(r"`(Matter\.\w+)`", match.group(1)))


def _tools(predicate) -> set[str]:
    return {
        str(tool.definition.fully_qualified_name)
        for tool in app._catalog
        if predicate(tool.definition.metadata.behavior)
    }


def test_read_gateway_list_is_exactly_the_read_only_tools():
    assert _documented("read-tools") == _tools(lambda b: b.read_only)


def test_write_gateway_list_is_the_non_destructive_writes():
    assert _documented("write-tools") == _tools(lambda b: not b.read_only and not b.destructive)


def test_destructive_list_is_exactly_the_destructive_tools():
    assert _documented("destructive-tools") == _tools(lambda b: b.destructive)


def test_no_destructive_tool_is_marked_read_only():
    assert not _tools(lambda b: b.destructive and b.read_only)
