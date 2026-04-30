# syntax=docker/dockerfile:1.7

# ---- Stage 1: Build the React frontend ----
FROM node:25-alpine AS frontend-build
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

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_SYSTEM_PYTHON=1 \
    UV_NO_CACHE=1

COPY --from=ghcr.io/astral-sh/uv:0.8.17 /uv /usr/local/bin/uv

COPY requirements.lock ./
RUN uv pip install --system --no-cache -r requirements.lock

# Explicit copies keep the runtime image lean: new top-level files do not
# silently end up inside the container unless added here.
COPY main.py ./
COPY app/ ./app/
COPY font/ ./font/
COPY overlay_static/ ./overlay_static/
COPY overlay_templates/ ./overlay_templates/
COPY --from=frontend-build /build/dist /app/frontend/dist

CMD ["python", "main.py"]
