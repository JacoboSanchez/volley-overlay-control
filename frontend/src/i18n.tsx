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
    'ctrl.undoOn': 'Undo mode ON',
    'ctrl.undoOff': 'Undo mode OFF',
    'ctrl.fullscreen': 'Fullscreen',
    'ctrl.exitFullscreen': 'Exit fullscreen',
    'ctrl.lightMode': 'Light mode',
    'ctrl.darkMode': 'Dark mode',
    'ctrl.config': 'Configuration',

    // Config panel
    'config.title': 'Config',
    'config.backToScoreboard': 'Back to scoreboard',
    'config.save': 'Save',
    'config.saveCustomization': 'Save customization',
    'config.failedToSave': 'Failed to save customization',
    'config.reloadFromServer': 'Reload from server',
    'config.reloadConfirm': 'Reload customization from server?',
    'config.resetMatch': 'Reset match',
    'config.resetConfirm': 'Reset the match?',
    'config.logout': 'Logout',
    'config.logoutConfirm': 'Disconnect and return to OID entry?',

    // Config sections
    'section.teams': 'Teams',
    'section.overlay': 'Overlay Style',
    'section.position': 'Position & Size',
    'section.buttons': 'Button Appearance',
    'section.behavior': 'Behavior',
    'section.links': 'Links',

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
    'ctrl.undoOn': 'Deshacer activado',
    'ctrl.undoOff': 'Deshacer desactivado',
    'ctrl.fullscreen': 'Pantalla completa',
    'ctrl.exitFullscreen': 'Salir de pantalla completa',
    'ctrl.lightMode': 'Modo claro',
    'ctrl.darkMode': 'Modo oscuro',
    'ctrl.config': 'Configuración',

    // Config panel
    'config.title': 'Config',
    'config.backToScoreboard': 'Volver al marcador',
    'config.save': 'Guardar',
    'config.saveCustomization': 'Guardar personalización',
    'config.failedToSave': 'Error al guardar la personalización',
    'config.reloadFromServer': 'Recargar del servidor',
    'config.reloadConfirm': '¿Recargar personalización del servidor?',
    'config.resetMatch': 'Reiniciar partido',
    'config.resetConfirm': '¿Reiniciar el partido?',
    'config.logout': 'Cerrar sesión',
    'config.logoutConfirm': '¿Desconectar y volver a la entrada de OID?',

    // Config sections
    'section.teams': 'Equipos',
    'section.overlay': 'Estilo del Overlay',
    'section.position': 'Posición y Tamaño',
    'section.buttons': 'Apariencia de Botones',
    'section.behavior': 'Comportamiento',
    'section.links': 'Enlaces',

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
    'app.title': 'Placar de Vôlei',
    'app.oidLabel': 'ID de Controle do Overlay (OID)',
    'app.oidPlaceholder': 'meu-overlay',
    'app.connect': 'Conectar',
    'app.selectOverlay': 'Selecionar Overlay',
    'app.selectOverlayPlaceholder': '— Selecionar —',
    'app.orManualOid': 'ou inserir o OID manualmente',

    // Dialog
    'dialog.ok': 'OK',
    'dialog.cancel': 'Cancelar',
    'dialog.setScore': 'Pontuação — Equipe {team}',
    'dialog.setSets': 'Sets vencidos — Equipe {team}',

    // Control buttons
    'ctrl.hideOverlay': 'Ocultar overlay',
    'ctrl.showOverlay': 'Mostrar overlay',
    'ctrl.hidePreview': 'Ocultar prévia',
    'ctrl.showPreview': 'Mostrar prévia',
    'ctrl.fullScoreboard': 'Placar completo',
    'ctrl.simpleScoreboard': 'Placar simples',
    'ctrl.undoOn': 'Modo desfazer ATIVO',
    'ctrl.undoOff': 'Modo desfazer INATIVO',
    'ctrl.fullscreen': 'Tela cheia',
    'ctrl.exitFullscreen': 'Sair da tela cheia',
    'ctrl.lightMode': 'Modo claro',
    'ctrl.darkMode': 'Modo escuro',
    'ctrl.config': 'Configuração',

    // Config panel
    'config.title': 'Config',
    'config.backToScoreboard': 'Voltar ao placar',
    'config.save': 'Salvar',
    'config.saveCustomization': 'Salvar personalização',
    'config.failedToSave': 'Erro ao salvar personalização',
    'config.reloadFromServer': 'Recarregar do servidor',
    'config.reloadConfirm': 'Recarregar personalização do servidor?',
    'config.resetMatch': 'Reiniciar partida',
    'config.resetConfirm': 'Reiniciar a partida?',
    'config.logout': 'Sair',
    'config.logoutConfirm': 'Desconectar e voltar à entrada do OID?',

    // Config sections
    'section.teams': 'Equipes',
    'section.overlay': 'Estilo do Overlay',
    'section.position': 'Posição e Tamanho',
    'section.buttons': 'Aparência dos Botões',
    'section.behavior': 'Comportamento',
    'section.links': 'Links',

    // Teams section
    'teams.select': '— Selecionar —',
    'teams.customPlaceholder': 'Nome personalizado da equipe...',
    'teams.backToList': 'Voltar à lista',
    'teams.customName': 'Nome personalizado',
    'teams.color': 'Cor',
    'teams.text': 'Texto',

    // Overlay section
    'overlay.logos': 'Logos',
    'overlay.gradient': 'Degradê',
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
    'position.links': 'Links',

    // Links dialog
    'links.title': 'Links',
    'links.control': 'Controle',
    'links.overlay': 'Overlay',
    'links.preview': 'Prévia',
    'links.copyToClipboard': 'Copiar para área de transferência',
    'links.close': 'Fechar',
    'links.noLinks': 'Não há links disponíveis para esta sessão.',

    // Buttons section
    'buttons.followTeamColors': 'Seguir cores da equipe',
    'buttons.t1Btn': 'Btn E1',
    'buttons.t1Text': 'Texto E1',
    'buttons.t2Btn': 'Btn E2',
    'buttons.t2Text': 'Texto E2',
    'buttons.resetColors': 'Redefinir cores',
    'buttons.showTeamIcon': 'Mostrar ícone da equipe',
    'buttons.opacity': 'Opacidade: {value}%',
    'buttons.buttonFont': 'Fonte dos botões',

    // Behavior section
    'behavior.autoHide': 'Ocultar placar automaticamente',
    'behavior.hideAfter': 'Ocultar após {value}s',
    'behavior.autoSimple': 'Modo simples automático',
    'behavior.fullOnTimeout': 'Modo completo no pedido de tempo',
    'behavior.showPreview': 'Mostrar prévia do overlay',

    // Preview
    'preview.title': 'Prévia do overlay',
    'preview.zoomIn': 'Ampliar',
    'preview.zoomOut': 'Reduzir',
    'preview.missingOutput': 'Nenhuma URL de saída do overlay foi fornecida.',
    'preview.styleOverride': 'Estilo da prévia (não altera o overlay)',
    'preview.styleDefault': 'Estilo padrão',

    // Color picker
    'colorPicker.presets': 'Predefinidos',
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
    'ctrl.undoOn': 'Modalità annulla ATTIVA',
    'ctrl.undoOff': 'Modalità annulla DISATTIVA',
    'ctrl.fullscreen': 'Schermo intero',
    'ctrl.exitFullscreen': 'Esci da schermo intero',
    'ctrl.lightMode': 'Modalità chiara',
    'ctrl.darkMode': 'Modalità scura',
    'ctrl.config': 'Configurazione',

    // Config panel
    'config.title': 'Config',
    'config.backToScoreboard': 'Torna al tabellone',
    'config.save': 'Salva',
    'config.saveCustomization': 'Salva personalizzazione',
    'config.failedToSave': 'Errore nel salvataggio della personalizzazione',
    'config.reloadFromServer': 'Ricarica dal server',
    'config.reloadConfirm': 'Ricaricare la personalizzazione dal server?',
    'config.resetMatch': 'Reimposta partita',
    'config.resetConfirm': 'Reimpostare la partita?',
    'config.logout': 'Esci',
    'config.logoutConfirm': 'Disconnettersi e tornare all’inserimento OID?',

    // Config sections
    'section.teams': 'Squadre',
    'section.overlay': 'Stile Overlay',
    'section.position': 'Posizione e Dimensione',
    'section.buttons': 'Aspetto dei Pulsanti',
    'section.behavior': 'Comportamento',
    'section.links': 'Link',

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
    'ctrl.undoOn': 'Mode annuler ACTIVÉ',
    'ctrl.undoOff': 'Mode annuler DÉSACTIVÉ',
    'ctrl.fullscreen': 'Plein écran',
    'ctrl.exitFullscreen': 'Quitter le plein écran',
    'ctrl.lightMode': 'Mode clair',
    'ctrl.darkMode': 'Mode sombre',
    'ctrl.config': 'Configuration',

    // Config panel
    'config.title': 'Config',
    'config.backToScoreboard': 'Retour au tableau',
    'config.save': 'Enregistrer',
    'config.saveCustomization': 'Enregistrer la personnalisation',
    'config.failedToSave': 'Échec de l’enregistrement de la personnalisation',
    'config.reloadFromServer': 'Recharger depuis le serveur',
    'config.reloadConfirm': 'Recharger la personnalisation depuis le serveur ?',
    'config.resetMatch': 'Réinitialiser le match',
    'config.resetConfirm': 'Réinitialiser le match ?',
    'config.logout': 'Déconnexion',
    'config.logoutConfirm': 'Se déconnecter et revenir à la saisie de l’OID ?',

    // Config sections
    'section.teams': 'Équipes',
    'section.overlay': 'Style de l’overlay',
    'section.position': 'Position et taille',
    'section.buttons': 'Apparence des boutons',
    'section.behavior': 'Comportement',
    'section.links': 'Liens',

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
    'ctrl.undoOn': 'Rückgängig-Modus EIN',
    'ctrl.undoOff': 'Rückgängig-Modus AUS',
    'ctrl.fullscreen': 'Vollbild',
    'ctrl.exitFullscreen': 'Vollbild beenden',
    'ctrl.lightMode': 'Heller Modus',
    'ctrl.darkMode': 'Dunkler Modus',
    'ctrl.config': 'Einstellungen',

    // Config panel
    'config.title': 'Config',
    'config.backToScoreboard': 'Zurück zur Anzeigetafel',
    'config.save': 'Speichern',
    'config.saveCustomization': 'Anpassung speichern',
    'config.failedToSave': 'Anpassung konnte nicht gespeichert werden',
    'config.reloadFromServer': 'Vom Server neu laden',
    'config.reloadConfirm': 'Anpassung vom Server neu laden?',
    'config.resetMatch': 'Spiel zurücksetzen',
    'config.resetConfirm': 'Das Spiel zurücksetzen?',
    'config.logout': 'Abmelden',
    'config.logoutConfirm': 'Abmelden und zur OID-Eingabe zurückkehren?',

    // Config sections
    'section.teams': 'Teams',
    'section.overlay': 'Overlay-Stil',
    'section.position': 'Position und Größe',
    'section.buttons': 'Button-Aussehen',
    'section.behavior': 'Verhalten',
    'section.links': 'Links',

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
    let str = translations[lang]?.[key] ?? translations.en[key] ?? key;
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
