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
  onReset: vi.fn(),
  onLogout: vi.fn(),
  onCustomizationSaved: vi.fn(),
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

  it('calls onBack when back button clicked with no unsaved changes', () => {
    renderWithI18n(<ConfigPanel {...defaultProps} />);
    fireEvent.click(screen.getByTestId('scoreboard-tab-button'));
    expect(defaultProps.onBack).toHaveBeenCalledOnce();
  });

  it('hides the save button when there are no unsaved changes', () => {
    renderWithI18n(<ConfigPanel {...defaultProps} />);
    expect(screen.queryByTestId('save-button')).not.toBeInTheDocument();
  });

  it('shows the save button after a customization change', async () => {
    renderWithI18n(<ConfigPanel {...defaultProps} />);
    const selector = await screen.findByTestId('team-1-name-selector');
    fireEvent.change(selector, { target: { value: '' } });
    await waitFor(() => {
      expect(screen.getByTestId('save-button')).toBeInTheDocument();
    });
    expect(screen.getByTestId('save-button')).toHaveTextContent('Save');
  });

  it('confirms before leaving when there are unsaved changes', async () => {
    window.confirm = vi.fn().mockReturnValue(false);
    renderWithI18n(<ConfigPanel {...defaultProps} />);
    const selector = await screen.findByTestId('team-1-name-selector');
    fireEvent.change(selector, { target: { value: '' } });
    await waitFor(() => {
      expect(screen.getByTestId('save-button')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByTestId('scoreboard-tab-button'));
    expect(window.confirm).toHaveBeenCalled();
    expect(defaultProps.onBack).not.toHaveBeenCalled();
  });

  it('exits without prompting after a successful save', async () => {
    vi.mocked(api.updateCustomization).mockResolvedValue({ success: true });
    window.confirm = vi.fn();
    renderWithI18n(<ConfigPanel {...defaultProps} />);
    const selector = await screen.findByTestId('team-1-name-selector');
    fireEvent.change(selector, { target: { value: '' } });
    const saveBtn = await screen.findByTestId('save-button');
    fireEvent.click(saveBtn);
    await waitFor(() => {
      expect(api.updateCustomization).toHaveBeenCalled();
      expect(defaultProps.onBack).toHaveBeenCalled();
    });
    expect(window.confirm).not.toHaveBeenCalled();
  });

  it('renders bottom bar action buttons', () => {
    renderWithI18n(<ConfigPanel {...defaultProps} />);
    expect(screen.getByTestId('refresh-button')).toBeInTheDocument();
    expect(screen.getByTestId('reset-button')).toBeInTheDocument();
    expect(screen.getByTestId('logout-button')).toBeInTheDocument();
  });

  it('calls onReset when reset button clicked', () => {
    renderWithI18n(<ConfigPanel {...defaultProps} />);
    fireEvent.click(screen.getByTestId('reset-button'));
    expect(defaultProps.onReset).toHaveBeenCalledOnce();
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
