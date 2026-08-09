import { createContext, useContext, useMemo, type ReactNode } from 'react';
import { useLocation } from 'react-router';
import { useAuth } from '../auth/AuthContext';

export type StorageScope = 'guest' | `user:${number}`;

export const GUEST_STORAGE_SCOPE: StorageScope = 'guest';

const LEGACY_PREFIX = 'volley_';
const USER_PREFIX = 'volley:user:';
const MIGRATION_MARKER = 'volley:account-storage-migration:v1';

function userScope(userId: number): StorageScope {
  return `user:${userId}`;
}

export function storageKey(scope: StorageScope, name: string): string {
  return scope === GUEST_STORAGE_SCOPE
    ? `${LEGACY_PREFIX}${name}`
    : `${USER_PREFIX}${scope.slice('user:'.length)}:${name}`;
}

export function storagePrefix(scope: StorageScope): string {
  return scope === GUEST_STORAGE_SCOPE
    ? LEGACY_PREFIX
    : `${USER_PREFIX}${scope.slice('user:'.length)}:`;
}

/** Move every pre-account ``volley_*`` value to the first signed-in account.
 *
 * The marker is deliberately global: without it, account B would inherit the
 * same legacy values after account A had already read them. User-scoped keys
 * use ``volley:`` (not ``volley_``), so a retry after a partial storage error
 * can never mistake already-migrated data for another legacy setting.
 */
export function migrateLegacyStorage(scope: StorageScope): void {
  if (scope === GUEST_STORAGE_SCOPE) return;
  try {
    if (localStorage.getItem(MIGRATION_MARKER) !== null) return;
    const legacyKeys: string[] = [];
    for (let index = 0; index < localStorage.length; index += 1) {
      const key = localStorage.key(index);
      if (key?.startsWith(LEGACY_PREFIX)) legacyKeys.push(key);
    }
    for (const legacyKey of legacyKeys) {
      const value = localStorage.getItem(legacyKey);
      if (value === null) continue;
      const name = legacyKey.slice(LEGACY_PREFIX.length);
      const target = storageKey(scope, name);
      if (localStorage.getItem(target) === null) localStorage.setItem(target, value);
    }
    for (const legacyKey of legacyKeys) localStorage.removeItem(legacyKey);
    localStorage.setItem(MIGRATION_MARKER, scope);
  } catch (error) {
    console.warn('Failed to migrate browser preferences:', error);
  }
}

export function getScopedItem(scope: StorageScope, name: string): string | null {
  migrateLegacyStorage(scope);
  return localStorage.getItem(storageKey(scope, name));
}

export function setScopedItem(scope: StorageScope, name: string, value: string): void {
  migrateLegacyStorage(scope);
  localStorage.setItem(storageKey(scope, name), value);
}

export function removeScopedItem(scope: StorageScope, name: string): void {
  migrateLegacyStorage(scope);
  localStorage.removeItem(storageKey(scope, name));
}

export interface StorageRouteUser {
  id: number;
  username: string;
}

/** Resolve account versus credential-link storage without retaining a token. */
export function resolveRouteStorageScope(
  pathname: string,
  search: string,
  user: StorageRouteUser | null,
): StorageScope {
  if (pathname.replace(/\/+$/, '') === '/board') {
    const params = new URLSearchParams(search);
    if (params.has('c')) return GUEST_STORAGE_SCOPE;
    const publicUser = params.get('u')?.trim().toLowerCase();
    if (publicUser && publicUser !== user?.username.toLowerCase()) {
      return GUEST_STORAGE_SCOPE;
    }
  }
  return user ? userScope(user.id) : GUEST_STORAGE_SCOPE;
}

const StorageScopeContext = createContext<StorageScope>(GUEST_STORAGE_SCOPE);

export function ScopedStorageProvider({
  scope,
  children,
}: {
  scope: StorageScope;
  children: ReactNode;
}) {
  return <StorageScopeContext.Provider value={scope}>{children}</StorageScopeContext.Provider>;
}

export function RouteStorageScopeProvider({ children }: { children: ReactNode }) {
  const { ctx } = useAuth();
  const location = useLocation();
  const user = ctx?.authenticated && ctx.user ? ctx.user : null;
  const scope = useMemo(
    () => resolveRouteStorageScope(location.pathname, location.search, user),
    [location.pathname, location.search, user],
  );
  return <ScopedStorageProvider scope={scope}>{children}</ScopedStorageProvider>;
}

export function useStorageScope(): StorageScope {
  return useContext(StorageScopeContext);
}
