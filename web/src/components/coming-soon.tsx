import type { NavItem } from "../lib/nav";
import { EmptyState } from "./ui/empty-state";
import { PageHeader } from "./ui/page-header";

/** A navigation entry whose page belongs to a later stage. Says so plainly
 *  instead of being a dead link or a fake screen. */
export function ComingSoon({ item }: { item: NavItem }) {
  return (
    <>
      <PageHeader title={item.label} description={item.description} />
      <div className="mt-8 rounded-lg bg-surface shadow-card">
        <EmptyState
          title={item.stage ? `This page arrives in stage ${item.stage}` : "This page isn’t built yet"}
          description="The navigation is in place so the whole app can be judged; the page itself comes later."
        />
      </div>
    </>
  );
}
