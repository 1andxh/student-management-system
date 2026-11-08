import { describe, expect, test } from "vitest";

import { createSession, SessionExpiredError, type LockManagerLike, type RefreshTransport } from "./session";

/**
 * A stand-in for POST /auth/refresh with the backend's real rotation rule
 * (ADR 0009, SessionRepository.rotate): the request carries whatever cookie
 * the browser holds when it's *sent*; the server rotates only if that cookie
 * is still current when it's *processed*. Two requests sent with the same
 * cookie → the second finds it already rotated → 401. One server = one
 * browser, so every "tab" built on it shares the cookie, as real tabs do.
 */
function fakeServer() {
  let cookie = "rt-0";
  let issued = 0;
  let calls = 0;
  let revoked = false;
  const transport: RefreshTransport = {
    async refresh() {
      calls++;
      const sent = cookie;
      await new Promise((resolve) => setTimeout(resolve, 5)); // network + DB
      if (revoked || sent !== cookie) throw new SessionExpiredError();
      issued++;
      cookie = `rt-${issued}`;
      return `access-${issued}`;
    },
  };
  return {
    transport,
    get calls() {
      return calls;
    },
    revoke() {
      revoked = true;
    },
  };
}

/** navigator.locks stand-in: one holder at a time, in request order. */
function serialLocks(): LockManagerLike {
  let tail: Promise<unknown> = Promise.resolve();
  return {
    request(_name, callback) {
      const run = tail.then(callback);
      tail = run.catch(() => undefined);
      return run;
    },
  };
}

/** No cross-tab coordination at all: what we'd have without the lock. */
const noLocks: LockManagerLike = { request: (_name, callback) => callback() };

describe("within one tab", () => {
  test("concurrent refreshes share a single request", async () => {
    // Several API calls hitting 401 at once must not each refresh: with
    // rotation, every refresh after the first would be rejected and the
    // user logged out by their own page.
    const server = fakeServer();
    const session = createSession({ transport: server.transport, locks: serialLocks() });

    const tokens = await Promise.all([session.refresh(), session.refresh(), session.refresh()]);

    expect(server.calls).toBe(1);
    expect(tokens).toEqual(["access-1", "access-1", "access-1"]);
    expect(session.getAccessToken()).toBe("access-1");
  });

  test("a refresh after the previous one settled makes a new request", async () => {
    const server = fakeServer();
    const session = createSession({ transport: server.transport, locks: serialLocks() });

    await session.refresh();
    const second = await session.refresh();

    expect(server.calls).toBe(2);
    expect(second).toBe("access-2");
  });

  test("an expired session resolves to null and forgets the token", async () => {
    const server = fakeServer();
    const session = createSession({ transport: server.transport, locks: serialLocks() });
    session.setAccessToken("access-old");
    server.revoke();

    await expect(session.refresh()).resolves.toBeNull();
    expect(session.getAccessToken()).toBeNull();
  });

  test("a network failure is not a logout", async () => {
    // Offline for a moment must not throw the user out: only a 401 means
    // the session is gone. Anything else propagates and the token stays.
    const session = createSession({
      transport: { refresh: () => Promise.reject(new TypeError("Failed to fetch")) },
      locks: serialLocks(),
    });
    session.setAccessToken("access-current");

    await expect(session.refresh()).rejects.toThrow("Failed to fetch");
    expect(session.getAccessToken()).toBe("access-current");
  });
});

describe("across tabs", () => {
  test("two tabs refreshing at once both stay signed in, because the lock serializes them", async () => {
    const server = fakeServer();
    const locks = serialLocks(); // navigator.locks is shared by all tabs of an origin
    const tabA = createSession({ transport: server.transport, locks });
    const tabB = createSession({ transport: server.transport, locks });

    const [a, b] = await Promise.all([tabA.refresh(), tabB.refresh()]);

    expect(a).not.toBeNull();
    expect(b).not.toBeNull();
  });

  test("without the lock, rotation logs one of them out (why the lock exists)", async () => {
    // Pins down the failure the lock prevents, against the same fake server:
    // if this ever passes with both tabs signed in, the fake no longer
    // models the backend and the test above proves nothing.
    const server = fakeServer();
    const tabA = createSession({ transport: server.transport, locks: noLocks });
    const tabB = createSession({ transport: server.transport, locks: noLocks });

    const results = await Promise.all([tabA.refresh(), tabB.refresh()]);

    expect(results.filter((token) => token === null)).toHaveLength(1);
  });
});

/** A JWT-shaped token whose payload carries `sub` (the backend puts the
 *  user id there). Unsigned: the client only reads it, never trusts it for
 *  anything the server doesn't check itself. */
function tokenFor(sub: string, n = 0): string {
  const b64 = (o: object) => btoa(JSON.stringify(o)).replace(/=+$/, "").replace(/\+/g, "-").replace(/\//g, "_");
  return `${b64({ alg: "HS256" })}.${b64({ sub, n })}.sig`;
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => (resolve = r));
  return { promise, resolve };
}

describe("ending a session", () => {
  test("a refresh still in flight when the session ends doesn't bring the token back", async () => {
    // Logout (here or from another tab) clears the token while a refresh
    // is on the wire. Its late answer must be discarded, or the previous
    // user's token quietly returns — and rides on every later request.
    const pending = deferred<string>();
    const session = createSession({ transport: { refresh: () => pending.promise }, locks: serialLocks() });
    session.setAccessToken(tokenFor("user-x"));

    const refreshing = session.refresh();
    session.clear();
    pending.resolve(tokenFor("user-x", 1));

    await expect(refreshing).resolves.toBeNull();
    expect(session.getAccessToken()).toBeNull();
  });
});

describe("identity", () => {
  test("a refreshed token for a different user ends the session instead of switching users", async () => {
    // Another tab signed in as someone else, so the shared cookie now
    // belongs to them. This tab must not carry on as that person.
    const session = createSession({
      transport: { refresh: async () => tokenFor("user-y") },
      locks: serialLocks(),
    });
    session.setAccessToken(tokenFor("user-x"));

    await expect(session.refresh()).resolves.toBeNull();
    expect(session.getAccessToken()).toBeNull();
  });

  test("the boot refresh (no user yet) accepts whoever the cookie belongs to", async () => {
    const session = createSession({
      transport: { refresh: async () => tokenFor("user-y") },
      locks: serialLocks(),
    });

    await expect(session.refresh()).resolves.toBe(tokenFor("user-y"));
  });
});
