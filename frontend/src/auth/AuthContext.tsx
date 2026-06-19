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
      const fallback: api.AuthContext = {
        authenticated: false,
        user: null,
        registration_open: true,
        needs_admin_bootstrap: false,
      };
      setCtx(fallback);
      return fallback;
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
