import { type ReactNode } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider, useAuth } from './auth/AuthContext';
import RequireAuth, { RouteLoading } from './auth/RequireAuth';
import { I18nProvider } from './i18n';
import { ToastProvider } from './components/Toast';
import { ConfirmProvider } from './components/ConfirmProvider';

import LoginPage from './pages/LoginPage';
import RegisterPage from './pages/RegisterPage';
import ClaimAdminPage from './pages/ClaimAdminPage';
import ChangePasswordPage from './pages/ChangePasswordPage';
import AccountLayout from './pages/AccountLayout';
import AccountHome from './pages/AccountHome';
import BoardPage from './pages/BoardPage';
import OverlaysPage from './pages/OverlaysPage';
import AccountSettingsPage from './pages/AccountSettingsPage';
import TeamsPage from './pages/TeamsPage';
import AdminTeamsPage from './pages/AdminTeamsPage';
import PresetsPage from './pages/PresetsPage';
import ReportsPage from './pages/ReportsPage';
import AdminPage from './pages/AdminPage';

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
