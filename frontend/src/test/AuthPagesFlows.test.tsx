import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { I18nProvider } from '../i18n';
import LoginPage from '../pages/LoginPage';
import RegisterPage from '../pages/RegisterPage';

// Parameterizable auth context + spies, same shape as AuthPagesI18n.test.tsx.
let mockCtx: Record<string, unknown> | null;
const refresh = vi.fn();
vi.mock('../auth/AuthContext', () => ({
  useAuth: () => ({ ctx: mockCtx, refresh }),
}));

const navigate = vi.fn();
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return { ...actual, useNavigate: () => navigate };
});

vi.mock('../api/client', () => ({
  ApiError: class ApiError extends Error {
    status: number;
    detail: string;
    constructor(status: number, message: string, detail?: string) {
      super(message);
      this.status = status;
      this.detail = detail || message;
    }
  },
  login: vi.fn(),
  registerAccount: vi.fn(),
}));

import * as api from '../api/client';

function renderPage(page: React.ReactElement) {
  return render(
    <MemoryRouter>
      <I18nProvider>{page}</I18nProvider>
    </MemoryRouter>,
  );
}

function fill(label: RegExp | string, value: string) {
  const input = screen.getByLabelText(label) as HTMLInputElement;
  fireEvent.change(input, { target: { value } });
}

describe('LoginPage submit flows', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    mockCtx = { needs_admin_bootstrap: false, registration_open: true };
  });

  it('logs in, refreshes the auth context, and navigates home', async () => {
    vi.mocked(api.login).mockResolvedValue({ must_change_password: false } as never);
    renderPage(<LoginPage />);
    fill(/Username/, ' alice ');
    fill(/Password/, 'secret123');
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/', { replace: true }));
    // The username is trimmed before hitting the API.
    expect(api.login).toHaveBeenCalledWith('alice', 'secret123');
    expect(refresh).toHaveBeenCalled();
  });

  it('routes to /change-password when the account owes a rotation', async () => {
    vi.mocked(api.login).mockResolvedValue({ must_change_password: true } as never);
    renderPage(<LoginPage />);
    fill(/Username/, 'alice');
    fill(/Password/, 'temppass1');
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    await waitFor(() =>
      expect(navigate).toHaveBeenCalledWith('/change-password', { replace: true }),
    );
  });

  it('shows the invalid-credentials copy only for a 401', async () => {
    vi.mocked(api.login).mockRejectedValue(new api.ApiError(401, 'nope'));
    renderPage(<LoginPage />);
    fill(/Username/, 'alice');
    fill(/Password/, 'wrong');
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    await waitFor(() =>
      expect(screen.getByText(/Invalid username or password/i)).toBeInTheDocument(),
    );
    expect(navigate).not.toHaveBeenCalled();
  });

  it('surfaces the server detail for non-401 errors (deactivated / rate limit)', async () => {
    vi.mocked(api.login).mockRejectedValue(
      new api.ApiError(403, 'forbidden', 'Account is deactivated.'),
    );
    renderPage(<LoginPage />);
    fill(/Username/, 'alice');
    fill(/Password/, 'secret123');
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    await waitFor(() => expect(screen.getByText('Account is deactivated.')).toBeInTheDocument());
  });

  it('shows the network-error copy for non-API failures', async () => {
    vi.mocked(api.login).mockRejectedValue(new TypeError('Failed to fetch'));
    renderPage(<LoginPage />);
    fill(/Username/, 'alice');
    fill(/Password/, 'secret123');
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }));
    await waitFor(() =>
      expect(screen.getByText(/Could not reach the server/i)).toBeInTheDocument(),
    );
  });

  it('points at /claim-admin while the first admin is unclaimed', () => {
    mockCtx = { needs_admin_bootstrap: true, registration_open: true };
    renderPage(<LoginPage />);
    expect(screen.getByRole('link', { name: /claim/i })).toHaveAttribute('href', '/claim-admin');
    // The ordinary register link is hidden during bootstrap.
    expect(screen.queryByRole('link', { name: 'Create one' })).not.toBeInTheDocument();
  });

  it('says sign-up is closed when registration is off', () => {
    mockCtx = { needs_admin_bootstrap: false, registration_open: false };
    renderPage(<LoginPage />);
    expect(screen.getByText(/Self sign-up is disabled/i)).toBeInTheDocument();
  });
});

describe('RegisterPage submit flows', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    mockCtx = { needs_admin_bootstrap: false, registration_open: true };
  });

  function fillForm({ confirm = 'secret123' } = {}) {
    fill(/Username/, ' bob ');
    fill(/Email/, ' bob@example.com ');
    fill(/^Password/, 'secret123');
    fill(/Confirm password/, confirm);
  }

  it('registers (trimmed fields), refreshes, and navigates home', async () => {
    vi.mocked(api.registerAccount).mockResolvedValue({} as never);
    renderPage(<RegisterPage />);
    fillForm();
    fireEvent.click(screen.getByRole('button', { name: 'Create account' }));
    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/'));
    expect(api.registerAccount).toHaveBeenCalledWith(
      'bob',
      'secret123',
      undefined,
      'bob@example.com',
    );
    expect(refresh).toHaveBeenCalled();
  });

  it('rejects a password mismatch client-side without calling the API', async () => {
    renderPage(<RegisterPage />);
    fillForm({ confirm: 'different1' });
    fireEvent.click(screen.getByRole('button', { name: 'Create account' }));
    await waitFor(() => expect(screen.getByText(/Passwords do not match/i)).toBeInTheDocument());
    expect(api.registerAccount).not.toHaveBeenCalled();
  });

  it('maps a 400 to the username-taken copy', async () => {
    vi.mocked(api.registerAccount).mockRejectedValue(new api.ApiError(400, 'taken'));
    renderPage(<RegisterPage />);
    fillForm();
    fireEvent.click(screen.getByRole('button', { name: 'Create account' }));
    await waitFor(() => expect(screen.getByText(/already taken/i)).toBeInTheDocument());
  });

  it('shows the generic failure copy for other errors', async () => {
    vi.mocked(api.registerAccount).mockRejectedValue(new TypeError('Failed to fetch'));
    renderPage(<RegisterPage />);
    fillForm();
    fireEvent.click(screen.getByRole('button', { name: 'Create account' }));
    await waitFor(() => expect(screen.getByText(/Registration failed/i)).toBeInTheDocument());
  });

  it('renders the closed card (not the form) when registration is off', () => {
    mockCtx = { needs_admin_bootstrap: false, registration_open: false };
    renderPage(<RegisterPage />);
    expect(screen.getByText('Sign-up disabled')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /sign in/i })).toHaveAttribute('href', '/login');
    expect(screen.queryByRole('button', { name: 'Create account' })).not.toBeInTheDocument();
  });

  it('steers to /claim-admin while the instance has no admin yet', () => {
    mockCtx = { needs_admin_bootstrap: true, registration_open: true };
    renderPage(<RegisterPage />);
    expect(screen.getByRole('link', { name: /claim/i })).toHaveAttribute('href', '/claim-admin');
  });
});
