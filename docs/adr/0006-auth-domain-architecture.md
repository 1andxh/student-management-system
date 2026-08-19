# 0006. Auth domain architecture and RBAC retrofit pattern

## Status
Accepted

## Context
Stage 2 needed to add authentication (JWT login) and role-based access control without breaking the domain-oriented architecture from ADR 0002, and needed to retrofit the already-existing Students domain (built open, pre-auth) behind real permission checks — the ordering explicitly chosen in ADR 0001 (auth lands early precisely so later stages don't have to retrofit). Two implementation-time decisions came up that aren't obvious from just reading the code: where JWT/password logic should live relative to the domain-oriented layering, and a FastAPI default that would have produced the wrong status code.

## Decision
- **`core/security.py` holds only domain-agnostic primitives** — `hash_password`/`verify_password` (Argon2) and `create_access_token`/`decode_access_token` (JWT encode/decode with no knowledge of `User`). `core/` stays free of any domain concept, matching ADR 0002.
- **`domains/auth/` owns everything that knows about `User`** — the model, `AuthService.login`, and critically `get_current_user`/`require_role(*roles)` (`domains/auth/dependencies.py`), even though every other domain depends on these. Auth is treated as upstream of every other domain (everything may depend on it; it depends on nothing else) rather than folding `get_current_user` into `core/`, which would have forced `core` to import a domain model — backwards from the intended dependency direction.
- **RBAC retrofit pattern for existing domains**: mutating routes get `dependencies=[Depends(require_role(...))]` at the route-decorator level (not as a function parameter, since the route body doesn't need the resolved user); read routes get `dependencies=[Depends(get_current_user)]` — any authenticated user, regardless of role. This is the pattern every future domain's router should follow when it needs the same read-open/write-restricted shape.
- **`HTTPBearer(auto_error=False)`**, not the default `auto_error=True`. FastAPI's `HTTPBearer` returns 403 for a *missing* Authorization header by default, not 401 — `get_current_user` handles the `None` case itself and raises `UnauthorizedError` (401) explicitly, matching the plan's explicit requirement that a missing token is 401 and only a wrong role is 403.

## Consequences
- Any future domain needing auth-gated routes imports `get_current_user`/`require_role` from `sms.domains.auth.dependencies` — a normal domain-to-domain dependency on `auth`, not a `core` import. This is intentional, not a layering violation to "fix" later.
- If a future FastAPI security dependency is added (e.g. an API-key scheme) with its own `auto_error` default, check what status code it produces on missing credentials before assuming it's correct — this project's contract is 401 for "not authenticated," 403 for "authenticated but not allowed."
- `core/security.py` must never import from `domains/` — if a change seems to require that, the function being added likely belongs in `domains/auth/` instead.
