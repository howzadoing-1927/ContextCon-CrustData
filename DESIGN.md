# Outcome AI — Design system (as built)

Operator console, dark. One screen per job: set up authority, launch a mission, watch it run, step in only when the worker is blocked. Source of truth for tokens: `apps/web/src/app/globals.css`. Machine-readable copy: `.impeccable/design.json`.

## Ground and layers

| Token | Value | Use |
| --- | --- | --- |
| `--background` | `oklch(0.168 0.014 248)` | Page ground, blue-tinted ink-slate |
| `--shell` | `oklch(0.198 0.02 250)` | Top bar, fixture bar, sticky rails |
| `--raised` / `--card` | `oklch(0.212 0.017 248)` | Message cards, notices, inputs |
| `--popover` | `oklch(0.238 0.019 248)` | Popovers, drawer |
| `--hairline` / `--border` | `oklch(0.285 0.017 248)` | All separation. Hairlines, never shadows |
| `--input` | `oklch(0.34 0.018 248)` | Field borders |

Ink: `--foreground oklch(0.95 0.006 248)`, `--muted-foreground oklch(0.76 0.014 248)`, `--faint oklch(0.66 0.014 248)`. Every text pair meets WCAG AA on its ground.

## Colour roles

- **Primary is light ink.** `--primary oklch(0.92 0.008 245)` on `--primary-foreground oklch(0.19 0.014 248)`. Used for the main action, the logo mark, checked controls.
- **Amber is signal only.** `--signal oklch(0.81 0.135 76)`, also `--ring`. Reserved for: needs-you state and the exception strip, the current route station, stale/unhealthy system banners, the focus ring. Never decoration, never the active tab.
- Status: `--ok oklch(0.79 0.13 158)`, `--info oklch(0.78 0.095 238)`, `--warn oklch(0.83 0.13 82)`, `--bad` / `--destructive oklch(0.72 0.16 25)`, `--quiet oklch(0.7 0.014 248)`.

## Provenance stamps

Square (no radius), uppercase, 11px, 0.06em tracking, icon + label. Every external fact or action carries one.

| Stamp | Treatment |
| --- | --- |
| LIVE | Solid `--live oklch(0.79 0.13 158)` fill, dark text, radio glyph |
| CACHED | `--cached oklch(0.78 0.095 238)` outline, history glyph |
| FIXTURE | `--fixture oklch(0.8 0.02 248)` **dashed** outline, flask glyph. Cool neutral: "not real" without a hue |
| SIMULATED BUYER | `--simbuyer oklch(0.83 0.095 196)` outline, mask glyph |

`ModeBadge` ("Live tools · simulated buyer") is visible at every width: full at `xl+`, compact (icons + "Simulated buyer") from `sm` to `xl` in the top bar, and in the mission header row below `sm`.

## Type

IBM Plex Sans for everything; IBM Plex Mono only for machine data (IDs, emails, timestamps, counts, versions). `font-variant-numeric: tabular-nums` everywhere numbers align; mono adds slashed zero. `text-wrap: pretty` on `p`, `li`, `dd`.

| Step | Size / line |
| --- | --- |
| `2xs` | 12 / 16 — metadata, mono IDs |
| `xs` | 13 / 18 — dense body, table cells |
| `sm` | 14 / 20 — body, section headings (`h2`, semibold) |
| `base` | 16 / 24 — handoff heading |
| `lg` | 20 / 28 — mission title (`h1`) |
| `xl` | 26 / 32 — page titles |

Measure: prose capped at 60–68ch.

## Shape and motion

Radius `0.375rem` (`sm 0.25`, `md 0.3125`, `lg 0.375`, `xl 0.5`). Stamps are square. Easing `--ease-out-expo cubic-bezier(0.16, 1, 0.3, 1)`. Motion: `station-pulse` on the active station (1.8s), `row-arrive` for ledger rows that land after first load. Both disabled under `prefers-reduced-motion`.

## Layout

- Navigation lives in the top bar (Missions, New mission, Setup), active tab underlined in foreground. Below `md` the bar wraps to two rows, nav on its own row.
- Mission detail: grid `13.75rem / 1fr / 23.75rem` — route rail, case + conversation, decision ledger. Rails are sticky under the top bar. Below `xl` the ledger moves under the centre; below `lg` the route becomes `CompactRoute` (dots, current station named, terminal spur chip).
- Setup: sticky readiness checklist (n/4) beside the sections.
- One amber exception strip under the mission header opens a right drawer (34rem) with typed resolutions. `#resolve` deep-links into it.

## Signature: the mission route

Ten stations from Research to Handoff written. Passed stations are filled grey, the current one is an amber ring (pulsing while running, hollow while waiting or paused), terminal outcomes branch off as a spur chip ("Needs you", "Stopped", "Failed", "No match", "Buyer declined").

## Bans

No gradients, no glass or backdrop blur (sheet overlay is flat `black/45`), no nested cards, no eyebrow labels, no hatched or violet stripes, no shadows for separation. Fixture data is never labelled LIVE; unknown cost reads "Cost unknown", never 0; attendees are never "accepted"; no approve-all, force-send or mark-complete controls.
