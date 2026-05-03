import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { screen, fireEvent, waitFor, act } from '@testing-library/react';
import App from '../App';
import * as api from '../api/client';
import { renderWithI18n, mockGameState, mockCustomization } from './helpers';
import { HUD_AUTO_HIDE_MS } from '../constants';

vi.mock('../api/client', () => ({
  initSession: vi.fn(),
  getCustomization: vi.fn(),
  getLinks: vi.fn(),
  getOverlays: vi.fn(),
  getAppConfig: vi.fn(),
  addPoint: vi.fn(),
  addSet: vi.fn(),
  addTimeout: vi.fn(),
  changeServe: vi.fn(),
  setScore: vi.fn(),
  setSets: vi.fn(),
  resetGame: vi.fn(),
  setVisibility: vi.fn(),
  setSimpleMode: vi.fn(),
  getTeams: vi.fn(),
  getThemes: vi.fn(),
  getStyles: vi.fn(),
  updateCustomization: vi.fn(),
}));

vi.mock('../api/websocket', () => ({
  createWebSocket: vi.fn(() => ({
    close: vi.fn(),
    onclose: null,
    onerror: null,
  })),
}));

describe('App', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Object.defineProperty(window, 'location', {
      value: { protocol: 'https:', host: 'localhost', search: '', href: 'https://localhost' },
      writable: true,
    });
    vi.mocked(api.getOverlays).mockResolvedValue([]);
    vi.mocked(api.getAppConfig).mockResolvedValue({ title: 'Volley Scoreboard' });
    vi.mocked(api.initSession).mockResolvedValue({ success: true, state: mockGameState });
    vi.mocked(api.getCustomization).mockResolvedValue(mockCustomization);
    vi.mocked(api.getLinks).mockResolvedValue({ control: '', overlay: '', preview: '' });
  });

  it('renders OID entry screen initially', () => {
    renderWithI18n(<App />);
    expect(screen.getByText('Volley Scoreboard')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('my-overlay')).toBeInTheDocument();
  });

  it('connect button is disabled when OID input is empty', () => {
    renderWithI18n(<App />);
    const btn = screen.getByText('Connect');
    expect(btn).toBeDisabled();
  });

  it('connect button is enabled when OID input has value', () => {
    renderWithI18n(<App />);
    const input = screen.getByPlaceholderText('my-overlay');
    fireEvent.change(input, { target: { value: 'test-oid' } });
    expect(screen.getByText('Connect')).not.toBeDisabled();
  });

  it('initializes session on form submit', async () => {
    renderWithI18n(<App />);
    const input = screen.getByPlaceholderText('my-overlay');
    fireEvent.change(input, { target: { value: 'my-oid' } });
    fireEvent.submit(input.closest('form')!);

    await waitFor(() => {
      expect(api.initSession).toHaveBeenCalledWith('my-oid');
    });
  });

  it('shows error message when session init fails', async () => {
    vi.mocked(api.initSession).mockResolvedValue({ success: false, message: 'Invalid OID' });
    renderWithI18n(<App />);
    const input = screen.getByPlaceholderText('my-overlay');
    fireEvent.change(input, { target: { value: 'bad' } });
    fireEvent.submit(input.closest('form')!);

    await waitFor(() => {
      expect(screen.getByText('Invalid OID')).toBeInTheDocument();
    });
  });

  it('renders scoreboard after successful init', async () => {
    renderWithI18n(<App />);
    const input = screen.getByPlaceholderText('my-overlay');
    fireEvent.change(input, { target: { value: 'valid-oid' } });
    fireEvent.submit(input.closest('form')!);

    await waitFor(() => {
      expect(screen.getByTestId('team-1-sets')).toBeInTheDocument();
      expect(screen.getByTestId('team-2-sets')).toBeInTheDocument();
    });
  });

  it('renders predefined overlays dropdown when available', async () => {
    vi.mocked(api.getOverlays).mockResolvedValue([
      { oid: 'overlay-1', name: 'My Overlay' },
      { oid: 'overlay-2', name: 'Other Overlay' },
    ] as unknown as api.OverlayPayload[]);
    renderWithI18n(<App />);

    await waitFor(() => {
      expect(screen.getByText('My Overlay')).toBeInTheDocument();
      expect(screen.getByText('Other Overlay')).toBeInTheDocument();
    });
  });

  it('switches to config tab when config button clicked', async () => {
    renderWithI18n(<App />);
    const input = screen.getByPlaceholderText('my-overlay');
    fireEvent.change(input, { target: { value: 'oid' } });
    fireEvent.submit(input.closest('form')!);

    await waitFor(() => {
      expect(screen.getByTestId('config-tab-button')).toBeInTheDocument();
    });

    // Mock additional API calls that ConfigPanel makes
    vi.mocked(api.getTeams).mockResolvedValue({});
    vi.mocked(api.getThemes).mockResolvedValue({});
    vi.mocked(api.getStyles).mockResolvedValue([]);

    fireEvent.click(screen.getByTestId('config-tab-button'));

    await waitFor(() => {
      expect(screen.getByText('Config')).toBeInTheDocument();
    });
  });

  it('persists OID to localStorage on connect', async () => {
    renderWithI18n(<App />);
    const input = screen.getByPlaceholderText('my-overlay');
    fireEvent.change(input, { target: { value: 'persist-oid' } });
    fireEvent.submit(input.closest('form')!);

    await waitFor(() => {
      expect(localStorage.setItem).toHaveBeenCalledWith('volley_oid', 'persist-oid');
    });
  });

  it('seeds initial OID from ?control= query alias', () => {
    Object.defineProperty(window, 'location', {
      value: {
        protocol: 'https:',
        host: 'localhost',
        search: '?control=alias-oid',
        href: 'https://localhost/?control=alias-oid',
      },
      writable: true,
    });
    renderWithI18n(<App />);
    const input = screen.getByPlaceholderText('my-overlay') as HTMLInputElement;
    expect(input.value).toBe('alias-oid');
  });

  describe('HUD auto-hide', () => {
    // Shrink the viewport below the persistent-controls breakpoint so the
    // inactivity timer is actually engaged.
    beforeEach(() => {
      Object.defineProperty(window, 'innerWidth', { configurable: true, value: 400 });
      Object.defineProperty(window, 'innerHeight', { configurable: true, value: 700 });
      vi.useFakeTimers();
    });
    afterEach(() => { vi.useRealTimers(); });

    async function bootApp() {
      renderWithI18n(<App />);
      const input = screen.getByPlaceholderText('my-overlay');
      fireEvent.change(input, { target: { value: 'auto-hide-oid' } });
      fireEvent.submit(input.closest('form')!);
      await vi.waitFor(() => {
        expect(screen.getByTestId('team-1-sets')).toBeInTheDocument();
      });
    }

    it('keeps the HUD visible while the match is pending (no match_started_at)', async () => {
      vi.mocked(api.initSession).mockResolvedValue({
        success: true,
        state: { ...mockGameState, match_started_at: null },
      });
      await bootApp();
      const hud = document.querySelector('.hud-controls')!;
      expect(hud.classList.contains('ui-hidden')).toBe(false);
      act(() => { vi.advanceTimersByTime(HUD_AUTO_HIDE_MS + 500); });
      expect(hud.classList.contains('ui-hidden')).toBe(false);
    });

    it('auto-hides the HUD after inactivity once the match has started', async () => {
      vi.mocked(api.initSession).mockResolvedValue({
        success: true,
        state: { ...mockGameState, match_started_at: 1700000000 },
      });
      await bootApp();
      const hud = document.querySelector('.hud-controls')!;
      expect(hud.classList.contains('ui-hidden')).toBe(false);
      act(() => { vi.advanceTimersByTime(HUD_AUTO_HIDE_MS + 500); });
      expect(hud.classList.contains('ui-hidden')).toBe(true);
    });
  });
});
