"""Tests for scripts/release/cut_changelog.py (pure string transform)."""

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = (
    Path(__file__).resolve().parent.parent
    / "scripts" / "release" / "cut_changelog.py"
)
_spec = importlib.util.spec_from_file_location("cut_changelog", _SCRIPT)
assert _spec is not None and _spec.loader is not None
cut_changelog = importlib.util.module_from_spec(_spec)
sys.modules["cut_changelog"] = cut_changelog
_spec.loader.exec_module(cut_changelog)

SAMPLE = """# Changelog

Intro text.

## [Unreleased]

### Added

- A shiny new feature.

### Fixed

- A bug.

## [5.5.0] - 2026-05-31

### Added

- Old stuff.
"""


def test_cut_moves_unreleased_into_versioned_section():
    new_text, _notes = cut_changelog.cut_unreleased(SAMPLE, "5.6.0", "2026-06-10")

    assert "## [5.6.0] - 2026-06-10" in new_text
    # A fresh empty Unreleased section sits above the new release.
    unreleased_pos = new_text.index("## [Unreleased]")
    release_pos = new_text.index("## [5.6.0]")
    old_pos = new_text.index("## [5.5.0]")
    assert unreleased_pos < release_pos < old_pos
    # The released body moved under the version heading, not Unreleased.
    between = new_text[unreleased_pos:release_pos]
    assert "A shiny new feature." not in between
    after = new_text[release_pos:old_pos]
    assert "A shiny new feature." in after
    assert "A bug." in after


def test_cut_returns_release_notes_body():
    _, notes = cut_changelog.cut_unreleased(SAMPLE, "5.6.0", "2026-06-10")
    assert notes.startswith("### Added")
    assert "A shiny new feature." in notes
    assert "## [" not in notes


def test_rejects_non_semver_version():
    with pytest.raises(cut_changelog.ChangelogError, match="not plain semver"):
        cut_changelog.cut_unreleased(SAMPLE, "v5.6.0", "2026-06-10")
    with pytest.raises(cut_changelog.ChangelogError, match="not plain semver"):
        cut_changelog.cut_unreleased(SAMPLE, "5.6", "2026-06-10")


def test_rejects_existing_version():
    with pytest.raises(cut_changelog.ChangelogError, match="already exists"):
        cut_changelog.cut_unreleased(SAMPLE, "5.5.0", "2026-06-10")


def test_rejects_empty_unreleased_section():
    empty = SAMPLE.replace(
        "### Added\n\n- A shiny new feature.\n\n### Fixed\n\n- A bug.\n\n", "",
    )
    with pytest.raises(cut_changelog.ChangelogError, match="empty"):
        cut_changelog.cut_unreleased(empty, "5.6.0", "2026-06-10")


def test_rejects_missing_unreleased_heading():
    no_heading = SAMPLE.replace("## [Unreleased]", "## Not a release heading")
    with pytest.raises(cut_changelog.ChangelogError, match="No"):
        cut_changelog.cut_unreleased(no_heading, "5.6.0", "2026-06-10")


def test_cli_dry_run_leaves_file_untouched(tmp_path, capsys):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(SAMPLE, encoding="utf-8")

    rc = cut_changelog.main(["5.6.0", "--changelog", str(changelog), "--dry-run"])

    assert rc == 0
    assert changelog.read_text(encoding="utf-8") == SAMPLE
    out = capsys.readouterr().out
    assert "A shiny new feature." in out


def test_cli_rewrites_file(tmp_path):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(SAMPLE, encoding="utf-8")

    rc = cut_changelog.main(["5.6.0", "--changelog", str(changelog)])

    assert rc == 0
    assert "## [5.6.0] - " in changelog.read_text(encoding="utf-8")


def test_cli_error_exit_code(tmp_path, capsys):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(SAMPLE, encoding="utf-8")

    rc = cut_changelog.main(["bogus", "--changelog", str(changelog)])

    assert rc == 1
    assert "not plain semver" in capsys.readouterr().err


# --------------------------------------------------------------------------
# Major rollover: the archive move is part of cutting the release
# --------------------------------------------------------------------------

LIVE_6X = """# Changelog

**This file covers the current major (6.x) and the unreleased work in
progress.** Older releases are in
[`docs/CHANGELOG-archive.md`](docs/CHANGELOG-archive.md).

## [Unreleased]

### Added

- The big one.

## [6.1.0] - 2026-07-09

### Added

- Six-one stuff.

## [6.0.0] - 2026-07-08

### Changed

- Six-oh stuff.
"""

ARCHIVE_5X = """# Changelog archive

Intro prose.

---

## [5.9.0] - 2026-06-19

### Added

- Five-nine stuff.
"""


def test_minor_release_archives_nothing():
    """The common case must be a no-op — this runs on every release."""
    live, _ = cut_changelog.cut_unreleased(LIVE_6X, "6.2.0", "2026-08-01")
    new_live, new_archive, moved = cut_changelog.archive_superseded_majors(
        live, ARCHIVE_5X, "6.2.0",
    )

    assert moved == []
    assert new_live == live
    assert new_archive == ARCHIVE_5X


def test_major_bump_moves_the_superseded_major():
    live, _ = cut_changelog.cut_unreleased(LIVE_6X, "7.0.0", "2026-08-01")
    new_live, new_archive, moved = cut_changelog.archive_superseded_majors(
        live, ARCHIVE_5X, "7.0.0",
    )

    assert moved == ["## [6.1.0] - 2026-07-09", "## [6.0.0] - 2026-07-08"]
    # The live file keeps Unreleased + the new major, and nothing older.
    assert "## [Unreleased]" in new_live
    assert "## [7.0.0] - 2026-08-01" in new_live
    assert "## [6.1.0]" not in new_live
    assert "## [6.0.0]" not in new_live
    # The header sentence is retargeted so it cannot go stale.
    assert "(7.x)" in new_live
    assert "(6.x)" not in new_live
    # The archive keeps descending order: 6.x lands above the older 5.9.0.
    assert new_archive.index("## [6.1.0]") < new_archive.index("## [6.0.0]")
    assert new_archive.index("## [6.0.0]") < new_archive.index("## [5.9.0]")
    # ...below the intro rule, not above it.
    assert new_archive.index("---") < new_archive.index("## [6.1.0]")
    # Bodies survive the move.
    assert "Six-one stuff." in new_archive
    assert "Five-nine stuff." in new_archive


def test_major_bump_loses_no_content():
    live, _ = cut_changelog.cut_unreleased(LIVE_6X, "7.0.0", "2026-08-01")
    new_live, new_archive, _ = cut_changelog.archive_superseded_majors(
        live, ARCHIVE_5X, "7.0.0",
    )
    for section in ("## [6.1.0] - 2026-07-09", "## [6.0.0] - 2026-07-08"):
        assert (section in new_live) != (section in new_archive)


def test_archive_refuses_out_of_order_changelog():
    scrambled = LIVE_6X.replace(
        "## [6.0.0] - 2026-07-08", "## [8.0.0] - 2026-07-08",
    )
    live, _ = cut_changelog.cut_unreleased(scrambled, "7.0.0", "2026-08-01")
    with pytest.raises(cut_changelog.ChangelogError, match="descending"):
        cut_changelog.archive_superseded_majors(live, ARCHIVE_5X, "7.0.0")


def test_archive_requires_a_current_major_marker():
    live, _ = cut_changelog.cut_unreleased(
        LIVE_6X.replace("(6.x)", "the current major"), "7.0.0", "2026-08-01",
    )
    with pytest.raises(cut_changelog.ChangelogError, match="current-major"):
        cut_changelog.archive_superseded_majors(live, ARCHIVE_5X, "7.0.0")


def test_cli_writes_both_files_on_a_major_bump(tmp_path):
    changelog = tmp_path / "CHANGELOG.md"
    archive = tmp_path / "CHANGELOG-archive.md"
    changelog.write_text(LIVE_6X, encoding="utf-8")
    archive.write_text(ARCHIVE_5X, encoding="utf-8")

    rc = cut_changelog.main(
        ["7.0.0", "--changelog", str(changelog), "--archive", str(archive)],
    )

    assert rc == 0
    live_text = changelog.read_text(encoding="utf-8")
    archive_text = archive.read_text(encoding="utf-8")
    assert "## [7.0.0] - " in live_text
    assert "## [6.1.0]" not in live_text
    assert "## [6.1.0]" in archive_text


def test_cli_dry_run_writes_neither_file(tmp_path):
    changelog = tmp_path / "CHANGELOG.md"
    archive = tmp_path / "CHANGELOG-archive.md"
    changelog.write_text(LIVE_6X, encoding="utf-8")
    archive.write_text(ARCHIVE_5X, encoding="utf-8")

    rc = cut_changelog.main(
        [
            "7.0.0", "--changelog", str(changelog),
            "--archive", str(archive), "--dry-run",
        ],
    )

    assert rc == 0
    assert changelog.read_text(encoding="utf-8") == LIVE_6X
    assert archive.read_text(encoding="utf-8") == ARCHIVE_5X
