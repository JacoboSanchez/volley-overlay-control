import { Suspense, lazy, useEffect, type ReactNode } from 'react';
import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
  useLocation,
} from 'react-router-dom';
import { AuthProvider, useAuth } from './auth/AuthContext';
import { I18nProvider } from './i18n';
import { SettingsProvider } from './hooks/useSettings';
import { ToastProvider } from './components/Toast';
import { ConfirmProvider } from './components/ConfirmProvider';

import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import ClaimAdminPage from './pages/ClaimAdminPage';
import ChangePasswordPage from './pages/ChangePasswordPage';
import AccountLayout from './pages/AccountLayout';
import AccountHome from './pages/AccountHome';
import OverlaysPage from './pages/OverlaysPage';
import AccountSettingsPage from './pages/AccountSettingsPage';
import TeamsPage from './pages/TeamsPage';
import PresetsPage from './pages/PresetsPage';
import ReportsPage from './pages/ReportsPage';
import AdminPage from './pages/AdminPage';

const App = lazy(() => import('./App'));

function Loading() {
  return <div style={{ minHeight: '100vh', background: '#0f1115' }} />;
}

function RequireAuth({ children }: { children: ReactNode }) {
  const { loading, ctx } = useAuth();
  const location = useLocation();
  if (loading || !ctx) return <Loading />;
  if (!ctx.authenticated) return <Navigate to="/login" replace />;
  if (ctx.user?.must_change_password && location.pathname !== '/change-password') {
    return <Navigate to="/change-password" replace />;
  }
  return <>{children}</>;
}

function PublicOnly({ children }: { children: ReactNode }) {
  const { loading, ctx } = useAuth();
  if (loading || !ctx) return <Loading />;
  if (ctx.authenticated && !ctx.user?.must_change_password) return <Navigate to="/" replace />;
  return <>{children}</>;
}

/** The control board, reachable three ways: owner (?oid= behind a login), an
 *  operator ?c=<control_token> capability link, or a public ?u=<username>&oid=
 *  bookmark. The two capability modes need no login. */
function Board() {
  const params = new URLSearchParams(useLocation().search);
  const controlToken = params.get('c');
  const publicUser = params.get('u');
  const oid = params.get('oid');

  // Point the PWA manifest at this specific board so an "Install app" (Chrome /
  // desktop) creates a launcher that reopens THIS board rather than the app
  // root. Only for the stable, no-login bookmark (username + oid): the control
  // token is revocable, so installing it would break when it's regenerated, and
  // owner mode (?oid= behind a login) would just land on the login screen.
  useEffect(() => {
    if (!publicUser || !oid) return undefined;
    const link = document.querySelector<HTMLLinkElement>('link[rel="manifest"]');
    if (!link) return undefined;
    const previous = link.getAttribute('href');
    link.setAttribute(
      'href',
      `/manifest.webmanifest?u=${encodeURIComponent(publicUser)}&oid=${encodeURIComponent(oid)}`,
    );
    return () => {
      if (previous !== null) link.setAttribute('href', previous);
    };
  }, [publicUser, oid]);

  const board = (
    <SettingsProvider>
      <Suspense fallback={<Loading />}>
        <App controlToken={controlToken ?? undefined} publicUser={publicUser ?? undefined} />
      </Suspense>
    </SettingsProvider>
  );
  // A capability link is its own credential — no session cookie required.
  return controlToken || publicUser ? board : <RequireAuth>{board}</RequireAuth>;
}

export default function AppRouter() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <I18nProvider>
          <ToastProvider>
            <ConfirmProvider>
              <Routes>
                <Route path="/login" element={<PublicOnly><LoginPage /></PublicOnly>} />
                <Route path="/register" element={<PublicOnly><RegisterPage /></PublicOnly>} />
                <Route path="/claim-admin" element={<PublicOnly><ClaimAdminPage /></PublicOnly>} />
                <Route
                  path="/change-password"
                  element={
                    <RequireAuth>
                      <ChangePasswordPage />
                    </RequireAuth>
                  }
                />
                <Route path="/board" element={<Board />} />
                <Route
                  element={
                    <RequireAuth>
                      <AccountLayout />
                    </RequireAuth>
                  }
                >
                  <Route path="/" element={<AccountHome />} />
                  <Route path="/overlays" element={<OverlaysPage />} />
                  <Route path="/teams" element={<TeamsPage />} />
                  <Route path="/presets" element={<PresetsPage />} />
                  <Route path="/reports" element={<ReportsPage />} />
                  <Route path="/account" element={<AccountSettingsPage />} />
                  <Route path="/admin" element={<AdminPage />} />
                </Route>
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </ConfirmProvider>
          </ToastProvider>
        </I18nProvider>
      </AuthProvider>
    </BrowserRouter>
  );
}
