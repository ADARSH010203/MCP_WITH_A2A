# H2: Capability and Authorization Validation

The coordinator separates authentication from specialist authorization.

## Routing boundary

Only agents present in the configured authorization allowlist are eligible for deterministic or semantic routing. An explicit agent selection is validated before a collaboration plan is built.

## Capability contract

Each registered specialist declares:

- supported capabilities
- input types
- output types
- dependencies
- execution parallelism

The coordinator rejects selections that violate the registered contract.

## Remote A2A boundary

A remote specialist must advertise a compatible capability in its A2A Agent Card. The advertised default input and output modes are also checked before the remote client is created.

## Configuration

Set `A2A_ALLOWED_AGENTS` to a comma-separated allowlist. Leave it empty to allow all registered specialists.

Authentication such as the A2A bearer API key remains a separate boundary from this capability authorization policy.
