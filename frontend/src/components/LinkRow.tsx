import { useState } from 'react';
import { useI18n } from '../i18n';
import { writeToClipboard } from '../utils/clipboard';

/** A single share-link row: an open-in-new-tab link plus a copy button that
 *  flips to a check mark for a moment after copying. Shared by the board Share
 *  dialog and the Config "Links" section so the markup lives in one place. */
export default function LinkRow({ url, label }: { url: string; label: string }) {
  const { t } = useI18n();
  const [copied, setCopied] = useState(false);

  return (
    <div className="link-row">
      <a href={url} target="_blank" rel="noopener noreferrer" className="link-text">
        {label}
      </a>
      <button
        className="link-copy-btn"
        title={t('links.copyToClipboard')}
        onClick={() => {
          void writeToClipboard(url);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        }}
      >
        <span className="material-icons">{copied ? 'check' : 'content_copy'}</span>
      </button>
    </div>
  );
}
