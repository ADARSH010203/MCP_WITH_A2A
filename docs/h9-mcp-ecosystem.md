# H9: MCP Tool Ecosystem and Safe Tool Access

The MCP layer now exposes a small, policy-controlled ecosystem instead of an unbounded collection of tools.

## Current tool domains

- utilities: bounded arithmetic
- finance: daily exchange-rate lookup
- files: paginated workspace listing
- search: bounded text search across supported workspace documents
- documents: bounded UTF-8 document reading
- data-analysis: bounded CSV schema, missing-value, numeric-summary, and preview analysis
- meta: queryable tool catalog

## Tool policy

`MCP_ALLOWED_TOOLS` is an optional comma-separated allowlist. Unknown names fail at MCP server startup. An empty value enables the registered safe catalog.

The catalog exposes category, description, read-only status, and pagination support.

## Filesystem safety

File tools operate only inside `MCP_SANDBOX_ROOT`. Absolute paths, traversal outside the root, and symlink escapes are rejected.

Reads are bounded by file-size and output-size limits. Search queries and result counts are bounded. CSV parsing is bounded by file size, row count, column count, and preview page size.

## Pagination and query access

Workspace listing, text search, CSV previews, and tool-catalog queries use explicit page/page-size controls. This prevents the MCP layer from turning a single request into an unbounded resource enumeration.

## Intentionally deferred

Arbitrary code execution is not enabled in this phase. A production code-execution MCP tool needs an isolated sandbox, resource limits, network policy, filesystem isolation, and a dedicated security test suite; adding a raw `exec`-style tool here would weaken the architecture rather than strengthen it.

A future Search provider or Database tool can plug into the same registry and policy layer without changing the core MCP server contract.
