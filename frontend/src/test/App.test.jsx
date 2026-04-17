import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import App from '../App';
import * as api from '../api/client';
import { renderWithI18n, mockGameState, mockCustomization } from './helpers';

vi.mock('../api/client', () => ({
  initSession: vi.fn(),
  getCustomization: vi.fn(),
  getLinks: vi.fn(),
  getOverlays: vi.fn(),
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
    // Reset URL
    Object.defineProperty(window, 'location', {
      value: { protocol: 'https:', host: 'localhost', search: '', href: 'https://localhost' },
      writable: true,
    });
    api.getOverlays.mockResolvedValue([]);
    api.initSession.mockResolvedValue({ success: true, state: mockGameState });
    api.getCustomization.mockResolvedValue(mockCustomization);
    api.getLinks.mockResolvedValue({ control: '', overlay: '', preview: '' });
  });

  it('renders OID entry screen initially', () => {
    renderWithI18n(<App />);
    expect(screen.getByText('Volley Scoreboard')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('C-my-overlay')).toBeInTheDocument();
  });

  it('connect button is disabled when OID input is empty', () => {
    renderWithI18n(<App />);
    const btn = screen.getByText('Connect');
    expect(btn).toBeDisabled();
  });

  it('connect button is enabled when OID input has value', () => {
    renderWithI18n(<App />);
    const input = screen.getByPlaceholderText('C-my-overlay');
    fireEvent.change(input, { target: { value: 'test-oid' } });
    expect(screen.getByText('Connect')).not.toBeDisabled();
  });

  it('initializes session on form submit', async () => {
    renderWithI18n(<App />);
    const input = screen.getByPlaceholderText('C-my-overlay');
    fireEvent.change(input, { target: { value: 'my-oid' } });
    fireEvent.submit(input.closest('form'));

    await waitFor(() => {
      expect(api.initSession).toHaveBeenCalledWith('my-oid');
    });
  });

  it('shows error message when session init fails', async () => {
    api.initSession.mockResolvedValue({ success: false, message: 'Invalid OID' });
    renderWithI18n(<App />);
    const input = screen.getByPlaceholderText('C-my-overlay');
    fireEvent.change(input, { target: { value: 'bad' } });
    fireEvent.submit(input.closest('form'));

    await waitFor(() => {
      expect(screen.getByText('Invalid OID')).toBeInTheDocument();
    });
  });

  it('renders scoreboard after successful init', async () => {
    renderWithI18n(<App />);
    const input = screen.getByPlaceholderText('C-my-overlay');
    fireEvent.change(input, { target: { value: 'valid-oid' } });
    fireEvent.submit(input.closest('form'));

    await waitFor(() => {
      expect(screen.getByTestId('team-1-sets')).toBeInTheDocument();
      expect(screen.getByTestId('team-2-sets')).toBeInTheDocument();
    });
  });

  it('renders predefined overlays dropdown when available', async () => {
    api.getOverlays.mockResolvedValue([
      { oid: 'overlay-1', name: 'My Overlay' },
      { oid: 'overlay-2', name: 'Other Overlay' },
    ]);
    renderWithI18n(<App />);

    await waitFor(() => {
      expect(screen.getByText('My Overlay')).toBeInTheDocument();
      expect(screen.getByText('Other Overlay')).toBeInTheDocument();
    });
  });

  it('switches to config tab when config button clicked', async () => {
    renderWithI18n(<App />);
    const input = screen.getByPlaceholderText('C-my-overlay');
    fireEvent.change(input, { target: { value: 'oid' } });
    fireEvent.submit(input.closest('form'));

    await waitFor(() => {
      expect(screen.getByTestId('config-tab-button')).toBeInTheDocument();
    });

    // Mock additional API calls that ConfigPanel makes
    api.getTeams.mockResolvedValue({});
    api.getThemes.mockResolvedValue({});
    api.getStyles.mockResolvedValue([]);

    fireEvent.click(screen.getByTestId('config-tab-button'));

    await waitFor(() => {
      expect(screen.getByText('Config')).toBeInTheDocument();
    });
  });

  it('persists OID to localStorage on connect', async () => {
    renderWithI18n(<App />);
    const input = screen.getByPlaceholderText('C-my-overlay');
    fireEvent.change(input, { target: { value: 'persist-oid' } });
    fireEvent.submit(input.closest('form'));

    await waitFor(() => {
      expect(localStorage.setItem).toHaveBeenCalledWith('volley_oid', 'persist-oid');
    });
  });
});
