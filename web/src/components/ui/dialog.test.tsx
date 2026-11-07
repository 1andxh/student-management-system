import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";

import { ConfirmDialog } from "./dialog";

function renderConfirm(onConfirm: () => void | Promise<void>) {
  const onOpenChange = vi.fn();
  render(
    <ConfirmDialog
      isOpen
      onOpenChange={onOpenChange}
      title="Remove Grace Hopper from 7A?"
      description="Her enrollments in 7A’s classes stay; remove them separately if needed."
      confirmLabel="Remove from section"
      onConfirm={onConfirm}
    />,
  );
  return { onOpenChange };
}

test("focus starts on Cancel, the safe choice", () => {
  // A destructive confirmation must not put focus on the destructive
  // button: one stray Enter would carry it out.
  renderConfirm(vi.fn());

  expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus();
  expect(screen.getByRole("alertdialog")).toHaveAccessibleName("Remove Grace Hopper from 7A?");
});

test("confirming runs the action, then closes", async () => {
  const onConfirm = vi.fn().mockResolvedValue(undefined);
  const { onOpenChange } = renderConfirm(onConfirm);

  await userEvent.click(screen.getByRole("button", { name: "Remove from section" }));

  expect(onConfirm).toHaveBeenCalledTimes(1);
  expect(onOpenChange).toHaveBeenCalledWith(false);
});

test("a failed action keeps the dialog open and shows why", async () => {
  // Closing on failure would make the user believe it worked.
  const onConfirm = vi.fn().mockRejectedValue(new Error("Grace Hopper is not in this section."));
  const { onOpenChange } = renderConfirm(onConfirm);

  await userEvent.click(screen.getByRole("button", { name: "Remove from section" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("Grace Hopper is not in this section.");
  expect(onOpenChange).not.toHaveBeenCalledWith(false);
  expect(screen.getByRole("alertdialog")).toBeInTheDocument();
});
