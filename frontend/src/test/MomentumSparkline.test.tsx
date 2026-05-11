import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import MomentumSparkline from '../components/MomentumSparkline';
import type { LiveStatsPoint } from '../api/client';

function point(team: 1 | 2, t1: number, t2: number): LiveStatsPoint {
  return { team, set: 1, ts: null, score: [t1, t2], action: 'add_point' };
}

describe('MomentumSparkline', () => {
  it('returns null for an empty history', () => {
    const { container } = render(<MomentumSparkline history={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders an SVG with polyline + two area fills', () => {
    const history: LiveStatsPoint[] = [
      point(1, 1, 0),
      point(1, 2, 0),
      point(2, 2, 1),
      point(1, 3, 1),
    ];
    const { container } = render(<MomentumSparkline history={history} />);
    const svg = container.querySelector('svg.momentum-sparkline');
    expect(svg).not.toBeNull();
    expect(svg?.getAttribute('role')).toBe('img');
    const paths = container.querySelectorAll('path');
    // 2 area paths + 1 polyline path
    expect(paths.length).toBe(3);
  });

  it('respects custom dimensions', () => {
    const history: LiveStatsPoint[] = [
      point(1, 1, 0),
      point(2, 1, 1),
    ];
    const { container } = render(
      <MomentumSparkline history={history} width={100} height={20} />,
    );
    const svg = container.querySelector('svg.momentum-sparkline') as SVGElement;
    expect(svg.getAttribute('width')).toBe('100');
    expect(svg.getAttribute('height')).toBe('20');
    expect(svg.getAttribute('viewBox')).toBe('0 0 100 20');
  });

  it('uses the provided team colours for the area fills', () => {
    const history: LiveStatsPoint[] = [
      point(1, 1, 0),
      point(2, 1, 1),
    ];
    const { container } = render(
      <MomentumSparkline
        history={history}
        colorTeam1="#abcdef"
        colorTeam2="#fedcba"
      />,
    );
    const fills = Array.from(container.querySelectorAll('path'))
      .map((p) => p.getAttribute('fill'))
      .filter((f): f is string => !!f);
    expect(fills).toContain('#abcdef');
    expect(fills).toContain('#fedcba');
  });

  it('uses the provided aria-label override', () => {
    const history: LiveStatsPoint[] = [point(1, 1, 0), point(2, 1, 1)];
    const { container } = render(
      <MomentumSparkline history={history} ariaLabel="Custom label" />,
    );
    const svg = container.querySelector('svg.momentum-sparkline');
    expect(svg?.getAttribute('aria-label')).toBe('Custom label');
  });
});
