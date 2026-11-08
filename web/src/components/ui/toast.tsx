import {
  Button as AriaButton,
  Text,
  UNSTABLE_Toast as AriaToast,
  UNSTABLE_ToastContent as AriaToastContent,
  UNSTABLE_ToastQueue as ToastQueue,
  UNSTABLE_ToastRegion as AriaToastRegion,
} from "react-aria-components";

import { AlertCircleIcon, CheckCircleIcon, InfoIcon, XIcon } from "../icons";

// React Aria's toast primitives are still marked UNSTABLE_ (their API may
// change in a future release). Used anyway because they handle what's easy
// to get wrong — a live region so toasts are announced, a landmark users
// can jump to (F6), focus restoration when the last toast closes — and the
// exact-pinned version means nothing changes until an upgrade is chosen.
// Everything else imports from this file, so an API change lands here only.

export type ToastTone = "success" | "error" | "info";

export interface ToastContent {
  tone: ToastTone;
  /** What happened, in the past tense: "Grace Hopper assigned to 7A". */
  title: string;
  description?: string;
}

const queue = new ToastQueue<ToastContent>({ maxVisibleToasts: 3 });

/**
 * Shows a toast. Success/info close after 5s (React Aria's accessible
 * minimum); errors stay until dismissed — an error you didn't get to read
 * is worse than none. Returns a key for closing it early.
 */
export function toast(content: ToastContent): string {
  return queue.add(content, content.tone === "error" ? {} : { timeout: 5000 });
}

export function closeToast(key: string) {
  queue.close(key);
}

/** Drops every toast. The queue is a module-level singleton, so it outlives
 *  any one render: tests reset it between cases (src/test/setup.ts), or one
 *  test's error toast — which never times out — shows up in the next. */
export function clearToasts() {
  queue.clear();
}

const toneStyles: Record<ToastTone, { icon: React.ReactNode; className: string }> = {
  success: { icon: <CheckCircleIcon className="size-5" />, className: "text-ok" },
  error: { icon: <AlertCircleIcon className="size-5" />, className: "text-red-pen" },
  info: { icon: <InfoIcon className="size-5" />, className: "text-accent-ink" },
};

/** Mount once, at the app root. */
export function Toaster() {
  return (
    <AriaToastRegion
      queue={queue}
      className="fixed bottom-4 right-4 z-[60] flex w-[min(24rem,calc(100vw-2rem))] flex-col-reverse gap-2 outline-none"
    >
      {({ toast: item }) => {
        const tone = toneStyles[item.content.tone];
        return (
          <AriaToast
            toast={item}
            className="flex animate-pop-in items-start gap-3 rounded-lg bg-overlay p-3.5 shadow-overlay outline-none data-focus-visible:outline-2 data-focus-visible:outline-offset-2 data-focus-visible:outline-accent"
          >
            <span className={`mt-px ${tone.className}`}>{tone.icon}</span>
            <AriaToastContent className="min-w-0 flex-1">
              <Text slot="title" className="block font-medium text-ink">
                {item.content.title}
              </Text>
              {item.content.description && (
                <Text slot="description" className="mt-0.5 block text-small text-ink-2">
                  {item.content.description}
                </Text>
              )}
            </AriaToastContent>
            <AriaButton
              slot="close"
              aria-label="Dismiss"
              className="-m-1 grid size-7 shrink-0 place-items-center rounded-md text-ink-3 transition-colors duration-150 ease-soft data-hovered:bg-hover data-hovered:text-ink pointer-coarse:size-11"
            >
              <XIcon className="size-4" />
            </AriaButton>
          </AriaToast>
        );
      }}
    </AriaToastRegion>
  );
}
