import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { screen, fireEvent, waitFor } from '@testing-library/react';
import PresetPicker from '../components/PresetPicker';
import * as api from '../api/client';
import type { PresetSummary } from '../api/client';
import { renderWithI18n } from './helpers';

vi.mock('../api/client', () => ({
  listPresets: vi.fn(),
  createPreset: vi.fn(),
  deletePreset: vi.fn(),
}));

const POSITION_PRESET: PresetSummary = {
  slug: 'court-a',
  name: 'Court A',
  created_at: 1234,
  source: 'user',
  categories: ['position'],
  values: { Height: 12, Width: 35 },
};

const TEAM_COLOR_PRESET: PresetSummary = {
  slug: 'home-colors',
  name: 'Home colors',
  created_at: 2345,
  source: 'user',
  categories: ['team1_color'],
  values: { 'Team 1 Color': '#0f0', 'Team 1 Text Color': '#000' },
};

const SYSTEM_THEME_PRESET: PresetSummary = {
  slug: 'system-bright-court',
  name: 'Bright Court',
  created_at: 0,
  source: 'system',
  categories: ['style'],
  values: { 'Color 1': '#ffffff', 'Text Color 1': '#000000' },
};

describe('PresetPicker', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('shows the empty state and the save-current toggle when no presets exist', async () => {
    vi.mocked(api.listPresets).mockResolvedValue({ items: [] });
    renderWithI18n(<PresetPicker model={{}} onApplyPatch={vi.fn()} />);
    await waitFor(() =>
      expect(screen.getByTestId('preset-picker-empty')).toBeInTheDocument(),
    );
    expect(screen.getByTestId('preset-create-toggle')).toBeInTheDocument();
  });

  it('lists presets with category chips', async () => {
    vi.mocked(api.listPresets).mockResolvedValue({
      items: [POSITION_PRESET, TEAM_COLOR_PRESET],
    });
    renderWithI18n(<PresetPicker model={{}} onApplyPatch={vi.fn()} />);
    await waitFor(() =>
      expect(screen.getByTestId('preset-item-court-a')).toBeInTheDocument(),
    );
    const courtA = screen.getByTestId('preset-item-court-a');
    expect(courtA).toHaveTextContent('Court A');
    expect(courtA).toHaveTextContent('Overlay position');
    const homeColors = screen.getByTestId('preset-item-home-colors');
    expect(homeColors).toHaveTextContent('Team 1 — color & logo');
  });

  it('passes the values to onApplyPatch when an item is applied', async () => {
    vi.mocked(api.listPresets).mockResolvedValue({ items: [POSITION_PRESET] });
    const onApplyPatch = vi.fn();
    renderWithI18n(
      <PresetPicker model={{}} onApplyPatch={onApplyPatch} />,
    );
    await waitFor(() =>
      expect(screen.getByTestId('preset-apply-court-a')).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByTestId('preset-apply-court-a'));
    expect(onApplyPatch).toHaveBeenCalledWith({ Height: 12, Width: 35 });
  });

  it('deletes a preset and refreshes the list', async () => {
    vi.mocked(api.listPresets)
      .mockResolvedValueOnce({ items: [POSITION_PRESET] })
      .mockResolvedValueOnce({ items: [] });
    vi.mocked(api.deletePreset).mockResolvedValue();
    renderWithI18n(<PresetPicker model={{}} onApplyPatch={vi.fn()} />);
    await waitFor(() =>
      expect(screen.getByTestId('preset-delete-court-a')).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByTestId('preset-delete-court-a'));
    await waitFor(() =>
      expect(api.deletePreset).toHaveBeenCalledWith('court-a'),
    );
    await waitFor(() =>
      expect(screen.getByTestId('preset-picker-empty')).toBeInTheDocument(),
    );
    expect(api.listPresets).toHaveBeenCalledTimes(2);
  });

  it('opens the create form, requires a name + at least one category, then saves', async () => {
    vi.mocked(api.listPresets)
      .mockResolvedValueOnce({ items: [] })
      .mockResolvedValueOnce({ items: [POSITION_PRESET] });
    vi.mocked(api.createPreset).mockResolvedValue(POSITION_PRESET);

    const model = { Height: 12, Width: 35, 'Up-Down': -40, 'Left-Right': -30 };
    renderWithI18n(<PresetPicker model={model} onApplyPatch={vi.fn()} />);

    await waitFor(() =>
      expect(screen.getByTestId('preset-create-toggle')).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByTestId('preset-create-toggle'));

    // Submitting empty surfaces an inline error (name + categories
    // both missing) and does NOT call the API.
    fireEvent.click(screen.getByTestId('preset-create-submit'));
    await waitFor(() =>
      expect(screen.getByTestId('preset-action-error')).toBeInTheDocument(),
    );
    expect(api.createPreset).not.toHaveBeenCalled();

    // Fill name + pick the position category, then save.
    fireEvent.change(screen.getByTestId('preset-create-name'), {
      target: { value: 'Court A' },
    });
    fireEvent.click(screen.getByTestId('preset-create-cat-position'));
    fireEvent.click(screen.getByTestId('preset-create-submit'));

    await waitFor(() => expect(api.createPreset).toHaveBeenCalledOnce());
    expect(api.createPreset).toHaveBeenCalledWith('Court A', {
      Height: 12,
      Width: 35,
      'Up-Down': -40,
      'Left-Right': -30,
    });
    // Refresh ran (initial + post-create) and the new item shows up.
    await waitFor(() =>
      expect(screen.getByTestId('preset-item-court-a')).toBeInTheDocument(),
    );
  });

  it('captures only the picked categories from the model on save', async () => {
    vi.mocked(api.listPresets)
      .mockResolvedValueOnce({ items: [] })
      .mockResolvedValueOnce({ items: [TEAM_COLOR_PRESET] });
    vi.mocked(api.createPreset).mockResolvedValue(TEAM_COLOR_PRESET);

    const model = {
      'Team 1 Name': 'Home',
      'Team 1 Color': '#0f0',
      'Team 1 Text Color': '#000',
      'Team 2 Name': 'Away',
      'Team 2 Color': '#f00',
      Height: 12,
      preferredStyle: 'esports',
    };
    renderWithI18n(<PresetPicker model={model} onApplyPatch={vi.fn()} />);
    await waitFor(() =>
      expect(screen.getByTestId('preset-create-toggle')).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByTestId('preset-create-toggle'));
    fireEvent.change(screen.getByTestId('preset-create-name'), {
      target: { value: 'Home colors' },
    });
    // Only Team 1 colour — Team 1 Name / Team 2 / position / style
    // must NOT appear in the request.
    fireEvent.click(screen.getByTestId('preset-create-cat-team1_color'));
    fireEvent.click(screen.getByTestId('preset-create-submit'));
    await waitFor(() => expect(api.createPreset).toHaveBeenCalledOnce());
    const call = vi.mocked(api.createPreset).mock.calls[0];
    expect(call).toBeDefined();
    const values = call![1];
    expect(Object.keys(values).sort()).toEqual([
      'Team 1 Color',
      'Team 1 Text Color',
    ]);
  });

  it('surfaces a load error from the API', async () => {
    vi.mocked(api.listPresets).mockRejectedValue(new Error('502 boom'));
    renderWithI18n(<PresetPicker model={{}} onApplyPatch={vi.fn()} />);
    await waitFor(() =>
      expect(screen.getByTestId('preset-picker-error')).toBeInTheDocument(),
    );
    expect(screen.getByTestId('preset-picker-error')).toHaveTextContent(/502/);
  });

  it('renders system presets with a badge and no delete button', async () => {
    vi.mocked(api.listPresets).mockResolvedValue({
      items: [SYSTEM_THEME_PRESET, POSITION_PRESET],
    });
    renderWithI18n(<PresetPicker model={{}} onApplyPatch={vi.fn()} />);
    await waitFor(() =>
      expect(
        screen.getByTestId('preset-item-system-bright-court'),
      ).toBeInTheDocument(),
    );
    // System chip is visible only on the env-driven entry.
    expect(
      screen.getByTestId('preset-system-chip-system-bright-court'),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId('preset-system-chip-court-a'),
    ).not.toBeInTheDocument();
    // Apply button works on both; delete button is suppressed for the
    // system entry but present for the user entry.
    expect(
      screen.getByTestId('preset-apply-system-bright-court'),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId('preset-delete-system-bright-court'),
    ).not.toBeInTheDocument();
    expect(screen.getByTestId('preset-delete-court-a')).toBeInTheDocument();
  });

  it('loads a system preset via onApplyPatch', async () => {
    vi.mocked(api.listPresets).mockResolvedValue({
      items: [SYSTEM_THEME_PRESET],
    });
    const onApplyPatch = vi.fn();
    renderWithI18n(
      <PresetPicker model={{}} onApplyPatch={onApplyPatch} />,
    );
    await waitFor(() =>
      expect(
        screen.getByTestId('preset-apply-system-bright-court'),
      ).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByTestId('preset-apply-system-bright-court'));
    expect(onApplyPatch).toHaveBeenCalledWith({
      'Color 1': '#ffffff',
      'Text Color 1': '#000000',
    });
  });
});
