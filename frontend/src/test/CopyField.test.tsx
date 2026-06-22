import { describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import CopyField from '../components/CopyField';

describe('CopyField', () => {
  it('renders the value in a read-only, selectable input', () => {
    render(<CopyField value="Tmp-9f3K2a" label="Temporary password" />);
    const input = screen.getByLabelText('Temporary password') as HTMLInputElement;
    expect(input).toHaveValue('Tmp-9f3K2a');
    expect(input).toHaveAttribute('readonly');
  });

  it('selects the whole value on focus so it can be copied manually', () => {
    render(<CopyField value="Tmp-9f3K2a" label="Temporary password" />);
    const input = screen.getByLabelText('Temporary password') as HTMLInputElement;
    const select = vi.spyOn(input, 'select');
    fireEvent.focus(input);
    expect(select).toHaveBeenCalled();
  });

  it('copies the value to the clipboard and confirms', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });

    render(<CopyField value="Tmp-9f3K2a" label="Temporary password" />);
    fireEvent.click(screen.getByRole('button', { name: 'Copy' }));

    expect(writeText).toHaveBeenCalledWith('Tmp-9f3K2a');
    await waitFor(() => expect(screen.getByRole('button', { name: 'Copied!' })).toBeInTheDocument());
  });
});
