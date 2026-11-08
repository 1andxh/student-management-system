import { createFileRoute } from "@tanstack/react-router";

import { AreaNotFound } from "../../components/area-not-found";
import { ComingSoon } from "../../components/coming-soon";
import { findNavItem } from "../../lib/nav";

// Placeholder for any page listed in the student sidebar that a later stage
// will build. Real pages get their own route file, which takes precedence
// over this $page match.
//
// Anything not in this role's sidebar (a typo, or the audit log for a plain
// admin) renders the not-found message *here*, inside the shell, rather
// than throwing notFound(): a layout route's notFoundComponent replaces the
// layout itself, which would take the sidebar and Log out with it.
export const Route = createFileRoute("/student/$page")({
  component: function StudentPage() {
    const { page } = Route.useParams();
    const { user } = Route.useRouteContext();
    const item = findNavItem("student", page, user.role);
    return item ? <ComingSoon item={item} /> : <AreaNotFound area="student" />;
  },
});
