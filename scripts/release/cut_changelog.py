"""Cut the ``## [Unreleased]`` section of CHANGELOG.md into a release.

Used by ``.github/workflows/release.yml``; runnable locally too:

    python scripts/release/cut_changelog.py 5.6.0 [--dry-run]

Behaviour:

* validates that *version* is plain semver (``X.Y.Z``);
* requires a non-empty ``## [Unreleased]`` section (a release with no
  notes is almost certainly a mistake);
* renames that heading to ``## [X.Y.Z] - <today, UTC>`` and inserts a
  fresh empty ``## [Unreleased]`` above it;
* **on a major bump, moves the superseded major(s) into
  ``docs/CHANGELOG-archive.md``** in the same commit, and retargets the
  live file's "current major (N.x)" sentence;
* prints the released section's body to stdout so the workflow can use
  it as the GitHub release notes.

``CHANGELOG.md`` is held to a single major by
``tests/test_docs_consistency.py`` — every contributor and every agent
reads and appends to it, so it is kept short deliberately. Archiving is
automatic here rather than a follow-up chore precisely because a manual
step would leave ``main`` red between the release commit and the archive
commit, and would eventually be forgotten.

Both transformations are pure functions (:func:`cut_unreleased`,
:func:`archive_superseded_majors`) so the test suite can exercise them
without touching the real files.
"""

from __future__ import annotations

import argparse
import datetime
import re
import sys
from pathlib import Path

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
UNRELEASED_HEADING = "## [Unreleased]"
VERSION_HEADING_RE = re.compile(r"^## \[(\d+)\.\d+\.\d+\]")
CURRENT_MAJOR_RE = re.compile(r"\(\d+\.x\)")
# The archive's intro ends with a horizontal rule; moved sections are
# inserted directly below it so the file stays newest-first.
ARCHIVE_RULE = "\n---\n"


class ChangelogError(ValueError):
    """Raised when the changelog cannot be cut as requested."""


def _parse_version(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def cut_unreleased(text: str, version: str, today: str) -> tuple[str, str]:
    """Return ``(new_changelog_text, release_notes)``.

    *today* is an ISO ``YYYY-MM-DD`` date string (passed in rather than
    computed so the function stays pure and testable).
    """
    if not SEMVER_RE.match(version):
        raise ChangelogError(
            f"Version {version!r} is not plain semver (expected X.Y.Z)."
        )
    if f"## [{version}]" in text:
        raise ChangelogError(f"Version {version} already exists in the changelog.")

    lines = text.splitlines(keepends=True)
    try:
        start = next(
            i for i, line in enumerate(lines)
            if line.rstrip() == UNRELEASED_HEADING
        )
    except StopIteration:
        raise ChangelogError(
            f"No {UNRELEASED_HEADING!r} heading found."
        ) from None

    end = next(
        (
            i for i in range(start + 1, len(lines))
            if lines[i].startswith("## [")
        ),
        len(lines),
    )

    body = "".join(lines[start + 1:end])
    if not body.strip():
        raise ChangelogError(
            "The [Unreleased] section is empty — nothing to release."
        )

    released_heading = f"## [{version}] - {today}\n"
    new_lines = [
        *lines[:start],
        UNRELEASED_HEADING + "\n",
        "\n",
        released_heading,
        *lines[start + 1:],
    ]
    return "".join(new_lines), body.strip() + "\n"


def archive_superseded_majors(
    live: str, archive: str, version: str,
) -> tuple[str, str, list[str]]:
    """Move releases older than *version*'s major out of *live*.

    Returns ``(new_live, new_archive, moved_versions)``. When *version* is
    not a major bump nothing moves and both texts come back unchanged, so
    this is safe to call on every release.
    """
    major = int(version.split(".")[0])
    lines = live.splitlines(keepends=True)

    cut_at = None
    moved: list[str] = []
    for i, line in enumerate(lines):
        match = VERSION_HEADING_RE.match(line)
        if match is None:
            continue
        if int(match.group(1)) < major:
            if cut_at is None:
                cut_at = i
            moved.append(line.strip())
        elif cut_at is not None:
            # A newer major below an older one means the file is already
            # out of order; refuse rather than silently interleave. Checked
            # before the version-ordering guard below because a scrambled
            # file is the more useful thing to report.
            raise ChangelogError(
                f"{line.strip()} appears below an older major — CHANGELOG.md "
                "is not in descending version order, so archiving would "
                "scramble it. Fix the ordering by hand."
            )

    # A version older than what is already released archives nothing (there is
    # no *older* major to move), so without this it would sail through the
    # early return below and the workflow would commit a changelog spanning two
    # majors — failing the single-live-major guard on main right after tagging.
    requested = _parse_version(version)
    newest = max(
        (
            _parse_version(m.group(1))
            for line in lines
            if (m := re.match(r"^## \[(\d+\.\d+\.\d+)\]", line))
            and _parse_version(m.group(1)) != requested
        ),
        default=None,
    )
    if newest is not None and requested < newest:
        raise ChangelogError(
            f"Version {version} is older than the newest release already in "
            f"the changelog ({'.'.join(str(p) for p in newest)}). Releases only "
            "move forward; check the version passed to the workflow."
        )

    if cut_at is None:
        return live, archive, []

    new_live = "".join(lines[:cut_at]).rstrip("\n") + "\n"
    superseded = "".join(lines[cut_at:]).rstrip("\n") + "\n"

    new_live, subs = CURRENT_MAJOR_RE.subn(f"({major}.x)", new_live, count=1)
    if not subs:
        raise ChangelogError(
            "CHANGELOG.md has no '(N.x)' current-major marker to retarget. "
            "Restore the sentence at the top of the file."
        )

    try:
        insert_at = archive.index(ARCHIVE_RULE) + len(ARCHIVE_RULE)
    except ValueError:
        raise ChangelogError(
            "The archive has no '---' rule under its intro to insert below."
        ) from None
    new_archive = (
        archive[:insert_at].rstrip("\n")
        + "\n\n"
        + superseded.rstrip("\n")
        + "\n\n"
        + archive[insert_at:].lstrip("\n")
    )
    return new_live, new_archive, moved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="Release version, e.g. 5.6.0")
    parser.add_argument(
        "--changelog",
        default="CHANGELOG.md",
        help="Path to the changelog file (default: CHANGELOG.md)",
    )
    parser.add_argument(
        "--archive",
        default="docs/CHANGELOG-archive.md",
        help="Path to the changelog archive (default: docs/CHANGELOG-archive.md)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the release notes but do not rewrite the changelog.",
    )
    args = parser.parse_args(argv)

    path = Path(args.changelog)
    archive_path = Path(args.archive)
    text = path.read_text(encoding="utf-8")
    today = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d")
    try:
        new_text, notes = cut_unreleased(text, args.version, today)
        # Read the archive only when it exists: a caller pointing --changelog
        # at a scratch file (tests, a rehearsal) should not have to supply an
        # archive when nothing is being archived.
        archive_text = (
            archive_path.read_text(encoding="utf-8")
            if archive_path.exists() else ""
        )
        new_text, new_archive, moved = archive_superseded_majors(
            new_text, archive_text, args.version,
        )
    except ChangelogError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if moved:
        print(
            f"note: major bump — archived {len(moved)} release(s) into "
            f"{archive_path}: {', '.join(moved)}",
            file=sys.stderr,
        )
    if not args.dry_run:
        path.write_text(new_text, encoding="utf-8")
        if moved:
            archive_path.write_text(new_archive, encoding="utf-8")
    sys.stdout.write(notes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
