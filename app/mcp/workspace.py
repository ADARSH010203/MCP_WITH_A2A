"""Safe, bounded workspace tools for MCP."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from app.config.settings import settings


_TEXT_EXTENSIONS = {".txt", ".md", ".json", ".csv", ".py", ".yaml", ".yml"}
_DOCUMENT_EXTENSIONS = {".txt", ".md", ".json", ".csv", ".yaml", ".yml"}


class WorkspaceError(ValueError):
    """Raised when a workspace operation violates the safety policy."""


def _root() -> Path:
    root = Path(settings.mcp_sandbox_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def resolve_workspace_path(relative_path: str) -> Path:
    """Resolve a relative workspace path without permitting traversal."""
    clean = relative_path.strip()
    if not clean:
        raise WorkspaceError("path is required")

    candidate_path = Path(clean)
    if candidate_path.is_absolute():
        raise WorkspaceError("absolute paths are not allowed")

    root = _root()
    candidate = (root / candidate_path).resolve()
    if candidate != root and root not in candidate.parents:
        raise WorkspaceError("path escapes the configured MCP workspace")

    return candidate


def _is_within_root(path: Path) -> bool:
    root = _root()
    resolved = path.resolve()
    return resolved == root or root in resolved.parents


def _validate_file_size(path: Path) -> None:
    if not _is_within_root(path):
        raise WorkspaceError("path escapes the configured MCP workspace")
    if not path.is_file():
        raise WorkspaceError("workspace path is not a file")

    size = path.stat().st_size
    if size > settings.mcp_max_file_bytes:
        raise WorkspaceError(
            f"file exceeds the {settings.mcp_max_file_bytes} byte limit"
        )


def _paginate(
    rows: list[Any],
    *,
    page: int,
    page_size: int,
) -> tuple[list[Any], bool]:
    if page < 1:
        raise WorkspaceError("page must be >= 1")
    if not 1 <= page_size <= settings.mcp_max_page_size:
        raise WorkspaceError(
            f"page_size must be between 1 and {settings.mcp_max_page_size}"
        )

    start = (page - 1) * page_size
    end = start + page_size
    return rows[start:end], end < len(rows)


def list_workspace_files(
    query: str = "",
    page: int = 1,
    page_size: int | None = None,
) -> dict[str, Any]:
    """List bounded workspace files using query-based pagination."""
    size = settings.mcp_default_page_size if page_size is None else page_size
    needle = query.strip().casefold()

    paths = [
        item
        for item in _root().rglob("*")
        if item.is_file()
        and _is_within_root(item)
        and (
            not needle
            or needle in item.relative_to(_root()).as_posix().casefold()
        )
    ]
    paths.sort(key=lambda item: item.relative_to(_root()).as_posix())

    rows, has_next = _paginate(paths, page=page, page_size=size)
    return {
        "files": [
            {
                "path": item.relative_to(_root()).as_posix(),
                "size_bytes": item.stat().st_size,
                "suffix": item.suffix.lower(),
            }
            for item in rows
        ],
        "page": page,
        "page_size": size,
        "total": len(paths),
        "has_next": has_next,
    }


def read_text_document(relative_path: str) -> dict[str, Any]:
    """Read a bounded supported text document."""
    path = resolve_workspace_path(relative_path)
    _validate_file_size(path)

    if path.suffix.lower() not in _DOCUMENT_EXTENSIONS:
        raise WorkspaceError("unsupported document type")

    text = path.read_text(encoding="utf-8")
    return {
        "path": relative_path,
        "content": text[: settings.mcp_max_output_chars],
        "truncated": len(text) > settings.mcp_max_output_chars,
    }


def search_workspace(
    query: str,
    page: int = 1,
    page_size: int | None = None,
) -> dict[str, Any]:
    """Search supported text files without escaping the configured workspace."""
    needle = query.strip().casefold()
    if not needle:
        raise WorkspaceError("search query is required")
    if len(needle) > settings.mcp_max_search_query_chars:
        raise WorkspaceError("search query is too long")

    size = settings.mcp_default_page_size if page_size is None else page_size
    root = _root()
    matches: list[dict[str, Any]] = []

    for path in sorted(root.rglob("*")):
        if len(matches) >= settings.mcp_max_search_results:
            break
        if not path.is_file() or path.suffix.lower() not in _TEXT_EXTENSIONS:
            continue
        try:
            _validate_file_size(path)
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError, WorkspaceError):
            continue

        lowered = content.casefold()
        index = lowered.find(needle)
        if index < 0:
            continue

        start = max(0, index - 120)
        end = min(len(content), index + len(needle) + 180)
        matches.append(
            {
                "path": path.relative_to(root).as_posix(),
                "snippet": content[start:end].replace("
", " "),
            }
        )

    rows, has_next = _paginate(matches, page=page, page_size=size)
    return {
        "matches": rows,
        "page": page,
        "page_size": size,
        "total": len(matches),
        "has_next": has_next,
    }


def analyze_csv_file(
    relative_path: str,
    preview_page: int = 1,
    preview_page_size: int | None = None,
) -> dict[str, Any]:
    """Analyze a bounded CSV using read-only pandas operations."""
    path = resolve_workspace_path(relative_path)
    _validate_file_size(path)

    if path.suffix.lower() != ".csv":
        raise WorkspaceError("analyze_csv_file requires a .csv file")

    frame = pd.read_csv(
        path,
        nrows=settings.mcp_max_csv_rows,
    )
    columns_truncated = len(frame.columns) > settings.mcp_max_csv_columns
    if columns_truncated:
        frame = frame.iloc[:, : settings.mcp_max_csv_columns]
    size = (
        settings.mcp_default_page_size
        if preview_page_size is None
        else preview_page_size
    )
    preview_rows = frame.to_dict(orient="records")
    rows, has_next = _paginate(
        preview_rows,
        page=preview_page,
        page_size=size,
    )

    missing = {
        str(column): int(value)
        for column, value in frame.isna().sum().items()
    }
    numeric_summary = (
        frame.select_dtypes(include="number")
        .describe()
        .round(4)
        .to_dict()
    )

    return {
        "path": relative_path,
        "rows_analyzed": int(len(frame)),
        "columns": [str(column) for column in frame.columns],
        "dtypes": {
            str(column): str(dtype)
            for column, dtype in frame.dtypes.items()
        },
        "missing_values": missing,
        "numeric_summary": numeric_summary,
        "preview": rows,
        "preview_page": preview_page,
        "preview_page_size": size,
        "preview_has_next": has_next,
        "truncated": len(frame) >= settings.mcp_max_csv_rows,
        "columns_truncated": columns_truncated,
    }
