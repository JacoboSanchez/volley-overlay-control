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
