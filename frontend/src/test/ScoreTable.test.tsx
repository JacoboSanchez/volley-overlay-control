import { describe, it, expect } from 'vitest';
import { screen } from '@testing-library/react';
import React from 'react';
import ScoreTable from '../components/ScoreTable';
import { renderWithI18n, mockGameState } from './helpers';

describe('ScoreTable', () => {
  it('returns null when state is null', () => {
    const { container } = renderWithI18n(
      <ScoreTable state={null} setsLimit={5} currentSet={2} teamId={1} />
    );
    expect(container.innerHTML).toBe('');
  });

  it('renders scores for completed sets', () => {
    renderWithI18n(
      <ScoreTable state={mockGameState} setsLimit={5} currentSet={2} teamId={1} />
    );
    // Set 1 is completed (score 25), should show "25"
    expect(screen.getByTestId('team-1-set-1-score')).toHaveTextContent('25');
  });

  it('pads scores to two digits', () => {
    const state = {
      ...mockGameState,
      team_1: { ...mockGameState.team_1, scores: { set_1: 5, set_2: 0 } },
      team_2: { ...mockGameState.team_2, scores: { set_1: 3, set_2: 0 } },
    };
    renderWithI18n(
      <ScoreTable state={state} setsLimit={5} currentSet={2} teamId={1} />
    );
    expect(screen.getByTestId('team-1-set-1-score')).toHaveTextContent('05');
  });

  it('applies score-bold class when team is winning a set', () => {
    renderWithI18n(
      <ScoreTable state={mockGameState} setsLimit={5} currentSet={2} teamId={1} />
    );
    const cell = screen.getByTestId('team-1-set-1-score');
    expect(cell.classList.contains('score-bold')).toBe(true);
  });

  it('does not apply score-bold when team is losing a set', () => {
    renderWithI18n(
      <ScoreTable state={mockGameState} setsLimit={5} currentSet={2} teamId={2} />
    );
    const cell = screen.getByTestId('team-2-set-1-score');
    expect(cell.classList.contains('score-bold')).toBe(false);
  });

  it('shows all set scores when match is finished', () => {
    const state = {
      ...mockGameState,
      match_finished: true,
      team_1: { ...mockGameState.team_1, sets: 3, scores: { set_1: 25, set_2: 25, set_3: 25 } },
      team_2: { ...mockGameState.team_2, sets: 0, scores: { set_1: 20, set_2: 20, set_3: 20 } },
    };
    renderWithI18n(
      <ScoreTable state={state} setsLimit={5} currentSet={3} teamId={1} />
    );
    expect(screen.getByTestId('team-1-set-1-score')).toBeInTheDocument();
    expect(screen.getByTestId('team-1-set-2-score')).toBeInTheDocument();
    expect(screen.getByTestId('team-1-set-3-score')).toBeInTheDocument();
  });

  it('returns null when no cells are generated', () => {
    // All scores zero and currentSet is 1 with match not finished = breaks before adding
    const state = {
      ...mockGameState,
      team_1: { ...mockGameState.team_1, sets: 0, scores: { set_1: 0 } },
      team_2: { ...mockGameState.team_2, sets: 0, scores: { set_1: 0 } },
    };
    const { container } = renderWithI18n(
      <ScoreTable state={state} setsLimit={5} currentSet={1} teamId={1} />
    );
    expect(container.querySelector('.score-column')).toBeNull();
  });

  it('renders team 2 scores correctly', () => {
    renderWithI18n(
      <ScoreTable state={mockGameState} setsLimit={5} currentSet={2} teamId={2} />
    );
    expect(screen.getByTestId('team-2-set-1-score')).toHaveTextContent('20');
  });
});
