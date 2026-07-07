"""ASGI request-body cap — closes the chunked-encoding upload bypass.

The route-level Content-Length guard is skippable by omitting the header
(chunked transfer); Starlette then spools the entire multipart body to
disk before any handler code runs. The BodySizeLimitMiddleware bounds
the read at the ASGI layer.
"""

import pytest
from fastapi.testclient import TestClient

from app.api.middleware.body_limit import BodySizeLimitMiddleware
from app.bootstrap import create_app
from tests.conftest import login_client


@pytest.fixture
def small_cap(monkeypatch):
    """Cap request bodies at 10 KiB for the app built after this fixture."""
    import app.bootstrap as bootstrap_module

    original = BodySizeLimitMiddleware.__init__

    def patched(self, app, max_bytes: int = 10 * 1024):
        original(self, app, max_bytes)

    monkeypatch.setattr(BodySizeLimitMiddleware, "__init__", patched)
    return bootstrap_module


def test_declared_oversized_body_is_413(small_cap, db_session):
    client = login_client(TestClient(create_app()), db_session, "cap1")
    resp = client.post(
        "/api/v1/icons/mine",
        content=b"x" * 100,
        headers={
            "Content-Type": "multipart/form-data; boundary=x",
            "Content-Length": str(50 * 1024),
        },
    )
    assert resp.status_code == 413


def test_chunked_body_without_content_length_is_413(small_cap, db_session):
    """The bypass: no Content-Length at all — the cap must still hold."""
    client = login_client(TestClient(create_app()), db_session, "cap2")

    def body_gen():
        for _ in range(64):  # 64 KiB total, streamed
            yield b"y" * 1024

    resp = client.post(
        "/api/v1/icons/mine",
        content=body_gen(),
        headers={"Content-Type": "multipart/form-data; boundary=x"},
    )
    assert resp.status_code == 413
    assert "too large" in resp.json()["detail"].lower()


def test_normal_requests_pass_through(small_cap, db_session):
    client = login_client(TestClient(create_app()), db_session, "cap3")
    assert client.get("/api/v1/auth/me").status_code == 200
    resp = client.post("/api/v1/session/init", json={"oid": "liga"})
    assert resp.status_code == 200
