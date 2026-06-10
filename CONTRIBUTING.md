# Contributing to Volley Overlay Control

Thanks for taking the time to contribute. This document is the short
version. The longer-form architecture, conventions, and pitfalls live in
[`AGENTS.md`](./AGENTS.md) and [`DEVELOPER_GUIDE.md`](./DEVELOPER_GUIDE.md);
**read those first** if you are new to the codebase.

---

## Quick start

```bash
# Backend (Python 3.11+)
python -m venv .venv && source .venv/bin/activate
pip install -U pip uv
uv pip install -r requirements.lock -r requirements-dev.lock
uv pip install ruff mypy

# Frontend (Node 20+)
cd frontend && npm ci
```

Run the app locally:

```bash
# Backend (auto-reload)
uvicorn main:app --reload --port 8080

# Frontend (Vite dev server, proxies API to :8080)
cd frontend && npm run dev
```

---

## Local development loop

Before pushing, run the same checks CI runs:

```bash
# Backend
ruff check .
mypy
pytest tests/ --cov=app --cov-report=term-missing --cov-fail-under=70

# Frontend
cd frontend
npm run lint
npm run typecheck
npm run test:coverage
```

Optional but recommended:

```bash
pre-commit install        # one-time
pre-commit run --all-files
```

---

## Branching

- `main` — protected; releases.
- `dev` — integration branch.
- Feature work goes on a topic branch off `dev`. Open the PR against
  `dev` unless you are landing a hotfix.

---

## Pull requests

Every PR must:

1. **Update [`CHANGELOG.md`](./CHANGELOG.md)** under the right
   `## [Unreleased]` subsection (`Added`, `Changed`, `Fixed`,
   `Removed`, `Deprecated`, `Security`, `Dependencies`). Pure internal
   refactors with no observable effect can skip this — when in doubt,
   add the entry.
2. **Pass CI** — backend (`ruff`, `mypy`, `pytest`, `bandit`,
   `pip-audit`) and frontend (`eslint`, `tsc`, `vitest`, `npm audit`).
3. **Regenerate screenshots** when an operator-facing surface
   changes — the React control UI, customization panel, `/manage`
   page, or any overlay template/static asset. See
   `scripts/screenshots/README.md` and
   `scripts/screenshots/run.sh`.
4. **Be small and focused.** Prefer a sequence of reviewable PRs over
   one mega-PR.

There is a PR template under
[`.github/pull_request_template.md`](./.github/pull_request_template.md)
that walks you through the checklist. Issue templates live in
[`.github/ISSUE_TEMPLATE/`](./.github/ISSUE_TEMPLATE).

---

## Releases

Releases are cut with the **Cut release** workflow
([`.github/workflows/release.yml`](./.github/workflows/release.yml)):

1. Make sure `## [Unreleased]` in `CHANGELOG.md` reflects everything
   that should ship (the workflow refuses to cut an empty section).
2. Run the workflow from the Actions tab with the plain semver version
   (e.g. `5.6.0`). Use the `dry_run` input first to preview the
   release notes without committing anything.
3. The workflow renames `[Unreleased]` to `[X.Y.Z] - <date>`, commits
   `Release vX.Y.Z` to `main`, pushes the `vX.Y.Z` tag, creates the
   GitHub release with the cut section as notes, and chains the
   Docker image build (`docker-publish.yml`) explicitly — a release
   created with `GITHUB_TOKEN` does not fire the `release: published`
   event on its own.

Because `main` is protected, the repository's branch-protection rules
must allow GitHub Actions to push (e.g. an "allow specified actors to
bypass" entry for the Actions app), or the workflow's push step will
be rejected. The changelog transform itself lives in
[`scripts/release/cut_changelog.py`](./scripts/release/cut_changelog.py)
and is unit-tested in `tests/test_release_script.py`, so it can also
be run locally for a manual release.

---

## Coding conventions

- **Backend:** see `pyproject.toml` for the active `ruff` rule set and
  `mypy` strictness. State mutations always go through
  `GameManager` → `Backend` → overlay backend. Never bypass the chain
  documented in `AGENTS.md`.
- **Frontend:** ESLint flat config in
  [`frontend/eslint.config.js`](./frontend/eslint.config.js). Prettier
  config in [`frontend/.prettierrc.json`](./frontend/.prettierrc.json).
  Run `npm run format` to auto-fix style; `npm run lint:fix` for
  auto-fixable lint errors.
- **No new emojis** in source files unless an existing module already
  uses them.
- **Comments:** explain *why*, not *what*. Prefer well-named
  identifiers over inline narration.

---

## Reporting security issues

**Do not** open a public issue for a vulnerability. Follow the
disclosure policy in [`SECURITY.md`](./SECURITY.md).

---

## License

By contributing you agree that your work is licensed under the
project's [LICENSE](./LICENSE).
