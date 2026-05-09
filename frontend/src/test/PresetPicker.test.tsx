import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { screen, fireEvent, waitFor } from '@testing-library/react';
import PresetPicker from '../components/PresetPicker';
import * as api from '../api/client';
import type { PresetOption } from '../api/client';
import { renderWithI18n } from './helpers';

vi.mock('../api/client', () => ({
  getPresetOptions: vi.fn(),
}));

const ENV_THEME: PresetOption = {
  source: 'env',
  id: 'theme:dark',
  name: 'dark',
  scopes: ['overlay_colors'],
  patch: { 'Color 1': '#000', 'Text Color 1': '#fff' },
  read_only: true,
};

const USER_PRESET: PresetOption = {
  source: 'user',
  id: 'preset:default-position',
  name: 'Default Position',
  scopes: ['overlay_layout'],
  patch: { Height: 12, Width: 35 },
  read_only: false,
};

describe('PresetPicker', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
  });

  afterEach(() => {
    window.localStorage.clear();
  });

  it('shows env-var themes under "Predefined" with a read-only badge', async () => {
    vi.mocked(api.getPresetOptions).mockResolvedValue({ items: [ENV_THEME] });
    renderWithI18n(
      <PresetPicker oid="op-1" onApplyPatch={vi.fn()} />,
    );
    await waitFor(() =>
      expect(screen.getByTestId('preset-group-predefined')).toBeInTheDocument(),
    );
    expect(screen.queryByTestId('preset-group-yours')).toBeNull();
    expect(screen.getByText('dark')).toBeInTheDocument();
    expect(screen.getByText('Read-only')).toBeInTheDocument();
  });

  it('shows user presets under "Yours" without the badge', async () => {
    vi.mocked(api.getPresetOptions).mockResolvedValue({ items: [USER_PRESET] });
    renderWithI18n(
      <PresetPicker oid="op-1" onApplyPatch={vi.fn()} />,
    );
    await waitFor(() =>
      expect(screen.getByTestId('preset-group-yours')).toBeInTheDocument(),
    );
    expect(screen.queryByTestId('preset-group-predefined')).toBeNull();
    expect(screen.getByText('Default Position')).toBeInTheDocument();
    expect(screen.queryByText('Read-only')).toBeNull();
  });

  it('renders both groups when the feed mixes env + user', async () => {
    vi.mocked(api.getPresetOptions).mockResolvedValue({
      items: [ENV_THEME, USER_PRESET],
    });
    renderWithI18n(
      <PresetPicker oid="op-1" onApplyPatch={vi.fn()} />,
    );
    await waitFor(() => {
      expect(screen.getByTestId('preset-group-predefined')).toBeInTheDocument();
      expect(screen.getByTestId('preset-group-yours')).toBeInTheDocument();
    });
  });

  it('renders the empty-state when the feed has no items', async () => {
    vi.mocked(api.getPresetOptions).mockResolvedValue({ items: [] });
    renderWithI18n(
      <PresetPicker oid="op-1" onApplyPatch={vi.fn()} />,
    );
    await waitFor(() =>
      expect(screen.getByTestId('preset-picker')).toHaveClass(
        'preset-picker-empty',
      ),
    );
    expect(screen.getByText(/No presets available/i)).toBeInTheDocument();
    expect(screen.getByText(/admin/i)).toBeInTheDocument();
  });

  it('passes the patch to onApplyPatch when an item is applied', async () => {
    vi.mocked(api.getPresetOptions).mockResolvedValue({ items: [USER_PRESET] });
    const onApplyPatch = vi.fn();
    renderWithI18n(
      <PresetPicker oid="op-1" onApplyPatch={onApplyPatch} />,
    );
    await waitFor(() =>
      expect(
        screen.getByTestId('preset-apply-preset:default-position'),
      ).toBeInTheDocument(),
    );
    fireEvent.click(
      screen.getByTestId('preset-apply-preset:default-position'),
    );
    expect(onApplyPatch).toHaveBeenCalledWith({ Height: 12, Width: 35 });
  });

  it('persists the last-applied preset id per OID in localStorage', async () => {
    vi.mocked(api.getPresetOptions).mockResolvedValue({ items: [USER_PRESET] });
    renderWithI18n(
      <PresetPicker oid="op-1" onApplyPatch={vi.fn()} />,
    );
    await waitFor(() =>
      expect(
        screen.getByTestId('preset-apply-preset:default-position'),
      ).toBeInTheDocument(),
    );
    fireEvent.click(
      screen.getByTestId('preset-apply-preset:default-position'),
    );
    expect(window.localStorage.getItem('volley_last_preset:op-1')).toBe(
      'preset:default-position',
    );
    // The pill renders the human-readable name from the live feed,
    // not the raw id, via i18n interpolation (``Last applied: {name}``).
    expect(screen.getByTestId('preset-picker-last')).toHaveTextContent(
      'Default Position',
    );
    expect(screen.getByTestId('preset-picker-last')).not.toHaveTextContent(
      'preset:default-position',
    );
  });

  it('falls back to the raw id when the last-applied entry is no longer in the feed', async () => {
    window.localStorage.setItem(
      'volley_last_preset:op-1',
      'preset:legacy-but-deleted',
    );
    vi.mocked(api.getPresetOptions).mockResolvedValue({ items: [USER_PRESET] });
    renderWithI18n(
      <PresetPicker oid="op-1" onApplyPatch={vi.fn()} />,
    );
    await waitFor(() =>
      expect(screen.getByTestId('preset-picker-last')).toBeInTheDocument(),
    );
    // Lookup misses → render the id verbatim so the operator at least
    // sees something stable, not an empty pill.
    expect(screen.getByTestId('preset-picker-last')).toHaveTextContent(
      'preset:legacy-but-deleted',
    );
  });

  it('renders the loading state while the request is in flight', async () => {
    let resolve!: (v: { items: PresetOption[] }) => void;
    vi.mocked(api.getPresetOptions).mockReturnValue(
      new Promise((r) => {
        resolve = r;
      }),
    );
    renderWithI18n(
      <PresetPicker oid="op-1" onApplyPatch={vi.fn()} />,
    );
    expect(screen.getByTestId('preset-picker')).toHaveClass(
      'preset-picker-loading',
    );
    resolve({ items: [USER_PRESET] });
    await waitFor(() =>
      expect(screen.getByTestId('preset-picker')).not.toHaveClass(
        'preset-picker-loading',
      ),
    );
  });

  it('surfaces a load error', async () => {
    vi.mocked(api.getPresetOptions).mockRejectedValue(new Error('502'));
    renderWithI18n(
      <PresetPicker oid="op-1" onApplyPatch={vi.fn()} />,
    );
    await waitFor(() =>
      expect(screen.getByTestId('preset-picker')).toHaveClass(
        'preset-picker-error',
      ),
    );
    expect(screen.getByText(/502/)).toBeInTheDocument();
  });
});
