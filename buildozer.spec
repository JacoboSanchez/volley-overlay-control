[app]
# (Requerido) Título de tu aplicación
title = Scoreboard
# (Requerido) Nombre del paquete, sin guiones ni espacios
package.name = volleyscoreboard
# (Requerido) Dominio del paquete, para crear un identificador único
package.domain = org.jasanlo
# (Requerido) Directorio que contiene tu código
source.dir = .
# (Requerido) Extensiones de archivo a incluir en el APK
source.include_exts = py, txt, md, json, ini
# Directorios a incluir explícitamente (tu código principal está en 'app')
source.include_dirs = app
# (Requerido) Directorios a excluir del APK (reduce el tamaño)
source.exclude_dirs = tests, .github, .venv, __pycache__
# Versión de tu aplicación
version = 0.1
# (Requerido) Lista de dependencias de Python
# Sacado de tu 'requirements.txt'. Excluimos las de testing.
requirements = python3,nicegui==3.2.0,requests,python-dotenv,urllib3,charset-normalizer,idna,certifi,typing-extensions,python-socketio,python-engineio,bidict,starlette,pydantic,anyio,sniffio,itsdangerous,aiofiles,aiohttp,vbuild,asyncio,fastapi,annotated_doc,markdown2,pygments,jinja2,markupsafe,docutils,ifaddr,uvicorn,watchfiles,click,h11,wsproto,chardet
orientation = portrait
# (Opcional) Icono de la aplicación
# icon.filename = %(source.dir)s/icon.png
# (bool) Indicate if the application should be fullscreen or not
fullscreen = 1
remote.origin.url=https://github.com/JacoboSanchez/volley-overlay-control.git
[buildozer]
# Nivel de detalle de los logs (2 = debug, muy útil para la primera vez)
log_level = 2
# Advertir si se ejecuta como root
warn_on_root = 1

# --- Configuración Específica de Android ---
[android]
# (Requerido) Lista de permisos que necesita la app.
# INTERNET es crucial porque usas 'requests' y NiceGUI es una app web.
# FOREGROUND_SERVICE puede ayudar a que el servidor Python siga funcionando
# si la app pasa a segundo plano.
android.permissions = INTERNET, FOREGROUND_SERVICE, ACCESS_NETWORK_STATE
# Nivel de API de Android (SDK 33 = Android 13)
android.api = 33
# Nivel mínimo de API (SDK 21 = Android 5.0)
android.minapi = 24
# SDK de Android a usar para la compilación
android.sdk = 33
# Arquitecturas a compilar. 'arm64-v8a' es la más común para teléfonos modernos.
android.archs = arm64-v8a
# (IMPORTANTE) Esta es la clave para apps web.
# Usa el 'bootstrap' de WebView en lugar del de Kivy/Pygame.
p4a.bootstrap = webview
# (IMPORTANTE) El puerto en el que se ejecuta tu app NiceGUI.
# Tu 'main.py' y 'docker-compose.yml' usan 8080.
p4a.port = 8080
android.env.APP_TITLE = Scoreboard