import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent, waitFor, render } from '@testing-library/react';
import * as api from '../api/client';
import IconPickerDialog from '../components/icons/IconPickerDialog';
import IconBatchImportDialog from '../components/icons/IconBatchImportDialog';
import IconLibrarySection from '../components/icons/IconLibrarySection';
import TeamFieldset from '../components/teams/TeamFieldset';
import { SwatchBox } from '../components/teams/TeamSwatch';
import { useTeamDraft } from '../components/teams/useTeamDraft';
import { renderWithI18n } from './helpers';

vi.mock('../api/client', () => ({
  ApiError: class ApiError extends Error {
    status: number;
    detail: string;
    constructor(status: number, message: string, detail?: string) {
      super(message);
      this.status = status;
      this.detail = detail || message;
    }
  },
  listIcons: vi.fn(),
  uploadMyIcon: vi.fn(),
  adminUploadIcon: vi.fn(),
  renameMyIcon: vi.fn(),
  adminRenameIcon: vi.fn(),
  getMyIconUsage: vi.fn(),
  adminGetIconUsage: vi.fn(),
  deleteMyIcon: vi.fn(),
  adminDeleteIcon: vi.fn(),
  importIconsFromMyTeams: vi.fn(),
  adminImportIconsFromTeams: vi.fn(),
}));

const mocked = vi.mocked(api);

function icon(id: number, name: string, isGlobal = false): api.IconOut {
  return {
    id,
    name,
    url: `/media/icons/hash${id}-abcd.webp`,
    is_global: isGlobal,
    width: 128,
    height: 128,
    size_bytes: 2048,
  };
}

function team(id: number, name: string, iconUrl: string | null): api.TeamOut {
  return { id, name, icon: iconUrl, color: null, text_color: null, is_global: false };
}

beforeEach(() => {
  vi.clearAllMocks();
  mocked.listIcons.mockResolvedValue({
    globals: [icon(1, 'League', true)],
    mine: [icon(2, 'Lions')],
    quota: { used: 1, limit: 50 },
  });
});

describe('IconPickerDialog', () => {
  it('lists both scopes and returns the picked icon URL', async () => {
    const onSelect = vi.fn();
    renderWithI18n(<IconPickerDialog open onClose={vi.fn()} onSelect={onSelect} />);
    await waitFor(() => expect(screen.getByText('League')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Lions'));
    expect(onSelect).toHaveBeenCalledWith('/media/icons/hash2-abcd.webp');
  });

  it('uploads a chosen file and auto-selects it', async () => {
    mocked.uploadMyIcon.mockResolvedValue(icon(9, 'Fresh'));
    const onSelect = vi.fn();
    renderWithI18n(<IconPickerDialog open onClose={vi.fn()} onSelect={onSelect} />);
    await waitFor(() => expect(mocked.listIcons).toHaveBeenCalled());
    const file = new File(['x'], 'fresh-logo.png', { type: 'image/png' });
    fireEvent.change(screen.getByTestId('icon-file-input'), { target: { files: [file] } });
    // Name prefilled from the file name, minus extension.
    const nameInput = screen.getByTestId('icon-upload-name') as HTMLInputElement;
    expect(nameInput.value).toBe('fresh-logo');
    fireEvent.click(screen.getByText('Upload'));
    await waitFor(() => expect(mocked.uploadMyIcon).toHaveBeenCalledWith('fresh-logo', file));
    expect(onSelect).toHaveBeenCalledWith('/media/icons/hash9-abcd.webp');
  });

  it('shows a name filter above the threshold and narrows both sections', async () => {
    mocked.listIcons.mockResolvedValue({
      globals: Array.from({ length: 6 }, (_, i) => icon(100 + i, `League ${i}`, true)),
      mine: [icon(1, 'Lions'), icon(2, 'Tigers'), icon(3, 'Panthers')],
      quota: { used: 3, limit: 50 },
    });
    renderWithI18n(<IconPickerDialog open onClose={vi.fn()} onSelect={vi.fn()} />);
    await waitFor(() => expect(screen.getByText('Lions')).toBeInTheDocument());
    const filter = screen.getByTestId('icon-picker-filter');
    fireEvent.change(filter, { target: { value: 'tig' } });
    expect(screen.getByText('Tigers')).toBeInTheDocument();
    expect(screen.queryByText('Lions')).not.toBeInTheDocument();
    expect(screen.queryByText('League 1')).not.toBeInTheDocument();
    // Empty-after-filter shows the no-match message, not the empty-library one.
    fireEvent.change(filter, { target: { value: 'zzz' } });
    expect(screen.getAllByText('No icon matches "zzz".').length).toBe(2);
  });

  it('hides the filter for small libraries', async () => {
    renderWithI18n(<IconPickerDialog open onClose={vi.fn()} onSelect={vi.fn()} />);
    await waitFor(() => expect(screen.getByText('Lions')).toBeInTheDocument());
    expect(screen.queryByTestId('icon-picker-filter')).not.toBeInTheDocument();
  });

  it('uploads to the global library when scoped for admin pages', async () => {
    mocked.adminUploadIcon.mockResolvedValue(icon(9, 'Fresh', true));
    renderWithI18n(
      <IconPickerDialog open onClose={vi.fn()} onSelect={vi.fn()} uploadScope="global" />,
    );
    await waitFor(() => expect(mocked.listIcons).toHaveBeenCalled());
    const file = new File(['x'], 'g.png', { type: 'image/png' });
    fireEvent.change(screen.getByTestId('icon-file-input'), { target: { files: [file] } });
    fireEvent.click(screen.getByText('Upload'));
    await waitFor(() => expect(mocked.adminUploadIcon).toHaveBeenCalled());
    expect(mocked.uploadMyIcon).not.toHaveBeenCalled();
  });
});

describe('TeamFieldset library button', () => {
  function Wrapper() {
    const draft = useTeamDraft();
    return (
      <div>
        <TeamFieldset draft={draft} idPrefix="tst" />
      </div>
    );
  }

  it('opens the picker and picking fills the logo input', async () => {
    renderWithI18n(<Wrapper />);
    fireEvent.click(screen.getByTestId('tst-logo-browse'));
    await waitFor(() => expect(screen.getByText('Lions')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Lions'));
    const logoInput = screen.getByTestId('tst-logo') as HTMLInputElement;
    await waitFor(() => expect(logoInput.value).toBe('/media/icons/hash2-abcd.webp'));
  });
});

describe('IconBatchImportDialog', () => {
  it('lists only teams with external URLs, preselected, and reports results', async () => {
    const importFn = vi.fn().mockResolvedValue({
      results: [{ team_id: 1, team_name: 'Ext', status: 'ok', icon_url: '/media/icons/x.webp' }],
    });
    const onDone = vi.fn();
    renderWithI18n(
      <IconBatchImportDialog
        open
        onClose={vi.fn()}
        teams={[
          team(1, 'Ext', 'https://cdn.example.com/a.png'),
          team(2, 'Hosted', '/media/icons/y.webp'),
          team(3, 'None', null),
        ]}
        importFn={importFn}
        onDone={onDone}
      />,
    );
    expect(screen.getByText('Ext')).toBeInTheDocument();
    expect(screen.queryByText('Hosted')).not.toBeInTheDocument();
    expect(screen.queryByText('None')).not.toBeInTheDocument();

    fireEvent.click(screen.getByText('Import 1 selected'));
    await waitFor(() => expect(importFn).toHaveBeenCalledWith([1]));
    await waitFor(() => expect(screen.getByText('Imported')).toBeInTheDocument());
    expect(onDone).toHaveBeenCalled();
  });

  it('keeps the results visible when the parent refetch delivers a new teams array', async () => {
    // Regression: after a successful run, onDone() makes the parent reload
    // teams; the new array reference used to re-trigger the reset effect and
    // wipe the just-rendered outcome list back to the (re-checked) checklist.
    const importFn = vi.fn().mockResolvedValue({
      results: [{ team_id: 1, team_name: 'Ext', status: 'ok', icon_url: '/media/icons/x.webp' }],
    });
    const view = renderWithI18n(
      <IconBatchImportDialog
        open
        onClose={vi.fn()}
        teams={[team(1, 'Ext', 'https://cdn.example.com/a.png')]}
        importFn={importFn}
        onDone={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByText('Import 1 selected'));
    await waitFor(() => expect(screen.getByText('Imported')).toBeInTheDocument());

    // Parent refetch: same data, brand-new array reference.
    view.rerender(
      <IconBatchImportDialog
        open
        onClose={vi.fn()}
        teams={[team(1, 'Ext', 'https://cdn.example.com/a.png')]}
        importFn={importFn}
        onDone={vi.fn()}
      />,
    );
    expect(screen.getByText('Imported')).toBeInTheDocument();

    // Close + reopen starts from a fresh checklist again.
    view.rerender(
      <IconBatchImportDialog
        open={false}
        onClose={vi.fn()}
        teams={[team(1, 'Ext', 'https://cdn.example.com/a.png')]}
        importFn={importFn}
        onDone={vi.fn()}
      />,
    );
    view.rerender(
      <IconBatchImportDialog
        open
        onClose={vi.fn()}
        teams={[team(1, 'Ext', 'https://cdn.example.com/a.png')]}
        importFn={importFn}
        onDone={vi.fn()}
      />,
    );
    expect(screen.queryByText('Imported')).not.toBeInTheDocument();
    expect(screen.getByText('Import 1 selected')).toBeInTheDocument();
  });

  it('shows the empty state when nothing is eligible', () => {
    renderWithI18n(
      <IconBatchImportDialog
        open
        onClose={vi.fn()}
        teams={[team(2, 'Hosted', '/media/icons/y.webp')]}
        importFn={vi.fn()}
        onDone={vi.fn()}
      />,
    );
    expect(screen.getByText('No teams with an external logo URL.')).toBeInTheDocument();
  });
});

describe('IconLibrarySection', () => {
  it('delete confirms with the usage count and toasts the cleared total', async () => {
    mocked.getMyIconUsage.mockResolvedValue({ teams: 3 });
    mocked.deleteMyIcon.mockResolvedValue({ ok: true, teams_cleared: 3 });
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    const onTeamsChanged = vi.fn();
    renderWithI18n(
      <IconLibrarySection scope="personal" teams={[]} onTeamsChanged={onTeamsChanged} />,
    );
    await waitFor(() => expect(screen.getByText('Lions')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Delete'));
    await waitFor(() => expect(mocked.deleteMyIcon).toHaveBeenCalledWith(2));
    expect(confirmSpy.mock.calls[0]![0]).toContain('3 team');
    await waitFor(() => expect(onTeamsChanged).toHaveBeenCalled());
    confirmSpy.mockRestore();
  });

  it('renames inline via the scoped endpoint', async () => {
    mocked.renameMyIcon.mockResolvedValue(icon(2, 'Panthers'));
    renderWithI18n(<IconLibrarySection scope="personal" teams={[]} onTeamsChanged={vi.fn()} />);
    await waitFor(() => expect(screen.getByText('Lions')).toBeInTheDocument());
    fireEvent.click(screen.getByText('Rename'));
    const input = screen.getByTestId('icon-rename-2');
    fireEvent.change(input, { target: { value: 'Panthers' } });
    fireEvent.click(screen.getByText('Save'));
    await waitFor(() => expect(mocked.renameMyIcon).toHaveBeenCalledWith(2, 'Panthers'));
  });

  it('global scope manages the global list with the admin endpoints', async () => {
    mocked.adminGetIconUsage.mockResolvedValue({ teams: 0 });
    mocked.adminDeleteIcon.mockResolvedValue({ ok: true, teams_cleared: 0 });
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    renderWithI18n(<IconLibrarySection scope="global" teams={[]} onTeamsChanged={vi.fn()} />);
    await waitFor(() => expect(screen.getByText('League')).toBeInTheDocument());
    expect(screen.queryByText('Lions')).not.toBeInTheDocument();
    fireEvent.click(screen.getByText('Delete'));
    await waitFor(() => expect(mocked.adminDeleteIcon).toHaveBeenCalledWith(1));
    confirmSpy.mockRestore();
  });
});

describe('SwatchBox', () => {
  it('falls back to the initial when the image errors', () => {
    render(<SwatchBox name="Lions" icon="/media/icons/gone.webp" />);
    const img = document.querySelector('img')!;
    fireEvent.error(img);
    expect(document.querySelector('img')).toBeNull();
    expect(screen.getByText('L')).toBeInTheDocument();
  });
});
