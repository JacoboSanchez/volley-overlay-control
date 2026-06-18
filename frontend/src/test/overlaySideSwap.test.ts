/*
 * Tests for the home/away side-swap transition in the OBS overlay
 * engine (overlay_static/js/app.js).
 *
 * app.js is a plain non-module script with no exports. Its top-level
 * function declarations share one scope, so we evaluate the source in a
 * ``new Function`` shell that injects a mock ``gsap`` and hands back the
 * two pieces under test: ``runSideSwapTransition`` and a setter that
 * rebinds the hoisted ``renderFullState`` (stubbed so the heavy full
 * re-render does not need a complete DOM). We then assert on the gsap
 * choreography the swap drives — the same thing an OBS browser source
 * renders — for the three cases that matter:
 *
 *   * edge-pinned (pylons / corners) + visible → each panel folds to its
 *     own screen edge, then the content re-renders swapped;
 *   * hidden → re-render silently, with nothing animated into view;
 *   * any other style + visible → the horizontal card-flip is preserved.
 */
import { beforeEach, describe, expect, it } from 'vitest';
import APP_SRC from '../../../overlay_static/js/app.js?raw';

interface Tween {
  targets: Element[];
  vars: Record<string, any>;
}

interface OverlayApp {
  runSideSwapTransition: (view: unknown, raw: unknown) => void;
  setRenderFullState: (fn: (view: unknown, raw: unknown) => void) => void;
}

function loadApp(gsap: unknown): OverlayApp {
  // The epilogue runs inside app.js's own function scope, so it can read
  // ``runSideSwapTransition`` and rebind the hoisted ``renderFullState``.
  const epilogue = `
    ;return {
      runSideSwapTransition: runSideSwapTransition,
      setRenderFullState: function (fn) { renderFullState = fn; },
    };`;
  const factory = new Function('gsap', APP_SRC + epilogue);
  return factory(gsap) as OverlayApp;
}

function makeGsap() {
  const tweens: Tween[] = [];
  const sets: Tween[] = [];
  const asArray = (t: unknown): Element[] =>
    (Array.isArray(t) ? t : [t]) as Element[];
  const gsap = {
    to(targets: unknown, vars: Record<string, any>) {
      tweens.push({ targets: asArray(targets), vars });
      // Drive the sequence synchronously so onComplete chaining resolves.
      if (typeof vars?.onComplete === 'function') vars.onComplete();
      return {};
    },
    set(targets: unknown, vars: Record<string, any>) {
      sets.push({ targets: asArray(targets), vars });
      return {};
    },
    getProperty: () => 1,
    killTweensOf: () => {},
    delayedCall: (_d: number, fn: () => void) => {
      if (typeof fn === 'function') fn();
      return {};
    },
  };
  return { gsap, tweens, sets };
}

function edgePinnedDom() {
  document.body.innerHTML = `
    <div id="scoreboard-container" data-fixed-geometry>
      <div class="corner-chip pylon-home team-home"></div>
      <div class="corner-chip pylon-away team-away"></div>
    </div>`;
}

function genericDom() {
  document.body.innerHTML = '<div id="scoreboard-container"></div>';
}

const view = (show: boolean) => ({
  overlay_control: { show_main_scoreboard: show },
});

describe('overlay side-swap transition', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
  });

  it('edge-pinned + visible: folds each panel to its own edge, then re-renders', () => {
    edgePinnedDom();
    const { gsap, tweens } = makeGsap();
    const app = loadApp(gsap);
    const rendered: unknown[] = [];
    app.setRenderFullState((v) => rendered.push(v));

    app.runSideSwapTransition(view(true), view(true));

    // Exactly one collapse tween, targeting both panels, fading them out.
    expect(tweens).toHaveLength(1);
    const collapse = tweens[0];
    if (!collapse) throw new Error('expected a collapse tween');
    expect(collapse.targets.map((el) => el.className)).toEqual([
      'corner-chip pylon-home team-home',
      'corner-chip pylon-away team-away',
    ]);
    expect(collapse.vars.opacity).toBe(0);
    // Home folds to the left edge (-120%), away to the right (+120%).
    expect(
      collapse.targets.map((el, i) => collapse.vars.xPercent(i, el)),
    ).toEqual([-120, 120]);
    // The swapped content is rendered once the fold completes.
    expect(rendered).toHaveLength(1);
  });

  it('hidden: re-renders silently with no reveal animation', () => {
    edgePinnedDom();
    const { gsap, tweens, sets } = makeGsap();
    const app = loadApp(gsap);
    const rendered: unknown[] = [];
    app.setRenderFullState((v) => rendered.push(v));

    app.runSideSwapTransition(view(false), view(false));

    expect(rendered).toHaveLength(1); // re-rendered swapped…
    expect(tweens).toHaveLength(0); // …but nothing animated into view
    expect(sets).toHaveLength(0);
  });

  it('generic style + visible: keeps the horizontal card-flip', () => {
    genericDom();
    const { gsap, tweens } = makeGsap();
    const app = loadApp(gsap);
    const rendered: unknown[] = [];
    app.setRenderFullState((v) => rendered.push(v));

    app.runSideSwapTransition(view(true), view(true));

    // Fold shut (scaleX → 0), re-render, then unfold (scaleX → 1).
    expect(tweens).toHaveLength(2);
    const [fold, unfold] = tweens;
    if (!fold || !unfold) throw new Error('expected fold + unfold tweens');
    expect(fold.vars.scaleX).toBe(0);
    expect(unfold.vars.scaleX).toBe(1);
    expect(rendered).toHaveLength(1);
  });
});
