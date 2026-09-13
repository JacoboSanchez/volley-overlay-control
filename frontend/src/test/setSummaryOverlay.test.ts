/*
 * Tests for the OBS set-summary recap overlay renderer
 * (overlay_static/js/set_summary.js).
 *
 * The renderer is a plain non-module IIFE loaded via a <script> tag in
 * overlay_templates/base.html, exposing only ``window.SetSummary``.
 * The suite reads the source from disk and evaluates it against the
 * jsdom globals, then drives it exclusively through the public
 * ``render``/``hide`` API and asserts on the produced DOM — the same
 * surface a real OBS browser source exercises.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
// Vite's ``?raw`` suffix loads the scripts as strings (see
// raw-modules.d.ts). The shared label bundle is listed first to
// mirror the template load order in overlay_templates/base.html.
import I18N_LABELS_SRC from '../../../overlay_static/js/i18n_labels.js?raw';
import SET_SUMMARY_SRC from '../../../overlay_static/js/set_summary.js?raw';

type AnyState = Record<string, any>;

function makeState(overrides: AnyState = {}): AnyState {
  const base: AnyState = {
    match_info: {
      show_set_summary: true,
      set_summary_style: 'brand_ledger',
      current_set: 1,
      best_of_sets: 5,
      server_time: Date.now() / 1000,
      match_finished: false,
    },
    team_home: {
      name: 'Lions',
      color_primary: '#123456',
      color_secondary: '#ffffff',
      points: 7,
      sets_won: 0,
      timeouts_taken: 0,
      timeouts_by_set: {},
      set_history: {},
    },
    team_away: {
      name: 'Tigers',
      color_primary: '#a05010',
      color_secondary: '#000000',
      points: 5,
      sets_won: 0,
      timeouts_taken: 0,
      timeouts_by_set: {},
      set_history: {},
    },
    overlay_control: {
      points_by_set: {
        1: [
          { team: 1, score: [1, 0], ts: 1000 },
          { team: 2, score: [1, 1], ts: 1010 },
          { team: 1, score: [2, 1], ts: 1020 },
        ],
      },
      timeouts_by_set: {},
      stats: {},
    },
  };
  // Shallow-merge each top-level section so callers can override
  // single fields without re-stating the whole broadcast shape.
  const merged: AnyState = { ...base };
  for (const key of Object.keys(overrides)) {
    merged[key] =
      typeof overrides[key] === 'object' && !Array.isArray(overrides[key])
        ? { ...base[key], ...overrides[key] }
        : overrides[key];
  }
  return merged;
}

function setSummary() {
  return (window as any).SetSummary;
}

function renderState(overrides: AnyState = {}): HTMLElement {
  setSummary().render(makeState(overrides));
  return document.getElementById('set-summary-stage') as HTMLElement;
}

describe('set_summary.js overlay renderer', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-01-01T12:00:00Z'));
    document.body.innerHTML = '';
    (window as any).OVERLAY_LOCALE = 'en';
    // jsdom has no requestAnimationFrame unless pretendToBeVisual is
    // on; a synchronous stub also makes the opacity-flip assertable.
    (window as any).requestAnimationFrame = (cb: FrameRequestCallback) => {
      cb(0);
      return 0;
    };
    // Evaluate the scripts fresh per test (in template load order) so
    // module state (live-tick interval, clock skew) can't leak
    // between cases.
    new Function(I18N_LABELS_SRC)();
    new Function(SET_SUMMARY_SRC)();
  });

  afterEach(() => {
    // The renderer starts a 1s setInterval live tick on first render.
    vi.clearAllTimers();
    vi.useRealTimers();
    delete (window as any).SetSummary;
    delete (window as any).OVERLAY_LABELS;
  });

  it('exposes only render/hide on window.SetSummary', () => {
    expect(typeof setSummary().render).toBe('function');
    expect(typeof setSummary().hide).toBe('function');
    expect(Object.keys(setSummary())).toEqual(['render', 'hide']);
  });

  it('ignores states without match_info', () => {
    setSummary().render({});
    expect(document.getElementById('set-summary-panel')).toBeNull();
  });

  describe('variant dispatch', () => {
    // Marker: a DOM node only that variant's builder produces.
    const VARIANT_MARKERS: Record<string, string> = {
      brand_ledger: '.ss-rally-ribbon',
      brand_columns: '.ss-chart-wrap',
      bento: '.ss-bento-ledger',
      glass: '.ss-team-row',
      ledger_diff: '.ss-ld-cols',
      bumper: '.ss-bumper-row',
    };

    for (const [style, marker] of Object.entries(VARIANT_MARKERS)) {
      it(`renders the ${style} variant`, () => {
        const stage = renderState({ match_info: { set_summary_style: style } });
        expect(stage.dataset.style).toBe(style);
        const panel = document.getElementById('set-summary-panel')!;
        expect(panel.querySelector(marker)).not.toBeNull();
      });
    }

    it('falls back to brand_ledger for unknown styles', () => {
      const stage = renderState({
        match_info: { set_summary_style: 'totally_bogus' },
      });
      expect(stage.dataset.style).toBe('brand_ledger');
      expect(stage.querySelector('.ss-rally-ribbon')).not.toBeNull();
    });

    it('falls back to brand_ledger for non-string styles', () => {
      const stage = renderState({ match_info: { set_summary_style: 42 } });
      expect(stage.dataset.style).toBe('brand_ledger');
    });

    it('rebuilds the stage on style hot-swap without leftovers', () => {
      renderState({ match_info: { set_summary_style: 'ledger_diff' } });
      const stage = renderState({
        match_info: { set_summary_style: 'glass' },
      });
      expect(stage.dataset.style).toBe('glass');
      expect(stage.querySelector('.ss-ld-cols')).toBeNull();
      expect(document.querySelectorAll('#set-summary-panel')).toHaveLength(1);
    });
  });

  describe('Rallies lower third', () => {
    const thirdSet = {
      match_info: { summary_set_num: 3, current_set: 4 },
      team_home: {
        name: 'CV Pontevedra',
        set_history: { set_1: 25, set_2: 22, set_3: 25, set_4: 0 },
        sets_won: 2,
      },
      team_away: {
        name: 'San Sadurniño',
        set_history: { set_1: 20, set_2: 25, set_3: 21, set_4: 0 },
        sets_won: 1,
      },
    };

    it('puts only earlier sets between each identity and its current score', () => {
      const stage = renderState(thirdSet);
      const home = stage.querySelector('.ss-strip-home')!;
      const away = stage.querySelector('.ss-strip-away')!;
      expect(Array.from(home.children).map((n) => n.className)).toEqual([
        'ss-strip-identity',
        'ss-strip-history',
        'ss-team-score',
      ]);
      expect(Array.from(away.children).map((n) => n.className)).toEqual([
        'ss-team-score',
        'ss-strip-history',
        'ss-strip-identity',
      ]);
      expect(home.querySelector('.ss-strip-history')!.textContent).toBe('S125S222');
      expect(away.querySelector('.ss-strip-history')!.textContent).toBe('S120S225');
      expect(home.querySelector('.ss-strip-previous .home')!.textContent).toBe('25');
      expect(away.querySelector('.ss-strip-previous .away')!.textContent).toBe('25');
      expect(stage.querySelector('.ss-strip-standing')!.textContent).toBe('Match2–1');
      expect(stage.querySelector('.ss-strip-status')!.textContent).toBe('Set 3Final');
      expect(stage.querySelector('.ss-ribbon')).toBeNull();
    });

    it('does not invent previous-set scores in the first set or with missing history', () => {
      let stage = renderState();
      expect(stage.querySelectorAll('.ss-strip-previous')).toHaveLength(0);
      stage = renderState({
        match_info: { summary_set_num: 3 },
        team_home: { set_history: { set_1: 25 } },
      });
      expect(stage.querySelector('.ss-strip-away .ss-strip-history')!.textContent).toBe('S1–');
      expect(
        stage.querySelectorAll('.ss-strip-previous .home, .ss-strip-previous .away'),
      ).toHaveLength(0);
    });

    it('shows all four previous sets in a deciding fifth set', () => {
      const stage = renderState({
        match_info: { summary_set_num: 5, current_set: 5, match_finished: true },
        team_home: { set_history: { set_1: 25, set_2: 22, set_3: 25, set_4: 24, set_5: 17 } },
        team_away: { set_history: { set_1: 20, set_2: 25, set_3: 21, set_4: 26, set_5: 15 } },
      });
      expect(stage.querySelectorAll('.ss-strip-previous')).toHaveLength(8);
      expect(stage.querySelector('.ss-strip-status')!.textContent).toBe('Set 5Final');
    });

    it('does not call a live set final when the payload includes every set slot', () => {
      const stage = renderState({
        team_home: { set_history: { set_1: 7, set_2: 0, set_3: 0 } },
        team_away: { set_history: { set_1: 5, set_2: 0, set_3: 0 } },
      });
      expect(stage.querySelector('.ss-strip-status')!.textContent).toBe('Set 1LIVE');
    });

    it('renders the recorded rally winners in order and outlines only the last', () => {
      const stage = renderState();
      const rallies = Array.from(stage.querySelectorAll('.ss-rally'));
      expect(rallies.map((n) => n.className)).toEqual([
        'ss-rally home',
        'ss-rally away',
        'ss-rally home ss-last',
      ]);
      expect(rallies.map((n) => n.getAttribute('title'))).toEqual([
        '1 · Lions · 1–0',
        '2 · Tigers · 1–1',
        '3 · Lions · 2–1',
      ]);
      // The live score is 7–5 but there are only three audit records.
      expect(stage.querySelector('.ss-rally-heading')!.textContent).toContain(
        'Recorded rallies · 3',
      );
    });

    it('retains every rally of a long deuce set and wraps to balanced rows', () => {
      const points = Array.from({ length: 126 }, (_, i) => ({
        team: (i % 2) + 1,
        score: [i, i],
        ts: 1000 + i,
      }));
      const stage = renderState({ overlay_control: { points_by_set: { 1: points } } });
      expect(stage.querySelectorAll('.ss-rally')).toHaveLength(126);
      expect(
        (stage.querySelector('.ss-rally-track') as HTMLElement).style.gridTemplateColumns,
      ).toBe('repeat(42, minmax(0, 1fr))');
      expect(stage.querySelector('.ss-last')!.getAttribute('title')).toContain('126 · Tigers');
    });

    it('uses an explicit no-recorded-rallies message even for a finished set', () => {
      (window as any).OVERLAY_LOCALE = 'es';
      const stage = renderState(thirdSet);
      expect(stage.querySelector('.ss-empty-note')!.textContent).toBe(
        'Sin rallies registrados en este set',
      );
      expect(stage.querySelectorAll('.ss-rally')).toHaveLength(0);
    });

    it('patterns the away rallies and legend when both teams share a colour', () => {
      const stage = renderState({
        team_home: { color_primary: '#124ade' },
        team_away: { color_primary: '#124ade' },
      });
      expect(stage.querySelector('.ss-rally-pattern .ss-rally.away')).not.toBeNull();
      expect(stage.querySelector('.ss-rally-pattern .ss-rally-legend .away')).not.toBeNull();
      renderState();
      expect(stage.querySelector('.ss-rally-pattern')).toBeNull();
    });

    it('retains configured colours for rallies and brightens dark text accents', () => {
      const stage = renderState({
        team_home: { color_primary: '#000000' },
        team_away: { color_primary: '#ef3340' },
      });
      expect(stage.style.getPropertyValue('--ss-home')).toBe('#000000');
      expect(stage.style.getPropertyValue('--ss-away')).toBe('#ef3340');
      expect(stage.style.getPropertyValue('--ss-home-text')).not.toBe('rgb(0, 0, 0)');
    });

    it('renders club names as text and uses configured logos', () => {
      const stage = renderState({
        team_home: { name: '<img src=x onerror=alert(1)>', logo_url: '/media/icons/home.webp' },
      });
      expect(stage.querySelector('.ss-team-name')!.textContent).toBe(
        '<img src=x onerror=alert(1)>',
      );
      expect(stage.querySelector('.ss-team-name img')).toBeNull();
      expect(stage.querySelector('.ss-logo img')!.getAttribute('src')).toBe(
        '/media/icons/home.webp',
      );
    });
  });

  describe('glass point-type band', () => {
    // A set that was scored with per-point scouting tags.
    const TAGGED = {
      1: {
        1: { ace: 3, kill: 0, block: 0, opp_error: 0 },
        2: { ace: 0, kill: 2, block: 1, opp_error: 1 },
      },
    };

    it('renders the band and flags the stage when the set has tagged points', () => {
      const stage = renderState({
        match_info: { set_summary_style: 'glass', summary_set_num: 1 },
        overlay_control: { stats: { point_types_by_set: TAGGED } },
      });
      // The flag lets the CSS tighten the score tile so the band's
      // extra row doesn't clip the lower stats — see set_summary.css.
      expect(stage.classList.contains('ss-has-breakdown')).toBe(true);
      expect(stage.querySelector('.ss-pt-breakdown-wide')).not.toBeNull();
    });

    it('omits the band and the flag when the set has no tagged points', () => {
      const stage = renderState({
        match_info: { set_summary_style: 'glass', summary_set_num: 1 },
        overlay_control: { stats: { point_types_by_set: {} } },
      });
      expect(stage.classList.contains('ss-has-breakdown')).toBe(false);
      expect(stage.querySelector('.ss-pt-breakdown-wide')).toBeNull();
    });

    it('clears the flag when hot-swapping a tagged set for an untagged one', () => {
      renderState({
        match_info: { set_summary_style: 'glass', summary_set_num: 1 },
        overlay_control: { stats: { point_types_by_set: TAGGED } },
      });
      const stage = renderState({
        match_info: { set_summary_style: 'glass', summary_set_num: 1 },
        overlay_control: { stats: { point_types_by_set: {} } },
      });
      expect(stage.classList.contains('ss-has-breakdown')).toBe(false);
    });

    it('drops the flag when hot-swapping glass (with band) to another style', () => {
      // The marker is glass-only; switching to a style that never sets
      // it must not leave the stale class on the stage (the per-render
      // className reset guarantees the clean slate the wipe promises).
      renderState({
        match_info: { set_summary_style: 'glass', summary_set_num: 1 },
        overlay_control: { stats: { point_types_by_set: TAGGED } },
      });
      const stage = renderState({
        match_info: { set_summary_style: 'brand_ledger', summary_set_num: 1 },
      });
      expect(stage.classList.contains('ss-has-breakdown')).toBe(false);
      expect(stage.className).toBe('ss-stage');
    });
  });

  describe('bumper point-type breakdown', () => {
    const TAGGED = {
      1: {
        1: { ace: 2, kill: 15, block: 5, opp_error: 1 },
        2: { ace: 3, kill: 14, block: 4, opp_error: 4 },
      },
    };

    it('never renders the two-row block, even on a fully tagged set', () => {
      // The bumper core is a free-floating card centred in a fixed
      // stage row, with the full-width chip ledger below it. The
      // breakdown's two rows grew the card from 371px to 534px — past
      // the ~420px row a 1280x720 browser source gives it — so the top
      // of the card was clipped and the away team's ledger row
      // disappeared behind the strip. See renderBumper.
      const stage = renderState({
        match_info: { set_summary_style: 'bumper', summary_set_num: 1 },
        overlay_control: { stats: { point_types_by_set: TAGGED } },
      });
      expect(stage.querySelector('.ss-pt-breakdown')).toBeNull();
      expect(stage.querySelector('.ss-pt-chips')).toBeNull();
      // The core keeps exactly its two rows, and both ledger rows
      // (home + away) still render below it.
      const core = stage.querySelector('.ss-bumper-core')!;
      expect(core.children).toHaveLength(2);
      expect(stage.querySelectorAll('.ss-bumper-row')).toHaveLength(2);
    });

    it('still renders the block in the variants that have room for it', () => {
      // Guards the fix against an over-broad revert: dropping the
      // block is bumper-only, the tile/centre variants keep it.
      for (const style of ['bento', 'glass']) {
        renderState({
          match_info: { set_summary_style: style, summary_set_num: 1 },
          overlay_control: { stats: { point_types_by_set: TAGGED } },
        });
        const panel = document.getElementById('set-summary-panel')!;
        expect(panel.querySelector('.ss-pt-breakdown')).not.toBeNull();
      }
    });
  });

  describe('ledger_diff scoresheet variant', () => {
    const TAGGED = {
      1: {
        1: { ace: 4, kill: 14, block: 5, opp_error: 2 },
        2: { ace: 2, kill: 12, block: 4, opp_error: 4 },
      },
    };

    it('splits stats into two columns when the set has tagged points', () => {
      const stage = renderState({
        match_info: { set_summary_style: 'ledger_diff', summary_set_num: 1 },
        overlay_control: { stats: { point_types_by_set: TAGGED } },
      });
      expect(stage.querySelector('.ss-ld-cols.two')).not.toBeNull();
      expect(stage.querySelector('.ss-ld-col-right')).not.toBeNull();
    });

    it('uses a single centred column when no points are tagged', () => {
      const stage = renderState({
        match_info: { set_summary_style: 'ledger_diff', summary_set_num: 1 },
        overlay_control: { stats: { point_types_by_set: {} } },
      });
      expect(stage.querySelector('.ss-ld-cols.one')).not.toBeNull();
      expect(stage.querySelector('.ss-ld-col-right')).toBeNull();
    });

    it('draws the point-difference line once the set has rallies', () => {
      const stage = renderState({
        match_info: { set_summary_style: 'ledger_diff' },
      });
      // makeState seeds points_by_set[1] with three rallies.
      expect(stage.querySelector('.ss-ld-svg .ss-ld-line')).not.toBeNull();
    });
  });

  describe('view model', () => {
    it('prefers the set_history final score over live points', () => {
      const stage = renderState({
        team_home: { points: 7, set_history: { set_1: 25 } },
        team_away: { points: 5, set_history: { set_1: 20 } },
      });
      const scores = stage.querySelectorAll('.ss-team-score');
      expect(scores[0]!.textContent).toBe('25');
      expect(scores[1]!.textContent).toBe('20');
    });

    it('prefers summary_set_num over current_set', () => {
      const stage = renderState({
        match_info: { summary_set_num: 2, current_set: 3 },
      });
      expect(stage.querySelector('.ss-set-number')!.textContent).toBe('2');
    });

    it('resolves shared bundle labels per locale', () => {
      // "set" lives in the shared window.OVERLAY_LABELS bundle, not
      // in the renderer's local dictionary.
      (window as any).OVERLAY_LOCALE = 'de';
      const stage = renderState();
      expect(stage.querySelector('.ss-set-label')!.textContent).toBe('Satz');
    });

    it('degrades to the raw key when the shared bundle is missing', () => {
      delete (window as any).OVERLAY_LABELS;
      const stage = renderState();
      expect(stage.querySelector('.ss-set-label')!.textContent).toBe('set');
    });

    it('filters set_score edits out of the ledger', () => {
      const stage = renderState({
        overlay_control: {
          points_by_set: {
            1: [
              { team: 1, score: [1, 0], ts: 1000 },
              { team: 1, score: [25, 20], ts: 2000, action: 'set_score' },
            ],
          },
          timeouts_by_set: {},
          stats: {},
        },
      });
      const homeChips = stage.querySelectorAll('.ss-rally.home');
      expect(homeChips).toHaveLength(1);
      expect(homeChips[0]!.getAttribute('title')).toBe('1 · Lions · 1–0');
    });

    it('shows the localized empty note before the first rally (chart variants)', () => {
      const stage = renderState({
        match_info: { set_summary_style: 'brand_columns' },
        overlay_control: { points_by_set: {}, timeouts_by_set: {}, stats: {} },
      });
      const note = stage.querySelector('.ss-chart-wrap .ss-empty-note');
      expect(note).not.toBeNull();
      expect(note!.textContent).toBe('No points yet this set');
    });

    it('shows the inline empty note in the rally ribbon', () => {
      const stage = renderState({
        overlay_control: { points_by_set: {}, timeouts_by_set: {}, stats: {} },
      });
      const note = stage.querySelector('.ss-rally-ribbon .ss-empty-note--inline');
      expect(note).not.toBeNull();
    });

    it('omits the empty note once the set has points', () => {
      const stage = renderState({
        match_info: { set_summary_style: 'brand_columns' },
      });
      expect(stage.querySelector('.ss-empty-note')).toBeNull();
    });

    it('scales the progression chart to the active rules set target', () => {
      // Deciding set of a best-of-5 with a 15-point target: a
      // 15-point score must hit the top of the chart (y = padTop)
      // instead of 15/25ths of the old fixed 25-point scale.
      const stage = renderState({
        match_info: {
          set_summary_style: 'brand_columns',
          best_of_sets: 5,
          current_set: 5,
          points_limit: 25,
          points_limit_last_set: 15,
        },
        overlay_control: {
          points_by_set: { 5: [{ team: 1, score: [15, 10], ts: 1000 }] },
          timeouts_by_set: {},
          stats: {},
        },
      });
      const points = stage.querySelector('.ss-line-home')!.getAttribute('points')!;
      const lastY = Number(points.split(' ').pop()!.split(',')[1]);
      expect(lastY).toBe(6); // chart padTop — full height
    });

    it('keeps the 25-point scale for regular indoor sets', () => {
      const stage = renderState({
        match_info: {
          set_summary_style: 'brand_columns',
          points_limit: 25,
          points_limit_last_set: 15,
        },
        overlay_control: {
          points_by_set: { 1: [{ team: 1, score: [15, 10], ts: 1000 }] },
          timeouts_by_set: {},
          stats: {},
        },
      });
      const points = stage.querySelector('.ss-line-home')!.getAttribute('points')!;
      const lastY = Number(points.split(' ').pop()!.split(',')[1]);
      expect(lastY).toBeCloseTo(380 - 6 - (15 / 25) * 368, 1);
    });

    it('renders timeout markers in the ledger', () => {
      const stage = renderState({
        match_info: { set_summary_style: 'bumper' },
        overlay_control: {
          points_by_set: { 1: [{ team: 1, score: [1, 0], ts: 1000 }] },
          timeouts_by_set: { 1: [{ team: 2, ts: 1500 }] },
          stats: {},
        },
      });
      const marker = stage.querySelector('.ss-bumper-row.away .ss-timeout');
      expect(marker).not.toBeNull();
      expect(marker!.textContent).toBe('T');
    });

    // The live ``timeouts_taken`` counter is reset by the backend when
    // the match moves on to the next set, so a recap of the set that
    // just finished must read the persisted per-set counters. The
    // audit-derived event list is best-effort and only feeds markers.
    describe('per-set timeout counts', () => {
      const SET_1_TIMEOUTS = {
        1: [
          { team: 1, ts: 1200 },
          { team: 2, ts: 1500 },
          { team: 2, ts: 1800 },
        ],
      };

      // The stat row each variant renders the pair in, and where the
      // two numbers sit inside it.
      const VARIANT_ROWS: Record<string, [string, string, string]> = {
        bento: ['.ss-stat-row', '.home', '.away'],
        glass: ['.ss-stat-row', '.home', '.away'],
        bumper: ['.ss-stat-row', '.home', '.away'],
        ledger_diff: ['.ss-ld-row', '.ss-ld-hv', '.ss-ld-av'],
      };

      for (const [style, [rowSelector, homeSel, awaySel]] of Object.entries(VARIANT_ROWS)) {
        it(`counts the displayed set's timeouts in ${style}`, () => {
          renderState({
            match_info: {
              set_summary_style: style,
              summary_set_num: 1,
              current_set: 2,
            },
            // Set 1 is over: the live counters already restarted for
            // set 2, but the persisted per-set history still holds it.
            team_home: {
              timeouts_taken: 0,
              timeouts_by_set: { set_1: 1 },
              set_history: { set_1: 25 },
            },
            team_away: {
              timeouts_taken: 0,
              timeouts_by_set: { set_1: 2 },
              set_history: { set_1: 23 },
            },
            overlay_control: {
              points_by_set: { 1: [{ team: 1, score: [1, 0], ts: 1000 }] },
              timeouts_by_set: SET_1_TIMEOUTS,
              stats: {},
            },
          });
          const panel = document.getElementById('set-summary-panel')!;
          const row = Array.from(panel.querySelectorAll(rowSelector)).find((n) =>
            /timeout/i.test(n.textContent || ''),
          );
          expect(row, `no timeout row in ${style}`).toBeTruthy();
          expect(row!.querySelector(homeSel)!.textContent).toBe('1');
          expect(row!.querySelector(awaySel)!.textContent).toBe('2');
        });
      }

      it('reads the persisted per-set totals, not the audit event list', () => {
        // A best-effort audit append can fail while the authoritative
        // per-set counter (the one the cap is enforced against) still
        // records the timeout. The totals must come from the state, so
        // an empty event list must not zero out a real count.
        renderState({
          match_info: {
            set_summary_style: 'bento',
            summary_set_num: 1,
            current_set: 1,
          },
          team_home: {
            timeouts_taken: 2,
            timeouts_by_set: { set_1: 2 },
          },
          team_away: { timeouts_taken: 1, timeouts_by_set: { set_1: 1 } },
          overlay_control: {
            points_by_set: { 1: [{ team: 1, score: [1, 0], ts: 1000 }] },
            // Audit is missing both events.
            timeouts_by_set: {},
            stats: {},
          },
        });
        const panel = document.getElementById('set-summary-panel')!;
        const row = Array.from(panel.querySelectorAll('.ss-stat-row')).find((n) =>
          /timeout/i.test(n.textContent || ''),
        );
        expect(row).toBeTruthy();
        expect(row!.querySelector('.home')!.textContent).toBe('2');
        expect(row!.querySelector('.away')!.textContent).toBe('1');
      });
    });
  });

  describe('clocks', () => {
    it('derives elapsed time from server_time (clock skew)', () => {
      // Server clock runs 120 s ahead of the (fake) client clock; the
      // match started 60 s ago in *server* time. A skew-naive client
      // would show 3:00 — the renderer must show 1:00.
      const serverNow = Date.now() / 1000 + 120;
      renderState({
        match_info: {
          server_time: serverNow,
          match_started_at: serverNow - 60,
        },
      });
      const clock = document.querySelector('[data-live-match]')!;
      expect(clock.textContent).toBe('1:00');
    });

    it('ticks the match clock between broadcasts', () => {
      const serverNow = Date.now() / 1000;
      renderState({
        match_info: {
          server_time: serverNow,
          match_started_at: serverNow - 60,
        },
      });
      vi.advanceTimersByTime(2000);
      const clock = document.querySelector('[data-live-match]')!;
      expect(clock.textContent).toBe('1:02');
    });

    it('freezes the match clock once the match is finished', () => {
      const serverNow = Date.now() / 1000;
      renderState({
        match_info: {
          server_time: serverNow,
          match_started_at: serverNow - 300,
          match_finished_at: serverNow - 60,
          match_finished: true,
        },
      });
      vi.advanceTimersByTime(5000);
      const clock = document.querySelector('[data-live-match]')!;
      expect(clock.textContent).toBe('4:00');
    });
  });

  describe('show/hide lifecycle', () => {
    it('fades the panel in on render and out on hide', () => {
      renderState();
      const panel = document.getElementById('set-summary-panel')!;
      expect(panel.style.opacity).toBe('1');
      expect(panel.style.pointerEvents).toBe('auto');

      setSummary().hide();
      expect(panel.style.opacity).toBe('0');
      expect(panel.style.pointerEvents).toBe('none');
    });

    it('reuses a single panel across renders', () => {
      renderState();
      setSummary().hide();
      renderState({ match_info: { set_summary_style: 'bumper' } });
      expect(document.querySelectorAll('#set-summary-panel')).toHaveLength(1);
    });
  });

  describe('team colour resolution', () => {
    const homeVar = (stage: HTMLElement) => stage.style.getPropertyValue('--ss-home');

    it('passes a normal primary colour through', () => {
      const stage = renderState({
        team_home: { color_primary: '#123456' },
      });
      expect(homeVar(stage)).toBe('#123456');
    });

    it('uses the mid-tone secondary when the primary is near-white', () => {
      const stage = renderState({
        team_home: { color_primary: '#ffffff', color_secondary: '#336699' },
      });
      expect(homeVar(stage)).toBe('#336699');
    });

    it('falls back to the accent when primary is white and secondary is black', () => {
      const stage = renderState({
        team_home: { color_primary: '#fdfdfd', color_secondary: '#000000' },
      });
      expect(homeVar(stage)).toBe('#d4314c');
    });

    it('dashes the away chart line when team colours are similar', () => {
      const panel = renderState({
        match_info: { set_summary_style: 'brand_columns' },
        team_home: { color_primary: '#1a2a6c' },
        team_away: { color_primary: '#23357f' },
      }).closest('#set-summary-panel')!;
      expect(panel.querySelector('.ss-line-away--dashed')).not.toBeNull();
    });

    it('keeps the away chart line solid for distinct colours', () => {
      const panel = renderState({
        match_info: { set_summary_style: 'brand_columns' },
      }).closest('#set-summary-panel')!;
      expect(panel.querySelector('.ss-line-away')).not.toBeNull();
      expect(panel.querySelector('.ss-line-away--dashed')).toBeNull();
    });
  });
});
