import { Link } from "@tanstack/react-router";

import type { Area } from "../lib/nav";
import { EmptyState } from "./ui/empty-state";

/** A missing page *inside* an area: rendered within the area's shell, so
 *  the sidebar (and Log out) stay put instead of the whole app vanishing. */
export function AreaNotFound({ area }: { area: Area }) {
  return (
    <div className="mt-8 rounded-lg bg-surface shadow-card">
      <EmptyState
        title="There’s no page here"
        description="The link may be out of date, or this page isn’t available to your account."
        action={
          <Link to={`/${area}`} className="font-medium text-accent-ink underline underline-offset-4">
            Back to your home page
          </Link>
        }
      />
    </div>
  );
}
