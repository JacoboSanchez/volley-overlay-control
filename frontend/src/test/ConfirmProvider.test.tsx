import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { useState } from 'react';
import { ConfirmProvider, useConfirm } from '../components/ConfirmProvider';

function Harness() {
  const confirm = useConfirm();
  const [result, setResult] = useState('');
  return (
    <div>
      <button
        onClick={async () => {
          const ok = await confirm({
            title: 'Delete thing',
            message: 'Really delete it?',
            confirmLabel: 'Delete',
            danger: true,
          });
          setResult(ok ? 'confirmed' : 'cancelled');
        }}
      >
        ask
      </button>
      <span data-testid="result">{result}</span>
    </div>
  );
}

describe('ConfirmProvider', () => {
  it('resolves true when the confirm button is clicked', async () => {
    render(
      <ConfirmProvider>
        <Harness />
      </ConfirmProvider>,
    );
    fireEvent.click(screen.getByText('ask'));
    expect(await screen.findByText('Really delete it?')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));
    await waitFor(() => expect(screen.getByTestId('result')).toHaveTextContent('confirmed'));
  });

  it('resolves false when cancelled', async () => {
    render(
      <ConfirmProvider>
        <Harness />
      </ConfirmProvider>,
    );
    fireEvent.click(screen.getByText('ask'));
    await screen.findByText('Really delete it?');
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    await waitFor(() => expect(screen.getByTestId('result')).toHaveTextContent('cancelled'));
  });
});
