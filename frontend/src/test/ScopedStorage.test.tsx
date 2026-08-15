import { useEffect } from 'react';
import { act, render, renderHook, screen, waitFor } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { I18nProvider, useI18n } from '../i18n';
import { SettingsProvider, useSettings } from '../hooks/useSettings';
import { useOidSession } from '../hooks/useOidSession';
import {
  GUEST_STORAGE_SCOPE,
  ScopedStorageProvider,
  getScopedItem,
  resolveRouteStorageScope,
  setScopedItem,
  storageKey,
  type StorageScope,
} from '../storage/ScopedStorage';

describe('account-scoped browser storage', () => {
  it('moves every legacy value to only the first account that reads it', () => {
    localStorage.setItem('volley_lang', 'es');
    localStorage.setItem('volley_darkMode', 'false');
    localStorage.setItem('volley_oid', 'centre-court');
    localStorage.setItem('volley_recentColors', '["#123456"]');

    expect(getScopedItem('user:17', 'lang')).toBe('es');
    expect(getScopedItem('user:17', 'darkMode')).toBe('false');
    expect(getScopedItem('user:17', 'oid')).toBe('centre-court');
    expect(getScopedItem('user:17', 'recentColors')).toBe('["#123456"]');
    expect(localStorage.getItem('volley_lang')).toBeNull();
    expect(localStorage.getItem('volley_oid')).toBeNull();

    // The global migration marker prevents a second account from inheriting
    // the same pre-upgrade preferences.
    expect(getScopedItem('user:23', 'lang')).toBeNull();
    expect(getScopedItem('user:23', 'oid')).toBeNull();
  });

  it('keeps writes and removals independent between accounts and guests', () => {
    setScopedItem('user:1', 'lang', 'es');
    setScopedItem('user:2', 'lang', 'de');
    setScopedItem(GUEST_STORAGE_SCOPE, 'lang', 'fr');

    expect(getScopedItem('user:1', 'lang')).toBe('es');
    expect(getScopedItem('user:2', 'lang')).toBe('de');
    expect(getScopedItem(GUEST_STORAGE_SCOPE, 'lang')).toBe('fr');
  });

  it('uses guest scope for capability links without putting the token in a key', () => {
    const token = 'secret-control-token';
    const scope = resolveRouteStorageScope('/board', `?c=${token}&oid=court`, {
      id: 7,
      storage_namespace: 'account-seven',
      username: 'owner',
    });

    expect(scope).toBe(GUEST_STORAGE_SCOPE);
    expect(storageKey(scope, 'darkMode')).not.toContain(token);
  });

  it('uses account scope for owner boards and guest scope for another public bookmark', () => {
    const owner = { id: 7, storage_namespace: 'account-seven', username: 'owner' };
    expect(resolveRouteStorageScope('/board', '?oid=court', owner)).toBe('user:account-seven');
    expect(resolveRouteStorageScope('/board', '?u=OWNER&oid=court', owner)).toBe(
      'user:account-seven',
    );
    expect(resolveRouteStorageScope('/board', '?u=other&oid=court', owner)).toBe('guest');
  });

  it('does not reuse storage when a database id is assigned to a new account', () => {
    const deleted = { id: 7, storage_namespace: 'deleted-account', username: 'old' };
    const replacement = { id: 7, storage_namespace: 'replacement-account', username: 'new' };

    const deletedScope = resolveRouteStorageScope('/', '', deleted);
    const replacementScope = resolveRouteStorageScope('/', '', replacement);
    setScopedItem(deletedScope, 'lang', 'es');

    expect(replacementScope).not.toBe(deletedScope);
    expect(getScopedItem(replacementScope, 'lang')).toBeNull();
  });
});

function PreferenceProbe() {
  const { lang } = useI18n();
  const { settings } = useSettings();
  return (
    <div>
      <span data-testid="scope-lang">{lang}</span>
      <span data-testid="scope-preview">{String(settings.showPreview)}</span>
    </div>
  );
}

function PreferenceTree({ scope }: { scope: StorageScope }) {
  return (
    <ScopedStorageProvider scope={scope}>
      <I18nProvider>
        <SettingsProvider>
          <PreferenceProbe />
        </SettingsProvider>
      </I18nProvider>
    </ScopedStorageProvider>
  );
}

describe('providers react to an account change', () => {
  it('reloads language and board preferences from the new account', async () => {
    // Seed the migration marker through an initial write, then populate both
    // explicit scopes so neither test account can consume legacy state.
    setScopedItem('user:1', 'lang', 'es');
    setScopedItem('user:1', 'showPreview', 'false');
    setScopedItem('user:2', 'lang', 'de');
    setScopedItem('user:2', 'showPreview', 'true');

    const view = render(<PreferenceTree scope="user:1" />);
    expect(screen.getByTestId('scope-lang')).toHaveTextContent('es');
    expect(screen.getByTestId('scope-preview')).toHaveTextContent('false');

    view.rerender(<PreferenceTree scope="user:2" />);
    await waitFor(() => expect(screen.getByTestId('scope-lang')).toHaveTextContent('de'));
    expect(screen.getByTestId('scope-preview')).toHaveTextContent('true');
  });
});

describe('recent overlay isolation', () => {
  it('boots and clears only the active account OID', () => {
    setScopedItem('user:1', 'oid', 'court-one');
    setScopedItem('user:2', 'oid', 'court-two');

    const first = renderHook(() => useOidSession({ storageScope: 'user:1' }));
    expect(first.result.current.oid).toBe('court-one');
    act(() => first.result.current.handleLogout());
    expect(getScopedItem('user:1', 'oid')).toBeNull();
    expect(getScopedItem('user:2', 'oid')).toBe('court-two');
    first.unmount();
  });

  it('persists a setting under the provider account', () => {
    function Setter() {
      const { setSetting } = useSettings();
      useEffect(() => setSetting('showPreview', false), [setSetting]);
      return null;
    }

    render(
      <ScopedStorageProvider scope="user:41">
        <SettingsProvider>
          <Setter />
        </SettingsProvider>
      </ScopedStorageProvider>,
    );

    expect(getScopedItem('user:41', 'showPreview')).toBe('false');
    expect(getScopedItem(GUEST_STORAGE_SCOPE, 'showPreview')).toBeNull();
  });
});
