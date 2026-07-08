import { useI18n } from '../../i18n';
import LinkRow from '../LinkRow';
import { LINK_KEYS, LOCALE_AWARE_KEYS, type ShareLinks, withLang } from '../../utils/links';

/** Kept as a named alias so existing importers (ConfigPanel) don't churn. */
export type LinksSectionLinks = ShareLinks;

export interface LinksSectionProps {
  links: LinksSectionLinks | null | undefined;
}

export default function LinksSection({ links }: LinksSectionProps) {
  const { t, lang } = useI18n();
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
            // Only the locale-aware surfaces get the ``?lang=`` tag; control /
            // overlay / preview URLs are passed through unchanged.
            const url = LOCALE_AWARE_KEYS.has(key) ? withLang(raw, lang) : raw;
            return <LinkRow key={key} url={url} label={t(`links.${key}`)} />;
          })
        )}
      </div>
    </div>
  );
}
