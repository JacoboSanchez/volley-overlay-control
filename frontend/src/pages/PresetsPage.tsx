import { useCallback, useEffect, useState } from 'react';
import * as api from '../api/client';
import { useAuth } from '../auth/AuthContext';
import EmptyState from '../components/EmptyState';
import { useToast } from '../components/Toast';
import { useConfirm } from '../components/ConfirmProvider';
import { useI18n } from '../i18n';
import JsonImportExport from './JsonImportExport';

export default function PresetsPage() {
  const { ctx } = useAuth();
  const isAdmin = ctx?.user?.role === 'admin';
  const { t } = useI18n();
  const { toast } = useToast();
  const confirm = useConfirm();
  const [items, setItems] = useState<api.PresetSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      const res = await api.listPresets();
      setItems(res.items);
    } catch {
      setError(t('acc.presets.errorLoad'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  async function onDelete(p: api.PresetSummary) {
    if (p.source !== 'user') return;
    const ok = await confirm({
      title: t('acc.presets.confirmDeleteTitle'),
      message: t('acc.presets.confirmDeleteMsg', { name: p.name }),
      confirmLabel: t('acc.common.delete'),
      danger: true,
    });
    if (!ok) return;
    try {
      await api.deletePreset(p.slug);
      await load();
      toast(t('acc.presets.toastDeleted', { name: p.name }));
    } catch (err) {
      toast(err instanceof api.ApiError ? err.detail : t('acc.presets.errorDelete'), 'error');
    }
  }

  return (
    <div>
      <h2>{t('acc.nav.presets')}</h2>
      <p className="acc-muted">{t('acc.presets.intro')}</p>
      {error && <div className="acc-error">{error}</div>}
      {loading ? (
        <p className="acc-muted">{t('acc.common.loading')}</p>
      ) : items.length === 0 ? (
        <EmptyState>{t('acc.presets.empty')}</EmptyState>
      ) : (
        <table className="acc-table">
          <thead><tr>
            <th scope="col">{t('acc.presets.colName')}</th><th scope="col">{t('acc.presets.colScope')}</th>
            <th scope="col">{t('acc.presets.colCovers')}</th><th scope="col"></th>
          </tr></thead>
          <tbody>
            {items.map((p) => (
              <tr key={`${p.source}:${p.slug}`}>
                <td>{p.name}</td>
                <td data-label={t('acc.presets.colScope')}><span className="acc-pill">{p.source}</span></td>
                <td className="acc-muted" data-label={t('acc.presets.colCovers')}>{p.categories.join(', ')}</td>
                <td>
                  {p.source === 'user' ? (
                    <button className="acc-btn danger" onClick={() => onDelete(p)}>{t('acc.common.delete')}</button>
                  ) : (
                    <span className="acc-muted">—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {isAdmin && <AdminGlobalPresets onChange={load} />}
    </div>
  );
}

function AdminGlobalPresets({ onChange }: { onChange: () => void }) {
  const { t } = useI18n();
  const { toast } = useToast();
  const confirm = useConfirm();
  const [globals, setGlobals] = useState<api.PresetSummary[]>([]);

  const load = useCallback(async () => {
    try {
      const res = await api.adminListGlobalPresets();
      setGlobals(res.items);
    } catch (err) {
      // Surface the failure — a swallowed rejection here rendered the
      // section as silently empty.
      toast(err instanceof api.ApiError ? err.detail : t('acc.presets.errorLoad'), 'error');
    }
  }, [toast, t]);

  useEffect(() => {
    void load();
  }, [load]);

  const refresh = useCallback(async () => {
    await load();
    onChange();
  }, [load, onChange]);

  async function toggle(p: api.PresetSummary) {
    try {
      await api.adminSetPresetActive(p.slug, !p.is_active);
      await refresh();
      toast(p.is_active
        ? t('acc.presets.toastDeactivated', { name: p.name })
        : t('acc.presets.toastActivated', { name: p.name }));
    } catch (err) {
      toast(err instanceof api.ApiError ? err.detail : t('acc.presets.errorUpdate'), 'error');
    }
  }
  async function del(p: api.PresetSummary) {
    const ok = await confirm({
      title: t('acc.presets.adminConfirmDeleteTitle'),
      message: t('acc.presets.adminConfirmDeleteMsg', { name: p.name }),
      confirmLabel: t('acc.common.delete'),
      danger: true,
    });
    if (!ok) return;
    try {
      await api.adminDeleteGlobalPreset(p.slug);
      await refresh();
      toast(t('acc.presets.toastDeleted', { name: p.name }));
    } catch (err) {
      toast(err instanceof api.ApiError ? err.detail : t('acc.presets.errorDelete'), 'error');
    }
  }

  return (
    <div className="acc-section">
      <h3>{t('acc.presets.adminTitle')}</h3>
      <p className="acc-muted">{t('acc.presets.adminDesc')}</p>
      {globals.length === 0 ? (
        <EmptyState>{t('acc.presets.adminEmpty')}</EmptyState>
      ) : (
        <table className="acc-table">
          <thead><tr>
            <th scope="col">{t('acc.presets.colName')}</th><th scope="col">{t('acc.presets.colActive')}</th>
            <th scope="col">{t('acc.presets.colCovers')}</th><th scope="col"></th>
          </tr></thead>
          <tbody>
            {globals.map((p) => (
              <tr key={p.slug}>
                <td>{p.name}</td>
                <td data-label={t('acc.presets.colActive')}>
                  <span className="acc-pill" style={{ background: p.is_active ? '#1e4031' : '#3a2b1d' }}>
                    {p.is_active ? t('acc.presets.active') : t('acc.presets.inactive')}
                  </span>
                </td>
                <td className="acc-muted" data-label={t('acc.presets.colCovers')}>{p.categories.join(', ')}</td>
                <td style={{ whiteSpace: 'nowrap' }}>
                  <button className="acc-btn ghost" onClick={() => toggle(p)}>
                    {p.is_active ? t('acc.presets.deactivate') : t('acc.presets.activate')}
                  </button>{' '}
                  <button className="acc-btn danger" onClick={() => del(p)}>{t('acc.common.delete')}</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <JsonImportExport
        label={t('acc.presets.jsonLabel')}
        exportFn={api.adminExportPresets}
        importFn={api.adminImportPresets}
        onImported={refresh}
      />
    </div>
  );
}
