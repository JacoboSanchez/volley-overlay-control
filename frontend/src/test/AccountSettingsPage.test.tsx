import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { I18nProvider } from '../i18n';
import AccountSettingsPage from '../pages/AccountSettingsPage';

vi.mock('../auth/AuthContext', () => ({
  useAuth: () => ({
    ctx: { user: { username: 'alex', display_name: 'Alex', email: 'a@b.c', role: 'user' } },
    refresh: vi.fn(),
  }),
}));

vi.mock('../api/client', () => ({
  ApiError: class ApiError extends Error {
    detail = '';
    status = 0;
  },
  updateMe: vi.fn(),
  changePassword: vi.fn(),
  deleteMe: vi.fn(),
}));

function renderPage() {
  return render(
    <MemoryRouter>
      <I18nProvider>
        <AccountSettingsPage />
      </I18nProvider>
    </MemoryRouter>,
  );
}

describe('AccountSettingsPage language preference', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('renders the account page in English by default with a language selector', () => {
    renderPage();
    expect(screen.getByRole('heading', { name: 'Account', level: 2 })).toBeInTheDocument();
    expect(screen.getByText('Preferences')).toBeInTheDocument();
    // The language <select> defaults to English.
    expect(screen.getByText('English')).toBeInTheDocument();
  });

  it('switches the whole account UI to the chosen language and persists it', async () => {
    renderPage();
    // Find the language selector (the only <select> on the page) and pick Spanish.
    const select = screen.getByRole('combobox') as HTMLSelectElement;
    fireEvent.change(select, { target: { value: 'es' } });

    // Account-page strings now render in Spanish…
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Cuenta', level: 2 })).toBeInTheDocument();
    });
    expect(screen.getByText('Preferencias')).toBeInTheDocument();
    expect(screen.getByText('Zona de peligro')).toBeInTheDocument();
    // …and the choice is saved for next time.
    expect(localStorage.getItem('volley_lang')).toBe('es');
  });
});
