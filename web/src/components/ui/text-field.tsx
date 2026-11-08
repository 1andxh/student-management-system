import {
  Input,
  TextField as AriaTextField,
  type TextFieldProps as AriaTextFieldProps,
  type ValidationResult,
} from "react-aria-components";

import { controlStyles, Description, FieldError, Label } from "./field";

export interface TextFieldProps extends Omit<AriaTextFieldProps, "className" | "style"> {
  /** Required: every control gets a real label (a placeholder is not one). */
  label: string;
  description?: string;
  errorMessage?: string | ((validation: ValidationResult) => string);
  /** An example of the expected format, ending with "…" (e.g. "STU-0001…"). */
  placeholder?: string;
  /** Phone keyboards capitalize the first letter by default; IDs like
   *  "STU-0001" want "characters", emails/codes want "off". */
  autoCapitalize?: "off" | "none" | "on" | "sentences" | "words" | "characters";
  /** Layout only. */
  className?: string;
}

export function TextField({ label, description, errorMessage, placeholder, autoCapitalize, className = "", ...props }: TextFieldProps) {
  return (
    <AriaTextField {...props} className={`flex flex-col gap-1.5 ${className}`}>
      <Label>{label}</Label>
      <Input placeholder={placeholder} autoCapitalize={autoCapitalize} className={controlStyles} />
      {description && <Description>{description}</Description>}
      <FieldError>{errorMessage}</FieldError>
    </AriaTextField>
  );
}
