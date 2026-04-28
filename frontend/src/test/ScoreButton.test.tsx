import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import React from 'react';
import ScoreButton from '../components/ScoreButton';

describe('ScoreButton', () => {
  beforeEach(() => { vi.useFakeTimers(); });
  afterEach(() => { vi.useRealTimers(); });

  it('renders with score text', () => {
    render(<ScoreButton text="12" color="#2196f3" onClick={vi.fn()} data-testid="btn" />);
    expect(screen.getByTestId('btn')).toHaveTextContent('12');
  });

  it('applies background color and text color', () => {
    render(<ScoreButton text="05" color="#ff0000" textColor="#00ff00" onClick={vi.fn()} data-testid="btn" />);
    const btn = screen.getByTestId('btn');
    expect(btn.style.backgroundColor).toBe('rgb(255, 0, 0)');
    expect(btn.style.color).toBe('rgb(0, 255, 0)');
  });

  it('applies size as width and height', () => {
    render(<ScoreButton text="00" color="#000" size={200} onClick={vi.fn()} data-testid="btn" />);
    const btn = screen.getByTestId('btn');
    expect(btn.style.width).toBe('200px');
    expect(btn.style.height).toBe('200px');
  });

  it('calls onClick immediately when no onDoubleTap handler', () => {
    const onClick = vi.fn();
    render(<ScoreButton text="00" color="#000" onClick={onClick} data-testid="btn" />);
    fireEvent.mouseDown(screen.getByTestId('btn'));
    fireEvent.mouseUp(screen.getByTestId('btn'));
    expect(onClick).toHaveBeenCalledOnce();
  });

  it('calls onClick after delay when onDoubleTap is provided (single tap)', () => {
    const onClick = vi.fn();
    const onDoubleTap = vi.fn();
    render(<ScoreButton text="00" color="#000" onClick={onClick} onDoubleTap={onDoubleTap} data-testid="btn" />);
    fireEvent.mouseDown(screen.getByTestId('btn'));
    fireEvent.mouseUp(screen.getByTestId('btn'));
    // Not called yet — waiting for potential double tap
    expect(onClick).not.toHaveBeenCalled();
    act(() => { vi.advanceTimersByTime(400); });
    expect(onClick).toHaveBeenCalledOnce();
    expect(onDoubleTap).not.toHaveBeenCalled();
  });

  it('calls onDoubleTap on rapid double tap (detected at mousedown)', () => {
    const onClick = vi.fn();
    const onDoubleTap = vi.fn();
    render(<ScoreButton text="00" color="#000" onClick={onClick} onDoubleTap={onDoubleTap} data-testid="btn" />);
    const btn = screen.getByTestId('btn');
    // First tap
    fireEvent.mouseDown(btn);
    fireEvent.mouseUp(btn);
    // Second tap within 400ms — double-tap detected at mouseDown
    act(() => { vi.advanceTimersByTime(150); });
    fireEvent.mouseDown(btn);
    fireEvent.mouseUp(btn);
    expect(onDoubleTap).toHaveBeenCalledOnce();
    expect(onClick).not.toHaveBeenCalled();
  });

  it('does not fire onDoubleTap if second tap is too slow', () => {
    const onClick = vi.fn();
    const onDoubleTap = vi.fn();
    render(<ScoreButton text="00" color="#000" onClick={onClick} onDoubleTap={onDoubleTap} data-testid="btn" />);
    const btn = screen.getByTestId('btn');
    // First tap
    fireEvent.mouseDown(btn);
    fireEvent.mouseUp(btn);
    // Wait past the 400ms double-tap window
    act(() => { vi.advanceTimersByTime(450); });
    expect(onClick).toHaveBeenCalledOnce();
    // Second tap — treated as a new first tap
    fireEvent.mouseDown(btn);
    fireEvent.mouseUp(btn);
    act(() => { vi.advanceTimersByTime(400); });
    expect(onClick).toHaveBeenCalledTimes(2);
    expect(onDoubleTap).not.toHaveBeenCalled();
  });

  it('applies custom font family from fontStyle', () => {
    render(
      <ScoreButton text="00" color="#000" onClick={vi.fn()} data-testid="btn"
        fontStyle={{ fontFamily: "'Digital Dismay'", fontScale: 1.16, fontOffsetY: 0.01 }} />
    );
    expect(screen.getByTestId('btn').style.fontFamily).toContain('Digital Dismay');
  });

  it('keyboard: Enter key activates onClick (single tap)', () => {
    const onClick = vi.fn();
    const onDoubleTap = vi.fn();
    render(<ScoreButton text="00" color="#000" onClick={onClick} onDoubleTap={onDoubleTap} data-testid="btn" />);
    const btn = screen.getByTestId('btn');
    fireEvent.keyDown(btn, { key: 'Enter' });
    fireEvent.keyUp(btn, { key: 'Enter' });
    act(() => { vi.advanceTimersByTime(400); });
    expect(onClick).toHaveBeenCalledOnce();
    expect(onDoubleTap).not.toHaveBeenCalled();
  });

  it('keyboard: Space key activates onClick (single tap)', () => {
    const onClick = vi.fn();
    render(<ScoreButton text="00" color="#000" onClick={onClick} data-testid="btn" />);
    const btn = screen.getByTestId('btn');
    fireEvent.keyDown(btn, { key: ' ' });
    fireEvent.keyUp(btn, { key: ' ' });
    expect(onClick).toHaveBeenCalledOnce();
  });

  it('keyboard: rapid double-Enter triggers onDoubleTap', () => {
    const onClick = vi.fn();
    const onDoubleTap = vi.fn();
    render(<ScoreButton text="00" color="#000" onClick={onClick} onDoubleTap={onDoubleTap} data-testid="btn" />);
    const btn = screen.getByTestId('btn');
    fireEvent.keyDown(btn, { key: 'Enter' });
    fireEvent.keyUp(btn, { key: 'Enter' });
    act(() => { vi.advanceTimersByTime(100); });
    fireEvent.keyDown(btn, { key: 'Enter' });
    fireEvent.keyUp(btn, { key: 'Enter' });
    expect(onDoubleTap).toHaveBeenCalledOnce();
    expect(onClick).not.toHaveBeenCalled();
  });

  it('keyboard: Tab key (and other non-activation keys) is ignored', () => {
    const onClick = vi.fn();
    render(<ScoreButton text="00" color="#000" onClick={onClick} data-testid="btn" />);
    const btn = screen.getByTestId('btn');
    fireEvent.keyDown(btn, { key: 'Tab' });
    fireEvent.keyUp(btn, { key: 'Tab' });
    fireEvent.keyDown(btn, { key: 'a' });
    fireEvent.keyUp(btn, { key: 'a' });
    expect(onClick).not.toHaveBeenCalled();
  });

  it('keyboard: held Enter (repeat=true) does not stack the long-press timer', () => {
    const onClick = vi.fn();
    const onLongPress = vi.fn();
    render(<ScoreButton text="00" color="#000" onClick={onClick} onLongPress={onLongPress} data-testid="btn" />);
    const btn = screen.getByTestId('btn');
    fireEvent.keyDown(btn, { key: 'Enter' });
    // Browser repeats keydown while held; these shouldn't reset the timer.
    fireEvent.keyDown(btn, { key: 'Enter', repeat: true });
    fireEvent.keyDown(btn, { key: 'Enter', repeat: true });
    act(() => { vi.advanceTimersByTime(1100); });
    fireEvent.keyUp(btn, { key: 'Enter' });
    expect(onLongPress).toHaveBeenCalledOnce();
    expect(onClick).not.toHaveBeenCalled();
  });
});
