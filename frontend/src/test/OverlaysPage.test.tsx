import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
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
  name: 'Liga Local',
  oid: 'liga',
  display_name: 'Liga Local',
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

  it('splits each overlay into its two jobs and shows both URLs inline', async () => {
    vi.mocked(api.getOverlays).mockResolvedValue([OVERLAY]);
    renderWithI18n(<OverlaysPage />);

    await waitFor(() => expect(screen.getByText('Liga Local')).toBeInTheDocument());
    // The oid is shown as a pill alongside the display name.
    expect(screen.getByText('liga')).toBeInTheDocument();
    // Both purpose headers are present.
    expect(screen.getByText('For OBS · video output')).toBeInTheDocument();
    expect(screen.getByText('To control · scoreboard')).toBeInTheDocument();
    // Output URL and the shareable control link are both visible without
    // expanding anything — the two actions the user comes here to do.
    expect(screen.getByDisplayValue('https://x/overlay/pub')).toBeInTheDocument();
    expect(screen.getByDisplayValue('https://x/board?c=ctl')).toBeInTheDocument();
    // The guessable self-bookmark stays in a collapsed Advanced disclosure.
    const advanced = screen.getByText('Advanced: permanent bookmark link').closest('details');
    expect(advanced).not.toHaveAttribute('open');
    // No "bookmark on" chip while public_control is disabled.
    expect(screen.queryByText('Bookmark on')).not.toBeInTheDocument();
  });

  it('flags the bookmark as on and opens Advanced when public_control is enabled', async () => {
    vi.mocked(api.getOverlays).mockResolvedValue([
      { ...OVERLAY, public_control: true, public_control_url: 'https://x/board?u=me&oid=liga' },
    ]);
    renderWithI18n(<OverlaysPage />);

    await waitFor(() => expect(screen.getByText('Bookmark on')).toBeInTheDocument());
    const advanced = screen.getByText('Advanced: permanent bookmark link').closest('details');
    expect(advanced).toHaveAttribute('open');
    expect(screen.getByDisplayValue('https://x/board?u=me&oid=liga')).toBeInTheDocument();
  });
});
