import { expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { SelectField, SelectItem } from "./select-field";

test("choosing an option selects it and shows it in the trigger", async () => {
  const onSelectionChange = vi.fn();
  render(
    <SelectField label="Day" placeholder="Choose a day…" onSelectionChange={onSelectionChange}>
      <SelectItem id="monday">Monday</SelectItem>
      <SelectItem id="tuesday">Tuesday</SelectItem>
    </SelectField>,
  );

  await userEvent.click(screen.getByRole("button", { name: /day/i }));
  await userEvent.click(await screen.findByRole("option", { name: "Tuesday" }));

  expect(onSelectionChange).toHaveBeenCalledWith("tuesday");
  expect(screen.getByRole("button", { name: /day/i })).toHaveTextContent("Tuesday");
});
