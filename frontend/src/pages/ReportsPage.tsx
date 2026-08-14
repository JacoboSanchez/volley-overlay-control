import { useCallback, useEffect, useRef, useState } from 'react';
import { getOverlays } from '../api/overlays';
import type { OverlayPayload } from '../api/overlays';
import { deleteMatches, listReportDays, listReports } from '../api/reports';
import type { MatchSummary } from '../api/reports';
import EmptyState from '../components/EmptyState';
import MatchCalendar from '../components/MatchCalendar';
import { useToast } from '../components/Toast';
import { useConfirm } from '../components/ConfirmProvider';
import { useSelection } from '../hooks/useSelection';
import { useI18n } from '../i18n';

type SortKey = 'ended' | 'duration';
type SortDir = 'asc' | 'desc';

const PAGE_SIZE = 20;
const MATCH_MODES = ['indoor', 'beach', 'table_tennis'] as const;

export default function ReportsPage() {
  const { t } = useI18n();
  const { toast } = useToast();
  const confirm = useConfirm();
  const [overlays, setOverlays] = useState<OverlayPayload[]>([]);
  const [oid, setOid] = useState('');
  const [matches, setMatches] = useState<MatchSummary[]>([]);
  const [matchDays, setMatchDays] = useState<string[]>([]);
  const [total, setTotal] = useState(0);
  const [day, setDay] = useState<string | null>(null);
  const [modeFilter, setModeFilter] = useState<string>('');
  const sel = useSelection<string>();
  // Stable across selection changes, unlike `sel` itself — safe as an effect dep.
  const { clear: clearSelection } = sel;
  const [sortKey, setSortKey] = useState<SortKey>('ended');
  const [sortDir, setSortDir] = useState<SortDir>('desc');
  const [page, setPage] = useState(0);
  // In-flight guard: a fast double-tap must not fan out the delete twice.
  const [deleting, setDeleting] = useState(false);
  const [loading, setLoading] = useState(false);
  const [overlaysLoaded, setOverlaysLoaded] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    void (async () => {
      try {
        const ovs = await getOverlays();
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

  // Overlay/mode/day/sort/page are server-side filters now, so changing one
  // starts a fresh request while the previous may still be in flight. Only
  // the newest may write state: a slower earlier response landing last would
  // otherwise repopulate the table with rows for controls the operator has
  // already moved on from.
  const loadSeq = useRef(0);

  const load = useCallback(async () => {
    const seq = ++loadSeq.current;
    if (!oid) {
      setMatches([]);
      setTotal(0);
      return;
    }
    setLoading(true);
    setError('');
    try {
      const res = await listReports({
        oid,
        ...(modeFilter ? { mode: modeFilter } : {}),
        day,
        sort: sortKey,
        direction: sortDir,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      });
      if (seq !== loadSeq.current) return;
      setMatches(res.matches);
      setTotal(res.count);
    } catch {
      if (seq !== loadSeq.current) return;
      setError(t('acc.reports.errorReports'));
    } finally {
      // The newest request owns the spinner; a superseded one must not
      // clear it while its replacement is still running.
      if (seq === loadSeq.current) setLoading(false);
    }
  }, [day, modeFilter, oid, page, sortDir, sortKey, t]);

  useEffect(() => {
    void load();
  }, [load]);

  // Calendar dots are a separate scalar-only query. Re-read them when the
  // overlay or mode changes, never on page/sort/day changes — plus after a
  // deletion, which can empty a day the calendar would otherwise keep
  // offering until the operator switched overlay or mode.
  const daysSeq = useRef(0);
  const loadDays = useCallback(() => {
    const seq = ++daysSeq.current;
    if (!oid) {
      setMatchDays([]);
      return Promise.resolve();
    }
    return listReportDays({ oid, ...(modeFilter ? { mode: modeFilter } : {}) })
      .then((res) => {
        // Same ordering guard as ``load``.
        if (seq === daysSeq.current) setMatchDays(res.days);
      })
      .catch(() => {
        if (seq === daysSeq.current) setMatchDays([]);
      });
  }, [modeFilter, oid]);

  useEffect(() => {
    void loadDays();
  }, [loadDays]);

  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const safePage = Math.min(page, pageCount - 1);

  useEffect(() => {
    if (page !== safePage) setPage(safePage);
  }, [page, safePage]);

  function toggleSort(key: SortKey) {
    setPage(0);
    clearSelection();
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

  const someSelected = sel.size > 0;
  const filtersActive = Boolean(modeFilter || day);

  // The header checkbox selects/clears just the rows on the *current page*,
  // adding to (or removing from) any selection made on other pages — so a
  // multi-page delete still works by paging and selecting each page in turn.
  const pageIds = matches.map((m) => m.match_id);
  const allPageSelected = sel.allSelected(pageIds);
  const somePageSelected = sel.someSelected(pageIds);

  async function deleteIds(ids: string[]) {
    setDeleting(true);
    try {
      const result = await deleteMatches(ids);
      sel.clear();
      if (page !== 0) setPage(0);
      else await load();
      await loadDays();
      if (result.deleted > 0) toast(t('acc.reports.toastDeleted', { n: result.deleted }));
      if (result.deleted < result.requested) toast(t('acc.reports.errorDelete'), 'error');
    } catch {
      toast(t('acc.reports.errorDelete'), 'error');
      // A large selection is sent in chunks, so a failure can still leave
      // earlier chunks deleted — never leave the list showing rows that
      // are already gone.
      await load();
      await loadDays();
    } finally {
      setDeleting(false);
    }
  }

  async function onDeleteOne(m: MatchSummary) {
    if (deleting) return;
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
    if (deleting) return;
    const ids = sel.ids;
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
            <select
              className="acc-input"
              value={oid}
              onChange={(e) => {
                setOid(e.target.value);
                setDay(null);
                setModeFilter('');
                setPage(0);
                clearSelection();
              }}
            >
              {overlays.map((o) => (
                <option key={o.oid} value={o.oid}>
                  {o.description ? `${o.oid} — ${o.description}` : o.oid}
                </option>
              ))}
            </select>
          </label>

          {loading ? (
            <p className="acc-muted">{t('acc.common.loading')}</p>
          ) : total === 0 && !filtersActive ? (
            <EmptyState>{t('acc.reports.emptyNoMatches')}</EmptyState>
          ) : (
            <>
              <div className="acc-row acc-reports-filters">
                <label className="acc-filter-inline">
                  <span>{t('acc.reports.matchType')}</span>
                  <select
                    className="acc-input acc-filter-select"
                    value={modeFilter}
                    onChange={(e) => {
                      setModeFilter(e.target.value);
                      setDay(null);
                      setPage(0);
                      clearSelection();
                    }}
                    data-testid="reports-mode-filter"
                  >
                    <option value="">{t('acc.reports.allTypes')}</option>
                    {MATCH_MODES.map((m) => (
                      <option key={m} value={m}>
                        {t(`rules.mode.${m}`)}
                      </option>
                    ))}
                  </select>
                </label>
                <MatchCalendar
                  key={oid + modeFilter}
                  matchDays={matchDays}
                  selected={day}
                  onSelect={(value) => {
                    setDay(value);
                    setPage(0);
                    clearSelection();
                  }}
                />
                <span className="acc-muted">
                  {t('acc.reports.showing', { shown: matches.length, total })}
                </span>
                {someSelected && (
                  <button
                    type="button"
                    className="acc-btn danger"
                    disabled={deleting}
                    onClick={onDeleteSelected}
                  >
                    {t('acc.reports.deleteSelected', {
                      n: sel.size,
                    })}
                  </button>
                )}
              </div>
              {matches.length === 0 ? (
                <EmptyState>
                  {day ? t('acc.reports.emptyNoMatchesDay') : t('acc.reports.emptyNoMatchesFilter')}
                </EmptyState>
              ) : (
                <table className="acc-table">
                  <thead>
                    <tr>
                      <th scope="col" style={{ width: 32 }}>
                        <input
                          type="checkbox"
                          aria-label={
                            allPageSelected
                              ? t('acc.reports.deselectPage')
                              : t('acc.reports.selectPage')
                          }
                          title={
                            allPageSelected
                              ? t('acc.reports.deselectPage')
                              : t('acc.reports.selectPage')
                          }
                          checked={allPageSelected}
                          ref={(el) => {
                            if (el) el.indeterminate = somePageSelected && !allPageSelected;
                          }}
                          onChange={() => sel.toggleAll(pageIds)}
                        />
                      </th>
                      <th scope="col">
                        <button
                          type="button"
                          className="acc-sort-th"
                          onClick={() => toggleSort('ended')}
                        >
                          {t('acc.reports.colEnded')}
                          {sortArrow('ended')}
                        </button>
                      </th>
                      <th scope="col">{t('acc.reports.colMatch')}</th>
                      <th scope="col">
                        <button
                          type="button"
                          className="acc-sort-th"
                          onClick={() => toggleSort('duration')}
                        >
                          {t('acc.reports.colDuration')}
                          {sortArrow('duration')}
                        </button>
                      </th>
                      <th scope="col"></th>
                    </tr>
                  </thead>
                  <tbody>
                    {matches.map((m) => (
                      <tr key={m.match_id}>
                        <td>
                          <input
                            type="checkbox"
                            aria-label={t('acc.reports.selectMatch')}
                            checked={sel.has(m.match_id)}
                            onChange={() => sel.toggle(m.match_id)}
                          />
                        </td>
                        <td data-label={t('acc.reports.colEnded')}>
                          {m.ended_at ? new Date(m.ended_at * 1000).toLocaleString() : '—'}
                        </td>
                        <td data-label={t('acc.reports.colMatch')}>
                          <MatchTeams m={m} />
                        </td>
                        <td data-label={t('acc.reports.colDuration')}>
                          {m.duration_s
                            ? t('acc.reports.minutes', { n: Math.round(m.duration_s / 60) })
                            : '—'}
                        </td>
                        <td>
                          <div className="acc-row" style={{ gap: 6, justifyContent: 'flex-end' }}>
                            <a
                              className="acc-btn ghost"
                              href={`/match/${m.match_id}/report`}
                              target="_blank"
                              rel="noreferrer"
                            >
                              {t('acc.reports.openReport')}
                            </a>
                            <button
                              type="button"
                              className="acc-btn danger ghost"
                              aria-label={t('acc.reports.deleteOne')}
                              title={t('acc.reports.deleteOne')}
                              disabled={deleting}
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
function MatchTeams({ m }: { m: MatchSummary }) {
  const { t } = useI18n();
  const n1 = m.team_1_name || t('acc.reports.team', { n: 1 });
  const n2 = m.team_2_name || t('acc.reports.team', { n: 2 });
  const s1 = m.team_1_sets ?? 0;
  const s2 = m.team_2_sets ?? 0;
  return (
    <span className="acc-match-teams">
      <span className={`acc-match-name${m.winning_team === 1 ? ' is-winner' : ''}`}>{n1}</span>
      <span className="acc-match-score">
        {s1}
        <span className="acc-match-dash">–</span>
        {s2}
      </span>
      <span className={`acc-match-name${m.winning_team === 2 ? ' is-winner' : ''}`}>{n2}</span>
    </span>
  );
}
