"""Guard against documentation drift on mechanically checkable claims.

The project docs are large and used to restate each other, which is how they
drifted away from the code (issue #448): ``AGENTS.md`` claimed 16 overlay
templates in one place and 30 in another, listed 11 test modules when there
were 63, and its quality-gate table omitted six gates CI actually fails on.
Every one of those was checkable by a test. Same spirit as
``tests/test_env_docs.py``: if a doc quotes a number or a list that the repo
already knows, assert it rather than trusting a human to re-read it.

Five families of check live here:

* **Quoted counts** — overlay template / selectable-style numbers against
  what is on disk, and README's explicit style list against the real one.
* **CI gates** — the documented gate table against the steps in
  ``ci.yml``, in *both* directions, because the interesting failure was a
  gate CI runs that no doc mentioned.
* **Route inventory** — every path in ``AUTHENTICATION.md`` §2.3 against
  the committed OpenAPI schema, so the auth source of truth cannot send an
  integrator to a 404.
* **Cross-document links** — the "one home per topic, link don't restate"
  rule (see the ownership table in ``AGENTS.md``) is only worth anything
  while the links resolve, anchors included.
* **Changelog split** — the live changelog holds the current major, the
  archive holds the rest, and no version appears in both.

Each check asserts that its own pattern still matched *something* before
asserting the value, so a reworded doc fails loudly instead of silently
turning the guard into a no-op.
"""

import json
import re
from pathlib import Path

import pytest
import yaml

from app.overlay.state_store import OverlayStateStore

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = REPO_ROOT / "overlay_templates"

# Docs checked for link integrity. Kept explicit rather than globbed so a new
# top-level document is a deliberate addition to the ownership table too.
DOC_FILES = (
    "README.md",
    "AGENTS.md",
    "CLAUDE.md",
    "CONTRIBUTING.md",
    "DEVELOPER_GUIDE.md",
    "FRONTEND_DEVELOPMENT.md",
    "AUTHENTICATION.md",
    "SECURITY.md",
    "CHANGELOG.md",
    "docs/CHANGELOG-archive.md",
)


@pytest.fixture(scope="module")
def selectable_styles(tmp_path_factory) -> list[str]:
    """The real selectable-style list, from a store with a throwaway data dir."""
    data_dir = tmp_path_factory.mktemp("overlay_state")
    store = OverlayStateStore(data_dir=str(data_dir), templates_dir=str(TEMPLATES_DIR))
    return list(store.get_available_styles_list())


def _read(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# Quoted counts
# --------------------------------------------------------------------------

# Matches both AGENTS.md phrasings: "(30 files, 27 selectable)" and
# "(30 files; 27 selectable styles via ...)".
_TEMPLATE_COUNT_RE = re.compile(r"(\d+) files[,;] (\d+) selectable")


def test_agents_template_counts_match_disk(selectable_styles):
    on_disk = sorted(p.name for p in TEMPLATES_DIR.glob("*.html"))
    claims = _TEMPLATE_COUNT_RE.findall(_read("AGENTS.md"))

    assert claims, (
        "AGENTS.md no longer states the overlay template counts in the "
        "'<N> files, <M> selectable' form this guard matches. Restore the "
        "wording or update _TEMPLATE_COUNT_RE in tests/test_docs_consistency.py "
        "— do not just delete the check."
    )
    expected = (str(len(on_disk)), str(len(selectable_styles)))
    wrong = [c for c in claims if c != expected]
    assert not wrong, (
        f"AGENTS.md claims {wrong} overlay templates/selectable styles, but "
        f"{TEMPLATES_DIR.name}/ holds {len(on_disk)} .html files of which "
        f"{len(selectable_styles)} are selectable. Update AGENTS.md."
    )


# "27 selectable styles", "27 Selectable Overlay Styles", "27 selectable templates".
_SELECTABLE_RE = re.compile(r"(\d+) [Ss]electable")


@pytest.mark.parametrize("doc", ["README.md", "AGENTS.md", "FRONTEND_DEVELOPMENT.md"])
def test_selectable_style_count_is_consistent(doc, selectable_styles):
    claims = set(_SELECTABLE_RE.findall(_read(doc)))
    assert claims, (
        f"{doc} no longer quotes a '<N> selectable' style count. If that is "
        "deliberate, drop it from this test's parametrize list."
    )
    assert claims == {str(len(selectable_styles))}, (
        f"{doc} claims {sorted(claims)} selectable overlay styles; "
        f"get_available_styles_list() returns {len(selectable_styles)}."
    )


def test_readme_style_list_matches_reality(selectable_styles):
    """README enumerates every selectable style by name — keep it honest."""
    readme = _read("README.md")
    match = re.search(r"Available styles: (.+?)\.\s", readme, re.DOTALL)
    assert match, (
        "README.md no longer has an 'Available styles: ...' sentence. Restore "
        "it or drop this check — a silently-unmatched regex guards nothing."
    )
    listed = sorted(re.findall(r"`([a-z0-9_]+)`", match.group(1)))
    assert listed == sorted(selectable_styles), (
        "README.md's style list is out of sync with "
        "get_available_styles_list().\n"
        f"  only in README: {sorted(set(listed) - set(selectable_styles))}\n"
        f"  only in code:   {sorted(set(selectable_styles) - set(listed))}"
    )


# --------------------------------------------------------------------------
# CI gates
# --------------------------------------------------------------------------

# Each documented gate → a command fragment that must appear in a ci.yml
# `run:` block. Keyed by the token AGENTS.md's gate table uses, so the two
# directions below can name the offender precisely.
#
# The value is a tuple because one documented gate can promise more than one
# CI step: the table says pip-audit covers "both lockfiles", so a lone
# "pip-audit -r" marker would stay satisfied after either scan was deleted.
# Every marker in a gate's tuple must be present for the gate to count as run.
CI_GATES = {
    "pytest": ("pytest tests/",),
    "ruff": ("ruff check",),
    "mypy": ("mypy",),
    "bandit": ("bandit -r",),
    "pip-audit": (
        "pip-audit -r requirements.lock",
        "pip-audit -r requirements-dev.lock",
    ),
    "lockfile-satisfies-`requirements.txt`": ("uv pip compile requirements.txt",),
    "vitest": ("npm run test:coverage",),
    "tsc": ("npm run typecheck",),
    "eslint": ("npm run lint",),
    "prettier --check": ("npm run format:check",),
    "npm audit": ("npm audit ",),
    "OpenAPI schema": ("git diff --exit-code -- frontend/schema/openapi.json",),
    "docker build": ("docker build",),
}

# ci.yml steps that cannot fail on a code problem: environment setup and
# artifact upload. Anything else that runs a command is a gate and must be
# documented.
NON_GATE_STEPS = {
    "Install dependencies",
    "Install Python dependencies",
    "Install frontend dependencies",
    "Install scanners",
    "Regenerate OpenAPI schema and TypeScript types",
}


def _ci_gate_steps() -> list[tuple[str, str]]:
    """Every ``(step name, run command)`` pair that can fail the build.

    Setup steps are excluded, and that exclusion is load-bearing rather than
    cosmetic: the dependency-install step pins ``ruff==…`` and ``mypy==…``, so
    searching every ``run:`` block would find "mypy" even with the
    ``Type-check with mypy`` step deleted.
    """
    workflow = yaml.safe_load(_read(".github/workflows/ci.yml"))
    steps = []
    for job in workflow["jobs"].values():
        for step in job.get("steps", []):
            if "run" in step and step.get("name") not in NON_GATE_STEPS:
                steps.append((step.get("name", "<unnamed>"), step["run"]))
    return steps


def _documented_gate_table() -> str:
    """The rows of AGENTS.md's quality-gate table, and nothing else.

    Scoped to the table on purpose: most gate names also appear in the
    tech-stack line and the example commands further down, so searching the
    whole file would let a gate be dropped from the table without failing.
    """
    lines = _read("AGENTS.md").splitlines()
    try:
        header = next(i for i, ln in enumerate(lines) if ln.startswith("| Surface | Gates |"))
    except StopIteration:  # pragma: no cover - guarded by the assert below
        return ""
    rows = []
    for line in lines[header + 1:]:
        if not line.startswith("|"):
            break
        rows.append(line)
    return "\n".join(rows)


def test_documented_gates_are_actually_run_by_ci():
    """No doc may promise a gate the pipeline does not enforce."""
    gate_commands = "\n".join(run for _, run in _ci_gate_steps())
    missing = sorted(
        f"{gate} ({marker!r})"
        for gate, markers in CI_GATES.items()
        for marker in markers
        if marker not in gate_commands
    )
    assert not missing, (
        f"AGENTS.md documents gates that ci.yml no longer runs: {missing}. "
        "Either restore the CI step or stop claiming the gate."
    )


def test_every_ci_gate_is_documented():
    """The direction that matters: a gate CI fails on must be in the docs.

    AGENTS.md's table previously omitted six of these, so contributors
    satisfied a subset and still got a red PR.
    """
    documented = _documented_gate_table()
    assert documented.count("\n") >= 3, (
        "Could not find AGENTS.md's '| Surface | Gates |' table (or it lost "
        "its rows). Restore it or update _documented_gate_table() — this "
        "guard is worthless if it searches an empty string."
    )
    undocumented = []
    for name, run in _ci_gate_steps():
        gate = next(
            (g for g, markers in CI_GATES.items() if any(m in run for m in markers)),
            None,
        )
        if gate is None:
            undocumented.append(name)
        elif gate not in documented:
            undocumented.append(f"{name} (gate {gate!r} missing from the table)")
    assert not undocumented, (
        "ci.yml has failing steps that AGENTS.md's quality-gate table does "
        f"not cover: {undocumented}. Add them to the table (and to CI_GATES "
        "here), or add a genuinely-non-gating step to NON_GATE_STEPS."
    )


# --------------------------------------------------------------------------
# Route inventory
# --------------------------------------------------------------------------

# Paths the committed OpenAPI schema legitimately does not carry.
# WebSockets have no OpenAPI representation at all.
ROUTES_NOT_IN_SCHEMA = {"/ws"}


def _normalise_path(path: str) -> str:
    """Collapse path parameters so ``/matches/{id}`` matches ``{match_id}``.

    The docs use short parameter names for readability. Comparing structure
    rather than spelling still catches the error this guard exists for — a
    documented route that simply is not registered.
    """
    return re.sub(r"\{[^}]*\}", "{}", path)


def test_documented_api_routes_exist():
    """Every ``/api/v1`` path in AUTHENTICATION.md §2.3 must be registered.

    A route inventory that invents a path is worse than no inventory: it
    sends integrators to a 404 while claiming to be the source of truth.
    The committed OpenAPI schema is the reference because CI already fails
    when it drifts from the app.
    """
    spec = json.loads(_read("frontend/schema/openapi.json"))
    registered = {_normalise_path(p) for p in spec["paths"]}

    text = _read("AUTHENTICATION.md")
    section = text[text.index("### 2.3"):text.index("### 2.4")]
    documented = []
    for line in section.splitlines():
        if not line.startswith("| `"):
            continue
        cells = [c.strip() for c in line.split("|")]
        documented.extend(re.findall(r"`(/[^`]*)`", cells[2]))

    assert len(documented) > 20, (
        "Could not parse the route rows out of AUTHENTICATION.md §2.3 "
        f"(found {len(documented)}). Update this guard rather than letting "
        "it check nothing."
    )
    missing = sorted(
        p for p in set(documented)
        if p not in ROUTES_NOT_IN_SCHEMA
        and _normalise_path("/api/v1" + p) not in registered
    )
    assert not missing, (
        f"AUTHENTICATION.md §2.3 documents unregistered routes: {missing}. "
        "Fix the path (check the decorator in app/api/routes/), or add it to "
        "ROUTES_NOT_IN_SCHEMA if it genuinely has no OpenAPI entry."
    )


# --------------------------------------------------------------------------
# Cross-document links
# --------------------------------------------------------------------------

_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
_HEADING_RE = re.compile(r"(?m)^#{1,6}\s+(.+?)\s*$")


def _slugify(heading: str) -> str:
    """GitHub's heading-anchor slug: strip punctuation, spaces → hyphens."""
    slug = heading.strip().lower()
    slug = re.sub(r"[^\w\s-]", "", slug)
    return slug.replace(" ", "-")


def _anchors(text: str) -> set[str]:
    return {_slugify(h) for h in _HEADING_RE.findall(text)}


def test_relative_doc_links_resolve():
    """Every relative link between docs points at a real file and anchor.

    The de-duplication in #448 replaced restated prose with cross-links, so a
    dangling link now loses information rather than merely annoying a reader.
    """
    broken: list[str] = []
    for doc in DOC_FILES:
        path = REPO_ROOT / doc
        text = path.read_text(encoding="utf-8")
        for target in _LINK_RE.findall(text):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            file_part, _, anchor = target.partition("#")
            if not file_part:
                # Same-document anchor.
                if anchor and anchor not in _anchors(text):
                    broken.append(f"{doc} → #{anchor} (no such heading)")
                continue
            resolved = (path.parent / file_part).resolve()
            if not resolved.exists():
                broken.append(f"{doc} → {target} (missing {file_part})")
                continue
            if anchor and resolved.suffix == ".md":
                target_text = resolved.read_text(encoding="utf-8")
                if anchor not in _anchors(target_text):
                    broken.append(f"{doc} → {target} (no such heading)")
    assert not broken, "Broken relative documentation links:\n  " + "\n  ".join(broken)


# --------------------------------------------------------------------------
# Changelog archive split
# --------------------------------------------------------------------------

_VERSION_HEADING_RE = re.compile(r"(?m)^## \[(\d+\.\d+\.\d+)\]")


def _parsed(version: str) -> tuple[int, ...]:
    return tuple(int(p) for p in version.split("."))


def test_changelog_archive_split_is_clean():
    """The live changelog keeps the current major; the archive keeps the rest.

    A 288 KB changelog that every PR must append to was the other half of
    #448. Splitting it only helps while the split stays clean, so: no version
    in both files, and everything archived is older than everything live.
    """
    live = _read("CHANGELOG.md")
    archive = _read("docs/CHANGELOG-archive.md")

    live_versions = _VERSION_HEADING_RE.findall(live)
    archive_versions = _VERSION_HEADING_RE.findall(archive)
    assert live_versions, "CHANGELOG.md lists no released versions."
    assert archive_versions, "docs/CHANGELOG-archive.md lists no released versions."

    duplicated = sorted(set(live_versions) & set(archive_versions))
    assert not duplicated, (
        f"Versions appear in both CHANGELOG.md and the archive: {duplicated}. "
        "Archiving moves entries; it never copies them."
    )

    oldest_live = min(_parsed(v) for v in live_versions)
    newest_archived = max(_parsed(v) for v in archive_versions)
    assert newest_archived < oldest_live, (
        f"The archive's newest entry ({newest_archived}) is not older than the "
        f"live changelog's oldest ({oldest_live}) — the split interleaves, so "
        "the history reads out of order."
    )

    assert "docs/CHANGELOG-archive.md" in live, (
        "CHANGELOG.md must link to docs/CHANGELOG-archive.md, or the archived "
        "history is unreachable from where readers start."
    )
    # Line-anchored: the archive's header prose mentions `## [Unreleased]`
    # inline to explain where entries actually go.
    assert not re.search(r"(?m)^## \[Unreleased\]", archive), (
        "The archive must not carry an [Unreleased] section — entries are only "
        "ever written into the live CHANGELOG.md."
    )
