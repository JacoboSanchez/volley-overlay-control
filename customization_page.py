from nicegui import ui
from nicegui.events import ValueChangeEventArguments
from conf import Conf
from backend import Backend
from state import State
from customization import Customization
from messages import Messages

@ui.page('/customize')
def get_customization_page():
    CustomizationPage().init()
    

class CustomizationPage:
      configuration = Conf()
      backend = Backend(configuration)
      state  = State(backend.getCurrentStateModel())
      customization = Customization(backend.getCurrentCustomizationStateModel())


      def updateTeamSelection(self, team, logo, tname, color, textColor, selector):
            fallback_name = CustomizationPage.getFallBackTeamName(team)
            team_name = tname if tname != None else fallback_name
            teamValues = Customization.getPredefinedTeams().get(team_name, None)
            if teamValues == None:
                  teamValues = Customization.getPredefinedTeams()[CustomizationPage.getFallBackTeamName(team)]
            ## update gui
            logo.set_source(teamValues[Customization.TEAM_VALUES_ICON])
            color.classes(replace=f'!bg-[{teamValues[Customization.TEAM_VALUES_COLOR]}]')
            textColor.classes(replace=f'!bg-[{teamValues[Customization.TEAM_VALUES_TEXT_COLOR]}]')
            selector.classes(replace=f'!bg-[{teamValues[Customization.TEAM_VALUES_COLOR]}]')
            selector.classes(replace=f'!fg-[{teamValues[Customization.TEAM_VALUES_TEXT_COLOR]}]')
            ## update model
            self.state.setTeamName(team, tname)
            self.customization.setTeamLogo(team, teamValues[Customization.TEAM_VALUES_ICON])
            self.customization.setTeamColor(team, teamValues[Customization.TEAM_VALUES_COLOR])
            self.customization.setTeamTextColor(team, teamValues[Customization.TEAM_VALUES_TEXT_COLOR])

      def updateTeamModelColor(self, team, color, button, textColor=False):
            button.classes(replace=f'!bg-[{color}]')
            if textColor:
                  self.customization.setTeamTextColor(team, color)
            else:
                  self.customization.setTeamColor(team, color)

      def updateModelColor(self, forSet, color, button, textColor=False):
            button.classes(replace=f'!bg-[{color}]')
            button.update()
            if textColor:
                  if forSet:
                        self.customization.setSetTextColor(color)
                  else:
                        self.customization.setGameTextColor(color)
            else:
                  if forSet:
                        self.customization.setSetColor(color)
                  else:
                        self.customization.setGameColor(color)


      def getFallBackTeamName(team):
            return Customization.LOCAL_NAME if team == 1 else Customization.VISITOR_NAME

      def create_team_card(self, team, teamNames):
            with ui.card():
                  with ui.row():
                        team_logo = ui.image(self.customization.getTeamLogo(team)).classes('w-9 h-9 m-auto')
                        self.customization.setTeamLogo(team, self.customization.getTeamLogo(team))
                        selector = ui.select(teamNames, 
                              new_value_mode = 'add-unique', 
                              value = self.state.getTeamName(team),
                              key_generator=lambda k: k,
                              on_change=lambda e: self.updateTeamSelection(team, team_logo, e.value, team_color, team_text_color, selector))
                        team_color = ui.button().classes('w-8 h-8 m-auto')
                        team_text_color = ui.button().classes('w-5 h-5')
                        with team_color:
                              team_color_picker = ui.color_picker(on_pick=lambda e: self.updateTeamModelColor(team, e.color, team_color, False))
                        team_color_picker.q_color.props('default-view=palette no-header no-footer')
                        with team_text_color:
                              team_text_color_picker = ui.color_picker(on_pick=lambda e: self.updateTeamModelColor(team, e.color, team_text_color, True))
                        team_text_color_picker.q_color.props('default-view=palette no-header no-footer')
                        self.updateTeamModelColor(team, self.customization.getTeamColor(team), team_color, False)
                        self.updateTeamModelColor(team, self.customization.getTeamTextColor(team), team_text_color, True)
 
      def save(self):
            state_model = self.state.getCurrentModel()
            sub_model = {clave: state_model[clave] for clave in [State.A_TEAM, State.B_TEAM, State.LOGOS_BOOL] if clave in state_model}
            self.backend.saveJSONState(sub_model)
            self.backend.saveJSONCustomization(self.customization.getModel())
            ui.navigate.to('/')

      def createChooseColor(self, name, forSet = False):
            ui.label(name)
            with ui.row():
                  main_color = ui.button().classes('w-8 h-8 m-auto')
                  main_text_color = ui.button().classes('w-5 h-5')
            with main_color:
                  main_color_picker = ui.color_picker(on_pick=lambda e: self.updateModelColor(forSet, e.color, main_color, False))
            main_color_picker.q_color.props('default-view=palette no-header no-footer')
            with main_text_color:
                  main_text_color_picker = ui.color_picker(on_pick=lambda e: self.updateModelColor(forSet, e.color, main_text_color, True))
            main_text_color_picker.q_color.props('default-view=palette no-header no-footer')
            self.updateModelColor(forSet, self.customization.getSetColor() if forSet else self.customization.getGameColor(), main_color, False)
            self.updateModelColor(forSet, self.customization.getSetTextColor() if forSet else self.customization.getGameTextColor(), main_text_color, True)
            

      def init(self):
            if (self.conf.debug):
                print('Initializing customization page')
            match self.configuration.darkMode:
                  case 'on':
                        ui.dark_mode(True)
                  case 'off':
                        ui.dark_mode(False)
                  case 'auto':
                        ui.dark_mode()
            teamNames = list(Customization.getPredefinedTeams())
            if self.state.getTeamName(1) not in teamNames:
                  teamNames.append(self.state.getTeamName(1))
            if self.state.getTeamName(2) not in teamNames:
                  teamNames.append(self.state.getTeamName(2))
            

            with ui.row():
                  self.create_team_card(1, teamNames)
                  self.create_team_card(2, teamNames)

            with ui.card():
                  with ui.row():
                        ui.switch(Messages.LOGOS, value=self.state.isShowLogos(), on_change=lambda e: self.state.setShowLogos(e.value))
                        ui.switch(Messages.FLAT_COLOR, value=not self.customization.isGlossy() , on_change=lambda e: self.customization.setGlossy(not e.value))
                  with ui.row():
                        self.createChooseColor(Messages.SET, True)
                        self.createChooseColor(Messages.GAME, False)

            with ui.card():
                  with ui.row().classes('place-content-center align-middle    '):
                        ui.number(label=Messages.HEIGHT, value=self.customization.getHeight(), format='%.1f', min=0, max=100,
                              on_change=lambda e: self.customization.setHeight(f'{e.value}'))
                        ui.space()
                        ui.number(label=Messages.WIDTH, value=self.customization.getWidth(), format='%.1f', min=0, max=100,
                              on_change=lambda e: self.customization.setWidth(f'{e.value}'))
                        ui.space()
                        ui.number(label=Messages.HPOS, value=self.customization.getHPos(), format='%.1f', min=-50, max=50,
                              on_change=lambda e: self.customization.setHPos(f'{e.value}'))
                        ui.space()
                        ui.number(label=Messages.VPOS, value=self.customization.getVPos(), format='%.1f', min=-50, max=50,
                              on_change=lambda e: self.customization.setVPos(f'{e.value}'))
                  if self.configuration.output != None:
                        ui.link(Messages.OVERLAY_LINK, self.configuration.output, new_tab=True)
            with ui.row().classes('w-full'):
                  ui.button(icon='save', color='blue-400', on_click=self.save).props('round').classes('text-white')    
                  ui.space()
                  ui.button(icon='close', color='red-400', on_click=lambda: ui.navigate.to('/')).props('round').classes('text-white')    
            if (self.conf.debug):
                print('initialized customization page')