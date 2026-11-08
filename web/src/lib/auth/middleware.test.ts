import createClient from "openapi-fetch";
import { describe, expect, test, vi } from "vitest";

import { createAuthMiddleware } from "./middleware";
import type { Session } from "./session";

/** A Session stub: our own interface, so a plain object is enough here. */
function stubSession(initial: string | null, refreshed: string | null): Session & { refreshCalls: number } {
  let token = initial;
  const s = {
    refreshCalls: 0,
    getAccessToken: () => token,
    setAccessToken: (t: string) => {
      token = t;
    },
    clear: () => {
      token = null;
    },
    refresh: async () => {
      s.refreshCalls++;
      token = refreshed;
      return refreshed;
    },
  };
  return s;
}

/**
 * Fake API: accepts only "Bearer valid", 401 otherwise. Records every
 * request (method, path, auth header, body) so tests can see retries.
 */
function fakeApi() {
  const seen: { method: string; path: string; auth: string | null; body: string }[] = [];
  const fetch = async (request: Request) => {
    const url = new URL(request.url);
    seen.push({ method: request.method, path: url.pathname, auth: request.headers.get("Authorization"), body: await request.clone().text() });
    if (request.headers.get("Authorization") !== "Bearer valid") {
      return new Response(JSON.stringify({ detail: "Not authenticated" }), { status: 401, headers: { "Content-Type": "application/json" } });
    }
    return new Response(JSON.stringify({ ok: true }), { status: 200, headers: { "Content-Type": "application/json" } });
  };
  return { fetch, seen };
}

function client(session: Session, onExpired = vi.fn()) {
  const api = fakeApi();
  // Untyped paths: these tests are about the middleware, not the schema.
  const c = createClient<Record<string, never>>({ baseUrl: "http://api.test", fetch: api.fetch });
  c.use(createAuthMiddleware(session, { onExpired }));
  return { c, api, onExpired };
}

describe("attaching the token", () => {
  test("sends the access token as a Bearer header", async () => {
    const { c, api } = client(stubSession("valid", null));

    await c.GET("/students");

    expect(api.seen[0]?.auth).toBe("Bearer valid");
  });

  test("sends no Authorization header when signed out", async () => {
    const { c, api } = client(stubSession(null, null));

    await c.GET("/health");

    expect(api.seen[0]?.auth).toBeNull();
  });
});

describe("on 401", () => {
  test("refreshes once and retries the original request, body intact", async () => {
    // A POST's body is a stream that's consumed when sent, so the retry
    // needs a copy taken *before* the first send.
    const session = stubSession("stale", "valid");
    const { c, api } = client(session);

    // @ts-expect-error untyped test path
    const result = await c.POST("/grades", { body: { score: 18 } });

    expect(result.response.status).toBe(200);
    expect(session.refreshCalls).toBe(1);
    expect(api.seen.map((r) => [r.method, r.auth, r.body])).toEqual([
      ["POST", "Bearer stale", '{"score":18}'],
      ["POST", "Bearer valid", '{"score":18}'],
    ]);
  });

  test("when the session is gone, reports it and returns the 401", async () => {
    const onExpired = vi.fn();
    const { c } = client(stubSession("stale", null), onExpired);

    const result = await c.GET("/students");

    expect(result.response.status).toBe(401);
    expect(onExpired).toHaveBeenCalledTimes(1);
  });

  test("retries only once, never loops", async () => {
    // Refresh "succeeds" but the new token is still rejected: one retry,
    // then give up, instead of refreshing forever.
    const session = stubSession("stale", "also-rejected");
    const { c, api } = client(session);

    const result = await c.GET("/students");

    expect(result.response.status).toBe(401);
    expect(session.refreshCalls).toBe(1);
    expect(api.seen).toHaveLength(2);
  });

  test("leaves /auth/* alone: a 401 from login means wrong credentials, not expiry", async () => {
    const session = stubSession(null, "valid");
    const onExpired = vi.fn();
    const { c, api } = client(session, onExpired);

    // @ts-expect-error untyped test path
    const result = await c.POST("/auth/login", { body: { email: "a@b.c", password: "x" } });

    expect(result.response.status).toBe(401);
    expect(session.refreshCalls).toBe(0);
    expect(onExpired).not.toHaveBeenCalled();
    expect(api.seen).toHaveLength(1);
  });
});
