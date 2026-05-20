import { useI18n } from '../i18n';

export interface ScoreboardSkeletonProps {
  /**
   * Layout orientation hint. The skeleton mirrors the real
   * scoreboard layout so the upcoming render swap doesn't shift the
   * operator's eye target. Defaults to landscape (the desktop
   * default) — the placeholder reads correctly in either mode.
   */
  isPortrait?: boolean;
}

/**
 * Lightweight placeholder shown after the operator has supplied an
 * OID but before the first authoritative ``GameState`` arrives over
 * the WebSocket. Mirrors the scoreboard's three-pane layout (team A
 * / centre / team B) so the actual score doesn't pop in from a
 * different visual frame.
 *
 * Uses the same shimmer animation as ``ConfigSkeleton`` to stay
 * tonally consistent with the rest of the loading states.
 */
export default function ScoreboardSkeleton({ isPortrait = false }: ScoreboardSkeletonProps) {
  const { t } = useI18n();
  return (
    <div
      className={`scoreboard-skeleton ${isPortrait ? 'scoreboard-skeleton-portrait' : 'scoreboard-skeleton-landscape'}`}
      role="status"
      aria-busy="true"
      aria-live="polite"
      aria-label={t('app.connecting')}
      data-testid="scoreboard-skeleton"
    >
      <div className="scoreboard-skeleton-team">
        <div className="scoreboard-skeleton-block scoreboard-skeleton-score" />
        <div className="scoreboard-skeleton-block scoreboard-skeleton-meta" />
      </div>
      <div className="scoreboard-skeleton-center">
        <div className="scoreboard-skeleton-block scoreboard-skeleton-sets" />
        <div className="scoreboard-skeleton-block scoreboard-skeleton-meta" />
      </div>
      <div className="scoreboard-skeleton-team">
        <div className="scoreboard-skeleton-block scoreboard-skeleton-score" />
        <div className="scoreboard-skeleton-block scoreboard-skeleton-meta" />
      </div>
    </div>
  );
}
