"""Backend-side i18n — reduced to the few strings still read by the
backend after the retirement of the NiceGUI UI.

All user-visible labels now live in the React frontend
(``frontend/src/i18n.jsx``).  The only strings kept here are the default
team names (``LOCAL`` / ``VISITOR``) used as dictionary keys for
``Customization.predefined_teams`` when ``APP_TEAMS`` is not provided.
"""

from app.env_vars_manager import EnvVarsManager


class Messages:
    LOCAL = "Local"
    VISITOR = "Visitor"

    messages = {
        "es": {
            LOCAL: "Local",
            VISITOR: "Visitante",
        },
        "en": {},
    }

    @staticmethod
    def get(message: str) -> str:
        lang = EnvVarsManager.get_env_var('SCOREBOARD_LANGUAGE', '')
        return Messages.messages.get(lang, {}).get(message, message)
