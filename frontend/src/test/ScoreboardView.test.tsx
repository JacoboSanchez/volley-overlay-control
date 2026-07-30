import { describe, it, expect, vi } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import ScoreboardView from '../components/ScoreboardView';
import { BoardContextProvider } from '../board/BoardContexts';
import { boardContextValues, renderWithBoard, renderWithI18n } from './helpers';

const mocks = vi.hoisted(() => ({
  teamPanel: vi.fn(({ teamId }: { teamId: number }) => (
    <div data-testid={`team-panel-${teamId}`} />
  )),
}));

vi.mock('../components/TeamPanel', () => ({
  default: mocks.teamPanel,
}));

vi.mock('../components/CenterPanel', () => ({
  default: () => <div data-testid="center-panel" />,
}));

vi.mock('../components/ControlButtons', () => ({
  default: () => <div data-testid="control-buttons" />,
}));

describe('ScoreboardView top-right corner stack', () => {
  it('does not recompose its subtree for a board-state-only update', () => {
    mocks.teamPanel.mockClear();
    const initial = boardContextValues();
    const { rerender } = renderWithI18n(
      <BoardContextProvider {...initial}>
        <ScoreboardView />
      </BoardContextProvider>,
    );
    expect(mocks.teamPanel).toHaveBeenCalledTimes(2);

    const next = {
      ...initial,
      state: {
        ...initial.state,
        state: {
          ...initial.state.state,
          team_1: {
            ...initial.state.state.team_1,
            scores: { ...initial.state.state.team_1.scores, set_1: 26 },
          },
        },
      },
    };
    rerender(
      <BoardContextProvider {...next}>
        <ScoreboardView />
      </BoardContextProvider>,
    );
    expect(mocks.teamPanel).toHaveBeenCalledTimes(2);
  });

  it('renders config, share and history buttons in the top-right stack', () => {
    renderWithBoard(<ScoreboardView />);
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

  it('keeps a fixed DOM order across a side swap', () => {
    // Regression guard: the side swap must reorder team panels visually in
    // their own context-aware implementation without moving CentrePanel's
    // position, which would reload its preview iframe.
    const domOrder = () =>
      Array.from(document.querySelector('.main-layout')!.children).map(
        (c) => (c as HTMLElement).dataset.testid,
      );

    const { unmount } = renderWithBoard(<ScoreboardView />);
    expect(domOrder()).toEqual(['team-panel-1', 'center-panel', 'team-panel-2']);
    unmount();

    renderWithBoard(<ScoreboardView />, { state: { sidesSwapped: true } });
    expect(domOrder()).toEqual(['team-panel-1', 'center-panel', 'team-panel-2']);
  });

  it('invokes the matching callback when each top-right button is clicked', () => {
    const onOpenConfig = vi.fn();
    const onOpenShare = vi.fn();
    const onOpenHistory = vi.fn();
    renderWithBoard(<ScoreboardView />, {
      actions: { onOpenConfig, onOpenShare, onOpenHistory },
    });
    fireEvent.click(screen.getByTestId('config-tab-button'));
    fireEvent.click(screen.getByTestId('share-button'));
    fireEvent.click(screen.getByTestId('history-button'));
    expect(onOpenConfig).toHaveBeenCalledOnce();
    expect(onOpenShare).toHaveBeenCalledOnce();
    expect(onOpenHistory).toHaveBeenCalledOnce();
  });
});
