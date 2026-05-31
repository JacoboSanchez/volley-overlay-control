let previousState = null;
let socket = null;
let heartbeatInterval = null;

// Restrict <img src> values coming from remote state to http(s) so a
// malicious logo_url (javascript:, data:, vbscript:, …) cannot turn into XSS.
function sanitizeImageUrl(url) {
    if (typeof url !== 'string' || url === '') return '';
    try {
        const parsed = new URL(url, window.location.origin);
        if (parsed.protocol === 'http:' || parsed.protocol === 'https:') {
            return parsed.href;
        }
    } catch (_e) {
        // Malformed URL — fall through and reject.
    }
    return '';
}

// Look up an element by id and invoke fn only if it exists. Overlay templates
// (compact, pill, ribbon, …) don't all render the same DOM, so bare
// `getElementById(id).prop = …` throws on the missing nodes and aborts the
// render. Funnel every optional write through this helper.
function withEl(id, fn) {
    const el = document.getElementById(id);
    if (el) fn(el);
}

// Send a "ping" to the server every 30 s so long-lived connections don't
// silently drop without triggering the onclose reconnect logic.
function startHeartbeat() {
    stopHeartbeat();
    heartbeatInterval = setInterval(() => {
        if (socket && socket.readyState === WebSocket.OPEN) {
            socket.send("ping");
        }
    }, 30000);
}

function stopHeartbeat() {
    if (heartbeatInterval) {
        clearInterval(heartbeatInterval);
        heartbeatInterval = null;
    }
}

function connectWebSocket() {
    console.log(`Connecting to WebSocket: ${wsUrl}`);
    socket = new WebSocket(wsUrl);

    socket.onopen = () => {
        console.log("WebSocket connected");
        startHeartbeat();
    };

    socket.onmessage = (event) => {
        // Ignore "pong" responses from our heartbeat ping
        if (event.data === "pong") return;
        try {
            const state = JSON.parse(event.data);
            processStateUpdate(state);
        } catch (e) {
            console.error("Error parsing WebSocket message:", e);
        }
    };

    socket.onclose = () => {
        console.log("WebSocket connection closed, reconnecting in 2s...");
        stopHeartbeat();
        setTimeout(connectWebSocket, 2000);
    };

    socket.onerror = (error) => {
        console.error("WebSocket error:", error);
        socket.close();
    };
}

// Supported locales — mirrors match_report_i18n.SUPPORTED_LOCALES on
// the backend and the LABELS keys in set_summary.js / spectator.js.
const SUPPORTED_OVERLAY_LOCALES = new Set(['en', 'es', 'pt', 'it', 'fr', 'de']);

// Re-applied on every state push so a locale change pushed by the
// operator (via raw_remote_customization.locale) lands before the next
// SetSummary.render(state) — the OBS browser source URL is fixed in
// the streaming app so we can't carry the locale in the URL.
function applyStateLocale(state) {
    const next = state && state.raw_remote_customization
        ? state.raw_remote_customization.locale
        : null;
    if (!next || typeof next !== 'string') return;
    const candidate = next.slice(0, 2).toLowerCase();
    if (SUPPORTED_OVERLAY_LOCALES.has(candidate)) {
        window.OVERLAY_LOCALE = candidate;
    }
}

function processStateUpdate(newState) {
    applyStateLocale(newState);
    if (!previousState) {
        // Initial render
        renderFullState(newState);
    } else {
        // Diff and apply
        updateStateDiff(previousState, newState);
    }
    previousState = structuredClone(newState);
}

/* Return true when a hex colour is white or very close to white. */
function isNearWhite(hex) {
    if (!hex || typeof hex !== 'string') return false;
    let h = hex.replace('#', '');
    // Expand 3-char shorthand (#FFF → FFFFFF)
    if (h.length === 3) h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2];
    if (!/^[0-9a-fA-F]{6}$/.test(h)) return false;
    const r = parseInt(h.substring(0, 2), 16);
    const g = parseInt(h.substring(2, 4), 16);
    const b = parseInt(h.substring(4, 6), 16);
    // Perceived luminance (rec-709) — threshold tuned so only very
    // light colours (e.g. #F0F0F0+) are considered "near white".
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) > 230;
}

function updateCSSVariables(teamHome, teamAway, colors = null) {
    const root = document.documentElement;
    root.style.setProperty('--home-primary', teamHome.color_primary);
    root.style.setProperty('--home-secondary', teamHome.color_secondary);
    if (teamHome.color_secondary) root.style.setProperty('--home-text', teamHome.color_secondary);
    root.style.setProperty('--away-primary', teamAway.color_primary);
    root.style.setProperty('--away-secondary', teamAway.color_secondary);
    if (teamAway.color_secondary) root.style.setProperty('--away-text', teamAway.color_secondary);

    // For the score-section gradient: fall back to the team's text
    // colour when the primary is white/near-white so the tint stays
    // visible against the light neumorphic background.
    root.style.setProperty('--home-gradient',
        isNearWhite(teamHome.color_primary) ? (teamHome.color_secondary || teamHome.color_primary) : teamHome.color_primary);
    root.style.setProperty('--away-gradient',
        isNearWhite(teamAway.color_primary) ? (teamAway.color_secondary || teamAway.color_primary) : teamAway.color_primary);

    if (colors) {
        if (colors.set_bg) root.style.setProperty('--set-bg', colors.set_bg);
        if (colors.set_text) root.style.setProperty('--set-text', colors.set_text);
        if (colors.game_bg) root.style.setProperty('--game-bg', colors.game_bg);
        if (colors.game_text) root.style.setProperty('--game-text', colors.game_text);
    }
}

function updateGeometry(geometry) {
    const container = document.getElementById("pill-wrapper") || document.getElementById("scoreboard-container");
    if (!container || !geometry) return;

    // Use a reference width. The overlay is designed at 1920x1080.
    // The "width" from customization is typically a percentage (e.g., 30 for 30%)
    const targetWidth = (geometry.width / 100) * 1920;

    // Calculate the scale needed. Because the container has a min-width (e.g., 600px),
    // and its actual width depends on the content, we'll scale it down/up based on a
    // baseline width (let's assume the baseline is ~800px or use the dynamic clientWidth)
    // A simpler approach is to apply the scale directly based on the percentage requested.
    // Let's assume a default scale of 1.0 for width=30%. 
    const baseWidthPercentage = 30.0;
    const scale = geometry.width / baseWidthPercentage;

    // The customization page sends x/y offset from -50 to +50 roughly.
    // Let's map these to pixels or vw/vh.
    // Xpos: -50 means left edge, 50 means right edge
    // Ypos: -50 means top edge, 50 means bottom edge

    // Convert -50..50 to 0..100vw/vh roughly.
    const leftPx = ((geometry.xpos + 50) / 100) * 1920;
    const topPx = ((geometry.ypos + 50) / 100) * 1080;

    gsap.set(container, {
        scale: scale,
        left: leftPx,
        top: topPx
    });
}

function animatePoints(elementId, newPoints) {
    // Kill any in-progress animation and remove the stale intermediate element
    const existingNew = document.getElementById(elementId + "-new");
    if (existingNew) {
        gsap.killTweensOf(existingNew);
        existingNew.remove();
    }

    const el = document.getElementById(elementId);
    if (!el) return;

    gsap.killTweensOf(el);
    gsap.set(el, { y: 0, opacity: 1 });

    // Create new point element
    const container = el.parentElement;
    const newEl = document.createElement("div");
    newEl.className = "points";
    newEl.id = elementId + "-new";
    newEl.textContent = newPoints;

    // Position it below
    gsap.set(newEl, { y: 40, opacity: 0 });
    container.appendChild(newEl);

    // Animate old element out
    gsap.to(el, {
        y: -40,
        opacity: 0,
        duration: 0.4,
        ease: "power2.inOut",
        onComplete: () => {
            el.remove();
            newEl.id = elementId; // Reassign ID to new element
        }
    });

    // Animate new element in
    gsap.to(newEl, {
        y: 0,
        opacity: 1,
        duration: 0.4,
        ease: "power2.inOut"
    });
}

function updateLogoVisibility(showLogos) {
    const homeLogo = document.getElementById("home-logo");
    const awayLogo = document.getElementById("away-logo");
    [homeLogo, awayLogo].forEach(img => {
        if (!img) return;
        const container = img.parentElement;
        if (showLogos) {
            if (container) container.style.display = '';
            img.style.removeProperty('display');
        } else {
            if (container) container.style.display = 'none';
        }
    });
    // Toggle layout class so .name-panel offsets adjust when logos are hidden
    const scoreboard = document.getElementById("scoreboard-container");
    if (scoreboard) scoreboard.classList.toggle('no-logos', !showLogos);
}

function renderFullState(state) {
    // 1. Overlay Visibility & Geometry
    if (state.overlay_control.geometry) {
        updateGeometry(state.overlay_control.geometry);
    }

    withEl("scoreboard-container", container => {
        if (state.overlay_control.show_main_scoreboard) {
            gsap.to(container, { x: 0, opacity: 1, duration: 0.8, ease: "power3.out" });
        } else {
            gsap.to(container, { x: -100, opacity: 0, duration: 0.5, ease: "power2.in" });
        }
        // Compact mode toggle (used by compact overlay to hide name/history)
        container.classList.toggle("compact-mode", !!state.match_info.show_only_current_set);
    });

    // Set summary recap panel (replaces the scoreboard between sets).
    // Toggled from the operator UI; CSS hides the scoreboard when the
    // body has `set-summary-mode`.
    const summaryOn = !!(state.match_info && state.match_info.show_set_summary);
    document.body.classList.toggle("set-summary-mode", summaryOn);
    if (summaryOn && window.SetSummary) {
        window.SetSummary.render(state);
    } else if (window.SetSummary) {
        window.SetSummary.hide();
    }

    // 2. Colors
    updateCSSVariables(state.team_home, state.team_away, state.overlay_control.colors);

    // 3. Match Info Removed

    // 4. Team Names & Logos
    withEl("home-name", el => { el.textContent = state.team_home.name; });
    withEl("away-name", el => { el.textContent = state.team_away.name; });
    equalizeNamePanels();
    fitBeachNames();

    // 4b. Logo visibility toggle (from remote-scoreboard "Logos" setting).
    // Run before the per-logo URL branches so those have the final say on
    // `display` — otherwise updateLogoVisibility clears our `display:'none'`
    // when a team has no logo_url and we end up rendering a broken image.
    const showLogos = state.overlay_control.show_logos !== false;
    updateLogoVisibility(showLogos);

    withEl("home-logo", logo => {
        const url = sanitizeImageUrl(state.team_home.logo_url);
        if (url) {
            logo.src = url;
            logo.style.display = 'block';
        } else {
            logo.style.display = 'none';
        }
    });

    withEl("away-logo", logo => {
        const url = sanitizeImageUrl(state.team_away.logo_url);
        if (url) {
            logo.src = url;
            logo.style.display = 'block';
        } else {
            logo.style.display = 'none';
        }
    });

    // 5. Points & Sets
    withEl("home-points", el => { el.textContent = state.team_home.points; });
    withEl("away-points", el => { el.textContent = state.team_away.points; });
    withEl("home-sets", el => { el.textContent = state.team_home.sets_won; });
    withEl("away-sets", el => { el.textContent = state.team_away.sets_won; });

    // 6. Serving Indicator
    withEl("home-serving", el => el.classList.toggle("active", state.team_home.serving));
    withEl("away-serving", el => el.classList.toggle("active", state.team_away.serving));

    // 7. Timeouts & Set History
    updateTimeouts('home', state.team_home.timeouts_taken);
    updateTimeouts('away', state.team_away.timeouts_taken);
    renderSetHistory(state, true);

    // 7b. Current Set Label
    withEl("current-set-label", el => { el.textContent = "SET " + state.match_info.current_set; });

    // 8. Bottom Ticker
    withEl("ticker-message", el => { el.textContent = state.overlay_control.ticker_message || ""; });
    withEl("ticker-container", tickerContainer => {
        if (state.overlay_control.show_bottom_ticker) {
            gsap.to(tickerContainer, { y: 0, opacity: 1, duration: 0.8, ease: "power3.out" });
        } else {
            gsap.set(tickerContainer, { y: 100, opacity: 0 });
        }
    });

    // 9. Player Stats
    renderPlayerStats(state.overlay_control.player_stats_data);
    withEl("player-stats-container", statsContainer => {
        if (state.overlay_control.show_player_stats) {
            gsap.to(statsContainer, { x: 0, opacity: 1, duration: 0.8, ease: "power3.out" });
        } else {
            gsap.set(statsContainer, { x: -100, opacity: 0 });
        }
    });

    // 10. Live stats panel + points history strip (opt-in per overlay).
    renderLiveStats(state);
    renderPointsHistory(state);
}

function updateStateDiff(oldState, newState) {
    // Check if the overall style template changed.
    // If so, the easiest architecture is to reload the browser source to process the new CSS/HTML template.
    // Compare against the style actually loaded by this page (window.OVERLAY_STYLE) to avoid a spurious
    // reload when preferredStyle is first set and the page is already showing the correct style.
    if (oldState.overlay_control.preferredStyle !== newState.overlay_control.preferredStyle) {
        const currentStyle = window.OVERLAY_STYLE || 'default';
        const newStyle = newState.overlay_control.preferredStyle || 'default';
        if (newStyle !== currentStyle) {
            window.location.reload();
            return;
        }
        // New preferredStyle already matches the loaded page — no reload needed, continue updating DOM.
    }

    // Visibility
    if (oldState.overlay_control.show_main_scoreboard !== newState.overlay_control.show_main_scoreboard) {
        withEl("scoreboard-container", container => {
            if (newState.overlay_control.show_main_scoreboard) {
                gsap.to(container, { x: 0, opacity: 1, duration: 0.8, ease: "power3.out" });
            } else {
                gsap.to(container, { x: -100, opacity: 0, duration: 0.5, ease: "power2.in" });
            }
        });
    }

    // Geometry
    if (JSON.stringify(oldState.overlay_control.geometry) !== JSON.stringify(newState.overlay_control.geometry)) {
        updateGeometry(newState.overlay_control.geometry);
    }

    // Colors
    if (oldState.team_home.color_primary !== newState.team_home.color_primary ||
        oldState.team_home.color_secondary !== newState.team_home.color_secondary ||
        oldState.team_away.color_primary !== newState.team_away.color_primary ||
        oldState.team_away.color_secondary !== newState.team_away.color_secondary ||
        JSON.stringify(oldState.overlay_control.colors) !== JSON.stringify(newState.overlay_control.colors)) {
        updateCSSVariables(newState.team_home, newState.team_away, newState.overlay_control.colors);
    }

    // Team Names
    if (oldState.team_home.name !== newState.team_home.name) {
        withEl("home-name", el => { el.textContent = newState.team_home.name; });
    }
    if (oldState.team_away.name !== newState.team_away.name) {
        withEl("away-name", el => { el.textContent = newState.team_away.name; });
    }
    if (oldState.team_home.name !== newState.team_home.name ||
        oldState.team_away.name !== newState.team_away.name) {
        equalizeNamePanels();
        fitBeachNames();
    }

    // Logo visibility toggle (runs before per-logo URL updates so the
    // per-logo `display:'none'` branch below isn't cleared by
    // updateLogoVisibility's `removeProperty('display')`, matching the
    // ordering in renderFullState).
    if (oldState.overlay_control.show_logos !== newState.overlay_control.show_logos) {
        updateLogoVisibility(newState.overlay_control.show_logos !== false);
    }

    // Logos
    if (oldState.team_home.logo_url !== newState.team_home.logo_url) {
        withEl("home-logo", logo => {
            const safeUrl = sanitizeImageUrl(newState.team_home.logo_url);
            if (safeUrl) {
                logo.src = safeUrl;
                logo.style.display = 'block';
            } else {
                logo.style.display = 'none';
            }
        });
    }
    if (oldState.team_away.logo_url !== newState.team_away.logo_url) {
        withEl("away-logo", logo => {
            const safeUrl = sanitizeImageUrl(newState.team_away.logo_url);
            if (safeUrl) {
                logo.src = safeUrl;
                logo.style.display = 'block';
            } else {
                logo.style.display = 'none';
            }
        });
    }

    // Points
    if (oldState.team_home.points !== newState.team_home.points) {
        animatePoints("home-points", newState.team_home.points);
    }
    if (oldState.team_away.points !== newState.team_away.points) {
        animatePoints("away-points", newState.team_away.points);
    }

    // Sets
    if (oldState.team_home.sets_won !== newState.team_home.sets_won) {
        withEl("home-sets", el => {
            gsap.to(el, { scale: 1.2, duration: 0.2, yoyo: true, repeat: 1 });
            el.textContent = newState.team_home.sets_won;
        });
    }
    if (oldState.team_away.sets_won !== newState.team_away.sets_won) {
        withEl("away-sets", el => {
            gsap.to(el, { scale: 1.2, duration: 0.2, yoyo: true, repeat: 1 });
            el.textContent = newState.team_away.sets_won;
        });
    }

    // Serving
    if (oldState.team_home.serving !== newState.team_home.serving) {
        withEl("home-serving", el => el.classList.toggle("active", newState.team_home.serving));
    }
    if (oldState.team_away.serving !== newState.team_away.serving) {
        withEl("away-serving", el => el.classList.toggle("active", newState.team_away.serving));
    }

    // Timeouts
    if (oldState.team_home.timeouts_taken !== newState.team_home.timeouts_taken) {
        updateTimeouts('home', newState.team_home.timeouts_taken);
    }
    if (oldState.team_away.timeouts_taken !== newState.team_away.timeouts_taken) {
        updateTimeouts('away', newState.team_away.timeouts_taken);
    }

    // Set History
    if (oldState.match_info.current_set !== newState.match_info.current_set ||
        oldState.match_info.show_only_current_set !== newState.match_info.show_only_current_set ||
        JSON.stringify(oldState.team_home.set_history) !== JSON.stringify(newState.team_home.set_history) ||
        JSON.stringify(oldState.team_away.set_history) !== JSON.stringify(newState.team_away.set_history)) {
        renderSetHistory(newState, false);
    }

    // Current Set Label
    if (oldState.match_info.current_set !== newState.match_info.current_set) {
        withEl("current-set-label", el => { el.textContent = "SET " + newState.match_info.current_set; });
    }

    // Compact mode toggle
    if (oldState.match_info.show_only_current_set !== newState.match_info.show_only_current_set) {
        withEl("scoreboard-container", container => {
            container.classList.toggle("compact-mode", !!newState.match_info.show_only_current_set);
        });
        // Re-fit beach names only when they reappear leaving compact mode;
        // entering it hides the names and CSS pins the bar width, so a
        // re-fit there would be a wasted reflow.
        if (!newState.match_info.show_only_current_set) {
            fitBeachNames();
        }
    }

    // Set summary recap panel toggle / re-render. Re-render also on
    // style or set-num changes so the operator can hot-swap styles
    // mid-display without taking the panel down.
    const newSummary = !!newState.match_info.show_set_summary;
    const oldSummary = !!oldState.match_info.show_set_summary;
    if (
        oldSummary !== newSummary
        || oldState.match_info.set_summary_style !== newState.match_info.set_summary_style
        || oldState.match_info.summary_set_num !== newState.match_info.summary_set_num
    ) {
        document.body.classList.toggle("set-summary-mode", newSummary);
        if (newSummary && window.SetSummary) {
            window.SetSummary.render(newState);
        } else if (window.SetSummary) {
            window.SetSummary.hide();
        }
    } else if (newSummary && window.SetSummary) {
        // Same flag/style/set, but stats may have changed (e.g. the
        // operator added a point right after activating the recap).
        window.SetSummary.render(newState);
    }

    // 8. Ticker
    if (oldState.overlay_control.show_bottom_ticker !== newState.overlay_control.show_bottom_ticker) {
        withEl("ticker-container", tickerContainer => {
            if (newState.overlay_control.show_bottom_ticker) {
                gsap.to(tickerContainer, { y: 0, opacity: 1, duration: 0.8, ease: "power3.out" });
            } else {
                gsap.to(tickerContainer, { y: 100, opacity: 0, duration: 0.5, ease: "power2.in" });
            }
        });
    }
    if (oldState.overlay_control.ticker_message !== newState.overlay_control.ticker_message) {
        withEl("ticker-message", tickerMessage => {
            gsap.to(tickerMessage, {
                opacity: 0, y: -20, duration: 0.3, onComplete: () => {
                    tickerMessage.textContent = newState.overlay_control.ticker_message || "";
                    gsap.fromTo(tickerMessage, { opacity: 0, y: 20 }, { opacity: 1, y: 0, duration: 0.3 });
                }
            });
        });
    }

    // 9. Player Stats
    if (oldState.overlay_control.show_player_stats !== newState.overlay_control.show_player_stats) {
        withEl("player-stats-container", statsContainer => {
            if (newState.overlay_control.show_player_stats) {
                gsap.to(statsContainer, { x: 0, opacity: 1, duration: 0.8, ease: "power3.out" });
            } else {
                gsap.to(statsContainer, { x: -100, opacity: 0, duration: 0.5, ease: "power2.in" });
            }
        });
    }
    if (JSON.stringify(oldState.overlay_control.player_stats_data) !== JSON.stringify(newState.overlay_control.player_stats_data)) {
        renderPlayerStats(newState.overlay_control.player_stats_data);
    }

    // 10. Live stats + points history. Both rerender unconditionally
    // because the underlying stats payload can change on every point
    // even when the toggles themselves don't move; the render
    // functions handle the hidden-by-default case internally.
    const oldOC = oldState.overlay_control || {};
    const newOC = newState.overlay_control || {};
    if (
        oldOC.show_stats !== newOC.show_stats
        || JSON.stringify(oldOC.stats) !== JSON.stringify(newOC.stats)
    ) {
        renderLiveStats(newState);
    }
    if (
        oldOC.show_points_history !== newOC.show_points_history
        || JSON.stringify(oldOC.points_history) !== JSON.stringify(newOC.points_history)
    ) {
        renderPointsHistory(newState);
    }

    // Phase 3 — set-won + match-finished glows. Sits at the end of
    // the diff so the panel/score updates land first; the alert
    // helper restarts the keyframe via a forced reflow if the same
    // class re-applies on a rapid follow-up event.
    dispatchAlertTransitions(oldState, newState);
}

// ── Beach name fitting ───────────────────────────────────────────────
// The beach board keeps both name bars symmetric. Rather than clipping a
// long name with an ellipsis, widen both bars to fit the longer of the two
// names, and only when that would exceed BEACH_NAME_MAX_BAR shrink the type
// (down to BEACH_NAME_MIN_FONT) so the full name still shows. Both sides
// always share the same width and font size.
const BEACH_NAME_BASE_FONT = 29;  // matches .team-name font-size in beach.css
const BEACH_NAME_MIN_FONT = 16;
const BEACH_NAME_MIN_BAR = 260;
const BEACH_NAME_MAX_BAR = 480;
const BEACH_NAME_PADDING = 44;    // .name-bar horizontal padding (2 * 22px)
let beachFontsHooked = false;

// Measure the rendered width of a beach team name at a given font size with
// an offscreen node, so the live (possibly clipped) element is untouched and
// short names report their true width.
function measureBeachName(text, fontSize) {
    let m = document.getElementById("beach-name-measure");
    if (!m) {
        m = document.createElement("span");
        m.id = "beach-name-measure";
        m.style.position = "absolute";
        m.style.left = "-9999px";
        m.style.top = "0";
        m.style.visibility = "hidden";
        m.style.whiteSpace = "nowrap";
        m.style.fontFamily = "'Montserrat', sans-serif";
        m.style.fontWeight = "800";
        m.style.textTransform = "uppercase";
        m.style.letterSpacing = "1px";
        document.body.appendChild(m);
    }
    m.style.fontSize = fontSize + "px";
    m.textContent = text || "";
    return m.offsetWidth;
}

function fitBeachNames() {
    const container = document.getElementById("scoreboard-container");
    const homeName = document.getElementById("home-name");
    const awayName = document.getElementById("away-name");
    if (!container || !homeName || !awayName) return;
    // Only the beach template uses `.name-bar`; bail out for every other style.
    if (!container.querySelector(".name-bar")) return;

    // The first measurement can land before the Montserrat webfont loads
    // (fallback metrics differ). Re-fit once it is ready, just once.
    if (document.fonts && !beachFontsHooked) {
        beachFontsHooked = true;
        document.fonts.ready.then(() => fitBeachNames());
    }

    const homeText = homeName.textContent || "";
    const awayText = awayName.textContent || "";

    // Shrink the type one step at a time, re-measuring each time, until the
    // longer name fits the widest bar we allow (or we hit the legibility
    // floor). We can't shrink proportionally in a single step because the
    // fixed 1px letter-spacing does not scale with the font size, so a
    // proportional guess lands a few pixels too wide and the name still
    // clips — the measured loop accounts for it exactly.
    const maxContent = BEACH_NAME_MAX_BAR - BEACH_NAME_PADDING;
    let fontSize = BEACH_NAME_BASE_FONT;
    let maxText = Math.max(
        measureBeachName(homeText, fontSize),
        measureBeachName(awayText, fontSize)
    );
    while (maxText > maxContent && fontSize > BEACH_NAME_MIN_FONT) {
        fontSize -= 1;
        maxText = Math.max(
            measureBeachName(homeText, fontSize),
            measureBeachName(awayText, fontSize)
        );
    }

    homeName.style.fontSize = fontSize + "px";
    awayName.style.fontSize = fontSize + "px";

    const barWidth = Math.min(
        BEACH_NAME_MAX_BAR,
        Math.max(BEACH_NAME_MIN_BAR, Math.ceil(maxText) + BEACH_NAME_PADDING + 2)
    );
    container.style.setProperty("--name-bar-width", barWidth + "px");
}

function equalizeNamePanels() {
    // Support both .team-info (pill, ribbon, glass) and .name-panel (compact overlay)
    const selector = document.querySelector('.team-home .name-panel') ? '.name-panel' : '.team-info';
    const homePanel = document.querySelector(`.team-home ${selector}`);
    const awayPanel = document.querySelector(`.team-away ${selector}`);
    if (!homePanel || !awayPanel) return;

    // Clear old manual minWidths
    homePanel.style.minWidth = '';
    awayPanel.style.minWidth = '';

    // Use a CSS Grid shadow element trick to naturally equalize widths!
    // This avoids JS read/write layout thrashing or delayed resizing jumps.
    homePanel.style.display = 'grid';
    awayPanel.style.display = 'grid';

    // CSS Grid implicitly anchors auto-sized tracks to 'start' vertically, 
    // undoing the previous Flexbox vertical centering. We fix this by centering the tract.
    homePanel.style.alignContent = 'center';
    awayPanel.style.alignContent = 'center';
    // Explicitly justify to the left as requested
    homePanel.style.justifyItems = 'start';
    awayPanel.style.justifyItems = 'start';

    const homeName = document.getElementById("home-name");
    const awayName = document.getElementById("away-name");
    
    if (homeName) homeName.style.gridArea = '1 / 1';
    if (awayName) awayName.style.gridArea = '1 / 1';

    let homeShadow = document.getElementById("home-name-shadow");
    if (!homeShadow) {
        homeShadow = document.createElement("div");
        homeShadow.id = "home-name-shadow";
        homeShadow.className = homeName ? homeName.className : "team-name";
        homeShadow.style.gridArea = '1 / 1';
        homeShadow.style.visibility = 'hidden';
        homeShadow.style.pointerEvents = 'none';
        homeShadow.style.whiteSpace = 'normal';
        homeShadow.style.wordBreak = 'break-word';
        homePanel.appendChild(homeShadow);
    }
    
    let awayShadow = document.getElementById("away-name-shadow");
    if (!awayShadow) {
        awayShadow = document.createElement("div");
        awayShadow.id = "away-name-shadow";
        awayShadow.className = awayName ? awayName.className : "team-name";
        awayShadow.style.gridArea = '1 / 1';
        awayShadow.style.visibility = 'hidden';
        awayShadow.style.pointerEvents = 'none';
        awayShadow.style.whiteSpace = 'normal';
        awayShadow.style.wordBreak = 'break-word';
        awayPanel.appendChild(awayShadow);
    }

    // Set the shadows to each other's text content!
    if (homeName && awayShadow) awayShadow.textContent = homeName.textContent;
    if (awayName && homeShadow) homeShadow.textContent = awayName.textContent;
}

function updateTimeouts(team, takenCount) {
    const dots = document.querySelectorAll(`#${team}-timeouts .timeout-dot`);
    dots.forEach((dot, index) => {
        if (index < takenCount) {
            dot.classList.add("active");
        } else {
            dot.classList.remove("active");
        }
    });
}

function renderSetHistory(state, isInitial = false) {
    const homeContainer = document.getElementById("home-history");
    const awayContainer = document.getElementById("away-history");
    // Compact and other minimal templates omit history containers entirely.
    if (!homeContainer || !awayContainer) return;

    const currentSet = state.match_info.current_set;
    const bestOfSets = state.match_info.best_of_sets || 5;
    const containers = [homeContainer, awayContainer];

    // Check if the overlay CSS natively handles container visibility (e.g. compact mode)
    const isCssDriven = !!document.querySelector('.team-home .name-panel');

    if (state.match_info.show_only_current_set) {
        if (!isCssDriven) {
            if (isInitial) {
                homeContainer.style.display = 'none';
                awayContainer.style.display = 'none';
            } else {
                if (homeContainer.style.display !== 'none') {
                    gsap.to(containers, {
                        width: 0,
                        paddingLeft: 0,
                        paddingRight: 0,
                        opacity: 0,
                        duration: 0.5,
                        ease: "power2.inOut",
                        onComplete: () => {
                            homeContainer.style.display = 'none';
                            awayContainer.style.display = 'none';
                        }
                    });
                }
            }
        }
        updateSetHistoryContainer(homeContainer, state.team_home.set_history, state.team_away.set_history, currentSet, bestOfSets, true);
        updateSetHistoryContainer(awayContainer, state.team_away.set_history, state.team_home.set_history, currentSet, bestOfSets, true);
    } else {
        if (!isCssDriven) {
            if (isInitial) {
                homeContainer.style.display = '';
                awayContainer.style.display = '';
                gsap.set(containers, { clearProps: "all" });
                updateSetHistoryContainer(homeContainer, state.team_home.set_history, state.team_away.set_history, currentSet, bestOfSets, true);
                updateSetHistoryContainer(awayContainer, state.team_away.set_history, state.team_home.set_history, currentSet, bestOfSets, true);
            } else {
                if (homeContainer.style.display === 'none') {
                    homeContainer.style.display = '';
                    awayContainer.style.display = '';

                    updateSetHistoryContainer(homeContainer, state.team_home.set_history, state.team_away.set_history, currentSet, bestOfSets, true);
                    updateSetHistoryContainer(awayContainer, state.team_away.set_history, state.team_home.set_history, currentSet, bestOfSets, true);

                    gsap.set(containers, { clearProps: "width,paddingLeft,paddingRight,opacity" });
                    gsap.from(containers, {
                        width: 0,
                        paddingLeft: 0,
                        paddingRight: 0,
                        opacity: 0,
                        duration: 0.5,
                        ease: "power2.inOut"
                    });
                } else {
                    gsap.set(containers, { clearProps: "width,paddingLeft,paddingRight,opacity" });
                    updateSetHistoryContainer(homeContainer, state.team_home.set_history, state.team_away.set_history, currentSet, bestOfSets, false);
                    updateSetHistoryContainer(awayContainer, state.team_away.set_history, state.team_home.set_history, currentSet, bestOfSets, false);
                }
            }
        } else {
            // CSS handles visibility, just clear inline styles
            gsap.set(containers, { clearProps: "all" });
            updateSetHistoryContainer(homeContainer, state.team_home.set_history, state.team_away.set_history, currentSet, bestOfSets, isInitial);
            updateSetHistoryContainer(awayContainer, state.team_away.set_history, state.team_home.set_history, currentSet, bestOfSets, isInitial);
        }
    }
}

function updateSetHistoryContainer(container, myHistory, theirHistory, currentSet, bestOfSets, isInitial) {
    const existing = Array.from(container.querySelectorAll(".set-score"));
    // Cap history to bestOfSets so a 3-set match never renders phantom set 4/5 cells
    const targetCount = Math.min(currentSet - 1, bestOfSets);
    const cellWidth = parseFloat(getComputedStyle(container).getPropertyValue("--cell-w")) || 40;

    for (let i = 1; i <= targetCount; i++) {
        const setKey = `set_${i}`;
        const myScore = myHistory[setKey] || 0;
        const theirScore = theirHistory[setKey] || 0;

        let el = existing[i - 1];
        if (!el) {
            el = document.createElement("div");
            el.className = "set-score";
            container.appendChild(el);

            if (isInitial) {
                gsap.set(el, { width: cellWidth, opacity: 1, marginLeft: (i === 1) ? 0 : 2 });
            } else {
                gsap.set(el, { width: 0, opacity: 0, marginLeft: 0 });
                gsap.to(el, {
                    width: cellWidth,
                    opacity: 1,
                    marginLeft: (i === 1) ? 0 : 2,
                    duration: 0.5,
                    ease: "power2.out"
                });
            }
        }

        el.textContent = myScore;
        const isWinner = myScore > theirScore;
        // The color is now handled via CSS var(--set-text) within the .set-score class
        el.style.opacity = isWinner ? "1" : "0.7";
        el.classList.toggle("set-won", isWinner);
        el.classList.toggle("set-lost", !isWinner);
    }

    // Remove extra elements
    for (let i = existing.length - 1; i >= targetCount; i--) {
        const elToRemove = existing[i];
        if (isInitial) {
            elToRemove.remove();
        } else {
            gsap.to(elToRemove, {
                width: 0,
                opacity: 0,
                marginLeft: 0,
                duration: 0.5,
                ease: "power2.in",
                onComplete: () => elToRemove.remove()
            });
        }
    }
}

// ── Live stats + points history ──────────────────────────────────────
//
// Both surfaces opt-in per overlay via ``overlay_control.show_stats``
// and ``overlay_control.show_points_history``. Templates that pre-date
// these features don't render the containers; ``withEl`` short-circuits
// the rendering in that case.

function _setStatsRow(rowId, labelText, valueText, teamClass) {
    withEl(rowId, row => {
        row.dataset.empty = valueText ? "false" : "true";
        if (!valueText) {
            row.textContent = "";
            return;
        }
        row.textContent = "";
        const label = document.createElement("span");
        label.className = "live-stats-label";
        label.textContent = labelText;
        const value = document.createElement("span");
        value.className = "live-stats-value " + (teamClass || "");
        value.textContent = valueText;
        row.appendChild(label);
        row.appendChild(value);
    });
}

function renderLiveStats(state) {
    const oc = (state && state.overlay_control) || {};
    const panel = document.getElementById("live-stats-panel");
    if (!panel) return;

    const show = !!oc.show_stats && !!oc.stats;
    panel.hidden = !show;
    if (!show) return;

    const stats = oc.stats;
    const cs = stats.current_streak || {};
    const ls = stats.longest_streak || {};
    const pcHome = (stats.partial_comeback || {})[1] || (stats.partial_comeback || {})["1"] || {};
    const pcAway = (stats.partial_comeback || {})[2] || (stats.partial_comeback || {})["2"] || {};

    if (cs.team && cs.n >= 2) {
        const teamClass = cs.team === 1 ? "live-stats-team-home" : "live-stats-team-away";
        _setStatsRow(
            "live-stats-streak", "STREAK",
            cs.n + " in a row", teamClass,
        );
    } else {
        _setStatsRow("live-stats-streak", "", "");
    }

    if (ls.team && ls.n >= 4 && ls.n > (cs.n || 0)) {
        const teamClass = ls.team === 1 ? "live-stats-team-home" : "live-stats-team-away";
        _setStatsRow(
            "live-stats-comeback", "LONGEST",
            ls.n + " streak", teamClass,
        );
    } else {
        const peak = Math.max(pcHome.deficit || 0, pcAway.deficit || 0);
        if (peak >= 3) {
            const team = (pcHome.deficit || 0) >= (pcAway.deficit || 0) ? 1 : 2;
            const teamClass = team === 1 ? "live-stats-team-home" : "live-stats-team-away";
            _setStatsRow(
                "live-stats-comeback", "COMEBACK",
                "-" + peak, teamClass,
            );
        } else {
            _setStatsRow("live-stats-comeback", "", "");
        }
    }

    if (typeof stats.total_points === "number" && stats.total_points > 0) {
        _setStatsRow(
            "live-stats-totals", "POINTS",
            String(stats.total_points), "",
        );
    } else {
        _setStatsRow("live-stats-totals", "", "");
    }
}

function renderPointsHistory(state) {
    const oc = (state && state.overlay_control) || {};
    const strip = document.getElementById("points-history-strip");
    if (!strip) return;

    const show = !!oc.show_points_history && Array.isArray(oc.points_history);
    strip.hidden = !show;
    if (!show) return;

    const track = document.getElementById("points-history-track");
    if (!track) return;

    const history = oc.points_history || [];
    track.textContent = "";
    const fragment = document.createDocumentFragment();
    history.forEach((p, idx) => {
        const chip = document.createElement("span");
        chip.className = "points-history-chip";
        chip.dataset.team = String(p.team || 1);
        // The last chip pulses to draw the eye to the freshest point.
        if (idx === history.length - 1) chip.dataset.fresh = "true";
        fragment.appendChild(chip);
    });
    track.appendChild(fragment);
}

function renderPlayerStats(data) {
    const container = document.getElementById("player-stats-data");
    if (!container) return;
    container.textContent = "";
    if (!data) return;

    const fragment = document.createDocumentFragment();

    const title = document.createElement("div");
    title.className = "player-stats-title";
    title.textContent = `#${data.number || ''} ${data.name || 'Estadísticas'}`;
    fragment.appendChild(title);

    if (data.stats) {
        for (const [key, value] of Object.entries(data.stats)) {
            const item = document.createElement("div");
            item.className = "player-stats-item";

            const label = document.createElement("span");
            label.className = "player-stats-label";
            label.textContent = key;

            const val = document.createElement("span");
            val.className = "player-stats-value";
            val.textContent = value;

            item.appendChild(label);
            item.appendChild(val);
            fragment.appendChild(item);
        }
    }

    container.appendChild(fragment);
}

function reportRenderArea() {
    const container = document.getElementById("scoreboard-container");
    if (!container) return;

    // The timeout ensures GSAP animations have a moment to start/apply if triggered simultaneously
    setTimeout(() => {
        const rect = container.getBoundingClientRect();
        // Send the absolute bounds to the parent window (useful for iframe previews)
        window.parent.postMessage({
            type: 'overlayRenderArea',
            bounds: {
                x: rect.x,
                y: rect.y,
                width: rect.width,
                height: rect.height,
                right: rect.right,
                bottom: rect.bottom
            }
        }, '*');
    }, 0);
}

function setupRenderAreaReporting() {
    const container = document.getElementById("scoreboard-container");
    if (!container) return;

    // Use ResizeObserver for any internal dimension changes
    const resizeObserver = new ResizeObserver(() => {
        reportRenderArea();
    });
    resizeObserver.observe(container);

    // Use MutationObserver to catch inline style changes (like GSAP animations on transform, width, top, left, etc.)
    const mutationObserver = new MutationObserver((mutations) => {
        for (const mutation of mutations) {
            if (mutation.type === 'attributes' && mutation.attributeName === 'style') {
                reportRenderArea();
            }
        }
    });

    mutationObserver.observe(container, { attributes: true, attributeFilter: ['style'] });

    // Trigger an initial report just in case
    reportRenderArea();
}

// ---------------------------------------------------------------------------
// Match-alert coreography (Phase 3)
// ---------------------------------------------------------------------------
//
// Adds a transient glow on the team panel + score block when the operator
// crosses two state-visible alert boundaries: a set is won (sets_won
// increments) and the match finishes (one team passes the win threshold
// derived from match_info.best_of_sets).
//
// Set-point and match-point glows are deliberately deferred — those
// require knowing the points-to-win threshold (25 / 15 / final-set
// override) which the overlay state does not currently carry. They will
// land when the backend pushes a ``match_info.alert`` flag.
//
// Opt-out via ``state.overlay_control.alerts_visual === false`` so an
// existing live broadcast can disable the new visual without an env-var
// or template edit.

const _ALERT_STYLES = `
@keyframes alerts-set-glow {
  0%   { box-shadow: 0 0 0 rgba(46, 125, 50, 0); }
  35%  { box-shadow: 0 0 24px 6px rgba(46, 125, 50, 0.65); }
  100% { box-shadow: 0 0 0 rgba(46, 125, 50, 0); }
}
@keyframes alerts-finished-glow {
  0%   { box-shadow: 0 0 0 rgba(244, 67, 54, 0); }
  20%  { box-shadow: 0 0 28px 8px rgba(244, 67, 54, 0.85); }
  60%  { box-shadow: 0 0 28px 8px rgba(244, 67, 54, 0.85); }
  100% { box-shadow: 0 0 0 rgba(244, 67, 54, 0); }
}
.alerts-set-won {
  animation: alerts-set-glow 1.4s ease-out 1;
  border-radius: 12px;
}
.alerts-match-finished {
  animation: alerts-finished-glow 2.4s ease-out 1;
  border-radius: 12px;
}
@media (prefers-reduced-motion: reduce) {
  .alerts-set-won, .alerts-match-finished { animation: none; }
}
`;
let _alertsStyleInjected = false;
function ensureAlertStylesInjected() {
    if (_alertsStyleInjected) return;
    const style = document.createElement('style');
    style.id = 'alerts-style';
    style.textContent = _ALERT_STYLES;
    document.head.appendChild(style);
    _alertsStyleInjected = true;
}

function _alertsEnabled(state) {
    // Opt-out: only ``=== false`` disables. Missing keys (legacy
    // overlays loaded before Phase 3) keep the new behaviour on.
    return state && state.overlay_control
        && state.overlay_control.alerts_visual !== false;
}

function _matchFinished(state) {
    if (!state) return false;
    const bestOf = (state.match_info && state.match_info.best_of_sets) || 5;
    const threshold = Math.ceil(bestOf / 2);
    return (state.team_home && state.team_home.sets_won >= threshold)
        || (state.team_away && state.team_away.sets_won >= threshold);
}

function _flashAlertOnTeam(team, className, durationMs) {
    // Combined target: the panel and the score node both pulse so
    // any template variant (compact, jersey, glass…) catches at
    // least one of them. We don't depend on a single shared
    // selector because each template renames the visible block.
    const targets = [
        document.querySelector(`.team-${team}`),
        document.getElementById(`${team}-points`),
        document.getElementById(`${team}-sets`),
    ].filter(Boolean);
    targets.forEach((el) => {
        // Cancel any in-flight removal for the same element so a
        // rapid follow-up (e.g. operator un-does a set then re-applies
        // it) doesn't get its animation cut short by the previous
        // setTimeout. The id is stored per-class so concurrent
        // alert kinds (set-won + match-finished landing on the same
        // tick) coexist cleanly.
        const timerKey = `_alertTimeout_${className}`;
        if (el[timerKey]) {
            clearTimeout(el[timerKey]);
            el[timerKey] = null;
        }
        el.classList.remove(className);
        // Re-apply on next frame to restart the keyframe animation
        // on repeated triggers (e.g. team won set 1 then set 2).
        // eslint-disable-next-line no-unused-expressions -- forces reflow
        void el.offsetWidth;
        el.classList.add(className);
        el[timerKey] = setTimeout(() => {
            el.classList.remove(className);
            el[timerKey] = null;
        }, durationMs + 50);
    });
}

function triggerSetWonAlert(team) {
    ensureAlertStylesInjected();
    _flashAlertOnTeam(team, 'alerts-set-won', 1400);
}

function triggerMatchFinishedAlert(team) {
    ensureAlertStylesInjected();
    _flashAlertOnTeam(team, 'alerts-match-finished', 2400);
}

function dispatchAlertTransitions(oldState, newState) {
    if (!_alertsEnabled(newState)) return;
    // Set-won: each side independently — same operator can fix one
    // side via long-press and we shouldn't double-fire on the other.
    if (oldState.team_home.sets_won !== newState.team_home.sets_won
        && newState.team_home.sets_won > oldState.team_home.sets_won) {
        triggerSetWonAlert('home');
    }
    if (oldState.team_away.sets_won !== newState.team_away.sets_won
        && newState.team_away.sets_won > oldState.team_away.sets_won) {
        triggerSetWonAlert('away');
    }
    // Match-finished: only fires on the rising edge. The match
    // archive flow may zero ``sets_won`` to prep the next match, so
    // we explicitly require the new state to be finished AND the
    // previous one to not have been.
    const wasFinished = _matchFinished(oldState);
    const nowFinished = _matchFinished(newState);
    if (!wasFinished && nowFinished) {
        const winner = (newState.team_home.sets_won
            > newState.team_away.sets_won) ? 'home' : 'away';
        triggerMatchFinishedAlert(winner);
    }
}

// Start connection when DOM is ready
document.addEventListener("DOMContentLoaded", () => {
    connectWebSocket();
    setupRenderAreaReporting();
    ensureAlertStylesInjected();
});
