from nicegui import ui
from app.components.score_button import ScoreButton

class CenterPanel:
    def __init__(self, gui):
        self.gui = gui

    async def create(self):
        with ui.column().classes('h-full'):
            with ui.row().classes('w-full justify-center'):
                self.gui.teamASet = ScoreButton.create(
                    self.gui, 1, True, '0', 'gray-700', 'text-white text-2xl'
                ).mark('team-1-sets')

                with ui.row().classes('justify-center items-start gap-x-2'):
                    with ui.column().classes('items-center gap-y-0'):
                        logo1_src = self.gui.current_customize_state.get_team_logo(1)
                        self.gui.teamA_logo = ui.image(source=logo1_src).classes('w-6 h-6').mark('team-1-logo')
                        self.gui.teamA_scores_container = ui.column().classes('items-center gap-y-0 min-h-24')

                    with ui.column().classes('items-center gap-y-0'):
                        logo2_src = self.gui.current_customize_state.get_team_logo(2)
                        self.gui.teamB_logo = ui.image(source=logo2_src).classes('w-6 h-6').mark('team-2-logo')
                        self.gui.teamB_scores_container = ui.column().classes('items-center gap-y-0 min-h-24')

                self.gui.teamBSet = ScoreButton.create(
                    self.gui, 2, True, '0', 'gray-700', 'text-white text-2xl'
                ).mark('team-2-sets')

            self.gui.set_selector = ui.pagination(
                1, self.gui.sets_limit, direction_links=True, on_change=lambda e: self.gui.switch_to_set(e.value)
            ).props('color=grey active-color=teal').classes('w-full justify-center').mark('set-selector')
            
            if self.gui.conf.show_preview and self.gui.conf.output is not None:
                self.gui.preview_container = ui.column()
                if self.gui.preview_visible:
                    with self.gui.preview_container:
                        await self.gui.create_iframe()
