import createClient from "openapi-fetch";

import type { components, paths } from "./api-schema";
import { createAuthMiddleware } from "./auth/middleware";
import { browserLocks, createSession, SessionExpiredError } from "./auth/session";

/**
 * The one typed client every API call goes through. `paths` is generated
 * from the backend's OpenAPI schema (`npm run gen:api`), so a request to a
 * route that doesn't exist, a wrong query param, or a misread response
 * field is a type error rather than a runtime surprise.
 *
 * 127.0.0.1, not localhost: on this machine the two resolve differently
 * (IPv4 vs IPv6), and the backend's CORS allowlist names 127.0.0.1.
 */
export const API_URL = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8001";

export type User = components["schemas"]["UserRead"];
export type Role = User["role"];

/**
 * The refresh call uses plain fetch, not the client below: it must not pass
 * through the auth middleware (a 401 here *is* the answer, not something to
 * refresh and retry). `credentials: "include"` is what sends the HttpOnly
 * refresh cookie cross-origin (5173 → 8001); the server's CORS allows it.
 */
export const session = createSession({
  locks: browserLocks(),
  transport: {
    async refresh() {
      const response = await fetch(`${API_URL}/auth/refresh`, { method: "POST", credentials: "include" });
      if (response.status === 401) throw new SessionExpiredError();
      if (!response.ok) throw new ApiError(response.status, `Refresh failed (${response.status})`);
      const body = (await response.json()) as components["schemas"]["AccessTokenResponse"];
      return body.access_token;
    },
  },
});

const expiredListeners = new Set<() => void>();

/** Called when a request finds the session gone; the auth provider listens. */
export function onSessionExpired(listener: () => void): () => void {
  expiredListeners.add(listener);
  return () => expiredListeners.delete(listener);
}

// credentials: "include" on every request: the browser needs it to *store*
// the cookie from a cross-origin login response, and to send it to
// /auth/refresh and /auth/logout. The cookie's Path=/auth keeps it off every
// other request anyway.
export const api = createClient<paths>({ baseUrl: API_URL, credentials: "include" });
api.use(createAuthMiddleware(session, { onExpired: () => expiredListeners.forEach((listener) => listener()) }));

/** An API error with a message fit to show a person. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly body?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function messageFor(status: number, body: unknown): string {
  if (status === 429) return "Too many attempts. Wait a minute, then try again.";
  if (body && typeof body === "object" && "detail" in body && typeof body.detail === "string") return body.detail;
  if (status >= 500) return "Something went wrong on the server. Try again in a moment.";
  return `The request failed (${status}).`;
}

/**
 * Turns openapi-fetch's { data, error, response } into data-or-throw, so
 * callers (and TanStack Query) see a thrown ApiError with a readable
 * message. A network failure (server unreachable) arrives as a TypeError
 * from fetch and is rethrown as an ApiError with status 0.
 */
export async function unwrap<T>(request: Promise<{ data?: T; error?: unknown; response: Response }>): Promise<T> {
  let result: { data?: T; error?: unknown; response: Response };
  try {
    result = await request;
  } catch {
    throw new ApiError(0, "Couldn’t reach the server. Check your connection and try again.");
  }
  const { data, error, response } = result;
  if (error !== undefined || !response.ok) throw new ApiError(response.status, messageFor(response.status, error), error);
  return data as T;
}
