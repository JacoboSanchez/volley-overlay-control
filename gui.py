import logging
import sys
from nicegui import ui, app
from state import State
from customization import Customization
from clientstorage import ClientStorage

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


logging.addLevelName( logging.DEBUG, "\033[33m%s\033[1;0m" % logging.getLevelName(logging.DEBUG))
logging.addLevelName( logging.INFO, "\033[1;33m%s\033[1;0m" % logging.getLevelName(logging.INFO))
logging.addLevelName( logging.WARNING, "\033[1;31m%s\033[1;0m" % logging.getLevelName(logging.WARNING))
logging.addLevelName( logging.ERROR, "\033[1;41m%s\033[1;0m" % logging.getLevelName(logging.ERROR))
root = logging.getLogger()
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter( "\033[1;36m%s\033[1;0m" % '%(asctime)s'+' %(levelname)s '+"\033[32m%s\033[1;0m" % '[%(name)s]'+':  %(message)s'))
root.addHandler(handler)


class GUI:
    
    def __init__(self, tabs=None, conf=None, backend=None):
        root.setLevel(conf.logging_level)
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
        self.current_customize_state = Customization(backend.getCurrentCustomizationStateModel())
        self.main_state = State(backend.getCurrentStateModel()) 
        self.visible = backend.isVisible()
        self.set_selector = None

    def setMainState(self, state):
        self.main_state = State(state)

    def getCurrentState(self):
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
        darkMode = ClientStorage.load(ClientStorage.DARK_MODE, -1)
        if darkMode == 0:
            logging.info('Restoring light mode')
            ui.dark_mode(False)
        elif darkMode == 1:
            logging.info('Restoring dark mode')
            ui.dark_mode(True)
        else:
            logging.info('Loading configured dark mode %s', self.conf.darkMode)
            match self.conf.darkMode:
                case 'on':
                    ui.dark_mode(True)
                case 'off': 
                    ui.dark_mode(False)
                case 'auto':
                    ui.dark_mode()
        #########################################
        ui.add_head_html('''
            <style type="text/tailwindcss">
                @layer components {
                    .blue-box {
                        @apply bg-blue-400 p-14 text-center shadow-lg rounded-lg text-white text-5xl font-bold;
                    }
                }
                @layer components {
                    .red-box {
                        @apply bg-red-400 p-14 text-center shadow-lg rounded-lg text-white text-5xl font-bold;
                    }
                }
            </style>
        ''')
        #########################################
        with ui.row().classes('w-full'):
            with ui.card():
                self.teamAButton = ui.button('00', on_click=lambda: self.addGame(1)).classes('blue-box')
                with ui.row().classes('text-4xl w-full'):
                    ui.button(icon='timer', color=TACOLOR_LIGHT, on_click=lambda: self.addTimeout(1)).props('outline round').classes('shadow-lg')
                    self.timeoutsA = ui.row()
                    ui.space()
                    self.serveA = ui.icon(name='sports_volleyball', color=TACOLOR_VLIGHT)
                    self.serveA.on('click', lambda: self.changeServe(1))
            ui.space()
            with ui.column().classes('justify-center'):
                with ui.row().classes('w-full justify-center'):
                    self.teamASet = ui.button('0', color='gray-700', on_click=lambda: self.addSet(1)).classes('text-white text-2xl')
                    with ui.row():
                        self.scores = ui.grid(columns=2).classes('justify-center') 
                    self.teamBSet = ui.button('0', color='gray-700', on_click=lambda: self.addSet(2)).classes('text-white text-2xl')
                self.set_selector = ui.pagination(1, self.sets_limit, direction_links=True, on_change=lambda e: self.switchToSet(e.value)).props('color=grey active-color=teal')        
            ui.space()
            with ui.card():
                self.teamBButton = ui.button('00', color='red', on_click=lambda: self.addGame(2)).classes('red-box')
                with ui.row().classes('text-4xl w-full'):
                    ui.button(icon='timer', color=TBCOLOR_LIGHT, on_click=lambda: self.addTimeout(2)).props('outline round').classes('shadow-lg ')
                    self.timeoutsB = ui.row() 
                    ui.space()
                    self.serveB = ui.icon(name='sports_volleyball', color=TBCOLOR_VLIGHT)
                    self.serveB.on('click', lambda: self.changeServe(2))
            

        with ui.row().classes("w-full justify-right"):
            self.visibility_button = ui.button(icon='visibility', color=VISIBLE_ON_COLOR, on_click=self.switchVisibility).props('round').classes('text-white')
            self.simple_button = ui.button(icon='grid_on', color=FULL_SCOREBOARD_COLOR, on_click=self.switchSimpleMode).props('round').classes('text-white')
            self.undo_button = ui.button(icon='undo', color=UNDO_COLOR, on_click=lambda: self.switchUndo(self.undo_button)).props('round').classes('text-white')    
            ui.space()
            ui.button(icon='keyboard_arrow_right', color='stone-500', on_click=lambda: self.tabs.set_value(Customization.CONFIG_TAB)).props('round').classes('text-white')    
                
        self.updateUI(False)
        self.logger.info('Initialized gui')
        

    def computeCurrentSet(self, current_state):
        t1sets = current_state.getSets(1)
        t2sets = current_state.getSets(2)
        current_sets =  t1sets + t2sets
        if self.matchFinished(t1sets, t2sets) != True:
            current_sets += 1
        return current_sets

    def matchFinished(self, t1sets, t2sets):
        limit = self.sets_limit
        soft_limit = 2 if self.sets_limit == 3 else 3
        if (t1sets + t2sets < limit and t1sets < soft_limit and t2sets < soft_limit):
            return False
        self.logger.info('Match finished')
        return True

    def updateUI(self, load_from_backend=False):
        global visible
        self.logger.info('Updating UI...')
        if load_from_backend or self.conf.cache:
            self.logger.info('loading data from backend')
            self.current_customize_state.setModel(self.backend.getCurrentCustomizationStateModel())
            update_state = State(self.backend.getCurrentStateModel())
            visible = self.backend.isVisible()
        else:
            update_state = self.main_state
            
        current_set = self.computeCurrentSet(update_state)
        self.updateUIServe(update_state)
        self.updateUISets(update_state)
        self.updateUIGames(update_state)
        self.updateUITimeouts(update_state)
        self.updateUICurrentSet(current_set)
        self.updateUIVisible(visible)
        clientSimple = ClientStorage.load(ClientStorage.SIMPLE_MODE, None)
        if clientSimple != None:
            self.switchSimpleMode(clientSimple)

    def updateUIGames(self, update_state):
        self.hold()
        for i in range(1, self.sets_limit+1):
            teamA_game_int = update_state.getGame(1, i)
            teamB_game_int = update_state.getGame(2, i)
            if (i == self.current_set):
                self.teamAButton.set_text(f'{teamA_game_int:02d}')
                self.teamBButton.set_text(f'{teamB_game_int:02d}')
            self.main_state.setGame(i, 1, str(teamA_game_int))
            self.main_state.setGame(i, 2, str(teamB_game_int))
        self.updateUIGamesTable(update_state)
        self.release()

    def updateUIGamesTable(self, update_state):
        logo1 = self.current_customize_state.getTeamLogo(1)
        logo2 = self.current_customize_state.getTeamLogo(2)
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
            match_finished = self.matchFinished(update_state.getSets(1), update_state.getSets(2))
            for i in range(1, self.sets_limit+1):
                teamA_game_int = update_state.getGame(1, i)
                teamB_game_int = update_state.getGame(2, i)
                if (teamA_game_int + teamB_game_int > 0):
                    lastWithoutZeroZero = i

            for i in range(1, self.sets_limit+1):
                teamA_game_int = update_state.getGame(1, i)
                teamB_game_int = update_state.getGame(2, i)
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

    def updateUITimeouts(self, update_state):
        self.hold()
        self.changeUITimeout(1, update_state.getTimeout(1))
        self.changeUITimeout(2, update_state.getTimeout(2))
        self.release()

    def updateUIServe(self, update_state):    
        self.hold()
        match update_state.getCurrentServe():
            case State.SERVE_NONE:
                self.changeServe(0)
            case State.SERVE_1:
                self.changeServe(1)
            case State.SERVE_2:
                self.changeServe(2)
        self.release()

    def updateUISets(self, update_state):
        self.hold()
        t1sets = update_state.getSets(1)
        t2sets = update_state.getSets(2)
        self.main_state.setSets(1, str(t1sets))
        self.main_state.setSets(2, str(t2sets))
        self.teamASet.set_text(str(t1sets))
        self.teamBSet.set_text(str(t2sets))
        self.release()

    def updateUICurrentSet(self, set):
        self.hold()
        self.main_state.setCurrentSet(set)
        self.set_selector.set_value(set)
        self.release()

    def updateUIVisible(self, enabled):
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

    def releaseHoldAndsendState(self):
        self.release()
        if self.holdUpdate == 0:
            self.sendState()

    def sendState(self):
        if (self.holdUpdate == 0):
            self.backend.save(self.main_state, self.simple)

    def reset(self):
        self.logger.info('Reset called')
        self.backend.reset(self.main_state)
        self.updateUI(True)

    def changeServe(self, team, force=False):
        match team:
            case 1:
                self.main_state.setCurrentServe(State.SERVE_1)
                if self.serveA.props['color']==TACOLOR_HIGH and force != True:
                    self.serveA.props(f'color={TACOLOR_VLIGHT}')
                    self.main_state.setCurrentServe(State.SERVE_NONE)
                else:                             
                    self.serveA.props(f'color={TACOLOR_HIGH}')
                self.serveB.props(f'color={TBCOLOR_VLIGHT}')
            case 2:
                self.main_state.setCurrentServe(State.SERVE_2)
                if self.serveB.props['color']==TBCOLOR_HIGH and force != True:
                    self.serveB.props(f'color={TBCOLOR_VLIGHT}')
                    self.main_state.setCurrentServe(State.SERVE_NONE)
                else:                             
                    self.serveB.props(f'color={TBCOLOR_HIGH}')
                self.serveA.props(f'color={TACOLOR_VLIGHT}')
            case 0:
                self.main_state.setCurrentServe(State.SERVE_NONE)
                self.serveB.props(f'color={TBCOLOR_VLIGHT}')
                self.serveA.props(f'color={TACOLOR_VLIGHT}')
        self.sendState()

    def addTimeout(self, team):
        if team == 1:
            color = TACOLOR_MEDIUM
            container = self.timeoutsA
        else:
            color = TBCOLOR_MEDIUM
            container = self.timeoutsB
        if self.undo:
            if len(list(container)) > 0:
                container.remove(0) if list(container) else None
            self.switchUndo(True)
        else:        
            if len(list(container)) < 2:
                with container:
                    ui.icon(name='radio_button_unchecked', color=color, size='12px')
            else:
                container.clear()
        self.main_state.setTimeout(team, len(list(container)))
        self.sendState()

    def changeUITimeout(self, team, value):
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
        self.main_state.setTimeout(team, len(list(container))) 

    def addGame(self, team):
        if self.preventAdditionalPoints():
            return
        self.hold()
        if team == 1:
            button = self.teamAButton
            rival_score = int(self.teamBButton.text)
            self.changeServe(1, True)
        else:
            button = self.teamBButton
            rival_score = int(self.teamAButton.text)
            self.changeServe(2, True)
        current = self.addIntToButton(button)
        self.main_state.setGame(self.current_set, team, current)
        if (current >=  self.getGameLimit(self.current_set) and (current - rival_score > 1)):
            self.addSet(team)
        self.releaseHoldAndsendState()

    def setTeamName(self, team, name):
        self.main_state.setTeamName(team, name)

    def getTeamName(self, team):
        return self.main_state.getTeamName(team)

    def getCurrentModel(self):
        return self.main_state.getCurrentModel()
    
    def isShowLogos(self):
        return self.main_state.isShowLogos()
    
    def setShowLogos(self, show):
        self.main_state.setShowLogos(show)

    def getGameLimit(self, set):
        if set == self.sets_limit:
            return self.points_limit_last_set
        else:
            return self.points_limit 

    def addSet(self, team, roll2zero=True):
        if self.preventAdditionalPoints():
            return
        self.hold()
        button = self.teamASet
        if team == 2: button = self.teamBSet
        soft_limit = 2 if self.sets_limit == 3 else 3
        current = self.addIntToButton(button, soft_limit if roll2zero else soft_limit+1, False)
        self.main_state.setSets(team, current)
        self.changeUITimeout(1, 0)
        self.changeUITimeout(2, 0)
        self.changeServe(0)
        self.switchToSet(self.computeCurrentSet(self.main_state))
        self.release()

    def preventAdditionalPoints(self):
        t1sets = self.main_state.getSets(1)
        t2sets = self.main_state.getSets(2)
        if not self.undo and self.matchFinished(t1sets, t2sets):
            return True
        return False

    def switchToSet(self, set):
        if (self.current_set != set):
            self.current_set = set
            self.updateUICurrentSet(self.current_set)
            self.updateUIGames(self.main_state)

    def switchVisibility(self):
        if self.visible:
            self.visible = False
            self.visibility_button.set_icon('visibility_off')
        else:
            self.visible = True
            self.visibility_button.set_icon('visibility')
        self.updateUIVisible(self.visible)
        self.backend.changeOverlayVisibility(self.visible)

    def switchSimpleMode(self, forceValue=None):
        self.hold()
        if (forceValue == None and self.simple == True) or forceValue == False:
            self.simple = False
            self.simple_button.set_icon('grid_on')
            self.simple_button.props('color='+FULL_SCOREBOARD_COLOR)
        elif (forceValue == None and self.simple == False) or forceValue == True:
            self.simple = True
            self.simple_button.set_icon('window')
            self.simple_button.props('color='+SIMPLE_SCOREBOARD_COLOR)
            self.backend.reduceGamesToOne()
        if forceValue == None:
            ClientStorage.save(ClientStorage.SIMPLE_MODE, self.simple)
        self.releaseHoldAndsendState()  

    def switchUndo(self, reset=False):
        if self.undo:
            self.undo = False
            self.undo_button.set_icon('undo')
            self.undo_button.props('color='+UNDO_COLOR)
        elif reset != True:
            self.undo = True
            self.undo_button.set_icon('redo')
            self.undo_button.props('color='+DO_COLOR)


    def addIntToButton(self, button, limit=99, force_digits=True):
        current = int(button.text)
        if self.undo:
            if (current != 0):
                current -= 1
            self.switchUndo(True)
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
        self.updateUI(True)