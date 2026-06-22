import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

/** Shared placeholder for "nothing here yet" states across the account pages.
 *  Optionally renders a call-to-action button linking somewhere useful (e.g.
 *  the Overlays page so an operator can create their first scoreboard). */
export default function EmptyState({
  children,
  action,
}: {
  children: ReactNode;
  action?: { to: string; label: string };
}) {
  return (
    <div className="acc-empty">
      <div>{children}</div>
      {action && (
        <div className="acc-empty-action">
          <Link className="acc-btn" to={action.to}>
            {action.label}
          </Link>
        </div>
      )}
    </div>
  );
}
