"""Direct unit tests for :mod:`app.match_report.access` — the authorization
gate behind ``/match/{id}/report``.

The integration surface (``TestMatchReportAuth`` in ``test_match_report.py``)
covers the full HTTP stack; this file focuses on the early-return exits in
``cookie_user_owns`` and the three-way decision in ``check_read_access``
that the integration suite can only exercise indirectly.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException, Request

from app.match_report.access import _public_mode_enabled, check_read_access, cookie_user_owns
from app.overlay_key import make_skey


def make_request(cookie: str | None = None) -> MagicMock:
    """A request stub carrying (or lacking) a ``vsession`` cookie."""
    req = MagicMock(spec=Request)
    req.cookies = {} if cookie is None else {"vsession": cookie}
    return req


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
# cookie_user_owns — every path that denies ownership
# ---------------------------------------------------------------------------


class TestCookieUserOwns:
    """Each test exercises exactly one exit point of ``cookie_user_owns``.

    ``cookie_user_owns`` uses lazy imports (``from app.auth import sessions``,
    ``from app.api import match_archive``) inside the function body, so we
    patch the actual source modules rather than ``app.match_report.access``.
    """

    # No match id to resolve.
    def test_none_match_id_returns_false(self):
        assert cookie_user_owns(make_request("any"), None) is False

    def test_empty_match_id_returns_false(self):
        assert cookie_user_owns(make_request("any"), "") is False

    # No session cookie on the request.
    def test_no_cookie_returns_false(self):
        assert cookie_user_owns(make_request(None), "match_abc123") is False

    def test_empty_cookie_returns_false(self):
        assert cookie_user_owns(make_request(""), "match_abc123") is False

    # Cookie present but does not resolve to a user.
    def test_invalid_session_returns_false(self):
        """A cookie that resolves to no user (e.g. forged)."""
        with patch("app.auth.sessions.resolve_session", return_value=None) as mock_resolve:
            assert cookie_user_owns(make_request("bogus-token"), "match_abc123") is False
            mock_resolve.assert_called_once()

    # match_id not present in the archive.
    def test_archive_miss_returns_false(self):
        mock_user = MagicMock()
        mock_user.id = 42

        with (
            patch("app.auth.sessions.resolve_session", return_value=mock_user),
            patch("app.api.match_archive.load_match", return_value=None),
        ):
            assert cookie_user_owns(make_request("valid-session"), "match_missing") is False

    # Archived payload carries no skey at all.
    def test_payload_without_oid_returns_false(self):
        mock_user = MagicMock()
        mock_user.id = 42

        with (
            patch("app.auth.sessions.resolve_session", return_value=mock_user),
            patch("app.api.match_archive.load_match", return_value={"final_state": {}}),
        ):
            assert cookie_user_owns(make_request("valid-session"), "match_no_oid") is False

    # Archived payload carries a skey that does not parse.
    def test_payload_with_invalid_skey_returns_false(self):
        mock_user = MagicMock()
        mock_user.id = 42

        with (
            patch("app.auth.sessions.resolve_session", return_value=mock_user),
            patch("app.api.match_archive.load_match", return_value={"oid": "not-a-valid-skey"}),
        ):
            assert cookie_user_owns(make_request("valid-session"), "match_bad_skey") is False

    # Happy path: the cookie's user is the skey's owner.
    def test_owner_match_returns_true(self):
        user_id = 42
        skey = make_skey(user_id, "test-oid")

        mock_user = MagicMock()
        mock_user.id = user_id

        with (
            patch("app.auth.sessions.resolve_session", return_value=mock_user),
            patch("app.api.match_archive.load_match", return_value={"oid": skey}),
        ):
            assert cookie_user_owns(make_request("owner-session"), "match_owned") is True

    # A signed-in user who is not the owner must not read someone else's report.
    def test_non_owner_returns_false(self):
        skey = make_skey(42, "test-oid")  # owner is 42

        mock_user = MagicMock()
        mock_user.id = 99  # intruder — not 42

        with (
            patch("app.auth.sessions.resolve_session", return_value=mock_user),
            patch("app.api.match_archive.load_match", return_value={"oid": skey}),
        ):
            assert cookie_user_owns(make_request("intruder-session"), "match_not_mine") is False


# ---------------------------------------------------------------------------
# check_read_access — the three-way decision gate
# ---------------------------------------------------------------------------


class TestCheckReadAccess:
    """Test each of the three access paths and the 401 fallback.

    ``check_read_access`` lazy-imports ``verify_signed_query`` from
    ``app.match_report.signing``, so we patch that source module.
    """

    # Path 1: public mode — admits anyone
    def test_public_mode_returns_without_raising(self, monkeypatch):
        monkeypatch.setenv("MATCH_REPORT_PUBLIC", "true")
        # Should not raise
        check_read_access(make_request(), "any-match")

    def test_public_mode_short_circuits_before_any_credential_check(self, monkeypatch):
        """Public mode must not need — or consult — a cookie or signature."""
        monkeypatch.setenv("MATCH_REPORT_PUBLIC", "true")
        with (
            patch("app.match_report.signing.verify_signed_query") as mock_verify,
            patch("app.match_report.access.cookie_user_owns") as mock_cookie_owns,
        ):
            check_read_access(make_request("some-cookie"), "any-match", exp="1", sig="deadbeef")
            mock_verify.assert_not_called()
            mock_cookie_owns.assert_not_called()

    # Path 2: signed URL with valid signature
    def test_signed_url_admits_with_valid_signature(self, monkeypatch):
        monkeypatch.delenv("MATCH_REPORT_PUBLIC", raising=False)
        with patch("app.match_report.signing.verify_signed_query", return_value=True) as mock_verify:
            # Should not raise
            check_read_access(
                make_request(),
                "match_signed",
                exp="1000000000",
                sig="abcdef123456",
            )
            # The match id must be bound into the verification, or one valid
            # signature would unlock every report.
            mock_verify.assert_called_once_with("match_signed", "1000000000", "abcdef123456")

    def test_signed_url_rejects_tampered_signature(self, monkeypatch):
        monkeypatch.delenv("MATCH_REPORT_PUBLIC", raising=False)
        with (
            patch("app.match_report.signing.verify_signed_query", return_value=False),
            patch("app.match_report.access.cookie_user_owns", return_value=False),
        ):
            with pytest.raises(HTTPException) as exc_info:
                check_read_access(
                    make_request(),
                    "match_signed",
                    exp="1000000000",
                    sig="tampered",
                )
            assert exc_info.value.status_code == 401

    def test_signed_url_failure_still_falls_back_to_the_owner_cookie(self, monkeypatch):
        """A stale link must not lock the owner out of their own report."""
        monkeypatch.delenv("MATCH_REPORT_PUBLIC", raising=False)
        with (
            patch("app.match_report.signing.verify_signed_query", return_value=False),
            patch("app.match_report.access.cookie_user_owns", return_value=True),
        ):
            # Should not raise
            check_read_access(make_request("owner"), "match_signed", exp="1", sig="expired")

    # Path 3: owner cookie
    def test_owner_cookie_admits(self, monkeypatch):
        monkeypatch.delenv("MATCH_REPORT_PUBLIC", raising=False)
        with patch("app.match_report.access.cookie_user_owns", return_value=True):
            # Should not raise
            check_read_access(make_request("owner"), "match_owned")

    # Fallback: 401 when nothing matches
    def test_raises_401_when_nothing_matches(self, monkeypatch):
        monkeypatch.delenv("MATCH_REPORT_PUBLIC", raising=False)
        with patch("app.match_report.access.cookie_user_owns", return_value=False):
            with pytest.raises(HTTPException) as exc_info:
                check_read_access(make_request(), "match_forbidden")
            assert exc_info.value.status_code == 401
            assert exc_info.value.headers is not None
            assert exc_info.value.headers["WWW-Authenticate"] == "Cookie"

    # Edge: matching both signed URL and cookie — signed takes priority
    def test_signed_url_checked_before_cookie(self, monkeypatch):
        """When both signed params and cookie are present, the signed path
        short-circuits before cookie_user_owns is called."""
        monkeypatch.delenv("MATCH_REPORT_PUBLIC", raising=False)
        with (
            patch("app.match_report.signing.verify_signed_query", return_value=True),
            patch("app.match_report.access.cookie_user_owns") as mock_cookie_owns,
        ):
            check_read_access(
                make_request("some-cookie"),
                "match_signed",
                exp="1000000000",
                sig="abcdef123456",
            )
            # cookie_user_owns must not be called — signed path short-circuits
            mock_cookie_owns.assert_not_called()

    # Edge: no match_id together with exp/sig → signed path not entered
    def test_no_match_id_with_exp_sig_skips_signed_path(self, monkeypatch):
        monkeypatch.delenv("MATCH_REPORT_PUBLIC", raising=False)
        with (
            patch("app.match_report.signing.verify_signed_query") as mock_verify,
            patch("app.match_report.access.cookie_user_owns", return_value=False),
        ):
            with pytest.raises(HTTPException):
                check_read_access(
                    make_request(),
                    None,  # match_id is None
                    exp="1000000000",
                    sig="abcdef",
                )
            # verify_signed_query must not be called when match_id is None
            mock_verify.assert_not_called()

    # Neither exp nor sig present → the signed path is skipped entirely.
    def test_missing_exp_and_sig_skips_signed_path(self, monkeypatch):
        monkeypatch.delenv("MATCH_REPORT_PUBLIC", raising=False)
        with (
            patch("app.match_report.signing.verify_signed_query") as mock_verify,
            patch("app.match_report.access.cookie_user_owns", return_value=True),
        ):
            check_read_access(make_request("owner"), "match_owned")
            mock_verify.assert_not_called()
