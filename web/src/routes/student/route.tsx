import { createFileRoute, Outlet } from "@tanstack/react-router";

import { AppShell } from "../../components/app-shell";
import { requireRole } from "../../lib/auth/guards";

// Layout + guard for every /student page.
export const Route = createFileRoute("/student")({
  beforeLoad: ({ context, location }) => requireRole(context.auth.state, location.href, ["student"]),
  component: StudentLayout,
});

function StudentLayout() {
  const { user } = Route.useRouteContext();
  return (
    <AppShell area="student" user={user}>
      <Outlet />
    </AppShell>
  );
}
