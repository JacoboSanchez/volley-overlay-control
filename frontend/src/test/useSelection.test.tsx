import { describe, it, expect } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useSelection } from '../hooks/useSelection';

describe('useSelection', () => {
  it('toggles a single key on and off', () => {
    const { result } = renderHook(() => useSelection<number>());
    expect(result.current.size).toBe(0);
    act(() => result.current.toggle(3));
    expect(result.current.has(3)).toBe(true);
    expect(result.current.ids).toEqual([3]);
    act(() => result.current.toggle(3));
    expect(result.current.has(3)).toBe(false);
  });

  it('works with string keys as well as numeric ones', () => {
    const { result } = renderHook(() => useSelection<string>());
    act(() => result.current.toggle('match-a'));
    expect(result.current.ids).toEqual(['match-a']);
  });

  it('add/remove only touch the ids given, leaving the rest selected', () => {
    const { result } = renderHook(() => useSelection<number>());
    act(() => result.current.add([1, 2, 3]));
    act(() => result.current.add([3, 4]));
    expect(result.current.ids.sort()).toEqual([1, 2, 3, 4]);
    act(() => result.current.remove([2, 3]));
    expect(result.current.ids.sort()).toEqual([1, 4]);
  });

  it('toggleAll selects the subset, then clears it once all are selected', () => {
    const { result } = renderHook(() => useSelection<string>());
    act(() => result.current.add(['off-page']));
    act(() => result.current.toggleAll(['a', 'b']));
    expect(result.current.ids.sort()).toEqual(['a', 'b', 'off-page']);
    // A second toggle drops just the page, keeping the other page's selection.
    act(() => result.current.toggleAll(['a', 'b']));
    expect(result.current.ids).toEqual(['off-page']);
  });

  it('toggleAll on a partially selected subset selects the rest', () => {
    const { result } = renderHook(() => useSelection<string>());
    act(() => result.current.add(['a']));
    act(() => result.current.toggleAll(['a', 'b']));
    expect(result.current.ids.sort()).toEqual(['a', 'b']);
  });

  it('toggleAll on an empty subset is a no-op', () => {
    const { result } = renderHook(() => useSelection<string>());
    act(() => result.current.add(['a']));
    act(() => result.current.toggleAll([]));
    expect(result.current.ids).toEqual(['a']);
  });

  it('allSelected is false for an empty subset, someSelected reports overlap', () => {
    const { result } = renderHook(() => useSelection<number>());
    act(() => result.current.add([1]));
    expect(result.current.allSelected([])).toBe(false);
    expect(result.current.allSelected([1])).toBe(true);
    expect(result.current.allSelected([1, 2])).toBe(false);
    expect(result.current.someSelected([1, 2])).toBe(true);
    expect(result.current.someSelected([2, 3])).toBe(false);
  });

  it('selectedAmong keeps the caller order and drops hidden selections', () => {
    const { result } = renderHook(() => useSelection<number>());
    act(() => result.current.add([9, 1, 5]));
    expect(result.current.selectedAmong([5, 1, 2])).toEqual([5, 1]);
  });

  it('replace swaps the whole selection and clear empties it', () => {
    const { result } = renderHook(() => useSelection<number>());
    act(() => result.current.add([1, 2]));
    act(() => result.current.replace([7]));
    expect(result.current.ids).toEqual([7]);
    act(() => result.current.clear());
    expect(result.current.size).toBe(0);
  });

  it('keeps mutator identities stable across selection changes', () => {
    const { result } = renderHook(() => useSelection<number>());
    const { toggle, add, remove, toggleAll, replace, clear } = result.current;
    act(() => result.current.toggle(1));
    expect(result.current.toggle).toBe(toggle);
    expect(result.current.add).toBe(add);
    expect(result.current.remove).toBe(remove);
    expect(result.current.toggleAll).toBe(toggleAll);
    expect(result.current.replace).toBe(replace);
    expect(result.current.clear).toBe(clear);
  });
});
