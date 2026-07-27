# ADR-001: The local API's trust boundary is the browser, not the network interface

Status: Proposed (partially implemented — see "Done so far")
Date: 2026-07-24

## Context

PageCap's engine binds to `127.0.0.1:8765` and the project has treated "bound
to loopback" as equivalent to "only the user can reach it". That is not true
for a machine running a web browser. Any website the user visits can issue
cross-origin requests to `http://127.0.0.1:8765`. What stops those requests
from being *useful* to an attacker is CORS — and CORS alone — because the API
has no authentication by default.

This audit found three ways that single control was thinner than assumed:

1. `allow_origins=["null"]` was unconditional. The packaged Electron renderer
   loads over `file://` and so sends `Origin: null` — but so does a sandboxed
   `<iframe>` on any website. One `<iframe sandbox srcdoc="…fetch…">` gave an
   arbitrary page full read/write access to the API.
2. WebSocket upgrades are not subject to CORS at all (browsers do not preflight
   `ws://`), and Starlette does not run HTTP middleware on the websocket scope.
   `/ws/{job_id}` was therefore unauthenticated and any-origin regardless of
   the CORS configuration.
3. `GET /templates` and `GET /schedules` returned the embedded `AuthConfig`
   verbatim, i.e. the user's plaintext password and TOTP secret for third-party
   sites. `/credentials` already stripped these; the two newer endpoints did
   not, so the redaction rule lived in one place out of three.

Chained, these gave any web page the user visited a read of their saved
credentials for other sites. The individual defects are fixed. The underlying
architectural fact is not: **an unauthenticated HTTP API on loopback is
reachable by hostile code, and every new endpoint is a new hole unless the
default is "deny".**

## Decision

Move the engine from *allowlist-the-origin* to *authenticate-the-caller* as the
primary control, and make the token mandatory rather than opt-in.

- Generate a token at first run, persist it beside the database with 0600, and
  require it on every route except `/health`. `PAGECAP_API_TOKEN` continues to
  override it.
- Ship the token to legitimate clients out-of-band: Electron injects it into
  the renderer (already implemented); the CLI reads the key file directly; the
  Vite dev server reads it via a `.env.local` written by `npm run dev:engine`.
- Keep CORS as defence in depth, not as the control.
- Add a repository fitness function: a test that fails when a route is added
  without appearing in the authenticated-route inventory, so "new endpoint,
  new hole" cannot recur silently.

## Consequences

Positive
- A hostile page can no longer do anything with the API even if it guesses a
  job ID or forges an `Origin`.
- The security property stops depending on every future endpoint author
  remembering to redact secrets.
- Makes the "tunnel the API somewhere else" use case safe by default rather
  than by configuration.

Negative
- Breaking change for any existing script that calls the API unauthenticated.
- `curl http://127.0.0.1:8765/jobs` stops working out of the box, which is a
  real ergonomic cost for a developer-facing local tool.
- Token-in-query-string (unavoidable for `<img src>`, `<a download>` and
  WebSocket, which cannot set headers) puts the token in browser history and
  any proxy logs. Mitigated by per-launch rotation in Electron; not mitigated
  for the persisted-token path.

## Migration path

1. **Expand.** Add token generation + the key file. Accept both authenticated
   and unauthenticated requests; log a deprecation warning with the caller's
   `User-Agent` on every unauthenticated one. *(No behaviour change.)*
2. Update all first-party clients — Electron (done), `@pagecap/core` (done),
   the UI (done), the CLI, and the README's `curl` examples — to send the token.
3. Ship one release in state (1) so out-of-tree scripts surface in the logs.
4. **Contract.** Flip the default to reject unauthenticated requests. Provide
   `PAGECAP_REQUIRE_AUTH=0` as a documented, warned-about escape hatch for one
   further release, then remove it.
5. Add the route-inventory fitness function to CI in the same PR as step 4.

## Done so far (this audit)

- `Origin: null` is now opt-in via `PAGECAP_ALLOW_NULL_ORIGIN`, and Electron
  sets it together with a per-launch random `PAGECAP_API_TOKEN`.
- `/ws/{job_id}` validates the token when configured, and otherwise checks the
  `Origin` header against the same allowlist the HTTP layer uses.
- Secrets are excluded from every template/schedule/credential response via a
  single shared `models.PUBLIC_EXCLUDE`, covered by tests.
- Token comparison uses `hmac.compare_digest`.
