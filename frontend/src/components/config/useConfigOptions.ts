import { useCallback, useEffect, useState } from 'react';
import {
  getBoardGroupTeams,
  getBoardGroups,
  getLinks,
  getStyleCapabilities,
  getStyles,
  setBoardSelectedGroup,
} from '../../api/board';
import type { BoardGroup, StyleCapabilities } from '../../api/board';
import type { PredefinedTeams } from '../TeamCard';
import type { LinksSectionLinks } from './LinksSection';

export interface ConfigOptions {
  /** Teams offered by the selected group's picker. */
  predefinedTeams: PredefinedTeams;
  groups: BoardGroup[];
  selectedGroupId: number | null;
  selectGroup: (id: number | null) => void;
  styles: string[];
  styleCaps: Record<string, StyleCapabilities>;
  links: LinksSectionLinks | null;
  /** True while the first (or a retried) load is in flight. */
  loading: boolean;
  /**
   * True when any of the remote lookups failed. The panel still renders —
   * the affected dropdown is simply empty — so this drives a banner offering
   * {@link ConfigOptions.reload} rather than replacing the whole panel.
   */
  failed: boolean;
  reload: () => void;
}

function warn(what: string, reason: unknown): void {
  console.warn(`Config panel could not load ${what}:`, reason);
}

/**
 * The four remote lookups the config panel's dropdowns are built from
 * (team groups, output links, overlay styles, per-style capabilities) plus
 * the group-scoped team list that depends on the remembered selection.
 *
 * These used to be five bare `.catch(console.warn)` calls, which left the
 * operator staring at empty dropdowns with no explanation and no way to try
 * again. Failures are collected into `failed` instead, and `reload` re-runs
 * every lookup.
 */
export function useConfigOptions(oid: string): ConfigOptions {
  const [predefinedTeams, setPredefinedTeams] = useState<PredefinedTeams>({});
  const [groups, setGroups] = useState<BoardGroup[]>([]);
  const [selectedGroupId, setSelectedGroupId] = useState<number | null>(null);
  // Gates the team-options fetch until the remembered selection is known, so a
  // board with a non-null group remembered doesn't first fetch "All" teams.
  const [groupsLoaded, setGroupsLoaded] = useState(false);
  const [styles, setStyles] = useState<string[]>([]);
  const [styleCaps, setStyleCaps] = useState<Record<string, StyleCapabilities>>({});
  const [links, setLinks] = useState<LinksSectionLinks | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  // Bumped by `reload` to re-run both effects without changing `oid`.
  const [attempt, setAttempt] = useState(0);

  const reload = useCallback(() => setAttempt((n) => n + 1), []);

  useEffect(() => {
    let cancelled = false;
    setGroupsLoaded(false);
    setLoading(true);
    setFailed(false);
    void (async () => {
      // allSettled, not all: one dead lookup must not blank the other three.
      const [groupsRes, linksRes, stylesRes, capsRes] = await Promise.allSettled([
        getBoardGroups(oid),
        getLinks(oid),
        getStyles(oid),
        getStyleCapabilities(oid),
      ]);
      if (cancelled) return;
      if (groupsRes.status === 'fulfilled') {
        setGroups(groupsRes.value.groups);
        setSelectedGroupId(groupsRes.value.selected_id);
      } else {
        warn('the team groups', groupsRes.reason);
      }
      if (linksRes.status === 'fulfilled') setLinks(linksRes.value as LinksSectionLinks);
      else warn('the output links', linksRes.reason);
      if (stylesRes.status === 'fulfilled') setStyles(stylesRes.value);
      else warn('the overlay styles', stylesRes.reason);
      if (capsRes.status === 'fulfilled') setStyleCaps(capsRes.value);
      else warn('the style capabilities', capsRes.reason);

      setFailed([groupsRes, linksRes, stylesRes, capsRes].some((r) => r.status === 'rejected'));
      setLoading(false);
      // Only unblock the team fetch when the remembered selection is real;
      // otherwise it would run against a default that isn't the operator's.
      setGroupsLoaded(groupsRes.status === 'fulfilled');
    })();
    return () => {
      cancelled = true;
    };
  }, [oid, attempt]);

  useEffect(() => {
    if (!groupsLoaded) return undefined;
    let cancelled = false;
    getBoardGroupTeams(oid, selectedGroupId)
      .then((d) => {
        if (!cancelled) setPredefinedTeams(d as PredefinedTeams);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        warn('the group roster', e);
        setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [oid, selectedGroupId, groupsLoaded, attempt]);

  const selectGroup = useCallback(
    (id: number | null) => {
      // Optimistic: the picker switches immediately and the effect above
      // fetches the new roster. Only persisting the choice can fail, and a
      // failure just means the next visit reopens on the previous group.
      setSelectedGroupId(id);
      setBoardSelectedGroup(oid, id).catch((e: unknown) => {
        warn('the selected group', e);
        setFailed(true);
      });
    },
    [oid],
  );

  return {
    predefinedTeams,
    groups,
    selectedGroupId,
    selectGroup,
    styles,
    styleCaps,
    links,
    loading,
    failed,
    reload,
  };
}
