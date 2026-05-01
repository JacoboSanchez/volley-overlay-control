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
  onAddSet: vi.fn(),
  onLongPressSet: vi.fn(),
  onSetChange: vi.fn(),
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

  it('renders set pagination with correct number of pages', () => {
    renderWithI18n(<CenterPanel {...defaultProps} />);
    const selector = screen.getByTestId('set-selector');
    // Should have 5 page buttons + 2 arrows
    const buttons = selector.querySelectorAll('button');
    expect(buttons).toHaveLength(7);
  });

  it('highlights current set in pagination', () => {
    renderWithI18n(<CenterPanel {...defaultProps} currentSet={3} />);
    const selector = screen.getByTestId('set-selector');
    const activePages = selector.querySelectorAll('.pagination-page-active');
    expect(activePages).toHaveLength(1);
    expect(activePages[0]).toHaveTextContent('3');
  });

  it('calls onSetChange when pagination button clicked', () => {
    renderWithI18n(<CenterPanel {...defaultProps} currentSet={2} />);
    const selector = screen.getByTestId('set-selector');
    const pageButtons = selector.querySelectorAll('.pagination-page');
    // Click page 4
    fireEvent.click(pageButtons[3]);
    expect(defaultProps.onSetChange).toHaveBeenCalledWith(4);
  });

  it('disables left arrow when on first set', () => {
    renderWithI18n(<CenterPanel {...defaultProps} currentSet={1} />);
    const selector = screen.getByTestId('set-selector');
    const arrows = selector.querySelectorAll('.pagination-arrow');
    expect(arrows[0]).toBeDisabled();
    expect(arrows[1]).not.toBeDisabled();
  });

  it('disables right arrow when on last set', () => {
    renderWithI18n(<CenterPanel {...defaultProps} currentSet={5} />);
    const selector = screen.getByTestId('set-selector');
    const arrows = selector.querySelectorAll('.pagination-arrow');
    expect(arrows[0]).not.toBeDisabled();
    expect(arrows[1]).toBeDisabled();
  });

  it('calls onSetChange with decremented value on left arrow click', () => {
    renderWithI18n(<CenterPanel {...defaultProps} currentSet={3} />);
    const selector = screen.getByTestId('set-selector');
    const arrows = selector.querySelectorAll('.pagination-arrow');
    fireEvent.click(arrows[0]);
    expect(defaultProps.onSetChange).toHaveBeenCalledWith(2);
  });

  it('calls onSetChange with incremented value on right arrow click', () => {
    renderWithI18n(<CenterPanel {...defaultProps} currentSet={3} />);
    const selector = screen.getByTestId('set-selector');
    const arrows = selector.querySelectorAll('.pagination-arrow');
    fireEvent.click(arrows[1]);
    expect(defaultProps.onSetChange).toHaveBeenCalledWith(4);
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

  it('hides the in-centre score tables when inlineScoreHistory is true (landscape compact)', () => {
    const cust = { ...mockCustomization, 'Team 1 Logo': 'logo1.png', 'Team 2 Logo': 'logo2.png' };
    const { container } = renderWithI18n(
      <CenterPanel
        {...defaultProps}
        customization={cust}
        isPortrait={false}
        inlineScoreHistory={true}
      />,
    );
    // The logos-scores-section is the wrapper for the per-team tables;
    // it should disappear when the tables are hosted by TeamPanel instead.
    expect(container.querySelector('.logos-scores-section')).toBeNull();
  });
});
