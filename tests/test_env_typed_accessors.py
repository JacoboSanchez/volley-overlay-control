"""Tests for the typed accessors on :class:`EnvVarsManager`.

These replace ``tests/test_config_validator.py``: validation now happens
where a value is read (so it applies to remote-config deployments too)
rather than in a startup pass that rewrote ``os.environ``.
"""

import logging

import pytest

from app.conf import Conf
from app.env_vars_manager import EnvVarsManager


@pytest.fixture(autouse=True)
def _no_remote_config(monkeypatch):
    """Keep every case on the plain ``os.environ`` path."""
    monkeypatch.delenv("REMOTE_CONFIG_URL", raising=False)
    EnvVarsManager._remote_config_cache = {}
    EnvVarsManager._cache_timestamp = 0
    yield
    EnvVarsManager._remote_config_cache = {}
    EnvVarsManager._cache_timestamp = 0


class TestGetIntEnv:
    def test_unset_returns_default(self):
        assert EnvVarsManager.get_int_env("VOC_TEST_INT", 7) == 7

    def test_valid_value_is_parsed(self, monkeypatch):
        monkeypatch.setenv("VOC_TEST_INT", "21")
        assert EnvVarsManager.get_int_env("VOC_TEST_INT", 25) == 21

    @pytest.mark.parametrize("raw", ["", "   ", "abc", "1.5"])
    def test_unusable_value_falls_back(self, monkeypatch, raw):
        monkeypatch.setenv("VOC_TEST_INT", raw)
        assert EnvVarsManager.get_int_env("VOC_TEST_INT", 25) == 25

    def test_below_minimum_falls_back_and_warns(self, monkeypatch, caplog):
        monkeypatch.setenv("VOC_TEST_INT", "-5")
        with caplog.at_level(logging.WARNING):
            assert EnvVarsManager.get_int_env("VOC_TEST_INT", 25, minimum=1) == 25
        assert any("VOC_TEST_INT" in r.message for r in caplog.records)

    def test_above_maximum_falls_back(self, monkeypatch):
        monkeypatch.setenv("VOC_TEST_INT", "99999")
        port = EnvVarsManager.get_int_env(
            "VOC_TEST_INT", 8080, minimum=1, maximum=65535,
        )
        assert port == 8080

    def test_zero_allowed_when_minimum_is_zero(self, monkeypatch):
        monkeypatch.setenv("VOC_TEST_INT", "0")
        assert EnvVarsManager.get_int_env("VOC_TEST_INT", 5, minimum=0) == 0

    def test_garbage_warns_once_with_the_key_name(self, monkeypatch, caplog):
        monkeypatch.setenv("VOC_TEST_INT", "notanumber")
        with caplog.at_level(logging.WARNING):
            EnvVarsManager.get_int_env("VOC_TEST_INT", 25)
        assert len([r for r in caplog.records if "VOC_TEST_INT" in r.message]) == 1


class TestGetFloatEnv:
    def test_valid_value_is_parsed(self, monkeypatch):
        monkeypatch.setenv("VOC_TEST_FLOAT", "0.5")
        assert EnvVarsManager.get_float_env("VOC_TEST_FLOAT", 2.0) == 0.5

    def test_exclusive_minimum_rejects_the_bound(self, monkeypatch):
        # A 0s timeout is never what the operator meant.
        monkeypatch.setenv("VOC_TEST_FLOAT", "0")
        value = EnvVarsManager.get_float_env(
            "VOC_TEST_FLOAT", 2.0, exclusive_minimum=0.0,
        )
        assert value == 2.0

    def test_inclusive_minimum_accepts_zero(self, monkeypatch):
        # ...but where 0 means "disabled" it must survive.
        monkeypatch.setenv("VOC_TEST_FLOAT", "0")
        assert EnvVarsManager.get_float_env("VOC_TEST_FLOAT", 2.0, minimum=0.0) == 0.0

    def test_garbage_falls_back(self, monkeypatch):
        monkeypatch.setenv("VOC_TEST_FLOAT", "fast")
        assert EnvVarsManager.get_float_env("VOC_TEST_FLOAT", 2.0) == 2.0

    @pytest.mark.parametrize("raw", ["nan", "NaN", "inf", "-inf", "infinity"])
    def test_non_finite_values_are_rejected(self, monkeypatch, raw):
        """``float()`` accepts these and every bound comparison against NaN
        is False, so an unchecked NaN would pass the range check and reach
        an ``asyncio.wait_for`` timeout."""
        monkeypatch.setenv("VOC_TEST_FLOAT", raw)
        value = EnvVarsManager.get_float_env(
            "VOC_TEST_FLOAT", 2.0, exclusive_minimum=0.0,
        )
        assert value == 2.0


class TestGetEnumEnv:
    _LEVELS = ("debug", "info", "warning", "error", "critical")

    def test_value_is_normalised_to_lower_case(self, monkeypatch):
        monkeypatch.setenv("VOC_TEST_ENUM", "  DEBUG ")
        assert EnvVarsManager.get_enum_env("VOC_TEST_ENUM", "warning", self._LEVELS) == "debug"

    def test_unknown_value_falls_back_and_warns(self, monkeypatch, caplog):
        monkeypatch.setenv("VOC_TEST_ENUM", "superdebug")
        with caplog.at_level(logging.WARNING):
            resolved = EnvVarsManager.get_enum_env(
                "VOC_TEST_ENUM", "warning", self._LEVELS,
            )
        assert resolved == "warning"
        assert any("VOC_TEST_ENUM" in r.message for r in caplog.records)

    def test_unset_returns_default(self):
        assert EnvVarsManager.get_enum_env("VOC_TEST_ENUM", "text", ("text", "json")) == "text"


class TestMatchRulesValidation:
    """``Conf`` clamps its match knobs itself, on every read path."""

    def test_valid_override_is_honoured(self, monkeypatch):
        monkeypatch.setenv("MATCH_GAME_POINTS", "21")
        assert Conf().points == 21

    @pytest.mark.parametrize("raw", ["invalid", "-5", "0"])
    def test_unusable_override_falls_back_to_the_default(self, monkeypatch, raw):
        monkeypatch.setenv("MATCH_GAME_POINTS", raw)
        monkeypatch.setenv("MATCH_SETS", raw)
        conf = Conf()
        assert conf.points == 25
        assert conf.sets == 5

    def test_remote_config_values_are_validated_too(self, monkeypatch):
        """The regression this refactor fixes.

        The old startup validator clamped ``os.environ`` only, while ``Conf``
        reads through the remote-config cache — so a remote
        ``MATCH_GAME_POINTS=-5`` reached the match rules unvalidated.
        """
        monkeypatch.setenv("REMOTE_CONFIG_URL", "http://config.example/env.json")
        EnvVarsManager._remote_config_cache = {"MATCH_GAME_POINTS": -5}
        EnvVarsManager._cache_timestamp = float("inf")  # never refetch

        assert Conf().points == 25

    def test_remote_config_supplies_valid_values(self, monkeypatch):
        monkeypatch.setenv("REMOTE_CONFIG_URL", "http://config.example/env.json")
        EnvVarsManager._remote_config_cache = {"MATCH_GAME_POINTS": "15"}
        EnvVarsManager._cache_timestamp = float("inf")

        assert Conf().points == 15


class TestJsonTypedRemoteValues:
    """Remote config is JSON, so a value arrives already typed.

    ``int()`` accepts what the equivalent local string rejects — it
    truncates ``1.9`` to ``1`` and turns ``True`` into ``1`` — so a
    fractional ``MATCH_SETS`` would silently become a one-set match.
    """

    @pytest.fixture(autouse=True)
    def _remote_cache(self, monkeypatch):
        monkeypatch.setenv("REMOTE_CONFIG_URL", "http://config.example/env.json")
        EnvVarsManager._cache_timestamp = float("inf")  # never refetch

    def _remote(self, value):
        EnvVarsManager._remote_config_cache = {"VOC_REMOTE": value}

    def test_fractional_number_is_rejected(self):
        self._remote(1.9)
        assert EnvVarsManager.get_int_env("VOC_REMOTE", 5, minimum=1) == 5

    def test_integral_float_is_accepted(self):
        # A configurator that serialises every number as a float must keep
        # working — 5.0 converts losslessly.
        self._remote(5.0)
        assert EnvVarsManager.get_int_env("VOC_REMOTE", 3, minimum=1) == 5

    def test_json_integer_is_accepted(self):
        self._remote(21)
        assert EnvVarsManager.get_int_env("VOC_REMOTE", 25, minimum=1) == 21

    @pytest.mark.parametrize("value", [True, False])
    def test_booleans_are_rejected(self, value):
        self._remote(value)
        assert EnvVarsManager.get_int_env("VOC_REMOTE", 5, minimum=1) == 5
        assert EnvVarsManager.get_float_env("VOC_REMOTE", 2.0) == 2.0

    def test_float_accessor_takes_json_numbers(self):
        self._remote(0.25)
        assert EnvVarsManager.get_float_env("VOC_REMOTE", 2.0) == 0.25
