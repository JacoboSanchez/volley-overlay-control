import { Suspense, lazy, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { useAuth } from '../auth/AuthContext';
import RequireAuth, { RouteLoading } from '../auth/RequireAuth';
import { SettingsProvider } from '../hooks/useSettings';

const App = lazy(() => import('../App'));

/** The control board, reachable three ways: owner (?oid= behind a login), an
 *  operator ?c=<control_token> capability link, or a public ?u=<username>&oid=
 *  bookmark. The two capability modes need no login. Kept out of AppRouter so
 *  its tests don't drag every other page into the module graph. */
export default function BoardPage() {
  const params = new URLSearchParams(useLocation().search);
  const controlToken = params.get('c');
  // Trim once at extraction: stray whitespace in a hand-copied bookmark URL
  // would fail the backend's token whitelist on every downstream use (API
  // credential, manifest query) — and a whitespace-only ``u`` is no ``u``.
  const publicUser = params.get('u')?.trim() || null;
  const oid = params.get('oid');
  const { loading, ctx } = useAuth();

  // A ?u=<username>&oid= bookmark opened by its signed-in owner is really an
  // owner visit: the cookie authorizes every board they own, so they get the
  // full owner experience (overlay switcher, sign-out) instead of the reduced
  // no-login one. Usernames are stored lowercased (see
  // app/auth/service.normalize_username), so compare accordingly.
  const ownBookmark =
    !!publicUser &&
    !controlToken &&
    !!ctx?.authenticated &&
    ctx.user?.username === publicUser.toLowerCase();

  // Point the PWA manifest at this specific board so an "Install app" (Chrome /
  // desktop) creates a launcher that reopens THIS board rather than the app
  // root. Covers the stable, no-login bookmark (username + oid) and the owner
  // board (?oid= behind a login — RequireAuth round-trips through /login and
  // returns here). Never the ?c= link: the control token is revocable, so
  // installing it would break when it's regenerated.
  useEffect(() => {
    if (!oid || controlToken) return undefined;
    const link = document.querySelector<HTMLLinkElement>('link[rel="manifest"]');
    if (!link) return undefined;
    const previous = link.getAttribute('href');
    const query = publicUser
      ? `u=${encodeURIComponent(publicUser)}&oid=${encodeURIComponent(oid)}`
      : `oid=${encodeURIComponent(oid)}`;
    link.setAttribute('href', `/manifest.webmanifest?${query}`);
    return () => {
      if (previous !== null) link.setAttribute('href', previous);
    };
  }, [publicUser, oid, controlToken]);

  // Hold the ?u= board until the auth probe answers: it decides owner vs
  // bookmark mode, and flipping credentials after the board has already
  // initialised would waste the first init round-trip.
  if (publicUser && !controlToken && (loading || !ctx)) return <RouteLoading />;

  const board = (
    <SettingsProvider>
      <Suspense fallback={<RouteLoading />}>
        <App
          controlToken={controlToken ?? undefined}
          publicUser={ownBookmark ? undefined : (publicUser ?? undefined)}
        />
      </Suspense>
    </SettingsProvider>
  );
  // A capability link is its own credential — no session cookie required.
  return controlToken || publicUser ? board : <RequireAuth>{board}</RequireAuth>;
}
