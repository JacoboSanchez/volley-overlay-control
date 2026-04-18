import React from 'react';
import ReactDOM from 'react-dom/client';
import { I18nProvider } from './i18n';
import { SettingsProvider } from './hooks/useSettings';
import App from './App';
import PreviewApp from './PreviewApp';
import './App.css';

const root = document.getElementById('root');
if (!root) throw new Error('Root element #root not found');

const isPreviewRoute =
  window.location.pathname.replace(/\/+$/, '').endsWith('/preview');

ReactDOM.createRoot(root).render(
  <React.StrictMode>
    {isPreviewRoute ? (
      <PreviewApp />
    ) : (
      <I18nProvider>
        <SettingsProvider>
          <App />
        </SettingsProvider>
      </I18nProvider>
    )}
  </React.StrictMode>
);
