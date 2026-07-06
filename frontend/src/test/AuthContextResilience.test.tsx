import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, render, screen, waitFor } from '@testing-library/react';
import * as api from '../api/client';
import { AuthProvider, useAuth } from '../auth/AuthContext';

vi.mock('../api/client', () => ({
  getAuthContext: vi.fn(),
}));

const mocked = vi.mocked(api);

function Probe() {
  const { loading, ctx, refresh } = useAuth();
  return (
    <div>
      <span data-testid="state">{loading ? 'loading' : ctx?.authenticated ? 'in' : 'out'}</span>
      <span data-testid="reg">{String(ctx?.registration_open ?? 'none')}</span>
      <button onClick={() => void refresh()}>refresh</button>
    </div>
  );
}

const AUTHED: api.AuthContext = {
  authenticated: true,
  user: {
    id: 1,
    username: 'alice',
    display_name: null,
    email: null,
    role: 'user',
    is_active: true,
    must_change_password: false,
  } as api.UserOut,
  registration_open: false,
  needs_admin_bootstrap: false,
};

describe('AuthProvider refresh resilience', () => {
  beforeEach(() => vi.resetAllMocks());

  it('keeps an established session when a refresh hits a network error', async () => {
    // Regression: a transient blip used to replace the authenticated
    // context with a logged-out fallback, bouncing the user to /login.
    mocked.getAuthContext.mockResolvedValueOnce(AUTHED);
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByTestId('state').textContent).toBe('in'));

    mocked.getAuthContext.mockRejectedValueOnce(new TypeError('Failed to fetch'));
    await act(async () => {
      screen.getByText('refresh').click();
    });
    expect(screen.getByTestId('state').textContent).toBe('in');
  });

  it('falls back to logged-out (registration closed) when the first load fails', async () => {
    mocked.getAuthContext.mockRejectedValueOnce(new TypeError('Failed to fetch'));
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByTestId('state').textContent).toBe('out'));
    expect(screen.getByTestId('reg').textContent).toBe('false');
  });
});
