import { Suspense, useEffect, useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router';
import * as api from '../api/client';
import { useAuth } from '../auth/AuthContext';
import ErrorBoundary from '../components/ErrorBoundary';
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
      {/* Mobile-only top bar: hamburger toggle on the left (next to where the
          drawer slides in from), brand after it. Hidden on desktop, where the
          sidebar nav is always visible. */}
      <header className="acc-topbar">
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
        <div className="brand">🏐 {t('acc.brand')}</div>
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
          <NavLink to="/" end>
            {t('acc.nav.dashboard')}
          </NavLink>
          <NavLink to="/overlays">{t('acc.nav.overlays')}</NavLink>
          <NavLink to="/teams">{t('acc.nav.teams')}</NavLink>
          <NavLink to="/presets">{t('acc.nav.presets')}</NavLink>
          <NavLink to="/reports">{t('acc.nav.reports')}</NavLink>
          <NavLink to="/account">{t('acc.nav.account')}</NavLink>
          {isAdmin && (
            <>
              <div className="acc-nav-section">{t('acc.nav.adminSection')}</div>
              <NavLink to="/admin">{t('acc.nav.admin')}</NavLink>
              <NavLink to="/admin/teams">{t('acc.nav.adminTeams')}</NavLink>
            </>
          )}
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
          {/* Two boundaries, for the two ways a lazy chunk can go wrong.
              Suspense covers a *pending* import; a null fallback keeps the
              nav and shell in place, since the chunk is same-origin and a
              spinner would flash more than it informs. ErrorBoundary covers
              a *rejected* one — a tab that outlived its deployment asks for
              a hashed chunk the new build no longer serves, and without
              this the rejection would blank the account UI. Inside the
              layout on purpose: the nav survives, so the operator can still
              move around.

              Keyed by pathname because an error boundary latches: once it
              has caught, it renders its fallback until it is remounted, so
              without this the surviving nav would change the route and
              still show the error — visible but useless, which is worse
              than honest. A new key gives each route its own boundary. */}
          <ErrorBoundary key={location.pathname}>
            <Suspense fallback={null}>
              <Outlet />
            </Suspense>
          </ErrorBoundary>
        </main>
      </div>
    </div>
  );
}
