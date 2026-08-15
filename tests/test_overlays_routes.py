"""End-to-end coverage for the per-user overlay routes (/api/v1/overlays).

Focus: the DELETE cascade (overlay row + live session + local state + archived
matches) and cross-user isolation when two users own the same oid.
"""

from __future__ import annotations

import threading

from fastapi.testclient import TestClient

from app.api import action_log, match_archive, session_persistence
from app.api.game_service import GameService
from app.api.session_manager import SessionManager
from app.bootstrap import create_app
from app.overlay import overlay_state_store
from app.overlay_executor import get_overlay_executor
from app.overlay_key import make_skey
from app.overlay_lifecycle import overlay_lifecycle_gate
from tests.conftest import login_client


def _archive(user_id: int, oid: str) -> str:
    match_id = match_archive.archive_match(
        oid=make_skey(user_id, oid),
        final_state={"team_1": {"sets": 3}, "team_2": {"sets": 0}},
        customization={"Team 1 Name": "Home", "Team 2 Name": "Away"},
        winning_team=1,
        sets_limit=5,
    )
    assert match_id is not None
    return match_id


def test_owner_delete_cascades_overlay_and_matches(db_session):
    c = TestClient(create_app())
    login_client(c, db_session, username="owner")

    assert c.post("/api/v1/overlays", json={"oid": "liga"}).status_code == 201
    _archive(c.test_user_id, "liga")
    assert match_archive.list_matches(oid=make_skey(c.test_user_id, "liga"))

    assert c.delete("/api/v1/overlays/liga").status_code == 200
    # Gone from the caller's listing…
    assert all(o["oid"] != "liga" for o in c.get("/api/v1/overlays").json())
    # …and the archived matches were cleaned up.
    assert match_archive.list_matches(oid=make_skey(c.test_user_id, "liga")) == []


def test_delete_unknown_overlay_is_404(db_session):
    c = TestClient(create_app())
    login_client(c, db_session, username="owner")
    assert c.delete("/api/v1/overlays/nope").status_code == 404
    # The rolled-back deletion claim must not strand the OID as busy.
    assert c.post("/api/v1/overlays", json={"oid": "nope"}).status_code == 201


def test_non_owner_cannot_delete_same_named_overlay(db_session):
    alice = TestClient(create_app())
    login_client(alice, db_session, username="alice")
    assert alice.post("/api/v1/overlays", json={"oid": "liga"}).status_code == 201

    bob = TestClient(create_app())
    login_client(bob, db_session, username="bob")
    # Bob has no "liga" overlay; deleting it must 404, not touch Alice's.
    assert bob.delete("/api/v1/overlays/liga").status_code == 404
    assert any(o["oid"] == "liga" for o in alice.get("/api/v1/overlays").json())


def test_owner_can_favorite_and_order_overlays(db_session):
    c = TestClient(create_app())
    login_client(c, db_session, username="owner")

    alpha = c.post("/api/v1/overlays", json={"oid": "alpha"})
    beta = c.post("/api/v1/overlays", json={"oid": "beta"})
    assert alpha.status_code == beta.status_code == 201
    assert alpha.json()["is_favorite"] is False

    updated = c.patch(
        "/api/v1/overlays/beta",
        json={"is_favorite": True},
    )
    assert updated.status_code == 200
    assert updated.json()["is_favorite"] is True
    assert [row["oid"] for row in c.get("/api/v1/overlays").json()] == [
        "beta",
        "alpha",
    ]


def test_delete_blocks_same_oid_recreation_until_runtime_cleanup(db_session):
    app = create_app()
    owner = TestClient(app)
    login_client(owner, db_session, username="race-owner")
    contender = TestClient(app)
    assert contender.post(
        "/api/v1/auth/login",
        json={"username": "race-owner", "password": "password123"},
    ).status_code == 200
    assert owner.post("/api/v1/session/init", json={"oid": "race"}).status_code == 200
    skey = make_skey(owner.test_user_id, "race")

    old_work_started = threading.Event()
    release_old_work = threading.Event()

    def old_queued_push() -> None:
        old_work_started.set()
        assert release_old_work.wait(timeout=3)

    old_work = get_overlay_executor().submit(skey, old_queued_push)
    assert old_work_started.wait(timeout=2)

    delete_status: list[int] = []

    def delete_overlay() -> None:
        delete_status.append(owner.delete("/api/v1/overlays/race").status_code)

    deleter = threading.Thread(target=delete_overlay)
    deleter.start()
    for _ in range(200):
        if overlay_lifecycle_gate.is_deleting(skey):
            break
        threading.Event().wait(0.01)
    assert overlay_lifecycle_gate.is_deleting(skey)

    # Both explicit recreation and owner-mode auto-creation are rejected
    # while deletion is waiting for stale keyed work to drain.
    assert contender.post("/api/v1/overlays", json={"oid": "race"}).status_code == 409
    assert contender.post("/api/v1/session/init", json={"oid": "race"}).status_code == 409

    release_old_work.set()
    old_work.result(timeout=3)
    deleter.join(timeout=3)
    assert not deleter.is_alive()
    assert delete_status == [200]
    assert SessionManager.peek(skey) is None
    assert not overlay_state_store.overlay_exists(skey)

    # Once cleanup releases the claim, recreation succeeds with fresh state.
    recreated = owner.post("/api/v1/session/init", json={"oid": "race"})
    assert recreated.status_code == 200
    assert recreated.json()["state"]["team_1"]["scores"].get("set_1", 0) == 0


def test_delete_rejects_inflight_mutation_then_removes_all_runtime(
    db_session, monkeypatch,
):
    app = create_app()
    owner = TestClient(app)
    login_client(owner, db_session, username="mutation-owner")
    operator = TestClient(app)
    assert operator.post(
        "/api/v1/auth/login",
        json={"username": "mutation-owner", "password": "password123"},
    ).status_code == 200
    assert owner.post("/api/v1/session/init", json={"oid": "mutation-race"}).status_code == 200
    skey = make_skey(owner.test_user_id, "mutation-race")
    _archive(owner.test_user_id, "mutation-race")

    mutation_started = threading.Event()
    release_mutation = threading.Event()
    mutation_status: list[int] = []
    original_add_point = GameService.add_point.__func__

    def blocked_add_point(cls, session, *args, **kwargs):
        mutation_started.set()
        assert release_mutation.wait(timeout=5)
        return original_add_point(cls, session, *args, **kwargs)

    monkeypatch.setattr(GameService, "add_point", classmethod(blocked_add_point))

    def mutate() -> None:
        mutation_status.append(
            operator.post(
                "/api/v1/game/add-point?oid=mutation-race",
                json={"team": 1},
            ).status_code,
        )

    mutator = threading.Thread(target=mutate)
    mutator.start()
    try:
        assert mutation_started.wait(timeout=3)
        # The mutation owns a shared request-lifecycle claim, so deletion
        # fails without touching the row or runtime instead of racing cleanup.
        assert owner.delete("/api/v1/overlays/mutation-race").status_code == 409
    finally:
        release_mutation.set()

    mutator.join(timeout=5)
    assert not mutator.is_alive()
    assert mutation_status == [200]
    assert action_log.read_all(skey)
    assert session_persistence.load_session_meta(skey) is not None
    assert match_archive.list_matches(oid=skey)

    assert owner.delete("/api/v1/overlays/mutation-race").status_code == 200
    assert SessionManager.peek(skey) is None
    assert action_log.read_all(skey) == []
    assert session_persistence.load_session_meta(skey) is None
    assert match_archive.list_matches(oid=skey) == []
    assert not overlay_state_store.overlay_exists(skey)
