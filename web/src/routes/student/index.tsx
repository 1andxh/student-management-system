import { createFileRoute } from "@tanstack/react-router";

import { ComingSoon } from "../../components/coming-soon";
import { findNavItem } from "../../lib/nav";

export const Route = createFileRoute("/student/")({
  component: function StudentHome() {
    const { user } = Route.useRouteContext();
    const item = findNavItem("student", null, user.role);
    return item ? <ComingSoon item={{ ...item, stage: "F5" }} /> : null;
  },
});
