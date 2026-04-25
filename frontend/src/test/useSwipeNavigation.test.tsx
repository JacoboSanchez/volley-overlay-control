import { describe, it, expect, vi } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import { DEFAULT_IGNORE_SELECTORS, useSwipeNavigation } from '../hooks/useSwipeNavigation';

interface HarnessProps {
  onSwipeLeft?: () => void;
  onSwipeRight?: () => void;
  threshold?: number;
  maxVerticalRatio?: number;
  innerNode?: React.ReactNode;
}

function Harness({ onSwipeLeft, onSwipeRight, threshold, maxVerticalRatio, innerNode }: HarnessProps) {
  const handlers = useSwipeNavigation({ onSwipeLeft, onSwipeRight, threshold, maxVerticalRatio });
  return (
    <div data-testid="surface" style={{ width: 400, height: 400 }} {...handlers}>
      <button data-testid="inner-button" type="button">Tap me</button>
      <span data-testid="plain-area">empty</span>
      {innerNode}
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

  it('rejects diagonal swipes where vertical motion exceeds half of horizontal motion', () => {
    const onSwipeLeft = vi.fn();
    const { getByTestId } = render(<Harness onSwipeLeft={onSwipeLeft} />);
    const surface = getByTestId('plain-area');

    // dx = -120, dy = 70 → ratio 0.58 > 0.5 default → ignored
    fireEvent.touchStart(surface, { touches: [touch(surface, 300, 100)] });
    fireEvent.touchEnd(surface, { changedTouches: [touch(surface, 180, 170)] });

    expect(onSwipeLeft).not.toHaveBeenCalled();
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

  it('cancels gesture detection on a second touch during move', () => {
    const onSwipeLeft = vi.fn();
    const { getByTestId } = render(<Harness onSwipeLeft={onSwipeLeft} />);
    const surface = getByTestId('plain-area');

    fireEvent.touchStart(surface, { touches: [touch(surface, 300, 200)] });
    fireEvent.touchMove(surface, { touches: [touch(surface, 280, 200), touch(surface, 200, 200)] });
    fireEvent.touchEnd(surface, { changedTouches: [touch(surface, 50, 200)] });

    expect(onSwipeLeft).not.toHaveBeenCalled();
  });

  it('does nothing on touchend without a prior touchstart', () => {
    const onSwipeLeft = vi.fn();
    const onSwipeRight = vi.fn();
    const { getByTestId } = render(<Harness onSwipeLeft={onSwipeLeft} onSwipeRight={onSwipeRight} />);
    const surface = getByTestId('plain-area');

    fireEvent.touchEnd(surface, { changedTouches: [touch(surface, 50, 200)] });

    expect(onSwipeLeft).not.toHaveBeenCalled();
    expect(onSwipeRight).not.toHaveBeenCalled();
  });

  it('clears pending gesture on touchcancel so a later end does not fire', () => {
    const onSwipeLeft = vi.fn();
    const { getByTestId } = render(<Harness onSwipeLeft={onSwipeLeft} />);
    const surface = getByTestId('plain-area');

    fireEvent.touchStart(surface, { touches: [touch(surface, 300, 200)] });
    fireEvent.touchCancel(surface, { changedTouches: [touch(surface, 300, 200)] });
    fireEvent.touchEnd(surface, { changedTouches: [touch(surface, 50, 200)] });

    expect(onSwipeLeft).not.toHaveBeenCalled();
  });

  describe('default ignore selectors', () => {
    const samples: Array<{ selector: string; html: React.ReactElement }> = [
      { selector: 'button', html: <button data-testid="t" type="button">b</button> },
      { selector: 'input', html: <input data-testid="t" type="range" min={0} max={10} readOnly /> },
      { selector: 'select', html: <select data-testid="t" defaultValue="a"><option value="a">a</option></select> },
      { selector: 'textarea', html: <textarea data-testid="t" defaultValue="" /> },
      { selector: 'a', html: <a data-testid="t" href="#x">link</a> },
      { selector: 'label', html: <label data-testid="t">lbl</label> },
      { selector: '[role="button"]', html: <div data-testid="t" role="button" tabIndex={0}>x</div> },
      { selector: '[role="slider"]', html: <div data-testid="t" role="slider" tabIndex={0} aria-valuenow={0}>x</div> },
      { selector: '[role="checkbox"]', html: <div data-testid="t" role="checkbox" tabIndex={0} aria-checked="false">x</div> },
      { selector: '[role="switch"]', html: <div data-testid="t" role="switch" tabIndex={0} aria-checked="false">x</div> },
      { selector: '[role="tab"]', html: <div data-testid="t" role="tab" tabIndex={0}>x</div> },
      { selector: '[role="menuitem"]', html: <div data-testid="t" role="menuitem" tabIndex={0}>x</div> },
      { selector: '[contenteditable="true"]', html: <div data-testid="t" contentEditable suppressContentEditableWarning>x</div> },
    ];

    it('covers every entry in DEFAULT_IGNORE_SELECTORS', () => {
      const covered = new Set(samples.map((s) => s.selector));
      for (const entry of DEFAULT_IGNORE_SELECTORS) {
        expect(covered.has(entry)).toBe(true);
      }
    });

    it.each(samples)('blocks swipe when gesture starts on $selector', ({ html }) => {
      const onSwipeLeft = vi.fn();
      const { getByTestId } = render(<Harness onSwipeLeft={onSwipeLeft} innerNode={html} />);
      const target = getByTestId('t');

      fireEvent.touchStart(target, { touches: [touch(target, 300, 200)] });
      fireEvent.touchEnd(target, { changedTouches: [touch(target, 50, 200)] });

      expect(onSwipeLeft).not.toHaveBeenCalled();
    });
  });
});
