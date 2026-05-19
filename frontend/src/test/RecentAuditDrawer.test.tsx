import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import RecentAuditDrawer from '../components/RecentAuditDrawer';
import * as api from '../api/client';
import type { AuditRecord } from '../api/client';
import { mockGameState, renderWithI18n } from './helpers';

vi.mock('../api/client', () => ({
  getAudit: vi.fn(),
}));

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

describe('RecentAuditDrawer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.getAudit).mockResolvedValue({
      oid: 'x',
      count: 0,
      records: [],
    });
  });

  it('renders nothing when closed', () => {
    renderWithI18n(
      <RecentAuditDrawer oid="x" open={false} confirmedState={mockGameState} onClose={vi.fn()} />,
    );
    expect(screen.queryByTestId('recent-audit-drawer')).toBeNull();
    expect(api.getAudit).not.toHaveBeenCalled();
  });

  it('renders the empty state when audit is empty', async () => {
    renderWithI18n(
      <RecentAuditDrawer oid="x" open={true} confirmedState={mockGameState} onClose={vi.fn()} />,
    );
    await waitFor(() => expect(screen.getByText(/no recent actions/i)).toBeInTheDocument());
  });

  it('lists records newest-first with action labels', async () => {
    const now = Date.now() / 1000;
    vi.mocked(api.getAudit).mockResolvedValue({
      oid: 'x',
      count: 3,
      records: [
        record(now - 60, 'add_point', { team: 1 }, { team_1: { score: 1 }, team_2: { score: 0 } }),
        record(now - 30, 'add_timeout', { team: 2 }),
        record(now - 5, 'add_point', { team: 2 }, { team_1: { score: 1 }, team_2: { score: 1 } }),
      ],
    });
    renderWithI18n(
      <RecentAuditDrawer oid="x" open={true} confirmedState={mockGameState} onClose={vi.fn()} />,
    );
    const list = await screen.findByTestId('recent-audit-list');
    const rows = list.querySelectorAll('li');
    expect(rows).toHaveLength(3);
    // Newest-first: the most recent (now-5) lands at the top.
    expect(rows[0]!.className).toContain('recent-audit-row-point-t2');
    expect(rows[1]!.className).toContain('recent-audit-row-timeout');
    expect(rows[2]!.className).toContain('recent-audit-row-point-t1');
    // Each row has a label.
    expect(rows[0]).toHaveTextContent(/Point — Team 2/);
    expect(rows[1]).toHaveTextContent(/Timeout — Team 2/);
  });

  it('marks undone rows with the strikethrough modifier', async () => {
    const now = Date.now() / 1000;
    vi.mocked(api.getAudit).mockResolvedValue({
      oid: 'x',
      count: 1,
      records: [record(now - 1, 'add_point', { team: 1, undo: true })],
    });
    renderWithI18n(
      <RecentAuditDrawer oid="x" open={true} confirmedState={mockGameState} onClose={vi.fn()} />,
    );
    const list = await screen.findByTestId('recent-audit-list');
    const row = list.querySelector('li')!;
    expect(row.className).toContain('recent-audit-row-undo');
    expect(row).toHaveTextContent(/\(undone\)/);
  });

  it('closes via the close button and via Escape', async () => {
    const onClose = vi.fn();
    renderWithI18n(
      <RecentAuditDrawer oid="x" open={true} confirmedState={mockGameState} onClose={onClose} />,
    );
    fireEvent.click(screen.getByTestId('recent-audit-close'));
    expect(onClose).toHaveBeenCalledTimes(1);
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledTimes(2);
  });

  it('refresh button forces a refetch', async () => {
    renderWithI18n(
      <RecentAuditDrawer oid="x" open={true} confirmedState={mockGameState} onClose={vi.fn()} />,
    );
    await waitFor(() => expect(api.getAudit).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByTestId('recent-audit-refresh'));
    await waitFor(() => expect(api.getAudit).toHaveBeenCalledTimes(2));
  });
});
