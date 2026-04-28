import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import TeamPanel, { TeamPanelProps } from '../components/TeamPanel';
import type { components } from '../api/schema';
import { mockGameState } from './helpers';

type TeamState = components['schemas']['TeamState'];

const baseTeamState: TeamState = {
  sets: 1,
  timeouts: 2,
  serving: true,
  scores: { set_1: 25, set_2: 15 },
};

const defaultProps: TeamPanelProps = {
  teamId: 1,
  teamState: baseTeamState,
  currentSet: 2,
  buttonColor: '#2196f3',
  buttonTextColor: '#ffffff',
  serveColor: '#5c6bc0',
  timeoutColor: '#5c6bc0',
  buttonSize: 150,
  isPortrait: false,
  iconLogo: null,
  iconOpacity: 50,
  fontStyle: { fontFamily: undefined, fontScale: 1.0, fontOffsetY: 0.0 },
  state: mockGameState,
  setsLimit: 5,
  onAddPoint: vi.fn(),
  onAddTimeout: vi.fn(),
  onChangeServe: vi.fn(),
  onDoubleTapScore: vi.fn(),
  onDoubleTapTimeout: vi.fn(),
  onLongPressScore: vi.fn(),
};

describe('TeamPanel', () => {
  beforeEach(() => { vi.useFakeTimers(); });
  afterEach(() => { vi.useRealTimers(); });

  it('renders score for current set', () => {
    render(<TeamPanel {...defaultProps} />);
    // currentSet=2, scores.set_2=15, displayed as "15"
    expect(screen.getByTestId('team-1-score')).toHaveTextContent('15');
  });

  it('renders timeout dots matching timeout count', () => {
    render(<TeamPanel {...defaultProps} />);
    expect(screen.getByTestId('timeout-1-number-0')).toBeInTheDocument();
    expect(screen.getByTestId('timeout-1-number-1')).toBeInTheDocument();
  });

  it('renders serve icon', () => {
    render(<TeamPanel {...defaultProps} />);
    const serve = screen.getByTestId('team-1-serve');
    expect(serve).toBeInTheDocument();
    expect(serve.style.opacity).toBe('1');
  });

  it('renders serve icon dimmed when not serving', () => {
    render(<TeamPanel {...defaultProps} teamState={{ ...baseTeamState, serving: false }} />);
    expect(screen.getByTestId('team-1-serve').style.opacity).toBe('0.4');
  });

  it('calls onAddPoint when score button tapped once', () => {
    const onAddPoint = vi.fn();
    render(<TeamPanel {...defaultProps} onAddPoint={onAddPoint} />);
    fireEvent.mouseDown(screen.getByTestId('team-1-score'));
    fireEvent.mouseUp(screen.getByTestId('team-1-score'));
    act(() => { vi.advanceTimersByTime(400); });
    expect(onAddPoint).toHaveBeenCalledWith(1);
  });

  it('calls onDoubleTapScore on rapid double-tap', () => {
    const onDoubleTapScore = vi.fn();
    const onAddPoint = vi.fn();
    render(<TeamPanel {...defaultProps} onAddPoint={onAddPoint} onDoubleTapScore={onDoubleTapScore} />);
    const btn = screen.getByTestId('team-1-score');
    fireEvent.mouseDown(btn);
    fireEvent.mouseUp(btn);
    act(() => { vi.advanceTimersByTime(100); });
    fireEvent.mouseDown(btn);
    fireEvent.mouseUp(btn);
    expect(onDoubleTapScore).toHaveBeenCalledWith(1);
    expect(onAddPoint).not.toHaveBeenCalled();
  });

  it('calls onAddTimeout when timeout button tapped once', () => {
    const onAddTimeout = vi.fn();
    render(<TeamPanel {...defaultProps} onAddTimeout={onAddTimeout} />);
    const btn = screen.getByTestId('team-1-timeout');
    fireEvent.mouseDown(btn);
    fireEvent.mouseUp(btn);
    act(() => { vi.advanceTimersByTime(400); });
    expect(onAddTimeout).toHaveBeenCalledWith(1);
  });

  it('calls onDoubleTapTimeout on rapid double-tap of timeout button', () => {
    const onDoubleTapTimeout = vi.fn();
    const onAddTimeout = vi.fn();
    render(
      <TeamPanel
        {...defaultProps}
        onAddTimeout={onAddTimeout}
        onDoubleTapTimeout={onDoubleTapTimeout}
      />
    );
    const btn = screen.getByTestId('team-1-timeout');
    fireEvent.mouseDown(btn);
    fireEvent.mouseUp(btn);
    act(() => { vi.advanceTimersByTime(100); });
    fireEvent.mouseDown(btn);
    fireEvent.mouseUp(btn);
    expect(onDoubleTapTimeout).toHaveBeenCalledWith(1);
    expect(onAddTimeout).not.toHaveBeenCalled();
  });

  it('calls onChangeServe when serve icon clicked', () => {
    render(<TeamPanel {...defaultProps} />);
    fireEvent.click(screen.getByTestId('team-1-serve'));
    expect(defaultProps.onChangeServe).toHaveBeenCalledWith(1);
  });

  it('uses portrait layout classes when isPortrait', () => {
    const { container } = render(<TeamPanel {...defaultProps} isPortrait={true} />);
    expect(container.querySelector('.team-panel-portrait')).toBeInTheDocument();
  });

  it('uses landscape layout classes when not portrait', () => {
    const { container } = render(<TeamPanel {...defaultProps} isPortrait={false} />);
    expect(container.querySelector('.team-panel-landscape')).toBeInTheDocument();
  });

  it('pads score to two digits', () => {
    render(<TeamPanel {...defaultProps} teamState={{ ...baseTeamState, scores: { set_2: 3 } }} />);
    expect(screen.getByTestId('team-1-score')).toHaveTextContent('03');
  });
});
