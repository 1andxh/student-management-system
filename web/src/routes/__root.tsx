import type { QueryClient } from "@tanstack/react-query";
import { createRootRouteWithContext, Link, Outlet } from "@tanstack/react-router";

import { EmptyState } from "../components/ui/empty-state";
import { Toaster } from "../components/ui/toast";
import type { Auth } from "../lib/auth/auth-context";

// Router context: what every route's beforeLoad can read without importing
// a singleton. `auth` is passed in by <App> on every render, and the router
// is invalidated whenever it changes, so guards always see the current
// session (signing in or out re-runs them).
export interface RouterContext {
  queryClient: QueryClient;
  auth: Auth;
}

export const Route = createRootRouteWithContext<RouterContext>()({
  component: () => (
    <>
      <Outlet />
      {/* One toast region for the whole app, outside any page, so a toast
          raised just before navigating still shows on the next page. */}
      <Toaster />
    </>
  ),
  notFoundComponent: () => (
    <main className="grid min-h-dvh place-items-center px-4">
      <EmptyState
        title="There’s no page here"
        description="The link may be out of date, or the page may have moved."
        action={
          <Link to="/" className="font-medium text-accent-ink underline underline-offset-4">
            Go to your home page
          </Link>
        }
      />
    </main>
  ),
});
