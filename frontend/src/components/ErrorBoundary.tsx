import { Component, ReactNode, ErrorInfo } from 'react';
import { reportClientError } from '../utils/errorReporter';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  message: string;
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, message: '' };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, message: error.message || 'Unexpected error' };
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
    return (
      <div className="error-boundary" role="alert" aria-live="assertive">
        <h2>Something went wrong</h2>
        <p>{this.state.message}</p>
        <button type="button" onClick={this.handleReload}>
          Reload
        </button>
      </div>
    );
  }
}
