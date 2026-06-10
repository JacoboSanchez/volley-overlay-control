import { describe, it, expect, vi } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import ShortcutsHelp from '../components/ShortcutsHelp';
import { renderWithI18n } from './helpers';

describe('ShortcutsHelp', () => {
  it('renders nothing when closed', () => {
    renderWithI18n(<ShortcutsHelp open={false} onClose={() => {}} />);
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('lists every shortcut binding with its label when open', () => {
    renderWithI18n(<ShortcutsHelp open onClose={() => {}} />);
    expect(screen.getByRole('dialog')).toHaveAccessibleName('Keyboard shortcuts');
    expect(screen.getByText('Keyboard shortcuts')).toBeInTheDocument();
    // One table row per binding (see ROWS in the component).
    const rows = screen.getByRole('table').querySelectorAll('tr');
    expect(rows).toHaveLength(11);
    // Dual-key bindings render both keys with a separator.
    const firstRow = rows[0]!;
    expect(firstRow.querySelectorAll('kbd')).toHaveLength(2);
    expect(firstRow.textContent).toContain('/');
  });

  it('renders the space key as a visible glyph and letters uppercased', () => {
    renderWithI18n(<ShortcutsHelp open onClose={() => {}} />);
    const keys = Array.from(document.querySelectorAll('kbd')).map((el) => el.textContent);
    expect(keys).toContain('␣'); // startMatch is bound to Space
    expect(keys).toContain('A');
    expect(keys).toContain('?');
    expect(keys).not.toContain('a');
  });

  it('fires onClose from the OK button', () => {
    const onClose = vi.fn();
    renderWithI18n(<ShortcutsHelp open onClose={onClose} />);
    fireEvent.click(screen.getByRole('button', { name: 'OK' }));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it('fires onClose on Escape via the dialog primitive', () => {
    const onClose = vi.fn();
    renderWithI18n(<ShortcutsHelp open onClose={onClose} />);
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalledOnce();
  });
});
