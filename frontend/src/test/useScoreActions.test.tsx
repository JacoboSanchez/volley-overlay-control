import { describe, it, expect, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useScoreActions } from '../hooks/useScoreActions';
import type { GameActions } from '../hooks/useGameState';
import type { Settings } from '../hooks/useSettings';
import type { useHaptics } from '../hooks/useHaptics';

// Mirrors the alias inside useScoreActions so a change to the haptics
// signature surfaces here as a type error instead of drifting silently.
type Pulse = ReturnType<typeof useHaptics>['pulse'];

interface HookProps {
  actions: GameActions;
  settings: Settings;
  simpleMode: boolean;
  matchFinished: boolean;
  pulse: Pulse;
}

function mockActions(overrides: Partial<GameActions> = {}): GameActions {
  return {
    addPoint: vi.fn(),
    addSet: vi.fn(),
    addTimeout: vi.fn(),
    changeServe: vi.fn(),
    setSimpleMode: vi.fn(),
    undoLast: vi.fn(),
    setScore: vi.fn(),
    setSets: vi.fn(),
    reset: vi.fn(),
    startMatch: vi.fn(),
    setVisibility: vi.fn(),
    setSwapSides: vi.fn(),
    setSetSummary: vi.fn(),
    setSetSummaryStyle: vi.fn(),
    syncOverlayLocale: vi.fn(),
    setAutoSwapSides: vi.fn(),
    setRules: vi.fn(),
    ...overrides,
  };
}

function mockSettings(overrides: Partial<Settings> = {}): Settings {
  // The hook reads only these three flags; the cast keeps the fixture from
  // having to restate every unrelated field of Settings.
  return {
    trackPointTypes: false,
    autoSimple: false,
    autoSimpleOnTimeout: false,
    ...overrides,
  } as Settings;
}

function render(overrides: Partial<HookProps> = {}) {
  const initialProps: HookProps = {
    actions: mockActions(),
    settings: mockSettings(),
    simpleMode: false,
    matchFinished: false,
    pulse: vi.fn(),
    ...overrides,
  };
  const view = renderHook((props: HookProps) => useScoreActions(props), { initialProps });
  return {
    ...view,
    /** Re-render with some inputs changed, as a live state push would. */
    update: (next: Partial<HookProps>) => view.rerender({ ...initialProps, ...next }),
  };
}

/** Narrow a mocked action back to its vi.fn() handle. */
function asMock(fn: unknown): ReturnType<typeof vi.fn> {
  return fn as ReturnType<typeof vi.fn>;
}

describe('useScoreActions', () => {
  // ------------------------------------------------------------------
  // handleAddPoint
  // ------------------------------------------------------------------
  describe('handleAddPoint', () => {
    it('scores a point immediately when trackPointTypes is off', () => {
      const actions = mockActions();
      const { result: r } = render({ actions });
      act(() => r.current.handleAddPoint(1));
      expect(actions.addPoint).toHaveBeenCalledWith(1, false, undefined, undefined);
    });

    it('opens the point-type picker when trackPointTypes is on', () => {
      const actions = mockActions();
      const settings = mockSettings({ trackPointTypes: true });
      const { result: r } = render({ actions, settings });
      act(() => r.current.handleAddPoint(1));
      expect(actions.addPoint).not.toHaveBeenCalled();
      expect(r.current.pointPickerTeam).toBe(1);
    });

    it('is a no-op when match is finished', () => {
      const actions = mockActions();
      const { result: r } = render({ actions, matchFinished: true });
      act(() => r.current.handleAddPoint(1));
      expect(actions.addPoint).not.toHaveBeenCalled();
    });

    it('is a no-op when matchFinished and trackPointTypes are both on', () => {
      const actions = mockActions();
      const settings = mockSettings({ trackPointTypes: true });
      const { result: r } = render({ actions, settings, matchFinished: true });
      act(() => r.current.handleAddPoint(2));
      expect(actions.addPoint).not.toHaveBeenCalled();
      expect(r.current.pointPickerTeam).toBeNull();
    });
  });

  // ------------------------------------------------------------------
  // commitPoint
  // ------------------------------------------------------------------
  describe('commitPoint', () => {
    it('scores with point type and error type', () => {
      const actions = mockActions();
      const { result: r } = render({ actions });
      act(() => r.current.commitPoint(2, 'kill', 'serve_error'));
      expect(actions.addPoint).toHaveBeenCalledWith(2, false, 'kill', 'serve_error');
    });

    it('scores without classification', () => {
      const actions = mockActions();
      const { result: r } = render({ actions });
      act(() => r.current.commitPoint(1));
      expect(actions.addPoint).toHaveBeenCalledWith(1, false, undefined, undefined);
    });

    it('enables simple mode via autoSimple when scoring and not already simple', () => {
      const actions = mockActions();
      const settings = mockSettings({ autoSimple: true });
      const { result: r } = render({ actions, settings, simpleMode: false });
      act(() => r.current.commitPoint(1));
      expect(actions.addPoint).toHaveBeenCalled();
      expect(actions.setSimpleMode).toHaveBeenCalledWith(true);
    });

    it('does not set simple mode when already in simple mode', () => {
      const actions = mockActions();
      const settings = mockSettings({ autoSimple: true });
      const { result: r } = render({ actions, settings, simpleMode: true });
      act(() => r.current.commitPoint(2));
      expect(actions.setSimpleMode).not.toHaveBeenCalled();
    });

    it('does not set simple mode when autoSimple is off', () => {
      const actions = mockActions();
      const settings = mockSettings({ autoSimple: false });
      const { result: r } = render({ actions, settings, simpleMode: false });
      act(() => r.current.commitPoint(1));
      expect(actions.setSimpleMode).not.toHaveBeenCalled();
    });
  });

  // ------------------------------------------------------------------
  // handleAddSet
  // ------------------------------------------------------------------
  describe('handleAddSet', () => {
    it('adds a set for team 1', () => {
      const actions = mockActions();
      const { result: r } = render({ actions });
      act(() => r.current.handleAddSet(1));
      expect(actions.addSet).toHaveBeenCalledWith(1, false);
    });

    it('adds a set for team 2', () => {
      const actions = mockActions();
      const { result: r } = render({ actions });
      act(() => r.current.handleAddSet(2));
      expect(actions.addSet).toHaveBeenCalledWith(2, false);
    });

    it('is a no-op when matchFinished', () => {
      const actions = mockActions();
      const { result: r } = render({ actions, matchFinished: true });
      act(() => r.current.handleAddSet(1));
      expect(actions.addSet).not.toHaveBeenCalled();
    });
  });

  // ------------------------------------------------------------------
  // handleAddTimeout
  // ------------------------------------------------------------------
  describe('handleAddTimeout', () => {
    it('registers a timeout for team 1', () => {
      const actions = mockActions();
      const { result: r } = render({ actions });
      act(() => r.current.handleAddTimeout(1));
      expect(actions.addTimeout).toHaveBeenCalledWith(1, false);
    });

    it('is a no-op when matchFinished', () => {
      const actions = mockActions();
      const { result: r } = render({ actions, matchFinished: true });
      act(() => r.current.handleAddTimeout(1));
      expect(actions.addTimeout).not.toHaveBeenCalled();
    });

    it('exits simple mode when autoSimple + autoSimpleOnTimeout are on and currently simple', () => {
      const actions = mockActions();
      const settings = mockSettings({ autoSimple: true, autoSimpleOnTimeout: true });
      const { result: r } = render({ actions, settings, simpleMode: true });
      act(() => r.current.handleAddTimeout(2));
      expect(actions.setSimpleMode).toHaveBeenCalledWith(false);
    });

    it('does not exit simple mode when autoSimpleOnTimeout is off', () => {
      const actions = mockActions();
      const settings = mockSettings({ autoSimple: true, autoSimpleOnTimeout: false });
      const { result: r } = render({ actions, settings, simpleMode: true });
      act(() => r.current.handleAddTimeout(2));
      expect(actions.setSimpleMode).not.toHaveBeenCalled();
    });

    it('does not exit simple mode when not currently in simple mode', () => {
      const actions = mockActions();
      const settings = mockSettings({ autoSimple: true, autoSimpleOnTimeout: true });
      const { result: r } = render({ actions, settings, simpleMode: false });
      act(() => r.current.handleAddTimeout(2));
      expect(actions.setSimpleMode).not.toHaveBeenCalled();
    });
  });

  // ------------------------------------------------------------------
  // handleChangeServe
  // ------------------------------------------------------------------
  describe('handleChangeServe', () => {
    it('changes serve to team 1', () => {
      const actions = mockActions();
      const { result: r } = render({ actions });
      act(() => r.current.handleChangeServe(1));
      expect(actions.changeServe).toHaveBeenCalledWith(1);
    });

    it('changes serve to team 2', () => {
      const actions = mockActions();
      const { result: r } = render({ actions });
      act(() => r.current.handleChangeServe(2));
      expect(actions.changeServe).toHaveBeenCalledWith(2);
    });
  });

  // ------------------------------------------------------------------
  // handleDoubleTapScore
  // ------------------------------------------------------------------
  describe('handleDoubleTapScore', () => {
    it('undoes a point for team 1 and pulses haptics', () => {
      const actions = mockActions();
      const pulse = vi.fn();
      const { result: r } = render({ actions, pulse });
      act(() => r.current.handleDoubleTapScore(1));
      expect(pulse).toHaveBeenCalledWith('confirm');
      expect(actions.addPoint).toHaveBeenCalledWith(1, true);
    });

    it('undoes a point for team 2 and pulses haptics', () => {
      const actions = mockActions();
      const pulse = vi.fn();
      const { result: r } = render({ actions, pulse });
      act(() => r.current.handleDoubleTapScore(2));
      expect(pulse).toHaveBeenCalledWith('confirm');
      expect(actions.addPoint).toHaveBeenCalledWith(2, true);
    });
  });

  // ------------------------------------------------------------------
  // handleDoubleTapTimeout
  // ------------------------------------------------------------------
  describe('handleDoubleTapTimeout', () => {
    it('undoes a timeout for team 1 and pulses haptics', () => {
      const actions = mockActions();
      const pulse = vi.fn();
      const { result: r } = render({ actions, pulse });
      act(() => r.current.handleDoubleTapTimeout(1));
      expect(pulse).toHaveBeenCalledWith('confirm');
      expect(actions.addTimeout).toHaveBeenCalledWith(1, true);
    });

    it('undoes a timeout for team 2 and pulses haptics', () => {
      const actions = mockActions();
      const pulse = vi.fn();
      const { result: r } = render({ actions, pulse });
      act(() => r.current.handleDoubleTapTimeout(2));
      expect(pulse).toHaveBeenCalledWith('confirm');
      expect(actions.addTimeout).toHaveBeenCalledWith(2, true);
    });
  });

  // ------------------------------------------------------------------
  // pointPickerTeam state
  // ------------------------------------------------------------------
  describe('pointPickerTeam', () => {
    it('starts null', () => {
      const { result: r } = render();
      expect(r.current.pointPickerTeam).toBeNull();
    });

    it('can be closed via setPointPickerTeam(null)', () => {
      const actions = mockActions();
      const settings = mockSettings({ trackPointTypes: true });
      const { result: r } = render({ actions, settings });
      act(() => r.current.handleAddPoint(1));
      expect(r.current.pointPickerTeam).toBe(1);
      act(() => r.current.setPointPickerTeam(null));
      expect(r.current.pointPickerTeam).toBeNull();
    });
  });

  // ------------------------------------------------------------------
  // Callback stability (inputsRef pattern)
  //
  // The handlers go into BoardActionsContext, whose memoized value must not
  // change just because a WebSocket push updated the score. That requires
  // two properties at once: the identities stay put across re-renders, and
  // the bodies still read the *current* inputs through inputsRef. A
  // regression in either direction is a real bug, so both are asserted.
  // ------------------------------------------------------------------
  describe('callback stability through inputsRef', () => {
    it('keeps every handler identity stable when the inputs change', () => {
      const { result: r, update } = render();
      const before = r.current;

      update({
        actions: mockActions(),
        settings: mockSettings({ autoSimple: true, trackPointTypes: true }),
        simpleMode: true,
        matchFinished: true,
        pulse: vi.fn(),
      });

      // Guard against a vacuous pass: the hook really did re-render.
      expect(r.current).not.toBe(before);
      expect(r.current.commitPoint).toBe(before.commitPoint);
      expect(r.current.handleAddPoint).toBe(before.handleAddPoint);
      expect(r.current.handleAddSet).toBe(before.handleAddSet);
      expect(r.current.handleAddTimeout).toBe(before.handleAddTimeout);
      expect(r.current.handleChangeServe).toBe(before.handleChangeServe);
      expect(r.current.handleDoubleTapScore).toBe(before.handleDoubleTapScore);
      expect(r.current.handleDoubleTapTimeout).toBe(before.handleDoubleTapTimeout);
      expect(r.current.setPointPickerTeam).toBe(before.setPointPickerTeam);
    });

    it('routes through to the replacement actions object, not the captured one', () => {
      const first = mockActions();
      const { result: r, update } = render({ actions: first });
      const second = mockActions();

      update({ actions: second });
      act(() => r.current.handleAddPoint(1));

      expect(first.addPoint).not.toHaveBeenCalled();
      expect(second.addPoint).toHaveBeenCalledWith(1, false, undefined, undefined);
    });

    it('reads up-to-date matchFinished from ref on subsequent renders', () => {
      const actions = mockActions();
      const { result: r, update } = render({ actions });

      act(() => r.current.handleAddPoint(1));
      expect(actions.addPoint).toHaveBeenCalledTimes(1);

      asMock(actions.addPoint).mockClear();
      update({ matchFinished: true });

      act(() => r.current.handleAddPoint(1));
      expect(actions.addPoint).not.toHaveBeenCalled();
    });

    it('reads up-to-date autoSimple from ref on subsequent renders', () => {
      const actions = mockActions();
      const { result: r, update } = render({ actions });

      act(() => r.current.commitPoint(1));
      expect(actions.setSimpleMode).not.toHaveBeenCalled();

      update({ settings: mockSettings({ autoSimple: true }) });

      act(() => r.current.commitPoint(2));
      expect(actions.setSimpleMode).toHaveBeenCalledWith(true);
    });
  });
});
