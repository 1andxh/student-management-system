import { createFileRoute } from "@tanstack/react-router";

import { ComingSoon } from "../../components/coming-soon";
import { findNavItem } from "../../lib/nav";

export const Route = createFileRoute("/teacher/")({
  component: function TeacherHome() {
    const { user } = Route.useRouteContext();
    const item = findNavItem("teacher", null, user.role);
    return item ? <ComingSoon item={{ ...item, stage: "F4" }} /> : null;
  },
});
