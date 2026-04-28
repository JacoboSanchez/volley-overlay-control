import { describe, it, expect } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useActionHistory } from '../hooks/useActionHistory';
import { ACTION_HISTORY_LIMIT } from '../constants';

describe('useActionHistory', () => {
  it('starts empty and not-undoable', () => {
    const { result } = renderHook(() => useActionHistory());
    expect(result.current.history).toEqual([]);
    expect(result.current.canUndo).toBe(false);
  });

  it('push appends entries and flips canUndo', () => {
    const { result } = renderHook(() => useActionHistory());
    act(() => result.current.push({ type: 'point', team: 1 }));
    expect(result.current.history).toEqual([{ type: 'point', team: 1 }]);
    expect(result.current.canUndo).toBe(true);
    act(() => result.current.push({ type: 'set', team: 2 }));
    expect(result.current.history).toEqual([
      { type: 'point', team: 1 },
      { type: 'set', team: 2 },
    ]);
  });

  it('undoLast pops the most recent entry and returns it', () => {
    const { result } = renderHook(() => useActionHistory());
    act(() => result.current.push({ type: 'point', team: 1 }));
    act(() => result.current.push({ type: 'timeout', team: 2 }));

    let popped: ReturnType<typeof result.current.undoLast> = null;
    act(() => { popped = result.current.undoLast(); });
    expect(popped).toEqual({ type: 'timeout', team: 2 });
    expect(result.current.history).toEqual([{ type: 'point', team: 1 }]);
  });

  it('undoLast returns null when empty', () => {
    const { result } = renderHook(() => useActionHistory());
    let popped: ReturnType<typeof result.current.undoLast> = { type: 'point', team: 1 };
    act(() => { popped = result.current.undoLast(); });
    expect(popped).toBeNull();
    expect(result.current.history).toEqual([]);
  });

  it('rapid sequential undoLast calls return distinct popped entries', () => {
    // Verifies the ref-mirroring contract: a second call before React
    // re-renders must still see the latest state and pop the second entry.
    const { result } = renderHook(() => useActionHistory());
    act(() => {
      result.current.push({ type: 'point', team: 1 });
      result.current.push({ type: 'set', team: 2 });
    });
    let firstPop: ReturnType<typeof result.current.undoLast> = null;
    let secondPop: ReturnType<typeof result.current.undoLast> = null;
    act(() => {
      firstPop = result.current.undoLast();
      secondPop = result.current.undoLast();
    });
    expect(firstPop).toEqual({ type: 'set', team: 2 });
    expect(secondPop).toEqual({ type: 'point', team: 1 });
    expect(result.current.history).toEqual([]);
  });

  it('popMatching removes the most recent entry matching type+team', () => {
    const { result } = renderHook(() => useActionHistory());
    act(() => {
      result.current.push({ type: 'point', team: 1 });
      result.current.push({ type: 'point', team: 2 });
      result.current.push({ type: 'point', team: 1 });
    });
    act(() => result.current.popMatching('point', 1));
    // Only the *most recent* matching entry is removed.
    expect(result.current.history).toEqual([
      { type: 'point', team: 1 },
      { type: 'point', team: 2 },
    ]);
  });

  it('popMatching is a no-op when no entry matches', () => {
    const { result } = renderHook(() => useActionHistory());
    act(() => result.current.push({ type: 'point', team: 1 }));
    act(() => result.current.popMatching('timeout', 2));
    expect(result.current.history).toEqual([{ type: 'point', team: 1 }]);
  });

  it('clear empties the stack', () => {
    const { result } = renderHook(() => useActionHistory());
    act(() => {
      result.current.push({ type: 'point', team: 1 });
      result.current.push({ type: 'set', team: 2 });
    });
    act(() => result.current.clear());
    expect(result.current.history).toEqual([]);
    expect(result.current.canUndo).toBe(false);
  });

  it('truncates at ACTION_HISTORY_LIMIT, evicting the oldest entry on overflow', () => {
    const { result } = renderHook(() => useActionHistory());
    act(() => {
      for (let i = 0; i < ACTION_HISTORY_LIMIT; i++) {
        result.current.push({ type: 'point', team: 1 });
      }
    });
    expect(result.current.history.length).toBe(ACTION_HISTORY_LIMIT);

    // Push one more — count stays at the cap, oldest entry is evicted.
    act(() => result.current.push({ type: 'set', team: 2 }));
    expect(result.current.history.length).toBe(ACTION_HISTORY_LIMIT);
    // The newly-pushed entry sits at the top.
    expect(result.current.history[result.current.history.length - 1])
      .toEqual({ type: 'set', team: 2 });
  });
});
