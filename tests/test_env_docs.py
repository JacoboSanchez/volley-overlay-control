"""Guard against env-var documentation drift.

Every environment variable the backend reads must be documented for
operators in ``README.md`` or ``.env.example`` (or be explicitly
allowlisted below as internal). This keeps the docs from silently
drifting as new tunables are added.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Variables intentionally undocumented: test-only knobs, values managed by
# the runtime itself, or vars surfaced through other docs.
ALLOWLIST = {
    # Auto-generated/persisted by security bootstrap; documented via the
    # OVERLAY_SERVER_TOKEN README entry rather than their own rows.
    "OVERLAY_SERVER_TOKEN_FILE",
    # Set by docker-entrypoint.sh, not operator-facing app config.
    "PUID",
    "PGID",
}

_READ_PATTERN = re.compile(
    r"(?:get_env_var|get_bool_env|environ\.get|getenv|environ\[)"
    r"\(?\s*['\"]([A-Z][A-Z0-9_]+)['\"]"
)


def _env_vars_read_by_app() -> set[str]:
    names: set[str] = set()
    sources = list((REPO_ROOT / "app").rglob("*.py"))
    sources.append(REPO_ROOT / "main.py")
    for path in sources:
        names.update(_READ_PATTERN.findall(path.read_text(encoding="utf-8")))
    return names


def test_every_env_var_is_documented():
    documented = (
        (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        + (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    )
    undocumented = {
        name
        for name in _env_vars_read_by_app()
        if name not in ALLOWLIST and name not in documented
    }
    assert not undocumented, (
        "Environment variables read by the backend but missing from "
        f"README.md / .env.example: {sorted(undocumented)}. Document them "
        "or add them to the allowlist in tests/test_env_docs.py."
    )
