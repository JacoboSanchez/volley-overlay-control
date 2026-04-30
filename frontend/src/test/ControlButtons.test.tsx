import { describe, it, expect, vi } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import React from 'react';
import { I18nProvider } from '../i18n';
import { SettingsProvider } from '../hooks/useSettings';
import ControlButtons from '../components/ControlButtons';
import { renderWithI18n } from './helpers';

const defaultProps = {
  visible: true,
  simpleMode: false,
  canUndo: true,
  darkMode: true,
  isFullscreen: false,
  onToggleVisibility: vi.fn(),
  onToggleSimpleMode: vi.fn(),
  onUndoLast: vi.fn(),
  onToggleDarkMode: vi.fn(),
  onToggleFullscreen: vi.fn(),
  showPreview: false,
  onTogglePreview: vi.fn(),
};

describe('ControlButtons', () => {
  it('renders all control buttons', () => {
    renderWithI18n(<ControlButtons {...defaultProps} />);
    expect(screen.getByTestId('visibility-button')).toBeInTheDocument();
    expect(screen.getByTestId('simple-mode-button')).toBeInTheDocument();
    expect(screen.getByTestId('undo-button')).toBeInTheDocument();
    expect(screen.getByTestId('fullscreen-button')).toBeInTheDocument();
    expect(screen.getByTestId('dark-mode-button')).toBeInTheDocument();
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

  it('calls onToggleDarkMode when dark mode button clicked', () => {
    renderWithI18n(<ControlButtons {...defaultProps} />);
    fireEvent.click(screen.getByTestId('dark-mode-button'));
    expect(defaultProps.onToggleDarkMode).toHaveBeenCalledOnce();
  });

  it('calls onToggleFullscreen when fullscreen button clicked', () => {
    renderWithI18n(<ControlButtons {...defaultProps} />);
    fireEvent.click(screen.getByTestId('fullscreen-button'));
    expect(defaultProps.onToggleFullscreen).toHaveBeenCalledOnce();
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
    // When not visible, shows visibility_off
    expect(screen.getByTestId('visibility-button')).toHaveTextContent('visibility_off');
  });

  it('shows light_mode icon in dark mode', () => {
    renderWithI18n(<ControlButtons {...defaultProps} darkMode={true} />);
    expect(screen.getByTestId('dark-mode-button')).toHaveTextContent('light_mode');
  });

  it('shows dark_mode icon in light mode', () => {
    renderWithI18n(<ControlButtons {...defaultProps} darkMode={false} />);
    expect(screen.getByTestId('dark-mode-button')).toHaveTextContent('dark_mode');
  });

  it('shows brightness_auto icon when theme is auto', () => {
    renderWithI18n(<ControlButtons {...defaultProps} darkMode="auto" />);
    expect(screen.getByTestId('dark-mode-button')).toHaveTextContent('brightness_auto');
  });

  it('shows fullscreen_exit icon when fullscreen', () => {
    renderWithI18n(<ControlButtons {...defaultProps} isFullscreen={true} />);
    expect(screen.getByTestId('fullscreen-button')).toHaveTextContent('fullscreen_exit');
  });

  it('preview button uses tv icon when showPreview is true', () => {
    renderWithI18n(<ControlButtons {...defaultProps} showPreview={true} />);
    expect(screen.getByTestId('preview-button')).toHaveTextContent('tv');
  });

  it('preview button uses tv_off icon when showPreview is false', () => {
    renderWithI18n(<ControlButtons {...defaultProps} showPreview={false} />);
    expect(screen.getByTestId('preview-button')).toHaveTextContent('tv_off');
  });
});
