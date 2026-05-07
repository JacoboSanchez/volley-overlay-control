<!--
  Thanks for contributing! Please make sure your PR follows the checklist
  in CONTRIBUTING.md. Delete sections that don't apply.
-->

## Summary

<!-- One or two sentences. What does this change do, and why? -->

## Changes

<!-- Bullet the user-visible / behavioural changes. Skip pure internal
     refactors here — describe them in "Implementation notes" instead. -->

-

## Implementation notes

<!-- Optional. Why this approach? What did you consider and reject?
     Anything reviewers should focus on? -->

## Test plan

- [ ] `ruff check .`
- [ ] `mypy`
- [ ] `pytest tests/ --cov=app --cov-fail-under=70`
- [ ] `cd frontend && npm run lint`
- [ ] `cd frontend && npm run typecheck`
- [ ] `cd frontend && npm run test:coverage`
- [ ] Manual smoke test (describe what you exercised)

## Checklist

- [ ] Added a `CHANGELOG.md` entry under `## [Unreleased]` (or
      explicitly justified the omission for an internal-only change)
- [ ] Regenerated screenshots if an operator-facing surface changed
      (`bash scripts/screenshots/run.sh`)
- [ ] Updated relevant docs (`README.md`, `AGENTS.md`,
      `FRONTEND_DEVELOPMENT.md`, …) when behaviour changed
- [ ] No secrets, credentials, or `.env` files committed
