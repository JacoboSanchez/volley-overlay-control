"""Tests for :class:`app.api.middleware.errors.ExceptionLoggingMiddleware`."""

import logging

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api.middleware.errors import ExceptionLoggingMiddleware
from app.api.middleware.logging import RequestContextMiddleware


def _build_app():
    app = FastAPI()

    @app.get("/boom")
    async def boom():
        raise RuntimeError("kapow")

    @app.get("/teapot")
    async def teapot():
        raise HTTPException(status_code=418, detail="i am a teapot")

    # Outermost middleware is added last (Starlette inserts at head).
    app.add_middleware(ExceptionLoggingMiddleware)
    app.add_middleware(RequestContextMiddleware)
    return app


def test_unhandled_exception_is_logged_and_reraised(caplog):
    client = TestClient(_build_app(), raise_server_exceptions=False)
    with caplog.at_level(logging.ERROR, logger="app.api.middleware.errors"):
        response = client.get("/boom")
    assert response.status_code == 500
    matches = [
        r for r in caplog.records
        if r.name == "app.api.middleware.errors" and r.levelno == logging.ERROR
    ]
    assert matches, "expected an ERROR log from ExceptionLoggingMiddleware"
    assert "kapow" in (matches[0].exc_text or "")


def test_http_exception_passes_through_silently(caplog):
    client = TestClient(_build_app())
    with caplog.at_level(logging.ERROR, logger="app.api.middleware.errors"):
        response = client.get("/teapot")
    assert response.status_code == 418
    assert not [
        r for r in caplog.records if r.name == "app.api.middleware.errors"
    ], "HTTPException must not be reported as an unhandled error"


def test_passes_through_lifespan_scope():
    """Lifespan must not be intercepted; the framework owns that channel."""
    seen = []

    async def inner(scope, receive, send):
        seen.append(scope["type"])

    middleware = ExceptionLoggingMiddleware(inner)

    import asyncio
    asyncio.run(middleware({"type": "lifespan"}, lambda: None, lambda m: None))
    assert seen == ["lifespan"]
