import {
  FieldError as AriaFieldError,
  Label as AriaLabel,
  Text,
  type FieldErrorProps,
  type LabelProps,
} from "react-aria-components";

import { AlertCircleIcon } from "../icons";

// The shared parts every form field is assembled from. React Aria wires
// the ids: the label labels the control, description and error are linked
// through aria-describedby, and the error only renders while invalid.

export function Label(props: Omit<LabelProps, "className">) {
  return <AriaLabel {...props} className="w-fit text-small font-medium text-ink" />;
}

export function Description({ children }: { children: React.ReactNode }) {
  return (
    <Text slot="description" className="text-caption text-ink-3">
      {children}
    </Text>
  );
}

export function FieldError({ children }: Omit<FieldErrorProps, "className">) {
  return (
    <AriaFieldError className="flex items-start gap-1.5 text-caption font-medium text-red-pen">
      {(validation) => (
        <>
          <AlertCircleIcon className="mt-px size-3.5" />
          <span>
            {typeof children === "function" ? children(validation) : (children ?? validation.validationErrors.join(" "))}
          </span>
        </>
      )}
    </AriaFieldError>
  );
}

// A soft edge (--line-field) at rest: Solomon's pick at review, after
// comparing a recessed, a raised and a full-contrast style. It sits below
// WCAG 1.4.11's 3:1 for a control boundary — a recorded exception (ADR
// 0029); fields are identified by their labels. Focus and invalid switch
// to full-contrast edges, so the states that matter stay unmistakable.
//
// The edge is 1.5px, built as a 1px border plus a 0.5px inset shadow ring:
// Chrome rounds border-width down to whole CSS pixels (border: 1.5px
// renders as 1px, even on 2x screens), but box-shadow isn't rounded.
// Both read one variable, --edge, so hover/focus/invalid recolor the
// whole edge at once instead of the two halves drifting apart.
// Invalid stays red even while focused (the stacked selector is more
// specific than plain data-focused). Disabled doesn't fade (enabled fields
// already have a soft edge, so a faded one would look the same): it
// becomes a grey filled well with muted text and no edge.
export const controlStyles =
  "h-10 w-full rounded-control border border-(--edge) bg-field px-3.5 text-body text-ink outline-none " +
  "[--edge:var(--line-field)] [--halo:transparent] " +
  "shadow-[inset_0_0_0_0.5px_var(--edge),inset_0_1px_2px_var(--shade-1),0_0_0_3px_var(--halo)] " +
  "transition-[border-color,box-shadow] duration-150 ease-soft placeholder:text-ink-3 pointer-coarse:h-11 " +
  "data-hovered:[--edge:var(--line-field-hover)] " +
  "data-focused:[--edge:var(--accent)] data-focused:[--halo:var(--accent-tint)] " +
  "data-focus-visible:[--edge:var(--accent)] data-focus-visible:[--halo:var(--accent-tint)] " +
  "data-invalid:[--edge:var(--red-pen)] " +
  "data-invalid:data-focused:[--edge:var(--red-pen)] data-invalid:data-focused:[--halo:var(--red-pen-tint)] " +
  "data-disabled:cursor-not-allowed data-disabled:bg-inset data-disabled:text-ink-3 data-disabled:[--edge:transparent] data-disabled:shadow-none";
