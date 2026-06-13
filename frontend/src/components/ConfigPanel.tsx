import { useState, useCallback, useEffect, useRef, lazy, Suspense } from 'react';
import { useI18n } from '../i18n';
import { useSettings, type ThemePreference } from '../hooks/useSettings';
import { useOrientation } from '../hooks/useOrientation';
import { useAsyncAction } from '../hooks/useAsyncAction';
import * as api from '../api/client';
import ConfigSkeleton from './ConfigSkeleton';
import ConfirmDialog from './ConfirmDialog';
import type { ConfigModel, PredefinedTeams } from './TeamCard';
import type { LinksSectionLinks } from './config/LinksSection';
import type { ButtonsSectionProps } from './config/ButtonsSection';
import type { DisplaySectionProps } from './config/DisplaySection';
import type { StatsSectionProps } from './config/StatsSection';
import type { RecapSectionProps } from './config/RecapSection';
import type { GeneralSectionProps } from './config/GeneralSection';

const TeamsSection = lazy(() => import('./config/TeamsSection'));
const OverlaySection = lazy(() => import('./config/OverlaySection'));
const PositionSection = lazy(() => import('./config/PositionSection'));
const ButtonsSection = lazy(() => import('./config/ButtonsSection'));
const DisplaySection = lazy(() => import('./config/DisplaySection'));
const StatsSection = lazy(() => import('./config/StatsSection'));
const RecapSection = lazy(() => import('./config/RecapSection'));
const GeneralSection = lazy(() => import('./config/GeneralSection'));
const LinksSection = lazy(() => import('./config/LinksSection'));
const MatchRulesSection = lazy(() => import('./config/MatchRulesSection'));
const PresetPicker = lazy(() => import('./PresetPicker'));

type Section =
  | 'presets'
  | 'teams'
  | 'overlay'
  | 'position'
  | 'buttons'
  | 'rules'
  | 'display'
  | 'stats'
  | 'recap'
  | 'general'
  | 'links';

// ``presets`` sits at the top so the operator notices the
// saved-configuration entry point before drilling into individual
// fields. Both env-driven ``APP_THEMES`` entries and operator-saved
// presets live in that single section.
const SECTIONS: readonly Section[] = [
  'presets',
  'teams',
  'overlay',
  'position',
  'buttons',
  'rules',
  'display',
  'stats',
  'recap',
  'general',
  'links',
];
const SECTION_KEYS: Record<Section, string> = {
  presets: 'section.presets',
  teams: 'section.teams',
  overlay: 'section.overlay',
  position: 'section.position',
  buttons: 'section.buttons',
  rules: 'section.rules',
  display: 'section.display',
  stats: 'section.stats',
  recap: 'section.recap',
  general: 'section.general',
  links: 'section.links',
};
const SECTION_ICONS: Record<Section, string> = {
  presets: 'bookmarks',
  teams: 'groups',
  overlay: 'palette',
  position: 'open_with',
  buttons: 'touch_app',
  rules: 'rule',
  display: 'visibility',
  stats: 'query_stats',
  recap: 'summarize',
  general: 'settings',
  links: 'link',
};

type LinksData = LinksSectionLinks | null;

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

export interface ConfigPanelProps {
  oid: string;
  customization: ConfigModel | null | undefined;
  actions?: unknown;
  /**
   * Live ``state.config`` from useGameState. Used by the
   * MatchRulesSection; ``null`` while the WebSocket is still
   * connecting.
   */
  gameConfig?: Record<string, unknown> | null;
  /** Live ``state.auto_swap_sides`` — drives the rules-section toggle. */
  autoSwapSides?: boolean | null;
  onBack: () => void;
  onLogout: () => void;
  onCustomizationSaved?: () => void | Promise<void>;
  /**
   * Theme + fullscreen toggles live in this panel — they're
   * once-per-session decisions and don't earn a permanent slot in
   * the in-game HUD. The HUD now owns Start-match / Reset instead.
   */
  darkMode: ThemePreference;
  isFullscreen: boolean;
  onToggleDarkMode: () => void;
  onToggleFullscreen: () => void;
  /**
   * Opens the keyboard shortcuts help modal. Only meaningful while
   * ``settings.keyboardShortcuts`` is on — the GeneralSection
   * surfaces the entry point conditionally.
   */
  onShowShortcuts?: () => void;
  /**
   * Set summary overlay style (forwarded to RecapSection so the
   * operator can pick the default style right next to the enable
   * toggle without having to activate the recap first).
   */
  setSummaryStyle?: import('../api/client').SetSummaryStyle;
  onChangeSetSummaryStyle?: (style: import('../api/client').SetSummaryStyle) => void;
}

export default function ConfigPanel({
  oid,
  customization,
  gameConfig,
  autoSwapSides = null,
  onBack,
  onLogout,
  onCustomizationSaved,
  darkMode,
  isFullscreen,
  onToggleDarkMode,
  onToggleFullscreen,
  onShowShortcuts,
  setSummaryStyle,
  onChangeSetSummaryStyle,
}: ConfigPanelProps) {
  const { t } = useI18n();
  const { settings, setSetting } = useSettings();
  const { isPortrait } = useOrientation();

  const [model, setModel] = useState<ConfigModel>(() => ({ ...(customization ?? {}) }));
  // Track dirtiness via a flag toggled by the mutation paths (updateField,
  // theme apply) instead of comparing model and customization with a
  // double JSON.stringify on every render. The form has many fields and
  // gets a setModel on every keystroke; the JSON.stringify approach was
  // O(n) per render in both depth and key count.
  const [isDirty, setIsDirty] = useState(false);

  useEffect(() => {
    if (customization) {
      setModel({ ...customization });
      setIsDirty(false);
    }
  }, [customization]);

  const isDirtyRef = useRef(isDirty);
  useEffect(() => {
    isDirtyRef.current = isDirty;
  }, [isDirty]);

  const [predefinedTeams, setPredefinedTeams] = useState<PredefinedTeams>({});
  const [styles, setStyles] = useState<string[]>([]);
  const [styleCaps, setStyleCaps] = useState<Record<string, api.StyleCapabilities>>({});
  const [links, setLinks] = useState<LinksData>(null);
  const [activeSection, setActiveSection] = useState<Section | null>('teams');
  const [logoutConfirmOpen, setLogoutConfirmOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .getTeams()
      .then((d) => {
        if (!cancelled) setPredefinedTeams(d as PredefinedTeams);
      })
      .catch(console.warn);
    api
      .getLinks(oid)
      .then((d) => {
        if (!cancelled) setLinks(d as LinksData);
      })
      .catch(console.warn);
    api
      .getStyles(oid)
      .then((d) => {
        if (!cancelled) setStyles(d);
      })
      .catch(console.warn);
    api
      .getStyleCapabilities(oid)
      .then((d) => {
        if (!cancelled) setStyleCaps(d);
      })
      .catch(console.warn);
    return () => {
      cancelled = true;
    };
  }, [oid]);

  const updateField = useCallback((key: string, value: unknown) => {
    setModel((m) => ({ ...m, [key]: value }));
    setIsDirty(true);
  }, []);

  const bypassConfirmRef = useRef(false);
  const ignoreNextPopRef = useRef(false);

  const confirmExitIfDirty = useCallback(
    () => !isDirtyRef.current || window.confirm(t('config.unsavedChangesConfirm')),
    [t],
  );
  const confirmExitIfDirtyRef = useRef(confirmExitIfDirty);
  useEffect(() => {
    confirmExitIfDirtyRef.current = confirmExitIfDirty;
  }, [confirmExitIfDirty]);

  const onBackRef = useRef(onBack);
  useEffect(() => {
    onBackRef.current = onBack;
  }, [onBack]);

  // Funnel both the explicit back button and a successful save through
  // history.back() so the popstate listener is the single exit point. That
  // keeps the pushed history entry consistently cleaned up regardless of
  // whether the user leaves via the UI or a swipe-back gesture.
  const handleBack = useCallback(() => {
    window.history.back();
  }, []);

  const {
    run: handleSave,
    pending: saving,
    error: saveError,
  } = useAsyncAction(
    async () => {
      await api.updateCustomization(oid, model);
      setIsDirty(false);
      if (onCustomizationSaved) await onCustomizationSaved();
      bypassConfirmRef.current = true;
      window.history.back();
    },
    {
      formatError: (e) => (e instanceof Error ? e.message : t('config.failedToSave')),
    },
  );

  useEffect(() => {
    window.history.pushState({ configOpen: true }, '');
    const handlePopState = () => {
      if (ignoreNextPopRef.current) {
        ignoreNextPopRef.current = false;
        return;
      }
      if (bypassConfirmRef.current) {
        bypassConfirmRef.current = false;
        onBackRef.current();
        return;
      }
      if (!confirmExitIfDirtyRef.current()) {
        // Restore the configOpen entry by going forward instead of pushing
        // a new one, so repeated cancels don't grow the history stack.
        ignoreNextPopRef.current = true;
        window.history.go(1);
        return;
      }
      onBackRef.current();
    };
    window.addEventListener('popstate', handlePopState);
    return () => {
      window.removeEventListener('popstate', handlePopState);
    };
  }, []);

  // ``PresetPicker`` (load) shares the same staging semantics as
  // direct field edits: shallow-merge the patch into ``model``, mark
  // the panel dirty, and let the existing Save button persist. Avoids
  // racing the operator's unsaved changes.
  const handleApplyPatch = useCallback((patch: ConfigModel) => {
    setModel((m) => ({ ...m, ...patch }));
    setIsDirty(true);
  }, []);

  const isCustomOverlay = !!(
    links?.overlay &&
    typeof links.overlay === 'string' &&
    !links.overlay.includes('overlays.uno')
  );

  function renderSection(sec: Section | null) {
    switch (sec) {
      case 'presets':
        return <PresetPicker model={model} onApplyPatch={handleApplyPatch} />;
      case 'teams':
        return (
          <TeamsSection model={model} updateField={updateField} predefinedTeams={predefinedTeams} />
        );
      case 'overlay':
        return (
          <OverlaySection
            model={model}
            updateField={updateField}
            styles={styles}
            capabilities={styleCaps}
            isCustomOverlay={isCustomOverlay}
          />
        );
      case 'position':
        return <PositionSection model={model} updateField={updateField} />;
      case 'buttons':
        return (
          <ButtonsSection
            settings={settings}
            setSetting={setSetting as ButtonsSectionProps['setSetting']}
          />
        );
      case 'display':
        return (
          <DisplaySection
            settings={settings}
            setSetting={setSetting as DisplaySectionProps['setSetting']}
          />
        );
      case 'stats':
        return (
          <StatsSection
            settings={settings}
            setSetting={setSetting as StatsSectionProps['setSetting']}
          />
        );
      case 'recap':
        return (
          <RecapSection
            settings={settings}
            setSetting={setSetting as RecapSectionProps['setSetting']}
            setSummaryStyle={setSummaryStyle}
            onChangeSetSummaryStyle={onChangeSetSummaryStyle}
          />
        );
      case 'general':
        return (
          <GeneralSection
            settings={settings}
            setSetting={setSetting as GeneralSectionProps['setSetting']}
            onShowShortcuts={onShowShortcuts}
          />
        );
      case 'rules':
        return (
          <MatchRulesSection
            oid={oid}
            autoSwapSides={autoSwapSides}
            mode={(gameConfig?.mode as api.MatchMode | undefined) ?? null}
            pointsLimit={(gameConfig?.points_limit as number | undefined) ?? null}
            pointsLimitLastSet={(gameConfig?.points_limit_last_set as number | undefined) ?? null}
            setsLimit={(gameConfig?.sets_limit as number | undefined) ?? null}
          />
        );
      case 'links':
        return <LinksSection links={links} />;
      default:
        return null;
    }
  }

  return (
    <div className="config-panel">
      <div className="config-top-bar">
        <button
          className="config-top-btn"
          onClick={handleBack}
          title={t('config.backToScoreboard')}
          data-testid="scoreboard-tab-button"
        >
          <span className="material-icons">arrow_back</span>
        </button>
        <span className="config-top-title">{t('config.title')}</span>
        <a
          className="config-top-btn"
          href="/manage"
          title={t('config.openManage')}
          aria-label={t('config.openManage')}
          data-testid="manage-link-button"
          onClick={(e) => {
            if (!confirmExitIfDirtyRef.current()) e.preventDefault();
          }}
        >
          <span className="material-icons">dashboard</span>
        </a>
      </div>

      <div
        className={`config-body ${isPortrait ? 'config-body-portrait' : 'config-body-landscape'}`}
      >
        {isPortrait ? (
          <div className="config-accordion">
            {SECTIONS.map((sec) => (
              <div key={sec} className="config-accordion-item">
                <button
                  className={`config-accordion-header ${activeSection === sec ? 'config-accordion-header-active' : ''}`}
                  onClick={() => setActiveSection(activeSection === sec ? null : sec)}
                >
                  <span className="material-icons">{SECTION_ICONS[sec]}</span>
                  {t(SECTION_KEYS[sec])}
                  <span className="material-icons config-accordion-chevron">
                    {activeSection === sec ? 'expand_less' : 'expand_more'}
                  </span>
                </button>
                {activeSection === sec && (
                  <div className="config-accordion-body">
                    <Suspense fallback={<ConfigSkeleton />}>{renderSection(sec)}</Suspense>
                  </div>
                )}
              </div>
            ))}
          </div>
        ) : (
          <>
            <nav className="config-sidebar">
              {SECTIONS.map((sec) => (
                <button
                  key={sec}
                  className={`config-sidebar-item ${activeSection === sec ? 'config-sidebar-item-active' : ''}`}
                  onClick={() => setActiveSection(sec)}
                >
                  <span className="material-icons">{SECTION_ICONS[sec]}</span>
                  <span className="config-sidebar-label">{t(SECTION_KEYS[sec])}</span>
                </button>
              ))}
            </nav>
            <div className="config-section-content">
              <Suspense fallback={<ConfigSkeleton />}>{renderSection(activeSection)}</Suspense>
            </div>
          </>
        )}
      </div>

      <div className="config-bottom-bar">
        <button
          className="config-bottom-btn config-bottom-btn-save"
          onClick={handleSave}
          disabled={saving || !isDirty}
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
        <div className="spacer" />
        <button
          className="config-bottom-btn config-bottom-btn-fullscreen"
          onClick={onToggleFullscreen}
          title={isFullscreen ? t('ctrl.exitFullscreen') : t('ctrl.fullscreen')}
          data-testid="fullscreen-button"
        >
          <span className="material-icons">{isFullscreen ? 'fullscreen_exit' : 'fullscreen'}</span>
        </button>
        <button
          className="config-bottom-btn config-bottom-btn-theme"
          onClick={onToggleDarkMode}
          title={themeTitle(darkMode, t)}
          data-testid="dark-mode-button"
        >
          <span className="material-icons">{themeIcon(darkMode)}</span>
        </button>
        <button
          className="config-bottom-btn config-bottom-btn-logout"
          onClick={() => setLogoutConfirmOpen(true)}
          title={t('config.logout')}
          data-testid="logout-button"
        >
          <span className="material-icons">logout</span>
        </button>
      </div>

      {saveError && (
        <div className="config-save-error" role="alert" data-testid="save-error-banner">
          <span className="material-icons" aria-hidden="true">
            error_outline
          </span>
          <span className="config-save-error-message">{saveError}</span>
          <button
            type="button"
            className="config-save-error-retry"
            onClick={handleSave}
            disabled={saving}
            data-testid="save-error-retry"
          >
            <span className="material-icons" aria-hidden="true">
              refresh
            </span>
            {t('config.retry')}
          </button>
        </div>
      )}

      <ConfirmDialog
        open={logoutConfirmOpen}
        message={t('config.logoutConfirm')}
        confirmLabel={t('config.logout')}
        danger
        onConfirm={() => {
          onLogout();
          setLogoutConfirmOpen(false);
        }}
        onClose={() => setLogoutConfirmOpen(false)}
      />
    </div>
  );
}
