import { describe, it, expect, vi } from 'vitest';
import { screen } from '@testing-library/react';
import OverlaySection from '../components/config/OverlaySection';
import { renderWithI18n } from './helpers';
import type { StyleCapabilities } from '../api/client';

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
  default: { theme: false, verticalAnchor: false },
  pylons: { theme: true, verticalAnchor: true },
  neon: { theme: true, verticalAnchor: false },
};

describe('OverlaySection capability gating', () => {
  it('hides the theme selector for the default style', () => {
    render({ preferredStyle: '' }, CAPS);
    expect(screen.getByTestId('style-selector')).toBeInTheDocument();
    expect(screen.queryByTestId('overlay-theme-selector')).not.toBeInTheDocument();
  });

  it('shows the theme selector for themed styles', () => {
    render({ preferredStyle: 'pylons' }, CAPS);
    expect(screen.getByTestId('overlay-theme-selector')).toBeInTheDocument();
  });

  it('never renders a vertical-anchor knob (placement lives in the Position section)', () => {
    render({ preferredStyle: 'pylons' }, CAPS);
    expect(screen.queryByTestId('vertical-anchor-selector')).not.toBeInTheDocument();
  });

  it('falls back to no special knobs when capabilities are unknown', () => {
    render({ preferredStyle: 'pylons' }, {});
    expect(screen.queryByTestId('overlay-theme-selector')).not.toBeInTheDocument();
  });
});
