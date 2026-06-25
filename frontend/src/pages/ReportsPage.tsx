import { useCallback, useEffect, useMemo, useState } from 'react';
import * as api from '../api/client';
import EmptyState from '../components/EmptyState';
import MatchCalendar, { dayKey } from '../components/MatchCalendar';
import { useToast } from '../components/Toast';
import { useConfirm } from '../components/ConfirmProvider';
import { useI18n } from '../i18n';

type SortKey = 'ended' | 'duration';
type SortDir = 'asc' | 'desc';

const PAGE_SIZE = 20;
const MATCH_MODES = ['indoor', 'beach', 'table_tennis'] as const;

export default function ReportsPage() {
  const { t } = useI18n();
  const { toast } = useToast();
  const confirm = useConfirm();
  const [overlays, setOverlays] = useState<api.OverlayPayload[]>([]);
  const [oid, setOid] = useState('');
  const [matches, setMatches] = useState<api.MatchSummary[]>([]);
  const [day, setDay] = useState<string | null>(null);
  const [modeFilter, setModeFilter] = useState<string>('');
  const [sel, setSel] = useState<Set<string>>(new Set());
  const [sortKey, setSortKey] = useState<SortKey>('ended');
  const [sortDir, setSortDir] = useState<SortDir>('desc');
  const [page, setPage] = useState(0);
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
    // Switching overlays starts from "all days" / "all types" — the prior
    // filters rarely map onto another overlay's matches. Selection resets too.
    setDay(null);
    setModeFilter('');
    setSel(new Set());
    void load(oid);
  }, [oid, load]);

  // Match-type filter first (feeds the calendar so it only dots days with
  // matches of the chosen type), then the day filter on top.
  const modeFiltered = useMemo(
    () => (modeFilter ? matches.filter((m) => (m.mode ?? '') === modeFilter) : matches),
    [matches, modeFilter],
  );
  const filtered = useMemo(
    () => (day ? modeFiltered.filter((m) => m.ended_at != null && dayKey(m.ended_at) === day) : modeFiltered),
    [modeFiltered, day],
  );

  const shown = useMemo(() => {
    const sign = sortDir === 'asc' ? 1 : -1;
    const val = (m: api.MatchSummary) => (sortKey === 'ended' ? m.ended_at : m.duration_s) ?? 0;
    return [...filtered].sort((a, b) => sign * (val(a) - val(b)));
  }, [filtered, sortKey, sortDir]);

  // Reset to the first page whenever the visible set changes (filter, sort,
  // overlay) so the operator never lands on a now-empty page.
  useEffect(() => { setPage(0); }, [oid, day, modeFilter, sortKey, sortDir]);

  const pageCount = Math.max(1, Math.ceil(shown.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount - 1);
  const paged = shown.slice(safePage * PAGE_SIZE, (safePage + 1) * PAGE_SIZE);

  function toggleSort(key: SortKey) {
    if (key === sortKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      // Dates default newest-first; durations default longest-first.
      setSortDir('desc');
    }
  }

  function sortArrow(key: SortKey) {
    if (key !== sortKey) return '';
    return sortDir === 'asc' ? ' ▲' : ' ▼';
  }

  function toggleOne(id: string) {
    setSel((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const shownIds = shown.map((m) => m.match_id);
  const someSelected = shownIds.some((id) => sel.has(id));

  // The header checkbox selects/clears just the rows on the *current page*,
  // adding to (or removing from) any selection made on other pages — so a
  // multi-page delete still works by paging and selecting each page in turn.
  const pageIds = paged.map((m) => m.match_id);
  const allPageSelected = pageIds.length > 0 && pageIds.every((id) => sel.has(id));
  const somePageSelected = pageIds.some((id) => sel.has(id));

  function toggleAllPage() {
    setSel((prev) => {
      const next = new Set(prev);
      if (allPageSelected) pageIds.forEach((id) => next.delete(id));
      else pageIds.forEach((id) => next.add(id));
      return next;
    });
  }

  async function deleteIds(ids: string[]) {
    // The backend exposes a single-match delete; fan out and tolerate
    // partial failures so one stale row can't block the rest.
    const results = await Promise.allSettled(ids.map((id) => api.deleteMatch(id)));
    const ok = results.filter((r) => r.status === 'fulfilled').length;
    const failed = results.length - ok;
    await load(oid);
    setSel(new Set());
    if (ok > 0) toast(t('acc.reports.toastDeleted', { n: ok }));
    if (failed > 0) toast(t('acc.reports.errorDelete'), 'error');
  }

  async function onDeleteOne(m: api.MatchSummary) {
    const ok = await confirm({
      title: t('acc.reports.confirmDeleteTitle'),
      message: t('acc.reports.confirmDeleteMsg'),
      confirmLabel: t('acc.common.delete'),
      danger: true,
    });
    if (!ok) return;
    await deleteIds([m.match_id]);
  }

  async function onDeleteSelected() {
    const ids = shownIds.filter((id) => sel.has(id));
    if (ids.length === 0) return;
    const ok = await confirm({
      title: t('acc.reports.confirmDeleteSelectedTitle'),
      message: t('acc.reports.confirmDeleteSelectedMsg', { n: ids.length }),
      confirmLabel: t('acc.common.delete'),
      danger: true,
    });
    if (!ok) return;
    await deleteIds(ids);
  }

  return (
    <div>
      <h2>{t('acc.reports.title')}</h2>
      <p className="acc-muted">{t('acc.reports.intro')}</p>
      {error && <div className="acc-error">{error}</div>}

      {overlaysLoaded && !error && overlays.length === 0 ? (
        <EmptyState action={{ to: '/overlays', label: t('acc.cta.createScoreboard') }}>
          {t('acc.reports.emptyNoOverlays')}
        </EmptyState>
      ) : (
        <>
          <label className="acc-field" style={{ maxWidth: 320, marginTop: 12 }}>
            <span>{t('acc.reports.scoreboard')}</span>
            <select className="acc-input" value={oid} onChange={(e) => setOid(e.target.value)}>
              {overlays.map((o) => (
                <option key={o.oid} value={o.oid}>
                  {o.description ? `${o.oid} — ${o.description}` : o.oid}
                </option>
              ))}
            </select>
          </label>

          {loading ? (
            <p className="acc-muted">{t('acc.common.loading')}</p>
          ) : matches.length === 0 ? (
            <EmptyState>{t('acc.reports.emptyNoMatches')}</EmptyState>
          ) : (
            <>
              <div className="acc-row acc-reports-filters">
                <label className="acc-filter-inline">
                  <span>{t('acc.reports.matchType')}</span>
                  <select
                    className="acc-input acc-filter-select"
                    value={modeFilter}
                    onChange={(e) => setModeFilter(e.target.value)}
                    data-testid="reports-mode-filter"
                  >
                    <option value="">{t('acc.reports.allTypes')}</option>
                    {MATCH_MODES.map((m) => (
                      <option key={m} value={m}>{t(`rules.mode.${m}`)}</option>
                    ))}
                  </select>
                </label>
                <MatchCalendar
                  key={oid + modeFilter}
                  matchTimes={modeFiltered.map((m) => m.ended_at).filter((x): x is number => x != null)}
                  selected={day}
                  onSelect={setDay}
                />
                <span className="acc-muted">{t('acc.reports.showing', { shown: shown.length, total: matches.length })}</span>
                {someSelected && (
                  <button type="button" className="acc-btn danger" onClick={onDeleteSelected}>
                    {t('acc.reports.deleteSelected', { n: shownIds.filter((id) => sel.has(id)).length })}
                  </button>
                )}
              </div>
              {shown.length === 0 ? (
                <EmptyState>
                  {day ? t('acc.reports.emptyNoMatchesDay') : t('acc.reports.emptyNoMatchesFilter')}
                </EmptyState>
              ) : (
                <table className="acc-table">
                  <thead><tr>
                    <th scope="col" style={{ width: 32 }}>
                      <input
                        type="checkbox"
                        aria-label={allPageSelected ? t('acc.reports.deselectPage') : t('acc.reports.selectPage')}
                        title={allPageSelected ? t('acc.reports.deselectPage') : t('acc.reports.selectPage')}
                        checked={allPageSelected}
                        ref={(el) => { if (el) el.indeterminate = somePageSelected && !allPageSelected; }}
                        onChange={toggleAllPage}
                      />
                    </th>
                    <th scope="col">
                      <button type="button" className="acc-sort-th" onClick={() => toggleSort('ended')}>
                        {t('acc.reports.colEnded')}{sortArrow('ended')}
                      </button>
                    </th>
                    <th scope="col">{t('acc.reports.colMatch')}</th>
                    <th scope="col">
                      <button type="button" className="acc-sort-th" onClick={() => toggleSort('duration')}>
                        {t('acc.reports.colDuration')}{sortArrow('duration')}
                      </button>
                    </th>
                    <th scope="col"></th>
                  </tr></thead>
                  <tbody>
                    {paged.map((m) => (
                      <tr key={m.match_id}>
                        <td>
                          <input
                            type="checkbox"
                            aria-label={t('acc.reports.selectMatch')}
                            checked={sel.has(m.match_id)}
                            onChange={() => toggleOne(m.match_id)}
                          />
                        </td>
                        <td data-label={t('acc.reports.colEnded')}>{m.ended_at ? new Date(m.ended_at * 1000).toLocaleString() : '—'}</td>
                        <td data-label={t('acc.reports.colMatch')}><MatchTeams m={m} /></td>
                        <td data-label={t('acc.reports.colDuration')}>{m.duration_s ? t('acc.reports.minutes', { n: Math.round(m.duration_s / 60) }) : '—'}</td>
                        <td>
                          <div className="acc-row" style={{ gap: 6, justifyContent: 'flex-end' }}>
                            <a className="acc-btn ghost" href={`/match/${m.match_id}/report`} target="_blank" rel="noreferrer">
                              {t('acc.reports.openReport')}
                            </a>
                            <button
                              type="button"
                              className="acc-btn danger ghost"
                              aria-label={t('acc.reports.deleteOne')}
                              title={t('acc.reports.deleteOne')}
                              onClick={() => onDeleteOne(m)}
                            >
                              <span className="material-icons">delete</span>
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
              {pageCount > 1 && (
                <div className="acc-row" style={{ alignItems: 'center', gap: 10, marginTop: 4 }}>
                  <button
                    type="button"
                    className="acc-btn ghost"
                    disabled={safePage <= 0}
                    onClick={() => setPage(safePage - 1)}
                  >
                    {t('acc.reports.prevPage')}
                  </button>
                  <span className="acc-muted">
                    {t('acc.reports.pageOf', { page: safePage + 1, pages: pageCount })}
                  </span>
                  <button
                    type="button"
                    className="acc-btn ghost"
                    disabled={safePage >= pageCount - 1}
                    onClick={() => setPage(safePage + 1)}
                  >
                    {t('acc.reports.nextPage')}
                  </button>
                </div>
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
