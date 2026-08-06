import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, screen } from '@testing-library/react';
import RecentAuditDrawer from '../components/RecentAuditDrawer';
import type { AuditFeed } from '../hooks/useAuditFeed';
import type { AuditRecord } from '../api/board';
import { renderWithI18n } from './helpers';

function record(
  ts: number,
  action: string,
  params: Record<string, unknown> = {},
  result?: Record<string, unknown>,
): AuditRecord {
  return {
    ts,
    action,
    params: params as AuditRecord['params'],
    result,
  };
}

/**
 * The drawer is a pure projection of the board's audit feed now — it does
 * no fetching of its own — so these render it against a plain feed object
 * rather than a mocked API.
 */
function feed(records: AuditRecord[] = [], overrides: Partial<AuditFeed> = {}): AuditFeed {
  return {
    records,
    loading: false,
    error: null,
    refresh: vi.fn(),
    onAppend: vi.fn(),
    onInvalidate: vi.fn(),
    onResync: vi.fn(),
    ...overrides,
  };
}

describe('RecentAuditDrawer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing when closed', () => {
    renderWithI18n(<RecentAuditDrawer open={false} audit={feed()} onClose={vi.fn()} />);
    expect(screen.queryByTestId('recent-audit-drawer')).toBeNull();
  });

  it('renders the empty state when audit is empty', () => {
    renderWithI18n(<RecentAuditDrawer open={true} audit={feed()} onClose={vi.fn()} />);
    expect(screen.getByText(/no recent actions/i)).toBeInTheDocument();
  });

  it('lists records newest-first with action labels', () => {
    const now = Date.now() / 1000;
    // Feed order is oldest-first, exactly as GET /audit returns it.
    const records = [
      record(now - 60, 'add_point', { team: 1 }, { team_1: { score: 1 }, team_2: { score: 0 } }),
      record(now - 30, 'add_timeout', { team: 2 }),
      record(now - 5, 'add_point', { team: 2 }, { team_1: { score: 1 }, team_2: { score: 1 } }),
    ];
    renderWithI18n(<RecentAuditDrawer open={true} audit={feed(records)} onClose={vi.fn()} />);

    const list = screen.getByTestId('recent-audit-list');
    const rows = list.querySelectorAll('li');
    expect(rows).toHaveLength(3);
    // Newest-first: the most recent (now-5) lands at the top.
    expect(rows[0]!.className).toContain('recent-audit-row-point-t2');
    expect(rows[1]!.className).toContain('recent-audit-row-timeout');
    expect(rows[2]!.className).toContain('recent-audit-row-point-t1');
    expect(rows[0]).toHaveTextContent(/Point — Team 2/);
    expect(rows[1]).toHaveTextContent(/Timeout — Team 2/);
  });

  it('shows only the newest ``limit`` records', () => {
    const now = Date.now() / 1000;
    const records = Array.from({ length: 5 }, (_, i) =>
      record(now - (5 - i), 'add_point', { team: 1 }),
    );
    renderWithI18n(
      <RecentAuditDrawer open={true} audit={feed(records)} limit={2} onClose={vi.fn()} />,
    );

    const rows = screen.getByTestId('recent-audit-list').querySelectorAll('li');
    expect(rows).toHaveLength(2);
  });

  it('marks undone rows with the strikethrough modifier', () => {
    const now = Date.now() / 1000;
    renderWithI18n(
      <RecentAuditDrawer
        open={true}
        audit={feed([record(now - 1, 'add_point', { team: 1, undo: true })])}
        onClose={vi.fn()}
      />,
    );
    const row = screen.getByTestId('recent-audit-list').querySelector('li')!;
    expect(row.className).toContain('recent-audit-row-undo');
    expect(row).toHaveTextContent(/\(undone\)/);
  });

  it('closes via the close button and via Escape', () => {
    const onClose = vi.fn();
    renderWithI18n(<RecentAuditDrawer open={true} audit={feed()} onClose={onClose} />);
    fireEvent.click(screen.getByTestId('recent-audit-close'));
    expect(onClose).toHaveBeenCalledTimes(1);
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it('refresh button asks the feed to re-read', () => {
    const refresh = vi.fn();
    renderWithI18n(
      <RecentAuditDrawer open={true} audit={feed([], { refresh })} onClose={vi.fn()} />,
    );
    fireEvent.click(screen.getByTestId('recent-audit-refresh'));
    expect(refresh).toHaveBeenCalledTimes(1);
  });
});
