import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import AppRouter from '../AppRouter';
import * as api from '../api/client';

// The board itself is exercised by App.test.tsx — here only the /board route
// wiring matters: which credential mode Board hands to App and where it points
// the PWA manifest. A stub that echoes its props keeps the test hermetic.
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
    window.history.pushState({}, '', '/board?u=alex&oid=liga');
    render(<AppRouter />);

    const app = await screen.findByTestId('board-app');
    expect(app.dataset.publicUser).toBe('alex');
    expect(manifestLink().getAttribute('href')).toBe('/manifest.webmanifest?u=alex&oid=liga');
  });

  it('upgrades an own ?u= bookmark to owner mode when the owner is signed in', async () => {
    vi.mocked(api.getAuthContext).mockResolvedValue(loggedInAs('alex'));
    window.history.pushState({}, '', '/board?u=Alex&oid=liga');
    render(<AppRouter />);

    const app = await screen.findByTestId('board-app');
    // Usernames are stored lowercased; the URL casing must not defeat the match.
    expect(app.dataset.publicUser).toBe('');
  });

  it('keeps bookmark mode when a different account is signed in', async () => {
    vi.mocked(api.getAuthContext).mockResolvedValue(loggedInAs('sam'));
    window.history.pushState({}, '', '/board?u=alex&oid=liga');
    render(<AppRouter />);

    const app = await screen.findByTestId('board-app');
    expect(app.dataset.publicUser).toBe('alex');
  });

  it('points the manifest at the owner board for a plain ?oid= visit', async () => {
    vi.mocked(api.getAuthContext).mockResolvedValue(loggedInAs('alex'));
    window.history.pushState({}, '', '/board?oid=liga');
    render(<AppRouter />);

    await screen.findByTestId('board-app');
    await waitFor(() =>
      expect(manifestLink().getAttribute('href')).toBe('/manifest.webmanifest?oid=liga'),
    );
  });

  it('leaves the manifest alone for a revocable ?c= link', async () => {
    vi.mocked(api.getAuthContext).mockResolvedValue(anonymous);
    window.history.pushState({}, '', '/board?c=tok123&oid=liga');
    render(<AppRouter />);

    const app = await screen.findByTestId('board-app');
    expect(app.dataset.controlToken).toBe('tok123');
    expect(manifestLink().getAttribute('href')).toBe('/manifest.webmanifest');
  });
});
