from nicegui import ui
import logging
import sys
from conf import Conf
from backend import Backend
from state import State
from customization import Customization
import customization_page

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

CYAN="\033[1;36m%s\033[1;0m"

conf = Conf()
backend = Backend(conf)
current_customize_state = Customization(backend.getCurrentCustomizationStateModel())
main_state = State() 
visible = backend.isVisible()

logging.addLevelName( logging.DEBUG, "\033[33m%s\033[1;0m" % logging.getLevelName(logging.DEBUG))
logging.addLevelName( logging.INFO, "\033[1;33m%s\033[1;0m" % logging.getLevelName(logging.INFO))
logging.addLevelName( logging.WARNING, "\033[1;31m%s\033[1;0m" % logging.getLevelName(logging.WARNING))
logging.addLevelName( logging.ERROR, "\033[1;41m%s\033[1;0m" % logging.getLevelName(logging.ERROR))
root = logging.getLogger()
root.setLevel(conf.logging_level)
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter( CYAN % '%(asctime)s'+' %(levelname)s '+"\033[32m%s\033[1;0m" % '[%(name)s]'+':  %(message)s'))
root.addHandler(handler)


class GUI:
    
    def __init__(self):
        global conf
        self.logger = logging.getLogger("GUI")
        self.undo = False
        self.simple = False
        self.holdUpdate = 0
        self.glimit = 25
        self.glimit_last = 15
        self.slimit = 5
        self.current_set = 1
        self.visible = True
    

    def init(self):
        self.logger.info('Initialize gui')
        match conf.darkMode:
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
                        @apply bg-blue-400 p-14 text-center shadow-lg rounded-lg text-white text-6xl font-bold;
                    }
                }
                @layer components {
                    .red-box {
                        @apply bg-red-400 p-14 text-center shadow-lg rounded-lg text-white text-6xl font-bold;
                    }
                }
            </style>
        ''')
        #########################################
        with ui.row().classes('w-full'):
            with ui.card():
                self.teamAButton = ui.button('00', on_click=lambda: self.addGame(1)).classes('blue-box')
                with ui.row().classes('text-3xl w-full'):
                    ui.button(icon='timer', color=TACOLOR_LIGHT, on_click=lambda: self.addTimeout(1)).props('outline round').classes('shadow-lg')
                    self.timeoutsA = ui.row()
                    ui.space()
                    self.serveA = ui.icon(name='sports_volleyball', color=TACOLOR_VLIGHT)
                    self.serveA.on('click', lambda: self.changeServe(1))
            self.teamASet = ui.button('0', color='gray-700', on_click=lambda: self.addSet(1)).classes('text-white text-2xl')
            ui.space()   
            with ui.card():
                self.scores = ui.grid(columns=2) 
            ui.space()
            self.teamBSet = ui.button('0', color='gray-700', on_click=lambda: self.addSet(2)).classes('text-white text-2xl')
            with ui.card():
                self.teamBButton = ui.button('00', color='red', on_click=lambda: self.addGame(2)).classes('red-box')
                with ui.row().classes('text-3xl w-full'):
                    ui.button(icon='timer', color=TBCOLOR_LIGHT, on_click=lambda: self.addTimeout(2)).props('outline round').classes('shadow-lg').props('checked-icon=sports-volley')
                    self.timeoutsB = ui.row() 
                    ui.space()
                    self.serveB = ui.icon(name='sports_volleyball', color=TBCOLOR_VLIGHT)
                    self.serveB.on('click', lambda: self.changeServe(2))
            ui.space()

        with ui.row().classes("w-full justify-center"):
            self.set_selector = ui.pagination(1, 5, direction_links=True, on_change=lambda e: self.switchToSet(e.value))
            

        with ui.row().classes("w-full justify-right"):
            self.visibility_button = ui.button(icon='visibility', color='green-600', on_click=self.switchVisibility).props('round').classes('text-white')
            self.simple_button = ui.button(icon='grid_on', color='yellow-600', on_click=self.switchSimpleMode).props('round').classes('text-white')
            #simple_button.set_visibility(False)
            self.undo_button = ui.button(icon='undo', color='orange-500', on_click=lambda: self.switchUndo(self.undo_button)).props('round').classes('text-white')    
            ui.space()
            ui.button(icon='sync', color='green-500', on_click=lambda: ui.navigate.to('/refresh')).props('round').classes('text-white')    
            ui.button(icon='settings', color='blue-500', on_click=lambda: ui.navigate.to('/customize')).props('round').classes('text-white')    
            self.dialog = ui.dialog()
            with self.dialog, ui.card():
                ui.label('Reset?')
                with ui.row():
                    ui.button(color='green-500', icon='done', on_click=lambda: self.dialog.submit(True))
                    ui.button(color='red-500', icon='close', on_click=lambda: self.dialog.submit(False))
            ui.button(icon='recycling', color='red-700', on_click=self.askReset).props('round').classes('text-white')
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
        limit = self.slimit
        soft_limit = 2 if self.slimit == 3 else 3
        if (t1sets + t2sets < limit and t1sets < soft_limit and t2sets < soft_limit):
            return False
        self.logger.info('Match finished')
        return True

    def updateUI(self, load_from_backend=False):
        global visible
        self.logger.info('Updating UI...')
        if load_from_backend or conf.cache:
            self.logger.info('loading data from backend')
            current_customize_state.setModel(backend.getCurrentCustomizationStateModel())
            update_state = State(backend.getCurrentStateModel())
            visible = backend.isVisible()
        else:
            update_state = main_state
            
        current_set = self.computeCurrentSet(update_state)
        self.updateUIServe(update_state)
        self.updateUISets(update_state)
        self.updateUIGames(update_state)
        self.updateUITimeouts(update_state)
        self.updateUICurrentSet(current_set)
        self.updateUIVisible(visible)

    def updateUIGames(self, update_state):
        self.hold()
        for i in range(1, self.slimit+1):
            teamA_game_int = update_state.getGame(1, i)
            teamB_game_int = update_state.getGame(2, i)
            if (i == self.current_set):
                self.teamAButton.set_text(f'{teamA_game_int:02d}')
                self.teamBButton.set_text(f'{teamB_game_int:02d}')
            main_state.setGame(i, 1, str(teamA_game_int))
            main_state.setGame(i, 2, str(teamB_game_int))
        self.updateUIGamesTable(update_state)
        self.release()

    def updateUIGamesTable(self, update_state):
        logo1 = current_customize_state.getTeamLogo(1)
        logo2 = current_customize_state.getTeamLogo(2)
        self.scores.clear()
        with self.scores:
            if (logo1 != None and logo1 != Customization.DEFAULT_IMAGE):
                ui.image(source=logo1).classes('w-5 h-5 m-auto')
            else: 
                ui.icon(name='sports_volleyball', color='blue', size='xs')
                
            if (logo2 != None and logo2 != Customization.DEFAULT_IMAGE):
                ui.image(source=logo2).classes('w-5 h-5 m-auto')
            else: 
                ui.icon(name='sports_volleyball', color='red', size='xs')
            lastWithoutZeroZero = 1
            for i in range(1, self.slimit+1):
                teamA_game_int = update_state.getGame(1, i)
                teamB_game_int = update_state.getGame(2, i)
                if (teamA_game_int + teamB_game_int > 0):
                    lastWithoutZeroZero = i

            for i in range(1, self.slimit+1):
                teamA_game_int = update_state.getGame(1, i)
                teamB_game_int = update_state.getGame(2, i)
                if (i > 1 and i > lastWithoutZeroZero):
                    break
                if (i == self.current_set & i < self.slimit):
                    break
                label1 = ui.label(f'{teamA_game_int:02d}')
                label2 = ui.label(f'{teamB_game_int:02d}')
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
        main_state.setSets(1, str(t1sets))
        main_state.setSets(2, str(t2sets))
        self.teamASet.set_text(str(t1sets))
        self.teamBSet.set_text(str(t2sets))
        self.release()

    def updateUICurrentSet(self, set):
        self.hold()
        main_state.setCurrentSet(set)
        self.set_selector.set_value(set)
        self.release()

    def updateUIVisible(self, enabled):
        if enabled:
            self.visibility_button.set_icon('visibility')
        else:
            self.visibility_button.set_icon('visibility_off')


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
            backend.save(main_state, self.simple)

    def reset(self):
        self.logger.info('Reset called')
        backend.reset(main_state)
        self.updateUI(True)

    def changeServe(self, team, force=False):
        match team:
            case 1:
                main_state.setCurrentServe(State.SERVE_1)
                if self.serveA.props['color']==TACOLOR_HIGH and force != True:
                    self.serveA.props(f'color={TACOLOR_VLIGHT}')
                    main_state.setCurrentServe(State.SERVE_NONE)
                else:                             
                    self.serveA.props(f'color={TACOLOR_HIGH}')
                self.serveB.props(f'color={TBCOLOR_VLIGHT}')
            case 2:
                main_state.setCurrentServe(State.SERVE_2)
                if self.serveB.props['color']==TBCOLOR_HIGH and force != True:
                    self.serveB.props(f'color={TBCOLOR_VLIGHT}')
                    main_state.setCurrentServe(State.SERVE_NONE)
                else:                             
                    self.serveB.props(f'color={TBCOLOR_HIGH}')
                self.serveA.props(f'color={TACOLOR_VLIGHT}')
            case 0:
                main_state.setCurrentServe(State.SERVE_NONE)
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
                    ui.icon(name='radio_button_unchecked', color=color, size='xs')
            else:
                container.clear()
        main_state.setTimeout(team, len(list(container)))
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
                ui.icon(name='radio_button_unchecked', color=color, size='xs')
        main_state.setTimeout(team, len(list(container))) 

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
        main_state.setGame(self.current_set, team, current)
        if (current >=  self.getGameLimit(self.current_set) and (current - rival_score > 1)):
            self.addSet(team)
        self.releaseHoldAndsendState()

    def getGameLimit(self, set):
        if set == self.slimit:
            return self.glimit_last
        else:
            return self.glimit 

    def addSet(self, team, roll2zero=True):
        if self.preventAdditionalPoints():
            return
        self.hold()
        button = self.teamASet
        if team == 2: button = self.teamBSet
        soft_limit = 2 if self.slimit == 3 else 3
        current = self.addIntToButton(button, soft_limit if roll2zero else soft_limit+1, False)
        main_state.setSets(team, current)
        self.changeUITimeout(team, 0)
        self.switchToSet(self.computeCurrentSet(main_state))
        self.release()

    def preventAdditionalPoints(self):
        t1sets = main_state.getSets(1)
        t2sets = main_state.getSets(2)
        if not self.undo and self.matchFinished(t1sets, t2sets):
            return True
        return False

    def switchToSet(self, set):
        if (self.current_set != set):
            self.current_set = set
            self.updateUICurrentSet(self.current_set)
            self.updateUIGames(main_state)

    def switchVisibility(self):
        if self.visible:
            self.visible = False
            self.visibility_button.set_icon('visibility_off')
        else:
            self.visible = True
            self.visibility_button.set_icon('visibility')
        self.updateUIVisible(self.visible)
        backend.changeOverlayVisibility(self.visible)

    def switchSimpleMode(self):
        self.hold()
        if self.simple == True:
            self.simple = False
            self.simple_button.set_icon('grid_on')
        else:
            self.simple = True
            self.simple_button.set_icon('window')
            backend.reduceGamesToOne()
        self.releaseHoldAndsendState()

    def switchUndo(self, reset=False):
        if self.undo:
            self.undo = False
            self.undo_button.set_icon('undo')
            self.undo_button.props('color=orange-500')
        elif reset != True:
            self.undo = True
            self.undo_button.set_icon('redo')
            self.undo_button.props('color=orange-900')


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

    async def askReset(self):
        result = await self.dialog
        if result:
            self.reset()

gui = GUI()
ui.page('/customize')

@ui.page("/refresh")
def refresh():
    gui.updateUI(True)
    ui.navigate.to('/')

@ui.page("/")
def main():
    gui.init()
    
    

custom_favicon='<svg xmlns="http://www.w3.org/2000/svg" enable-background="new 0 0 24 24" height="24px" viewBox="0 0 24 24" width="24px" fill="#5f6368"><g><rect fill="none" height="24" width="24"/></g><g><g><path d="M12,2C6.48,2,2,6.48,2,12c0,5.52,4.48,10,10,10s10-4.48,10-10C22,6.48,17.52,2,12,2z M13,4.07 c3.07,0.38,5.57,2.52,6.54,5.36L13,5.65V4.07z M8,5.08c1.18-0.69,3.33-1.06,3-1.02v7.35l-3,1.73V5.08z M4.63,15.1 C4.23,14.14,4,13.1,4,12c0-2.02,0.76-3.86,2-5.27v7.58L4.63,15.1z M5.64,16.83L12,13.15l3,1.73l-6.98,4.03 C7.09,18.38,6.28,17.68,5.64,16.83z M10.42,19.84 M12,20c-0.54,0-1.07-0.06-1.58-0.16l6.58-3.8l1.36,0.78 C16.9,18.75,14.6,20,12,20z M13,11.42V7.96l7,4.05c0,1.1-0.23,2.14-0.63,3.09L13,11.42z"/></g></g></svg>'
ui.run(title=conf.title, favicon=custom_favicon, on_air=conf.onair, port=conf.port)