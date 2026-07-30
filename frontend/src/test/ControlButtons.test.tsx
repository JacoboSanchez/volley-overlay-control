import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import ControlButtons from '../components/ControlButtons';
import { mockGameState, renderWithBoard } from './helpers';
import type { GameState } from '../api/client';

function liveState(overrides: Partial<GameState> = {}): GameState {
  return { ...mockGameState, ...overrides };
}

describe('ControlButtons', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('renders the in-game control buttons', () => {
    renderWithBoard(<ControlButtons />);
    expect(screen.getByTestId('visibility-button')).toBeInTheDocument();
    expect(screen.getByTestId('simple-mode-button')).toBeInTheDocument();
    expect(screen.getByTestId('undo-button')).toBeInTheDocument();
    expect(screen.getByTestId('preview-button')).toBeInTheDocument();
  });

  it('calls the matching action for each primary toggle', () => {
    const onToggleVisibility = vi.fn();
    const onToggleSimpleMode = vi.fn();
    const onUndoLast = vi.fn();
    const onTogglePreview = vi.fn();
    renderWithBoard(<ControlButtons />, {
      state: { state: liveState({ can_undo: true }) },
      actions: { onToggleVisibility, onToggleSimpleMode, onUndoLast, onTogglePreview },
    });
    fireEvent.click(screen.getByTestId('visibility-button'));
    fireEvent.click(screen.getByTestId('simple-mode-button'));
    fireEvent.click(screen.getByTestId('undo-button'));
    fireEvent.click(screen.getByTestId('preview-button'));
    expect(onToggleVisibility).toHaveBeenCalledOnce();
    expect(onToggleSimpleMode).toHaveBeenCalledOnce();
    expect(onUndoLast).toHaveBeenCalledOnce();
    expect(onTogglePreview).toHaveBeenCalledOnce();
  });

  it('disables undo when no server-side action can be reversed', () => {
    const onUndoLast = vi.fn();
    renderWithBoard(<ControlButtons />, {
      state: { state: liveState({ can_undo: false }) },
      actions: { onUndoLast },
    });
    const button = screen.getByTestId('undo-button') as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    fireEvent.click(button);
    expect(onUndoLast).not.toHaveBeenCalled();
  });

  it('always renders the undo icon (no redo toggle)', () => {
    renderWithBoard(<ControlButtons />, { state: { state: liveState({ can_undo: true }) } });
    expect(screen.getByTestId('undo-button')).toHaveTextContent('undo');
  });

  it('does not render share / history buttons — both live in the top-right corner stack', () => {
    renderWithBoard(<ControlButtons />);
    expect(screen.queryByTestId('share-button')).toBeNull();
    expect(screen.queryByTestId('history-button')).toBeNull();
  });

  it('uses state and preferences for the visibility and preview button icons', () => {
    const { unmount } = renderWithBoard(<ControlButtons />, {
      state: { state: liveState({ visible: true }), showPreview: true },
    });
    expect(screen.getByTestId('visibility-button')).toHaveTextContent('visibility');
    expect(screen.getByTestId('preview-button')).toHaveTextContent('tv');
    unmount();

    renderWithBoard(<ControlButtons />, {
      state: { state: liveState({ visible: false }), showPreview: false },
    });
    expect(screen.getByTestId('visibility-button')).toHaveTextContent('visibility_off');
    expect(screen.getByTestId('preview-button')).toHaveTextContent('tv_off');
  });

  it('does not render theme/fullscreen buttons in the HUD', () => {
    renderWithBoard(<ControlButtons />);
    expect(screen.queryByTestId('dark-mode-button')).toBeNull();
    expect(screen.queryByTestId('fullscreen-button')).toBeNull();
  });

  it('shows Start-match before the match is armed and calls its action', () => {
    const onStartMatch = vi.fn();
    renderWithBoard(<ControlButtons />, {
      state: { state: liveState({ match_started_at: null }) },
      actions: { onStartMatch },
    });
    const start = screen.getByTestId('start-match-button');
    expect(start).toHaveTextContent(/Start match/i);
    expect(screen.queryByTestId('reset-button')).toBeNull();
    fireEvent.click(start);
    expect(onStartMatch).toHaveBeenCalledOnce();
  });

  it('shows Reset once the match is armed and calls its action', () => {
    const onReset = vi.fn();
    renderWithBoard(<ControlButtons />, {
      state: { state: liveState({ match_started_at: 1700000000 }) },
      actions: { onReset },
    });
    expect(screen.getByTestId('reset-button')).toBeInTheDocument();
    expect(screen.queryByTestId('start-match-button')).toBeNull();
    fireEvent.click(screen.getByTestId('reset-button'));
    expect(onReset).toHaveBeenCalledOnce();
  });

  it('shows Reset after a finished match even with no start timestamp', () => {
    renderWithBoard(<ControlButtons />, {
      state: { state: liveState({ match_started_at: null, match_finished: true }) },
    });
    expect(screen.getByTestId('reset-button')).toBeInTheDocument();
    expect(screen.queryByTestId('start-match-button')).toBeNull();
  });

  it('renders the match timer only once the match is armed', () => {
    const { unmount } = renderWithBoard(<ControlButtons />, {
      state: { state: liveState({ match_started_at: null }) },
    });
    expect(screen.queryByTestId('match-timer')).toBeNull();
    unmount();

    renderWithBoard(<ControlButtons />, {
      state: { state: liveState({ match_started_at: Date.now() / 1000 }) },
    });
    expect(screen.getByTestId('match-timer')).toBeInTheDocument();
  });

  it('shows the on-air badge only when enabled and clients are connected', () => {
    const { unmount } = renderWithBoard(<ControlButtons />, {
      state: { state: liveState({ obs_clients: 3 }), showOnAir: true },
    });
    expect(screen.getByTestId('onair-indicator')).toHaveTextContent('3');
    unmount();

    renderWithBoard(<ControlButtons />, {
      state: { state: liveState({ obs_clients: 5 }), showOnAir: false },
    });
    expect(screen.queryByTestId('onair-indicator')).toBeNull();
  });

  it('shows the report link only for a finished match when enabled', () => {
    const { unmount } = renderWithBoard(<ControlButtons />, {
      state: {
        state: liveState({ match_finished: true, last_match_id: 'match_abc_123' }),
        showReportLink: true,
      },
    });
    const link = screen.getByTestId('view-report-button') as HTMLAnchorElement;
    expect(link.getAttribute('href')).toContain('/match/match_abc_123/report');
    expect(link.getAttribute('target')).toBe('_blank');
    unmount();

    renderWithBoard(<ControlButtons />, {
      state: {
        state: liveState({ match_finished: true, last_match_id: 'match_abc_123' }),
        showReportLink: false,
      },
    });
    expect(screen.queryByTestId('view-report-button')).toBeNull();
  });

  it('localizes icon-only controls and exposes toggle state', () => {
    localStorage.setItem('volley_lang', 'es');
    const { container } = renderWithBoard(<ControlButtons />, {
      state: {
        state: liveState({ visible: true, set_summary: false }),
        simpleMode: true,
        showPreview: false,
        setSummaryEnabled: true,
      },
    });

    expect(screen.getByTestId('undo-button')).toHaveAccessibleName('Deshacer última acción');
    expect(screen.getByTestId('simple-mode-button')).toHaveAccessibleName('Marcador simple');
    expect(screen.getByTestId('simple-mode-button')).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByTestId('preview-button')).toHaveAccessibleName('Vista previa');
    expect(screen.getByTestId('preview-button')).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByTestId('visibility-button')).toHaveAccessibleName('Visibilidad del overlay');
    expect(screen.getByTestId('visibility-button')).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByTestId('set-summary-button')).toHaveAccessibleName(
      'Mostrar resumen del set en el overlay',
    );
    for (const icon of container.querySelectorAll('.material-icons')) {
      expect(icon).toHaveAttribute('aria-hidden', 'true');
    }
  });
});
