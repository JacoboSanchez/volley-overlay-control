import { describe, it, expect, vi } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import ScoreboardView from '../components/ScoreboardView';
import { renderWithI18n, mockGameState, mockCustomization } from './helpers';

vi.mock('../components/TeamPanel', () => ({
  default: ({ teamId, order }: { teamId: number; order?: number }) => (
    <div data-testid={`team-panel-${teamId}`} style={{ order }} />
  ),
}));

vi.mock('../components/CenterPanel', () => ({
  default: () => <div data-testid="center-panel" />,
}));

vi.mock('../components/ControlButtons', () => ({
  default: () => <div data-testid="control-buttons" />,
}));

const baseProps = {
  state: mockGameState,
  customization: mockCustomization,
  currentSet: 1,
  setsLimit: 5,
  isPortrait: false,
  previewData: null,
  showPreview: false,
  recentEvents: [],
  showControls: true,
  setShowControls: vi.fn(),
  canUndo: false,
  simpleMode: false,
  btnColorA: '#2196f3',
  btnTextA: '#ffffff',
  btnColorB: '#f44336',
  btnTextB: '#ffffff',
  iconLogoA: null,
  iconLogoB: null,
  onAddPoint: vi.fn(),
  onAddSet: vi.fn(),
  onAddTimeout: vi.fn(),
  onChangeServe: vi.fn(),
  onDoubleTapScore: vi.fn(),
  onDoubleTapTimeout: vi.fn(),
  onLongPressScore: vi.fn(),
  onLongPressSet: vi.fn(),
  onToggleVisibility: vi.fn(),
  onToggleSimpleMode: vi.fn(),
  onUndoLast: vi.fn(),
  onTogglePreview: vi.fn(),
  onStartMatch: vi.fn(),
  onReset: vi.fn(),
  onOpenConfig: vi.fn(),
  onOpenShare: vi.fn(),
  onOpenHistory: vi.fn(),
  sidesSwapped: false,
  onSwapSides: vi.fn(),
};

describe('ScoreboardView top-right corner stack', () => {
  it('renders config, share and history buttons in the top-right stack', () => {
    renderWithI18n(<ScoreboardView {...baseProps} />);
    const stack = document.querySelector('.top-corner-stack.top-right-stack');
    expect(stack).not.toBeNull();
    expect(screen.getByTestId('config-tab-button')).toBeInTheDocument();
    expect(screen.getByTestId('share-button')).toBeInTheDocument();
    expect(screen.getByTestId('history-button')).toBeInTheDocument();
    // Order matters: config on top, history at the bottom — that's
    // the visual hierarchy the operator scans on a phone in portrait.
    const buttons = Array.from(
      stack!.querySelectorAll<HTMLButtonElement>('button[data-testid]'),
    ).map((b) => b.dataset.testid);
    expect(buttons).toEqual(['config-tab-button', 'share-button', 'history-button']);
  });

  it('keeps a fixed DOM order across a side swap, flipping only flex order', () => {
    // Regression guard: the side swap must reorder the panels *visually*
    // (via CSS flex ``order``) without changing their DOM positions. If
    // the swap reordered the DOM, React would move the centre panel's
    // node — tearing down and reloading its embedded preview iframe (a
    // visible flash on every swap).
    const domOrder = () =>
      Array.from(document.querySelector('.main-layout')!.children).map(
        (c) => (c as HTMLElement).dataset.testid,
      );
    const orderOf = (testid: string) =>
      Number((screen.getByTestId(testid) as HTMLElement).style.order);

    const { rerender } = renderWithI18n(<ScoreboardView {...baseProps} sidesSwapped={false} />);
    // DOM order is always panel1 · centre · panel2.
    expect(domOrder()).toEqual(['team-panel-1', 'center-panel', 'team-panel-2']);
    // Not swapped: team 1 sits visually to the left of team 2.
    expect(orderOf('team-panel-1')).toBeLessThan(orderOf('team-panel-2'));

    rerender(<ScoreboardView {...baseProps} sidesSwapped={true} />);
    // DOM order is unchanged — only the flex order flips.
    expect(domOrder()).toEqual(['team-panel-1', 'center-panel', 'team-panel-2']);
    // Swapped: team 2 now sits visually to the left of team 1.
    expect(orderOf('team-panel-2')).toBeLessThan(orderOf('team-panel-1'));
  });

  it('invokes the matching callback when each top-right button is clicked', () => {
    const onOpenConfig = vi.fn();
    const onOpenShare = vi.fn();
    const onOpenHistory = vi.fn();
    renderWithI18n(
      <ScoreboardView
        {...baseProps}
        onOpenConfig={onOpenConfig}
        onOpenShare={onOpenShare}
        onOpenHistory={onOpenHistory}
      />,
    );
    fireEvent.click(screen.getByTestId('config-tab-button'));
    fireEvent.click(screen.getByTestId('share-button'));
    fireEvent.click(screen.getByTestId('history-button'));
    expect(onOpenConfig).toHaveBeenCalledOnce();
    expect(onOpenShare).toHaveBeenCalledOnce();
    expect(onOpenHistory).toHaveBeenCalledOnce();
  });
});
