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
});
