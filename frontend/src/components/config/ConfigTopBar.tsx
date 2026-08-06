import { useI18n } from '../../i18n';
import OverlaySwitcher from './OverlaySwitcher';

export interface ConfigTopBarProps {
  oid: string;
  onBack: () => void;
  /** Owner mode only — capability boards cannot enumerate overlays. */
  onSwitchOverlay?: ((oid: string) => void) | undefined;
  operator: boolean;
  /** Whether the dashboard link has to ask before navigating away. */
  isDirty: boolean;
  /** Runs `action` once the operator has confirmed leaving. */
  guardExit: (action: () => void) => void;
}

/** Back, the board's identity (or switcher), and the dashboard link. */
export default function ConfigTopBar({
  oid,
  onBack,
  onSwitchOverlay,
  operator,
  isDirty,
  guardExit,
}: ConfigTopBarProps) {
  const { t } = useI18n();
  return (
    <div className="config-top-bar">
      <button
        className="config-top-btn"
        onClick={onBack}
        title={t('config.backToScoreboard')}
        aria-label={t('config.backToScoreboard')}
        data-testid="scoreboard-tab-button"
      >
        <span className="material-icons">arrow_back</span>
      </button>
      {!operator && onSwitchOverlay ? (
        // Owner mode: the centre slot names the board being controlled and
        // doubles as the switcher. The settings context is already obvious
        // from the surrounding panel, so the static title gives way.
        <OverlaySwitcher currentOid={oid} onSwitch={onSwitchOverlay} />
      ) : (
        <span className="config-top-title">{t('config.title')}</span>
      )}
      <a
        className="config-top-btn"
        href="/overlays"
        title={t('config.openManage')}
        aria-label={t('config.openManage')}
        data-testid="manage-link-button"
        onClick={(e) => {
          // A clean panel follows the href natively. A dirty one has to ask
          // first, and the prompt is async, so take the navigation over.
          if (!isDirty) return;
          e.preventDefault();
          guardExit(() => window.location.assign('/overlays'));
        }}
      >
        <span className="material-icons">dashboard</span>
      </a>
    </div>
  );
}
