import { createFileRoute, redirect } from "@tanstack/react-router";

import { homeFor } from "../lib/auth/auth-context";

// "/" has no page of its own: it sends you to your role's home, or to sign in.
export const Route = createFileRoute("/")({
  beforeLoad: ({ context }) => {
    const { state } = context.auth;
    if (state.status !== "authenticated") throw redirect({ to: "/login" });
    throw redirect({ to: homeFor(state.user.role) });
  },
});
