import { useCallback, useEffect, useRef, useState } from 'react';
import * as api from '../../api/client';
import { useConfirm } from '../ConfirmProvider';
import { useI18n } from '../../i18n';
import { useToast } from '../Toast';
import IconBatchImportDialog from './IconBatchImportDialog';
import { prefillIconName } from './iconName';

/** Management panel for one scope of the hosted icon library.
 *
 *  ``scope='personal'`` (the /teams page) manages the caller's icons and
 *  shows the quota; ``scope='global'`` (the admin catalog page) manages
 *  the shared ones. Rename is inline; delete pre-counts the referencing
 *  teams so the confirm dialog says what it will clear. The batch-import
 *  dialog converts the given *teams*' external logo URLs. */
export default function IconLibrarySection({
  scope,
  teams,
  onTeamsChanged,
}: {
  scope: 'personal' | 'global';
  teams: api.TeamOut[];
  onTeamsChanged: () => void;
}) {
  const { t } = useI18n();
  const { toast } = useToast();
  const confirm = useConfirm();
  const [library, setLibrary] = useState<api.IconLibrary | null>(null);
  const [renamingId, setRenamingId] = useState<number | null>(null);
  const [renameValue, setRenameValue] = useState('');
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [uploadName, setUploadName] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [batchOpen, setBatchOpen] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const isGlobal = scope === 'global';
  const fns = isGlobal
    ? {
        upload: api.adminUploadIcon,
        rename: api.adminRenameIcon,
        usage: api.adminGetIconUsage,
        remove: api.adminDeleteIcon,
        importTeams: api.adminImportIconsFromTeams,
      }
    : {
        upload: api.uploadMyIcon,
        rename: api.renameMyIcon,
        usage: api.getMyIconUsage,
        remove: api.deleteMyIcon,
        importTeams: api.importIconsFromMyTeams,
      };

  const refresh = useCallback(() => {
    api
      .listIcons()
      .then(setLibrary)
      .catch((e) => setError(e instanceof api.ApiError ? e.detail : t('acc.icons.errorLoad')));
  }, [t]);

  useEffect(() => {
    // Mount-load with a cancel guard; post-action refreshes reuse refresh()
    // directly (the section is still mounted there by construction).
    let cancelled = false;
    api
      .listIcons()
      .then((lib) => {
        if (!cancelled) setLibrary(lib);
      })
      .catch((e) => {
        if (!cancelled) {
          setError(e instanceof api.ApiError ? e.detail : t('acc.icons.errorLoad'));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [t]);

  const icons = isGlobal ? (library?.globals ?? []) : (library?.mine ?? []);
  const quotaFull = !isGlobal && library != null && library.quota.used >= library.quota.limit;

  async function doUpload() {
    if (!pendingFile) return;
    setError('');
    setBusy(true);
    try {
      await fns.upload(uploadName.trim(), pendingFile);
      setPendingFile(null);
      toast(t('acc.icons.toastUploaded'));
      refresh();
    } catch (e) {
      setError(e instanceof api.ApiError ? e.detail : t('acc.icons.errorUpload'));
    } finally {
      setBusy(false);
    }
  }

  async function saveRename(icon: api.IconOut) {
    if (!renameValue.trim()) return;
    setBusy(true);
    try {
      await fns.rename(icon.id, renameValue.trim());
      setRenamingId(null);
      refresh();
    } catch (e) {
      toast(e instanceof api.ApiError ? e.detail : t('acc.icons.errorRename'), 'error');
    } finally {
      setBusy(false);
    }
  }

  async function remove(icon: api.IconOut) {
    setError('');
    let teamsUsing = 0;
    try {
      teamsUsing = (await fns.usage(icon.id)).teams;
    } catch {
      /* usage is advisory — the delete itself still reports the count */
    }
    const ok = await confirm({
      title: t('acc.icons.confirmDeleteTitle'),
      message: t('acc.icons.confirmDeleteMsg', { name: icon.name, n: teamsUsing }),
      confirmLabel: t('acc.icons.delete'),
      danger: true,
    });
    if (!ok) return;
    setBusy(true);
    try {
      const res = await fns.remove(icon.id);
      toast(t('acc.icons.toastDeleted', { n: res.teams_cleared }));
      refresh();
      if (res.teams_cleared > 0) onTeamsChanged();
    } catch (e) {
      toast(e instanceof api.ApiError ? e.detail : t('acc.icons.errorDelete'), 'error');
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="acc-panel" style={{ marginTop: 18 }}>
      <div className="acc-panel-head">
        <h3>{t('acc.icons.sectionTitle')}</h3>
        {!isGlobal && library && (
          <span className="acc-muted">
            {t('acc.icons.quota', { used: library.quota.used, limit: library.quota.limit })}
          </span>
        )}
      </div>
      <p className="acc-muted">
        {t(isGlobal ? 'acc.icons.sectionHintGlobal' : 'acc.icons.sectionHint')}
      </p>
      {error && <div className="acc-error">{error}</div>}
      {icons.length === 0 ? (
        <p className="acc-muted">{t('acc.icons.empty')}</p>
      ) : (
        <div className="acc-icon-grid">
          {icons.map((icon) => (
            <div key={icon.id} className="acc-icon-chip acc-icon-chip--manage">
              <img src={icon.url} alt="" loading="lazy" />
              {renamingId === icon.id ? (
                <span className="acc-icon-rename">
                  <input
                    className="acc-input"
                    value={renameValue}
                    onChange={(e) => setRenameValue(e.target.value)}
                    data-testid={`icon-rename-${icon.id}`}
                  />
                  <button
                    className="acc-btn"
                    onClick={() => saveRename(icon)}
                    disabled={busy || !renameValue.trim()}
                  >
                    {t('acc.common.save')}
                  </button>
                  <button
                    className="acc-btn secondary"
                    onClick={() => setRenamingId(null)}
                    disabled={busy}
                  >
                    {t('acc.common.cancel')}
                  </button>
                </span>
              ) : (
                <>
                  <span className="acc-icon-chip-name" title={`${icon.width}×${icon.height}`}>
                    {icon.name}
                  </span>
                  <span className="acc-icon-chip-actions">
                    <button
                      className="acc-link"
                      onClick={() => {
                        setRenamingId(icon.id);
                        setRenameValue(icon.name);
                      }}
                    >
                      {t('acc.icons.rename')}
                    </button>
                    <button className="acc-link danger" onClick={() => remove(icon)}>
                      {t('acc.icons.delete')}
                    </button>
                  </span>
                </>
              )}
            </div>
          ))}
        </div>
      )}
      <div className="acc-btn-row" style={{ marginTop: 12 }}>
        {pendingFile ? (
          <>
            <input
              className="acc-input"
              value={uploadName}
              onChange={(e) => setUploadName(e.target.value)}
              placeholder={t('acc.icons.uploadName')}
              style={{ maxWidth: 220 }}
              data-testid="icon-section-upload-name"
            />
            <button className="acc-btn" onClick={doUpload} disabled={busy || !uploadName.trim()}>
              {busy ? t('acc.icons.uploading') : t('acc.icons.uploadBtn')}
            </button>
            <button
              className="acc-btn secondary"
              onClick={() => setPendingFile(null)}
              disabled={busy}
            >
              {t('acc.common.cancel')}
            </button>
          </>
        ) : (
          <button
            className="acc-btn secondary"
            onClick={() => fileInputRef.current?.click()}
            disabled={busy || quotaFull}
            title={quotaFull ? t('acc.icons.quotaFull') : undefined}
          >
            {t('acc.icons.upload')}
          </button>
        )}
        <input
          ref={fileInputRef}
          type="file"
          accept="image/png,image/jpeg,image/webp,image/gif"
          style={{ display: 'none' }}
          data-testid="icon-section-file-input"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) {
              setPendingFile(file);
              setUploadName(prefillIconName(file.name));
              setError('');
            }
            e.target.value = '';
          }}
        />
        <button className="acc-btn secondary" onClick={() => setBatchOpen(true)}>
          {t('acc.icons.batchBtn')}
        </button>
      </div>
      <IconBatchImportDialog
        open={batchOpen}
        onClose={() => setBatchOpen(false)}
        teams={teams}
        importFn={fns.importTeams}
        onDone={() => {
          refresh();
          onTeamsChanged();
        }}
      />
    </section>
  );
}
