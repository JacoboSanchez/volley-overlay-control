import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import Dialog from '../components/Dialog';

describe('Dialog', () => {
  it('renders nothing when closed', () => {
    render(
      <Dialog open={false} onClose={() => {}} ariaLabel="Test dialog">
        <p>Body</p>
      </Dialog>,
    );
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(screen.queryByText('Body')).toBeNull();
  });

  it('renders children with dialog a11y attributes when open', () => {
    render(
      <Dialog open onClose={() => {}} ariaLabel="Test dialog">
        <p>Body</p>
      </Dialog>,
    );
    const dialog = screen.getByRole('dialog');
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(dialog).toHaveAttribute('aria-label', 'Test dialog');
    expect(screen.getByText('Body')).toBeInTheDocument();
  });

  it('supports labelling via an existing element id', () => {
    render(
      <Dialog open onClose={() => {}} ariaLabelledBy="my-title">
        <h2 id="my-title">Named title</h2>
      </Dialog>,
    );
    expect(screen.getByRole('dialog')).toHaveAccessibleName('Named title');
  });

  it('focuses the dialog card on open', () => {
    render(
      <Dialog open onClose={() => {}} ariaLabel="Focus me">
        <p>Body</p>
      </Dialog>,
    );
    expect(document.activeElement).toBe(screen.getByRole('dialog'));
  });

  it('calls onClose on Escape', () => {
    const onClose = vi.fn();
    render(
      <Dialog open onClose={onClose} ariaLabel="Esc">
        <p>Body</p>
      </Dialog>,
    );
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('calls onClose when the backdrop is clicked', () => {
    const onClose = vi.fn();
    render(
      <Dialog open onClose={onClose} ariaLabel="Backdrop">
        <p>Body</p>
      </Dialog>,
    );
    fireEvent.click(screen.getByLabelText('Close dialog'));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('does not listen for Escape after closing', () => {
    const onClose = vi.fn();
    const { rerender } = render(
      <Dialog open onClose={onClose} ariaLabel="Esc">
        <p>Body</p>
      </Dialog>,
    );
    rerender(
      <Dialog open={false} onClose={onClose} ariaLabel="Esc">
        <p>Body</p>
      </Dialog>,
    );
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).not.toHaveBeenCalled();
  });

  it('traps Tab: wraps from the last focusable element to the first', () => {
    render(
      <Dialog open onClose={() => {}} ariaLabel="Trap">
        <button type="button">First</button>
        <button type="button">Last</button>
      </Dialog>,
    );
    screen.getByText('Last').focus();
    fireEvent.keyDown(document, { key: 'Tab' });
    expect(document.activeElement).toBe(screen.getByText('First'));
  });

  it('traps Shift+Tab: wraps from the card/first element to the last', () => {
    render(
      <Dialog open onClose={() => {}} ariaLabel="Trap">
        <button type="button">First</button>
        <button type="button">Last</button>
      </Dialog>,
    );
    // Card is focused on open — Shift+Tab from there lands on the last control.
    fireEvent.keyDown(document, { key: 'Tab', shiftKey: true });
    expect(document.activeElement).toBe(screen.getByText('Last'));
    // And again from the first control.
    screen.getByText('First').focus();
    fireEvent.keyDown(document, { key: 'Tab', shiftKey: true });
    expect(document.activeElement).toBe(screen.getByText('Last'));
  });

  it('keeps focus on the card when there is nothing focusable inside', () => {
    render(
      <Dialog open onClose={() => {}} ariaLabel="Empty">
        <p>Just text</p>
      </Dialog>,
    );
    fireEvent.keyDown(document, { key: 'Tab' });
    expect(document.activeElement).toBe(screen.getByRole('dialog'));
  });
});
