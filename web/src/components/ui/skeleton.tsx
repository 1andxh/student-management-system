// A placeholder block in the shape of content that's loading. Size it with
// layout classes (h-4 w-32). Purely visual: mark the loading region itself
// aria-busy and give it a "Loading…" label for screen readers. The pulse is
// an opacity animation, and stops under prefers-reduced-motion.

export function Skeleton({ className = "h-4 w-24" }: { className?: string }) {
  return <span aria-hidden="true" className={`block animate-pulse rounded-sm bg-line ${className}`} />;
}
