"""Tests for the optional error-tracking integration point.

``sentry-sdk`` is deliberately not a bundled dependency, so these tests
never import it. They install a stub module in ``sys.modules`` to prove
the wiring, and separately prove that a missing package degrades to
"logged but not reported" instead of failing startup.
"""
from __future__ import annotations

import logging
import sys

import pytest

from app import observability
from app.logging_context import request_id_var, trace_id_var


@pytest.fixture(autouse=True)
def _reset():
    observability._reset_for_tests()
    yield
    observability._reset_for_tests()


class _StubSentry:
    """Minimal stand-in for the parts of ``sentry_sdk`` we touch."""

    def __init__(self, *, fail_init=False, fail_capture=False):
        self.init_kwargs: dict | None = None
        self.captured: list[BaseException] = []
        self._fail_init = fail_init
        self._fail_capture = fail_capture

    def init(self, **kwargs):
        if self._fail_init:
            raise RuntimeError("bad dsn")
        self.init_kwargs = kwargs

    def capture_exception(self, exc):
        if self._fail_capture:
            raise RuntimeError("reporter down")
        self.captured.append(exc)


@pytest.fixture
def stub_sentry(monkeypatch):
    def _install(**kwargs):
        stub = _StubSentry(**kwargs)
        monkeypatch.setitem(sys.modules, "sentry_sdk", stub)
        return stub

    return _install


class TestInitIsOptOut:
    def test_no_dsn_wires_nothing(self, monkeypatch):
        monkeypatch.delenv("SENTRY_DSN", raising=False)
        assert observability.init_error_tracking() is False
        assert observability.is_error_tracking_enabled() is False

    def test_blank_dsn_is_treated_as_unset(self, monkeypatch):
        monkeypatch.setenv("SENTRY_DSN", "   ")
        assert observability.init_error_tracking() is False

    def test_capture_is_a_noop_without_a_reporter(self, monkeypatch):
        monkeypatch.delenv("SENTRY_DSN", raising=False)
        observability.init_error_tracking()
        # Must not raise — this runs inside the exception middleware.
        observability.capture_exception(ValueError("boom"))

    def test_dsn_without_the_package_warns_but_boots(self, monkeypatch, caplog):
        monkeypatch.setenv("SENTRY_DSN", "https://key@example.invalid/1")
        monkeypatch.setitem(sys.modules, "sentry_sdk", None)
        with caplog.at_level(logging.WARNING, logger="app.observability"):
            assert observability.init_error_tracking() is False
        assert "sentry-sdk" in caplog.text
        assert observability.is_error_tracking_enabled() is False


class TestInitWiresTheReporter:
    def test_dsn_plus_package_enables_capture(self, monkeypatch, stub_sentry):
        stub = stub_sentry()
        monkeypatch.setenv("SENTRY_DSN", "https://key@example.invalid/1")
        assert observability.init_error_tracking() is True
        assert observability.is_error_tracking_enabled() is True
        assert stub.init_kwargs["dsn"] == "https://key@example.invalid/1"

        exc = ValueError("boom")
        observability.capture_exception(exc)
        assert stub.captured == [exc]

    def test_pii_is_off_by_default(self, monkeypatch, stub_sentry):
        # The project redacts OIDs and URLs in its own logs; shipping
        # headers/cookies/IPs to a third party would quietly undo that.
        stub = stub_sentry()
        monkeypatch.setenv("SENTRY_DSN", "https://key@example.invalid/1")
        observability.init_error_tracking()
        assert stub.init_kwargs["send_default_pii"] is False

    def test_environment_is_forwarded_when_set(self, monkeypatch, stub_sentry):
        stub = stub_sentry()
        monkeypatch.setenv("SENTRY_DSN", "https://key@example.invalid/1")
        monkeypatch.setenv("SENTRY_ENVIRONMENT", "production")
        observability.init_error_tracking()
        assert stub.init_kwargs["environment"] == "production"

    def test_environment_is_omitted_when_unset(self, monkeypatch, stub_sentry):
        stub = stub_sentry()
        monkeypatch.setenv("SENTRY_DSN", "https://key@example.invalid/1")
        monkeypatch.delenv("SENTRY_ENVIRONMENT", raising=False)
        observability.init_error_tracking()
        assert "environment" not in stub.init_kwargs

    @pytest.mark.parametrize("raw,expected", [("0", 0.0), ("0.25", 0.25), ("1", 1.0)])
    def test_valid_sample_rate_is_forwarded(
        self, monkeypatch, stub_sentry, raw, expected,
    ):
        stub = stub_sentry()
        monkeypatch.setenv("SENTRY_DSN", "https://key@example.invalid/1")
        monkeypatch.setenv("SENTRY_TRACES_SAMPLE_RATE", raw)
        observability.init_error_tracking()
        assert stub.init_kwargs["traces_sample_rate"] == expected

    @pytest.mark.parametrize("raw", ["", "abc", "-0.5", "1.5", "nonsense"])
    def test_invalid_sample_rate_is_dropped_not_fatal(
        self, monkeypatch, stub_sentry, raw,
    ):
        stub = stub_sentry()
        monkeypatch.setenv("SENTRY_DSN", "https://key@example.invalid/1")
        monkeypatch.setenv("SENTRY_TRACES_SAMPLE_RATE", raw)
        assert observability.init_error_tracking() is True
        assert "traces_sample_rate" not in stub.init_kwargs

    def test_init_is_idempotent(self, monkeypatch, stub_sentry):
        stub = stub_sentry()
        monkeypatch.setenv("SENTRY_DSN", "https://key@example.invalid/1")
        assert observability.init_error_tracking() is True
        stub.init_kwargs = None
        # create_app runs once per test in this suite; a second call must
        # not re-init the SDK.
        assert observability.init_error_tracking() is True
        assert stub.init_kwargs is None


class TestFailuresNeverBreakTheApp:
    def test_failing_init_degrades_to_no_reporting(self, monkeypatch, stub_sentry):
        stub_sentry(fail_init=True)
        monkeypatch.setenv("SENTRY_DSN", "https://key@example.invalid/1")
        assert observability.init_error_tracking() is False
        assert observability.is_error_tracking_enabled() is False

    def test_failing_capture_is_swallowed(self, monkeypatch, stub_sentry):
        stub_sentry(fail_capture=True)
        monkeypatch.setenv("SENTRY_DSN", "https://key@example.invalid/1")
        observability.init_error_tracking()
        # A reporter that is down must not turn a logged 500 into a crash
        # inside the middleware.
        observability.capture_exception(ValueError("boom"))


class TestEventScrubbing:
    """Credentials must not leave the process in an error report.

    ``send_default_pii=False`` withholds cookies, the client IP and
    sensitive headers — it does **not** strip the request URL, query
    string or body, which is where this app's capability tokens and
    passwords live.
    """

    @pytest.mark.parametrize(
        "path",
        [
            "/overlay/tok_abc123",
            "/follow/tok_abc123",
            "/ws/tok_abc123",
            "/matches/tok_abc123",
            "/match/tok_abc123/report",
        ],
    )
    def test_capability_path_segments_are_masked(self, path):
        event = observability._before_send(
            {"request": {"url": f"https://scores.example.com{path}"}}, None,
        )
        assert "tok_abc123" not in event["request"]["url"]
        assert observability._MASK in event["request"]["url"]

    def test_ordinary_paths_are_left_readable(self):
        # Masking everything would make the reports useless for triage.
        event = observability._before_send(
            {"request": {"url": "https://scores.example.com/api/v1/game/add-point"}},
            None,
        )
        assert event["request"]["url"].endswith("/api/v1/game/add-point")

    def test_query_string_is_dropped(self):
        # ?c= is the shareable operator board token; ?sig= signs a report.
        event = observability._before_send(
            {
                "request": {
                    "url": "https://scores.example.com/board?c=ctl_secret",
                    "query_string": "c=ctl_secret&u=alice",
                },
            },
            None,
        )
        assert "ctl_secret" not in str(event["request"])
        assert "alice" not in str(event["request"])

    def test_request_body_is_dropped(self):
        # POST /api/v1/auth/login carries a plaintext password.
        event = observability._before_send(
            {
                "request": {
                    "url": "https://scores.example.com/api/v1/auth/login",
                    "data": {"username": "alice", "password": "hunter2"},
                },
            },
            None,
        )
        assert event["request"]["data"] == observability._MASK
        assert "hunter2" not in str(event)

    def test_cookies_are_dropped(self):
        event = observability._before_send(
            {"request": {"cookies": {"vsession": "sess_secret"}}}, None,
        )
        assert "sess_secret" not in str(event)

    @pytest.mark.parametrize(
        "header", ["Authorization", "authorization", "Cookie", "X-Control-Token"],
    )
    def test_sensitive_headers_are_masked(self, header):
        event = observability._before_send(
            {"request": {"headers": {header: "creds", "User-Agent": "obs/1.0"}}},
            None,
        )
        assert event["request"]["headers"][header] == observability._MASK
        # Non-sensitive headers stay — they are useful for triage.
        assert event["request"]["headers"]["User-Agent"] == "obs/1.0"

    def test_userinfo_is_stripped_from_the_url(self):
        event = observability._before_send(
            {"request": {"url": "https://user:pw@scores.example.com/api/v1/state"}},
            None,
        )
        assert "pw" not in event["request"]["url"]
        assert "user" not in event["request"]["url"]

    def test_scrubbing_is_independent_of_log_redact(self, monkeypatch):
        # LOG_REDACT=0 lets a developer read raw values in their own
        # terminal; it must not open a channel to an external service.
        monkeypatch.setenv("LOG_REDACT", "0")
        event = observability._before_send(
            {"request": {"url": "https://scores.example.com/overlay/tok_abc123"}},
            None,
        )
        assert "tok_abc123" not in event["request"]["url"]

    def test_event_without_request_context_is_fine(self):
        event = observability._before_send({}, None)
        assert "request" not in event or event["request"] == observability._MASK

    def test_malformed_request_context_is_not_shipped_raw(self, monkeypatch):
        # If the scrubber itself fails, the event must lose its request
        # context rather than going out unscrubbed.
        def boom(_request):
            raise RuntimeError("scrubber bug")

        monkeypatch.setattr(observability, "_scrub_request", boom)
        event = observability._before_send(
            {"request": {"url": "https://scores.example.com/overlay/tok_abc123"}},
            None,
        )
        assert event["request"] == observability._MASK

    def test_unparseable_url_is_masked(self):
        event = observability._before_send(
            {"request": {"url": "http://[oops"}}, None,
        )
        assert event["request"]["url"] == observability._MASK


class TestRemoteConfigIsHonoured:
    """``SENTRY_*`` must resolve through the remote-config manager.

    An operator who supplies the DSN only via ``REMOTE_CONFIG_URL`` would
    otherwise get no reporting at all, since a bare ``os.environ`` read
    never sees those values.
    """

    @pytest.fixture
    def remote_config(self, monkeypatch):
        """Serve a remote-config payload without any network access."""
        import time

        from app.env_vars_manager import EnvVarsManager

        saved_cache = EnvVarsManager._remote_config_cache
        saved_ts = EnvVarsManager._cache_timestamp

        def _install(values: dict):
            # A configured URL is what stops _load_remote_config_if_needed
            # from clearing the cache; a fresh timestamp keeps it on the
            # no-refetch fast path.
            monkeypatch.setenv("REMOTE_CONFIG_URL", "https://cfg.invalid/c.json")
            EnvVarsManager._remote_config_cache = values
            EnvVarsManager._cache_timestamp = time.time()

        yield _install
        EnvVarsManager._remote_config_cache = saved_cache
        EnvVarsManager._cache_timestamp = saved_ts

    def test_dsn_from_remote_config_enables_reporting(
        self, monkeypatch, stub_sentry, remote_config,
    ):
        stub = stub_sentry()
        monkeypatch.delenv("SENTRY_DSN", raising=False)
        monkeypatch.delenv("SENTRY_ENVIRONMENT", raising=False)
        monkeypatch.delenv("SENTRY_TRACES_SAMPLE_RATE", raising=False)
        remote_config({
            "SENTRY_DSN": "https://key@example.invalid/9",
            "SENTRY_ENVIRONMENT": "staging",
            "SENTRY_TRACES_SAMPLE_RATE": "0.5",
        })
        assert observability.init_error_tracking() is True
        assert stub.init_kwargs["dsn"] == "https://key@example.invalid/9"
        assert stub.init_kwargs["environment"] == "staging"
        assert stub.init_kwargs["traces_sample_rate"] == 0.5


class TestEventTagging:
    def test_correlation_ids_are_attached(self):
        rid = request_id_var.set("rid-42")
        trace = trace_id_var.set("0af7651916cd43dd8448eb211c80319c")
        try:
            event = observability._before_send({}, None)
        finally:
            request_id_var.reset(rid)
            trace_id_var.reset(trace)
        assert event["tags"]["request_id"] == "rid-42"
        assert event["tags"]["trace_id"] == "0af7651916cd43dd8448eb211c80319c"

    def test_absent_trace_id_is_not_tagged(self):
        rid = request_id_var.set("rid-7")
        try:
            event = observability._before_send({}, None)
        finally:
            request_id_var.reset(rid)
        assert event["tags"]["request_id"] == "rid-7"
        assert "trace_id" not in event["tags"]

    def test_existing_tags_are_preserved(self):
        event = observability._before_send({"tags": {"request_id": "already"}}, None)
        assert event["tags"]["request_id"] == "already"

    def test_malformed_event_is_returned_unchanged(self):
        # before_send must never raise into the SDK's send path.
        event = {"tags": "not-a-dict"}
        assert observability._before_send(event, None) is event


class TestMiddlewareReportsUnhandledExceptions:
    def test_exception_reaches_the_reporter(self, monkeypatch, stub_sentry):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.api.middleware.errors import ExceptionLoggingMiddleware

        stub = stub_sentry()
        monkeypatch.setenv("SENTRY_DSN", "https://key@example.invalid/1")
        observability.init_error_tracking()

        app = FastAPI()

        @app.get("/boom")
        async def boom():
            raise RuntimeError("kaboom")

        @app.get("/teapot")
        async def teapot():
            from fastapi import HTTPException

            raise HTTPException(status_code=418, detail="nope")

        app.add_middleware(ExceptionLoggingMiddleware)
        client = TestClient(app, raise_server_exceptions=False)

        assert client.get("/boom").status_code == 500
        assert len(stub.captured) == 1
        assert isinstance(stub.captured[0], RuntimeError)

        # An HTTPException is a structured response signal, not an error;
        # reporting it would bury real failures under 401/404 noise.
        assert client.get("/teapot").status_code == 418
        assert len(stub.captured) == 1
