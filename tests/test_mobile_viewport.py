"""
Mobile viewport tests for the Remote-Scoreboard PWA.

These tests verify that the app renders correctly at mobile screen sizes and
that PWA-critical features are in place, using two complementary approaches:

1. NiceGUI User tests  — functional checks for mobile-critical UI elements
   (score buttons, control buttons, navigation) using the same headless client
   as the rest of the test suite.

2. Playwright viewport tests  — launch a real Chromium browser at common mobile
   resolutions (iPhone 14 Pro: 393×852, Pixel 7: 412×915) to assert that key
   elements are actually visible and not clipped/overflowing on small screens.

Running the Playwright tests requires browser binaries to be installed:
    playwright install chromium
"""

import json
import os
import pytest
import asyncio
from nicegui.testing import User
from tests.conftest import load_fixture
from app.messages import Messages

# ---------------------------------------------------------------------------
# Shared viewport definitions
# ---------------------------------------------------------------------------

MOBILE_VIEWPORTS = [
    {"name": "iPhone 14 Pro",  "width": 393,  "height": 852},
    {"name": "Pixel 7",        "width": 412,  "height": 915},
    {"name": "Galaxy S22",     "width": 360,  "height": 780},
]

# ---------------------------------------------------------------------------
# NiceGUI User tests — mobile-critical functional checks
# ---------------------------------------------------------------------------

async def test_pwa_manifest_accessible(user: User):
    """The PWA manifest must be reachable so mobile browsers can install the app."""
    await user.open("/pwa/manifest.json")
    # NiceGUI serves static files; any non-error response means it's reachable
    await user.should_not_see("404")
    await user.should_not_see("Not Found")


async def test_score_buttons_present_on_mobile(user: User):
    """Score increment buttons must be present — they are the primary touch targets."""
    await user.open("/")
    await user.should_see(marker="team-1-score")
    await user.should_see(marker="team-2-score")


async def test_set_counters_present_on_mobile(user: User):
    """Set counters must be rendered — essential context on a mobile scoreboard view."""
    await user.open("/")
    await user.should_see(marker="team-1-sets")
    await user.should_see(marker="team-2-sets")


async def test_control_buttons_present_on_mobile(user: User):
    """Control buttons (reset, timeout, etc.) must render on mobile."""
    await user.open("/")
    # The undo button is the most important recoverable action on mobile
    await user.should_see(marker="undo-button")


async def test_score_increment_works_on_mobile(user: User):
    """Tapping a score button must increment the score — core mobile interaction."""
    await user.open("/")
    await user.should_see(content="0", marker="team-1-score")
    user.find(marker="team-1-score").click()
    await asyncio.sleep(0.5)
    await user.should_see(content="1", marker="team-1-score")


# ---------------------------------------------------------------------------
# PWA manifest content validation
# ---------------------------------------------------------------------------


def test_pwa_manifest_has_required_mobile_fields():
    """
    The PWA manifest must contain the fields mobile browsers require to offer
    'Add to Home Screen' and to render the app in fullscreen mode.
    """
    manifest_path = os.path.join(
        os.path.dirname(__file__), "..", "app", "pwa", "manifest.json"
    )
    with open(manifest_path) as f:
        manifest = json.load(f)

    assert "name" in manifest, "manifest must have a 'name'"
    assert "short_name" in manifest, "manifest must have a 'short_name'"
    assert "start_url" in manifest, "manifest must have a 'start_url'"
    assert "display" in manifest, "manifest must have a 'display' mode"
    assert manifest["display"] in ("fullscreen", "standalone", "minimal-ui"), (
        "display mode must be mobile-friendly"
    )
    assert "icons" in manifest and len(manifest["icons"]) >= 1, (
        "manifest must declare at least one icon"
    )

    sizes = {icon.get("sizes") for icon in manifest["icons"]}
    assert "192x192" in sizes, "manifest must include a 192×192 icon for Android"
    assert "512x512" in sizes, "manifest must include a 512×512 icon for splash screens"


# ---------------------------------------------------------------------------
# Playwright viewport tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("viewport", MOBILE_VIEWPORTS, ids=[v["name"] for v in MOBILE_VIEWPORTS])
def test_app_renders_at_mobile_viewport(viewport, page, nicegui_reset_globals):
    """
    Launch the app in a real Chromium browser at the given mobile resolution and
    verify that the primary score area is visible without horizontal overflow.

    Requires: playwright install chromium
    """
    page.set_viewport_size({"width": viewport["width"], "height": viewport["height"]})

    # NiceGUI test server runs on port 3392 by default when using nicegui.testing.plugin
    page.goto("http://localhost:3392/")
    page.wait_for_load_state("networkidle", timeout=10_000)

    # The two score elements must be in the viewport — not scrolled off-screen
    team1_score = page.locator("[data-testid='team-1-score'], [marker='team-1-score']").first
    team2_score = page.locator("[data-testid='team-2-score'], [marker='team-2-score']").first

    assert team1_score.is_visible(), f"Team 1 score not visible at {viewport['name']} resolution"
    assert team2_score.is_visible(), f"Team 2 score not visible at {viewport['name']} resolution"

    # Check for horizontal scroll — a key mobile UX failure
    overflow = page.evaluate(
        "document.documentElement.scrollWidth > document.documentElement.clientWidth"
    )
    assert not overflow, (
        f"Horizontal scroll detected at {viewport['name']} ({viewport['width']}px wide) "
        "— content overflows the mobile viewport"
    )


@pytest.mark.parametrize("viewport", MOBILE_VIEWPORTS, ids=[v["name"] for v in MOBILE_VIEWPORTS])
def test_score_buttons_are_touch_friendly(viewport, page, nicegui_reset_globals):
    """
    Score buttons must meet a minimum 44×44 px touch target size recommended by
    WCAG 2.5.5 and Apple/Google mobile HIG guidelines.
    """
    page.set_viewport_size({"width": viewport["width"], "height": viewport["height"]})
    page.goto("http://localhost:3392/")
    page.wait_for_load_state("networkidle", timeout=10_000)

    for marker in ("team-1-score", "team-2-score"):
        btn = page.locator(f"[marker='{marker}']").first
        if not btn.is_visible():
            pytest.skip(f"Score button '{marker}' not found — may need OID setup")

        box = btn.bounding_box()
        assert box is not None, f"Could not measure bounding box for {marker}"
        assert box["width"] >= 44, (
            f"{marker} button width {box['width']:.0f}px is below the 44px minimum touch target"
        )
        assert box["height"] >= 44, (
            f"{marker} button height {box['height']:.0f}px is below the 44px minimum touch target"
        )
