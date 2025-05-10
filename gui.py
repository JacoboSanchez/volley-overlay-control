import logging
from nicegui import ui
from state import State
from customization import Customization
from app_storage import AppStorage
from customization_page import CustomizationPage

TACOLOR='blue'
TBCOLOR='red'
TACOLOR_VLIGHT='blue-1'
TACOLOR_LIGHT='blue-2'
TACOLOR_MEDIUM='blue-3'
TACOLOR_HIGH='blue-4'
TBCOLOR_VLIGHT='red-1'
TBCOLOR_LIGHT='red-2'
TBCOLOR_MEDIUM='red-3'
TBCOLOR_HIGH='red-4'

DO_COLOR='indigo-700'
UNDO_COLOR='indigo-400' 
VISIBLE_ON_COLOR='green-600'
VISIBLE_OFF_COLOR='green-800' 
FULL_SCOREBOARD_COLOR='orange-500'
SIMPLE_SCOREBOARD_COLOR='orange-700' 

RED_BUTTON_COLOR='red'
BLUE_BUTTON_COLOR='blue'
GAME_BUTTON_PADDING_BIG='p-16'
GAME_BUTTON_PADDING_NORMAL='p-14'
GAME_BUTTON_PADDING_SMALL='p-11'
GAME_BUTTON_TEXT_NORMAL='text-5xl'
GAME_BUTTON_TEXT_BIG='text-6xl'
GAME_BUTTON_CLASSES=' text-center shadow-lg rounded-lg text-white font-bold '

class GUI:
    
    def __init__(self, tabs=None, conf=None, backend=None):
        self.logger = logging.getLogger("GUI")
        self.undo = False
        self.simple = False
        self.holdUpdate = 0
        self.current_set = 1
        self.visible = True
        self.initialized = False
        self.tabs = tabs
        self.conf = conf
        self.backend = backend
        self.current_customize_state = Customization(backend.get_current_customization())
        self.main_state = State(backend.get_current_model()) 
        self.visible = backend.is_visible()
        self.set_selector = None
        self.page_height = None
        self.page_width = None
        self.PADDINGS = GAME_BUTTON_PADDING_NORMAL
        self.TEXTSIZE = GAME_BUTTON_TEXT_NORMAL
        self.initialized = False

    def set_page_size(self, width, height):
        self.page_height = height
        self.page_width = width
        self.logger.debug('Set page size to: %sx%s', self.page_height, self.page_width)
        if self.page_width >= self.page_height:
            if (self.page_width > 850):
                if self.PADDINGS != GAME_BUTTON_PADDING_BIG:
                    self.switch_padding(GAME_BUTTON_PADDING_BIG)
                    self.switch_textsize(GAME_BUTTON_TEXT_BIG)
            elif (self.page_width > 745):
                if self.PADDINGS != GAME_BUTTON_PADDING_NORMAL:
                    self.switch_padding(GAME_BUTTON_PADDING_NORMAL)
                    self.switch_textsize(GAME_BUTTON_TEXT_NORMAL)
            else:
                if self.PADDINGS != GAME_BUTTON_PADDING_SMALL:
                    self.switch_padding(GAME_BUTTON_PADDING_SMALL)
                    self.switch_textsize(GAME_BUTTON_TEXT_NORMAL)
        else:
            if (self.page_height > 850):
                if self.PADDINGS != GAME_BUTTON_PADDING_BIG:
                    self.switch_padding(GAME_BUTTON_PADDING_BIG)
                    self.switch_textsize(GAME_BUTTON_TEXT_BIG)
            elif (self.page_height > 800):
                if self.PADDINGS != GAME_BUTTON_PADDING_NORMAL:
                    self.switch_padding(GAME_BUTTON_PADDING_NORMAL)
                    self.switch_textsize(GAME_BUTTON_TEXT_NORMAL)
            else:
                if self.PADDINGS != GAME_BUTTON_PADDING_SMALL:
                    self.switch_padding(GAME_BUTTON_PADDING_SMALL)
                    self.switch_textsize(GAME_BUTTON_TEXT_NORMAL)
                

    def switch_padding(self, padding):
            if self.initialized:
                self.teamAButton.classes(remove=self.PADDINGS)
                self.teamBButton.classes(remove=self.PADDINGS)
            self.PADDINGS = padding
            self.logger.info("Change paddings to %s", padding)
            if self.initialized:
                self.teamAButton.classes(add=self.PADDINGS)
                self.teamBButton.classes(add=self.PADDINGS)

    def switch_textsize(self, textsize):
            if self.initialized:
                self.teamAButton.classes(remove=self.TEXTSIZE)
                self.teamBButton.classes(remove=self.TEXTSIZE)
            self.TEXTSIZE = textsize
            self.logger.info("Change textsize to %s", textsize)
            if self.initialized:
                self.teamAButton.classes(add=self.TEXTSIZE)
                self.teamBButton.classes(add=self.TEXTSIZE)

    def set_main_state(self, state):
        self.main_state = State(state)

    def get_current_state(self):
        return self.main_state

    def init(self, force=True, custom_points_limit=None, custom_points_limit_last_set=None, custom_sets_limit=None):
        if self.initialized == True and force == False:
            return
        self.logger.info('Initialize gui')
        if custom_points_limit != None:
            self.points_limit = custom_points_limit
        else:
            self.points_limit = self.conf.points
        if custom_points_limit_last_set != None:
            self.points_limit_last_set = custom_points_limit_last_set
        else:
            self.points_limit_last_set = self.conf.points_last_set
        if custom_sets_limit != None:
            self.sets_limit = custom_sets_limit
        else:
            self.sets_limit = self.conf.sets
        self.logger.info('Set points: %s', self.points_limit)
        self.logger.info('Set points last set: %s', self.points_limit_last_set)
        self.logger.info('Sets to win: %s', self.sets_limit)
        with ui.row().classes('w-full'):
            with ui.card():
                self.teamAButton = ui.button('00', color=BLUE_BUTTON_COLOR, on_click=lambda: self.add_game(1)).classes(self.PADDINGS+GAME_BUTTON_CLASSES+self.TEXTSIZE)
                with ui.row().classes('text-4xl w-full'):
                    ui.button(icon='timer', color=TACOLOR_LIGHT, on_click=lambda: self.add_timeout(1)).props('outline round').classes('shadow-lg')
                    self.timeoutsA = ui.column()
                    ui.space()
                    self.serveA = ui.icon(name='sports_volleyball', color=TACOLOR_VLIGHT)
                    self.serveA.on('click', lambda: self.change_serve(1))
            ui.space()
            with ui.column().classes('justify-center'):
                with ui.row().classes('w-full justify-center'):
                    self.teamASet = ui.button('0', color='gray-700', on_click=lambda: self.add_set(1)).classes('text-white text-2xl')
                    with ui.row():
                        self.scores = ui.grid(columns=2).classes('justify-center') 
                    self.teamBSet = ui.button('0', color='gray-700', on_click=lambda: self.add_set(2)).classes('text-white text-2xl')
                self.set_selector = ui.pagination(1, self.sets_limit, direction_links=True, on_change=lambda e: self.switch_to_set(e.value)).props('color=grey active-color=teal')        
            ui.space()
            with ui.card():
                self.teamBButton = ui.button('00', color=RED_BUTTON_COLOR, on_click=lambda: self.add_game(2)).classes(self.PADDINGS+GAME_BUTTON_CLASSES+self.TEXTSIZE)
                with ui.row().classes('text-4xl w-full'):
                    ui.button(icon='timer', color=TBCOLOR_LIGHT, on_click=lambda: self.add_timeout(2)).props('outline round').classes('shadow-lg ')
                    self.timeoutsB = ui.column() 
                    ui.space()
                    self.serveB = ui.icon(name='sports_volleyball', color=TBCOLOR_VLIGHT)
                    self.serveB.on('click', lambda: self.change_serve(2))
            

        with ui.row().classes("w-full justify-right"):
            self.visibility_button = ui.button(icon='visibility', color=VISIBLE_ON_COLOR, on_click=self.switch_visibility).props('round').classes('text-white')
            self.simple_button = ui.button(icon='grid_on', color=FULL_SCOREBOARD_COLOR, on_click=self.switch_simple_mode).props('round').classes('text-white')
            self.undo_button = ui.button(icon='undo', color=UNDO_COLOR, on_click=lambda: self.switch_undo(self.undo_button)).props('round').classes('text-white')    
            ui.space()
            ui.button(icon='keyboard_arrow_right', color='stone-500', on_click=lambda: self.tabs.set_value(Customization.CONFIG_TAB)).props('round').classes('text-white')    
                
        self.update_ui(False)
        self.initialized = True
        self.logger.info('Initialized gui')
        

    def compute_current_set(self, current_state):
        t1sets = current_state.get_sets(1)
        t2sets = current_state.get_sets(2)
        current_sets =  t1sets + t2sets
        if self.match_finished(t1sets, t2sets) != True:
            current_sets += 1
        return current_sets

    def match_finished(self, t1sets, t2sets):
        limit = self.sets_limit
        soft_limit = 2 if self.sets_limit == 3 else 3
        if (t1sets + t2sets < limit and t1sets < soft_limit and t2sets < soft_limit):
            return False
        self.logger.info('Match finished')
        return True

    def update_ui(self, load_from_backend=False):
        global visible
        self.logger.info('Updating UI...')
        if load_from_backend or self.conf.cache:
            self.logger.info('loading data from backend')
            self.current_customize_state.set_model(self.backend.get_current_customization())
            update_state = State(self.backend.get_current_model())
            visible = self.backend.is_visible()
        else:
            update_state = self.main_state
            
        darkMode = AppStorage.load(AppStorage.Category.DARK_MODE, default=None)
        logging.debug('loaded dark mode %s', darkMode)
        if darkMode == None:
            darkMode = self.conf.darkMode
        logging.info('Setting dark mode %s', darkMode)
        CustomizationPage.set_ui_dark_mode(darkMode)

        current_set = self.compute_current_set(update_state)
        self.update_ui_serve(update_state)
        self.update_ui_sets(update_state)
        self.update_ui_games(update_state)
        self.update_ui_timeouts(update_state)
        self.update_ui_current_set(current_set)
        self.update_ui_visible(visible)
        clientSimple = AppStorage.load(AppStorage.Category.SIMPLE_MODE, oid=self.conf.oid)
        if load_from_backend:
            self.switch_simple_mode(False)
        elif clientSimple != None:
            self.switch_simple_mode(clientSimple) 

    def update_ui_games(self, update_state):
        self.hold()
        for i in range(1, self.sets_limit+1):
            teamA_game_int = update_state.get_game(1, i)
            teamB_game_int = update_state.get_game(2, i)
            if (i == self.current_set):
                self.teamAButton.set_text(f'{teamA_game_int:02d}')
                self.teamBButton.set_text(f'{teamB_game_int:02d}')
            self.main_state.set_game(i, 1, str(teamA_game_int))
            self.main_state.set_game(i, 2, str(teamB_game_int))
        self.update_ui_games_table(update_state)
        self.release()

    def update_ui_games_table(self, update_state):
        logo1 = self.current_customize_state.get_team_logo(1)
        logo2 = self.current_customize_state.get_team_logo(2)
        self.scores.clear()
        with self.scores:
            if (logo1 != None and logo1 != Customization.DEFAULT_IMAGE):
                ui.image(source=logo1).classes('w-6 h-6 m-auto')
            else: 
                ui.icon(name='sports_volleyball', color='blue', size='xs')
                
            if (logo2 != None and logo2 != Customization.DEFAULT_IMAGE):
                ui.image(source=logo2).classes('w-6 h-6 m-auto')
            else: 
                ui.icon(name='sports_volleyball', color='red', size='xs')
            lastWithoutZeroZero = 1
            match_finished = self.match_finished(update_state.get_sets(1), update_state.get_sets(2))
            for i in range(1, self.sets_limit+1):
                teamA_game_int = update_state.get_game(1, i)
                teamB_game_int = update_state.get_game(2, i)
                if (teamA_game_int + teamB_game_int > 0):
                    lastWithoutZeroZero = i

            for i in range(1, self.sets_limit+1):
                teamA_game_int = update_state.get_game(1, i)
                teamB_game_int = update_state.get_game(2, i)
                if (i > 1 and i > lastWithoutZeroZero):
                    break
                if (i == self.current_set and i < self.sets_limit and match_finished != True):
                    break
                label1 = ui.label(f'{teamA_game_int:02d}').classes('p-0')
                label2 = ui.label(f'{teamB_game_int:02d}').classes('p-0')
                if (teamA_game_int > teamB_game_int):
                    label1.classes('text-bold')
                elif (teamA_game_int < teamB_game_int):
                    label2.classes('text-bold')

    def update_ui_timeouts(self, update_state):
        self.hold()
        self.change_ui_timeout(1, update_state.get_timeout(1))
        self.change_ui_timeout(2, update_state.get_timeout(2))
        self.release()

    def update_ui_serve(self, update_state):    
        self.hold()
        match update_state.get_current_serve():
            case State.SERVE_NONE:
                self.change_serve(0)
            case State.SERVE_1:
                self.change_serve(1)
            case State.SERVE_2:
                self.change_serve(2)
        self.release()

    def update_ui_sets(self, update_state):
        self.hold()
        t1sets = update_state.get_sets(1)
        t2sets = update_state.get_sets(2)
        self.main_state.set_sets(1, str(t1sets))
        self.main_state.set_sets(2, str(t2sets))
        self.teamASet.set_text(str(t1sets))
        self.teamBSet.set_text(str(t2sets))
        self.release()

    def update_ui_current_set(self, set):
        self.hold()
        self.main_state.set_current_set(set)
        self.set_selector.set_value(set)
        self.release()

    def update_ui_visible(self, enabled):
        if enabled:
            self.visibility_button.set_icon('visibility')
            self.visibility_button.props('color='+VISIBLE_ON_COLOR)
        else:
            self.visibility_button.set_icon('visibility_off')
            self.visibility_button.props('color='+VISIBLE_OFF_COLOR)


    def hold(self):
        self.holdUpdate += 1

    def release(self):
        if self.holdUpdate > 0:
            self.holdUpdate -= 1 

    def release_hold_and_send_state(self):
        self.release()
        if self.holdUpdate == 0:
            self.send_state()

    def send_state(self):
        if (self.holdUpdate == 0):
            self.backend.save(self.main_state, self.simple)

    def reset(self):
        self.logger.info('Reset called')
        self.backend.reset(self.main_state)
        self.update_ui(True)

    def change_serve(self, team, force=False):
        match team:
            case 1:
                self.main_state.set_current_serve(State.SERVE_1)
                if self.serveA.props['color']==TACOLOR_HIGH and force != True:
                    self.serveA.props(f'color={TACOLOR_VLIGHT}')
                    self.main_state.set_current_serve(State.SERVE_NONE)
                else:                             
                    self.serveA.props(f'color={TACOLOR_HIGH}')
                self.serveB.props(f'color={TBCOLOR_VLIGHT}')
            case 2:
                self.main_state.set_current_serve(State.SERVE_2)
                if self.serveB.props['color']==TBCOLOR_HIGH and force != True:
                    self.serveB.props(f'color={TBCOLOR_VLIGHT}')
                    self.main_state.set_current_serve(State.SERVE_NONE)
                else:                             
                    self.serveB.props(f'color={TBCOLOR_HIGH}')
                self.serveA.props(f'color={TACOLOR_VLIGHT}')
            case 0:
                self.main_state.set_current_serve(State.SERVE_NONE)
                self.serveB.props(f'color={TBCOLOR_VLIGHT}')
                self.serveA.props(f'color={TACOLOR_VLIGHT}')
        self.send_state()

    def add_timeout(self, team):
        if team == 1:
            color = TACOLOR_MEDIUM
            container = self.timeoutsA
        else:
            color = TBCOLOR_MEDIUM
            container = self.timeoutsB
        if self.undo:
            if len(list(container)) > 0:
                container.remove(0) if list(container) else None
            self.switch_undo(True)
        else:        
            if len(list(container)) < 2:
                with container:
                    ui.icon(name='radio_button_unchecked', color=color, size='12px').classes('text-center')
            else:
                container.clear()
        self.main_state.set_timeout(team, len(list(container)))
        self.send_state()

    def change_ui_timeout(self, team, value):
        if team == 1:
            color = TACOLOR_MEDIUM
            container = self.timeoutsA
        else:
            color = TBCOLOR_MEDIUM
            container = self.timeoutsB
        container.clear()
        for i in range(value):
            with container:
                ui.icon(name='radio_button_unchecked', color=color, size='12px')
        self.main_state.set_timeout(team, len(list(container))) 

    def add_game(self, team):
        if self.block_additional_points():
            return
        self.hold()
        if team == 1:
            button = self.teamAButton
            rival_score = int(self.teamBButton.text)
            self.change_serve(1, True)
        else:
            button = self.teamBButton
            rival_score = int(self.teamAButton.text)
            self.change_serve(2, True)
        current = self.add_int_to_button(button)
        self.main_state.set_game(self.current_set, team, current)
        if (current >=  self.get_game_limit(self.current_set) and (current - rival_score > 1)):
            self.add_set(team)
        self.release_hold_and_send_state()

    def set_team_name(self, team, name):
        self.main_state.set_team_name(team, name)

    def get_team_name(self, team):
        return self.main_state.get_team_name(team)

    def get_current_model(self):
        return self.main_state.get_current_model()
    
    def is_show_logos(self):
        return self.main_state.is_show_logos()
    
    def set_show_logos(self, show):
        self.main_state.set_show_logos(show)

    def get_game_limit(self, set):
        if set == self.sets_limit:
            return self.points_limit_last_set
        else:
            return self.points_limit 

    def add_set(self, team, roll2zero=True):
        if self.block_additional_points():
            return
        self.hold()
        button = self.teamASet
        if team == 2: button = self.teamBSet
        soft_limit = 2 if self.sets_limit == 3 else 3
        current = self.add_int_to_button(button, soft_limit if roll2zero else soft_limit+1, False)
        self.main_state.set_sets(team, current)
        self.change_ui_timeout(1, 0)
        self.change_ui_timeout(2, 0)
        self.change_serve(0)
        self.switch_to_set(self.compute_current_set(self.main_state))
        self.release()

    def block_additional_points(self):
        t1sets = self.main_state.get_sets(1)
        t2sets = self.main_state.get_sets(2)
        if not self.undo and self.match_finished(t1sets, t2sets):
            return True
        return False

    def switch_to_set(self, set):
        if (self.current_set != set):
            self.current_set = set
            self.update_ui_current_set(self.current_set)
            self.update_ui_games(self.main_state)

    def switch_visibility(self):
        if self.visible:
            self.visible = False
            self.visibility_button.set_icon('visibility_off')
        else:
            self.visible = True
            self.visibility_button.set_icon('visibility')
        self.update_ui_visible(self.visible)
        self.backend.change_overlay_visibility(self.visible)

    def switch_simple_mode(self, force_value=None):
        self.hold()
        if (force_value == None and self.simple == True) or force_value == False:
            self.simple = False
            self.simple_button.set_icon('grid_on')
            self.simple_button.props('color='+FULL_SCOREBOARD_COLOR)
        elif (force_value == None and self.simple == False) or force_value == True:
            self.simple = True
            self.simple_button.set_icon('window')
            self.simple_button.props('color='+SIMPLE_SCOREBOARD_COLOR)
            self.backend.reduce_games_to_one()
        if force_value == None:
            AppStorage.save(AppStorage.Category.SIMPLE_MODE, self.simple, oid=self.conf.oid)
        self.release_hold_and_send_state()  

    def switch_undo(self, reset=False):
        if self.undo:
            self.undo = False
            self.undo_button.set_icon('undo')
            self.undo_button.props('color='+UNDO_COLOR)
        elif reset != True:
            self.undo = True
            self.undo_button.set_icon('redo')
            self.undo_button.props('color='+DO_COLOR)


    def add_int_to_button(self, button, limit=99, force_digits=True):
        current = int(button.text)
        if self.undo:
            if (current != 0):
                current -= 1
            self.switch_undo(True)
        else:
            current += 1
        if current > limit:
            current = 0
        if force_digits:
            button.set_text(f'{current:02d}')
        else:
            button.set_text(f'{current:01d}')
        return current
    
    def refresh(self):
        self.update_ui(True)