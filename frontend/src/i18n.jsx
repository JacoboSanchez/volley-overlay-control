import React, { createContext, useContext, useState, useCallback } from 'react';

const translations = {
  en: {
    // Init screen
    'app.title': 'Volley Scoreboard',
    'app.oidLabel': 'Overlay Control ID (OID)',
    'app.oidPlaceholder': 'C-my-overlay',
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
    'app.oidPlaceholder': 'C-mi-overlay',
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

    // Color picker
    'colorPicker.presets': 'Predefinidos',
    'colorPicker.recent': 'Recientes',

    // Language
    'lang.label': 'Idioma',
  },
};

const I18nContext = createContext();

export function I18nProvider({ children }) {
  const [lang, setLang] = useState(() => {
    try {
      const saved = localStorage.getItem('volley_lang');
      if (saved && translations[saved]) return saved;
    } catch (e) { console.warn('Failed to read language setting:', e); }
    const browserLang = navigator.language?.slice(0, 2);
    return translations[browserLang] ? browserLang : 'en';
  });

  const setLanguage = useCallback((l) => {
    setLang(l);
    try { localStorage.setItem('volley_lang', l); } catch (e) { console.warn('Failed to save language setting:', e); }
  }, []);

  const t = useCallback((key, params) => {
    let str = translations[lang]?.[key] ?? translations.en[key] ?? key;
    if (params) {
      Object.entries(params).forEach(([k, v]) => {
        str = str.replaceAll(`{${k}}`, v);
      });
    }
    return str;
  }, [lang]);

  return (
    <I18nContext.Provider value={{ lang, setLanguage, t, languages: Object.keys(translations) }}>
      {children}
    </I18nContext.Provider>
  );
}

export function useI18n() {
  return useContext(I18nContext);
}
