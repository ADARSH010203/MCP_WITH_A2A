"""MCP server exposing the currency exchange-rate demonstration tool."""

from mcp.server.fastmcp import FastMCP  # type: ignore

from app.mcp.tools.calculator import calculate
from app.mcp.tools.currency import get_exchange_rate

MCP_HOST = "0.0.0.0"
MCP_PORT = 3000

mcp = FastMCP(name="CurrencyTools", host=MCP_HOST, port=MCP_PORT)
mcp.tool()(get_exchange_rate)
mcp.tool()(calculate)

if __name__ == "__main__":
    mcp.run(transport="sse")
