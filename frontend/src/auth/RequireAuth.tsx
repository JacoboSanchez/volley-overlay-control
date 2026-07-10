import { type ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from './AuthContext';

/** Neutral full-viewport placeholder shown while a route decides what to
 *  render (auth probe in flight, lazy chunk loading). */
export function RouteLoading() {
  return <div style={{ minHeight: '100vh', background: '#0f1115' }} />;
}

/** Gate that only renders its children for a signed-in, password-current
 *  account. Lives in its own module (not AppRouter) so route components can
 *  be imported individually without pulling in every page of the app. */
export default function RequireAuth({ children }: { children: ReactNode }) {
  const { loading, ctx } = useAuth();
  const location = useLocation();
  if (loading || !ctx) return <RouteLoading />;
  // Remember where the visitor was headed so LoginPage can return there —
  // e.g. an installed board PWA whose start_url is /board?oid=<board> must
  // land back on that board after the login round-trip, not on the dashboard.
  if (!ctx.authenticated) return <Navigate to="/login" replace state={{ from: location }} />;
  if (ctx.user?.must_change_password && location.pathname !== '/change-password') {
    return <Navigate to="/change-password" replace />;
  }
  return <>{children}</>;
}
