import React, { Suspense, lazy } from 'react';
import ReactDOM from 'react-dom/client';
import { installErrorReporter } from './utils/errorReporter';
import ErrorBoundary from './components/ErrorBoundary';
import './material-icons.css';
import './App.css';

installErrorReporter();

// The OBS preview surface (/preview) is a standalone, auth-free page; the rest
// of the SPA goes through the authenticated router (AppRouter), which mounts
// the login/account pages and the control board.
const PreviewApp = lazy(() => import('./PreviewApp'));
const AppRouter = lazy(() => import('./AppRouter'));

const root = document.getElementById('root');
if (!root) throw new Error('Root element #root not found');

const isPreviewRoute = window.location.pathname.replace(/\/+$/, '').endsWith('/preview');

ReactDOM.createRoot(root).render(
  <React.StrictMode>
    {/* Outermost net for a rejected chunk. The router, the preview app
        and the board are all lazily imported, so any of them can fail to
        load in a tab that outlived its deployment — and a rejection that
        reaches the root unmounts everything, leaving a blank page with no
        way back. */}
    <ErrorBoundary>
      <Suspense fallback={null}>{isPreviewRoute ? <PreviewApp /> : <AppRouter />}</Suspense>
    </ErrorBoundary>
  </React.StrictMode>,
);
