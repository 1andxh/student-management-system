import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createRouter, RouterProvider } from "@tanstack/react-router";
import { StrictMode, useEffect } from "react";
import { createRoot } from "react-dom/client";

import { SpinnerIcon } from "./components/icons";
import { AuthProvider, useAuth } from "./lib/auth/auth-context";
import { routeTree } from "./routeTree.gen";
import "./styles.css";

// One QueryClient for the app's lifetime: it *is* the server-state cache.
// (Signing in or out clears it — see AuthProvider.)
const queryClient = new QueryClient();

const router = createRouter({
  routeTree,
  // `auth` is supplied for real by <App> below, on every render. Nothing
  // may load routes before that (see the guard on invalidate below), so
  // this placeholder is never read.
  context: { queryClient, auth: undefined! },
  defaultPreload: "intent",
});

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}

function App() {
  const auth = useAuth();

  // Re-run every route guard when the session changes: signing in sends
  // /login on to the right home, signing out (here or in another tab) or
  // expiring sends a guarded page to /login.
  //
  // Not while loading: the RouterProvider isn't mounted yet, so invalidating
  // would load routes against the placeholder context above, and every
  // guard would throw on `context.auth` being undefined. (It did, on every
  // page load, silently recovered — caught by watching the browser console.)
  useEffect(() => {
    if (auth.state.status !== "loading") void router.invalidate();
  }, [auth.state]);

  // Until the boot refresh answers "signed in or not", guards can't decide
  // anything, so nothing routes yet.
  if (auth.state.status === "loading") {
    return (
      <div className="grid min-h-dvh place-items-center text-ink-3" aria-busy="true">
        <SpinnerIcon className="size-5" />
        <span className="sr-only">Loading…</span>
      </div>
    );
  }
  return <RouterProvider router={router} context={{ auth }} />;
}

const rootElement = document.getElementById("root");
if (!rootElement) throw new Error("index.html is missing #root");

createRoot(rootElement).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <AuthProvider queryClient={queryClient}>
        <App />
      </AuthProvider>
    </QueryClientProvider>
  </StrictMode>,
);
