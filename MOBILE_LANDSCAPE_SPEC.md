# Mobile Landscape UX Specification

**Project:** Volley Overlay Control
**Scope:** Optimized experience for phones held in landscape orientation
**Status:** Draft

---

## 1. Context and Goals

The application already ships as a PWA and detects orientation via `GUI.is_portrait()`. However, the landscape layout currently has several friction points when operated from a phone during a live match:

- Score buttons are sized relative to `page_width / 4.5`, which produces buttons that are too small on a 375 pt-wide phone screen.
- The center panel (sets history, set selector, live preview) takes horizontal space that crowds the scoring buttons.
- The undo mode is a separate toggle that requires two actions (enable undo, then tap score button).
- The options/customization dialogs use desktop-oriented forms that are difficult to interact with one-handed.
- There is no visual lock to prevent accidental taps while a phone is being passed to a co-scorer.

The goal of this specification is to define a layout, interaction model, and configuration surface that makes the app **fully operable with one thumb in landscape mode on a phone-sized screen (≥ 360 × 640 dp)** without degrading the experience on tablets or desktop browsers.

---

## 2. Target Screen Classes

| Class | Width (dp) | Height (dp) | Typical Device |
|---|---|---|---|
| Phone landscape (small) | 568 – 667 | 320 – 375 | iPhone SE, Galaxy A series |
| Phone landscape (standard) | 667 – 844 | 375 – 390 | iPhone 14/15, Pixel 7 |
| Phone landscape (large) | 844 – 932 | 390 – 430 | iPhone 14/15 Plus/Pro Max |
| Tablet landscape | 1024 + | 768 + | iPad, Galaxy Tab |
| Desktop | 1280 + | 800 + | browser window |

All layout decisions in this document target **phone landscape** as the primary class. Tablet and desktop layouts must continue to work as today with no regressions.

---

## 3. Orientation Detection

**Current rule** (in `gui.py:23`):
```python
return height > 1.2 * width and not width > 800
```

This correctly identifies portrait for narrow phones but should be updated to explicitly handle the phone-landscape class:

```
is_phone_landscape = width <= 932 and height <= 430
is_portrait         = height > 1.2 * width and width <= 800
```

Devices wider than 932 dp (tablets, desktops) use the existing landscape layout unchanged.

Hysteresis thresholds remain at 1.1 (exit portrait) / 1.3 (enter portrait) as today.

---

## 4. Layout: Phone Landscape Mode

### 4.1 Grid Structure

Use a single-row, three-column layout that fills 100 vw × 100 vh with no scrolling.

```
┌──────────────┬──────────────────┬──────────────┐
│              │                  │              │
│   TEAM A     │   CENTER STRIP   │   TEAM B     │
│   COLUMN     │                  │   COLUMN     │
│  (38% width) │   (24% width)    │  (38% width) │
│              │                  │              │
└──────────────┴──────────────────┴──────────────┘
```

Team columns each receive **38% of the viewport width**. The center strip receives **24%**. This allocation ensures the score buttons remain large enough to be tapped reliably while giving the center panel enough room to display set history legibly.

### 4.2 Team Column

Each team column is a flex column with three rows:

```
┌────────────────────┐
│  SCORE BUTTON      │  ← fills ~65% of column height
│  (tap = +1 point)  │
├────────────────────┤
│  SET BADGE  SERVE  │  ← ~20% height
├────────────────────┤
│  TIMEOUT DOTS      │  ← ~15% height
└────────────────────┘
```

**Score button sizing:**
- Width: 100% of column (≈ 38 vw)
- Height: `min(65vh, 38vw)` so it remains square-ish on very wide screens
- Font size: `button_height * 0.45`

At 667 × 375 dp (standard phone landscape) this produces a score button of approximately 253 × 244 dp, meeting the 48 dp minimum touch target by a large margin.

**Score button interaction (unchanged from current behavior):**
- Single tap → +1 point for that team (or −1 in undo mode)
- Double-tap within 350 ms → undo last point for that team
- Long press (≥ 1 000 ms) → open custom value input dialog
- Haptic feedback on every tap (existing implementation)

### 4.3 Center Strip

The center strip renders vertically from top to bottom:

1. **Set badges row** — two small circular badges (one per team) showing sets won. Tap a badge to increment/decrement sets directly. Height: `~22% of viewport height`.
2. **Per-set scores table** — compact grid showing scores for each completed set. Condensed to `text-xs`. Height: `~40% of viewport height`. Scrollable vertically if more than 5 sets are configured.
3. **Set selector** — a compact pagination row (← N →) to navigate between active sets. Height: `~18% of viewport height`.
4. **Match status indicator** — a small text label ("Set 3 · 21 pts") or "Match finished" banner. Height: `~20% of viewport height`.

The live preview iframe is **not shown** in phone landscape mode (it would be too small to be useful). Toggling preview is still available from the options dialog.

### 4.4 Control Bar

The existing control buttons (undo toggle, simple mode, visibility, save/reset, options, fullscreen, dark mode) are moved into a **collapsible control bar** that overlays the bottom of the screen.

- **Collapsed state (default):** a single 44 dp handle / grip icon centered at the bottom edge. Semi-transparent background.
- **Expanded state:** a horizontal pill that rises up ~56 dp from the bottom showing all control buttons at 36 dp size each, with equal horizontal spacing.
- Tapping anywhere outside the expanded bar collapses it.
- The control bar does not push the main layout up; it overlays it.

This removes the control buttons from the competing for height with the score buttons.

---

## 5. Touch Interaction Improvements

### 5.1 Swipe-to-Undo

In addition to the existing double-tap and undo toggle, introduce a **swipe-left gesture** on a score button as an alternative undo path:

- Swipe left ≥ 40 dp on the score button → undo last point for that team.
- Visual feedback: the button briefly shows a leftward slide animation and displays the decremented score.
- Swipe right on the button → (no action; reserved for future use).

Implementation: add `touchstart` / `touchend` listeners in `button_interaction.py`. Only fires if horizontal delta ≥ 40 dp and vertical delta < 30 dp (to avoid conflicts with scroll).

This means three undo paths exist: swipe-left, double-tap, and the undo toggle. All three remain active simultaneously.

### 5.2 Accidental Tap Guard

Add a **tap-lock mode** that disables score buttons to prevent accidental scoring when the phone changes hands:

- Accessible from the expanded control bar via a lock icon button.
- When locked: score buttons are visually dimmed (opacity 0.4) and show a lock overlay icon.
- Tapping a locked button shows a brief notification ("Tap lock active") instead of scoring.
- Unlocking: tap the lock icon in the control bar again, or perform a two-finger tap anywhere on the screen.
- Lock state is not persisted across sessions (resets on page reload).

### 5.3 Serve Toggle

Serve indicator is already a tappable icon per team. In phone landscape mode the serve icon is **enlarged to 44 × 44 dp** and repositioned to the bottom-left (Team A) / bottom-right (Team B) of the score button so it does not overlap with score text.

### 5.4 Timeout Action

Currently a round button in the team panel. In phone landscape mode:

- The timeout button is **replaced by three small circular dots** (filled = used, empty = available) below the score button.
- Tapping any dot calls `add_timeout` for that team (same as before).
- Long-pressing the dot area undoes the last timeout (equivalent to undo + add_timeout).
- Maximum 2 timeouts per team per set; dots reset at set change (existing `add_set` behavior).

---

## 6. Configuration Surface

The options dialog (`options_dialog.py`) is already two-column on wide screens. For phone landscape, the dialog should adapt:

### 6.1 Drawer Pattern

Replace the modal dialog with a **bottom drawer** that slides up from the bottom of the screen to 85% of viewport height when opened. This avoids the virtual keyboard shifting issues and feels native on mobile.

- Drawer slides in with a 200 ms ease-out transition.
- A drag handle at the top allows dragging down to dismiss.
- The existing two-column layout is kept for content, but columns reflow to single-column if viewport width < 480 dp.

### 6.2 Sections Visible in Phone Landscape

Organize the drawer into three tabs or accordion sections:

| Section | Contents |
|---|---|
| **Display** | Auto-hide (switch + slider), Simple mode (switch), Timeout-resets-simple (switch) |
| **Buttons** | Font selector, Follow team colors (switch), Team A color picker, Team B color picker, Text color picker, Reset colors button |
| **Match** | Points limit (number input), Points last set (number input), Sets to win (number input), Reset scores button, Reload from backend button |

The **Match** section exposes game configuration that currently requires environment variables. Changing these values overrides the conf values for the current session only (not persisted) unless a "Save as default" option is enabled (out of scope for this spec).

---

## 7. Visual Design

### 7.1 Score Button Appearance

No change from current implementation. Button color, font, and icon overlay continue to be configured via options. Haptic on tap is preserved.

### 7.2 Minimum Touch Targets

All interactive elements in phone landscape mode must meet 44 × 44 dp minimum. Elements that would be smaller (e.g., set badge, serve icon) get a 44 dp invisible touch area via padding or an overlay tap zone.

### 7.3 Safe Area Insets

On devices with a notch or a home indicator (iPhone X and later), the layout must respect CSS `env(safe-area-inset-*)`:

- Left/right paddings on the outer row: `max(8px, env(safe-area-inset-left))` and `max(8px, env(safe-area-inset-right))`.
- Bottom padding of the control bar: `max(8px, env(safe-area-inset-bottom))`.

These can be injected via NiceGUI's `ui.add_head_html` or inline style on the root container.

### 7.4 Status Bar / PWA Theme

When running as a PWA in fullscreen mode (already configured with `display: fullscreen` in manifest.json), no changes needed. When running in the browser, the existing dark/light mode toggle is preserved.

---

## 8. State and Data Model

No changes to `State`, `GameManager`, `Backend`, or the overlay communication protocol. This specification is purely a presentation-layer change.

The following `AppStorage` category keys may be added:

| Key | Type | Default | Purpose |
|---|---|---|---|
| `TAP_LOCK_ACTIVE` | `bool` | `false` | Per-session tap lock state |
| `CONTROL_BAR_EXPANDED` | `bool` | `false` | Remember collapsed/expanded preference |

---

## 9. Affected Files

| File | Change Type |
|---|---|
| `app/gui.py` | Update `is_portrait()` logic, button sizing calculation for phone landscape |
| `app/components/team_panel.py` | Refactor column layout, timeout dots, serve icon sizing |
| `app/components/center_panel.py` | Remove preview from phone landscape, compact set table |
| `app/components/control_buttons.py` | Move buttons into collapsible overlay bar |
| `app/components/button_interaction.py` | Add swipe-left gesture for undo |
| `app/options_dialog.py` | Convert to bottom drawer, add Match section |
| `app/theme.py` | Add constants for phone landscape breakpoint (932 dp) |
| `app/app_storage.py` | Add `TAP_LOCK_ACTIVE` and `CONTROL_BAR_EXPANDED` categories |
| `app/pwa/manifest.json` | No change |

New files:
- `app/components/tap_lock.py` — manages tap lock state and the lock overlay element.
- `app/components/control_bar.py` — collapsible bottom bar extracted from `ControlButtons`.

---

## 10. Testing Requirements

### 10.1 Viewport Tests (Playwright)

Extend the existing mobile viewport test suite (`tests/test_mobile_viewport.py`) with the following cases:

| Test | Viewport (w × h px) | Assertion |
|---|---|---|
| Score buttons fill majority of team columns | 667 × 375 | Each score button height ≥ 200 px |
| No horizontal scroll | 568 × 320 | `document.body.scrollWidth <= 568` |
| Control bar hidden by default | 667 × 375 | Control bar element `display: none` or `opacity: 0` |
| Control bar shows on handle tap | 667 × 375 | Control bar visible after simulated tap on handle |
| Tap-lock prevents scoring | 667 × 375 | Score does not change when lock is active |
| Swipe-left triggers undo | 667 × 375 | Score decrements on synthesized swipe-left gesture |
| Serve icon tap target ≥ 44 px | 667 × 375 | Computed touch area of serve icon ≥ 44 × 44 px |
| Options drawer slides up | 667 × 375 | Drawer element visible after options button tap |
| Tablet layout unchanged | 1024 × 768 | Layout matches current landscape behavior |
| Desktop layout unchanged | 1280 × 800 | Layout matches current landscape behavior |

### 10.2 Unit Tests

- `GameManager` and `State` require no new unit tests (no logic changes).
- `ButtonInteraction`: add tests for swipe-left detection and the threshold conditions (≥ 40 dp horizontal, < 30 dp vertical).
- `AppStorage`: add tests for the two new categories.

---

## 11. Out of Scope

- Server-side rendering optimizations.
- Changes to the overlay communication protocol or `Backend`.
- Custom overlay API contract changes.
- Internationalization of new UI strings (English first; Spanish strings can be added in a follow-up).
- Changing the portrait layout.
- Tablet-specific layout improvements.
