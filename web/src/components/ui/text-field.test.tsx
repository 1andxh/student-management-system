import { expect, test } from "vitest";
import { render, screen } from "@testing-library/react";

import { TextField } from "./text-field";

test("the label names the input", () => {
  render(<TextField label="Student number" />);

  expect(screen.getByLabelText("Student number")).toBeInTheDocument();
});

test("description and error are announced with the input", () => {
  // Visible text next to a field is not enough: a screen reader only reads
  // what is linked to the input (aria-describedby). This is the wiring
  // field.tsx relies on React Aria for.
  render(
    <TextField
      label="PIN"
      description="Six digits, issued by an admin."
      isInvalid
      errorMessage="PIN must be 6 digits."
    />,
  );
  const input = screen.getByLabelText("PIN");

  expect(input).toHaveAttribute("aria-invalid", "true");
  expect(input).toHaveAccessibleDescription(/Six digits, issued by an admin\./);
  expect(input).toHaveAccessibleDescription(/PIN must be 6 digits\./);
});

test("no error is shown while the field is valid", () => {
  render(<TextField label="PIN" errorMessage="PIN must be 6 digits." />);

  expect(screen.queryByText("PIN must be 6 digits.")).not.toBeInTheDocument();
});
