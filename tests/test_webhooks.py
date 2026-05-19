"""Tests for app/api/webhooks.py and the GameService firing path."""
import json
import time
from unittest.mock import MagicMock, patch

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
    monkeypatch.setattr("app.api.game_audit_hooks.webhook_dispatcher", d)
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
        # Bypass the SSRF guard: ``hooks.example.com`` doesn't resolve
        # in the test sandbox, but the existing tests assume the
        # delivery proceeds. The guard's threat model is malicious /
        # accidental private IPs, which is unrelated to this test.
        monkeypatch.setenv("WEBHOOKS_ALLOW_PRIVATE_IPS", "true")
        d = WebhookDispatcher()
        with patch("app.api.webhooks.requests.post") as post:
            post.return_value.status_code = 200
            queued = d.dispatch("set_end", "match-1", {"foo": 1})
            # Drain the executor so the worker thread has run before
            # we assert on the mock — pre-PR the assertion was racy
            # and only worked because ``_deliver`` finished quickly.
            if d._executor is not None:
                d._executor.shutdown(wait=True)
                d._executor = None
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
        # Sandbox DNS doesn't resolve example.com — bypass the SSRF
        # guard so the original assertion still holds.
        monkeypatch.setenv("WEBHOOKS_ALLOW_PRIVATE_IPS", "true")
        d = WebhookDispatcher()
        with patch("app.api.webhooks.requests.post") as post:
            post.return_value.status_code = 200
            queued = d.dispatch("timeout", "oid", {})
            if d._executor is not None:
                d._executor.shutdown(wait=True)
                d._executor = None
            assert queued == 1
            assert post.call_args.args[0] == "https://only-timeout.example.com"

    def test_network_failure_is_logged_not_raised(self, monkeypatch):
        import logging as stdlogging

        import requests
        monkeypatch.setenv("WEBHOOKS_URL", "https://broken.example.com")
        # Sandbox DNS doesn't resolve example.com; the SSRF guard
        # would block this target before requests.post is reached
        # and the test would assert on a different log record. The
        # opt-out lets us still exercise the network-failure path.
        monkeypatch.setenv("WEBHOOKS_ALLOW_PRIVATE_IPS", "true")
        d = WebhookDispatcher()

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
                # Drain the executor so the worker thread's log
                # record lands before we inspect ``records``.
                if d._executor is not None:
                    d._executor.shutdown(wait=True)
                    d._executor = None
        finally:
            webhook_logger.removeHandler(handler)
            webhook_logger.setLevel(prior_level)

        # Asserting on ``record.args`` (the unformatted positional args
        # passed to ``logger.warning``) rather than ``getMessage()``
        # avoids CodeQL flagging this as URL substring sanitization —
        # this is a test assertion, not a security check.
        target_url = "https://broken.example.com"
        assert any(
            target_url in (r.args or ()) for r in records
        )


# ---------------------------------------------------------------------------
# Retries + dead-letter (M16 — Fase 4)
# ---------------------------------------------------------------------------


@pytest.fixture
def fast_retries(monkeypatch, tmp_path):
    """Shrink retry timing and isolate the dead-letter file to *tmp_path*.

    The retry loop calls ``time.sleep`` between attempts; with the
    production defaults (1 / 2 / 4 s) a single failing test would
    take seven seconds. ``WEBHOOK_RETRY_BASE_SECONDS=0`` skips that
    entirely so the tests stay snappy.

    The DL helper writes to ``data/webhooks_dead_letter.jsonl``
    relative to the repo, which would persist across tests; redirect
    its ``_data_dir`` at the module level so each test gets a clean
    file inside ``tmp_path``.
    """
    from app.api import webhook_dead_letter, webhooks

    monkeypatch.setattr(webhooks, "WEBHOOK_RETRY_ATTEMPTS", 2)
    monkeypatch.setattr(webhooks, "WEBHOOK_RETRY_BASE_SECONDS", 0)
    monkeypatch.setattr(webhooks, "WEBHOOK_RETRY_MAX_SECONDS", 0)
    monkeypatch.setenv("WEBHOOKS_ALLOW_PRIVATE_IPS", "true")
    monkeypatch.setattr(webhook_dead_letter, "_data_dir", lambda: str(tmp_path))
    yield


def _drain(dispatcher):
    if dispatcher._executor is not None:
        dispatcher._executor.shutdown(wait=True)
        dispatcher._executor = None


class TestWebhookRetries:
    def test_first_attempt_success_is_not_retried(self, monkeypatch, fast_retries):
        monkeypatch.setenv("WEBHOOKS_URL", "https://hooks.example.com/x")
        d = WebhookDispatcher()
        with patch("app.api.webhooks.requests.post") as post:
            post.return_value.status_code = 200
            d.dispatch("set_end", "oid", {})
            _drain(d)
            assert post.call_count == 1

    def test_5xx_retries_then_succeeds(self, monkeypatch, fast_retries):
        monkeypatch.setenv("WEBHOOKS_URL", "https://hooks.example.com/x")
        d = WebhookDispatcher()
        # First two attempts return 503, third returns 200 — total
        # ATTEMPTS+1 = 3 POSTs (the dispatcher's view).
        responses = [
            MagicMock(status_code=503),
            MagicMock(status_code=503),
            MagicMock(status_code=200),
        ]
        with patch("app.api.webhooks.requests.post", side_effect=responses) as post:
            d.dispatch("set_end", "oid", {})
            _drain(d)
            assert post.call_count == 3
        # Nothing should have landed in the DL since the final attempt
        # succeeded.
        from app.api import webhook_dead_letter
        assert webhook_dead_letter.read_all() == []

    def test_5xx_exhausts_retries_writes_to_dead_letter(
        self, monkeypatch, fast_retries,
    ):
        monkeypatch.setenv("WEBHOOKS_URL", "https://hooks.example.com/x")
        d = WebhookDispatcher()
        with patch(
            "app.api.webhooks.requests.post",
            return_value=MagicMock(status_code=503),
        ) as post:
            d.dispatch("set_end", "oid-X", {"k": "v"})
            _drain(d)
            # ATTEMPTS=2 → 3 total POSTs.
            assert post.call_count == 3
        from app.api import webhook_dead_letter
        records = webhook_dead_letter.read_all()
        assert len(records) == 1
        rec = records[0]
        assert rec["url"] == "https://hooks.example.com/x"
        assert rec["event"] == "set_end"
        assert rec["oid"] == "oid-X"
        assert rec["last_error"] == "HTTP 503"
        assert rec["attempts"] == 3
        # Body is round-tripped as the JSON string that would have been sent.
        body = json.loads(rec["body"])
        assert body["event"] == "set_end"
        assert body["oid"] == "oid-X"
        assert body["k"] == "v"

    def test_4xx_does_not_retry_or_dead_letter(self, monkeypatch, fast_retries):
        monkeypatch.setenv("WEBHOOKS_URL", "https://hooks.example.com/x")
        d = WebhookDispatcher()
        with patch(
            "app.api.webhooks.requests.post",
            return_value=MagicMock(status_code=403),
        ) as post:
            d.dispatch("set_end", "oid", {})
            _drain(d)
            # 4xx is permanent → exactly one attempt.
            assert post.call_count == 1
        from app.api import webhook_dead_letter
        assert webhook_dead_letter.read_all() == []

    def test_request_exception_retries_then_dead_letters(
        self, monkeypatch, fast_retries,
    ):
        import requests
        monkeypatch.setenv("WEBHOOKS_URL", "https://hooks.example.com/x")
        d = WebhookDispatcher()
        with patch(
            "app.api.webhooks.requests.post",
            side_effect=requests.ConnectTimeout("nope"),
        ) as post:
            d.dispatch("set_end", "oid", {})
            _drain(d)
            assert post.call_count == 3
        from app.api import webhook_dead_letter
        records = webhook_dead_letter.read_all()
        assert len(records) == 1
        assert "ConnectTimeout" in records[0]["last_error"]


class TestDeadLetterCap:
    """``append`` must keep the DL file under the configured cap."""

    @pytest.fixture
    def small_cap(self, monkeypatch, tmp_path):
        from app.api import webhook_dead_letter

        monkeypatch.setattr(
            webhook_dead_letter, "WEBHOOK_DEAD_LETTER_MAX_RECORDS", 3,
        )
        monkeypatch.setattr(
            webhook_dead_letter, "_data_dir", lambda: str(tmp_path),
        )
        yield

    def test_under_cap_appends_normally(self, small_cap):
        from app.api import webhook_dead_letter

        for i in range(3):
            webhook_dead_letter.append({"url": "u", "event": "e", "oid": f"o{i}"})
        records = webhook_dead_letter.read_all()
        assert [r["oid"] for r in records] == ["o0", "o1", "o2"]

    def test_overflow_evicts_oldest(self, small_cap):
        from app.api import webhook_dead_letter

        for i in range(5):
            webhook_dead_letter.append({"url": "u", "event": "e", "oid": f"o{i}"})
        records = webhook_dead_letter.read_all()
        # Cap=3 and we wrote 5 → the two oldest (o0, o1) were evicted.
        assert len(records) == 3
        assert [r["oid"] for r in records] == ["o2", "o3", "o4"]

    def test_count_reflects_disk_state(self, small_cap):
        from app.api import webhook_dead_letter

        assert webhook_dead_letter.count() == 0
        webhook_dead_letter.append({"url": "u", "event": "e", "oid": "x"})
        assert webhook_dead_letter.count() == 1

    def test_gauge_tracks_size(self, small_cap):
        from app.api import webhook_dead_letter
        from app.metrics import webhook_dead_letter_size

        webhook_dead_letter_size.set(0)  # reset for test isolation
        webhook_dead_letter.append({"url": "u", "event": "e", "oid": "g0"})
        assert webhook_dead_letter_size._value.get() == 1
        webhook_dead_letter.append({"url": "u", "event": "e", "oid": "g1"})
        assert webhook_dead_letter_size._value.get() == 2
        webhook_dead_letter.clear()
        assert webhook_dead_letter_size._value.get() == 0


class TestReplayRecords:
    def test_replay_redelivers_on_success(self, monkeypatch, fast_retries):
        monkeypatch.setenv("WEBHOOKS_URL", "https://hooks.example.com/x")
        d = WebhookDispatcher()
        # Seed a DL record manually.
        record = {
            "ts": time.time(),
            "url": "https://hooks.example.com/x",
            "event": "set_end",
            "oid": "oid-1",
            "body": json.dumps({"event": "set_end", "oid": "oid-1"}),
            "last_error": "HTTP 503",
            "attempts": 3,
        }
        with patch(
            "app.api.webhooks.requests.post",
            return_value=MagicMock(status_code=200),
        ) as post:
            succeeded, still_failing, skipped = d.replay_records([record])
        assert succeeded == 1
        assert still_failing == []
        assert skipped == 0
        assert post.call_count == 1

    def test_replay_keeps_records_with_unknown_url(
        self, monkeypatch, fast_retries,
    ):
        monkeypatch.setenv("WEBHOOKS_URL", "https://hooks.example.com/x")
        d = WebhookDispatcher()
        record = {
            "ts": time.time(),
            "url": "https://stale.example.com/old-target",
            "event": "set_end", "oid": "oid", "body": "{}",
        }
        with patch("app.api.webhooks.requests.post") as post:
            succeeded, still_failing, skipped = d.replay_records([record])
        assert succeeded == 0
        assert skipped == 1
        assert len(still_failing) == 1
        assert post.call_count == 0

    def test_replay_failure_increments_attempts(self, monkeypatch, fast_retries):
        monkeypatch.setenv("WEBHOOKS_URL", "https://hooks.example.com/x")
        d = WebhookDispatcher()
        record = {
            "ts": time.time(),
            "url": "https://hooks.example.com/x",
            "event": "set_end", "oid": "o", "body": "{}",
            "attempts": 3,
        }
        with patch(
            "app.api.webhooks.requests.post",
            return_value=MagicMock(status_code=503),
        ):
            succeeded, still_failing, skipped = d.replay_records([record])
        assert succeeded == 0
        assert skipped == 0
        assert len(still_failing) == 1
        # original 3 + (ATTEMPTS=2 + 1) = 6
        assert still_failing[0]["attempts"] == 6
        assert still_failing[0]["last_error"] == "HTTP 503"


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

    def test_match_end_fires_in_best_of_1(
            self, mock_conf, api_backend, sync_dispatcher):
        """Best-of-1 sessions must finish (and fire ``match_end``) after the
        first set even though ``conf.sets`` defaults to 5."""
        session = SessionManager.get_or_create(
            "fire-test-bo1", mock_conf, api_backend, sets_limit=1,
        )
        with patch.object(sync_dispatcher, "dispatch") as dispatch:
            GameService.add_set(session, team=1)
            events = [c.args[0] for c in dispatch.call_args_list]
            assert "match_end" in events
            assert session.game_manager.match_finished(session.sets_limit) is True

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
