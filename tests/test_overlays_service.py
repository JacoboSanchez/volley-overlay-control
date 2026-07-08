"""Phase 3a — per-user overlay storage keys and the user_overlays service."""

from __future__ import annotations

import pytest

from app import overlays_service
from app.overlay_key import is_valid_skey, make_skey, split_skey


def _user(db, username):
    from app.auth import service
    return service.create_user(db, username=username, password="password123")


# ---- skey helpers ----------------------------------------------------------


def test_skey_roundtrip():
    skey = make_skey(7, "liga")
    assert skey == "7:liga"
    assert is_valid_skey(skey)
    assert split_skey(skey) == (7, "liga")


@pytest.mark.parametrize("bad", ["liga", "x:liga", "7:..", "7:bad/slash", ":liga", "7:"])
def test_invalid_skeys_rejected(bad):
    assert not is_valid_skey(bad)


def test_oid_with_allowed_punctuation_is_valid():
    assert is_valid_skey(make_skey(12, "my.board-1_v2"))


# ---- service ---------------------------------------------------------------


def test_two_users_can_create_same_oid(db_session):
    a = _user(db_session, "alice")
    b = _user(db_session, "bob")
    db_session.flush()

    oa = overlays_service.create_overlay(db_session, a.id, "liga", description="A liga")
    ob = overlays_service.create_overlay(db_session, b.id, "liga")
    db_session.commit()

    assert oa.oid == ob.oid == "liga"
    assert oa.public_token != ob.public_token
    assert overlays_service.skey_for(oa) == f"{a.id}:liga"
    assert overlays_service.skey_for(ob) == f"{b.id}:liga"


def test_duplicate_oid_for_same_user_rejected(db_session):
    a = _user(db_session, "alice")
    db_session.flush()
    overlays_service.create_overlay(db_session, a.id, "liga")
    with pytest.raises(overlays_service.OverlayError):
        overlays_service.create_overlay(db_session, a.id, "liga")


def test_invalid_oid_rejected(db_session):
    a = _user(db_session, "alice")
    db_session.flush()
    with pytest.raises(overlays_service.OverlayError):
        overlays_service.create_overlay(db_session, a.id, "bad/slash")


def test_lookup_by_public_token_and_listing(db_session):
    a = _user(db_session, "alice")
    db_session.flush()
    o1 = overlays_service.create_overlay(db_session, a.id, "alpha")
    o2 = overlays_service.create_overlay(db_session, a.id, "beta")
    db_session.commit()

    assert overlays_service.get_by_public_token(db_session, o1.public_token).id == o1.id
    assert overlays_service.get_by_public_token(db_session, "nope") is None
    assert [o.oid for o in overlays_service.list_overlays(db_session, a.id)] == ["alpha", "beta"]
    assert overlays_service.delete_overlay(db_session, a.id, "alpha") is True
    assert overlays_service.delete_overlay(db_session, a.id, "alpha") is False
    assert [o.oid for o in overlays_service.list_overlays(db_session, a.id)] == ["beta"]
    _ = o2


def test_create_and_update_overlay_settings(db_session):
    a = _user(db_session, "alice")
    db_session.flush()
    o = overlays_service.create_overlay(
        db_session, a.id, "liga",
        description="Liga",
    )
    db_session.commit()
    assert o.description == "Liga"

    # Partial update: toggling public_control leaves description untouched.
    overlays_service.update_overlay(db_session, a.id, "liga", public_control=True)
    db_session.commit()
    refreshed = overlays_service.get_overlay(db_session, a.id, "liga")
    assert refreshed.public_control is True
    assert refreshed.description == "Liga"

    # Clearing a field with an empty string nulls it.
    overlays_service.update_overlay(db_session, a.id, "liga", description="")
    db_session.commit()
    assert overlays_service.get_overlay(db_session, a.id, "liga").description is None


def test_overlays_deleted_when_user_deleted(db_session):
    from app.auth import service

    a = _user(db_session, "alice")
    db_session.flush()
    overlays_service.create_overlay(db_session, a.id, "alpha")
    db_session.commit()

    service.delete_user(db_session, a)
    db_session.commit()
    assert overlays_service.list_overlays(db_session, a.id) == []


def test_create_overlay_race_maps_integrity_error(db_session, monkeypatch):
    """A concurrent duplicate that slips past the pre-check must surface as
    OverlayError (→ 400), not IntegrityError (→ 500), and leave the
    session usable."""
    from app import overlays_service
    from tests.conftest import make_user

    user = make_user(db_session, "raceuser")
    overlays_service.create_overlay(db_session, user.id, "liga")
    db_session.commit()

    monkeypatch.setattr(overlays_service, "get_overlay", lambda db, uid, oid: None)
    with pytest.raises(overlays_service.OverlayError, match="already have"):
        overlays_service.create_overlay(db_session, user.id, "liga")
    # Session survived the rollback and still works.
    assert overlays_service.get_by_control_token(db_session, "nope") is None
