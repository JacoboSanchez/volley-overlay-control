import { FormEvent, useCallback, useEffect, useRef, useState } from 'react';
import * as api from '../api/client';
import { useAuth } from '../auth/AuthContext';
import EmptyState from '../components/EmptyState';
import { useToast } from '../components/Toast';
import { useConfirm } from '../components/ConfirmProvider';
import { useI18n } from '../i18n';
import JsonImportExport from './JsonImportExport';

function useSelection() {
  const [sel, setSel] = useState<Set<number>>(new Set());
  const toggle = useCallback((id: number) => {
    setSel((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }, []);
  const clear = useCallback(() => setSel(new Set()), []);
  const replace = useCallback((ids: number[]) => setSel(new Set(ids)), []);
  return { sel, toggle, clear, replace };
}

/** Header checkbox that selects all / none of *ids*, with an indeterminate
 *  state when only some are selected. */
function SelectAll({
  ids, selected, onSelectAll, onClear,
}: {
  ids: number[];
  selected: Set<number>;
  onSelectAll: (ids: number[]) => void;
  onClear: () => void;
}) {
  const { t } = useI18n();
  const ref = useRef<HTMLInputElement>(null);
  const inList = ids.filter((id) => selected.has(id)).length;
  const all = ids.length > 0 && inList === ids.length;
  useEffect(() => {
    if (ref.current) ref.current.indeterminate = inList > 0 && !all;
  }, [inList, all]);
  return (
    <input
      ref={ref}
      type="checkbox"
      aria-label={all ? t('acc.common.deselectAll') : t('acc.common.selectAll')}
      checked={all}
      disabled={ids.length === 0}
      onChange={() => (all ? onClear() : onSelectAll(ids))}
    />
  );
}

export default function TeamsPage() {
  const { ctx } = useAuth();
  const isAdmin = ctx?.user?.role === 'admin';
  const { t } = useI18n();
  const { toast } = useToast();
  const confirm = useConfirm();
  const [mine, setMine] = useState<api.TeamOut[]>([]);
  const [catalog, setCatalog] = useState<api.TeamOut[]>([]);
  const [groups, setGroups] = useState<api.TeamGroupOut[]>([]);
  const [editing, setEditing] = useState<number | null>(null);
  const [loadError, setLoadError] = useState('');
  const [loaded, setLoaded] = useState(false);

  const mineSel = useSelection();
  const catSel = useSelection();

  const load = useCallback(async () => {
    try {
      const [m, c, g] = await Promise.all([
        api.getMyTeams(),
        api.getTeamCatalog(),
        api.getTeamGroups(),
      ]);
      setMine(m);
      setCatalog(c);
      setGroups(g);
    } catch {
      setLoadError(t('acc.teams.errorLoad'));
    } finally {
      setLoaded(true);
    }
  }, [t]);

  useEffect(() => {
    void load();
  }, [load]);

  const reload = useCallback(async () => {
    mineSel.clear();
    catSel.clear();
    setEditing(null);
    await load();
  }, [load, mineSel, catSel]);

  const mineIds = new Set(mine.map((team) => team.id));
  // Catalog teams not yet in the user's list (matched by id, so a custom team
  // sharing a catalog team's name never masks the real catalog entry).
  const addable = catalog.filter((team) => !mineIds.has(team.id));

  async function removeSelectedMine() {
    if (mineSel.sel.size === 0) return;
    const ids = [...mineSel.sel];
    // Removing an owned custom team deletes it for good — make that explicit.
    const customCount = mine.filter((team) => ids.includes(team.id) && !team.is_global).length;
    if (customCount > 0) {
      const ok = await confirm({
        title: t('acc.teams.confirmRemoveTitle'),
        message:
          customCount === ids.length
            ? t('acc.teams.confirmRemoveAll', { n: customCount })
            : t('acc.teams.confirmRemoveSome', { n: customCount }),
        confirmLabel: t('acc.teams.removeLabel'),
        danger: true,
      });
      if (!ok) return;
    }
    try {
      const { removed } = await api.removeTeamsFromMine(ids);
      await reload();
      toast(t('acc.teams.toastRemoved', { n: removed }));
    } catch (err) {
      toast(err instanceof api.ApiError ? err.detail : t('acc.teams.errorRemove'), 'error');
    }
  }
  async function addSelectedCatalog() {
    if (catSel.sel.size === 0) return;
    try {
      const { added } = await api.addTeamsToMine([...catSel.sel]);
      await reload();
      toast(t('acc.teams.toastAdded', { n: added }));
    } catch (err) {
      toast(err instanceof api.ApiError ? err.detail : t('acc.teams.errorAdd'), 'error');
    }
  }
  async function copyGroup(id: number, name: string) {
    try {
      const { added } = await api.copyGroupToMine(id);
      await reload();
      toast(t('acc.teams.toastCopied', { name, n: added }));
    } catch (err) {
      toast(err instanceof api.ApiError ? err.detail : t('acc.teams.errorCopy'), 'error');
    }
  }

  return (
    <div>
      <h2>{t('acc.nav.teams')}</h2>
      {loadError && <div className="acc-error">{loadError}</div>}
      <p className="acc-muted">{t('acc.teams.intro')}</p>

      <h3 className="acc-subhead">{t('acc.teams.myTeams')}</h3>
      {mine.length === 0 ? (
        loaded && <EmptyState>{t('acc.teams.emptyMine')}</EmptyState>
      ) : (
        <>
          <div className="acc-row" style={{ marginBottom: 8, alignItems: 'center' }}>
            <span className="acc-muted" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <SelectAll ids={mine.map((team) => team.id)} selected={mineSel.sel}
                onSelectAll={mineSel.replace} onClear={mineSel.clear} />
              {t('acc.common.selectAll')}
            </span>
            <button className="acc-btn danger" disabled={mineSel.sel.size === 0}
              onClick={removeSelectedMine}>
              {t('acc.teams.removeSelected', { n: mineSel.sel.size })}
            </button>
          </div>
          <table className="acc-table acc-checklist">
            <thead><tr>
              <th scope="col"></th><th scope="col">{t('acc.teams.colTeam')}</th><th scope="col"></th>
            </tr></thead>
            <tbody>
              {mine.map((team) => (
                <MyTeamRow
                  key={team.id} t={team}
                  selected={mineSel.sel.has(team.id)} onToggle={() => mineSel.toggle(team.id)}
                  editing={editing === team.id}
                  onEdit={() => setEditing(editing === team.id ? null : team.id)}
                  onChanged={reload}
                />
              ))}
            </tbody>
          </table>
        </>
      )}

      <CustomTeamForm onCreated={reload} />

      {groups.length > 0 && (
        <>
          <h3 className="acc-subhead">{t('acc.teams.groups')}</h3>
          {groups.map((g) => (
            <div key={g.id} style={{ marginBottom: 10 }}>
              <button className="acc-btn secondary" onClick={() => copyGroup(g.id, g.name)}>
                {t('acc.teams.copyGroup', { name: g.name, n: g.teams.length })}
              </button>
            </div>
          ))}
        </>
      )}

      <h3 className="acc-subhead">{t('acc.teams.catalog')}</h3>
      {addable.length === 0 ? (
        loaded && (
          <EmptyState>
            {catalog.length === 0 ? t('acc.teams.emptyCatalogNone') : t('acc.teams.emptyCatalog')}
          </EmptyState>
        )
      ) : (
        <>
          <div className="acc-row" style={{ marginBottom: 8, alignItems: 'center' }}>
            <span className="acc-muted" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <SelectAll ids={addable.map((team) => team.id)} selected={catSel.sel}
                onSelectAll={catSel.replace} onClear={catSel.clear} />
              {t('acc.common.selectAll')}
            </span>
            <button className="acc-btn" disabled={catSel.sel.size === 0} onClick={addSelectedCatalog}>
              {t('acc.teams.addSelected', { n: catSel.sel.size })}
            </button>
          </div>
          <table className="acc-table acc-checklist">
            <thead><tr><th scope="col"></th><th scope="col">{t('acc.teams.colTeam')}</th></tr></thead>
            <tbody>
              {addable.map((team) => (
                <tr key={team.id}>
                  <td>
                    <input type="checkbox" aria-label={t('acc.teams.selectTeam', { name: team.name })}
                      checked={catSel.sel.has(team.id)} onChange={() => catSel.toggle(team.id)} />
                  </td>
                  <td><TeamSwatch t={team} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}

      {isAdmin && <AdminCatalog catalog={catalog} onChange={load} />}
    </div>
  );
}

function MyTeamRow({
  t: team, selected, onToggle, editing, onEdit, onChanged,
}: {
  t: api.TeamOut;
  selected: boolean;
  onToggle: () => void;
  editing: boolean;
  onEdit: () => void;
  onChanged: () => void;
}) {
  const { t } = useI18n();
  return (
    <>
      <tr>
        <td>
          <input type="checkbox" aria-label={t('acc.teams.selectTeam', { name: team.name })}
            checked={selected} onChange={onToggle} />
        </td>
        <td>
          <TeamSwatch t={team} />
          {!team.is_global && <span className="acc-pill" style={{ marginLeft: 8 }}>{t('acc.teams.custom')}</span>}
        </td>
        <td style={{ whiteSpace: 'nowrap' }}>
          {!team.is_global && (
            <button className="acc-btn ghost" onClick={onEdit}>
              {editing ? t('acc.common.close') : t('acc.common.edit')}
            </button>
          )}
        </td>
      </tr>
      {editing && !team.is_global && (
        <tr>
          <td colSpan={3}><CustomTeamEditor t={team} onSaved={onChanged} /></td>
        </tr>
      )}
    </>
  );
}

function CustomTeamForm({ onCreated }: { onCreated: () => void }) {
  const { t } = useI18n();
  const { toast } = useToast();
  const [name, setName] = useState('');
  const [icon, setIcon] = useState('');
  const [color, setColor] = useState('#1565c0');
  const [textColor, setTextColor] = useState('#ffffff');
  const [error, setError] = useState('');

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    setError('');
    try {
      const created = await api.createMyTeam({ name: name.trim(), icon: icon.trim() || null, color, text_color: textColor });
      setName('');
      setIcon('');
      onCreated();
      toast(t('acc.teams.toastCreated', { name: created.name }));
    } catch (err) {
      setError(err instanceof api.ApiError ? err.detail : t('acc.teams.errorCreate'));
    }
  }

  return (
    <div className="acc-section">
      <h3>{t('acc.teams.customTitle')}</h3>
      <p className="acc-muted">{t('acc.teams.customDesc')}</p>
      <form className="acc-form" onSubmit={onCreate}>
        <label className="acc-field">
          <span>{t('acc.teams.fieldName')}</span>
          <input className="acc-input" value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="acc-field">
          <span>{t('acc.teams.fieldLogo')}</span>
          <input className="acc-input" value={icon} placeholder={t('acc.teams.logoPlaceholder')}
            onChange={(e) => setIcon(e.target.value)} />
        </label>
        <label className="acc-field" style={{ flex: '0 0 auto' }}>
          <span>{t('acc.teams.fieldColour')}</span>
          <input type="color" className="acc-color" value={color}
            onChange={(e) => setColor(e.target.value)} />
        </label>
        <label className="acc-field" style={{ flex: '0 0 auto' }}>
          <span>{t('acc.teams.fieldTextColour')}</span>
          <input type="color" className="acc-color" value={textColor}
            onChange={(e) => setTextColor(e.target.value)} />
        </label>
        <div className="acc-form-actions">
          <span className="acc-form-spacer" aria-hidden="true">&nbsp;</span>
          <button className="acc-btn" type="submit" disabled={!name.trim()}>{t('acc.teams.customAdd')}</button>
        </div>
      </form>
      {error && <div className="acc-error">{error}</div>}
    </div>
  );
}

function CustomTeamEditor({ t: team, onSaved }: { t: api.TeamOut; onSaved: () => void }) {
  const { t } = useI18n();
  const { toast } = useToast();
  const [name, setName] = useState(team.name);
  const [icon, setIcon] = useState(team.icon || '');
  const [color, setColor] = useState(hex(team.color, '#1565c0'));
  const [textColor, setTextColor] = useState(hex(team.text_color, '#ffffff'));
  const [saved, setSaved] = useState(false);

  async function save() {
    try {
      await api.updateMyTeam(team.id, {
        name: name.trim() || undefined,
        icon: icon.trim() || null,
        color,
        text_color: textColor,
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 1200);
      onSaved();
      toast(t('acc.teams.toastSaved'));
    } catch (err) {
      toast(err instanceof api.ApiError ? err.detail : t('acc.teams.errorSave'), 'error');
    }
  }

  return (
    <div style={{ background: '#14171d', borderRadius: 10, padding: 14, margin: '6px 0' }}>
      <div className="acc-row" style={{ marginBottom: 8 }}>
        <label className="acc-field" style={{ marginBottom: 0 }}>
          <span>{t('acc.teams.fieldName')}</span>
          <input className="acc-input" value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="acc-field" style={{ marginBottom: 0, minWidth: 200 }}>
          <span>{t('acc.teams.fieldLogoShort')}</span>
          <input className="acc-input" value={icon} placeholder={t('acc.teams.logoPlaceholder')}
            onChange={(e) => setIcon(e.target.value)} />
        </label>
        <label className="acc-field" style={{ marginBottom: 0 }}>
          <span>{t('acc.teams.fieldColour')}</span>
          <input type="color" className="acc-color sm" value={color}
            onChange={(e) => setColor(e.target.value)} />
        </label>
        <label className="acc-field" style={{ marginBottom: 0 }}>
          <span>{t('acc.teams.fieldText')}</span>
          <input type="color" className="acc-color sm" value={textColor}
            onChange={(e) => setTextColor(e.target.value)} />
        </label>
      </div>
      <button className="acc-btn" onClick={save}>{saved ? t('acc.common.saved') : t('acc.common.save')}</button>
    </div>
  );
}

function TeamSwatch({ t }: { t: api.TeamOut }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: 10 }}>
      <span
        style={{
          width: 26, height: 26, borderRadius: 5, flex: '0 0 auto',
          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
          background: t.color || '#444', color: t.text_color || '#fff',
          border: '1px solid #333', overflow: 'hidden', fontSize: 11, fontWeight: 700,
        }}
        title={`bg ${t.color || '—'} / text ${t.text_color || '—'}`}
      >
        {t.icon ? (
          <img src={t.icon} alt="" style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
        ) : (
          (t.name[0] || '?').toUpperCase()
        )}
      </span>
      {t.name}
    </span>
  );
}

function hex(value: string | null | undefined, fallback: string): string {
  return value && /^#[0-9a-fA-F]{6}$/.test(value) ? value : fallback;
}

function AdminCatalog({ catalog, onChange }: { catalog: api.TeamOut[]; onChange: () => void }) {
  const { t } = useI18n();
  const { toast } = useToast();
  const [name, setName] = useState('');
  const [icon, setIcon] = useState('');
  const [color, setColor] = useState('#1565c0');
  const [textColor, setTextColor] = useState('#ffffff');
  const [error, setError] = useState('');

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    setError('');
    try {
      await api.adminCreateTeam({ name: name.trim(), icon: icon.trim() || null, color, text_color: textColor });
      const created = name.trim();
      setName('');
      setIcon('');
      await onChange();
      toast(t('acc.teams.adminToastAdded', { name: created }));
    } catch (err) {
      setError(err instanceof api.ApiError ? err.detail : t('acc.teams.errorCreate'));
    }
  }

  return (
    <div className="acc-section">
      <h3>{t('acc.teams.adminTitle')}</h3>
      <p className="acc-muted">{t('acc.teams.adminDesc')}</p>

      <form className="acc-row" onSubmit={onCreate}>
        <label className="acc-field" style={{ marginBottom: 0 }}>
          <span>{t('acc.teams.fieldName')}</span>
          <input className="acc-input" value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label className="acc-field" style={{ marginBottom: 0, minWidth: 220 }}>
          <span>{t('acc.teams.fieldLogoShort')}</span>
          <input className="acc-input" value={icon} placeholder={t('acc.teams.logoPlaceholder')}
            onChange={(e) => setIcon(e.target.value)} />
        </label>
        <label className="acc-field" style={{ marginBottom: 0 }}>
          <span>{t('acc.teams.fieldColour')}</span>
          <input type="color" className="acc-color" value={color}
            onChange={(e) => setColor(e.target.value)} />
        </label>
        <label className="acc-field" style={{ marginBottom: 0 }}>
          <span>{t('acc.teams.fieldTextColour')}</span>
          <input type="color" className="acc-color" value={textColor}
            onChange={(e) => setTextColor(e.target.value)} />
        </label>
        <button className="acc-btn" type="submit" disabled={!name.trim()}>{t('acc.teams.adminAdd')}</button>
      </form>
      {error && <div className="acc-error">{error}</div>}

      <table className="acc-table">
        <thead>
          <tr>
            <th scope="col">{t('acc.teams.colTeam')}</th><th scope="col">{t('acc.teams.colLogo')}</th>
            <th scope="col">{t('acc.teams.colColour')}</th><th scope="col">{t('acc.teams.colText')}</th>
            <th scope="col"></th>
          </tr>
        </thead>
        <tbody>
          {catalog.map((team) => (
            <AdminTeamRow key={team.id} team={team} onChange={onChange} />
          ))}
        </tbody>
      </table>

      <JsonImportExport
        label={t('acc.teams.jsonLabel')}
        exportFn={api.adminExportTeams}
        importFn={api.adminImportTeams}
        onImported={onChange}
      />
    </div>
  );
}

function AdminTeamRow({ team, onChange }: { team: api.TeamOut; onChange: () => void }) {
  const { t } = useI18n();
  const { toast } = useToast();
  const confirm = useConfirm();
  const [icon, setIcon] = useState(team.icon || '');
  const [color, setColor] = useState(hex(team.color, '#1565c0'));
  const [textColor, setTextColor] = useState(hex(team.text_color, '#ffffff'));
  const [saved, setSaved] = useState(false);

  async function save() {
    try {
      await api.adminUpdateTeam(team.id, { icon: icon.trim() || null, color, text_color: textColor });
      setSaved(true);
      setTimeout(() => setSaved(false), 1200);
      await onChange();
      toast(t('acc.teams.toastSaved'));
    } catch (err) {
      toast(err instanceof api.ApiError ? err.detail : t('acc.teams.errorSave'), 'error');
    }
  }
  async function del() {
    const ok = await confirm({
      title: t('acc.teams.adminConfirmDeleteTitle'),
      message: t('acc.teams.adminConfirmDeleteMsg', { name: team.name }),
      confirmLabel: t('acc.common.delete'),
      danger: true,
    });
    if (!ok) return;
    try {
      await api.adminDeleteTeam(team.id);
      await onChange();
      toast(t('acc.teams.adminToastDeleted', { name: team.name }));
    } catch (err) {
      toast(err instanceof api.ApiError ? err.detail : t('acc.teams.adminErrorDelete'), 'error');
    }
  }

  return (
    <tr>
      <td><TeamSwatch t={{ ...team, color, text_color: textColor, icon: icon || null }} /></td>
      <td>
        <input className="acc-input" value={icon} placeholder={t('acc.teams.logoPlaceholder')}
          onChange={(e) => setIcon(e.target.value)} style={{ minWidth: 200 }} />
      </td>
      <td>
        <input type="color" className="acc-color sm" value={color}
          onChange={(e) => setColor(e.target.value)} />
      </td>
      <td>
        <input type="color" className="acc-color sm" value={textColor}
          onChange={(e) => setTextColor(e.target.value)} />
      </td>
      <td style={{ whiteSpace: 'nowrap' }}>
        <button className="acc-btn" onClick={save}>{saved ? t('acc.common.saved') : t('acc.common.save')}</button>{' '}
        <button className="acc-btn danger" onClick={del}>{t('acc.common.delete')}</button>
      </td>
    </tr>
  );
}
