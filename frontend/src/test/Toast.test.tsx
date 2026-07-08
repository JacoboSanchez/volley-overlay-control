import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ToastProvider, useToast } from '../components/Toast';

function Harness() {
  const { toast } = useToast();
  return <button onClick={() => toast('Saved!', 'success')}>fire</button>;
}

describe('ToastProvider', () => {
  it('shows a toast message when fired', () => {
    render(
      <ToastProvider>
        <Harness />
      </ToastProvider>,
    );
    fireEvent.click(screen.getByText('fire'));
    expect(screen.getByRole('status')).toHaveTextContent('Saved!');
  });

  it('useToast is a no-op outside a provider', () => {
    // Should render without throwing even though there is no ToastProvider.
    render(<Harness />);
    expect(() => fireEvent.click(screen.getByText('fire'))).not.toThrow();
  });
});
