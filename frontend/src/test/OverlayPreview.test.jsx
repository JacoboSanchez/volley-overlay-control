import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import React from 'react';
import OverlayPreview from '../components/OverlayPreview';
import { renderWithI18n } from './helpers';

describe('OverlayPreview', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('returns null when overlayUrl is empty', () => {
    const { container } = renderWithI18n(
      <OverlayPreview overlayUrl="" x={0} y={0} width={30} height={10} layoutId="" />
    );
    expect(container.innerHTML).toBe('');
  });

  it('returns null when overlayUrl is not provided', () => {
    const { container } = renderWithI18n(
      <OverlayPreview x={0} y={0} width={30} height={10} layoutId="" />
    );
    expect(container.innerHTML).toBe('');
  });

  it('renders standard overlay iframe for overlays.uno URL', () => {
    renderWithI18n(
      <OverlayPreview
        overlayUrl="https://overlays.uno/output/abc"
        x={-33}
        y={-41}
        width={30}
        height={10}
        layoutId="some-layout"
        cardWidth={300}
      />
    );
    const iframe = screen.getByTestId('overlay-preview');
    expect(iframe).toBeInTheDocument();
    expect(iframe.getAttribute('src')).toContain('overlays.uno');
    expect(iframe.getAttribute('src')).toMatch(/aspect=16[:%]3A9/);
  });

  it('renders custom overlay iframe for non-overlays.uno URL', () => {
    renderWithI18n(
      <OverlayPreview
        overlayUrl="https://custom.example.com/overlay"
        x={0}
        y={0}
        width={30}
        height={10}
        layoutId="auto"
        cardWidth={300}
      />
    );
    const iframe = screen.getByTestId('overlay-preview');
    expect(iframe).toBeInTheDocument();
    expect(iframe.getAttribute('src')).toContain('https://custom.example.com/overlay');
    expect(iframe.getAttribute('src')).toMatch(/_t=\d+/);
  });

  it('renders custom overlay for C- prefixed layoutId', () => {
    renderWithI18n(
      <OverlayPreview
        overlayUrl="https://overlays.uno/output/abc"
        x={0}
        y={0}
        width={30}
        height={10}
        layoutId="C-custom-layout"
        cardWidth={300}
      />
    );
    const iframe = screen.getByTestId('overlay-preview');
    expect(iframe.getAttribute('src')).toContain('https://overlays.uno/output/abc');
    expect(iframe.getAttribute('src')).toMatch(/_t=\d+/);
  });

  it('sets sandbox and allowTransparency on iframe', () => {
    renderWithI18n(
      <OverlayPreview
        overlayUrl="https://overlays.uno/output/abc"
        x={0}
        y={0}
        width={30}
        height={10}
        layoutId=""
        cardWidth={300}
      />
    );
    const iframe = screen.getByTestId('overlay-preview');
    expect(iframe.getAttribute('sandbox')).toBe('allow-scripts allow-same-origin');
    expect(iframe.getAttribute('allowTransparency')).toBe('true');
  });

  it('uses default cardWidth of 300', () => {
    renderWithI18n(
      <OverlayPreview
        overlayUrl="https://overlays.uno/output/abc"
        x={0}
        y={0}
        width={30}
        height={10}
        layoutId=""
      />
    );
    const container = screen.getByTestId('overlay-preview').closest('.preview-container');
    expect(container).toHaveStyle({ width: '300px', height: '50px' });
  });

  it('appends aspect param with & when URL already has query params', () => {
    renderWithI18n(
      <OverlayPreview
        overlayUrl="https://overlays.uno/output/abc?token=xyz"
        x={0}
        y={0}
        width={30}
        height={10}
        layoutId=""
        cardWidth={300}
      />
    );
    const iframe = screen.getByTestId('overlay-preview');
    expect(iframe.getAttribute('src')).toContain('token=xyz');
    expect(iframe.getAttribute('src')).toMatch(/aspect=16[:%]3A9/);
    expect(iframe.getAttribute('src')).toMatch(/_t=\d+/);
  });

  it('custom overlay iframe has 1920x1080 dimensions', () => {
    renderWithI18n(
      <OverlayPreview
        overlayUrl="https://custom.example.com/overlay"
        x={0}
        y={0}
        width={30}
        height={10}
        layoutId="auto"
        cardWidth={300}
      />
    );
    const iframe = screen.getByTestId('overlay-preview');
    expect(iframe.getAttribute('width')).toBe('1920');
    expect(iframe.getAttribute('height')).toBe('1080');
  });
});
