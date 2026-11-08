/**
 * Returns `target` only if it's a path inside this app; otherwise
 * `fallback`. Guards /login?redirect=…, which unchecked is an open
 * redirect: a crafted link to the real login page that lands a freshly
 * signed-in user on a look-alike site.
 *
 * Resolved with the URL parser rather than string checks, because browsers
 * normalize before navigating: "/\evil.com" and "/<tab>/evil.com" both
 * become "//evil.com", a different host. Whatever the parser decides is
 * what the browser would do.
 */
const BASE = "http://app.invalid";

export function safeRedirect(target: unknown, fallback: string): string {
  if (typeof target !== "string" || !target.startsWith("/")) return fallback;
  let url: URL;
  try {
    url = new URL(target, BASE);
  } catch {
    return fallback;
  }
  if (url.origin !== BASE || url.pathname === "/login") return fallback;
  // Check the *output* too: dot segments can leave a pathname that starts
  // with "//" (new URL("/..//evil.com").pathname === "//evil.com") — the
  // origin check above passed, but the string returned would be a
  // protocol-relative URL to another host.
  const out = url.pathname + url.search + url.hash;
  if (out.startsWith("//") || new URL(out, BASE).origin !== BASE) return fallback;
  return out;
}
