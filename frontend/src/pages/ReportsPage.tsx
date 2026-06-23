import { useCallback, useEffect, useState } from 'react';
import * as api from '../api/client';
import EmptyState from '../components/EmptyState';
import MatchCalendar, { dayKey } from '../components/MatchCalendar';
import { useI18n } from '../i18n';

export default function ReportsPage() {
  const { t } = useI18n();
  const [overlays, setOverlays] = useState<api.OverlayPayload[]>([]);
  const [oid, setOid] = useState('');
  const [matches, setMatches] = useState<api.MatchSummary[]>([]);
  const [day, setDay] = useState<string | null>(null);
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
    // Switching overlays starts from "all days" — the prior day rarely maps
    // onto another overlay's match dates.
    setDay(null);
    void load(oid);
  }, [oid, load]);

  const shown = day ? matches.filter((m) => m.ended_at != null && dayKey(m.ended_at) === day) : matches;

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
            <>
              <div className="acc-row" style={{ margin: '12px 0', alignItems: 'center' }}>
                <MatchCalendar
                  key={oid}
                  matchTimes={matches.map((m) => m.ended_at).filter((x): x is number => x != null)}
                  selected={day}
                  onSelect={setDay}
                />
                <span className="acc-muted">{t('acc.reports.showing', { shown: shown.length, total: matches.length })}</span>
              </div>
              {shown.length === 0 ? (
                <EmptyState>{t('acc.reports.emptyNoMatchesDay')}</EmptyState>
              ) : (
                <table className="acc-table">
                  <thead><tr>
                    <th scope="col">{t('acc.reports.colEnded')}</th>
                    <th scope="col">{t('acc.reports.colMatch')}</th>
                    <th scope="col">{t('acc.reports.colDuration')}</th>
                    <th scope="col"></th>
                  </tr></thead>
                  <tbody>
                    {shown.map((m) => (
                      <tr key={m.match_id}>
                        <td data-label={t('acc.reports.colEnded')}>{m.ended_at ? new Date(m.ended_at * 1000).toLocaleString() : '—'}</td>
                        <td data-label={t('acc.reports.colMatch')}><MatchTeams m={m} /></td>
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
        </>
      )}
    </div>
  );
}

/** "Team 1  3–1  Team 2", with the winner's name highlighted. Falls back to
 *  "Team 1" / "Team 2" when a match was archived without custom names. */
function MatchTeams({ m }: { m: api.MatchSummary }) {
  const { t } = useI18n();
  const n1 = m.team_1_name || t('acc.reports.team', { n: 1 });
  const n2 = m.team_2_name || t('acc.reports.team', { n: 2 });
  const s1 = m.team_1_sets ?? 0;
  const s2 = m.team_2_sets ?? 0;
  return (
    <span className="acc-match-teams">
      <span className={`acc-match-name${m.winning_team === 1 ? ' is-winner' : ''}`}>{n1}</span>
      <span className="acc-match-score">{s1}<span className="acc-match-dash">–</span>{s2}</span>
      <span className={`acc-match-name${m.winning_team === 2 ? ' is-winner' : ''}`}>{n2}</span>
    </span>
  );
}
