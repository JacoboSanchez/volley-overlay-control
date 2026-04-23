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

function processStateUpdate(newState) {
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

    // 2. Colors
    updateCSSVariables(state.team_home, state.team_away, state.overlay_control.colors);

    // 3. Match Info Removed

    // 4. Team Names & Logos
    withEl("home-name", el => { el.textContent = state.team_home.name; });
    withEl("away-name", el => { el.textContent = state.team_away.name; });
    equalizeNamePanels();

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

    // 4b. Logo visibility toggle (from remote-scoreboard "Logos" setting)
    const showLogos = state.overlay_control.show_logos !== false;
    updateLogoVisibility(showLogos);

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

    // Logo visibility toggle
    if (oldState.overlay_control.show_logos !== newState.overlay_control.show_logos) {
        updateLogoVisibility(newState.overlay_control.show_logos !== false);
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
                gsap.set(el, { width: 40, opacity: 1, marginLeft: (i === 1) ? 0 : 2 });
            } else {
                gsap.set(el, { width: 0, opacity: 0, marginLeft: 0 });
                gsap.to(el, {
                    width: 40,
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

// Start connection when DOM is ready
document.addEventListener("DOMContentLoaded", () => {
    connectWebSocket();
    setupRenderAreaReporting();
});
