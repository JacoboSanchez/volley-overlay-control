"""Highlight-card rendering for match reports."""

from __future__ import annotations

import html

from app.api.schemas import ERROR_TYPES
from app.match_report.i18n import t as _t


def _fmt_seconds(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {seconds:02d}s"
    return f"{minutes}m {seconds:02d}s"


_PT_LABEL_KEYS = {
    "ace": "pointTypeAce",
    "kill": "pointTypeKill",
    "block": "pointTypeBlock",
    "opp_error": "pointTypeOppError",
}
_ET_LABEL_KEYS = {
    "serve_error": "errorTypeServe",
    "attack_error": "errorTypeAttack",
    "reception_error": "errorTypeReception",
    "ball_handling": "errorTypeBallHandling",
    "net_fault": "errorTypeNet",
    "position_fault": "errorTypePosition",
    "other": "errorTypeOther",
}


def _pct(n: int, denom: int) -> int:
    return round(100 * n / denom) if denom else 0


def _comeback_card(
    card, team_label, locale: str, data: dict, *,
    qualifies: bool, label_key: str, value_key: str,
    field: str = "deficit",
) -> None:
    """Append one best-of-both-teams highlight card.

    *data* is a per-team ``{team: {field, "set"}}`` accumulator from
    ``_compute_stats`` — historically the comeback deficits, and via
    *field* also the biggest-lead flavour. When both teams' best value
    is the same, a single tied-card is rendered instead of arbitrarily
    picking one team. *qualifies* carries the flavour-specific
    threshold check.
    """
    if not qualifies:
        return
    d1 = (data.get(1) or {}).get(field, 0)
    d2 = (data.get(2) or {}).get(field, 0)
    if d1 == d2:
        card(
            _t(locale, label_key),
            _t(locale, "pointsValue", n=max(d1, d2)),
            _t(locale, "comebackTie"),
        )
        return
    team = 1 if d1 > d2 else 2
    entry = data[team]
    card(
        _t(locale, label_key),
        _t(locale, value_key, n=entry[field], set=entry.get("set") or "?"),
        team_label(team),
    )


def _point_composition_cards(
    card, team_label, locale: str,
    point_types: dict, totals_by_team: dict,
) -> None:
    """Point composition: how each team scored, each type as a share
    of that team's total points won (the remainder, if any, is
    untagged). One card per team with at least one classified point.
    """
    for team in (1, 2):
        counts = point_types.get(team) or {}
        total_typed = sum(v for v in counts.values() if isinstance(v, int))
        if total_typed <= 0:
            continue
        team_total = totals_by_team.get(team) or 0
        parts = []
        for k in ("ace", "kill", "block", "opp_error"):
            n = counts.get(k) or 0
            if not n:
                continue
            # "Label: N" (plural category label) reads grammatically at
            # any count, unlike "N label" which yields "3 kill".
            label = f"{_t(locale, _PT_LABEL_KEYS[k])}: {n}"
            if team_total:
                label += f" ({_pct(n, team_total)}%)"
            parts.append(label)
        card(
            f"{team_label(team)} · {_t(locale, 'pointTypesHeading')}",
            str(total_typed),
            " · ".join(parts),
        )


def _own_error_cards(
    card, team_label, locale: str,
    point_types: dict, error_types: dict, totals_by_team: dict,
) -> None:
    """Own errors: points a team gave away through its own faults,
    i.e. the opponent's ``opp_error`` tally (and its cause breakdown),
    plus the share of the opponent's points those mistakes accounted
    for.
    """
    for team in (1, 2):
        opp = 2 if team == 1 else 1
        gifted = (point_types.get(opp) or {}).get("opp_error") or 0
        if gifted <= 0:
            continue
        opp_total = totals_by_team.get(opp) or 0
        errs = error_types.get(opp) or {}
        # "Label: N" (plural cause label) — grammatical at any count and
        # self-describing, so no separate "errors:" lead-in is needed.
        err_parts = [
            f"{_t(locale, _ET_LABEL_KEYS[k])}: {errs[k]}"
            for k in ERROR_TYPES
            if errs.get(k)
        ]
        detail = (
            _t(locale, "ownErrorsShare", pct=_pct(gifted, opp_total))
            if opp_total else ""
        )
        if err_parts:
            sep = " — " if detail else ""
            detail += sep + " · ".join(err_parts)
        card(
            f"{team_label(team)} · {_t(locale, 'ownErrorsHeading')}",
            str(gifted),
            detail,
        )


def _serve_receive_cards(
    card, team_label, locale: str, serve_receive: dict,
) -> None:
    """Serve/receive split: how many of a team's points came on its
    own serve vs on receive (side-outs). One card per team with at
    least one attributed rally; the value pairs both counts and the
    detail spells out honest denominators — rallies whose server is
    unknown (legacy logs, pre-seed) are excluded from numerator and
    denominator alike, so the percentages never guess.
    """
    for team in (1, 2):
        opp = 2 if team == 1 else 1
        mine = serve_receive.get(team) or {}
        theirs = serve_receive.get(opp) or {}
        serve_total = mine.get("served") or 0
        serve_won = mine.get("won") or 0
        receive_total = theirs.get("served") or 0
        receive_won = receive_total - (theirs.get("won") or 0)
        if serve_total + receive_total <= 0:
            continue
        parts = []
        if serve_total:
            parts.append(_t(
                locale, "serveDetail",
                won=serve_won, total=serve_total,
                pct=_pct(serve_won, serve_total),
            ))
        if receive_total:
            parts.append(_t(
                locale, "receiveDetail",
                won=receive_won, total=receive_total,
                pct=_pct(receive_won, receive_total),
            ))
        card(
            f"{team_label(team)} · {_t(locale, 'serveReceiveHeading')}",
            f"{serve_won} / {receive_won}",
            " · ".join(parts),
        )


def _render_highlights(
    stats: dict, locale: str,
    *, team1_name: str, team2_name: str,
) -> str:
    """Build the Highlights grid (longest streak / comeback / totals / set durations).

    *team1_name* / *team2_name* are the human-readable team labels so
    the cards say "Alpha" instead of the cryptic "Team 1". Falls back
    to the i18n ``team`` template when a card references a team
    number we somehow can't map (defensive — shouldn't happen).
    """
    cards: list[str] = []

    def _team_label(team: int | None) -> str:
        if team == 1:
            return team1_name
        if team == 2:
            return team2_name
        if team:
            return _t(locale, "team", team=team)
        return ""

    def _card(label: str, value: str, detail: str = "") -> None:
        detail_html = (
            f'<div class="detail">{html.escape(detail)}</div>' if detail else ""
        )
        cards.append(
            f'<div class="highlight"><div class="label">{html.escape(label)}</div>'
            f'<div class="value">{html.escape(value)}</div>{detail_html}</div>'
        )

    streak = stats.get("longest_streak") or {}
    if streak.get("n", 0) >= 2 and streak.get("team"):
        _card(
            _t(locale, "highlightStreak"),
            _t(locale, "pointsValue", n=streak["n"]),
            f"{_team_label(streak['team'])} · "
            + _t(locale, "setLabel", n=streak.get("set") or "?"),
        )

    # Set-winning comeback: surface only big erased deficits (≥5 pts).
    set_win = stats.get("set_win_comeback") or {}
    sw_max = max(
        (set_win.get(1) or {}).get("deficit", 0),
        (set_win.get(2) or {}).get("deficit", 0),
    )
    _comeback_card(
        _card, _team_label, locale, set_win,
        qualifies=sw_max >= 5,
        label_key="highlightComeback",
        value_key="deltaValue",
    )

    # Partial comeback: a deficit a team trimmed but couldn't close.
    # Threshold > 3 pts so we don't celebrate a one-rally swing.
    partial = stats.get("partial_comeback") or {}
    p_max = max(
        (partial.get(1) or {}).get("deficit", 0),
        (partial.get(2) or {}).get("deficit", 0),
    )
    _comeback_card(
        _card, _team_label, locale, partial,
        qualifies=p_max > 3,
        label_key="highlightPartialComeback",
        value_key="partialDeltaValue",
    )

    # Biggest lead either team opened. The ≥5 floor matches the
    # set-win comeback threshold — a lead is, after all, the other
    # team's deficit.
    lead = stats.get("biggest_lead") or {}
    lead_max = max(
        (lead.get(1) or {}).get("lead", 0),
        (lead.get(2) or {}).get("lead", 0),
    )
    _comeback_card(
        _card, _team_label, locale, lead,
        qualifies=lead_max >= 5,
        label_key="highlightBiggestLead",
        value_key="leadValue",
        field="lead",
    )

    rally = stats.get("longest_rally") or {}
    rally_duration = rally.get("duration_s") or 0
    if rally_duration >= 1 and rally.get("set"):
        # Sub-second rallies are noise (back-to-back action_log
        # appends at the same wallclock); only show when there's
        # actually a measurable gap.
        _card(
            _t(locale, "highlightLongestRally"),
            _fmt_seconds(rally_duration),
            _t(locale, "setLabel", n=rally["set"]),
        )

    total = stats.get("total_points", 0)
    if total:
        _card(_t(locale, "highlightTotalPoints"), str(total))

    durations = stats.get("set_durations") or {}
    if durations:
        longest = max(durations.items(), key=lambda kv: kv[1])
        shortest = min(durations.items(), key=lambda kv: kv[1])
        _card(
            _t(locale, "highlightLongestSet"),
            _fmt_seconds(longest[1]),
            _t(locale, "setLabel", n=longest[0]),
        )
        if shortest[0] != longest[0]:
            _card(
                _t(locale, "highlightShortestSet"),
                _fmt_seconds(shortest[1]),
                _t(locale, "setLabel", n=shortest[0]),
            )

    # Per-point classification breakdown (opt-in scouting tags). One
    # card per team that recorded at least one classified point; the
    # value is the classified total and the detail spells out the mix,
    # with opponent errors further broken down by cause when tracked.
    point_types = stats.get("point_types") or {}
    error_types = stats.get("error_types") or {}
    totals_by_team = stats.get("total_points_by_team") or {}
    _point_composition_cards(
        _card, _team_label, locale, point_types, totals_by_team,
    )
    _own_error_cards(
        _card, _team_label, locale, point_types, error_types, totals_by_team,
    )
    _serve_receive_cards(
        _card, _team_label, locale, stats.get("serve_receive") or {},
    )

    if not cards:
        # Empty matches still render an explicit "no highlights" card
        # rather than collapsing the whole section into a void.
        _card(_t(locale, "highlights"), "—")
    return "".join(cards)
