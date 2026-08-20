# Overlay Design Proposals

**Status:** proposal / not implemented · **Audience:** maintainers, designers, operators

Ten new overlay designs for the catalogue. Six extend the existing
**stream family** (transparent graphics composited over live video in an
OBS/vMix browser source). Four introduce a **new full-screen dashboard
family**: opaque, edge-to-edge layouts that own the whole display and are
meant for a venue screen, a projector, a second monitor or a bench tablet
— *not* for compositing over a match feed.

Nothing here is built yet. Each entry is written so it can be picked up
and implemented on its own: wireframe, exact payload bindings, the DOM
contract it reuses from `overlay_static/js/app.js`, the files it adds,
and the risks it carries. The platform work the dashboard family needs
(and only that family needs) is collected once in
[The dashboard platform](#the-dashboard-platform) rather than repeated
per design.

---

## Contents

- [Where the catalogue is today](#where-the-catalogue-is-today)
- [What is missing](#what-is-missing)
- [How to read each proposal](#how-to-read-each-proposal)
- [Part 1 — Stream overlays](#part-1--stream-overlays)
  - [1. `momentum` — Momentum Rail](#1-momentum--momentum-rail)
  - [2. `courtmap` — Court Map](#2-courtmap--court-map)
  - [3. `banner` — Broadcast Band](#3-banner--broadcast-band)
  - [4. `portrait` — Portrait Bug](#4-portrait--portrait-bug)
  - [5. `flip` — Split-Flap](#5-flip--split-flap)
  - [6. `rally` — Table-Tennis Bug](#6-rally--table-tennis-bug)
- [Part 2 — Full-screen dashboards](#part-2--full-screen-dashboards)
  - [The dashboard platform](#the-dashboard-platform)
  - [7. `arena` — Arena Board](#7-arena--arena-board)
  - [8. `analyst` — Analyst Dashboard](#8-analyst--analyst-dashboard)
  - [9. `journey` — Match Journey](#9-journey--match-journey)
  - [10. `bench` — Bench Kiosk](#10-bench--bench-kiosk)
- [Data the payload already carries](#data-the-payload-already-carries)
- [Effort and suggested phasing](#effort-and-suggested-phasing)
- [Open questions](#open-questions)

---

## Where the catalogue is today

27 selectable styles, all built the same way: a Jinja2 template in
`overlay_templates/` extending `base.html`, a stylesheet in
`overlay_static/css/`, and zero per-style JavaScript — `app.js` writes
into a fixed set of element ids and skips whatever a template does not
ship (`withEl`). Grouped by intent:

| Group | Styles | Idea |
| --- | --- | --- |
| Classic bars | `default`, `original`, `split`, `compact`, `broadcast` | Two stacked rows, floating card |
| Corner chips | `corner_gradient`, `corner_jersey`, `corner_tags`, `corner_wedge`, `pylons`, `pylons_gradient` | Edge-docked pair, one chip per team |
| Kit / jersey | `clear_jersey`, `neo_jersey`, `split_jersey`, `shield` | Team identity leads |
| Texture / mood | `neon`, `led`, `glass`, `esports`, `diagonal`, `ribbon`, `pill` | A material or motion-graphics language |
| Footprint | `micro`, `vertical`, `baseline` | Very small, narrow column, bottom lower-third |
| Discipline | `beach`, `beach_twoline` | Beach-specific two-player layouts |

Two full-frame surfaces already exist and are worth studying before
building anything in Part 2, because they solve half the problems the
dashboards will hit:

- **The set-summary recap** (`overlay_static/js/set_summary.js`) —
  six full-frame recap layouts (`brand ledger`, `brand columns`, `bento`,
  `glass`, `ledger diff`, `bumper`) drawn from the same payload, toggled
  by `match_info.show_set_summary`. It is the proof that a full-frame,
  chart-carrying render loop works inside the overlay page.
- **The spectator page** (`overlay_templates/_spectator.html` +
  `spectator.js`, 826 lines of CSS) — an opaque, responsive,
  self-contained page with a per-set SVG progression chart, a set-history
  table, and a nine-row live-stats table. It is the closest thing to a
  dashboard the project has, and its chart and stat rows are the
  components the dashboards should reuse rather than reinvent.

## What is missing

Six gaps, each of which one or more proposals below closes.

1. **Nothing on the live overlay shows how the match is *going*.** Every
   style renders instantaneous state — score, sets, serve, timeouts. The
   backend computes streaks, runs, service hold and a full point-by-point
   history on every broadcast, and the live overlay throws all of it away.
   (This is deliberate: the live-stats panel and points-history strip were
   removed from the operator UI, see the comment in `base.html`. The
   proposals respect that decision — `momentum` reintroduces *one derived
   bar*, not a stats panel; the rest of the evolution data goes to the
   dashboards, which are not composited over a match feed.)
2. **No spatial information.** Volleyball has sides, and the app tracks
   them (`match_info.sides_swapped`, plus a beach side-switch countdown).
   No style draws a court.
3. **Every style is authored on a 1920×1080 canvas.** Vertical-video
   streams (Shorts / Reels / TikTok / phone-first club streams) get a
   landscape bug scaled down into a corner.
4. **Table tennis has no style of its own.** `beach`/`beach_twoline`
   serve the beach preset; the table-tennis preset (11 points, best of
   up to 7, serve rotating every 2 points with a backend-computed
   countdown) renders on layouts designed for a 25-point indoor set.
5. **No full-screen output.** The only way to put the score on a gym TV
   today is the spectator page, which is a phone-first read-only page
   with browser chrome, not a display board.
6. **No analytical surface during play.** The match report covers the
   match *after* it ends; nothing shows evolution *while* it is running.

---

## How to read each proposal

Every entry uses the same fields:

- **Pitch / For** — one line, and who it is aimed at.
- **Wireframe** — schematic, not to scale.
- **Bindings** — exact paths in the WebSocket payload
  (`build_overlay_payload` in `app/overlay_payload.py`).
- **DOM contract** — which ids from `app.js` the template ships, and
  which new ones it needs. Reusing an existing id means the render is
  free; a new id means a change to `app.js` or a new script.
- **Adds** — the files the change creates.
- **Effort** — **S** ≈ template + CSS only, no JS change. **M** ≈ plus a
  small addition to `app.js`. **L** ≈ new render module and/or backend or
  catalogue changes.

The DOM ids `app.js` already fills, for reference: `home-name`,
`away-name`, `home-points`, `away-points`, `home-sets`, `away-sets`,
`home-serving`, `away-serving`, `home-logo`, `away-logo`,
`home-timeouts`/`away-timeouts` (`.timeout-dot` children),
`home-history`/`away-history`, `home-set-pips`/`away-set-pips`
(`renderSetPips`), `home-set-progress`/`away-set-progress` (each holding
one `<i>` fill, `renderSetProgress`), `current-set-label`,
`ticker-container`/`ticker-message`, `player-stats-container`/
`player-stats-data`, and the `scoreboard-container` root.

---

# Part 1 — Stream overlays

Transparent, composited over the match feed, selectable in the operator's
Overlay Style picker, honouring operator geometry (position, size, scale,
margin) exactly like the current 27.

## 1. `momentum` — Momentum Rail

**Pitch:** a lower-third scorebug whose spine is a live momentum bar, so a
viewer who joins mid-set can see who is on a run.
**For:** club and league streams that want one broadcast-grade insight
without a stats panel.

```
        ┌────────────────────────────────────────────────────────┐
        │  ▌ HOME            2 │ 18        16 │ 1            AWAY │
        │  ▌ ●●                │                        ○○      ▐ │
        ├──────────────────────┴───────────────────────────────  ┤
        │ ████████████████████████████▉·············             │  ← momentum
        │            ▲ run 6                        SET 3        │
        └────────────────────────────────────────────────────────┘
```

A single 6 px rail runs the full width under the two team blocks. Its
split point is a smoothed function of the last N points: dead level at
the start of a set, sliding toward the team that is scoring. A small
caption on the leading side reads the current run (`run 4`) and fades out
when the run ends. Points, sets, serve and timeouts read as a
conventional bar above it, so the style degrades gracefully to "a normal
scorebug" when the match is even.

- **Bindings:** `overlay_control.stats.current_streak` (team + length),
  `overlay_control.points_history` (last 30 events, each
  `{team, set, ts, score:[t1,t2], action}`) for the smoothing window,
  `overlay_control.stats.longest_streak` for the rail's scale cap.
- **DOM contract:** all standard ids, plus `#momentum-rail` (with an `<i>`
  fill, mirroring the `renderSetProgress` convention) and
  `#momentum-caption`. Needs a `renderMomentum(state)` in `app.js`
  alongside `renderSetPips`/`renderSetProgress` — ~40 lines, called from
  both the full-render and diff paths.
- **Motion:** GSAP tween on the fill width, 400 ms `power2.out`. The
  caption fades in at run ≥ 3 and out when the other team scores.
- **Adds:** `overlay_templates/momentum.html`,
  `overlay_static/css/momentum.css`, `renderMomentum` in `app.js`.
- **Effort:** **M**.
- **Risks:** the smoothing function is the whole design — too twitchy and
  it distracts, too damped and it never moves. Suggested start: fill % =
  50 + 50 × (weighted point differential over the last 8 points), weights
  linearly decaying, clamped to ±40 % so it never fully bottoms out.
  Reintroduces derived stats to the live overlay, which the project
  previously pulled back from; worth an explicit decision before build.

## 2. `courtmap` — Court Map

**Pitch:** a compact scorebug with a top-down half-court diagram showing
who is on which side, who serves, and (beach) how far to the next switch.
**For:** streams where the camera moves or flips, and for beach, where
sides change every 7 points and viewers lose track.

```
   ┌───────────────────────────────────────────┐
   │  HOME  ●●        18 │ 16        ○○   AWAY │
   │  2 sets                              1 set│
   ├───────────────────────────────────────────┤
   │      ┌───────────┬───────────┐            │
   │      │▓▓▓▓▓▓▓▓▓▓▓│           │  switch in │
   │      │▓▓▓ HOME ▓▓│   AWAY    │     3      │
   │      │▓▓▓▓▓▓▓▓▓▓▓│           │            │
   │      └───────────┴───────────┘            │
   │             ▲ serving                     │
   └───────────────────────────────────────────┘
```

The court is a 2:1 rectangle split by a net line, each half tinted with
that team's primary colour, the serving half carrying a pulsing serve
marker behind the baseline. The whole diagram mirrors when
`match_info.sides_swapped` flips — which is free, because `app.js`
already swaps the two team objects before rendering, so "home" is always
the left half. The switch counter only renders in beach mode.

- **Bindings:** `match_info.sides_swapped`, `match_info.mode`,
  `team_*.serving`, `overlay_control.beach_side_switch`
  (`{interval, points_in_set, next_switch_at, points_until_switch,
  is_switch_pending}`, `null` outside beach).
- **DOM contract:** standard ids plus `#court-diagram` (inline SVG, tinted
  by the existing `--home-primary` / `--away-primary` variables — no JS),
  `#court-serve-marker` (toggled by a class the serve render already
  drives), `#switch-countdown`. The countdown needs ~15 lines in `app.js`
  to write `points_until_switch` and toggle `is_switch_pending`.
- **Motion:** on a swap, the existing card-flip transition already fires;
  the diagram inherits it. `is_switch_pending` pulses the countdown chip.
- **Adds:** `overlay_templates/courtmap.html`,
  `overlay_static/css/courtmap.css`, small `app.js` addition.
- **Effort:** **M**.
- **Risks:** the diagram must stay legible at the smallest operator scale;
  keep it to two tinted rectangles and one marker, no player dots.

## 3. `banner` — Broadcast Band

**Pitch:** an edge-to-edge band across the top or bottom of the frame, the
way a TV channel runs its score bar — no floating card, no rounded corners.
**For:** productions that want the graphic to read as part of the channel,
and for streams whose composition leaves the frame edges free.

```
┌──────────────────────────────────────────────────────────────────────────┐
│ SUPERLIGA │ ▌HOME  2 │  18  ─  16  │ 1  AWAY▐ │ 25-22 25-19 21-25 │ SET 4│
└──────────────────────────────────────────────────────────────────────────┘
 ▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔                       ← progress
```

Full canvas width, ~84 px tall, four zones: competition/phase on the far
left, the scoreline centred, set history as chips on the right, the set
label at the far edge. A 3 px hairline along the outermost edge is the
two teams' set-progress bars growing toward each other from the corners.
The ticker, when enabled, renders *inside* the band as a second line
rather than as a separate strip.

- **Bindings:** `match_info.tournament`, `match_info.phase`, the standard
  team fields, `team_*.set_history`,
  `match_info.points_limit`/`points_limit_last_set` via the existing
  `renderSetProgress`.
- **DOM contract:** entirely existing ids. `#scoreboard-container` carries
  `data-fixed-geometry` (opting out of x/y/scale, exactly like `pylons`)
  and `data-vertical-anchor` (top/bottom, already applied by
  `applyVerticalAnchor`). Note `applyScoreboardVisibility` looks for
  `.pylon-home`/`.pylon-away` children on fixed-geometry containers — the
  band should either ship those class names on its two halves or the
  visibility branch needs a "single full-width panel" case (slide the band
  off its own edge).
- **Motion:** slides up/down off its anchored edge on hide, rather than
  sideways.
- **Adds:** `overlay_templates/banner.html`,
  `overlay_static/css/banner.css`, one branch in
  `applyScoreboardVisibility`.
- **Effort:** **S–M**.
- **Risks:** competition/phase are currently hard-coded strings in
  `build_overlay_payload` (`"Superliga Masculina"` / `"Playoffs"`) — this
  is the first style that would surface them prominently, so they should
  become operator-editable first, or the zone should fall back to the
  team-vs-team title.

## 4. `portrait` — Portrait Bug

**Pitch:** a scorebug designed on a 1080×1920 canvas for vertical video,
instead of a landscape bug shrunk into a corner.
**For:** phone-shot club streams, Shorts/Reels/TikTok verticals, and the
increasingly common vertical second output.

```
   ┌─────────────────┐
   │   (safe area)   │
   ├─────────────────┤
   │ ▌ HOME      ●●  │
   │ ▌  2        18  │
   │─────────────────│
   │ ▌ AWAY      ○○  │
   │ ▌  1        16  │
   │  ▔▔▔▔▔▔▔▔▔▔     │
   │  SET 3  25-22   │
   ├─────────────────┤
   │                 │
   │     (video)     │
   │                 │
```

Two full-width rows docked under the platform's top safe area (roughly
the first 12 % of the frame is reserved by UI chrome on every vertical
platform), stacked name-left / score-right with numerals large enough to
survive a 6-inch screen. Set history collapses to the current set plus
the previous set's final score. Everything sits inside a configurable
safe inset so platform UI never covers it.

- **Bindings:** standard. Nothing new.
- **DOM contract:** all existing ids.
- **The real work is the canvas.** Every stylesheet today hard-codes
  `body { width: 1920px; height: 1080px }` and `app.js` anchors against
  `CANVAS_W`/`CANVAS_H` constants. This style needs the canvas to be
  either declared per style or driven by a URL parameter
  (`?canvas=1080x1920`), with `applyGeometry` reading it instead of the
  module constants. That is a small, contained change — the constants are
  used in exactly one function — but it is a change to shared code and
  should be reviewed as such. Interim option: ship the style with
  `data-fixed-geometry` and a pure-CSS `100vw`/`100dvh` layout, sidestepping
  `applyGeometry` entirely; the operator loses x/y nudging on this style
  only.
- **Adds:** `overlay_templates/portrait.html`,
  `overlay_static/css/portrait.css`, optional canvas parameter in `app.js`.
- **Effort:** **M** (CSS-only route) / **L** (parameterised canvas).
- **Risks:** the mosaic preview grid and the SPA preview card both assume
  a landscape canvas; a portrait style will look wrong in both unless they
  read the same canvas hint.

## 5. `flip` — Split-Flap

**Pitch:** mechanical split-flap digits — each point physically flips over,
the way a departure board or a flip clock does.
**For:** retro/analog-warm productions, and as the animation-led
counterpart to `led` (dot-matrix) and `neon` (glow).

```
   ┌──────────────────────────────────────┐
   │  HOME              ┌──┐┌──┐          │
   │  ●●   2   sets     │1▄││8▄│          │
   │                    └──┘└──┘          │
   ├──────────────────────────────────────┤
   │  AWAY              ┌──┐┌──┐          │
   │  ○○   1   sets     │1▄││6▄│          │
   │                    └──┘└──┘          │
   └──────────────────────────────────────┘
```

Each digit is a two-halves card with a hairline seam; a score change flips
the top half down over the new digit with a short, sharp ease and a
1-frame shadow. Warm off-white cards on a charcoal cabinet, or the
inverse under the dark theme. Set counters flip too, but slower.

- **Bindings:** standard.
- **DOM contract:** the digits are the catch. `app.js` writes
  `#home-points` as text and runs its own `animatePoints` cross-fade; a
  split-flap needs per-digit elements. Two options: (a) a
  `data-digit-flip` opt-in attribute that makes `animatePoints` delegate to
  a small flip renderer, or (b) pure CSS — keep the single text node,
  give it a 3D `rotateX` keyframe on change, and accept "the whole number
  flips" instead of per-digit. Option (b) is markedly cheaper and reads
  nearly as well at stream sizes; recommend starting there.
- **Adds:** `overlay_templates/flip.html`, `overlay_static/css/flip.css`
  (+ optional `animatePoints` branch).
- **Effort:** **S** (option b) / **M** (option a).
- **Risks:** 3D transforms plus GSAP's existing opacity tween can fight
  each other; the flip must be driven from the same code path that owns
  the number, not layered on top.

## 6. `rally` — Table-Tennis Bug

**Pitch:** the first style built for the table-tennis preset: 11-point
scale, up to best-of-7 games, and the serve-rotation countdown the backend
already computes.
**For:** the table-tennis mode, which today borrows layouts designed for a
25-point indoor set.

```
   ┌────────────────────────────────────────────┐
   │  ▌ PLAYER A   ● ● ● ○ ○ ○ ○      8         │
   │  ▌                                         │
   │  ▌ PLAYER B   ● ● ○ ○ ○ ○ ○     10   ⟲2    │
   └────────────────────────────────────────────┘
                                        ▲ serve changes in 2
```

Game pips scale to `best_of_sets` (up to 7, so pips not numerals), points
sized for two digits rather than three, and a serve chip that shows both
who serves and how many points until the serve rotates — pulsing when
`is_change_pending` fires. At deuce the chip switches to "every point".

- **Bindings:** `match_info.best_of_sets`, `match_info.points_limit`,
  standard team fields, and the serve-rotation countdown
  `{server, points_in_set, next_change_at, points_until_change,
  is_change_pending}`.
- **Needs a small backend change.** `compute_serve_switch`
  (`app/api/match_rules.py`) already produces that countdown, but it is
  wired only into the SPA control-state response
  (`app/api/game_state_presenter.py` → `ServeSwitch` in `schemas.py`), not
  into the overlay broadcast — so no overlay style can render it today.
  Its beach counterpart *is* wired in: `_add_rule_indicators` in
  `app/overlay_payload.py` attaches `control["beach_side_switch"]`. Adding
  `control["serve_switch"]` beside it, from the same rule context, is a
  handful of lines and follows an existing pattern.
- **DOM contract:** standard ids plus `#serve-switch-chip`; the countdown
  rendering is the same ~15-line `app.js` addition `courtmap` needs, so
  build the two together.
- **Adds:** `overlay_templates/rally.html`,
  `overlay_static/css/rally.css`, shared `app.js` addition,
  `serve_switch` in `_add_rule_indicators`.
- **Effort:** **M**.
- **Risks:** the payload addition is the only non-cosmetic part, and it is
  additive (a `null` field outside table tennis, exactly like
  `beach_side_switch`). Worth confirming with a table-tennis operator
  whether pips or numerals read better at best-of-7.

---

# Part 2 — Full-screen dashboards

A new family. These are **not** composited over video: they paint an
opaque background, fill the display edge to edge, and are meant to be the
only thing on the screen. Four target surfaces:

| Surface | Typical hardware | Design constraint |
| --- | --- | --- |
| Venue board | Gym TV, projector, LED wall | Read at 15–30 m; nothing below ~40 px |
| Analyst screen | Laptop / second monitor at a desk | Density is the point |
| Storyboard | Lobby screen, between-sets stream scene | Reads as a narrative, updates slowly |
| Bench kiosk | 10-inch tablet, often portrait | Glanceable in 2 seconds, no interaction |

## The dashboard platform

Shared work, needed once, before or alongside the first dashboard.

**1. Keep them out of the OBS style picker.** An operator who picks
`analyst` from the Overlay Style dropdown would get an opaque page
covering their entire match feed. `StyleCatalog` already has exactly the
right mechanism: `_META_STYLES` (currently `{"mosaic"}`) marks a template
as *renderable via `?style=`* but *hidden from the picker*, and
`serve_overlay` validates the parameter against the renderable superset.
Add a `_FULLSCREEN_STYLES` set the same way — dashboards stay reachable by
URL, invisible in the dropdown, zero risk to existing operators.

**2. Surface them where the spectator link lives.** `LinksDialog.tsx`
already lists control / overlay / preview / spectator / report links
built by `build_overlay_links`. Dashboards belong there, as a "Display
boards" group of copyable `…/overlay/{public_token}?style=arena` URLs —
the same public-token capability model, no new auth surface.

**3. A dashboard base template.** `base.html` hard-wires `app.js`,
the ticker and the player-stats block, all of which are stream-overlay
furniture. Add `overlay_templates/_dashboard_base.html` (underscore =
private, never selectable — the same convention `_spectator.html` uses)
that loads `i18n_labels.js` and a new
`overlay_static/js/dashboard.js`, and skips the ticker/GSAP baggage.
Each dashboard then extends it, exactly as the stream styles extend
`base.html`.

**4. One render module, four layouts.** `dashboard.js` should follow the
shape `set_summary.js` already proved: one WebSocket subscription, one
view-model builder, and a `render<Layout>(stage, vm)` per style selected
by `window.OVERLAY_STYLE`. Roughly 60 % of the view-model
(per-set series, stat rows, service rates, streaks) is already written
twice — in `spectator.js` and `set_summary.js`. **Extract that into a
shared `overlay_static/js/match_view_model.js` first** and have all three
consume it; otherwise this is the third copy and the one that makes the
drift permanent.

**5. Sizing.** Do not copy `body { width: 1920px; height: 1080px }`.
Dashboards target unknown displays, from a 10-inch tablet to a 4K wall.
Use `100vw`/`100dvh`, a `vmin`-derived type scale
(`--u: clamp(8px, 1.1vmin, 22px)`) and container queries for the panels.
Portrait must not break: `bench` is portrait-first, and the others should
reflow to a single column below ~900 px wide.

**6. Geometry.** Ship `data-fixed-geometry` so `updateGeometry` skips
them. Deliberately **keep** `updateOutputTransform`: its `scale` and
`margin` knobs are the existing, working answer to TV overscan, which is a
real problem on exactly this hardware.

**7. Theme.** Dashboards are opaque, so light/dark is a genuine choice
rather than a tint. Support both through the established
`body.overlay-theme-dark` / `overlay-theme-light` classes so
`get_style_capabilities` reports `theme: true` for them, and default to
dark (a bright wall of white in a dim gym is unkind).

**8. Data gap to close.** `points_by_set` is capped at 60 events per set
(`_points_by_set(events, per_set_limit=60)`). A 25-point set typically
runs 45–50 rallies, but an extended deuce passes 60 and the tail is
silently dropped — the `journey` timeline would draw a match that stops
mid-set. Either raise the cap for this consumer or add a downsampled
full-match series to the payload. Also note `points_history` is only the
last 30 events; it is not a match-wide series.

**9. Tests and docs to update.** `tests/test_style_capabilities.py`
(new capability flag), `tests/test_docs_consistency.py` (the selectable-
style count in `README.md`, `AGENTS.md` and `FRONTEND_DEVELOPMENT.md`,
plus the `Available styles:` list — meta-styles are excluded from that
count, so hidden dashboards leave it unchanged), a CHANGELOG entry, and
`scripts/screenshots` for any operator-facing surface that changes.

## 7. `arena` — Arena Board

**Pitch:** the score, readable from the back row of the gym, with just
enough evolution to reward a longer look.
**For:** a TV or projector in the venue; the simplest of the four and the
one most likely to run unattended for hours.

```
┌──────────────────────────────────────────────────────────────────────┐
│  SUPERLIGA MASCULINA · PLAYOFFS — FINAL              SET 3   41:07   │
├───────────────────────────────────┬──────────────────────────────────┤
│                                   │                                  │
│   ⬤ HOME TEAM              ●●     │        AWAY TEAM ○○              │
│                                   │                                  │
│         18                        │              16                  │
│                                   │                                  │
│   ████████████████░░░░░░░  /25    │   ██████████████░░░░░░░░  /25    │
├───────────────────────────────────┴──────────────────────────────────┤
│  SETS   2 — 1        25-22 │ 19-25 │ 25-21 │  ·  │  ·                │
├──────────────────────────────────────────────────────────────────────┤
│  ▁▂▃▅▆▇▆▅▃▂▁▂▄▆▇█▇▆▄▂▁  run: HOME 6        serve ⬤ HOME              │
└──────────────────────────────────────────────────────────────────────┘
```

Four bands: a header with competition, current set and the running match
clock; the score itself taking the middle 55 % of the height at roughly
`22vmin` numerals; a set-history ribbon; and a single-line footer with a
sparkline of the current set's point differential, the active run, and
the serving team. Nothing else. Timeouts are pips beside the team name;
the serving team's half carries a soft team-colour wash.

- **Bindings:** all standard team/match fields, `team_*.set_history`,
  `match_info.match_started_at` + `server_time` for the clock,
  `overlay_control.points_by_set[current_set]` for the sparkline,
  `overlay_control.stats.current_streak`.
- **Layout:** CSS grid, four rows (`auto 1fr auto auto`), the score band
  split by a centre rule. Type scale from `vmin` so a 4 K wall and a
  1080p projector both fill correctly.
- **Adds:** `overlay_templates/arena.html`,
  `overlay_static/css/arena.css`, `renderArena` in `dashboard.js`.
- **Effort:** **M** once the platform exists.
- **Risks:** burn-in on always-on venue panels — shift the whole grid by a
  few pixels every few minutes, or dim the chrome between rallies.

## 8. `analyst` — Analyst Dashboard

**Pitch:** everything the backend already computes, on one screen, updated
live — the match report's analytics without waiting for the match to end.
**For:** a coach's laptop, a second monitor beside the stream, a statistician.

```
┌───────────────────────────────────────────────────────────────────────────┐
│ HOME TEAM  2      18 ─ 16      1  AWAY TEAM     SET 3 · 41:07 · ⬤ HOME    │
├─────────────────────────────────────────────┬─────────────────────────────┤
│  SET 3 PROGRESSION                          │  POINT TYPES (set 3)        │
│  25┤                                  ╭──   │   attack  ████████ 9 │ 7    │
│    │                         ╭────────╯     │   block   ███ 3      │ 5    │
│    │              ╭──────────╯   ╭───       │   ace     ██ 2       │ 1    │
│    │      ╭───────╯      ╭───────╯          │   opp err ████ 4     │ 3    │
│   0┼──┴───┴──────┴───────┴─────────────     ├─────────────────────────────┤
│      ▲T          ▲T                         │  SERVICE TURNS HELD         │
│      home ──   away ──   ▲ timeout          │   HOME  62 % (13/21)        │
├─────────────────────────────────────────────┤   AWAY  48 % (10/21)        │
│  SET     1      2      3      4      5      ├─────────────────────────────┤
│  HOME   25     19     18      ·      ·      │  RUNS                       │
│  AWAY   22     25     16      ·      ·      │   current   HOME 6          │
│  TIME  28:4   31:2   12:1     ·      ·      │   longest   HOME 6 / AWAY 4 │
├─────────────────────────────────────────────┤   comeback  HOME −5 → +2    │
│  LAST 12 POINTS  ○○○●○○●●●●●●               │                             │
└─────────────────────────────────────────────┴─────────────────────────────┘
```

A 12-column grid. The progression chart is the spectator page's SVG chart
promoted to a hero panel — same shape, larger, with timeout markers on the
time axis and the set navigable (auto-follows the live set, arrows to look
back). Right rail: point-type breakdown scoped to the displayed set,
service hold, run/comeback figures. Bottom left: per-set score and
duration table, then a last-N-points rail where each dot is a rally,
coloured by winner and shaded by point type.

- **Bindings:** `overlay_control.points_by_set` (chart),
  `overlay_control.timeouts_by_set` (markers),
  `overlay_control.stats.point_types_by_set`,
  `stats.services` / `services_by_set`, `stats.current_streak`,
  `stats.longest_streak_by_set`, `stats.partial_comeback` /
  `set_win_comeback`, `stats.set_durations`,
  `overlay_control.points_history` (last-12 rail),
  `stats.last_point` (`{team, set, point_type, error_type}`).
- **Reuse:** the chart path builder, the nine stat rows and their i18n keys
  all exist in `spectator.js`; this panel set is a re-layout of that page,
  not new computation. Every label already has translations in
  `i18n_labels.js` for the six supported locales.
- **Adds:** `overlay_templates/analyst.html`,
  `overlay_static/css/analyst.css`, `renderAnalyst` in `dashboard.js`.
- **Effort:** **L** — the largest of the four, and the one that most needs
  the shared view-model extracted first.
- **Risks:** density. The temptation is to show all nine stat rows plus
  everything else; the wireframe above deliberately drops the rows that
  duplicate the chart. Also: point-type data only exists when the operator
  tags points, so every tagged panel needs a designed empty state, not a
  row of dashes.

## 9. `journey` — Match Journey

**Pitch:** the whole match as one continuous timeline — every point, every
timeout, every set boundary, runs called out as bands.
**For:** a lobby screen, a between-sets full-screen stream scene, or the
end-of-match "how we got here" shot. Slower, more narrative, less dense
than `analyst`.

```
┌────────────────────────────────────────────────────────────────────────────┐
│  HOME TEAM  ───────────────  2 : 1  ─────────────── AWAY TEAM              │
├────────────────────────────────────────────────────────────────────────────┤
│ +10                                                                        │
│      ╭─╮      ╭──╮                    ╭───────╮                            │
│  ╭───╯ ╰──────╯  ╰──╮   ╭─╮      ╭────╯       ╰───╮                        │
│ ─┼─────────────────────╳───╰──────╯─────────────────╲──────────────────    │
│  │                  ╰─╯    ╰──╮ ╭─╯                  ╰────╮                │
│ −10                           ╰─╯                         ╰──              │
│  ├──── SET 1 ────┤├──── SET 2 ────┤├──── SET 3 ────┤├── SET 4 (live) ──    │
│    ▲T      ▲T        ▲T   ▲T          ▲T                ▲T                 │
│    ▒▒▒▒ run 6                    ▒▒▒▒▒ run 5                               │
├──────────────┬──────────────┬──────────────┬──────────────┬────────────────┤
│  SET 1       │  SET 2       │  SET 3       │  SET 4       │  MATCH         │
│  25 — 22 ✓   │  19 — 25     │  25 — 21 ✓   │  18 — 16 ●   │  87 — 84       │
│  28:41       │  31:12       │  26:03       │  12:18       │  1:38:14       │
└──────────────┴──────────────┴──────────────┴──────────────┴────────────────┘
```

One horizontal axis spanning the entire match, plotting the running point
**differential** rather than raw score — so the line crossing zero is the
lead changing, and the shape of the match is legible at a glance. Set
boundaries are vertical rules, timeouts are ticks on the axis, runs of 4+
are shaded bands. Below, one card per set with the final score, winner
tick and duration; the live set pulses. On match end, the last card flips
to a result summary.

- **Bindings:** `overlay_control.points_by_set` (all sets, concatenated —
  **this is the consumer that needs the 60-event cap raised**),
  `overlay_control.timeouts_by_set`,
  `overlay_control.stats.set_durations`, `stats.longest_streak_by_set`,
  `team_*.set_history`, `match_info.match_finished`.
- **Layout:** a single responsive SVG (full width, ~55 % height) plus a
  flex row of set cards. The x-axis is rally index, not wall-clock, so
  timeouts and long deuces do not distort the shape; wall-clock is
  available in each event's `ts` if a time axis is preferred.
- **Adds:** `overlay_templates/journey.html`,
  `overlay_static/css/journey.css`, `renderJourney` in `dashboard.js`,
  plus the payload change in item 8 of the platform section.
- **Effort:** **L** (**M** for the view alone, if the cap is lifted first).
- **Risks:** a five-set match is ~200 rallies across a 1920 px axis — about
  9 px per point, enough. A tablet is not: below ~1200 px the timeline
  should collapse to the current set plus thumbnails of the completed ones.

## 10. `bench` — Bench Kiosk

**Pitch:** the tactical state a coach actually checks between rallies,
sized for a tablet propped on the bench, portrait-first.
**For:** the bench, the scorer's table, a warm-up-area screen.

```
        ┌──────────────────────────┐
        │  SET 3          41:07    │
        ├──────────────────────────┤
        │   HOME             18    │
        │   ⬤ serving      ●● T/O  │
        ├──────────────────────────┤
        │   AWAY             16    │
        │                  ○○ T/O  │
        ├──────────────────────────┤
        │  RUN                     │
        │  HOME ██████ 6           │
        ├──────────────────────────┤
        │  SERVICE TURNS HELD      │
        │  HOME 62 %   AWAY 48 %   │
        ├──────────────────────────┤
        │  SWITCH IN  3   (beach)  │
        ├──────────────────────────┤
        │  LAST 8   ○○●●●●●●       │
        ├──────────────────────────┤
        │  25-22 │ 19-25 │ 25-21   │
        └──────────────────────────┘
```

A single scrolling column of fixed-height cards, each one fact, ordered by
how often it is checked. Two-second glanceability is the whole brief: no
charts, no axes, no legends. High contrast for a sunlit outdoor bench;
touch targets are irrelevant because nothing is interactive. Rotates to
landscape as a 2-column grid.

- **Bindings:** standard team fields, `stats.current_streak`,
  `stats.services`, `overlay_control.beach_side_switch` (or
  `serve_switch` in table tennis), `overlay_control.points_history`,
  `team_*.set_history`, `team_*.timeouts_taken`.
- **Layout:** `dvh`-based column (`100dvh` handles mobile browser chrome),
  cards at `minmax(11dvh, auto)`. This is the one dashboard that must be
  correct on a phone as well as a tablet.
- **Adds:** `overlay_templates/bench.html`,
  `overlay_static/css/bench.css`, `renderBench` in `dashboard.js`.
- **Effort:** **M**.
- **Risks:** overlaps the spectator page's audience. The distinction to
  hold: the spectator page answers *what is the score*; `bench` answers
  *what is happening right now*. If that line blurs during design, drop
  this and add a "coach mode" toggle to the spectator page instead — it
  would be less work and less surface.

---

## Data the payload already carries

Every binding above resolves against the existing broadcast payload
(`build_overlay_payload`, `app/overlay_payload.py`; live stats from
`compute_live_stats`, `app/api/live_stats.py`). **Two proposals need a
payload change:** `journey` (lift a cap) and `rally` (attach an
already-computed field). Everything else binds to what is broadcast today.

| Path | Shape | Used by |
| --- | --- | --- |
| `match_info.current_set` / `best_of_sets` | int | all |
| `match_info.points_limit` / `points_limit_last_set` | int | progress bars, `rally` |
| `match_info.mode` | `indoor` \| `beach` \| `table_tennis` | `courtmap`, `rally`, `bench` |
| `match_info.sides_swapped` | bool | `courtmap` |
| `match_info.match_started_at` / `server_time` / `match_finished` | float / bool | clocks, `journey` |
| `team_*.{name, short_name, colors, logo_url, points, sets_won, serving, timeouts_taken, set_history}` | — | all |
| `overlay_control.beach_side_switch` | `{interval, points_in_set, next_switch_at, points_until_switch, is_switch_pending}` \| null | `courtmap`, `bench` |
| `overlay_control.serve_switch` | `{server, points_in_set, next_change_at, points_until_change, is_change_pending}` \| null — **not in the overlay payload yet**, see proposal 6 | `rally` |
| `overlay_control.match_point_info` | set/match-point flags | `arena`, `bench` |
| `overlay_control.points_history` | last 30 `{team, set, ts, score, action}` | `momentum`, `analyst`, `bench` |
| `overlay_control.points_by_set` | `{set: [event, …]}`, **60/set cap** | `arena`, `analyst`, `journey` |
| `overlay_control.timeouts_by_set` | `{set: [{…, ts}]}` | `analyst`, `journey` |
| `overlay_control.stats.current_streak` / `longest_streak` / `longest_streak_by_set` | — | `momentum`, `arena`, `analyst`, `bench` |
| `overlay_control.stats.services` / `services_by_set` | won/total per team | `analyst`, `bench` |
| `overlay_control.stats.point_types` / `point_types_by_set` / `error_types` | tallies per team | `analyst` |
| `overlay_control.stats.partial_comeback` / `set_win_comeback` | int | `analyst` |
| `overlay_control.stats.set_durations` | `{set: seconds}` | `analyst`, `journey` |
| `overlay_control.stats.last_point` | `{team, set, point_type, error_type}` \| null | `analyst`, `bench` |

Note that `_REPLACE_SUBTREES` in `app/overlay/state_store.py` already
force-replaces the per-set buckets on every broadcast, so a reset clears
them properly — dashboards inherit that correctness for free.

---

## Effort and suggested phasing

| # | Style | Family | Effort | Depends on |
| --- | --- | --- | --- | --- |
| 5 | `flip` | stream | S | — |
| 3 | `banner` | stream | S–M | visibility branch for full-width fixed geometry |
| 1 | `momentum` | stream | M | `renderMomentum` in `app.js`; product decision on live stats |
| 2 | `courtmap` | stream | M | shared switch-countdown helper |
| 6 | `rally` | stream | M | same helper as `courtmap`; `serve_switch` in the overlay payload |
| 4 | `portrait` | stream | M / L | canvas assumption (CSS-only route avoids it) |
| — | *dashboard platform* | — | M | catalogue flag, `_dashboard_base.html`, shared view-model |
| 7 | `arena` | dashboard | M | platform |
| 10 | `bench` | dashboard | M | platform |
| 9 | `journey` | dashboard | L | platform + `points_by_set` cap |
| 8 | `analyst` | dashboard | L | platform + shared view-model |

A sensible order:

1. **`flip` and `banner`** — cheap, self-contained, and they exercise
   nothing shared. Good first merges to settle review conventions.
2. **`courtmap` + `rally`** together — they share one `app.js` helper, and
   `rally` closes the table-tennis gap.
3. **`momentum`** — needs the product call on live stats on the overlay
   first, so it should not block the others.
4. **Extract the shared view-model** out of `spectator.js` /
   `set_summary.js`. Nothing new ships in this step, which is exactly why
   it will be tempting to skip; skipping it makes `analyst` a third copy.
5. **Dashboard platform + `arena`** — `arena` is the simplest dashboard
   and validates the platform under real venue conditions.
6. **`bench`**, then **`journey`** (with the payload cap fix), then
   **`analyst`**.
7. **`portrait`** whenever the canvas question is answered.

## Open questions

1. **Live stats on the live overlay.** `momentum` reintroduces derived
   data to a surface the project deliberately reduced to "scoreboard
   only". One bar is not a stats panel, but it is a reversal of direction
   and should be decided explicitly, not inside a design review.
2. **Do dashboards belong in the style picker at all?** The proposal hides
   them (meta-style route) and surfaces them in the links dialog. The
   alternative — showing them in the picker with a "full screen" badge —
   is more discoverable and strictly more dangerous.
3. **Competition and phase strings** are hard-coded in
   `build_overlay_payload`. `banner`, `arena` and `journey` all want them.
   Making them operator-editable is a small, independently useful change
   that should probably land before those three.
4. **`bench` vs. a spectator "coach mode"** — see the risk note under
   proposal 10. Worth resolving before either is built.
5. **Screenshots.** `mosaic` renders every *selectable* style in a grid for
   the README. Hidden dashboards will not appear there, so they need their
   own capture path in `scripts/screenshots` if they are to be documented
   visually.
