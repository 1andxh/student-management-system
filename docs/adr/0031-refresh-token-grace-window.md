# 0031. Grace window and deterministic rotation for refresh tokens

## Status
Accepted. Amends ADR 0009 (rotation). A rotated-away refresh token no longer dies *immediately*: it can be replayed within a grace window. Rotation is now deterministic rather than random.

## Context
ADR 0009 rotates the refresh token on every refresh, atomically, and ADR 0027 put that token in an HttpOnly cookie for the new SPA. Building the SPA's session restore (frontend Stage F3) exposed a failure that rotation always has without a grace window. **Two quick reloads signed the user out**, reproduced in a real browser:
1. Reload #1's boot refresh reaches the server, which rotates the cookie and commits it.
2. Reload #2 aborts #1's request in the browser (`ERR_ABORTED`), and the response carrying the new `Set-Cookie` is thrown away.
3. The browser still holds the old cookie, which the server has already retired. The next refresh is a 401: signed out.

Navigating mid-load, or a connection dropping after the server commits, does the same thing. The client can't prevent it. Solomon chose a grace window over rotating less often or accepting the limitation.

**The first version wasn't enough.** It let the previous token refresh once more by minting a *new random* successor. The `security-auditor` review found the other ordering:
1. Reload #1's aborted request is still running on the server when #2's refresh (the same token) completes first, and #2's cookie is the one the browser keeps.
2. #1 then finishes through the grace path and mints a *second* successor, retiring the one the browser holds.
3. The user is signed out anyway.

The root cause was that a replay wasn't idempotent: each replay produced a different successor, and the last writer won. A unit test confirmed it (first as a strict `xfail`, now passing).

## Decision
- **Rotation is deterministic.** The next token is `derive_successor_token(current)`, an HMAC-SHA256 of the current token keyed by `JWT_SECRET_KEY` with a fixed domain-separation label (`src/sms/core/security.py`). It's unpredictable without the secret, but always the same for a given token. Every replay of a token, whether an aborted request still running or the new page's request, computes the same successor, so the order requests finish in no longer matters. Solomon chose to derive the key from the existing JWT secret rather than add `REFRESH_ROTATION_KEY`: anyone holding the JWT secret can already mint access tokens, so this adds no new exposure. Logins still issue random tokens; only rotations are derived.
- **The previous token stays usable for `settings.refresh_grace_seconds`** (default 30, bounded to 0–120 at startup) after the rotation that retired it. Each `Session` stores `previous_refresh_token_hash` and `rotated_at` (migration `d39b74fa3746`). `SessionRepository.get_for_refresh` matches the current hash, or the previous one inside the window.
- **Presenting the current token** does a normal rotation, as a compare-and-swap: the current token becomes the previous one, and the window starts now.
- **Presenting the previous token inside its window** returns the session's current token, which is that previous token's successor, and **writes nothing**:
  - no second token is minted, and nothing is retired;
  - the window stays anchored to the original rotation, so a stolen previous token can't extend its own life.
  
  If the session has moved past that successor, the replay is refused.
- **Refresh retries once after losing the compare-and-swap.** A request that read the token as current and then lost the race re-reads the session. By then the token sits in the grace slot, already rotated to the same successor this request would have produced. The re-read uses `populate_existing`; otherwise SQLAlchemy's identity map returns the stale copy it already holds.
- **Logout honors the grace slot,** so logging out with the cookie a browser actually holds ends the session.
- **Logout's rate limit is now 120/minute.** It was 20/minute (ADR 0009); login stays at 5, refresh at 20. Logout can only end sessions and tokens can't be guessed, so a tight limit protects little. Meanwhile, at a school behind one IP, a class signing out at the bell could hit 20, and a rejected logout leaves the session alive in that browser (review finding #1). Solomon chose to raise it rather than exempt it.
- **Errors stay uniform.** Unknown, out-of-window, moved-past, expired, revoked and inactive-user tokens all get the same `InvalidRefreshTokenError` (ADR 0008/0009).

**Verified** by tests and in a real browser:
- 2, 3 and 5 rapid reloads, and reloads staggered 5, 15 and 40 ms apart, all stay signed in. Before the grace window, two were enough to sign out.
- Mutation-checked: random successors fail five tests, and removing the retry fails the race test.

### Security review (post-implementation)
A `security-auditor` pass over F3 (this change plus the SPA's auth layer) found nothing critical or high. Outcome:
- **Brought to Solomon and decided:**
  - **#2, the late grace refresh evicting the live token:** fixed with deterministic rotation.
  - **The logout rate limit behind #1:** raised to 120/minute.
- **Fixed directly** (in the SPA; ADR 0028):
  - **#1:** a logout the server didn't confirm (429/403/500) now warns the user instead of looking signed out.
  - **#3:** a tab whose refreshed token belongs to a different user ends its session.
  - **#4:** a refresh still in flight when the session ends can't bring the token back.
  - **#5:** `safeRedirect` rejected `/..//evil.example`, which normalizes to a protocol-relative URL.
  - **#7:** signing out drops `?redirect=`, so the next person doesn't land on the previous person's page.
  - **#8:** the grace setting is bounded.
- **Resolved by #2's fix:** #6, where a user evicted by a thief could log out without ending the thief's session. With deterministic rotation nobody is evicted, and logging out with any token the user holds ends the session for everyone sharing it.

## Consequences
- **The accepted tradeoff, now *silent*:** a refresh token stolen and replayed within 30 seconds of its rotation gets the *same* successor as the legitimate browser, and both carry on with the shared session. The first version of this ADR described theft in the window as having a visible symptom (the user getting evicted). That symptom was the very bug the review found, and the fix removed it. Reuse/theft detection, deferred since ADR 0009, would address this. Revisit the two together if the threat model changes.
- **The chain of refresh tokens is a function of the login token and `JWT_SECRET_KEY`.** Leaking that secret was already a total compromise, since it signs access tokens. Rotating it ends every session's chain, as it already invalidates every access token.
- **Sessions created before the migration have no previous token until their next rotation.**
- **`refresh_grace_seconds` bounds how long a retired token lives.** Aborted reloads need about a second; don't raise it to cover "slow networks". Startup rejects values outside 0–120.
