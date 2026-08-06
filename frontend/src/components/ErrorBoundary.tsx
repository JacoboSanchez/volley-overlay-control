import { Component, type ReactNode, type ErrorInfo } from 'react';
import { reportClientError } from '../utils/errorReporter';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  message: string;
  isStaleChunk: boolean;
}

/**
 * True for the "this tab outlived the deployment it was loaded from"
 * failure: a lazy route asks for a hashed chunk the new build no longer
 * serves and the dynamic import rejects. Suspense only covers a *pending*
 * import, so without a boundary this blanks the UI. Worth telling apart
 * from a genuine crash because the fix is simply to reload, and because a
 * dropped connection produces the same rejection.
 */
function isChunkLoadError(error: Error): boolean {
  const text = `${error.name} ${error.message}`;
  return (
    /ChunkLoadError/i.test(text) ||
    /dynamically imported module/i.test(text) ||
    /Importing a module script failed/i.test(text) ||
    /error loading dynamically imported module/i.test(text)
  );
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, message: '', isStaleChunk: false };

  static getDerivedStateFromError(error: Error): State {
    return {
      hasError: true,
      message: error.message || 'Unexpected error',
      isStaleChunk: isChunkLoadError(error),
    };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Surface React-caught errors through the same channel as window.onerror.
    reportClientError({
      level: 'error',
      message: error.message || 'React error boundary',
      stack: `${error.stack ?? ''}\n${info.componentStack ?? ''}`.trim(),
    });
  }

  handleReload = () => {
    window.location.reload();
  };

  render() {
    if (!this.state.hasError) return this.props.children;
    if (this.props.fallback) return this.props.fallback;
    // Deliberately not auto-reloading: the same rejection comes from a
    // dropped connection, where a reload loop would trap the operator
    // instead of helping. One button, one reload, their choice.
    return (
      <div className="error-boundary" role="alert" aria-live="assertive">
        <h2>{this.state.isStaleChunk ? 'This page needs reloading' : 'Something went wrong'}</h2>
        <p>
          {this.state.isStaleChunk
            ? 'The app was updated (or the connection dropped) while this tab was open, so part of it could not be loaded. Reloading picks up the current version.'
            : this.state.message}
        </p>
        <button type="button" onClick={this.handleReload}>
          Reload
        </button>
      </div>
    );
  }
}
