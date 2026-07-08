import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import AccountLayout from '../pages/AccountLayout';

// Minimal auth context: a signed-in non-admin user.
const mockCtx = {
  authenticated: true,
  user: { username: 'alex', display_name: 'Alex', role: 'user' },
  registration_open: true,
  needs_admin_bootstrap: false,
};

vi.mock('../auth/AuthContext', () => ({
  useAuth: () => ({ ctx: mockCtx, refresh: vi.fn(), loading: false, setUser: vi.fn() }),
}));

vi.mock('../api/client', () => ({
  logout: vi.fn().mockResolvedValue(undefined),
}));

function renderLayout() {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <Routes>
        <Route element={<AccountLayout />}>
          <Route path="/" element={<div>Dashboard content</div>} />
          <Route path="/teams" element={<div>Teams content</div>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe('AccountLayout mobile navigation', () => {
  beforeEach(() => {
    document.body.style.overflow = '';
  });

  it('exposes every destination through the hamburger-toggled drawer', () => {
    const { container } = renderLayout();
    const nav = container.querySelector('#acc-primary-nav') as HTMLElement;
    const toggle = screen.getByRole('button', { name: /open menu/i });

    // Drawer is collapsed initially, but all links are still in the DOM (CSS
    // hides them off-canvas) — including the ones that used to scroll off the
    // edge of the old horizontal menu.
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(nav.className).not.toContain('open');
    for (const label of ['Dashboard', 'My overlays', 'Teams', 'Presets', 'Reports', 'Account']) {
      expect(within(nav).getByRole('link', { name: label })).toBeInTheDocument();
    }
    expect(within(nav).getByRole('button', { name: /sign out/i })).toBeInTheDocument();
  });

  it('toggles the drawer open and closed and locks body scroll while open', () => {
    const { container } = renderLayout();
    const nav = container.querySelector('#acc-primary-nav') as HTMLElement;
    const toggle = screen.getByRole('button', { name: /open menu/i });

    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(nav.className).toContain('open');
    expect(document.body.style.overflow).toBe('hidden');

    fireEvent.click(screen.getByRole('button', { name: /close menu/i }));
    expect(nav.className).not.toContain('open');
    expect(document.body.style.overflow).toBe('');
  });

  it('closes the drawer when a destination is chosen', () => {
    const { container } = renderLayout();
    const nav = container.querySelector('#acc-primary-nav') as HTMLElement;

    fireEvent.click(screen.getByRole('button', { name: /open menu/i }));
    expect(nav.className).toContain('open');

    fireEvent.click(within(nav).getByRole('link', { name: 'Teams' }));
    expect(screen.getByText('Teams content')).toBeInTheDocument();
    expect(nav.className).not.toContain('open');
  });

  it('hides the admin link for non-admins', () => {
    const { container } = renderLayout();
    const nav = container.querySelector('#acc-primary-nav') as HTMLElement;
    expect(within(nav).queryByRole('link', { name: 'Admin' })).not.toBeInTheDocument();
  });
});
