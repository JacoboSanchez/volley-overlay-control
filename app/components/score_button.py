from nicegui import ui

class ScoreButton:
    @staticmethod
    def create(gui, team_id, is_set_button, text, color, classes_str=None):
        def handle_press():
            if not is_set_button:
                ui.run_javascript('if (navigator.vibrate) navigator.vibrate(50)')
            gui.handle_button_press(team_id, is_set_button=is_set_button)

        button = ui.button(text, color=color)
        button.on('mousedown', handle_press)
        button.on('touchstart', handle_press, [])
        button.on('mouseup', lambda: gui.handle_button_release(team_id, is_set_button=is_set_button))
        button.on('touchend', lambda: gui.handle_button_release(team_id, is_set_button=is_set_button))
        button.on('touchmove', gui.handle_press_cancel)
        if classes_str:
            button.classes(classes_str)
        return button
