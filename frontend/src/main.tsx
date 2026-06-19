import React, { Suspense, lazy } from 'react';
import ReactDOM from 'react-dom/client';
import { installErrorReporter } from './utils/errorReporter';
import 'material-icons/iconfont/filled.css';
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
    <Suspense fallback={null}>{isPreviewRoute ? <PreviewApp /> : <AppRouter />}</Suspense>
  </React.StrictMode>,
);
