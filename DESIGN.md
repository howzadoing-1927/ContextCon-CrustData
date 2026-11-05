---
name: Outcome AI
description: Dark operator console for an autonomous SDR worker. Proof-first, calm density, honest provenance.
---

<!-- SEED: established with the user before implementation; re-run /impeccable document once there's code to capture the actual tokens and components. -->

# Design

## Overview

Outcome AI is a working console. Someone launches a mission and watches an autonomous worker research, email, read a reply and book a meeting, and every step has to read as proven. The thesis is **proof as the interface**: provider IDs, hashes and timestamps are part of the visible design, not hidden in a debug panel.

Scene: a founder at a laptop late at night, with Gmail and Google Calendar open in the next window, screen-recording for evaluators. That scene sets a dark ground. The dim room and long session call for low glare, and the screen must sit calmly beside Google's light UIs without competing with them.

Signature move: **the mission route.** The conversation state machine is drawn as a single vertical transit line. Passed stations are filled, the current station is ringed in the signal colour, and terminal outcomes (declined, suppressed, needs human, send unknown, stopped) branch off as a short spur at the point where they happened. The same route appears in miniature on mission list rows.

Motion conveys state only. A station advancing, a chip changing, or a drawer opening takes 150–200 ms with exponential ease-out. Waiting is still, never animated. Active work gets one slow ring pulse on the current station and nothing else. `prefers-reduced-motion` removes the pulse.

## Colors

Strategy: Restrained, with colour doing real jobs. The ground is a blue-tinted ink slate with a slightly cooler second layer for the shell rail and panels. One warm signal colour marks "needs attention" and the current station. Semantic state hues sit on top only where they carry meaning.

Roles (values to be finalized in implementation, starting from these OKLCH targets):

- ground, shell, raised surface, hairline: ink-slate ramp around hue 245
- text, muted, faint: tinted neutrals from the same hue, never pure grey
- signal (attention, current station, primary action): warm amber
- success (booked, completed, criterion pass), info (running, evaluating), warning (waiting, needs human), danger (failed, suppressed, stopped, criterion fail), muted (draft, no match, declined, unknown)
- provenance: LIVE solid green; CACHED blue outline; FIXTURE violet with a hatched fill; SIMULATED BUYER cyan outline with a mask glyph. These four treatments are never reused for anything else.

## Typography

One workhorse family, chosen for Operate mode: IBM Plex Sans for every UI role and IBM Plex Mono only for data that really is machine data (UUIDs, provider refs, hashes, RFC3339 timestamps, field paths, counters). Mono is never used as a "technical" costume for labels or headings. Fixed rem scale with a tight ratio: 12 / 13 / 14 / 16 / 20 / 26. Tabular numerals everywhere numbers align.

## Layout

App shell: a top bar (product, organization, mode badge, worker health) and a narrow left nav. Mission detail is a three-zone working screen: the route rail on the left, the case (prospect, conversation, slots, booking, handoff) in the centre at a readable measure, and the decision ledger on the right as a scrollable column. Below 1280 px the ledger collapses under the case; below 1024 px the route rail becomes a horizontal strip. Spacing is on a 4 px grid, with tight groups and generous separation between sections.

## Elevation & Depth

Flat layers separated by tone and 1 px hairlines. No nested cards. Only overlays (popovers, drawers) get a shadow, and it is soft and offset to read as lifted above the console.

## Shapes

Small radii (4–6 px) on controls and panels and full rounding only on status chips. Provenance stamps are square-cornered so they read as stamps, not pills.

## Do's and Don'ts

- Do show the evidence one click from every claim.
- Do keep the real researched identity and the simulated buyer visually separate. The buyer always carries the SIMULATED BUYER stamp.
- Do render unknown as "unknown". Never render it as zero, blank, or a guess.
- Don't put a spinner on waiting states; show the last check and what happens next.
- Don't add approve-all, force-send, or mark-complete controls.
- Don't use gradients, glass, glow, eyebrow labels, or icon tiles above headings.
- Don't label calendar attendees as accepted.
