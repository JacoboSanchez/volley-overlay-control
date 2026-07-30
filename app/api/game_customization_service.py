"""Customization reads, validation, and persistence."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any, cast

from app.api import game_rapid_pair as _rapid_pair
from app.api.schemas import (
    ALLOWED_CUSTOMIZATION_KEYS,
    LOGO_KEYS,
    MAX_CUSTOMIZATION_KEYS,
    MAX_STRING_VALUE_LENGTH,
    VALID_ANCHORS,
    ActionResponse,
    is_safe_logo_url,
)
from app.customization_cache_ttl import customization_cache_ttl_seconds
from app.match_report.i18n import SUPPORTED_LOCALES as _SUPPORTED_LOCALES

if TYPE_CHECKING:
    from app.api.game_service import GameService
    from app.api.session_manager import GameSession

logger = logging.getLogger(__name__)

# Window for the rapid-pair "undo correction" flow. Two opposite
# ``add_point`` actions on the same team that land within this many
# seconds of each other collapse into a no-op:
#
#   * tap → double-tap-undo within 5 s ⇒ neither lands in the audit
#     log (the just-added forward is tombstoned, no undo is appended).
#   * double-tap-undo → tap within 5 s ⇒ the original forward (which
#     the undo had hidden) is restored and the undo is tombstoned.
#
# Outside the window the actions stay separate. Tuned to match the
# operator's "wait, that wasn't right" reflex without being so wide
# that a deliberate next-rally tap could be mistaken for a recovery.
RAPID_PAIR_WINDOW_S = _rapid_pair.RAPID_PAIR_WINDOW_S

# Short TTL for the customization read-through cache. The overlay server is
# authoritative, but the React UI polls this endpoint on every config panel
# open; coalescing into a 5 s window avoids a burst of redundant round-trips
# without letting the UI show truly stale data.
CUSTOMIZATION_CACHE_TTL_SECONDS = customization_cache_ttl_seconds()


def _cache_ttl_seconds() -> float:
    # Keep the historical monkeypatch surface at app.api.game_service.
    from app.api import game_service

    return float(game_service.CUSTOMIZATION_CACHE_TTL_SECONDS)


def _service(cls: type) -> type[GameService]:
    """Return the composed facade class for cross-mixin calls."""
    return cast("type[GameService]", cls)


class GameCustomizationService:
    """Manage customization state without owning gameplay actions."""

    @classmethod
    def get_customization(
        cls,
        session: GameSession,
    ) -> dict[str, Any]:
        return session.customization.get_model()

    @classmethod
    def refresh_customization(
        cls,
        session: GameSession,
    ) -> dict[str, Any]:
        """Re-fetch customization from the overlay server and update the session cache.

        For custom overlays this performs an HTTP round-trip to the overlay server
        so the React UI always sees the latest team names, colors, logos, etc.
        For Uno overlays the backend fetches from the Uno API.

        A short TTL (``_cache_ttl_seconds()``) short-circuits the
        network call when the last successful refresh happened recently —
        callers still receive the current session model, just without a
        redundant HTTP round-trip. ``update_customization`` primes the
        timestamp, so a write is immediately visible on the next read.

        Concurrent callers for the same session coalesce on
        ``session.customization_fetch_lock``: only the first request hits
        the overlay server, the rest return the freshly populated cache
        as soon as the lock is released. Without this, a burst of UI
        opens (config panel, scoreboard mount, control bar refresh) can
        fire several simultaneous fetches before the first one populates
        the TTL window.
        """
        now = time.monotonic()
        last = getattr(session, "_last_customization_fetch", None)
        if last is not None and now - last < _cache_ttl_seconds():
            return session.customization.get_model()

        with session.customization_fetch_lock:
            # Re-check inside the lock: a sibling caller may have refreshed
            # while we were blocked, in which case the cache is now warm.
            now = time.monotonic()
            last = getattr(session, "_last_customization_fetch", None)
            if last is not None and now - last < _cache_ttl_seconds():
                return session.customization.get_model()

            fresh = session.backend.get_current_customization()
            if fresh is not None:
                session.customization.set_model(fresh)
            session._last_customization_fetch = now
            return session.customization.get_model()

    # ------------------------------------------------------------------
    # State mutations
    # ------------------------------------------------------------------

    @classmethod
    def set_selected_team_group(cls, session: GameSession, group_id: int | None) -> None:
        """Remember the board's selected team group (``None`` = the "All"
        group). Persist-only — the selection changes which teams the control
        selectors offer, not the rendered overlay, so no broadcast is needed."""
        session.selected_team_group_id = group_id
        session.persist_meta()

    @classmethod
    def update_customization(
        cls,
        session: GameSession,
        data: dict[str, Any],
    ) -> ActionResponse:
        # Reject obviously malformed payloads before doing any work. The
        # cap on top-level keys keeps a malicious client from streaming
        # tens of thousands of unknown keys (the filter below drops them,
        # but allocating the dict iteration is still wasted work).
        if not isinstance(data, dict):
            return ActionResponse(
                success=False,
                state=_service(cls).get_state(session),
                message="Customization payload must be a JSON object.",
            )
        if len(data) > MAX_CUSTOMIZATION_KEYS:
            return ActionResponse(
                success=False,
                state=_service(cls).get_state(session),
                message=(f"Customization payload exceeds {MAX_CUSTOMIZATION_KEYS} keys."),
            )

        # Filter to allowed keys only
        filtered = {k: v for k, v in data.items() if k in ALLOWED_CUSTOMIZATION_KEYS}
        if not filtered:
            return ActionResponse(
                success=False,
                state=_service(cls).get_state(session),
                message="No valid customization keys provided.",
            )

        # Per-value validation: only scalar JSON types are allowed
        # (str / bool / int / float / None). Lists and nested objects
        # are rejected outright — the customization model is a flat
        # map of UI knobs, so an array or dict would either be ignored
        # downstream or balloon the broadcast payload via deep merge.
        # Strings are length-capped and logo URLs are scheme-checked.
        for key, value in filtered.items():
            if key in LOGO_KEYS:
                if value in (None, ""):
                    continue
                if not is_safe_logo_url(value):
                    return ActionResponse(
                        success=False,
                        state=_service(cls).get_state(session),
                        message=(f"Logo URL for '{key}' must use http(s) or data:image scheme."),
                    )
            elif key == "locale":
                if value is None:
                    continue
                if not isinstance(value, str) or value.strip().lower() not in _SUPPORTED_LOCALES:
                    return ActionResponse(
                        success=False,
                        state=_service(cls).get_state(session),
                        message=(f"Value for 'locale' must be one of {list(_SUPPORTED_LOCALES)}."),
                    )
            elif key == "Anchor":
                if value is None:
                    continue
                if not isinstance(value, str) or value.strip().lower() not in VALID_ANCHORS:
                    return ActionResponse(
                        success=False,
                        state=_service(cls).get_state(session),
                        message=(f"Value for 'Anchor' must be one of {sorted(VALID_ANCHORS)}."),
                    )
            elif isinstance(value, str):
                if len(value) > MAX_STRING_VALUE_LENGTH:
                    return ActionResponse(
                        success=False,
                        state=_service(cls).get_state(session),
                        message=(f"Value for '{key}' exceeds {MAX_STRING_VALUE_LENGTH} characters."),
                    )
            elif not isinstance(value, (bool, int, float, type(None))):
                # ``bool`` is a subclass of ``int`` so it would have
                # been accepted by the numeric branch anyway, but
                # listing it explicitly documents intent.
                return ActionResponse(
                    success=False,
                    state=_service(cls).get_state(session),
                    message=(f"Value for '{key}' must be a string, boolean, number, or null."),
                )
        # Merge into existing model to preserve keys not in the allowed set
        # (e.g. Team 1 Logo Fit, Color 3, Text Color 3)
        current = session.customization.get_model()
        merged = {**current, **filtered}
        session.customization.set_model(merged)
        session.backend.save_json_customization(merged)
        # A write just made the session's view authoritative — prime the
        # cache so the next refresh short-circuits instead of fetching
        # the same data we just pushed.
        session._last_customization_fetch = time.monotonic()
        state_response = _service(cls).get_state(session)
        _service(cls)._broadcast(session, state_response)
        return ActionResponse(success=True, state=state_response)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
