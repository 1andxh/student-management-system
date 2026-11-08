import { QueryClient } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";

import { Toaster } from "../../components/ui/toast";

// The provider is tested against a stubbed API module: what's under test is
// how it reacts to the server's answers, not the network.
const apiPost = vi.fn();
vi.mock("../api", () => ({
  api: { POST: (...args: unknown[]) => apiPost(...args), GET: vi.fn() },
  session: { refresh: vi.fn().mockResolvedValue(null), clear: vi.fn(), setAccessToken: vi.fn() },
  onSessionExpired: () => () => undefined,
  unwrap: vi.fn(),
}));

const { AuthProvider, useAuth } = await import("./auth-context");

function Probe() {
  const auth = useAuth();
  return (
    <>
      <p>status: {auth.state.status}</p>
      <button onClick={() => void auth.logout()}>Log out</button>
    </>
  );
}

beforeEach(() => apiPost.mockReset());

async function renderProvider() {
  render(
    <AuthProvider queryClient={new QueryClient()}>
      <Probe />
      <Toaster />
    </AuthProvider>,
  );
  await screen.findByText("status: anonymous"); // boot finished (no session)
}

test("a logout the server didn't confirm warns the user", async () => {
  // A 429/403/500 resolves (it isn't a network error), so the server
  // session and the HttpOnly cookie both survive — only the server can
  // clear that cookie. On a shared computer the next person would open the
  // app signed in as this user. Say so, instead of looking signed out.
  apiPost.mockResolvedValue({ response: new Response(null, { status: 429 }) });
  await renderProvider();

  await userEvent.click(screen.getByRole("button", { name: "Log out" }));

  expect(await screen.findByRole("alert")).toHaveTextContent(/sign-out didn’t reach the server/i);
});

test("a confirmed logout stays quiet", async () => {
  apiPost.mockResolvedValue({ response: new Response(null, { status: 204 }) });
  await renderProvider();

  await userEvent.click(screen.getByRole("button", { name: "Log out" }));

  expect(apiPost).toHaveBeenCalledWith("/auth/logout");
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});
