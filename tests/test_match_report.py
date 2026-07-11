"""Tests for the print-friendly match report at /match/{match_id}/report."""
import json
import os
import re
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import action_log, match_archive
from app.match_report import match_report_router
from app.overlay_key import is_valid_skey, make_skey

pytestmark = pytest.mark.usefixtures("clean_sessions")

# These legacy print-report tests predate the per-user storage keys and seed
# matches by bare oid. Match reports are DB-backed and keyed by a real user
# now, so a single autouse fixture transparently maps every bare oid to a
# fixed "reporter" user's storage key (archival, listing, deletion, and the
# audit-log writes), keeping the tests focused on report rendering / access.
_REPORTER_UID = 0


def _sk(oid):
    """Map a bare oid to the reporter user's storage key (skey pass-through)."""
    if oid is None or is_valid_skey(oid):
        return oid
    return make_skey(_REPORTER_UID, oid)


@pytest.fixture(autouse=True)
def _reporter_user(db_session, monkeypatch):
    from app.auth import service

    global _REPORTER_UID
    user = service.create_user(db_session, username="reporter", password="password123")
    db_session.commit()
    _REPORTER_UID = user.id

    real_archive = match_archive.archive_match
    real_list = match_archive.list_matches
    real_delete_for = match_archive.delete_for_oid
    real_append = action_log.append
    monkeypatch.setattr(match_archive, "archive_match", lambda oid, **kw: real_archive(_sk(oid), **kw))
    monkeypatch.setattr(match_archive, "list_matches", lambda oid=None: real_list(_sk(oid)))
    monkeypatch.setattr(match_archive, "delete_for_oid", lambda oid: real_delete_for(_sk(oid)))
    monkeypatch.setattr(action_log, "append", lambda oid, *a, **k: real_append(_sk(oid), *a, **k))


def _seed_realistic_audit(oid: str, base_ts: float) -> None:
    """Write a deterministic audit JSONL covering streak, comeback,
    running-score and undo paths. Bypasses ``action_log.append`` so the
    timestamps we care about don't depend on wallclock.
    """
    import json
    import os

    from app.api import action_log as _al

    records: list[dict] = []

    def _add(action: str, params: dict, result: dict, offset: float) -> None:
        # Mirror the live engine: every audit result snapshots the
        # post-action serve, and in volleyball the serve follows the
        # rally winner. This feeds the serve/receive breakdown the
        # same way real logs do.
        if action == "add_point" and params.get("team") in (1, 2):
            result.setdefault("serve", "A" if params["team"] == 1 else "B")
        records.append({
            "ts": base_ts + offset,
            "action": action,
            "params": params,
            "result": result,
        })

    # Set 1: team 1 takes a 5-0 streak (longest streak), team 2 catches up.
    for i in range(5):
        _add("add_point", {"team": 1, "undo": False},
             {"current_set": 1, "team_1": {"score": i + 1},
              "team_2": {"score": 0}}, offset=i * 30)
    _add("add_point", {"team": 2, "undo": False},
         {"current_set": 1, "team_1": {"score": 5},
          "team_2": {"score": 1}}, offset=180)
    _add("add_point", {"team": 2, "undo": False},
         {"current_set": 1, "team_1": {"score": 5},
          "team_2": {"score": 2}}, offset=210)
    # An undo pair: team 2 scores then retracts. The retraction must
    # mark the prior record as ``_was_undone`` in the collapsed timeline.
    _add("add_point", {"team": 2, "undo": False},
         {"current_set": 1, "team_1": {"score": 5},
          "team_2": {"score": 3}}, offset=240)
    _add("add_point", {"team": 2, "undo": True},
         {"current_set": 1, "team_1": {"score": 5},
          "team_2": {"score": 2}}, offset=260)

    # Set 2: 6-0 deficit then full comeback (biggest comeback = 6 points).
    for i in range(6):
        _add("add_point", {"team": 1, "undo": False},
             {"current_set": 2, "team_1": {"score": i + 1},
              "team_2": {"score": 0}}, offset=600 + i * 30)
    _add("add_point", {"team": 2, "undo": False},
         {"current_set": 2, "team_1": {"score": 6},
          "team_2": {"score": 1}}, offset=900)
    _add("add_point", {"team": 2, "undo": False},
         {"current_set": 2, "team_1": {"score": 22},
          "team_2": {"score": 25}}, offset=1500)

    path = _al._path(_sk(oid))
    assert path is not None, "action_log path resolution failed in test"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, separators=(",", ":"), ensure_ascii=False) + "\n")


@pytest.fixture
def rich_match():
    """A match snapshot with a realistic audit log — exercises the
    running-score, comeback, streak, undo and chart paths in one go.
    """
    base_ts = time.time() - 3600
    _seed_realistic_audit("rich-1", base_ts)
    match_id = match_archive.archive_match(
        oid="rich-1",
        final_state={
            "current_set": 2,
            "team_1": {"sets": 0, "timeouts": 0,
                       "scores": {"set_1": 25, "set_2": 22}},
            "team_2": {"sets": 2, "timeouts": 1,
                       "scores": {"set_1": 23, "set_2": 25}},
        },
        customization={
            "Team 1 Name": "Alpha",
            "Team 2 Name": "Bravo",
            "Team 1 Logo": "https://example.com/alpha.png",
            "Color 1": "#0047AB",
            "Color 2": "#E21836",
            "Text Color 1": "#FFFFFF",
            "Text Color 2": "#FFFFFF",
        },
        started_at=base_ts,
        winning_team=2,
        points_limit=25,
        points_limit_last_set=15,
        sets_limit=3,
    )
    assert match_id is not None
    return match_id


@pytest.fixture
def client(monkeypatch):
    """Default client: report endpoint open via MATCH_REPORT_PUBLIC.

    Tests that exercise the auth gate use ``gated_client`` instead.
    """
    monkeypatch.setenv("MATCH_REPORT_PUBLIC", "true")
    monkeypatch.delenv("OVERLAY_MANAGER_PASSWORD", raising=False)
    app = FastAPI()
    app.include_router(match_report_router)
    return TestClient(app)


@pytest.fixture
def archived_match():
    """Seed a fully-populated archive snapshot and return its match_id."""
    action_log.append("rep-1", "add_point", {"team": 1, "undo": False},
                      {"team_1": {"score": 1}})
    action_log.append("rep-1", "add_point", {"team": 2, "undo": False},
                      {"team_2": {"score": 1}})
    match_id = match_archive.archive_match(
        oid="rep-1",
        final_state={
            "current_set": 4,
            "team_1": {
                "sets": 3,
                "timeouts": 2,
                "scores": {"set_1": 25, "set_2": 18, "set_3": 25,
                           "set_4": 25, "set_5": 0},
            },
            "team_2": {
                "sets": 1,
                "timeouts": 1,
                "scores": {"set_1": 18, "set_2": 25, "set_3": 22,
                           "set_4": 21, "set_5": 0},
            },
        },
        customization={
            "Team 1 Name": "Thunder Wolves",
            "Team 2 Name": "Solar Hawks",
            "Color 1": "#0047AB",
            "Color 2": "#FFD700",
            "Text Color 1": "#FFFFFF",
            "Text Color 2": "#000000",
        },
        started_at=time.time() - 5400,
        winning_team=1,
        points_limit=25,
        points_limit_last_set=15,
        sets_limit=5,
    )
    assert match_id is not None
    return match_id


class TestMatchReportTemplateStructure:
    """Structural guardrails for the ``str.format``-based templates.

    The report module renders HTML by ``str.format``-ing the
    ``_REPORT_TEMPLATE`` string template.
    A stray single ``{`` or ``}`` in a CSS / JS block would parse
    fine when the file loads but raise ``KeyError`` (or ``IndexError``)
    the next time the report is rendered — a runtime regression
    that's invisible to type checkers and easy to introduce when
    adding new style rules. ``string.Formatter().parse()`` does the
    bracket-matching pass without needing actual values, so we run
    it once per template here as a fast structural smoke test.
    """

    @pytest.mark.parametrize("name", ["_REPORT_TEMPLATE"])
    def test_template_has_balanced_braces(self, name):
        import string

        import app.match_report as mr
        tpl = getattr(mr, name)
        # Forces the formatter to scan every brace — a literal single
        # ``{`` (without a matching ``}`` or its escaped ``{{`` form)
        # raises ``ValueError`` here, surfacing the bug in CI instead
        # of in a 500 response from /match/{id}/report.
        list(string.Formatter().parse(tpl))


class TestMatchReport:
    def test_404_for_unknown_match(self, client):
        response = client.get("/match/match_zzzz_invalid/report")
        assert response.status_code == 404

    def test_404_for_path_traversal(self, client):
        response = client.get("/match/..%2F..%2Fetc%2Fpasswd/report")
        assert response.status_code in (404, 422)

    def test_renders_html(self, client, archived_match):
        response = client.get(f"/match/{archived_match}/report")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_renders_team_names(self, client, archived_match):
        response = client.get(f"/match/{archived_match}/report")
        assert "Thunder Wolves" in response.text
        assert "Solar Hawks" in response.text

    def test_renders_team_names_from_legacy_text_name_alias(self, client):
        """Customization that uses the legacy ``Team {n} Text Name``
        alias (``Customization.A_TEAM`` / ``B_TEAM``) instead of the
        canonical ``Team {n} Name`` should still surface the names
        in the report. Regression: UNO-backed sessions round-trip
        the legacy form via the overlays.uno cloud customization
        API, and an earlier version of ``_team_name`` only checked
        the canonical key — so UNO match reports rendered the
        literal ``Team 1`` / ``Team 2`` fallback strings.
        """
        action_log.append(
            "legacy-1", "add_point", {"team": 1, "undo": False},
            {"team_1": {"score": 1}},
        )
        match_id = match_archive.archive_match(
            oid="legacy-1",
            final_state={
                "current_set": 1,
                "team_1": {"sets": 0, "timeouts": 0,
                           "scores": {"set_1": 1}},
                "team_2": {"sets": 0, "timeouts": 0,
                           "scores": {"set_1": 0}},
            },
            customization={
                # Legacy alias only — no canonical key.
                "Team 1 Text Name": "Aurora",
                "Team 2 Text Name": "Boreal",
            },
            started_at=time.time() - 60,
            sets_limit=3,
        )
        assert match_id is not None
        response = client.get(f"/match/{match_id}/report")
        assert response.status_code == 200
        assert "Aurora" in response.text
        assert "Boreal" in response.text
        # Sanity: the literal fallback strings should NOT appear.
        assert ">Team 1<" not in response.text
        assert ">Team 2<" not in response.text

    def test_lang_query_overrides_accept_language(self, client, archived_match):
        """An explicit ``?lang=`` should win over the browser's
        ``Accept-Language`` header so an operator who shares the
        report from a Spanish-set control UI doesn't get an
        English render at the receiving end (browser default).
        """
        # Browser advertises French; operator's link forces ``es``.
        response = client.get(
            f"/match/{archived_match}/report?lang=es",
            headers={"Accept-Language": "fr"},
        )
        assert response.status_code == 200
        # Spanish ``setByset`` heading is unique enough to be a
        # cheap locale fingerprint.
        assert "Set a set" in response.text
        # Defensive — no stray French / English heading from a
        # half-applied locale override.
        assert "Set par set" not in response.text

    def test_lang_query_falls_back_to_accept_language_when_unknown(
        self, client, archived_match,
    ):
        """An unknown ``?lang=`` value falls through to
        ``Accept-Language`` rather than locking the report into
        the default. Mirrors how ``resolve_locale`` already
        handles malformed ``Accept-Language`` tokens.
        """
        response = client.get(
            f"/match/{archived_match}/report?lang=xx",
            headers={"Accept-Language": "es"},
        )
        assert response.status_code == 200
        assert "Set a set" in response.text

    def test_hostile_lang_never_reflects_into_markup(
        self, client, archived_match,
    ):
        """Regression for CodeQL ``py/reflective-xss``: the resolved
        locale flows into ``<html lang="…">`` unquoted, so a hostile
        ``?lang=`` / ``Accept-Language`` must both fall back to a
        supported tag and never echo attacker bytes into the page.
        """
        payload = '"><script>alert(1)</script>'
        response = client.get(
            f"/match/{archived_match}/report",
            params={"lang": payload},
            headers={"Accept-Language": f"{payload}, es;q=0.9"},
        )
        assert response.status_code == 200
        assert "<script>alert(1)" not in response.text
        # The malformed tags fall through to the ``es`` header entry.
        assert 'lang="es"' in response.text

    def test_renders_final_score(self, client, archived_match):
        response = client.get(f"/match/{archived_match}/report")
        # Set scores 3-1; the winner is implicit from those plus the
        # ``Team 1 3 – 1 Team 2`` page title (no separate badge — the
        # scores themselves carry the verdict).
        assert ">3<" in response.text
        assert ">1<" in response.text
        # The legacy "Match winner" badge below the winning team's
        # score has been removed; just being a higher number says it.
        assert "Match winner" not in response.text

    def test_renders_set_by_set_table(self, client, archived_match):
        response = client.get(f"/match/{archived_match}/report")
        for score in ("25", "18", "22", "21"):
            assert score in response.text

    def test_renders_audit_timeline(self, client, archived_match):
        response = client.get(f"/match/{archived_match}/report")
        # Two add_point entries were logged before archive.
        assert "Point — Team 1" in response.text
        assert "Point — Team 2" in response.text

    def test_uses_team_colors_from_customization(self, client, archived_match):
        response = client.get(f"/match/{archived_match}/report")
        assert "#0047AB" in response.text
        assert "#FFD700" in response.text

    def test_oid_is_not_exposed_in_report_html(self, client, archived_match):
        # The single-match report URL uses an opaque hash-prefixed
        # match_id, not the OID — so the OID is not derivable from
        # the link. The page must not leak it back, otherwise anyone
        # who receives a report URL learns which control session
        # produced it. Both the literal OID string and the "OID"
        # label row must be gone.
        response = client.get(f"/match/{archived_match}/report")
        assert response.status_code == 200
        assert "rep-1" not in response.text
        assert ">OID<" not in response.text

    # ── Print toolbar + page-break hints ───────────────────────────────

    def test_renders_print_and_copy_toolbar(self, client, archived_match):
        response = client.get(f"/match/{archived_match}/report")
        assert 'data-action="print"' in response.text
        assert 'data-action="copy"' in response.text
        # Permalink anchor on the toolbar; lets the JS grab it without
        # parsing window.location.
        assert f'data-permalink="/match/{archived_match}/report"' in response.text
        # Print button carries the include-log prompt as a
        # ``data-include-prompt`` attribute so the JS can confirm()
        # without re-fetching translations.
        assert "data-include-prompt=" in response.text
        # Timeline section gets an id so the JS can toggle ``print-hidden``.
        assert 'id="report-timeline-section"' in response.text
        assert ".print-hidden" in response.text

    def _seed_minimal_chart_audit(self, oid: str) -> None:
        """Two-point audit log so the chart layer has something to plot."""
        from app.api import action_log as _al
        records = [
            {"ts": time.time(), "action": "add_point",
             "params": {"team": 1, "undo": False},
             "result": {"current_set": 1, "team_1": {"score": 1},
                        "team_2": {"score": 0}}},
            {"ts": time.time() + 1, "action": "add_point",
             "params": {"team": 2, "undo": False},
             "result": {"current_set": 1, "team_1": {"score": 1},
                        "team_2": {"score": 1}}},
        ]
        path = _al._path(_sk(oid))
        assert path is not None
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")

    def test_team_color_priority_prefers_team_identity_keys(self, client):
        # The customization separates *overlay* colours (alternating
        # row strips, ``Color 1`` / ``Color 2``) from *team identity*
        # colours (``Team 1 Color`` / ``Team 2 Color``). The report
        # should pick the team's own colour even when both kinds are
        # set — otherwise team 2's chart line snaps to whatever the
        # overlay's row 2 happens to be (often the default red).
        oid = "color-priority"
        self._seed_minimal_chart_audit(oid)
        match_id = match_archive.archive_match(
            oid=oid,
            final_state={
                "team_1": {"sets": 0, "scores": {"set_1": 1}},
                "team_2": {"sets": 0, "scores": {"set_1": 1}},
            },
            customization={
                "Team 1 Name": "A",
                "Team 2 Name": "B",
                # Overlay-wide row colours — should NOT win.
                "Color 1": "#000000",
                "Color 2": "#E21836",
                # Team identity colours — should win.
                "Team 1 Color": "#FFFFFF",
                "Team 1 Text Color": "#000000",
                "Team 2 Color": "#0047AB",
                "Team 2 Text Color": "#FFFFFF",
            },
            winning_team=None, sets_limit=3,
        )
        response = client.get(f"/match/{match_id}/report")
        # Team 2's chart polyline should be blue (the team-identity
        # colour) — not red (the overlay's ``Color 2`` row).
        assert 'stroke="#0047AB"' in response.text
        assert 'stroke="#E21836"' not in response.text

    def test_chart_uses_contrast_safe_color_for_white_team(self, client):
        # Team 2 picks pure white as its primary brand colour. That's
        # invisible on the report's white surface, so the chart layer
        # should snap to the team's text colour or the fallback palette
        # instead.
        oid = "white-team"
        self._seed_minimal_chart_audit(oid)
        match_id = match_archive.archive_match(
            oid=oid,
            final_state={
                "team_1": {"sets": 0, "scores": {"set_1": 1}},
                "team_2": {"sets": 0, "scores": {"set_1": 1}},
            },
            customization={
                "Team 1 Name": "A",
                "Team 2 Name": "B",
                "Color 1": "#0047AB",
                "Color 2": "#FFFFFF",
                "Text Color 1": "#FFFFFF",
                "Text Color 2": "#000000",
            },
            winning_team=None, sets_limit=3,
        )
        response = client.get(f"/match/{match_id}/report")
        # The chart for team 2 must use a darker colour (text colour
        # ``#000000`` or the fallback palette).
        assert ('stroke="#000000"' in response.text
                or 'stroke="#E21836"' in response.text)

    def test_chart_colors_are_distinct_when_both_teams_share_a_colour(
            self, client):
        # Both teams pick the same brand colour. The chart layer
        # forces a fallback on team 2 so the polylines remain
        # distinguishable.
        oid = "same-team-color"
        self._seed_minimal_chart_audit(oid)
        match_id = match_archive.archive_match(
            oid=oid,
            final_state={
                "team_1": {"sets": 0, "scores": {"set_1": 1}},
                "team_2": {"sets": 0, "scores": {"set_1": 1}},
            },
            customization={
                "Team 1 Name": "A",
                "Team 2 Name": "B",
                "Color 1": "#0047AB",
                "Color 2": "#0047AB",
                "Text Color 1": "#FFFFFF",
                "Text Color 2": "#FFFFFF",
            },
            winning_team=None, sets_limit=3,
        )
        response = client.get(f"/match/{match_id}/report")
        assert 'stroke="#0047AB"' in response.text
        assert 'stroke="#E21836"' in response.text

    def test_print_media_query_hides_toolbar_and_unbounds_timeline(
            self, client, archived_match):
        response = client.get(f"/match/{archived_match}/report")
        assert "@media print" in response.text
        assert ".toolbar { display: none; }" in response.text
        assert "break-inside: avoid" in response.text

    # ── Team logos ─────────────────────────────────────────────────────

    def test_renders_team_logo_when_customization_has_url(self, client):
        match_id = match_archive.archive_match(
            oid="logo-1",
            final_state={"team_1": {"sets": 0}, "team_2": {"sets": 0}},
            customization={
                "Team 1 Logo": "https://example.com/alpha.png",
                "Team 2 Logo": "data:image/png;base64,iVBORw0",
            },
            winning_team=1, sets_limit=3,
        )
        response = client.get(f"/match/{match_id}/report")
        assert 'src="https://example.com/alpha.png"' in response.text
        assert 'src="data:image/png;base64,iVBORw0"' in response.text

    def test_logo_with_dangerous_scheme_is_dropped(self, client):
        match_id = match_archive.archive_match(
            oid="logo-xss",
            final_state={"team_1": {"sets": 0}, "team_2": {"sets": 0}},
            customization={
                "Team 1 Logo": "javascript:alert(1)",
                "Team 2 Logo": "  http://ok.example/img.png  ",
            },
            winning_team=1, sets_limit=3,
        )
        response = client.get(f"/match/{match_id}/report")
        assert "javascript:alert(1)" not in response.text
        # The other team's safe URL still renders (whitespace stripped).
        assert 'src="http://ok.example/img.png"' in response.text


class TestChartColorContrast:
    """``_chart_color`` must keep every polyline readable on the chart surface.

    The old luminance cap waved through light-but-not-white brand colours
    (e.g. ``#d3d3d3``) that then sat at ~1.3:1 against the grey ``#fafafa``
    surface — effectively invisible. The contrast-ratio model guarantees a
    floor and preserves hue by darkening rather than discarding the colour.
    """

    @staticmethod
    def _contrast(c1, c2):
        from app.match_report_render import _relative_luminance
        l1, l2 = _relative_luminance(c1), _relative_luminance(c2)
        lo, hi = sorted((l1, l2))
        return (hi + 0.05) / (lo + 0.05)

    @pytest.mark.parametrize(
        "brand,fg",
        [
            ("#ffffff", "#000000"),  # white brand, dark text
            ("#ffffff", "#f5f5f5"),  # white brand, light text (worst case)
            ("#e0e0e0", "#ffffff"),  # light grey brand + light text
            ("#d3d3d3", "#ffffff"),  # lightgrey brand
            ("#cccccc", "#eeeeee"),  # silver brand + light text
            ("#90ee90", "#ffffff"),  # pale green
            ("#0047ab", "#ffffff"),  # already-strong brand
        ],
    )
    def test_every_resolved_colour_clears_the_contrast_floor(self, brand, fg):
        from app.match_report_render import (
            _CHART_SURFACE,
            _MIN_CHART_CONTRAST,
            _chart_color,
        )
        for team in (1, 2):
            resolved = _chart_color(team, brand, fg)
            assert self._contrast(resolved, _CHART_SURFACE) >= _MIN_CHART_CONTRAST

    def test_light_coloured_brand_keeps_its_hue(self):
        # A pale green that fails the floor is darkened (green channel stays
        # dominant), not swapped for the generic blue/red fallback.
        from app.match_report_render import _CHART_FALLBACK, _chart_color, _hex_to_rgb
        resolved = _chart_color(1, "#90ee90", "#ffffff")
        assert resolved not in _CHART_FALLBACK
        r, g, b = _hex_to_rgb(resolved)
        assert g > r and g > b

    def test_strong_brand_colour_is_left_untouched(self):
        from app.match_report_render import _chart_color
        assert _chart_color(1, "#0047AB", "#ffffff") == "#0047AB"

    @pytest.mark.parametrize(
        "brand,fg",
        [
            ("#000000", "#ffffff"),  # black brand, would vanish on dark
            ("#00234f", "#0a0a0a"),  # navy brand + dark text (worst case)
            ("#1a1a1a", "#333333"),  # near-surface greys
            ("#90ee90", "#ffffff"),  # pale green (fine on dark already)
            ("#0047ab", "#ffffff"),  # cobalt — too dark for #1e1e1e
        ],
    )
    def test_dark_surface_colours_clear_the_floor(self, brand, fg):
        from app.match_report_render import (
            _CHART_FALLBACK_DARK,
            _CHART_SURFACE_DARK,
            _MIN_CHART_CONTRAST,
            _chart_color,
        )
        for team in (1, 2):
            resolved = _chart_color(
                team, brand, fg,
                surface=_CHART_SURFACE_DARK, fallbacks=_CHART_FALLBACK_DARK,
            )
            assert self._contrast(resolved, _CHART_SURFACE_DARK) \
                >= _MIN_CHART_CONTRAST

    def test_dark_brand_is_lightened_keeping_hue(self):
        # A navy that fails on the dark surface is lifted toward white
        # (blue channel stays dominant), not swapped for the fallback.
        from app.match_report_render import (
            _CHART_FALLBACK_DARK,
            _CHART_SURFACE_DARK,
            _chart_color,
            _hex_to_rgb,
        )
        resolved = _chart_color(
            1, "#00234f", "#0a0a0a",
            surface=_CHART_SURFACE_DARK, fallbacks=_CHART_FALLBACK_DARK,
        )
        assert resolved not in _CHART_FALLBACK_DARK
        r, g, b = _hex_to_rgb(resolved)
        assert b > r and b > g

    def test_dark_fallback_palette_clears_the_floor(self):
        from app.match_report_render import (
            _CHART_FALLBACK_DARK,
            _CHART_SURFACE_DARK,
            _MIN_CHART_CONTRAST,
        )
        for color in _CHART_FALLBACK_DARK:
            assert self._contrast(color, _CHART_SURFACE_DARK) \
                >= _MIN_CHART_CONTRAST


class TestMatchReportI18n:
    """Locale resolution from ``Accept-Language`` header."""

    def test_default_locale_is_english(self, client, archived_match):
        response = client.get(f"/match/{archived_match}/report")
        assert response.status_code == 200
        assert "Match facts" in response.text
        assert 'lang="en"' in response.text

    def test_spanish_when_accept_language_es(self, client, archived_match):
        response = client.get(
            f"/match/{archived_match}/report",
            headers={"Accept-Language": "es-ES,es;q=0.9,en;q=0.8"},
        )
        assert "Datos del partido" in response.text
        assert 'lang="es"' in response.text

    def test_german_when_accept_language_de(self, client, archived_match):
        response = client.get(
            f"/match/{archived_match}/report",
            headers={"Accept-Language": "de"},
        )
        assert "Spieldaten" in response.text

    def test_unknown_locale_falls_back_to_english(self, client, archived_match):
        response = client.get(
            f"/match/{archived_match}/report",
            headers={"Accept-Language": "kl,xx-YY"},
        )
        assert "Match facts" in response.text


class TestMatchReportRichSections:
    """Coverage for highlights, charts, timeline running-score and undo collapse."""

    def test_highlights_section_renders(self, client, rich_match):
        response = client.get(f"/match/{rich_match}/report")
        # Header is rendered via i18n; the seeded audit guarantees the
        # streak / comeback / total / set-duration cards all qualify.
        assert "Highlights" in response.text
        assert ">5 pts<" in response.text or "5 pts" in response.text  # 5-0 streak
        # Biggest set-winning comeback in this audit is 6 (team 2
        # trailed 0-6 in set 2 and won it 25-22), well above the
        # 5-point threshold.
        assert "down 6" in response.text or ">6<" in response.text
        assert "Biggest set-winning comeback" in response.text

    def test_charts_render_inline_svg_per_set(self, client, rich_match):
        response = client.get(f"/match/{rich_match}/report")
        # One per played set in the audit (1 and 2). The SVG class
        # is stable; both colours from the customization should appear.
        assert response.text.count('class="set-chart"') == 2
        assert "#0047AB" in response.text
        assert "#E21836" in response.text

    def test_chart_marks_data_points_and_labels_axes(
            self, client, rich_match):
        response = client.get(f"/match/{rich_match}/report")
        # Each rally has a marker per team, so the page is full of
        # ``<circle>`` elements; we just need at least a handful to
        # confirm the markers are emitted at all.
        assert response.text.count("<circle") >= 8
        # Y-axis ticks always include 0.
        assert ">0</text>" in response.text
        # The rich fixture's audit timestamps are tightly spaced
        # (max gap < 15 min), so the time-axis branch kicks in and
        # labels read ``0:00`` (left) / ``M:SS`` (right).
        assert 'data-x-axis="time"' in response.text
        assert ">0:00</text>" in response.text

    def test_highlights_use_team_names_not_indices(self, client, rich_match):
        response = client.get(f"/match/{rich_match}/report")
        # The timeline still spells out ``Team 1 / Team 2`` in the
        # action labels (that's the audit-log idiom), so we slice
        # just the highlights region to assert *that* uses the
        # human-readable name from customization.
        body = response.text
        start = body.index('<div class="highlights">')
        # Find the closing div for the highlights section: it's the
        # one matching ``<div class="highlights">``. Walk forward
        # collecting nested divs.
        depth = 1
        cursor = start + len('<div class="highlights">')
        while depth and cursor < len(body):
            next_open = body.find('<div', cursor)
            next_close = body.find('</div>', cursor)
            if next_close == -1:
                break
            if next_open != -1 and next_open < next_close:
                depth += 1
                cursor = next_open + 4
            else:
                depth -= 1
                cursor = next_close + 6
        highlights_block = body[start:cursor]
        # Highlights mention real team names — ``Alpha`` / ``Bravo``
        # — rather than the opaque ``Team 1`` label.
        assert "Alpha" in highlights_block
        assert "Bravo" in highlights_block
        assert "Team 1" not in highlights_block
        assert "Team 2" not in highlights_block

    def test_set_winning_point_groups_under_previous_set(self, client):
        # Set-winning ``add_point`` records advance ``current_set`` in
        # the audit result, but the scores still belong to the set
        # that just ended. ``score_set`` tags this in the audit log;
        # the report must use it so the winning point doesn't
        # leak into the *next* set's timeline / chart.
        oid = "score-set-bug"
        from app.api import action_log as _al
        records = [
            # Set 1: just one point to keep the fixture small.
            {"ts": 1700000000, "action": "add_point",
             "params": {"team": 1, "undo": False},
             "result": {"current_set": 1, "score_set": 1,
                        "team_1": {"score": 1},
                        "team_2": {"score": 0}}},
            # Set-winning point of set 1: ``current_set`` has advanced
            # to 2 but ``score_set`` keeps the scores anchored to 1.
            {"ts": 1700000010, "action": "add_point",
             "params": {"team": 1, "undo": False},
             "result": {"current_set": 2, "score_set": 1,
                        "team_1": {"score": 25},
                        "team_2": {"score": 18}}},
            # First real point of set 2.
            {"ts": 1700000020, "action": "add_point",
             "params": {"team": 1, "undo": False},
             "result": {"current_set": 2, "score_set": 2,
                        "team_1": {"score": 1},
                        "team_2": {"score": 0}}},
        ]
        path = _al._path(_sk(oid))
        assert path is not None
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")
        match_id = match_archive.archive_match(
            oid=oid,
            final_state={
                "team_1": {"sets": 1,
                           "scores": {"set_1": 25, "set_2": 1}},
                "team_2": {"sets": 0,
                           "scores": {"set_1": 18, "set_2": 0}},
            },
            customization={"Team 1 Name": "A", "Team 2 Name": "B"},
            winning_team=1, sets_limit=3,
        )
        response = client.get(f"/match/{match_id}/report")
        # The 25-18 record is grouped under set 1 — set 2's running
        # scores in the timeline must NOT include ``(25–18)``. The
        # timeline groups its sets with ``<section class="timeline-set">``,
        # so we slice between those markers to scope the assertion.
        body = response.text
        timeline_set1 = body.index('<section class="timeline-set"')
        timeline_set2 = body.index(
            '<section class="timeline-set"', timeline_set1 + 1,
        )
        set1_slice = body[timeline_set1:timeline_set2]
        set2_slice = body[timeline_set2:body.index("</div>", timeline_set2)]
        assert "25–18" in set1_slice
        assert "25–18" not in set2_slice

    def test_chart_x_axis_uses_mmss_label_when_time_mode(self, client):
        # Two points 90 s apart in set 1 → time-axis kicks in. Right
        # label should be ``1:30``, left label ``0:00``.
        oid = "axis-time-label"
        from app.api import action_log as _al
        records = [
            {"ts": 1700000000, "action": "add_point",
             "params": {"team": 1, "undo": False},
             "result": {"current_set": 1, "score_set": 1,
                        "team_1": {"score": 1},
                        "team_2": {"score": 0}}},
            {"ts": 1700000090, "action": "add_point",
             "params": {"team": 2, "undo": False},
             "result": {"current_set": 1, "score_set": 1,
                        "team_1": {"score": 1},
                        "team_2": {"score": 1}}},
        ]
        path = _al._path(_sk(oid))
        assert path is not None
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")
        match_id = match_archive.archive_match(
            oid=oid,
            final_state={"team_1": {"scores": {"set_1": 1}},
                         "team_2": {"scores": {"set_1": 1}}},
            customization={"Team 1 Name": "A", "Team 2 Name": "B"},
            winning_team=None, sets_limit=3,
        )
        response = client.get(f"/match/{match_id}/report")
        assert 'data-x-axis="time"' in response.text
        assert ">0:00</text>" in response.text
        assert ">1:30</text>" in response.text

    def test_chart_x_axis_falls_back_to_rally_when_gap_exceeds_15_min(
            self, client):
        # 16-minute lull between two consecutive points in a set: the
        # operator was probably AFK, so the timestamps stop reflecting
        # play. Chart falls back to rally-number indexing — left
        # label ``1``, right label = number of points (3 here).
        oid = "axis-fallback"
        from app.api import action_log as _al
        records = [
            {"ts": 1700000000, "action": "add_point",
             "params": {"team": 1, "undo": False},
             "result": {"current_set": 1, "score_set": 1,
                        "team_1": {"score": 1},
                        "team_2": {"score": 0}}},
            {"ts": 1700000030, "action": "add_point",
             "params": {"team": 2, "undo": False},
             "result": {"current_set": 1, "score_set": 1,
                        "team_1": {"score": 1},
                        "team_2": {"score": 1}}},
            # 16 min later — exceeds the threshold.
            {"ts": 1700000030 + 16 * 60, "action": "add_point",
             "params": {"team": 1, "undo": False},
             "result": {"current_set": 1, "score_set": 1,
                        "team_1": {"score": 2},
                        "team_2": {"score": 1}}},
        ]
        path = _al._path(_sk(oid))
        assert path is not None
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")
        match_id = match_archive.archive_match(
            oid=oid,
            final_state={"team_1": {"scores": {"set_1": 2}},
                         "team_2": {"scores": {"set_1": 1}}},
            customization={"Team 1 Name": "A", "Team 2 Name": "B"},
            winning_team=None, sets_limit=3,
        )
        response = client.get(f"/match/{match_id}/report")
        assert 'data-x-axis="rally"' in response.text
        # Rally-axis labels: ``1`` (left), ``3`` (right).
        assert ">1</text>" in response.text
        assert ">3</text>" in response.text

    def test_chart_x_axis_falls_back_to_rally_on_non_monotonic_timestamps(
            self, client):
        # Clock skew / NTP correction: a later record has an earlier
        # ``ts`` than its predecessor. Plotting time-mode would put
        # the second point at a negative x and outside the SVG
        # viewport — fall back to rally-number indexing instead.
        oid = "axis-skew"
        from app.api import action_log as _al
        records = [
            {"ts": 1700000100, "action": "add_point",
             "params": {"team": 1, "undo": False},
             "result": {"current_set": 1, "score_set": 1,
                        "team_1": {"score": 1},
                        "team_2": {"score": 0}}},
            # 30 s *earlier* than the previous record.
            {"ts": 1700000070, "action": "add_point",
             "params": {"team": 2, "undo": False},
             "result": {"current_set": 1, "score_set": 1,
                        "team_1": {"score": 1},
                        "team_2": {"score": 1}}},
        ]
        path = _al._path(_sk(oid))
        assert path is not None
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")
        match_id = match_archive.archive_match(
            oid=oid,
            final_state={"team_1": {"scores": {"set_1": 1}},
                         "team_2": {"scores": {"set_1": 1}}},
            customization={"Team 1 Name": "A", "Team 2 Name": "B"},
            winning_team=None, sets_limit=3,
        )
        response = client.get(f"/match/{match_id}/report")
        assert 'data-x-axis="rally"' in response.text

    def test_longest_rally_card_renders(self, client, rich_match):
        response = client.get(f"/match/{rich_match}/report")
        # The rich fixture's set 2 has a 5m 0s gap (last point at
        # offset 1500, second-to-last at 900 — but those aren't
        # consecutive in the audit; the actual sorted gap depends
        # on the seed). Any non-zero rally duration should produce
        # the card with the i18n label.
        assert "Longest rally" in response.text

    def test_longest_rally_ignores_manual_score_overrides(self, client):
        # Operator scores 1-0 at t=0 then *5 minutes* later corrects
        # the score via ``set_score`` (typo / late edit). That gap is
        # editorial, not a real rally — the longest-rally card
        # should ignore it and fall back to the actual ``add_point``
        # cadence (which here is just a single point, not enough
        # for a rally calculation).
        oid = "rally-edit"
        from app.api import action_log as _al
        records = [
            {"ts": 1700000000, "action": "add_point",
             "params": {"team": 1, "undo": False},
             "result": {"current_set": 1, "team_1": {"score": 1},
                        "team_2": {"score": 0}}},
            {"ts": 1700000300, "action": "set_score",
             "params": {"team": 1, "set_number": 1, "value": 5},
             "result": {"current_set": 1, "team_1": {"score": 5},
                        "team_2": {"score": 0}}},
        ]
        path = _al._path(_sk(oid))
        assert path is not None
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")
        match_id = match_archive.archive_match(
            oid=oid,
            final_state={"team_1": {"scores": {"set_1": 5}},
                         "team_2": {"scores": {"set_1": 0}}},
            customization={"Team 1 Name": "A", "Team 2 Name": "B"},
            winning_team=None, sets_limit=3,
        )
        response = client.get(f"/match/{match_id}/report")
        # The set-duration row legitimately shows ``5m 00s`` (set 1
        # spans 300 s of audit timestamps), but the longest-rally
        # card must not exist at all — there's only one ``add_point``
        # in the fixture, so no consecutive-rally gap to measure.
        assert "Longest rally" not in response.text

    def test_timeline_groups_by_set_and_shows_running_score(
            self, client, rich_match):
        response = client.get(f"/match/{rich_match}/report")
        # Grouped sections — one per set. Running score is rendered as
        # ``(t1-t2)`` next to point actions.
        assert response.text.count('class="timeline-set"') >= 2
        assert "(5–0)" in response.text  # mid-streak running score
        assert "(22–25)" in response.text  # set-2 final running score

    def test_timeline_uses_relative_timestamps(self, client, rich_match):
        response = client.get(f"/match/{rich_match}/report")
        # Base ts == first record (offset 0) → ``+0:00``. Later offsets
        # progress monotonically. Spot-check a known offset (180s = +3:00).
        assert "+0:00" in response.text
        assert "+3:00" in response.text

    def test_undo_pairs_disappear_from_timeline(self, client, rich_match):
        """Both halves of an undo pair (the forward action and the
        explicit undo) should be stripped from the rendered timeline
        — the report reads as if the action never happened. Replaces
        the legacy strikethrough behaviour, which left the forward
        line struck-through with an "↶ Undone" badge.
        """
        import re
        response = client.get(f"/match/{rich_match}/report")
        text = response.text
        # No row carries the ``undone`` modifier any more.
        assert not re.search(r'class="timeline-li[^"]*\bundone\b', text)
        assert 'class="undone-badge"' not in text
        assert 'chip-undone' not in text
        # No "(undone)" / "(undo)" suffix from the old i18n key.
        assert '(undone)' not in text
        assert '(undo)' not in text
        # The fixture's undone team-2 add_point was paired with an
        # explicit undo (see ``_seed_realistic_audit``). Set 1's
        # team-2 score should never reach 3 in the timeline running
        # tally — the running-score chip on team-2's last surviving
        # record should be ``(5–2)`` or earlier, not ``(5–3)``.
        assert '(5–3)' not in text

    def test_footer_carries_permalink_and_generated_at(self, client, rich_match):
        """Phase 3 enriches the report footer with the canonical
        ``/match/{id}/report`` permalink and a "Generated at" line so
        a shared print/PDF stays self-describing.
        """
        response = client.get(f"/match/{rich_match}/report")
        assert 'class="footer-permalink"' in response.text
        assert f'/match/{rich_match}/report' in response.text
        assert 'class="footer-line"' in response.text
        # English locale is the default; the permalink + generated
        # labels both render as standalone <strong> headings on
        # their own line.
        assert 'Permalink' in response.text
        assert 'Generated at' in response.text

    def test_timeline_emits_typed_chips_per_action(self, client, rich_match):
        """Phase 3 styles each timeline ``<li>`` with a per-action chip
        modifier (``chip-point-t1``, ``chip-set``, …) plus a glyph
        cell. The legend at the bottom of the timeline should also
        be present so the colour palette is decodable at a glance.
        """
        response = client.get(f"/match/{rich_match}/report")
        # Both team chips appear (rich fixture has add_point for both).
        assert 'class="timeline-li chip-point-t1"' in response.text
        assert 'class="timeline-li chip-point-t2"' in response.text
        # Glyph cell rendered for each row.
        assert 'class="chip-glyph chip-glyph-point-t1"' in response.text
        assert 'class="chip-glyph chip-glyph-point-t2"' in response.text
        # Mini legend renders once per timeline.
        assert 'class="timeline-legend"' in response.text
        assert 'class="timeline-legend-item"' in response.text

    def test_no_undone_artefacts_in_rendered_html(self, client, rich_match):
        """Defensive: confirm the report ships none of the legacy
        undo affordances. A future regression that re-introduces
        strikethrough rows (``.undone`` modifier) or the
        ``↶ Undone`` badge should fail this case loudly.
        """
        response = client.get(f"/match/{rich_match}/report")
        assert 'undone-badge' not in response.text
        assert 'chip-undone' not in response.text
        assert 'chip-glyph-undone' not in response.text
        assert 'legendUndone' not in response.text

    def test_set_byset_table_no_longer_has_timeouts_row(
        self, client, rich_match,
    ):
        """The redundant per-set timeouts row was removed: the
        score cells already show the timeout count in parentheses
        (``25 (1)``), so a dedicated row was just a second pass at
        the same data. Timeouts now render as marker glyphs on the
        per-set score-evolution chart instead.
        """
        response = client.get(f"/match/{rich_match}/report")
        # The old row label must be gone.
        assert "Timeouts (T1/T2)" not in response.text
        # And so must the ``T1/T2`` cell shape it produced.
        import re
        assert not re.search(r'<td>\d+/\d+</td>', response.text)

    def test_orphan_undo_records_are_dropped(self):
        """Unified-undo logs only carry the trailing undo record (the
        forward was popped by ``action_log.pop_last_forward``). The
        report must not surface those orphan rows — they reference an
        action that no longer exists in the timeline.
        """
        from app.match_report import _collapse_undos
        audit = [
            {"ts": 1.0, "action": "add_point",
             "params": {"team": 1, "undo": False},
             "result": {"current_set": 1,
                        "team_1": {"score": 1}, "team_2": {"score": 0}}},
            # Orphan undo: no matching forward survived in the log.
            {"ts": 2.0, "action": "add_point",
             "params": {"team": 2, "undo": True},
             "result": {"current_set": 1,
                        "team_1": {"score": 1}, "team_2": {"score": 0}}},
        ]
        out = _collapse_undos(audit)
        # The legitimate forward survives, the orphan undo is dropped.
        assert len(out) == 1
        assert out[0]["params"]["team"] == 1
        assert not (out[0].get("params") or {}).get("undo")

    def test_set_durations_row_shows_seconds(self, client, rich_match):
        response = client.get(f"/match/{rich_match}/report")
        # Set 1 last surviving record is the offset-210 team-2 point
        # (the offset-240 forward + its offset-260 undo are both
        # dropped by the up-front ``_collapse_undos`` pass, so the
        # set-1 duration spans 0..210). Set 2 still spans 600..1500.
        # The exact text comes from ``_fmt_seconds``.
        assert "3m 30s" in response.text
        assert "15m 00s" in response.text
        # The row label is i18n-driven.
        assert "Set durations" in response.text


class TestMatchReportComebacks:
    """The Highlights block surfaces two comeback flavours.

    * *Set-winning comeback*: only when the erased deficit was 5 pts
      or more. Smaller "comebacks" by the eventual winner are noise
      (a 2-point swing inside a tight set is nothing remarkable).
    * *Partial comeback*: the largest deficit a team trimmed but
      ultimately couldn't close, threshold > 3 pts.

    When team 1 and team 2 share the same maximum the card swaps to
    a "tied between both teams" detail rather than picking a winner.
    """

    def _seed(self, oid: str, sets: list[list[tuple[int, int]]]) -> None:
        """Write a deterministic JSONL audit for a sequence of sets.

        Each set is a list of ``(team_1_score, team_2_score)`` running
        scores after every ``add_point`` action; the team that scored
        is inferred from the diff vs. the previous record.
        """
        from app.api import action_log as _al
        records: list[dict] = []
        ts = 1700000000.0
        for set_idx, scores in enumerate(sets, start=1):
            prev = (0, 0)
            for s1, s2 in scores:
                team = 1 if s1 > prev[0] else 2
                records.append({
                    "ts": ts,
                    "action": "add_point",
                    "params": {"team": team, "undo": False},
                    "result": {
                        "current_set": set_idx,
                        "score_set": set_idx,
                        "team_1": {"score": s1},
                        "team_2": {"score": s2},
                    },
                })
                ts += 30.0
                prev = (s1, s2)
        path = _al._path(_sk(oid))
        assert path is not None
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")

    def _archive(self, oid: str, *, winning_team: int = 1) -> str:
        match_id = match_archive.archive_match(
            oid=oid,
            final_state={
                "team_1": {"sets": 1 if winning_team == 1 else 0},
                "team_2": {"sets": 1 if winning_team == 2 else 0},
            },
            customization={"Team 1 Name": "Alpha", "Team 2 Name": "Bravo"},
            winning_team=winning_team,
            sets_limit=3,
        )
        assert match_id is not None
        return match_id

    def test_set_win_comeback_below_5_is_suppressed(self, client):
        # Team 1 trailed 0-3 then won 25-23 — comeback of 3 pts, below
        # the 5-point threshold. The card must not appear.
        scores = [(0, 1), (0, 2), (0, 3), (1, 3), (24, 3), (25, 23)]
        oid = "cb-small"
        self._seed(oid, [scores])
        match_id = self._archive(oid, winning_team=1)
        body = client.get(f"/match/{match_id}/report").text
        assert "set-winning comeback" not in body.lower()

    @staticmethod
    def _highlights_block(body: str) -> str:
        start = body.index('<div class="highlights">')
        depth, cursor = 1, start + len('<div class="highlights">')
        while depth and cursor < len(body):
            no = body.find('<div', cursor)
            nc = body.find('</div>', cursor)
            if nc == -1:
                break
            if no != -1 and no < nc:
                depth += 1
                cursor = no + 4
            else:
                depth -= 1
                cursor = nc + 6
        return body[start:cursor]

    @classmethod
    def _highlight_card(cls, body: str, label: str) -> str:
        """Return the single ``<div class="highlight">`` that owns ``label``."""
        block = cls._highlights_block(body)
        marker = f'<div class="label">{label}</div>'
        label_at = block.index(marker)
        # Walk backwards to find the enclosing ``<div class="highlight">``.
        card_start = block.rfind('<div class="highlight">', 0, label_at)
        # Each card is exactly one nested ``<div>`` deep so the closing
        # ``</div>`` of the card itself is the *fourth* one after start.
        cursor = card_start + len('<div class="highlight">')
        depth = 1
        while depth and cursor < len(block):
            no = block.find('<div', cursor)
            nc = block.find('</div>', cursor)
            if nc == -1:
                break
            if no != -1 and no < nc:
                depth += 1
                cursor = no + 4
            else:
                depth -= 1
                cursor = nc + 6
        return block[card_start:cursor]

    def test_set_win_comeback_at_5_renders(self, client):
        # Team 2 trailed 0-5 in set 1 and won 25-23 — comeback of 5.
        scores = [(i, 0) for i in range(1, 6)] + [(5, 23), (5, 25)]
        oid = "cb-five"
        self._seed(oid, [scores])
        match_id = self._archive(oid, winning_team=2)
        body = client.get(f"/match/{match_id}/report").text
        assert "Biggest set-winning comeback" in body
        assert "down 5" in body
        # Only the eventual set winner can credit a set-winning comeback.
        assert "Bravo" in self._highlights_block(body)

    def test_set_win_comeback_tie_renders_message(self, client):
        # Set 1: team 1 wins from 0-5 down. Set 2: team 2 wins from
        # 0-5 down. Both maxima are 5 → tie message.
        s1 = [(0, i) for i in range(1, 6)] + [(23, 5), (25, 5)]
        s2 = [(i, 0) for i in range(1, 6)] + [(5, 23), (5, 25)]
        oid = "cb-tie"
        self._seed(oid, [s1, s2])
        match_id = self._archive(oid, winning_team=1)
        body = client.get(f"/match/{match_id}/report").text
        # On a tie, the card collapses to the magnitude alone ("5 pts")
        # and the per-team detail is replaced by the tie text.
        card = self._highlight_card(body, "Biggest set-winning comeback")
        assert "5 pts" in card
        assert "Tied between both teams" in card
        assert "Alpha" not in card and "Bravo" not in card

    def test_partial_comeback_below_4_is_suppressed(self, client):
        # Team 2 trailed 0-3 then crawled back to 1-3 (recovery of 1
        # pt), still lost 25-22. The 1-point recovery is below the
        # >3 threshold; partial card must not appear.
        scores = [(1, 0), (2, 0), (3, 0), (3, 1), (25, 22)]
        oid = "pc-small"
        self._seed(oid, [scores])
        match_id = self._archive(oid, winning_team=1)
        body = client.get(f"/match/{match_id}/report").text
        assert "partial comeback" not in body.lower()

    def test_partial_comeback_above_3_renders_for_loser(self, client):
        # Team 2 trailed 0-10, fought back to 4-10 (recovery of 4),
        # then lost 25-14. 4 > 3 → partial card surfaces and must
        # credit the *losing* team (Bravo).
        scores = [(i, 0) for i in range(1, 11)]
        scores += [(10, j) for j in range(1, 5)]
        scores += [(25, 14)]
        oid = "pc-loser"
        self._seed(oid, [scores])
        match_id = self._archive(oid, winning_team=1)
        body = client.get(f"/match/{match_id}/report").text
        card = self._highlight_card(body, "Biggest partial comeback")
        assert "made up 4 pts" in card
        # The card credits the *losing* team for the partial recovery.
        assert "Bravo" in card
        assert "Alpha" not in card

    def test_partial_comeback_recovery_caps_at_the_tie(self, client):
        # Team 2 trailed 0-10 (peak deficit 10), crawled all the way
        # back to a brief 10-12 lead, then bled out as team 1 closed
        # 25-12. The "partial comeback" must be 10 (the tying
        # recovery), not 12 — the +2 lead segment is a separate
        # story and must not extend the "points recovered while
        # trailing" counter.
        scores = [(i, 0) for i in range(1, 11)]       # 1-0..10-0
        scores += [(10, j) for j in range(1, 13)]     # 10-1..10-12
        scores += [(k, 12) for k in range(11, 26)]    # 11-12..25-12
        oid = "pc-cap-at-tie"
        self._seed(oid, [scores])
        match_id = self._archive(oid, winning_team=1)
        body = client.get(f"/match/{match_id}/report").text
        card = self._highlight_card(body, "Biggest partial comeback")
        # 10 = peak deficit; the +2 lead segment is NOT credited.
        assert "made up 10 pts" in card
        assert "made up 12 pts" not in card
        # Credited to the losing team (Bravo).
        assert "Bravo" in card

    def test_loser_who_only_led_then_collapsed_is_not_a_comeback(self, client):
        # Team 2 leads 5-0 from the opening and then bleeds the lead
        # without ever trailing → final 5-25. Team 2 was *never*
        # behind, so neither a set-winning nor a partial comeback
        # should be credited (the bug was that the diff between
        # ``loser_deficit = -5`` and the initial ``loser_min_after_peak
        # = 0`` was being read as a 5-point recovery).
        scores = [(0, i) for i in range(1, 6)]
        scores += [(j, 5) for j in range(1, 26)]
        oid = "pc-led-then-lost"
        self._seed(oid, [scores])
        match_id = self._archive(oid, winning_team=1)
        body = client.get(f"/match/{match_id}/report").text
        assert "partial comeback" not in body.lower()
        # The set-winning side gets a 5-pt comeback for team 1
        # (trailed 0-5 then won) — that one *is* legit and stays.
        assert "Biggest set-winning comeback" in body

    def test_partial_comeback_tie_renders_message(self, client):
        # Set 1 won by team 1: team 2 trims a 0-10 deficit to 4-10
        # (partial recovery of 4) before losing 25-14.
        # Set 2 won by team 2: team 1 trims a 0-10 deficit to 4-10
        # (partial recovery of 4) before losing 14-25.
        # Maxima are tied at 4 → expect the tie message.
        s1 = [(i, 0) for i in range(1, 11)]
        s1 += [(10, j) for j in range(1, 5)]
        s1 += [(25, 14)]
        s2 = [(0, i) for i in range(1, 11)]
        s2 += [(j, 10) for j in range(1, 5)]
        s2 += [(14, 25)]
        oid = "pc-tie"
        self._seed(oid, [s1, s2])
        match_id = self._archive(oid, winning_team=1)
        body = client.get(f"/match/{match_id}/report").text
        card = self._highlight_card(body, "Biggest partial comeback")
        assert "4 pts" in card
        assert "Tied between both teams" in card
        assert "Alpha" not in card and "Bravo" not in card


class TestMatchReportPregameTrim:
    """Reset / pregame records must not anchor the report timeline."""

    def _seed_audit(self, oid: str, records: list[dict]) -> None:
        from app.api import action_log as _al
        path = _al._path(_sk(oid))
        assert path is not None
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")

    def test_relative_timestamps_anchor_at_first_point_not_reset(self, client):
        # Reset 5 min before the first point; the first point must
        # render as ``+0:00`` (anchoring restarts here) and the
        # second point 60 s later as ``+1:00``. The reset line
        # itself is trimmed and the audit_count drops to 2.
        # In real flow ``GameSession.match_started_at`` is ``None``
        # at reset time and is auto-armed by the first ``add_point``
        # — so the archived ``started_at`` reflects the first point,
        # not the reset. Mirror that here.
        base_ts = time.time() - 1000
        first_pt_ts = base_ts + 300
        oid = "trim-1"
        self._seed_audit(oid, [
            {"ts": base_ts, "action": "reset", "params": {},
             "result": {"current_set": 1, "team_1": {"score": 0},
                        "team_2": {"score": 0}}},
            {"ts": first_pt_ts, "action": "add_point",
             "params": {"team": 1, "undo": False},
             "result": {"current_set": 1, "team_1": {"score": 1},
                        "team_2": {"score": 0}}},
            {"ts": first_pt_ts + 60, "action": "add_point",
             "params": {"team": 2, "undo": False},
             "result": {"current_set": 1, "team_1": {"score": 1},
                        "team_2": {"score": 1}}},
        ])
        match_id = match_archive.archive_match(
            oid=oid, final_state={
                "team_1": {"sets": 0, "scores": {"set_1": 1}},
                "team_2": {"sets": 0, "scores": {"set_1": 1}},
            },
            customization={"Team 1 Name": "A", "Team 2 Name": "B"},
            started_at=first_pt_ts, sets_limit=3,
        )
        response = client.get(f"/match/{match_id}/report")
        # First scored point is the anchor → +0:00; second point 60s
        # later → +1:00.
        assert "+0:00" in response.text
        assert "+1:00" in response.text
        # Reset entry is gone from the rendered timeline. Phase 3 added
        # a "Reset" key in the legend, so the bare ``>Reset<`` substring
        # is no longer load-bearing — pin to the chip-bearing ``<li>``
        # the timeline emits for an actual reset action instead.
        assert 'class="timeline-li chip-reset' not in response.text
        # ``Audit entries`` reflects the trimmed view (3 raw → 2 shown).
        assert ">2</td>" in response.text

    def test_explicit_start_match_anchors_before_first_point(self, client):
        # Operator hits Start match 5 min before the first rally
        # (``GameSession.match_started_at`` set explicitly). The
        # archive then carries ``started_at = T_explicit`` and the
        # report's anchor follows: first point now reads ``+5:00``,
        # not ``+0:00``.
        explicit_start = time.time() - 1000
        first_pt_ts = explicit_start + 300
        oid = "trim-explicit"
        self._seed_audit(oid, [
            {"ts": explicit_start, "action": "start_match",
             "params": {},
             "result": {"current_set": 1, "team_1": {"score": 0},
                        "team_2": {"score": 0}}},
            {"ts": first_pt_ts, "action": "add_point",
             "params": {"team": 1, "undo": False},
             "result": {"current_set": 1, "team_1": {"score": 1},
                        "team_2": {"score": 0}}},
        ])
        match_id = match_archive.archive_match(
            oid=oid,
            final_state={"team_1": {"scores": {"set_1": 1}},
                         "team_2": {"scores": {"set_1": 0}}},
            customization={"Team 1 Name": "A", "Team 2 Name": "B"},
            started_at=explicit_start, sets_limit=3,
        )
        response = client.get(f"/match/{match_id}/report")
        # 300 s gap between the explicit anchor and the first rally.
        assert "+5:00" in response.text

    def test_started_at_uses_first_scoring_ts(self, client):
        # Real-flow archive: started_at == first-point ts (auto-arm).
        # The "Started" row in the match-facts table should render
        # that timestamp.
        import datetime as _dt
        base_ts = time.time() - 1000
        first_pt_ts = base_ts + 300
        oid = "trim-started"
        self._seed_audit(oid, [
            {"ts": base_ts, "action": "reset", "params": {},
             "result": {"current_set": 1, "team_1": {"score": 0},
                        "team_2": {"score": 0}}},
            {"ts": first_pt_ts, "action": "add_point",
             "params": {"team": 1, "undo": False},
             "result": {"current_set": 1, "team_1": {"score": 1},
                        "team_2": {"score": 0}}},
        ])
        match_id = match_archive.archive_match(
            oid=oid,
            final_state={"team_1": {"scores": {"set_1": 1}},
                         "team_2": {"scores": {"set_1": 0}}},
            customization={"Team 1 Name": "A", "Team 2 Name": "B"},
            started_at=first_pt_ts, sets_limit=3,
        )
        response = client.get(f"/match/{match_id}/report")
        first_pt_label = _dt.datetime.fromtimestamp(
            first_pt_ts, _dt.UTC,
        ).strftime("%Y-%m-%d %H:%M UTC")
        reset_label = _dt.datetime.fromtimestamp(
            base_ts, _dt.UTC,
        ).strftime("%Y-%m-%d %H:%M UTC")
        assert first_pt_label in response.text
        if first_pt_label != reset_label:
            assert response.text.count(reset_label) == 0

    def test_timeline_omits_pregame_actions(self, client):
        # Reset + a stray timeout before any point should both be
        # trimmed; only the first scored point survives in the timeline.
        oid = "trim-stray"
        base = time.time() - 3000
        self._seed_audit(oid, [
            {"ts": base, "action": "reset", "params": {},
             "result": {"current_set": 1, "team_1": {"score": 0},
                        "team_2": {"score": 0}}},
            {"ts": base + 30, "action": "add_timeout",
             "params": {"team": 1, "undo": False},
             "result": {"current_set": 1, "team_1": {"score": 0,
                                                     "timeouts": 1},
                        "team_2": {"score": 0, "timeouts": 0}}},
            {"ts": base + 90, "action": "add_point",
             "params": {"team": 1, "undo": False},
             "result": {"current_set": 1, "team_1": {"score": 1},
                        "team_2": {"score": 0}}},
        ])
        match_id = match_archive.archive_match(
            oid=oid,
            final_state={"team_1": {"scores": {"set_1": 1}},
                         "team_2": {"scores": {"set_1": 0}}},
            customization={"Team 1 Name": "A", "Team 2 Name": "B"},
            started_at=base + 90, sets_limit=3,
        )
        response = client.get(f"/match/{match_id}/report")
        # Pregame timeout/reset shouldn't appear in the timeline. The
        # action-label form ``Timeout — Team N`` is the timeline-row
        # marker; the set-by-set table now shows timeouts inline as
        # ``score (N)`` rather than a separate row, so this match
        # match-substring isn't load-bearing against any other label.
        assert "Timeout — Team" not in response.text
        # Phase 3 added a "Reset" entry to the timeline legend, so we
        # can no longer ban the bare ``>Reset<`` substring globally.
        # Pin the assertion to the chip-bearing ``<li>`` rendered for
        # an actual reset action — that's the only place a pregame
        # reset would surface in the timeline.
        assert 'class="timeline-li chip-reset' not in response.text
        assert "Point — Team 1" in response.text


class TestMatchReportTimeoutsInline:
    """Timeouts are now annotated inline in the set-by-set table.

    Set scores render as ``25 (N)`` when the team called N>0 timeouts
    in that set; bare ``25`` when none. The previous "Timeouts (final
    set)" summary row has been removed in favour of this per-set view.
    """

    def _seed_audit(self, oid: str, records: list[dict]) -> None:
        from app.api import action_log as _al
        path = _al._path(_sk(oid))
        assert path is not None
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")

    def test_set_score_cell_appends_timeout_count(self, client):
        # Set 1: team_1 took 2 timeouts; set 2: team_2 took 1; set 3:
        # neither team. The cell text must read "25 (2)" / "25 (1)" /
        # "25" (no parens) accordingly. Records must be appended in
        # chronological order — ``_trim_pregame`` indexes by FILE
        # position (not timestamp) when searching for the first
        # scoring action, so out-of-order seeding would silently drop
        # the timeouts that came after the seeded first add_point but
        # earlier in the file.
        base_ts = time.time() - 3000
        oid = "to-inline-1"
        records = []

        def _add(action, params, result, off):
            records.append({"ts": base_ts + off, "action": action,
                            "params": params, "result": result})

        # Set 1 — team_1 wins, with 2 timeouts. Two scoring records
        # so the per-set chart can actually draw a polyline (single
        # points return "" and the timeout glyphs would have nowhere
        # to live).
        _add("add_point", {"team": 1, "undo": False},
             {"current_set": 1,
              "team_1": {"score": 1}, "team_2": {"score": 0}}, off=5)
        _add("add_timeout", {"team": 1, "undo": False},
             {"current_set": 1,
              "team_1": {"score": 5, "timeouts": 1},
              "team_2": {"score": 3, "timeouts": 0}}, off=10)
        _add("add_point", {"team": 1, "undo": False},
             {"current_set": 1,
              "team_1": {"score": 25}, "team_2": {"score": 23}}, off=100)
        _add("add_timeout", {"team": 1, "undo": False},
             {"current_set": 1,
              "team_1": {"score": 18, "timeouts": 2},
              "team_2": {"score": 16, "timeouts": 0}}, off=120)
        # Set 2 — team_2 takes 1 timeout. Two scoring records again
        # so the chart renders + the timeout glyph has a home.
        _add("add_point", {"team": 2, "undo": False},
             {"current_set": 2,
              "team_1": {"score": 0}, "team_2": {"score": 1}}, off=200)
        _add("add_timeout", {"team": 2, "undo": False},
             {"current_set": 2,
              "team_1": {"score": 12, "timeouts": 0},
              "team_2": {"score": 14, "timeouts": 1}}, off=300)
        _add("add_point", {"team": 2, "undo": False},
             {"current_set": 2,
              "team_1": {"score": 21}, "team_2": {"score": 25}}, off=400)
        # Set 3 — no timeouts on either side. Two scoring records to
        # confirm absence of timeout markers on a clean chart.
        _add("add_point", {"team": 1, "undo": False},
             {"current_set": 3,
              "team_1": {"score": 1}, "team_2": {"score": 0}}, off=600)
        _add("add_point", {"team": 1, "undo": False},
             {"current_set": 3,
              "team_1": {"score": 25}, "team_2": {"score": 19}}, off=700)
        self._seed_audit(oid, records)

        match_id = match_archive.archive_match(
            oid=oid,
            final_state={
                "current_set": 3,
                "team_1": {"sets": 2, "timeouts": 0,
                           "scores": {"set_1": 25, "set_2": 21,
                                      "set_3": 25}},
                "team_2": {"sets": 1, "timeouts": 0,
                           "scores": {"set_1": 23, "set_2": 25,
                                      "set_3": 19}},
            },
            customization={"Team 1 Name": "A", "Team 2 Name": "B"},
            winning_team=1, sets_limit=3, started_at=base_ts + 5,
        )
        response = client.get(f"/match/{match_id}/report")

        # team_1 set 1: 25 with 2 timeouts → "25 (2)"
        assert "25 (2)" in response.text
        # team_2 set 2: 25 with 1 timeout → "25 (1)"
        assert "25 (1)" in response.text
        # No-timeout cells stay bare. Use the absence of "(0)" parens
        # as a coarse check that we never spell out a zero count.
        assert "(0)" not in response.text
        # The legacy "Timeouts (final set)" row must be gone.
        assert "Timeouts (final set)" not in response.text

        # The redundant "Timeouts (T1/T2)" row was retired — the score
        # cells already carry the count in parentheses, and timeouts
        # now render as marker glyphs on the per-set chart.
        assert "Timeouts (T1/T2)" not in response.text
        import re
        assert not re.search(r'<td>\d+/\d+</td>', response.text)

        # The chart picks up the timeouts as dashed-guide markers,
        # one per ``add_timeout``. team-1 took 2 in set 1, team-2
        # took 1 in set 2 — three glyphs total.
        glyphs = re.findall(
            r'class="set-chart-timeout-glyph"\s+data-team="(\d+)"',
            response.text,
        )
        assert glyphs.count("1") == 2
        assert glyphs.count("2") == 1

    def test_undone_timeout_does_not_count(self, client):
        """An ``add_timeout`` that was undone must not contribute to
        either the inline ``25 (N)`` suffix or the new
        "Timeouts (T1/T2)" summary row. Regression:
        ``_timeouts_per_set`` only skipped records where
        ``params.undo`` is truthy, but the *forward* of an undone
        pair still slipped through. The report pipeline now feeds
        every reducer a ``_collapse_undos`` slice so the forward
        and the undo both disappear.
        """
        base_ts = time.time() - 1000
        oid = "to-undone-1"
        records = []

        def _add(action, params, result, off):
            records.append({"ts": base_ts + off, "action": action,
                            "params": params, "result": result})

        # Set 1: two scoring records ground the set so the per-set
        # chart actually renders, then T1 takes a timeout and
        # immediately undoes it. Expected: no inline ``(1)`` suffix
        # on the score cells AND no chart timeout glyph.
        _add("add_point", {"team": 1, "undo": False},
             {"current_set": 1,
              "team_1": {"score": 1}, "team_2": {"score": 0}}, off=5)
        _add("add_timeout", {"team": 1, "undo": False},
             {"current_set": 1,
              "team_1": {"score": 1, "timeouts": 1},
              "team_2": {"score": 0, "timeouts": 0}}, off=10)
        _add("add_timeout", {"team": 1, "undo": True},
             {"current_set": 1,
              "team_1": {"score": 1, "timeouts": 0},
              "team_2": {"score": 0, "timeouts": 0}}, off=15)
        _add("add_point", {"team": 1, "undo": False},
             {"current_set": 1,
              "team_1": {"score": 25}, "team_2": {"score": 23}}, off=100)
        # Set 2 grounding scores so the table has at least two sets
        # and the chart can draw a polyline there too.
        _add("add_point", {"team": 2, "undo": False},
             {"current_set": 2,
              "team_1": {"score": 1}, "team_2": {"score": 1}}, off=200)
        _add("add_point", {"team": 2, "undo": False},
             {"current_set": 2,
              "team_1": {"score": 23}, "team_2": {"score": 25}}, off=300)
        self._seed_audit(oid, records)

        match_id = match_archive.archive_match(
            oid=oid,
            final_state={
                "current_set": 2,
                "team_1": {"sets": 1, "timeouts": 0,
                           "scores": {"set_1": 25, "set_2": 0}},
                "team_2": {"sets": 0, "timeouts": 0,
                           "scores": {"set_1": 23, "set_2": 1}},
            },
            customization={"Team 1 Name": "A", "Team 2 Name": "B"},
            winning_team=1, sets_limit=3, started_at=base_ts + 5,
        )
        response = client.get(f"/match/{match_id}/report")

        # Inline suffix must stay bare for the score cells.
        assert "(1)" not in response.text
        # No ``N/M`` tuple anywhere in the table — every set row is "—".
        import re
        assert not re.search(r'<td>\d+/\d+</td>', response.text)
        # Chart must not surface a dashed guide for the undone timeout.
        assert 'class="set-chart-timeout"' not in response.text
        assert 'class="set-chart-timeout-glyph"' not in response.text


class TestMatchReportEmptySets:
    """A best-of-3 ending 2-0 must not render a Set 3 column / chart."""

    def test_unplayed_trailing_sets_are_omitted(self, client):
        # Final state: set 1 won 25-22, set 2 won 25-19, set 3 untouched
        # (operator never reached the deciding set).
        match_id = match_archive.archive_match(
            oid="empty-3",
            final_state={
                "team_1": {"sets": 2, "scores": {"set_1": 25, "set_2": 25,
                                                 "set_3": 0}},
                "team_2": {"sets": 0, "scores": {"set_1": 22, "set_2": 19,
                                                 "set_3": 0}},
            },
            customization={"Team 1 Name": "A", "Team 2 Name": "B"},
            winning_team=1, sets_limit=3,
        )
        response = client.get(f"/match/{match_id}/report")
        # Set headers and chart card titles use "Set N"; with set 3
        # omitted, the substring shouldn't appear at all in the page.
        assert "Set 1" in response.text
        assert "Set 2" in response.text
        assert "Set 3" not in response.text
        # The "Best of 3" rule still appears — that's the match
        # configuration, not the played-set count.
        assert "Best of 3" in response.text

    def test_full_three_sets_still_render_when_played(self, client):
        # Best-of-3 going to a deciding set — every column / card
        # must still render (this is the regression guard for the
        # opt-in trimming).
        match_id = match_archive.archive_match(
            oid="empty-full",
            final_state={
                "team_1": {"sets": 2, "scores": {"set_1": 25, "set_2": 22,
                                                 "set_3": 15}},
                "team_2": {"sets": 1, "scores": {"set_1": 22, "set_2": 25,
                                                 "set_3": 13}},
            },
            customization={"Team 1 Name": "A", "Team 2 Name": "B"},
            winning_team=1, sets_limit=3,
        )
        response = client.get(f"/match/{match_id}/report")
        for label in ("Set 1", "Set 2", "Set 3"):
            assert label in response.text

    def test_empty_match_collapses_to_single_set_frame(self, client):
        # ``_played_set_count`` returns 1 (not ``sets_limit``) when the
        # archive has no scoring data — otherwise a fresh-archive
        # snapshot would paint 3 or 5 empty columns.
        match_id = match_archive.archive_match(
            oid="empty-fresh",
            final_state={
                "team_1": {"sets": 0, "scores": {"set_1": 0, "set_2": 0,
                                                 "set_3": 0}},
                "team_2": {"sets": 0, "scores": {"set_1": 0, "set_2": 0,
                                                 "set_3": 0}},
            },
            customization={"Team 1 Name": "A", "Team 2 Name": "B"},
            winning_team=None, sets_limit=3,
        )
        response = client.get(f"/match/{match_id}/report")
        assert "Set 1" in response.text
        assert "Set 2" not in response.text
        assert "Set 3" not in response.text

    def test_played_set_count_clamps_to_sets_limit(self, client):
        # Defensive: a snapshot reporting set-4 scores in a best-of-3
        # match (data-corruption / mode-change scenario) shouldn't
        # render past the formal limit either, otherwise we'd paint a
        # column the rules don't allow.
        match_id = match_archive.archive_match(
            oid="empty-overrun",
            final_state={
                "team_1": {"sets": 0, "scores": {"set_1": 25, "set_2": 0,
                                                 "set_3": 0, "set_4": 25}},
                "team_2": {"sets": 0, "scores": {"set_1": 22, "set_2": 0,
                                                 "set_3": 0, "set_4": 19}},
            },
            customization={"Team 1 Name": "A", "Team 2 Name": "B"},
            winning_team=1, sets_limit=3,
        )
        response = client.get(f"/match/{match_id}/report")
        assert "Set 4" not in response.text

    def test_team_name_with_ampersand_is_not_double_escaped(self, client):
        # Regression: ``A & B`` was being html.escape'd twice — once
        # into ``match_label`` and again into ``title`` — so it ended
        # up reading ``A &amp;amp; B`` in the browser tab. The label
        # is now raw end-to-end and only escaped at insertion sites.
        match_id = match_archive.archive_match(
            oid="amp-1",
            final_state={"team_1": {"sets": 0}, "team_2": {"sets": 0}},
            customization={"Team 1 Name": "A & B", "Team 2 Name": "C"},
            winning_team=1,
            sets_limit=3,
        )
        response = client.get(f"/match/{match_id}/report")
        assert response.status_code == 200
        assert "&amp;amp;" not in response.text
        # The expected single-pass escape: literal ``&`` becomes
        # ``&amp;`` exactly once in both ``<title>`` and ``<h1>``.
        assert response.text.count("A &amp; B") >= 2

    def test_team_name_html_escaped(self, client):
        action_log.append("rep-xss", "add_point",
                          {"team": 1, "undo": False}, {})
        match_id = match_archive.archive_match(
            oid="rep-xss",
            final_state={"team_1": {"sets": 0}, "team_2": {"sets": 0}},
            customization={"Team 1 Name": "<script>alert(1)</script>"},
            winning_team=1,
            sets_limit=3,
        )
        response = client.get(f"/match/{match_id}/report")
        assert response.status_code == 200
        assert "<script>alert(1)</script>" not in response.text
        assert "&lt;script&gt;" in response.text

    def test_color_injection_falls_back_to_default(self, client):
        """Malformed customization colours must not flow into CSS verbatim.

        ``_HEX_COLOR_RE`` only accepts ``#RGB`` / ``#RRGGBB``. Anything
        else (right length, wrong characters; CSS-breaking content) is
        replaced by the team's default.
        """
        match_id = match_archive.archive_match(
            oid="rep-css",
            final_state={"team_1": {"sets": 0}, "team_2": {"sets": 0}},
            customization={
                "Color 1": "#a;}b",          # length 5 — rejected
                "Color 2": "#zzz",           # length 4, non-hex — rejected
                "Text Color 1": "red; }",    # not a hex string — rejected
            },
            winning_team=1,
            sets_limit=3,
        )
        response = client.get(f"/match/{match_id}/report")
        assert response.status_code == 200
        # Defaults (team 1 background) appear in the CSS.
        assert "#0047AB" in response.text
        assert "#E21836" in response.text
        # Malformed values do not.
        assert "#a;}b" not in response.text
        assert "#zzz" not in response.text
        assert "red; }" not in response.text


class TestMatchReportAuth:
    """Cookie-owner / signed-URL / public access for /match/{id}/report."""

    def _seed(self, oid="auth-1"):
        match_id = match_archive.archive_match(
            oid=oid,
            final_state={"team_1": {"sets": 3}, "team_2": {"sets": 0}},
            customization={"Team 1 Name": "Home", "Team 2 Name": "Away"},
            winning_team=1, sets_limit=3,
        )
        assert match_id is not None
        return match_id

    def test_public_mode_allows_anyone(self, monkeypatch):
        monkeypatch.setenv("MATCH_REPORT_PUBLIC", "true")
        app = FastAPI()
        app.include_router(match_report_router)
        c = TestClient(app)
        match_id = self._seed("pub")
        assert c.get(f"/match/{match_id}/report").status_code == 200

    def test_non_public_without_cookie_is_401(self, monkeypatch):
        monkeypatch.delenv("MATCH_REPORT_PUBLIC", raising=False)
        app = FastAPI()
        app.include_router(match_report_router)
        c = TestClient(app)
        match_id = self._seed("priv")
        assert c.get(f"/match/{match_id}/report").status_code == 401

    def test_signed_url_allows_access(self, monkeypatch):
        monkeypatch.delenv("MATCH_REPORT_PUBLIC", raising=False)
        monkeypatch.setenv("SESSION_SECRET", "test-signing-secret")
        from app.match_report_signing import make_signed_query
        app = FastAPI()
        app.include_router(match_report_router)
        c = TestClient(app)
        match_id = self._seed("signed")
        sq = make_signed_query(match_id)
        assert c.get(f"/match/{match_id}/report?exp={sq['exp']}&sig={sq['sig']}").status_code == 200
        # A tampered signature is rejected.
        assert c.get(f"/match/{match_id}/report?exp={sq['exp']}&sig=deadbeef").status_code == 401

    def test_owner_cookie_allows_access(self, monkeypatch):
        monkeypatch.delenv("MATCH_REPORT_PUBLIC", raising=False)
        from app.bootstrap import create_app
        c = TestClient(create_app())
        # The autouse _reporter_user fixture created "reporter"; sign in so the
        # cookie identifies the report's owner.
        assert c.post(
            "/api/v1/auth/login",
            json={"username": "reporter", "password": "password123"},
        ).status_code == 200
        match_id = self._seed("owned")
        assert c.get(f"/match/{match_id}/report").status_code == 200

    def test_non_owner_cookie_is_401(self, db_session, monkeypatch):
        monkeypatch.delenv("MATCH_REPORT_PUBLIC", raising=False)
        from app.auth import service
        from app.bootstrap import create_app
        service.create_user(db_session, username="intruder", password="password123")
        db_session.commit()
        c = TestClient(create_app())
        c.post("/api/v1/auth/login", json={"username": "intruder", "password": "password123"})
        match_id = self._seed("owned-by-reporter")
        assert c.get(f"/match/{match_id}/report").status_code == 401


class TestPointTypeBreakdown:
    """Per-point classification breakdown in stats + highlights render."""

    @staticmethod
    def _point(team, score_pair, *, point_type=None, error_type=None, ts=1.0):
        params = {"team": team, "undo": False}
        if point_type:
            params["point_type"] = point_type
        if error_type:
            params["error_type"] = error_type
        return {
            "ts": ts,
            "action": "add_point",
            "params": params,
            "result": {
                "current_set": 1,
                "team_1": {"score": score_pair[0]},
                "team_2": {"score": score_pair[1]},
                "serve": "A" if team == 1 else "B",
            },
        }

    def test_compute_stats_tallies_types_and_errors(self):
        from app.match_report import _compute_stats

        audit = [
            self._point(1, (1, 0), point_type="ace", ts=1.0),
            self._point(1, (2, 0), point_type="kill", ts=2.0),
            self._point(1, (3, 0), point_type="opp_error",
                        error_type="serve_error", ts=3.0),
            self._point(2, (3, 1), point_type="block", ts=4.0),
        ]
        stats = _compute_stats(audit)
        assert stats["point_types"][1] == {
            "ace": 1, "kill": 1, "block": 0, "opp_error": 1,
        }
        assert stats["point_types"][2]["block"] == 1
        assert stats["error_types"][1]["serve_error"] == 1
        # Per-team totals back the composition percentages.
        assert stats["total_points_by_team"] == {1: 3, 2: 1}

    def test_composition_card_shows_percentages(self):
        from app.match_report import _compute_stats, _render_highlights

        # Team 1 wins 4 points: 1 ace + 3 kills → ace = 25%, kill = 75%.
        audit = [
            self._point(1, (1, 0), point_type="ace", ts=1.0),
            self._point(1, (2, 0), point_type="kill", ts=2.0),
            self._point(1, (3, 0), point_type="kill", ts=3.0),
            self._point(1, (4, 0), point_type="kill", ts=4.0),
        ]
        stats = _compute_stats(audit)
        html = _render_highlights(
            stats, "en", team1_name="Alpha", team2_name="Beta",
        )
        assert "Aces: 1 (25%)" in html
        assert "Kills: 3 (75%)" in html

    def test_own_errors_card_attributes_faults_to_faulting_team(self):
        from app.match_report import _compute_stats, _render_highlights

        # Team 1 wins 3 points off team 2's faults (2 serve, 1 net);
        # team 2 wins 1 clean point. So team 2's "own errors" = 3.
        audit = [
            self._point(1, (1, 0), point_type="opp_error",
                        error_type="serve_error", ts=1.0),
            self._point(1, (2, 0), point_type="opp_error",
                        error_type="serve_error", ts=2.0),
            self._point(1, (3, 0), point_type="opp_error",
                        error_type="net_fault", ts=3.0),
            self._point(2, (3, 1), point_type="kill", ts=4.0),
        ]
        stats = _compute_stats(audit)
        html = _render_highlights(
            stats, "en", team1_name="Alpha", team2_name="Beta",
        )
        # The own-errors card is attributed to Beta (team 2), who gave
        # away the 3 points, with the cause breakdown and the share of
        # Alpha's points (3 of Alpha's 3 = 100%).
        assert "Beta · Own errors" in html
        assert "100% of opponent points" in html
        assert "Serve errors: 2" in html and "Net faults: 1" in html
        # Alpha committed no faults → no own-errors card for Alpha.
        assert "Alpha · Own errors" not in html

    def test_render_highlights_includes_localized_breakdown(self):
        from app.match_report import _compute_stats, _render_highlights

        audit = [
            self._point(1, (1, 0), point_type="ace", ts=1.0),
            self._point(1, (2, 0), point_type="opp_error",
                        error_type="net_fault", ts=2.0),
        ]
        stats = _compute_stats(audit)
        html_en = _render_highlights(
            stats, "en", team1_name="Alpha", team2_name="Beta",
        )
        assert "Points won" in html_en
        assert "Aces: 1" in html_en
        assert "Net faults: 1" in html_en  # error cause detail
        # Locale labels resolve (Spanish "Puntos ganados").
        html_es = _render_highlights(
            stats, "es", team1_name="Alpha", team2_name="Beta",
        )
        assert "Puntos ganados" in html_es

    def test_untyped_match_renders_no_breakdown_card(self):
        from app.match_report import _compute_stats, _render_highlights

        audit = [self._point(1, (1, 0), ts=1.0)]
        stats = _compute_stats(audit)
        html = _render_highlights(
            stats, "en", team1_name="Alpha", team2_name="Beta",
        )
        assert "Points won" not in html


class TestServeReceiveBreakdown:
    """Serve/receive attribution walk + highlight cards.

    The server of rally N is the ``result.serve`` snapshot of record
    N-1 (post-action serve follows the rally winner), seeded for the
    very first rally from the pregame slice.
    """

    # Reuse the realistic record builder — its results already carry
    # the winner-serves-next snapshot.
    _point = staticmethod(TestPointTypeBreakdown._point)

    @staticmethod
    def _serve_change(serve: str, *, ts: float) -> dict:
        return {
            "ts": ts,
            "action": "change_serve",
            "params": {"team": 1 if serve == "A" else 2},
            "result": {
                "current_set": 1,
                "team_1": {"score": 0},
                "team_2": {"score": 0},
                "serve": serve,
            },
        }

    def test_points_attributed_by_previous_records_serve(self):
        from app.match_report_stats import _serve_receive_summary

        # Seeded: team 1 serves rally 1 and wins it (hold), serves
        # rally 2 and loses it (team 2 side-out), then team 2 serves
        # rally 3 and wins it (hold).
        audit = [
            self._point(1, (1, 0), ts=1.0),   # server: seed (1) → won
            self._point(2, (1, 1), ts=2.0),   # server: 1 → lost (side-out)
            self._point(2, (1, 2), ts=3.0),   # server: 2 → won
        ]
        out = _serve_receive_summary(audit, initial_serve=1)
        assert out[1] == {"served": 2, "won": 1}
        assert out[2] == {"served": 1, "won": 1}

    def test_unseeded_first_point_excluded_from_totals(self):
        from app.match_report_stats import _serve_receive_summary

        audit = [
            self._point(1, (1, 0), ts=1.0),   # server unknown → skipped
            self._point(1, (2, 0), ts=2.0),   # server: 1 (from record 1)
        ]
        out = _serve_receive_summary(audit)
        assert out[1] == {"served": 1, "won": 1}
        assert out[2] == {"served": 0, "won": 0}

    def test_initial_serve_seeded_from_pregame_change_serve(self):
        from app.match_report_stats import _initial_serve_from_pregame

        raw = [
            self._serve_change("B", ts=1.0),
            self._point(1, (1, 0), ts=2.0),
        ]
        assert _initial_serve_from_pregame(raw) == 2

    def test_pregame_serve_none_clears_the_seed(self):
        from app.match_report_stats import _initial_serve_from_pregame

        # The reset's ``serve: "None"`` supersedes the earlier
        # assignment — resurrecting it would guess.
        raw = [
            self._serve_change("A", ts=1.0),
            {"ts": 2.0, "action": "reset", "params": {},
             "result": {"current_set": 1, "team_1": {"score": 0},
                        "team_2": {"score": 0}, "serve": "None"}},
            self._point(1, (1, 0), ts=3.0),
        ]
        assert _initial_serve_from_pregame(raw) is None

    def test_no_scoring_action_yields_no_seed(self):
        from app.match_report_stats import _initial_serve_from_pregame

        assert _initial_serve_from_pregame([]) is None
        assert _initial_serve_from_pregame(
            [self._serve_change("A", ts=1.0)],
        ) is None

    def test_undo_records_do_not_move_counters_or_tracker(self):
        from app.match_report_stats import _serve_receive_summary

        # Uncollapsed log (live-style): the undo record must neither
        # count as a rally nor update the serve tracker.
        undo = self._point(2, (1, 0), ts=3.0)
        undo["params"]["undo"] = True
        audit = [
            self._point(1, (1, 0), ts=1.0),
            self._point(2, (1, 1), ts=2.0),
            undo,
            self._point(1, (2, 1), ts=4.0),  # server: 2 (not the undo's B)
        ]
        out = _serve_receive_summary(audit, initial_serve=1)
        assert out[1] == {"served": 2, "won": 1}
        assert out[2] == {"served": 1, "won": 0}

    def test_legacy_log_without_serve_renders_no_cards(self):
        from app.match_report import _compute_stats, _render_highlights

        audit = []
        for i, team in enumerate((1, 2, 1), start=1):
            record = self._point(team, (i, 0), ts=float(i))
            del record["result"]["serve"]
            audit.append(record)
        stats = _compute_stats(audit)
        assert stats["serve_receive"][1] == {"served": 0, "won": 0}
        assert stats["serve_receive"][2] == {"served": 0, "won": 0}
        html = _render_highlights(
            stats, "en", team1_name="Alpha", team2_name="Beta",
        )
        assert "Points on serve / receive" not in html

    def test_cards_render_with_names_and_percentages(self):
        from app.match_report import _compute_stats, _render_highlights

        # Team 1 serves and wins both rallies; team 2 never wins a
        # serve. Alpha: 2 of 2 on serve (100%); Beta: 0 side-outs of
        # 2 receives (0%).
        audit = [
            self._point(1, (1, 0), ts=1.0),
            self._point(1, (2, 0), ts=2.0),
        ]
        stats = _compute_stats(audit, initial_serve=1)
        html = _render_highlights(
            stats, "en", team1_name="Alpha", team2_name="Beta",
        )
        assert "Alpha · Points on serve / receive" in html
        assert "On serve: 2 of 2 (100%)" in html
        assert "Beta · Points on serve / receive" in html
        assert "On receive: 0 of 2 (0%)" in html

    def test_report_route_renders_serve_cards_from_pregame_seed(self, client):
        # End-to-end through the archive: pregame serve assignment →
        # trimmed report still attributes the first rally.
        seeder = TestMatchReportPregameTrim()
        base_ts = time.time() - 1000
        oid = "serve-route-1"
        seeder._seed_audit(oid, [
            self._serve_change("A", ts=base_ts),
            self._point(1, (1, 0), ts=base_ts + 10),
            self._point(2, (1, 1), ts=base_ts + 40),
        ])
        match_id = match_archive.archive_match(
            oid=oid,
            final_state={"team_1": {"scores": {"set_1": 1}},
                         "team_2": {"scores": {"set_1": 1}}},
            customization={"Team 1 Name": "Alpha", "Team 2 Name": "Beta"},
            started_at=base_ts + 10, sets_limit=3,
        )
        response = client.get(f"/match/{match_id}/report")
        assert response.status_code == 200
        # Both rallies were served by team 1 (seed, then hold): Alpha
        # 1 of 2 on serve, Beta 1 side-out of 2 receives.
        assert "Alpha · Points on serve / receive" in response.text
        assert "On serve: 1 of 2 (50%)" in response.text
        assert "On receive: 1 of 2 (50%)" in response.text

    def test_localized_heading(self):
        from app.match_report import _compute_stats, _render_highlights

        audit = [self._point(1, (1, 0), ts=1.0)]
        stats = _compute_stats(audit, initial_serve=1)
        html = _render_highlights(
            stats, "es", team1_name="Alpha", team2_name="Beta",
        )
        assert "Puntos al saque / en recepción" in html


class TestBiggestLeadHighlight:
    """Largest score gap either team opened, as a highlight card.

    Threshold mirrors the set-win comeback floor (>= 5): a lead is
    the other team's deficit, so the two cards should agree on what
    counts as noteworthy.
    """

    # Reuse the running-score seeder / card extractor from the
    # comeback suite — the data shape is identical.
    _seed = TestMatchReportComebacks._seed
    _archive = TestMatchReportComebacks._archive
    _highlight_card = TestMatchReportComebacks._highlight_card

    def test_lead_below_5_is_suppressed(self, client):
        # Team 1 never leads by more than 4.
        scores = [(1, 0), (2, 0), (3, 0), (4, 0), (4, 1)]
        oid = "lead-small"
        self._seed(oid, [scores])
        match_id = self._archive(oid, winning_team=1)
        body = client.get(f"/match/{match_id}/report").text
        assert "Biggest lead" not in body

    def test_lead_at_5_renders_with_team_and_set(self, client):
        # Team 1 opens a 5-0 gap and the margin never grows past 5.
        scores = [(1, 0), (2, 0), (3, 0), (4, 0), (5, 0), (5, 1), (6, 1)]
        oid = "lead-five"
        self._seed(oid, [scores])
        match_id = self._archive(oid, winning_team=1)
        body = client.get(f"/match/{match_id}/report").text
        card = self._highlight_card(body, "Biggest lead")
        assert "led by 5 in set 1" in card
        assert "Alpha" in card

    def test_lead_tie_renders_tie_message(self, client):
        # Team 1 leads 5-0; team 2 storms back to lead 5-10 — both
        # peak at +5, so the card must not pick a side.
        scores = [(1, 0), (2, 0), (3, 0), (4, 0), (5, 0)] + [
            (5, n) for n in range(1, 11)
        ]
        oid = "lead-tie"
        self._seed(oid, [scores])
        match_id = self._archive(oid, winning_team=2)
        body = client.get(f"/match/{match_id}/report").text
        card = self._highlight_card(body, "Biggest lead")
        assert "Tied between both teams" in card

    def test_lead_recorded_when_no_comeback_qualifies(self):
        from app.match_report import _compute_stats

        # A one-sided 25-10 set: no comeback story at all, but a
        # 15-point lead worth surfacing.
        audit = []
        s1 = s2 = 0
        ts = 1.0
        while s1 < 25 or s2 < 10:
            team = 1 if (s1 < 25 and (s2 >= 10 or (s1 + s2) % 3 != 2)) else 2
            s1, s2 = (s1 + 1, s2) if team == 1 else (s1, s2 + 1)
            audit.append({
                "ts": ts, "action": "add_point",
                "params": {"team": team, "undo": False},
                "result": {"current_set": 1, "score_set": 1,
                           "team_1": {"score": s1}, "team_2": {"score": s2}},
            })
            ts += 30.0
        stats = _compute_stats(audit)
        assert stats["biggest_lead"][1] == {"lead": 15, "set": 1}
        assert stats["biggest_lead"][2] == {"lead": 0, "set": None}
        assert stats["set_win_comeback"][1]["deficit"] == 0


class TestMatchReportWinner:
    """Winner badge on the hero panel + bold set-winner scores."""

    def test_winner_badge_on_winning_panel_only(self, client, archived_match):
        body = client.get(f"/match/{archived_match}/report").text
        assert body.count('class="winner-badge"') == 1
        # The badge sits inside the team-1 panel: after the t1 div
        # opens and before the "vs" separator div.
        badge_at = body.index('class="winner-badge"')
        assert body.index('<div class="team t1">') < badge_at
        assert badge_at < body.index('<div class="vs">')
        assert "Winner" in body

    def test_no_badge_when_winning_team_missing(self, client):
        match_id = match_archive.archive_match(
            oid="win-none",
            final_state={"team_1": {"scores": {"set_1": 10}},
                         "team_2": {"scores": {"set_1": 8}}},
            customization={"Team 1 Name": "A", "Team 2 Name": "B"},
            sets_limit=3,
        )
        body = client.get(f"/match/{match_id}/report").text
        assert 'class="winner-badge"' not in body

    def test_winning_set_scores_are_bold(self, client, archived_match):
        body = client.get(f"/match/{archived_match}/report").text
        # Sets 1/3/4 went to team 1 (25-18, 25-22, 25-21); set 2 to
        # team 2 (18-25). Both rows carry set-won cells; the losing
        # scores stay in plain <td>s.
        assert body.count('<td class="set-won">25') == 4
        assert '<td class="set-won">18' not in body
        assert '<td class="set-won">21' not in body
        assert "<td>18</td>" in body

    def test_tied_set_scores_not_bold(self, client):
        match_id = match_archive.archive_match(
            oid="win-tie",
            final_state={"team_1": {"scores": {"set_1": 12}},
                         "team_2": {"scores": {"set_1": 12}}},
            customization={"Team 1 Name": "A", "Team 2 Name": "B"},
            winning_team=1,
            sets_limit=3,
        )
        body = client.get(f"/match/{match_id}/report").text
        assert 'class="set-won"' not in body

    def test_badge_is_localized(self, client, archived_match):
        body = client.get(f"/match/{archived_match}/report?lang=es").text
        assert "Ganador" in body
        assert ">Winner<" not in body


class TestMatchReportDarkMode:
    """The report follows ``prefers-color-scheme: dark`` on screen only.

    Chart colours are resolved twice server-side (light + dark surface)
    and plumbed through CSS vars; the inline SVG presentation
    attributes keep the light values as the no-CSS fallback.
    """

    def _archive(self, oid: str, customization: dict) -> str:
        _seed_realistic_audit(oid, time.time() - 3600)
        match_id = match_archive.archive_match(
            oid=oid,
            final_state={
                "team_1": {"sets": 0, "scores": {"set_1": 25, "set_2": 22}},
                "team_2": {"sets": 2, "scores": {"set_1": 23, "set_2": 25}},
            },
            customization=customization,
            winning_team=2, sets_limit=3,
        )
        assert match_id is not None
        return match_id

    def test_dark_media_block_is_screen_scoped(self, client):
        match_id = self._archive("dark-1", {
            "Team 1 Name": "Alpha", "Team 2 Name": "Bravo",
        })
        body = client.get(f"/match/{match_id}/report").text
        assert "@media screen and (prefers-color-scheme: dark)" in body
        assert "color-scheme: light dark" in body

    def test_chart_vars_emitted_for_both_schemes(self, client):
        # A white team 1 brand: the light pass darkens it (or falls
        # back), the dark pass keeps it white — the two var values
        # must differ so each scheme stays readable.
        match_id = self._archive("dark-2", {
            "Team 1 Name": "Alpha", "Team 2 Name": "Bravo",
            "Team 1 Color": "#ffffff", "Team 1 Text Color": "#f5f5f5",
            "Team 2 Color": "#E21836", "Team 2 Text Color": "#FFFFFF",
        })
        body = client.get(f"/match/{match_id}/report").text
        values = re.findall(r"--t1-chart:\s*(#[0-9a-fA-F]{3,6})", body)
        assert len(values) == 2
        light_value, dark_value = values
        assert light_value.lower() != dark_value.lower()
        assert dark_value.lower() == "#ffffff"

    def test_svg_elements_carry_theme_classes_and_inline_attrs(self, client):
        match_id = self._archive("dark-3", {
            "Team 1 Name": "Alpha", "Team 2 Name": "Bravo",
            "Color 1": "#0047AB", "Color 2": "#E21836",
        })
        body = client.get(f"/match/{match_id}/report").text
        assert '<polyline class="t1-stroke"' in body
        assert '<polyline class="t2-stroke"' in body
        assert '<circle class="t1-fill"' in body
        assert 'class="chart-grid"' in body
        assert 'class="chart-axis"' in body
        # The no-CSS fallback: inline attributes still present.
        assert 'stroke="#0047AB"' in body
        # Legend swatches are var-driven now.
        assert '<span class="swatch swatch-t1"></span>' in body
        assert '<span class="swatch swatch-t2"></span>' in body
