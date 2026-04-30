"""Tests for app/api/webhooks.py and the GameService firing path."""
import json
from unittest.mock import patch

import pytest

from app.api import webhooks
from app.api.game_service import GameService
from app.api.session_manager import SessionManager
from app.api.webhooks import WebhookDispatcher, WebhookTarget

pytestmark = pytest.mark.usefixtures("clean_sessions")


@pytest.fixture(autouse=True)
def reset_dispatcher():
    """Drop the module singleton's cached config between tests."""
    webhooks.webhook_dispatcher.shutdown()
    yield
    webhooks.webhook_dispatcher.shutdown()


@pytest.fixture
def sync_dispatcher(monkeypatch):
    """Run webhook deliveries synchronously and capture them."""
    d = WebhookDispatcher()
    monkeypatch.setattr(webhooks, "webhook_dispatcher", d)
    monkeypatch.setattr("app.api.game_service.webhook_dispatcher", d)
    return d


# ---------------------------------------------------------------------------
# WebhookTarget
# ---------------------------------------------------------------------------

class TestWebhookTarget:
    def test_accepts_when_no_filter(self):
        t = WebhookTarget("http://example.com")
        for event in ("set_end", "match_end", "timeout", "serve_change"):
            assert t.accepts(event) is True

    def test_filters_unknown_events(self):
        t = WebhookTarget("http://example.com",
                          events=["set_end", "bogus", "match_end"])
        assert t.accepts("set_end") is True
        assert t.accepts("match_end") is True
        assert t.accepts("timeout") is False

    def test_invalid_timeout_falls_back(self):
        t = WebhookTarget("http://example.com", timeout_s="oops")
        assert t.timeout_s == 5.0

    def test_csv_events(self):
        t = WebhookTarget("http://example.com", events="set_end,timeout")
        assert t.accepts("set_end")
        assert t.accepts("timeout")
        assert not t.accepts("match_end")


# ---------------------------------------------------------------------------
# WebhookDispatcher configuration
# ---------------------------------------------------------------------------

class TestDispatcherConfig:
    def test_no_targets_when_unset(self, monkeypatch):
        monkeypatch.delenv("WEBHOOKS_URL", raising=False)
        monkeypatch.delenv("WEBHOOKS_JSON", raising=False)
        d = WebhookDispatcher()
        assert d._ensure_loaded() == []

    def test_single_url_config(self, monkeypatch):
        monkeypatch.setenv("WEBHOOKS_URL", "https://hooks.example.com/x")
        monkeypatch.setenv("WEBHOOKS_SECRET", "s3cr3t")
        d = WebhookDispatcher()
        targets = d._ensure_loaded()
        assert len(targets) == 1
        assert targets[0].url == "https://hooks.example.com/x"
        assert targets[0].secret == "s3cr3t"
        assert targets[0].events is None  # all events

    def test_single_url_event_filter(self, monkeypatch):
        monkeypatch.setenv("WEBHOOKS_URL", "https://hooks.example.com/x")
        monkeypatch.setenv("WEBHOOKS_EVENTS", "set_end,match_end")
        d = WebhookDispatcher()
        target = d._ensure_loaded()[0]
        assert target.accepts("set_end")
        assert target.accepts("match_end")
        assert not target.accepts("timeout")

    def test_json_config_preferred(self, monkeypatch):
        monkeypatch.setenv("WEBHOOKS_URL", "https://ignored.example.com")
        monkeypatch.setenv("WEBHOOKS_JSON", json.dumps([
            {"url": "https://a.example.com", "events": ["set_end"]},
            {"url": "https://b.example.com", "secret": "k"},
        ]))
        d = WebhookDispatcher()
        targets = d._ensure_loaded()
        assert [t.url for t in targets] == [
            "https://a.example.com", "https://b.example.com",
        ]
        assert targets[0].events == {"set_end"}
        assert targets[1].secret == "k"

    def test_invalid_json_is_dropped(self, monkeypatch):
        monkeypatch.setenv("WEBHOOKS_JSON", "not-json")
        d = WebhookDispatcher()
        assert d._ensure_loaded() == []

    def test_reload_picks_up_new_config(self, monkeypatch):
        d = WebhookDispatcher()
        monkeypatch.delenv("WEBHOOKS_URL", raising=False)
        monkeypatch.delenv("WEBHOOKS_JSON", raising=False)
        assert d._ensure_loaded() == []
        monkeypatch.setenv("WEBHOOKS_URL", "https://later.example.com")
        d.reload()
        assert len(d._ensure_loaded()) == 1


# ---------------------------------------------------------------------------
# Dispatch / signing
# ---------------------------------------------------------------------------

class TestDispatch:
    def test_unknown_event_is_ignored(self, monkeypatch):
        monkeypatch.setenv("WEBHOOKS_URL", "https://hooks.example.com/x")
        d = WebhookDispatcher()
        with patch("app.api.webhooks.requests.post") as post:
            assert d.dispatch("not_an_event", "oid", {}) == 0
            post.assert_not_called()

    def test_dispatch_posts_signed_body(self, monkeypatch):
        monkeypatch.setenv("WEBHOOKS_URL", "https://hooks.example.com/x")
        monkeypatch.setenv("WEBHOOKS_SECRET", "topsecret")
        d = WebhookDispatcher()
        # Force synchronous delivery for assertion.
        d._executor = None
        with patch("app.api.webhooks.requests.post") as post:
            post.return_value.status_code = 200
            queued = d.dispatch("set_end", "match-1", {"foo": 1})
            assert queued == 1
            post.assert_called_once()
            kwargs = post.call_args.kwargs
            sig = kwargs["headers"]["X-Webhook-Signature"]
            assert sig.startswith("sha256=")
            # Verify the signature corresponds to the body that was sent.
            import hashlib
            import hmac
            expected = "sha256=" + hmac.new(
                b"topsecret", kwargs["data"], hashlib.sha256
            ).hexdigest()
            assert sig == expected
            body = json.loads(kwargs["data"])
            assert body["event"] == "set_end"
            assert body["oid"] == "match-1"
            assert body["foo"] == 1
            assert "ts" in body

    def test_dispatch_skips_unsubscribed(self, monkeypatch):
        monkeypatch.setenv("WEBHOOKS_JSON", json.dumps([
            {"url": "https://only-set.example.com", "events": ["set_end"]},
            {"url": "https://only-timeout.example.com", "events": ["timeout"]},
        ]))
        d = WebhookDispatcher()
        d._executor = None
        with patch("app.api.webhooks.requests.post") as post:
            post.return_value.status_code = 200
            queued = d.dispatch("timeout", "oid", {})
            assert queued == 1
            assert post.call_args.args[0] == "https://only-timeout.example.com"

    def test_network_failure_is_logged_not_raised(self, monkeypatch):
        import logging as stdlogging

        import requests
        monkeypatch.setenv("WEBHOOKS_URL", "https://broken.example.com")
        d = WebhookDispatcher()
        d._executor = None

        # Attach our own handler directly to the dispatcher's logger so the
        # assertion does not depend on caplog plumbing (which interacts
        # poorly with the project's logging dictConfig in some test
        # orderings).
        records: list[stdlogging.LogRecord] = []
        handler = stdlogging.Handler(level=stdlogging.WARNING)
        handler.emit = records.append  # type: ignore[assignment]
        webhook_logger = stdlogging.getLogger("app.api.webhooks")
        prior_level = webhook_logger.level
        webhook_logger.addHandler(handler)
        webhook_logger.setLevel(stdlogging.WARNING)
        try:
            with patch("app.api.webhooks.requests.post",
                       side_effect=requests.ConnectionError("nope")):
                d.dispatch("set_end", "oid", {})
        finally:
            webhook_logger.removeHandler(handler)
            webhook_logger.setLevel(prior_level)

        assert any(
            "broken.example.com" in r.getMessage() for r in records
        )


# ---------------------------------------------------------------------------
# GameService firing path
# ---------------------------------------------------------------------------

class TestGameServiceFires:
    def test_add_point_does_not_fire_set_end_on_normal_point(
            self, mock_conf, api_backend, sync_dispatcher):
        session = SessionManager.get_or_create(
            "fire-test-1", mock_conf, api_backend,
        )
        with patch.object(sync_dispatcher, "dispatch") as dispatch:
            GameService.add_point(session, team=1)
            events = [c.args[0] for c in dispatch.call_args_list]
            assert "set_end" not in events
            # serve_change should fire on first point (NONE -> A)
            assert "serve_change" in events

    def test_add_set_fires_set_end(
            self, mock_conf, api_backend, sync_dispatcher):
        session = SessionManager.get_or_create(
            "fire-test-2", mock_conf, api_backend,
        )
        with patch.object(sync_dispatcher, "dispatch") as dispatch:
            GameService.add_set(session, team=1)
            events = [c.args[0] for c in dispatch.call_args_list]
            assert "set_end" in events

    def test_add_set_undo_does_not_fire(
            self, mock_conf, api_backend, sync_dispatcher):
        session = SessionManager.get_or_create(
            "fire-test-3", mock_conf, api_backend,
        )
        # Give team 1 a set first so undo has something to undo.
        GameService.add_set(session, team=1)
        with patch.object(sync_dispatcher, "dispatch") as dispatch:
            GameService.add_set(session, team=1, undo=True)
            assert dispatch.call_count == 0

    def test_match_end_fires_when_match_finishes(
            self, mock_conf, api_backend, sync_dispatcher):
        # mock_conf has sets=5 → soft limit = 3 sets won.
        session = SessionManager.get_or_create(
            "fire-test-4", mock_conf, api_backend,
        )
        GameService.add_set(session, team=1)
        GameService.add_set(session, team=1)
        with patch.object(sync_dispatcher, "dispatch") as dispatch:
            GameService.add_set(session, team=1)
            events = [c.args[0] for c in dispatch.call_args_list]
            assert "match_end" in events
            assert "set_end" in events

    def test_add_timeout_fires(
            self, mock_conf, api_backend, sync_dispatcher):
        session = SessionManager.get_or_create(
            "fire-test-5", mock_conf, api_backend,
        )
        with patch.object(sync_dispatcher, "dispatch") as dispatch:
            GameService.add_timeout(session, team=2)
            events = [c.args[0] for c in dispatch.call_args_list]
            assert "timeout" in events

    def test_dispatch_failure_does_not_break_action(
            self, mock_conf, api_backend, sync_dispatcher):
        session = SessionManager.get_or_create(
            "fire-test-6", mock_conf, api_backend,
        )
        with patch.object(sync_dispatcher, "dispatch",
                          side_effect=RuntimeError("boom")):
            response = GameService.add_timeout(session, team=1)
            # The action still succeeds even if the webhook layer dies.
            assert response.success is True
