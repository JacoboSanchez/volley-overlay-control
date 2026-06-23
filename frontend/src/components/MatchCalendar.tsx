import { useEffect, useMemo, useRef, useState } from 'react';
import { useI18n } from '../i18n';

/** Local ``YYYY-MM-DD`` key for a Date — calendar cells are local days. */
function ymd(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

/** Local day key for a match's ``ended_at`` (unix seconds). */
export function dayKey(ts: number): string {
  return ymd(new Date(ts * 1000));
}

export interface MatchCalendarProps {
  /** ``ended_at`` (unix seconds) for every match currently listed. */
  matchTimes: number[];
  /** Selected day as ``YYYY-MM-DD``, or null for "all days". */
  selected: string | null;
  onSelect: (day: string | null) => void;
}

/**
 * Month calendar that marks the days with archived matches and filters the
 * reports list to a single day on click. Self-contained (no date library, no
 * browser-native picker) so it looks the same everywhere and can highlight
 * which days actually have matches.
 */
export default function MatchCalendar({ matchTimes, selected, onSelect }: MatchCalendarProps) {
  const { t, lang } = useI18n();
  const [open, setOpen] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);

  const daysWithMatches = useMemo(() => {
    const s = new Set<string>();
    for (const ts of matchTimes) if (ts != null) s.add(dayKey(ts));
    return s;
  }, [matchTimes]);

  // Month on screen; defaults to the most recent match (list is newest-first).
  const [view, setView] = useState(() => {
    const recent = matchTimes.filter((x) => x != null);
    const base = recent.length ? new Date(Math.max(...recent) * 1000) : new Date();
    return { year: base.getFullYear(), month: base.getMonth() };
  });

  useEffect(() => {
    if (!open) return;
    function onDown(e: PointerEvent) {
      if (wrap.current && !wrap.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener('pointerdown', onDown);
    return () => document.removeEventListener('pointerdown', onDown);
  }, [open]);

  const monthLabel = new Date(view.year, view.month, 1).toLocaleDateString(lang, {
    month: 'long',
    year: 'numeric',
  });

  // Monday-first weekday initials, localized. 2024-01-01 was a Monday.
  const weekdays = useMemo(
    () =>
      Array.from({ length: 7 }, (_, i) =>
        new Date(2024, 0, 1 + i).toLocaleDateString(lang, { weekday: 'short' }),
      ),
    [lang],
  );

  const cells = useMemo(() => {
    const offset = (new Date(view.year, view.month, 1).getDay() + 6) % 7; // Mon-first
    const days = new Date(view.year, view.month + 1, 0).getDate();
    return [
      ...Array.from({ length: offset }, () => null),
      ...Array.from({ length: days }, (_, i) => i + 1),
    ];
  }, [view]);

  const shift = (delta: number) =>
    setView((v) => {
      const d = new Date(v.year, v.month + delta, 1);
      return { year: d.getFullYear(), month: d.getMonth() };
    });

  const triggerLabel = selected
    ? new Date(`${selected}T00:00:00`).toLocaleDateString(lang, {
        day: 'numeric',
        month: 'short',
        year: 'numeric',
      })
    : t('acc.reports.filterByDay');

  return (
    <div className="acc-cal" ref={wrap}>
      <button
        type="button"
        className={`acc-btn ghost acc-cal-trigger${selected ? ' is-active' : ''}`}
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        <span className="material-icons" aria-hidden="true">calendar_month</span>
        <span>{triggerLabel}</span>
      </button>
      {selected && (
        <button type="button" className="acc-btn ghost acc-cal-clear" onClick={() => onSelect(null)}>
          {t('acc.reports.allDays')}
        </button>
      )}

      {open && (
        <div className="acc-cal-pop" role="dialog" aria-label={t('acc.reports.filterByDay')}>
          <div className="acc-cal-head">
            <button
              type="button"
              className="acc-cal-nav"
              aria-label={t('acc.reports.prevMonth')}
              onClick={() => shift(-1)}
            >
              <span className="material-icons">chevron_left</span>
            </button>
            <span className="acc-cal-month">{monthLabel}</span>
            <button
              type="button"
              className="acc-cal-nav"
              aria-label={t('acc.reports.nextMonth')}
              onClick={() => shift(1)}
            >
              <span className="material-icons">chevron_right</span>
            </button>
          </div>
          <div className="acc-cal-grid acc-cal-weekdays">
            {weekdays.map((w, i) => (
              <span key={i} className="acc-cal-weekday">{w}</span>
            ))}
          </div>
          <div className="acc-cal-grid">
            {cells.map((d, i) => {
              if (d == null) return <span key={`b${i}`} className="acc-cal-cell acc-cal-blank" />;
              const key = `${view.year}-${String(view.month + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
              const has = daysWithMatches.has(key);
              const sel = selected === key;
              return (
                <button
                  key={key}
                  type="button"
                  className={`acc-cal-cell${has ? ' has-match' : ''}${sel ? ' is-selected' : ''}`}
                  disabled={!has}
                  aria-pressed={sel}
                  onClick={() => {
                    onSelect(sel ? null : key);
                    setOpen(false);
                  }}
                >
                  {d}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
