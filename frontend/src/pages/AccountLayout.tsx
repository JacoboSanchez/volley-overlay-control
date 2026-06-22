import { useEffect, useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import * as api from '../api/client';
import { useAuth } from '../auth/AuthContext';
import { useI18n } from '../i18n';
import './account.css';

export default function AccountLayout() {
  const { ctx, refresh } = useAuth();
  const { t } = useI18n();
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
        <div className="brand">🏐 {t('acc.brand')}</div>
        <button
          type="button"
          className={`acc-hamburger${menuOpen ? ' open' : ''}`}
          aria-label={menuOpen ? t('acc.nav.closeMenu') : t('acc.nav.openMenu')}
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
          aria-label={t('acc.nav.primary')}
        >
          <div className="brand">🏐 {t('acc.brand')}</div>
          <NavLink to="/" end>{t('acc.nav.dashboard')}</NavLink>
          <NavLink to="/overlays">{t('acc.nav.overlays')}</NavLink>
          <NavLink to="/teams">{t('acc.nav.teams')}</NavLink>
          <NavLink to="/presets">{t('acc.nav.presets')}</NavLink>
          <NavLink to="/reports">{t('acc.nav.reports')}</NavLink>
          <NavLink to="/account">{t('acc.nav.account')}</NavLink>
          {isAdmin && <NavLink to="/admin">{t('acc.nav.admin')}</NavLink>}
          <div className="spacer" />
          <div className="acc-nav-user">
            <span className="acc-muted">{displayName}</span>
            {isAdmin && <span className="acc-pill">{t('acc.pill.admin')}</span>}
          </div>
          <button className="acc-btn ghost acc-nav-signout" onClick={onLogout}>
            {t('acc.nav.signOut')}
          </button>
        </nav>
        <main className="acc-main">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
