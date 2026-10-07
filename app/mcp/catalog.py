"""Registry and allowlist for the MCP tool ecosystem."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolDescriptor:
    """Public capability metadata for one MCP tool."""

    name: str
    category: str
    description: str
    read_only: bool
    supports_pagination: bool = False


class MCPToolRegistry:
    """Validated, queryable catalog of registered MCP tools."""

    def __init__(self, descriptors: tuple[ToolDescriptor, ...]) -> None:
        names = [item.name for item in descriptors]
        if len(names) != len(set(names)):
            raise ValueError("MCP tool names must be unique.")
        self._descriptors = {item.name: item for item in descriptors}

    def get(self, name: str) -> ToolDescriptor:
        try:
            return self._descriptors[name]
        except KeyError as exc:
            raise ValueError(f"Unknown MCP tool: {name}") from exc

    def names(self) -> tuple[str, ...]:
        return tuple(self._descriptors)

    def query(
        self,
        *,
        search: str = "",
        category: str = "",
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, object]:
        if page < 1:
            raise ValueError("page must be >= 1")
        if not 1 <= page_size <= 100:
            raise ValueError("page_size must be between 1 and 100")

        needle = search.strip().casefold()
        category_filter = category.strip().casefold()
        matches = [
            item
            for item in self._descriptors.values()
            if (
                not category_filter
                or item.category.casefold() == category_filter
            )
            and (
                not needle
                or needle
                in " ".join(
                    (item.name, item.category, item.description)
                ).casefold()
            )
        ]

        start = (page - 1) * page_size
        end = start + page_size
        rows = matches[start:end]
        return {
            "tools": [
                {
                    "name": item.name,
                    "category": item.category,
                    "description": item.description,
                    "read_only": item.read_only,
                    "supports_pagination": item.supports_pagination,
                }
                for item in rows
            ],
            "page": page,
            "page_size": page_size,
            "total": len(matches),
            "has_next": end < len(matches),
        }


DEFAULT_TOOL_REGISTRY = MCPToolRegistry(
    (
        ToolDescriptor(
            name="calculate",
            category="utilities",
            description="Evaluate bounded numeric arithmetic.",
            read_only=True,
        ),
        ToolDescriptor(
            name="get_exchange_rate",
            category="finance",
            description="Fetch a daily reference exchange rate.",
            read_only=True,
        ),
        ToolDescriptor(
            name="list_workspace_files",
            category="files",
            description="List files inside the configured MCP workspace with pagination.",
            read_only=True,
            supports_pagination=True,
        ),
        ToolDescriptor(
            name="search_workspace",
            category="search",
            description="Search supported text documents inside the configured workspace.",
            read_only=True,
            supports_pagination=True,
        ),
        ToolDescriptor(
            name="read_text_document",
            category="documents",
            description="Read a bounded UTF-8 text document from the workspace.",
            read_only=True,
        ),
        ToolDescriptor(
            name="analyze_csv_file",
            category="data-analysis",
            description="Inspect a bounded CSV dataset and return schema, missing values, numeric summary, and a paginated preview.",
            read_only=True,
            supports_pagination=True,
        ),
        ToolDescriptor(
            name="list_tool_catalog",
            category="meta",
            description="Query the MCP tool catalog using search, category, and pagination.",
            read_only=True,
            supports_pagination=True,
        ),
    )
)
