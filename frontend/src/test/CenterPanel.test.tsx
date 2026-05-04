import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import React from 'react';
import CenterPanel from '../components/CenterPanel';
import { renderWithI18n, mockGameState, mockCustomization } from './helpers';

const defaultProps = {
  state: mockGameState,
  customization: mockCustomization,
  currentSet: 2,
  setsLimit: 5,
  isPortrait: false,
  previewData: null,
  recentEvents: [],
  btnColorA: '#2196f3',
  btnTextA: '#ffffff',
  btnColorB: '#f44336',
  btnTextB: '#ffffff',
  onAddSet: vi.fn(),
  onLongPressSet: vi.fn(),
};

describe('CenterPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('returns null when state is null', () => {
    const { container } = renderWithI18n(<CenterPanel {...defaultProps} state={null} />);
    expect(container.innerHTML).toBe('');
  });

  it('renders team 1 and team 2 set buttons', () => {
    renderWithI18n(<CenterPanel {...defaultProps} />);
    expect(screen.getByTestId('team-1-sets')).toHaveTextContent('1');
    expect(screen.getByTestId('team-2-sets')).toHaveTextContent('0');
  });

  it('calls onAddSet when set buttons are pressed', () => {
    renderWithI18n(<CenterPanel {...defaultProps} />);
    // ScoreButton uses mouseDown/mouseUp instead of click
    const btn1 = screen.getByTestId('team-1-sets');
    fireEvent.mouseDown(btn1);
    fireEvent.mouseUp(btn1);
    expect(defaultProps.onAddSet).toHaveBeenCalledWith(1);

    const btn2 = screen.getByTestId('team-2-sets');
    fireEvent.mouseDown(btn2);
    fireEvent.mouseUp(btn2);
    expect(defaultProps.onAddSet).toHaveBeenCalledWith(2);
  });

  it('does not render the legacy set selector', () => {
    renderWithI18n(<CenterPanel {...defaultProps} />);
    expect(screen.queryByTestId('set-selector')).not.toBeInTheDocument();
  });

  it('renders the current set indicator with the active set number in landscape', () => {
    renderWithI18n(<CenterPanel {...defaultProps} currentSet={3} isPortrait={false} />);
    const indicators = screen.getAllByTestId('current-set-indicator');
    expect(indicators).toHaveLength(1);
    expect(indicators[0]).toHaveTextContent('3');
  });

  it('renders the current set indicator with the active set number in portrait', () => {
    renderWithI18n(<CenterPanel {...defaultProps} currentSet={4} isPortrait={true} />);
    const indicators = screen.getAllByTestId('current-set-indicator');
    expect(indicators).toHaveLength(1);
    expect(indicators[0]).toHaveTextContent('4');
  });

  it('shows logos in landscape mode when customization has logos', () => {
    const cust = { ...mockCustomization, 'Team 1 Logo': 'logo1.png', 'Team 2 Logo': 'logo2.png' };
    renderWithI18n(<CenterPanel {...defaultProps} customization={cust} isPortrait={false} />);
    expect(screen.getByTestId('team-1-logo')).toHaveAttribute('src', 'logo1.png');
    expect(screen.getByTestId('team-2-logo')).toHaveAttribute('src', 'logo2.png');
  });

  it('hides score section in portrait mode', () => {
    renderWithI18n(<CenterPanel {...defaultProps} isPortrait={true} />);
    expect(screen.queryByTestId('team-1-logo')).not.toBeInTheDocument();
  });

  it('does not render logos when customization has empty logo URLs', () => {
    renderWithI18n(<CenterPanel {...defaultProps} />);
    expect(screen.queryByTestId('team-1-logo')).not.toBeInTheDocument();
    expect(screen.queryByTestId('team-2-logo')).not.toBeInTheDocument();
  });

  it('applies the compact modifier when compactLandscape is true', () => {
    const { container } = renderWithI18n(
      <CenterPanel {...defaultProps} compactLandscape={true} />,
    );
    expect(container.querySelector('.center-panel-compact')).not.toBeNull();
  });

  it('omits the compact modifier by default', () => {
    const { container } = renderWithI18n(<CenterPanel {...defaultProps} />);
    expect(container.querySelector('.center-panel-compact')).toBeNull();
  });

  it('renders the points history strip when no preview is provided', () => {
    const events = [
      { ts: 1, team: 1 as const, kind: 'point_add' as const },
      { ts: 2, team: 2 as const, kind: 'point_add' as const },
    ];
    renderWithI18n(<CenterPanel {...defaultProps} previewData={null} recentEvents={events} />);
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
    const events = [{ ts: 1, team: 1 as const, kind: 'point_add' as const }];
    renderWithI18n(
      <CenterPanel {...defaultProps} previewData={previewData} recentEvents={events} />,
    );
    expect(screen.queryByTestId('points-history-strip')).not.toBeInTheDocument();
  });
});
