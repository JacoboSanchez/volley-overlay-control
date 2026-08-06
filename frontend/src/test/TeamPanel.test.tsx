import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { screen, fireEvent, act } from '@testing-library/react';
import TeamPanel from '../components/TeamPanel';
import type { GameState, TeamState } from '../api/board';
import { mockGameState, mockCustomization, renderWithBoard } from './helpers';

const baseTeamState: TeamState = {
  sets: 1,
  timeouts: 2,
  timeouts_by_set: { set_1: 1, set_2: 2 },
  serving: true,
  scores: { set_1: 25, set_2: 15 },
};

interface TeamPanelTestValues {
  teamId: 1 | 2;
  teamState: TeamState;
  currentSet: number;
  buttonColor: string;
  buttonTextColor: string;
  buttonSize: number;
  isPortrait: boolean;
  iconLogo: string | null;
  iconOpacity: number;
  state: GameState;
  setsLimit: number;
  customization: Record<string, unknown> | null;
  onAddPoint: (teamId: 1 | 2) => void;
  onAddTimeout: (teamId: 1 | 2) => void;
  onChangeServe: (teamId: 1 | 2) => void;
  onDoubleTapScore: (teamId: 1 | 2) => void;
  onDoubleTapTimeout: (teamId: 1 | 2) => void;
  onLongPressScore: (teamId: 1 | 2) => void;
}

const defaults: TeamPanelTestValues = {
  teamId: 1,
  teamState: baseTeamState,
  currentSet: 2,
  buttonColor: '#2196f3',
  buttonTextColor: '#ffffff',
  buttonSize: 150,
  isPortrait: false,
  iconLogo: null,
  iconOpacity: 50,
  state: mockGameState,
  setsLimit: 5,
  customization: mockCustomization,
  onAddPoint: vi.fn(),
  onAddTimeout: vi.fn(),
  onChangeServe: vi.fn(),
  onDoubleTapScore: vi.fn(),
  onDoubleTapTimeout: vi.fn(),
  onLongPressScore: vi.fn(),
};

function renderTeamPanel(overrides: Partial<TeamPanelTestValues> = {}) {
  const values = { ...defaults, ...overrides };
  const state = {
    ...values.state,
    [values.teamId === 1 ? 'team_1' : 'team_2']: values.teamState,
  } as GameState;
  return renderWithBoard(<TeamPanel teamId={values.teamId} />, {
    state: {
      state,
      customization: values.customization,
      currentSet: values.currentSet,
      setsLimit: values.setsLimit,
    },
    theme:
      values.teamId === 1
        ? {
            btnColorA: values.buttonColor,
            btnTextA: values.buttonTextColor,
            iconLogoA: values.iconLogo,
            iconOpacity: values.iconOpacity,
          }
        : {
            btnColorB: values.buttonColor,
            btnTextB: values.buttonTextColor,
            iconLogoB: values.iconLogo,
            iconOpacity: values.iconOpacity,
          },
    layout: { buttonSize: values.buttonSize, isPortrait: values.isPortrait },
    actions: {
      onAddPoint: values.onAddPoint,
      onAddTimeout: values.onAddTimeout,
      onChangeServe: values.onChangeServe,
      onDoubleTapScore: values.onDoubleTapScore,
      onDoubleTapTimeout: values.onDoubleTapTimeout,
      onLongPressScore: values.onLongPressScore,
    },
  });
}

describe('TeamPanel', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
    localStorage.clear();
  });

  it('renders score for current set', () => {
    renderTeamPanel();
    expect(screen.getByTestId('team-1-score')).toHaveTextContent('15');
  });

  it('renders timeout dots matching timeout count', () => {
    renderTeamPanel();
    expect(screen.getByTestId('timeout-1-number-0')).toBeInTheDocument();
    expect(screen.getByTestId('timeout-1-number-1')).toBeInTheDocument();
  });

  it('renders serve icon and dims it when the team is not serving', () => {
    const { unmount } = renderTeamPanel();
    const serve = screen.getByTestId('team-1-serve');
    expect(serve.style.opacity).toBe('1');
    expect(serve.querySelector<HTMLElement>('.material-icons')?.style.fontSize).toBe('2rem');
    unmount();

    renderTeamPanel({ teamState: { ...baseTeamState, serving: false } });
    expect(screen.getByTestId('team-1-serve').style.opacity).toBe('0.4');
  });

  it('calls onAddPoint when score button tapped once', () => {
    const onAddPoint = vi.fn();
    renderTeamPanel({ onAddPoint });
    fireEvent.mouseDown(screen.getByTestId('team-1-score'));
    fireEvent.mouseUp(screen.getByTestId('team-1-score'));
    act(() => vi.advanceTimersByTime(400));
    expect(onAddPoint).toHaveBeenCalledWith(1);
  });

  it('calls onDoubleTapScore on rapid double-tap', () => {
    const onDoubleTapScore = vi.fn();
    const onAddPoint = vi.fn();
    renderTeamPanel({ onAddPoint, onDoubleTapScore });
    const button = screen.getByTestId('team-1-score');
    fireEvent.mouseDown(button);
    fireEvent.mouseUp(button);
    act(() => vi.advanceTimersByTime(100));
    fireEvent.mouseDown(button);
    fireEvent.mouseUp(button);
    expect(onDoubleTapScore).toHaveBeenCalledWith(1);
    expect(onAddPoint).not.toHaveBeenCalled();
  });

  it('handles single and double taps on timeout controls', () => {
    const onAddTimeout = vi.fn();
    const { unmount } = renderTeamPanel({ onAddTimeout });
    const button = screen.getByTestId('team-1-timeout');
    fireEvent.mouseDown(button);
    fireEvent.mouseUp(button);
    act(() => vi.advanceTimersByTime(400));
    expect(onAddTimeout).toHaveBeenCalledWith(1);
    unmount();

    const onDoubleTapTimeout = vi.fn();
    renderTeamPanel({ onAddTimeout, onDoubleTapTimeout });
    const doubleTapButton = screen.getByTestId('team-1-timeout');
    fireEvent.mouseDown(doubleTapButton);
    fireEvent.mouseUp(doubleTapButton);
    act(() => vi.advanceTimersByTime(100));
    fireEvent.mouseDown(doubleTapButton);
    fireEvent.mouseUp(doubleTapButton);
    expect(onDoubleTapTimeout).toHaveBeenCalledWith(1);
  });

  it('supports keyboard activation of timeout controls', () => {
    const onAddTimeout = vi.fn();
    renderTeamPanel({ onAddTimeout });
    const button = screen.getByTestId('team-1-timeout');
    fireEvent.keyDown(button, { key: 'Enter' });
    fireEvent.keyUp(button, { key: 'Enter' });
    act(() => vi.advanceTimersByTime(400));
    expect(onAddTimeout).toHaveBeenCalledWith(1);
  });

  it('calls onChangeServe when serve icon clicked', () => {
    const onChangeServe = vi.fn();
    renderTeamPanel({ onChangeServe });
    fireEvent.click(screen.getByTestId('team-1-serve'));
    expect(onChangeServe).toHaveBeenCalledWith(1);
  });

  it('uses portrait and landscape layout classes', () => {
    const { container, unmount } = renderTeamPanel({ isPortrait: true });
    expect(container.querySelector('.team-panel-portrait')).toBeInTheDocument();
    unmount();
    const { container: landscape } = renderTeamPanel({ isPortrait: false });
    expect(landscape.querySelector('.team-panel-landscape')).toBeInTheDocument();
  });

  it('pads scores to two digits', () => {
    renderTeamPanel({ teamState: { ...baseTeamState, scores: { set_2: 3 } } });
    expect(screen.getByTestId('team-1-score')).toHaveTextContent('03');
  });

  it('uses only the resolved icon theme value in portrait mode', () => {
    const { unmount } = renderTeamPanel({
      isPortrait: true,
      iconLogo: null,
      customization: { 'Team 1 Logo': 'https://example.com/logo.png' },
    });
    expect(screen.queryByTestId('team-1-logo')).toBeNull();
    unmount();

    renderTeamPanel({ isPortrait: true, iconLogo: 'https://example.com/logo.png' });
    expect(screen.getByTestId('team-1-logo')).toHaveAttribute(
      'src',
      'https://example.com/logo.png',
    );
  });

  it('localizes scoring-control names and gesture descriptions', () => {
    localStorage.setItem('volley_lang', 'es');
    renderTeamPanel({
      isPortrait: true,
      iconLogo: 'https://example.com/logo.png',
      customization: { 'Team 1 Name': 'Lobos' },
    });

    expect(screen.getByTestId('team-1-score')).toHaveAccessibleName('Lobos, puntuación 15');
    expect(screen.getByTestId('team-1-score')).toHaveAccessibleDescription(
      'Toca para sumar un punto, toca dos veces para deshacer o mantén pulsado para establecer un valor.',
    );
    expect(screen.getByTestId('team-1-timeout')).toHaveAccessibleName('Lobos, tiempo muerto');
    expect(screen.getByTestId('team-1-timeout')).toHaveAccessibleDescription(
      'Toca para sumar un tiempo muerto o toca dos veces para deshacer.',
    );
    expect(screen.getByTestId('team-1-serve')).toHaveAccessibleName('Lobos, saque');
    expect(screen.getByTestId('team-1-logo')).toHaveAttribute('alt', 'Lobos');
  });
});
