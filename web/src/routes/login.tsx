import { createFileRoute, redirect } from "@tanstack/react-router";
import { useState, type FormEvent } from "react";
import { Form } from "react-aria-components";

import { BrandMark } from "../components/brand";
import { Button } from "../components/ui/button";
import { Notice } from "../components/ui/notice";
import { Tab, TabList, TabPanel, Tabs } from "../components/ui/tabs";
import { TextField } from "../components/ui/text-field";
import { ApiError } from "../lib/api";
import { homeFor, useAuth } from "../lib/auth/auth-context";
import { safeRedirect } from "../lib/auth/safe-redirect";

export const Route = createFileRoute("/login")({
  validateSearch: (search: Record<string, unknown>): { redirect?: string } =>
    typeof search.redirect === "string" ? { redirect: search.redirect } : {},
  // Signed in already (or just now: signing in re-runs this guard) → go on
  // to where you were headed, if that's a page inside this app, else home.
  beforeLoad: ({ context, search }) => {
    const { state } = context.auth;
    if (state.status === "authenticated") {
      throw redirect({ href: safeRedirect(search.redirect, homeFor(state.user.role)) });
    }
  },
  component: LoginPage,
});

function LoginPage() {
  return (
    <main className="grid min-h-dvh place-items-center px-4 py-12">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex items-center justify-center gap-2.5">
          <BrandMark className="size-9" />
          <span className="text-title font-semibold">School</span>
        </div>
        <div className="rounded-lg bg-surface p-6 shadow-card sm:p-8">
          <h1 className="text-title font-semibold">Sign in</h1>
          <p className="mt-1 text-small text-ink-3">Staff use their email. Students use their student number and PIN.</p>
          <Tabs className="mt-6" defaultSelectedKey="staff">
            <TabList aria-label="Account type">
              <Tab id="staff">Staff</Tab>
              <Tab id="student">Student</Tab>
            </TabList>
            <TabPanel id="staff">
              <StaffForm />
            </TabPanel>
            <TabPanel id="student">
              <StudentForm />
            </TabPanel>
          </Tabs>
        </div>
        <p className="mt-6 text-pretty text-center text-small text-ink-3">
          Forgot your password or PIN? A school administrator can issue you a new one.
        </p>
      </div>
    </main>
  );
}

/**
 * Shared submit handling. A 401 gets this form's own wording: the backend
 * deliberately returns one identical message for every failed sign-in (so
 * it never reveals whether an account exists), and that message mentions
 * email even on the PIN form. Anything else (429, offline, 500) uses the
 * readable message ApiError already carries.
 */
function useSignIn(unauthorizedMessage: string) {
  const [error, setError] = useState<string | null>(null);
  const [isPending, setPending] = useState(false);

  async function run(attempt: () => Promise<unknown>) {
    setError(null);
    setPending(true);
    try {
      await attempt();
      // Success: the session change re-runs /login's guard, which navigates
      // away. Stay pending until then, so the button can't be pressed twice.
    } catch (e) {
      setError(e instanceof ApiError && e.status === 401 ? unauthorizedMessage : e instanceof Error ? e.message : "Sign-in failed. Try again.");
      setPending(false);
    }
  }
  return { error, isPending, run };
}

function StaffForm() {
  const { loginWithPassword } = useAuth();
  const { error, isPending, run } = useSignIn("That email and password don’t match an account.");

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    void run(() => loginWithPassword(String(data.get("email")), String(data.get("password"))));
  }

  return (
    <Form onSubmit={onSubmit} className="flex flex-col gap-4">
      {error && <Notice tone="error" title={error} />}
      <TextField label="Email" name="email" type="email" autoComplete="username" autoCapitalize="off" spellCheck="false" isRequired />
      <TextField label="Password" name="password" type="password" autoComplete="current-password" isRequired />
      <Button type="submit" variant="primary" isPending={isPending} className="mt-2 w-full">
        Sign in
      </Button>
    </Form>
  );
}

function StudentForm() {
  const { loginWithPin } = useAuth();
  const { error, isPending, run } = useSignIn("That student number and PIN don’t match.");

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    void run(() => loginWithPin(String(data.get("student_number")).trim(), String(data.get("pin"))));
  }

  return (
    <Form onSubmit={onSubmit} className="flex flex-col gap-4">
      {error && <Notice tone="error" title={error} />}
      <TextField
        label="Student number"
        name="student_number"
        autoComplete="username"
        autoCapitalize="characters"
        spellCheck="false"
        placeholder="STU-0001…"
        isRequired
      />
      {/* Checked here before sending: sign-in is rate-limited to 5 tries a
          minute, and a typo shouldn't spend one. */}
      <TextField
        label="PIN"
        name="pin"
        type="password"
        inputMode="numeric"
        autoComplete="current-password"
        description="6 digits."
        isRequired
        validate={(value) => (/^\d{6}$/.test(value) ? null : "A PIN is 6 digits, numbers only.")}
      />
      <Button type="submit" variant="primary" isPending={isPending} className="mt-2 w-full">
        Sign in
      </Button>
    </Form>
  );
}
