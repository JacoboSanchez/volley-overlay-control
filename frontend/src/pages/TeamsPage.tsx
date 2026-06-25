import { FormEvent, useCallback, useEffect, useState } from 'react';
import * as api from '../api/client';
import EmptyState from '../components/EmptyState';
import { useToast } from '../components/Toast';
import { useConfirm } from '../components/ConfirmProvider';
import { useI18n } from '../i18n';
import TeamRowCard from '../components/teams/TeamRowCard';
import TeamListToolbar from '../components/teams/TeamListToolbar';
import TeamCreatePanel from '../components/teams/TeamCreatePanel';
import TeamInlineEditor from '../components/teams/TeamInlineEditor';
import { SwatchBox } from '../components/teams/TeamSwatch';
import { useTeamSelection } from '../components/teams/useTeamSelection';
import { FILTER_THRESHOLD, filterTeams } from '../components/teams/teamUtils';

/** The user's team groups are the primary unit. "All" (catalog + customs) is
 *  read-only; shared admin groups can be extended with the user's own teams;
 *  private groups are fully managed. Custom teams are authored below and can be
 *  added to any group. The control board picks one of these groups. */
export default function TeamsPage() {
  const { t } = useI18n();
  const [groups, setGroups] = useState<api.GroupDetail[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      setGroups(await api.getMyGroups());
    } catch {
      setError(t('acc.teams.errorLoad'));
    } finally {
      setLoaded(true);
    }
  }, [t]);

  useEffect(() => { void load(); }, [load]);

  const allGroup = groups.find((g) => g.kind === 'all');
  const universe = allGroup?.teams ?? [];            // catalog ∪ the user's customs
  const customs = universe.filter((tm) => !tm.is_global);
  const realGroups = groups.filter((g) => g.kind !== 'all');

  return (
    <div>
      <h2>{t('acc.nav.teams')}</h2>
      {error && <div className="acc-error">{error}</div>}
      <p className="acc-muted">{t('acc.teams.introGroups')}</p>

      <h3 className="acc-subhead">{t('acc.teams.yourGroups')}</h3>
      <CreateGroupForm onCreated={load} />
      {allGroup ? (
        <div className="acc-tlist">
          <GroupCard group={allGroup} universe={universe} onChange={load} />
          {realGroups.map((g) => (
            <GroupCard key={g.id} group={g} universe={universe} onChange={load} />
          ))}
        </div>
      ) : (
        loaded && <EmptyState>{t('acc.teams.errorLoad')}</EmptyState>
      )}

      <CustomTeamsSection customs={customs} loaded={loaded} onChange={load} />
    </div>
  );
}

function CreateGroupForm({ onCreated }: { onCreated: () => void }) {
  const { t } = useI18n();
  const { toast } = useToast();
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!name.trim() || busy) return;
    setBusy(true);
    try {
      const g = await api.createMyGroup(name.trim());
      setName('');
      onCreated();
      toast(t('acc.groups.toastCreated', { name: g.name }));
    } catch (err) {
      toast(err instanceof api.ApiError ? err.detail : t('acc.groups.errorCreate'), 'error');
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="acc-group-create" onSubmit={submit}>
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
  );
}

function GroupCard({
  group, universe, onChange,
}: {
  group: api.GroupDetail;
  universe: api.TeamOut[];
  onChange: () => void | Promise<void>;
}) {
  const { t } = useI18n();
  const { toast } = useToast();
  const confirm = useConfirm();
  const [open, setOpen] = useState(false);
  const [adding, setAdding] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [rename, setRename] = useState(group.name);
  const [busy, setBusy] = useState(false);

  const isAll = group.kind === 'all';
  const removable = new Set(group.removable_ids);
  const memberIds = new Set(group.teams.map((tm) => tm.id));
  const addable = universe.filter((tm) => !memberIds.has(tm.id));

  async function run(fn: () => Promise<unknown>, errKey = 'acc.groups.errorGeneric') {
    setBusy(true);
    try {
      await fn();
      // Await the parent reload so ``busy`` (and the disabled buttons) stay
      // set until the refetch settles — otherwise a second mutation can fire
      // against stale data.
      await onChange();
    } catch (err) {
      toast(err instanceof api.ApiError ? err.detail : t(errKey), 'error');
    } finally {
      setBusy(false);
    }
  }

  async function saveName() {
    if (!rename.trim() || group.id == null) return;
    await run(async () => {
      await api.renameMyGroup(group.id as number, rename.trim());
      setRenaming(false);
    });
  }
  async function del() {
    const ok = await confirm({
      title: t('acc.groups.confirmDeleteTitle'),
      message: t('acc.groups.confirmDeleteMsg', { name: group.name }),
      confirmLabel: t('acc.common.delete'),
      danger: true,
    });
    if (!ok || group.id == null) return;
    await run(async () => {
      await api.deleteMyGroup(group.id as number);
      toast(t('acc.groups.toastDeleted', { name: group.name }));
    });
  }
  async function removeMember(team: api.TeamOut) {
    if (group.id == null) return;
    await run(() => api.removeTeamFromMyGroup(group.id as number, team.id));
  }
  async function addTeams(ids: number[]) {
    if (group.id == null || ids.length === 0) return;
    await run(async () => {
      const { added } = await api.addTeamsToMyGroup(group.id as number, ids);
      setAdding(false);
      toast(t('acc.groups.toastTeamsAdded', { n: added }));
    });
  }

  const badge = isAll ? null : (
    <span className={`acc-pill${group.is_private ? '' : ' is-on'}`}>
      {group.is_private ? t('acc.groups.badgePrivate') : t('acc.groups.badgeShared')}
    </span>
  );

  return (
    <div className="acc-tcard acc-gcard">
      <div className="acc-tcard__main">
        <span className="acc-tcard__name">{group.name}</span>
        {badge}
        <span className="acc-muted acc-gcard__count">{t('acc.groups.memberCount', { n: group.teams.length })}</span>
        <span className="acc-tcard__spacer" />
        <button
          className={`acc-btn ghost${open ? ' is-active' : ''}`}
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
        >
          {open ? t('acc.common.close') : isAll ? t('acc.groups.view') : t('acc.groups.manage')}
        </button>
      </div>

      {open && (
        <div className="acc-tcard__editor">
          {isAll && <p className="acc-muted">{t('acc.groups.allHint')}</p>}

          {group.is_private && (
            <div className="acc-gcard__row">
              {renaming ? (
                <>
                  <input
                    className="acc-input"
                    value={rename}
                    aria-label={t('acc.groups.nameLabel')}
                    onChange={(e) => setRename(e.target.value)}
                  />
                  <button className="acc-btn" disabled={busy || !rename.trim()} onClick={saveName}>
                    {t('acc.common.save')}
                  </button>
                </>
              ) : (
                <button className="acc-btn secondary" onClick={() => { setRename(group.name); setRenaming(true); }}>
                  {t('acc.groups.rename')}
                </button>
              )}
              <button className="acc-btn danger" disabled={busy} onClick={del}>
                {t('acc.groups.deleteGroup')}
              </button>
            </div>
          )}

          <div className="acc-gcard__members-label acc-muted">{t('acc.groups.members')}</div>
          {group.teams.length === 0 ? (
            <p className="acc-muted">{t('acc.groups.noMembers')}</p>
          ) : (
            <ul className="acc-gcard__members">
              {group.teams.map((tm) => (
                <li key={tm.id} className="acc-gchip">
                  <SwatchBox color={tm.color} textColor={tm.text_color} icon={tm.icon} name={tm.name} size={22} />
                  <span className="acc-gchip__name">{tm.name}</span>
                  {removable.has(tm.id) && (
                    <button
                      className="acc-gchip__x"
                      disabled={busy}
                      aria-label={t('acc.groups.removeMember', { name: tm.name })}
                      title={t('acc.groups.removeMember', { name: tm.name })}
                      onClick={() => removeMember(tm)}
                    >
                      <span aria-hidden="true">×</span>
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}

          {!isAll && (
            adding ? (
              <AddTeamsPanel addable={addable} busy={busy} onAdd={addTeams} onCancel={() => setAdding(false)} />
            ) : (
              <button className="acc-btn" style={{ marginTop: 12 }} onClick={() => setAdding(true)}>
                {t('acc.groups.addTeams')}
              </button>
            )
          )}
        </div>
      )}
    </div>
  );
}

/** Searchable, multi-select picker of teams not yet in a group, with bulk add. */
function AddTeamsPanel({
  addable, busy, onAdd, onCancel,
}: {
  addable: api.TeamOut[];
  busy: boolean;
  onAdd: (ids: number[]) => void;
  onCancel: () => void;
}) {
  const { t } = useI18n();
  const sel = useTeamSelection();
  const [query, setQuery] = useState('');
  const shown = filterTeams(addable, query);
  const selShownIds = shown.filter((x) => sel.has(x.id)).map((x) => x.id);

  if (addable.length === 0) {
    return (
      <div className="acc-overlay-panel" style={{ marginTop: 12 }}>
        <p className="acc-muted">{t('acc.groups.allTeamsIn')}</p>
        <button className="acc-btn ghost" onClick={onCancel}>{t('acc.common.close')}</button>
      </div>
    );
  }

  return (
    <div className="acc-overlay-panel" style={{ marginTop: 12 }}>
      <TeamListToolbar
        shownCount={shown.length}
        selectedShownCount={selShownIds.length}
        onSelectAll={() => sel.replace([...new Set([...sel.ids, ...shown.map((x) => x.id)])])}
        onClearSelection={() => sel.replace(sel.ids.filter((id) => !shown.some((x) => x.id === id)))}
        query={query}
        onQuery={setQuery}
        total={addable.length}
        showFilter={addable.length > FILTER_THRESHOLD}
      />
      {shown.length === 0 ? (
        <EmptyState>{t('acc.teams.noMatch', { q: query.trim() })}</EmptyState>
      ) : (
        <div className="acc-tlist">
          {shown.map((tm) => (
            <TeamRowCard
              key={tm.id}
              team={tm}
              selected={sel.has(tm.id)}
              onToggleSelect={() => sel.toggle(tm.id)}
              pill={!tm.is_global ? <span className="acc-pill">{t('acc.teams.custom')}</span> : undefined}
            />
          ))}
        </div>
      )}
      <div className="acc-gcard__row" style={{ marginTop: 12 }}>
        <button
          className="acc-btn"
          disabled={busy || selShownIds.length === 0}
          onClick={() => onAdd(selShownIds)}
        >
          {t('acc.groups.addSelected', { n: selShownIds.length })}
        </button>
        <button className="acc-btn ghost" onClick={onCancel}>{t('acc.common.close')}</button>
      </div>
    </div>
  );
}

function CustomTeamsSection({
  customs, loaded, onChange,
}: {
  customs: api.TeamOut[];
  loaded: boolean;
  onChange: () => void;
}) {
  const { t } = useI18n();
  const { toast } = useToast();
  const confirm = useConfirm();
  const [editing, setEditing] = useState<number | null>(null);

  async function del(team: api.TeamOut) {
    const ok = await confirm({
      title: t('acc.teams.confirmRemoveTitle'),
      message: t('acc.teams.confirmRemoveAll', { n: 1 }),
      confirmLabel: t('acc.common.delete'),
      danger: true,
    });
    if (!ok) return;
    try {
      await api.removeTeamFromMine(team.id);
      setEditing(null);
      onChange();
      toast(t('acc.teams.toastRemoved', { n: 1 }));
    } catch (err) {
      toast(err instanceof api.ApiError ? err.detail : t('acc.teams.errorRemove'), 'error');
    }
  }

  return (
    <div className="acc-section">
      <h3>{t('acc.teams.customTitle')}</h3>
      <p className="acc-muted">{t('acc.teams.customGroupsDesc')}</p>
      <TeamCreatePanel
        onCreate={(fields) => api.createMyTeam(fields)}
        onCreated={onChange}
        addLabel={t('acc.teams.customAdd')}
        successMessage={(name) => t('acc.teams.toastCreated', { name })}
        idPrefix="custom"
      />
      {customs.length === 0 ? (
        loaded && <EmptyState>{t('acc.teams.noCustomYet')}</EmptyState>
      ) : (
        <div className="acc-tlist" style={{ marginTop: 14 }}>
          {customs.map((team) => (
            <TeamRowCard
              key={team.id}
              team={team}
              editable
              editing={editing === team.id}
              onToggleEdit={() => setEditing(editing === team.id ? null : team.id)}
            >
              <TeamInlineEditor
                team={team}
                onSave={(fields) => api.updateMyTeam(team.id, fields)}
                onSaved={onChange}
                danger={{ label: t('acc.common.delete'), onClick: () => void del(team) }}
              />
            </TeamRowCard>
          ))}
        </div>
      )}
    </div>
  );
}
