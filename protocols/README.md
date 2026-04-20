# Backend Protocols

This package holds transport payload contracts that cross backend or API
boundaries.

Keep this package narrow:

- Put HTTP/SSE/polling/server-to-server payloads here when multiple backends or
  transports share the same semantic shape.
- Do not put database row models, repository protocols, provider configs, or
  service-private helper types here.
- Add sibling protocol modules only when a real split lane needs them; do not
  add filler files to make the directory look populated.

The durable design ruling is recorded in
`mycel-db-design/program/doc/core/shared-protocol-package-boundary-ruling-2026-04-18.md`.
