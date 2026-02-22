from nicegui import ui
from app.components.score_button import ScoreButton
from app.theme import GAME_BUTTON_CLASSES

class TeamPanel:
    def __init__(self, gui, team_id, button_color, timeout_light_color, serve_vlight_color):
        self.gui = gui
        self.team_id = team_id
        self.button_color = button_color
        self.timeout_light_color = timeout_light_color
        self.serve_vlight_color = serve_vlight_color

    def create(self):
        with ui.card(align_items='begin'):
            with ui.row() if self.gui.is_portrait else ui.column():
                button = ScoreButton.create(
                    self.gui, 
                    team_id=self.team_id, 
                    is_set_button=False, 
                    text='00', 
                    color=self.button_color, 
                    classes_str=GAME_BUTTON_CLASSES
                ).mark(f'team-{self.team_id}-score')

                if self.gui.is_portrait:
                    with ui.column().classes('text-4xl h-full'):
                        serve_icon = ui.icon(name='sports_volleyball', color=self.serve_vlight_color).mark(f'team-{self.team_id}-serve')
                        ui.space()
                        ui.button(icon='timer', color=self.timeout_light_color,
                                on_click=lambda: self.gui.add_timeout(self.team_id)).props('outline round').mark(f'team-{self.team_id}-timeout').classes('shadow-lg')
                        timeouts = ui.row().mark(f'team-{self.team_id}-timeouts-display')
                        serve_icon.on('click', lambda: self.gui.change_serve(self.team_id))  
                else: 
                    with ui.row().classes('text-4xl w-full'):
                        ui.button(icon='timer', color=self.timeout_light_color,
                                on_click=lambda: self.gui.add_timeout(self.team_id)).props('outline round').mark(f'team-{self.team_id}-timeout').classes('shadow-lg')
                        timeouts = ui.column().mark(f'team-{self.team_id}-timeouts-display')
                        ui.space()
                        serve_icon = ui.icon(name='sports_volleyball', color=self.serve_vlight_color).mark(f'team-{self.team_id}-serve')
                        serve_icon.on('click', lambda: self.gui.change_serve(self.team_id))
        return button, timeouts, serve_icon
