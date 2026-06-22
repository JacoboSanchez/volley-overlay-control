import { useCallback, useEffect, useState } from 'react';
import * as api from '../api/client';
import EmptyState from '../components/EmptyState';

export default function ReportsPage() {
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
        if (ovs[0]) setOid(ovs[0].oid);
      } catch {
        setError('Could not load your overlays.');
      } finally {
        setOverlaysLoaded(true);
      }
    })();
  }, []);

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
      setError('Could not load match reports.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(oid);
  }, [oid, load]);

  return (
    <div>
      <h2>Match reports</h2>
      <p className="acc-muted">Archived matches for each of your scoreboards.</p>
      {error && <div className="acc-error">{error}</div>}

      {overlaysLoaded && overlays.length === 0 ? (
        <EmptyState action={{ to: '/overlays', label: 'Create a scoreboard →' }}>
          You don’t have any scoreboards yet. Create one to start archiving match reports.
        </EmptyState>
      ) : (
        <>
          <label className="acc-field" style={{ maxWidth: 320, marginTop: 12 }}>
            <span>Scoreboard</span>
            <select className="acc-input" value={oid} onChange={(e) => setOid(e.target.value)}>
              {overlays.map((o) => (
                <option key={o.oid} value={o.oid}>{o.display_name || o.oid}</option>
              ))}
            </select>
          </label>

          {loading ? (
            <p className="acc-muted">Loading…</p>
          ) : matches.length === 0 ? (
            <EmptyState>No archived matches for this scoreboard yet.</EmptyState>
          ) : (
            <table className="acc-table">
              <thead><tr><th>Ended</th><th>Winner</th><th>Duration</th><th></th></tr></thead>
              <tbody>
                {matches.map((m) => (
                  <tr key={m.match_id}>
                    <td>{m.ended_at ? new Date(m.ended_at * 1000).toLocaleString() : '—'}</td>
                    <td>{m.winning_team ? `Team ${m.winning_team}` : '—'}</td>
                    <td>{m.duration_s ? `${Math.round(m.duration_s / 60)} min` : '—'}</td>
                    <td>
                      <a className="acc-btn ghost" href={`/match/${m.match_id}/report`} target="_blank" rel="noreferrer">
                        Open report
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
