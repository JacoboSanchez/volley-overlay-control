"""Portable global-team catalog transfer and conflict resolution."""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import icons_service
from app.bootstrap import create_app
from tests.conftest import login_client


@pytest.fixture(autouse=True)
def _icons_tmp_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(icons_service, "icons_dir", lambda: str(tmp_path / "icons"))


def _admin(db_session, username="root"):
    return login_client(
        TestClient(create_app()), db_session, username, role="admin",
    )


def _package(*teams, logos=None):
    return {
        "format": "volley-overlay-team-catalog",
        "version": 1,
        "teams": [
            {
                "key": f"team-{index}",
                "name": team[0],
                "icon": team[1] if len(team) > 1 else None,
                "color": team[2] if len(team) > 2 else None,
                "text_color": team[3] if len(team) > 3 else None,
                "logo_asset": team[4] if len(team) > 4 else None,
            }
            for index, team in enumerate(teams, start=1)
        ],
        "logos": logos or {},
    }


def _png_bytes() -> bytes:
    out = io.BytesIO()
    Image.new("RGBA", (32, 32), (20, 80, 220, 255)).save(out, format="PNG")
    return out.getvalue()


def test_transfer_endpoints_require_admin(db_session):
    user = login_client(TestClient(create_app()), db_session, "alice", role="user")
    package = _package(("Lions",))

    assert user.get("/api/v1/admin/teams/transfer/export").status_code == 403
    assert user.post(
        "/api/v1/admin/teams/transfer/preview", json=package,
    ).status_code == 403
    assert user.post(
        "/api/v1/admin/teams/transfer/import",
        json={"catalog": package},
    ).status_code == 403


def test_export_option_embeds_hosted_logos(db_session):
    admin = _admin(db_session)
    upload = admin.post(
        "/api/v1/admin/icons",
        data={"name": "Lions"},
        files={"file": ("lions.png", _png_bytes(), "image/png")},
    )
    assert upload.status_code == 201, upload.text
    logo_url = upload.json()["url"]
    admin.post(
        "/api/v1/admin/teams",
        json={"name": "Lions", "icon": logo_url, "color": "#123456"},
    )

    without = admin.get("/api/v1/admin/teams/transfer/export").json()
    assert without["format"] == "volley-overlay-team-catalog"
    assert without["version"] == 1
    assert without["logos"] == {}
    assert without["teams"][0]["logo_asset"] is None
    assert without["teams"][0]["icon"] == logo_url

    with_logos = admin.get(
        "/api/v1/admin/teams/transfer/export?include_logos=true"
    ).json()
    asset_key = with_logos["teams"][0]["logo_asset"]
    assert asset_key in with_logos["logos"]
    assert with_logos["logos"][asset_key]["mime"] == "image/webp"
    assert with_logos["logos"][asset_key]["data"]


def test_export_with_logos_rejects_untracked_hosted_url(db_session):
    admin = _admin(db_session)
    admin.post(
        "/api/v1/admin/teams",
        json={"name": "Broken", "icon": "/media/icons/missing.webp"},
    )

    exported = admin.get(
        "/api/v1/admin/teams/transfer/export?include_logos=true"
    )
    assert exported.status_code == 400
    assert "global icon library" in exported.json()["detail"]


def test_replace_preserves_team_id_and_group_membership(db_session):
    admin = _admin(db_session)
    existing = admin.post(
        "/api/v1/admin/teams", json={"name": "Lions", "color": "#111111"},
    ).json()
    group_id = admin.post(
        "/api/v1/admin/team-groups", json={"name": "League"},
    ).json()["id"]
    admin.post(
        f"/api/v1/admin/team-groups/{group_id}/members",
        json={"team_id": existing["id"]},
    )
    package = _package(("Lions", None, "#abcdef", "#ffffff"))

    preview = admin.post(
        "/api/v1/admin/teams/transfer/preview", json=package,
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["conflicts"] == [
        {
            "key": "team-1",
            "incoming_name": "Lions",
            "existing_team_id": existing["id"],
            "existing_name": "Lions",
            "kind": "catalog",
        }
    ]

    imported = admin.post(
        "/api/v1/admin/teams/transfer/import",
        json={
            "catalog": package,
            "resolutions": [
                {
                    "key": "team-1",
                    "action": "replace",
                    "expected_team_id": existing["id"],
                }
            ],
        },
    )
    assert imported.status_code == 200, imported.text
    assert imported.json() == {"imported": 1, "created": 0, "replaced": 1}
    catalog = admin.get("/api/v1/teams/catalog").json()
    assert catalog == [{**existing, "color": "#abcdef", "text_color": "#ffffff"}]
    group = admin.get("/api/v1/admin/team-groups").json()[0]
    assert [team["id"] for team in group["teams"]] == [existing["id"]]


def test_rename_one_conflict_and_replace_all_remaining(db_session):
    admin = _admin(db_session)
    admin.post("/api/v1/admin/teams", json={"name": "Lions", "color": "old"})
    tigers = admin.post(
        "/api/v1/admin/teams", json={"name": "Tigers", "color": "old"},
    ).json()
    package = _package(
        ("Lions", None, "new-lions"),
        ("Tigers", None, "new-tigers"),
        ("Bears", None, "new-bears"),
    )

    imported = admin.post(
        "/api/v1/admin/teams/transfer/import",
        json={
            "catalog": package,
            "resolutions": [
                {"key": "team-1", "action": "rename", "name": "Lions imported"},
                {
                    "key": "team-2",
                    "action": "replace",
                    "expected_team_id": tigers["id"],
                },
            ],
        },
    )
    assert imported.status_code == 200, imported.text
    assert imported.json() == {"imported": 3, "created": 2, "replaced": 1}
    catalog = {
        team["name"]: team for team in admin.get("/api/v1/teams/catalog").json()
    }
    assert catalog["Lions"]["color"] == "old"
    assert catalog["Lions imported"]["color"] == "new-lions"
    assert catalog["Tigers"]["color"] == "new-tigers"
    assert catalog["Bears"]["color"] == "new-bears"


def test_duplicate_name_in_file_never_replaces_one_team_twice(db_session):
    admin = _admin(db_session)
    existing = admin.post(
        "/api/v1/admin/teams", json={"name": "Lions"},
    ).json()
    package = _package(("Lions",), ("Lions",))

    preview = admin.post(
        "/api/v1/admin/teams/transfer/preview", json=package,
    ).json()
    assert preview["conflicts"][0]["kind"] == "catalog"
    assert preview["conflicts"][1]["kind"] == "file"

    imported = admin.post(
        "/api/v1/admin/teams/transfer/import",
        json={
            "catalog": package,
            "resolutions": [
                {
                    "key": "team-1",
                    "action": "replace",
                    "expected_team_id": existing["id"],
                },
                {"key": "team-2", "action": "rename", "name": "Lions copy"},
            ],
        },
    )
    assert imported.status_code == 200, imported.text
    assert imported.json() == {"imported": 2, "created": 1, "replaced": 1}


def test_replace_rejects_a_stale_previewed_team_id(db_session):
    admin = _admin(db_session)
    team = admin.post("/api/v1/admin/teams", json={"name": "Lions"}).json()
    package = _package(("Lions",))

    imported = admin.post(
        "/api/v1/admin/teams/transfer/import",
        json={
            "catalog": package,
            "resolutions": [
                {
                    "key": "team-1",
                    "action": "replace",
                    "expected_team_id": team["id"] + 1000,
                }
            ],
        },
    )
    assert imported.status_code == 409
    assert "preview" in imported.json()["detail"]


def test_embedded_logo_is_reprocessed_into_the_global_library(db_session):
    admin = _admin(db_session)
    upload = admin.post(
        "/api/v1/admin/icons",
        data={"name": "Portable"},
        files={"file": ("portable.png", _png_bytes(), "image/png")},
    ).json()
    team = admin.post(
        "/api/v1/admin/teams",
        json={"name": "Portable", "icon": upload["url"]},
    ).json()
    package = admin.get(
        "/api/v1/admin/teams/transfer/export?include_logos=true"
    ).json()
    admin.delete(f"/api/v1/admin/teams/{team['id']}")

    imported = admin.post(
        "/api/v1/admin/teams/transfer/import", json={"catalog": package},
    )
    assert imported.status_code == 200, imported.text
    recreated = admin.get("/api/v1/teams/catalog").json()[0]
    assert recreated["icon"].startswith("/media/icons/")
    assert recreated["icon"] != upload["url"]


def test_import_rejects_unresolved_and_invalid_logo_conflicts(db_session):
    admin = _admin(db_session)
    admin.post("/api/v1/admin/teams", json={"name": "Lions"})
    conflict = _package(("Lions",))
    unresolved = admin.post(
        "/api/v1/admin/teams/transfer/import", json={"catalog": conflict},
    )
    assert unresolved.status_code == 409

    bad_logo = _package(
        ("Bears", None, None, None, "bad"),
        logos={"bad": {"mime": "image/webp", "data": "!!!!"}},
    )
    invalid = admin.post(
        "/api/v1/admin/teams/transfer/import", json={"catalog": bad_logo},
    )
    assert invalid.status_code == 400
    assert "base64" in invalid.json()["detail"]
