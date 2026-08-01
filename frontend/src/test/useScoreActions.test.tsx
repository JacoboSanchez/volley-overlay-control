import { describe, it, expect, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useScoreActions } from '../hooks/useScoreActions';
import type { GameActions } from '../hooks/useGameState';
import type { Settings } from '../hooks/useSettings';
import type { HapticPattern } from '../hooks/useHaptics';

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
    ...overrides,
  };
}

function mockSettings(overrides: Partial<Settings> = {}): Settings {
  return {
    trackPointTypes: false,
    autoSimple: false,
    autoSimpleOnTimeout: false,
    ...overrides,
  } as Settings;
}

function mockPulse(): (pattern: HapticPattern | string) => void {
  return vi.fn();
}

function render({
  actions = mockActions(),
  settings = mockSettings(),
  simpleMode = false,
  matchFinished = false,
  pulse = mockPulse(),
}: {
  actions?: GameActions;
  settings?: Settings;
  simpleMode?: boolean;
  matchFinished?: boolean;
  pulse?: ReturnType<typeof mockPulse>;
} = {}) {
  return renderHook(
    ({ a, s, sm, mf, p }: {
      a: GameActions;
      s: Settings;
      sm: boolean;
      mf: boolean;
      p: (pattern: HapticPattern | string) => void;
    }) => useScoreActions({ actions: a, settings: s, simpleMode: sm, matchFinished: mf, pulse: p }),
    {
      initialProps: { a: actions, s: settings, sm: simpleMode, mf: matchFinished, p: pulse },
    },
  );
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
  // ------------------------------------------------------------------
  describe('callback stability through inputsRef', () => {
    it('reads up-to-date matchFinished from ref on subsequent renders', () => {
      const actions = mockActions();
      const pulse = vi.fn();
      const { result: r, rerender } = renderHook(
        ({ mf }: { mf: boolean }) =>
          useScoreActions({
            actions,
            settings: mockSettings(),
            simpleMode: false,
            matchFinished: mf,
            pulse,
          }),
        { initialProps: { mf: false } },
      );

      act(() => r.current.handleAddPoint(1));
      expect(actions.addPoint).toHaveBeenCalledTimes(1);

      (actions.addPoint as ReturnType<typeof vi.fn>).mockClear();
      rerender({ mf: true });

      act(() => r.current.handleAddPoint(1));
      expect(actions.addPoint).not.toHaveBeenCalled();
    });

    it('reads up-to-date autoSimple from ref on subsequent renders', () => {
      const actions = mockActions();
      const pulse = vi.fn();
      const { result: r, rerender } = renderHook(
        ({ autoSimple }: { autoSimple: boolean }) =>
          useScoreActions({
            actions,
            settings: mockSettings({ autoSimple }),
            simpleMode: false,
            matchFinished: false,
            pulse,
          }),
        { initialProps: { autoSimple: false } },
      );

      act(() => r.current.commitPoint(1));
      expect(actions.setSimpleMode).not.toHaveBeenCalled();

      (actions.addPoint as ReturnType<typeof vi.fn>).mockClear();
      (actions.setSimpleMode as ReturnType<typeof vi.fn>).mockClear();
      rerender({ autoSimple: true });

      act(() => r.current.commitPoint(2));
      expect(actions.setSimpleMode).toHaveBeenCalledWith(true);
    });
  });
});