import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";

import { OneTimeSecretDialog } from "./one-time-secret-dialog";

function renderSecret() {
  const onClose = vi.fn();
  render(
    <OneTimeSecretDialog
      isOpen
      onClose={onClose}
      title="New password for Ada Lovelace"
      recipient="Ada Lovelace"
      secretName="password"
      secret="S_7lD50GYvsGVY0m3wErQw"
    />,
  );
  return { onClose };
}

test("Copy puts the exact secret on the clipboard and says so", async () => {
  // userEvent.setup() installs a working clipboard stub in jsdom.
  const user = userEvent.setup();
  renderSecret();

  await user.click(screen.getByRole("button", { name: "Copy password" }));

  await expect(navigator.clipboard.readText()).resolves.toBe("S_7lD50GYvsGVY0m3wErQw");
  expect(screen.getByText("Copied to the clipboard.")).toBeInTheDocument();
});

test("Esc does not close it: the secret can't be shown again", async () => {
  const user = userEvent.setup();
  const { onClose } = renderSecret();

  await user.keyboard("{Escape}");

  expect(onClose).not.toHaveBeenCalled();
  expect(screen.getByRole("alertdialog")).toBeInTheDocument();
});

test("only confirming closes it", async () => {
  const user = userEvent.setup();
  const { onClose } = renderSecret();

  await user.click(screen.getByRole("button", { name: "I’ve copied it" }));

  expect(onClose).toHaveBeenCalledTimes(1);
});
