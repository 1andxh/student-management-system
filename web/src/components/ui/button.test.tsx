import { expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { Button } from "./button";

test("presses call onPress", async () => {
  const onPress = vi.fn();
  render(<Button onPress={onPress}>Save changes</Button>);

  await userEvent.click(screen.getByRole("button", { name: "Save changes" }));

  expect(onPress).toHaveBeenCalledTimes(1);
});

test("a pending button ignores presses but stays focusable", async () => {
  // The double-submit guard: while a request is in flight, pressing again
  // must not fire a second one. Staying focusable (unlike `disabled`)
  // means keyboard users don't lose their place mid-request.
  const onPress = vi.fn();
  render(
    <Button onPress={onPress} isPending>
      Save changes
    </Button>,
  );
  const button = screen.getByRole("button", { name: /save changes/i });

  await userEvent.tab(); // keyboard users can still reach it…
  expect(button).toHaveFocus();
  await userEvent.keyboard("{Enter}"); // …but activating it does nothing
  await userEvent.click(button); // and neither does a click

  expect(onPress).not.toHaveBeenCalled();
  // aria-disabled, not the disabled attribute: that's what keeps it in the
  // tab order while still telling assistive tech it can't be used now.
  expect(button).toHaveAttribute("aria-disabled", "true");
  expect(button).not.toHaveAttribute("disabled");
});
