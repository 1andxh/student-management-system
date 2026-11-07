import { act, render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import { toast, Toaster } from "./toast";

test("a toast is announced, not just painted", async () => {
  render(<Toaster />);

  act(() => {
    toast({ tone: "error", title: "Couldn’t save the timetable", description: "Check your connection and try again." });
  });

  // The region is a landmark named with a live count ("1 notification."),
  // and each toast's text sits in an alert, which is what a screen reader
  // announces. Asserting the alert, not just visible text, is the point.
  expect(await screen.findByRole("region", { name: /1 notification/i })).toBeInTheDocument();
  expect(screen.getByRole("alert")).toHaveTextContent("Couldn’t save the timetable");
});
