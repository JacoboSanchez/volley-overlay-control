import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent, waitFor } from '@testing-library/react';
import { renderWithI18n } from './helpers';
import ReportsPage from '../pages/ReportsPage';

vi.mock('../api/client', () => ({
  ApiError: class ApiError extends Error { detail = ''; },
  getOverlays: vi.fn(),
  listReports: vi.fn(),
  deleteMatch: vi.fn(),
}));

import * as api from '../api/client';

const overlay = (oid: string) => ({ oid, display_name: oid }) as unknown as api.OverlayPayload;
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
  }) as api.MatchSummary;

describe('ReportsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.getOverlays).mockResolvedValue([overlay('o1')]);
    // m1: newer (ended 2000), shorter (10 min); m2: older (1000), longer (20 min).
    vi.mocked(api.listReports).mockResolvedValue({
      count: 2,
      matches: [match('m1', 2000, 600), match('m2', 1000, 1200)],
    });
    vi.mocked(api.deleteMatch).mockResolvedValue(undefined);
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

  it('deletes a single report after confirmation', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    renderWithI18n(<ReportsPage />);
    await waitFor(() => expect(screen.getAllByText(/min/).length).toBe(2));
    // First row is the newest match (m1) under the default sort.
    fireEvent.click(screen.getAllByRole('button', { name: 'Delete report' })[0]!);
    await waitFor(() => expect(api.deleteMatch).toHaveBeenCalledWith('m1'));
    confirmSpy.mockRestore();
  });

  it('bulk-deletes the selected reports', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    renderWithI18n(<ReportsPage />);
    await waitFor(() => expect(screen.getAllByText(/min/).length).toBe(2));
    fireEvent.click(screen.getAllByLabelText('Select match')[0]!); // selects m1
    fireEvent.click(screen.getByRole('button', { name: /Delete selected \(1\)/ }));
    await waitFor(() => expect(api.deleteMatch).toHaveBeenCalledWith('m1'));
    expect(api.deleteMatch).toHaveBeenCalledTimes(1);
    confirmSpy.mockRestore();
  });

  it('filters reports by match type', async () => {
    vi.mocked(api.listReports).mockResolvedValue({
      count: 2,
      matches: [
        { ...match('m1', 2000, 600), mode: 'beach' },
        { ...match('m2', 1000, 1200), mode: 'table_tennis' },
      ],
    });
    renderWithI18n(<ReportsPage />);
    await waitFor(() => expect(screen.getAllByText(/min/).length).toBe(2));
    fireEvent.change(screen.getByTestId('reports-mode-filter'), { target: { value: 'beach' } });
    await waitFor(() => expect(screen.getAllByText(/min/).length).toBe(1));
    // The remaining row is the beach match (10 min).
    expect(screen.getByText('10 min')).toBeInTheDocument();
  });

  it('paginates when there are more than one page of matches', async () => {
    const many = Array.from({ length: 25 }, (_, i) => match(`m${i}`, 1000 + i, 600));
    vi.mocked(api.listReports).mockResolvedValue({ count: 25, matches: many });
    renderWithI18n(<ReportsPage />);
    await waitFor(() => expect(screen.getAllByText(/min/).length).toBe(20)); // PAGE_SIZE
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    await waitFor(() => expect(screen.getAllByText(/min/).length).toBe(5)); // remainder
  });

  it('select-all picks every shown report', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    renderWithI18n(<ReportsPage />);
    await waitFor(() => expect(screen.getAllByText(/min/).length).toBe(2));
    fireEvent.click(screen.getByLabelText('Select all'));
    fireEvent.click(screen.getByRole('button', { name: /Delete selected \(2\)/ }));
    await waitFor(() => expect(api.deleteMatch).toHaveBeenCalledTimes(2));
    confirmSpy.mockRestore();
  });
});
