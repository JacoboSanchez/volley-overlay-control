import { describe, it, expect, vi } from 'vitest';
import { act, screen, fireEvent } from '@testing-library/react';
import {
  ConfigSwitch,
  ConfigColorField,
  ConfigRange,
  InstantHint,
} from '../components/config/fields';
import LinkRow from '../components/LinkRow';
import { renderWithI18n } from './helpers';

vi.mock('../utils/clipboard', () => ({ writeToClipboard: vi.fn().mockResolvedValue(true) }));

import { writeToClipboard } from '../utils/clipboard';

describe('config field primitives', () => {
  it('ConfigSwitch reports the new checked state', () => {
    const onChange = vi.fn();
    renderWithI18n(<ConfigSwitch label="Logos" checked={false} onChange={onChange} testId="sw" />);
    fireEvent.click(screen.getByTestId('sw'));
    expect(onChange).toHaveBeenCalledWith(true);
  });

  it('ConfigRange emits numbers and links its label to the input', () => {
    const onChange = vi.fn();
    renderWithI18n(<ConfigRange label="Height" value={10} min={0} max={100} onChange={onChange} />);
    const slider = screen.getByLabelText('Height');
    fireEvent.change(slider, { target: { value: '42' } });
    expect(onChange).toHaveBeenCalledWith(42);
  });

  it('ConfigColorField labels its picker for assistive tech', () => {
    renderWithI18n(
      <ConfigColorField label="Set background" color="#123456" onChange={vi.fn()} testId="cp" />,
    );
    expect(screen.getByTestId('cp')).toHaveAttribute('aria-label', 'Set background');
  });

  it('InstantHint renders the applies-immediately copy', () => {
    renderWithI18n(<InstantHint />);
    expect(document.querySelector('.config-instant-hint')).not.toBeNull();
  });
});

describe('LinkRow', () => {
  it('opens in a new tab and copies with a transient check mark', () => {
    vi.useFakeTimers();
    renderWithI18n(<LinkRow url="https://x/overlay/tok" label="Overlay" />);
    const link = screen.getByRole('link', { name: 'Overlay' });
    expect(link).toHaveAttribute('href', 'https://x/overlay/tok');
    expect(link).toHaveAttribute('target', '_blank');

    fireEvent.click(screen.getByRole('button'));
    expect(writeToClipboard).toHaveBeenCalledWith('https://x/overlay/tok');
    expect(screen.getByText('check')).toBeInTheDocument();
    act(() => vi.advanceTimersByTime(1600));
    expect(screen.getByText('content_copy')).toBeInTheDocument();
    vi.useRealTimers();
  });
});
