import type { Middleware } from "openapi-fetch";

import type { Session } from "./session";

/** 401 here means bad credentials or no session, never "token expired":
 *  refreshing and retrying would be wrong (and /auth/refresh would recurse). */
const NO_RETRY = new Set(["/auth/login", "/auth/login-pin", "/auth/refresh", "/auth/logout"]);

/**
 * Attaches the in-memory access token to every API request. On a 401 it
 * refreshes (single-flight, see session.ts) and retries the request once.
 * If the session is gone, it calls onExpired (the app sends the user to
 * /login) and hands the 401 back to the caller.
 */
export function createAuthMiddleware(session: Session, { onExpired }: { onExpired: () => void }): Middleware {
  // A request body is a stream, consumed when sent. To retry a POST, keep a
  // copy taken *before* the first send, keyed by openapi-fetch's request id.
  const originals = new Map<string, Request>();

  return {
    onRequest({ request, id, schemaPath }) {
      const token = session.getAccessToken();
      if (token) request.headers.set("Authorization", `Bearer ${token}`);
      if (!NO_RETRY.has(schemaPath)) originals.set(id, request.clone());
      return request;
    },

    async onResponse({ response, id, options }) {
      const original = originals.get(id);
      originals.delete(id);
      if (response.status !== 401 || !original) return response;

      let token: string | null;
      try {
        token = await session.refresh();
      } catch {
        return response; // couldn't reach the server: not a logout
      }
      if (!token) {
        onExpired();
        return response;
      }
      original.headers.set("Authorization", `Bearer ${token}`);
      // options.fetch is the raw fetch, outside this middleware, so a
      // second 401 comes straight back: one retry, never a loop.
      return options.fetch(original);
    },

    onError({ id }) {
      originals.delete(id);
    },
  };
}
