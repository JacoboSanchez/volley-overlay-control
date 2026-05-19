import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, fireEvent } from '@testing-library/react';
import {
  useKeyboardShortcuts,
  defaultKeyboardShortcutsEnabled,
  type KeyboardShortcutHandlers,
} from '../hooks/useKeyboardShortcuts';

interface HarnessProps extends KeyboardShortcutHandlers {
  enabled?: boolean;
  showInput?: boolean;
}

function Harness({ enabled = true, showInput, ...handlers }: HarnessProps) {
  useKeyboardShortcuts({ enabled, ...handlers });
  return (
    <div>
      {showInput && <input data-testid="text-input" type="text" />}
      <button data-testid="some-button" type="button">
        btn
      </button>
    </div>
  );
}

function press(key: string, options: KeyboardEventInit = {}) {
  fireEvent.keyDown(document, { key, ...options });
}

describe('useKeyboardShortcuts', () => {
  it('does not bind listeners when disabled', () => {
    const onAddPoint = vi.fn();
    render(<Harness enabled={false} onAddPoint={onAddPoint} />);
    press('a');
    expect(onAddPoint).not.toHaveBeenCalled();
  });

  it('routes A/B to onAddPoint with the right team', () => {
    const onAddPoint = vi.fn();
    render(<Harness onAddPoint={onAddPoint} />);
    press('a');
    press('B');
    expect(onAddPoint).toHaveBeenCalledTimes(2);
    expect(onAddPoint).toHaveBeenNthCalledWith(1, 1);
    expect(onAddPoint).toHaveBeenNthCalledWith(2, 2);
  });

  it('routes Z to onUndoLast', () => {
    const onUndoLast = vi.fn();
    render(<Harness onUndoLast={onUndoLast} />);
    press('z');
    expect(onUndoLast).toHaveBeenCalledTimes(1);
  });

  it('routes 1/2 to onChangeServe', () => {
    const onChangeServe = vi.fn();
    render(<Harness onChangeServe={onChangeServe} />);
    press('1');
    press('2');
    expect(onChangeServe).toHaveBeenCalledTimes(2);
    expect(onChangeServe).toHaveBeenNthCalledWith(1, 1);
    expect(onChangeServe).toHaveBeenNthCalledWith(2, 2);
  });

  it('routes Q/P to onAddTimeout', () => {
    const onAddTimeout = vi.fn();
    render(<Harness onAddTimeout={onAddTimeout} />);
    press('q');
    press('P');
    expect(onAddTimeout).toHaveBeenCalledTimes(2);
    expect(onAddTimeout).toHaveBeenNthCalledWith(1, 1);
    expect(onAddTimeout).toHaveBeenNthCalledWith(2, 2);
  });

  it('routes Space to onStartMatch when bound', () => {
    const onStartMatch = vi.fn();
    render(<Harness onStartMatch={onStartMatch} />);
    press(' ');
    expect(onStartMatch).toHaveBeenCalledTimes(1);
  });

  it('routes H to onToggleVisibility and S to onToggleSimpleMode', () => {
    const onToggleVisibility = vi.fn();
    const onToggleSimpleMode = vi.fn();
    render(
      <Harness onToggleVisibility={onToggleVisibility} onToggleSimpleMode={onToggleSimpleMode} />,
    );
    press('h');
    press('s');
    expect(onToggleVisibility).toHaveBeenCalledTimes(1);
    expect(onToggleSimpleMode).toHaveBeenCalledTimes(1);
  });

  it('routes ? to onOpenHelp', () => {
    const onOpenHelp = vi.fn();
    render(<Harness onOpenHelp={onOpenHelp} />);
    press('?');
    expect(onOpenHelp).toHaveBeenCalledTimes(1);
  });

  it('ignores keystrokes coming from text inputs', () => {
    const onAddPoint = vi.fn();
    const { getByTestId } = render(<Harness onAddPoint={onAddPoint} showInput />);
    const input = getByTestId('text-input') as HTMLInputElement;
    input.focus();
    fireEvent.keyDown(input, { key: 'a' });
    expect(onAddPoint).not.toHaveBeenCalled();
  });

  it('ignores keystrokes with modifier keys held', () => {
    const onAddPoint = vi.fn();
    render(<Harness onAddPoint={onAddPoint} />);
    press('a', { ctrlKey: true });
    press('a', { metaKey: true });
    press('a', { altKey: true });
    expect(onAddPoint).not.toHaveBeenCalled();
  });

  it('ignores key repeats (auto-repeat hold)', () => {
    const onAddPoint = vi.fn();
    render(<Harness onAddPoint={onAddPoint} />);
    press('a', { repeat: true });
    expect(onAddPoint).not.toHaveBeenCalled();
  });

  it('ignores keys without registered handlers', () => {
    // No handler bound → the key press just falls through, no exceptions.
    expect(() => {
      render(<Harness />);
      press('a');
      press('z');
    }).not.toThrow();
  });

  it('uses the latest handler reference without re-binding listeners', () => {
    const first = vi.fn();
    const second = vi.fn();
    const { rerender } = render(<Harness onAddPoint={first} />);
    press('a');
    rerender(<Harness onAddPoint={second} />);
    press('a');
    expect(first).toHaveBeenCalledTimes(1);
    expect(second).toHaveBeenCalledTimes(1);
  });

  it('removes the listener when disabled mid-life', () => {
    const onAddPoint = vi.fn();
    const { rerender } = render(<Harness enabled onAddPoint={onAddPoint} />);
    rerender(<Harness enabled={false} onAddPoint={onAddPoint} />);
    press('a');
    expect(onAddPoint).not.toHaveBeenCalled();
  });
});

describe('defaultKeyboardShortcutsEnabled', () => {
  let originalMatchMedia: typeof window.matchMedia | undefined;

  beforeEach(() => {
    originalMatchMedia = window.matchMedia;
  });

  afterEach(() => {
    if (originalMatchMedia) {
      Object.defineProperty(window, 'matchMedia', {
        configurable: true,
        value: originalMatchMedia,
      });
    }
  });

  it('returns false on coarse-pointer devices', () => {
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: (q: string) => ({ matches: q.includes('coarse') }) as MediaQueryList,
    });
    expect(defaultKeyboardShortcutsEnabled()).toBe(false);
  });

  it('returns true on fine-pointer devices', () => {
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: () => ({ matches: false }) as MediaQueryList,
    });
    expect(defaultKeyboardShortcutsEnabled()).toBe(true);
  });

  it('returns true when matchMedia throws', () => {
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: () => {
        throw new Error('boom');
      },
    });
    expect(defaultKeyboardShortcutsEnabled()).toBe(true);
  });
});
