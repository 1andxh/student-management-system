import { createFileRoute } from "@tanstack/react-router";

import { ComingSoon } from "../../components/coming-soon";
import { findNavItem } from "../../lib/nav";

export const Route = createFileRoute("/admin/")({
  component: function AdminHome() {
    const { user } = Route.useRouteContext();
    const item = findNavItem("admin", null, user.role);
    return item ? <ComingSoon item={{ ...item, stage: "F6a" }} /> : null;
  },
});
