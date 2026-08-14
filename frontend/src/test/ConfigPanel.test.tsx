import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { screen, fireEvent, waitFor } from '@testing-library/react';
import ConfigPanel from '../components/ConfigPanel';
import * as boardApi from '../api/board';
import * as presetsApi from '../api/presets';
import { ConfirmProvider } from '../components/ConfirmProvider';
import { renderWithI18n, mockCustomization } from './helpers';

// Mock the API module
vi.mock('../api/board', () => ({
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
}));
vi.mock('../api/http', () => ({
  ApiError: class ApiError extends Error {
    status: number;
    detail: string;
    constructor(status: number, message: string, detail?: string) {
      super(message);
      this.status = status;
      this.detail = detail || message;
    }
  },
}));
vi.mock('../api/presets', () => ({
  listPresets: vi.fn().mockResolvedValue({ items: [] }),
  createPreset: vi.fn().mockResolvedValue({}),
  deletePreset: vi.fn().mockResolvedValue(undefined),
}));

const defaultProps = {
  oid: 'test-oid',
  customization: mockCustomization,
  setRules: vi.fn().mockResolvedValue({ success: true }),
  setAutoSwapSides: vi.fn().mockResolvedValue({ success: true }),
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
      expect(presetsApi.listPresets).toHaveBeenCalled();
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
    vi.mocked(boardApi.updateCustomization).mockResolvedValue({ success: true });
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
      expect(boardApi.updateCustomization).toHaveBeenCalled();
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

  it('does not prompt on an immediate Back press right after saving', async () => {
    // Regression guard for a stale-ref race. The popstate listener reads the
    // dirty flag through a ref that used to be synced in a useEffect, so
    // between the commit that cleared `isDirty` and the passive effect that
    // updated the ref there was a window where the panel looked clean but a
    // Back press still prompted. Dispatching popstate in the same tick the
    // save resolves lands squarely in that window.
    vi.mocked(boardApi.updateCustomization).mockResolvedValue({ success: true });
    window.confirm = vi.fn();
    renderWithI18n(<ConfigPanel {...defaultProps} />);
    openTeamsSection();
    const selector = await screen.findByTestId('team-1-name-selector');
    fireEvent.change(selector, { target: { value: '' } });
    const saveBtn = screen.getByTestId('save-button');
    await waitFor(() => expect(saveBtn).not.toBeDisabled());

    fireEvent.click(saveBtn);
    // As soon as the panel has committed as clean, leave — without awaiting the
    // extra ticks a passive effect would need.
    await waitFor(() => expect(saveBtn).toBeDisabled());
    window.dispatchEvent(new PopStateEvent('popstate'));

    expect(window.confirm).not.toHaveBeenCalled();
  });

  it('clears the Saved status as soon as the panel goes dirty again', async () => {
    vi.mocked(boardApi.updateCustomization).mockResolvedValue({ success: true });
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
    vi.mocked(boardApi.getStyles).mockResolvedValue(['Classic', 'Modern']);
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
    vi.mocked(boardApi.getStyles).mockResolvedValue(['OnlyOne']);
    renderWithI18n(<ConfigPanel {...defaultProps} />);
    const overlayButton = screen.getByText('Overlay Style').closest('button')!;
    fireEvent.click(overlayButton);
    await waitFor(() => {
      expect(screen.queryByTestId('style-selector')).not.toBeInTheDocument();
    });
  });

  it('surfaces a retryable error banner when save fails', async () => {
    vi.mocked(boardApi.updateCustomization).mockRejectedValueOnce(new Error('Server is on fire'));
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

    vi.mocked(boardApi.updateCustomization).mockResolvedValueOnce({ success: true });
    fireEvent.click(retryBtn);
    await waitFor(() => {
      expect(boardApi.updateCustomization).toHaveBeenCalledTimes(2);
    });
  });

  it('save-error banner can be dismissed without retrying', async () => {
    vi.mocked(boardApi.updateCustomization).mockRejectedValueOnce(new Error('boom'));
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
    expect(boardApi.updateCustomization).toHaveBeenCalledTimes(1);
  });

  it('never shows the (removed) gradient toggle', async () => {
    vi.mocked(boardApi.getLinks).mockResolvedValue({
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

describe('ConfigPanel section navigation semantics', () => {
  const REAL_WIDTH = window.innerWidth;
  const REAL_HEIGHT = window.innerHeight;

  function setViewport(width: number, height: number) {
    Object.defineProperty(window, 'innerWidth', { value: width, configurable: true });
    Object.defineProperty(window, 'innerHeight', { value: height, configurable: true });
  }

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    setViewport(REAL_WIDTH, REAL_HEIGHT);
  });

  it('marks the landscape sidebar entry for the section on screen', async () => {
    setViewport(1024, 768);
    renderWithI18n(<ConfigPanel {...defaultProps} />);
    const presets = screen.getByText('Presets').closest('button')!;
    const teams = screen.getByText('Teams').closest('button')!;

    // Presets is the section the panel opens on.
    expect(presets).toHaveAttribute('aria-current', 'page');
    expect(teams).not.toHaveAttribute('aria-current');

    fireEvent.click(teams);
    await waitFor(() => expect(teams).toHaveAttribute('aria-current', 'page'));
    expect(presets).not.toHaveAttribute('aria-current');
  });

  it('names the panel each portrait accordion header controls', async () => {
    setViewport(390, 844);
    renderWithI18n(<ConfigPanel {...defaultProps} />);
    const presets = screen.getByText('Presets').closest('button')!;
    const teams = screen.getByText('Teams').closest('button')!;

    expect(presets).toHaveAttribute('aria-expanded', 'true');
    expect(teams).toHaveAttribute('aria-expanded', 'false');

    const panelId = presets.getAttribute('aria-controls')!;
    expect(panelId).toBeTruthy();
    const panel = document.getElementById(panelId)!;
    expect(panel).toBeInTheDocument();
    expect(panel.getAttribute('aria-labelledby')).toBe(presets.id);

    fireEvent.click(teams);
    await waitFor(() => expect(teams).toHaveAttribute('aria-expanded', 'true'));
    expect(presets).toHaveAttribute('aria-expanded', 'false');
    // Collapsing removes the region entirely, so nothing dangles.
    expect(document.getElementById(panelId)).toBeNull();

    // Portrait sections collapse: clicking the open one closes it.
    fireEvent.click(teams);
    await waitFor(() => expect(teams).toHaveAttribute('aria-expanded', 'false'));
  });
});

describe('ConfigPanel option loading failures', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(console, 'warn').mockImplementation(() => {});
  });

  it('shows no banner when every lookup succeeds', async () => {
    renderWithI18n(<ConfigPanel {...defaultProps} />);
    await waitFor(() => expect(boardApi.getStyles).toHaveBeenCalled());
    expect(screen.queryByTestId('options-error-banner')).not.toBeInTheDocument();
  });

  it('surfaces a retryable banner when a lookup fails, instead of an empty dropdown', async () => {
    vi.mocked(boardApi.getStyles).mockRejectedValueOnce(new Error('offline'));
    renderWithI18n(<ConfigPanel {...defaultProps} />);

    const banner = await screen.findByTestId('options-error-banner');
    expect(banner.getAttribute('role')).toBe('alert');
    // The other three lookups still landed — one failure does not blank them.
    expect(boardApi.getLinks).toHaveBeenCalled();
    expect(boardApi.getBoardGroups).toHaveBeenCalled();

    vi.mocked(boardApi.getStyles).mockResolvedValue(['Classic', 'Modern']);
    fireEvent.click(screen.getByTestId('options-error-retry'));
    await waitFor(() => {
      expect(screen.queryByTestId('options-error-banner')).not.toBeInTheDocument();
    });

    // The retried styles are the ones the selector now offers.
    fireEvent.click(screen.getByText('Overlay Style').closest('button')!);
    const selector = await screen.findByTestId('style-selector');
    expect(selector.querySelectorAll('option')).toHaveLength(3);
  });

  it('reports a failure to persist the selected team group', async () => {
    vi.mocked(boardApi.getBoardGroups).mockResolvedValue({
      groups: [
        { id: null, name: 'All teams', kind: 'all', count: 1 },
        { id: 4, name: 'Liga', kind: 'shared', count: 2 },
      ],
      selected_id: null,
    });
    vi.mocked(boardApi.setBoardSelectedGroup).mockRejectedValueOnce(new Error('offline'));
    renderWithI18n(<ConfigPanel {...defaultProps} />);
    openTeamsSection();

    const picker = await screen.findByTestId('team-group-picker');
    fireEvent.change(picker, { target: { value: '4' } });
    await screen.findByTestId('options-error-banner');
  });
});

describe('ConfigPanel unsaved-changes prompt', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  function renderWithConfirm() {
    return renderWithI18n(
      <ConfirmProvider>
        <ConfigPanel {...defaultProps} />
      </ConfirmProvider>,
    );
  }

  async function dirtyThePanel() {
    openTeamsSection();
    const selector = await screen.findByTestId('team-1-name-selector');
    fireEvent.change(selector, { target: { value: '' } });
    await waitFor(() => expect(screen.getByTestId('save-button')).not.toBeDisabled());
  }

  it('uses the styled dialog rather than window.confirm', async () => {
    window.confirm = vi.fn();
    renderWithConfirm();
    await dirtyThePanel();

    fireEvent.click(screen.getByTestId('scoreboard-tab-button'));
    expect(
      await screen.findByText('You have unsaved changes that will be lost. Leave anyway?'),
    ).toBeInTheDocument();
    expect(window.confirm).not.toHaveBeenCalled();
    expect(defaultProps.onBack).not.toHaveBeenCalled();
  });

  it('re-arms the history guard before the prompt resolves', async () => {
    // Regression guard. The prompt used to be `window.confirm`, which blocked
    // the main thread, so the popped history entry could not be traversed past
    // while it was open. The styled dialog does not block, so the entry has to
    // be restored up front — otherwise a second Back press during the prompt
    // walks off the board and discards the unsaved edits silently.
    const go = vi.spyOn(window.history, 'go').mockImplementation(() => {});
    try {
      renderWithConfirm();
      await dirtyThePanel();

      window.dispatchEvent(new PopStateEvent('popstate'));
      // Synchronously, in the same handler that opened the prompt.
      expect(go).toHaveBeenCalledWith(1);
      expect(defaultProps.onBack).not.toHaveBeenCalled();

      await screen.findByText('You have unsaved changes that will be lost. Leave anyway?');

      // A second Back while the prompt is open must not stack a competing
      // dialog, and must not exit.
      window.dispatchEvent(new PopStateEvent('popstate'));
      expect(
        screen.getAllByText('You have unsaved changes that will be lost. Leave anyway?'),
      ).toHaveLength(1);
      expect(defaultProps.onBack).not.toHaveBeenCalled();

      // Accepting consumes the restored entry rather than stranding it.
      fireEvent.click(screen.getByText('Leave'));
      await waitFor(() => expect(defaultProps.onBack).toHaveBeenCalledOnce());
      expect(go).toHaveBeenCalledWith(-1);
    } finally {
      go.mockRestore();
    }
  });

  it('stays put when the prompt is dismissed and leaves when it is accepted', async () => {
    renderWithConfirm();
    await dirtyThePanel();

    fireEvent.click(screen.getByTestId('scoreboard-tab-button'));
    fireEvent.click(await screen.findByText('Stay'));
    await waitFor(() =>
      expect(
        screen.queryByText('You have unsaved changes that will be lost. Leave anyway?'),
      ).not.toBeInTheDocument(),
    );
    expect(defaultProps.onBack).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTestId('scoreboard-tab-button'));
    fireEvent.click(await screen.findByText('Leave'));
    await waitFor(() => expect(defaultProps.onBack).toHaveBeenCalledOnce());
  });
});
