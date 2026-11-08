import { expect, test } from "vitest";

import { safeRedirect } from "./safe-redirect";

// /login?redirect=… sends the user back where they were after signing in.
// Unchecked, it's an open redirect: a crafted link to the real login page
// that lands a freshly signed-in teacher on an attacker's look-alike site.

test.each(["/teacher", "/teacher/classes?term=2", "/admin/students#top"])("keeps in-app path %s", (path) => {
  expect(safeRedirect(path, "/")).toBe(path);
});

test.each([
  ["absolute URL", "https://evil.example/login"],
  ["protocol-relative", "//evil.example/login"],
  ["backslash (browsers read /\\ as //)", "/\\evil.example"],
  ["tab inside (browsers strip it → //)", "/\t/evil.example"],
  // Dot segments: "/.." is dropped during parsing but the empty segment
  // after it stays, so the *pathname* comes out as "//evil.example" — a
  // protocol-relative URL — even though the origin check passed.
  ["dot-segment to //", "/..//evil.example"],
  ["nested dot-segment to //", "/a/..//evil.example"],
  ["javascript: URL", "javascript:alert(1)"],
  ["relative without slash", "evil.example"],
  ["empty", ""],
  ["back to login itself", "/login"],
  ["not a string", 42],
  ["missing", undefined],
])("rejects %s", (_label, target) => {
  expect(safeRedirect(target, "/")).toBe("/");
});
