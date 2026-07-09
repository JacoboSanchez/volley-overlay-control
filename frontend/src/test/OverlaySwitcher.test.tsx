import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent, waitFor } from '@testing-library/react';
import OverlaySwitcher from '../components/config/OverlaySwitcher';
import ConfigPanel from '../components/ConfigPanel';
import * as api from '../api/client';
import { renderWithI18n, mockCustomization } from './helpers';

// Mock the API module — everything ConfigPanel fetches on mount, plus the
// overlay list the switcher's useOverlays() loads.
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
  getOverlays: vi.fn(),
}));

const overlayFixture = (oid: string, description: string | null = null) => ({
  name: oid,
  oid,
  description,
  public_token: `tok-${oid}`,
  output_url: `http://x/overlay/tok-${oid}`,
  control_token: null,
  control_url: null,
  public_control: false,
  public_control_url: null,
});

const myOverlays = [
  overlayFixture('court-a', 'Center court'),
  overlayFixture('court-b', 'Side court'),
  overlayFixture('practice'),
];

async function openMenu() {
  const trigger = screen.getByTestId('overlay-switcher-trigger');
  // The trigger is disabled until the overlay list has loaded.
  await waitFor(() => expect(trigger).not.toBeDisabled());
  fireEvent.click(trigger);
  await screen.findByTestId('overlay-switcher-menu');
  return trigger;
}

describe('OverlaySwitcher (component)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.getOverlays).mockResolvedValue(myOverlays);
  });

  it('names the current oid on the trigger', async () => {
    renderWithI18n(<OverlaySwitcher currentOid="court-a" onSwitch={vi.fn()} />);
    expect(screen.getByTestId('overlay-switcher-trigger')).toHaveTextContent('court-a');
    await waitFor(() => expect(api.getOverlays).toHaveBeenCalled());
  });

  it('lists the owned overlays with the current one selected', async () => {
    renderWithI18n(<OverlaySwitcher currentOid="court-a" onSwitch={vi.fn()} />);
    await openMenu();
    const options = screen.getAllByRole('option');
    expect(options).toHaveLength(3);
    expect(options[0]).toHaveTextContent('court-a');
    expect(options[0]).toHaveAttribute('aria-selected', 'true');
    expect(options[1]).toHaveTextContent('court-b');
    expect(options[1]).toHaveTextContent('Side court');
    expect(options[1]).toHaveAttribute('aria-selected', 'false');
  });

  it('calls onSwitch with the picked oid and closes the menu', async () => {
    const onSwitch = vi.fn();
    renderWithI18n(<OverlaySwitcher currentOid="court-a" onSwitch={onSwitch} />);
    await openMenu();
    fireEvent.click(screen.getByText('court-b'));
    expect(onSwitch).toHaveBeenCalledExactlyOnceWith('court-b');
    expect(screen.queryByTestId('overlay-switcher-menu')).not.toBeInTheDocument();
  });

  it('does not call onSwitch when re-picking the current overlay', async () => {
    const onSwitch = vi.fn();
    renderWithI18n(<OverlaySwitcher currentOid="court-a" onSwitch={onSwitch} />);
    await openMenu();
    fireEvent.click(screen.getAllByRole('option')[0]);
    expect(onSwitch).not.toHaveBeenCalled();
    expect(screen.queryByTestId('overlay-switcher-menu')).not.toBeInTheDocument();
  });

  it('closes on Escape without switching', async () => {
    const onSwitch = vi.fn();
    renderWithI18n(<OverlaySwitcher currentOid="court-a" onSwitch={onSwitch} />);
    await openMenu();
    fireEvent.keyDown(document, { key: 'Escape' });
    await waitFor(() => {
      expect(screen.queryByTestId('overlay-switcher-menu')).not.toBeInTheDocument();
    });
    expect(onSwitch).not.toHaveBeenCalled();
  });

  it('still names the board (disabled) when the list cannot load', async () => {
    vi.mocked(api.getOverlays).mockRejectedValue(new Error('offline'));
    renderWithI18n(<OverlaySwitcher currentOid="court-a" onSwitch={vi.fn()} />);
    await waitFor(() => expect(api.getOverlays).toHaveBeenCalled());
    const trigger = screen.getByTestId('overlay-switcher-trigger');
    expect(trigger).toHaveTextContent('court-a');
    expect(trigger).toBeDisabled();
  });
});

describe('OverlaySwitcher (in ConfigPanel)', () => {
  const panelProps = {
    oid: 'court-a',
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

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.getOverlays).mockResolvedValue(myOverlays);
  });

  it('replaces the static title in owner mode', () => {
    renderWithI18n(<ConfigPanel {...panelProps} onSwitchOverlay={vi.fn()} />);
    expect(screen.getByTestId('overlay-switcher-trigger')).toHaveTextContent('court-a');
    expect(screen.queryByText('Config')).not.toBeInTheDocument();
  });

  it('keeps the static title in operator mode', () => {
    renderWithI18n(<ConfigPanel {...panelProps} operator onSwitchOverlay={vi.fn()} />);
    expect(screen.queryByTestId('overlay-switcher-trigger')).not.toBeInTheDocument();
    expect(screen.getByText('Config')).toBeInTheDocument();
  });

  it('keeps the static title when no switch handler is provided', () => {
    renderWithI18n(<ConfigPanel {...panelProps} />);
    expect(screen.queryByTestId('overlay-switcher-trigger')).not.toBeInTheDocument();
    expect(screen.getByText('Config')).toBeInTheDocument();
  });

  it('switches straight away when nothing is dirty', async () => {
    const onSwitchOverlay = vi.fn();
    window.confirm = vi.fn();
    renderWithI18n(<ConfigPanel {...panelProps} onSwitchOverlay={onSwitchOverlay} />);
    await openMenu();
    fireEvent.click(screen.getByText('court-b'));
    expect(window.confirm).not.toHaveBeenCalled();
    expect(onSwitchOverlay).toHaveBeenCalledExactlyOnceWith('court-b');
  });

  it('blocks the switch behind the unsaved-changes confirm when dirty', async () => {
    const onSwitchOverlay = vi.fn();
    window.confirm = vi.fn().mockReturnValue(false);
    renderWithI18n(<ConfigPanel {...panelProps} onSwitchOverlay={onSwitchOverlay} />);
    // Dirty the panel via a team-name edit, like the other guard tests.
    fireEvent.click(screen.getByText('Teams').closest('button')!);
    const selector = await screen.findByTestId('team-1-name-selector');
    fireEvent.change(selector, { target: { value: '' } });
    await waitFor(() => {
      expect(screen.getByTestId('save-button')).not.toBeDisabled();
    });
    await openMenu();
    fireEvent.click(screen.getByText('court-b'));
    expect(window.confirm).toHaveBeenCalled();
    expect(onSwitchOverlay).not.toHaveBeenCalled();

    // Accepting the prompt lets the switch through.
    vi.mocked(window.confirm).mockReturnValue(true);
    await openMenu();
    fireEvent.click(screen.getByText('court-b'));
    expect(onSwitchOverlay).toHaveBeenCalledExactlyOnceWith('court-b');
  });
});
