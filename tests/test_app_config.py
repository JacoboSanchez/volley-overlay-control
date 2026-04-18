"""Tests for the runtime app-config plumbing (APP_TITLE env var).

Covers both the small ``GET /api/v1/app-config`` endpoint and the helper
that rewrites ``<title>`` inside the served SPA ``index.html``.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import api_router
from app.bootstrap import _inject_title_into_html
from app.app_config import DEFAULT_APP_TITLE, get_app_title


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(api_router)
    return TestClient(app)


def test_app_config_returns_default_title(client, monkeypatch):
    monkeypatch.delenv("APP_TITLE", raising=False)
    res = client.get("/api/v1/app-config")
    assert res.status_code == 200
    assert res.json() == {"title": DEFAULT_APP_TITLE}


def test_app_config_returns_env_title(client, monkeypatch):
    monkeypatch.setenv("APP_TITLE", "My Liga Volley")
    res = client.get("/api/v1/app-config")
    assert res.status_code == 200
    assert res.json() == {"title": "My Liga Volley"}


def test_app_config_falls_back_when_env_is_blank(monkeypatch):
    monkeypatch.setenv("APP_TITLE", "   ")
    assert get_app_title() == DEFAULT_APP_TITLE


def test_inject_title_replaces_tag():
    html = "<html><head><title>Old</title></head><body/></html>"
    result = _inject_title_into_html(html, "New Title")
    assert "<title>New Title</title>" in result
    assert "Old" not in result


def test_inject_title_escapes_html_special_chars():
    html = "<html><head><title>x</title></head></html>"
    result = _inject_title_into_html(html, "A & <B>")
    assert "<title>A &amp; &lt;B&gt;</title>" in result


def test_inject_title_only_replaces_first_match():
    html = "<title>a</title>...<title>b</title>"
    result = _inject_title_into_html(html, "Z")
    assert result == "<title>Z</title>...<title>b</title>"
