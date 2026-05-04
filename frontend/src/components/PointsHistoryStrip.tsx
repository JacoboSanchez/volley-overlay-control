import type { RecentEvent } from '../hooks/useRecentEvents';

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
}

const ICON_VIEWBOX = '0 0 24 24';

function ClockIcon({ struck }: { struck?: boolean }) {
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
      {struck && (
        <line
          x1="4"
          y1="20"
          x2="20"
          y2="4"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
        />
      )}
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
      return <span className="phs-chip-text">+1</span>;
    case 'point_undo':
      return <span className="phs-chip-text">−1</span>;
    case 'set_won':
      return <TrophyIcon />;
    case 'timeout':
      return <ClockIcon />;
    case 'timeout_undo':
      return <ClockIcon struck />;
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

function chipAriaLabel(ev: RecentEvent, teamName: string): string {
  switch (ev.kind) {
    case 'point_add':
      return `${teamName}: +1`;
    case 'point_undo':
      return `${teamName}: undo point`;
    case 'set_won':
      return `${teamName}: set won`;
    case 'timeout':
      return `${teamName}: timeout`;
    case 'timeout_undo':
      return `${teamName}: undo timeout`;
    case 'manual':
      return `${teamName}: manual ${ev.value ?? 0}`;
  }
}

interface RowProps {
  team: 1 | 2;
  events: RecentEvent[];
  color: string;
  textColor: string;
  logo: string | null;
  name: string;
}

function Row({ team, events, color, textColor, logo, name }: RowProps) {
  return (
    <div className="phs-row" data-testid={`phs-row-${team}`}>
      <span
        className="phs-marker"
        style={{ backgroundColor: color }}
        role="img"
        aria-label={name}
      >
        {logo && <img src={logo} alt="" className="phs-marker-logo" />}
      </span>
      {events.map((ev, i) => {
        const isOurs = ev.team === team;
        return (
          <span
            key={`${ev.ts}-${i}`}
            className="phs-cell"
            data-testid={`phs-cell-${team}-${i}`}
          >
            {isOurs && (
              <span
                className={`phs-chip phs-chip-${ev.kind}`}
                style={{ backgroundColor: color, color: textColor }}
                data-testid={`phs-chip-${team}-${i}`}
                aria-label={chipAriaLabel(ev, name)}
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
}: PointsHistoryStripProps) {
  if (events.length === 0) return null;
  return (
    <div
      className="points-history-strip"
      data-testid="points-history-strip"
      aria-label="Recent actions"
    >
      <Row
        team={1}
        events={events}
        color={team1Color}
        textColor={team1TextColor}
        logo={team1Logo}
        name={team1Name}
      />
      <Row
        team={2}
        events={events}
        color={team2Color}
        textColor={team2TextColor}
        logo={team2Logo}
        name={team2Name}
      />
    </div>
  );
}
