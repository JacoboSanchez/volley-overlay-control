# syntax=docker/dockerfile:1.7

# ---- Stage 1: Build the React frontend ----
FROM node:26-alpine AS frontend-build
WORKDIR /build

# Install dependencies first so they are cached independently of source.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build


# ---- Stage 2: Python runtime ----
# Only runtime artifacts land here — no Node, no frontend source, no dev deps.
FROM python:3.14-slim AS runtime
WORKDIR /app

# Apply Debian security updates before anything else lands on top. The
# ``python:3.14-slim`` tag is rebuilt on its own cadence, so between those
# rebuilds a published Debian fix sits unapplied in the base layer and the
# Trivy gate goes red on packages no application change can reach — that is
# how the util-linux cluster (CVE-2026-53613 / -53614 / -53615, fixed in
# 2.41.5-0+deb13u1) started failing every PR. The gate runs with
# ``ignore-unfixed``, so anything it reports has a fix waiting in the
# archive; upgrading here takes it, in the same spirit as dropping pip
# below rather than suppressing the finding.
#
# ``APT_REFRESH`` keeps that promise against a warm build cache. Every image
# workflow imports a persistent ``type=gha`` cache, and BuildKit keys a layer
# on its expanded command, so without a changing value this RUN would be
# replayed verbatim and keep serving whatever packages it installed the first
# time — exactly the stale-base problem it exists to fix, just moved into the
# cache. CI and the dev image pass the UTC date, so the upgrade re-runs once
# a day and hits the cache in between; the release workflow passes its run id
# so a published image always resolves packages from the current archive. A
# plain ``docker build`` keeps the default and stays fully cacheable.
ARG APT_REFRESH=static
RUN echo "apt security refresh: ${APT_REFRESH}" \
    && export DEBIAN_FRONTEND=noninteractive \
    && apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_SYSTEM_PYTHON=1 \
    UV_NO_CACHE=1

COPY --from=ghcr.io/astral-sh/uv:0.8.17 /uv /usr/local/bin/uv

COPY requirements.lock ./
# Drop pip once the dependencies are in. Nothing here installs packages at
# runtime — ``uv`` did the install and stays available for an operator who
# needs one — and pip is not free to carry: its ``_vendor`` tree bundles
# pinned copies of msgpack, setuptools and friends, which the Trivy gate
# reports as image vulnerabilities we cannot patch without waiting for a
# pip release. Removing the installer from a production image is the fix
# at the root rather than a scanner suppression, and it shrinks the layer.
# Keep this in the same RUN as the install so the deleted files never land
# in a layer of their own.
RUN uv pip install --system --no-cache -r requirements.lock \
    && rm -rf /usr/local/lib/python3*/site-packages/pip \
              /usr/local/lib/python3*/site-packages/pip-*.dist-info \
              /usr/local/lib/python3*/site-packages/pkg_resources \
              /usr/local/lib/python3*/site-packages/setuptools \
              /usr/local/lib/python3*/site-packages/setuptools-*.dist-info \
              /usr/local/lib/python3*/site-packages/wheel \
              /usr/local/lib/python3*/site-packages/wheel-*.dist-info \
    && python -c "import alembic.config, fastapi, jinja2, PIL, psycopg, requests, sqlalchemy, uvicorn"

# Explicit copies keep the runtime image lean: new top-level files do not
# silently end up inside the container unless added here.
COPY main.py ./
COPY app/ ./app/
# Alembic migrations + config — required so the app can upgrade the database
# to head on startup (and for ``alembic upgrade head`` from a shell).
COPY alembic.ini ./
COPY migrations/ ./migrations/
COPY font/ ./font/
COPY overlay_static/ ./overlay_static/
COPY overlay_templates/ ./overlay_templates/
COPY --from=frontend-build /build/dist /app/frontend/dist
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

# Create an unprivileged ``app`` user but keep the container starting as root
# so the entrypoint can chown the data volume on first boot of an upgraded
# image (existing volumes from previous images are root-owned). The entrypoint
# drops to ``app`` via ``runuser`` before exec'ing the real command.
RUN groupadd --system --gid 1000 app \
    && useradd --system --uid 1000 --gid app --create-home --home /home/app app \
    && chown -R app:app /app \
    && chmod +x /usr/local/bin/docker-entrypoint.sh

# Standalone containers (not via compose) get the same liveness probe.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request, os, sys; \
url = f\"http://127.0.0.1:{os.environ.get('APP_PORT','8080')}/health\"; \
sys.exit(0 if urllib.request.urlopen(url, timeout=3).status == 200 else 1)"

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["python", "main.py"]
