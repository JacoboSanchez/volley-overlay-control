import { describe, it, expect, vi } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import TeamCard, { PredefinedTeams } from '../components/TeamCard';
import { renderWithI18n } from './helpers';

const predefinedTeams: PredefinedTeams = {
  Lions: { icon: 'https://example.com/lions.png', color: '#112233', text_color: '#ffffff' },
  Tigers: {},
};

describe('TeamCard', () => {
  it('shows a placeholder when the team has no logo', () => {
    renderWithI18n(
      <TeamCard teamId={1} model={{}} updateField={() => {}} predefinedTeams={predefinedTeams} />,
    );
    const preview = screen.getByTestId('team-1-logo-preview');
    expect(preview.querySelector('img')).toBeNull();
    expect(preview).toHaveTextContent('image');
  });

  it('shows a broken-image placeholder and hint on load error', () => {
    renderWithI18n(
      <TeamCard
        teamId={2}
        model={{ 'Team 2 Logo': 'https://example.com/away.png' }}
        updateField={() => {}}
        predefinedTeams={predefinedTeams}
      />,
    );
    const img = screen.getByAltText('Team 2 logo') as HTMLImageElement;
    expect(img).toHaveAttribute('src', 'https://example.com/away.png');
    fireEvent.error(img);
    // The failure stays visible instead of silently vanishing.
    expect(screen.queryByAltText('Team 2 logo')).toBeNull();
    expect(screen.getByTestId('team-2-logo-preview')).toHaveTextContent('broken_image');
    expect(screen.getByText('Image failed to load')).toBeInTheDocument();
  });

  it('edits the logo URL through the new field and clears it', () => {
    const updateField = vi.fn();
    renderWithI18n(
      <TeamCard
        teamId={1}
        model={{ 'Team 1 Logo': 'https://example.com/old.png' }}
        updateField={updateField}
        predefinedTeams={predefinedTeams}
      />,
    );
    fireEvent.change(screen.getByTestId('team-1-logo-url'), {
      target: { value: 'https://example.com/new.png' },
    });
    expect(updateField).toHaveBeenCalledWith('Team 1 Logo', 'https://example.com/new.png');

    fireEvent.click(screen.getByTestId('team-1-logo-clear'));
    expect(updateField).toHaveBeenCalledWith('Team 1 Logo', '');
  });

  it('disables the clear button when there is no logo', () => {
    renderWithI18n(
      <TeamCard teamId={1} model={{}} updateField={() => {}} predefinedTeams={predefinedTeams} />,
    );
    expect(screen.getByTestId('team-1-logo-clear')).toBeDisabled();
  });

  it('selecting a predefined team applies name, logo and colors', () => {
    const updateField = vi.fn();
    renderWithI18n(
      <TeamCard
        teamId={1}
        model={{}}
        updateField={updateField}
        predefinedTeams={predefinedTeams}
      />,
    );
    fireEvent.change(screen.getByTestId('team-1-name-selector'), {
      target: { value: 'Lions' },
    });
    expect(updateField).toHaveBeenCalledWith('Team 1 Name', 'Lions');
    expect(updateField).toHaveBeenCalledWith('Team 1 Logo', 'https://example.com/lions.png');
    expect(updateField).toHaveBeenCalledWith('Team 1 Color', '#112233');
    expect(updateField).toHaveBeenCalledWith('Team 1 Text Color', '#ffffff');
  });

  it('selecting a team without presets only updates the name', () => {
    const updateField = vi.fn();
    renderWithI18n(
      <TeamCard
        teamId={1}
        model={{}}
        updateField={updateField}
        predefinedTeams={predefinedTeams}
      />,
    );
    fireEvent.change(screen.getByTestId('team-1-name-selector'), {
      target: { value: 'Tigers' },
    });
    expect(updateField).toHaveBeenCalledOnce();
    expect(updateField).toHaveBeenCalledWith('Team 1 Name', 'Tigers');
  });

  it('appends a custom current name to the option list', () => {
    renderWithI18n(
      <TeamCard
        teamId={1}
        model={{ 'Team 1 Name': 'Garage Heroes' }}
        updateField={() => {}}
        predefinedTeams={predefinedTeams}
      />,
    );
    const select = screen.getByTestId('team-1-name-selector') as HTMLSelectElement;
    expect(select.value).toBe('Garage Heroes');
    expect(screen.getByRole('option', { name: 'Garage Heroes' })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: 'Lions' })).toBeInTheDocument();
  });

  it('writes to the legacy "Text Name" key when the model still uses it', () => {
    const updateField = vi.fn();
    renderWithI18n(
      <TeamCard
        teamId={1}
        model={{ 'Team 1 Text Name': 'Old Schema FC' }}
        updateField={updateField}
        predefinedTeams={predefinedTeams}
      />,
    );
    fireEvent.change(screen.getByTestId('team-1-name-selector'), {
      target: { value: 'Tigers' },
    });
    expect(updateField).toHaveBeenCalledWith('Team 1 Text Name', 'Tigers');
  });

  it('edit mode swaps in a text input that forwards typing, and exits on blur', () => {
    const updateField = vi.fn();
    renderWithI18n(
      <TeamCard
        teamId={1}
        model={{ 'Team 1 Name': 'Lions' }}
        updateField={updateField}
        predefinedTeams={predefinedTeams}
      />,
    );
    fireEvent.click(screen.getByTitle('Custom name'));
    const input = screen.getByTestId('team-1-name-selector') as HTMLInputElement;
    expect(input.tagName).toBe('INPUT');
    expect(input.value).toBe('Lions');
    fireEvent.change(input, { target: { value: 'Lionesses' } });
    expect(updateField).toHaveBeenCalledWith('Team 1 Name', 'Lionesses');
    fireEvent.blur(input);
    expect((screen.getByTestId('team-1-name-selector') as HTMLElement).tagName).toBe('SELECT');
  });

  it('the check button leaves edit mode without changing the name', () => {
    const updateField = vi.fn();
    renderWithI18n(
      <TeamCard teamId={1} model={{}} updateField={updateField} predefinedTeams={{}} />,
    );
    fireEvent.click(screen.getByTitle('Custom name'));
    fireEvent.mouseDown(screen.getByTitle('Back to list'));
    expect((screen.getByTestId('team-1-name-selector') as HTMLElement).tagName).toBe('SELECT');
    expect(updateField).not.toHaveBeenCalled();
  });

  it('forwards color changes to the right model keys', () => {
    const updateField = vi.fn();
    renderWithI18n(
      <TeamCard
        teamId={2}
        model={{ 'Team 2 Color': '#ff0000', 'Team 2 Text Color': '#000000' }}
        updateField={updateField}
        predefinedTeams={{}}
      />,
    );
    // Open the team color picker and pick a preset swatch.
    fireEvent.click(screen.getByTestId('team-2-color-input'));
    const presets = screen.getByTestId('team-2-color-input-presets');
    fireEvent.click(presets.querySelector('button')!);
    expect(updateField).toHaveBeenCalledWith('Team 2 Color', expect.stringMatching(/^#/));
  });
});
