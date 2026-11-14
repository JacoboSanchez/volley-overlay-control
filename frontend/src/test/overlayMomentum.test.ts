/*
 * Tests for the momentum strip and the set-progress custom property in the
 * OBS overlay engine (overlay_static/js/app.js).
 *
 * ``renderMomentum`` fills ``#momentum-track`` (the Momentum style) with the
 * latest rallies of the live set; ``renderSetProgress`` publishes each team's
 * progress toward the set target as ``--set-progress`` (the Anillos rings).
 *
 * app.js is a plain non-module script with no exports, so the source is
 * evaluated in a ``new Function`` shell (as overlayCompactMode.test.ts does)
 * that hands back the helpers under test.
 */
import { beforeEach, describe, expect, it } from 'vitest';
import APP_SRC from '../../../overlay_static/js/app.js?raw';

type AnyState = Record<string, any>;
interface Helpers {
  renderMomentum: (state: AnyState) => void;
  renderSetProgress: (state: AnyState) => void;
}

function loadHelpers(): Helpers {
  const epilogue = ';return { renderMomentum, renderSetProgress };';
  const factory = new Function('gsap', APP_SRC + epilogue);
  return factory({ to: () => {}, set: () => {}, killTweensOf: () => {} }) as Helpers;
}

function rallies(sequence: string) {
  return Array.from(sequence, (c) => ({ action: 'add_point', team: c === 'h' ? 1 : 2 }));
}

function stateWith(points: AnyState[], matchInfo: AnyState = {}): AnyState {
  return {
    match_info: { current_set: 2, best_of_sets: 5, points_limit: 25, ...matchInfo },
    team_home: { points: 0 },
    team_away: { points: 0 },
    overlay_control: { points_by_set: { 1: rallies('hhhh'), 2: points } },
  };
}

function chips(): string {
  const track = document.getElementById('momentum-track')!;
  return Array.from(track.children, (chip) =>
    chip.classList.contains('home') ? 'h' : chip.classList.contains('away') ? 'a' : '.',
  ).join('');
}

describe('renderMomentum', () => {
  let helpers: Helpers;

  beforeEach(() => {
    helpers = loadHelpers();
    document.body.innerHTML = '<div id="momentum-track"></div>';
  });

  it('pads the live set to twelve slots, unplayed ones first', () => {
    helpers.renderMomentum(stateWith(rallies('hah')));
    expect(chips()).toBe('.........hah');
  });

  it('keeps only the latest twelve rallies and outlines the last one', () => {
    helpers.renderMomentum(stateWith(rallies('hhhaaaaaaaaaaah')));
    expect(chips()).toBe('aaaaaaaaaaah');
    const track = document.getElementById('momentum-track')!;
    expect(track.querySelectorAll('.last')).toHaveLength(1);
    expect(track.lastElementChild!.classList.contains('last')).toBe(true);
  });

  it('skips manual score edits, which are not rallies', () => {
    helpers.renderMomentum(
      stateWith([...rallies('h'), { action: 'set_score', team: 2 }, ...rallies('a')]),
    );
    expect(chips()).toBe('..........ha');
  });

  it('follows a side swap with the team colours', () => {
    helpers.renderMomentum(stateWith(rallies('hha'), { sides_swapped: true }));
    expect(chips()).toBe('.........aah');
  });

  it('starts empty when the live set has no rallies yet', () => {
    helpers.renderMomentum(stateWith([]));
    expect(chips()).toBe('............');
  });

  it('leaves the strip untouched when the sequence did not change', () => {
    const state = stateWith(rallies('ha'));
    helpers.renderMomentum(state);
    const first = document.getElementById('momentum-track')!.firstElementChild;
    helpers.renderMomentum(state);
    expect(document.getElementById('momentum-track')!.firstElementChild).toBe(first);
  });

  it('is a no-op for styles without a momentum track', () => {
    document.body.innerHTML = '';
    expect(() => helpers.renderMomentum(stateWith(rallies('h')))).not.toThrow();
  });
});

describe('renderSetProgress', () => {
  it('publishes the progress toward the set target on fill-less containers', () => {
    const helpers = loadHelpers();
    document.body.innerHTML =
      '<div id="home-set-progress"></div><div id="away-set-progress"><i></i></div>';
    const state = stateWith([]);
    state.team_home.points = 20;
    state.team_away.points = 30;
    helpers.renderSetProgress(state);

    const home = document.getElementById('home-set-progress')!;
    const away = document.getElementById('away-set-progress')!;
    expect(home.style.getPropertyValue('--set-progress')).toBe('80.0');
    // Clamped once a team is past the target (deuce), and bar styles
    // still get their <i> fill width.
    expect(away.style.getPropertyValue('--set-progress')).toBe('100.0');
    expect(away.querySelector('i')!.style.width).toBe('100%');
  });
});
