import { describe, it, expect } from 'vitest';
import { screen } from '@testing-library/react';
import ScoreboardSkeleton from '../components/ScoreboardSkeleton';
import { renderWithI18n } from './helpers';

describe('ScoreboardSkeleton', () => {
  it('renders three placeholder panes for the scoreboard layout', () => {
    renderWithI18n(<ScoreboardSkeleton />);
    const skeleton = screen.getByTestId('scoreboard-skeleton');
    expect(skeleton).toBeInTheDocument();
    expect(skeleton.querySelectorAll('.scoreboard-skeleton-team').length).toBe(2);
    expect(skeleton.querySelector('.scoreboard-skeleton-center')).not.toBeNull();
  });

  it('exposes a polite live region with the connecting label', () => {
    renderWithI18n(<ScoreboardSkeleton />);
    const skeleton = screen.getByTestId('scoreboard-skeleton');
    expect(skeleton.getAttribute('role')).toBe('status');
    expect(skeleton.getAttribute('aria-busy')).toBe('true');
    expect(skeleton.getAttribute('aria-live')).toBe('polite');
    expect(skeleton.getAttribute('aria-label')).toBe('Connecting…');
  });

  it('switches the layout class for portrait orientation', () => {
    renderWithI18n(<ScoreboardSkeleton isPortrait />);
    const skeleton = screen.getByTestId('scoreboard-skeleton');
    expect(skeleton.className).toContain('scoreboard-skeleton-portrait');
    expect(skeleton.className).not.toContain('scoreboard-skeleton-landscape');
  });

  it('defaults to the landscape layout class', () => {
    renderWithI18n(<ScoreboardSkeleton />);
    const skeleton = screen.getByTestId('scoreboard-skeleton');
    expect(skeleton.className).toContain('scoreboard-skeleton-landscape');
  });
});
