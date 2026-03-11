from nicegui import ui


class ButtonInteraction:
    """
    Manages tap, double-tap, and long-press detection for score buttons.
    Owns all related timer and tap-tracking state, keeping it out of the main GUI class.
    """

    def __init__(self, gui):
        self.gui = gui
        self.click_gate_open = True
        self.long_press_timer = None
        self.tap_count = 0
        self.tap_timer = None
        self.tap_team = None
        self.tap_is_set = None

    def open_click_gate(self):
        """Opens the gate to allow new click events."""
        self.click_gate_open = True

    def handle_press_cancel(self):
        """Cancels the long press timer if the touch moves."""
        if self.long_press_timer is not None:
            self.long_press_timer.cancel()
            self.long_press_timer = None
            self.tap_count = 0
            if self.tap_timer is not None:
                self.tap_timer.cancel()
                self.tap_timer = None
        self.open_click_gate()

    def _execute_pending_tap(self):
        """Executes the action for a single tap."""
        if self.tap_timer is not None:
            self.tap_timer.cancel()
            self.tap_timer = None

        if self.tap_count > 0:
            if self.tap_is_set:
                self.gui.add_set(self.tap_team)
            else:
                ui.run_javascript('if (navigator.vibrate) navigator.vibrate(50)')
                self.gui.add_game(self.tap_team)
            self.tap_count = 0
            self.tap_team = None
            self.tap_is_set = None

    def handle_button_press(self, team: int, is_set_button: bool):
        """Starts a timer on mousedown/touchstart to detect a long press."""
        if not self.click_gate_open:
            return
        self.click_gate_open = False

        # If a different button was pressed while a tap was pending, execute the pending tap immediately
        if self.tap_count > 0 and (self.tap_team != team or self.tap_is_set != is_set_button):
            self._execute_pending_tap()

        if is_set_button:
            button = self.gui.teamASet if team == 1 else self.gui.teamBSet
            initial_value = int(button.text)
            max_value = self.gui.sets_limit
        else:
            button = self.gui.teamAButton if team == 1 else self.gui.teamBButton
            initial_value = int(button.text)
            max_value = self.gui.get_game_limit(self.gui.current_set)

        async def long_press_callback():
            self.long_press_timer = None
            self.tap_count = 0  # Cancel any double-tap sequence if it becomes a long press
            if self.tap_timer is not None:
                self.tap_timer.cancel()
                self.tap_timer = None
            if not is_set_button:
                ui.run_javascript('if (navigator.vibrate) navigator.vibrate(200)')
            await self.gui.show_custom_value_dialog(team, is_set_button, initial_value, max_value)

        self.long_press_timer = ui.timer(1.0, long_press_callback, once=True)

    def handle_button_release(self, team: int, is_set_button: bool):
        """Cancels the long press timer and processes tap or double-tap."""
        if self.long_press_timer is not None:
            self.long_press_timer.cancel()
            self.long_press_timer = None

            # This was a valid tap (not a long press)
            self.tap_team = team
            self.tap_is_set = is_set_button
            self.tap_count += 1

            if self.tap_count == 1:
                # Start timer to wait for a potential second tap
                self.tap_timer = ui.timer(0.4, self._execute_pending_tap, once=True)
            elif self.tap_count == 2:
                # Double tap detected
                if self.tap_timer is not None:
                    self.tap_timer.cancel()
                    self.tap_timer = None

                self.gui.undo = True
                if self.tap_is_set:
                    self.gui.add_set(self.tap_team)
                else:
                    ui.run_javascript('if (navigator.vibrate) navigator.vibrate([50, 100, 50])')
                    self.gui.add_game(self.tap_team)
                self.gui.undo = False  # reset undo back just in case

                self.tap_count = 0
                self.tap_team = None
                self.tap_is_set = None

        # Re-open the gate after a short delay to ignore ghost clicks
        ui.timer(0.1, self.open_click_gate, once=True)
