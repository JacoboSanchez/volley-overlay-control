import { useEffect, useState } from 'react';

export interface MatchTimerProps {
  /**
   * Match start timestamp (Unix seconds), or ``null`` when the match
   * is unarmed. The component renders nothing in the null case so
   * the toolbar shows clean negative space until the operator scores
   * or hits Start match.
   */
  startedAt: number | null | undefined;
}

/**
 * Live MM:SS counter relative to ``startedAt``. Updates once per
 * second via ``setInterval``; pauses when the prop goes to ``null``.
 *
 * Shown in the HUD control bar so the operator and the match report
 * agree on "match duration so far". Negative deltas (clock skew
 * between server and client) clamp to ``0:00`` rather than render a
 * minus sign.
 */
export default function MatchTimer({ startedAt }: MatchTimerProps) {
  const [now, setNow] = useState<number>(() => Date.now() / 1000);

  useEffect(() => {
    if (startedAt == null) return;
    const id = setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => clearInterval(id);
  }, [startedAt]);

  if (startedAt == null) return null;
  const elapsed = Math.max(0, Math.floor(now - startedAt));
  const minutes = Math.floor(elapsed / 60);
  const seconds = elapsed % 60;
  const label = `${minutes}:${String(seconds).padStart(2, '0')}`;

  return (
    <div
      className="match-timer"
      role="timer"
      aria-live="off"
      data-testid="match-timer"
    >
      <span className="material-icons">timer</span>
      <span>{label}</span>
    </div>
  );
}
