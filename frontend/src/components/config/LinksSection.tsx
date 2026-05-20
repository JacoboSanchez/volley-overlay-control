import { useState } from 'react';
import { useI18n } from '../../i18n';

export interface LinksSectionLinks {
  control?: string;
  overlay?: string;
  preview?: string;
  follow?: string;
  latest_match_report?: string;
  match_history?: string;
}

export interface LinksSectionProps {
  links: LinksSectionLinks | null | undefined;
}

const LINK_KEYS: Array<keyof LinksSectionLinks> = [
  'control',
  'overlay',
  'preview',
  'follow',
  'latest_match_report',
  'match_history',
];

// Keys whose URL targets a locale-aware HTML surface (the match
// report, the matches index, and the public spectator/follow page).
// We append the operator's selected app locale as ``?lang=<code>``
// so the spectator sees the same language the operator was using
// when they shared the link, rather than whatever ``Accept-Language``
// the spectator's browser happens to advertise.
const LOCALE_AWARE_KEYS: ReadonlySet<keyof LinksSectionLinks> = new Set([
  'follow',
  'latest_match_report',
  'match_history',
]);

function withLang(url: string, lang: string): string {
  try {
    const parsed = new URL(url, window.location.origin);
    parsed.searchParams.set('lang', lang);
    return parsed.toString();
  } catch {
    // Malformed URL — leave untouched rather than corrupt it.
    return url;
  }
}

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
  const { t, lang } = useI18n();
  const [copiedKey, setCopiedKey] = useState<keyof LinksSectionLinks | null>(null);
  const availableLinks = LINK_KEYS.filter((key) => links?.[key]);

  return (
    <div className="config-section-links">
      <div className="links-list">
        {availableLinks.length === 0 ? (
          <p className="config-label" style={{ textAlign: 'center', padding: '0.5rem 0' }}>
            {t('links.noLinks')}
          </p>
        ) : (
          availableLinks.map((key) => {
            const raw = links?.[key] as string;
            // Only the locale-aware surfaces get the ``?lang=`` tag;
            // overlay / preview / control URLs are passed through
            // unchanged so we don't bloat them with a query param the
            // target service has no use for.
            const url = LOCALE_AWARE_KEYS.has(key) ? withLang(raw, lang) : raw;
            return (
              <div key={key} className="link-row">
                <a href={url} target="_blank" rel="noopener noreferrer" className="link-text">
                  {t(`links.${key}`)}
                </a>
                <button
                  className="link-copy-btn"
                  title={t('links.copyToClipboard')}
                  onClick={() => {
                    copyToClipboard(url);
                    setCopiedKey(key);
                    setTimeout(() => setCopiedKey(null), 1500);
                  }}
                >
                  <span className="material-icons">
                    {copiedKey === key ? 'check' : 'content_copy'}
                  </span>
                </button>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
