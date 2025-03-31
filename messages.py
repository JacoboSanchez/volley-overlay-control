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
    OVERLAY_LINK = "Overlay"
    CONTROL_LINK = "Control"
    RESET_LINKS = "Reset"
    LOCAL = "Local"
    VISITOR = "Visitor"
    LOADING = "Loading..."
    INVALID_OVERLAY_CONTROL_TOKEN = "Invalid overlay control token"
    USERNAME = "Username"
    PASSWORD = "Password"
    WRONG_USER_NAME = "Wrong username or password"
    LOGOUT = "Logout"

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
            OVERLAY_LINK:"Overlay",
            CONTROL_LINK:"Control",
            RESET_LINKS:"Reset",
            LOCAL:"Local",
            VISITOR:"Visitante",
            LOADING:"Cargando...",
            INVALID_OVERLAY_CONTROL_TOKEN:"Token de control inválido",
            USERNAME:"Usuario",
            PASSWORD:"Contraseña",
            WRONG_USER_NAME:"Usuario o contraseña incorrectos",
            LOGOUT: "Desconectar"
          }
        }

    def get(message:str) -> str:
        local_messages = Messages.messages.get(os.environ.get('LANGUAGE', ''), {})
        return local_messages.get(message, message)

