import { describe, it, expect, vi } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import React from 'react';
import SetValueDialog from '../components/SetValueDialog';
import { renderWithI18n } from './helpers';

describe('SetValueDialog', () => {
  it('does not render when closed', () => {
    const { container } = renderWithI18n(
      <SetValueDialog open={false} title="Test" initialValue={0} maxValue={99} onSubmit={vi.fn()} onClose={vi.fn()} />
    );
    expect(container.querySelector('.dialog-overlay')).not.toBeInTheDocument();
  });

  it('renders when open', () => {
    renderWithI18n(
      <SetValueDialog open={true} title="Set Score" initialValue={10} maxValue={99} onSubmit={vi.fn()} onClose={vi.fn()} />
    );
    expect(screen.getByText('Set Score')).toBeInTheDocument();
    expect(screen.getByDisplayValue('10')).toBeInTheDocument();
  });

  it('shows OK and Cancel buttons', () => {
    renderWithI18n(
      <SetValueDialog open={true} title="Test" initialValue={0} maxValue={99} onSubmit={vi.fn()} onClose={vi.fn()} />
    );
    expect(screen.getByText('OK')).toBeInTheDocument();
    expect(screen.getByText('Cancel')).toBeInTheDocument();
  });

  it('calls onSubmit with clamped value on submit', () => {
    const onSubmit = vi.fn();
    renderWithI18n(
      <SetValueDialog open={true} title="Test" initialValue={5} maxValue={25} onSubmit={onSubmit} onClose={vi.fn()} />
    );
    fireEvent.click(screen.getByText('OK'));
    expect(onSubmit).toHaveBeenCalledWith(5);
  });

  it('calls onClose when Cancel clicked', () => {
    const onClose = vi.fn();
    renderWithI18n(
      <SetValueDialog open={true} title="Test" initialValue={0} maxValue={99} onSubmit={vi.fn()} onClose={onClose} />
    );
    fireEvent.click(screen.getByText('Cancel'));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('calls onClose when overlay clicked', () => {
    const onClose = vi.fn();
    const { container } = renderWithI18n(
      <SetValueDialog open={true} title="Test" initialValue={0} maxValue={99} onSubmit={vi.fn()} onClose={onClose} />
    );
    fireEvent.click(container.querySelector('.dialog-overlay'));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('clamps value to maxValue', () => {
    const onSubmit = vi.fn();
    renderWithI18n(
      <SetValueDialog open={true} title="Test" initialValue={0} maxValue={10} onSubmit={onSubmit} onClose={vi.fn()} />
    );
    const input = screen.getByDisplayValue('0');
    fireEvent.change(input, { target: { value: '50' } });
    fireEvent.submit(input.closest('form'));
    expect(onSubmit).toHaveBeenCalledWith(10);
  });

  it('submits 0 when input is cleared (empty)', () => {
    const onSubmit = vi.fn();
    renderWithI18n(
      <SetValueDialog open={true} title="Test" initialValue={5} maxValue={99} onSubmit={onSubmit} onClose={vi.fn()} />
    );
    const input = screen.getByDisplayValue('5');
    fireEvent.change(input, { target: { value: '' } });
    fireEvent.submit(input.closest('form'));
    expect(onSubmit).toHaveBeenCalledWith(0);
  });

  it('clamps negative values to 0', () => {
    const onSubmit = vi.fn();
    renderWithI18n(
      <SetValueDialog open={true} title="Test" initialValue={5} maxValue={99} onSubmit={onSubmit} onClose={vi.fn()} />
    );
    const input = screen.getByDisplayValue('5');
    fireEvent.change(input, { target: { value: '-10' } });
    fireEvent.submit(input.closest('form'));
    expect(onSubmit).toHaveBeenCalledWith(0);
  });
});
