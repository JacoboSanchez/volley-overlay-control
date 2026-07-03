import { useEffect, useRef, useState } from 'react';
import * as api from '../../api/client';
import Dialog from '../Dialog';
import { useI18n } from '../../i18n';

/** Browse-and-pick dialog over the hosted icon library.
 *
 *  Two sections (global icons, the caller's own) plus an inline upload
 *  affordance so "the logo I need isn't there yet" doesn't force a trip
 *  to the library section. Selecting an icon returns its hosted URL via
 *  ``onSelect`` and closes. ``uploadScope`` decides where the inline
 *  upload lands: 'personal' everywhere, 'global' on the admin pages. */
export default function IconPickerDialog({
  open,
  onClose,
  onSelect,
  uploadScope = 'personal',
}: {
  open: boolean;
  onClose: () => void;
  onSelect: (url: string) => void;
  uploadScope?: 'personal' | 'global';
}) {
  const { t } = useI18n();
  const [library, setLibrary] = useState<api.IconLibrary | null>(null);
  const [error, setError] = useState('');
  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [uploadName, setUploadName] = useState('');
  const [busy, setBusy] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (!open) return;
    setError('');
    setPendingFile(null);
    setUploadName('');
    api
      .listIcons()
      .then(setLibrary)
      .catch((e) => setError(e instanceof api.ApiError ? e.detail : t('acc.icons.errorLoad')));
  }, [open, t]);

  function pick(icon: api.IconOut) {
    onSelect(icon.url);
    onClose();
  }

  function onFileChosen(file: File) {
    setError('');
    setPendingFile(file);
    // Prefill the icon name from the file name, minus the extension.
    setUploadName(file.name.replace(/\.[^.]+$/, ''));
  }

  async function doUpload() {
    if (!pendingFile) return;
    setError('');
    setBusy(true);
    try {
      const uploaded = uploadScope === 'global'
        ? await api.adminUploadIcon(uploadName.trim(), pendingFile)
        : await api.uploadMyIcon(uploadName.trim(), pendingFile);
      pick(uploaded);
    } catch (e) {
      setError(e instanceof api.ApiError ? e.detail : t('acc.icons.errorUpload'));
    } finally {
      setBusy(false);
    }
  }

  const quotaFull =
    uploadScope === 'personal' &&
    library != null &&
    library.quota.used >= library.quota.limit;

  function renderSection(title: string, icons: api.IconOut[]) {
    return (
      <div className="acc-icon-section">
        <h4 className="acc-muted">{title}</h4>
        {icons.length === 0 ? (
          <p className="acc-muted acc-icon-empty">{t('acc.icons.empty')}</p>
        ) : (
          <div className="acc-icon-grid">
            {icons.map((icon) => (
              <button
                key={icon.id}
                type="button"
                className="acc-icon-chip"
                onClick={() => pick(icon)}
                title={`${icon.width}×${icon.height}`}
              >
                <img src={icon.url} alt="" loading="lazy" />
                <span>{icon.name}</span>
              </button>
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <Dialog open={open} onClose={onClose} ariaLabel={t('acc.icons.pickerTitle')}>
      <div className="acc-icon-picker">
        <h3 style={{ marginTop: 0 }}>{t('acc.icons.pickerTitle')}</h3>
        {error && <div className="acc-error">{error}</div>}
        {renderSection(t('acc.icons.globalSection'), library?.globals ?? [])}
        {renderSection(
          uploadScope === 'personal'
            ? t('acc.icons.mineSectionQuota', {
                used: library?.quota.used ?? 0,
                limit: library?.quota.limit ?? 0,
              })
            : t('acc.icons.mineSection'),
          library?.mine ?? [],
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
                data-testid="icon-upload-name"
              />
              <button
                className="acc-btn"
                onClick={doUpload}
                disabled={busy || !uploadName.trim()}
              >
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
            data-testid="icon-file-input"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) onFileChosen(file);
              e.target.value = '';
            }}
          />
          <button className="acc-btn secondary" onClick={onClose} style={{ marginLeft: 'auto' }}>
            {t('acc.common.close')}
          </button>
        </div>
      </div>
    </Dialog>
  );
}
