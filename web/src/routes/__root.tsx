import type { QueryClient } from "@tanstack/react-query";
import { createRootRouteWithContext, Outlet } from "@tanstack/react-router";

// Router context: what every route's loader/beforeLoad can reach without
// importing a singleton. F3 adds the auth session here, which is what the
// role guards (beforeLoad) will read.
export interface RouterContext {
  queryClient: QueryClient;
}

export const Route = createRootRouteWithContext<RouterContext>()({
  component: () => <Outlet />,
});
