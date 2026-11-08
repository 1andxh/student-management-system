import { redirect } from "@tanstack/react-router";

import type { Role, User } from "../api";
import { homeFor, type AuthState } from "./auth-context";

/**
 * Route guard for an area's layout route (beforeLoad). Signed out → /login,
 * remembering where they were going; signed in with the wrong role → their
 * own home. Returns the user so child routes get it typed via context.
 *
 * This is navigation, not security: hiding a page from a student stops
 * nothing by itself. The API enforces every permission (require_role on the
 * backend); the guard just keeps people out of pages that would only fail.
 */
export function requireRole(state: AuthState, href: string, allowed: Role[]): { user: User } {
  if (state.status === "anonymous" && state.signedOut) {
    // Signed out on purpose: the next person to sign in here shouldn't be
    // sent to the previous person's last page (or learn its URL).
    throw redirect({ to: "/login", replace: true });
  }
  if (state.status !== "authenticated") {
    throw redirect({ to: "/login", search: { redirect: href } });
  }
  if (!allowed.includes(state.user.role)) {
    throw redirect({ to: homeFor(state.user.role) });
  }
  return { user: state.user };
}
