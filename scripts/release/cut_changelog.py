"""Cut the ``## [Unreleased]`` section of CHANGELOG.md into a release.

Used by ``.github/workflows/release.yml``; runnable locally too:

    python scripts/release/cut_changelog.py 5.6.0 [--dry-run]

Behaviour:

* validates that *version* is plain semver (``X.Y.Z``);
* requires a non-empty ``## [Unreleased]`` section (a release with no
  notes is almost certainly a mistake);
* renames that heading to ``## [X.Y.Z] - <today, UTC>`` and inserts a
  fresh empty ``## [Unreleased]`` above it;
* prints the released section's body to stdout so the workflow can use
  it as the GitHub release notes.

The transformation is a pure function (:func:`cut_unreleased`) so the
test suite can exercise it without touching the real file.
"""

from __future__ import annotations

import argparse
import datetime
import re
import sys
from pathlib import Path

SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
UNRELEASED_HEADING = "## [Unreleased]"


class ChangelogError(ValueError):
    """Raised when the changelog cannot be cut as requested."""


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="Release version, e.g. 5.6.0")
    parser.add_argument(
        "--changelog",
        default="CHANGELOG.md",
        help="Path to the changelog file (default: CHANGELOG.md)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the release notes but do not rewrite the changelog.",
    )
    args = parser.parse_args(argv)

    path = Path(args.changelog)
    text = path.read_text(encoding="utf-8")
    today = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d")
    try:
        new_text, notes = cut_unreleased(text, args.version, today)
    except ChangelogError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if not args.dry_run:
        path.write_text(new_text, encoding="utf-8")
    sys.stdout.write(notes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
