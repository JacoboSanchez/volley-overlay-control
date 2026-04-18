import { useI18n } from '../i18n';

export interface LinksDialogLinks {
  control?: string;
  overlay?: string;
  preview?: string;
}

export interface LinksDialogProps {
  links: LinksDialogLinks;
  onClose: () => void;
}

/**
 * Links dialog — control, overlay, and preview links with copy buttons.
 */
export default function LinksDialog({ links, onClose }: LinksDialogProps) {
  const { t } = useI18n();
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

  return (
    <div className="dialog-overlay" onClick={onClose}>
      <div className="dialog-card" onClick={(e) => e.stopPropagation()}>
        <h3 className="dialog-title">{t('links.title')}</h3>
        <div className="links-list">
          {links.control && (
            <div className="link-row">
              <a href={links.control} target="_blank" rel="noopener noreferrer" className="link-text">
                {t('links.control')}
              </a>
              <button className="link-copy-btn" onClick={() => copyToClipboard(links.control!)} title={t('links.copyToClipboard')}>
                <span className="material-icons">content_copy</span>
              </button>
            </div>
          )}
          {links.overlay && (
            <div className="link-row">
              <a href={links.overlay} target="_blank" rel="noopener noreferrer" className="link-text">
                {t('links.overlay')}
              </a>
              <button className="link-copy-btn" onClick={() => copyToClipboard(links.overlay!)} title={t('links.copyToClipboard')}>
                <span className="material-icons">content_copy</span>
              </button>
            </div>
          )}
          {links.preview && (
            <div className="link-row">
              <a href={links.preview} target="_blank" rel="noopener noreferrer" className="link-text">
                {t('links.preview')}
              </a>
              <button className="link-copy-btn" onClick={() => copyToClipboard(links.preview!)} title={t('links.copyToClipboard')}>
                <span className="material-icons">content_copy</span>
              </button>
            </div>
          )}
          {!links.control && !links.overlay && !links.preview && (
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
      </div>
    </div>
  );
}
