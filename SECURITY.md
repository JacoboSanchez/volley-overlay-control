# Security Policy

## Supported versions

Security fixes target the latest tagged release on `main` and the
`dev` branch. Earlier releases are not patched — operators running an
older build are expected to upgrade to receive fixes.

## Reporting a vulnerability

If you believe you have found a security issue in
`volley-overlay-control`, please **do not** open a public GitHub issue
or pull request describing the vulnerability. Instead:

1. Use GitHub's [private vulnerability reporting](https://github.com/JacoboSanchez/volley-overlay-control/security/advisories/new)
   to file a confidential advisory.
2. Or, if the GitHub flow is not available to you, open a **public**
   GitHub issue with the single sentence "I have a security issue to
   report; please send me a contact channel" — a maintainer will
   reach out off-band.

When you report, please include:

- The version (commit SHA or release tag) you're running.
- Steps to reproduce, including any required configuration.
- The impact you observed and what you think the worst-case impact
  could be.
- Optional: a suggested mitigation or patch.

We aim to acknowledge reports within five business days and to ship a
fix or coordinated disclosure within 90 days. Reports that turn out to
be configuration questions or low-impact hardening suggestions are
welcome too — we'll just route them to a regular issue / PR with your
permission.

## Scope

In-scope:

- The FastAPI backend (`app/`).
- The React control UI (`frontend/`).
- The bundled overlay templates (`overlay_templates/`,
  `overlay_static/`).
- The Docker image and `docker-compose.yml`.
- Any documented integration surface (REST, WebSocket, webhooks).

Out of scope:

- Vulnerabilities that require an attacker who already has shell
  access to the host (the application runs as a non-root user inside
  the container; container-escape findings should go to the upstream
  base images: `python:3.13-slim`, `node:25-alpine`).
- Issues that depend on a misconfiguration explicitly called out as
  insecure in [`AUTHENTICATION.md`](AUTHENTICATION.md) — e.g.
  `OVERLAY_SERVER_TOKEN_DISABLED=true` on a public deployment, or
  `MATCH_REPORT_PUBLIC=true` with a guessable `match_id` (the IDs are
  hash-prefixed and intentionally hard to guess, but the model is
  capability-URL).
- Vulnerabilities in third-party services this app integrates with
  (OBS itself, the operator's reverse proxy).

## Hardening reference

The auth ladder, the credential-transport patterns, the
defence-in-depth middlewares, and the hash-at-rest options are
documented in [`AUTHENTICATION.md`](AUTHENTICATION.md). New operators
should at least:

1. Claim the first admin on first start (the bootstrap token is logged
   at startup / visible in `docker logs`), then create user accounts —
   every `/api/v1/*` scoreboard route is cookie + role gated, so the API
   is not open to the network out of the box.
2. Leave `REGISTRATION_OPEN` off (admins create users) unless you want
   open self-registration, and let `SESSION_SECRET` auto-mint (or set it
   explicitly) so sessions and report share-URLs are signed.
3. Set `OVERLAY_SERVER_TOKEN` (or let the bootstrap auto-generate it)
   so overlay-server mutation endpoints reject anonymous writes; gate
   `GET /metrics` with `METRICS_REQUIRE_ADMIN=true` if you don't want it
   exposed.
4. Configure `TRUSTED_HOSTS` to the public hostname(s) the app serves
   from when running behind a reverse proxy.
5. If serving the React UI from a different origin, set
   `CORS_ALLOWED_ORIGINS` explicitly — wildcards are rejected.

## CI scanning

Every PR runs three security scanners as part of the CI matrix
(`.github/workflows/ci.yml`, job `security-scan`):

- **Bandit** — static analysis of `app/` at MEDIUM+ severity.
- **pip-audit** — CVE scan of both `requirements.lock` and
  `requirements-dev.lock`.
- **npm audit** — CVE scan of `frontend/` runtime dependencies at
  HIGH+ severity (dev tooling is omitted to keep the signal-to-noise
  ratio high).

A PR cannot merge with red scanners; suppressing a finding requires
either a documented `# nosec` comment with a rationale, or an
explicit advisory ignore in the corresponding tool's config.
