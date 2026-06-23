import { useCallback, useEffect, useState } from 'react';
import * as api from '../api/client';
import EmptyState from '../components/EmptyState';
import { useI18n } from '../i18n';

export default function ReportsPage() {
  const { t } = useI18n();
  const [overlays, setOverlays] = useState<api.OverlayPayload[]>([]);
  const [oid, setOid] = useState('');
  const [matches, setMatches] = useState<api.MatchSummary[]>([]);
  const [loading, setLoading] = useState(false);
  const [overlaysLoaded, setOverlaysLoaded] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    void (async () => {
      try {
        const ovs = await api.getOverlays();
        setOverlays(ovs);
        if (ovs[0]) {
          // Honour a ``?oid=`` deep link (e.g. the board's "All reports"
          // share link) when it matches one of the user's overlays;
          // otherwise default to the first.
          const wanted = new URLSearchParams(window.location.search).get('oid');
          const match = wanted && ovs.find((o) => o.oid === wanted);
          setOid(match ? match.oid : ovs[0].oid);
        }
      } catch {
        setError(t('acc.reports.errorOverlays'));
      } finally {
        setOverlaysLoaded(true);
      }
    })();
  }, [t]);

  const load = useCallback(async (id: string) => {
    if (!id) {
      setMatches([]);
      return;
    }
    setLoading(true);
    setError('');
    try {
      const res = await api.listReports(id);
      setMatches(res.matches);
    } catch {
      setError(t('acc.reports.errorReports'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load(oid);
  }, [oid, load]);

  return (
    <div>
      <h2>{t('acc.reports.title')}</h2>
      <p className="acc-muted">{t('acc.reports.intro')}</p>
      {error && <div className="acc-error">{error}</div>}

      {overlaysLoaded && overlays.length === 0 ? (
        <EmptyState action={{ to: '/overlays', label: t('acc.cta.createScoreboard') }}>
          {t('acc.reports.emptyNoOverlays')}
        </EmptyState>
      ) : (
        <>
          <label className="acc-field" style={{ maxWidth: 320, marginTop: 12 }}>
            <span>{t('acc.reports.scoreboard')}</span>
            <select className="acc-input" value={oid} onChange={(e) => setOid(e.target.value)}>
              {overlays.map((o) => (
                <option key={o.oid} value={o.oid}>{o.display_name || o.oid}</option>
              ))}
            </select>
          </label>

          {loading ? (
            <p className="acc-muted">{t('acc.common.loading')}</p>
          ) : matches.length === 0 ? (
            <EmptyState>{t('acc.reports.emptyNoMatches')}</EmptyState>
          ) : (
            <table className="acc-table">
              <thead><tr>
                <th scope="col">{t('acc.reports.colEnded')}</th>
                <th scope="col">{t('acc.reports.colWinner')}</th>
                <th scope="col">{t('acc.reports.colDuration')}</th>
                <th scope="col"></th>
              </tr></thead>
              <tbody>
                {matches.map((m) => (
                  <tr key={m.match_id}>
                    <td data-label={t('acc.reports.colEnded')}>{m.ended_at ? new Date(m.ended_at * 1000).toLocaleString() : '—'}</td>
                    <td data-label={t('acc.reports.colWinner')}>{m.winning_team ? t('acc.reports.team', { n: m.winning_team }) : '—'}</td>
                    <td data-label={t('acc.reports.colDuration')}>{m.duration_s ? t('acc.reports.minutes', { n: Math.round(m.duration_s / 60) }) : '—'}</td>
                    <td>
                      <a className="acc-btn ghost" href={`/match/${m.match_id}/report`} target="_blank" rel="noreferrer">
                        {t('acc.reports.openReport')}
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
    </div>
  );
}
