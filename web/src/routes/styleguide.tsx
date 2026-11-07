import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useLayoutEffect, useState } from "react";

import type { SortDescriptor } from "react-aria-components";

import { Button } from "../components/ui/button";
import { ConfirmDialog, Dialog, DialogActions, DialogTrigger } from "../components/ui/dialog";
import { EmptyState } from "../components/ui/empty-state";
import { Notice } from "../components/ui/notice";
import { OneTimeSecretDialog } from "../components/ui/one-time-secret-dialog";
import { SelectField, SelectItem } from "../components/ui/select-field";
import { Skeleton } from "../components/ui/skeleton";
import { Cell, Column, Pagination, Row, Table, TableBody, TableFrame, TableHeader } from "../components/ui/table";
import { TextField } from "../components/ui/text-field";
import { toast } from "../components/ui/toast";

export const Route = createFileRoute("/styleguide")({
  component: Styleguide,
});

type Theme = "system" | "light" | "dark";
const THEMES: Theme[] = ["system", "light", "dark"];

// The living reference for the design system (ADR 0029): tokens first,
// then the real components from src/components/ui, then a composed sample.
// The theme switch is still a hand-rolled placeholder until a
// SegmentedControl component exists.
function Styleguide() {
  const [theme, setTheme] = useState<Theme>("system");

  // Layout effect, not effect: the attribute must land before paint, or
  // swatches would read (and the page would flash) the previous theme.
  useLayoutEffect(() => {
    const root = document.documentElement;
    if (theme === "system") delete root.dataset.theme;
    else root.dataset.theme = theme;
    return () => {
      delete root.dataset.theme;
    };
  }, [theme]);

  return (
    <div className="mx-auto max-w-5xl px-4 pb-24 pt-12 sm:px-8">
      <header className="flex flex-wrap items-end justify-between gap-6">
        <div>
          <h1 className="text-display font-semibold">Report card</h1>
          <p className="mt-2 max-w-prose text-lead text-ink-2">
            Calm, dense and paper-like. One chalkboard-green accent; red pen only where something
            needs attention.
          </p>
        </div>
        <ThemeSwitch value={theme} onChange={setTheme} />
      </header>

      <Section title="Color" note="Values are resolved live from the stylesheet.">
        <div className="grid gap-4 md:grid-cols-2">
          <SwatchGroup label="Surfaces" names={["canvas", "surface", "field", "inset", "well"]} theme={theme} />
          <SwatchGroup label="Ink" names={["ink", "ink-2", "ink-3"]} theme={theme} text />
          <SwatchGroup label="Accent" names={["accent", "accent-hover", "accent-ink", "accent-tint"]} theme={theme} />
          <SwatchGroup label="Red pen" names={["red-pen", "red-pen-tint"]} theme={theme} />
          <SwatchGroup label="Status" names={["warn", "warn-tint", "ok", "ok-tint"]} theme={theme} />
          <SwatchGroup label="Lines" names={["line", "line-strong"]} theme={theme} />
        </div>
      </Section>

      <Section
        title="Depth"
        note="Surfaces are separated by light, not borders. Each level is a stack of shadows; in dark mode a lit top edge does most of the work."
      >
        <ElevationSample />
      </Section>

      <Section title="Type" note="Public Sans for the interface, IBM Plex Mono for figures.">
        <TypeScale />
      </Section>

      <Section
        title="Buttons"
        note="One primary per view. Press one to see the pending state: it keeps its width, ignores presses and stays focusable."
      >
        <ButtonSample />
      </Section>

      <Section
        title="Fields"
        note="Labels are always real labels. Errors sit under the field and are read out with it."
      >
        <FieldSample />
      </Section>

      <Section
        title="Dialogs"
        note="General dialogs close by X, Esc or clicking outside. Confirmations and one-time secrets can’t be closed by accident."
      >
        <DialogSample />
      </Section>

      <Section title="Toasts" note="Success and info close after 5 seconds. Errors stay until dismissed.">
        <ToastSample />
      </Section>

      <Section
        title="Table"
        note="Sortable headers, pinned first column, numbers in mono. Arrow keys move between cells. Try the empty and loading states."
      >
        <TableSample />
      </Section>

      <Section title="Notices" note="Inline messages in the page. The icon shape carries the state, not just the color.">
        <div className="grid gap-4 sm:grid-cols-2">
          <Notice tone="error" title="Ms. Lovelace already teaches period 3 on Monday">
            Pick another period, or move her 7B Science class first.
          </Notice>
          <Notice tone="success" title="Grace Hopper assigned to 7A">
            Enrolled in all 6 of 7A’s classes.
          </Notice>
          <Notice tone="warning" title="Conflicts are only checked when a slot is created">
            Changing a class’s teacher or room later can create one silently.
          </Notice>
        </div>
      </Section>

      <Section title="In context" note="A gradebook excerpt: the screen this direction is built around.">
        <GradebookSample />
      </Section>
    </div>
  );
}

/* ---------------------------------------------------------------- switch */

// One indicator that slides between options (transform only), rather than
// each option toggling its own background: it reads as a single piece of
// UI following the selection. Equal-width columns make the slide a plain
// translateX(index × 100%), with no measuring.
function ThemeSwitch({ value, onChange }: { value: Theme; onChange: (t: Theme) => void }) {
  const index = THEMES.indexOf(value);
  return (
    <fieldset className="relative grid grid-cols-3 rounded-md bg-well p-1 shadow-[inset_0_1px_2px_var(--shade-2)]">
      <legend className="sr-only">Theme</legend>
      <span
        aria-hidden="true"
        className="absolute inset-y-1 left-1 w-[calc((100%-0.5rem)/3)] rounded-sm bg-surface shadow-control transition-transform duration-250 ease-snap"
        style={{ transform: `translateX(${index * 100}%)` }}
      />
      {THEMES.map((option) => (
        <label
          key={option}
          className="relative z-10 flex h-8 cursor-pointer items-center justify-center rounded-sm px-4 text-small capitalize text-ink-2 transition-colors duration-150 ease-soft select-none hover:text-ink has-checked:font-medium has-checked:text-ink has-focus-visible:outline-2 has-focus-visible:outline-offset-2 has-focus-visible:outline-accent pointer-coarse:h-11"
        >
          <input
            type="radio"
            name="theme"
            value={option}
            checked={value === option}
            onChange={() => onChange(option)}
            className="sr-only"
          />
          {option}
        </label>
      ))}
    </fieldset>
  );
}

/* --------------------------------------------------------------- layout */

function Section({ title, note, children }: { title: string; note: string; children: React.ReactNode }) {
  return (
    <section className="mt-16">
      <h2 className="text-title font-semibold">{title}</h2>
      <p className="mt-1 max-w-prose text-ink-3">{note}</p>
      <div className="mt-6 space-y-4">{children}</div>
    </section>
  );
}

/* --------------------------------------------------------------- swatches */

// Custom properties come back from getComputedStyle as their raw text
// ("light-dark(#f2f4f3, #111615)"), not a color. To show what the token
// actually resolves to in the active theme, paint it onto a real property
// of a throwaway element and read that back.
function resolveToken(name: string): string {
  const probe = document.createElement("div");
  probe.style.color = `var(--${name})`;
  document.body.append(probe);
  const rgb = getComputedStyle(probe).color;
  probe.remove();
  const parts = rgb.match(/[\d.]+/g)?.map(Number) ?? [];
  if (parts.length < 3) return rgb;
  const [r = 0, g = 0, b = 0] = parts;
  return "#" + [r, g, b].map((n) => Math.round(n).toString(16).padStart(2, "0")).join("");
}

function useTokenValue(name: string, theme: Theme) {
  const [value, setValue] = useState("");
  useEffect(() => {
    const read = () => setValue(resolveToken(name));
    read();
    // "system" follows the OS; re-read if the OS theme flips while open.
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    media.addEventListener("change", read);
    return () => media.removeEventListener("change", read);
  }, [name, theme]);
  return value;
}

function SwatchGroup({
  label,
  names,
  theme,
  text = false,
}: {
  label: string;
  names: string[];
  theme: Theme;
  text?: boolean;
}) {
  return (
    <div className="rounded-lg bg-surface p-4 shadow-card">
      <h3 className="text-small font-medium text-ink-2">{label}</h3>
      <ul className="mt-3 grid grid-cols-2 gap-x-3 gap-y-4 sm:grid-cols-4">
        {names.map((name) => (
          <Swatch key={name} name={name} text={text} theme={theme} />
        ))}
      </ul>
    </div>
  );
}

function Swatch({ name, text, theme }: { name: string; text: boolean; theme: Theme }) {
  const value = useTokenValue(name, theme);
  return (
    <li>
      {text ? (
        <div
          className="flex h-12 items-center text-title font-semibold"
          style={{ color: `var(--${name})` }}
        >
          Aa
        </div>
      ) : (
        // An inner 1px ring keeps a near-white swatch visible on a white card.
        <div
          className="h-12 rounded-sm shadow-[inset_0_0_0_1px_var(--edge-ring)]"
          style={{ background: `var(--${name})` }}
        />
      )}
      <div className="mt-2 text-small font-medium">{name}</div>
      <div className="font-mono text-caption text-ink-3">{value || "…"}</div>
    </li>
  );
}

/* --------------------------------------------------------------- depth */

function ElevationSample() {
  const levels = [
    { name: "control", className: "shadow-control rounded-md", use: "Inputs, switches" },
    { name: "card", className: "shadow-card rounded-lg", use: "Panels, tables" },
    { name: "raised", className: "shadow-raised rounded-lg", use: "Hovered or dragged" },
    { name: "overlay", className: "shadow-overlay rounded-lg", use: "Menus, dialogs" },
  ];
  return (
    <div className="grid grid-cols-2 gap-6 rounded-lg bg-inset p-6 sm:grid-cols-4 sm:p-8">
      {levels.map((level) => (
        <div key={level.name} className={`bg-surface p-4 ${level.className}`}>
          <div className="text-small font-medium">{level.name}</div>
          <div className="mt-6 text-caption text-ink-3">{level.use}</div>
        </div>
      ))}
    </div>
  );
}

/* --------------------------------------------------------------- type */

// Full class names, never `text-${token}`: Tailwind only generates CSS for
// class names it can find spelled out in the source.
const TYPE_STEPS = [
  { token: "display", size: "30 / 36", sample: "Mathematics · 7A", className: "text-display font-semibold" },
  { token: "title", size: "20 / 28", sample: "Autumn term gradebook", className: "text-title font-semibold" },
  { token: "lead", size: "16 / 24", sample: "Next: Science in Lab 2 at 10:50", className: "text-lead font-medium" },
  { token: "body", size: "14 / 20", sample: "Assigning a student to a section enrolls them in all of its classes.", className: "text-body" },
  { token: "small", size: "13 / 18", sample: "Attached to Grade 7, Section A", className: "text-small text-ink-2" },
  { token: "caption", size: "12 / 16", sample: "Last updated 3 minutes ago", className: "text-caption text-ink-3" },
] as const;

function TypeScale() {
  return (
    <div className="divide-y divide-line rounded-lg bg-surface shadow-card">
      {TYPE_STEPS.map((step) => (
        <div key={step.token} className="grid grid-cols-[5.5rem_1fr] items-baseline gap-4 px-5 py-4 sm:grid-cols-[8rem_1fr]">
          <div>
            <div className="text-small font-medium">{step.token}</div>
            <div className="font-mono text-caption text-ink-3">{step.size}</div>
          </div>
          <p className={`${step.className} min-w-0`}>{step.sample}</p>
        </div>
      ))}
      <div className="grid grid-cols-[5.5rem_1fr] items-baseline gap-4 px-5 py-4 sm:grid-cols-[8rem_1fr]">
        <div>
          <div className="text-small font-medium">mono</div>
          <div className="font-mono text-caption text-ink-3">figures</div>
        </div>
        <p className="min-w-0 font-mono tabular">STU-0003 · 18.50 / 20.00 · 09:45–10:30</p>
      </div>
    </div>
  );
}

/* --------------------------------------------------------------- components */

function useFakeRequest() {
  const [pending, setPending] = useState<string | null>(null);
  const run = (key: string) => {
    setPending(key);
    window.setTimeout(() => setPending(null), 1500);
  };
  return { pending, run };
}

function ButtonSample() {
  const { pending, run } = useFakeRequest();
  return (
    <div className="space-y-4 rounded-lg bg-surface p-5 shadow-card">
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="primary" isPending={pending === "primary"} onPress={() => run("primary")}>
          Save changes
        </Button>
        <Button isPending={pending === "secondary"} onPress={() => run("secondary")}>
          Export roster
        </Button>
        <Button variant="quiet" isPending={pending === "quiet"} onPress={() => run("quiet")}>
          Cancel
        </Button>
        <Button variant="danger" isPending={pending === "danger"} onPress={() => run("danger")}>
          Remove from section
        </Button>
      </div>
      <div className="flex flex-wrap items-center gap-3 border-t border-line pt-4">
        <Button size="sm" variant="primary">
          Grade
        </Button>
        <Button size="sm">Edit</Button>
        <Button size="sm" variant="quiet">
          Details
        </Button>
        <Button isDisabled>Disabled</Button>
      </div>
    </div>
  );
}

const DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"];

function FieldSample() {
  return (
    <div className="grid gap-x-6 gap-y-5 rounded-lg bg-surface p-5 shadow-card sm:grid-cols-2">
      <TextField label="Student number" placeholder="STU-0001…" spellCheck="false" autoComplete="off" />
      <TextField
        label="Room"
        description="Free text. “Lab 2” and “lab 2” count as different rooms."
        defaultValue="Lab 2"
      />
      <TextField label="PIN" defaultValue="12a4" isInvalid errorMessage="A PIN is 6 digits. Letters aren’t allowed." />
      <TextField label="Email" defaultValue="grace.hopper@demo.school" isDisabled />
      <SelectField label="Day" placeholder="Choose a day…">
        {DAYS.map((day) => (
          <SelectItem key={day} id={day.toLowerCase()}>
            {day}
          </SelectItem>
        ))}
      </SelectField>
      <SelectField label="Period" placeholder="Choose a period…" isInvalid errorMessage="Ms. Lovelace already teaches period 3 on Monday.">
        <SelectItem id="p1">Period 1 · 08:00–08:45</SelectItem>
        <SelectItem id="p2">Period 2 · 08:50–09:35</SelectItem>
        <SelectItem id="p3">Period 3 · 09:45–10:30</SelectItem>
      </SelectField>
    </div>
  );
}

function DialogSample() {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [secret, setSecret] = useState<{ title: string; recipient: string; name: string; value: string } | null>(null);
  const wait = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms));

  return (
    <div className="flex flex-wrap gap-3 rounded-lg bg-surface p-5 shadow-card">
      <DialogTrigger>
        <Button>Edit room</Button>
        <Dialog title="Edit room for 7A Science" description="Rooms are free text and case-sensitive.">
          {({ close }) => (
            <>
              <TextField label="Room" defaultValue="Lab 2" />
              <DialogActions>
                <Button variant="quiet" onPress={close}>
                  Cancel
                </Button>
                <Button variant="primary" onPress={close}>
                  Save room
                </Button>
              </DialogActions>
            </>
          )}
        </Dialog>
      </DialogTrigger>

      <Button variant="danger" onPress={() => setConfirmOpen(true)}>
        Remove from section…
      </Button>
      <ConfirmDialog
        isOpen={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Remove Grace Hopper from 7A?"
        description="Her enrollments in 7A’s classes stay. Remove those separately if she’s leaving them too."
        confirmLabel="Remove from section"
        onConfirm={async () => {
          await wait(1200);
          toast({ tone: "success", title: "Grace Hopper removed from 7A" });
        }}
      />

      <Button
        onPress={() =>
          setSecret({ title: "New password for Ada Lovelace", recipient: "Ada Lovelace", name: "password", value: "S_7lD50GYvsGVY0m3wErQw" })
        }
      >
        Issue teacher password
      </Button>
      <Button
        onPress={() => setSecret({ title: "PIN for Grace Hopper", recipient: "Grace Hopper", name: "PIN", value: "482913" })}
      >
        Issue student PIN
      </Button>
      {secret && (
        <OneTimeSecretDialog
          isOpen
          onClose={() => setSecret(null)}
          title={secret.title}
          recipient={secret.recipient}
          secretName={secret.name}
          secret={secret.value}
        />
      )}
    </div>
  );
}

function ToastSample() {
  return (
    <div className="flex flex-wrap gap-3 rounded-lg bg-surface p-5 shadow-card">
      <Button onPress={() => toast({ tone: "success", title: "Timetable saved", description: "7A’s Monday now has 6 periods." })}>
        Success
      </Button>
      <Button
        onPress={() =>
          toast({ tone: "error", title: "Couldn’t save the timetable", description: "The connection dropped. Your changes are still here; try again." })
        }
      >
        Error
      </Button>
      <Button onPress={() => toast({ tone: "info", title: "Showing Autumn term only" })}>Info</Button>
    </div>
  );
}

interface StudentRow {
  id: string;
  name: string;
  number: string;
  section: string;
  active: boolean;
  classes: number;
}

const STUDENTS: StudentRow[] = [
  { id: "1", name: "Hopper, Grace", number: "STU-0003", section: "7A", active: true, classes: 6 },
  { id: "2", name: "Johnson, Katherine", number: "STU-0011", section: "7A", active: true, classes: 6 },
  { id: "3", name: "Lovelace, Ada", number: "STU-0001", section: "7B", active: true, classes: 5 },
  { id: "4", name: "Turing, Alan", number: "STU-0007", section: "7B", active: false, classes: 0 },
  { id: "5", name: "Hamilton, Margaret", number: "STU-0014", section: "8A", active: true, classes: 7 },
  { id: "6", name: "Shannon, Claude", number: "STU-0009", section: "8A", active: true, classes: 7 },
  { id: "7", name: "Liskov, Barbara", number: "STU-0016", section: "8A", active: true, classes: 7 },
];
const PAGE = 5;

function TableSample() {
  const [sort, setSort] = useState<SortDescriptor>({ column: "name", direction: "ascending" });
  const [offset, setOffset] = useState(0);
  const [mode, setMode] = useState<"rows" | "empty" | "loading">("rows");

  const sorted = [...STUDENTS].sort((a, b) => {
    const key = sort.column as keyof StudentRow;
    const cmp = String(a[key]).localeCompare(String(b[key]), undefined, { numeric: true });
    return sort.direction === "descending" ? -cmp : cmp;
  });
  const rows = mode === "rows" ? sorted.slice(offset, offset + PAGE) : [];
  // Placeholder rows while loading, so each skeleton bar sits in the column
  // it stands in for.
  const placeholders = Array.from({ length: 4 }, (_, i) => ({ id: `loading-${i}` }));

  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        {(["rows", "empty", "loading"] as const).map((m) => (
          <Button key={m} size="sm" variant={mode === m ? "secondary" : "quiet"} onPress={() => setMode(m)}>
            {m === "rows" ? "With rows" : m === "empty" ? "Empty" : "Loading"}
          </Button>
        ))}
      </div>
      <TableFrame
        footer={
          mode !== "loading" && (
          <Pagination
            offset={offset}
            limit={PAGE}
            total={mode === "rows" ? STUDENTS.length : 0}
            onChange={setOffset}
            noun="students"
          />
          )
        }
      >
        <div aria-busy={mode === "loading"}>
          {mode === "loading" && <span className="sr-only">Loading students…</span>}
          <Table aria-label="Students" sortDescriptor={sort} onSortChange={setSort}>
            <TableHeader>
              <Column id="name" isRowHeader allowsSorting>
                Name
              </Column>
              <Column id="number" allowsSorting>
                Student number
              </Column>
              <Column id="section" allowsSorting>
                Section
              </Column>
              <Column id="active">Status</Column>
              <Column id="classes" kind="number" allowsSorting>
                Classes
              </Column>
            </TableHeader>
            {mode === "loading" ? (
              <TableBody items={placeholders}>
                {(row) => (
                  <Row id={row.id}>
                    <Cell>
                      <Skeleton className="h-4 w-36" />
                    </Cell>
                    <Cell>
                      <Skeleton className="h-4 w-20" />
                    </Cell>
                    <Cell>
                      <Skeleton className="h-4 w-8" />
                    </Cell>
                    <Cell>
                      <Skeleton className="h-4 w-16" />
                    </Cell>
                    <Cell kind="number">
                      <Skeleton className="ml-auto h-4 w-6" />
                    </Cell>
                  </Row>
                )}
              </TableBody>
            ) : (
              <TableBody
                items={rows}
                renderEmptyState={() => (
                  <EmptyState
                    title="No students in this section yet"
                    description="Assign students to a section to enroll them in all of its classes."
                    action={<Button variant="primary">Assign students</Button>}
                  />
                )}
              >
                {(row) => (
                  <Row id={row.id}>
                    <Cell>
                      <span className="font-medium">{row.name}</span>
                    </Cell>
                    <Cell>
                      <span className="font-mono text-small text-ink-2">{row.number}</span>
                    </Cell>
                    <Cell>{row.section}</Cell>
                    <Cell>
                      {/* Dot + neutral text, not a filled pill: pills get loud
                          across many rows (dense-ui-craft). */}
                      <span className="inline-flex items-center gap-2 text-small text-ink-2">
                        <span aria-hidden="true" className={`size-2 rounded-full ${row.active ? "bg-ok" : "bg-line-strong"}`} />
                        {row.active ? "Active" : "Withdrawn"}
                      </span>
                    </Cell>
                    <Cell kind="number">{row.classes}</Cell>
                  </Row>
                )}
              </TableBody>
            )}
          </Table>
        </div>
      </TableFrame>
    </div>
  );
}

/* --------------------------------------------------------------- context */

const ASSESSMENTS = ["Quiz 1", "Quiz 2", "Test 1", "Project"];
const ROWS: { name: string; number: string; scores: (number | null)[] }[] = [
  { name: "Hopper, Grace", number: "STU-0003", scores: [12, null, 41.5, 18] },
  { name: "Johnson, Katherine", number: "STU-0011", scores: [19.5, 17, 47, 19] },
  { name: "Lovelace, Ada", number: "STU-0001", scores: [18.5, 17, 44, null] },
  { name: "Turing, Alan", number: "STU-0007", scores: [16, 15.5, 39, 17.5] },
];
const MAX = [20, 20, 50, 20];

function GradebookSample() {
  return (
    <div className="overflow-hidden rounded-lg bg-surface shadow-card">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 px-5 pb-3 pt-4">
        <h3 className="text-lead font-semibold">7A · Mathematics</h3>
        <p className="text-small text-ink-3">Autumn term · 4 students</p>
      </div>
      {/* `relative` matters: the sr-only "Not graded" labels are
          position:absolute, and an absolute element is clipped only by a
          *positioned* ancestor. Without it they escape this scroller and
          widen the whole page on phones. */}
      <div className="relative overflow-x-auto">
        <table className="w-full min-w-[36rem] border-collapse text-left">
          <thead>
            <tr className="border-y border-line bg-inset text-small text-ink-3">
              <th scope="col" className="sticky left-0 bg-inset px-5 py-2 font-medium">Student</th>
              {ASSESSMENTS.map((a, i) => (
                <th key={a} scope="col" className="px-3 py-2 text-right font-medium">
                  {a} <span className="font-mono text-caption">/{MAX[i]}</span>
                </th>
              ))}
              <th scope="col" className="px-5 py-2 text-right font-medium">Average</th>
            </tr>
          </thead>
          <tbody>
            {ROWS.map((row) => {
              const graded = row.scores
                .map((s, i) => (s === null ? null : s / (MAX[i] ?? 1)))
                .filter((s): s is number => s !== null);
              const avg = Math.round((graded.reduce((a, b) => a + b, 0) / graded.length) * 100);
              return (
                <tr key={row.number} className="border-b border-line transition-colors duration-150 ease-soft last:border-b-0 hover:bg-hover">
                  <th scope="row" className="sticky left-0 bg-surface px-5 py-2.5 text-left font-normal">
                    <div className="font-medium">{row.name}</div>
                    <div className="font-mono text-caption text-ink-3">{row.number}</div>
                  </th>
                  {row.scores.map((score, i) => (
                    <td key={i} className="px-3 py-2.5 text-right font-mono">
                      {score === null ? (
                        <span className="inline-flex h-6 min-w-10 items-center justify-center rounded-sm bg-red-pen-tint px-2 text-small font-medium text-red-pen">
                          <span aria-hidden="true">—</span>
                          <span className="sr-only">Not graded</span>
                        </span>
                      ) : (
                        score.toFixed(1)
                      )}
                    </td>
                  ))}
                  <td className="px-5 py-2.5 text-right font-mono font-medium">{avg}%</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line bg-inset px-5 py-3">
        <p className="text-small text-ink-3">
          <span className="font-medium text-red-pen">2 ungraded</span> · class average{" "}
          <span className="font-mono">84%</span>
        </p>
        <Button variant="primary">Add assessment</Button>
      </div>
    </div>
  );
}
