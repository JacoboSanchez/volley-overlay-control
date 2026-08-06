import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import AdminTeamsPage from '../pages/AdminTeamsPage';

const auth = vi.hoisted(() => ({ role: 'admin' as 'admin' | 'user' }));
vi.mock('../auth/AuthContext', () => ({
  useAuth: () => ({ ctx: { user: { role: auth.role } } }),
}));

vi.mock('../api/admin', () => ({
  adminCreateTeam: vi.fn(),
  adminUpdateTeam: vi.fn(),
  adminDeleteTeam: vi.fn(),
  adminExportTeams: vi.fn(),
  adminImportTeams: vi.fn(),
  adminListGroups: vi.fn(),
  adminCreateGroup: vi.fn(),
  adminAddGroupMember: vi.fn(),
  adminRemoveGroupMember: vi.fn(),
  adminSetGroupActive: vi.fn(),
  adminDeleteGroup: vi.fn(),
  adminUploadIcon: vi.fn(),
  adminRenameIcon: vi.fn(),
  adminGetIconUsage: vi.fn(),
  adminDeleteIcon: vi.fn(),
  adminImportIconsFromTeams: vi.fn(),
}));
vi.mock('../api/http', () => ({
  ApiError: class ApiError extends Error {
    detail = '';
  },
}));
vi.mock('../api/icons', () => ({
  // Icon library (rendered by IconLibrarySection / the fieldset picker).
  listIcons: vi.fn().mockResolvedValue({
    globals: [],
    mine: [],
    quota: { used: 0, limit: 50 },
  }),
}));
vi.mock('../api/teams', () => ({
  getTeamCatalog: vi.fn(),
}));

import * as adminApi from '../api/admin';
import * as teamsApi from '../api/teams';

const team = (id: number, name: string): teamsApi.TeamOut => ({
  id,
  name,
  icon: null,
  color: '#123456',
  text_color: '#ffffff',
  is_global: true,
});

function renderPage() {
  return render(
    <MemoryRouter>
      <AdminTeamsPage />
    </MemoryRouter>,
  );
}

describe('AdminTeamsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    auth.role = 'admin';
    vi.mocked(teamsApi.getTeamCatalog).mockResolvedValue([
      team(1, 'Breogán'),
      team(2, 'Estudiantes'),
    ]);
    vi.mocked(adminApi.adminListGroups).mockResolvedValue([]);
    vi.mocked(adminApi.adminCreateTeam).mockResolvedValue(team(9, 'Lugo'));
    vi.mocked(adminApi.adminDeleteTeam).mockResolvedValue({ ok: true });
    vi.mocked(adminApi.adminCreateGroup).mockResolvedValue({
      id: 5,
      name: 'Liga',
      is_active: false,
      teams: [],
    });
    vi.mocked(adminApi.adminAddGroupMember).mockResolvedValue({ ok: true });
    vi.mocked(adminApi.adminRemoveGroupMember).mockResolvedValue({ ok: true, removed: true });
    vi.mocked(adminApi.adminSetGroupActive).mockResolvedValue({ id: 5, is_active: true });
    vi.mocked(adminApi.adminDeleteGroup).mockResolvedValue({ ok: true });
  });

  it('redirects a non-admin away from the page', () => {
    auth.role = 'user';
    renderPage();
    expect(screen.queryByText('Global catalog')).not.toBeInTheDocument();
  });

  it('renders catalog teams as cards', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText('Estudiantes')).toBeInTheDocument());
    expect(screen.getByText('Breogán')).toBeInTheDocument();
    expect(screen.getByText('Global catalog')).toBeInTheDocument();
  });

  it('bulk-deletes the selected catalog teams after confirming', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    renderPage();
    await waitFor(() => expect(screen.getByText('Breogán')).toBeInTheDocument());
    // No bulk action until something is selected.
    expect(screen.queryByRole('button', { name: /Delete selected/ })).toBeNull();
    fireEvent.click(screen.getByLabelText('Select Breogán'));
    fireEvent.click(screen.getByRole('button', { name: /Delete selected \(1\)/ }));
    await waitFor(() => expect(adminApi.adminDeleteTeam).toHaveBeenCalledWith(1));
    confirmSpy.mockRestore();
  });

  it('creates a catalog team from the reveal form', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText('Global catalog')).toBeInTheDocument());
    // The reveal button and the submit button share the "Add team" label, but
    // the reveal flips to "Close" once open, so only the submit remains.
    fireEvent.click(screen.getByRole('button', { name: 'Add team' }));
    fireEvent.change(screen.getByTestId('admin-team-name') as HTMLInputElement, {
      target: { value: 'Lugo CV' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Add team' }));
    await waitFor(() =>
      expect(adminApi.adminCreateTeam).toHaveBeenCalledWith(
        expect.objectContaining({ name: 'Lugo CV' }),
      ),
    );
  });

  it('creates a team group', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText('Team groups')).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText('Group name'), { target: { value: 'Liga Gallega' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create group' }));
    await waitFor(() => expect(adminApi.adminCreateGroup).toHaveBeenCalledWith('Liga Gallega'));
  });

  describe('group management', () => {
    beforeEach(() => {
      vi.mocked(adminApi.adminListGroups).mockResolvedValue([
        { id: 5, name: 'Liga', is_active: false, teams: [team(1, 'Breogán')] },
      ]);
    });

    it('adds a member, removes a member, publishes and deletes a group', async () => {
      const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
      renderPage();
      await waitFor(() => expect(screen.getByText('Liga')).toBeInTheDocument());
      // Scope to the group card: "Add team" also exists in the catalog section,
      // so unscoped role queries would be ambiguous.
      const card = screen.getByText('Liga').closest('.acc-tcard') as HTMLElement;
      fireEvent.click(within(card).getByRole('button', { name: 'Manage' }));

      // Publish (it starts as a draft).
      fireEvent.click(within(card).getByRole('button', { name: 'Publish' }));
      await waitFor(() => expect(adminApi.adminSetGroupActive).toHaveBeenCalledWith(5, true));

      // Remove the existing member (Breogán).
      fireEvent.click(within(card).getByRole('button', { name: 'Remove Breogán' }));
      await waitFor(() => expect(adminApi.adminRemoveGroupMember).toHaveBeenCalledWith(5, 1));

      // Add a catalog team not yet in the group (Estudiantes, id 2).
      fireEvent.change(within(card).getByLabelText('Choose a team to add'), {
        target: { value: '2' },
      });
      fireEvent.click(within(card).getByRole('button', { name: 'Add team' }));
      await waitFor(() => expect(adminApi.adminAddGroupMember).toHaveBeenCalledWith(5, 2));

      // Delete the group.
      fireEvent.click(within(card).getByRole('button', { name: 'Delete group' }));
      await waitFor(() => expect(adminApi.adminDeleteGroup).toHaveBeenCalledWith(5));
      confirmSpy.mockRestore();
    });
  });
});
