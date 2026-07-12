"""Tests for the runtime app-config plumbing (APP_TITLE env var).

Covers both the small ``GET /api/v1/app-config`` endpoint and the helper
that rewrites ``<title>`` inside the served SPA ``index.html``.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import api_router
from app.app_config import (
    DEFAULT_APP_TITLE,
    DEFAULT_STALE_SET_THRESHOLD_MINUTES,
    get_app_title,
    get_stale_set_threshold_minutes,
)
from app.bootstrap import (
    _BOARD_TOKEN_RE,
    _board_manifest,
    _inject_title_into_html,
    _render_index_html,
    _render_manifest,
)


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(api_router)
    return TestClient(app)


def test_app_config_returns_default_title(client, monkeypatch):
    monkeypatch.delenv("APP_TITLE", raising=False)
    monkeypatch.delenv("STALE_SET_THRESHOLD_MINUTES", raising=False)
    res = client.get("/api/v1/app-config")
    assert res.status_code == 200
    assert res.json() == {
        "title": DEFAULT_APP_TITLE,
        "stale_set_threshold_minutes": DEFAULT_STALE_SET_THRESHOLD_MINUTES,
    }


def test_app_config_returns_env_title(client, monkeypatch):
    monkeypatch.setenv("APP_TITLE", "My Liga Volley")
    monkeypatch.delenv("STALE_SET_THRESHOLD_MINUTES", raising=False)
    res = client.get("/api/v1/app-config")
    assert res.status_code == 200
    assert res.json() == {
        "title": "My Liga Volley",
        "stale_set_threshold_minutes": DEFAULT_STALE_SET_THRESHOLD_MINUTES,
    }


def test_app_config_falls_back_when_env_is_blank(monkeypatch):
    monkeypatch.setenv("APP_TITLE", "   ")
    assert get_app_title() == DEFAULT_APP_TITLE


def test_stale_set_threshold_reads_env(client, monkeypatch):
    monkeypatch.setenv("STALE_SET_THRESHOLD_MINUTES", "15")
    res = client.get("/api/v1/app-config")
    assert res.status_code == 200
    assert res.json()["stale_set_threshold_minutes"] == 15


def test_stale_set_threshold_disabled_by_zero(client, monkeypatch):
    monkeypatch.setenv("STALE_SET_THRESHOLD_MINUTES", "0")
    res = client.get("/api/v1/app-config")
    assert res.status_code == 200
    assert res.json()["stale_set_threshold_minutes"] == 0


def test_stale_set_threshold_clamps_negative_to_zero(monkeypatch):
    monkeypatch.setenv("STALE_SET_THRESHOLD_MINUTES", "-30")
    assert get_stale_set_threshold_minutes() == 0


def test_stale_set_threshold_falls_back_on_garbage(monkeypatch):
    monkeypatch.setenv("STALE_SET_THRESHOLD_MINUTES", "not-a-number")
    assert get_stale_set_threshold_minutes() == DEFAULT_STALE_SET_THRESHOLD_MINUTES


def test_inject_title_replaces_tag():
    html = "<html><head><title>Old</title></head><body/></html>"
    result = _inject_title_into_html(html, "New Title")
    assert "<title>New Title</title>" in result
    assert "Old" not in result


def test_inject_title_escapes_html_special_chars():
    html = "<html><head><title>x</title></head></html>"
    result = _inject_title_into_html(html, "A & <B>")
    assert "<title>A &amp; &lt;B&gt;</title>" in result


def test_inject_title_only_replaces_first_match():
    html = "<title>a</title>...<title>b</title>"
    result = _inject_title_into_html(html, "Z")
    assert result == "<title>Z</title>...<title>b</title>"


def test_inject_title_handles_attributes_on_title_tag():
    html = '<head><title lang="en">Old</title></head>'
    result = _inject_title_into_html(html, "New")
    assert "<title>New</title>" in result
    assert "Old" not in result


def test_render_index_html_caches_disk_reads(tmp_path):
    """Repeat calls with the same (path, mtime, title) read disk only once."""
    index = tmp_path / "index.html"
    index.write_text("<title>Old</title>", encoding="utf-8")
    mtime = index.stat().st_mtime

    _render_index_html.cache_clear()
    first = _render_index_html(str(index), mtime, "Hello")
    info_before = _render_index_html.cache_info()
    # Mutate the file but pass the same mtime so the cache key is unchanged.
    index.write_text("<title>Mutated</title>", encoding="utf-8")
    second = _render_index_html(str(index), mtime, "Hello")
    info_after = _render_index_html.cache_info()

    assert first == second == "<title>Hello</title>"
    assert info_after.hits == info_before.hits + 1


def test_render_manifest_injects_title_into_name_fields(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        '{"name": "Old", "short_name": "Old", "icons": []}',
        encoding="utf-8",
    )
    _render_manifest.cache_clear()
    data = _render_manifest(str(manifest), manifest.stat().st_mtime, "MyApp")
    assert data["name"] == "MyApp"
    assert data["short_name"] == "MyApp"
    assert data["icons"] == []


def test_board_manifest_points_start_url_at_the_board():
    base = {"name": "Volley", "short_name": "Volley", "start_url": "/", "icons": ["x"]}
    out = _board_manifest(base, "Volley", "alex", "liga")
    assert out["start_url"] == "/board?u=alex&oid=liga"
    # Distinct ``id`` so Chrome installs it as its own app, scope covers it.
    assert out["id"] == "/board?u=alex&oid=liga"
    assert out["scope"] == "/"
    assert out["short_name"] == "liga"
    # Boards carry their own icon set, distinct from the base app's.
    assert out["icons"][0]["src"] == "icon-board.svg"
    assert all("icon-board" in icon["src"] for icon in out["icons"])
    # Shared/cached base dict is not mutated.
    assert base["start_url"] == "/"
    assert base["icons"] == ["x"]


def test_board_manifest_owner_variant_targets_oid_only_board():
    # No username → the owner's board link. RequireAuth round-trips through
    # /login (preserving the destination) when the cookie is missing, so the
    # installed launcher still lands on the board.
    base = {"name": "Volley", "short_name": "Volley", "start_url": "/", "icons": ["x"]}
    out = _board_manifest(base, "Volley", None, "liga")
    assert out["start_url"] == "/board?oid=liga"
    assert out["id"] == "/board?oid=liga"
    assert out["scope"] == "/"
    assert out["short_name"] == "liga"
    assert base["start_url"] == "/"


def test_board_manifest_token_regex_rejects_unsafe_values():
    assert _BOARD_TOKEN_RE.match("liga-2024.A_b")
    assert not _BOARD_TOKEN_RE.match("a/b")
    assert not _BOARD_TOKEN_RE.match("a b")
    assert not _BOARD_TOKEN_RE.match("")


def test_manifest_route_serves_per_board_variant(tmp_path, monkeypatch):
    # A minimal built frontend so the manifest route finds a source file.
    import app.bootstrap as bootstrap

    frontend = tmp_path / "dist"
    frontend.mkdir()
    (frontend / "manifest.webmanifest").write_text(
        '{"name": "Volley", "short_name": "Volley", "start_url": "/", "icons": []}',
        encoding="utf-8",
    )
    (frontend / "index.html").write_text("<title>x</title>", encoding="utf-8")
    monkeypatch.setattr(bootstrap, "FRONTEND_DIR", frontend)
    _render_manifest.cache_clear()

    with TestClient(bootstrap.create_app()) as client:
        base = client.get("/manifest.webmanifest").json()
        assert base["start_url"] == "/"

        board = client.get(
            "/manifest.webmanifest", params={"u": "alex", "oid": "liga"}
        ).json()
        assert board["start_url"] == "/board?u=alex&oid=liga"
        assert board["id"] == "/board?u=alex&oid=liga"
        assert board["icons"][0]["src"] == "icon-board.svg"

        # ``?oid=`` alone is the owner-board variant.
        owner = client.get("/manifest.webmanifest", params={"oid": "liga"}).json()
        assert owner["start_url"] == "/board?oid=liga"
        assert owner["id"] == "/board?oid=liga"
        assert owner["icons"][0]["src"] == "icon-board.svg"

        # Unsafe params are ignored — falls back to the app-wide manifest.
        bad = client.get(
            "/manifest.webmanifest", params={"u": "a/b", "oid": "liga"}
        ).json()
        assert bad["start_url"] == "/"
        assert client.get("/manifest.webmanifest", params={"oid": "a/b"}).json()[
            "start_url"
        ] == "/"


def test_manifest_route_adds_signed_in_overlay_shortcuts(tmp_path, monkeypatch, db_session):
    """The signed-in owner's overlays become manifest ``shortcuts`` — the app
    shortcuts Android surfaces on a long-press of the installed icon. Built
    from the ``vsession`` cookie only: an anonymous request gets none, and one
    account's overlays never leak into another's manifest."""
    import app.bootstrap as bootstrap
    from app import overlays_service
    from tests.conftest import login_client, make_user

    frontend = tmp_path / "dist"
    frontend.mkdir()
    (frontend / "manifest.webmanifest").write_text(
        '{"name": "Volley", "short_name": "Volley", "start_url": "/", "icons": []}',
        encoding="utf-8",
    )
    (frontend / "index.html").write_text("<title>x</title>", encoding="utf-8")
    monkeypatch.setattr(bootstrap, "FRONTEND_DIR", frontend)
    _render_manifest.cache_clear()

    with TestClient(bootstrap.create_app()) as client:
        # Anonymous: no personalised shortcuts.
        assert "shortcuts" not in client.get("/manifest.webmanifest").json()

        # Sign in and give the owner two overlays (one described).
        login_client(client, db_session, username="alex")
        overlays_service.create_overlay(
            db_session, client.test_user_id, "liga", description="Liga local"
        )
        overlays_service.create_overlay(db_session, client.test_user_id, "copa")
        db_session.commit()

        res = client.get("/manifest.webmanifest")
        assert "Cookie" in res.headers.get("Vary", "")
        shortcuts = res.json()["shortcuts"]
        # Ordered by oid (list_overlays orders by oid): copa, liga.
        assert [s["url"] for s in shortcuts] == [
            "/board?oid=copa", "/board?oid=liga",
        ]
        assert [s["name"] for s in shortcuts] == ["copa", "liga"]
        by_oid = {s["name"]: s for s in shortcuts}
        assert by_oid["liga"]["description"] == "Liga local"
        assert "description" not in by_oid["copa"]  # absent when unset
        assert shortcuts[0]["icons"][0]["src"] == "icon-board-192x192.png"

        # A per-board manifest variant keeps the owner's shortcuts too.
        board = client.get("/manifest.webmanifest", params={"oid": "liga"}).json()
        assert board["start_url"] == "/board?oid=liga"
        assert [s["url"] for s in board["shortcuts"]] == [
            "/board?oid=copa", "/board?oid=liga",
        ]

        # A second account's overlays must never leak into alex's manifest.
        bob = make_user(db_session, "bob")
        overlays_service.create_overlay(db_session, bob.id, "bobonly")
        db_session.commit()
        urls = [s["url"] for s in client.get("/manifest.webmanifest").json()["shortcuts"]]
        assert "/board?oid=bobonly" not in urls


def test_conf_survives_malformed_numeric_env(monkeypatch):
    """MATCH_GAME_POINTS=abc must degrade to the default with a warning,
    not crash Conf() (and with it every session init)."""
    from app.conf import Conf

    monkeypatch.setenv("MATCH_GAME_POINTS", "abc")
    monkeypatch.setenv("MATCH_SETS", "")
    conf = Conf()
    assert conf.points == 25
    assert conf.sets == 5

    monkeypatch.setenv("MATCH_GAME_POINTS", "21")
    assert Conf().points == 21
