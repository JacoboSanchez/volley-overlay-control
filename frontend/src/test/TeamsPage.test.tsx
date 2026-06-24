import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import TeamsPage from '../pages/TeamsPage';

vi.mock('../api/client', () => ({
  ApiError: class ApiError extends Error { detail = ''; },
  getMyGroups: vi.fn(),
  createMyGroup: vi.fn(),
  renameMyGroup: vi.fn(),
  deleteMyGroup: vi.fn(),
  addTeamsToMyGroup: vi.fn(),
  removeTeamFromMyGroup: vi.fn(),
  createMyTeam: vi.fn(),
  updateMyTeam: vi.fn(),
  removeTeamFromMine: vi.fn(),
}));

import * as api from '../api/client';

const team = (id: number, name: string, is_global = true): api.TeamOut => ({
  id, name, icon: null, color: '#123456', text_color: '#ffffff', is_global,
});

const groups = (): api.GroupDetail[] => [
  { id: null, name: 'All teams', kind: 'all', is_private: false,
    teams: [team(1, 'Breogán'), team(2, 'Estudiantes')], removable_ids: [] },
  { id: 5, name: 'My league', kind: 'private', is_private: true,
    teams: [team(1, 'Breogán')], removable_ids: [1] },
];

function cardFor(name: string): HTMLElement {
  return screen.getByText(name).closest('.acc-tcard') as HTMLElement;
}

describe('TeamsPage (groups)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.getMyGroups).mockResolvedValue(groups());
    vi.mocked(api.createMyGroup).mockResolvedValue(
      { id: 9, name: 'New', kind: 'private', is_private: true, teams: [], removable_ids: [] },
    );
    vi.mocked(api.addTeamsToMyGroup).mockResolvedValue({ added: 1 });
    vi.mocked(api.removeTeamFromMyGroup).mockResolvedValue({ ok: true, removed: true });
    vi.mocked(api.createMyTeam).mockResolvedValue(team(9, 'Lugo', false));
  });

  it('lists the All group (read-only) and the private group', async () => {
    render(<TeamsPage />);
    await waitFor(() => expect(screen.getByText('All teams')).toBeInTheDocument());
    // All teams offers "View" (read-only); the private group offers "Manage".
    expect(within(cardFor('All teams')).getByRole('button', { name: 'View' })).toBeInTheDocument();
    expect(within(cardFor('My league')).getByRole('button', { name: 'Manage' })).toBeInTheDocument();
  });

  it('creates a private group', async () => {
    render(<TeamsPage />);
    await waitFor(() => expect(screen.getByText('All teams')).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText('Group name'), { target: { value: 'Liga Gallega' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create group' }));
    await waitFor(() => expect(api.createMyGroup).toHaveBeenCalledWith('Liga Gallega'));
  });

  it('adds an addable team to a private group', async () => {
    render(<TeamsPage />);
    await waitFor(() => expect(screen.getByText('My league')).toBeInTheDocument());
    const card = cardFor('My league');
    fireEvent.click(within(card).getByRole('button', { name: 'Manage' }));
    fireEvent.click(within(card).getByRole('button', { name: 'Add teams' }));
    // Estudiantes is the only addable team (Breogán is already a member).
    fireEvent.click(within(card).getByLabelText('Select Estudiantes'));
    fireEvent.click(within(card).getByRole('button', { name: 'Add selected (1)' }));
    await waitFor(() => expect(api.addTeamsToMyGroup).toHaveBeenCalledWith(5, [2]));
  });

  it('removes the user-added member of a group', async () => {
    render(<TeamsPage />);
    await waitFor(() => expect(screen.getByText('My league')).toBeInTheDocument());
    const card = cardFor('My league');
    fireEvent.click(within(card).getByRole('button', { name: 'Manage' }));
    fireEvent.click(within(card).getByRole('button', { name: 'Remove Breogán' }));
    await waitFor(() => expect(api.removeTeamFromMyGroup).toHaveBeenCalledWith(5, 1));
  });

  it('creates a custom team', async () => {
    render(<TeamsPage />);
    await waitFor(() => expect(screen.getByText('Create a custom team')).toBeInTheDocument());
    const section = screen.getByText('Create a custom team').closest('div')!;
    fireEvent.change(within(section).getByLabelText('Name', { selector: 'input' }) as HTMLInputElement, {
      target: { value: 'Lugo CV' },
    });
    fireEvent.click(within(section).getByRole('button', { name: 'Add team' }));
    await waitFor(() =>
      expect(api.createMyTeam).toHaveBeenCalledWith(expect.objectContaining({ name: 'Lugo CV' })),
    );
  });
});
