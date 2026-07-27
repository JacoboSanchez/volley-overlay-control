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
* **CI gates** — ``AGENTS.md``'s gate table against the steps in
  ``ci.yml``, in *both* directions, because the interesting failure was a
  gate CI runs that no doc mentioned.
* **Route inventory** — ``AUTHENTICATION.md`` §2 against the committed
  OpenAPI schema, comparing ``(method, path)`` pairs in both directions,
  so the auth source of truth can neither send an integrator to a 404/405
  nor quietly omit an access path.
* **Cross-document links** — the "one home per topic, link don't restate"
  rule (see the ownership table in ``AGENTS.md``) is only worth anything
  while the links resolve, anchors included.
* **Changelog split** — the live changelog holds exactly one major, the
  archive holds the rest, and no version appears in both.

Two properties every check here must keep, both learned the hard way when
review found this file asserting less than it advertised:

1. **Assert the pattern matched something before asserting the value.** A
   reworded doc must fail loudly rather than silently reduce a check to
   comparing two empty sets.
2. **Compare whole sets in both directions, and derive the input rather
   than hand-listing it.** Every hole found so far was a narrowing: one
   direction instead of two, paths instead of ``(method, path)``, a prefix
   filter that excluded the routes it should have covered, an inclusion
   list that stopped matching reality.
"""

import json
import os
import re
import subprocess
from pathlib import Path

import pytest
import yaml

from app.overlay.state_store import OverlayStateStore

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = REPO_ROOT / "overlay_templates"

# Markdown excluded from the link check. Keep this list tiny and justified:
# a hand-maintained *inclusion* list was the previous shape here, and it had
# silently stopped covering five tracked files — the same "the guard checks
# less than it claims" failure this module keeps finding elsewhere.
UNCHECKED_MARKDOWN: set[str] = set()


def _markdown_files() -> list[str]:
    """Every tracked markdown file, so a new doc is covered automatically."""
    listed = subprocess.run(
        ["git", "ls-files", "*.md"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    ).stdout.split()
    return [f for f in listed if f not in UNCHECKED_MARKDOWN]


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
    # The table promises "OpenAPI schema + generated types"; the drift step
    # diffs both paths, so both must stay in the command.
    "OpenAPI schema": (
        "git diff --exit-code -- frontend/schema/openapi.json",
        "frontend/src/api/schema.d.ts",
    ),
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


def _table_gate_entries() -> list[str]:
    """The individual gates listed in AGENTS.md's table, split on the bullet."""
    entries = []
    for row in _documented_gate_table().splitlines():
        cells = row.split("|")
        if len(cells) < 3:
            continue
        cell = cells[2].strip()
        if not cell or set(cell) <= set("-: "):  # markdown separator row
            continue
        entries.extend(e.strip() for e in cell.split("·") if e.strip())
    return entries


def test_every_table_gate_is_mapped():
    """A gate added to the table must be wired to a real CI command.

    Without this, the docs→CI direction only ever checks the hard-coded
    ``CI_GATES``: someone could add a row to the table promising a gate that
    neither CI runs nor this file knows about, and nothing would notice.
    """
    entries = _table_gate_entries()
    assert len(entries) >= 10, (
        "Could not split AGENTS.md's gate table into individual gates "
        f"(found {entries}). The rows are '·'-separated; update this helper "
        "if that changed."
    )
    unmapped = [e for e in entries if not any(g in e for g in CI_GATES)]
    assert not unmapped, (
        f"AGENTS.md's gate table lists gates with no CI_GATES mapping: "
        f"{unmapped}. Add each to CI_GATES with the command that enforces it "
        "(and make sure ci.yml actually runs it), or stop promising it."
    )


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
        # Every gate the step runs, not just the first match: a single step
        # invoking both `ruff check .` and `mypy` would otherwise be recorded
        # as "ruff" alone, and dropping mypy from the table would go unnoticed
        # while CI still enforced it.
        gates = [g for g, markers in CI_GATES.items() if any(m in run for m in markers)]
        if not gates:
            undocumented.append(name)
        undocumented.extend(
            f"{name} (gate {g!r} missing from the table)"
            for g in gates
            if g not in documented
        )
    assert not undocumented, (
        "ci.yml has failing steps that AGENTS.md's quality-gate table does "
        f"not cover: {undocumented}. Add them to the table (and to CI_GATES "
        "here), or add a genuinely-non-gating step to NON_GATE_STEPS."
    )


# --------------------------------------------------------------------------
# Route inventory
# --------------------------------------------------------------------------

# Paths the committed OpenAPI schema legitimately does not carry: WebSockets
# have no OpenAPI representation, and the static mounts are Starlette mounts
# rather than routes.
#
# An exemption is a hole in both directions at once — the forward check skips
# it and the inverse check never sees it — so the WebSocket entries are
# verified against the real routers by test_exempt_websocket_routes_exist
# rather than trusted. The static mounts are checked there too.
WEBSOCKET_EXEMPTIONS = {"/api/v1/ws", "/ws/{public_token}"}
MOUNT_EXEMPTIONS = {"/fonts/**", "/static/**", "/media/**", "/pwa/**"}
# Served by the SPA catch-all / a sub-application, so there is no route object
# to enumerate. Kept minimal.
UNVERIFIABLE_EXEMPTIONS = {"/favicon.ico", "/assets/**"}

OPERATIONS_NOT_IN_SCHEMA = (
    WEBSOCKET_EXEMPTIONS | MOUNT_EXEMPTIONS | UNVERIFIABLE_EXEMPTIONS
)

# Inventory rows that describe a family rather than one route.
WILDCARD_INVENTORY_PATHS = {"/**"}


def _normalise_path(path: str) -> str:
    """Collapse path parameters so ``/matches/{id}`` matches ``{match_id}``.

    The docs use short parameter names for readability. Comparing structure
    rather than spelling still catches the error this guard exists for — a
    documented route that simply is not registered.
    """
    return re.sub(r"\{[^}]*\}", "{}", path)


def _registered_operations() -> set[tuple[str, str]]:
    """Every ``(method, path)`` the committed schema exposes.

    Deliberately *not* filtered to ``/api/v1``: the report, spectator,
    metrics and health surfaces are registered routes with real auth
    postures, and scoping the check to the API prefix would let them drift
    while the guard stayed green.
    """
    spec = json.loads(_read("frontend/schema/openapi.json"))
    return {
        (method.lower(), path)
        for path, operations in spec["paths"].items()
        for method in operations
    }


def _inventoried_operations() -> set[tuple[str, str]]:
    """Every ``(method, path)`` AUTHENTICATION.md §2 lists.

    Each subsection declares its own ``Prefix `/api/v1/...` `` line and the
    rows are relative to it, so the prefix is applied per subsection. Methods
    come from the row's first column: comparing paths alone let a row claim
    ``GET`` on a POST-only route and pass.
    """
    text = _read("AUTHENTICATION.md")
    section = text[text.index("## 2. Route inventory"):text.index("## 3. Findings")]
    operations: set[tuple[str, str]] = set()
    for part in re.split(r"(?m)^### ", section)[1:]:
        prefix_match = re.search(r"Prefix `([^`]+)`", part)
        prefix = prefix_match.group(1).rstrip("/") if prefix_match else ""
        for line in part.splitlines():
            if not line.startswith("| `"):
                continue
            cells = [c.strip() for c in line.split("|")]
            if len(cells) < 3:
                continue
            methods = re.findall(r"`([A-Z]+)`", cells[1])
            paths = re.findall(r"`(/[^`]*)`", cells[2])
            operations.update(
                (method.lower(), prefix + path)
                for method in methods
                for path in paths
            )
    return operations


def test_documented_api_routes_exist():
    """Nothing in the inventory may claim a method/path that is not registered.

    A route inventory that invents an operation is worse than no inventory:
    it sends integrators to a 404 (or a 405) while claiming to be the source
    of truth. The committed OpenAPI schema is the reference because CI
    already fails when it drifts from the app.
    """
    registered = {(m, _normalise_path(p)) for m, p in _registered_operations()}
    documented = _inventoried_operations()

    assert len(documented) > 80, (
        "Could not parse the route rows out of AUTHENTICATION.md §2 "
        f"(found {len(documented)}). Update this guard rather than letting "
        "it check nothing."
    )
    missing = sorted(
        f"{m.upper()} {p}" for m, p in documented
        if p not in OPERATIONS_NOT_IN_SCHEMA
        and p not in WILDCARD_INVENTORY_PATHS
        and (m, _normalise_path(p)) not in registered
    )
    assert not missing, (
        f"AUTHENTICATION.md §2 documents operations that are not registered: "
        f"{missing}. Check the decorator in app/ — a row listing 'GET / POST' "
        "against a POST-only route is the usual cause. Add to "
        "OPERATIONS_NOT_IN_SCHEMA only if it genuinely has no OpenAPI entry."
    )


def test_exempt_websocket_routes_exist():
    """The exemptions must name routes that are actually registered.

    Exempting a path punches a hole in *both* directions: the forward check
    skips it, and the inverse check never sees it because WebSockets have no
    OpenAPI entry. So AUTHENTICATION.md could keep advertising a WebSocket
    that had been renamed away with the whole suite green. Enumerate them
    from the routers instead of assuming they are there.
    """
    from fastapi.templating import Jinja2Templates

    from app.api.routes import api_router
    from app.api.routes import websocket as websocket_routes
    from app.overlay import obs_broadcast_hub, overlay_state_store
    from app.overlay.routes import create_overlay_router

    def ws_paths(router, prefix: str = "") -> set[str]:
        return {
            prefix + r.path
            for r in router.routes
            if type(r).__name__ == "APIWebSocketRoute"
        }

    overlay_router = create_overlay_router(
        overlay_state_store,
        obs_broadcast_hub,
        Jinja2Templates(directory=str(TEMPLATES_DIR)),
    )
    registered = ws_paths(websocket_routes.router, api_router.prefix)
    registered |= ws_paths(overlay_router)

    missing = sorted(WEBSOCKET_EXEMPTIONS - registered)
    assert not missing, (
        f"WEBSOCKET_EXEMPTIONS names routes that are not registered: "
        f"{missing} (found {sorted(registered)}). Either the route was "
        "renamed — in which case AUTHENTICATION.md is advertising a dead "
        "path — or the exemption is stale and should be dropped."
    )
    unexempted = sorted(registered - WEBSOCKET_EXEMPTIONS)
    assert not unexempted, (
        f"WebSocket routes with no exemption entry: {unexempted}. They have "
        "no OpenAPI entry, so the inverse inventory check cannot see them; "
        "add them to WEBSOCKET_EXEMPTIONS *and* give them a row in "
        "AUTHENTICATION.md §2."
    )


def test_exempt_mounts_exist():
    """Same argument for the static mounts the inventory lists."""
    import tempfile

    from starlette.routing import Mount

    from app.bootstrap import create_app

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["DATABASE_URL"] = f"sqlite:///{tmp}/docs_guard.db"
        app = create_app()
        mounted = {r.path + "/**" for r in app.routes if isinstance(r, Mount)}

    missing = sorted(MOUNT_EXEMPTIONS - mounted)
    assert not missing, (
        f"MOUNT_EXEMPTIONS names mounts that do not exist: {missing} "
        f"(found {sorted(mounted)}). AUTHENTICATION.md §2.6 would be listing "
        "a static surface the app no longer serves."
    )


def test_api_route_inventory_is_complete():
    """...and the inverse: every registered operation must be inventoried.

    This is the direction that decays silently. ``AUTHENTICATION.md`` calls
    itself the per-route inventory, so a route added without a row leaves it
    quietly incomplete — which is exactly what happened: 36 routes were
    missing when this check was written, and five non-``/api/v1`` ones
    survived the first version because it only looked at the API prefix.
    """
    documented = {(m, _normalise_path(p)) for m, p in _inventoried_operations()}
    undocumented = sorted(
        f"{m.upper()} {p}" for m, p in _registered_operations()
        if (m, _normalise_path(p)) not in documented
    )
    assert not undocumented, (
        f"Operations registered but absent from AUTHENTICATION.md §2: "
        f"{undocumented}. Add a row under the matching subsection with its "
        "auth class (Y / A / B / —). The document is the per-route auth "
        "inventory; a route missing from it is an undocumented access path."
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
    docs = _markdown_files()
    assert len(docs) >= 10, (
        f"Only found {len(docs)} tracked markdown files — the git ls-files "
        "lookup is not seeing the docs, so this guard is checking nothing."
    )
    broken: list[str] = []
    for doc in docs:
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

    # The ordering check above is necessary but not sufficient: with 5.9.0
    # archived, adding 7.0.0 while 6.x is still live keeps `5.9.0 < 6.0.0`
    # true, so nothing would notice the archive step being skipped and the
    # file would resume growing without bound. Hold the live file to the one
    # major it claims to cover.
    live_majors = sorted({_parsed(v)[0] for v in live_versions})
    assert len(live_majors) == 1, (
        f"CHANGELOG.md spans majors {live_majors}, but it documents itself as "
        "covering the current major only. Archive the superseded major(s) into "
        "docs/CHANGELOG-archive.md — see the 'Archiving a superseded major' "
        "procedure in CONTRIBUTING.md — and update the header sentence."
    )

    # Ordering plus single-live-major still allows the current major to be
    # *split*: archiving 6.0.0 while live starts at 6.1.0 keeps
    # (6,0,0) < (6,1,0) true and leaves one live major. The invariant is that
    # the archive holds only *superseded* majors, so compare majors directly.
    straddling = sorted(
        {v for v in archive_versions if _parsed(v)[0] >= live_majors[0]}
    )
    assert not straddling, (
        f"Archived versions {straddling} are in the live major "
        f"({live_majors[0]}.x), so the current major is split across both "
        "files. The archive holds superseded majors only — move them back."
    )
    assert f"({live_majors[0]}.x)" in live, (
        f"CHANGELOG.md's header must name the major it covers as "
        f"'({live_majors[0]}.x)'; the released entries below it are all "
        f"{live_majors[0]}.x. Update the sentence at the top."
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
