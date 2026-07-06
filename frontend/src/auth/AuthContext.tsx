import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import * as api from '../api/client';

interface AuthState {
  loading: boolean;
  ctx: api.AuthContext | null;
  refresh: () => Promise<api.AuthContext | null>;
  setUser: (user: api.UserOut | null) => void;
}

const AuthCtx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [loading, setLoading] = useState(true);
  const [ctx, setCtx] = useState<api.AuthContext | null>(null);

  const refresh = useCallback(async () => {
    try {
      const next = await api.getAuthContext();
      setCtx(next);
      return next;
    } catch {
      // /auth/context answers 200 with an `authenticated` flag even when
      // logged out, so landing here means a network blip / 5xx — not an
      // authoritative "not logged in". Keep an already-established context
      // instead of bouncing a validly-cookied user to /login; only fall
      // back to logged-out (registration closed, matching the backend
      // default) when we never had one.
      const fallback: api.AuthContext = {
        authenticated: false,
        user: null,
        registration_open: false,
        needs_admin_bootstrap: false,
      };
      let effective = fallback;
      setCtx((prev) => {
        effective = prev ?? fallback;
        return effective;
      });
      return effective;
    } finally {
      setLoading(false);
    }
  }, []);

  const setUser = useCallback((user: api.UserOut | null) => {
    setCtx((prev) =>
      prev ? { ...prev, authenticated: !!user, user } : prev,
    );
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // When any API call gets a 401 (session expired/revoked mid-use), mark the
  // context unauthenticated so RequireAuth redirects to /login.
  useEffect(() => {
    const onUnauthorized = () =>
      setCtx((prev) =>
        prev && prev.authenticated
          ? { ...prev, authenticated: false, user: null }
          : prev,
      );
    window.addEventListener('auth:unauthorized', onUnauthorized);
    return () => window.removeEventListener('auth:unauthorized', onUnauthorized);
  }, []);

  // When any API call gets a 409 password_change_required (an admin reset the
  // password mid-session), flip the flag so RequireAuth routes the user to
  // /change-password on the next render.
  useEffect(() => {
    const onPwChangeRequired = () =>
      setCtx((prev) =>
        prev?.user && !prev.user.must_change_password
          ? { ...prev, user: { ...prev.user, must_change_password: true } }
          : prev,
      );
    window.addEventListener('auth:password-change-required', onPwChangeRequired);
    return () => window.removeEventListener('auth:password-change-required', onPwChangeRequired);
  }, []);

  const value = useMemo(
    () => ({ loading, ctx, refresh, setUser }),
    [loading, ctx, refresh, setUser],
  );

  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>;
}

export function useAuth(): AuthState {
  const v = useContext(AuthCtx);
  if (!v) throw new Error('useAuth must be used within an AuthProvider');
  return v;
}
