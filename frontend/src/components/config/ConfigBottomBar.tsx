import { useI18n } from '../../i18n';
import type { ThemePreference } from '../../hooks/useSettings';

function themeIcon(pref: ThemePreference): string {
  if (pref === 'auto') return 'brightness_auto';
  // Boolean: icon represents the *next* state — clicking it cycles
  // light → dark → auto.
  return pref ? 'light_mode' : 'dark_mode';
}

function themeTitle(pref: ThemePreference, t: (k: string) => string): string {
  if (pref === 'auto') return t('ctrl.themeAuto');
  return pref ? t('ctrl.lightMode') : t('ctrl.darkMode');
}

export interface ConfigBottomBarProps {
  onSave: () => void;
  saving: boolean;
  canSave: boolean;
  justSaved: boolean;
  darkMode: ThemePreference;
  isFullscreen: boolean;
  onToggleDarkMode: () => void;
  onToggleFullscreen: () => void;
  /** Operator (shareable-link) mode hides Sign out. */
  operator: boolean;
  onLogout: () => void;
}

/** Save + save status on the left, session-level toggles on the right. */
export default function ConfigBottomBar({
  onSave,
  saving,
  canSave,
  justSaved,
  darkMode,
  isFullscreen,
  onToggleDarkMode,
  onToggleFullscreen,
  operator,
  onLogout,
}: ConfigBottomBarProps) {
  const { t } = useI18n();
  return (
    <div className="config-bottom-bar">
      <button
        className="config-bottom-btn config-bottom-btn-save"
        onClick={onSave}
        disabled={saving || !canSave}
        title={t('config.saveCustomization')}
        data-testid="save-button"
      >
        <span className="material-icons">save</span>
        <span>{saving ? '...' : t('config.save')}</span>
      </button>
      {saving && (
        <span
          className="config-save-status config-save-status-pending"
          role="status"
          aria-live="polite"
          data-testid="save-status-pending"
        >
          <span className="material-icons">cloud_upload</span>
          {t('config.saving')}
        </span>
      )}
      {!saving && justSaved && (
        <span
          className="config-save-status config-save-status-saved"
          role="status"
          aria-live="polite"
          data-testid="save-status-saved"
        >
          <span className="material-icons">check_circle</span>
          {t('config.saved')}
        </span>
      )}
      <div className="spacer" />
      <button
        className="config-bottom-btn config-bottom-btn-fullscreen"
        onClick={onToggleFullscreen}
        title={isFullscreen ? t('ctrl.exitFullscreen') : t('ctrl.fullscreen')}
        aria-label={isFullscreen ? t('ctrl.exitFullscreen') : t('ctrl.fullscreen')}
        data-testid="fullscreen-button"
      >
        <span className="material-icons">{isFullscreen ? 'fullscreen_exit' : 'fullscreen'}</span>
      </button>
      <button
        className="config-bottom-btn config-bottom-btn-theme"
        onClick={onToggleDarkMode}
        title={themeTitle(darkMode, t)}
        aria-label={themeTitle(darkMode, t)}
        data-testid="dark-mode-button"
      >
        <span className="material-icons">{themeIcon(darkMode)}</span>
      </button>
      {!operator && (
        <button
          className="config-bottom-btn config-bottom-btn-logout"
          onClick={onLogout}
          title={t('config.logout')}
          aria-label={t('config.logout')}
          data-testid="logout-button"
        >
          <span className="material-icons">logout</span>
        </button>
      )}
    </div>
  );
}
