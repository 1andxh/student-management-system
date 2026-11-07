import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";

import { pageInfo, Pagination } from "./table";

test.each([
  // [offset, limit, total] → shown range, prev/next offsets
  { offset: 0, limit: 50, total: 312, from: 1, to: 50, prev: null, next: 50 },
  { offset: 50, limit: 50, total: 312, from: 51, to: 100, prev: 0, next: 100 },
  { offset: 300, limit: 50, total: 312, from: 301, to: 312, prev: 250, next: null },
  { offset: 0, limit: 50, total: 50, from: 1, to: 50, prev: null, next: null },
  { offset: 0, limit: 50, total: 0, from: 0, to: 0, prev: null, next: null },
  // A stale URL after rows were deleted: offset past the end snaps to the
  // last real page instead of claiming "301–300 of 120".
  { offset: 300, limit: 50, total: 120, from: 101, to: 120, prev: 50, next: null },
])("pageInfo($offset, $limit, $total) shows $from–$to", ({ offset, limit, total, from, to, prev, next }) => {
  const page = pageInfo(offset, limit, total);

  expect([page.from, page.to, page.prevOffset, page.nextOffset]).toEqual([from, to, prev, next]);
});

test("Pagination disables the edges and moves by one page", async () => {
  const onChange = vi.fn();
  render(<Pagination offset={0} limit={50} total={120} onChange={onChange} noun="students" />);

  expect(screen.getByRole("button", { name: /previous/i })).toBeDisabled();
  expect(screen.getByText(/of/)).toHaveTextContent("Showing 1–50 of 120 students");

  await userEvent.click(screen.getByRole("button", { name: /next/i }));

  expect(onChange).toHaveBeenCalledWith(50);
});
