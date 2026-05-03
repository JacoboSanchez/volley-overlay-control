import { useState, useCallback, useEffect, useMemo, useRef, lazy, Suspense } from 'react';
import { useI18n } from '../i18n';
import { useSettings, type ThemePreference } from '../hooks/useSettings';
import { useOrientation } from '../hooks/useOrientation';
import * as api from '../api/client';
import ConfigSkeleton from './ConfigSkeleton';
import type { ConfigModel, PredefinedTeams } from './TeamCard';
import type { LinksSectionLinks } from './config/LinksSection';
import type { ButtonsSectionProps } from './config/ButtonsSection';
import type { BehaviorSectionProps } from './config/BehaviorSection';

const TeamsSection = lazy(() => import('./config/TeamsSection'));
const OverlaySection = lazy(() => import('./config/OverlaySection'));
const PositionSection = lazy(() => import('./config/PositionSection'));
const ButtonsSection = lazy(() => import('./config/ButtonsSection'));
const BehaviorSection = lazy(() => import('./config/BehaviorSection'));
const LinksSection = lazy(() => import('./config/LinksSection'));
const MatchRulesSection = lazy(() => import('./config/MatchRulesSection'));

type Section = 'teams' | 'overlay' | 'position' | 'buttons' | 'rules' | 'behavior' | 'links';

const SECTIONS: readonly Section[] = [
  'teams', 'overlay', 'position', 'buttons', 'rules', 'behavior', 'links',
];
const SECTION_KEYS: Record<Section, string> = {
  teams: 'section.teams',
  overlay: 'section.overlay',
  position: 'section.position',
  buttons: 'section.buttons',
  rules: 'section.rules',
  behavior: 'section.behavior',
  links: 'section.links',
};
const SECTION_ICONS: Record<Section, string> = {
  teams: 'groups',
  overlay: 'palette',
  position: 'open_with',
  buttons: 'touch_app',
  rules: 'rule',
  behavior: 'tune',
  links: 'link',
};

type Themes = Record<string, ConfigModel>;
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
}

export default function ConfigPanel({
  oid,
  customization,
  gameConfig,
  onBack,
  onLogout,
  onCustomizationSaved,
  darkMode,
  isFullscreen,
  onToggleDarkMode,
  onToggleFullscreen,
}: ConfigPanelProps) {
  const { t } = useI18n();
  const { settings, setSetting } = useSettings();
  const { isPortrait } = useOrientation();

  const [model, setModel] = useState<ConfigModel>(() => ({ ...(customization ?? {}) }));
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    if (customization) {
      setModel({ ...customization });
    }
  }, [customization]);

  const isDirty = useMemo(
    () => JSON.stringify(model) !== JSON.stringify(customization ?? {}),
    [model, customization],
  );
  const isDirtyRef = useRef(isDirty);
  useEffect(() => { isDirtyRef.current = isDirty; }, [isDirty]);

  const [predefinedTeams, setPredefinedTeams] = useState<PredefinedTeams>({});
  const [themes, setThemes] = useState<Themes>({});
  const [styles, setStyles] = useState<string[]>([]);
  const [links, setLinks] = useState<LinksData>(null);
  const [selectedTheme, setSelectedTheme] = useState('');
  const [activeSection, setActiveSection] = useState<Section | null>('teams');

  useEffect(() => {
    let cancelled = false;
    api.getTeams().then((d) => { if (!cancelled) setPredefinedTeams(d as PredefinedTeams); }).catch(console.warn);
    api.getThemes().then((d) => { if (!cancelled) setThemes(d as Themes); }).catch(console.warn);
    api.getLinks(oid).then((d) => { if (!cancelled) setLinks(d as LinksData); }).catch(console.warn);
    api.getStyles(oid).then((d) => { if (!cancelled) setStyles(d); }).catch(console.warn);
    return () => { cancelled = true; };
  }, [oid]);

  const updateField = useCallback((key: string, value: unknown) => {
    setModel((m) => ({ ...m, [key]: value }));
  }, []);

  const bypassConfirmRef = useRef(false);
  const ignoreNextPopRef = useRef(false);

  const confirmExitIfDirty = useCallback(
    () => !isDirtyRef.current || window.confirm(t('config.unsavedChangesConfirm')),
    [t],
  );
  const confirmExitIfDirtyRef = useRef(confirmExitIfDirty);
  useEffect(() => { confirmExitIfDirtyRef.current = confirmExitIfDirty; }, [confirmExitIfDirty]);

  const onBackRef = useRef(onBack);
  useEffect(() => { onBackRef.current = onBack; }, [onBack]);

  // Funnel both the explicit back button and a successful save through
  // history.back() so the popstate listener is the single exit point. That
  // keeps the pushed history entry consistently cleaned up regardless of
  // whether the user leaves via the UI or a swipe-back gesture.
  const handleBack = useCallback(() => {
    window.history.back();
  }, []);

  const handleSave = useCallback(async () => {
    setSaving(true);
    setSaveError(null);
    try {
      await api.updateCustomization(oid, model);
      if (onCustomizationSaved) await onCustomizationSaved();
      bypassConfirmRef.current = true;
      window.history.back();
    } catch (e) {
      const msg = e instanceof Error ? e.message : t('config.failedToSave');
      setSaveError(msg);
    } finally {
      setSaving(false);
    }
  }, [oid, model, onCustomizationSaved, t]);

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

  const handleApplyTheme = useCallback((themeName: string) => {
    const themeData = themes[themeName];
    if (themeData) {
      setModel((m) => ({ ...m, ...themeData }));
    }
  }, [themes]);

  const isCustomOverlay = !!(
    links?.overlay && typeof links.overlay === 'string' && !links.overlay.includes('overlays.uno')
  );

  function renderSection(sec: Section | null) {
    switch (sec) {
      case 'teams':
        return <TeamsSection model={model} updateField={updateField} predefinedTeams={predefinedTeams} />;
      case 'overlay':
        return (
          <OverlaySection
            model={model}
            updateField={updateField}
            themes={themes}
            styles={styles}
            selectedTheme={selectedTheme}
            setSelectedTheme={setSelectedTheme}
            onApplyTheme={handleApplyTheme}
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
      case 'behavior':
        return (
          <BehaviorSection
            settings={settings}
            setSetting={setSetting as BehaviorSectionProps['setSetting']}
          />
        );
      case 'rules':
        return (
          <MatchRulesSection
            oid={oid}
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
        <button className="config-top-btn" onClick={handleBack} title={t('config.backToScoreboard')}
          data-testid="scoreboard-tab-button">
          <span className="material-icons">arrow_back</span>
        </button>
        <span className="config-top-title">{t('config.title')}</span>
        <div style={{ minWidth: 44 }} />
      </div>

      <div className={`config-body ${isPortrait ? 'config-body-portrait' : 'config-body-landscape'}`}>
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
                    <Suspense fallback={<ConfigSkeleton />}>
                      {renderSection(sec)}
                    </Suspense>
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
              <Suspense fallback={<ConfigSkeleton />}>
                {renderSection(activeSection)}
              </Suspense>
            </div>
          </>
        )}
      </div>

      <div className="config-bottom-bar">
        <button className="config-bottom-btn config-bottom-btn-save"
          onClick={handleSave} disabled={saving || !isDirty} title={t('config.saveCustomization')} data-testid="save-button">
          <span className="material-icons">save</span>
          <span>{saving ? '...' : t('config.save')}</span>
        </button>
        <div className="spacer" />
        <button className="config-bottom-btn config-bottom-btn-fullscreen"
          onClick={onToggleFullscreen}
          title={isFullscreen ? t('ctrl.exitFullscreen') : t('ctrl.fullscreen')}
          data-testid="fullscreen-button">
          <span className="material-icons">
            {isFullscreen ? 'fullscreen_exit' : 'fullscreen'}
          </span>
        </button>
        <button className="config-bottom-btn config-bottom-btn-theme"
          onClick={onToggleDarkMode}
          title={themeTitle(darkMode, t)}
          data-testid="dark-mode-button">
          <span className="material-icons">{themeIcon(darkMode)}</span>
        </button>
        <button className="config-bottom-btn config-bottom-btn-logout"
          onClick={() => { if (window.confirm(t('config.logoutConfirm'))) onLogout(); }}
          title={t('config.logout')} data-testid="logout-button">
          <span className="material-icons">logout</span>
        </button>
      </div>

      {saveError && (
        <div className="config-save-error">{saveError}</div>
      )}

    </div>
  );
}
