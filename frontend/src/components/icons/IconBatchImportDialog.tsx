import { useEffect, useMemo, useState } from 'react';
import * as api from '../../api/client';
import Dialog from '../Dialog';
import { useI18n } from '../../i18n';

/** Convert selected teams' external logo URLs into hosted library icons.
 *
 *  Lists the eligible teams (external http(s) logo, not yet hosted),
 *  lets the user tick which to convert, fires ONE server call, and
 *  renders the per-team outcome the server reports. The server is the
 *  authority on eligibility and scope — this filter is just UX. */
export default function IconBatchImportDialog({
  open,
  onClose,
  teams,
  importFn,
  onDone,
}: {
  open: boolean;
  onClose: () => void;
  teams: api.TeamOut[];
  importFn: (teamIds: number[]) => Promise<{ results: api.IconImportResult[] }>;
  onDone: () => void;
}) {
  const { t } = useI18n();
  const eligible = useMemo(
    () => teams.filter((team) => /^https?:\/\//i.test(team.icon ?? '')),
    [teams],
  );
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [results, setResults] = useState<api.IconImportResult[] | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    // Preselect everything eligible — the common case is "convert them all".
    setSelected(new Set(eligible.map((team) => team.id)));
    setResults(null);
    setError('');
  }, [open, eligible]);

  function toggle(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function run() {
    setError('');
    setBusy(true);
    try {
      const res = await importFn([...selected]);
      setResults(res.results);
      onDone();
    } catch (e) {
      setError(e instanceof api.ApiError ? e.detail : t('acc.icons.errorImport'));
    } finally {
      setBusy(false);
    }
  }

  const statusLabel: Record<api.IconImportResult['status'], string> = {
    ok: t('acc.icons.statusOk'),
    skipped: t('acc.icons.statusSkipped'),
    error: t('acc.icons.statusError'),
  };

  return (
    <Dialog open={open} onClose={onClose} ariaLabel={t('acc.icons.batchTitle')}>
      <div className="acc-icon-batch">
        <h3 style={{ marginTop: 0 }}>{t('acc.icons.batchTitle')}</h3>
        <p className="acc-muted">{t('acc.icons.batchHint')}</p>
        {error && <div className="acc-error">{error}</div>}
        {results === null ? (
          <>
            {eligible.length === 0 ? (
              <p className="acc-muted">{t('acc.icons.batchEmpty')}</p>
            ) : (
              <ul className="acc-icon-batch-list">
                {eligible.map((team) => (
                  <li key={team.id}>
                    <label>
                      <input
                        type="checkbox"
                        checked={selected.has(team.id)}
                        onChange={() => toggle(team.id)}
                      />
                      <span className="acc-icon-batch-name">{team.name}</span>
                      <span className="acc-muted acc-icon-batch-url">{team.icon}</span>
                    </label>
                  </li>
                ))}
              </ul>
            )}
            <div className="acc-btn-row" style={{ marginTop: 12 }}>
              <button
                className="acc-btn"
                onClick={run}
                disabled={busy || selected.size === 0}
              >
                {busy
                  ? t('acc.icons.batchRunning')
                  : t('acc.icons.batchRun', { n: selected.size })}
              </button>
              <button className="acc-btn secondary" onClick={onClose} disabled={busy}>
                {t('acc.common.cancel')}
              </button>
            </div>
          </>
        ) : (
          <>
            <ul className="acc-icon-batch-list acc-icon-batch-results">
              {results.map((result) => (
                <li key={result.team_id} data-status={result.status}>
                  <span className="acc-icon-batch-name">{result.team_name}</span>
                  <span className={result.status === 'error' ? 'acc-error-text' : 'acc-muted'}>
                    {statusLabel[result.status]}
                    {result.error ? ` — ${result.error}` : ''}
                  </span>
                </li>
              ))}
            </ul>
            <div className="acc-btn-row" style={{ marginTop: 12 }}>
              <button className="acc-btn" onClick={onClose}>
                {t('acc.common.close')}
              </button>
            </div>
          </>
        )}
      </div>
    </Dialog>
  );
}
