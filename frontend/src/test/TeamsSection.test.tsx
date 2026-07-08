import { describe, it, expect, vi } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import { renderWithI18n } from './helpers';
import TeamsSection from '../components/config/TeamsSection';
import type { BoardGroup } from '../api/client';

const GROUPS: BoardGroup[] = [
  { id: null, name: 'All teams', kind: 'all', count: 3 },
  { id: 5, name: 'Liga', kind: 'shared', count: 2 },
  { id: 9, name: 'My league', kind: 'private', count: 1 },
];

const base = {
  model: {},
  updateField: vi.fn(),
  predefinedTeams: {},
};

describe('TeamsSection group picker', () => {
  it('renders no picker when there are no groups', () => {
    renderWithI18n(<TeamsSection {...base} />);
    expect(screen.queryByTestId('team-group-picker')).toBeNull();
  });

  it('lists groups (All localized + names with counts) and reports selection', () => {
    const onSelectGroup = vi.fn();
    renderWithI18n(
      <TeamsSection {...base} groups={GROUPS} selectedGroupId={5} onSelectGroup={onSelectGroup} />,
    );
    const picker = screen.getByTestId('team-group-picker') as HTMLSelectElement;
    expect(picker.value).toBe('5');
    // The virtual "All" option is localized; real groups keep their name.
    expect(screen.getByRole('option', { name: 'All teams (3)' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Liga (2)' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'My league (1)' })).toBeInTheDocument();

    fireEvent.change(picker, { target: { value: '9' } });
    expect(onSelectGroup).toHaveBeenCalledWith(9);
    // Selecting the "All" option reports null, not a number.
    fireEvent.change(picker, { target: { value: '' } });
    expect(onSelectGroup).toHaveBeenLastCalledWith(null);
  });
});
