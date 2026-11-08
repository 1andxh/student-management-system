import { createFileRoute, Outlet } from "@tanstack/react-router";

import { AppShell } from "../../components/app-shell";
import { requireRole } from "../../lib/auth/guards";

// Layout + guard for every /teacher page.
export const Route = createFileRoute("/teacher")({
  beforeLoad: ({ context, location }) => requireRole(context.auth.state, location.href, ["teacher"]),
  component: TeacherLayout,
});

function TeacherLayout() {
  const { user } = Route.useRouteContext();
  return (
    <AppShell area="teacher" user={user}>
      <Outlet />
    </AppShell>
  );
}
