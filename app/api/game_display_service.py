"""Display-only toggles and side-swap behavior."""

import logging

from app.api import game_rapid_pair as _rapid_pair
from app.api.schemas import (
    ActionResponse,
)
from app.customization_cache_ttl import customization_cache_ttl_seconds

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


def _service(cls: type):
    """Return the composed facade class for cross-mixin calls."""
    return cls


class GameDisplayService:
    """Manage overlay presentation flags without scoring mutations."""

    @classmethod
    def set_visibility(cls, session, visible: bool) -> ActionResponse:
        session.visible = visible
        session.backend.change_overlay_visibility(visible)
        state_response = _service(cls).get_state(session)
        _service(cls)._broadcast(session, state_response)
        return ActionResponse(success=True, state=state_response)

    @classmethod
    def set_simple_mode(cls, session, enabled: bool) -> ActionResponse:
        session.simple = enabled
        if enabled:
            session.backend.reduce_games_to_one()
        state_response = _service(cls).get_state(session)
        _service(cls)._save_and_broadcast(session, state_response)
        return ActionResponse(success=True, state=state_response)

    @classmethod
    def _auto_swap_component(cls, session, state) -> bool:
        """Auto-derived side-swap parity for the session's live state."""
        from app.api.match_rules import compute_sides_swapped_auto

        completed = [(state.get_game(1, i), state.get_game(2, i)) for i in range(1, session.current_set)]
        return compute_sides_swapped_auto(
            mode=session.mode,
            current_set=session.current_set,
            sets_limit=session.sets_limit,
            team1_score=state.get_game(1, session.current_set),
            team2_score=state.get_game(2, session.current_set),
            points_limit=session.points_limit,
            points_limit_last_set=session.points_limit_last_set,
            completed_set_scores=completed,
        )

    @classmethod
    def effective_sides_swapped(cls, session, state) -> bool:
        """The orientation every live view should render right now.

        Manual base XOR the auto component (when auto-swap is on), so
        the swap button keeps working as a correction in auto mode.
        """
        swapped = bool(session.sides_swapped_manual)
        if session.auto_swap_sides:
            swapped ^= _service(cls)._auto_swap_component(session, state)
        return swapped

    @classmethod
    def set_sides_swapped(cls, session, swapped: bool) -> ActionResponse:
        """Set the *effective* display orientation to ``swapped``.

        The stored manual base absorbs the auto component so the
        operator's intent ("show it this way now") wins regardless of
        the auto-swap setting.
        """
        state = session.game_manager.get_current_state()
        base = bool(swapped)
        if session.auto_swap_sides:
            base ^= _service(cls)._auto_swap_component(session, state)
        session.sides_swapped_manual = base
        session.persist_meta()
        state_response = _service(cls).get_state(session)
        _service(cls)._save_and_broadcast(session, state_response)
        return ActionResponse(success=True, state=state_response)

    @classmethod
    def set_auto_swap_sides(cls, session, enabled: bool) -> ActionResponse:
        """Toggle automatic side swapping.

        The manual base is re-anchored so the orientation visible at
        the moment of the toggle does not jump — the setting changes
        future behaviour, not the current picture.
        """
        enabled = bool(enabled)
        if enabled != session.auto_swap_sides:
            state = session.game_manager.get_current_state()
            current_effective = _service(cls).effective_sides_swapped(session, state)
            session.auto_swap_sides = enabled
            base = current_effective
            if enabled:
                base ^= _service(cls)._auto_swap_component(session, state)
            session.sides_swapped_manual = base
            session.persist_meta()
        state_response = _service(cls).get_state(session)
        _service(cls)._save_and_broadcast(session, state_response)
        return ActionResponse(success=True, state=state_response)

    @classmethod
    def set_set_summary_mode(cls, session, enabled: bool) -> ActionResponse:
        """Toggle the set-summary overlay panel.

        The summary picks the "last played" set: if the current set has
        any points, it's the current set; otherwise (just after a set
        transition) it's the previous set so the operator can roll the
        recap immediately on stream.
        """
        session.set_summary = bool(enabled)
        session.persist_meta()
        state_response = _service(cls).get_state(session)
        _service(cls)._save_and_broadcast(session, state_response)
        return ActionResponse(success=True, state=state_response)

    @classmethod
    def set_set_summary_style(cls, session, style: str) -> ActionResponse:
        """Pick the visual variant for the set-summary overlay.

        ``style`` is validated against
        :data:`app.api.schemas.SET_SUMMARY_STYLE_CHOICES`. Unknown styles
        fall back to the existing value rather than raising — callers
        get the validation through the FastAPI ``Literal`` type.
        """
        from app.api.schemas import SET_SUMMARY_STYLE_CHOICES

        if style in SET_SUMMARY_STYLE_CHOICES:
            session.set_summary_style = style
            session.persist_meta()
        state_response = _service(cls).get_state(session)
        _service(cls)._save_and_broadcast(session, state_response)
        return ActionResponse(success=True, state=state_response)
