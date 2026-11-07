import { AlertCircleIcon, AlertTriangleIcon, CheckCircleIcon } from "../icons";

// An inline message in the page (a toast is for things that happen
// elsewhere or in passing). Soft tinted card with a status icon — no
// colored side strip (removed at review, ADR 0029). The icon's shape
// carries the state too, so it never depends on color alone.

export type NoticeTone = "error" | "warning" | "success";

const tones: Record<NoticeTone, { icon: React.ReactNode; className: string; role: "alert" | "status" }> = {
  error: { icon: <AlertCircleIcon className="size-5" />, className: "bg-red-pen-tint text-red-pen", role: "alert" },
  warning: { icon: <AlertTriangleIcon className="size-5" />, className: "bg-warn-tint text-warn", role: "alert" },
  success: { icon: <CheckCircleIcon className="size-5" />, className: "bg-ok-tint text-ok", role: "status" },
};

export interface NoticeProps {
  tone: NoticeTone;
  /** What happened, specifically: "Ms. Lovelace already teaches period 3 on Monday". */
  title: string;
  /** How to fix it, or what follows from it. */
  children?: React.ReactNode;
}

export function Notice({ tone, title, children }: NoticeProps) {
  const t = tones[tone];
  return (
    <div role={t.role} className={`flex gap-3 rounded-lg p-4 ${t.className}`}>
      <span className="shrink-0">{t.icon}</span>
      <div className="min-w-0">
        <p className="font-medium">{title}</p>
        {children && <div className="mt-1 text-small text-ink-2">{children}</div>}
      </div>
    </div>
  );
}
