from types import SimpleNamespace

import pytest

from app.mcp.catalog import DEFAULT_TOOL_REGISTRY, MCPToolRegistry, ToolDescriptor
from app.mcp.workspace import (
    WorkspaceError,
    analyze_csv_file,
    list_workspace_files,
    read_text_document,
    resolve_workspace_path,
    search_workspace,
)


def _workspace_settings(root, **overrides):
    values = {
        "mcp_sandbox_root": str(root),
        "mcp_max_file_bytes": 2_000_000,
        "mcp_max_output_chars": 20_000,
        "mcp_max_search_query_chars": 200,
        "mcp_max_search_results": 500,
        "mcp_default_page_size": 2,
        "mcp_max_page_size": 100,
        "mcp_max_csv_rows": 10_000,
        "mcp_max_csv_columns": 100,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_tool_registry_rejects_duplicate_names():
    with pytest.raises(ValueError, match="must be unique"):
        MCPToolRegistry(
            (
                ToolDescriptor("x", "test", "X", True),
                ToolDescriptor("x", "test", "Duplicate", True),
            )
        )


def test_tool_registry_supports_query_and_pagination():
    result = DEFAULT_TOOL_REGISTRY.query(
        search="file",
        category="files",
        page=1,
        page_size=10,
    )

    assert result["total"] == 1
    assert result["tools"][0]["name"] == "list_workspace_files"
    assert result["has_next"] is False


def test_workspace_path_rejects_absolute_and_traversal(monkeypatch, tmp_path):
    import app.mcp.workspace as module

    monkeypatch.setattr(module, "settings", _workspace_settings(tmp_path))

    with pytest.raises(WorkspaceError, match="absolute paths"):
        resolve_workspace_path(str(tmp_path / "file.txt"))

    outside = tmp_path.parent / "outside.txt"
    outside.write_text("private", encoding="utf-8")
    with pytest.raises(WorkspaceError, match="escapes"):
        resolve_workspace_path("../outside.txt")


def test_workspace_tools_support_search_and_pagination(monkeypatch, tmp_path):
    import app.mcp.workspace as module

    monkeypatch.setattr(module, "settings", _workspace_settings(tmp_path))

    (tmp_path / "a.txt").write_text("alpha database record", encoding="utf-8")
    (tmp_path / "b.md").write_text("alpha documentation", encoding="utf-8")
    (tmp_path / "c.txt").write_text("unrelated", encoding="utf-8")

    files = list_workspace_files(page=1, page_size=2)
    assert files["total"] == 3
    assert len(files["files"]) == 2
    assert files["has_next"] is True

    matches = search_workspace("alpha", page=1, page_size=1)
    assert matches["total"] == 2
    assert len(matches["matches"]) == 1
    assert matches["has_next"] is True


def test_workspace_read_document_is_bounded(monkeypatch, tmp_path):
    import app.mcp.workspace as module

    monkeypatch.setattr(
        module,
        "settings",
        _workspace_settings(tmp_path, mcp_max_output_chars=5),
    )
    (tmp_path / "note.txt").write_text("1234567890", encoding="utf-8")

    result = read_text_document("note.txt")
    assert result["content"] == "12345"
    assert result["truncated"] is True


def test_workspace_rejects_symlink_escape(monkeypatch, tmp_path):
    import app.mcp.workspace as module

    monkeypatch.setattr(module, "settings", _workspace_settings(tmp_path))
    outside = tmp_path.parent / "secret.txt"
    outside.write_text("do not read", encoding="utf-8")
    link = tmp_path / "linked.txt"
    link.symlink_to(outside)

    with pytest.raises(WorkspaceError, match="escapes"):
        read_text_document("linked.txt")


def test_csv_analysis_returns_bounded_schema_summary(monkeypatch, tmp_path):
    import app.mcp.workspace as module

    monkeypatch.setattr(
        module,
        "settings",
        _workspace_settings(
            tmp_path,
            mcp_max_csv_rows=2,
            mcp_max_csv_columns=2,
            mcp_default_page_size=1,
        ),
    )
    (tmp_path / "data.csv").write_text(
        "name,age,score\nalice,30,10\nbob,40,20\ncarol,50,30\n",
        encoding="utf-8",
    )

    result = analyze_csv_file("data.csv", preview_page=1)

    assert result["rows_analyzed"] == 2
    assert result["columns"] == ["name", "age"]
    assert result["columns_truncated"] is True
    assert len(result["preview"]) == 1
    assert result["truncated"] is True


def test_tool_allowlist_rejects_unknown_names(monkeypatch):
    import app.mcp.server as server_module

    monkeypatch.setattr(
        server_module.settings,
        "mcp_allowed_tools",
        ("does-not-exist",),
    )
    with pytest.raises(ValueError, match="Unsupported MCP tools"):
        server_module._build_tool_registry()


def test_tool_allowlist_filters_catalog(monkeypatch):
    import app.mcp.server as server_module

    monkeypatch.setattr(
        server_module.settings,
        "mcp_allowed_tools",
        ("calculate", "list_tool_catalog"),
    )

    registry = server_module._build_tool_registry()
    assert registry.names() == ("calculate", "list_tool_catalog")
