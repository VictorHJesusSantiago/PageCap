# ADR-002: Version the HTTP API under /v1 and retire the unversioned paths

Status: Accepted
Date: 2026-07-26

## Context

Every route was mounted at the root (`/extract`, `/jobs/{id}`, `/ws/{id}`). The
API is consumed by three first-party clients (`@pagecap/core`, the Electron
renderer, the CLI) and, because it is a documented local HTTP surface, by
whatever ad-hoc scripts users have written against it.

With no version in the path there is no way to change a response shape without
breaking every consumer at once. This audit needed exactly that: `/jobs` went
from returning `{"jobs": [...]}` (unbounded) to a keyset-paginated
`{"jobs": [...], "next_cursor": ..., "total": ...}`, errors went from
`{"detail": "..."}` to RFC 7807 `application/problem+json`, and
`GET /templates` stopped returning secrets. Each of those is a breaking change
delivered with no negotiation mechanism.

## Decision

Mount the whole router twice:

- `/v1/*` — canonical, documented in OpenAPI, what clients should use.
- `/*` — the same handlers, `include_in_schema=False`, with `Deprecation: true`,
  `Sunset: Wed, 31 Dec 2026 23:59:59 GMT` and a `Link: <...>; rel="successor-version"`
  header on every response.

The WebSocket is mounted at both `/v1/ws/{job_id}` and `/ws/{job_id}` for the
same reason.

Additive changes (new optional request fields, new response keys) stay within
`v1`. A `v2` is only minted for a breaking change: removing or renaming a field,
narrowing a type, or changing a status code's meaning.

## Consequences

Positive
- Breaking changes become negotiable instead of instantaneous.
- Clients can be migrated one at a time; the deprecation headers make stale
  callers discoverable from the response itself, not from a changelog.
- OpenAPI documents exactly one surface, so `/docs` stops showing each route
  twice.

Negative
- Both mounts share one implementation, so the legacy path is not frozen — it
  inherits the same behaviour changes as `/v1`. It preserves *URLs*, not
  response shapes. This is a deliberate trade: maintaining a genuinely frozen
  v0 would mean duplicating handlers, which for a single-user local tool costs
  more than it protects.
- Two mounts double the route count in the router, which slightly slows startup
  and shows up in route-matching. Immaterial at this scale.

## Migration path

1. **Done** — both mounts live; `@pagecap/core` (and therefore the UI and
   Electron) target `/v1`. `_normalized_path()` strips the prefix so auth and
   health-exemption policy is written once, not per mount.
2. Update the README's `curl` examples and the CLI to `/v1`.
3. Watch for `Deprecation`-header hits in logs (legacy responses are tagged, so
   a log filter finds them) through the sunset date.
4. After the sunset date, delete `app.include_router(router)` and the
   `app.websocket("/ws/{job_id}")` line. Nothing else changes.

## Notes

`/health`, `/health/live` and `/health/ready` are reachable unversioned without
deprecation headers, permanently. A supervisor's probe configuration should not
have to be rewritten for an application-level API version bump.
