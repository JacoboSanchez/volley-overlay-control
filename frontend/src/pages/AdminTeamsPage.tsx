import { FormEvent, useCallback, useEffect, useRef, useState } from 'react';
import { Navigate } from 'react-router-dom';
import * as api from '../api/client';
import { useAuth } from '../auth/AuthContext';
import EmptyState from '../components/EmptyState';
import { useToast } from '../components/Toast';
import { useConfirm } from '../components/ConfirmProvider';
import { useI18n } from '../i18n';
import JsonImportExport from './JsonImportExport';
import TeamRowCard from '../components/teams/TeamRowCard';
import TeamListToolbar from '../components/teams/TeamListToolbar';
import BulkActionBar from '../components/teams/BulkActionBar';
import TeamCreatePanel from '../components/teams/TeamCreatePanel';
import TeamInlineEditor from '../components/teams/TeamInlineEditor';
import IconLibrarySection from '../components/icons/IconLibrarySection';
import { SwatchBox } from '../components/teams/TeamSwatch';
import { useTeamSelection } from '../components/teams/useTeamSelection';
import {
  FILTER_THRESHOLD,
  filterTeams,
  restoreFocus,
  withPinnedEdit,
} from '../components/teams/teamUtils';

/** Admin-only authoring of the global team catalog and the published groups —
 *  split off from the user's own /teams roster so an operator managing 20-30
 *  teams from a phone never wades through their personal list to get here. */
export default function AdminTeamsPage() {
  const { ctx } = useAuth();
  const { t } = useI18n();
  if (ctx && ctx.user?.role !== 'admin') return <Navigate to="/" replace />;

  return (
    <div>
      <h2>{t('acc.adminTeams.title')}</h2>
      <p className="acc-muted">{t('acc.adminTeams.intro')}</p>
      <AdminCatalog />
      <AdminGroups />
    </div>
  );
}

// ── Global catalog ────────────────────────────────────────────────────────

function AdminCatalog() {
  const { t } = useI18n();
  const { toast } = useToast();
  const confirm = useConfirm();
  const [catalog, setCatalog] = useState<api.TeamOut[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [query, setQuery] = useState('');
  const [editing, setEditing] = useState<number | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const sel = useTeamSelection();
  const selAllRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    try {
      setCatalog(await api.getTeamCatalog());
    } catch {
      toast(t('acc.adminTeams.errorLoad'), 'error');
    } finally {
      setLoaded(true);
    }
  }, [t, toast]);

  useEffect(() => {
    void load();
  }, [load]);

  const reload = useCallback(async () => {
    sel.clear();
    setEditing(null);
    await load();
  }, [load, sel]);

  // Pin the edited row so filtering never unmounts an open editor mid-edit.
  const shown = withPinnedEdit(filterTeams(catalog, query), catalog, editing);
  // Only act on the currently-visible selected rows (count matches), so a
  // selection hidden by the filter is never deleted behind the operator's back.
  const selShownIds = shown.filter((x) => sel.has(x.id)).map((x) => x.id);

  async function deleteSelected() {
    const ids = selShownIds;
    if (ids.length === 0) return;
    const ok = await confirm({
      title: t('acc.adminTeams.confirmDeleteTitle'),
      message: t('acc.adminTeams.confirmDeleteMsg', { n: ids.length }),
      confirmLabel: t('acc.common.delete'),
      danger: true,
    });
    if (!ok) return;
    // allSettled + reload-in-finally: a partial failure (e.g. a concurrent
    // delete 404) still refreshes the list to reflect what actually went, and
    // reports the real success/failure split instead of claiming total failure.
    const results = await Promise.allSettled(ids.map((id) => api.adminDeleteTeam(id)));
    await reload();
    restoreFocus(selAllRef);
    const failed = results.filter((r) => r.status === 'rejected').length;
    const ok2 = ids.length - failed;
    if (failed === 0) {
      toast(t('acc.adminTeams.toastDeleted', { n: ok2 }));
    } else {
      toast(t('acc.adminTeams.toastDeletedPartial', { ok: ok2, failed }), 'error');
    }
  }

  async function deleteOne(team: api.TeamOut) {
    const ok = await confirm({
      title: t('acc.teams.adminConfirmDeleteTitle'),
      message: t('acc.teams.adminConfirmDeleteMsg', { name: team.name }),
      confirmLabel: t('acc.common.delete'),
      danger: true,
    });
    if (!ok) return;
    try {
      await api.adminDeleteTeam(team.id);
      await reload();
      toast(t('acc.teams.adminToastDeleted', { name: team.name }));
    } catch (err) {
      toast(err instanceof api.ApiError ? err.detail : t('acc.teams.adminErrorDelete'), 'error');
    }
  }

  return (
    <div className="acc-section">
      <div className="acc-section-head">
        <h3>{t('acc.adminTeams.catalogTitle')}</h3>
        <button
          className={`acc-btn${showCreate ? ' secondary' : ''}`}
          aria-expanded={showCreate}
          onClick={() => setShowCreate((v) => !v)}
        >
          {showCreate ? t('acc.common.close') : t('acc.adminTeams.addTeam')}
        </button>
      </div>
      <p className="acc-muted">{t('acc.teams.adminDesc')}</p>

      {showCreate && (
        <div className="acc-overlay-panel">
          <TeamCreatePanel
            onCreate={(fields) => api.adminCreateTeam(fields)}
            onCreated={() => {
              void reload();
              setShowCreate(false);
            }}
            addLabel={t('acc.teams.adminAdd')}
            successMessage={(name) => t('acc.teams.adminToastAdded', { name })}
            idPrefix="admin-team"
            iconPickerScope="global"
          />
        </div>
      )}

      {catalog.length === 0 ? (
        loaded && <EmptyState>{t('acc.adminTeams.emptyCatalog')}</EmptyState>
      ) : (
        <>
          <TeamListToolbar
            inputRef={selAllRef}
            shownCount={shown.length}
            selectedShownCount={selShownIds.length}
            onSelectAll={() => sel.replace([...new Set([...sel.ids, ...shown.map((x) => x.id)])])}
            onClearSelection={() =>
              sel.replace(sel.ids.filter((id) => !shown.some((x) => x.id === id)))
            }
            query={query}
            onQuery={setQuery}
            total={catalog.length}
            showFilter={catalog.length > FILTER_THRESHOLD}
          />
          {shown.length === 0 ? (
            <EmptyState>{t('acc.teams.noMatch', { q: query.trim() })}</EmptyState>
          ) : (
            <div className="acc-tlist">
              {shown.map((team) => (
                <TeamRowCard
                  key={team.id}
                  team={team}
                  selected={sel.has(team.id)}
                  onToggleSelect={() => sel.toggle(team.id)}
                  editable
                  editing={editing === team.id}
                  onToggleEdit={() => setEditing(editing === team.id ? null : team.id)}
                >
                  <TeamInlineEditor
                    team={team}
                    onSave={(fields) => api.adminUpdateTeam(team.id, fields)}
                    onSaved={() => void load()}
                    danger={{ label: t('acc.common.delete'), onClick: () => void deleteOne(team) }}
                    iconPickerScope="global"
                  />
                </TeamRowCard>
              ))}
            </div>
          )}
          <BulkActionBar
            count={selShownIds.length}
            onClear={() => {
              sel.clear();
              restoreFocus(selAllRef);
            }}
          >
            <button className="acc-btn danger" onClick={deleteSelected}>
              {t('acc.adminTeams.deleteSelected', { n: selShownIds.length })}
            </button>
          </BulkActionBar>
        </>
      )}

      <JsonImportExport
        label={t('acc.teams.jsonLabel')}
        exportFn={api.adminExportTeams}
        importFn={api.adminImportTeams}
        onImported={() => void load()}
      />

      <IconLibrarySection scope="global" teams={catalog} onTeamsChanged={() => void load()} />
    </div>
  );
}

// ── Team groups ───────────────────────────────────────────────────────────

function AdminGroups() {
  const { t } = useI18n();
  const { toast } = useToast();
  const [groups, setGroups] = useState<api.TeamGroupOut[]>([]);
  const [catalog, setCatalog] = useState<api.TeamOut[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [g, c] = await Promise.all([api.adminListGroups(), api.getTeamCatalog()]);
      setGroups(g);
      setCatalog(c);
    } catch {
      toast(t('acc.adminTeams.errorLoad'), 'error');
    } finally {
      setLoaded(true);
    }
  }, [t, toast]);

  useEffect(() => {
    void load();
  }, [load]);

  async function create(e: FormEvent) {
    e.preventDefault();
    if (!name.trim() || busy) return;
    setBusy(true);
    try {
      const g = await api.adminCreateGroup(name.trim());
      setName('');
      await load();
      toast(t('acc.groups.toastCreated', { name: g.name }));
    } catch (err) {
      toast(err instanceof api.ApiError ? err.detail : t('acc.groups.errorCreate'), 'error');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="acc-section">
      <h3>{t('acc.groups.title')}</h3>
      <p className="acc-muted">{t('acc.groups.desc')}</p>

      <form className="acc-group-create" onSubmit={create}>
        <input
          className="acc-input"
          value={name}
          placeholder={t('acc.groups.namePlaceholder')}
          aria-label={t('acc.groups.nameLabel')}
          onChange={(e) => setName(e.target.value)}
        />
        <button className="acc-btn" type="submit" disabled={!name.trim() || busy}>
          {t('acc.groups.create')}
        </button>
      </form>

      {groups.length === 0 ? (
        loaded && <EmptyState>{t('acc.groups.empty')}</EmptyState>
      ) : (
        <div className="acc-tlist">
          {groups.map((g) => (
            <GroupCard key={g.id} group={g} catalog={catalog} onChange={load} />
          ))}
        </div>
      )}
    </div>
  );
}

function GroupCard({
  group,
  catalog,
  onChange,
}: {
  group: api.TeamGroupOut;
  catalog: api.TeamOut[];
  onChange: () => Promise<void> | void;
}) {
  const { t } = useI18n();
  const { toast } = useToast();
  const confirm = useConfirm();
  const [open, setOpen] = useState(false);
  const [addId, setAddId] = useState('');
  const [busy, setBusy] = useState(false);

  const memberIds = new Set(group.teams.map((m) => m.id));
  const addable = catalog.filter((c) => !memberIds.has(c.id));

  async function run(fn: () => Promise<unknown>, errKey = 'acc.groups.errorGeneric') {
    setBusy(true);
    try {
      await fn();
      await onChange();
    } catch (err) {
      toast(err instanceof api.ApiError ? err.detail : t(errKey), 'error');
    } finally {
      setBusy(false);
    }
  }

  async function togglePublished() {
    await run(async () => {
      await api.adminSetGroupActive(group.id, !group.is_active);
      toast(group.is_active ? t('acc.groups.toastUnpublished') : t('acc.groups.toastPublished'));
    });
  }

  async function addMember() {
    const id = Number(addId);
    if (!id) return;
    await run(async () => {
      await api.adminAddGroupMember(group.id, id);
      setAddId('');
    });
  }

  async function removeMember(team: api.TeamOut) {
    await run(() => api.adminRemoveGroupMember(group.id, team.id));
  }

  async function del() {
    const ok = await confirm({
      title: t('acc.groups.confirmDeleteTitle'),
      message: t('acc.groups.confirmDeleteMsg', { name: group.name }),
      confirmLabel: t('acc.common.delete'),
      danger: true,
    });
    if (!ok) return;
    await run(async () => {
      await api.adminDeleteGroup(group.id);
      toast(t('acc.groups.toastDeleted', { name: group.name }));
    });
  }

  return (
    <div className="acc-tcard acc-gcard">
      <div className="acc-tcard__main">
        <span className="acc-tcard__name">{group.name}</span>
        <span className={`acc-pill${group.is_active ? ' is-on' : ''}`}>
          {group.is_active ? t('acc.groups.published') : t('acc.groups.draft')}
        </span>
        <span className="acc-muted acc-gcard__count">
          {t('acc.groups.memberCount', { n: group.teams.length })}
        </span>
        <span className="acc-tcard__spacer" />
        <button
          className={`acc-btn ghost${open ? ' is-active' : ''}`}
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
        >
          {open ? t('acc.common.close') : t('acc.groups.manage')}
        </button>
      </div>

      {open && (
        <div className="acc-tcard__editor">
          <div className="acc-gcard__row">
            <button className="acc-btn secondary" disabled={busy} onClick={togglePublished}>
              {group.is_active ? t('acc.groups.unpublish') : t('acc.groups.publish')}
            </button>
            <button className="acc-btn danger" disabled={busy} onClick={del}>
              {t('acc.groups.deleteGroup')}
            </button>
          </div>

          <div className="acc-gcard__members-label acc-muted">{t('acc.groups.members')}</div>
          {group.teams.length === 0 ? (
            <p className="acc-muted">{t('acc.groups.noMembers')}</p>
          ) : (
            <ul className="acc-gcard__members">
              {group.teams.map((m) => (
                <li key={m.id} className="acc-gchip">
                  <SwatchBox
                    color={m.color}
                    textColor={m.text_color}
                    icon={m.icon}
                    name={m.name}
                    size={22}
                  />
                  <span className="acc-gchip__name">{m.name}</span>
                  <button
                    className="acc-gchip__x"
                    disabled={busy}
                    aria-label={t('acc.groups.removeMember', { name: m.name })}
                    title={t('acc.groups.removeMember', { name: m.name })}
                    onClick={() => removeMember(m)}
                  >
                    <span aria-hidden="true">×</span>
                  </button>
                </li>
              ))}
            </ul>
          )}

          {addable.length === 0 ? (
            <p className="acc-muted">{t('acc.groups.allTeamsIn')}</p>
          ) : (
            <div className="acc-gcard__add">
              <select
                className="acc-input"
                value={addId}
                aria-label={t('acc.groups.chooseTeamToAdd')}
                onChange={(e) => setAddId(e.target.value)}
              >
                <option value="">{t('acc.groups.addMemberPlaceholder')}</option>
                {addable.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
              <button className="acc-btn" disabled={busy || !addId} onClick={addMember}>
                {t('acc.groups.addMember')}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
