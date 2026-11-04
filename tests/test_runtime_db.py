"""Runtime-state database: URL derivation, schema, and the legacy import."""

from __future__ import annotations

import json
import os

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api import action_log, session_persistence
from app.api._persistence_paths import hashed_filename
from app.db import runtime
from app.db.runtime import AuditEvent, OverlayRuntimeState, RuntimeSessionMeta
from app.db.runtime_import import IMPORTED_SUFFIX, import_legacy_runtime_files


class TestRuntimeDatabaseUrl:
    def test_sqlite_file_maps_to_sibling_runtime_db(self, tmp_path):
        main = f"sqlite:///{tmp_path}/app.db"
        assert runtime.runtime_database_url(main) == f"sqlite:///{tmp_path}/runtime.db"

    def test_in_memory_sqlite_stays_in_memory(self):
        assert runtime.runtime_database_url("sqlite://") == "sqlite://"
        assert runtime.runtime_database_url("sqlite:///:memory:") == "sqlite:///:memory:"

    def test_server_database_is_shared(self):
        url = "postgresql+psycopg://u:secret@db:5432/volley"
        assert runtime.runtime_database_url(url) == url

    def test_runtime_tables_are_not_in_the_alembic_metadata(self):
        from app.db import Base

        assert not any(runtime.is_runtime_table(t) for t in Base.metadata.tables)
        assert all(runtime.is_runtime_table(t) for t in runtime.RuntimeBase.metadata.tables)


class TestRuntimeSchema:
    def test_init_is_idempotent_and_stamps_version(self, runtime_db):
        runtime.init_runtime_schema(runtime_db)
        runtime.init_runtime_schema(runtime_db)
        with Session(runtime_db) as db:
            rows = db.scalars(select(runtime.RuntimeSchema)).all()
        assert [(r.id, r.version) for r in rows] == [(1, runtime.RUNTIME_SCHEMA_VERSION)]

    def test_file_backed_sqlite_uses_wal(self, tmp_path):
        engine = runtime.configure_runtime_engine(f"sqlite:///{tmp_path}/runtime.db")
        try:
            runtime.init_runtime_schema(engine)
            with engine.connect() as conn:
                mode = conn.exec_driver_sql("PRAGMA journal_mode").scalar()
            assert str(mode).lower() == "wal"
        finally:
            engine.dispose()


def _write_json(path, payload) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f)


@pytest.fixture
def legacy_dir(tmp_path):
    """A data dir holding one overlay's full set of pre-database files."""
    key = "7:court-1"
    _write_json(
        tmp_path / hashed_filename("overlay_state_", key),
        {"_meta": {"overlay_id": key}, "team_home": {"points": 11}},
    )
    _write_json(
        tmp_path / hashed_filename("session_meta_", key),
        {"_meta": {"oid": key}, "simple": True, "sets_limit": 3},
    )
    audit = tmp_path / hashed_filename("audit_", key, ".jsonl")
    # Rotated .2 is the oldest, then .1, then the active file.
    lines = {
        f"{audit}.2": [{"ts": 1.0, "action": "add_point", "params": {"team": 1}}],
        f"{audit}.1": [{"ts": 2.0, "action": "add_point", "params": {"team": 2}}],
        str(audit): [
            {"ts": 3.0, "action": "add_point", "params": {"team": 1}},
            {"ts": 4.0, "action": "_pop", "ref_ts": 3.0},
        ],
    }
    for path, records in lines.items():
        with open(path, "w", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record) + "\n")
            f.write("not json\n")
    # An audit file for an overlay we know nothing about.
    with open(tmp_path / hashed_filename("audit_", "9:ghost", ".jsonl"), "w") as f:
        f.write(json.dumps({"ts": 1.0, "action": "add_point"}) + "\n")
    return tmp_path, key


class TestLegacyImport:
    def test_imports_every_kind_and_renames_originals(self, legacy_dir, runtime_db):
        directory, key = legacy_dir
        counts = import_legacy_runtime_files(str(directory))
        assert counts == {"overlay_state": 1, "session_meta": 1, "audit": 3}

        with Session(runtime_db) as db:
            state = db.get(OverlayRuntimeState, key).state
            meta = db.get(RuntimeSessionMeta, key).data
        assert state["team_home"]["points"] == 11
        assert meta == {"simple": True, "sets_limit": 3}
        assert session_persistence.load_session_meta(key) == {"simple": True, "sets_limit": 3}

        # Oldest rotation first; malformed lines skipped; tombstone honoured.
        visible = action_log.read_all(key)
        assert [r["ts"] for r in visible] == [1.0, 2.0]

        names = os.listdir(directory)
        assert not any(
            n.startswith(("overlay_state_", "session_meta_")) and n.endswith(".json")
            for n in names
        )
        assert sum(n.endswith(IMPORTED_SUFFIX) for n in names) == 5
        # The orphan audit file is left exactly where it was.
        assert hashed_filename("audit_", "9:ghost", ".jsonl") in names

    def test_rerun_is_a_no_op(self, legacy_dir, runtime_db):
        directory, _key = legacy_dir
        import_legacy_runtime_files(str(directory))
        again = import_legacy_runtime_files(str(directory))
        assert again == {"overlay_state": 0, "session_meta": 0, "audit": 0}
        with Session(runtime_db) as db:
            assert len(db.scalars(select(AuditEvent)).all()) == 4

    def test_existing_rows_are_never_overwritten(self, legacy_dir, runtime_db):
        """A crash between commit and rename leaves file + row; the re-run
        must keep the row (it may have moved on) and just rename."""
        directory, key = legacy_dir
        with Session(runtime_db) as db, db.begin():
            db.add(OverlayRuntimeState(store_key=key, state={"newer": True}, updated_at=0.0))
            db.add(AuditEvent(store_key=key, ts=99.0, size=1, record={"ts": 99.0, "action": "x"}))
        import_legacy_runtime_files(str(directory))
        with Session(runtime_db) as db:
            assert db.get(OverlayRuntimeState, key).state == {"newer": True}
            records = db.scalars(
                select(AuditEvent.record).where(AuditEvent.store_key == key)
            ).all()
        assert records == [{"ts": 99.0, "action": "x"}]
        base = hashed_filename("audit_", key, ".jsonl")
        assert not any(
            n.startswith(base) and not n.endswith(IMPORTED_SUFFIX)
            for n in os.listdir(directory)
        )

    def test_audit_is_matched_to_keys_from_an_earlier_run(self, legacy_dir, runtime_db):
        """Crash after the state file was imported and renamed, before its
        audit files: the next start must still find and import them."""
        directory, key = legacy_dir
        state_name = hashed_filename("overlay_state_", key)
        meta_name = hashed_filename("session_meta_", key)
        with Session(runtime_db) as db, db.begin():
            db.add(OverlayRuntimeState(store_key=key, state={"x": 1}, updated_at=0.0))
        for name in (state_name, meta_name):
            os.replace(directory / name, directory / (name + IMPORTED_SUFFIX))

        counts = import_legacy_runtime_files(str(directory))
        assert counts["audit"] == 3
        assert [r["ts"] for r in action_log.read_all(key)] == [1.0, 2.0]

    def test_one_bad_file_does_not_block_the_rest(self, legacy_dir, runtime_db, monkeypatch):
        directory, key = legacy_dir
        from app.db import runtime_import

        def unreadable(path):
            raise OSError("simulated EIO")

        monkeypatch.setattr(runtime_import, "_read_jsonl", unreadable)
        counts = import_legacy_runtime_files(str(directory))
        # State and meta still imported; the audit set is left for next time.
        assert counts["overlay_state"] == 1 and counts["session_meta"] == 1
        base = hashed_filename("audit_", key, ".jsonl")
        assert base in os.listdir(directory)
        with Session(runtime_db) as db:
            assert db.scalars(select(AuditEvent)).all() == []

        monkeypatch.undo()
        import_legacy_runtime_files(str(directory))
        assert [r["ts"] for r in action_log.read_all(key)] == [1.0, 2.0]

    def test_non_numeric_ts_is_coerced_not_fatal(self, tmp_path, runtime_db):
        key = "3:bad-ts"
        _write_json(
            tmp_path / hashed_filename("overlay_state_", key),
            {"_meta": {"overlay_id": key}},
        )
        audit = tmp_path / hashed_filename("audit_", key, ".jsonl")
        audit.write_text(json.dumps({"ts": "bad", "action": "add_point"}) + "\n")
        counts = import_legacy_runtime_files(str(tmp_path))
        assert counts["audit"] == 1
        with Session(runtime_db) as db:
            (row,) = db.scalars(select(AuditEvent)).all()
        assert row.ts == 0.0 and row.record["ts"] == "bad"

    def test_single_tenant_bare_id_files_are_left_alone(self, tmp_path, runtime_db):
        """Pre-multi-user files are never read by the multi-user app (see
        README); the importer must not pull them in either."""
        name = hashed_filename("overlay_state_", "legacy-court")
        _write_json(tmp_path / name, {"_meta": {"overlay_id": "legacy-court"}})
        assert import_legacy_runtime_files(str(tmp_path))["overlay_state"] == 0
        assert name in os.listdir(tmp_path)
        with Session(runtime_db) as db:
            assert db.get(OverlayRuntimeState, "legacy-court") is None

    def test_missing_directory_is_fine(self, tmp_path):
        assert import_legacy_runtime_files(str(tmp_path / "nope")) == {
            "overlay_state": 0,
            "session_meta": 0,
            "audit": 0,
        }

    def test_imported_overlay_is_served_by_the_store(self, legacy_dir):
        from app.overlay import overlay_state_store

        directory, key = legacy_dir
        import_legacy_runtime_files(str(directory))
        assert overlay_state_store.overlay_exists(key)
        assert overlay_state_store.get_state(key)["team_home"]["points"] == 11
