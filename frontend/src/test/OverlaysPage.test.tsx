import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act, screen, fireEvent, waitFor, within } from '@testing-library/react';
import OverlaysPage from '../pages/OverlaysPage';
import * as api from '../api/overlays';
import { ApiError } from '../api/http';
import { renderWithI18n } from './helpers';

vi.mock('../api/http', () => ({
  // Mirror the real ApiError(status, message, detail?) signature so tsc is
  // happy when tests construct it; keep detail resolution the same.
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

vi.mock('../api/overlays', () => ({
  getOverlays: vi.fn(),
  createOverlay: vi.fn(),
  deleteOverlay: vi.fn(),
  updateOverlay: vi.fn(),
  regenerateControlToken: vi.fn(),
}));

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
  is_favorite: false,
};

function overlay(
  oid: string,
  description: string | null = null,
  isFavorite = false,
): api.OverlayPayload {
  return {
    ...OVERLAY,
    name: oid,
    oid,
    description,
    output_url: `https://x/overlay/${oid}`,
    control_url: `https://x/board?c=${oid}`,
    is_favorite: isFavorite,
  };
}

describe('OverlaysPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows a friendly name and both frequent actions while details stay collapsed', async () => {
    vi.mocked(api.getOverlays).mockResolvedValue([OVERLAY]);
    renderWithI18n(<OverlaysPage />);

    // The human description leads; the immutable oid remains useful metadata.
    await waitFor(() => expect(screen.getByText('Liga Local')).toBeInTheDocument());
    expect(screen.getByText('ID: liga')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /control scoreboard/i })).toHaveAttribute(
      'href',
      '/board?oid=liga',
    );
    expect(screen.getByRole('link', { name: /view overlay/i })).toHaveAttribute(
      'href',
      OVERLAY.output_url,
    );
    // Copy-once links and settings are not rendered until expanded.
    expect(screen.queryByText('For OBS · video output')).not.toBeInTheDocument();
    expect(screen.queryByText('https://x/overlay/pub')).not.toBeInTheDocument();
    const toggle = screen.getByRole('button', { name: /links and settings/i });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
  });

  it('expands to reveal the two jobs and both URLs inline', async () => {
    vi.mocked(api.getOverlays).mockResolvedValue([OVERLAY]);
    renderWithI18n(<OverlaysPage />);
    await waitFor(() => expect(screen.getByText('Liga Local')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /links and settings/i }));

    expect(screen.getByText('For OBS · video output')).toBeInTheDocument();
    expect(screen.getByText('Share control')).toBeInTheDocument();
    // URLs render as wrapping text blocks (not inputs) so a portrait phone
    // shows the whole URI, not just its first characters.
    expect(screen.getByText('https://x/overlay/pub')).toBeInTheDocument();
    expect(screen.getByText('https://x/board?c=ctl')).toBeInTheDocument();
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
    await waitFor(() => expect(screen.getByText('Permanent link on')).toBeInTheDocument());
    // Once expanded, the Advanced disclosure is open and shows the bookmark URL.
    fireEvent.click(screen.getByRole('button', { name: /links and settings/i }));
    const advanced = screen.getByText('Advanced: permanent bookmark link').closest('details');
    expect(advanced).toHaveAttribute('open');
    expect(screen.getByText('https://x/board?u=me&oid=liga')).toBeInTheDocument();
  });

  it('searches long lists by friendly name or id and reports the result count', async () => {
    vi.mocked(api.getOverlays).mockResolvedValue([
      overlay('alpha', 'Central court'),
      overlay('beta', 'Second court'),
      overlay('cup-final', 'Cup final'),
      overlay('league', 'League'),
      overlay('north', 'North venue'),
      overlay('south', 'South venue'),
    ]);
    renderWithI18n(<OverlaysPage />);

    const search = await screen.findByRole('searchbox', { name: /search overlays/i });
    fireEvent.change(search, { target: { value: 'central' } });

    expect(screen.getByText('Central court')).toBeInTheDocument();
    expect(screen.queryByText('Second court')).not.toBeInTheDocument();
    expect(screen.getByText('1 of 6')).toBeInTheDocument();

    fireEvent.change(search, { target: { value: 'cup-final' } });
    expect(screen.getByText('Cup final')).toBeInTheDocument();
  });

  it('normalizes search independently from the browser locale', async () => {
    const localeLower = vi
      .spyOn(String.prototype, 'toLocaleLowerCase')
      .mockImplementation(function (this: string) {
        return this.toString().replaceAll('I', 'ı').toLowerCase();
      });
    vi.mocked(api.getOverlays).mockResolvedValue([
      overlay('final', 'FINAL'),
      overlay('beta', 'Beta'),
      overlay('cup', 'Cup'),
      overlay('league', 'League'),
      overlay('north', 'North'),
      overlay('south', 'South'),
    ]);
    renderWithI18n(<OverlaysPage />);

    const search = await screen.findByRole('searchbox', { name: /search overlays/i });
    fireEvent.change(search, { target: { value: 'final' } });

    expect(screen.getByText('FINAL')).toBeInTheDocument();
    localeLower.mockRestore();
  });

  it('keeps active filters visible when the list drops below the tools threshold', async () => {
    const initial = [
      overlay('alpha', 'Court one'),
      overlay('beta', 'Court two'),
      overlay('cup', 'Cup'),
      overlay('league', 'League'),
      overlay('north', 'North'),
      overlay('south', 'South'),
    ];
    vi.mocked(api.getOverlays).mockResolvedValue(initial);
    vi.mocked(api.deleteOverlay).mockResolvedValue(undefined as never);
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    renderWithI18n(<OverlaysPage />);

    const search = await screen.findByRole('searchbox', { name: /search overlays/i });
    fireEvent.change(search, { target: { value: 'court' } });
    expect(screen.getByText('2 of 6')).toBeInTheDocument();

    vi.mocked(api.getOverlays).mockResolvedValue(initial.filter((item) => item.oid !== 'alpha'));
    fireEvent.click(within(cardFor('alpha')).getByRole('button', { name: /more actions/i }));
    fireEvent.click(within(cardFor('alpha')).getByRole('button', { name: /delete/i }));

    await waitFor(() => expect(api.deleteOverlay).toHaveBeenCalledWith('alpha'));
    await waitFor(() => expect(screen.getByText('1 of 5')).toBeInTheDocument());
    expect(screen.getByRole('searchbox', { name: /search overlays/i })).toHaveValue('court');
    expect(screen.getByText('Court two')).toBeInTheDocument();
    confirmSpy.mockRestore();
  });

  it('sorts favorites first and can show only favorites', async () => {
    vi.mocked(api.getOverlays).mockResolvedValue([
      overlay('alpha', 'Alpha'),
      overlay('beta', 'Beta', true),
      overlay('cup', 'Cup'),
      overlay('league', 'League'),
      overlay('north', 'North'),
      overlay('south', 'South'),
    ]);
    renderWithI18n(<OverlaysPage />);

    await screen.findByRole('button', { name: /favorites only/i });
    const cards = document.querySelectorAll('.acc-overlay-card');
    expect(cards[0]).toHaveTextContent('Beta');

    fireEvent.click(screen.getByRole('button', { name: /favorites only/i }));
    expect(screen.getByText('Beta')).toBeInTheDocument();
    expect(screen.queryByText('Alpha')).not.toBeInTheDocument();
    expect(screen.getByText('1 of 6')).toBeInTheDocument();
  });
});

// ---- flows: create / delete / rename / share / bookmark ---------------------

function cardFor(oid: string): HTMLElement {
  return document
    .querySelector(`a[href="/board?oid=${oid}"]`)
    ?.closest('.acc-overlay-card') as HTMLElement;
}

describe('OverlaysPage flows', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.getOverlays).mockResolvedValue([OVERLAY]);
  });

  it('creates an overlay (trimmed description), clears the form, reloads', async () => {
    vi.mocked(api.createOverlay).mockResolvedValue({ ...OVERLAY, oid: 'nueva' });
    renderWithI18n(<OverlaysPage />);
    await waitFor(() => expect(screen.getByText('Liga Local')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /new overlay/i }));
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
    await waitFor(() => expect(screen.getByText('ID: nueva')).toBeInTheDocument());
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(cardFor('nueva')).toHaveClass('is-new');
  });

  it('rejects an invalid oid inline without calling the API', async () => {
    renderWithI18n(<OverlaysPage />);
    await waitFor(() => expect(screen.getByText('Liga Local')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /new overlay/i }));
    fireEvent.change(screen.getAllByRole('textbox')[0]!, { target: { value: 'bad name!' } });
    fireEvent.click(screen.getByRole('button', { name: /add overlay/i }));
    await waitFor(() => expect(document.querySelector('.acc-error')).not.toBeNull());
    expect(api.createOverlay).not.toHaveBeenCalled();
  });

  it('shows the server detail when create fails but keeps the list', async () => {
    vi.mocked(api.createOverlay).mockRejectedValue(
      new ApiError(400, 'dup', 'You already have an overlay with that id.'),
    );
    renderWithI18n(<OverlaysPage />);
    await waitFor(() => expect(screen.getByText('Liga Local')).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: /new overlay/i }));
    fireEvent.change(screen.getAllByRole('textbox')[0]!, { target: { value: 'liga' } });
    fireEvent.click(screen.getByRole('button', { name: /add overlay/i }));
    await waitFor(() =>
      expect(screen.getByText('You already have an overlay with that id.')).toBeInTheDocument(),
    );
    expect(screen.getByText('ID: liga')).toBeInTheDocument();
  });

  it('deletes after confirmation and reloads to the empty state', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(api.deleteOverlay).mockResolvedValue(undefined as never);
    renderWithI18n(<OverlaysPage />);
    await waitFor(() => expect(screen.getByText('Liga Local')).toBeInTheDocument());

    vi.mocked(api.getOverlays).mockResolvedValue([]);
    fireEvent.click(within(cardFor('liga')).getByRole('button', { name: /more actions/i }));
    fireEvent.click(within(cardFor('liga')).getByRole('button', { name: /delete/i }));
    await waitFor(() => expect(api.deleteOverlay).toHaveBeenCalledWith('liga'));
    confirmSpy.mockRestore();
  });

  it('does not delete when the confirm is declined', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    renderWithI18n(<OverlaysPage />);
    await waitFor(() => expect(screen.getByText('Liga Local')).toBeInTheDocument());
    fireEvent.click(within(cardFor('liga')).getByRole('button', { name: /more actions/i }));
    fireEvent.click(within(cardFor('liga')).getByRole('button', { name: /delete/i }));
    await waitFor(() => expect(confirmSpy).toHaveBeenCalled());
    expect(api.deleteOverlay).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it('saves a new description from the rename panel', async () => {
    vi.mocked(api.updateOverlay).mockResolvedValue({ ...OVERLAY, description: 'Renamed' });
    renderWithI18n(<OverlaysPage />);
    await waitFor(() => expect(screen.getByText('Liga Local')).toBeInTheDocument());

    fireEvent.click(within(cardFor('liga')).getByRole('button', { name: /more actions/i }));
    fireEvent.click(within(cardFor('liga')).getByRole('button', { name: /edit name/i }));
    const panelInput = screen.getByDisplayValue('Liga Local');
    fireEvent.change(panelInput, { target: { value: 'Renamed' } });
    fireEvent.click(screen.getByRole('button', { name: /save settings/i }));
    await waitFor(() =>
      expect(api.updateOverlay).toHaveBeenCalledWith('liga', { description: 'Renamed' }),
    );
  });

  it('favorites an overlay from the management menu', async () => {
    vi.mocked(api.updateOverlay).mockResolvedValue({ ...OVERLAY, is_favorite: true });
    renderWithI18n(<OverlaysPage />);
    await waitFor(() => expect(screen.getByText('Liga Local')).toBeInTheDocument());

    fireEvent.click(within(cardFor('liga')).getByRole('button', { name: /more actions/i }));
    fireEvent.click(within(cardFor('liga')).getByRole('button', { name: /add to favorites/i }));

    await waitFor(() =>
      expect(api.updateOverlay).toHaveBeenCalledWith('liga', { is_favorite: true }),
    );
  });

  it('regenerates the shared control link behind a confirm when one exists', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(api.regenerateControlToken).mockResolvedValue(OVERLAY);
    renderWithI18n(<OverlaysPage />);
    await waitFor(() => expect(screen.getByText('Liga Local')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /links and settings/i }));
    fireEvent.click(screen.getByRole('button', { name: /regenerate/i }));
    await waitFor(() => expect(api.regenerateControlToken).toHaveBeenCalledWith('liga'));
    expect(confirmSpy).toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it('enables the public bookmark behind a confirm', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(api.updateOverlay).mockResolvedValue({ ...OVERLAY, public_control: true });
    renderWithI18n(<OverlaysPage />);
    await waitFor(() => expect(screen.getByText('Liga Local')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /links and settings/i }));
    vi.mocked(api.getOverlays).mockResolvedValue([
      { ...OVERLAY, public_control: true, public_control_url: 'https://x/board?u=me&oid=liga' },
    ]);
    fireEvent.click(screen.getByRole('checkbox'));
    await waitFor(() =>
      expect(api.updateOverlay).toHaveBeenCalledWith('liga', { public_control: true }),
    );
    await waitFor(() => expect(screen.getByText('Permanent link on')).toBeInTheDocument());
    confirmSpy.mockRestore();
  });

  // Regression: a reload used to swap the whole list for the loading
  // placeholder, unmounting the cards. The operator who had just minted or
  // revoked a link was dropped back on the collapsed overlay list — exactly
  // when they still needed the card to copy the new URL from.
  it('stays in the expanded card while the refresh runs and swaps in the new URL', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(api.regenerateControlToken).mockResolvedValue({
      ...OVERLAY,
      control_token: 'fresh',
      control_url: 'https://x/board?c=fresh',
    });
    renderWithI18n(<OverlaysPage />);
    await waitFor(() => expect(screen.getByText('Liga Local')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /links and settings/i }));

    // Hold the refresh open so the in-flight window is observable — that is
    // where the list used to be swapped for the loading placeholder.
    let finishRefresh!: (rows: api.OverlayPayload[]) => void;
    vi.mocked(api.getOverlays).mockReturnValue(
      new Promise<api.OverlayPayload[]>((resolve) => {
        finishRefresh = resolve;
      }),
    );
    fireEvent.click(screen.getByRole('button', { name: /regenerate/i }));
    await waitFor(() => expect(api.regenerateControlToken).toHaveBeenCalledWith('liga'));

    expect(screen.getByRole('button', { name: /links and settings/i })).toHaveAttribute(
      'aria-expanded',
      'true',
    );
    expect(document.querySelector('.acc-overlay-cards')).toHaveAttribute('aria-busy', 'true');

    finishRefresh([{ ...OVERLAY, control_token: 'fresh', control_url: 'https://x/board?c=fresh' }]);

    await waitFor(() => expect(screen.getByText('https://x/board?c=fresh')).toBeInTheDocument());
    expect(screen.getByRole('button', { name: /links and settings/i })).toHaveAttribute(
      'aria-expanded',
      'true',
    );
    // The revoked link is gone from the copy field, not merely hidden.
    expect(screen.queryByText('https://x/board?c=ctl')).not.toBeInTheDocument();
    confirmSpy.mockRestore();
  });

  it('keeps the card and the Advanced panel open after removing public access', async () => {
    vi.mocked(api.getOverlays).mockResolvedValue([
      { ...OVERLAY, public_control: true, public_control_url: 'https://x/board?u=me&oid=liga' },
    ]);
    vi.mocked(api.updateOverlay).mockResolvedValue({ ...OVERLAY, public_control: false });
    renderWithI18n(<OverlaysPage />);
    await waitFor(() => expect(screen.getByText('Liga Local')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /links and settings/i }));
    vi.mocked(api.getOverlays).mockResolvedValue([OVERLAY]);
    fireEvent.click(screen.getByRole('checkbox'));

    await waitFor(() =>
      expect(api.updateOverlay).toHaveBeenCalledWith('liga', { public_control: false }),
    );
    await waitFor(() => expect(screen.queryByText('Permanent link on')).not.toBeInTheDocument());
    expect(screen.getByRole('button', { name: /links and settings/i })).toHaveAttribute(
      'aria-expanded',
      'true',
    );
    // The disclosure that hosts the toggle stays open, so re-enabling the
    // bookmark is one click away instead of two.
    expect(
      screen.getByText('Advanced: permanent bookmark link').closest('details'),
    ).toHaveAttribute('open');
    expect(screen.getByRole('checkbox')).not.toBeChecked();
  });

  // A mutation commits server-side even when the refresh after it fails, so
  // the row is written from the mutation's own response: the revoked control
  // URL must never stay under the Copy button beneath a success toast.
  it('shows the new link, not the revoked one, when the refresh after it fails', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(api.regenerateControlToken).mockResolvedValue({
      ...OVERLAY,
      control_token: 'fresh',
      control_url: 'https://x/board?c=fresh',
    });
    renderWithI18n(<OverlaysPage />);
    await waitFor(() => expect(screen.getByText('Liga Local')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /links and settings/i }));
    vi.mocked(api.getOverlays).mockRejectedValue(new TypeError('Failed to fetch'));
    fireEvent.click(screen.getByRole('button', { name: /regenerate/i }));

    await waitFor(() => expect(screen.getByText('https://x/board?c=fresh')).toBeInTheDocument());
    expect(screen.queryByText('https://x/board?c=ctl')).not.toBeInTheDocument();
    // The failed refresh is still reported; it just does not roll the card back.
    expect(document.querySelector('.acc-error')).not.toBeNull();
    confirmSpy.mockRestore();
  });

  it('drops a deleted overlay even when the refresh after it fails', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(api.getOverlays).mockResolvedValue([OVERLAY, overlay('otra', 'Otra pista')]);
    vi.mocked(api.deleteOverlay).mockResolvedValue(undefined as never);
    renderWithI18n(<OverlaysPage />);
    await waitFor(() => expect(screen.getByText('Liga Local')).toBeInTheDocument());

    vi.mocked(api.getOverlays).mockRejectedValue(new TypeError('Failed to fetch'));
    fireEvent.click(within(cardFor('liga')).getByRole('button', { name: /more actions/i }));
    fireEvent.click(within(cardFor('liga')).getByRole('button', { name: /delete/i }));

    await waitFor(() => expect(api.deleteOverlay).toHaveBeenCalledWith('liga'));
    await waitFor(() => expect(screen.queryByText('Liga Local')).not.toBeInTheDocument());
    expect(screen.getByText('Otra pista')).toBeInTheDocument();
    confirmSpy.mockRestore();
  });

  // Two refreshes can now overlap, because the cards stay clickable while one
  // is in flight. If the older response lands last it must not win, or the
  // regenerated link visibly reverts to the revoked URL.
  it('ignores an overlapping older refresh that resolves last', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(api.updateOverlay).mockResolvedValue({ ...OVERLAY, is_favorite: true });
    vi.mocked(api.regenerateControlToken).mockResolvedValue({
      ...OVERLAY,
      is_favorite: true,
      control_token: 'fresh',
      control_url: 'https://x/board?c=fresh',
    });
    renderWithI18n(<OverlaysPage />);
    await waitFor(() => expect(screen.getByText('Liga Local')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /links and settings/i }));

    // Hold every refresh from here on so both can be in flight at once.
    const pending: ((rows: api.OverlayPayload[]) => void)[] = [];
    vi.mocked(api.getOverlays).mockImplementation(
      () =>
        new Promise<api.OverlayPayload[]>((resolve) => {
          pending.push(resolve);
        }),
    );

    fireEvent.click(within(cardFor('liga')).getByRole('button', { name: /more actions/i }));
    fireEvent.click(within(cardFor('liga')).getByRole('button', { name: /add to favorites/i }));
    await waitFor(() => expect(pending).toHaveLength(1));

    fireEvent.click(screen.getByRole('button', { name: /regenerate/i }));
    await waitFor(() => expect(pending).toHaveLength(2));

    const favorited = { ...OVERLAY, is_favorite: true };
    const regenerated = {
      ...favorited,
      control_token: 'fresh',
      control_url: 'https://x/board?c=fresh',
    };
    // Newest first...
    await act(async () => {
      pending[1]!([regenerated]);
    });
    expect(screen.getByText('https://x/board?c=fresh')).toBeInTheDocument();
    // ...then the stale one, carrying pre-regenerate rows.
    await act(async () => {
      pending[0]!([favorited]);
    });

    expect(screen.getByText('https://x/board?c=fresh')).toBeInTheDocument();
    expect(screen.queryByText('https://x/board?c=ctl')).not.toBeInTheDocument();
    confirmSpy.mockRestore();
  });

  // Two mutations on one card can overlap (the favorite toggle has no busy
  // guard), and each answers with a whole-row snapshot. A favorite response
  // that still carries the pre-regeneration control_url must not put that
  // revoked link back under the Copy button.
  it('never lets an overlapping mutation response restore the revoked link', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(api.regenerateControlToken).mockResolvedValue({
      ...OVERLAY,
      control_token: 'fresh',
      control_url: 'https://x/board?c=fresh',
    });
    // The favorite PATCH read the row before the regeneration committed, so
    // its snapshot still holds the old control_url.
    vi.mocked(api.updateOverlay).mockResolvedValue({ ...OVERLAY, is_favorite: true });
    renderWithI18n(<OverlaysPage />);
    await waitFor(() => expect(screen.getByText('Liga Local')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: /links and settings/i }));

    // Hold every refresh, so only the mutation responses decide what is shown.
    vi.mocked(api.getOverlays).mockImplementation(() => new Promise(() => {}));

    fireEvent.click(screen.getByRole('button', { name: /regenerate/i }));
    await waitFor(() => expect(screen.getByText('https://x/board?c=fresh')).toBeInTheDocument());

    fireEvent.click(within(cardFor('liga')).getByRole('button', { name: /more actions/i }));
    fireEvent.click(within(cardFor('liga')).getByRole('button', { name: /add to favorites/i }));
    await waitFor(() =>
      expect(api.updateOverlay).toHaveBeenCalledWith('liga', { is_favorite: true }),
    );

    // The favorite lands, and it only carries the favorite.
    await waitFor(() =>
      expect(cardFor('liga').querySelector('.acc-overlay-favorite')).not.toBeNull(),
    );
    expect(screen.getByText('https://x/board?c=fresh')).toBeInTheDocument();
    expect(screen.queryByText('https://x/board?c=ctl')).not.toBeInTheDocument();
    confirmSpy.mockRestore();
  });

  it('keeps the last good list under the banner when a refresh fails', async () => {
    vi.mocked(api.updateOverlay).mockResolvedValue({ ...OVERLAY, is_favorite: true });
    renderWithI18n(<OverlaysPage />);
    await waitFor(() => expect(screen.getByText('Liga Local')).toBeInTheDocument());

    vi.mocked(api.getOverlays).mockRejectedValue(new TypeError('Failed to fetch'));
    fireEvent.click(within(cardFor('liga')).getByRole('button', { name: /more actions/i }));
    fireEvent.click(within(cardFor('liga')).getByRole('button', { name: /add to favorites/i }));

    await waitFor(() => expect(document.querySelector('.acc-error')).not.toBeNull());
    expect(screen.getByText('Liga Local')).toBeInTheDocument();
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
