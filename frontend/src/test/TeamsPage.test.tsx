import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import TeamsPage from '../pages/TeamsPage';

vi.mock('../auth/AuthContext', () => ({
  useAuth: () => ({ ctx: { user: { role: 'user' } } }),
}));

vi.mock('../api/client', () => ({
  ApiError: class ApiError extends Error { detail = ''; },
  getMyTeams: vi.fn(),
  getTeamCatalog: vi.fn(),
  getTeamGroups: vi.fn(),
  addTeamsToMine: vi.fn(),
  removeTeamsFromMine: vi.fn(),
  createMyTeam: vi.fn(),
  updateMyTeam: vi.fn(),
  copyGroupToMine: vi.fn(),
}));

import * as api from '../api/client';

const team = (id: number, name: string, is_global = true): api.TeamOut => ({
  id, name, icon: null, color: '#123456', text_color: '#ffffff', is_global,
});

describe('TeamsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.getMyTeams).mockResolvedValue([team(1, 'Breogán'), team(2, 'My Club', false)]);
    vi.mocked(api.getTeamCatalog).mockResolvedValue([team(1, 'Breogán'), team(3, 'Estudiantes')]);
    vi.mocked(api.getTeamGroups).mockResolvedValue([]);
    vi.mocked(api.removeTeamsFromMine).mockResolvedValue({ removed: 1 });
    vi.mocked(api.addTeamsToMine).mockResolvedValue({ added: 1 });
    vi.mocked(api.createMyTeam).mockResolvedValue(team(9, 'New', false));
  });

  it('marks a user-owned team as custom and offers Edit', async () => {
    render(<TeamsPage />);
    await waitFor(() => expect(screen.getByText('My Club')).toBeInTheDocument());
    expect(screen.getByText('custom')).toBeInTheDocument();
    // Custom team has an Edit button; the global one does not.
    expect(screen.getAllByRole('button', { name: 'Edit' })).toHaveLength(1);
  });

  it('only lists catalog teams not already in my list', async () => {
    render(<TeamsPage />);
    await waitFor(() => expect(screen.getByText('Estudiantes')).toBeInTheDocument());
    // Breogán is already mine → it appears under "My teams" but not as an
    // addable catalog card. The bulk "Add selected" action only surfaces once a
    // team is selected, so it is absent on first render.
    expect(screen.queryByRole('button', { name: /Add selected/ })).toBeNull();
    fireEvent.click(screen.getByLabelText('Select Estudiantes'));
    expect(screen.getByRole('button', { name: /Add selected \(1\)/ })).toBeInTheDocument();
  });

  it('batch-removes the selected teams from my list', async () => {
    render(<TeamsPage />);
    await waitFor(() => expect(screen.getByText('Breogán')).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText('Select Breogán'));
    fireEvent.click(screen.getByRole('button', { name: /Remove selected \(1\)/ }));
    await waitFor(() => expect(api.removeTeamsFromMine).toHaveBeenCalledWith([1]));
  });

  it('batch-adds the selected catalog teams', async () => {
    render(<TeamsPage />);
    await waitFor(() => expect(screen.getByText('Estudiantes')).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText('Select Estudiantes'));
    fireEvent.click(screen.getByRole('button', { name: /Add selected \(1\)/ }));
    await waitFor(() => expect(api.addTeamsToMine).toHaveBeenCalledWith([3]));
  });

  it('select-all toggles every team in my list', async () => {
    // The selection includes the custom "My Club", so removal first asks for
    // confirmation; outside a ConfirmProvider that falls back to window.confirm.
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    render(<TeamsPage />);
    await waitFor(() => expect(screen.getByText('Breogán')).toBeInTheDocument());
    // First select-all is the "My teams" header (Catalog has its own).
    fireEvent.click(screen.getAllByLabelText('Select all')[0]!);
    fireEvent.click(screen.getByRole('button', { name: /Remove selected \(2\)/ }));
    await waitFor(() => expect(api.removeTeamsFromMine).toHaveBeenCalledWith([1, 2]));
    confirmSpy.mockRestore();
  });

  it('creates a custom team', async () => {
    render(<TeamsPage />);
    await waitFor(() => expect(screen.getByText('Create a custom team')).toBeInTheDocument());
    const form = screen.getByText('Create a custom team').closest('div')!;
    fireEvent.change(within(form).getByLabelText('Name', { selector: 'input' }) as HTMLInputElement, {
      target: { value: 'Lugo CV' },
    });
    // The two colour pickers carry distinct accessible names (a11y).
    expect(within(form).getByLabelText('Colour')).toBeInTheDocument();
    expect(within(form).getByLabelText('Text')).toBeInTheDocument();
    fireEvent.click(within(form).getByRole('button', { name: 'Add team' }));
    await waitFor(() =>
      expect(api.createMyTeam).toHaveBeenCalledWith(
        expect.objectContaining({ name: 'Lugo CV' }),
      ),
    );
  });

  it('a filtered bulk-remove only deletes the visible selection, not hidden selected rows', async () => {
    // >8 teams so the filter box renders; all global so removal needs no confirm.
    const many = Array.from({ length: 9 }, (_, i) =>
      team(100 + i, i === 0 ? 'Breogán' : `Team ${i}`));
    vi.mocked(api.getMyTeams).mockResolvedValue(many);
    vi.mocked(api.getTeamCatalog).mockResolvedValue(many); // all already mine → no catalog list/filter
    render(<TeamsPage />);
    await waitFor(() => expect(screen.getByText('Breogán')).toBeInTheDocument());

    // Select all 9, then narrow the filter to just Breogán.
    fireEvent.click(screen.getByLabelText('Select all'));
    expect(screen.getByRole('button', { name: 'Remove selected (9)' })).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText('Filter by name…'), { target: { value: 'Breog' } });

    // The bulk action now matches the single visible row — the 8 hidden-but-still
    // -selected teams are NOT removed.
    expect(screen.getByRole('button', { name: 'Remove selected (1)' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Remove selected (1)' }));
    await waitFor(() => expect(api.removeTeamsFromMine).toHaveBeenCalledWith([100]));
  });
});
