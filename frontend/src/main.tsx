import React, { Suspense, lazy } from 'react';
import ReactDOM from 'react-dom/client';
import { I18nProvider } from './i18n';
import { SettingsProvider } from './hooks/useSettings';
import { installErrorReporter } from './utils/errorReporter';
import './App.css';

installErrorReporter();

const App = lazy(() => import('./App'));
const PreviewApp = lazy(() => import('./PreviewApp'));

const root = document.getElementById('root');
if (!root) throw new Error('Root element #root not found');

const isPreviewRoute =
  window.location.pathname.replace(/\/+$/, '').endsWith('/preview');

ReactDOM.createRoot(root).render(
  <React.StrictMode>
    <Suspense fallback={null}>
      {isPreviewRoute ? (
        <PreviewApp />
      ) : (
        <I18nProvider>
          <SettingsProvider>
            <App />
          </SettingsProvider>
        </I18nProvider>
      )}
    </Suspense>
  </React.StrictMode>
);
