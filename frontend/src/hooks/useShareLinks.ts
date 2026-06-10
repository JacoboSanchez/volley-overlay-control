import { useState, useCallback } from 'react';
import * as api from '../api/client';

export interface ShareLinks {
  control?: string;
  overlay?: string;
  preview?: string;
  follow?: string;
}

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

  const handleOpenShare = useCallback(async () => {
    if (!oid) return;
    setShareOpen(true);
    if (!shareLinks) {
      try {
        const links = await api.getLinks(oid);
        setShareLinks({
          control: typeof links?.control === 'string' ? links.control : '',
          overlay: typeof links?.overlay === 'string' ? links.overlay : '',
          preview: typeof links?.preview === 'string' ? links.preview : '',
          follow: typeof links?.follow === 'string' ? links.follow : '',
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
