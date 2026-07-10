import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { AuthProvider } from '../auth/AuthContext';
import BoardPage from '../pages/BoardPage';
import * as api from '../api/client';

// The board itself is exercised by App.test.tsx — here only the /board route
// wiring matters: which credential mode BoardPage hands to App and where it
// points the PWA manifest. A stub that echoes its props keeps the test
// hermetic (and keeps the heavyweight App out of the module graph).
vi.mock('../App', () => ({
  default: (props: { controlToken?: string; publicUser?: string }) => (
    <div
      data-testid="board-app"
      data-control-token={props.controlToken ?? ''}
      data-public-user={props.publicUser ?? ''}
    />
  ),
}));

vi.mock('../api/client', () => ({
  ApiError: class ApiError extends Error {
    status = 0;
    detail = '';
  },
  getAuthContext: vi.fn(),
}));

const anonymous = {
  authenticated: false,
  user: null,
  registration_open: false,
  needs_admin_bootstrap: false,
};

function loggedInAs(username: string) {
  return {
    authenticated: true,
    user: {
      id: 1,
      username,
      display_name: null,
      email: null,
      role: 'user' as const,
      is_active: true,
      must_change_password: false,
    },
    registration_open: false,
    needs_admin_bootstrap: false,
  };
}

/** Stub /login that records the location state RequireAuth forwarded. */
function LoginProbe() {
  const location = useLocation();
  const from = (location.state as { from?: { pathname?: string; search?: string } } | null)?.from;
  return (
    <div data-testid="login-page" data-from={`${from?.pathname ?? ''}${from?.search ?? ''}`} />
  );
}

function renderBoard(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <Routes>
          <Route path="/board" element={<BoardPage />} />
          <Route path="/login" element={<LoginProbe />} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

function manifestLink(): HTMLLinkElement {
  const link = document.querySelector<HTMLLinkElement>('link[rel="manifest"]');
  if (!link) throw new Error('manifest link missing');
  return link;
}

describe('/board route', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    document.head.innerHTML = '<link rel="manifest" href="/manifest.webmanifest" />';
  });

  it('keeps bookmark mode for an anonymous ?u= visitor and points the manifest at it', async () => {
    vi.mocked(api.getAuthContext).mockResolvedValue(anonymous);
    renderBoard('/board?u=alex&oid=liga');

    const app = await screen.findByTestId('board-app');
    expect(app.dataset.publicUser).toBe('alex');
    expect(manifestLink().getAttribute('href')).toBe('/manifest.webmanifest?u=alex&oid=liga');
  });

  it('upgrades an own ?u= bookmark to owner mode when the owner is signed in', async () => {
    vi.mocked(api.getAuthContext).mockResolvedValue(loggedInAs('alex'));
    // Usernames are stored lowercased and hand-copied URLs pick up stray
    // whitespace; neither casing nor padding must defeat the match.
    renderBoard('/board?u=%20Alex%20&oid=liga');

    const app = await screen.findByTestId('board-app');
    expect(app.dataset.publicUser).toBe('');
  });

  it('keeps bookmark mode when a different account is signed in', async () => {
    vi.mocked(api.getAuthContext).mockResolvedValue(loggedInAs('sam'));
    renderBoard('/board?u=alex&oid=liga');

    const app = await screen.findByTestId('board-app');
    expect(app.dataset.publicUser).toBe('alex');
  });

  it('points the manifest at the owner board for a plain ?oid= visit', async () => {
    vi.mocked(api.getAuthContext).mockResolvedValue(loggedInAs('alex'));
    renderBoard('/board?oid=liga');

    await screen.findByTestId('board-app');
    await waitFor(() =>
      expect(manifestLink().getAttribute('href')).toBe('/manifest.webmanifest?oid=liga'),
    );
  });

  it('bounces an anonymous ?oid= visit to /login, preserving the destination', async () => {
    vi.mocked(api.getAuthContext).mockResolvedValue(anonymous);
    renderBoard('/board?oid=liga');

    const login = await screen.findByTestId('login-page');
    // RequireAuth stashes the origin so LoginPage can navigate back — this is
    // what makes an installed /board?oid= PWA usable without a live session.
    expect(login.dataset.from).toBe('/board?oid=liga');
  });

  it('leaves the manifest alone for a revocable ?c= link', async () => {
    vi.mocked(api.getAuthContext).mockResolvedValue(anonymous);
    renderBoard('/board?c=tok123&oid=liga');

    const app = await screen.findByTestId('board-app');
    expect(app.dataset.controlToken).toBe('tok123');
    expect(manifestLink().getAttribute('href')).toBe('/manifest.webmanifest');
  });
});
