"""Checks every registered tool against the design rules in docs/SPEC.md.

Each phase PR adds its tool names to EXPECTED_TOOLS.
"""

from arcade_mcp_server.metadata import ServiceDomain

from arcade_matter.server import app

READ_TOOLS: set[str] = {
    "GetAccount",
    "ListReadingSessions",
    "ListItems",
    "GetItem",
    "GetItemContent",
    "SearchLibrary",
    "ListHighlights",
    "ListTags",
}
WRITE_TOOLS: set[str] = {
    "SaveItem",
    "UpdateItem",
    "DeleteItem",
    "AddTag",
    "RemoveTag",
    "RenameTag",
    "DeleteTag",
    "SetHighlightNote",
    "DeleteHighlight",
}
EXPECTED_TOOLS = READ_TOOLS | WRITE_TOOLS


def _definitions():
    return [tool.definition for tool in app._catalog]


def test_registers_expected_tools():
    names = {d.name for d in _definitions()}
    assert names == EXPECTED_TOOLS
    assert all(str(d.fully_qualified_name).startswith("Matter.") for d in _definitions())


def test_every_tool_requires_the_matter_token():
    for d in _definitions():
        secrets = {s.key for s in d.requirements.secrets or []}
        assert secrets == {"MATTER_API_TOKEN"}, d.name
        assert d.requirements.authorization is None, d.name


def test_every_tool_declares_metadata():
    for d in _definitions():
        assert d.metadata is not None, d.name
        assert d.metadata.classification.service_domains == [ServiceDomain.DOCUMENTS]
        assert d.metadata.behavior.open_world is True


def test_read_tools_are_read_only():
    for d in _definitions():
        if d.name in READ_TOOLS:
            assert d.metadata.behavior.read_only is True, d.name
            assert d.metadata.behavior.destructive is False, d.name


def test_write_tools_flag_deletes_as_destructive():
    for d in _definitions():
        if d.name in WRITE_TOOLS:
            behavior = d.metadata.behavior
            assert behavior.read_only is False, d.name
            assert behavior.destructive is d.name.startswith("Delete"), d.name


def test_every_tool_has_a_description():
    for d in _definitions():
        assert d.description and len(d.description) > 20, d.name


def test_server_identity():
    assert app.name == "matter"
