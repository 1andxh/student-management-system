import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useLayoutEffect, useState } from "react";

export const Route = createFileRoute("/styleguide")({
  component: Styleguide,
});

type Theme = "system" | "light" | "dark";
const THEMES: Theme[] = ["system", "light", "dark"];

// Token preview for Stage F2a: the raw design decisions, rendered, before
// any component is built on them. Components (F2b) get their own section
// here once they exist. The controls on this page are hand-rolled
// placeholders, not the real Button/SegmentedControl.
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

      <Section title="In context" note="A gradebook excerpt: the screen this direction is built around.">
        <GradebookSample />
        <NoticeSample />
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
        <button
          type="button"
          className="inline-flex h-9 items-center rounded-md bg-accent px-4 text-small font-medium text-on-accent shadow-button transition-[background-color,transform] duration-150 ease-soft hover:bg-accent-hover active:scale-[0.96] pointer-coarse:h-11"
        >
          Add assessment
        </button>
      </div>
    </div>
  );
}

// Hand-authored 24×24 stroke icons (dense-ui-craft): same voice as the type,
// no icon-library import. Shape carries the state too, so it never depends
// on color alone.
function AlertIcon() {
  return (
    <svg viewBox="0 0 24 24" className="size-5 shrink-0" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7.5v5.5" />
      <path d="M12 16.5h.01" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg viewBox="0 0 24 24" className="size-5 shrink-0" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="9" />
      <path d="M8 12.5l2.75 2.75L16 10" />
    </svg>
  );
}

function NoticeSample() {
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <div role="note" className="flex gap-3 rounded-lg bg-red-pen-tint p-4 text-red-pen">
        <AlertIcon />
        <div>
          <p className="font-medium">Ms. Lovelace already teaches period 3 on Monday</p>
          <p className="mt-1 text-small text-ink-2">
            Pick another period, or move her 7B Science class first.
          </p>
        </div>
      </div>
      <div role="note" className="flex gap-3 rounded-lg bg-ok-tint p-4 text-ok">
        <CheckIcon />
        <div>
          <p className="font-medium">Grace Hopper assigned to 7A</p>
          <p className="mt-1 text-small text-ink-2">Enrolled in all 6 of 7A’s classes.</p>
        </div>
      </div>
    </div>
  );
}
