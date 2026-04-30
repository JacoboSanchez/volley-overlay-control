import { useState } from 'react';
import { useI18n } from '../../i18n';

export interface LinksSectionLinks {
  control?: string;
  overlay?: string;
  preview?: string;
  latest_match_report?: string;
  match_history?: string;
}

export interface LinksSectionProps {
  links: LinksSectionLinks | null | undefined;
}

const LINK_KEYS: Array<keyof LinksSectionLinks> = [
  'control', 'overlay', 'preview', 'latest_match_report', 'match_history',
];

function copyToClipboard(text: string) {
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
}

export default function LinksSection({ links }: LinksSectionProps) {
  const { t } = useI18n();
  const [copiedKey, setCopiedKey] = useState<keyof LinksSectionLinks | null>(null);
  const availableLinks = LINK_KEYS.filter((key) => links?.[key]);

  return (
    <div className="config-section-links">
      <div className="links-list">
        {availableLinks.length === 0 ? (
          <p className="config-label" style={{ textAlign: 'center', padding: '0.5rem 0' }}>
            {t('links.noLinks')}
          </p>
        ) : availableLinks.map((key) => {
          const url = links?.[key] as string;
          return (
            <div key={key} className="link-row">
              <a href={url} target="_blank" rel="noopener noreferrer" className="link-text">
                {t(`links.${key}`)}
              </a>
              <button className="link-copy-btn" title={t('links.copyToClipboard')}
                onClick={() => {
                  copyToClipboard(url);
                  setCopiedKey(key);
                  setTimeout(() => setCopiedKey(null), 1500);
                }}>
                <span className="material-icons">{copiedKey === key ? 'check' : 'content_copy'}</span>
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
