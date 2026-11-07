// What a list shows when it has nothing in it: say what's missing and what
// to do about it, in the interface's own words — never a blank table.
// No illustration or icon: an icon that only repeats the title is noise.

export interface EmptyStateProps {
  /** "No students in 7A yet" */
  title: string;
  /** The next step: "Assign students to this section to enroll them in its classes." */
  description?: string;
  action?: React.ReactNode;
}

export function EmptyState({ title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center px-6 py-12 text-center">
      <p className="font-medium text-ink">{title}</p>
      {description && <p className="mt-1 max-w-sm text-pretty text-small text-ink-3">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
