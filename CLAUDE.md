# CLAUDE.md

Project context for Claude Code lives in [`AGENTS.md`](./AGENTS.md). Read it
before making changes — it covers the architecture (FastAPI backend, React
control UI, overlay serving engine), the test/lint expectations (pytest +
ruff + mypy on the backend, vitest + tsc on the frontend), the release
flow (CHANGELOG entry on every user-visible change, screenshot regeneration
when operator-facing surfaces change), and conventions specific to this
repo (per-OID audit log, optimistic state in `useGameState`, WS broadcast
ordering, etc.).

When `AGENTS.md` and this file disagree, `AGENTS.md` is the source of truth.
