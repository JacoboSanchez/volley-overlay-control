import { useRef, useState } from 'react';
import {
  adminExportTeamCatalog,
  adminImportTeamCatalog,
  adminPreviewTeamCatalogImport,
  type TeamCatalogConflict,
  type TeamCatalogConflictResolution,
  type TeamCatalogTransferPackage,
} from '../../api/admin';
import { apiErrorMessage } from '../../hooks/useAsyncAction';
import { useI18n } from '../../i18n';
import Dialog from '../Dialog';
import { useToast } from '../Toast';

interface Props {
  existingNames: string[];
  onImported: () => void | Promise<void>;
}

const MAX_CATALOG_FILE_BYTES = 8 * 1024 * 1024;

class CatalogFileTooLargeError extends Error {}

async function readStreamLimited(
  stream: ReadableStream<Uint8Array>,
  maxBytes: number,
): Promise<Uint8Array> {
  const reader = stream.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.byteLength;
    if (total > maxBytes) {
      await reader.cancel();
      throw new CatalogFileTooLargeError();
    }
    chunks.push(value);
  }
  const result = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    result.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return result;
}

async function gzipJson(value: unknown): Promise<Blob> {
  const compression = new CompressionStream('gzip');
  const compressed = readStreamLimited(compression.readable, MAX_CATALOG_FILE_BYTES);
  const writer = compression.writable.getWriter();
  await writer.write(new TextEncoder().encode(JSON.stringify(value)));
  await writer.close();
  return new Blob([new Uint8Array(await compressed).buffer], { type: 'application/gzip' });
}

async function readCatalogFile(file: File): Promise<string> {
  const gzip = file.name.toLowerCase().endsWith('.gz') || file.type === 'application/gzip';
  if (!gzip) return file.text();

  const decompression = new DecompressionStream('gzip');
  const decompressed = readStreamLimited(decompression.readable, MAX_CATALOG_FILE_BYTES);
  const writer = decompression.writable.getWriter();
  await writer.write(new Uint8Array(await file.arrayBuffer()));
  await writer.close();
  return new TextDecoder().decode(await decompressed);
}

function nextName(name: string, occupied: Set<string>): string {
  for (let suffix = 2; suffix < 1000; suffix += 1) {
    const marker = ` (${suffix})`;
    const candidate = `${name.slice(0, 120 - marker.length)}${marker}`;
    if (!occupied.has(candidate)) return candidate;
  }
  return name.slice(0, 116) + ' copy';
}

export default function TeamCatalogTransfer({ existingNames, onImported }: Props) {
  const { t } = useI18n();
  const { toast } = useToast();
  const fileRef = useRef<HTMLInputElement>(null);
  const [includeLogos, setIncludeLogos] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [catalog, setCatalog] = useState<TeamCatalogTransferPackage | null>(null);
  const [conflicts, setConflicts] = useState<TeamCatalogConflict[]>([]);
  const [conflictIndex, setConflictIndex] = useState(0);
  const [resolutions, setResolutions] = useState<TeamCatalogConflictResolution[]>([]);
  const [rename, setRename] = useState('');

  const current = conflicts[conflictIndex];

  function suggestedName(
    conflict: TeamCatalogConflict,
    decided = resolutions,
    source = catalog,
  ): string {
    const occupied = new Set(existingNames);
    source?.teams.forEach((team) => occupied.add(team.name));
    decided.forEach((resolution) => {
      if (resolution.name) occupied.add(resolution.name);
    });
    return nextName(conflict.incoming_name, occupied);
  }

  function closeConflicts() {
    setCatalog(null);
    setConflicts([]);
    setConflictIndex(0);
    setResolutions([]);
  }

  async function applyImport(
    packageToImport: TeamCatalogTransferPackage,
    decisions: TeamCatalogConflictResolution[],
  ) {
    setBusy(true);
    setError('');
    try {
      const result = await adminImportTeamCatalog(packageToImport, decisions);
      await onImported();
      closeConflicts();
      toast(
        t('acc.teams.transferImported', {
          n: result.imported,
          created: result.created,
          replaced: result.replaced,
        }),
      );
    } catch (err) {
      setError(apiErrorMessage(err, t('acc.teams.transferImportError')));
    } finally {
      setBusy(false);
    }
  }

  async function loadFile(file: File) {
    setError('');
    if (file.size > MAX_CATALOG_FILE_BYTES) {
      setError(t('acc.teams.transferFileTooLarge'));
      return;
    }
    setBusy(true);
    try {
      let parsed: TeamCatalogTransferPackage;
      try {
        parsed = JSON.parse(await readCatalogFile(file)) as TeamCatalogTransferPackage;
      } catch (err) {
        setError(
          err instanceof CatalogFileTooLargeError
            ? t('acc.teams.transferFileTooLarge')
            : t('acc.teams.transferInvalidFile'),
        );
        return;
      }
      const preview = await adminPreviewTeamCatalogImport(parsed);
      if (preview.conflicts.length === 0) {
        await applyImport(parsed, []);
        return;
      }
      setCatalog(parsed);
      setConflicts(preview.conflicts);
      setConflictIndex(0);
      setResolutions([]);
      setRename(suggestedName(preview.conflicts[0]!, [], parsed));
    } catch (err) {
      setError(apiErrorMessage(err, t('acc.teams.transferImportError')));
    } finally {
      setBusy(false);
    }
  }

  async function downloadExport() {
    setBusy(true);
    setError('');
    try {
      const exported = await adminExportTeamCatalog(includeLogos);
      const blob = await gzipJson(exported);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = 'team-catalog.json.gz';
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      toast(t('acc.teams.transferExported', { n: exported.teams.length }));
    } catch (err) {
      setError(apiErrorMessage(err, t('acc.teams.transferExportError')));
    } finally {
      setBusy(false);
    }
  }

  function resolveCurrent(action: 'replace' | 'rename') {
    if (!catalog || !current) return;
    const decision: TeamCatalogConflictResolution = {
      key: current.key,
      action,
      ...(action === 'rename' ? { name: rename.trim() } : {}),
      ...(action === 'replace' && current.existing_team_id != null
        ? { expected_team_id: current.existing_team_id }
        : {}),
    };
    const nextResolutions = [...resolutions, decision];
    if (conflictIndex === conflicts.length - 1) {
      void applyImport(catalog, nextResolutions);
      return;
    }
    const nextIndex = conflictIndex + 1;
    setResolutions(nextResolutions);
    setConflictIndex(nextIndex);
    setRename(suggestedName(conflicts[nextIndex]!, nextResolutions));
  }

  return (
    <div className="acc-team-transfer">
      <h4>{t('acc.teams.transferTitle')}</h4>
      <p className="acc-muted">{t('acc.teams.transferDesc')}</p>
      {error && <div className="acc-error">{error}</div>}
      <div className="acc-team-transfer__actions">
        <label className="acc-muted acc-team-transfer__check">
          <input
            type="checkbox"
            checked={includeLogos}
            onChange={(event) => setIncludeLogos(event.target.checked)}
          />
          {t('acc.teams.transferIncludeLogos')}
        </label>
        <button className="acc-btn secondary" disabled={busy} onClick={downloadExport}>
          {t('acc.teams.transferExport')}
        </button>
        <button className="acc-btn" disabled={busy} onClick={() => fileRef.current?.click()}>
          {t('acc.teams.transferImport')}
        </button>
        <input
          ref={fileRef}
          type="file"
          accept=".json,.gz,application/json,application/gzip"
          data-testid="team-catalog-file-input"
          hidden
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void loadFile(file);
            event.target.value = '';
          }}
        />
      </div>

      <Dialog
        open={Boolean(catalog && current)}
        onClose={() => {
          if (!busy) closeConflicts();
        }}
        ariaLabelledBy="team-catalog-conflict-title"
      >
        {current && (
          <div className="acc-team-conflict">
            <h3 id="team-catalog-conflict-title">{t('acc.teams.transferConflictTitle')}</h3>
            <p className="acc-muted">
              {t('acc.teams.transferConflictProgress', {
                current: conflictIndex + 1,
                total: conflicts.length,
              })}
            </p>
            <p>
              {t('acc.teams.transferConflictDesc', {
                incoming: current.incoming_name,
                existing: current.existing_name,
              })}
            </p>
            {current.kind === 'file' && (
              <p className="acc-info">{t('acc.teams.transferDuplicateFile')}</p>
            )}
            <label className="acc-field-label" htmlFor="team-catalog-rename">
              {t('acc.teams.transferRenameLabel')}
            </label>
            <input
              id="team-catalog-rename"
              className="acc-input"
              value={rename}
              maxLength={120}
              onChange={(event) => setRename(event.target.value)}
            />
            <div className="acc-btn-row">
              <button
                className="acc-btn"
                disabled={busy || !rename.trim()}
                onClick={() => resolveCurrent('rename')}
              >
                {t('acc.teams.transferRename')}
              </button>
              {current.kind === 'catalog' && (
                <>
                  <button
                    className="acc-btn secondary"
                    disabled={busy}
                    onClick={() => resolveCurrent('replace')}
                  >
                    {t('acc.teams.transferReplace')}
                  </button>
                  {conflicts
                    .slice(conflictIndex)
                    .every((conflict) => conflict.kind === 'catalog') && (
                    <button
                      className="acc-btn danger"
                      disabled={busy}
                      onClick={() => {
                        if (!catalog) return;
                        const replacements = conflicts.slice(conflictIndex).map((conflict) => ({
                          key: conflict.key,
                          action: 'replace' as const,
                          expected_team_id: conflict.existing_team_id as number,
                        }));
                        void applyImport(catalog, [...resolutions, ...replacements]);
                      }}
                    >
                      {t('acc.teams.transferReplaceAll')}
                    </button>
                  )}
                </>
              )}
              <button className="acc-btn ghost" disabled={busy} onClick={closeConflicts}>
                {t('acc.common.cancel')}
              </button>
            </div>
          </div>
        )}
      </Dialog>
    </div>
  );
}
