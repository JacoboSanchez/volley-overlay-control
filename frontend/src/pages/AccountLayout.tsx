import { useEffect, useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import * as api from '../api/client';
import { useAuth } from '../auth/AuthContext';
import './account.css';

export default function AccountLayout() {
  const { ctx, refresh } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const isAdmin = ctx?.user?.role === 'admin';
  const [menuOpen, setMenuOpen] = useState(false);

  // Collapse the mobile drawer whenever the route changes so it never lingers
  // open over freshly navigated content.
  useEffect(() => {
    setMenuOpen(false);
  }, [location.pathname]);

  // While the drawer is open, allow Escape to close it and lock background
  // scroll so the page underneath doesn't drift behind the overlay.
  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setMenuOpen(false);
    };
    window.addEventListener('keydown', onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [menuOpen]);

  async function onLogout() {
    try {
      await api.logout();
    } catch {
      /* ignore */
    }
    await refresh();
    navigate('/login');
  }

  const displayName = ctx?.user?.display_name || ctx?.user?.username;

  return (
    <div className="acc-shell">
      {/* Mobile-only top bar: brand on the left, hamburger toggle on the right.
          Hidden on desktop, where the sidebar nav is always visible. */}
      <header className="acc-topbar">
        <div className="brand">🏐 Overlay Control</div>
        <button
          type="button"
          className={`acc-hamburger${menuOpen ? ' open' : ''}`}
          aria-label={menuOpen ? 'Close menu' : 'Open menu'}
          aria-expanded={menuOpen}
          aria-controls="acc-primary-nav"
          onClick={() => setMenuOpen((v) => !v)}
        >
          <span className="acc-hamburger-box" aria-hidden="true">
            <span className="acc-hamburger-inner" />
          </span>
        </button>
      </header>

      {/* Dim + close-on-tap backdrop behind the mobile drawer. */}
      <div
        className={`acc-nav-backdrop${menuOpen ? ' open' : ''}`}
        onClick={() => setMenuOpen(false)}
        aria-hidden="true"
      />

      <div className="acc-layout">
        <nav
          id="acc-primary-nav"
          className={`acc-nav${menuOpen ? ' open' : ''}`}
          aria-label="Primary"
        >
          <div className="brand">🏐 Overlay Control</div>
          <NavLink to="/" end>Dashboard</NavLink>
          <NavLink to="/overlays">My overlays</NavLink>
          <NavLink to="/teams">Teams</NavLink>
          <NavLink to="/presets">Presets</NavLink>
          <NavLink to="/reports">Reports</NavLink>
          <NavLink to="/account">Account</NavLink>
          {isAdmin && <NavLink to="/admin">Admin</NavLink>}
          <div className="spacer" />
          <div className="acc-nav-user">
            <span className="acc-muted">{displayName}</span>
            {isAdmin && <span className="acc-pill">admin</span>}
          </div>
          <button className="acc-btn ghost acc-nav-signout" onClick={onLogout}>
            Sign out
          </button>
        </nav>
        <main className="acc-main">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
