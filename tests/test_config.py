"""Non-GUI tests for the application foundation."""

from batikcraft_studio.config import WORKSPACES, get_workspace


def test_workspace_keys_are_unique() -> None:
    keys = [workspace.key for workspace in WORKSPACES]
    assert len(keys) == len(set(keys))


def test_expected_workspace_order() -> None:
    assert [workspace.key for workspace in WORKSPACES] == [
        "dashboard",
        "editor",
        "batikification",
        "preview",
        "publish",
    ]


def test_get_workspace_returns_definition() -> None:
    workspace = get_workspace("batikification")
    assert workspace.label == "Object Batikfication"
    assert workspace.title
    assert workspace.description


def test_get_workspace_rejects_unknown_key() -> None:
    try:
        get_workspace("unknown")
    except KeyError as exc:
        assert "Unknown workspace" in str(exc)
    else:
        raise AssertionError("Unknown workspace must raise KeyError")
