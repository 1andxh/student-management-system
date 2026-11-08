import { Link, useNavigate, useRouterState } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import {
  Button as AriaButton,
  Dialog as AriaDialog,
  Modal,
  ModalOverlay,
  SharedElement,
  SharedElementTransition,
} from "react-aria-components";

import type { User } from "../lib/api";
import { useAuth } from "../lib/auth/auth-context";
import { ROLE_LABEL, visibleGroups, type Area, type NavGroup, type NavItem } from "../lib/nav";
import { BrandMark } from "./brand";
import { LogOutIcon, MenuIcon, XIcon } from "./icons";

/**
 * The signed-in frame: a floating sidebar card on wide screens, a top bar
 * with a slide-in drawer on narrow ones, and the page in <main>.
 */
export function AppShell({ area, user, children }: { area: Area; user: User; children: React.ReactNode }) {
  const groups = visibleGroups(area, user.role);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const mainRef = useRef<HTMLElement>(null);
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const previousPath = useRef(pathname);

  // After navigating, move focus to the page. Otherwise keyboard and
  // screen-reader users stay on the link they pressed, in a sidebar that
  // didn't change, with no sign the page did. Not on first load: there the
  // browser's own start-of-document focus is right.
  useEffect(() => {
    if (previousPath.current === pathname) return;
    previousPath.current = pathname;
    mainRef.current?.focus({ preventScroll: true });
  }, [pathname]);

  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[16rem_1fr]">
      <a
        href="#main"
        className="sr-only z-50 rounded-md bg-surface px-3 py-2 font-medium shadow-overlay focus:not-sr-only focus:fixed focus:left-3 focus:top-3"
      >
        Skip to content
      </a>

      {/* Wide screens: the sidebar is a card floating on the canvas — depth
          from light, like everything else (ADR 0029). */}
      <aside className="hidden lg:sticky lg:top-0 lg:block lg:h-dvh lg:p-3">
        <div className="flex h-full flex-col rounded-lg bg-surface shadow-card">
          <Sidebar area={area} groups={groups} user={user} />
        </div>
      </aside>

      {/* Narrow screens: a top bar, and the same sidebar in a drawer. */}
      <header className="sticky top-0 z-30 flex h-14 items-center justify-between bg-canvas/90 px-4 backdrop-blur-sm lg:hidden">
        <Brand area={area} user={user} />
        <AriaButton
          aria-label="Open menu"
          onPress={() => setDrawerOpen(true)}
          className="grid size-11 place-items-center rounded-md text-ink-2 data-hovered:bg-hover data-pressed:scale-[0.96]"
        >
          <MenuIcon className="size-5" />
        </AriaButton>
      </header>
      <ModalOverlay
        isDismissable
        isOpen={drawerOpen}
        onOpenChange={setDrawerOpen}
        className="fixed inset-0 z-50 bg-scrim data-entering:animate-fade-in data-exiting:animate-fade-out lg:hidden"
      >
        <Modal className="fixed inset-y-0 left-0 w-[min(20rem,85vw)] bg-surface shadow-overlay outline-none data-entering:animate-drawer-in data-exiting:animate-drawer-out">
          <AriaDialog aria-label="Menu" className="flex h-full flex-col outline-none">
            {({ close }) => (
              <>
                <AriaButton
                  aria-label="Close menu"
                  onPress={close}
                  className="absolute right-3 top-3 grid size-11 place-items-center rounded-md text-ink-3 data-hovered:bg-hover"
                >
                  <XIcon className="size-5" />
                </AriaButton>
                <Sidebar area={area} groups={groups} user={user} onNavigate={close} />
              </>
            )}
          </AriaDialog>
        </Modal>
      </ModalOverlay>

      <main id="main" ref={mainRef} tabIndex={-1} className="min-w-0 px-4 pb-16 pt-6 outline-none sm:px-8 lg:pt-12">
        <div className="mx-auto max-w-6xl">{children}</div>
      </main>
    </div>
  );
}

function Brand({ area, user }: { area: Area; user: User }) {
  return (
    <Link to={`/${area}`} className="flex items-center gap-2.5 rounded-md outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent">
      <BrandMark className="size-7" />
      <span className="font-semibold">School</span>
      <span className="text-small text-ink-3">{ROLE_LABEL[user.role]}</span>
    </Link>
  );
}

function Sidebar({ area, groups, user, onNavigate }: { area: Area; groups: NavGroup[]; user: User; onNavigate?: () => void }) {
  const { logout } = useAuth();
  const navigate = useNavigate();

  return (
    <>
      <div className="px-4 pb-2 pt-4">
        <Brand area={area} user={user} />
      </div>
      <nav aria-label="Main" className="flex-1 overflow-y-auto px-2 py-2">
        {/* One pill that slides to the active page (React Aria's
            SharedElement moves a single element between links), rather
            than each link toggling its own background. */}
        <SharedElementTransition>
          {groups.map((group, i) => (
            <div key={group.label ?? i} className={i > 0 ? "mt-5" : ""}>
              {group.label && <h2 className="mb-1 px-3 text-caption font-medium text-ink-3">{group.label}</h2>}
              <ul className="flex flex-col gap-0.5">
                {group.items.map((item) => (
                  <li key={item.slug ?? "home"}>
                    <NavLink area={area} item={item} onNavigate={onNavigate} />
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </SharedElementTransition>
      </nav>
      <div className="border-t border-line p-3">
        <div className="min-w-0 px-1 pb-2">
          <p className="truncate text-small font-medium" title={user.email}>
            {user.email}
          </p>
          <p className="text-caption text-ink-3">{ROLE_LABEL[user.role]}</p>
        </div>
        <AriaButton
          onPress={async () => {
            await logout();
            await navigate({ to: "/login" });
          }}
          className="flex h-9 w-full items-center gap-2 rounded-md px-2 text-small font-medium text-ink-2 transition-colors duration-150 ease-soft data-hovered:bg-hover data-hovered:text-ink data-pressed:scale-[0.98] pointer-coarse:h-11"
        >
          <LogOutIcon className="size-4" />
          Log out
        </AriaButton>
      </div>
    </>
  );
}

function NavLink({ area, item, onNavigate }: { area: Area; item: NavItem; onNavigate?: () => void }) {
  const linkProps = item.slug === null ? { to: `/${area}` as const } : { to: `/${area}/$page` as const, params: { page: item.slug } };
  return (
    <Link
      {...linkProps}
      activeOptions={{ exact: item.slug === null }}
      onClick={onNavigate}
      className="relative flex h-9 items-center rounded-md px-3 text-small font-medium text-ink-2 outline-none transition-colors duration-150 ease-soft hover:text-ink focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent data-[status=active]:text-accent-ink pointer-coarse:h-11"
    >
      {({ isActive }) => (
        <>
          <SharedElement
            name="nav-active"
            isVisible={isActive}
            className="absolute inset-0 rounded-md bg-accent-tint transition-[translate,width,height] duration-250 ease-snap"
          />
          <span className="relative truncate">{item.label}</span>
        </>
      )}
    </Link>
  );
}
