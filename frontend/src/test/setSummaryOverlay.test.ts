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
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

// Vitest runs with cwd = frontend/; the overlay scripts live at the
// repo root (import.meta.url is an http: URL under jsdom, so resolve
// from cwd instead).
const SET_SUMMARY_SRC = readFileSync(
  resolve(process.cwd(), '../overlay_static/js/set_summary.js'),
  'utf8',
);

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
      set_history: {},
    },
    team_away: {
      name: 'Tigers',
      color_primary: '#a05010',
      color_secondary: '#000000',
      points: 5,
      sets_won: 0,
      timeouts_taken: 0,
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
    // Evaluate the IIFE fresh per test so module state (live-tick
    // interval, clock skew) can't leak between cases.
    new Function(SET_SUMMARY_SRC)();
  });

  afterEach(() => {
    // The renderer starts a 1s setInterval live tick on first render.
    vi.clearAllTimers();
    vi.useRealTimers();
    delete (window as any).SetSummary;
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
      brand_ledger: '.ss-ledger-col',
      brand_columns: '.ss-chart-wrap',
      bento: '.ss-bento-ledger',
      glass: '.ss-team-row',
      podium: '.ss-pillar',
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
      expect(stage.querySelector('.ss-ledger-col')).not.toBeNull();
    });

    it('falls back to brand_ledger for non-string styles', () => {
      const stage = renderState({ match_info: { set_summary_style: 42 } });
      expect(stage.dataset.style).toBe('brand_ledger');
    });

    it('rebuilds the stage on style hot-swap without leftovers', () => {
      renderState({ match_info: { set_summary_style: 'podium' } });
      const stage = renderState({
        match_info: { set_summary_style: 'glass' },
      });
      expect(stage.dataset.style).toBe('glass');
      expect(stage.querySelector('.ss-pillar')).toBeNull();
      expect(
        document.querySelectorAll('#set-summary-panel'),
      ).toHaveLength(1);
    });
  });

  describe('view model', () => {
    it('prefers the set_history final score over live points', () => {
      const stage = renderState({
        team_home: { points: 7, set_history: { set_1: 25 } },
        team_away: { points: 5, set_history: { set_1: 20 } },
      });
      const scores = stage.querySelectorAll('.ss-team-score');
      expect(scores[0].textContent).toBe('25');
      expect(scores[1].textContent).toBe('20');
    });

    it('prefers summary_set_num over current_set', () => {
      const stage = renderState({
        match_info: { summary_set_num: 2, current_set: 3 },
      });
      expect(stage.querySelector('.ss-set-number')!.textContent).toBe('2');
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
      const homeChips = stage.querySelectorAll(
        '.ss-ledger-col-home .ss-point:not(.ss-empty)',
      );
      expect(homeChips).toHaveLength(1);
      expect(homeChips[0].textContent).toBe('1');
    });

    it('renders timeout markers in the ledger', () => {
      const stage = renderState({
        overlay_control: {
          points_by_set: { 1: [{ team: 1, score: [1, 0], ts: 1000 }] },
          timeouts_by_set: { 1: [{ team: 2, ts: 1500 }] },
          stats: {},
        },
      });
      const marker = stage.querySelector('.ss-ledger-col-away .ss-timeout');
      expect(marker).not.toBeNull();
      expect(marker!.textContent).toBe('T');
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
    const homeVar = (stage: HTMLElement) =>
      stage.style.getPropertyValue('--ss-home');

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
