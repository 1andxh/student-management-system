import {
  Button as AriaButton,
  composeRenderProps,
  type ButtonProps as AriaButtonProps,
} from "react-aria-components";

import { SpinnerIcon } from "../icons";

// One named variant prop, not a stack of booleans (isPrimary, isDanger…):
// every boolean doubles the possible states, most of them nonsense.
//   primary   — the one main action in a view (ADR 0029: one accent per view)
//   secondary — everything else; the default, so "primary" is a choice
//   quiet     — low-emphasis actions inside dense UI (table rows, toolbars)
//   danger    — confirms something destructive; red pen means attention
export type ButtonVariant = "primary" | "secondary" | "quiet" | "danger";
export type ButtonSize = "md" | "sm";

// Styling hangs off the data-* attributes React Aria sets (data-pressed,
// data-hovered, data-disabled, data-pending), not on state we track. Its
// hover only fires for real mouse pointers, so touch screens never get a
// stuck hover state. Transitions list properties explicitly — never `all`.
const base =
  "group relative inline-flex select-none items-center justify-center gap-2 whitespace-nowrap font-medium " +
  "transition-[background-color,color,transform] duration-150 ease-soft " +
  "data-pressed:scale-[0.96] data-disabled:cursor-not-allowed data-disabled:opacity-50 data-pending:cursor-wait";

const variants: Record<ButtonVariant, string> = {
  primary: "bg-accent text-on-accent shadow-button data-hovered:bg-accent-hover",
  secondary: "bg-surface text-ink shadow-control data-hovered:bg-inset",
  quiet: "bg-transparent text-ink-2 data-hovered:bg-hover data-hovered:text-ink",
  danger: "bg-red-pen text-on-red-pen shadow-control data-hovered:bg-red-pen-hover",
};

// 40px (the same height and corners as fields, so a button lines up with
// the input beside it) / 28px for dense rows; 44px hit target on touch.
const sizes: Record<ButtonSize, string> = {
  md: "h-10 rounded-control px-4 text-small pointer-coarse:h-11",
  sm: "h-7 rounded-md px-2.5 text-small pointer-coarse:h-11",
};

export interface ButtonProps extends Omit<AriaButtonProps, "className" | "style"> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** Layout only (width, margin, alignment). Visual style comes from `variant`. */
  className?: string;
}

/**
 * `isPending` keeps the button focusable and its width stable (the label
 * goes invisible, not away), ignores presses, and React Aria announces the
 * pending state to screen readers. Use it for the duration of a request,
 * not before one starts.
 */
export function Button({ variant = "secondary", size = "md", className = "", children, ...props }: ButtonProps) {
  return (
    <AriaButton {...props} className={`${base} ${variants[variant]} ${sizes[size]} ${className}`}>
      {composeRenderProps(children, (children, { isPending }) => (
        <>
          <span className="inline-flex items-center gap-2 group-data-pending:invisible">{children}</span>
          {isPending && <SpinnerIcon className="absolute size-4" />}
        </>
      ))}
    </AriaButton>
  );
}
