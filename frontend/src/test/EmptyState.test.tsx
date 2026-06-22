import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import EmptyState from '../components/EmptyState';

describe('EmptyState', () => {
  it('renders its message without an action by default', () => {
    render(
      <MemoryRouter>
        <EmptyState>Nothing here yet.</EmptyState>
      </MemoryRouter>,
    );
    expect(screen.getByText('Nothing here yet.')).toBeInTheDocument();
    expect(screen.queryByRole('link')).not.toBeInTheDocument();
  });

  it('renders a call-to-action link when an action is provided', () => {
    render(
      <MemoryRouter>
        <EmptyState action={{ to: '/overlays', label: 'Create a scoreboard →' }}>
          You have no scoreboards.
        </EmptyState>
      </MemoryRouter>,
    );
    const link = screen.getByRole('link', { name: 'Create a scoreboard →' });
    expect(link).toHaveAttribute('href', '/overlays');
  });
});
