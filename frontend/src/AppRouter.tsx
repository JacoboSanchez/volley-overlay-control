import { lazy, type ReactNode } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router';
import { AuthProvider, useAuth } from './auth/AuthContext';
import RequireAuth, { RouteLoading } from './auth/RequireAuth';
import { I18nProvider } from './i18n';
import { ToastProvider } from './components/Toast';
import { ConfirmProvider } from './components/ConfirmProvider';

// Eager: the unauthenticated front door plus the board. These are the first
// paint for every visitor, so a lazy chunk here would only add a round-trip.
import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import ClaimAdminPage from './pages/ClaimAdminPage';
import ChangePasswordPage from './pages/ChangePasswordPage';
import AccountLayout from './pages/AccountLayout';
import BoardPage from './pages/BoardPage';

// Lazy: every signed-in account page. None of them are reachable before the
// auth probe resolves, so a visitor stuck on /login never downloads them —
// nor their heavy transitive deps (icon library/picker, match calendar,
// JSON import/export, react-colorful). AccountLayout renders the Suspense
// boundary these resolve against.
const AccountHome = lazy(() => import('./pages/AccountHome'));
const OverlaysPage = lazy(() => import('./pages/OverlaysPage'));
const AccountSettingsPage = lazy(() => import('./pages/AccountSettingsPage'));
const TeamsPage = lazy(() => import('./pages/TeamsPage'));
const AdminTeamsPage = lazy(() => import('./pages/AdminTeamsPage'));
const PresetsPage = lazy(() => import('./pages/PresetsPage'));
const ReportsPage = lazy(() => import('./pages/ReportsPage'));
const AdminPage = lazy(() => import('./pages/AdminPage'));

function PublicOnly({ children }: { children: ReactNode }) {
  const { loading, ctx } = useAuth();
  if (loading || !ctx) return <RouteLoading />;
  if (ctx.authenticated && !ctx.user?.must_change_password) return <Navigate to="/" replace />;
  return <>{children}</>;
}

export default function AppRouter() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <I18nProvider>
          <ToastProvider>
            <ConfirmProvider>
              <Routes>
                <Route
                  path="/login"
                  element={
                    <PublicOnly>
                      <LoginPage />
                    </PublicOnly>
                  }
                />
                <Route
                  path="/register"
                  element={
                    <PublicOnly>
                      <RegisterPage />
                    </PublicOnly>
                  }
                />
                <Route
                  path="/claim-admin"
                  element={
                    <PublicOnly>
                      <ClaimAdminPage />
                    </PublicOnly>
                  }
                />
                <Route
                  path="/change-password"
                  element={
                    <RequireAuth>
                      <ChangePasswordPage />
                    </RequireAuth>
                  }
                />
                <Route path="/board" element={<BoardPage />} />
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
                  <Route path="/admin/teams" element={<AdminTeamsPage />} />
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
