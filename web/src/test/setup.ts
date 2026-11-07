import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

// Adds DOM matchers (toBeInTheDocument, toHaveAccessibleDescription, ...)
// to Vitest's expect.
import "@testing-library/jest-dom/vitest";

// Unmount whatever each test rendered. Testing Library only registers this
// automatically when test globals exist, and this project imports test/
// expect explicitly instead — so without this line, one test's DOM leaks
// into the next (a button "appears twice", an error "is still showing").
afterEach(cleanup);
