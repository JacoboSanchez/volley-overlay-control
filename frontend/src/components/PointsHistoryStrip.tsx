import type { RecentEvent } from '../hooks/useRecentEvents';
import { getReadableOnSurface } from '../utils/contrast';
import { useSurfaceColor } from '../hooks/useSurfaceColor';
import { useI18n, type Translate } from '../i18n';

// Markers are non-text UI shapes — WCAG AA only requires 3:1 here.
const MARKER_MIN_RATIO = 3;

export interface PointsHistoryStripProps {
  events: RecentEvent[];
  team1Color: string;
  team1TextColor: string;
  team1Logo: string | null;
  team1Name: string;
  team2Color: string;
  team2TextColor: string;
  team2Logo: string | null;
  team2Name: string;
  /**
   * Display-side swap: renders team 2's row on top. Each row keeps
   * its own identity bundle (events route by ``ev.team``), only the
   * order flips — mirroring the swapped team panels around it.
   */
  swapped?: boolean;
}

const ICON_VIEWBOX = '0 0 24 24';

// Compact glyph for a tagged point. Language-neutral single letters so
// the chip stays tiny; the full type is spelled out in the aria-label.
const POINT_TYPE_ABBR: Record<string, string> = {
  ace: 'A',
  kill: 'K',
  block: 'B',
  opp_error: 'E',
};

// Translation keys for the full words announced by screen readers, so
// the aria-label never exposes a raw programmatic token such as
// ``opp_error``.
const POINT_TYPE_ARIA_KEYS: Record<string, string> = {
  ace: 'pointType.ace',
  kill: 'pointType.kill',
  block: 'pointType.block',
  opp_error: 'pointType.opp_error',
};

function ClockIcon() {
  return (
    <svg viewBox={ICON_VIEWBOX} className="phs-icon" aria-hidden="true">
      <circle cx="12" cy="12" r="8" fill="none" stroke="currentColor" strokeWidth="2" />
      <path
        d="M12 7.5v5l3 2"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  );
}

function TrophyIcon() {
  return (
    <svg viewBox={ICON_VIEWBOX} className="phs-icon" aria-hidden="true">
      <path
        d="M7 4h10v3a5 5 0 0 1-10 0V4zm-4 1h2v2a3 3 0 0 0 3 3v-2H4V5zm16 0h2v2a3 3 0 0 1-3 3v-2h2V5zM10 13h4v3h2v3H8v-3h2v-3z"
        fill="currentColor"
      />
    </svg>
  );
}

function StarIcon() {
  return (
    <svg viewBox={ICON_VIEWBOX} className="phs-icon" aria-hidden="true">
      <path
        d="M12 2.5l2.6 6.8 7.4.5-5.6 4.8 1.8 7.2L12 17.9 5.8 21.8l1.8-7.2L2 9.8l7.4-.5L12 2.5z"
        fill="currentColor"
      />
    </svg>
  );
}

function PencilIcon() {
  return (
    <svg viewBox={ICON_VIEWBOX} className="phs-icon phs-icon-sm" aria-hidden="true">
      <path
        d="M14.06 4.94l3 3L8.5 16.5l-4 1 1-4 8.56-8.56zm1.41-1.41a2 2 0 0 1 2.83 0l.59.59a2 2 0 0 1 0 2.83L17.47 8.4l-3-3 1.0-1.0z"
        fill="currentColor"
      />
    </svg>
  );
}

function chipContent(ev: RecentEvent) {
  switch (ev.kind) {
    case 'point_add':
      return (
        <span className="phs-chip-text">
          {ev.pointType ? (POINT_TYPE_ABBR[ev.pointType] ?? '+1') : '+1'}
        </span>
      );
    case 'set_won':
      return <StarIcon />;
    case 'match_won':
      return <TrophyIcon />;
    case 'timeout':
      return <ClockIcon />;
    case 'manual': {
      const v = ev.value ?? 0;
      return (
        <span className="phs-chip-manual">
          <PencilIcon />
          <span className="phs-chip-text-sm">{v}</span>
        </span>
      );
    }
  }
}

function chipAriaLabel(ev: RecentEvent, teamName: string, t: Translate): string {
  switch (ev.kind) {
    case 'point_add': {
      if (!ev.pointType) return t('history.chip.point', { team: teamName });
      const typeKey = POINT_TYPE_ARIA_KEYS[ev.pointType];
      const type = typeKey ? t(typeKey) : ev.pointType;
      return t('history.chip.typedPoint', { team: teamName, type });
    }
    case 'set_won':
      return t('history.chip.setWon', { team: teamName });
    case 'match_won':
      return t('history.chip.matchWon', { team: teamName });
    case 'timeout':
      return t('history.chip.timeout', { team: teamName });
    case 'manual':
      return t('history.chip.manual', { team: teamName, value: ev.value ?? 0 });
  }
}

interface RowProps {
  team: 1 | 2;
  events: RecentEvent[];
  color: string;
  textColor: string;
  logo: string | null;
  name: string;
  t: Translate;
}

function Row({
  team,
  events,
  color,
  textColor,
  logo,
  name,
  t,
  surface,
}: RowProps & { surface: string }) {
  const markerColor = getReadableOnSurface(color, surface, MARKER_MIN_RATIO);
  return (
    <div className="phs-row" data-testid={`phs-row-${team}`}>
      <span
        className="phs-marker"
        style={{ backgroundColor: markerColor }}
        role="img"
        aria-label={name}
      >
        {logo && <img src={logo} alt="" className="phs-marker-logo" />}
      </span>
      {events.map((ev, i) => {
        const isOurs = ev.team === team;
        return (
          <span
            key={`${ev.ts}-${ev.team}-${ev.kind}-${ev.value ?? ''}`}
            className="phs-cell"
            data-testid={`phs-cell-${team}-${i}`}
          >
            {isOurs && (
              <span
                className={`phs-chip phs-chip-${ev.kind}`}
                style={{ backgroundColor: color, color: textColor }}
                data-testid={`phs-chip-${team}-${i}`}
                aria-label={chipAriaLabel(ev, name, t)}
              >
                {chipContent(ev)}
              </span>
            )}
          </span>
        );
      })}
    </div>
  );
}

export default function PointsHistoryStrip({
  events,
  team1Color,
  team1TextColor,
  team1Logo,
  team1Name,
  team2Color,
  team2TextColor,
  team2Logo,
  team2Name,
  swapped = false,
}: PointsHistoryStripProps) {
  const { t } = useI18n();
  const surface = useSurfaceColor();
  if (events.length === 0) return null;
  const rows = [
    <Row
      key={1}
      team={1}
      events={events}
      color={team1Color}
      textColor={team1TextColor}
      logo={team1Logo}
      name={team1Name}
      t={t}
      surface={surface}
    />,
    <Row
      key={2}
      team={2}
      events={events}
      color={team2Color}
      textColor={team2TextColor}
      logo={team2Logo}
      name={team2Name}
      t={t}
      surface={surface}
    />,
  ];
  if (swapped) rows.reverse();
  return (
    <div
      className="points-history-strip"
      data-testid="points-history-strip"
      aria-label={t('history.recentActions')}
    >
      {rows}
    </div>
  );
}
