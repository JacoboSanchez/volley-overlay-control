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
ALLOWLIST: set[str] = set()

# Variables consumed by Docker Compose itself rather than the application.
COMPOSE_ONLY = {
    "DOCKER_LOG_MAX_FILE",
    "DOCKER_LOG_MAX_SIZE",
    "EXTERNAL_PORT",
}

# Also matches local ``_env_*("NAME", default)`` helper wrappers used in the
# constants, settings, logging, and middleware modules. The reverse guard
# below makes a newly-documented variable fail as stale if a new helper naming
# pattern is not represented here.
_READ_PATTERN = re.compile(
    r"(?:get_env_var|get_bool_env|environ\.get|getenv|environ\[|_env(?:_[a-z]+)*)"
    r"\(?\s*\(?\s*['\"]([A-Z][A-Z0-9_]+)['\"]"
)
_EXAMPLE_DECLARATION_PATTERN = re.compile(
    r"(?m)^\s*#?\s*([A-Z][A-Z0-9_]+)\s*="
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
        if name not in ALLOWLIST
        and not re.search(r"\b" + re.escape(name) + r"\b", documented)
    }
    assert not undocumented, (
        "Environment variables read by the backend but missing from "
        f"README.md / .env.example: {sorted(undocumented)}. Document them "
        "or add them to the allowlist in tests/test_env_docs.py."
    )


def test_every_example_env_var_is_used_or_compose_only():
    example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    documented = set(_EXAMPLE_DECLARATION_PATTERN.findall(example))
    stale = documented - _env_vars_read_by_app() - COMPOSE_ONLY
    assert not stale, (
        "Environment variables declared in .env.example but not read by the "
        f"backend or Compose: {sorted(stale)}. Remove stale knobs or teach "
        "the read-pattern guard about the helper that consumes them."
    )
