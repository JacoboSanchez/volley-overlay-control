"""Tests for the print-friendly match report at /match/{match_id}/report."""
import json
import os
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import action_log, match_archive
from app.match_report import match_report_router

pytestmark = pytest.mark.usefixtures("clean_sessions")


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

    path = _al._path(oid)
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
def gated_client(monkeypatch):
    """Client where access requires OVERLAY_MANAGER_PASSWORD."""
    monkeypatch.delenv("MATCH_REPORT_PUBLIC", raising=False)
    monkeypatch.setenv("OVERLAY_MANAGER_PASSWORD", "s3cret")
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

    def test_renders_final_score(self, client, archived_match):
        response = client.get(f"/match/{archived_match}/report")
        # Match winner team 1 with 3-1 sets.
        assert ">3<" in response.text
        assert ">1<" in response.text
        assert "Match winner" in response.text

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
        path = _al._path(oid)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")

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
        # Biggest comeback in this audit is 6 (team 2 trailed 0-6).
        assert "down 6" in response.text or ">6<" in response.text

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
        # Axis text labels — y-axis ticks include 0 and the max
        # (set 1 caps at 5, set 2 at 25). Spot-check 0.
        assert ">0</text>" in response.text
        # X-axis labels are 1 / N where N is the number of plotted
        # rallies; the rich-fixture set 1 has 9 scoring records
        # (set_score not used) → endpoint label is 9.
        assert ">1</text>" in response.text

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

    def test_longest_rally_card_renders(self, client, rich_match):
        response = client.get(f"/match/{rich_match}/report")
        # The rich fixture's set 2 has a 5m 0s gap (last point at
        # offset 1500, second-to-last at 900 — but those aren't
        # consecutive in the audit; the actual sorted gap depends
        # on the seed). Any non-zero rally duration should produce
        # the card with the i18n label.
        assert "Longest rally" in response.text

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

    def test_undo_collapses_to_strikethrough(self, client, rich_match):
        response = client.get(f"/match/{rich_match}/report")
        # The original team-2 forward record at 5-3 is paired with the
        # explicit undo right after it; the collapsed timeline marks
        # the original with class="undone" (CSS draws strike-through).
        assert 'class="undone"' in response.text
        # The standalone undo entry must NOT be rendered as its own row
        # — pairing collapses both into one editorial line.
        assert response.text.count('(undone)') <= 1
        assert response.text.count("(undo)") == 0

    def test_set_durations_row_shows_seconds(self, client, rich_match):
        response = client.get(f"/match/{rich_match}/report")
        # Set 1 last forward record sits at offset 240 (the offset-260
        # entry is the explicit undo, which we skip). Set 2 spans
        # 600..1500. The exact text comes from ``_fmt_seconds``.
        assert "4m 00s" in response.text
        assert "15m 00s" in response.text
        # The row label is i18n-driven.
        assert "Set durations" in response.text


class TestMatchReportPregameTrim:
    """Reset / pregame records must not anchor the report timeline."""

    def _seed_audit(self, oid: str, records: list[dict]) -> None:
        from app.api import action_log as _al
        path = _al._path(oid)
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
        # Reset entry is gone from the rendered timeline.
        assert ">Reset<" not in response.text
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
            first_pt_ts, _dt.timezone.utc,
        ).strftime("%Y-%m-%d %H:%M UTC")
        reset_label = _dt.datetime.fromtimestamp(
            base_ts, _dt.timezone.utc,
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
        # Pregame timeout/reset shouldn't appear in the timeline. We
        # check the action-label form (``Timeout — Team N``) so we
        # don't false-match the ``Timeouts (final set)`` row label.
        assert "Timeout — Team" not in response.text
        assert ">Reset<" not in response.text
        assert "Point — Team 1" in response.text


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
    """Coverage for the auth gate added under MATCH_REPORT_PUBLIC=false."""

    def _seed_match(self, oid: str = "auth-1") -> str:
        match_id = match_archive.archive_match(
            oid=oid,
            final_state={"team_1": {"sets": 3}, "team_2": {"sets": 0}},
            customization={"Team 1 Name": "Home", "Team 2 Name": "Away"},
            winning_team=1,
            sets_limit=3,
        )
        assert match_id is not None
        return match_id

    def test_503_when_no_env_var_configured(self, monkeypatch):
        monkeypatch.delenv("MATCH_REPORT_PUBLIC", raising=False)
        monkeypatch.delenv("OVERLAY_MANAGER_PASSWORD", raising=False)
        app = FastAPI()
        app.include_router(match_report_router)
        c = TestClient(app)
        match_id = self._seed_match("auth-503")
        response = c.get(f"/match/{match_id}/report")
        assert response.status_code == 503

    def test_401_without_credentials(self, gated_client):
        match_id = self._seed_match("auth-401")
        response = gated_client.get(f"/match/{match_id}/report")
        assert response.status_code == 401

    def test_403_with_wrong_credentials(self, gated_client):
        match_id = self._seed_match("auth-403-bearer")
        bearer = gated_client.get(
            f"/match/{match_id}/report",
            headers={"Authorization": "Bearer wrong"},
        )
        assert bearer.status_code == 403
        query = gated_client.get(f"/match/{match_id}/report?token=wrong")
        assert query.status_code == 403

    def test_200_with_bearer_header(self, gated_client):
        match_id = self._seed_match("auth-bearer-ok")
        response = gated_client.get(
            f"/match/{match_id}/report",
            headers={"Authorization": "Bearer s3cret"},
        )
        assert response.status_code == 200

    def test_200_with_query_token(self, gated_client):
        match_id = self._seed_match("auth-query-ok")
        response = gated_client.get(
            f"/match/{match_id}/report?token=s3cret",
        )
        assert response.status_code == 200

    def test_public_mode_overrides_password(self, monkeypatch):
        monkeypatch.setenv("MATCH_REPORT_PUBLIC", "true")
        monkeypatch.setenv("OVERLAY_MANAGER_PASSWORD", "s3cret")
        app = FastAPI()
        app.include_router(match_report_router)
        c = TestClient(app)
        match_id = self._seed_match("auth-public")
        response = c.get(f"/match/{match_id}/report")
        assert response.status_code == 200


class TestMatchesIndex:
    """Coverage for the new /matches/index.html browseable list."""

    def _archive(self, oid: str, winner: int) -> str:
        match_id = match_archive.archive_match(
            oid=oid,
            final_state={
                "team_1": {"sets": 3 if winner == 1 else 1},
                "team_2": {"sets": 1 if winner == 1 else 3},
            },
            customization={"Team 1 Name": "Home", "Team 2 Name": "Away"},
            winning_team=winner,
            sets_limit=5,
        )
        assert match_id is not None
        return match_id

    def test_index_lists_archived_matches(self, client):
        a = self._archive("idx-1", winner=1)
        b = self._archive("idx-1", winner=2)
        response = client.get("/matches/index.html?oid=idx-1")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        # Both match_ids should appear as links to their reports.
        assert f"/match/{a}/report" in response.text
        assert f"/match/{b}/report" in response.text
        # Header shows the OID and a count of 2.
        assert "idx-1" in response.text
        assert "2 matches" in response.text

    def test_index_filters_by_oid(self, client):
        own = self._archive("idx-mine", winner=1)
        self._archive("idx-other", winner=2)  # different OID
        response = client.get("/matches/index.html?oid=idx-mine")
        assert f"/match/{own}/report" in response.text
        # The "other" OID's match must NOT leak in.
        assert "idx-other" not in response.text

    def test_index_empty_state(self, client):
        response = client.get("/matches/index.html?oid=idx-empty")
        assert response.status_code == 200
        assert "0 match" in response.text
        assert "No matches archived yet" in response.text

    def test_index_requires_oid(self, client):
        response = client.get("/matches/index.html")
        assert response.status_code == 422

    def test_index_503_when_no_auth_configured(self, monkeypatch):
        monkeypatch.delenv("MATCH_REPORT_PUBLIC", raising=False)
        monkeypatch.delenv("OVERLAY_MANAGER_PASSWORD", raising=False)
        app = FastAPI()
        app.include_router(match_report_router)
        c = TestClient(app)
        response = c.get("/matches/index.html?oid=anything")
        assert response.status_code == 503

    def test_index_401_without_token_when_gated(self, gated_client):
        response = gated_client.get("/matches/index.html?oid=anything")
        assert response.status_code == 401

    def test_index_token_propagates_to_report_links(self, gated_client):
        """When the operator opens the gated index with ``?token=…``,
        the per-match report links should carry the same token so a
        click-through doesn't re-prompt for credentials."""
        match_id = self._archive("idx-token", winner=1)
        response = gated_client.get(
            "/matches/index.html?oid=idx-token&token=s3cret",
        )
        assert response.status_code == 200
        assert f"/match/{match_id}/report?token=s3cret" in response.text

    def test_index_oid_is_html_escaped(self, client):
        # OID containing HTML metacharacters must not break the page.
        # ``match_archive`` only accepts a strict regex so this is
        # belt-and-braces — but the index template must still escape.
        response = client.get("/matches/index.html?oid=%3Cscript%3E")
        # OID failed regex → no archives → empty page rendered cleanly.
        assert response.status_code == 200
        assert "<script>" not in response.text

    def test_index_renders_delete_affordances(self, client):
        match_id = self._archive("idx-del", winner=1)
        response = client.get("/matches/index.html?oid=idx-del")
        # Toolbar + per-row delete + select-all checkbox + script wired up.
        assert 'id="delete-selected"' in response.text
        assert 'id="select-all"' in response.text
        assert 'class="row-delete"' in response.text
        assert f'data-match-id="{match_id}"' in response.text
        assert "/matches/' + encodeURIComponent" in response.text


class TestDeleteArchivedMatch:
    """Coverage for DELETE /matches/{match_id}."""

    def _archive(self, oid: str = "del-1") -> str:
        match_id = match_archive.archive_match(
            oid=oid, final_state={}, winning_team=1,
        )
        assert match_id is not None
        return match_id

    def test_delete_succeeds_with_token(self, gated_client):
        match_id = self._archive()
        response = gated_client.delete(f"/matches/{match_id}?token=s3cret")
        assert response.status_code == 204
        assert match_archive.load_match(match_id) is None

    def test_delete_accepts_bearer_header(self, gated_client):
        match_id = self._archive()
        response = gated_client.delete(
            f"/matches/{match_id}",
            headers={"Authorization": "Bearer s3cret"},
        )
        assert response.status_code == 204

    def test_delete_404_for_unknown_match(self, gated_client):
        bogus = "match_" + "0" * 20 + "_20260101T000000_000000Z"
        response = gated_client.delete(f"/matches/{bogus}?token=s3cret")
        assert response.status_code == 404

    def test_delete_401_without_token(self, gated_client):
        match_id = self._archive()
        response = gated_client.delete(f"/matches/{match_id}")
        assert response.status_code == 401
        # Match must NOT have been deleted.
        assert match_archive.load_match(match_id) is not None

    def test_delete_403_with_wrong_token(self, gated_client):
        match_id = self._archive()
        response = gated_client.delete(f"/matches/{match_id}?token=wrong")
        assert response.status_code == 403
        assert match_archive.load_match(match_id) is not None

    def test_delete_503_when_no_admin_password(self, monkeypatch):
        # Public mode is on, but no admin password — destructive calls
        # must still be denied.
        monkeypatch.setenv("MATCH_REPORT_PUBLIC", "true")
        monkeypatch.delenv("OVERLAY_MANAGER_PASSWORD", raising=False)
        app = FastAPI()
        app.include_router(match_report_router)
        c = TestClient(app)
        match_id = self._archive()
        response = c.delete(f"/matches/{match_id}")
        assert response.status_code == 503
        assert match_archive.load_match(match_id) is not None

    def test_delete_rejects_public_mode_without_token(self, monkeypatch):
        # MATCH_REPORT_PUBLIC=true grants read access, but DELETE must
        # still require the admin token.
        monkeypatch.setenv("MATCH_REPORT_PUBLIC", "true")
        monkeypatch.setenv("OVERLAY_MANAGER_PASSWORD", "s3cret")
        app = FastAPI()
        app.include_router(match_report_router)
        c = TestClient(app)
        match_id = self._archive()
        response = c.delete(f"/matches/{match_id}")
        assert response.status_code == 401
        assert match_archive.load_match(match_id) is not None

    def test_delete_validates_match_id_shape(self, gated_client):
        # Path-traversal attempts get rejected at the helper level, so
        # the route should respond 404 (not 500, not partial filesystem
        # exception). FastAPI may also bounce malformed ids before they
        # reach the handler — accept either.
        response = gated_client.delete("/matches/not-a-match-id?token=s3cret")
        assert response.status_code in (404, 422)

    # ── MATCH_REPORT_PUBLIC_DELETE opt-in ──────────────────────────────

    def _public_delete_client(self, monkeypatch):
        monkeypatch.setenv("MATCH_REPORT_PUBLIC_DELETE", "true")
        # Read access still gated — we're isolating the delete flag.
        monkeypatch.delenv("MATCH_REPORT_PUBLIC", raising=False)
        monkeypatch.setenv("OVERLAY_MANAGER_PASSWORD", "s3cret")
        app = FastAPI()
        app.include_router(match_report_router)
        return TestClient(app)

    def test_delete_public_mode_succeeds_without_token(self, monkeypatch):
        c = self._public_delete_client(monkeypatch)
        match_id = self._archive()
        response = c.delete(f"/matches/{match_id}")
        assert response.status_code == 204
        assert match_archive.load_match(match_id) is None

    def test_delete_public_mode_works_without_admin_password(self, monkeypatch):
        # The whole point of the flag is to avoid the "I have to set
        # OVERLAY_MANAGER_PASSWORD just to enable Delete" trap. Without
        # the password set, the delete must still go through.
        monkeypatch.setenv("MATCH_REPORT_PUBLIC_DELETE", "true")
        monkeypatch.delenv("MATCH_REPORT_PUBLIC", raising=False)
        monkeypatch.delenv("OVERLAY_MANAGER_PASSWORD", raising=False)
        app = FastAPI()
        app.include_router(match_report_router)
        c = TestClient(app)
        match_id = self._archive()
        response = c.delete(f"/matches/{match_id}")
        assert response.status_code == 204
        assert match_archive.load_match(match_id) is None

    def test_delete_public_mode_still_404s_for_unknown(self, monkeypatch):
        c = self._public_delete_client(monkeypatch)
        bogus = "match_" + "0" * 20 + "_20260101T000000_000000Z"
        response = c.delete(f"/matches/{bogus}")
        assert response.status_code == 404

    def test_public_read_alone_does_not_unlock_delete(self, monkeypatch):
        # MATCH_REPORT_PUBLIC=true (read) without
        # MATCH_REPORT_PUBLIC_DELETE must NOT enable destructive calls
        # — this independence is the safety property of the two flags.
        monkeypatch.setenv("MATCH_REPORT_PUBLIC", "true")
        monkeypatch.delenv("MATCH_REPORT_PUBLIC_DELETE", raising=False)
        monkeypatch.setenv("OVERLAY_MANAGER_PASSWORD", "s3cret")
        app = FastAPI()
        app.include_router(match_report_router)
        c = TestClient(app)
        match_id = self._archive()
        response = c.delete(f"/matches/{match_id}")
        assert response.status_code == 401
        assert match_archive.load_match(match_id) is not None
