import { useI18n } from '../i18n';
import Dialog from './Dialog';
import LinkRow from './LinkRow';
import { LINK_KEYS, LOCALE_AWARE_KEYS, type ShareLinks, withLang } from '../utils/links';

/** Kept as a named alias so existing importers don't churn. */
export type LinksDialogLinks = ShareLinks;

export interface LinksDialogProps {
  links: LinksDialogLinks;
  /**
   * The signed-in owner's full reports page for this board, or ``null``
   * for unauthenticated (operator-token / public-bookmark) viewers. When
   * present it gives the owner one-tap access to manage every report;
   * unauthenticated viewers only get the read-only public links above.
   */
  reportsUrl?: string | null;
  onClose: () => void;
}

/**
 * Links dialog — control, overlay, preview, spectator and report links with
 * copy buttons.
 */
export default function LinksDialog({ links, reportsUrl, onClose }: LinksDialogProps) {
  const { t, lang } = useI18n();
  const rows = LINK_KEYS.filter((key) => links[key]).map((key) => {
    const raw = links[key] as string;
    return {
      key: key as string,
      label: t(`links.${key}`),
      // Locale-aware HTML surfaces (follow / report / history) carry the
      // operator's app locale; control / overlay / preview pass through.
      url: LOCALE_AWARE_KEYS.has(key) ? withLang(raw, lang) : raw,
    };
  });
  // The owner-only "all reports" page is not part of the shared link set.
  if (reportsUrl) rows.push({ key: 'reports', label: t('links.reports'), url: reportsUrl });

  return (
    <Dialog open onClose={onClose} ariaLabelledBy="links-dialog-title">
      <h3 className="dialog-title" id="links-dialog-title">
        {t('links.title')}
      </h3>
      <div className="links-list">
        {rows.length === 0 ? (
          <p className="config-label" style={{ textAlign: 'center', padding: '0.5rem 0' }}>
            {t('links.noLinks')}
          </p>
        ) : (
          rows.map((r) => <LinkRow key={r.key} url={r.url} label={r.label} />)
        )}
      </div>
      <div className="dialog-actions">
        <button className="dialog-btn dialog-btn-cancel" onClick={onClose}>
          <span className="material-icons">close</span>
          {t('links.close')}
        </button>
      </div>
    </Dialog>
  );
}
