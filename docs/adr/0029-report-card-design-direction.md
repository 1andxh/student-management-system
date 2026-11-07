# 0029. "Report card" design direction and tokens

## Status
Accepted. Solomon approved the rendered `/styleguide` after one revision.

## Context
The frontend this replaces looked generic. Three directions were offered, each drawn from a school's own objects: "Report card" (paper, chalkboard green, red pen), "Bell schedule" (time-first, school-bus yellow) and "Chalk & slate" (subject color-coding). Solomon picked Report card. Its first rendering was approved in direction but judged "too generic … should feel premium and smooth, not just flat", with two specific dislikes: uppercase eyebrow labels, and a colored side strip on notice boxes. He also shared a UI guide (molveau.ca "UI prompt pack") as a reference.

## Decision
- **Palette: one accent, one attention color, everything else neutral.**
  - **Chalkboard green** (`--accent`) is for the primary action in a view, links, focus and selection.
  - **Red pen** (`--red-pen`) is used *only* where something needs attention: ungraded cells, conflicts, errors, destructive actions. It is never decorative.
  - Neutrals are slightly green-tinted greys, and ink is never pure black or white.
  - All values live in `web/src/styles.css`.
- **Every token is declared once with both themes: `light-dark(<light>, <dark>)`.** `color-scheme` alone picks the theme: the OS preference by default, or `data-theme` on `<html>` to override it. The first version repeated the dark block for the OS case and the explicit-switch case, and the two copies drifted within a day. A single declaration can't drift. This requires Chrome 123, Safari 17.5 or Firefox 120 (all 2024) or later.
- **Depth comes from light, not borders.**
  - Cards get a layered shadow *instead of* a border, never both: the reference guide's "keep one" rule, and the main reason the first rendering read as flat.
  - Each elevation level (`control`, `card`, `raised`, `overlay`) stacks a 1px ring for a crisp edge, a tight contact shadow and a wide ambient one.
  - In dark mode, where shadows barely register, a lit inset top edge does most of the work.
  - The canvas sits a step below white (`#F2F4F3`) so cards lift off it.
  - Recessed tracks such as switches use a darker `--well`.
- **No decorative gradients.** "Not flat" was solved with elevation and light, not gradients; the reference guide rejects decorative gradients, and so does this design.
- **Type:**
  - **Public Sans** (made for the U.S. Web Design System) for the interface. **IBM Plex Mono** for every score, ID, time and count, with `tabular-nums` so columns line up.
  - The scale is dense and named by job: caption 12, small 13, body 14, lead 16, title 20, display 30.
  - Sentence case everywhere: no uppercase eyebrows or uppercase table headers.
  - Fonts are self-hosted through `@fontsource`, not loaded from Google Fonts, so the app makes no third-party requests. That matters for a system holding minors' data.
- **Tailwind's default scales are removed** (`--color-*`, `--text-*`, `--shadow-*`, `--radius-*: initial`). `bg-blue-500`, `text-lg` or `shadow-md` generate no CSS, so the only values anyone can reach for are these tokens.
- **Motion:**
  - Only `transform`/`opacity`, plus color on hover, all under 300ms.
  - One house curve (`--ease-soft`) for state changes, and a snappier one (`--ease-snap`) for things that open or slide.
  - Pressed controls scale to 0.96.
  - Moving selection uses a single sliding indicator, not each item toggling its own background.
  - `prefers-reduced-motion` turns non-essential motion off globally.
- **State is never carried by color alone.** Notices pair their tint with a status icon, an ungraded cell is a dash with "Not graded" for screen readers, and the selected switch option is raised and bolder as well as colored.
- **Controls are 36px tall, and 44px on touch screens** (`pointer-coarse`).

### Contrast (WCAG AA, computed, not eyeballed)
Every text/background pair the components use passes 4.5:1, and every control boundary passes 3:1, in both themes. Representative pairs (light / dark):

| Pair | Light | Dark |
|---|---|---|
| ink-3 (muted) on canvas | 4.98 | 7.01 |
| ink-3 on inset (table header) | 4.90 | 6.77 |
| on-accent on accent (primary button) | 6.29 | 8.66 |
| red-pen on surface | 6.54 | 6.96 |
| red-pen on red-pen-tint | 5.65 | 6.26 |
| ink-2 on red-pen-tint (notice body) | 7.70 | 8.69 |
| line-strong on field (input border, 3:1) | 3.70 | 3.55 |
| accent on surface (focus ring, 3:1) | 6.29 | 8.19 |

Two values from the originally previewed palette failed and were changed:
- Muted text `#6B777A` measured 4.11 on inset panels, so it became `#5F6B6E`.
- The hairline `#DDE1DE` measured 1.32 as an input border, so inputs got a separate `--line-strong`.

`ink-3` on `--well` measures 4.41, so text on wells uses `ink-2`.

## Consequences
- **Any token change means re-running the contrast check** for the pairs it touches. The pair table above is the minimum set.
- **Components never use `dark:` variants or raw hex.** They use role utilities (`bg-surface`, `text-ink-3`, `shadow-card`), and theme switching is entirely the stylesheet's job.
- **A new color role is added in three places:** its `light-dark()` value, its `@theme` mapping, and the styleguide swatch list.
- **`/styleguide` is the living reference.** F2b adds the real components to it. It should become dev-only (or admin-only) once the app has real routes (F3).
- **Older browsers degrade.** Ones without `light-dark()` lose theme colors. That's accepted for a school-managed modern-browser audience, and not polyfilled.
