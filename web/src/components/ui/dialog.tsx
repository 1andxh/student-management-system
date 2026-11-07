import { useId, useState } from "react";
import {
  Button as AriaButton,
  Dialog as AriaDialog,
  Heading,
  Modal,
  ModalOverlay,
} from "react-aria-components";

import { AlertCircleIcon, XIcon } from "../icons";
import { Button } from "./button";

export { DialogTrigger } from "react-aria-components";

// Dialogs are built from React Aria's Modal, which handles the parts that
// are easy to get wrong: focus is trapped inside and returned to the
// trigger on close, the page behind is inert to screen readers, and the
// body stops scrolling. Every dialog closes the same three ways where
// that's safe (X, Esc, click outside); the two variants below that must
// not close by accident say so explicitly.

const overlayStyles =
  "fixed inset-0 z-50 flex items-center justify-center overflow-y-auto overscroll-contain bg-scrim p-4 " +
  "data-entering:animate-fade-in data-exiting:animate-fade-out";

const modalStyles =
  "relative w-full max-w-md rounded-lg bg-overlay shadow-overlay outline-none " +
  "data-entering:animate-pop-in data-exiting:animate-pop-out";

export interface ShellProps {
  title: string;
  description?: React.ReactNode;
  children: React.ReactNode | ((opts: { close: () => void }) => React.ReactNode);
  role?: "dialog" | "alertdialog";
  isDismissable?: boolean;
  isKeyboardDismissDisabled?: boolean;
  showCloseButton?: boolean;
  /** Controlled use. Omit both when the dialog sits inside a <DialogTrigger>. */
  isOpen?: boolean;
  onOpenChange?: (isOpen: boolean) => void;
}

/** The shared frame. Use it only to build a new dialog variant, not in screens. */
export function DialogShell({
  title,
  description,
  children,
  role = "dialog",
  isDismissable = true,
  isKeyboardDismissDisabled = false,
  showCloseButton = true,
  isOpen,
  onOpenChange,
}: ShellProps) {
  // React Aria labels the dialog from its title Heading automatically, but
  // not its description — link that by id so a screen reader reads both.
  const descriptionId = useId();
  return (
    <ModalOverlay
      isDismissable={isDismissable}
      isKeyboardDismissDisabled={isKeyboardDismissDisabled}
      isOpen={isOpen}
      onOpenChange={onOpenChange}
      className={overlayStyles}
    >
      <Modal className={modalStyles}>
        <AriaDialog
          role={role}
          aria-describedby={description ? descriptionId : undefined}
          className="outline-none"
        >
          {({ close }) => (
            <>
              <div className="px-6 pt-6">
                <Heading slot="title" className="pr-8 text-title font-semibold text-balance">
                  {title}
                </Heading>
                {description && (
                  <div id={descriptionId} className="mt-1.5 text-pretty text-ink-2">
                    {description}
                  </div>
                )}
              </div>
              {showCloseButton && (
                <AriaButton
                  aria-label="Close"
                  onPress={close}
                  className="absolute right-3 top-3 grid size-8 place-items-center rounded-md text-ink-3 transition-colors duration-150 ease-soft data-hovered:bg-hover data-hovered:text-ink data-pressed:scale-[0.96] pointer-coarse:size-11"
                >
                  <XIcon className="size-4" />
                </AriaButton>
              )}
              <div className="px-6 pb-6 pt-5">{typeof children === "function" ? children({ close }) : children}</div>
            </>
          )}
        </AriaDialog>
      </Modal>
    </ModalOverlay>
  );
}

/** Right-aligned row of dialog buttons; put the safe action first. */
export function DialogActions({ children }: { children: React.ReactNode }) {
  return <div className="mt-6 flex flex-wrap justify-end gap-2">{children}</div>;
}

export type DialogProps = Omit<ShellProps, "role" | "isDismissable" | "isKeyboardDismissDisabled" | "showCloseButton">;

/** A general dialog: closes by X, Esc or clicking outside. */
export function Dialog(props: DialogProps) {
  return <DialogShell {...props} />;
}

export interface ConfirmDialogProps {
  title: string;
  description: React.ReactNode;
  /** Specific verb for what happens: "Remove from section", not "OK". */
  confirmLabel: string;
  cancelLabel?: string;
  /**
   * May return a promise: the confirm button shows pending until it
   * settles, then the dialog closes. If it throws, the dialog stays open
   * and shows the error, so the user can retry or cancel.
   */
  onConfirm: () => void | Promise<void>;
  isOpen?: boolean;
  onOpenChange?: (isOpen: boolean) => void;
}

/**
 * Confirmation for a destructive action. An alertdialog: it interrupts, it
 * doesn't close on an outside click (a stray click mustn't count as an
 * answer), and focus starts on Cancel — explicitly (autoFocus): React Aria
 * otherwise focuses the dialog element itself, and DOM order alone doesn't
 * decide it. Esc still cancels, except while the action is in flight.
 */
export function ConfirmDialog({
  title,
  description,
  confirmLabel,
  cancelLabel = "Cancel",
  onConfirm,
  isOpen,
  onOpenChange,
}: ConfirmDialogProps) {
  const [isPending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  return (
    <DialogShell
      title={title}
      description={description}
      role="alertdialog"
      isDismissable={false}
      isKeyboardDismissDisabled={isPending}
      showCloseButton={false}
      isOpen={isOpen}
      onOpenChange={(open) => {
        if (!open) setError(null);
        onOpenChange?.(open);
      }}
    >
      {({ close }) => (
        <>
          {error && (
            <p role="alert" className="flex items-start gap-2 rounded-md bg-red-pen-tint p-3 text-small text-red-pen">
              <AlertCircleIcon className="mt-px size-4" />
              <span>{error}</span>
            </p>
          )}
          <DialogActions>
            <Button variant="secondary" onPress={close} isDisabled={isPending} autoFocus>
              {cancelLabel}
            </Button>
            <Button
              variant="danger"
              isPending={isPending}
              onPress={async () => {
                setError(null);
                setPending(true);
                try {
                  await onConfirm();
                  close();
                } catch (e) {
                  setError(e instanceof Error ? e.message : "That didn’t work. Try again, or cancel.");
                } finally {
                  setPending(false);
                }
              }}
            >
              {confirmLabel}
            </Button>
          </DialogActions>
        </>
      )}
    </DialogShell>
  );
}

