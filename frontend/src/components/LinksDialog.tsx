import { useI18n } from '../i18n';
import Dialog from './Dialog';

export interface LinksDialogLinks {
  control?: string;
  overlay?: string;
  preview?: string;
  follow?: string;
  latest_match_report?: string;
  match_history?: string;
}

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

// The spectator (follow) page reads ``?lang=`` to pick its UI
// locale (see ``overlay_static/js/spectator.js``). Append the
// operator's active app locale so a shared link opens in the same
// language they were using, instead of falling back to the
// spectator browser's ``navigator.language``.
function withLang(url: string, lang: string): string {
  try {
    const parsed = new URL(url, window.location.origin);
    parsed.searchParams.set('lang', lang);
    return parsed.toString();
  } catch {
    return url;
  }
}

/**
 * Links dialog — control, overlay, and preview links with copy buttons.
 */
export default function LinksDialog({ links, reportsUrl, onClose }: LinksDialogProps) {
  const { t, lang } = useI18n();
  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text).catch(() => {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
    });
  };
  const followUrl = links.follow ? withLang(links.follow, lang) : undefined;
  // The report surfaces are locale-aware HTML pages — share them in the
  // operator's current language (see LinksSection for the rationale).
  const latestReportUrl = links.latest_match_report
    ? withLang(links.latest_match_report, lang)
    : undefined;
  const matchHistoryUrl = links.match_history ? withLang(links.match_history, lang) : undefined;
  const hasAnyLink =
    !!links.control ||
    !!links.overlay ||
    !!links.preview ||
    !!followUrl ||
    !!latestReportUrl ||
    !!matchHistoryUrl ||
    !!reportsUrl;

  return (
    <Dialog open onClose={onClose} ariaLabelledBy="links-dialog-title">
      <h3 className="dialog-title" id="links-dialog-title">
        {t('links.title')}
      </h3>
      <div className="links-list">
        {links.control && (
          <div className="link-row">
            <a href={links.control} target="_blank" rel="noopener noreferrer" className="link-text">
              {t('links.control')}
            </a>
            <button
              className="link-copy-btn"
              onClick={() => copyToClipboard(links.control!)}
              title={t('links.copyToClipboard')}
            >
              <span className="material-icons">content_copy</span>
            </button>
          </div>
        )}
        {links.overlay && (
          <div className="link-row">
            <a href={links.overlay} target="_blank" rel="noopener noreferrer" className="link-text">
              {t('links.overlay')}
            </a>
            <button
              className="link-copy-btn"
              onClick={() => copyToClipboard(links.overlay!)}
              title={t('links.copyToClipboard')}
            >
              <span className="material-icons">content_copy</span>
            </button>
          </div>
        )}
        {links.preview && (
          <div className="link-row">
            <a href={links.preview} target="_blank" rel="noopener noreferrer" className="link-text">
              {t('links.preview')}
            </a>
            <button
              className="link-copy-btn"
              onClick={() => copyToClipboard(links.preview!)}
              title={t('links.copyToClipboard')}
            >
              <span className="material-icons">content_copy</span>
            </button>
          </div>
        )}
        {followUrl && (
          <div className="link-row">
            <a href={followUrl} target="_blank" rel="noopener noreferrer" className="link-text">
              {t('links.follow')}
            </a>
            <button
              className="link-copy-btn"
              onClick={() => copyToClipboard(followUrl)}
              title={t('links.copyToClipboard')}
            >
              <span className="material-icons">content_copy</span>
            </button>
          </div>
        )}
        {latestReportUrl && (
          <div className="link-row">
            <a href={latestReportUrl} target="_blank" rel="noopener noreferrer" className="link-text">
              {t('links.latest_match_report')}
            </a>
            <button
              className="link-copy-btn"
              onClick={() => copyToClipboard(latestReportUrl)}
              title={t('links.copyToClipboard')}
            >
              <span className="material-icons">content_copy</span>
            </button>
          </div>
        )}
        {matchHistoryUrl && (
          <div className="link-row">
            <a href={matchHistoryUrl} target="_blank" rel="noopener noreferrer" className="link-text">
              {t('links.match_history')}
            </a>
            <button
              className="link-copy-btn"
              onClick={() => copyToClipboard(matchHistoryUrl)}
              title={t('links.copyToClipboard')}
            >
              <span className="material-icons">content_copy</span>
            </button>
          </div>
        )}
        {reportsUrl && (
          <div className="link-row">
            <a href={reportsUrl} target="_blank" rel="noopener noreferrer" className="link-text">
              {t('links.reports')}
            </a>
            <button
              className="link-copy-btn"
              onClick={() => copyToClipboard(reportsUrl)}
              title={t('links.copyToClipboard')}
            >
              <span className="material-icons">content_copy</span>
            </button>
          </div>
        )}
        {!hasAnyLink && (
          <p className="config-label" style={{ textAlign: 'center', padding: '0.5rem 0' }}>
            {t('links.noLinks')}
          </p>
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
