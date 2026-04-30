"""Tests for the print-friendly match report at /match/{match_id}/report."""
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import action_log, match_archive
from app.match_report import match_report_router

pytestmark = pytest.mark.usefixtures("clean_sessions")


@pytest.fixture
def client():
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
