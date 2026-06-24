import { useCallback, useEffect, useRef, useState } from 'react';
import * as api from '../api/client';
import EmptyState from '../components/EmptyState';
import { useToast } from '../components/Toast';
import { useConfirm } from '../components/ConfirmProvider';
import { useI18n } from '../i18n';
import TeamRowCard from '../components/teams/TeamRowCard';
import TeamListToolbar from '../components/teams/TeamListToolbar';
import BulkActionBar from '../components/teams/BulkActionBar';
import TeamCreatePanel from '../components/teams/TeamCreatePanel';
import TeamInlineEditor from '../components/teams/TeamInlineEditor';
import { useTeamSelection } from '../components/teams/useTeamSelection';
import {
  FILTER_THRESHOLD, filterTeams, restoreFocus, withPinnedEdit,
} from '../components/teams/teamUtils';

/** A user's own team roster: add catalog teams, copy a published group, or
 *  create custom teams. Admin catalog/group authoring lives on /admin/teams. */
export default function TeamsPage() {
  const { t } = useI18n();
  const { toast } = useToast();
  const confirm = useConfirm();
  const [mine, setMine] = useState<api.TeamOut[]>([]);
  const [catalog, setCatalog] = useState<api.TeamOut[]>([]);
  const [groups, setGroups] = useState<api.TeamGroupOut[]>([]);
  const [editing, setEditing] = useState<number | null>(null);
  const [loadError, setLoadError] = useState('');
  const [loaded, setLoaded] = useState(false);
  const [mineQuery, setMineQuery] = useState('');
  const [catQuery, setCatQuery] = useState('');

  const mineSel = useTeamSelection();
  const catSel = useTeamSelection();
  const mineSelAllRef = useRef<HTMLInputElement>(null);
  const catSelAllRef = useRef<HTMLInputElement>(null);

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
  // The currently-edited row stays visible even when the filter would hide it,
  // so typing in the filter box never silently drops an open editor's edits.
  const mineShown = withPinnedEdit(filterTeams(mine, mineQuery), mine, editing);
  const addableShown = filterTeams(addable, catQuery);

  // Bulk actions operate ONLY on the currently-visible selected rows, and the
  // bar count matches — so a selection hidden by the filter can never be
  // removed/added behind the user's back.
  const mineSelShownIds = mineShown.filter((x) => mineSel.has(x.id)).map((x) => x.id);
  const catSelShownIds = addableShown.filter((x) => catSel.has(x.id)).map((x) => x.id);

  // Keep at most one list's selection active so the two bulk bars never stack:
  // touching one list drops the other's selection.
  const toggleMine = (id: number) => { catSel.clear(); mineSel.toggle(id); };
  const toggleCat = (id: number) => { mineSel.clear(); catSel.toggle(id); };
  const union = (ids: number[], add: number[]) => [...new Set([...ids, ...add])];
  const selectAllMine = () => { catSel.clear(); mineSel.replace(union(mineSel.ids, mineShown.map((x) => x.id))); };
  const clearShownMine = () =>
    mineSel.replace(mineSel.ids.filter((id) => !mineShown.some((x) => x.id === id)));
  const selectAllCat = () => { mineSel.clear(); catSel.replace(union(catSel.ids, addableShown.map((x) => x.id))); };
  const clearShownCat = () =>
    catSel.replace(catSel.ids.filter((id) => !addableShown.some((x) => x.id === id)));

  async function removeSelectedMine() {
    const ids = mineSelShownIds;
    if (ids.length === 0) return;
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
      restoreFocus(mineSelAllRef);
    } catch (err) {
      toast(err instanceof api.ApiError ? err.detail : t('acc.teams.errorRemove'), 'error');
    }
  }

  async function addSelectedCatalog() {
    const ids = catSelShownIds;
    if (ids.length === 0) return;
    try {
      const { added } = await api.addTeamsToMine(ids);
      await reload();
      toast(t('acc.teams.toastAdded', { n: added }));
      restoreFocus(catSelAllRef);
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
          <TeamListToolbar
            inputRef={mineSelAllRef}
            shownCount={mineShown.length}
            selectedShownCount={mineSelShownIds.length}
            onSelectAll={selectAllMine}
            onClearSelection={clearShownMine}
            query={mineQuery}
            onQuery={setMineQuery}
            total={mine.length}
            showFilter={mine.length > FILTER_THRESHOLD}
          />
          {mineShown.length === 0 ? (
            <EmptyState>{t('acc.teams.noMatch', { q: mineQuery.trim() })}</EmptyState>
          ) : (
            <div className="acc-tlist">
              {mineShown.map((team) => (
                <TeamRowCard
                  key={team.id}
                  team={team}
                  selected={mineSel.has(team.id)}
                  onToggleSelect={() => toggleMine(team.id)}
                  pill={!team.is_global ? <span className="acc-pill">{t('acc.teams.custom')}</span> : undefined}
                  editable={!team.is_global}
                  editing={editing === team.id}
                  onToggleEdit={() => setEditing(editing === team.id ? null : team.id)}
                >
                  <TeamInlineEditor
                    team={team}
                    onSave={(fields) => api.updateMyTeam(team.id, fields)}
                    onSaved={reload}
                  />
                </TeamRowCard>
              ))}
            </div>
          )}
          <BulkActionBar
            count={mineSelShownIds.length}
            onClear={() => { mineSel.clear(); restoreFocus(mineSelAllRef); }}
          >
            <button className="acc-btn danger" onClick={removeSelectedMine}>
              {t('acc.teams.removeSelected', { n: mineSelShownIds.length })}
            </button>
          </BulkActionBar>
        </>
      )}

      <div className="acc-section">
        <h3>{t('acc.teams.customTitle')}</h3>
        <p className="acc-muted">{t('acc.teams.customDesc')}</p>
        <TeamCreatePanel
          onCreate={(fields) => api.createMyTeam(fields)}
          onCreated={reload}
          addLabel={t('acc.teams.customAdd')}
          successMessage={(name) => t('acc.teams.toastCreated', { name })}
          idPrefix="custom"
        />
      </div>

      {groups.length > 0 && (
        <div className="acc-section">
          <h3>{t('acc.teams.groups')}</h3>
          <p className="acc-muted">{t('acc.teams.groupsDesc')}</p>
          <div className="acc-group-copies">
            {groups.map((g) => (
              <button key={g.id} className="acc-btn secondary" onClick={() => copyGroup(g.id, g.name)}>
                {t('acc.teams.copyGroup', { name: g.name, n: g.teams.length })}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="acc-section">
        <h3>{t('acc.teams.catalog')}</h3>
        <p className="acc-muted">{t('acc.teams.catalogDesc')}</p>
        {addable.length === 0 ? (
          loaded && (
            <EmptyState>
              {catalog.length === 0 ? t('acc.teams.emptyCatalogNone') : t('acc.teams.emptyCatalog')}
            </EmptyState>
          )
        ) : (
          <>
            <TeamListToolbar
              inputRef={catSelAllRef}
              shownCount={addableShown.length}
              selectedShownCount={catSelShownIds.length}
              onSelectAll={selectAllCat}
              onClearSelection={clearShownCat}
              query={catQuery}
              onQuery={setCatQuery}
              total={addable.length}
              showFilter={addable.length > FILTER_THRESHOLD}
            />
            {addableShown.length === 0 ? (
              <EmptyState>{t('acc.teams.noMatch', { q: catQuery.trim() })}</EmptyState>
            ) : (
              <div className="acc-tlist">
                {addableShown.map((team) => (
                  <TeamRowCard
                    key={team.id}
                    team={team}
                    selected={catSel.has(team.id)}
                    onToggleSelect={() => toggleCat(team.id)}
                  />
                ))}
              </div>
            )}
            <BulkActionBar
              count={catSelShownIds.length}
              onClear={() => { catSel.clear(); restoreFocus(catSelAllRef); }}
            >
              <button className="acc-btn" onClick={addSelectedCatalog}>
                {t('acc.teams.addSelected', { n: catSelShownIds.length })}
              </button>
            </BulkActionBar>
          </>
        )}
      </div>
    </div>
  );
}
