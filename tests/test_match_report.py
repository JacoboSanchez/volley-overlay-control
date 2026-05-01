"""Tests for the print-friendly match report at /match/{match_id}/report."""
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import action_log, match_archive
from app.match_report import match_report_router

pytestmark = pytest.mark.usefixtures("clean_sessions")


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
