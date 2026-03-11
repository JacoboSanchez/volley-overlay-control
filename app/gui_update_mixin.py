from nicegui import ui
from app.state import State
from app.theme import (
    TACOLOR_HIGH, TACOLOR_VLIGHT, TACOLOR_MEDIUM,
    TBCOLOR_HIGH, TBCOLOR_VLIGHT, TBCOLOR_MEDIUM,
    VISIBLE_ON_COLOR, VISIBLE_OFF_COLOR,
)
from app.game_manager import GameManager
from app.app_storage import AppStorage
from app.components.button_style import update_button_style as _update_button_style


class UIUpdateMixin:
    """Mixin providing all UI state-update methods for the GUI class."""

    def compute_current_set(self, current_state):
        t1sets = current_state.get_sets(1)
        t2sets = current_state.get_sets(2)
        current_sets = t1sets + t2sets
        if not self.game_manager.match_finished():
            current_sets += 1
        return current_sets

    def update_ui_logos(self):
        """Updates the team logos without recreating the elements."""
        logo1_src = self.current_customize_state.get_team_logo(1)
        logo2_src = self.current_customize_state.get_team_logo(2)
        self.teamA_logo.set_source(logo1_src)
        self.teamB_logo.set_source(logo2_src)

    def update_button_style(self):
        """Updates the style of the score buttons based on configuration."""
        _update_button_style(
            self.teamAButton, self.teamBButton, self.teamASet, self.teamBSet,
            self.button_size, self.button_text_size,
            self.current_customize_state, self.logger,
        )

    def update_ui(self, load_from_backend=False):
        self.logger.debug('Updating UI...')
        if load_from_backend:
            self.logger.info('loading data from backend')
            self.game_manager = GameManager(self.conf, self.backend)
            self.current_customize_state.set_model(
                self.backend.get_current_customization())
            self.visible = self.backend.is_visible()
            self.update_ui_logos()
        self.update_button_style()

        update_state = self.game_manager.get_current_state()

        self.current_set = self.compute_current_set(update_state)

        self.update_ui_serve(update_state)
        self.update_ui_sets(update_state)
        self.update_ui_games(update_state)
        self.update_ui_timeouts(update_state)
        self.update_ui_current_set(self.current_set)
        self.update_ui_visible(self.visible)
        clientSimple = AppStorage.load(
            AppStorage.Category.SIMPLE_MODE, oid=self.conf.oid)
        if clientSimple is not None:
            self.switch_simple_mode(clientSimple)

    def update_ui_games(self, update_state):
        """Updates the game scores on the UI."""
        for i in range(1, self.sets_limit + 1):
            teamA_game_int = update_state.get_game(1, i)
            teamB_game_int = update_state.get_game(2, i)
            if i == self.current_set:
                self.logger.debug(f'setting games {teamA_game_int:02d} {teamB_game_int:02d} on current set {self.current_set:01d}')
                self.teamAButton.set_text(f'{teamA_game_int:02d}')
                self.teamBButton.set_text(f'{teamB_game_int:02d}')
        self.update_ui_games_table(update_state)

    def update_ui_games_table(self, update_state):
        if self.teamA_scores_container is None or self.teamB_scores_container is None:
            return

        self.teamA_scores_container.clear()
        self.teamB_scores_container.clear()

        lastWithoutZeroZero = 1
        match_finished = self.game_manager.match_finished()
        for i in range(1, self.sets_limit + 1):
            teamA_game_int = update_state.get_game(1, i)
            teamB_game_int = update_state.get_game(2, i)
            if teamA_game_int + teamB_game_int > 0:
                lastWithoutZeroZero = i

        for i in range(1, self.sets_limit + 1):
            teamA_game_int = update_state.get_game(1, i)
            teamB_game_int = update_state.get_game(2, i)
            do_break = False
            empty_label = False
            if i > 1 and i > lastWithoutZeroZero:
                do_break = True
            if i == self.current_set and i < self.sets_limit and not match_finished:
                do_break = True
            if do_break:
                break

            with self.teamA_scores_container:
                label1 = ui.label(f'{teamA_game_int:02d}').classes('p-0 m-0').mark(f'team-1-set-{i}-score')
            with self.teamB_scores_container:
                label2 = ui.space() if empty_label else ui.label(f'{teamB_game_int:02d}').classes('p-0 m-0').mark(f'team-2-set-{i}-score')

            if teamA_game_int > teamB_game_int:
                label1.classes('text-bold')
            elif teamA_game_int < teamB_game_int:
                label2.classes('text-bold')

    def update_ui_timeouts(self, update_state):
        self.change_ui_timeout(1, update_state.get_timeout(1))
        self.change_ui_timeout(2, update_state.get_timeout(2))

    def update_ui_serve(self, update_state):
        """Updates the serve icons based on the current state."""
        current_serve = update_state.get_current_serve()

        is_serving_a = current_serve == State.SERVE_1
        self.serveA.props(f'color={TACOLOR_HIGH if is_serving_a else TACOLOR_VLIGHT}')
        self.serveA.style(f'opacity: {1 if is_serving_a else 0.4}')

        is_serving_b = current_serve == State.SERVE_2
        self.serveB.props(f'color={TBCOLOR_HIGH if is_serving_b else TBCOLOR_VLIGHT}')
        self.serveB.style(f'opacity: {1 if is_serving_b else 0.4}')

    def update_ui_sets(self, update_state):
        t1sets = update_state.get_sets(1)
        t2sets = update_state.get_sets(2)
        self.teamASet.set_text(str(t1sets))
        self.teamBSet.set_text(str(t2sets))

    def update_ui_current_set(self, set_number):
        self.set_selector.set_value(set_number)

    def update_ui_visible(self, enabled):
        icon = 'visibility' if enabled else 'visibility_off'
        color = VISIBLE_ON_COLOR if enabled else VISIBLE_OFF_COLOR
        self.visibility_button.set_icon(icon)
        self.visibility_button.props(f'color={color}')

    def change_ui_timeout(self, team, value):
        color = TACOLOR_MEDIUM if team == 1 else TBCOLOR_MEDIUM
        container = self.timeoutsA if team == 1 else self.timeoutsB
        container.clear()
        with container:
            for n in range(value):
                ui.icon(name='radio_button_unchecked',
                        color=color, size='12px').mark(f'timeout-{team}-number-{n}')
