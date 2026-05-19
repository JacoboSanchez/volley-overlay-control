import { useEffect, useRef } from 'react';
import { useI18n, type Translate } from '../i18n';
import { useAuditLog } from '../hooks/useAuditLog';
import type { AuditRecord, GameState } from '../api/client';
import ActionChip from './ActionChip';
import { classifyChip } from '../utils/chipCatalogue';

export interface RecentAuditDrawerProps {
  oid: string | null;
  open: boolean;
  /** Authoritative state — drives the refetch trigger. */
  confirmedState: GameState | null | undefined;
  /** Maximum records shown in the drawer. */
  limit?: number;
  onClose: () => void;
}

function formatRelative(now: number, ts: number, t: Translate): string {
  const elapsed = Math.max(0, now - ts);
  if (elapsed < 5) return t('history.relative.justNow');
  if (elapsed < 60) {
    return t('history.relative.seconds', { n: Math.floor(elapsed) });
  }
  if (elapsed < 3600) {
    const m = Math.floor(elapsed / 60);
    return t('history.relative.minutes', { n: m });
  }
  const h = Math.floor(elapsed / 3600);
  return t('history.relative.hours', { n: h });
}

function teamLabel(team: unknown): string | number {
  if (team === 1 || team === 2) return team;
  return '?';
}

function safeNumber(value: unknown, fallback: string | number = '?'): string | number {
  if (typeof value === 'number') return value;
  if (typeof value === 'string' && value.trim() !== '') return value;
  return fallback;
}

function actionLabel(record: AuditRecord, t: Translate): string {
  const params = record.params ?? {};
  const team = teamLabel((params as Record<string, unknown>).team);
  const undo = (params as Record<string, unknown>).undo === true;
  const undoSuffix = undo ? t('history.action.undoSuffix') : '';
  // Every branch appends ``undoSuffix`` so the row label stays
  // consistent with the visual strikethrough — without it, an
  // undone change_serve / set_score / reset would render struck-
  // through but read as if it were a fresh action.
  switch (record.action) {
    case 'add_point':
      return t('history.action.point', { team }) + undoSuffix;
    case 'add_set':
      return t('history.action.set', { team }) + undoSuffix;
    case 'add_timeout':
      return t('history.action.timeout', { team }) + undoSuffix;
    case 'change_serve':
      return t('history.action.serve', { team }) + undoSuffix;
    case 'set_score': {
      const setNum = safeNumber((params as Record<string, unknown>).set_number);
      const value = safeNumber((params as Record<string, unknown>).value);
      return t('history.action.edit', { team, set: setNum, value }) + undoSuffix;
    }
    case 'reset':
      return t('history.action.reset') + undoSuffix;
    default:
      return (record.action || t('history.action.unknown')) + undoSuffix;
  }
}

function runningScore(record: AuditRecord): string | null {
  const result = record.result as Record<string, unknown> | undefined;
  if (!result) return null;
  const t1 = (result.team_1 as Record<string, unknown> | undefined)?.score;
  const t2 = (result.team_2 as Record<string, unknown> | undefined)?.score;
  if (typeof t1 === 'number' && typeof t2 === 'number') {
    return `${t1}–${t2}`;
  }
  return null;
}

/**
 * Slide-in drawer that shows the most recent audit entries for the
 * current OID. Intentionally **not** a modal — the operator can
 * keep tapping team panels behind the drawer to react to live
 * play. Dismiss via the close button, ESC, or tapping the
 * transparent backdrop.
 *
 * Reuses ``ActionChip`` so the colour palette matches the post-
 * match HTML report; the kind→glyph catalogue is the shared
 * ``frontend/src/utils/chipCatalogue.ts``.
 */
export default function RecentAuditDrawer({
  oid,
  open,
  confirmedState,
  limit = 20,
  onClose,
}: RecentAuditDrawerProps) {
  const { t } = useI18n();
  const { records, loading, error, refresh } = useAuditLog(oid, open, {
    trigger: confirmedState,
    limit,
  });
  const closeBtnRef = useRef<HTMLButtonElement | null>(null);

  // Computed each render — formatRelative runs once per row and the
  // operator never has more than 20 rows visible. Snapshotting via
  // useMemo would either thrash on every state push or stale the
  // relative labels until the next refetch; neither beats the
  // straight read.
  const now = Date.now() / 1000;

  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onClose();
      }
    };
    document.addEventListener('keydown', onKey);
    setTimeout(() => closeBtnRef.current?.focus(), 30);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="recent-audit-drawer"
      role="region"
      aria-label={t('history.title')}
      data-testid="recent-audit-drawer"
    >
      <button
        type="button"
        className="recent-audit-backdrop"
        onClick={onClose}
        aria-label={t('history.close')}
        tabIndex={-1}
      />
      <div className="recent-audit-card">
        <header className="recent-audit-header">
          <h3 className="recent-audit-title">{t('history.title')}</h3>
          <div className="recent-audit-toolbar">
            <button
              type="button"
              className="recent-audit-btn"
              onClick={refresh}
              title={t('history.refresh')}
              aria-label={t('history.refresh')}
              data-testid="recent-audit-refresh"
            >
              <span className="material-icons" aria-hidden="true">
                refresh
              </span>
            </button>
            <button
              ref={closeBtnRef}
              type="button"
              className="recent-audit-btn recent-audit-close"
              onClick={onClose}
              title={t('history.close')}
              aria-label={t('history.close')}
              data-testid="recent-audit-close"
            >
              <span className="material-icons" aria-hidden="true">
                close
              </span>
            </button>
          </div>
        </header>

        <div className="recent-audit-body">
          {error && (
            <div className="recent-audit-error" role="alert">
              {error}
            </div>
          )}
          {loading && records.length === 0 && (
            <div className="recent-audit-empty">{t('history.loading')}</div>
          )}
          {!loading && !error && records.length === 0 && (
            <div className="recent-audit-empty">{t('history.empty')}</div>
          )}
          {records.length > 0 && (
            <ol className="recent-audit-list" data-testid="recent-audit-list">
              {records.map((record) => {
                const params = record.params ?? {};
                const team = params.team === 1 || params.team === 2 ? params.team : undefined;
                const isUndo = params.undo === true;
                const kind = classifyChip(record.action, team, isUndo);
                const label = actionLabel(record, t);
                const score = runningScore(record);
                const rel = formatRelative(now, record.ts, t);
                return (
                  <li
                    key={`${record.ts}:${record.action}:${team ?? '_'}`}
                    className={`recent-audit-row recent-audit-row-${kind}${isUndo ? ' recent-audit-row-undo' : ''}`}
                  >
                    <ActionChip kind={kind} glyphOnly />
                    <span className="recent-audit-row-label">{label}</span>
                    {score && <span className="recent-audit-row-score">{score}</span>}
                    <span className="recent-audit-row-ts">{rel}</span>
                  </li>
                );
              })}
            </ol>
          )}
        </div>
      </div>
    </div>
  );
}
