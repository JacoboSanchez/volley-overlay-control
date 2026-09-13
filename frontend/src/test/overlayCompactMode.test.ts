/*
 * Tests for the compact-mode ("show only current set") toggle in the OBS
 * overlay engine (overlay_static/js/app.js).
 *
 * The page renders the card in its full state and the first payload only
 * arrives over the websocket, so a browser source that opens while compact
 * mode is already on applies it a beat late. Styles that transition the
 * collapse — neon's header — would then animate it shut over the card's
 * fade-in, flashing the chrome compact mode exists to remove. `.priming`
 * marks that first application so such a style can switch its transition
 * off for it; every later operator toggle has to animate normally.
 *
 * The guard hinges on one instant: the forced `offsetHeight` read that
 * commits the collapsed layout. It has to happen while `.priming` is still
 * on — otherwise dropping the guard changes a value mid-transition and the
 * animation runs anyway. These tests observe the class list from an
 * `offsetHeight` getter, which is exactly that instant, rather than from a
 * MutationObserver (whose callback only runs once the call has returned,
 * by which time the guard is gone either way).
 *
 * app.js is a plain non-module script with no exports, so the source is
 * evaluated in a ``new Function`` shell (as overlaySideSwap.test.ts does)
 * that hands back the helper under test.
 */
import { beforeEach, describe, expect, it } from 'vitest';
import APP_SRC from '../../../overlay_static/js/app.js?raw';

type ApplyCompactMode = (container: HTMLElement, on: unknown) => void;

function loadApplyCompactMode(): ApplyCompactMode {
  const epilogue = ';return applyCompactMode;';
  const factory = new Function('gsap', APP_SRC + epilogue);
  // The helper never touches gsap; a bare stub keeps the shell happy.
  return factory({ to: () => {}, set: () => {}, killTweensOf: () => {} }) as ApplyCompactMode;
}

describe('applyCompactMode', () => {
  let applyCompactMode: ApplyCompactMode;
  let container: HTMLElement;
  /** Class list as it stood at each forced-reflow read. */
  let reflows: string[];

  beforeEach(() => {
    applyCompactMode = loadApplyCompactMode();
    document.body.innerHTML = '<div id="scoreboard-container"></div>';
    container = document.getElementById('scoreboard-container') as HTMLElement;
    reflows = [];
    Object.defineProperty(container, 'offsetHeight', {
      configurable: true,
      get() {
        reflows.push(container.className);
        return 0;
      },
    });
  });

  it('commits the first application while the transition is still off', () => {
    expect(container.dataset.compactPrimed).toBeUndefined();

    applyCompactMode(container, true);

    expect(container.classList.contains('compact-mode')).toBe(true);
    expect(container.dataset.compactPrimed).toBe('1');
    // The collapsed layout was committed with the guard on ...
    expect(reflows.map((c) => c.split(' ').sort())).toEqual([['compact-mode', 'priming']]);
    // ... and the guard did not outlive the call, or nothing would animate.
    expect(container.classList.contains('priming')).toBe(false);
  });

  it('leaves later toggles to animate, priming neither direction', () => {
    applyCompactMode(container, true);
    reflows.length = 0;

    applyCompactMode(container, false);
    expect(container.classList.contains('compact-mode')).toBe(false);

    applyCompactMode(container, true);
    expect(container.classList.contains('compact-mode')).toBe(true);

    // No guard, and no forced reflow, on either toggle.
    expect(reflows).toEqual([]);
    expect(container.classList.contains('priming')).toBe(false);
  });

  it('primes a card that loads with compact mode already off', () => {
    applyCompactMode(container, false);

    expect(container.classList.contains('compact-mode')).toBe(false);
    expect(container.dataset.compactPrimed).toBe('1');
    expect(reflows).toEqual(['priming']);
  });

  it('treats a missing flag as compact mode off', () => {
    applyCompactMode(container, true);
    expect(container.classList.contains('compact-mode')).toBe(true);

    applyCompactMode(container, undefined);
    expect(container.classList.contains('compact-mode')).toBe(false);
  });
});
