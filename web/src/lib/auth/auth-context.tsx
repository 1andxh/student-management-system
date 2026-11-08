import type { QueryClient } from "@tanstack/react-query";
import { createContext, use, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { toast } from "../../components/ui/toast";
import { api, onSessionExpired, session, unwrap, type Role, type User } from "../api";

export type AuthState =
  | { status: "loading" }
  /** `signedOut`: ended on purpose (logout here or in another tab, or
   *  another user signing in) as opposed to never signed in or expired.
   *  Guards then drop `?redirect=`: the next person to sign in on this
   *  computer shouldn't land on the previous person's last page. */
  | { status: "anonymous"; signedOut?: boolean }
  | { status: "authenticated"; user: User };

export interface Auth {
  state: AuthState;
  loginWithPassword(email: string, password: string): Promise<User>;
  loginWithPin(studentNumber: string, pin: string): Promise<User>;
  logout(): Promise<void>;
}

const AuthContext = createContext<Auth | null>(null);

export function useAuth(): Auth {
  const auth = use(AuthContext);
  if (!auth) throw new Error("useAuth must be used inside <AuthProvider>");
  return auth;
}

/** Where each role lands after signing in, and what "/" redirects to. */
export function homeFor(role: Role): "/admin" | "/teacher" | "/student" {
  switch (role) {
    case "super_admin":
    case "admin":
      return "/admin";
    case "teacher":
      return "/teacher";
    case "student":
      return "/student";
  }
}

// Keeps tabs in step. "logout": without it, a tab left open keeps working
// with its in-memory access token for up to 30 minutes after the user
// "logged out" in another tab — on a shared school computer, the next
// person would find the previous one still signed in. "login": another tab
// signed in, so the shared refresh cookie now belongs to that user; a tab
// showing someone else must end, not drift into acting as the new user.
const CHANNEL = "sms-auth";
type TabMessage = { type: "logout" } | { type: "login"; userId: string };

function tellOtherTabs(message: TabMessage) {
  if (typeof BroadcastChannel === "undefined") return;
  const channel = new BroadcastChannel(CHANNEL);
  channel.postMessage(message);
  channel.close();
}

export function AuthProvider({ queryClient, children }: { queryClient: QueryClient; children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>({ status: "loading" });
  const userIdRef = useRef<string | null>(null);
  useEffect(() => {
    userIdRef.current = state.status === "authenticated" ? state.user.id : null;
  }, [state]);

  // Everything that ends a session in this tab goes through here. The query
  // cache is cleared too: it holds the previous user's data, and the next
  // person to sign in on this computer must not see a flash of it.
  const endSession = useCallback(
    (signedOut: boolean) => {
      session.clear();
      void queryClient.cancelQueries();
      queryClient.clear();
      setState({ status: "anonymous", signedOut });
    },
    [queryClient],
  );

  const startSession = useCallback(
    async (accessToken: string) => {
      session.setAccessToken(accessToken);
      queryClient.clear();
      const user = await unwrap(api.GET("/auth/me"));
      setState({ status: "authenticated", user });
      tellOtherTabs({ type: "login", userId: user.id });
      return user;
    },
    [queryClient],
  );

  // Boot: there's no access token after a reload (memory only), but the
  // HttpOnly cookie may still hold a session. One refresh tells us which.
  useEffect(() => {
    let cancelled = false;
    session
      .refresh()
      .then(async (token) => {
        if (!token) return cancelled || setState({ status: "anonymous" });
        const user = await unwrap(api.GET("/auth/me"));
        if (!cancelled) setState({ status: "authenticated", user });
      })
      .catch(() => {
        // Server unreachable: show the login page; signing in will report
        // the real problem.
        if (!cancelled) setState({ status: "anonymous" });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // A request found the session gone (expired, revoked, or the account was
  // deactivated). The router's guards then send the user to /login.
  useEffect(
    () =>
      onSessionExpired(() => {
        endSession(false);
        toast({ tone: "info", title: "Your session ended", description: "Sign in again to continue." });
      }),
    [endSession],
  );

  useEffect(() => {
    if (typeof BroadcastChannel === "undefined") return;
    const channel = new BroadcastChannel(CHANNEL);
    channel.onmessage = (event: MessageEvent<TabMessage>) => {
      const message = event.data;
      if (message.type === "logout" && userIdRef.current) endSession(true);
      if (message.type === "login" && userIdRef.current && message.userId !== userIdRef.current) endSession(true);
    };
    return () => channel.close();
  }, [endSession]);

  const value = useMemo<Auth>(
    () => ({
      state,
      async loginWithPassword(email, password) {
        const { access_token } = await unwrap(api.POST("/auth/login", { body: { email, password } }));
        return startSession(access_token);
      },
      async loginWithPin(studentNumber, pin) {
        const { access_token } = await unwrap(api.POST("/auth/login-pin", { body: { student_number: studentNumber, pin } }));
        return startSession(access_token);
      },
      async logout() {
        // Only the server can end the session *and* clear the HttpOnly
        // cookie. A 429/403/500 doesn't throw (only network errors do), so
        // check the answer: if it didn't confirm, the cookie is still in this
        // browser and opening the app again signs this user back in. This tab
        // forgets everything either way, but says so rather than looking
        // safely signed out on a shared computer.
        let confirmed = false;
        try {
          confirmed = (await api.POST("/auth/logout")).response.ok;
        } catch {
          // offline: not confirmed
        }
        endSession(true);
        tellOtherTabs({ type: "logout" });
        if (!confirmed) {
          toast({
            tone: "error",
            title: "Sign-out didn’t reach the server",
            description: "You may still be signed in on this computer. Close every browser window before you leave it.",
          });
        }
      },
    }),
    [state, startSession, endSession],
  );

  return <AuthContext value={value}>{children}</AuthContext>;
}
