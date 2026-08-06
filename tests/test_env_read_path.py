"""Guard the single env read path.

``EnvVarsManager`` layers the optional ``REMOTE_CONFIG_URL`` payload over
``os.environ``, so a module that reads ``os.environ`` directly is invisible
to remote-config deployments — its setting silently keeps the local value.
A short list of readers does that deliberately (see the allowlist below);
this test keeps that list exhaustive rather than aspirational, the way
``test_env_docs.py`` keeps the env-var documentation honest.

If this fails, the fix is almost always to switch the new reader to
``EnvVarsManager.get_env_var`` / ``get_bool_env`` / ``get_int_env`` /
``get_float_env`` / ``get_enum_env`` — not to extend the allowlist.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# path -> why this module is allowed to bypass EnvVarsManager. Every entry
# is a value needed *before or in order to reach* the remote config, so it
# cannot come from it.
ALLOWED_DIRECT_READERS = {
    "app/env_vars_manager.py": (
        "reads REMOTE_CONFIG_URL / REMOTE_CONFIG_ALLOW_PRIVATE_IPS — what "
        "decides how the remote config is fetched must not come from it"
    ),
    "app/db/engine.py": "DATABASE_URL is resolved at import, before any fetch",
    "app/security_bootstrap.py": (
        "runs before any router is registered, to mint/load SESSION_SECRET "
        "and MATCH_REPORT_SIGNING_SECRET"
    ),
    "app/auth/bootstrap.py": "ADMIN_BOOTSTRAP_TOKEN is claimed during startup",
    "app/logging_utils.py": "LOG_REDACT gates the redaction used by the fetch's own logs",
    "app/bootstrap.py": (
        "TRUSTED_HOSTS / CORS_ALLOWED_ORIGINS are applied while the app is "
        "being constructed"
    ),
    "main.py": "loads the dotenv file that everything else then reads",
}

_ENV_ACCESS = re.compile(r"\bos\.(?:environ|getenv)\b")


def _sources() -> list[Path]:
    paths = sorted((REPO_ROOT / "app").rglob("*.py"))
    paths.append(REPO_ROOT / "main.py")
    return paths


def test_direct_environ_readers_stay_on_the_allowlist():
    offenders = {}
    for path in _sources():
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel in ALLOWED_DIRECT_READERS:
            continue
        source = path.read_text(encoding="utf-8")
        hits = [
            f"{rel}:{i}"
            for i, line in enumerate(source.splitlines(), start=1)
            if _ENV_ACCESS.search(line)
        ]
        if hits:
            offenders[rel] = hits
    assert not offenders, (
        "These modules read os.environ directly, so REMOTE_CONFIG_URL "
        f"deployments cannot configure them: {offenders}. Read through "
        "EnvVarsManager instead, or add the module to ALLOWED_DIRECT_READERS "
        "here (and to the list in AGENTS.md) with the reason it must bypass "
        "the remote config."
    )


def test_allowlist_has_no_stale_entries():
    """A module that stopped reading os.environ should leave the allowlist."""
    stale = []
    for rel in ALLOWED_DIRECT_READERS:
        source = (REPO_ROOT / rel).read_text(encoding="utf-8")
        if not _ENV_ACCESS.search(source):
            stale.append(rel)
    assert not stale, (
        f"ALLOWED_DIRECT_READERS lists modules that no longer read os.environ: "
        f"{stale}. Drop them so the list keeps meaning something."
    )


def test_agents_md_documents_the_same_exceptions():
    """The prose in AGENTS.md and this allowlist must not drift apart."""
    agents = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    section = agents.split("**One read path, validated at the read.**", 1)
    assert len(section) == 2, "the read-path convention section moved or was renamed"
    prose = section[1].split("\n---", 1)[0]
    for name in (
        "DATABASE_URL",
        "SESSION_SECRET",
        "ADMIN_BOOTSTRAP_TOKEN",
        "TRUSTED_HOSTS",
        "CORS_ALLOWED_ORIGINS",
        "LOG_REDACT",
        "REMOTE_CONFIG_URL",
        "REMOTE_CONFIG_ALLOW_PRIVATE_IPS",
    ):
        assert name in prose, (
            f"{name} bypasses EnvVarsManager but AGENTS.md no longer lists it "
            "as an exception."
        )
