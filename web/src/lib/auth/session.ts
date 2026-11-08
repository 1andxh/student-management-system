/**
 * The client half of ADR 0027's auth: the access token lives here, in
 * memory only (never localStorage — anything script can read, injected
 * script can read), and the refresh token is an HttpOnly cookie this code
 * never sees. A reload loses the access token; refresh() gets a new one.
 *
 * The hard part is concurrency. The backend rotates the refresh cookie on
 * every refresh, atomically (ADR 0009): of two refreshes sent with the same
 * cookie, the second gets 401. So:
 *  - within a tab, concurrent callers share ONE in-flight refresh
 *    (several API calls hitting 401 together must not each refresh);
 *  - across tabs, refreshes are serialized with a Web Lock, so a tab
 *    waiting its turn sends the cookie the previous tab just rotated to.
 * Either missing, and the app logs its own user out. session.test.ts
 * reproduces both races against a fake with the backend's rotation rule.
 */

/** The refresh call, injected so tests can stand in a fake server. */
export interface RefreshTransport {
  /** POST /auth/refresh with the HttpOnly cookie. Resolves to a new access
   *  token; rejects with SessionExpiredError when the server says 401. */
  refresh(): Promise<string>;
}

/** The subset of navigator.locks used here; injected for tests. */
export interface LockManagerLike {
  request<T>(name: string, callback: () => Promise<T>): Promise<T>;
}

export class SessionExpiredError extends Error {
  constructor() {
    super("Session expired");
    this.name = "SessionExpiredError";
  }
}

export interface Session {
  getAccessToken(): string | null;
  setAccessToken(token: string): void;
  /** New access token, or null if the session is gone (401). Rejects on
   *  anything else (e.g. offline): a network blip is not a logout. */
  refresh(): Promise<string | null>;
  clear(): void;
}

const LOCK_NAME = "sms-auth-refresh";

/** The `sub` (user id) of a JWT access token, read without verifying —
 *  only to notice a *change* of user; the server verifies every token. */
export function subjectOf(token: string): string | null {
  try {
    const payload = token.split(".")[1];
    if (!payload) return null;
    const json = atob(payload.replace(/-/g, "+").replace(/_/g, "/"));
    const sub = (JSON.parse(json) as { sub?: unknown }).sub;
    return typeof sub === "string" ? sub : null;
  } catch {
    return null;
  }
}

export function createSession({ transport, locks }: { transport: RefreshTransport; locks: LockManagerLike }): Session {
  let token: string | null = null;
  // Whose session this tab holds. The refresh cookie is shared by every tab,
  // so if another tab signs in as someone else, this tab's next refresh
  // returns *their* token. Comparing subjects catches that, and ends this
  // tab's session instead of silently carrying on as the other person.
  let subject: string | null = null;
  // Bumped by clear(). A refresh that started before the session ended
  // must not write its late answer back — the previous user's token would
  // quietly return and ride on every later request.
  let epoch = 0;
  let inFlight: Promise<string | null> | null = null;

  const session: Session = {
    getAccessToken: () => token,
    setAccessToken: (next) => {
      token = next;
      subject = subjectOf(next);
    },
    clear: () => {
      token = null;
      subject = null;
      inFlight = null;
      epoch++;
    },
    refresh() {
      if (inFlight) return inFlight;
      const startedIn = epoch;
      const expected = subject;
      const attempt: Promise<string | null> = locks
        .request(LOCK_NAME, async () => {
          try {
            const next = await transport.refresh();
            if (epoch !== startedIn) return null; // session ended meanwhile
            const nextSubject = subjectOf(next);
            if (expected !== null && nextSubject !== expected) {
              session.clear(); // the cookie now belongs to someone else
              return null;
            }
            token = next;
            subject = nextSubject;
            return next;
          } catch (error) {
            if (error instanceof SessionExpiredError) {
              if (epoch === startedIn) {
                token = null;
                subject = null;
              }
              return null;
            }
            throw error;
          }
        })
        .finally(() => {
          // Only forget *this* attempt: clear() may already have let a newer
          // one start, and that one must stay shared.
          if (inFlight === attempt) inFlight = null;
        });
      inFlight = attempt;
      return attempt;
    },
  };
  return session;
}

/**
 * navigator.locks where the browser has it (every current browser); a
 * same-tab queue otherwise, which keeps the single-tab guarantee and only
 * loses the cross-tab one.
 */
export function browserLocks(): LockManagerLike {
  if (typeof navigator !== "undefined" && navigator.locks) {
    // The DOM typings say request() returns whatever the callback returns —
    // for an async callback, Promise<Promise<T>>. Promises flatten at
    // runtime; awaiting here makes the type say so too, without a cast.
    return { request: async (name, callback) => await navigator.locks.request(name, callback) };
  }
  let tail: Promise<unknown> = Promise.resolve();
  return {
    request(_name, callback) {
      const run = tail.then(callback);
      tail = run.catch(() => undefined);
      return run;
    },
  };
}
