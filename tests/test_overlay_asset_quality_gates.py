"""Keep the on-air overlay assets inside the JavaScript/CSS quality gates."""

import json
import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def test_frontend_scripts_cover_first_party_overlay_assets() -> None:
    package = json.loads(_read("frontend/package.json"))
    scripts = package["scripts"]

    assert "npm run lint:overlays" in scripts["lint"]
    assert "overlay_static/js" in scripts["lint:overlays"]
    assert "../overlay_static/js" in scripts["format:check"]
    assert "../overlay_static/css" in scripts["format:check"]
    assert "../overlay_static/css" in scripts["stylelint"]


def test_eslint_config_covers_browser_scripts_but_excludes_vendored_gsap() -> None:
    config = _read("frontend/eslint.config.js")
    prettier_ignore = _read("frontend/.prettierignore")

    assert "overlay_static/js/**/*.js" in config
    assert "...globals.browser" in config
    assert "'no-undef': 'error'" in config
    assert "'no-unused-vars': [" in config
    assert "overlay_static/js/gsap.min.js" in config
    assert "../overlay_static/js/gsap.min.js" in prettier_ignore


def test_precommit_hooks_cover_overlay_javascript_and_css() -> None:
    config = yaml.safe_load(_read(".pre-commit-config.yaml"))
    hooks = {
        hook["id"]: hook
        for repo in config["repos"]
        if repo["repo"] == "local"
        for hook in repo["hooks"]
    }

    assert "overlay_static/" in hooks["frontend-prettier"]["files"]
    assert "overlay_static/js/" in hooks["frontend-eslint"]["files"]
    assert "overlay_static/css/" in hooks["overlay-stylelint"]["files"]
    assert "npm run stylelint" in hooks["overlay-stylelint"]["entry"]


def test_long_team_names_keep_an_older_obs_wrapping_fallback() -> None:
    fallback = "overflow-wrap: break-word;\n  overflow-wrap: anywhere;"

    for stylesheet in (
        "overlay_static/css/corners_shared.css",
        "overlay_static/css/spectator.css",
        "overlay_static/css/vertical.css",
    ):
        assert fallback in _read(stylesheet), stylesheet


def test_neon_compact_mode_collapses_the_whole_header() -> None:
    """Simple mode must hide `neon`'s header, chips and set label alike.

    The header carries a ``min-height``, which would win over the
    ``max-height: 0`` collapse and leave an 18px stub across the top of
    the card — so both have to be zeroed together.
    """
    css = _read("overlay_static/css/neon.css")

    match = re.search(r"\.compact-mode \.head \{([^}]*)\}", css)
    assert match, "neon.css no longer collapses .head in compact mode"
    block = match.group(1)

    for declaration in ("max-height: 0", "min-height: 0"):
        assert declaration in block, declaration
