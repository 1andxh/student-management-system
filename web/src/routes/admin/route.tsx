import { createFileRoute, Outlet } from "@tanstack/react-router";

import { AppShell } from "../../components/app-shell";
import { requireRole } from "../../lib/auth/guards";

// Layout + guard for every /admin page.
export const Route = createFileRoute("/admin")({
  beforeLoad: ({ context, location }) => requireRole(context.auth.state, location.href, ["admin", "super_admin"]),
  component: AdminLayout,
});

function AdminLayout() {
  const { user } = Route.useRouteContext();
  return (
    <AppShell area="admin" user={user}>
      <Outlet />
    </AppShell>
  );
}
