import { Suspense, lazy, type ReactNode } from 'react';
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

/** The control board. Owner mode is scoped via ?oid= behind a login; operator
 *  mode is scoped via a ?c=<control_token> capability link and needs no login. */
function Board() {
  const controlToken = new URLSearchParams(useLocation().search).get('c');
  const board = (
    <I18nProvider>
      <SettingsProvider>
        <Suspense fallback={<Loading />}>
          <App controlToken={controlToken ?? undefined} />
        </Suspense>
      </SettingsProvider>
    </I18nProvider>
  );
  // A valid control link is its own credential — no session cookie required.
  return controlToken ? board : <RequireAuth>{board}</RequireAuth>;
}

export default function AppRouter() {
  return (
    <BrowserRouter>
      <AuthProvider>
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
      </AuthProvider>
    </BrowserRouter>
  );
}
