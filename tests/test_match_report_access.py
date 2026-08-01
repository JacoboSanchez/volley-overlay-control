"""Direct unit tests for :mod:`app.match_report.access` — the authorization
gate behind ``/match/{id}/report``.

The integration surface (``TestMatchReportAuth`` in ``test_match_report.py``)
covers the full HTTP stack; this file focuses on the five early-return exits
in ``cookie_user_owns`` and the three-way decision in ``check_read_access``
that the integration suite can only exercise indirectly.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, Request

from app.match_report.access import _public_mode_enabled, check_read_access, cookie_user_owns

# ---------------------------------------------------------------------------
# _public_mode_enabled
# ---------------------------------------------------------------------------

class TestPublicModeEnabled:
    def test_true_when_env_is_true(self, monkeypatch):
        monkeypatch.setenv("MATCH_REPORT_PUBLIC", "true")
        assert _public_mode_enabled() is True

    def test_false_when_env_is_false(self, monkeypatch):
        monkeypatch.setenv("MATCH_REPORT_PUBLIC", "false")
        assert _public_mode_enabled() is False

    def test_false_when_env_is_absent(self, monkeypatch):
        monkeypatch.delenv("MATCH_REPORT_PUBLIC", raising=False)
        assert _public_mode_enabled() is False


# ---------------------------------------------------------------------------
# cookie_user_owns — the five early-return-False exit points
# ---------------------------------------------------------------------------

class TestCookieUserOwns:
    """Each test exercises exactly one exit point of ``cookie_user_owns``.

    ``cookie_user_owns`` uses lazy imports (``from app.auth import sessions``,
    ``from app.api import match_archive``, ``from app.api.match_archive``)
    inside the function body, so we patch the actual source modules rather
    than ``app.match_report.access``.
    """

    def _make_request(self, cookie: str | None = None) -> MagicMock:
        req = MagicMock(spec=Request)
        req.cookies = {}
        if cookie is not None:
            req.cookies["vsession"] = cookie
        return req

    # Exit 1: match_id is None / falsy — line 29-30
    def test_none_match_id_returns_false(self):
        assert cookie_user_owns(self._make_request("any"), None) is False

    def test_empty_match_id_returns_false(self):
        assert cookie_user_owns(self._make_request("any"), "") is False

    # Exit 2: no session cookie in request — line 35-36
    def test_no_cookie_returns_false(self):
        assert cookie_user_owns(self._make_request(None), "match_abc123") is False

    def test_empty_cookie_returns_false(self):
        req = self._make_request()
        req.cookies["vsession"] = ""
        assert cookie_user_owns(req, "match_abc123") is False

    # Exit 3: session cookie does not resolve to a user — line 39-40
    def test_invalid_session_returns_false(self):
        """A cookie that resolves to no user (e.g. forged)."""
        with patch("app.auth.sessions.resolve_session", return_value=None) as mock_resolve:
            assert cookie_user_owns(self._make_request("bogus-token"), "match_abc123") is False
            mock_resolve.assert_called_once()

    # Exit 4: match_id not found in archive — line 44-45
    def test_archive_miss_returns_false(self):
        mock_user = MagicMock()
        mock_user.id = 42

        with patch("app.auth.sessions.resolve_session", return_value=mock_user), \
             patch("app.api.match_archive.load_match", return_value=None):
            assert cookie_user_owns(self._make_request("valid-session"), "match_missing") is False

    # Exit 5a: skey missing from payload — line 47-48
    def test_payload_without_oid_returns_false(self):
        mock_user = MagicMock()
        mock_user.id = 42

        with patch("app.auth.sessions.resolve_session", return_value=mock_user), \
             patch("app.api.match_archive.load_match", return_value={"final_state": {}}):
            assert cookie_user_owns(self._make_request("valid-session"), "match_no_oid") is False

    # Exit 5b: skey present but invalid — line 47-48
    def test_payload_with_invalid_skey_returns_false(self):
        mock_user = MagicMock()
        mock_user.id = 42

        with patch("app.auth.sessions.resolve_session", return_value=mock_user), \
             patch("app.api.match_archive.load_match",
                   return_value={"oid": "not-a-valid-skey"}):
            assert cookie_user_owns(self._make_request("valid-session"), "match_bad_skey") is False

    # Happy path: owner matches — line 49-50
    def test_owner_match_returns_true(self):
        from app.overlay_key import make_skey

        user_id = 42
        skey = make_skey(user_id, "test-oid")

        mock_user = MagicMock()
        mock_user.id = user_id

        with patch("app.auth.sessions.resolve_session", return_value=mock_user), \
             patch("app.api.match_archive.load_match", return_value={"oid": skey}):
            assert cookie_user_owns(self._make_request("owner-session"), "match_owned") is True

    # Non-owner user — returns False (owner_id != user.id)
    def test_non_owner_returns_false(self):
        from app.overlay_key import make_skey

        skey = make_skey(42, "test-oid")  # owner is 42

        mock_user = MagicMock()
        mock_user.id = 99  # intruder — not 42

        with patch("app.auth.sessions.resolve_session", return_value=mock_user), \
             patch("app.api.match_archive.load_match", return_value={"oid": skey}):
            assert cookie_user_owns(self._make_request("intruder-session"), "match_not_mine") is False


# ---------------------------------------------------------------------------
# check_read_access — the three-way decision gate
# ---------------------------------------------------------------------------

class TestCheckReadAccess:
    """Test each of the three access paths and the 401 fallback.

    ``check_read_access`` lazy-imports ``verify_signed_query`` from
    ``app.match_report.signing``, so we patch that source module.
    """

    def _make_request(self, cookie: str | None = None) -> MagicMock:
        req = MagicMock(spec=Request)
        req.cookies = {}
        if cookie is not None:
            req.cookies["vsession"] = cookie
        return req

    # Path 1: public mode — admits anyone
    def test_public_mode_returns_without_raising(self, monkeypatch):
        monkeypatch.setenv("MATCH_REPORT_PUBLIC", "true")
        # Should not raise
        check_read_access(self._make_request(), "any-match")

    # Path 2: signed URL with valid signature
    def test_signed_url_admits_with_valid_signature(self, monkeypatch):
        monkeypatch.delenv("MATCH_REPORT_PUBLIC", raising=False)
        with patch("app.match_report.signing.verify_signed_query", return_value=True):
            # Should not raise
            check_read_access(
                self._make_request(),
                "match_signed",
                exp="1000000000",
                sig="abcdef123456",
            )

    def test_signed_url_rejects_tampered_signature(self, monkeypatch):
        monkeypatch.delenv("MATCH_REPORT_PUBLIC", raising=False)
        with patch("app.match_report.signing.verify_signed_query", return_value=False), \
             patch("app.match_report.access.cookie_user_owns", return_value=False):
            with pytest.raises(HTTPException) as exc_info:
                check_read_access(
                    self._make_request(),
                    "match_signed",
                    exp="1000000000",
                    sig="tampered",
                )
            assert exc_info.value.status_code == 401

    # Path 3: owner cookie
    def test_owner_cookie_admits(self, monkeypatch):
        monkeypatch.delenv("MATCH_REPORT_PUBLIC", raising=False)
        with patch("app.match_report.access.cookie_user_owns", return_value=True):
            # Should not raise
            check_read_access(self._make_request("owner"), "match_owned")

    # Fallback: 401 when nothing matches
    def test_raises_401_when_nothing_matches(self, monkeypatch):
        monkeypatch.delenv("MATCH_REPORT_PUBLIC", raising=False)
        with patch("app.match_report.access.cookie_user_owns", return_value=False):
            with pytest.raises(HTTPException) as exc_info:
                check_read_access(self._make_request(), "match_forbidden")
            assert exc_info.value.status_code == 401
            assert "WWW-Authenticate" in exc_info.value.headers

    # Edge: matching both signed URL and cookie — signed takes priority
    def test_signed_url_checked_before_cookie(self, monkeypatch):
        """When both signed params and cookie are present, the signed path
        short-circuits before cookie_user_owns is called."""
        monkeypatch.delenv("MATCH_REPORT_PUBLIC", raising=False)
        with patch("app.match_report.signing.verify_signed_query", return_value=True), \
             patch("app.match_report.access.cookie_user_owns") as mock_cookie_owns:
            check_read_access(
                self._make_request("some-cookie"),
                "match_signed",
                exp="1000000000",
                sig="abcdef123456",
            )
            # cookie_user_owns must not be called — signed path short-circuits
            mock_cookie_owns.assert_not_called()

    # Edge: no match_id together with exp/sig → signed path not entered
    def test_no_match_id_with_exp_sig_skips_signed_path(self, monkeypatch):
        monkeypatch.delenv("MATCH_REPORT_PUBLIC", raising=False)
        with patch("app.match_report.signing.verify_signed_query") as mock_verify, \
             patch("app.match_report.access.cookie_user_owns", return_value=False):
            with pytest.raises(HTTPException):
                check_read_access(
                    self._make_request(),
                    None,  # match_id is None
                    exp="1000000000",
                    sig="abcdef",
                )
            # verify_signed_query must not be called when match_id is None
            mock_verify.assert_not_called()
