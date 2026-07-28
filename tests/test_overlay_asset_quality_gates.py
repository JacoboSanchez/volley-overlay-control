"""Keep the on-air overlay assets inside the JavaScript/CSS quality gates."""

import json
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
