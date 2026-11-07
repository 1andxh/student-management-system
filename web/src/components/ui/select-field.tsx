import {
  Button as AriaButton,
  composeRenderProps,
  ListBox,
  ListBoxItem,
  Popover,
  Select as AriaSelect,
  SelectValue,
  type ListBoxItemProps,
  type SelectProps as AriaSelectProps,
} from "react-aria-components";

import { CheckIcon, ChevronDownIcon } from "../icons";
import { controlStyles, Description, FieldError, Label } from "./field";

export interface SelectFieldProps<T extends object>
  extends Omit<AriaSelectProps<T>, "children" | "className" | "style"> {
  label: string;
  description?: string;
  errorMessage?: string;
  items?: Iterable<T>;
  /** <SelectItem>s, or a function rendering one per entry in `items`. */
  children: React.ReactNode | ((item: T) => React.ReactNode);
  /** Layout only. */
  className?: string;
}

// The popover is sized to the trigger (--trigger-width) and grows out of it
// (--trigger-anchor-point), so it reads as the field opening, not a new
// window appearing. Both variables are set by React Aria.
export function SelectField<T extends object>({
  label,
  description,
  errorMessage,
  items,
  children,
  className = "",
  ...props
}: SelectFieldProps<T>) {
  return (
    <AriaSelect {...props} className={`group flex flex-col gap-1.5 ${className}`}>
      <Label>{label}</Label>
      <AriaButton
        className={`${controlStyles} flex cursor-default items-center justify-between gap-2 text-left group-data-invalid:[--edge:var(--red-pen)]`}
      >
        <SelectValue className="min-w-0 truncate data-placeholder:text-ink-3" />
        <ChevronDownIcon className="size-4 text-ink-3 transition-transform duration-200 ease-soft group-data-open:rotate-180" />
      </AriaButton>
      {description && <Description>{description}</Description>}
      <FieldError>{errorMessage}</FieldError>
      <Popover className="min-w-(--trigger-width) origin-(--trigger-anchor-point) overflow-hidden rounded-lg bg-overlay p-1 shadow-overlay outline-none data-entering:animate-pop-in data-exiting:animate-pop-out">
        <ListBox items={items} className="max-h-72 overflow-auto overscroll-contain outline-none">
          {children}
        </ListBox>
      </Popover>
    </AriaSelect>
  );
}

export function SelectItem(props: Omit<ListBoxItemProps, "className" | "style">) {
  // React Aria needs plain text for typeahead when children aren't a string.
  const textValue = props.textValue ?? (typeof props.children === "string" ? props.children : undefined);
  return (
    <ListBoxItem
      {...props}
      textValue={textValue}
      className="flex h-8 cursor-default select-none items-center gap-2 rounded-sm px-2.5 text-body text-ink outline-none data-disabled:opacity-50 data-focused:bg-accent-tint data-focused:text-accent-ink data-selected:font-medium pointer-coarse:h-11"
    >
      {composeRenderProps(props.children, (children, { isSelected }) => (
        <>
          <span className="min-w-0 flex-1 truncate">{children}</span>
          {isSelected && <CheckIcon className="size-4 text-accent-ink" />}
        </>
      ))}
    </ListBoxItem>
  );
}
