import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent, waitFor, within } from '@testing-library/react';
import OverlaysPage from '../pages/OverlaysPage';
import * as api from '../api/client';
import { renderWithI18n } from './helpers';

vi.mock('../api/client', () => {
  // Mirror the real ApiError(status, message, detail?) signature so tsc is
  // happy when tests construct it; keep detail resolution the same.
  class ApiError extends Error {
    status: number;
    detail: string;
    constructor(status: number, message: string, detail?: string) {
      super(message);
      this.status = status;
      this.detail = detail || message;
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

// ---- flows: create / delete / rename / share / bookmark ---------------------

function cardFor(oid: string): HTMLElement {
  return screen.getByText(oid).closest('.acc-overlay-card') as HTMLElement;
}

describe('OverlaysPage flows', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.getOverlays).mockResolvedValue([OVERLAY]);
  });

  it('creates an overlay (trimmed description), clears the form, reloads', async () => {
    vi.mocked(api.createOverlay).mockResolvedValue({ ...OVERLAY, oid: 'nueva' });
    renderWithI18n(<OverlaysPage />);
    await waitFor(() => expect(screen.getByText('liga')).toBeInTheDocument());

    const inputs = screen.getAllByRole('textbox');
    fireEvent.change(inputs[0]!, { target: { value: 'nueva' } });
    fireEvent.change(inputs[1]!, { target: { value: '  Cup  ' } });
    vi.mocked(api.getOverlays).mockResolvedValue([
      OVERLAY,
      { ...OVERLAY, oid: 'nueva', description: 'Cup' },
    ]);
    fireEvent.click(screen.getByRole('button', { name: /add overlay/i }));

    await waitFor(() =>
      expect(api.createOverlay).toHaveBeenCalledWith('nueva', { description: 'Cup' }),
    );
    await waitFor(() => expect(screen.getByText('nueva')).toBeInTheDocument());
    expect((screen.getAllByRole('textbox')[0] as HTMLInputElement).value).toBe('');
  });

  it('rejects an invalid oid inline without calling the API', async () => {
    renderWithI18n(<OverlaysPage />);
    await waitFor(() => expect(screen.getByText('liga')).toBeInTheDocument());
    fireEvent.change(screen.getAllByRole('textbox')[0]!, { target: { value: 'bad name!' } });
    fireEvent.click(screen.getByRole('button', { name: /add overlay/i }));
    await waitFor(() => expect(document.querySelector('.acc-error')).not.toBeNull());
    expect(api.createOverlay).not.toHaveBeenCalled();
  });

  it('shows the server detail when create fails but keeps the list', async () => {
    vi.mocked(api.createOverlay).mockRejectedValue(
      new api.ApiError(400, 'dup', 'You already have an overlay with that id.'),
    );
    renderWithI18n(<OverlaysPage />);
    await waitFor(() => expect(screen.getByText('liga')).toBeInTheDocument());
    fireEvent.change(screen.getAllByRole('textbox')[0]!, { target: { value: 'liga' } });
    fireEvent.click(screen.getByRole('button', { name: /add overlay/i }));
    await waitFor(() =>
      expect(screen.getByText('You already have an overlay with that id.')).toBeInTheDocument(),
    );
    expect(screen.getByText('liga')).toBeInTheDocument();
  });

  it('deletes after confirmation and reloads to the empty state', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(api.deleteOverlay).mockResolvedValue(undefined as never);
    renderWithI18n(<OverlaysPage />);
    await waitFor(() => expect(screen.getByText('liga')).toBeInTheDocument());

    vi.mocked(api.getOverlays).mockResolvedValue([]);
    fireEvent.click(within(cardFor('liga')).getByRole('button', { name: /delete/i }));
    await waitFor(() => expect(api.deleteOverlay).toHaveBeenCalledWith('liga'));
    confirmSpy.mockRestore();
  });

  it('does not delete when the confirm is declined', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    renderWithI18n(<OverlaysPage />);
    await waitFor(() => expect(screen.getByText('liga')).toBeInTheDocument());
    fireEvent.click(within(cardFor('liga')).getByRole('button', { name: /delete/i }));
    await waitFor(() => expect(confirmSpy).toHaveBeenCalled());
    expect(api.deleteOverlay).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it('saves a new description from the rename panel', async () => {
    vi.mocked(api.updateOverlay).mockResolvedValue({ ...OVERLAY, description: 'Renamed' });
    renderWithI18n(<OverlaysPage />);
    await waitFor(() => expect(screen.getByText('liga')).toBeInTheDocument());

    fireEvent.click(within(cardFor('liga')).getByRole('button', { name: /edit settings/i }));
    const panelInput = screen.getByDisplayValue('Liga Local');
    fireEvent.change(panelInput, { target: { value: 'Renamed' } });
    fireEvent.click(screen.getByRole('button', { name: /save settings/i }));
    await waitFor(() =>
      expect(api.updateOverlay).toHaveBeenCalledWith('liga', { description: 'Renamed' }),
    );
  });

  it('regenerates the shared control link behind a confirm when one exists', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(api.regenerateControlToken).mockResolvedValue(OVERLAY);
    renderWithI18n(<OverlaysPage />);
    await waitFor(() => expect(screen.getByText('liga')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /liga/i }));
    fireEvent.click(screen.getByRole('button', { name: /regenerate/i }));
    await waitFor(() => expect(api.regenerateControlToken).toHaveBeenCalledWith('liga'));
    expect(confirmSpy).toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it('enables the public bookmark behind a confirm', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(api.updateOverlay).mockResolvedValue({ ...OVERLAY, public_control: true });
    renderWithI18n(<OverlaysPage />);
    await waitFor(() => expect(screen.getByText('liga')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /liga/i }));
    vi.mocked(api.getOverlays).mockResolvedValue([
      { ...OVERLAY, public_control: true, public_control_url: 'https://x/board?u=me&oid=liga' },
    ]);
    fireEvent.click(screen.getByRole('checkbox'));
    await waitFor(() =>
      expect(api.updateOverlay).toHaveBeenCalledWith('liga', { public_control: true }),
    );
    await waitFor(() => expect(screen.getByText('Bookmark on')).toBeInTheDocument());
    confirmSpy.mockRestore();
  });

  it('shows the empty state without overlays and the error banner on load failure', async () => {
    vi.mocked(api.getOverlays).mockResolvedValue([]);
    const view = renderWithI18n(<OverlaysPage />);
    await waitFor(() => expect(document.querySelector('.acc-empty, .acc-muted')).not.toBeNull());
    view.unmount();

    vi.mocked(api.getOverlays).mockRejectedValue(new TypeError('Failed to fetch'));
    renderWithI18n(<OverlaysPage />);
    await waitFor(() => expect(document.querySelector('.acc-error')).not.toBeNull());
  });
});
