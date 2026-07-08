import { useState, useCallback, useEffect } from 'react';
import * as api from '../api/client';
import type { ShareLinks } from '../utils/links';

export type { ShareLinks };

export interface UseShareLinksResult {
  shareOpen: boolean;
  setShareOpen: (open: boolean) => void;
  shareLinks: ShareLinks | null;
  handleOpenShare: () => Promise<void>;
}

/**
 * Share dialog: lazy-fetched links, opened from the HUD's share
 * button. Kept at the App level so the dialog renders on top of both
 * the scoreboard and config tabs (useful when the operator opens it
 * from either surface).
 */
export function useShareLinks(oid: string): UseShareLinksResult {
  const [shareOpen, setShareOpen] = useState(false);
  const [shareLinks, setShareLinks] = useState<ShareLinks | null>(null);

  // Drop the cached links when the overlay changes — ``App`` stays mounted
  // across owner overlay switches, so without this, reopening the dialog would
  // show the previously-selected overlay's URLs.
  useEffect(() => {
    setShareLinks(null);
  }, [oid]);

  const handleOpenShare = useCallback(async () => {
    if (!oid) return;
    setShareOpen(true);
    if (!shareLinks) {
      try {
        const links = await api.getLinks(oid);
        const str = (v: unknown) => (typeof v === 'string' ? v : '');
        setShareLinks({
          control: str(links?.control),
          overlay: str(links?.overlay),
          preview: str(links?.preview),
          follow: str(links?.follow),
          latest_match_report: str(links?.latest_match_report),
          match_history: str(links?.match_history),
        });
      } catch {
        // Empty links surface as the "No links available" fallback
        // already rendered by LinksDialog — no extra error UI needed.
        setShareLinks({});
      }
    }
  }, [oid, shareLinks]);

  return { shareOpen, setShareOpen, shareLinks, handleOpenShare };
}
