import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import FontSelector from '../components/FontSelector';
import { FONT_OPTIONS } from '../theme';

describe('FontSelector', () => {
  it('renders the current value on the trigger with the dropdown closed', () => {
    render(<FontSelector value="Atlas" onChange={() => {}} />);
    const trigger = screen.getByRole('button', { name: /Atlas/ });
    expect(trigger).toHaveTextContent('25-25');
    expect(trigger).toHaveTextContent('expand_more');
    expect(document.querySelector('.font-selector-dropdown')).toBeNull();
  });

  it('opens the dropdown with one option per font and marks the active one', () => {
    render(<FontSelector value="Atlas" onChange={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: /Atlas/ }));
    const options = document.querySelectorAll('.font-selector-option');
    expect(options).toHaveLength(FONT_OPTIONS.length);
    const active = document.querySelectorAll('.font-selector-option-active');
    expect(active).toHaveLength(1);
    expect(active[0]).toHaveTextContent('Atlas');
    // Chevron flips while open.
    expect(document.querySelector('.font-selector-trigger')).toHaveTextContent('expand_less');
  });

  it('previews each font in its own family, except Default', () => {
    render(<FontSelector value="Default" onChange={() => {}} />);
    // Trigger preview for Default carries no inline font family.
    const triggerPreview = document.querySelector('.font-selector-preview') as HTMLElement;
    expect(triggerPreview.style.fontFamily).toBe('');
    fireEvent.click(screen.getByRole('button', { name: /Default/ }));
    const atlasOption = Array.from(
      document.querySelectorAll<HTMLElement>('.font-selector-option'),
    ).find((el) => el.textContent?.includes('Atlas'))!;
    const preview = atlasOption.querySelector<HTMLElement>('.font-selector-preview')!;
    expect(preview.style.fontFamily).toContain('Atlas');
  });

  it('fires onChange and closes when an option is picked', () => {
    const onChange = vi.fn();
    render(<FontSelector value="Default" onChange={onChange} />);
    fireEvent.click(screen.getByRole('button', { name: /Default/ }));
    const option = Array.from(document.querySelectorAll<HTMLElement>('.font-selector-option')).find(
      (el) => el.textContent?.includes('Aluminum'),
    )!;
    fireEvent.click(option);
    expect(onChange).toHaveBeenCalledWith('Aluminum');
    expect(document.querySelector('.font-selector-dropdown')).toBeNull();
  });

  it('closes on pointerdown outside but stays open on inside interaction', () => {
    render(<FontSelector value="Default" onChange={() => {}} />);
    fireEvent.click(screen.getByRole('button', { name: /Default/ }));
    fireEvent.pointerDown(screen.getByTestId('font-selector'));
    expect(document.querySelector('.font-selector-dropdown')).not.toBeNull();
    fireEvent.pointerDown(document.body);
    expect(document.querySelector('.font-selector-dropdown')).toBeNull();
  });

  it('toggles closed when the trigger is clicked again', () => {
    render(<FontSelector value="Default" onChange={() => {}} />);
    const trigger = screen.getByRole('button', { name: /Default/ });
    fireEvent.click(trigger);
    expect(document.querySelector('.font-selector-dropdown')).not.toBeNull();
    fireEvent.click(trigger);
    expect(document.querySelector('.font-selector-dropdown')).toBeNull();
  });
});
