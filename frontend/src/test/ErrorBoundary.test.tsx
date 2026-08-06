import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import ErrorBoundary from '../components/ErrorBoundary';

function Boom({ when }: { when: boolean }) {
  if (when) throw new Error('kaboom');
  return <div>ok</div>;
}

describe('ErrorBoundary', () => {
  let originalConsoleError: typeof console.error;

  beforeEach(() => {
    // React 19 still prints the caught error; silence the noise in tests.
    originalConsoleError = console.error;
    console.error = vi.fn();
  });

  afterEach(() => {
    console.error = originalConsoleError;
  });

  it('renders children when no error', () => {
    render(
      <ErrorBoundary>
        <Boom when={false} />
      </ErrorBoundary>,
    );
    expect(screen.getByText('ok')).toBeInTheDocument();
  });

  it('shows the fallback and error message when a child throws', () => {
    render(
      <ErrorBoundary>
        <Boom when={true} />
      </ErrorBoundary>,
    );
    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByText('kaboom')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /reload/i })).toBeInTheDocument();
  });

  it.each([
    'Failed to fetch dynamically imported module: https://x/assets/TeamsPage-abc.js',
    'error loading dynamically imported module',
    'Importing a module script failed.',
  ])('explains a stale-deployment chunk failure rather than dumping it: %s', (message) => {
    function ChunkBoom(): never {
      throw new Error(message);
    }
    render(
      <ErrorBoundary>
        <ChunkBoom />
      </ErrorBoundary>,
    );

    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByText(/needs reloading/i)).toBeInTheDocument();
    expect(screen.getByText(/app was updated/i)).toBeInTheDocument();
    // The raw fetch failure is not what an operator mid-match needs to read.
    expect(screen.queryByText(message)).toBeNull();
    expect(screen.getByRole('button', { name: /reload/i })).toBeInTheDocument();
  });

  it('recognises a ChunkLoadError by name', () => {
    function NamedChunkBoom(): never {
      const err = new Error('Loading chunk 42 failed.');
      err.name = 'ChunkLoadError';
      throw err;
    }
    render(
      <ErrorBoundary>
        <NamedChunkBoom />
      </ErrorBoundary>,
    );
    expect(screen.getByText(/needs reloading/i)).toBeInTheDocument();
  });

  it('still shows the raw message for an ordinary crash', () => {
    render(
      <ErrorBoundary>
        <Boom when={true} />
      </ErrorBoundary>,
    );
    expect(screen.getByText('kaboom')).toBeInTheDocument();
    expect(screen.queryByText(/needs reloading/i)).toBeNull();
  });

  it('reload button calls window.location.reload', () => {
    const reload = vi.fn();
    const origLocation = window.location;
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: { ...origLocation, reload },
    });

    render(
      <ErrorBoundary>
        <Boom when={true} />
      </ErrorBoundary>,
    );
    fireEvent.click(screen.getByRole('button', { name: /reload/i }));
    expect(reload).toHaveBeenCalled();

    Object.defineProperty(window, 'location', { configurable: true, value: origLocation });
  });
});
