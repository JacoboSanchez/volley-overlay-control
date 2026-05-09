import { createContext, useContext, useState, useCallback, useMemo, ReactNode } from 'react';

type TranslationDict = Record<string, string>;

const translations: Record<string, TranslationDict> = {
  en: {
    // Init screen
    'app.title': 'Volley Scoreboard',
    'app.oidLabel': 'Overlay Control ID (OID)',
    'app.oidPlaceholder': 'my-overlay',
    'app.connect': 'Connect',
    'app.selectOverlay': 'Select Overlay',
    'app.selectOverlayPlaceholder': '— Select —',
    'app.orManualOid': 'or enter OID manually',
    'app.connecting': 'Connecting…',

    // Dialog
    'dialog.ok': 'OK',
    'dialog.cancel': 'Cancel',
    'dialog.setScore': 'Set score — Team {team}',
    'dialog.setSets': 'Set sets won — Team {team}',

    // Control buttons
    'ctrl.hideOverlay': 'Hide overlay',
    'ctrl.showOverlay': 'Show overlay',
    'ctrl.hidePreview': 'Hide preview',
    'ctrl.showPreview': 'Show preview',
    'ctrl.fullScoreboard': 'Full scoreboard',
    'ctrl.simpleScoreboard': 'Simple scoreboard',
    'ctrl.undoLast': 'Undo last action',
    'ctrl.fullscreen': 'Fullscreen',
    'ctrl.exitFullscreen': 'Exit fullscreen',
    'ctrl.lightMode': 'Light mode',
    'ctrl.darkMode': 'Dark mode',
    'ctrl.themeAuto': 'Theme: follow system',
    'ctrl.startMatch': 'Start match',
    'ctrl.reset': 'Reset',
    'ctrl.config': 'Configuration',
    'ctrl.configHint': 'Configuration — or swipe left',

    // Connection status
    'conn.online': 'Live updates connected',
    'conn.reconnecting': 'Reconnecting…',

    // Confirmation dialogs
    'confirm.title': 'Are you sure?',
    'confirm.confirm': 'Confirm',
    'confirm.cancel': 'Cancel',

    // Preview fallback
    'preview.unavailable': 'Preview unavailable',
    'preview.retry': 'Retry',

    // Gesture coachmark / first-run tour
    'tour.skip': 'Skip',
    'tour.prev': 'Back',
    'tour.next': 'Next',
    'tour.done': 'Got it',
    'tour.progress': 'Step {step} of {total}',
    'tour.tap.title': 'Tap to score',
    'tour.tap.body': 'Tap a team panel to add a point. The serve switches automatically.',
    'tour.doubletap.title': 'Double-tap to undo',
    'tour.doubletap.body': 'Double-tap a team panel — or use the undo button — to revert the last point or timeout for that team.',
    'tour.longpress.title': 'Long-press to edit',
    'tour.longpress.body': 'Press and hold a score or set count to set a custom value when something needs a manual fix.',
    'tour.config.title': 'Open configuration',
    'tour.config.body': 'Swipe left, or tap the gear icon top-right, for teams, colors, rules and links.',

    // Share / quick links
    'share.title': 'Share match',

    // Recent-audit drawer (Phase 4.2)
    'history.title': 'History',
    'history.close': 'Close history',
    'history.refresh': 'Refresh',
    'history.empty': 'No recent actions yet.',
    'history.loading': 'Loading…',
    'history.relative.justNow': 'just now',
    'history.relative.seconds': '{n}s ago',
    'history.relative.minutes': '{n}m ago',
    'history.relative.hours': '{n}h ago',
    'history.action.point': 'Point — Team {team}',
    'history.action.set': 'Set won — Team {team}',
    'history.action.timeout': 'Timeout — Team {team}',
    'history.action.serve': 'Serve change → Team {team}',
    'history.action.edit': 'Manual score — Team {team} set {set} = {value}',
    'history.action.reset': 'Reset',
    'history.action.unknown': '(unknown action)',
    'history.action.undoSuffix': ' (undone)',
    'history.legend.pointT1': 'Point T1',
    'history.legend.pointT2': 'Point T2',
    'history.legend.set': 'Set won',
    'history.legend.timeout': 'Timeout',
    'history.legend.serve': 'Serve change',
    'history.legend.edit': 'Manual edit',
    'history.legend.reset': 'Reset',
    'history.legend.undone': 'Undone',

    // Config panel
    'config.title': 'Config',
    'config.backToScoreboard': 'Back to scoreboard',
    'config.openManage': 'Open Custom Overlay Manager',
    'config.save': 'Save',
    'config.saveCustomization': 'Save customization',
    'config.failedToSave': 'Failed to save customization',
    'config.saving': 'Saving…',
    'config.retry': 'Retry',
    'config.reloadFromServer': 'Reload from server',
    'config.reloadConfirm': 'Reload customization from server?',
    'config.resetMatch': 'Reset match',
    'config.resetConfirm': 'Reset the match?',
    'config.logout': 'Logout',
    'config.logoutConfirm': 'Disconnect and return to OID entry?',
    'config.unsavedChangesConfirm': 'You have unsaved changes that will be lost. Leave anyway?',

    // Config sections
    'section.presets': 'Presets',
    'section.teams': 'Teams',
    'section.overlay': 'Overlay Style',
    'section.position': 'Position & Size',
    'section.buttons': 'Button Appearance',
    'section.behavior': 'Behavior',
    'section.rules': 'Match rules',
    'section.links': 'Links',
    'presets.predefined': 'Predefined',
    'presets.yours': 'Yours',
    'presets.apply': 'Apply',
    'presets.empty': 'No presets available',
    'presets.emptyHint': 'Ask an admin to save one from /manage.',
    'presets.lastApplied': 'Last applied',
    'presets.readOnlyBadge': 'Read-only',
    'presets.readOnlyHint': 'Predefined by environment variable; cannot be edited from this panel.',
    'presets.loading': 'Loading presets…',
    'presets.loadFailed': 'Could not load presets.',
    'presets.scope.teamHome': 'Home team',
    'presets.scope.teamAway': 'Away team',
    'presets.scope.layout': 'Position',
    'presets.scope.colors': 'Colors',
    'presets.scope.style': 'Style',
    'presets.scope.theme': 'Theme',
    'rules.loading': 'Loading rules…',
    'rules.mode': 'Mode',
    'rules.mode.indoor': 'Indoor',
    'rules.mode.beach': 'Beach',
    'rules.setsLimit': 'Sets',
    'rules.bestOf.1': 'Single set',
    'rules.bestOf.3': 'Best of 3',
    'rules.bestOf.5': 'Best of 5',
    'rules.pointsLimit': 'Points / set',
    'rules.pointsLimitLastSet': 'Points / final set',
    'rules.resetDefaults': 'Reset defaults for mode',
    'rules.sideSwitchPending': 'Switch sides now',
    'rules.sideSwitchInN': 'Side switch in {n}',
    'alerts.matchFinished': 'Match finished',
    'alerts.matchPoint': 'Match point',
    'alerts.setPoint': 'Set point',
    'alerts.team': 'Team {team}',

    // Teams section
    'teams.select': '— Select —',
    'teams.customPlaceholder': 'Custom team name...',
    'teams.backToList': 'Back to list',
    'teams.customName': 'Custom name',
    'teams.color': 'Color',
    'teams.text': 'Text',

    // Overlay section
    'overlay.logos': 'Logos',
    'overlay.gradient': 'Gradient',
    'overlay.setColor': 'Set Color',
    'overlay.setText': 'Set Text',
    'overlay.gameColor': 'Game Color',
    'overlay.gameText': 'Game Text',
    'overlay.styleLabel': 'Overlay Style',
    'overlay.style': '— Style —',
    'overlay.preloadedConfigLabel': 'Preloaded Config',
    'overlay.selectAndLoad': '— Select and Load —',

    // Position section
    'position.height': 'Height',
    'position.width': 'Width',
    'position.hPos': 'H Pos',
    'position.vPos': 'V Pos',
    'position.decrease': 'Decrease',
    'position.increase': 'Increase',
    'position.links': 'Links',

    // Links dialog
    'links.title': 'Links',
    'links.control': 'Control',
    'links.overlay': 'Overlay',
    'links.preview': 'Preview',
    'links.latest_match_report': 'Latest match report',
    'links.match_history': 'Match history',
    'links.copyToClipboard': 'Copy to clipboard',
    'links.close': 'Close',
    'links.noLinks': 'No links available for this session.',

    // Buttons section
    'buttons.followTeamColors': 'Follow team colors',
    'buttons.t1Btn': 'T1 Btn',
    'buttons.t1Text': 'T1 Text',
    'buttons.t2Btn': 'T2 Btn',
    'buttons.t2Text': 'T2 Text',
    'buttons.resetColors': 'Reset colors',
    'buttons.showTeamIcon': 'Show team icon',
    'buttons.opacity': 'Opacity: {value}%',
    'buttons.buttonFont': 'Button font',

    // Behavior section
    'behavior.autoHide': 'Auto-hide scoreboard',
    'behavior.hideAfter': 'Hide after {value}s',
    'behavior.autoSimple': 'Auto simple mode',
    'behavior.fullOnTimeout': 'Full mode on timeout',
    'behavior.haptics': 'Haptic feedback',
    'behavior.showPreview': 'Show overlay preview',

    // Preview
    'preview.title': 'Overlay preview',
    'preview.zoomIn': 'Zoom in',
    'preview.zoomOut': 'Zoom out',
    'preview.missingOutput': 'No overlay output URL provided.',
    'preview.styleOverride': 'Preview style (does not change the overlay)',
    'preview.styleDefault': 'Default style',

    // Color picker
    'colorPicker.presets': 'Presets',
    'colorPicker.recent': 'Recent',

    // Language
    'lang.label': 'Language',
  },
  es: {
    // Init screen
    'app.title': 'Marcador',
    'app.oidLabel': 'ID de Control del Overlay (OID)',
    'app.oidPlaceholder': 'mi-overlay',
    'app.connect': 'Conectar',
    'app.selectOverlay': 'Seleccionar Overlay',
    'app.selectOverlayPlaceholder': '— Elegir —',
    'app.orManualOid': 'o introducir OID manualmente',
    'app.connecting': 'Conectando…',

    // Dialog
    'dialog.ok': 'OK',
    'dialog.cancel': 'Cancelar',
    'dialog.setScore': 'Puntuación — Equipo {team}',
    'dialog.setSets': 'Sets ganados — Equipo {team}',

    // Control buttons
    'ctrl.hideOverlay': 'Ocultar overlay',
    'ctrl.showOverlay': 'Mostrar overlay',
    'ctrl.hidePreview': 'Ocultar vista previa',
    'ctrl.showPreview': 'Mostrar vista previa',
    'ctrl.fullScoreboard': 'Marcador completo',
    'ctrl.simpleScoreboard': 'Marcador simple',
    'ctrl.undoLast': 'Deshacer última acción',
    'ctrl.fullscreen': 'Pantalla completa',
    'ctrl.exitFullscreen': 'Salir de pantalla completa',
    'ctrl.lightMode': 'Modo claro',
    'ctrl.darkMode': 'Modo oscuro',
    'ctrl.themeAuto': 'Tema: seguir al sistema',
    'ctrl.startMatch': 'Iniciar partido',
    'ctrl.reset': 'Reiniciar',
    'ctrl.config': 'Configuración',
    'ctrl.configHint': 'Configuración — o desliza a la izquierda',

    // Connection status
    'conn.online': 'Sincronización en directo',
    'conn.reconnecting': 'Reconectando…',

    // Confirmation dialogs
    'confirm.title': '¿Confirmas?',
    'confirm.confirm': 'Confirmar',
    'confirm.cancel': 'Cancelar',

    // Preview fallback
    'preview.unavailable': 'Vista previa no disponible',
    'preview.retry': 'Reintentar',

    // Gesture coachmark / first-run tour
    'tour.skip': 'Omitir',
    'tour.prev': 'Atrás',
    'tour.next': 'Siguiente',
    'tour.done': 'Entendido',
    'tour.progress': 'Paso {step} de {total}',
    'tour.tap.title': 'Toca para sumar punto',
    'tour.tap.body': 'Toca el panel de un equipo para sumar un punto. El saque cambia automáticamente.',
    'tour.doubletap.title': 'Doble toque para deshacer',
    'tour.doubletap.body': 'Doble toque sobre el panel de un equipo — o el botón Deshacer — para revertir el último punto o tiempo muerto de ese equipo.',
    'tour.longpress.title': 'Mantén pulsado para editar',
    'tour.longpress.body': 'Mantén pulsado el marcador o el contador de sets para establecer un valor personalizado cuando haga falta corregir manualmente.',
    'tour.config.title': 'Abrir configuración',
    'tour.config.body': 'Desliza a la izquierda, o pulsa el engranaje arriba-derecha, para equipos, colores, reglas y enlaces.',

    // Share / quick links
    'share.title': 'Compartir partido',

    // Recent-audit drawer (Phase 4.2)
    'history.title': 'Historial',
    'history.close': 'Cerrar historial',
    'history.refresh': 'Actualizar',
    'history.empty': 'Sin acciones recientes.',
    'history.loading': 'Cargando…',
    'history.relative.justNow': 'justo ahora',
    'history.relative.seconds': 'hace {n}s',
    'history.relative.minutes': 'hace {n}m',
    'history.relative.hours': 'hace {n}h',
    'history.action.point': 'Punto — Equipo {team}',
    'history.action.set': 'Set ganado — Equipo {team}',
    'history.action.timeout': 'Tiempo muerto — Equipo {team}',
    'history.action.serve': 'Cambio de saque → Equipo {team}',
    'history.action.edit': 'Marcador manual — Equipo {team} set {set} = {value}',
    'history.action.reset': 'Reinicio',
    'history.action.unknown': '(acción desconocida)',
    'history.action.undoSuffix': ' (deshecho)',
    'history.legend.pointT1': 'Punto E1',
    'history.legend.pointT2': 'Punto E2',
    'history.legend.set': 'Set ganado',
    'history.legend.timeout': 'Tiempo muerto',
    'history.legend.serve': 'Cambio de saque',
    'history.legend.edit': 'Edición manual',
    'history.legend.reset': 'Reinicio',
    'history.legend.undone': 'Deshecho',

    // Config panel
    'config.title': 'Config',
    'config.backToScoreboard': 'Volver al marcador',
    'config.openManage': 'Abrir gestor de overlays',
    'config.save': 'Guardar',
    'config.saveCustomization': 'Guardar personalización',
    'config.failedToSave': 'Error al guardar la personalización',
    'config.saving': 'Guardando…',
    'config.retry': 'Reintentar',
    'config.reloadFromServer': 'Recargar del servidor',
    'config.reloadConfirm': '¿Recargar personalización del servidor?',
    'config.resetMatch': 'Reiniciar partido',
    'config.resetConfirm': '¿Reiniciar el partido?',
    'config.logout': 'Cerrar sesión',
    'config.logoutConfirm': '¿Desconectar y volver a la entrada de OID?',
    'config.unsavedChangesConfirm': 'Hay cambios sin guardar que se perderán. ¿Salir de todas formas?',

    // Config sections
    'section.presets': 'Presets',
    'section.teams': 'Equipos',
    'section.overlay': 'Estilo del Overlay',
    'section.position': 'Posición y Tamaño',
    'section.buttons': 'Apariencia de Botones',
    'section.behavior': 'Comportamiento',
    'section.rules': 'Reglas del partido',
    'section.links': 'Enlaces',
    'presets.predefined': 'Predefinidos',
    'presets.yours': 'Tuyos',
    'presets.apply': 'Aplicar',
    'presets.empty': 'No hay presets disponibles',
    'presets.emptyHint': 'Pide a un admin que cree alguno desde /manage.',
    'presets.lastApplied': 'Último aplicado',
    'presets.readOnlyBadge': 'Solo lectura',
    'presets.readOnlyHint': 'Definido por variable de entorno; no editable desde aquí.',
    'presets.loading': 'Cargando presets…',
    'presets.loadFailed': 'No se han podido cargar los presets.',
    'presets.scope.teamHome': 'Equipo local',
    'presets.scope.teamAway': 'Equipo visitante',
    'presets.scope.layout': 'Posición',
    'presets.scope.colors': 'Colores',
    'presets.scope.style': 'Estilo',
    'presets.scope.theme': 'Tema',
    'rules.loading': 'Cargando reglas…',
    'rules.mode': 'Modalidad',
    'rules.mode.indoor': 'Pista',
    'rules.mode.beach': 'Playa',
    'rules.setsLimit': 'Sets',
    'rules.bestOf.1': 'A un set',
    'rules.bestOf.3': 'Al mejor de 3',
    'rules.bestOf.5': 'Al mejor de 5',
    'rules.pointsLimit': 'Puntos / set',
    'rules.pointsLimitLastSet': 'Puntos / último set',
    'rules.resetDefaults': 'Restaurar valores de la modalidad',
    'rules.sideSwitchPending': 'Cambiar de lado',
    'rules.sideSwitchInN': 'Cambio de lado en {n}',
    'alerts.matchFinished': 'Partido finalizado',
    'alerts.matchPoint': 'Punto de partido',
    'alerts.setPoint': 'Punto de set',
    'alerts.team': 'Equipo {team}',

    // Teams section
    'teams.select': '— Elegir —',
    'teams.customPlaceholder': 'Nombre personalizado...',
    'teams.backToList': 'Volver a la lista',
    'teams.customName': 'Nombre personalizado',
    'teams.color': 'Color',
    'teams.text': 'Texto',

    // Overlay section
    'overlay.logos': 'Logos',
    'overlay.gradient': 'Degradado',
    'overlay.setColor': 'Color Set',
    'overlay.setText': 'Texto Set',
    'overlay.gameColor': 'Color Juego',
    'overlay.gameText': 'Texto Juego',
    'overlay.styleLabel': 'Estilo del Overlay',
    'overlay.style': '— Estilo —',
    'overlay.preloadedConfigLabel': 'Config. Predefinida',
    'overlay.selectAndLoad': '— Seleccionar y Cargar —',

    // Position section
    'position.height': 'Alto',
    'position.width': 'Ancho',
    'position.hPos': 'Pos H',
    'position.vPos': 'Pos V',
    'position.decrease': 'Disminuir',
    'position.increase': 'Aumentar',
    'position.links': 'Enlaces',

    // Links dialog
    'links.title': 'Enlaces',
    'links.control': 'Control',
    'links.overlay': 'Overlay',
    'links.preview': 'Vista previa',
    'links.latest_match_report': 'Último informe de partido',
    'links.match_history': 'Historial de partidos',
    'links.copyToClipboard': 'Copiar al portapapeles',
    'links.close': 'Cerrar',
    'links.noLinks': 'No hay enlaces disponibles para esta sesión.',

    // Buttons section
    'buttons.followTeamColors': 'Seguir colores del equipo',
    'buttons.t1Btn': 'Btn E1',
    'buttons.t1Text': 'Texto E1',
    'buttons.t2Btn': 'Btn E2',
    'buttons.t2Text': 'Texto E2',
    'buttons.resetColors': 'Restablecer colores',
    'buttons.showTeamIcon': 'Mostrar icono del equipo',
    'buttons.opacity': 'Opacidad: {value}%',
    'buttons.buttonFont': 'Fuente de botones',

    // Behavior section
    'behavior.autoHide': 'Ocultar marcador automáticamente',
    'behavior.hideAfter': 'Ocultar después de {value}s',
    'behavior.autoSimple': 'Modo simple automático',
    'behavior.fullOnTimeout': 'Modo completo en tiempo muerto',
    'behavior.haptics': 'Vibración táctil',
    'behavior.showPreview': 'Mostrar vista previa del overlay',

    // Preview
    'preview.title': 'Vista previa del overlay',
    'preview.zoomIn': 'Acercar',
    'preview.zoomOut': 'Alejar',
    'preview.missingOutput': 'No se ha proporcionado URL de salida del overlay.',
    'preview.styleOverride': 'Estilo de la vista previa (no cambia el overlay)',
    'preview.styleDefault': 'Estilo por defecto',

    // Color picker
    'colorPicker.presets': 'Predefinidos',
    'colorPicker.recent': 'Recientes',

    // Language
    'lang.label': 'Idioma',
  },
  pt: {
    // Init screen
    'app.title': 'Marcador de Voleibol',
    'app.oidLabel': 'ID de Controlo do Overlay (OID)',
    'app.oidPlaceholder': 'o-meu-overlay',
    'app.connect': 'Ligar',
    'app.selectOverlay': 'Selecionar Overlay',
    'app.selectOverlayPlaceholder': '— Selecionar —',
    'app.orManualOid': 'ou introduzir o OID manualmente',
    'app.connecting': 'A ligar…',

    // Dialog
    'dialog.ok': 'OK',
    'dialog.cancel': 'Cancelar',
    'dialog.setScore': 'Pontuação — Equipa {team}',
    'dialog.setSets': 'Sets ganhos — Equipa {team}',

    // Control buttons
    'ctrl.hideOverlay': 'Ocultar overlay',
    'ctrl.showOverlay': 'Mostrar overlay',
    'ctrl.hidePreview': 'Ocultar pré-visualização',
    'ctrl.showPreview': 'Mostrar pré-visualização',
    'ctrl.fullScoreboard': 'Marcador completo',
    'ctrl.simpleScoreboard': 'Marcador simples',
    'ctrl.undoLast': 'Desfazer última ação',
    'ctrl.fullscreen': 'Ecrã inteiro',
    'ctrl.exitFullscreen': 'Sair do ecrã inteiro',
    'ctrl.lightMode': 'Modo claro',
    'ctrl.darkMode': 'Modo escuro',
    'ctrl.themeAuto': 'Tema: seguir o sistema',
    'ctrl.startMatch': 'Iniciar jogo',
    'ctrl.reset': 'Reiniciar',
    'ctrl.config': 'Configuração',
    'ctrl.configHint': 'Configuração — ou desliza para a esquerda',

    // Connection status
    'conn.online': 'Sincronização em direto',
    'conn.reconnecting': 'A reconectar…',

    // Confirmation dialogs
    'confirm.title': 'Confirmas?',
    'confirm.confirm': 'Confirmar',
    'confirm.cancel': 'Cancelar',

    // Preview fallback
    'preview.unavailable': 'Pré-visualização indisponível',
    'preview.retry': 'Tentar novamente',

    // Gesture coachmark / first-run tour
    'tour.skip': 'Saltar',
    'tour.prev': 'Anterior',
    'tour.next': 'Seguinte',
    'tour.done': 'Entendi',
    'tour.progress': 'Passo {step} de {total}',
    'tour.tap.title': 'Toca para somar ponto',
    'tour.tap.body': 'Toca no painel de uma equipa para somar um ponto. O saque muda automaticamente.',
    'tour.doubletap.title': 'Toque duplo para desfazer',
    'tour.doubletap.body': 'Toque duplo no painel de uma equipa — ou o botão Desfazer — para reverter o último ponto ou desconto de tempo dessa equipa.',
    'tour.longpress.title': 'Mantém premido para editar',
    'tour.longpress.body': 'Mantém premido a pontuação ou o contador de sets para definir um valor personalizado quando for preciso corrigir manualmente.',
    'tour.config.title': 'Abrir configuração',
    'tour.config.body': 'Desliza para a esquerda, ou toca na engrenagem em cima à direita, para equipas, cores, regras e ligações.',

    // Share / quick links
    'share.title': 'Partilhar jogo',

    // Recent-audit drawer (Phase 4.2)
    'history.title': 'Histórico',
    'history.close': 'Fechar histórico',
    'history.refresh': 'Atualizar',
    'history.empty': 'Sem ações recentes.',
    'history.loading': 'A carregar…',
    'history.relative.justNow': 'agora mesmo',
    'history.relative.seconds': 'há {n}s',
    'history.relative.minutes': 'há {n}m',
    'history.relative.hours': 'há {n}h',
    'history.action.point': 'Ponto — Equipa {team}',
    'history.action.set': 'Set ganho — Equipa {team}',
    'history.action.timeout': 'Tempo morto — Equipa {team}',
    'history.action.serve': 'Troca de saque → Equipa {team}',
    'history.action.edit': 'Pontuação manual — Equipa {team} set {set} = {value}',
    'history.action.reset': 'Reinício',
    'history.action.unknown': '(ação desconhecida)',
    'history.action.undoSuffix': ' (desfeito)',
    'history.legend.pointT1': 'Ponto E1',
    'history.legend.pointT2': 'Ponto E2',
    'history.legend.set': 'Set ganho',
    'history.legend.timeout': 'Tempo morto',
    'history.legend.serve': 'Troca de saque',
    'history.legend.edit': 'Edição manual',
    'history.legend.reset': 'Reinício',
    'history.legend.undone': 'Desfeito',

    // Config panel
    'config.title': 'Config',
    'config.backToScoreboard': 'Voltar ao marcador',
    'config.save': 'Guardar',
    'config.saveCustomization': 'Guardar personalização',
    'config.failedToSave': 'Falha ao guardar a personalização',
    'config.saving': 'A guardar…',
    'config.retry': 'Tentar novamente',
    'config.reloadFromServer': 'Recarregar do servidor',
    'config.reloadConfirm': 'Recarregar personalização do servidor?',
    'config.resetMatch': 'Reiniciar jogo',
    'config.resetConfirm': 'Reiniciar o jogo?',
    'config.logout': 'Terminar sessão',
    'config.logoutConfirm': 'Desligar e voltar à introdução do OID?',
    'config.unsavedChangesConfirm': 'Há alterações não guardadas que serão perdidas. Sair mesmo assim?',

    // Config sections
    'section.presets': 'Presets',
    'section.teams': 'Equipas',
    'section.overlay': 'Estilo do Overlay',
    'section.position': 'Posição e Tamanho',
    'section.buttons': 'Aparência dos Botões',
    'section.behavior': 'Comportamento',
    'section.rules': 'Regras do jogo',
    'section.links': 'Ligações',
    'presets.predefined': 'Predefinidos',
    'presets.yours': 'Os teus',
    'presets.apply': 'Aplicar',
    'presets.empty': 'Sem presets disponíveis',
    'presets.emptyHint': 'Pede a um admin que crie algum em /manage.',
    'presets.lastApplied': 'Último aplicado',
    'presets.readOnlyBadge': 'Apenas leitura',
    'presets.readOnlyHint': 'Definido por variável de ambiente; não é editável aqui.',
    'presets.loading': 'A carregar presets…',
    'presets.loadFailed': 'Falha ao carregar os presets.',
    'presets.scope.teamHome': 'Equipa da casa',
    'presets.scope.teamAway': 'Equipa visitante',
    'presets.scope.layout': 'Posição',
    'presets.scope.colors': 'Cores',
    'presets.scope.style': 'Estilo',
    'presets.scope.theme': 'Tema',
    'rules.loading': 'A carregar regras…',
    'rules.mode': 'Modalidade',
    'rules.mode.indoor': 'Pavilhão',
    'rules.mode.beach': 'Praia',
    'rules.setsLimit': 'Sets',
    'rules.bestOf.1': 'Set único',
    'rules.bestOf.3': 'À melhor de 3',
    'rules.bestOf.5': 'À melhor de 5',
    'rules.pointsLimit': 'Pontos / set',
    'rules.pointsLimitLastSet': 'Pontos / set decisivo',
    'rules.resetDefaults': 'Repor valores da modalidade',
    'rules.sideSwitchPending': 'Trocar de lado',
    'rules.sideSwitchInN': 'Troca de lado em {n}',
    'alerts.matchFinished': 'Jogo terminado',
    'alerts.matchPoint': 'Match point',
    'alerts.setPoint': 'Set point',
    'alerts.team': 'Equipa {team}',

    // Teams section
    'teams.select': '— Selecionar —',
    'teams.customPlaceholder': 'Nome personalizado da equipa...',
    'teams.backToList': 'Voltar à lista',
    'teams.customName': 'Nome personalizado',
    'teams.color': 'Cor',
    'teams.text': 'Texto',

    // Overlay section
    'overlay.logos': 'Logótipos',
    'overlay.gradient': 'Gradiente',
    'overlay.setColor': 'Cor do Set',
    'overlay.setText': 'Texto do Set',
    'overlay.gameColor': 'Cor do Jogo',
    'overlay.gameText': 'Texto do Jogo',
    'overlay.styleLabel': 'Estilo do Overlay',
    'overlay.style': '— Estilo —',
    'overlay.preloadedConfigLabel': 'Config. Predefinida',
    'overlay.selectAndLoad': '— Selecionar e Carregar —',

    // Position section
    'position.height': 'Altura',
    'position.width': 'Largura',
    'position.hPos': 'Pos H',
    'position.vPos': 'Pos V',
    'position.decrease': 'Diminuir',
    'position.increase': 'Aumentar',
    'position.links': 'Ligações',

    // Links dialog
    'links.title': 'Ligações',
    'links.control': 'Controlo',
    'links.overlay': 'Overlay',
    'links.preview': 'Pré-visualização',
    'links.latest_match_report': 'Relatório do último jogo',
    'links.match_history': 'Histórico de jogos',
    'links.copyToClipboard': 'Copiar para a área de transferência',
    'links.close': 'Fechar',
    'links.noLinks': 'Não há ligações disponíveis para esta sessão.',

    // Buttons section
    'buttons.followTeamColors': 'Seguir as cores da equipa',
    'buttons.t1Btn': 'Btn E1',
    'buttons.t1Text': 'Texto E1',
    'buttons.t2Btn': 'Btn E2',
    'buttons.t2Text': 'Texto E2',
    'buttons.resetColors': 'Repor cores',
    'buttons.showTeamIcon': 'Mostrar ícone da equipa',
    'buttons.opacity': 'Opacidade: {value}%',
    'buttons.buttonFont': 'Tipo de letra dos botões',

    // Behavior section
    'behavior.autoHide': 'Ocultar marcador automaticamente',
    'behavior.hideAfter': 'Ocultar após {value}s',
    'behavior.autoSimple': 'Modo simples automático',
    'behavior.fullOnTimeout': 'Modo completo no desconto de tempo',
    'behavior.haptics': 'Vibração tátil',
    'behavior.showPreview': 'Mostrar pré-visualização do overlay',

    // Preview
    'preview.title': 'Pré-visualização do overlay',
    'preview.zoomIn': 'Ampliar',
    'preview.zoomOut': 'Reduzir',
    'preview.missingOutput': 'Nenhum URL de saída do overlay foi fornecido.',
    'preview.styleOverride': 'Estilo da pré-visualização (não altera o overlay)',
    'preview.styleDefault': 'Estilo predefinido',

    // Color picker
    'colorPicker.presets': 'Predefinições',
    'colorPicker.recent': 'Recentes',

    // Language
    'lang.label': 'Idioma',
  },
  it: {
    // Init screen
    'app.title': 'Tabellone Volley',
    'app.oidLabel': 'ID Controllo Overlay (OID)',
    'app.oidPlaceholder': 'mio-overlay',
    'app.connect': 'Connetti',
    'app.selectOverlay': 'Seleziona Overlay',
    'app.selectOverlayPlaceholder': '— Seleziona —',
    'app.orManualOid': 'o inserisci l’OID manualmente',
    'app.connecting': 'Connessione…',

    // Dialog
    'dialog.ok': 'OK',
    'dialog.cancel': 'Annulla',
    'dialog.setScore': 'Punteggio — Squadra {team}',
    'dialog.setSets': 'Set vinti — Squadra {team}',

    // Control buttons
    'ctrl.hideOverlay': 'Nascondi overlay',
    'ctrl.showOverlay': 'Mostra overlay',
    'ctrl.hidePreview': 'Nascondi anteprima',
    'ctrl.showPreview': 'Mostra anteprima',
    'ctrl.fullScoreboard': 'Tabellone completo',
    'ctrl.simpleScoreboard': 'Tabellone semplice',
    'ctrl.undoLast': 'Annulla ultima azione',
    'ctrl.fullscreen': 'Schermo intero',
    'ctrl.exitFullscreen': 'Esci da schermo intero',
    'ctrl.lightMode': 'Modalità chiara',
    'ctrl.darkMode': 'Modalità scura',
    'ctrl.themeAuto': 'Tema: segui il sistema',
    'ctrl.startMatch': 'Inizia partita',
    'ctrl.reset': 'Reimposta',
    'ctrl.config': 'Configurazione',
    'ctrl.configHint': 'Configurazione — o scorri a sinistra',

    // Connection status
    'conn.online': 'Sincronizzazione in diretta',
    'conn.reconnecting': 'Riconnessione…',

    // Confirmation dialogs
    'confirm.title': 'Confermi?',
    'confirm.confirm': 'Conferma',
    'confirm.cancel': 'Annulla',

    // Preview fallback
    'preview.unavailable': 'Anteprima non disponibile',
    'preview.retry': 'Riprova',

    // Gesture coachmark / first-run tour
    'tour.skip': 'Salta',
    'tour.prev': 'Indietro',
    'tour.next': 'Avanti',
    'tour.done': 'Ho capito',
    'tour.progress': 'Passo {step} di {total}',
    'tour.tap.title': 'Tocca per segnare',
    'tour.tap.body': 'Tocca il pannello di una squadra per aggiungere un punto. La battuta cambia automaticamente.',
    'tour.doubletap.title': 'Doppio tocco per annullare',
    'tour.doubletap.body': 'Doppio tocco sul pannello di una squadra — o il pulsante Annulla — per annullare l\'ultimo punto o time-out di quella squadra.',
    'tour.longpress.title': 'Tieni premuto per modificare',
    'tour.longpress.body': 'Tieni premuto il punteggio o il contatore set per impostare un valore personalizzato quando serve correggere a mano.',
    'tour.config.title': 'Apri la configurazione',
    'tour.config.body': 'Scorri a sinistra, o tocca l\'ingranaggio in alto a destra, per squadre, colori, regole e link.',

    // Share / quick links
    'share.title': 'Condividi partita',

    // Recent-audit drawer (Phase 4.2)
    'history.title': 'Cronologia',
    'history.close': 'Chiudi cronologia',
    'history.refresh': 'Aggiorna',
    'history.empty': 'Nessuna azione recente.',
    'history.loading': 'Caricamento…',
    'history.relative.justNow': 'adesso',
    'history.relative.seconds': '{n}s fa',
    'history.relative.minutes': '{n}m fa',
    'history.relative.hours': '{n}h fa',
    'history.action.point': 'Punto — Squadra {team}',
    'history.action.set': 'Set vinto — Squadra {team}',
    'history.action.timeout': 'Time-out — Squadra {team}',
    'history.action.serve': 'Cambio battuta → Squadra {team}',
    'history.action.edit': 'Punteggio manuale — Squadra {team} set {set} = {value}',
    'history.action.reset': 'Reset',
    'history.action.unknown': '(azione sconosciuta)',
    'history.action.undoSuffix': ' (annullato)',
    'history.legend.pointT1': 'Punto S1',
    'history.legend.pointT2': 'Punto S2',
    'history.legend.set': 'Set vinto',
    'history.legend.timeout': 'Time-out',
    'history.legend.serve': 'Cambio battuta',
    'history.legend.edit': 'Modifica manuale',
    'history.legend.reset': 'Reset',
    'history.legend.undone': 'Annullato',

    // Config panel
    'config.title': 'Config',
    'config.backToScoreboard': 'Torna al tabellone',
    'config.save': 'Salva',
    'config.saveCustomization': 'Salva personalizzazione',
    'config.failedToSave': 'Errore nel salvataggio della personalizzazione',
    'config.saving': 'Salvataggio…',
    'config.retry': 'Riprova',
    'config.reloadFromServer': 'Ricarica dal server',
    'config.reloadConfirm': 'Ricaricare la personalizzazione dal server?',
    'config.resetMatch': 'Reimposta partita',
    'config.resetConfirm': 'Reimpostare la partita?',
    'config.logout': 'Esci',
    'config.logoutConfirm': 'Disconnettersi e tornare all’inserimento OID?',
    'config.unsavedChangesConfirm': 'Ci sono modifiche non salvate che andranno perse. Uscire comunque?',

    // Config sections
    'section.presets': 'Preset',
    'section.teams': 'Squadre',
    'section.overlay': 'Stile Overlay',
    'section.position': 'Posizione e Dimensione',
    'section.buttons': 'Aspetto dei Pulsanti',
    'section.behavior': 'Comportamento',
    'section.rules': 'Regole del match',
    'section.links': 'Link',
    'presets.predefined': 'Predefiniti',
    'presets.yours': 'I tuoi',
    'presets.apply': 'Applica',
    'presets.empty': 'Nessun preset disponibile',
    'presets.emptyHint': 'Chiedi a un admin di crearne uno da /manage.',
    'presets.lastApplied': 'Ultimo applicato',
    'presets.readOnlyBadge': 'Sola lettura',
    'presets.readOnlyHint': 'Definito da variabile d\'ambiente; non modificabile qui.',
    'presets.loading': 'Caricamento preset…',
    'presets.loadFailed': 'Impossibile caricare i preset.',
    'presets.scope.teamHome': 'Squadra di casa',
    'presets.scope.teamAway': 'Squadra ospite',
    'presets.scope.layout': 'Posizione',
    'presets.scope.colors': 'Colori',
    'presets.scope.style': 'Stile',
    'presets.scope.theme': 'Tema',
    'rules.loading': 'Caricamento regole…',
    'rules.mode': 'Modalità',
    'rules.mode.indoor': 'Indoor',
    'rules.mode.beach': 'Beach',
    'rules.setsLimit': 'Set',
    'rules.bestOf.1': 'Set unico',
    'rules.bestOf.3': 'Al meglio di 3',
    'rules.bestOf.5': 'Al meglio di 5',
    'rules.pointsLimit': 'Punti / set',
    'rules.pointsLimitLastSet': 'Punti / set decisivo',
    'rules.resetDefaults': 'Ripristina valori della modalità',
    'rules.sideSwitchPending': 'Cambio campo',
    'rules.sideSwitchInN': 'Cambio campo tra {n}',
    'alerts.matchFinished': 'Partita terminata',
    'alerts.matchPoint': 'Match point',
    'alerts.setPoint': 'Set point',
    'alerts.team': 'Squadra {team}',

    // Teams section
    'teams.select': '— Seleziona —',
    'teams.customPlaceholder': 'Nome squadra personalizzato...',
    'teams.backToList': 'Torna alla lista',
    'teams.customName': 'Nome personalizzato',
    'teams.color': 'Colore',
    'teams.text': 'Testo',

    // Overlay section
    'overlay.logos': 'Loghi',
    'overlay.gradient': 'Gradiente',
    'overlay.setColor': 'Colore Set',
    'overlay.setText': 'Testo Set',
    'overlay.gameColor': 'Colore Gioco',
    'overlay.gameText': 'Testo Gioco',
    'overlay.styleLabel': 'Stile Overlay',
    'overlay.style': '— Stile —',
    'overlay.preloadedConfigLabel': 'Config. Preimpostata',
    'overlay.selectAndLoad': '— Seleziona e Carica —',

    // Position section
    'position.height': 'Altezza',
    'position.width': 'Larghezza',
    'position.hPos': 'Pos O',
    'position.vPos': 'Pos V',
    'position.decrease': 'Diminuisci',
    'position.increase': 'Aumenta',
    'position.links': 'Link',

    // Links dialog
    'links.title': 'Link',
    'links.control': 'Controllo',
    'links.overlay': 'Overlay',
    'links.preview': 'Anteprima',
    'links.latest_match_report': 'Ultimo referto della partita',
    'links.match_history': 'Storico delle partite',
    'links.copyToClipboard': 'Copia negli appunti',
    'links.close': 'Chiudi',
    'links.noLinks': 'Nessun link disponibile per questa sessione.',

    // Buttons section
    'buttons.followTeamColors': 'Segui i colori della squadra',
    'buttons.t1Btn': 'Btn S1',
    'buttons.t1Text': 'Testo S1',
    'buttons.t2Btn': 'Btn S2',
    'buttons.t2Text': 'Testo S2',
    'buttons.resetColors': 'Ripristina colori',
    'buttons.showTeamIcon': 'Mostra icona squadra',
    'buttons.opacity': 'Opacità: {value}%',
    'buttons.buttonFont': 'Font dei pulsanti',

    // Behavior section
    'behavior.autoHide': 'Nascondi tabellone automaticamente',
    'behavior.hideAfter': 'Nascondi dopo {value}s',
    'behavior.autoSimple': 'Modalità semplice automatica',
    'behavior.fullOnTimeout': 'Modalità completa al time-out',
    'behavior.haptics': 'Feedback aptico',
    'behavior.showPreview': 'Mostra anteprima overlay',

    // Preview
    'preview.title': 'Anteprima overlay',
    'preview.zoomIn': 'Ingrandisci',
    'preview.zoomOut': 'Riduci',
    'preview.missingOutput': 'Nessun URL di output overlay fornito.',
    'preview.styleOverride': 'Stile anteprima (non modifica l’overlay)',
    'preview.styleDefault': 'Stile predefinito',

    // Color picker
    'colorPicker.presets': 'Preimpostati',
    'colorPicker.recent': 'Recenti',

    // Language
    'lang.label': 'Lingua',
  },
  fr: {
    // Init screen
    'app.title': 'Tableau de score Volley',
    'app.oidLabel': 'ID de contrôle de l’overlay (OID)',
    'app.oidPlaceholder': 'mon-overlay',
    'app.connect': 'Connecter',
    'app.selectOverlay': 'Sélectionner l’overlay',
    'app.selectOverlayPlaceholder': '— Sélectionner —',
    'app.orManualOid': 'ou saisir l’OID manuellement',
    'app.connecting': 'Connexion…',

    // Dialog
    'dialog.ok': 'OK',
    'dialog.cancel': 'Annuler',
    'dialog.setScore': 'Score — Équipe {team}',
    'dialog.setSets': 'Sets gagnés — Équipe {team}',

    // Control buttons
    'ctrl.hideOverlay': 'Masquer l’overlay',
    'ctrl.showOverlay': 'Afficher l’overlay',
    'ctrl.hidePreview': 'Masquer l’aperçu',
    'ctrl.showPreview': 'Afficher l’aperçu',
    'ctrl.fullScoreboard': 'Tableau complet',
    'ctrl.simpleScoreboard': 'Tableau simple',
    'ctrl.undoLast': 'Annuler la dernière action',
    'ctrl.fullscreen': 'Plein écran',
    'ctrl.exitFullscreen': 'Quitter le plein écran',
    'ctrl.lightMode': 'Mode clair',
    'ctrl.darkMode': 'Mode sombre',
    'ctrl.themeAuto': 'Thème : suivre le système',
    'ctrl.startMatch': 'Démarrer le match',
    'ctrl.reset': 'Réinitialiser',
    'ctrl.config': 'Configuration',
    'ctrl.configHint': 'Configuration — ou glissez vers la gauche',

    // Connection status
    'conn.online': 'Synchronisation en direct',
    'conn.reconnecting': 'Reconnexion…',

    // Confirmation dialogs
    'confirm.title': 'Confirmer ?',
    'confirm.confirm': 'Confirmer',
    'confirm.cancel': 'Annuler',

    // Preview fallback
    'preview.unavailable': 'Aperçu indisponible',
    'preview.retry': 'Réessayer',

    // Gesture coachmark / first-run tour
    'tour.skip': 'Passer',
    'tour.prev': 'Précédent',
    'tour.next': 'Suivant',
    'tour.done': 'Compris',
    'tour.progress': 'Étape {step} sur {total}',
    'tour.tap.title': 'Touchez pour marquer',
    'tour.tap.body': 'Touchez le panneau d\'une équipe pour ajouter un point. Le service bascule automatiquement.',
    'tour.doubletap.title': 'Double-tap pour annuler',
    'tour.doubletap.body': 'Double-tap sur le panneau d\'une équipe — ou le bouton Annuler — pour annuler le dernier point ou temps mort de cette équipe.',
    'tour.longpress.title': 'Appui long pour modifier',
    'tour.longpress.body': 'Appui long sur le score ou le compteur de sets pour définir une valeur personnalisée quand une correction manuelle est nécessaire.',
    'tour.config.title': 'Ouvrir la configuration',
    'tour.config.body': 'Glissez vers la gauche, ou touchez l\'engrenage en haut à droite, pour équipes, couleurs, règles et liens.',

    // Share / quick links
    'share.title': 'Partager le match',

    // Recent-audit drawer (Phase 4.2)
    'history.title': 'Historique',
    'history.close': 'Fermer l’historique',
    'history.refresh': 'Actualiser',
    'history.empty': 'Aucune action récente.',
    'history.loading': 'Chargement…',
    'history.relative.justNow': 'à l’instant',
    'history.relative.seconds': 'il y a {n}s',
    'history.relative.minutes': 'il y a {n}m',
    'history.relative.hours': 'il y a {n}h',
    'history.action.point': 'Point — Équipe {team}',
    'history.action.set': 'Set gagné — Équipe {team}',
    'history.action.timeout': 'Temps mort — Équipe {team}',
    'history.action.serve': 'Changement de service → Équipe {team}',
    'history.action.edit': 'Score manuel — Équipe {team} set {set} = {value}',
    'history.action.reset': 'Réinitialisation',
    'history.action.unknown': '(action inconnue)',
    'history.action.undoSuffix': ' (annulé)',
    'history.legend.pointT1': 'Point É1',
    'history.legend.pointT2': 'Point É2',
    'history.legend.set': 'Set gagné',
    'history.legend.timeout': 'Temps mort',
    'history.legend.serve': 'Changement de service',
    'history.legend.edit': 'Édition manuelle',
    'history.legend.reset': 'Réinitialisation',
    'history.legend.undone': 'Annulé',

    // Config panel
    'config.title': 'Config',
    'config.backToScoreboard': 'Retour au tableau',
    'config.save': 'Enregistrer',
    'config.saveCustomization': 'Enregistrer la personnalisation',
    'config.failedToSave': 'Échec de l’enregistrement de la personnalisation',
    'config.saving': 'Enregistrement…',
    'config.retry': 'Réessayer',
    'config.reloadFromServer': 'Recharger depuis le serveur',
    'config.reloadConfirm': 'Recharger la personnalisation depuis le serveur ?',
    'config.resetMatch': 'Réinitialiser le match',
    'config.resetConfirm': 'Réinitialiser le match ?',
    'config.logout': 'Déconnexion',
    'config.logoutConfirm': 'Se déconnecter et revenir à la saisie de l’OID ?',
    'config.unsavedChangesConfirm': 'Des modifications non enregistrées seront perdues. Quitter quand même ?',

    // Config sections
    'section.presets': 'Presets',
    'section.teams': 'Équipes',
    'section.overlay': 'Style de l’overlay',
    'section.position': 'Position et taille',
    'section.buttons': 'Apparence des boutons',
    'section.behavior': 'Comportement',
    'section.rules': 'Règles du match',
    'section.links': 'Liens',
    'presets.predefined': 'Prédéfinis',
    'presets.yours': 'Les tiens',
    'presets.apply': 'Appliquer',
    'presets.empty': 'Aucun preset disponible',
    'presets.emptyHint': 'Demandez à un admin d’en créer un depuis /manage.',
    'presets.lastApplied': 'Dernier appliqué',
    'presets.readOnlyBadge': 'Lecture seule',
    'presets.readOnlyHint': 'Défini par variable d’environnement ; non modifiable ici.',
    'presets.loading': 'Chargement des presets…',
    'presets.loadFailed': 'Impossible de charger les presets.',
    'presets.scope.teamHome': 'Équipe à domicile',
    'presets.scope.teamAway': 'Équipe visiteuse',
    'presets.scope.layout': 'Position',
    'presets.scope.colors': 'Couleurs',
    'presets.scope.style': 'Style',
    'presets.scope.theme': 'Thème',
    'rules.loading': 'Chargement des règles…',
    'rules.mode': 'Mode',
    'rules.mode.indoor': 'Salle',
    'rules.mode.beach': 'Plage',
    'rules.setsLimit': 'Sets',
    'rules.bestOf.1': 'Un seul set',
    'rules.bestOf.3': 'Au meilleur des 3',
    'rules.bestOf.5': 'Au meilleur des 5',
    'rules.pointsLimit': 'Points / set',
    'rules.pointsLimitLastSet': 'Points / set décisif',
    'rules.resetDefaults': 'Réinitialiser le mode',
    'rules.sideSwitchPending': 'Changement de côté',
    'rules.sideSwitchInN': 'Changement de côté dans {n}',
    'alerts.matchFinished': 'Match terminé',
    'alerts.matchPoint': 'Balle de match',
    'alerts.setPoint': 'Balle de set',
    'alerts.team': 'Équipe {team}',

    // Teams section
    'teams.select': '— Sélectionner —',
    'teams.customPlaceholder': 'Nom d’équipe personnalisé...',
    'teams.backToList': 'Retour à la liste',
    'teams.customName': 'Nom personnalisé',
    'teams.color': 'Couleur',
    'teams.text': 'Texte',

    // Overlay section
    'overlay.logos': 'Logos',
    'overlay.gradient': 'Dégradé',
    'overlay.setColor': 'Couleur du set',
    'overlay.setText': 'Texte du set',
    'overlay.gameColor': 'Couleur du jeu',
    'overlay.gameText': 'Texte du jeu',
    'overlay.styleLabel': 'Style de l’overlay',
    'overlay.style': '— Style —',
    'overlay.preloadedConfigLabel': 'Config. préchargée',
    'overlay.selectAndLoad': '— Sélectionner et charger —',

    // Position section
    'position.height': 'Hauteur',
    'position.width': 'Largeur',
    'position.hPos': 'Pos H',
    'position.vPos': 'Pos V',
    'position.decrease': 'Diminuer',
    'position.increase': 'Augmenter',
    'position.links': 'Liens',

    // Links dialog
    'links.title': 'Liens',
    'links.control': 'Contrôle',
    'links.overlay': 'Overlay',
    'links.preview': 'Aperçu',
    'links.latest_match_report': 'Rapport du dernier match',
    'links.match_history': 'Historique des matchs',
    'links.copyToClipboard': 'Copier dans le presse-papiers',
    'links.close': 'Fermer',
    'links.noLinks': 'Aucun lien disponible pour cette session.',

    // Buttons section
    'buttons.followTeamColors': 'Suivre les couleurs d’équipe',
    'buttons.t1Btn': 'Btn É1',
    'buttons.t1Text': 'Texte É1',
    'buttons.t2Btn': 'Btn É2',
    'buttons.t2Text': 'Texte É2',
    'buttons.resetColors': 'Réinitialiser les couleurs',
    'buttons.showTeamIcon': 'Afficher l’icône d’équipe',
    'buttons.opacity': 'Opacité : {value}%',
    'buttons.buttonFont': 'Police des boutons',

    // Behavior section
    'behavior.autoHide': 'Masquer le tableau automatiquement',
    'behavior.hideAfter': 'Masquer après {value}s',
    'behavior.autoSimple': 'Mode simple automatique',
    'behavior.fullOnTimeout': 'Mode complet au temps mort',
    'behavior.haptics': 'Retour haptique',
    'behavior.showPreview': 'Afficher l’aperçu de l’overlay',

    // Preview
    'preview.title': 'Aperçu de l’overlay',
    'preview.zoomIn': 'Zoom avant',
    'preview.zoomOut': 'Zoom arrière',
    'preview.missingOutput': 'Aucune URL de sortie d’overlay fournie.',
    'preview.styleOverride': 'Style de l’aperçu (ne modifie pas l’overlay)',
    'preview.styleDefault': 'Style par défaut',

    // Color picker
    'colorPicker.presets': 'Préréglages',
    'colorPicker.recent': 'Récents',

    // Language
    'lang.label': 'Langue',
  },
  de: {
    // Init screen
    'app.title': 'Volleyball-Anzeigetafel',
    'app.oidLabel': 'Overlay-Steuer-ID (OID)',
    'app.oidPlaceholder': 'mein-overlay',
    'app.connect': 'Verbinden',
    'app.selectOverlay': 'Overlay auswählen',
    'app.selectOverlayPlaceholder': '— Auswählen —',
    'app.orManualOid': 'oder OID manuell eingeben',
    'app.connecting': 'Verbinde…',

    // Dialog
    'dialog.ok': 'OK',
    'dialog.cancel': 'Abbrechen',
    'dialog.setScore': 'Punktestand — Team {team}',
    'dialog.setSets': 'Gewonnene Sätze — Team {team}',

    // Control buttons
    'ctrl.hideOverlay': 'Overlay ausblenden',
    'ctrl.showOverlay': 'Overlay einblenden',
    'ctrl.hidePreview': 'Vorschau ausblenden',
    'ctrl.showPreview': 'Vorschau einblenden',
    'ctrl.fullScoreboard': 'Volle Anzeigetafel',
    'ctrl.simpleScoreboard': 'Einfache Anzeigetafel',
    'ctrl.undoLast': 'Letzte Aktion rückgängig',
    'ctrl.fullscreen': 'Vollbild',
    'ctrl.exitFullscreen': 'Vollbild beenden',
    'ctrl.lightMode': 'Heller Modus',
    'ctrl.darkMode': 'Dunkler Modus',
    'ctrl.themeAuto': 'Theme: System folgen',
    'ctrl.startMatch': 'Spiel starten',
    'ctrl.reset': 'Zurücksetzen',
    'ctrl.config': 'Einstellungen',
    'ctrl.configHint': 'Einstellungen — oder nach links wischen',

    // Connection status
    'conn.online': 'Live-Synchronisation aktiv',
    'conn.reconnecting': 'Verbindung wird wiederhergestellt…',

    // Confirmation dialogs
    'confirm.title': 'Sicher?',
    'confirm.confirm': 'Bestätigen',
    'confirm.cancel': 'Abbrechen',

    // Preview fallback
    'preview.unavailable': 'Vorschau nicht verfügbar',
    'preview.retry': 'Erneut versuchen',

    // Gesture coachmark / first-run tour
    'tour.skip': 'Überspringen',
    'tour.prev': 'Zurück',
    'tour.next': 'Weiter',
    'tour.done': 'Verstanden',
    'tour.progress': 'Schritt {step} von {total}',
    'tour.tap.title': 'Tippen für Punkt',
    'tour.tap.body': 'Tippe auf das Team-Panel, um einen Punkt zu vergeben. Der Aufschlag wechselt automatisch.',
    'tour.doubletap.title': 'Doppeltippen zum Rückgängig machen',
    'tour.doubletap.body': 'Doppeltippen auf das Team-Panel — oder die Rückgängig-Taste — macht den letzten Punkt oder die letzte Auszeit dieses Teams rückgängig.',
    'tour.longpress.title': 'Lange drücken zum Bearbeiten',
    'tour.longpress.body': 'Halte den Punktestand oder Satzzähler gedrückt, um einen eigenen Wert zu setzen, falls eine manuelle Korrektur nötig ist.',
    'tour.config.title': 'Einstellungen öffnen',
    'tour.config.body': 'Wische nach links, oder tippe das Zahnrad oben rechts, für Teams, Farben, Regeln und Links.',

    // Share / quick links
    'share.title': 'Spiel teilen',

    // Recent-audit drawer (Phase 4.2)
    'history.title': 'Verlauf',
    'history.close': 'Verlauf schließen',
    'history.refresh': 'Aktualisieren',
    'history.empty': 'Noch keine Aktionen.',
    'history.loading': 'Lädt…',
    'history.relative.justNow': 'gerade eben',
    'history.relative.seconds': 'vor {n}s',
    'history.relative.minutes': 'vor {n}m',
    'history.relative.hours': 'vor {n}h',
    'history.action.point': 'Punkt — Team {team}',
    'history.action.set': 'Satzgewinn — Team {team}',
    'history.action.timeout': 'Auszeit — Team {team}',
    'history.action.serve': 'Aufschlagwechsel → Team {team}',
    'history.action.edit': 'Manuelle Punktzahl — Team {team} Satz {set} = {value}',
    'history.action.reset': 'Reset',
    'history.action.unknown': '(unbekannte Aktion)',
    'history.action.undoSuffix': ' (rückgängig)',
    'history.legend.pointT1': 'Punkt T1',
    'history.legend.pointT2': 'Punkt T2',
    'history.legend.set': 'Satzgewinn',
    'history.legend.timeout': 'Auszeit',
    'history.legend.serve': 'Aufschlagwechsel',
    'history.legend.edit': 'Manuelle Bearbeitung',
    'history.legend.reset': 'Reset',
    'history.legend.undone': 'Rückgängig',

    // Config panel
    'config.title': 'Config',
    'config.backToScoreboard': 'Zurück zur Anzeigetafel',
    'config.save': 'Speichern',
    'config.saveCustomization': 'Anpassung speichern',
    'config.failedToSave': 'Anpassung konnte nicht gespeichert werden',
    'config.saving': 'Speichert…',
    'config.retry': 'Erneut versuchen',
    'config.reloadFromServer': 'Vom Server neu laden',
    'config.reloadConfirm': 'Anpassung vom Server neu laden?',
    'config.resetMatch': 'Spiel zurücksetzen',
    'config.resetConfirm': 'Das Spiel zurücksetzen?',
    'config.logout': 'Abmelden',
    'config.logoutConfirm': 'Abmelden und zur OID-Eingabe zurückkehren?',
    'config.unsavedChangesConfirm': 'Es gibt ungespeicherte Änderungen, die verloren gehen. Trotzdem verlassen?',

    // Config sections
    'section.presets': 'Vorlagen',
    'section.teams': 'Teams',
    'section.overlay': 'Overlay-Stil',
    'section.position': 'Position und Größe',
    'section.buttons': 'Button-Aussehen',
    'section.behavior': 'Verhalten',
    'section.rules': 'Spielregeln',
    'section.links': 'Links',
    'presets.predefined': 'Vordefiniert',
    'presets.yours': 'Deine',
    'presets.apply': 'Anwenden',
    'presets.empty': 'Keine Vorlagen verfügbar',
    'presets.emptyHint': 'Bitte einen Admin, eine über /manage anzulegen.',
    'presets.lastApplied': 'Zuletzt angewendet',
    'presets.readOnlyBadge': 'Schreibgeschützt',
    'presets.readOnlyHint': 'Per Umgebungsvariable definiert; hier nicht änderbar.',
    'presets.loading': 'Lade Vorlagen…',
    'presets.loadFailed': 'Vorlagen konnten nicht geladen werden.',
    'presets.scope.teamHome': 'Heimteam',
    'presets.scope.teamAway': 'Gästeteam',
    'presets.scope.layout': 'Position',
    'presets.scope.colors': 'Farben',
    'presets.scope.style': 'Stil',
    'presets.scope.theme': 'Thema',
    'rules.loading': 'Regeln werden geladen…',
    'rules.mode': 'Modus',
    'rules.mode.indoor': 'Halle',
    'rules.mode.beach': 'Beach',
    'rules.setsLimit': 'Sätze',
    'rules.bestOf.1': 'Einzelsatz',
    'rules.bestOf.3': 'Best of 3',
    'rules.bestOf.5': 'Best of 5',
    'rules.pointsLimit': 'Punkte / Satz',
    'rules.pointsLimitLastSet': 'Punkte / Entscheidungssatz',
    'rules.resetDefaults': 'Standardwerte zurücksetzen',
    'rules.sideSwitchPending': 'Seitenwechsel',
    'rules.sideSwitchInN': 'Seitenwechsel in {n}',
    'alerts.matchFinished': 'Spiel beendet',
    'alerts.matchPoint': 'Matchball',
    'alerts.setPoint': 'Satzball',
    'alerts.team': 'Team {team}',

    // Teams section
    'teams.select': '— Auswählen —',
    'teams.customPlaceholder': 'Eigener Teamname...',
    'teams.backToList': 'Zurück zur Liste',
    'teams.customName': 'Eigener Name',
    'teams.color': 'Farbe',
    'teams.text': 'Text',

    // Overlay section
    'overlay.logos': 'Logos',
    'overlay.gradient': 'Verlauf',
    'overlay.setColor': 'Satz-Farbe',
    'overlay.setText': 'Satz-Text',
    'overlay.gameColor': 'Spiel-Farbe',
    'overlay.gameText': 'Spiel-Text',
    'overlay.styleLabel': 'Overlay-Stil',
    'overlay.style': '— Stil —',
    'overlay.preloadedConfigLabel': 'Vorkonfig.',
    'overlay.selectAndLoad': '— Auswählen und Laden —',

    // Position section
    'position.height': 'Höhe',
    'position.width': 'Breite',
    'position.hPos': 'Pos H',
    'position.vPos': 'Pos V',
    'position.decrease': 'Verringern',
    'position.increase': 'Erhöhen',
    'position.links': 'Links',

    // Links dialog
    'links.title': 'Links',
    'links.control': 'Steuerung',
    'links.overlay': 'Overlay',
    'links.preview': 'Vorschau',
    'links.latest_match_report': 'Letzter Spielbericht',
    'links.match_history': 'Spielverlauf',
    'links.copyToClipboard': 'In Zwischenablage kopieren',
    'links.close': 'Schließen',
    'links.noLinks': 'Keine Links für diese Sitzung verfügbar.',

    // Buttons section
    'buttons.followTeamColors': 'Teamfarben übernehmen',
    'buttons.t1Btn': 'Btn T1',
    'buttons.t1Text': 'Text T1',
    'buttons.t2Btn': 'Btn T2',
    'buttons.t2Text': 'Text T2',
    'buttons.resetColors': 'Farben zurücksetzen',
    'buttons.showTeamIcon': 'Teamsymbol anzeigen',
    'buttons.opacity': 'Deckkraft: {value}%',
    'buttons.buttonFont': 'Button-Schriftart',

    // Behavior section
    'behavior.autoHide': 'Anzeigetafel automatisch ausblenden',
    'behavior.hideAfter': 'Nach {value}s ausblenden',
    'behavior.autoSimple': 'Automatischer Einfachmodus',
    'behavior.fullOnTimeout': 'Vollmodus bei Auszeit',
    'behavior.haptics': 'Haptisches Feedback',
    'behavior.showPreview': 'Overlay-Vorschau anzeigen',

    // Preview
    'preview.title': 'Overlay-Vorschau',
    'preview.zoomIn': 'Vergrößern',
    'preview.zoomOut': 'Verkleinern',
    'preview.missingOutput': 'Keine Overlay-Ausgabe-URL angegeben.',
    'preview.styleOverride': 'Vorschaustil (ändert das Overlay nicht)',
    'preview.styleDefault': 'Standardstil',

    // Color picker
    'colorPicker.presets': 'Voreinstellungen',
    'colorPicker.recent': 'Zuletzt verwendet',

    // Language
    'lang.label': 'Sprache',
  },
};

export type TranslateParams = Record<string, string | number>;
export type Translate = (key: string, params?: TranslateParams) => string;

export interface I18nContextValue {
  lang: string;
  setLanguage: (l: string) => void;
  t: Translate;
  languages: string[];
}

const I18nContext = createContext<I18nContextValue | undefined>(undefined);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLang] = useState<string>(() => {
    try {
      const saved = localStorage.getItem('volley_lang');
      if (saved && translations[saved]) return saved;
    } catch (e) { console.warn('Failed to read language setting:', e); }
    const browserLang = navigator.language?.slice(0, 2);
    return translations[browserLang ?? ''] ? browserLang! : 'en';
  });

  const setLanguage = useCallback((l: string) => {
    setLang(l);
    try { localStorage.setItem('volley_lang', l); } catch (e) { console.warn('Failed to save language setting:', e); }
  }, []);

  const t = useCallback<Translate>((key, params) => {
    let str = translations[lang]?.[key] ?? translations.en?.[key] ?? key;
    if (params) {
      Object.entries(params).forEach(([k, v]) => {
        str = str.replaceAll(`{${k}}`, () => String(v));
      });
    }
    return str;
  }, [lang]);

  const value = useMemo<I18nContextValue>(
    () => ({ lang, setLanguage, t, languages: Object.keys(translations) }),
    [lang, setLanguage, t],
  );

  return (
    <I18nContext.Provider value={value}>
      {children}
    </I18nContext.Provider>
  );
}

export function useI18n(): I18nContextValue {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error('useI18n must be used within an I18nProvider');
  return ctx;
}
