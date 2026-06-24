import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent, waitFor } from '@testing-library/react';
import OverlaysPage from '../pages/OverlaysPage';
import * as api from '../api/client';
import { renderWithI18n } from './helpers';

vi.mock('../api/client', () => {
  class ApiError extends Error {
    detail: string;
    constructor(detail: string) {
      super(detail);
      this.detail = detail;
    }
  }
  return {
    ApiError,
    getOverlays: vi.fn(),
    createOverlay: vi.fn(),
    deleteOverlay: vi.fn(),
    updateOverlay: vi.fn(),
    regenerateControlToken: vi.fn(),
  };
});

const OVERLAY: api.OverlayPayload = {
  name: 'liga',
  oid: 'liga',
  description: 'Liga Local',
  public_token: 'pub',
  output_url: 'https://x/overlay/pub',
  control_token: 'ctl',
  control_url: 'https://x/board?c=ctl',
  public_control: false,
  public_control_url: null,
};

describe('OverlaysPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows the oid as the name and the description as a small subtitle, collapsed by default', async () => {
    vi.mocked(api.getOverlays).mockResolvedValue([OVERLAY]);
    renderWithI18n(<OverlaysPage />);

    // Header identifies the overlay by its oid (the name) + description.
    await waitFor(() => expect(screen.getByText('liga')).toBeInTheDocument());
    expect(screen.getByText('Liga Local')).toBeInTheDocument();
    // Collapsed by default: the jobs/URLs are not rendered until expanded.
    expect(screen.queryByText('For OBS · video output')).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue('https://x/overlay/pub')).not.toBeInTheDocument();
    const toggle = screen.getByRole('button', { name: /liga/i });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
  });

  it('expands to reveal the two jobs and both URLs inline', async () => {
    vi.mocked(api.getOverlays).mockResolvedValue([OVERLAY]);
    renderWithI18n(<OverlaysPage />);
    await waitFor(() => expect(screen.getByText('liga')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /liga/i }));

    expect(screen.getByText('For OBS · video output')).toBeInTheDocument();
    expect(screen.getByText('To control · scoreboard')).toBeInTheDocument();
    expect(screen.getByDisplayValue('https://x/overlay/pub')).toBeInTheDocument();
    expect(screen.getByDisplayValue('https://x/board?c=ctl')).toBeInTheDocument();
    // The guessable bookmark stays in a collapsed Advanced disclosure.
    const advanced = screen.getByText('Advanced: permanent bookmark link').closest('details');
    expect(advanced).not.toHaveAttribute('open');
  });

  it('flags the bookmark with a chip in the collapsed header when enabled', async () => {
    vi.mocked(api.getOverlays).mockResolvedValue([
      { ...OVERLAY, public_control: true, public_control_url: 'https://x/board?u=me&oid=liga' },
    ]);
    renderWithI18n(<OverlaysPage />);

    // The chip is visible without expanding the card.
    await waitFor(() => expect(screen.getByText('Bookmark on')).toBeInTheDocument());
    // Once expanded, the Advanced disclosure is open and shows the bookmark URL.
    fireEvent.click(screen.getByRole('button', { name: /liga/i }));
    const advanced = screen.getByText('Advanced: permanent bookmark link').closest('details');
    expect(advanced).toHaveAttribute('open');
    expect(screen.getByDisplayValue('https://x/board?u=me&oid=liga')).toBeInTheDocument();
  });
});
