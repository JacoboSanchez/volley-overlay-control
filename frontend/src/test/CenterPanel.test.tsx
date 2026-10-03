import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import CenterPanel from '../components/CenterPanel';
import { BoardContextProvider } from '../board/BoardContexts';
import {
  boardContextValues,
  mockCustomization,
  mockGameState,
  renderWithBoard,
  renderWithI18n,
} from './helpers';

const overlayPreview = {
  overlayUrl: 'https://my-app.example/overlay/tok',
  x: 0,
  y: 0,
  width: 30,
  height: 10,
  layoutId: 'auto',
};
const recapOnAir = { ...mockGameState, set_summary: true, set_summary_set_num: 2 };

describe('CenterPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('renders team 1 and team 2 set buttons', () => {
    renderWithBoard(<CenterPanel />, { state: { currentSet: 2 } });
    expect(screen.getByTestId('team-1-sets')).toHaveTextContent('1');
    expect(screen.getByTestId('team-2-sets')).toHaveTextContent('0');
  });

  it('calls onAddSet when set buttons are pressed', () => {
    const onAddSet = vi.fn();
    renderWithBoard(<CenterPanel />, { actions: { onAddSet } });
    // ScoreButton uses mouseDown/mouseUp instead of click.
    const btn1 = screen.getByTestId('team-1-sets');
    fireEvent.mouseDown(btn1);
    fireEvent.mouseUp(btn1);
    expect(onAddSet).toHaveBeenCalledWith(1);

    const btn2 = screen.getByTestId('team-2-sets');
    fireEvent.mouseDown(btn2);
    fireEvent.mouseUp(btn2);
    expect(onAddSet).toHaveBeenCalledWith(2);
  });

  it('does not render the legacy set selector', () => {
    renderWithBoard(<CenterPanel />);
    expect(screen.queryByTestId('set-selector')).not.toBeInTheDocument();
  });

  it('renders the current set indicator with the active set number in landscape', () => {
    renderWithBoard(<CenterPanel />, {
      state: { currentSet: 3 },
      layout: { isPortrait: false },
    });
    const indicators = screen.getAllByTestId('current-set-indicator');
    expect(indicators).toHaveLength(1);
    expect(indicators[0]).toHaveTextContent('3');
  });

  it('renders the current set indicator with the active set number in portrait', () => {
    renderWithBoard(<CenterPanel />, {
      state: { currentSet: 4 },
      layout: { isPortrait: true },
    });
    const indicators = screen.getAllByTestId('current-set-indicator');
    expect(indicators).toHaveLength(1);
    expect(indicators[0]).toHaveTextContent('4');
  });

  it('shows logos in landscape mode when logos are provided', () => {
    renderWithBoard(<CenterPanel />, {
      theme: { iconLogoA: 'logo1.png', iconLogoB: 'logo2.png' },
      layout: { isPortrait: false },
    });
    expect(screen.getByTestId('team-1-logo')).toHaveAttribute('src', 'logo1.png');
    expect(screen.getByTestId('team-2-logo')).toHaveAttribute('src', 'logo2.png');
  });

  it('uses localized fallback team names for logo alt text', () => {
    localStorage.setItem('volley_lang', 'es');
    renderWithBoard(<CenterPanel />, {
      state: { customization: null },
      theme: { iconLogoA: 'logo1.png', iconLogoB: 'logo2.png' },
      layout: { isPortrait: false },
    });
    expect(screen.getByTestId('team-1-logo')).toHaveAttribute('alt', 'Equipo 1');
    expect(screen.getByTestId('team-2-logo')).toHaveAttribute('alt', 'Equipo 2');
  });

  it('hides logos when they are turned off, regardless of the customization', () => {
    // The resolved theme values are null when the operator turns logos off;
    // CentrePanel must not fall back to the raw customization URLs.
    const customization = {
      ...mockCustomization,
      'Team 1 Logo': 'logo1.png',
      'Team 2 Logo': 'logo2.png',
    };
    renderWithBoard(<CenterPanel />, { state: { customization } });
    expect(screen.queryByTestId('team-1-logo')).not.toBeInTheDocument();
    expect(screen.queryByTestId('team-2-logo')).not.toBeInTheDocument();
  });

  it('hides score section in portrait mode', () => {
    renderWithBoard(<CenterPanel />, { layout: { isPortrait: true } });
    expect(screen.queryByTestId('team-1-logo')).not.toBeInTheDocument();
  });

  it('does not render logos when the resolved logo URLs are empty', () => {
    renderWithBoard(<CenterPanel />);
    expect(screen.queryByTestId('team-1-logo')).not.toBeInTheDocument();
    expect(screen.queryByTestId('team-2-logo')).not.toBeInTheDocument();
  });

  it('applies the compact modifier when compactLandscape is true', () => {
    const { container } = renderWithBoard(<CenterPanel />, {
      layout: { compactLandscape: true },
    });
    expect(container.querySelector('.center-panel-compact')).not.toBeNull();
  });

  it('omits the compact modifier by default', () => {
    const { container } = renderWithBoard(<CenterPanel />);
    expect(container.querySelector('.center-panel-compact')).toBeNull();
  });

  it('renders the points history strip when no preview is provided', () => {
    const recentEvents = [
      { ts: 1, team: 1 as const, kind: 'point_add' as const },
      { ts: 2, team: 2 as const, kind: 'point_add' as const },
    ];
    renderWithBoard(<CenterPanel />, { state: { recentEvents } });
    expect(screen.getByTestId('points-history-strip')).toBeInTheDocument();
    expect(screen.getByTestId('phs-chip-1-0')).toHaveTextContent('+1');
    expect(screen.getByTestId('phs-chip-2-1')).toHaveTextContent('+1');
  });

  it('does not render the points history strip when preview is provided', () => {
    const previewData = {
      overlayUrl: 'about:blank',
      x: 0,
      y: 0,
      width: 100,
      height: 50,
    };
    renderWithBoard(<CenterPanel />, { state: { previewData, showPreview: true } });
    expect(screen.queryByTestId('points-history-strip')).not.toBeInTheDocument();
  });

  describe('while the set recap is on air', () => {
    it('shows the full-frame overlay preview and the hide button, without the style picker', () => {
      const onToggleSetSummary = vi.fn();
      const { container } = renderWithBoard(<CenterPanel />, {
        state: { state: recapOnAir, previewData: overlayPreview, showPreview: true },
        actions: { onToggleSetSummary },
      });
      expect(screen.getByTestId('overlay-preview')).toBeInTheDocument();
      expect(container.querySelector('.preview-container-full')).not.toBeNull();
      expect(screen.queryByTestId('set-summary-notice-status')).not.toBeInTheDocument();
      expect(screen.queryByTestId('set-summary-style-picker')).not.toBeInTheDocument();
      expect(screen.queryByTestId('points-history-strip')).not.toBeInTheDocument();
      fireEvent.click(screen.getByTestId('set-summary-notice-deactivate'));
      expect(onToggleSetSummary).toHaveBeenCalledOnce();
    });

    it('shows the full-frame preview even when the scoreboard preview is off', () => {
      const { container } = renderWithBoard(<CenterPanel />, {
        state: { state: recapOnAir, previewData: overlayPreview, showPreview: false },
      });
      expect(container.querySelector('.preview-container-full')).not.toBeNull();
      expect(screen.queryByTestId('points-history-strip')).not.toBeInTheDocument();
    });

    it('falls back to the on-air status line when no preview is available', () => {
      renderWithBoard(<CenterPanel />, {
        state: { state: recapOnAir, previewData: null, showPreview: true },
      });
      expect(screen.queryByTestId('overlay-preview')).not.toBeInTheDocument();
      expect(screen.getByTestId('set-summary-notice-status')).toHaveTextContent('Showing set 2');
      expect(screen.getByTestId('set-summary-notice-deactivate')).toBeInTheDocument();
    });

    it('moves the hide button into the alerts row on landscape phones', () => {
      renderWithBoard(<CenterPanel />, {
        state: { state: recapOnAir, previewData: overlayPreview, showPreview: true },
        layout: { compactLandscape: true },
      });
      const notice = screen.getByTestId('set-summary-notice');
      expect(screen.getByTestId('match-alerts-row')).toContainElement(notice);
      expect(notice).toHaveClass('set-summary-notice-inline');
      expect(screen.getAllByTestId('set-summary-notice-deactivate')).toHaveLength(1);
    });

    it('keeps the hide button under the preview outside landscape phones', () => {
      renderWithBoard(<CenterPanel />, {
        state: { state: recapOnAir, previewData: overlayPreview, showPreview: true },
      });
      const notice = screen.getByTestId('set-summary-notice');
      expect(screen.getByTestId('match-alerts-row')).not.toContainElement(notice);
      expect(notice).not.toHaveClass('set-summary-notice-inline');
    });

    it('keeps the same preview iframe when the recap comes and goes', () => {
      const ui = (gameState: typeof mockGameState) => (
        <BoardContextProvider
          {...boardContextValues({
            state: { state: gameState, previewData: overlayPreview, showPreview: true },
          })}
        >
          <CenterPanel />
        </BoardContextProvider>
      );
      const { container, rerender } = renderWithI18n(ui(mockGameState));
      const iframe = screen.getByTestId('overlay-preview');
      expect(container.querySelector('.preview-container-full')).toBeNull();

      rerender(ui(recapOnAir));
      expect(screen.getByTestId('overlay-preview')).toBe(iframe);
      expect(container.querySelector('.preview-container-full')).not.toBeNull();

      rerender(ui(mockGameState));
      expect(screen.getByTestId('overlay-preview')).toBe(iframe);
      expect(container.querySelector('.preview-container-full')).toBeNull();
      expect(screen.queryByTestId('set-summary-notice')).not.toBeInTheDocument();
    });
  });
});
