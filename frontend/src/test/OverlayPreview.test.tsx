import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen } from '@testing-library/react';
import OverlayPreview, { OverlayPreviewProps } from '../components/OverlayPreview';
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
    const props = { x: 0, y: 0, width: 30, height: 10, layoutId: '' } as unknown as OverlayPreviewProps;
    const { container } = renderWithI18n(<OverlayPreview {...props} />);
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
    // 16:9 box (cardWidth * 9 / 16 = 168.75), matching the custom-overlay
    // path so the visual slot is the same regardless of overlay kind.
    expect(container).toHaveStyle({ width: '300px', height: '168.75px' });
  });

  it('renders the UNO preview in the same 16:9 box as a custom overlay', () => {
    // Both kinds should share the same container dimensions so the
    // scoreboard isn't squeezed into a tiny strip on UNO previews.
    renderWithI18n(
      <OverlayPreview
        overlayUrl="https://overlays.uno/output/abc"
        x={-33}
        y={-41}
        width={30}
        height={10}
        layoutId="some-layout"
        cardWidth={400}
      />
    );
    const uno = screen.getByTestId('overlay-preview').closest('.preview-container');
    expect(uno).toHaveStyle({ width: '400px', height: '225px' });
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

  // Scheme validation: the iframe src is derived from overlayUrl, so any
  // non-http(s) scheme must be rejected before it reaches the DOM.
  it.each([
    'javascript:alert(1)',
    'data:text/html,<script>1</script>',
    'file:///etc/passwd',
    'vbscript:msgbox(1)',
  ])('renders nothing for unsafe overlayUrl: %s', (unsafe) => {
    const { container } = renderWithI18n(
      <OverlayPreview
        overlayUrl={unsafe}
        x={0}
        y={0}
        width={30}
        height={10}
        layoutId=""
        cardWidth={300}
      />
    );
    expect(container.innerHTML).toBe('');
  });

  // Domain-spoof guard: a hostname that merely ends with 'overlays.uno'
  // (e.g. 'evil-overlays.uno') must not be treated as the real Uno overlay.
  it('treats evil-overlays.uno as a custom overlay, not Uno', () => {
    renderWithI18n(
      <OverlayPreview
        overlayUrl="https://evil-overlays.uno/output/abc"
        x={0}
        y={0}
        width={30}
        height={10}
        layoutId=""
        cardWidth={300}
      />
    );
    const iframe = screen.getByTestId('overlay-preview');
    // Custom path renders at 1920x1080; Uno path would be 600x...
    expect(iframe.getAttribute('width')).toBe('1920');
  });
});
