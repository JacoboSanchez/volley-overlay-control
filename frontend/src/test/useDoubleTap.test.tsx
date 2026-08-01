import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useDoubleTap } from '../hooks/useDoubleTap';
import type { UseDoubleTapOptions } from '../hooks/useDoubleTap';
import { DOUBLE_TAP_MS, LONG_PRESS_MS } from '../constants';

function mouseDown(): React.MouseEvent<HTMLElement> {
  return new MouseEvent('mousedown', { bubbles: true }) as unknown as React.MouseEvent<HTMLElement>;
}

function mouseUp(): React.MouseEvent<HTMLElement> {
  return new MouseEvent('mouseup', { bubbles: true }) as unknown as React.MouseEvent<HTMLElement>;
}

function touchStart(): React.TouchEvent<HTMLElement> {
  return new TouchEvent('touchstart', {
    bubbles: true,
    touches: [{ identifier: 0, target: document.body, clientX: 0, clientY: 0 } as unknown as Touch],
  }) as unknown as React.TouchEvent<HTMLElement>;
}

function touchEnd(): React.TouchEvent<HTMLElement> {
  return new TouchEvent('touchend', {
    bubbles: true,
    touches: [],
  }) as unknown as React.TouchEvent<HTMLElement>;
}

function keyDown(key: string, repeat = false): React.KeyboardEvent<HTMLElement> {
  return new KeyboardEvent('keydown', { key, repeat, bubbles: true }) as unknown as React.KeyboardEvent<HTMLElement>;
}

function keyUp(key: string): React.KeyboardEvent<HTMLElement> {
  return new KeyboardEvent('keyup', { key, bubbles: true }) as unknown as React.KeyboardEvent<HTMLElement>;
}

function render(options: UseDoubleTapOptions = {}) {
  return renderHook((opts: UseDoubleTapOptions = options) => useDoubleTap(opts), {
    initialProps: options,
  });
}

describe('useDoubleTap', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  // ------------------------------------------------------------------
  // No onDoubleTap — onClick fires immediately on press-end
  // ------------------------------------------------------------------
  describe('single-tap only (no onDoubleTap)', () => {
    it('fires onClick immediately on mouseUp', () => {
      const onClick = vi.fn();
      const { result } = render({ onClick });
      result.current.onMouseDown(mouseDown());
      result.current.onMouseUp(mouseUp());
      expect(onClick).toHaveBeenCalledOnce();
    });

    it('fires onClick immediately on touchend', () => {
      const onClick = vi.fn();
      const { result } = render({ onClick });
      result.current.onTouchStart(touchStart());
      result.current.onTouchEnd(touchEnd());
      // touchActive cleared after 50ms setTimeout
      act(() => vi.advanceTimersByTime(50));
      expect(onClick).toHaveBeenCalledOnce();
    });

    it('fires onClick immediately on Enter keydown/keyup', () => {
      const onClick = vi.fn();
      const { result } = render({ onClick });
      result.current.onKeyDown(keyDown('Enter'));
      result.current.onKeyUp(keyUp('Enter'));
      expect(onClick).toHaveBeenCalledOnce();
    });

    it('fires onClick immediately on Space keydown/keyup', () => {
      const onClick = vi.fn();
      const { result } = render({ onClick });
      result.current.onKeyDown(keyDown(' '));
      result.current.onKeyUp(keyUp(' '));
      expect(onClick).toHaveBeenCalledOnce();
    });
  });

  // ------------------------------------------------------------------
  // Double-tap detection (at press-start)
  // ------------------------------------------------------------------
  describe('double-tap', () => {
    it('detects double tap on second mousedown within window', () => {
      const onClick = vi.fn();
      const onDoubleTap = vi.fn();
      const { result } = render({ onClick, onDoubleTap });

      result.current.onMouseDown(mouseDown());
      result.current.onMouseUp(mouseUp());

      act(() => vi.advanceTimersByTime(150));
      result.current.onMouseDown(mouseDown());
      result.current.onMouseUp(mouseUp());

      expect(onDoubleTap).toHaveBeenCalledOnce();
      expect(onClick).not.toHaveBeenCalled();
    });

    it('fires single tap after double-tap window expires', () => {
      const onClick = vi.fn();
      const onDoubleTap = vi.fn();
      const { result } = render({ onClick, onDoubleTap });

      result.current.onMouseDown(mouseDown());
      result.current.onMouseUp(mouseUp());

      act(() => vi.advanceTimersByTime(DOUBLE_TAP_MS + 10));
      expect(onClick).toHaveBeenCalledOnce();
      expect(onDoubleTap).not.toHaveBeenCalled();
    });

    it('treats slow second tap as a new first tap', () => {
      const onClick = vi.fn();
      const onDoubleTap = vi.fn();
      const { result } = render({ onClick, onDoubleTap });

      result.current.onMouseDown(mouseDown());
      result.current.onMouseUp(mouseUp());
      act(() => vi.advanceTimersByTime(DOUBLE_TAP_MS + 10));
      expect(onClick).toHaveBeenCalledOnce();

      result.current.onMouseDown(mouseDown());
      result.current.onMouseUp(mouseUp());
      act(() => vi.advanceTimersByTime(DOUBLE_TAP_MS + 10));
      expect(onClick).toHaveBeenCalledTimes(2);
      expect(onDoubleTap).not.toHaveBeenCalled();
    });

    it('keyboard double tap on Enter', () => {
      const onClick = vi.fn();
      const onDoubleTap = vi.fn();
      const { result } = render({ onClick, onDoubleTap });

      result.current.onKeyDown(keyDown('Enter'));
      result.current.onKeyUp(keyUp('Enter'));

      act(() => vi.advanceTimersByTime(100));
      result.current.onKeyDown(keyDown('Enter'));
      result.current.onKeyUp(keyUp('Enter'));

      expect(onDoubleTap).toHaveBeenCalledOnce();
      expect(onClick).not.toHaveBeenCalled();
    });
  });

  // ------------------------------------------------------------------
  // Long-press detection
  // ------------------------------------------------------------------
  describe('long-press', () => {
    it('fires onLongPress after hold duration', () => {
      const onLongPress = vi.fn();
      const onClick = vi.fn();
      const { result } = render({ onClick, onLongPress });

      result.current.onMouseDown(mouseDown());
      act(() => vi.advanceTimersByTime(LONG_PRESS_MS));
      result.current.onMouseUp(mouseUp());

      expect(onLongPress).toHaveBeenCalledOnce();
      expect(onClick).not.toHaveBeenCalled();
    });

    it('does not fire onLongPress if released before threshold', () => {
      const onLongPress = vi.fn();
      const onClick = vi.fn();
      const { result } = render({ onClick, onLongPress });

      result.current.onMouseDown(mouseDown());
      act(() => vi.advanceTimersByTime(LONG_PRESS_MS - 100));
      result.current.onMouseUp(mouseUp());

      expect(onLongPress).not.toHaveBeenCalled();
      expect(onClick).toHaveBeenCalledOnce();
    });

    it('long-press suppresses single tap even when onDoubleTap is set', () => {
      const onLongPress = vi.fn();
      const onClick = vi.fn();
      const onDoubleTap = vi.fn();
      const { result } = render({ onClick, onDoubleTap, onLongPress });

      result.current.onMouseDown(mouseDown());
      act(() => vi.advanceTimersByTime(LONG_PRESS_MS));
      result.current.onMouseUp(mouseUp());

      expect(onLongPress).toHaveBeenCalledOnce();
      expect(onClick).not.toHaveBeenCalled();
      expect(onDoubleTap).not.toHaveBeenCalled();
    });

    it('long-press overrides pending double-tap', () => {
      const onLongPress = vi.fn();
      const onClick = vi.fn();
      const onDoubleTap = vi.fn();
      const { result } = render({ onClick, onDoubleTap, onLongPress });

      result.current.onMouseDown(mouseDown());
      result.current.onMouseUp(mouseUp());

      act(() => vi.advanceTimersByTime(100));
      result.current.onMouseDown(mouseDown());
      act(() => vi.advanceTimersByTime(LONG_PRESS_MS));
      result.current.onMouseUp(mouseUp());

      expect(onLongPress).toHaveBeenCalledOnce();
      expect(onDoubleTap).not.toHaveBeenCalled();
    });

    it('respects custom longPressMs', () => {
      const onLongPress = vi.fn();
      const { result } = render({ onLongPress, longPressMs: 500 });

      result.current.onMouseDown(mouseDown());
      act(() => vi.advanceTimersByTime(400));
      result.current.onMouseUp(mouseUp());
      expect(onLongPress).not.toHaveBeenCalled();

      result.current.onMouseDown(mouseDown());
      act(() => vi.advanceTimersByTime(500));
      result.current.onMouseUp(mouseUp());
      expect(onLongPress).toHaveBeenCalledOnce();
    });

    it('respects custom doubleTapMs', () => {
      const onClick = vi.fn();
      const onDoubleTap = vi.fn();
      const { result } = render({ onClick, onDoubleTap, doubleTapMs: 500 });

      result.current.onMouseDown(mouseDown());
      result.current.onMouseUp(mouseUp());

      act(() => vi.advanceTimersByTime(300));
      result.current.onMouseDown(mouseDown());
      result.current.onMouseUp(mouseUp());
      expect(onDoubleTap).toHaveBeenCalledOnce();
    });
  });

  // ------------------------------------------------------------------
  // Gesture priority: long-press > double-tap > single-tap
  // ------------------------------------------------------------------
  describe('gesture priority', () => {
    it('long-press wins over double-tap when all three are provided', () => {
      const onClick = vi.fn();
      const onDoubleTap = vi.fn();
      const onLongPress = vi.fn();
      const { result } = render({ onClick, onDoubleTap, onLongPress });

      result.current.onMouseDown(mouseDown());
      result.current.onMouseUp(mouseUp());

      act(() => vi.advanceTimersByTime(100));
      result.current.onMouseDown(mouseDown());
      act(() => vi.advanceTimersByTime(LONG_PRESS_MS));
      result.current.onMouseUp(mouseUp());

      expect(onLongPress).toHaveBeenCalledOnce();
      expect(onDoubleTap).not.toHaveBeenCalled();
      expect(onClick).not.toHaveBeenCalled();
    });

    it('double-tap wins over single-tap', () => {
      const onClick = vi.fn();
      const onDoubleTap = vi.fn();
      const { result } = render({ onClick, onDoubleTap });

      result.current.onMouseDown(mouseDown());
      result.current.onMouseUp(mouseUp());

      act(() => vi.advanceTimersByTime(100));
      result.current.onMouseDown(mouseDown());
      result.current.onMouseUp(mouseUp());

      expect(onDoubleTap).toHaveBeenCalledOnce();
      expect(onClick).not.toHaveBeenCalled();
    });
  });

  // ------------------------------------------------------------------
  // Concurrent-input guards
  // ------------------------------------------------------------------
  describe('concurrent input guards', () => {
    it('touch blocks mouse after touchstart', () => {
      const onClick = vi.fn();
      const { result } = render({ onClick });

      result.current.onTouchStart(touchStart());

      result.current.onMouseDown(mouseDown());
      result.current.onMouseUp(mouseUp());

      result.current.onTouchEnd(touchEnd());
      act(() => vi.advanceTimersByTime(50));

      expect(onClick).toHaveBeenCalledOnce();
    });

    it('touchActive cleared after 50ms debounce on touchend', () => {
      const onClick = vi.fn();
      const { result } = render({ onClick });

      result.current.onTouchStart(touchStart());
      result.current.onTouchEnd(touchEnd());
      expect(onClick).toHaveBeenCalledOnce();

      onClick.mockClear();
      result.current.onMouseDown(mouseDown());
      result.current.onMouseUp(mouseUp());
      expect(onClick).not.toHaveBeenCalled();

      act(() => vi.advanceTimersByTime(50));
      result.current.onMouseDown(mouseDown());
      result.current.onMouseUp(mouseUp());
      expect(onClick).toHaveBeenCalledOnce();
    });

    it('mouse is not blocked when no touch active', () => {
      const onClick = vi.fn();
      const { result } = render({ onClick });

      result.current.onMouseDown(mouseDown());
      result.current.onMouseUp(mouseUp());
      expect(onClick).toHaveBeenCalledOnce();
    });

    it('keyboard repeat events are ignored', () => {
      const onClick = vi.fn();
      const { result } = render({ onClick });

      result.current.onKeyDown(keyDown('Enter', false));
      result.current.onKeyDown(keyDown('Enter', true));
      result.current.onKeyDown(keyDown('Enter', true));
      result.current.onKeyUp(keyUp('Enter'));
      expect(onClick).toHaveBeenCalledOnce();
    });

    it('keyUp without prior keyDown is ignored', () => {
      const onClick = vi.fn();
      const { result } = render({ onClick });

      result.current.onKeyUp(keyUp('Enter'));
      expect(onClick).not.toHaveBeenCalled();
    });

    it('ignores non-Enter/non-Space keys', () => {
      const onClick = vi.fn();
      const { result } = render({ onClick });

      result.current.onKeyDown(keyDown('a'));
      result.current.onKeyUp(keyUp('a'));
      expect(onClick).not.toHaveBeenCalled();
    });
  });

  // ------------------------------------------------------------------
  // Cancel press (mouseLeave / touchMove / touchCancel)
  // ------------------------------------------------------------------
  describe('cancel press', () => {
    it('mouseLeave cancels long-press timer', () => {
      const onLongPress = vi.fn();
      const { result } = render({ onLongPress });

      result.current.onMouseDown(mouseDown());
      result.current.onMouseLeave(mouseUp());

      act(() => vi.advanceTimersByTime(LONG_PRESS_MS + 100));
      expect(onLongPress).not.toHaveBeenCalled();
    });

    it('touchMove cancels long-press and clears touchActive', () => {
      const onLongPress = vi.fn();
      const onClick = vi.fn();
      const { result } = render({ onClick, onLongPress });

      result.current.onTouchStart(touchStart());
      result.current.onTouchMove(
        new TouchEvent('touchmove', { bubbles: true, touches: [] }) as unknown as React.TouchEvent<HTMLElement>,
      );
      act(() => vi.advanceTimersByTime(LONG_PRESS_MS + 100));
      expect(onLongPress).not.toHaveBeenCalled();

      result.current.onMouseDown(mouseDown());
      result.current.onMouseUp(mouseUp());
      expect(onClick).toHaveBeenCalledOnce();
    });

    it('mouseLeave cancels in-flight long-press but not already-scheduled single tap', () => {
      const onClick = vi.fn();
      const onDoubleTap = vi.fn();
      const { result } = render({ onClick, onDoubleTap });

      result.current.onMouseDown(mouseDown());
      result.current.onMouseUp(mouseUp());

      act(() => vi.advanceTimersByTime(50));
      result.current.onMouseLeave(mouseUp());

      act(() => vi.advanceTimersByTime(DOUBLE_TAP_MS + 100));
      expect(onClick).toHaveBeenCalledOnce();
      expect(onDoubleTap).not.toHaveBeenCalled();
    });
  });

  // ------------------------------------------------------------------
  // Cleanup
  // ------------------------------------------------------------------
  describe('cleanup', () => {
    it('clears timers on unmount', () => {
      const onLongPress = vi.fn();
      const onClick = vi.fn();
      const { result, unmount } = render({ onClick, onLongPress });

      result.current.onMouseDown(mouseDown());
      unmount();

      act(() => vi.advanceTimersByTime(LONG_PRESS_MS + 100));
      expect(onLongPress).not.toHaveBeenCalled();
    });
  });

  // ------------------------------------------------------------------
  // Defensive: concurrent press paths
  // ------------------------------------------------------------------
  describe('defensive concurrent press paths', () => {
    it('a second press-start clears the first long-press timer', () => {
      const onLongPress = vi.fn();
      const { result } = render({ onLongPress });

      result.current.onMouseDown(mouseDown());
      act(() => vi.advanceTimersByTime(200));

      result.current.onKeyDown(keyDown('Enter'));
      act(() => vi.advanceTimersByTime(LONG_PRESS_MS));

      expect(onLongPress).toHaveBeenCalledOnce();
    });
  });
});