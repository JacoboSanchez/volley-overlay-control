import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent, waitFor } from '@testing-library/react';
import ConfigPanel from '../components/ConfigPanel';
import * as api from '../api/client';
import { renderWithI18n, mockCustomization } from './helpers';

// Mock the API module
vi.mock('../api/client', () => ({
  getTeams: vi.fn().mockResolvedValue({ Home: { icon: '', color: '#0000ff', text_color: '#ffffff' } }),
  getThemes: vi.fn().mockResolvedValue({}),
  getStyles: vi.fn().mockResolvedValue([]),
  getLinks: vi.fn().mockResolvedValue({ control: '', overlay: '', preview: '' }),
  getCustomization: vi.fn().mockResolvedValue({}),
  updateCustomization: vi.fn().mockResolvedValue({}),
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

describe('ConfigPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
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
    const selector = await screen.findByTestId('team-1-name-selector');
    fireEvent.change(selector, { target: { value: '' } });
    await waitFor(() => {
      expect(screen.getByTestId('save-button')).not.toBeDisabled();
    });
  });

  it('confirms before leaving when there are unsaved changes', async () => {
    window.confirm = vi.fn().mockReturnValue(false);
    renderWithI18n(<ConfigPanel {...defaultProps} />);
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

  it('exits without prompting after a successful save', async () => {
    vi.mocked(api.updateCustomization).mockResolvedValue({ success: true });
    window.confirm = vi.fn();
    renderWithI18n(<ConfigPanel {...defaultProps} />);
    const selector = await screen.findByTestId('team-1-name-selector');
    fireEvent.change(selector, { target: { value: '' } });
    const saveBtn = screen.getByTestId('save-button');
    await waitFor(() => {
      expect(saveBtn).not.toBeDisabled();
    });
    fireEvent.click(saveBtn);
    await waitFor(() => {
      expect(api.updateCustomization).toHaveBeenCalled();
      expect(defaultProps.onBack).toHaveBeenCalled();
    });
    expect(window.confirm).not.toHaveBeenCalled();
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

  it('shows logout confirmation', () => {
    window.confirm = vi.fn().mockReturnValue(true);
    renderWithI18n(<ConfigPanel {...defaultProps} />);
    fireEvent.click(screen.getByTestId('logout-button'));
    expect(window.confirm).toHaveBeenCalled();
    expect(defaultProps.onLogout).toHaveBeenCalledOnce();
  });

  it('does not logout if confirm cancelled', () => {
    window.confirm = vi.fn().mockReturnValue(false);
    renderWithI18n(<ConfigPanel {...defaultProps} />);
    fireEvent.click(screen.getByTestId('logout-button'));
    expect(defaultProps.onLogout).not.toHaveBeenCalled();
  });

  it('renders language selector in behavior section', async () => {
    renderWithI18n(<ConfigPanel {...defaultProps} />);
    // In landscape mode, click the behavior sidebar item
    const behaviorButton = screen.getByText('Behavior').closest('button')!;
    fireEvent.click(behaviorButton);
    await waitFor(() => {
      expect(screen.getByText('English')).toBeInTheDocument();
    });
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

  it('hides gradient toggle for custom overlays', async () => {
    vi.mocked(api.getLinks).mockResolvedValue({ control: '', overlay: 'http://custom-overlay.example.com/output', preview: '' });
    renderWithI18n(<ConfigPanel {...defaultProps} />);
    const overlayButton = screen.getByText('Overlay Style').closest('button')!;
    fireEvent.click(overlayButton);
    await waitFor(() => {
      expect(screen.queryByText('Gradient')).not.toBeInTheDocument();
    });
  });

  it('shows gradient toggle for standard overlays', async () => {
    vi.mocked(api.getLinks).mockResolvedValue({ control: '', overlay: 'https://overlays.uno/output/abc', preview: '' });
    renderWithI18n(<ConfigPanel {...defaultProps} />);
    const overlayButton = screen.getByText('Overlay Style').closest('button')!;
    fireEvent.click(overlayButton);
    await waitFor(() => {
      expect(screen.getByText('Gradient')).toBeInTheDocument();
    });
  });
});
