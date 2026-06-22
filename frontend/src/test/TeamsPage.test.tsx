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
    // Breogán is already mine → it appears under "My teams" but not as an addable catalog row.
    // "Estudiantes" is the only addable catalog entry.
    const addBtn = screen.getByRole('button', { name: /Add selected/ });
    expect(addBtn).toBeDisabled();
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

  it('creates a custom team', async () => {
    render(<TeamsPage />);
    await waitFor(() => expect(screen.getByText('Create a custom team')).toBeInTheDocument());
    const form = screen.getByText('Create a custom team').closest('div')!;
    fireEvent.change(within(form).getByLabelText('Name', { selector: 'input' }) as HTMLInputElement, {
      target: { value: 'Lugo CV' },
    });
    fireEvent.click(within(form).getByRole('button', { name: 'Add team' }));
    await waitFor(() =>
      expect(api.createMyTeam).toHaveBeenCalledWith(
        expect.objectContaining({ name: 'Lugo CV' }),
      ),
    );
  });
});
