import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import PreviewApp from '../PreviewApp';

function setLocation(search: string, pathname = '/preview') {
  window.history.replaceState({}, '', `${pathname}${search}`);
}

describe('PreviewApp', () => {
  beforeEach(() => {
    setLocation('');
  });

  afterEach(() => {
    setLocation('', '/');
  });

  it('shows missing-output message when output param is absent', () => {
    setLocation('');
    render(<PreviewApp />);
    expect(screen.getByText(/no overlay output/i)).toBeInTheDocument();
  });

  it('renders OverlayPreview iframe when output param is provided', () => {
    setLocation(
      '?output=https%3A%2F%2Foverlays.uno%2Foutput%2Fabc&x=-33&y=-41&width=30&height=10&layout_id=lyt',
    );
    render(<PreviewApp />);
    const iframe = screen.getByTestId('overlay-preview');
    expect(iframe.getAttribute('src')).toContain('overlays.uno/output/abc');
  });

  it('renders the toolbar with zoom, theme and fullscreen controls', () => {
    setLocation(
      '?output=https%3A%2F%2Foverlays.uno%2Foutput%2Fabc&x=0&y=0&width=30&height=10',
    );
    render(<PreviewApp />);
    const toolbar = screen.getByTestId('preview-toolbar');
    expect(toolbar).toBeInTheDocument();
    expect(toolbar.querySelectorAll('button').length).toBe(4);
  });

  it('toggles backdrop class when light/dark button is clicked', async () => {
    setLocation(
      '?output=https%3A%2F%2Foverlays.uno%2Foutput%2Fabc&x=0&y=0&width=30&height=10',
    );
    const { container } = render(<PreviewApp />);
    const page = container.querySelector('.preview-page') as HTMLElement;
    expect(page.classList.contains('preview-page--dark')).toBe(true);

    const themeBtn = screen.getByLabelText(/light mode/i);
    await userEvent.click(themeBtn);
    expect(page.classList.contains('preview-page--light')).toBe(true);
  });

  it('hides the style selector when styles param is absent', () => {
    setLocation(
      '?output=https%3A%2F%2Fcustom.example.com%2Foverlay&x=0&y=0&width=100&height=100&layout_id=auto',
    );
    render(<PreviewApp />);
    expect(screen.queryByTestId('preview-style-selector')).toBeNull();
  });

  it('hides the style selector when only one style is available', () => {
    setLocation(
      '?output=https%3A%2F%2Fcustom.example.com%2Foverlay&x=0&y=0&width=100&height=100&layout_id=auto&styles=only',
    );
    render(<PreviewApp />);
    expect(screen.queryByTestId('preview-style-selector')).toBeNull();
  });

  it('shows the style selector and applies the override to the iframe URL', async () => {
    setLocation(
      '?output=https%3A%2F%2Fcustom.example.com%2Foverlay&x=0&y=0&width=100&height=100&layout_id=auto&styles=pill,glass,default',
    );
    render(<PreviewApp />);
    const select = screen.getByTestId('preview-style-selector') as HTMLSelectElement;
    expect(select).toBeInTheDocument();

    const optionValues = Array.from(select.querySelectorAll('option')).map(
      (o) => (o as HTMLOptionElement).value,
    );
    expect(optionValues).toEqual(['', 'pill', 'glass', 'default']);

    const iframe = screen.getByTestId('overlay-preview');
    expect(iframe.getAttribute('src')).not.toMatch(/[?&]style=/);

    await userEvent.selectOptions(select, 'glass');
    expect(iframe.getAttribute('src')).toMatch(/[?&]style=glass\b/);
  });

  it('initializes the style override from the style query param when valid', () => {
    setLocation(
      '?output=https%3A%2F%2Fcustom.example.com%2Foverlay&x=0&y=0&width=100&height=100&layout_id=auto&styles=pill,glass,default&style=glass',
    );
    render(<PreviewApp />);
    const select = screen.getByTestId('preview-style-selector') as HTMLSelectElement;
    expect(select.value).toBe('glass');
    const iframe = screen.getByTestId('overlay-preview');
    expect(iframe.getAttribute('src')).toMatch(/[?&]style=glass\b/);
  });

  it('ignores style query param when not in the advertised list', () => {
    setLocation(
      '?output=https%3A%2F%2Fcustom.example.com%2Foverlay&x=0&y=0&width=100&height=100&layout_id=auto&styles=pill,glass,default&style=bogus',
    );
    render(<PreviewApp />);
    const select = screen.getByTestId('preview-style-selector') as HTMLSelectElement;
    expect(select.value).toBe('');
    const iframe = screen.getByTestId('overlay-preview');
    expect(iframe.getAttribute('src')).not.toMatch(/[?&]style=/);
  });
});
