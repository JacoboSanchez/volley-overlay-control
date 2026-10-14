import { describe, it, expect, vi } from 'vitest';
import { fireEvent, screen } from '@testing-library/react';
import OverlaySection from '../components/config/OverlaySection';
import { renderWithI18n } from './helpers';
import type { StyleCapabilities } from '../api/board';

const STYLES = ['default', 'pylons', 'neon'];

function render(
  model: Record<string, unknown>,
  capabilities: Record<string, StyleCapabilities>,
  updateField = vi.fn(),
) {
  renderWithI18n(
    <OverlaySection
      model={model}
      updateField={updateField}
      styles={STYLES}
      capabilities={capabilities}
    />,
  );
  return updateField;
}

const CAPS: Record<string, StyleCapabilities> = {
  default: { theme: false, nativeTheme: 'dark', verticalAnchor: false },
  pylons: { theme: true, nativeTheme: 'dark', verticalAnchor: true },
  neon: { theme: true, nativeTheme: 'dark', verticalAnchor: false },
};

describe('OverlaySection theme selector', () => {
  it('is shown for styles without a scoreboard theme, since it drives the set summary', () => {
    render({ preferredStyle: '' }, CAPS);
    expect(screen.getByTestId('style-selector')).toBeInTheDocument();
    expect(screen.getByTestId('overlay-theme-selector')).toBeInTheDocument();
    expect(screen.getByTestId('overlay-theme-hint')).toHaveTextContent(
      'This scoreboard style keeps its own palette; the theme applies to the set summary.',
    );
  });

  it('says the theme reaches the scoreboard too for themed styles', () => {
    render({ preferredStyle: 'pylons' }, CAPS);
    expect(screen.getByTestId('overlay-theme-hint')).toHaveTextContent(
      'Applies to the scoreboard and the set summary.',
    );
  });

  it('is shown even when capabilities are unknown or there is a single style', () => {
    renderWithI18n(
      <OverlaySection model={{}} updateField={vi.fn()} styles={['default']} capabilities={{}} />,
    );
    expect(screen.queryByTestId('style-selector')).not.toBeInTheDocument();
    expect(screen.getByTestId('overlay-theme-selector')).toBeInTheDocument();
    expect(screen.getByTestId('overlay-theme-hint')).toHaveTextContent(
      'Applies to the scoreboard and the set summary.',
    );
  });

  it('marks the stored theme and writes the picked one', () => {
    const updateField = render({ preferredStyle: '', overlayTheme: 'dark' }, CAPS);
    expect(screen.getByTestId('overlay-theme-dark')).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByTestId('overlay-theme-default')).toHaveAttribute('aria-checked', 'false');

    fireEvent.click(screen.getByTestId('overlay-theme-light'));
    expect(updateField).toHaveBeenCalledWith('overlayTheme', 'light');

    fireEvent.click(screen.getByTestId('overlay-theme-default'));
    expect(updateField).toHaveBeenCalledWith('overlayTheme', '');
  });

  it('treats an unrecognised stored theme as default', () => {
    render({ overlayTheme: 'sepia' }, CAPS);
    expect(screen.getByTestId('overlay-theme-default')).toHaveAttribute('aria-checked', 'true');
  });

  it('never renders a vertical-anchor knob (placement lives in the Position section)', () => {
    render({ preferredStyle: 'pylons' }, CAPS);
    expect(screen.queryByTestId('vertical-anchor-selector')).not.toBeInTheDocument();
  });
});
