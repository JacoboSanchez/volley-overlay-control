import { describe, it, expect, vi } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
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
      isCustomOverlay
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
  it('hides theme and vertical-anchor for the default style', () => {
    render({ preferredStyle: '' }, CAPS);
    expect(screen.getByTestId('style-selector')).toBeInTheDocument();
    expect(screen.queryByTestId('overlay-theme-selector')).not.toBeInTheDocument();
    expect(screen.queryByTestId('vertical-anchor-selector')).not.toBeInTheDocument();
  });

  it('shows both knobs for an edge-pinned themed style (pylons)', () => {
    render({ preferredStyle: 'pylons' }, CAPS);
    expect(screen.getByTestId('overlay-theme-selector')).toBeInTheDocument();
    expect(screen.getByTestId('vertical-anchor-selector')).toBeInTheDocument();
  });

  it('shows theme but not vertical-anchor for a themed geometry style (neon)', () => {
    render({ preferredStyle: 'neon' }, CAPS);
    expect(screen.getByTestId('overlay-theme-selector')).toBeInTheDocument();
    expect(screen.queryByTestId('vertical-anchor-selector')).not.toBeInTheDocument();
  });

  it('persists the chosen vertical anchor via updateField', () => {
    const updateField = render({ preferredStyle: 'pylons' }, CAPS);
    fireEvent.change(screen.getByTestId('vertical-anchor-selector'), {
      target: { value: 'top' },
    });
    expect(updateField).toHaveBeenCalledWith('verticalAnchor', 'top');
  });

  it('falls back to no special knobs when capabilities are unknown', () => {
    render({ preferredStyle: 'pylons' }, {});
    expect(screen.queryByTestId('overlay-theme-selector')).not.toBeInTheDocument();
    expect(screen.queryByTestId('vertical-anchor-selector')).not.toBeInTheDocument();
  });
});
