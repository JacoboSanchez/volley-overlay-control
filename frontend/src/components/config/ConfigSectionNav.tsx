import { Suspense, type ReactNode } from 'react';
import { useI18n } from '../../i18n';
import ConfigSkeleton from '../ConfigSkeleton';
import { CONFIG_SECTIONS, type SectionId } from './sections';

export interface ConfigSectionNavProps {
  /** Portrait shows a stacked accordion, landscape a sidebar + content pane. */
  isPortrait: boolean;
  /** ``null`` only in portrait, where every section can be collapsed. */
  activeSection: SectionId | null;
  onSelect: (section: SectionId | null) => void;
  /** Renders the body of one section. */
  renderSection: (section: SectionId | null) => ReactNode;
}

function panelId(section: SectionId): string {
  return `config-section-${section}`;
}

function headerId(section: SectionId): string {
  return `config-section-${section}-header`;
}

/** The panel's two alternate layouts, and the only place that knows which
 *  section is on screen. Both expose the same section list; they differ in
 *  whether a section can be collapsed (portrait) or merely switched away from
 *  (landscape). */
export default function ConfigSectionNav({
  isPortrait,
  activeSection,
  onSelect,
  renderSection,
}: ConfigSectionNavProps) {
  const { t } = useI18n();

  if (isPortrait) {
    return (
      <div className="config-accordion">
        {CONFIG_SECTIONS.map((sec) => {
          const expanded = activeSection === sec.id;
          return (
            <div key={sec.id} className="config-accordion-item">
              <button
                id={headerId(sec.id)}
                className={`config-accordion-header ${expanded ? 'config-accordion-header-active' : ''}`}
                aria-expanded={expanded}
                aria-controls={panelId(sec.id)}
                onClick={() => onSelect(expanded ? null : sec.id)}
              >
                <span className="material-icons">{sec.icon}</span>
                {t(sec.labelKey)}
                <span className="material-icons config-accordion-chevron">
                  {expanded ? 'expand_less' : 'expand_more'}
                </span>
              </button>
              {expanded && (
                <div
                  id={panelId(sec.id)}
                  role="region"
                  aria-labelledby={headerId(sec.id)}
                  className="config-accordion-body"
                >
                  <Suspense fallback={<ConfigSkeleton />}>{renderSection(sec.id)}</Suspense>
                </div>
              )}
            </div>
          );
        })}
      </div>
    );
  }

  return (
    <>
      <nav className="config-sidebar">
        {CONFIG_SECTIONS.map((sec) => (
          <button
            key={sec.id}
            className={`config-sidebar-item ${activeSection === sec.id ? 'config-sidebar-item-active' : ''}`}
            aria-current={activeSection === sec.id ? 'page' : undefined}
            onClick={() => onSelect(sec.id)}
          >
            <span className="material-icons">{sec.icon}</span>
            <span className="config-sidebar-label">{t(sec.labelKey)}</span>
          </button>
        ))}
      </nav>
      <div className="config-section-content">
        <Suspense fallback={<ConfigSkeleton />}>{renderSection(activeSection)}</Suspense>
      </div>
    </>
  );
}
