"""Tests for per-style UI capability detection (theme / vertical-anchor).

The capabilities are scanned from the real on-disk templates and CSS so the
control UI only offers a knob where it has a visible effect.
"""

import os

import pytest

from app.overlay.state_store import OverlayStateStore

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TEMPLATES_DIR = os.path.join(_REPO_ROOT, "overlay_templates")


@pytest.fixture
def store(tmp_path):
    return OverlayStateStore(
        data_dir=str(tmp_path / "data"),
        templates_dir=_TEMPLATES_DIR,
    )


def test_pylons_supports_both_theme_and_vertical_anchor(store):
    caps = store.get_style_capabilities()
    assert caps["pylons"] == {"verticalAnchor": True, "theme": True}
    assert caps["pylons_gradient"]["verticalAnchor"] is True


def test_default_style_exposes_no_special_knobs(store):
    caps = store.get_style_capabilities()
    # The default template honours operator geometry and ships no
    # overlay-theme override, so neither knob should be offered.
    assert caps["default"] == {"verticalAnchor": False, "theme": False}


def test_theme_only_style_has_no_vertical_anchor(store):
    """A themed but geometry-driven style gets theme, not vertical anchor."""
    caps = store.get_style_capabilities()
    # ``clear_jersey`` pulls its theme override in via @import jersey_shared.css,
    # exercising the one-level import follow.
    assert caps["clear_jersey"]["theme"] is True
    assert caps["clear_jersey"]["verticalAnchor"] is False


def test_capabilities_cover_every_available_style(store):
    caps = store.get_style_capabilities()
    assert set(caps) == set(store.get_available_styles_list())


def test_capabilities_are_cached(store):
    first = store.get_style_capabilities()
    assert store.get_style_capabilities() is first
