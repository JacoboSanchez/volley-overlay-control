import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import { useSwipeNavigation } from '../hooks/useSwipeNavigation';

interface HarnessProps {
  onSwipeLeft?: () => void;
  onSwipeRight?: () => void;
  threshold?: number;
  maxVerticalRatio?: number;
}

function Harness({ onSwipeLeft, onSwipeRight, threshold, maxVerticalRatio }: HarnessProps) {
  const handlers = useSwipeNavigation({ onSwipeLeft, onSwipeRight, threshold, maxVerticalRatio });
  return (
    <div data-testid="surface" style={{ width: 400, height: 400 }} {...handlers}>
      <button data-testid="inner-button" type="button">Tap me</button>
      <span data-testid="plain-area">empty</span>
    </div>
  );
}

function touch(target: Element, x: number, y: number) {
  return { clientX: x, clientY: y, target } as unknown as Touch;
}

describe('useSwipeNavigation', () => {
  it('fires onSwipeLeft when finger moves left far enough', () => {
    const onSwipeLeft = vi.fn();
    const onSwipeRight = vi.fn();
    const { getByTestId } = render(<Harness onSwipeLeft={onSwipeLeft} onSwipeRight={onSwipeRight} />);
    const surface = getByTestId('plain-area');

    fireEvent.touchStart(surface, { touches: [touch(surface, 300, 200)] });
    fireEvent.touchEnd(surface, { changedTouches: [touch(surface, 100, 210)] });

    expect(onSwipeLeft).toHaveBeenCalledTimes(1);
    expect(onSwipeRight).not.toHaveBeenCalled();
  });

  it('fires onSwipeRight when finger moves right far enough', () => {
    const onSwipeLeft = vi.fn();
    const onSwipeRight = vi.fn();
    const { getByTestId } = render(<Harness onSwipeLeft={onSwipeLeft} onSwipeRight={onSwipeRight} />);
    const surface = getByTestId('plain-area');

    fireEvent.touchStart(surface, { touches: [touch(surface, 50, 200)] });
    fireEvent.touchEnd(surface, { changedTouches: [touch(surface, 250, 195)] });

    expect(onSwipeRight).toHaveBeenCalledTimes(1);
    expect(onSwipeLeft).not.toHaveBeenCalled();
  });

  it('ignores swipes that do not exceed the threshold', () => {
    const onSwipeLeft = vi.fn();
    const { getByTestId } = render(<Harness onSwipeLeft={onSwipeLeft} threshold={120} />);
    const surface = getByTestId('plain-area');

    fireEvent.touchStart(surface, { touches: [touch(surface, 200, 200)] });
    fireEvent.touchEnd(surface, { changedTouches: [touch(surface, 130, 200)] });

    expect(onSwipeLeft).not.toHaveBeenCalled();
  });

  it('ignores mostly-vertical gestures (treated as scrolling)', () => {
    const onSwipeLeft = vi.fn();
    const onSwipeRight = vi.fn();
    const { getByTestId } = render(<Harness onSwipeLeft={onSwipeLeft} onSwipeRight={onSwipeRight} />);
    const surface = getByTestId('plain-area');

    fireEvent.touchStart(surface, { touches: [touch(surface, 200, 100)] });
    fireEvent.touchEnd(surface, { changedTouches: [touch(surface, 100, 350)] });

    expect(onSwipeLeft).not.toHaveBeenCalled();
    expect(onSwipeRight).not.toHaveBeenCalled();
  });

  it('does not trigger when the gesture starts on a button', () => {
    const onSwipeLeft = vi.fn();
    const { getByTestId } = render(<Harness onSwipeLeft={onSwipeLeft} />);
    const button = getByTestId('inner-button');

    fireEvent.touchStart(button, { touches: [touch(button, 300, 200)] });
    fireEvent.touchEnd(button, { changedTouches: [touch(button, 50, 200)] });

    expect(onSwipeLeft).not.toHaveBeenCalled();
  });

  it('cancels gesture detection when a second touch begins', () => {
    const onSwipeLeft = vi.fn();
    const { getByTestId } = render(<Harness onSwipeLeft={onSwipeLeft} />);
    const surface = getByTestId('plain-area');

    fireEvent.touchStart(surface, { touches: [touch(surface, 300, 200), touch(surface, 250, 200)] });
    fireEvent.touchEnd(surface, { changedTouches: [touch(surface, 50, 200)] });

    expect(onSwipeLeft).not.toHaveBeenCalled();
  });
});
