"""Unit coverage for the hosted icon library service layer.

The image pipeline (decode → shrink → WebP) and the DB/file consistency
rules (quota, scoped names, delete-clears-teams) are exercised directly
against the in-memory SQLite session from ``conftest.db_session``; the
HTTP layer has its own coverage in ``test_icons_api.py``.
"""

from __future__ import annotations

import io
import os

import pytest
from PIL import Image

from app import icons_service
from app.db.models.icon import Icon
from app.db.models.team import Team
from app.db.models.user import User


@pytest.fixture(autouse=True)
def _icons_tmp_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(icons_service, "icons_dir", lambda: str(tmp_path / "icons"))
    yield


@pytest.fixture
def user(db_session):
    u = User(username="ana", password_hash="x")
    db_session.add(u)
    db_session.commit()
    return u


def png_bytes(width=64, height=64, color=(255, 0, 0, 255), fmt="PNG"):
    buf = io.BytesIO()
    Image.new("RGBA", (width, height), color).save(buf, format=fmt)
    return buf.getvalue()


# ---- process_icon_upload -----------------------------------------------------


def test_process_small_png_roundtrips_to_webp():
    processed = icons_service.process_icon_upload(png_bytes(64, 64))
    assert processed.width == 64 and processed.height == 64
    with Image.open(io.BytesIO(processed.content)) as out:
        assert out.format == "WEBP"


def test_process_shrinks_oversized_images_preserving_aspect():
    processed = icons_service.process_icon_upload(png_bytes(2048, 1024))
    assert (processed.width, processed.height) == (512, 256)


def test_process_never_upscales():
    processed = icons_service.process_icon_upload(png_bytes(30, 20))
    assert (processed.width, processed.height) == (30, 20)


def test_process_rejects_svg_with_clear_message():
    svg = b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"/>'
    with pytest.raises(icons_service.IconError, match="SVG"):
        icons_service.process_icon_upload(svg)


def test_process_rejects_non_image_bytes():
    with pytest.raises(icons_service.IconError, match="not a recognizable image"):
        icons_service.process_icon_upload(b"definitely not an image")


def test_process_rejects_oversized_input(monkeypatch):
    monkeypatch.setattr(icons_service, "ICONS_MAX_UPLOAD_BYTES", 100)
    with pytest.raises(icons_service.IconError, match="too large"):
        icons_service.process_icon_upload(png_bytes(256, 256))


def test_process_flattens_animated_gif_to_first_frame():
    frames = [
        Image.new("P", (40, 40), i) for i in (0, 128, 255)
    ]
    buf = io.BytesIO()
    frames[0].save(buf, format="GIF", save_all=True, append_images=frames[1:])
    processed = icons_service.process_icon_upload(buf.getvalue())
    with Image.open(io.BytesIO(processed.content)) as out:
        assert out.format == "WEBP"
        assert getattr(out, "n_frames", 1) == 1


def test_process_applies_exif_orientation():
    # Orientation 6 = rotate 270° CW on display: a 100x60 JPEG renders 60x100.
    img = Image.new("RGB", (100, 60), (0, 128, 0))
    exif = img.getexif()
    exif[0x0112] = 6
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    processed = icons_service.process_icon_upload(buf.getvalue())
    assert (processed.width, processed.height) == (60, 100)


# ---- create / quota / names --------------------------------------------------


def test_create_personal_icon_writes_file_and_row(db_session, user):
    icon = icons_service.create_icon(
        db_session, name="Lions", raw=png_bytes(), user_id=user.id,
    )
    db_session.commit()
    assert icon.is_global is False and icon.owner_user_id == user.id
    assert icon.mime == "image/webp"
    path = os.path.join(icons_service.icons_dir(), icon.filename)
    assert os.path.isfile(path)
    assert os.path.getsize(path) == icon.size_bytes
    # mkstemp creates 0600; the stored file must be world-readable so a
    # reverse proxy serving /media straight from disk can read it.
    assert os.stat(path).st_mode & 0o777 == 0o644


def test_create_global_icon_has_no_owner(db_session):
    icon = icons_service.create_icon(
        db_session, name="League", raw=png_bytes(), user_id=None,
    )
    db_session.commit()
    assert icon.is_global is True and icon.owner_user_id is None


def test_duplicate_name_rejected_case_insensitively(db_session, user):
    icons_service.create_icon(db_session, name="Lions", raw=png_bytes(), user_id=user.id)
    with pytest.raises(icons_service.IconError, match="already exists"):
        icons_service.create_icon(db_session, name="lions", raw=png_bytes(), user_id=user.id)


def test_same_name_allowed_across_scopes(db_session, user):
    icons_service.create_icon(db_session, name="Lions", raw=png_bytes(), user_id=user.id)
    icons_service.create_icon(db_session, name="Lions", raw=png_bytes(), user_id=None)
    db_session.commit()


def test_dedupe_suffixes_taken_names(db_session, user):
    icons_service.create_icon(db_session, name="Lions", raw=png_bytes(), user_id=user.id)
    icon = icons_service.create_icon(
        db_session, name="Lions", raw=png_bytes(), user_id=user.id, dedupe=True,
    )
    assert icon.name == "Lions (2)"


def test_dedupe_never_exceeds_the_column_width(db_session, user):
    """A 120-char base (a team name at the limit) must yield a suffixed
    candidate that still fits String(120) — Postgres refuses overflow."""
    base = "L" * 120
    icons_service.create_icon(db_session, name=base, raw=png_bytes(), user_id=user.id)
    icon = icons_service.create_icon(
        db_session, name=base, raw=png_bytes(), user_id=user.id, dedupe=True,
    )
    assert len(icon.name) <= 120
    assert icon.name.endswith(" (2)")


def test_delete_rolled_back_keeps_row_and_file(db_session, user):
    """The unlink belongs to the caller's post-commit step: a rollback must
    leave both the row and the file intact (no dangling row pointing at
    nothing) — and no lingering session hook may delete the file later."""
    icon = icons_service.create_icon(
        db_session, name="Keep", raw=png_bytes(), user_id=user.id,
    )
    db_session.commit()
    path = os.path.join(icons_service.icons_dir(), icon.filename)

    icons_service.delete_icon(db_session, icon)
    db_session.rollback()

    assert os.path.exists(path)
    assert db_session.query(Icon).count() == 1

    # Regression (PR #392 round 3): with the old after_commit listener a
    # later unrelated commit on the same session deleted the file.
    db_session.add(Icon(
        name="Other", filename="other-file.webp", mime="image/webp",
        width=1, height=1, size_bytes=1, owner_user_id=user.id,
    ))
    db_session.commit()
    assert os.path.exists(path)


def test_batch_import_isolates_unexpected_commit_errors(db_session, user, monkeypatch):
    """A non-application exception on one team must not take the batch down."""
    db_session.add_all([
        Team(name="First", icon_url="https://cdn.example.com/a.png", owner_user_id=user.id),
        Team(name="Second", icon_url="https://cdn.example.com/b.png", owner_user_id=user.id),
    ])
    db_session.commit()
    teams = list(db_session.query(Team).order_by(Team.id))

    monkeypatch.setattr(icons_service, "fetch_guarded", lambda url, **kw: png_bytes())
    original_create = icons_service.create_icon
    calls = {"n": 0}

    def flaky_create(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("simulated transient failure")
        return original_create(*args, **kwargs)

    monkeypatch.setattr(icons_service, "create_icon", flaky_create)
    results = icons_service.import_icons_from_teams(db_session, teams, user_id=user.id)

    assert [r["status"] for r in results] == ["error", "ok"]
    assert results[0]["error"] == "internal error"
    assert results[1]["icon_url"].startswith("/media/icons/")


def test_personal_quota_enforced(db_session, user, monkeypatch):
    monkeypatch.setattr(icons_service, "ICONS_MAX_PER_USER", 2)
    icons_service.create_icon(db_session, name="A", raw=png_bytes(), user_id=user.id)
    icons_service.create_icon(db_session, name="B", raw=png_bytes(), user_id=user.id)
    with pytest.raises(icons_service.IconError, match="quota"):
        icons_service.create_icon(db_session, name="C", raw=png_bytes(), user_id=user.id)
    # Globals ignore the per-user cap.
    icons_service.create_icon(db_session, name="G", raw=png_bytes(), user_id=None)


def test_rename_checks_scope_uniqueness(db_session, user):
    icons_service.create_icon(db_session, name="Lions", raw=png_bytes(), user_id=user.id)
    tigers = icons_service.create_icon(
        db_session, name="Tigers", raw=png_bytes(), user_id=user.id,
    )
    with pytest.raises(icons_service.IconError, match="already exists"):
        icons_service.rename_icon(db_session, tigers, "LIONS")
    icons_service.rename_icon(db_session, tigers, "Panthers")
    assert tigers.name == "Panthers"


def test_get_scoped_hides_cross_scope_rows(db_session, user):
    personal = icons_service.create_icon(
        db_session, name="Mine", raw=png_bytes(), user_id=user.id,
    )
    global_icon = icons_service.create_icon(
        db_session, name="Global", raw=png_bytes(), user_id=None,
    )
    db_session.commit()
    assert icons_service.get_scoped(db_session, personal.id, user_id=None) is None
    assert icons_service.get_scoped(db_session, global_icon.id, user_id=user.id) is None
    assert icons_service.get_scoped(db_session, personal.id, user_id=user.id) is personal


# ---- delete clears referencing teams ----------------------------------------


def test_delete_clears_referencing_teams_and_unlinks_file(db_session, user):
    icon = icons_service.create_icon(
        db_session, name="Lions", raw=png_bytes(), user_id=user.id,
    )
    url = icons_service.icon_public_url(icon.filename)
    db_session.add_all([
        Team(name="Lions A", icon_url=url, owner_user_id=user.id),
        Team(name="Lions B", icon_url=url, is_global=True),
        Team(name="Other", icon_url="https://example.com/x.png", is_global=True),
    ])
    db_session.commit()
    path = os.path.join(icons_service.icons_dir(), icon.filename)

    assert icons_service.usage_count(db_session, icon) == 2
    cleared, filename = icons_service.delete_icon(db_session, icon)
    db_session.commit()

    assert cleared == 2
    # The service never unlinks — that's the caller's post-commit step.
    assert os.path.exists(path)
    icons_service.unlink_files([filename])
    assert not os.path.exists(path)
    urls = [t.icon_url for t in db_session.query(Team).order_by(Team.name)]
    assert urls == [None, None, "https://example.com/x.png"]
    assert db_session.query(Icon).count() == 0


def test_filenames_for_user_and_unlink(db_session, user, tmp_path):
    a = icons_service.create_icon(db_session, name="A", raw=png_bytes(), user_id=user.id)
    icons_service.create_icon(db_session, name="G", raw=png_bytes(), user_id=None)
    db_session.commit()
    names = icons_service.filenames_for_user(db_session, user.id)
    assert names == [a.filename]
    icons_service.unlink_files(names)
    assert not os.path.exists(os.path.join(icons_service.icons_dir(), a.filename))


def test_pixel_budget_enforced_before_decode(monkeypatch, db_session):
    """An image between 1× and 2× ICONS_MAX_PIXELS decodes fine under
    Pillow's bomb guard (which only hard-fails at 2×) but must be
    rejected by the explicit pre-decode check."""
    import io

    from PIL import Image

    from app import icons_service

    img = Image.new("RGB", (300, 300))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    raw = buf.getvalue()

    monkeypatch.setattr(icons_service, "ICONS_MAX_PIXELS", 300 * 300 - 1)
    with pytest.raises(icons_service.IconError, match="too many pixels"):
        icons_service.process_icon_upload(raw)

    monkeypatch.setattr(icons_service, "ICONS_MAX_PIXELS", 300 * 300)
    assert icons_service.process_icon_upload(raw).width == 300


def test_upload_commit_failure_leaves_no_orphan_file(monkeypatch, db_session, tmp_path):
    """If the route's commit fails after create_icon wrote the file, the
    file must be unlinked — not orphaned under /media."""
    import io
    import os

    from PIL import Image

    from app import icons_service
    from app.api.routes.icons import _create_icon_sync

    monkeypatch.setattr(icons_service, "icons_dir", lambda: str(tmp_path))
    img = Image.new("RGB", (10, 10))
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    real_commit = db_session.commit
    calls = {"n": 0}

    def failing_commit():
        calls["n"] += 1
        raise RuntimeError("disk full")

    monkeypatch.setattr(db_session, "commit", failing_commit)
    with pytest.raises(RuntimeError, match="disk full"):
        _create_icon_sync(db_session, name="Boom", raw=buf.getvalue(), user_id=None)
    monkeypatch.setattr(db_session, "commit", real_commit)

    assert calls["n"] == 1
    assert os.listdir(tmp_path) == [], "orphaned icon file left behind"


def test_batch_import_commit_failure_cleans_created_file(monkeypatch, db_session, tmp_path):
    import io
    import os

    from PIL import Image

    from app import icons_service
    from app.db.models.team import Team

    monkeypatch.setattr(icons_service, "icons_dir", lambda: str(tmp_path))
    img = Image.new("RGB", (10, 10))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    monkeypatch.setattr(
        icons_service, "fetch_guarded",
        lambda url, max_bytes, timeout: buf.getvalue(),
    )

    team = Team(name="Wolves", is_global=True, icon_url="https://x/y.png")
    db_session.add(team)
    db_session.commit()

    monkeypatch.setattr(
        db_session, "commit",
        lambda: (_ for _ in ()).throw(RuntimeError("commit died")),
    )
    results = icons_service.import_icons_from_teams(db_session, [team], user_id=None)
    assert results[0]["status"] == "error"
    assert os.listdir(tmp_path) == [], "orphaned icon file left behind"
