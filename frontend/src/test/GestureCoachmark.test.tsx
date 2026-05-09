import { describe, it, expect, vi } from 'vitest';
import { fireEvent, screen } from '@testing-library/react';
import GestureCoachmark from '../components/GestureCoachmark';
import { renderWithI18n } from './helpers';

describe('GestureCoachmark', () => {
  it('renders nothing when closed', () => {
    renderWithI18n(<GestureCoachmark open={false} onDismiss={vi.fn()} />);
    expect(screen.queryByTestId('gesture-coachmark')).toBeNull();
  });

  it('starts on the first step when opened', () => {
    renderWithI18n(<GestureCoachmark open={true} onDismiss={vi.fn()} />);
    expect(screen.getByTestId('gesture-coachmark')).toBeInTheDocument();
    expect(screen.getByText(/tap to score/i)).toBeInTheDocument();
    // Skip + Next on the first step; Back is hidden until step 2.
    expect(screen.getByTestId('gesture-coachmark-skip')).toBeInTheDocument();
    expect(screen.getByTestId('gesture-coachmark-next')).toHaveTextContent(/next/i);
    expect(screen.queryByTestId('gesture-coachmark-prev')).toBeNull();
  });

  it('advances through the steps with Next', () => {
    renderWithI18n(<GestureCoachmark open={true} onDismiss={vi.fn()} />);
    fireEvent.click(screen.getByTestId('gesture-coachmark-next'));
    expect(screen.getByTestId('gesture-coachmark-prev')).toBeInTheDocument();
    expect(screen.getByText(/double-tap to undo/i)).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('gesture-coachmark-next'));
    expect(screen.getByText(/long-press to edit/i)).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('gesture-coachmark-next'));
    expect(screen.getByText(/open configuration/i)).toBeInTheDocument();
    // Last step relabels Next as "Got it".
    expect(screen.getByTestId('gesture-coachmark-next')).toHaveTextContent(/got it/i);
  });

  it('steps backward with Back', () => {
    renderWithI18n(<GestureCoachmark open={true} onDismiss={vi.fn()} />);
    fireEvent.click(screen.getByTestId('gesture-coachmark-next'));
    fireEvent.click(screen.getByTestId('gesture-coachmark-prev'));
    expect(screen.getByText(/tap to score/i)).toBeInTheDocument();
  });

  it('dismisses via the Skip button', () => {
    const onDismiss = vi.fn();
    renderWithI18n(<GestureCoachmark open={true} onDismiss={onDismiss} />);
    fireEvent.click(screen.getByTestId('gesture-coachmark-skip'));
    expect(onDismiss).toHaveBeenCalledOnce();
  });

  it('dismisses via Got it on the last step', () => {
    const onDismiss = vi.fn();
    renderWithI18n(<GestureCoachmark open={true} onDismiss={onDismiss} />);
    // Walk to the last step then click Got it.
    fireEvent.click(screen.getByTestId('gesture-coachmark-next'));
    fireEvent.click(screen.getByTestId('gesture-coachmark-next'));
    fireEvent.click(screen.getByTestId('gesture-coachmark-next'));
    fireEvent.click(screen.getByTestId('gesture-coachmark-next'));
    expect(onDismiss).toHaveBeenCalledOnce();
  });

  it('dismisses on Escape', () => {
    const onDismiss = vi.fn();
    renderWithI18n(<GestureCoachmark open={true} onDismiss={onDismiss} />);
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onDismiss).toHaveBeenCalledOnce();
  });

  it('advances on ArrowRight and steps back on ArrowLeft', () => {
    renderWithI18n(<GestureCoachmark open={true} onDismiss={vi.fn()} />);
    fireEvent.keyDown(document, { key: 'ArrowRight' });
    expect(screen.getByText(/double-tap to undo/i)).toBeInTheDocument();
    fireEvent.keyDown(document, { key: 'ArrowLeft' });
    expect(screen.getByText(/tap to score/i)).toBeInTheDocument();
  });
});
