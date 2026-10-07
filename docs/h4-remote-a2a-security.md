# H4: Remote A2A Security

Remote specialists are treated as untrusted network peers.

## Transport

Remote specialist URLs must use HTTPS by default. This policy is controlled by `A2A_REMOTE_REQUIRE_HTTPS=true`.

## Authentication

Remote specialists must have a bearer credential by default. Configure per-agent credentials with `A2A_SPECIALIST_API_KEYS`; a global A2A key remains available as a fallback where appropriate. Anonymous remote calls can only be enabled explicitly with `A2A_REMOTE_REQUIRE_AUTH=false`.

## Agent Card pinning

The remote Agent Card URL must remain on the configured service origin. Embedded credentials in either configured or advertised URLs are rejected.

Capability compatibility is enforced by H2 before a remote client is created.

For production multi-agent deployments, keep remote URLs and credentials in deployment secrets rather than user input.
