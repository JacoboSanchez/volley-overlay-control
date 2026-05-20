import { describe, it, expect, vi } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import ConfirmDialog from '../components/ConfirmDialog';
import { renderWithI18n } from './helpers';

describe('ConfirmDialog', () => {
  it('renders nothing when closed', () => {
    renderWithI18n(
      <ConfirmDialog
        open={false}
        message="Reset the match?"
        onConfirm={() => {}}
        onClose={() => {}}
      />,
    );
    expect(screen.queryByTestId('confirm-dialog-ok')).toBeNull();
  });

  it('shows the message and default labels when open', () => {
    renderWithI18n(
      <ConfirmDialog
        open={true}
        message="Reset the match?"
        onConfirm={() => {}}
        onClose={() => {}}
      />,
    );
    expect(screen.getByText('Reset the match?')).toBeInTheDocument();
    expect(screen.getByTestId('confirm-dialog-ok')).toHaveTextContent('Confirm');
    expect(screen.getByTestId('confirm-dialog-cancel')).toHaveTextContent('Cancel');
  });

  it('only calls onConfirm when OK is clicked — parent owns close', () => {
    // Decoupled from onClose so async confirm flows can keep the
    // dialog open (e.g. to show a loading state) until the parent
    // explicitly dismisses. Synchronous parents call onClose
    // themselves from inside the same handler.
    const onConfirm = vi.fn();
    const onClose = vi.fn();
    renderWithI18n(
      <ConfirmDialog open={true} message="Logout?" onConfirm={onConfirm} onClose={onClose} />,
    );
    fireEvent.click(screen.getByTestId('confirm-dialog-ok'));
    expect(onConfirm).toHaveBeenCalledOnce();
    expect(onClose).not.toHaveBeenCalled();
  });

  it('calls onClose only when Cancel is clicked', () => {
    const onConfirm = vi.fn();
    const onClose = vi.fn();
    renderWithI18n(
      <ConfirmDialog open={true} message="Logout?" onConfirm={onConfirm} onClose={onClose} />,
    );
    fireEvent.click(screen.getByTestId('confirm-dialog-cancel'));
    expect(onConfirm).not.toHaveBeenCalled();
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('uses the danger button style for destructive confirmations', () => {
    renderWithI18n(
      <ConfirmDialog
        open={true}
        message="Reset the match?"
        danger
        onConfirm={() => {}}
        onClose={() => {}}
      />,
    );
    const ok = screen.getByTestId('confirm-dialog-ok');
    expect(ok.className).toContain('dialog-btn-danger');
  });

  it('honours custom labels and title', () => {
    renderWithI18n(
      <ConfirmDialog
        open={true}
        title="Hold up"
        message="Really reset?"
        confirmLabel="Reset match"
        cancelLabel="Keep playing"
        onConfirm={() => {}}
        onClose={() => {}}
      />,
    );
    expect(screen.getByText('Hold up')).toBeInTheDocument();
    expect(screen.getByTestId('confirm-dialog-ok')).toHaveTextContent('Reset match');
    expect(screen.getByTestId('confirm-dialog-cancel')).toHaveTextContent('Keep playing');
  });
});
