import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent, waitFor } from '@testing-library/react';
import ConfigPanel from '../components/ConfigPanel';
import * as api from '../api/client';
import { renderWithI18n, mockCustomization } from './helpers';

// Mock the API module
vi.mock('../api/client', () => ({
  ApiError: class ApiError extends Error {
    status: number;
    detail: string;
    constructor(status: number, message: string, detail?: string) {
      super(message);
      this.status = status;
      this.detail = detail || message;
    }
  },
  getBoardGroups: vi.fn().mockResolvedValue({
    groups: [{ id: null, name: 'All teams', kind: 'all', count: 1 }],
    selected_id: null,
  }),
  getBoardGroupTeams: vi
    .fn()
    .mockResolvedValue({ Home: { icon: '', color: '#0000ff', text_color: '#ffffff' } }),
  setBoardSelectedGroup: vi.fn().mockResolvedValue({ ok: true, selected_id: null }),
  getStyles: vi.fn().mockResolvedValue([]),
  getStyleCapabilities: vi.fn().mockResolvedValue({}),
  getLinks: vi.fn().mockResolvedValue({ control: '', overlay: '', preview: '' }),
  getCustomization: vi.fn().mockResolvedValue({}),
  updateCustomization: vi.fn().mockResolvedValue({}),
  listPresets: vi.fn().mockResolvedValue({ items: [] }),
  createPreset: vi.fn().mockResolvedValue({}),
  deletePreset: vi.fn().mockResolvedValue(undefined),
}));

const defaultProps = {
  oid: 'test-oid',
  customization: mockCustomization,
  actions: {},
  onBack: vi.fn(),
  onLogout: vi.fn(),
  onCustomizationSaved: vi.fn(),
  darkMode: 'auto' as const,
  isFullscreen: false,
  onToggleDarkMode: vi.fn(),
  onToggleFullscreen: vi.fn(),
};

/** The default-open section is Presets; team fields need explicit navigation. */
function openTeamsSection() {
  fireEvent.click(screen.getByText('Teams').closest('button')!);
}

describe('ConfigPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('opens on the Presets section by default', async () => {
    renderWithI18n(<ConfigPanel {...defaultProps} />);
    await waitFor(() => {
      expect(api.listPresets).toHaveBeenCalled();
    });
    expect(screen.queryByTestId('team-1-name-selector')).not.toBeInTheDocument();
  });

  it('renders config title', () => {
    renderWithI18n(<ConfigPanel {...defaultProps} />);
    expect(screen.getByText('Config')).toBeInTheDocument();
  });

  it('renders back button', () => {
    renderWithI18n(<ConfigPanel {...defaultProps} />);
    expect(screen.getByTestId('scoreboard-tab-button')).toBeInTheDocument();
  });

  it('calls onBack when back button clicked with no unsaved changes', async () => {
    renderWithI18n(<ConfigPanel {...defaultProps} />);
    fireEvent.click(screen.getByTestId('scoreboard-tab-button'));
    await waitFor(() => {
      expect(defaultProps.onBack).toHaveBeenCalledOnce();
    });
  });

  it('disables the save button when there are no unsaved changes', () => {
    renderWithI18n(<ConfigPanel {...defaultProps} />);
    const saveBtn = screen.getByTestId('save-button');
    expect(saveBtn).toBeInTheDocument();
    expect(saveBtn).toBeDisabled();
    expect(saveBtn).toHaveTextContent('Save');
  });

  it('enables the save button after a customization change', async () => {
    renderWithI18n(<ConfigPanel {...defaultProps} />);
    openTeamsSection();
    const selector = await screen.findByTestId('team-1-name-selector');
    fireEvent.change(selector, { target: { value: '' } });
    await waitFor(() => {
      expect(screen.getByTestId('save-button')).not.toBeDisabled();
    });
  });

  it('confirms before leaving when there are unsaved changes', async () => {
    window.confirm = vi.fn().mockReturnValue(false);
    renderWithI18n(<ConfigPanel {...defaultProps} />);
    openTeamsSection();
    const selector = await screen.findByTestId('team-1-name-selector');
    fireEvent.change(selector, { target: { value: '' } });
    await waitFor(() => {
      expect(screen.getByTestId('save-button')).not.toBeDisabled();
    });
    fireEvent.click(screen.getByTestId('scoreboard-tab-button'));
    await waitFor(() => {
      expect(window.confirm).toHaveBeenCalled();
    });
    expect(defaultProps.onBack).not.toHaveBeenCalled();
  });

  it('confirms when popstate fires (swipe back) with unsaved changes', async () => {
    window.confirm = vi.fn().mockReturnValue(false);
    renderWithI18n(<ConfigPanel {...defaultProps} />);
    openTeamsSection();
    const selector = await screen.findByTestId('team-1-name-selector');
    fireEvent.change(selector, { target: { value: '' } });
    await waitFor(() => {
      expect(screen.getByTestId('save-button')).not.toBeDisabled();
    });
    window.dispatchEvent(new PopStateEvent('popstate'));
    expect(window.confirm).toHaveBeenCalled();
    expect(defaultProps.onBack).not.toHaveBeenCalled();
  });

  it('exits via popstate without prompting when nothing is dirty', () => {
    window.confirm = vi.fn();
    renderWithI18n(<ConfigPanel {...defaultProps} />);
    window.dispatchEvent(new PopStateEvent('popstate'));
    expect(window.confirm).not.toHaveBeenCalled();
    expect(defaultProps.onBack).toHaveBeenCalledOnce();
  });

  it('stays in the panel after a successful save and shows a Saved status', async () => {
    vi.mocked(api.updateCustomization).mockResolvedValue({ success: true });
    window.confirm = vi.fn();
    renderWithI18n(<ConfigPanel {...defaultProps} />);
    openTeamsSection();
    const selector = await screen.findByTestId('team-1-name-selector');
    fireEvent.change(selector, { target: { value: '' } });
    const saveBtn = screen.getByTestId('save-button');
    await waitFor(() => {
      expect(saveBtn).not.toBeDisabled();
    });
    fireEvent.click(saveBtn);
    await waitFor(() => {
      expect(api.updateCustomization).toHaveBeenCalled();
      expect(screen.getByTestId('save-status-saved')).toBeInTheDocument();
    });
    // The operator keeps iterating: no auto-exit, Save disarms again.
    expect(defaultProps.onBack).not.toHaveBeenCalled();
    expect(saveBtn).toBeDisabled();

    // Leaving afterwards needs no unsaved-changes prompt.
    window.dispatchEvent(new PopStateEvent('popstate'));
    expect(window.confirm).not.toHaveBeenCalled();
    expect(defaultProps.onBack).toHaveBeenCalledOnce();
  });

  it('clears the Saved status as soon as the panel goes dirty again', async () => {
    vi.mocked(api.updateCustomization).mockResolvedValue({ success: true });
    renderWithI18n(<ConfigPanel {...defaultProps} />);
    openTeamsSection();
    const selector = await screen.findByTestId('team-1-name-selector');
    fireEvent.change(selector, { target: { value: '' } });
    await waitFor(() => {
      expect(screen.getByTestId('save-button')).not.toBeDisabled();
    });
    fireEvent.click(screen.getByTestId('save-button'));
    await screen.findByTestId('save-status-saved');

    fireEvent.change(selector, { target: { value: 'Home' } });
    await waitFor(() => {
      expect(screen.queryByTestId('save-status-saved')).not.toBeInTheDocument();
    });
    expect(screen.getByTestId('save-button')).not.toBeDisabled();
  });

  it('renders bottom bar action buttons', () => {
    renderWithI18n(<ConfigPanel {...defaultProps} />);
    // Save / fullscreen / theme / logout. Reset and refresh moved
    // out of the panel; reset now lives on the HUD next to the
    // Start-match toggle.
    expect(screen.getByTestId('save-button')).toBeInTheDocument();
    expect(screen.getByTestId('fullscreen-button')).toBeInTheDocument();
    expect(screen.getByTestId('dark-mode-button')).toBeInTheDocument();
    expect(screen.getByTestId('logout-button')).toBeInTheDocument();
    // Both removed.
    expect(screen.queryByTestId('refresh-button')).toBeNull();
    expect(screen.queryByTestId('reset-button')).toBeNull();
  });

  it('calls onToggleDarkMode when theme button clicked', () => {
    renderWithI18n(<ConfigPanel {...defaultProps} />);
    fireEvent.click(screen.getByTestId('dark-mode-button'));
    expect(defaultProps.onToggleDarkMode).toHaveBeenCalledOnce();
  });

  it('calls onToggleFullscreen when fullscreen button clicked', () => {
    renderWithI18n(<ConfigPanel {...defaultProps} />);
    fireEvent.click(screen.getByTestId('fullscreen-button'));
    expect(defaultProps.onToggleFullscreen).toHaveBeenCalledOnce();
  });

  it('shows logout confirmation dialog', async () => {
    renderWithI18n(<ConfigPanel {...defaultProps} />);
    fireEvent.click(screen.getByTestId('logout-button'));
    const confirmBtn = await screen.findByTestId('confirm-dialog-ok');
    fireEvent.click(confirmBtn);
    expect(defaultProps.onLogout).toHaveBeenCalledOnce();
  });

  it('does not logout if dialog cancelled', async () => {
    renderWithI18n(<ConfigPanel {...defaultProps} />);
    fireEvent.click(screen.getByTestId('logout-button'));
    const cancelBtn = await screen.findByTestId('confirm-dialog-cancel');
    fireEvent.click(cancelBtn);
    expect(defaultProps.onLogout).not.toHaveBeenCalled();
  });

  it('shows style selector when backend returns multiple styles', async () => {
    vi.mocked(api.getStyles).mockResolvedValue(['Classic', 'Modern']);
    renderWithI18n(<ConfigPanel {...defaultProps} />);
    // Navigate to overlay section
    const overlayButton = screen.getByText('Overlay Style').closest('button')!;
    fireEvent.click(overlayButton);
    await waitFor(() => {
      expect(screen.getByTestId('style-selector')).toBeInTheDocument();
    });
    const options = screen.getByTestId('style-selector').querySelectorAll('option');
    expect(options).toHaveLength(3); // placeholder + 2 styles
    expect(options[1]).toHaveTextContent('Classic');
    expect(options[2]).toHaveTextContent('Modern');
  });

  it('hides style selector when only one style', async () => {
    vi.mocked(api.getStyles).mockResolvedValue(['OnlyOne']);
    renderWithI18n(<ConfigPanel {...defaultProps} />);
    const overlayButton = screen.getByText('Overlay Style').closest('button')!;
    fireEvent.click(overlayButton);
    await waitFor(() => {
      expect(screen.queryByTestId('style-selector')).not.toBeInTheDocument();
    });
  });

  it('surfaces a retryable error banner when save fails', async () => {
    vi.mocked(api.updateCustomization).mockRejectedValueOnce(new Error('Server is on fire'));
    renderWithI18n(<ConfigPanel {...defaultProps} />);
    openTeamsSection();
    const selector = await screen.findByTestId('team-1-name-selector');
    fireEvent.change(selector, { target: { value: '' } });
    const saveBtn = screen.getByTestId('save-button');
    await waitFor(() => {
      expect(saveBtn).not.toBeDisabled();
    });
    fireEvent.click(saveBtn);
    const banner = await screen.findByTestId('save-error-banner');
    expect(banner).toHaveTextContent('Server is on fire');
    expect(banner.getAttribute('role')).toBe('alert');
    const retryBtn = screen.getByTestId('save-error-retry');
    expect(retryBtn).toHaveTextContent('Retry');

    vi.mocked(api.updateCustomization).mockResolvedValueOnce({ success: true });
    fireEvent.click(retryBtn);
    await waitFor(() => {
      expect(api.updateCustomization).toHaveBeenCalledTimes(2);
    });
  });

  it('save-error banner can be dismissed without retrying', async () => {
    vi.mocked(api.updateCustomization).mockRejectedValueOnce(new Error('boom'));
    renderWithI18n(<ConfigPanel {...defaultProps} />);
    openTeamsSection();
    const selector = await screen.findByTestId('team-1-name-selector');
    fireEvent.change(selector, { target: { value: '' } });
    await waitFor(() => {
      expect(screen.getByTestId('save-button')).not.toBeDisabled();
    });
    fireEvent.click(screen.getByTestId('save-button'));
    await screen.findByTestId('save-error-banner');

    fireEvent.click(screen.getByTestId('save-error-dismiss'));
    expect(screen.queryByTestId('save-error-banner')).not.toBeInTheDocument();
    expect(api.updateCustomization).toHaveBeenCalledTimes(1);
  });

  it('never shows the (removed) gradient toggle', async () => {
    vi.mocked(api.getLinks).mockResolvedValue({
      control: '',
      overlay: 'http://my-app.example/overlay/tok',
      preview: '',
    });
    renderWithI18n(<ConfigPanel {...defaultProps} />);
    const overlayButton = screen.getByText('Overlay Style').closest('button')!;
    fireEvent.click(overlayButton);
    await waitFor(() => {
      expect(screen.getByText('Overlay Style')).toBeInTheDocument();
    });
    expect(screen.queryByText('Gradient')).not.toBeInTheDocument();
  });
});
