"""MCP server exposing the currency exchange-rate demonstration tool."""

from mcp.server.fastmcp import FastMCP  # type: ignore

MCP_HOST = "0.0.0.0"
MCP_PORT = 3000

mcp = FastMCP(
    name="CurrencyTools",
    host=MCP_HOST,
    port=MCP_PORT,
)


@mcp.tool()
def get_exchange_rate(
    currency_from: str = "USD",
    currency_to: str = "EUR",
    currency_date: str = "latest",
) -> dict:
    """Return a placeholder exchange rate for the requested currency pair.

    This tool is intentionally deterministic for the MCP/A2A demo. It does not
    query a live exchange-rate provider.
    """
    base = currency_from.strip().upper()
    target = currency_to.strip().upper()
    date = currency_date.strip() or "latest"

    if len(base) != 3 or len(target) != 3:
        raise ValueError("currency_from and currency_to must be 3-letter currency codes")

    if base == target:
        rate = 1.0
    else:
        rate = 0.85

    return {
        "amount": 1,
        "base": base,
        "date": date,
        "rates": {target: rate},
    }


if __name__ == "__main__":
    mcp.run(transport="sse")
