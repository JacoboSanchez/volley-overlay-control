import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useDoubleTap } from '../hooks/useDoubleTap';
import type { UseDoubleTapOptions } from '../hooks/useDoubleTap';
import { DOUBLE_TAP_MS, LONG_PRESS_MS } from '../constants';

// Real DOM events, cast to their React synthetic counterparts: the hook only
// reads ``type`` / ``key`` / ``repeat`` and calls ``preventDefault``, so the
// native event is a faithful stand-in. They are ``cancelable`` so tests can
// assert the default-suppression the hook promises (Space must not scroll).
function mouseDown(): React.MouseEvent<HTMLElement> {
  return new MouseEvent('mousedown', { bubbles: true }) as unknown as React.MouseEvent<HTMLElement>;
}

function mouseUp(): React.MouseEvent<HTMLElement> {
  return new MouseEvent('mouseup', { bubbles: true }) as unknown as React.MouseEvent<HTMLElement>;
}

function mouseLeave(): React.MouseEvent<HTMLElement> {
  return new MouseEvent('mouseleave', {
    bubbles: false,
  }) as unknown as React.MouseEvent<HTMLElement>;
}

function touchStart(): React.TouchEvent<HTMLElement> {
  return new TouchEvent('touchstart', {
    bubbles: true,
    cancelable: true,
    touches: [{ identifier: 0, target: document.body, clientX: 0, clientY: 0 } as unknown as Touch],
  }) as unknown as React.TouchEvent<HTMLElement>;
}

function touchEvent(type: 'touchend' | 'touchmove' | 'touchcancel'): React.TouchEvent<HTMLElement> {
  return new TouchEvent(type, {
    bubbles: true,
    cancelable: true,
    touches: [],
  }) as unknown as React.TouchEvent<HTMLElement>;
}

function keyDown(key: string, repeat = false): React.KeyboardEvent<HTMLElement> {
  return new KeyboardEvent('keydown', {
    key,
    repeat,
    bubbles: true,
    cancelable: true,
  }) as unknown as React.KeyboardEvent<HTMLElement>;
}

function keyUp(key: string): React.KeyboardEvent<HTMLElement> {
  return new KeyboardEvent('keyup', {
    key,
    bubbles: true,
    cancelable: true,
  }) as unknown as React.KeyboardEvent<HTMLElement>;
}

function render(options: UseDoubleTapOptions = {}) {
  return renderHook(() => useDoubleTap(options));
}

describe('useDoubleTap', () => {
  beforeEach(() => {
    // Fake timers also fake ``Date.now``, which the double-tap gap depends on.
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
      result.current.onTouchEnd(touchEvent('touchend'));
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
  // Browser default suppression
  // ------------------------------------------------------------------
  describe('default suppression', () => {
    it('preventDefaults Space so the page does not scroll under the button', () => {
      const { result } = render({ onClick: vi.fn() });
      const down = keyDown(' ');
      const up = keyUp(' ');
      result.current.onKeyDown(down);
      result.current.onKeyUp(up);
      expect((down as unknown as KeyboardEvent).defaultPrevented).toBe(true);
      expect((up as unknown as KeyboardEvent).defaultPrevented).toBe(true);
    });

    it('leaves unhandled keys alone', () => {
      const { result } = render({ onClick: vi.fn() });
      const down = keyDown('a');
      result.current.onKeyDown(down);
      expect((down as unknown as KeyboardEvent).defaultPrevented).toBe(false);
    });

    it('preventDefaults touchend so the browser emits no synthetic click', () => {
      const { result } = render({ onClick: vi.fn() });
      const end = touchEvent('touchend');
      result.current.onTouchStart(touchStart());
      result.current.onTouchEnd(end);
      expect((end as unknown as TouchEvent).defaultPrevented).toBe(true);
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
      // Double-tap wins over single-tap: the pending onClick is cancelled.
      expect(onClick).not.toHaveBeenCalled();
      act(() => vi.advanceTimersByTime(DOUBLE_TAP_MS + 10));
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

      // 300ms would be too slow for the default 280ms window.
      act(() => vi.advanceTimersByTime(300));
      result.current.onMouseDown(mouseDown());
      result.current.onMouseUp(mouseUp());
      expect(onDoubleTap).toHaveBeenCalledOnce();
      expect(onClick).not.toHaveBeenCalled();
    });
  });

  // ------------------------------------------------------------------
  // Gesture priority: long-press > double-tap > single-tap.
  // (double-tap > single-tap is asserted in the double-tap block above.)
  // ------------------------------------------------------------------
  describe('gesture priority', () => {
    it('long-press wins over a pending double-tap and the single tap', () => {
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

      result.current.onTouchEnd(touchEvent('touchend'));
      act(() => vi.advanceTimersByTime(50));

      // Only the touch path fired; the emulated mouse pair was swallowed.
      expect(onClick).toHaveBeenCalledOnce();
    });

    it('touchActive cleared after 50ms debounce on touchend', () => {
      const onClick = vi.fn();
      const { result } = render({ onClick });

      result.current.onTouchStart(touchStart());
      result.current.onTouchEnd(touchEvent('touchend'));
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
      result.current.onMouseLeave(mouseLeave());

      act(() => vi.advanceTimersByTime(LONG_PRESS_MS + 100));
      expect(onLongPress).not.toHaveBeenCalled();
    });

    it('touchMove cancels long-press and clears touchActive', () => {
      const onLongPress = vi.fn();
      const onClick = vi.fn();
      const { result } = render({ onClick, onLongPress });

      result.current.onTouchStart(touchStart());
      result.current.onTouchMove(touchEvent('touchmove'));
      act(() => vi.advanceTimersByTime(LONG_PRESS_MS + 100));
      expect(onLongPress).not.toHaveBeenCalled();

      // touchActive was released, so the mouse path works again immediately.
      result.current.onMouseDown(mouseDown());
      result.current.onMouseUp(mouseUp());
      expect(onClick).toHaveBeenCalledOnce();
    });

    it('touchCancel cancels the long-press timer', () => {
      const onLongPress = vi.fn();
      const { result } = render({ onLongPress });

      result.current.onTouchStart(touchStart());
      result.current.onTouchCancel(touchEvent('touchcancel'));

      act(() => vi.advanceTimersByTime(LONG_PRESS_MS + 100));
      expect(onLongPress).not.toHaveBeenCalled();
    });

    it('mouseLeave drops a pending double-tap but not an already-scheduled single tap', () => {
      const onClick = vi.fn();
      const onDoubleTap = vi.fn();
      const { result } = render({ onClick, onDoubleTap });

      result.current.onMouseDown(mouseDown());
      result.current.onMouseUp(mouseUp());

      act(() => vi.advanceTimersByTime(50));
      result.current.onMouseLeave(mouseLeave());

      act(() => vi.advanceTimersByTime(DOUBLE_TAP_MS + 100));
      expect(onClick).toHaveBeenCalledOnce();
      expect(onDoubleTap).not.toHaveBeenCalled();
    });
  });

  // ------------------------------------------------------------------
  // Cleanup
  // ------------------------------------------------------------------
  describe('cleanup', () => {
    it('clears the long-press timer on unmount', () => {
      const onLongPress = vi.fn();
      const onClick = vi.fn();
      const { result, unmount } = render({ onClick, onLongPress });

      result.current.onMouseDown(mouseDown());
      unmount();

      act(() => vi.advanceTimersByTime(LONG_PRESS_MS + 100));
      expect(onLongPress).not.toHaveBeenCalled();
    });

    it('clears the pending single-tap timer on unmount', () => {
      const onClick = vi.fn();
      const onDoubleTap = vi.fn();
      const { result, unmount } = render({ onClick, onDoubleTap });

      // A single tap leaves onClick scheduled for the length of the
      // double-tap window; unmounting inside it must not score a point on
      // a board the operator has already navigated away from.
      result.current.onMouseDown(mouseDown());
      result.current.onMouseUp(mouseUp());
      unmount();

      act(() => vi.advanceTimersByTime(DOUBLE_TAP_MS + 100));
      expect(onClick).not.toHaveBeenCalled();
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

      // Without the defensive clear the orphaned first timer would also
      // fire inside this window, making it two calls.
      expect(onLongPress).toHaveBeenCalledOnce();
    });
  });
});
