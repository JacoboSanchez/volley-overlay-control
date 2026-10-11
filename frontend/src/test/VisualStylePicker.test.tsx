import { describe, it, expect, vi, afterEach } from 'vitest';
import { act, fireEvent, screen, within } from '@testing-library/react';
import { renderWithI18n } from './helpers';
import VisualStylePicker from '../components/VisualStylePicker';
import SetSummaryStylePicker from '../components/SetSummaryStylePicker';
import { SET_SUMMARY_STYLES } from '../api/board';
import { ScopedStorageProvider, setScopedItem, getScopedItem } from '../storage/ScopedStorage';
import { OVERLAY_CATEGORIES, stylePresentation } from '../styles/catalog';
import { translations } from '../i18n/translations';

afterEach(() => vi.unstubAllGlobals());

function renderPicker(onChange = vi.fn()) {
  renderWithI18n(
    <VisualStylePicker
      kind="overlay"
      value="default"
      styles={['default', 'neon', 'compact', 'corner_jersey', 'custom_style']}
      onChange={onChange}
      testId="styles"
    />,
  );
  fireEvent.click(screen.getByRole('button', { name: /Choose a scoreboard:/ }));
  return onChange;
}

describe('Visual style gallery', () => {
  it('renders configured thumbnails only while visible and keeps a single enlarged preview', () => {
    const observers: { target: Element; visible: (visible: boolean) => void }[] = [];
    const disconnect = vi.fn();
    vi.stubGlobal(
      'IntersectionObserver',
      class {
        constructor(private callback: (entries: { isIntersecting: boolean }[]) => void) {}
        observe(target: Element) {
          observers.push({
            target,
            visible: (visible) => this.callback([{ isIntersecting: visible }]),
          });
        }
        disconnect = disconnect;
      },
    );
    const change = vi.fn();
    renderWithI18n(
      <VisualStylePicker
        kind="overlay"
        value="default"
        styles={['default', 'neon']}
        onChange={change}
        testId="styles"
        configuration={{ 'Team 1 Name': 'Berlin VC', 'Team 2 Name': 'Hamburg' }}
      />,
    );
    expect(document.querySelectorAll('iframe')).toHaveLength(0);
    fireEvent.click(screen.getByRole('button', { name: /Choose a scoreboard:/ }));
    const card = screen.getByTestId('overlay-style-neon');
    const observer = observers.find(({ target }) => card.contains(target))!;
    expect(observer).toBeDefined();
    act(() => observer.visible(true));
    const thumbnail = within(card).getByTestId('style-thumbnail-overlay-neon') as HTMLIFrameElement;
    const send = vi.spyOn(thumbnail.contentWindow!, 'postMessage');
    fireEvent.load(thumbnail);
    expect(send).toHaveBeenCalledWith(
      expect.objectContaining({
        appearance: expect.objectContaining({
          team_home: expect.objectContaining({ name: 'Berlin VC' }),
        }),
      }),
      window.location.origin,
    );
    expect(thumbnail).toHaveAttribute('tabindex', '-1');
    expect(document.querySelectorAll('iframe')).toHaveLength(2);
    act(() => observer.visible(false));
    expect(card.querySelector('iframe')).toBeNull();
    expect(document.querySelectorAll('iframe')).toHaveLength(1);
    expect(change).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(disconnect).toHaveBeenCalled();
  });

  it('previews a local candidate in a single iframe and only confirms explicitly', () => {
    const change = renderPicker();
    fireEvent.click(screen.getByTestId('overlay-style-neon'));
    expect(change).not.toHaveBeenCalled();
    expect(document.querySelectorAll('iframe')).toHaveLength(1);
    expect(screen.getByTestId('overlay-preview').getAttribute('src')).toContain(
      '/overlay-preview/neon?',
    );
    fireEvent.click(screen.getByTestId('style-picker-apply'));
    expect(change).toHaveBeenCalledExactlyOnceWith('neon');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(document.querySelectorAll('iframe')).toHaveLength(0);
    expect(screen.getByRole('button', { name: /Choose a scoreboard:/ })).toHaveFocus();
  });

  it('cancel and Escape discard a candidate and reopen at the current value', () => {
    const change = renderPicker();
    fireEvent.click(screen.getByTestId('overlay-style-neon'));
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    fireEvent.click(screen.getByRole('button', { name: /Choose a scoreboard:/ }));
    expect(screen.getByTestId('overlay-style-default')).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(screen.getByTestId('overlay-style-compact'));
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(change).not.toHaveBeenCalled();
    expect(getScopedItem('guest', 'recent-styles-overlay')).toBeNull();
  });

  it('filters by category without changing the selected candidate', () => {
    const change = renderPicker();
    fireEvent.click(screen.getByRole('button', { name: 'Jerseys' }));
    expect(screen.getByTestId('overlay-style-corner_jersey')).toBeInTheDocument();
    expect(screen.queryByTestId('overlay-style-neon')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'All' }));
    expect(screen.getByTestId('overlay-style-default')).toHaveAttribute('aria-pressed', 'true');
    fireEvent.click(screen.getByTestId('style-picker-apply'));
    expect(change).not.toHaveBeenCalled();
  });

  it('offers a native quick list whose changes also require confirmation', () => {
    const change = renderPicker();
    fireEvent.click(screen.getByRole('button', { name: 'Quick selection' }));
    const select = screen.getByRole('combobox');
    expect(within(select).getAllByRole('option')).toHaveLength(5);
    fireEvent.change(select, { target: { value: 'compact' } });
    expect(change).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId('style-picker-apply'));
    expect(change).toHaveBeenCalledExactlyOnceWith('compact');
  });

  it('handles unknown custom styles without loading a broken renderer or thumbnail', () => {
    const change = renderPicker();
    fireEvent.click(screen.getByTestId('overlay-style-custom_style'));
    expect(screen.getByText('Preview unavailable')).toBeInTheDocument();
    expect(document.querySelector('iframe')).toBeNull();
    fireEvent.click(screen.getByTestId('style-picker-apply'));
    expect(change).toHaveBeenCalledExactlyOnceWith('custom_style');
  });

  it('keeps recent choices scoped to the account and ranks current first', () => {
    setScopedItem('user:a', 'recent-styles-overlay', JSON.stringify(['compact', 'neon']));
    setScopedItem('user:b', 'recent-styles-overlay', JSON.stringify(['neon']));
    renderWithI18n(
      <ScopedStorageProvider scope="user:a">
        <VisualStylePicker
          kind="overlay"
          value="default"
          styles={['neon', 'compact', 'default']}
          onChange={() => {}}
          testId="styles"
        />
      </ScopedStorageProvider>,
    );
    fireEvent.click(screen.getByRole('button', { name: /Choose a scoreboard:/ }));
    const options = document.querySelectorAll('.style-gallery-option');
    expect(Array.from(options, (el) => el.getAttribute('data-testid'))).toEqual([
      'overlay-style-default',
      'overlay-style-compact',
      'overlay-style-neon',
    ]);
    fireEvent.click(screen.getByTestId('overlay-style-compact'));
    fireEvent.click(screen.getByTestId('style-picker-apply'));
    expect(getScopedItem('user:b', 'recent-styles-overlay')).toBe('["neon"]');
    expect(getScopedItem('guest', 'recent-styles-overlay')).toBeNull();
  });

  it('recovers from malformed or unavailable browser storage', () => {
    setScopedItem('guest', 'recent-styles-overlay', '{bad json');
    const change = renderPicker();
    fireEvent.click(screen.getByTestId('overlay-style-neon'));
    vi.mocked(localStorage.setItem).mockImplementationOnce(() => {
      throw new Error('full');
    });
    fireEvent.click(screen.getByTestId('style-picker-apply'));
    expect(change).toHaveBeenCalledExactlyOnceWith('neon');
  });
});

describe('Set summary gallery', () => {
  it('keeps static fallbacks when the configured custom scoreboard cannot be previewed', () => {
    const observe = vi.fn();
    vi.stubGlobal(
      'IntersectionObserver',
      class {
        observe = observe;
        disconnect() {}
      },
    );
    renderWithI18n(
      <SetSummaryStylePicker
        value="brand_ledger"
        onChange={() => {}}
        overlayStyle="custom_style"
        configuration={{ 'Team 1 Name': 'Berlin VC' }}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /Choose a set summary:/ }));
    expect(screen.getByText('Preview unavailable')).toBeInTheDocument();
    expect(observe).not.toHaveBeenCalled();
    expect(document.querySelectorAll('iframe')).toHaveLength(0);
  });

  it('shows six designs, inherits the scoreboard palette and confirms once', () => {
    const change = vi.fn();
    renderWithI18n(
      <SetSummaryStylePicker
        value="brand_ledger"
        onChange={change}
        overlayStyle="broadcast"
        overlayTheme="dark"
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /Choose a set summary:/ }));
    for (const id of SET_SUMMARY_STYLES)
      expect(screen.getByTestId(`summary-style-${id}`)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'All' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId('summary-style-bento'));
    const url = new URL(screen.getByTestId('overlay-preview').getAttribute('src')!);
    expect(url.pathname).toBe('/overlay-preview/broadcast');
    expect(url.searchParams.get('summary')).toBe('bento');
    expect(url.searchParams.get('theme')).toBe('dark');
    expect(change).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId('style-picker-apply'));
    expect(change).toHaveBeenCalledExactlyOnceWith('bento');
  });

  it('cannot open when disabled', () => {
    renderWithI18n(<SetSummaryStylePicker value="bento" onChange={() => {}} disabled />);
    const trigger = screen.getByRole('button', { name: /Choose a set summary:/ });
    expect(trigger).toBeDisabled();
    fireEvent.click(trigger);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('does not emit an action when the current summary is confirmed', () => {
    const change = vi.fn();
    renderWithI18n(<SetSummaryStylePicker value="bento" onChange={change} />);
    fireEvent.click(screen.getByRole('button', { name: /Choose a set summary:/ }));
    fireEvent.click(screen.getByTestId('style-picker-apply'));
    expect(change).not.toHaveBeenCalled();
  });
});

it('provides a name and description for all 33 designs in every UI language', () => {
  expect(Object.keys(OVERLAY_CATEGORIES)).toHaveLength(27);
  for (const dict of Object.values(translations)) {
    for (const [kind, styles] of [
      ['overlay', Object.keys(OVERLAY_CATEGORIES)],
      ['summary', SET_SUMMARY_STYLES],
    ] as const) {
      for (const id of styles) {
        const presentation = stylePresentation(kind, id, (key) => dict[key] ?? key);
        expect(presentation.name).not.toContain('styleCatalog.');
        expect(presentation.description).not.toContain('styleCatalog.');
      }
    }
  }
});
