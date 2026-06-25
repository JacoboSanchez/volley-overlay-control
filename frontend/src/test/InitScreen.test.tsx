import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent, waitFor } from '@testing-library/react';
import InitScreen, { InitScreenProps } from '../components/InitScreen';
import * as api from '../api/client';
import type { OverlayPayload } from '../api/client';
import { renderWithI18n } from './helpers';

vi.mock('../api/client', () => ({
  getOverlays: vi.fn(),
}));

function makeProps(overrides: Partial<InitScreenProps> = {}): InitScreenProps {
  return {
    oidInput: '',
    setOidInput: vi.fn(),
    onSubmit: vi.fn((e) => e.preventDefault()),
    onSelect: vi.fn(),
    ...overrides,
  };
}

describe('InitScreen', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.getOverlays).mockResolvedValue([]);
  });

  it('renders the default app title and OID form', () => {
    renderWithI18n(<InitScreen {...makeProps()} />);
    expect(screen.getByRole('heading', { name: 'Volley Scoreboard' })).toBeInTheDocument();
    expect(screen.getByPlaceholderText('my-overlay')).toBeInTheDocument();
  });

  it('renders a custom title when provided', () => {
    renderWithI18n(<InitScreen {...makeProps({ title: 'My Tournament' })} />);
    expect(screen.getByRole('heading', { name: 'My Tournament' })).toBeInTheDocument();
  });

  it('forwards typing to setOidInput', () => {
    const props = makeProps();
    renderWithI18n(<InitScreen {...props} />);
    fireEvent.change(screen.getByPlaceholderText('my-overlay'), {
      target: { value: 'my-match' },
    });
    expect(props.setOidInput).toHaveBeenCalledWith('my-match');
  });

  it('disables Connect while the input is blank or whitespace', () => {
    const { unmount } = renderWithI18n(<InitScreen {...makeProps({ oidInput: '   ' })} />);
    expect(screen.getByRole('button', { name: 'Connect' })).toBeDisabled();
    unmount();
    renderWithI18n(<InitScreen {...makeProps({ oidInput: 'abc' })} />);
    expect(screen.getByRole('button', { name: 'Connect' })).toBeEnabled();
  });

  it('submits the form via the Connect button', () => {
    const props = makeProps({ oidInput: 'my-match' });
    renderWithI18n(<InitScreen {...props} />);
    fireEvent.click(screen.getByRole('button', { name: 'Connect' }));
    expect(props.onSubmit).toHaveBeenCalledOnce();
  });

  it('shows the error message when provided', () => {
    renderWithI18n(<InitScreen {...makeProps({ error: 'Session not found' })} />);
    expect(screen.getByText('Session not found')).toBeInTheDocument();
  });

  it('hides the overlay selector when no predefined overlays exist', async () => {
    renderWithI18n(<InitScreen {...makeProps()} />);
    await waitFor(() => expect(api.getOverlays).toHaveBeenCalled());
    expect(screen.queryByRole('combobox')).toBeNull();
  });

  it('lists predefined overlays and fires onSelect when one is picked', async () => {
    vi.mocked(api.getOverlays).mockResolvedValue([
      { oid: 'oid-a', name: 'Court A' },
      { oid: 'oid-b', name: 'Court B' },
    ] as unknown as OverlayPayload[]);
    const props = makeProps();
    renderWithI18n(<InitScreen {...props} />);
    const select = await screen.findByRole('combobox');
    expect(screen.getByRole('option', { name: 'Court A' })).toBeInTheDocument();
    expect(screen.getByText('or enter OID manually')).toBeInTheDocument();

    fireEvent.change(select, { target: { value: 'oid-b' } });
    expect(props.setOidInput).toHaveBeenCalledWith('oid-b');
    expect(props.onSelect).toHaveBeenCalledWith('oid-b');
  });

  it('does not fire onSelect when the placeholder option is re-picked', async () => {
    vi.mocked(api.getOverlays).mockResolvedValue([
      { oid: 'oid-a', name: 'Court A' },
    ] as unknown as OverlayPayload[]);
    const props = makeProps();
    renderWithI18n(<InitScreen {...props} />);
    const select = await screen.findByRole('combobox');
    fireEvent.change(select, { target: { value: '' } });
    expect(props.setOidInput).toHaveBeenCalledWith('');
    expect(props.onSelect).not.toHaveBeenCalled();
  });

  it('normalizes name→oid object maps and bare-string entries', async () => {
    vi.mocked(api.getOverlays).mockResolvedValue({
      'Beach Court': 'oid-beach',
      broken: 42,
    } as unknown as OverlayPayload[]);
    renderWithI18n(<InitScreen {...makeProps()} />);
    expect(await screen.findByRole('option', { name: 'Beach Court' })).toHaveValue('oid-beach');
    // Non-string oid entry is dropped.
    expect(screen.queryByRole('option', { name: 'broken' })).toBeNull();

    vi.mocked(api.getOverlays).mockResolvedValue([
      'plain-oid',
      { oid: '', name: 'no oid' },
      { name: 'missing oid' },
    ] as unknown as OverlayPayload[]);
    renderWithI18n(<InitScreen {...makeProps()} />);
    // Bare strings become both name and oid; invalid entries are dropped.
    expect(await screen.findByRole('option', { name: 'plain-oid' })).toHaveValue('plain-oid');
    expect(screen.queryByText('no oid')).toBeNull();
    expect(screen.queryByText('missing oid')).toBeNull();
  });

  it('keeps the manual form usable when the overlays fetch fails', async () => {
    vi.mocked(api.getOverlays).mockRejectedValue(new Error('boom'));
    renderWithI18n(<InitScreen {...makeProps()} />);
    // The fetch failure is swallowed (no selector), but the manual id form
    // stays usable.
    await waitFor(() => expect(api.getOverlays).toHaveBeenCalled());
    expect(screen.queryByRole('combobox')).toBeNull();
    expect(screen.getByPlaceholderText('my-overlay')).toBeInTheDocument();
  });
});
