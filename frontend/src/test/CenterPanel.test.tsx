import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import CenterPanel from '../components/CenterPanel';
import { mockCustomization, renderWithBoard } from './helpers';

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
});
