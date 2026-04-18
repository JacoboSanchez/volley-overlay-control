import { useState, useCallback, useEffect } from 'react';
import { useI18n } from '../i18n';
import { useSettings } from '../hooks/useSettings';
import { useOrientation } from '../hooks/useOrientation';
import * as api from '../api/client';
import TeamsSection from './config/TeamsSection';
import OverlaySection from './config/OverlaySection';
import PositionSection from './config/PositionSection';
import ButtonsSection, { ButtonsSectionProps } from './config/ButtonsSection';
import BehaviorSection, { BehaviorSectionProps } from './config/BehaviorSection';
import LinksSection from './config/LinksSection';
import type { ConfigModel, PredefinedTeams } from './TeamCard';
import type { LinksSectionLinks } from './config/LinksSection';

type Section = 'teams' | 'overlay' | 'position' | 'buttons' | 'behavior' | 'links';

const SECTIONS: readonly Section[] = ['teams', 'overlay', 'position', 'buttons', 'behavior', 'links'];
const SECTION_KEYS: Record<Section, string> = {
  teams: 'section.teams',
  overlay: 'section.overlay',
  position: 'section.position',
  buttons: 'section.buttons',
  behavior: 'section.behavior',
  links: 'section.links',
};
const SECTION_ICONS: Record<Section, string> = {
  teams: 'groups',
  overlay: 'palette',
  position: 'open_with',
  buttons: 'touch_app',
  behavior: 'tune',
  links: 'link',
};

type Themes = Record<string, ConfigModel>;
type LinksData = LinksSectionLinks | null;

export interface ConfigPanelProps {
  oid: string;
  customization: ConfigModel | null | undefined;
  actions?: unknown;
  onBack: () => void;
  onReset: () => void;
  onLogout: () => void;
  onCustomizationSaved?: () => void | Promise<void>;
  onCustomizationRefreshed?: (fresh: ConfigModel) => void;
}

export default function ConfigPanel({
  oid,
  customization,
  onBack,
  onReset,
  onLogout,
  onCustomizationSaved,
  onCustomizationRefreshed,
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

  const [refreshing, setRefreshing] = useState(false);
  const [predefinedTeams, setPredefinedTeams] = useState<PredefinedTeams>({});
  const [themes, setThemes] = useState<Themes>({});
  const [styles, setStyles] = useState<string[]>([]);
  const [links, setLinks] = useState<LinksData>(null);
  const [selectedTheme, setSelectedTheme] = useState('');
  const [activeSection, setActiveSection] = useState<Section | null>('teams');

  useEffect(() => {
    api.getTeams().then((d) => setPredefinedTeams(d as PredefinedTeams)).catch(console.warn);
    api.getThemes().then((d) => setThemes(d as Themes)).catch(console.warn);
    api.getLinks(oid).then((d) => setLinks(d as LinksData)).catch(console.warn);
    api.getStyles(oid).then(setStyles).catch(console.warn);
  }, [oid]);

  const updateField = useCallback((key: string, value: unknown) => {
    setModel((m) => ({ ...m, [key]: value }));
  }, []);

  const handleSave = useCallback(async () => {
    setSaving(true);
    setSaveError(null);
    try {
      await api.updateCustomization(oid, model);
      if (onCustomizationSaved) await onCustomizationSaved();
      onBack();
    } catch (e) {
      const msg = e instanceof Error ? e.message : t('config.failedToSave');
      setSaveError(msg);
    } finally {
      setSaving(false);
    }
  }, [oid, model, onBack, onCustomizationSaved, t]);

  const handleRefresh = useCallback(async () => {
    if (!window.confirm(t('config.reloadConfirm'))) return;
    setRefreshing(true);
    try {
      const fresh = await api.getCustomization(oid);
      setModel({ ...fresh });
      if (onCustomizationRefreshed) onCustomizationRefreshed(fresh);
    } finally {
      setRefreshing(false);
    }
  }, [oid, t, onCustomizationRefreshed]);

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
      case 'links':
        return <LinksSection links={links} />;
      default:
        return null;
    }
  }

  return (
    <div className="config-panel">
      <div className="config-top-bar">
        <button className="config-top-btn" onClick={onBack} title={t('config.backToScoreboard')}
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
                    {renderSection(sec)}
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
              {renderSection(activeSection)}
            </div>
          </>
        )}
      </div>

      <div className="config-bottom-bar">
        <button className="config-bottom-btn config-bottom-btn-save"
          onClick={handleSave} disabled={saving} title={t('config.saveCustomization')} data-testid="save-button">
          <span className="material-icons">save</span>
          <span>{saving ? '...' : t('config.save')}</span>
        </button>
        <div className="spacer" />
        <button className="config-bottom-btn config-bottom-btn-refresh" onClick={handleRefresh}
          disabled={refreshing} title={t('config.reloadFromServer')} data-testid="refresh-button">
          <span className="material-icons">sync</span>
        </button>
        <button className="config-bottom-btn config-bottom-btn-reset" onClick={onReset}
          title={t('config.resetMatch')} data-testid="reset-button">
          <span className="material-icons">recycling</span>
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
