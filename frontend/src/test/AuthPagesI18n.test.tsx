import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { I18nProvider } from '../i18n';
import LoginPage from '../pages/LoginPage';
import RegisterPage from '../pages/RegisterPage';
import ChangePasswordPage from '../pages/ChangePasswordPage';

// Parameterizable auth context: each test sets what the boot context reports.
let mockCtx: Record<string, unknown> | null;
vi.mock('../auth/AuthContext', () => ({
  useAuth: () => ({ ctx: mockCtx, refresh: vi.fn() }),
}));

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
  changePassword: vi.fn(),
  claimAdmin: vi.fn(),
}));

function renderPage(page: React.ReactElement) {
  return render(
    <MemoryRouter>
      <I18nProvider>{page}</I18nProvider>
    </MemoryRouter>,
  );
}

describe('auth pages follow the detected UI language', () => {
  beforeEach(() => {
    localStorage.clear();
    mockCtx = null;
  });

  it('renders the login page in Spanish when volley_lang=es', () => {
    localStorage.setItem('volley_lang', 'es');
    mockCtx = { needs_admin_bootstrap: false, registration_open: true };
    renderPage(<LoginPage />);
    expect(screen.getByRole('heading', { name: 'Iniciar sesión' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Crea una' })).toBeInTheDocument();
    expect(screen.getByText('Contraseña')).toBeInTheDocument();
  });

  it('falls back to English without a saved language (jsdom locale is en-US)', () => {
    mockCtx = { needs_admin_bootstrap: false, registration_open: true };
    renderPage(<LoginPage />);
    expect(screen.getByRole('heading', { name: 'Sign in' })).toBeInTheDocument();
  });

  it('renders the closed-registration card in Spanish', () => {
    localStorage.setItem('volley_lang', 'es');
    mockCtx = { needs_admin_bootstrap: false, registration_open: false };
    renderPage(<RegisterPage />);
    expect(screen.getByRole('heading', { name: 'Registro desactivado' })).toBeInTheDocument();
    expect(
      screen.getByText('El registro público está cerrado actualmente en esta instancia.'),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'inicia sesión' })).toBeInTheDocument();
  });

  it('shows the translated mismatch error on the change-password page', async () => {
    localStorage.setItem('volley_lang', 'es');
    mockCtx = { authenticated: true, user: { id: 1, username: 'ana' } };
    const { container } = renderPage(<ChangePasswordPage />);
    const [current, next, confirm] = Array.from(
      container.querySelectorAll<HTMLInputElement>('input[type="password"]'),
    );
    fireEvent.change(current!, { target: { value: 'temp-1234' } });
    fireEvent.change(next!, { target: { value: 'new-password-1' } });
    fireEvent.change(confirm!, { target: { value: 'new-password-2' } });
    fireEvent.submit(next!.closest('form')!);
    await waitFor(() => {
      expect(screen.getByText('Las contraseñas no coinciden.')).toBeInTheDocument();
    });
  });
});
