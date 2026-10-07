"""MCP server with an explicit, policy-controlled tool ecosystem."""

from mcp.server.fastmcp import FastMCP  # type: ignore

from app.config.settings import settings
from app.mcp.catalog import DEFAULT_TOOL_REGISTRY, MCPToolRegistry
from app.mcp.tools.calculator import calculate
from app.mcp.tools.currency import get_exchange_rate
from app.mcp.workspace import (
    analyze_csv_file,
    list_workspace_files,
    read_text_document,
    search_workspace,
)

MCP_HOST = "0.0.0.0"
MCP_PORT = 3000

_TOOL_FUNCTIONS = {
    "calculate": calculate,
    "get_exchange_rate": get_exchange_rate,
    "list_workspace_files": list_workspace_files,
    "search_workspace": search_workspace,
    "read_text_document": read_text_document,
    "analyze_csv_file": analyze_csv_file,
}


def _build_tool_registry() -> MCPToolRegistry:
    allowed = settings.mcp_allowed_tools
    if not allowed:
        return DEFAULT_TOOL_REGISTRY

    unknown = set(allowed) - set(DEFAULT_TOOL_REGISTRY.names())
    if unknown:
        names = ", ".join(sorted(unknown))
        raise ValueError(f"Unsupported MCP tools: {names}")

    descriptors = tuple(
        DEFAULT_TOOL_REGISTRY.get(name)
        for name in DEFAULT_TOOL_REGISTRY.names()
        if name in allowed
    )
    return MCPToolRegistry(descriptors)


TOOL_REGISTRY = _build_tool_registry()
mcp = FastMCP(name="MCPTools", host=MCP_HOST, port=MCP_PORT)


def list_tool_catalog(
    search: str = "",
    category: str = "",
    page: int = 1,
    page_size: int = 20,
) -> dict[str, object]:
    """Query the enabled MCP tool catalog with bounded pagination."""
    if "list_tool_catalog" not in TOOL_REGISTRY.names():
        raise ValueError("list_tool_catalog is disabled by MCP_ALLOWED_TOOLS")
    return TOOL_REGISTRY.query(
        search=search,
        category=category,
        page=page,
        page_size=page_size,
    )


_TOOL_FUNCTIONS["list_tool_catalog"] = list_tool_catalog

for tool_name in TOOL_REGISTRY.names():
    function = _TOOL_FUNCTIONS.get(tool_name)
    if function is None:
        raise ValueError(
            f"MCP tool '{tool_name}' has no implementation registered."
        )
    mcp.tool()(function)


if __name__ == "__main__":
    mcp.run(transport="sse")
