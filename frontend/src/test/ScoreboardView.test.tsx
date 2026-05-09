import { describe, it, expect, vi } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import ScoreboardView from '../components/ScoreboardView';
import { renderWithI18n, mockGameState, mockCustomization } from './helpers';

vi.mock('../components/TeamPanel', () => ({
  default: ({ teamId }: { teamId: number }) => (
    <div data-testid={`team-panel-${teamId}`} />
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
    expect(buttons).toEqual([
      'config-tab-button',
      'share-button',
      'history-button',
    ]);
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
