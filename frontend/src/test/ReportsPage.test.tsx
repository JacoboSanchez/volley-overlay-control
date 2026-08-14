import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent, waitFor } from '@testing-library/react';
import { renderWithI18n } from './helpers';
import ReportsPage from '../pages/ReportsPage';

vi.mock('../api/http', () => ({
  ApiError: class ApiError extends Error {
    detail = '';
  },
}));
vi.mock('../api/overlays', () => ({
  getOverlays: vi.fn(),
}));
vi.mock('../api/reports', () => ({
  listReports: vi.fn(),
  listReportDays: vi.fn(),
  deleteMatch: vi.fn(),
  deleteMatches: vi.fn(),
}));

import * as overlaysApi from '../api/overlays';
import * as reportsApi from '../api/reports';

const overlay = (oid: string) =>
  ({ oid, description: null }) as unknown as overlaysApi.OverlayPayload;
const match = (id: string, ended: number, dur: number) =>
  ({
    match_id: id,
    oid: 'o1',
    ended_at: ended,
    duration_s: dur,
    winning_team: 1,
    team_1_sets: 3,
    team_2_sets: 1,
    team_1_name: 'A',
    team_2_name: 'B',
  }) as reportsApi.MatchSummary;

let reportRows: reportsApi.MatchSummary[] = [];

describe('ReportsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(overlaysApi.getOverlays).mockResolvedValue([overlay('o1')]);
    // m1: newer (ended 2000), shorter (10 min); m2: older (1000), longer (20 min).
    reportRows = [match('m1', 2000, 600), match('m2', 1000, 1200)];
    vi.mocked(reportsApi.listReports).mockImplementation(async (params = {}) => {
      let rows = [...reportRows];
      if (params.mode) rows = rows.filter((row) => row.mode === params.mode);
      const key = params.sort === 'duration' ? 'duration_s' : 'ended_at';
      const sign = params.direction === 'asc' ? 1 : -1;
      rows.sort((a, b) => sign * ((a[key] ?? 0) - (b[key] ?? 0)));
      const offset = params.offset ?? 0;
      const limit = params.limit ?? 20;
      return {
        count: rows.length,
        matches: rows.slice(offset, offset + limit),
        limit,
        offset,
        sort: params.sort ?? 'ended',
        direction: params.direction ?? 'desc',
      };
    });
    vi.mocked(reportsApi.listReportDays).mockResolvedValue({ days: ['1970-01-01'] });
    vi.mocked(reportsApi.deleteMatches).mockImplementation(async (ids) => ({
      requested: ids.length,
      deleted: ids.length,
    }));
  });

  it('sorts by date descending by default (newest first)', async () => {
    renderWithI18n(<ReportsPage />);
    await waitFor(() => expect(screen.getAllByText(/min/).length).toBe(2));
    const durations = screen.getAllByText(/min/).map((el) => el.textContent);
    expect(durations).toEqual(['10 min', '20 min']);
  });

  it('toggles to sort by duration when the Duration header is clicked', async () => {
    renderWithI18n(<ReportsPage />);
    await waitFor(() => expect(screen.getAllByText(/min/).length).toBe(2));
    fireEvent.click(screen.getByRole('button', { name: /Duration/ }));
    await waitFor(() => {
      const durations = screen.getAllByText(/min/).map((el) => el.textContent);
      expect(durations).toEqual(['20 min', '10 min']); // longest first
    });
  });

  it('ignores a stale report response that resolves after a newer one', async () => {
    // Filtering/sorting/paging are server-side now, so switching one starts a
    // request while the previous is still open. The slower earlier response
    // must not repopulate the table the operator has already moved past.
    vi.mocked(overlaysApi.getOverlays).mockResolvedValue([
      overlay('o1'),
      overlay('o2'),
      overlay('o3'),
    ]);
    renderWithI18n(<ReportsPage />);
    await waitFor(() => expect(screen.getAllByText(/min/).length).toBe(2));

    // From here on every request hangs until the test answers it.
    const pending: Array<(rows: reportsApi.MatchSummary[]) => void> = [];
    vi.mocked(reportsApi.listReports).mockImplementation(
      (params = {}) =>
        new Promise((resolve) => {
          pending.push((rows) =>
            resolve({
              count: rows.length,
              matches: rows,
              limit: 20,
              offset: 0,
              sort: params.sort ?? 'ended',
              direction: params.direction ?? 'desc',
            }),
          );
        }),
    );

    // The scoreboard picker stays usable while the table loads, so two
    // switches in a row leave two requests open.
    const picker = screen.getByLabelText('Scoreboard');
    fireEvent.change(picker, { target: { value: 'o2' } });
    await waitFor(() => expect(pending.length).toBe(1));
    fireEvent.change(picker, { target: { value: 'o3' } });
    await waitFor(() => expect(pending.length).toBe(2));

    // Newest request answers first…
    pending[1]!([match('new', 3000, 900)]);
    await waitFor(() => expect(screen.getByText('15 min')).toBeInTheDocument());
    // …then the superseded one finally lands.
    pending[0]!([match('stale', 1000, 1200)]);

    await waitFor(() => expect(screen.getAllByText(/min/).length).toBe(1));
    expect(screen.getByText('15 min')).toBeInTheDocument();
    expect(screen.queryByText('20 min')).toBeNull();
  });

  it('deletes a single report after confirmation', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    renderWithI18n(<ReportsPage />);
    await waitFor(() => expect(screen.getAllByText(/min/).length).toBe(2));
    // First row is the newest match (m1) under the default sort.
    fireEvent.click(screen.getAllByRole('button', { name: 'Delete report' })[0]!);
    await waitFor(() => expect(reportsApi.deleteMatches).toHaveBeenCalledWith(['m1']));
    confirmSpy.mockRestore();
  });

  it('bulk-deletes the selected reports', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    renderWithI18n(<ReportsPage />);
    await waitFor(() => expect(screen.getAllByText(/min/).length).toBe(2));
    fireEvent.click(screen.getAllByLabelText('Select match')[0]!); // selects m1
    fireEvent.click(screen.getByRole('button', { name: /Delete selected \(1\)/ }));
    await waitFor(() => expect(reportsApi.deleteMatches).toHaveBeenCalledWith(['m1']));
    expect(reportsApi.deleteMatches).toHaveBeenCalledTimes(1);
    confirmSpy.mockRestore();
  });

  it('filters reports by match type', async () => {
    reportRows = [
      { ...match('m1', 2000, 600), mode: 'beach' },
      { ...match('m2', 1000, 1200), mode: 'table_tennis' },
    ];
    renderWithI18n(<ReportsPage />);
    await waitFor(() => expect(screen.getAllByText(/min/).length).toBe(2));
    fireEvent.change(screen.getByTestId('reports-mode-filter'), { target: { value: 'beach' } });
    await waitFor(() => expect(screen.getAllByText(/min/).length).toBe(1));
    // The remaining row is the beach match (10 min).
    expect(screen.getByText('10 min')).toBeInTheDocument();
  });

  it('paginates when there are more than one page of matches', async () => {
    const many = Array.from({ length: 25 }, (_, i) => match(`m${i}`, 1000 + i, 600));
    reportRows = many;
    renderWithI18n(<ReportsPage />);
    await waitFor(() => expect(screen.getAllByText(/min/).length).toBe(20)); // PAGE_SIZE
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    await waitFor(() => expect(screen.getAllByText(/min/).length).toBe(5)); // remainder
  });

  it('select-all-on-page picks every report on the current page', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    renderWithI18n(<ReportsPage />);
    await waitFor(() => expect(screen.getAllByText(/min/).length).toBe(2));
    fireEvent.click(screen.getByLabelText('Select all on this page'));
    fireEvent.click(screen.getByRole('button', { name: /Delete selected \(2\)/ }));
    await waitFor(() => expect(reportsApi.deleteMatches).toHaveBeenCalledTimes(1));
    expect(vi.mocked(reportsApi.deleteMatches).mock.calls[0]?.[0]).toHaveLength(2);
    confirmSpy.mockRestore();
  });

  it('refreshes the calendar days after a deletion', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    renderWithI18n(<ReportsPage />);
    await waitFor(() => expect(screen.getAllByText(/min/).length).toBe(2));
    const before = vi.mocked(reportsApi.listReportDays).mock.calls.length;

    fireEvent.click(screen.getByLabelText('Select all on this page'));
    fireEvent.click(screen.getByRole('button', { name: /Delete selected \(2\)/ }));

    // Deleting the last report of a day must drop its dot; neither oid nor
    // mode changed, so the day query only reruns if the delete asks it to.
    await waitFor(() =>
      expect(vi.mocked(reportsApi.listReportDays).mock.calls.length).toBeGreaterThan(before),
    );
    confirmSpy.mockRestore();
  });

  it('select-all-on-page only selects the visible page, not every page', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    const many = Array.from({ length: 25 }, (_, i) => match(`m${i}`, 1000 + i, 600));
    reportRows = many;
    renderWithI18n(<ReportsPage />);
    await waitFor(() => expect(screen.getAllByText(/min/).length).toBe(20)); // PAGE_SIZE
    fireEvent.click(screen.getByLabelText('Select all on this page'));
    // Only the 20 rows on this page are selected, not all 25.
    fireEvent.click(screen.getByRole('button', { name: /Delete selected \(20\)/ }));
    await waitFor(() => expect(reportsApi.deleteMatches).toHaveBeenCalledTimes(1));
    expect(vi.mocked(reportsApi.deleteMatches).mock.calls[0]?.[0]).toHaveLength(20);
    confirmSpy.mockRestore();
  });
});
