import { useCallback, useState } from 'react';
import { useI18n } from '../i18n';
import { useSettings, type ThemePreference } from '../hooks/useSettings';
import { useOrientation } from '../hooks/useOrientation';
import { useAsyncAction } from '../hooks/useAsyncAction';
import { updateCustomization } from '../api/board';
import type { SetSummaryStyle } from '../api/board';
import { ApiError } from '../api/http';
import ConfirmDialog from './ConfirmDialog';
import ConfigBottomBar from './config/ConfigBottomBar';
import ConfigErrorBanner from './config/ConfigErrorBanner';
import ConfigSectionBody from './config/ConfigSectionBody';
import ConfigSectionNav from './config/ConfigSectionNav';
import ConfigTopBar from './config/ConfigTopBar';
import { CONFIG_SECTIONS, type SectionId } from './config/sections';
import { useConfigModel } from './config/useConfigModel';
import { useConfigOptions } from './config/useConfigOptions';
import { useUnsavedChangesGuard } from './config/useUnsavedChangesGuard';
import type { ConfigModel } from './TeamCard';

export interface ConfigPanelProps {
  oid: string;
  customization: ConfigModel | null | undefined;
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
  /** Operator (shareable-link) mode: hide the owner-only Sign out control,
   *  which would otherwise drop the board to the OID picker the operator
   *  cannot use. */
  operator?: boolean;
  /**
   * Switch the board to another overlay the signed-in owner owns. When set
   * (owner mode only), the top bar swaps its static title for the
   * OverlaySwitcher, which names the current oid and lists the rest.
   * Capability/public-bookmark credentials cannot enumerate overlays, so
   * operator boards keep the plain title.
   */
  onSwitchOverlay?: ((oid: string) => void) | undefined;
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
  setSummaryStyle?: SetSummaryStyle;
  onChangeSetSummaryStyle?: (style: SetSummaryStyle) => void;
}

/**
 * The board's settings surface. This component owns the composition only —
 * the form model, the remote option lookups, the unsaved-changes guard, the
 * section registry and the two alternate layouts each live in their own
 * module under ``./config``.
 */
export default function ConfigPanel({
  oid,
  customization,
  gameConfig,
  autoSwapSides = null,
  onBack,
  onLogout,
  operator = false,
  onSwitchOverlay,
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

  const { model, isDirty, justSaved, updateField, applyPatch, markSaved } =
    useConfigModel(customization);
  const options = useConfigOptions(oid);
  const guardExit = useUnsavedChangesGuard(isDirty, onBack);

  // ``presets`` matches the deliberate CONFIG_SECTIONS ordering — the saved-
  // configuration entry point is what the operator should see first.
  const [activeSection, setActiveSection] = useState<SectionId | null>(CONFIG_SECTIONS[0].id);
  const [logoutConfirmOpen, setLogoutConfirmOpen] = useState(false);

  // Switching boards discards the staged (unsaved) model just like leaving
  // the panel does, so it goes through the same dirty-check as the back
  // button and the dashboard link.
  const handleSwitchOverlay = useCallback(
    (newOid: string) => {
      if (!onSwitchOverlay) return;
      guardExit(() => onSwitchOverlay(newOid));
    },
    [onSwitchOverlay, guardExit],
  );

  // Funnel both the explicit back button and a swipe-back gesture through
  // history.back() so the guard's popstate listener is the single exit point.
  // That keeps the pushed history entry consistently cleaned up regardless of
  // which one the operator used.
  const handleBack = useCallback(() => {
    window.history.back();
  }, []);

  const {
    run: handleSave,
    pending: saving,
    error: saveError,
    clearError: clearSaveError,
  } = useAsyncAction(
    async () => {
      await updateCustomization(oid, model);
      // Before awaiting the refresh below: the panel must commit clean as
      // early as possible so an immediate Back press doesn't prompt.
      // Staying in the panel is deliberate — the "Saved ✓" status is the
      // confirmation, and leaving remains an explicit back action.
      markSaved();
      if (onCustomizationSaved) await onCustomizationSaved();
    },
    {
      formatError: (e) =>
        e instanceof ApiError
          ? e.detail
          : e instanceof Error
            ? e.message
            : t('config.failedToSave'),
    },
  );

  const renderSection = useCallback(
    (section: SectionId | null) => (
      <ConfigSectionBody
        section={section}
        oid={oid}
        model={model}
        updateField={updateField}
        onApplyPatch={applyPatch}
        options={options}
        settings={settings}
        setSetting={setSetting}
        gameConfig={gameConfig}
        autoSwapSides={autoSwapSides}
        onShowShortcuts={onShowShortcuts}
        setSummaryStyle={setSummaryStyle}
        onChangeSetSummaryStyle={onChangeSetSummaryStyle}
      />
    ),
    [
      oid,
      model,
      updateField,
      applyPatch,
      options,
      settings,
      setSetting,
      gameConfig,
      autoSwapSides,
      onShowShortcuts,
      setSummaryStyle,
      onChangeSetSummaryStyle,
    ],
  );

  return (
    <div className="config-panel">
      <ConfigTopBar
        oid={oid}
        onBack={handleBack}
        onSwitchOverlay={onSwitchOverlay ? handleSwitchOverlay : undefined}
        operator={operator}
        isDirty={isDirty}
        guardExit={guardExit}
      />

      {options.failed && (
        <ConfigErrorBanner
          message={t('config.optionsLoadFailed')}
          onRetry={options.reload}
          retryDisabled={options.loading}
          testId="options-error-banner"
        />
      )}

      <div
        className={`config-body ${isPortrait ? 'config-body-portrait' : 'config-body-landscape'}`}
      >
        <ConfigSectionNav
          isPortrait={isPortrait}
          activeSection={activeSection}
          onSelect={setActiveSection}
          renderSection={renderSection}
        />
      </div>

      <ConfigBottomBar
        onSave={handleSave}
        saving={saving}
        canSave={isDirty}
        justSaved={justSaved}
        darkMode={darkMode}
        isFullscreen={isFullscreen}
        onToggleDarkMode={onToggleDarkMode}
        onToggleFullscreen={onToggleFullscreen}
        operator={operator}
        onLogout={() => setLogoutConfirmOpen(true)}
      />

      {saveError && (
        <ConfigErrorBanner
          message={saveError}
          onRetry={handleSave}
          retryDisabled={saving}
          onDismiss={clearSaveError}
          testId="save-error-banner"
        />
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
