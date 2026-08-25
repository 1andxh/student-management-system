# 0008. Stage 2 security review findings

## Status
Accepted

## Context
Per ADR 0006/the `agent-team` skill's own guidance, an independent `security-auditor` review was run against the Stage 2 auth implementation before considering it done. It returned 5 findings. Two carried no real tradeoff and were applied immediately; two carried genuine tradeoffs and were brought to the user as explicit questions rather than resolved unilaterally — both were approved and applied; one was noted as forward-looking only.

## Decision
**Applied directly** (no real tradeoff, clear improvement):
- `Settings.jwt_secret_key` now has a `field_validator` rejecting secrets under 32 characters or matching a known placeholder value (`src/sms/core/config.py`) — fails app startup rather than silently running with a forgeable JWT signing key.
- `UserRepository.get_by_email` now compares case-insensitively (`func.lower(...)`), and `LoginRequest.email` is now `EmailStr` — closes a latent case-sensitivity footgun before any user-creation endpoint exists to trigger it.

**Presented as a tradeoff, then applied on approval**:
- **Login enumeration/timing oracle** — `AuthService.login` (`src/sms/domains/auth/service.py`) now always runs an Argon2 verification, against `sms.core.security.DUMMY_PASSWORD_HASH` when no user matches the email, and always raises the same `InvalidCredentialsError` for unknown email, wrong password, *and* an inactive account. The UX cost — a real deactivated user no longer gets a distinguishing message from login — was accepted explicitly, not discovered later. (`get_current_user`'s separate inactive-user check, for an already-authenticated session, is unaffected — that scenario isn't an enumeration risk since the caller already holds a valid token.)
- **No rate limiting on `POST /auth/login`** — added `slowapi`, a per-IP `5/minute` limit on the login route (`src/sms/domains/auth/router.py`), a dedicated `RateLimitExceeded` handler matching this project's `{"detail": ...}` error shape (`src/sms/core/exception_handlers.py`), and `SlowAPIMiddleware` ordered *before* `RequestLoggingMiddleware` in `main.py` so a rate-limited request still gets logged, not silently skipped. The module-level `limiter` singleton's in-memory counters persist across the process, so `tests/conftest.py` gained an autouse `_reset_rate_limiter` fixture — same isolation principle as `db_session`'s SAVEPOINT rollback, applied to in-memory state instead of the database.

**Noted, not acted on**: no token revocation mechanism (no `jti`/`token_version`). Explicitly forward-looking — irrelevant until a password-change or logout-everywhere feature exists to need it. Revisit when either is built, not before.

## Consequences
- Login no longer distinguishes "wrong password" from "unknown email" from "inactive account" in either response content or timing — don't reintroduce a differentiated message or an early-return-before-hashing shortcut later without re-opening this decision.
- `/auth/login` is capped at 5 requests/minute per client IP. A legitimate user who mistypes their password repeatedly will eventually see 429, not 401 — expected, not a bug. If a real deployment needs a different threshold or per-account (not per-IP) limiting, that's a deliberate change to make here, not a default to assume is already handled elsewhere.
- Any future rate-limited route needs the same `_reset_rate_limiter` awareness — a new route decorated with `@limiter.limit(...)` and tested without resetting the limiter between tests will silently accumulate state across unrelated tests, the same class of bug the SAVEPOINT fixture already prevents for the database.
- Confirmed-clean by the review, not re-litigated later without a new reason: Argon2 password storage, explicit JWT algorithm pinning (no `alg=none` exposure), `hashed_password` never serialized in any response, exception handlers not leaking stack traces, and the RBAC wiring on every Students route (traced individually, no bypass found).
