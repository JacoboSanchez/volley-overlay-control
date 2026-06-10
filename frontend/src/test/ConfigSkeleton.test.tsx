import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import ConfigSkeleton from '../components/ConfigSkeleton';

describe('ConfigSkeleton', () => {
  it('renders a busy live region so screen readers announce loading', () => {
    const { container } = render(<ConfigSkeleton />);
    const root = container.querySelector('.config-skeleton');
    expect(root).not.toBeNull();
    expect(root).toHaveAttribute('aria-busy', 'true');
    expect(root).toHaveAttribute('aria-live', 'polite');
  });

  it('renders the placeholder lines including title and short variants', () => {
    const { container } = render(<ConfigSkeleton />);
    expect(container.querySelectorAll('.config-skeleton-line')).toHaveLength(4);
    expect(container.querySelectorAll('.config-skeleton-line-title')).toHaveLength(1);
    expect(container.querySelectorAll('.config-skeleton-line-short')).toHaveLength(1);
  });
});
