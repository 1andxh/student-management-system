import { useState } from "react";

import { CheckIcon, CopyIcon } from "../icons";
import { Button } from "./button";
import { DialogActions, DialogShell } from "./dialog";

export interface OneTimeSecretDialogProps {
  isOpen: boolean;
  /** Called once the admin confirms they have the secret. Drop it from state here. */
  onClose: () => void;
  /** e.g. "New password for Ada Lovelace" */
  title: string;
  /** Who it's for, used in the instructions: "Ada Lovelace". */
  recipient: string;
  /** "password" (teachers) or "PIN" (students): what the secret is called. */
  secretName: string;
  secret: string;
}

/**
 * Shows a teacher password or student PIN exactly once (backend: POST
 * /teachers/{id}/credentials, /students/{id}/credentials). The API never
 * returns it again, so losing this dialog means issuing a new one:
 *  - it can't be closed by a stray click or Esc — only by confirming;
 *  - the secret is selectable in one click and has a Copy button;
 *  - it is never logged or stored; the caller holds it in component state
 *    and drops it in onClose.
 */
export function OneTimeSecretDialog({ isOpen, onClose, title, recipient, secretName, secret }: OneTimeSecretDialogProps) {
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">("idle");

  async function copy() {
    try {
      await navigator.clipboard.writeText(secret);
      setCopyState("copied");
    } catch {
      // Clipboard access can be refused (permissions, insecure context).
      // The secret is still on screen and selectable, so say how to proceed.
      setCopyState("failed");
    }
  }

  return (
    <DialogShell
      title={title}
      description={
        <>
          This is the only time this {secretName} will be shown. Copy it and give it to {recipient}{" "}
          directly. If it’s lost, issue a new one: that replaces this {secretName}.
        </>
      }
      role="alertdialog"
      isDismissable={false}
      isKeyboardDismissDisabled
      showCloseButton={false}
      isOpen={isOpen}
      onOpenChange={(open) => {
        if (!open) {
          setCopyState("idle");
          onClose();
        }
      }}
    >
      {({ close }) => (
        <>
          <div className="flex items-center gap-2 rounded-lg bg-inset p-2 pl-4 shadow-[inset_0_1px_2px_var(--shade-1)]">
            <code
              translate="no"
              className="min-w-0 flex-1 select-all break-all font-mono text-lead font-medium tracking-[0.08em] text-ink"
            >
              {secret}
            </code>
            <Button size="sm" onPress={copy} aria-label={`Copy ${secretName}`}>
              {copyState === "copied" ? <CheckIcon className="size-4 text-ok" /> : <CopyIcon className="size-4" />}
              {copyState === "copied" ? "Copied" : "Copy"}
            </Button>
          </div>
          {/* Announced, not just shown: a screen-reader user can't see the
              button label flip to "Copied". */}
          <p aria-live="polite" className="mt-2 min-h-4 text-caption text-ink-3">
            {copyState === "copied" && "Copied to the clipboard."}
            {copyState === "failed" && "Couldn’t copy automatically. Select the text above and copy it."}
          </p>
          <DialogActions>
            <Button variant="primary" onPress={close}>
              I’ve copied it
            </Button>
          </DialogActions>
        </>
      )}
    </DialogShell>
  );
}
