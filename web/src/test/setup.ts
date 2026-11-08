import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

import { clearToasts } from "../components/ui/toast";

// Adds DOM matchers (toBeInTheDocument, toHaveAccessibleDescription, ...)
// to Vitest's expect.
import "@testing-library/jest-dom/vitest";

// Unmount whatever each test rendered. Testing Library only registers this
// automatically when test globals exist, and this project imports test/
// expect explicitly instead — so without this line, one test's DOM leaks
// into the next (a button "appears twice", an error "is still showing").
afterEach(cleanup);

// Module-level state needs the same per-test reset (the backend's rate
// limiter has one for the same reason, tests/conftest.py). The toast queue
// outlives renders, and error toasts never time out.
afterEach(clearToasts);
