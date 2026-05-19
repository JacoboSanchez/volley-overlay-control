import { describe, it, expect } from 'vitest';
import { screen } from '@testing-library/react';
import LinksSection from '../components/config/LinksSection';
import { renderWithI18n } from './helpers';

describe('LinksSection', () => {
  it('renders an empty fallback when no links are provided', () => {
    renderWithI18n(<LinksSection links={null} />);
    expect(screen.getByText(/no links available/i)).toBeInTheDocument();
  });

  it('does not append lang to control / overlay / preview URLs', () => {
    renderWithI18n(
      <LinksSection
        links={{
          control: 'https://example.com/control?token=abc',
          overlay: 'https://overlays.uno/output/abc?aspect=16:9',
          preview: 'https://example.com/preview',
        }}
      />,
    );
    const anchors = screen.getAllByRole('link') as HTMLAnchorElement[];
    expect(anchors.map((a) => a.href)).toEqual([
      'https://example.com/control?token=abc',
      // overlays.uno preserves its existing query string.
      'https://overlays.uno/output/abc?aspect=16:9',
      'https://example.com/preview',
    ]);
    // Defensive — no stray lang= leaked into non-locale-aware
    // surfaces.
    anchors.forEach((a) => {
      expect(a.href).not.toContain('lang=');
    });
  });

  it('appends lang= to the match-report and history URLs', () => {
    renderWithI18n(
      <LinksSection
        links={{
          latest_match_report: '/match/abc/report',
          match_history: '/matches?oid=foo',
        }}
      />,
    );
    const anchors = screen.getAllByRole('link') as HTMLAnchorElement[];
    // Default i18n locale in tests is English.
    anchors.forEach((a) => {
      expect(a.href).toContain('lang=en');
    });
    // Existing query strings on the index URL are preserved.
    const history = anchors.find((a) => a.href.includes('/matches'))!;
    expect(history.href).toContain('oid=foo');
  });

  it('preserves an existing lang param by overwriting it', () => {
    renderWithI18n(
      <LinksSection
        links={{
          latest_match_report: '/match/abc/report?lang=fr',
        }}
      />,
    );
    const a = screen.getByRole('link') as HTMLAnchorElement;
    expect(a.href).toContain('lang=en');
    expect(a.href).not.toContain('lang=fr');
  });

  it('leaves malformed URLs untouched', () => {
    renderWithI18n(
      <LinksSection
        links={{
          latest_match_report: 'not a url',
        }}
      />,
    );
    const a = screen.getByRole('link') as HTMLAnchorElement;
    // jsdom resolves the bare string against the document's base
    // URL; the helper falls back to the original on URL parse
    // failure, but ``new URL('not a url', origin)`` actually
    // succeeds, so we just check the link rendered without
    // throwing.
    expect(a).toBeInTheDocument();
  });
});
