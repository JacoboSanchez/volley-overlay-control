import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { lazy } from 'react';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router';
import AccountLayout from '../pages/AccountLayout';
import { I18nProvider } from '../i18n';

vi.mock('../api/client', () => ({ logout: vi.fn() }));
vi.mock('../auth/AuthContext', () => ({
  useAuth: () => ({
    ctx: { authenticated: true, user: { username: 'op', role: 'user' } },
    refresh: vi.fn(),
  }),
}));

/**
 * The failure this guards against is specific to route-level code
 * splitting: a tab that outlived the deployment it was loaded from asks
 * for a hashed chunk the new build no longer serves, and the dynamic
 * import rejects. ``Suspense`` only covers a *pending* import, so before
 * the boundary went in, that rejection unmounted the account UI and left
 * a blank page with no way back.
 */
const StaleChunkPage = lazy(() =>
  Promise.reject(
    new Error('Failed to fetch dynamically imported module: /assets/TeamsPage-abc.js'),
  ),
);

function renderAccountShell() {
  return render(
    <I18nProvider>
      <MemoryRouter initialEntries={['/teams']}>
        <Routes>
          <Route element={<AccountLayout />}>
            <Route path="/teams" element={<StaleChunkPage />} />
          </Route>
        </Routes>
      </MemoryRouter>
    </I18nProvider>,
  );
}

describe('AccountLayout with a chunk that will not load', () => {
  let originalConsoleError: typeof console.error;

  beforeEach(() => {
    originalConsoleError = console.error;
    console.error = vi.fn();
  });

  afterEach(() => {
    console.error = originalConsoleError;
  });

  it('shows a recoverable error instead of blanking the account UI', async () => {
    renderAccountShell();

    const alert = await screen.findByRole('alert');
    expect(alert).toBeInTheDocument();
    expect(screen.getByText(/needs reloading/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /reload/i })).toBeInTheDocument();
  });

  it('keeps the navigation mounted so the operator can move elsewhere', async () => {
    renderAccountShell();
    await screen.findByRole('alert');

    // The boundary sits inside the layout precisely so this survives —
    // a root-level one would take the whole shell down with the page.
    expect(screen.getByRole('navigation')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /overlays/i })).toBeInTheDocument();
  });
});
