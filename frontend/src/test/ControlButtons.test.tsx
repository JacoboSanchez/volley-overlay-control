import { describe, it, expect, vi } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import { I18nProvider } from '../i18n';
import { SettingsProvider } from '../hooks/useSettings';
import ControlButtons from '../components/ControlButtons';
import { renderWithI18n } from './helpers';

const defaultProps = {
  visible: true,
  simpleMode: false,
  canUndo: true,
  showPreview: false,
  matchStartedAt: null as number | null,
  matchFinished: false,
  onToggleVisibility: vi.fn(),
  onToggleSimpleMode: vi.fn(),
  onUndoLast: vi.fn(),
  onTogglePreview: vi.fn(),
  onStartMatch: vi.fn(),
  onReset: vi.fn(),
};

describe('ControlButtons', () => {
  it('renders the in-game control buttons', () => {
    renderWithI18n(<ControlButtons {...defaultProps} />);
    expect(screen.getByTestId('visibility-button')).toBeInTheDocument();
    expect(screen.getByTestId('simple-mode-button')).toBeInTheDocument();
    expect(screen.getByTestId('undo-button')).toBeInTheDocument();
    expect(screen.getByTestId('preview-button')).toBeInTheDocument();
  });

  it('calls onToggleVisibility when visibility button clicked', () => {
    renderWithI18n(<ControlButtons {...defaultProps} />);
    fireEvent.click(screen.getByTestId('visibility-button'));
    expect(defaultProps.onToggleVisibility).toHaveBeenCalledOnce();
  });

  it('calls onToggleSimpleMode when simple mode button clicked', () => {
    renderWithI18n(<ControlButtons {...defaultProps} />);
    fireEvent.click(screen.getByTestId('simple-mode-button'));
    expect(defaultProps.onToggleSimpleMode).toHaveBeenCalledOnce();
  });

  it('calls onUndoLast when undo button clicked and canUndo', () => {
    renderWithI18n(<ControlButtons {...defaultProps} />);
    fireEvent.click(screen.getByTestId('undo-button'));
    expect(defaultProps.onUndoLast).toHaveBeenCalledOnce();
  });

  it('disables undo button when canUndo is false', () => {
    const onUndoLast = vi.fn();
    renderWithI18n(
      <ControlButtons {...defaultProps} canUndo={false} onUndoLast={onUndoLast} />
    );
    const btn = screen.getByTestId('undo-button') as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
    fireEvent.click(btn);
    expect(onUndoLast).not.toHaveBeenCalled();
  });

  it('always renders the undo icon (no redo toggle)', () => {
    renderWithI18n(<ControlButtons {...defaultProps} canUndo={true} />);
    expect(screen.getByTestId('undo-button')).toHaveTextContent('undo');
  });

  it('calls onTogglePreview when preview button clicked', () => {
    renderWithI18n(<ControlButtons {...defaultProps} />);
    fireEvent.click(screen.getByTestId('preview-button'));
    expect(defaultProps.onTogglePreview).toHaveBeenCalledOnce();
  });

  it('shows visibility icon based on visible prop', () => {
    const { rerender } = renderWithI18n(<ControlButtons {...defaultProps} visible={true} />);
    expect(screen.getByTestId('visibility-button')).toHaveTextContent('visibility');

    rerender(
      <I18nProvider><SettingsProvider><ControlButtons {...defaultProps} visible={false} /></SettingsProvider></I18nProvider>
    );
    expect(screen.getByTestId('visibility-button')).toHaveTextContent('visibility_off');
  });

  it('preview button uses tv icon when showPreview is true', () => {
    renderWithI18n(<ControlButtons {...defaultProps} showPreview={true} />);
    expect(screen.getByTestId('preview-button')).toHaveTextContent('tv');
  });

  it('preview button uses tv_off icon when showPreview is false', () => {
    renderWithI18n(<ControlButtons {...defaultProps} showPreview={false} />);
    expect(screen.getByTestId('preview-button')).toHaveTextContent('tv_off');
  });

  // ── Theme + fullscreen relocated to the config panel ──────────────

  it('does not render theme/fullscreen buttons in the HUD', () => {
    renderWithI18n(<ControlButtons {...defaultProps} />);
    expect(screen.queryByTestId('dark-mode-button')).toBeNull();
    expect(screen.queryByTestId('fullscreen-button')).toBeNull();
  });

  // ── Start-match / Reset toggle ─────────────────────────────────────

  it('shows the Start-match button when match is unarmed', () => {
    renderWithI18n(<ControlButtons {...defaultProps} matchStartedAt={null} />);
    expect(screen.getByTestId('start-match-button')).toBeInTheDocument();
    expect(screen.queryByTestId('reset-button')).toBeNull();
  });

  it('shows the Reset button once the match is armed', () => {
    renderWithI18n(
      <ControlButtons {...defaultProps} matchStartedAt={1700000000} />,
    );
    expect(screen.getByTestId('reset-button')).toBeInTheDocument();
    expect(screen.queryByTestId('start-match-button')).toBeNull();
  });

  it('calls onStartMatch when Start-match button clicked', () => {
    const onStartMatch = vi.fn();
    renderWithI18n(
      <ControlButtons
        {...defaultProps}
        matchStartedAt={null}
        onStartMatch={onStartMatch}
      />,
    );
    fireEvent.click(screen.getByTestId('start-match-button'));
    expect(onStartMatch).toHaveBeenCalledOnce();
  });

  it('calls onReset when Reset button clicked', () => {
    const onReset = vi.fn();
    renderWithI18n(
      <ControlButtons
        {...defaultProps}
        matchStartedAt={1700000000}
        onReset={onReset}
      />,
    );
    fireEvent.click(screen.getByTestId('reset-button'));
    expect(onReset).toHaveBeenCalledOnce();
  });

  it('shows Reset (not Start) once the match is finished, even if matchStartedAt is null', () => {
    // Regression: ``_archive_if_finished`` clears
    // ``match_started_at`` to prep the next match, but the
    // operator still sees the just-played scoreboard. The next
    // required action is Reset, not Start — otherwise clicking
    // Start would arm a fresh timer over the visible (finished)
    // scores.
    renderWithI18n(
      <ControlButtons
        {...defaultProps}
        matchStartedAt={null}
        matchFinished={true}
      />,
    );
    expect(screen.getByTestId('reset-button')).toBeInTheDocument();
    expect(screen.queryByTestId('start-match-button')).toBeNull();
  });

  it('renders the start/reset button with a visible text label', () => {
    // The primary action sits on the left edge of the HUD with an
    // icon *and* text — ``ctrl.startMatch`` / ``ctrl.reset`` from
    // the i18n catalogue. Bare-icon mode is reserved for the
    // secondary toggles on the right.
    renderWithI18n(<ControlButtons {...defaultProps} matchStartedAt={null} />);
    const start = screen.getByTestId('start-match-button');
    expect(start.textContent).toMatch(/Start match/i);
  });

  // ── Match timer ────────────────────────────────────────────────────

  it('omits the match timer until the match is armed', () => {
    renderWithI18n(<ControlButtons {...defaultProps} matchStartedAt={null} />);
    expect(screen.queryByTestId('match-timer')).toBeNull();
  });

  it('renders the match timer once the match is armed', () => {
    renderWithI18n(
      <ControlButtons {...defaultProps} matchStartedAt={Date.now() / 1000} />,
    );
    expect(screen.getByTestId('match-timer')).toBeInTheDocument();
  });
});
