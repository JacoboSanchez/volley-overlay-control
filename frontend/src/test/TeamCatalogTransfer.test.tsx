import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import TeamCatalogTransfer from '../components/teams/TeamCatalogTransfer';
import { renderWithI18n } from './helpers';

vi.mock('../api/admin', () => ({
  adminExportTeamCatalog: vi.fn(),
  adminPreviewTeamCatalogImport: vi.fn(),
  adminImportTeamCatalog: vi.fn(),
}));
vi.mock('../api/http', () => ({
  ApiError: class ApiError extends Error {
    detail = '';
  },
}));

import * as api from '../api/admin';

const catalog: api.TeamCatalogTransferPackage = {
  format: 'volley-overlay-team-catalog',
  version: 1,
  teams: [
    {
      key: 'team-1',
      name: 'Lions',
      icon: null,
      color: '#123456',
      text_color: '#ffffff',
      logo_asset: null,
    },
    {
      key: 'team-2',
      name: 'Tigers',
      icon: null,
      color: '#654321',
      text_color: '#ffffff',
      logo_asset: null,
    },
  ],
  logos: {},
};

function jsonFile(value: unknown): File {
  const file = new File([JSON.stringify(value)], 'catalog.json', {
    type: 'application/json',
  });
  Object.defineProperty(file, 'text', {
    value: vi.fn().mockResolvedValue(JSON.stringify(value)),
  });
  return file;
}

async function gzipFile(value: unknown): Promise<File> {
  const compression = new CompressionStream('gzip');
  const compressed = new Response(compression.readable).arrayBuffer();
  const writer = compression.writable.getWriter();
  await writer.write(new TextEncoder().encode(JSON.stringify(value)));
  await writer.close();
  const bytes = await compressed;
  const file = new File([bytes], 'catalog.json.gz', { type: 'application/gzip' });
  Object.defineProperty(file, 'arrayBuffer', {
    value: vi.fn().mockResolvedValue(bytes),
  });
  return file;
}

describe('TeamCatalogTransfer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.adminImportTeamCatalog).mockResolvedValue({
      imported: 2,
      created: 0,
      replaced: 2,
    });
  });

  it('passes the include-logo option to export', async () => {
    vi.mocked(api.adminExportTeamCatalog).mockResolvedValue(catalog);
    const createObjectURL = vi.fn().mockReturnValue('blob:catalog');
    const revokeObjectURL = vi.fn();
    const downloads: string[] = [];
    Object.defineProperty(URL, 'createObjectURL', { value: createObjectURL, configurable: true });
    Object.defineProperty(URL, 'revokeObjectURL', { value: revokeObjectURL, configurable: true });
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
      this: HTMLAnchorElement,
    ) {
      downloads.push(this.download);
    });

    renderWithI18n(<TeamCatalogTransfer existingNames={[]} onImported={vi.fn()} />);
    fireEvent.click(screen.getByRole('button', { name: 'Export catalog' }));
    await waitFor(() => expect(api.adminExportTeamCatalog).toHaveBeenCalledWith(true));
    await waitFor(() => expect(createObjectURL).toHaveBeenCalled());
    expect(createObjectURL.mock.calls[0]?.[0]).toMatchObject({ type: 'application/gzip' });
    expect(downloads[0]).toBe('team-catalog.json.gz');

    fireEvent.click(screen.getByRole('checkbox', { name: 'Include hosted logos in the file' }));
    fireEvent.click(screen.getByRole('button', { name: 'Export catalog' }));
    await waitFor(() => expect(api.adminExportTeamCatalog).toHaveBeenLastCalledWith(false));
  });

  it('imports immediately when the preview has no conflicts', async () => {
    vi.mocked(api.adminPreviewTeamCatalogImport).mockResolvedValue({
      teams: 2,
      conflicts: [],
    });
    const onImported = vi.fn();
    renderWithI18n(<TeamCatalogTransfer existingNames={[]} onImported={onImported} />);

    fireEvent.change(screen.getByTestId('team-catalog-file-input'), {
      target: { files: [jsonFile(catalog)] },
    });
    await waitFor(() => expect(api.adminImportTeamCatalog).toHaveBeenCalledWith(catalog, []));
    await waitFor(() => expect(onImported).toHaveBeenCalled());
  });

  it('imports a compressed catalog file', async () => {
    vi.mocked(api.adminPreviewTeamCatalogImport).mockResolvedValue({
      teams: 2,
      conflicts: [],
    });
    renderWithI18n(<TeamCatalogTransfer existingNames={[]} onImported={vi.fn()} />);

    fireEvent.change(screen.getByTestId('team-catalog-file-input'), {
      target: { files: [await gzipFile(catalog)] },
    });

    await waitFor(() => expect(api.adminPreviewTeamCatalogImport).toHaveBeenCalledWith(catalog));
    await waitFor(() => expect(api.adminImportTeamCatalog).toHaveBeenCalledWith(catalog, []));
  });

  it('rejects an oversized file before reading or uploading it', async () => {
    const file = jsonFile(catalog);
    Object.defineProperty(file, 'size', { value: 9 * 1024 * 1024 });
    renderWithI18n(<TeamCatalogTransfer existingNames={[]} onImported={vi.fn()} />);

    fireEvent.change(screen.getByTestId('team-catalog-file-input'), {
      target: { files: [file] },
    });

    expect(await screen.findByText('The selected catalog file is too large.')).toBeInTheDocument();
    expect(file.text).not.toHaveBeenCalled();
    expect(api.adminPreviewTeamCatalogImport).not.toHaveBeenCalled();
  });

  it('asks per conflict and supports rename followed by replace all', async () => {
    vi.mocked(api.adminPreviewTeamCatalogImport).mockResolvedValue({
      teams: 2,
      conflicts: [
        {
          key: 'team-1',
          incoming_name: 'Lions',
          existing_team_id: 1,
          existing_name: 'Lions',
          kind: 'catalog',
        },
        {
          key: 'team-2',
          incoming_name: 'Tigers',
          existing_team_id: 2,
          existing_name: 'Tigers',
          kind: 'catalog',
        },
      ],
    });
    renderWithI18n(
      <TeamCatalogTransfer existingNames={['Lions', 'Tigers']} onImported={vi.fn()} />,
    );
    fireEvent.change(screen.getByTestId('team-catalog-file-input'), {
      target: { files: [jsonFile(catalog)] },
    });

    await waitFor(() => expect(screen.getByText('Conflict 1 of 2')).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText('Alternative team name'), {
      target: { value: 'Imported Lions' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save with another name' }));
    expect(screen.getByText('Conflict 2 of 2')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Replace all' }));

    await waitFor(() =>
      expect(api.adminImportTeamCatalog).toHaveBeenCalledWith(catalog, [
        { key: 'team-1', action: 'rename', name: 'Imported Lions' },
        { key: 'team-2', action: 'replace', expected_team_id: 2 },
      ]),
    );
  });

  it('only offers rename for a duplicate inside the import file', async () => {
    vi.mocked(api.adminPreviewTeamCatalogImport).mockResolvedValue({
      teams: 2,
      conflicts: [
        {
          key: 'team-2',
          incoming_name: 'Lions',
          existing_team_id: null,
          existing_name: 'Lions',
          kind: 'file',
        },
      ],
    });
    renderWithI18n(<TeamCatalogTransfer existingNames={[]} onImported={vi.fn()} />);
    fireEvent.change(screen.getByTestId('team-catalog-file-input'), {
      target: { files: [jsonFile(catalog)] },
    });

    await waitFor(() => expect(screen.getByText(/appears more than once/)).toBeInTheDocument());
    expect(screen.queryByRole('button', { name: 'Replace' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Replace all' })).not.toBeInTheDocument();
  });
});
