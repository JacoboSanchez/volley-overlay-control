"""HTTP coverage for the hosted icon library (``/api/v1/icons*``).

Service internals are covered in ``test_icons_service.py``; these tests
drive the FastAPI routes end-to-end: multipart uploads, scoping, quota
and size limits surfacing as HTTP errors, and the batch import that
converts teams' external logo URLs (with the download monkeypatched —
``net_guard`` itself is covered in ``test_net_guard.py``).
"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import icons_service
from app.bootstrap import create_app
from app.net_guard import GuardedFetchError
from tests.conftest import login_client


@pytest.fixture(autouse=True)
def _icons_tmp_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(icons_service, "icons_dir", lambda: str(tmp_path / "icons"))
    yield


def _admin(db_session):
    return login_client(TestClient(create_app()), db_session, "root", role="admin")


def _user(db_session, name="alice"):
    return login_client(TestClient(create_app()), db_session, name, role="user")


def png_bytes(width=64, height=64):
    buf = io.BytesIO()
    Image.new("RGBA", (width, height), (0, 0, 255, 255)).save(buf, format="PNG")
    return buf.getvalue()


def upload(client, path, name="Lions", content=None, filename="logo.png"):
    return client.post(
        path,
        data={"name": name},
        files={"file": (filename, content or png_bytes(), "image/png")},
    )


# ---- upload ------------------------------------------------------------------


def test_user_uploads_personal_icon(db_session):
    user = _user(db_session)
    resp = upload(user, "/api/v1/icons/mine")
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["name"] == "Lions"
    assert body["url"].startswith("/media/icons/") and body["url"].endswith(".webp")
    assert body["is_global"] is False
    assert body["width"] == 64

    listing = user.get("/api/v1/icons").json()
    assert [i["name"] for i in listing["mine"]] == ["Lions"]
    assert listing["globals"] == []
    assert listing["quota"]["used"] == 1


def test_admin_uploads_global_icon_visible_to_users(db_session):
    admin = _admin(db_session)
    assert upload(admin, "/api/v1/admin/icons", name="League").status_code == 201
    user = _user(db_session)
    listing = user.get("/api/v1/icons").json()
    assert [i["name"] for i in listing["globals"]] == ["League"]
    assert listing["globals"][0]["is_global"] is True


def test_upload_requires_auth(db_session):
    client = TestClient(create_app())
    assert upload(client, "/api/v1/icons/mine").status_code == 401


def test_admin_upload_requires_admin(db_session):
    user = _user(db_session)
    assert upload(user, "/api/v1/admin/icons").status_code == 403


def test_upload_rejects_svg_with_clear_message(db_session):
    user = _user(db_session)
    svg = b'<svg xmlns="http://www.w3.org/2000/svg"></svg>'
    resp = upload(user, "/api/v1/icons/mine", content=svg, filename="logo.svg")
    assert resp.status_code == 400
    assert "SVG" in resp.json()["detail"]


def test_upload_rejects_oversized_body_with_413(db_session, monkeypatch):
    from app.api.routes import icons as icons_routes

    monkeypatch.setattr(icons_routes, "ICONS_MAX_UPLOAD_BYTES", 1024)
    user = _user(db_session)
    resp = upload(user, "/api/v1/icons/mine", content=b"x" * 20_000)
    assert resp.status_code == 413


def test_upload_duplicate_name_is_400(db_session):
    user = _user(db_session)
    assert upload(user, "/api/v1/icons/mine").status_code == 201
    resp = upload(user, "/api/v1/icons/mine", name="lions")
    assert resp.status_code == 400
    assert "already exists" in resp.json()["detail"]


def test_quota_surfaces_as_400(db_session, monkeypatch):
    monkeypatch.setattr(icons_service, "ICONS_MAX_PER_USER", 1)
    user = _user(db_session)
    assert upload(user, "/api/v1/icons/mine", name="A").status_code == 201
    resp = upload(user, "/api/v1/icons/mine", name="B")
    assert resp.status_code == 400
    assert "quota" in resp.json()["detail"].lower()


# ---- rename / usage / delete ---------------------------------------------------


def test_rename_and_usage_and_delete_clear_teams(db_session):
    user = _user(db_session)
    icon = upload(user, "/api/v1/icons/mine").json()

    # Point a custom team at the hosted icon (the picker flow).
    team = user.post(
        "/api/v1/teams/mine/custom",
        json={"name": "Lions A", "icon": icon["url"]},
    ).json()

    renamed = user.patch(
        f"/api/v1/icons/mine/{icon['id']}", json={"name": "Lions FC"},
    )
    assert renamed.status_code == 200 and renamed.json()["name"] == "Lions FC"
    # Rename never changes the URL (content-addressed).
    assert renamed.json()["url"] == icon["url"]

    usage = user.get(f"/api/v1/icons/mine/{icon['id']}/usage").json()
    assert usage == {"teams": 1}

    deleted = user.delete(f"/api/v1/icons/mine/{icon['id']}").json()
    assert deleted == {"ok": True, "teams_cleared": 1}

    catalog = user.get("/api/v1/my/groups").json()
    all_teams = [t for g in catalog for t in g["teams"] if t["id"] == team["id"]]
    assert all_teams and all_teams[0]["icon"] is None


def test_cross_scope_ids_are_404(db_session):
    admin = _admin(db_session)
    global_icon = upload(admin, "/api/v1/admin/icons", name="League").json()
    user = _user(db_session)
    personal = upload(user, "/api/v1/icons/mine", name="Mine").json()

    # A user cannot touch a global icon via the personal routes...
    assert user.delete(f"/api/v1/icons/mine/{global_icon['id']}").status_code == 404
    assert user.patch(
        f"/api/v1/icons/mine/{global_icon['id']}", json={"name": "X"},
    ).status_code == 404
    # ...and the admin routes only see globals.
    assert admin.delete(f"/api/v1/admin/icons/{personal['id']}").status_code == 404


# ---- batch import --------------------------------------------------------------


def _fake_fetch(monkeypatch, payload=None, error=None):
    calls = []

    def fake(url, *, max_bytes, timeout, max_redirects=3):
        calls.append(url)
        if error is not None:
            raise error
        return payload if payload is not None else png_bytes()

    monkeypatch.setattr(icons_service, "fetch_guarded", fake)
    return calls


def test_batch_import_converts_external_urls_and_is_idempotent(db_session, monkeypatch):
    calls = _fake_fetch(monkeypatch)
    user = _user(db_session)
    team = user.post(
        "/api/v1/teams/mine/custom",
        json={"name": "Lions", "icon": "https://cdn.example.com/lions.png"},
    ).json()

    resp = user.post(
        "/api/v1/icons/mine/import-from-teams", json={"team_ids": [team["id"]]},
    )
    assert resp.status_code == 200, resp.text
    (result,) = resp.json()["results"]
    assert result["status"] == "ok"
    assert result["icon_url"].startswith("/media/icons/")
    assert calls == ["https://cdn.example.com/lions.png"]

    # The team now points at the hosted icon and the icon is named after it.
    listing = user.get("/api/v1/icons").json()
    assert [i["name"] for i in listing["mine"]] == ["Lions"]

    # Re-running skips (already hosted) instead of duplicating.
    again = user.post(
        "/api/v1/icons/mine/import-from-teams", json={"team_ids": [team["id"]]},
    ).json()["results"][0]
    assert again["status"] == "skipped"
    assert len(calls) == 1


def test_batch_import_reports_download_errors_per_team(db_session, monkeypatch):
    _fake_fetch(monkeypatch, error=GuardedFetchError("host resolves to private/loopback IP 10.0.0.5"))
    user = _user(db_session)
    team = user.post(
        "/api/v1/teams/mine/custom",
        json={"name": "Lions", "icon": "https://internal.example.com/x.png"},
    ).json()

    (result,) = user.post(
        "/api/v1/icons/mine/import-from-teams", json={"team_ids": [team["id"]]},
    ).json()["results"]
    assert result["status"] == "error"
    assert "private" in result["error"]
    # The team keeps its original URL on failure.
    listing = user.get("/api/v1/icons").json()
    assert listing["mine"] == []


def test_batch_import_cannot_touch_other_users_teams(db_session, monkeypatch):
    _fake_fetch(monkeypatch)
    alice = _user(db_session, "alice")
    bob = _user(db_session, "bob")
    bob_team = bob.post(
        "/api/v1/teams/mine/custom",
        json={"name": "Bobs", "icon": "https://cdn.example.com/b.png"},
    ).json()

    (result,) = alice.post(
        "/api/v1/icons/mine/import-from-teams", json={"team_ids": [bob_team["id"]]},
    ).json()["results"]
    assert result["status"] == "error"
    assert "not found" in result["error"]


def test_admin_batch_import_converts_global_teams(db_session, monkeypatch):
    _fake_fetch(monkeypatch)
    admin = _admin(db_session)
    created = admin.post(
        "/api/v1/admin/teams",
        json={"name": "League Team", "icon": "https://cdn.example.com/l.png"},
    ).json()

    (result,) = admin.post(
        "/api/v1/admin/icons/import-from-teams", json={"team_ids": [created["id"]]},
    ).json()["results"]
    assert result["status"] == "ok"
    listing_icon = admin.get("/api/v1/icons").json()["globals"][0]
    assert listing_icon["name"] == "League Team"
    assert listing_icon["is_global"] is True


def test_batch_import_dedupes_repeated_team_ids(db_session, monkeypatch):
    calls = _fake_fetch(monkeypatch)
    user = _user(db_session)
    team = user.post(
        "/api/v1/teams/mine/custom",
        json={"name": "Lions", "icon": "https://cdn.example.com/lions.png"},
    ).json()

    results = user.post(
        "/api/v1/icons/mine/import-from-teams",
        json={"team_ids": [team["id"], team["id"], team["id"]]},
    ).json()["results"]
    assert len(results) == 1 and results[0]["status"] == "ok"
    assert len(calls) == 1


def test_batch_import_caps_batch_size(db_session, monkeypatch):
    from app.api.routes import icons as icons_routes

    monkeypatch.setattr(icons_routes, "ICONS_IMPORT_MAX_BATCH", 2)
    user = _user(db_session)
    resp = user.post(
        "/api/v1/icons/mine/import-from-teams", json={"team_ids": [1, 2, 3]},
    )
    assert resp.status_code == 400


def test_batch_import_dedupes_icon_names(db_session, monkeypatch):
    _fake_fetch(monkeypatch)
    user = _user(db_session)
    upload(user, "/api/v1/icons/mine", name="Lions")
    team = user.post(
        "/api/v1/teams/mine/custom",
        json={"name": "Lions", "icon": "https://cdn.example.com/lions.png"},
    ).json()

    (result,) = user.post(
        "/api/v1/icons/mine/import-from-teams", json={"team_ids": [team["id"]]},
    ).json()["results"]
    assert result["status"] == "ok"
    names = [i["name"] for i in user.get("/api/v1/icons").json()["mine"]]
    assert names == ["Lions", "Lions (2)"]


def test_deleting_a_user_unlinks_their_icon_files(db_session):
    """Icon rows cascade with the user; the bytes on disk must go too."""
    import os

    admin = _admin(db_session)
    user = _user(db_session, "temp-user")
    uploaded = upload(user, "/api/v1/icons/mine", name="Mine").json()
    filename = uploaded["url"].removeprefix("/media/icons/")
    path = os.path.join(icons_service.icons_dir(), filename)
    assert os.path.isfile(path)

    resp = admin.delete(f"/api/v1/admin/users/{user.test_user_id}")
    assert resp.status_code == 200, resp.text
    assert not os.path.exists(path)


# ---- team CRUD icon gate --------------------------------------------------------


def test_team_write_rejects_javascript_icon(db_session):
    user = _user(db_session)
    resp = user.post(
        "/api/v1/teams/mine/custom",
        json={"name": "Evil", "icon": "javascript:alert(1)"},
    )
    assert resp.status_code == 422


def test_team_write_accepts_hosted_and_legacy_icons(db_session):
    user = _user(db_session)
    assert user.post(
        "/api/v1/teams/mine/custom",
        json={"name": "Hosted", "icon": "/media/icons/abc-1234.webp"},
    ).status_code == 201
    assert user.post(
        "/api/v1/teams/mine/custom",
        json={"name": "Legacy", "icon": "foo.png"},
    ).status_code == 201
