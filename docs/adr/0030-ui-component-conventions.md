# 0030. UI component conventions

## Status
Accepted (frontend Stage F2b).

## Context
F2b built the shared components every screen will be assembled from, in `web/src/components/ui/`: Button, TextField, SelectField, Dialog, ConfirmDialog, OneTimeSecretDialog, Toast, Table with Pagination, Notice, EmptyState and Skeleton. Their visual language is ADR 0029. This ADR records the API and behavior conventions they settled, so later screens follow them rather than re-deciding, and so none of the non-obvious choices below gets "simplified" away.

## Decision
- **Built on React Aria Components, not hand-rolled.** It supplies the parts that are easy to get subtly wrong:
  - focus trapping and restoring focus to the trigger when a dialog closes;
  - hiding the page behind a modal from screen readers;
  - linking label, description and error to each field;
  - listbox typeahead;
  - table grid navigation and `aria-sort`;
  - toast live regions.
  
  Our code is the styling plus the behaviors below.
- **Variants are one named prop, never boolean flags.** `variant: "primary" | "secondary" | "quiet" | "danger"`, plus `kind: "text" | "number"` for table cells. Each boolean doubles the possible states, most of them nonsense ("primary *and* danger"). The default Button is `secondary`, so choosing `primary` is deliberate (ADR 0029: one primary action per view).
- **Callers can't restyle components.** `className` is accepted for layout only (width, margin, alignment). Visual style comes from the variant. Otherwise every screen slowly drifts away from the design.
- **State styling hangs off React Aria's `data-*` attributes** (`data-pressed`, `data-hovered`, `data-focused`, `data-invalid`, `data-disabled`, `data-pending`), not off state we track ourselves. React Aria only reports hover for real mouse pointers, so touch screens never get a stuck hover.
- **Every field has a real label, enforced by the types** (`label: string` is required). A placeholder is never a label; placeholders show an example ending in "…".
- **Pending buttons stay focusable.** `isPending` sets `aria-disabled`, not `disabled`:
  - presses are ignored, so a second click can't submit twice;
  - keyboard users keep their place in the tab order;
  - the label stays in the layout so the button keeps its width;
  - React Aria announces the pending state.
- **Dialog dismissal is deliberate per kind:**
  - **Dialog** (general) closes by X, Esc, or clicking outside. Every general dialog closes the same three ways.
  - **ConfirmDialog** (destructive) is an `alertdialog`:
    - It ignores outside clicks, because a stray click mustn't count as an answer.
    - Focus starts on **Cancel** via explicit `autoFocus`. React Aria otherwise focuses the dialog element itself, and DOM order doesn't decide it. A test caught the first version relying on DOM order.
    - Esc cancels, except while the action is running.
    - A failed action keeps the dialog open and shows the error, because closing on failure would read as success.
  - **OneTimeSecretDialog** (teacher passwords, student PINs; the API never returns them twice):
    - It can't be closed by Esc or an outside click, only by "I've copied it".
    - The secret is selectable in one click, Copy announces itself through a live region, and if clipboard access is refused it says how to copy by hand.
    - The secret is never logged or stored. The caller holds it in component state and drops it in `onClose`.
- **Toasts:** success and info close after 5s, React Aria's accessible minimum. **Errors stay until dismissed**, because an error you didn't get to read is worse than none. One `<Toaster />` sits at the app root, outside any page, so a toast raised just before navigating still shows.
- **React Aria's toast API is `UNSTABLE_`, and is used anyway.** It handles the live region, the landmark and focus restoration. The risk is contained two ways:
  - the exact-pinned version means nothing changes until an upgrade is chosen;
  - only `toast.tsx` imports it, so an API change lands in one file.
- **Tables:**
  - **Sorting and paging are controlled**, and screens keep them in the URL as search params, not only in component state.
  - **The first column is pinned**, so its cells (and the row-hover color) are opaque. `--row-hover` exists because a translucent hover would leave the pinned cell un-highlighted.
  - **`pageInfo()` is the pure paging math** for the backend's `limit`/`offset` + `X-Total-Count`. A stale offset past the end snaps to the last real page.
  - **Loading shows placeholder rows** with a Skeleton in each cell, not a block in `renderEmptyState`, so the bars line up with their columns.
- **No dedicated ConflictNotice.** The backend's 409 messages are already specific ("This class's room is already occupied in this day and period."), so a generic `Notice` shows them. Per-screen hints such as "move her 7B class first" belong with the timetable screens (F6d).
- **Tests cover our wiring, not React Aria.** Label association, error and description linking, the pending guard, dialog focus and dismissal rules, the secret's copy and lock, paging math and toast announcement. Each test written after the fact was checked by breaking the behavior and watching it fail. Vitest's `test`/`expect` are imported explicitly, so Testing Library's per-test cleanup is registered by hand in `src/test/setup.ts`; without it one test's DOM leaks into the next.

## Consequences
- **A new component follows this checklist:** variant enum, layout-only `className`, `data-*` state styling, real labels, a styleguide entry, and tests for whatever behavior is ours.
- **Upgrading React Aria means re-checking `toast.tsx`** against the toast API, which may have stabilized or changed by then.
- **Bundle size:** the root chunk is about 121 kB gzipped, mostly React and React Aria (the Toaster lives at the root). That's acceptable for an internal app. Revisit it with the React performance guide if first load becomes a problem.
- **The styleguide's demos (tables, dialogs, toasts) use local state.** Real screens wire the same components to TanStack Query and URL search params from F3 on.
