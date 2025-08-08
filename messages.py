import os

class Messages:
    GRADIENT = "Gradient"
    LOGOS = "Logos"
    SET = "Set"
    GAME = "Game"
    HEIGHT = "Height"
    WIDTH = "Width"
    HPOS = "Pos. X"
    VPOS = "Pos. Y"
    ASK_RESET = "Reset score?"
    ASK_RELOAD = "Reload data?"
    ASK_LOGOUT = "Logout?"
    OVERLAY_LINK = "Overlay output page"
    CONTROL_LINK = "Control page"
    RESET_LINKS = "Change overlay"
    LOCAL = "Local"
    VISITOR = "Visitor"
    LOADING = "Loading..."
    INVALID_OVERLAY_CONTROL_TOKEN = "Invalid overlay control token"
    OVERLAY_CONFIGURATION_REQUIRED = "Overlay control URL not provided"
    EMPTY_OVERLAY_CONTROL_TOKEN = "Empty overlay control token"
    USERNAME = "Username"
    PASSWORD = "Password"
    WRONG_USER_NAME = "Wrong username or password"
    LOGOUT = "Logout"
    USE_PREDEFINED_OVERLAYS = "Use predefined overlays",
    OVERLAY_DEPRECATED = "Outdated overlay version, please use a new one"
    LOGIN = "Log in"
    CONTROL_URL = "Control URL"
    COLORS_LOCK = "Colors"
    ICONS_LOCK = "Icons"
    LOCK = "Lock:"
    OPTIONS_TITLE = "Configuration"
    AUTO_HIDE = "Auto-hide scoreboard"
    HIDE_TIMEOUT = "Hide after (seconds)"
    AUTO_SIMPLE_MODE = "Show only current set while playing"
    VISUALIZATION_OPTIONS = "Webpage options"
    HIDE_OPTIONS = "Hide options"
    CLOSE = "Close"

    messages = {
        "es": {
            GRADIENT : "Gradiente",
            LOGOS:"Logos",
            SET:"Set",
            GAME:"Juego",
            HEIGHT:"Altura",
            WIDTH:"Ancho",
            HPOS:"Pos. X",
            VPOS:"Pos. Y",
            OVERLAY_LINK:"Visualizar",
            CONTROL_LINK:"Página de control",
            RESET_LINKS:"Cambiar overlay",
            LOCAL:"Local",
            VISITOR:"Visitante",
            LOADING:"Cargando...",
            INVALID_OVERLAY_CONTROL_TOKEN:"Token de control inválido",
            OVERLAY_CONFIGURATION_REQUIRED:"La URL de control es necesaria",
            EMPTY_OVERLAY_CONTROL_TOKEN:"Token de control vacío",
            USERNAME:"Usuario",
            PASSWORD:"Contraseña",
            WRONG_USER_NAME:"Usuario o contraseña incorrectos",
            LOGOUT: "Desconectar",
            USE_PREDEFINED_OVERLAYS: "Usar overlays predefinidos",
            OVERLAY_DEPRECATED: "Overlay no soportado, cambiar a uno actual",
            LOGIN:"Entrar",
            CONTROL_URL:"Página de control",
            ASK_RESET:"¿Reiniciar marcador?",
            ASK_RELOAD:"¿Recargar valores?",
            ASK_LOGOUT:"¿Desconectar?",
            COLORS_LOCK:"Color",
            ICONS_LOCK:"Icono",
            LOCK:"Bloquear:",
            OPTIONS_TITLE: "Configuración",
            AUTO_HIDE: "Auto-ocultar marcador",
            HIDE_TIMEOUT: "Ocultar tras (segundos)",
            AUTO_SIMPLE_MODE: "Mostrar solo set actual mientras se juega",
            VISUALIZATION_OPTIONS: "Opciones de página web",
            HIDE_OPTIONS: "Opciones de ocultación",
            CLOSE: "Cerrar"
          }
        }

    def get(message:str) -> str:
        local_messages = Messages.messages.get(os.environ.get('SCOREBOARD_LANGUAGE', ''), {})
        return local_messages.get(message, message)
