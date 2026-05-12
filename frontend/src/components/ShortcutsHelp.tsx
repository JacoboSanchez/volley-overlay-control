import { useI18n } from '../i18n';
import Dialog from './Dialog';
import { SHORTCUT_BINDINGS } from '../hooks/useKeyboardShortcuts';

export interface ShortcutsHelpProps {
  open: boolean;
  onClose: () => void;
}

interface Row {
  keys: readonly string[];
  labelKey: string;
}

const ROWS: Row[] = [
  { keys: SHORTCUT_BINDINGS.pointTeam1, labelKey: 'shortcuts.pointTeam1' },
  { keys: SHORTCUT_BINDINGS.pointTeam2, labelKey: 'shortcuts.pointTeam2' },
  { keys: SHORTCUT_BINDINGS.undo, labelKey: 'shortcuts.undo' },
  { keys: SHORTCUT_BINDINGS.serveTeam1, labelKey: 'shortcuts.serveTeam1' },
  { keys: SHORTCUT_BINDINGS.serveTeam2, labelKey: 'shortcuts.serveTeam2' },
  { keys: SHORTCUT_BINDINGS.timeoutTeam1, labelKey: 'shortcuts.timeoutTeam1' },
  { keys: SHORTCUT_BINDINGS.timeoutTeam2, labelKey: 'shortcuts.timeoutTeam2' },
  { keys: SHORTCUT_BINDINGS.startMatch, labelKey: 'shortcuts.startMatch' },
  { keys: SHORTCUT_BINDINGS.toggleVisibility, labelKey: 'shortcuts.toggleVisibility' },
  { keys: SHORTCUT_BINDINGS.toggleSimple, labelKey: 'shortcuts.toggleSimple' },
  { keys: SHORTCUT_BINDINGS.openHelp, labelKey: 'shortcuts.openHelp' },
];

function renderKey(key: string): string {
  if (key === ' ') return '␣';
  return key.toUpperCase();
}

export default function ShortcutsHelp({ open, onClose }: ShortcutsHelpProps) {
  const { t } = useI18n();
  return (
    <Dialog open={open} onClose={onClose} ariaLabel={t('shortcuts.title')}>
      <div className="shortcuts-help">
        <h2 className="shortcuts-title">{t('shortcuts.title')}</h2>
        <p className="shortcuts-subtitle">{t('shortcuts.subtitle')}</p>
        <table className="shortcuts-table">
          <tbody>
            {ROWS.map((row) => (
              <tr key={row.labelKey}>
                <td className="shortcuts-keys">
                  {row.keys.map((k, i) => (
                    <span key={k}>
                      <kbd className="shortcut-kbd">{renderKey(k)}</kbd>
                      {i < row.keys.length - 1 && <span className="shortcut-sep"> / </span>}
                    </span>
                  ))}
                </td>
                <td className="shortcuts-label">{t(row.labelKey)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="shortcuts-actions">
          <button type="button" className="dialog-btn" onClick={onClose}>
            {t('dialog.ok')}
          </button>
        </div>
      </div>
    </Dialog>
  );
}
