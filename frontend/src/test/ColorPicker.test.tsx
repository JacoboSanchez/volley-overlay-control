import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import ColorPicker from '../components/ColorPicker';
import { renderWithI18n } from './helpers';

vi.mock('react-colorful', () => ({
  HexColorPicker: ({ color, onChange }: { color: string; onChange: (c: string) => void }) => (
    <div data-testid="hex-color-picker" data-color={color} onClick={() => onChange('#ff0000')}>
      MockPicker
    </div>
  ),
}));

describe('ColorPicker', () => {
  const onChange = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('renders swatch button with correct background color', () => {
    renderWithI18n(<ColorPicker color="#0000ff" onChange={onChange} data-testid="picker" />);
    const swatch = screen.getByTestId('picker');
    expect(swatch.style.backgroundColor).toBe('rgb(0, 0, 255)');
  });

  it('defaults to #000000 when color is not provided', () => {
    renderWithI18n(<ColorPicker onChange={onChange} data-testid="picker" />);
    const swatch = screen.getByTestId('picker');
    expect(swatch.style.backgroundColor).toBe('rgb(0, 0, 0)');
  });

  it('opens popover on swatch click', () => {
    renderWithI18n(<ColorPicker color="#0000ff" onChange={onChange} data-testid="picker" />);
    expect(screen.queryByTestId('hex-color-picker')).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId('picker'));
    expect(screen.getByTestId('hex-color-picker')).toBeInTheDocument();
  });

  it('closes popover on second swatch click', () => {
    renderWithI18n(<ColorPicker color="#0000ff" onChange={onChange} data-testid="picker" />);
    fireEvent.click(screen.getByTestId('picker'));
    expect(screen.getByTestId('hex-color-picker')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('picker'));
    expect(screen.queryByTestId('hex-color-picker')).not.toBeInTheDocument();
  });

  it('calls onChange when picker color changes', () => {
    renderWithI18n(<ColorPicker color="#0000ff" onChange={onChange} data-testid="picker" />);
    fireEvent.click(screen.getByTestId('picker'));
    fireEvent.click(screen.getByTestId('hex-color-picker'));
    expect(onChange).toHaveBeenCalledWith('#ff0000');
  });

  it('shows hex input with current color value', () => {
    renderWithI18n(<ColorPicker color="#abcdef" onChange={onChange} data-testid="picker" />);
    fireEvent.click(screen.getByTestId('picker'));
    const input = screen.getByTestId('picker-hex') as HTMLInputElement;
    expect(input.value).toBe('#abcdef');
  });

  it('calls onChange on valid hex input', () => {
    renderWithI18n(<ColorPicker color="#000000" onChange={onChange} data-testid="picker" />);
    fireEvent.click(screen.getByTestId('picker'));
    const input = screen.getByTestId('picker-hex');
    fireEvent.change(input, { target: { value: '#ff00ff' } });
    expect(onChange).toHaveBeenCalledWith('#ff00ff');
  });

  it('does not call onChange on invalid hex input', () => {
    renderWithI18n(<ColorPicker color="#000000" onChange={onChange} data-testid="picker" />);
    fireEvent.click(screen.getByTestId('picker'));
    const input = screen.getByTestId('picker-hex');
    fireEvent.change(input, { target: { value: '#gggggg' } });
    expect(onChange).not.toHaveBeenCalled();
  });

  it('accepts 3-digit hex values', () => {
    renderWithI18n(<ColorPicker color="#000000" onChange={onChange} data-testid="picker" />);
    fireEvent.click(screen.getByTestId('picker'));
    const input = screen.getByTestId('picker-hex');
    fireEvent.change(input, { target: { value: '#f0f' } });
    expect(onChange).toHaveBeenCalledWith('#f0f');
  });

  it('has correct aria-label on swatch button', () => {
    renderWithI18n(<ColorPicker color="#000" onChange={onChange} data-testid="picker" />);
    expect(screen.getByLabelText('Pick color')).toBeInTheDocument();
  });

  it('closes popover on outside pointerdown', () => {
    renderWithI18n(<ColorPicker color="#000" onChange={onChange} data-testid="picker" />);
    fireEvent.click(screen.getByTestId('picker'));
    expect(screen.getByTestId('hex-color-picker')).toBeInTheDocument();
    // Simulate outside click
    fireEvent.pointerDown(document.body);
    expect(screen.queryByTestId('hex-color-picker')).not.toBeInTheDocument();
  });

  // --- Preset colors ---

  it('shows preset color swatches when popover is open', () => {
    renderWithI18n(<ColorPicker color="#000" onChange={onChange} data-testid="picker" />);
    fireEvent.click(screen.getByTestId('picker'));
    expect(screen.getByTestId('picker-presets')).toBeInTheDocument();
    // Should have 12 preset buttons
    const presets = screen.getByTestId('picker-presets').querySelectorAll('button');
    expect(presets.length).toBe(12);
  });

  it('calls onChange when a preset color is clicked', () => {
    renderWithI18n(<ColorPicker color="#000000" onChange={onChange} data-testid="picker" />);
    fireEvent.click(screen.getByTestId('picker'));
    const presetBtn = screen.getByLabelText('#d32f2f');
    fireEvent.click(presetBtn);
    expect(onChange).toHaveBeenCalledWith('#d32f2f');
  });

  it('highlights the active preset swatch', () => {
    renderWithI18n(<ColorPicker color="#d32f2f" onChange={onChange} data-testid="picker" />);
    fireEvent.click(screen.getByTestId('picker'));
    const presetBtn = screen.getByLabelText('#d32f2f');
    expect(presetBtn.className).toContain('active');
  });

  // --- Recent colors ---

  it('does not show recent section when no recent colors exist', () => {
    renderWithI18n(<ColorPicker color="#000" onChange={onChange} data-testid="picker" />);
    fireEvent.click(screen.getByTestId('picker'));
    expect(screen.queryByTestId('picker-recent')).not.toBeInTheDocument();
  });

  it('shows recent colors from localStorage', () => {
    localStorage.setItem('volley_recentColors', JSON.stringify(['#abcdef', '#123456']));
    renderWithI18n(<ColorPicker color="#000" onChange={onChange} data-testid="picker" />);
    fireEvent.click(screen.getByTestId('picker'));
    expect(screen.getByTestId('picker-recent')).toBeInTheDocument();
    const recentBtns = screen.getByTestId('picker-recent').querySelectorAll('button');
    expect(recentBtns.length).toBe(2);
  });

  it('saves picked color to recent colors in localStorage', () => {
    renderWithI18n(<ColorPicker color="#000000" onChange={onChange} data-testid="picker" />);
    fireEvent.click(screen.getByTestId('picker'));
    // Click a preset
    fireEvent.click(screen.getByLabelText('#d32f2f'));
    const stored = JSON.parse(localStorage.getItem('volley_recentColors')!);
    expect(stored).toContain('#d32f2f');
  });

  it('saves hex input to recent colors only on blur', () => {
    renderWithI18n(<ColorPicker color="#000000" onChange={onChange} data-testid="picker" />);
    fireEvent.click(screen.getByTestId('picker'));
    const input = screen.getByTestId('picker-hex');
    fireEvent.change(input, { target: { value: '#aabbcc' } });
    // Not saved yet while still typing
    expect(localStorage.getItem('volley_recentColors')).toBeNull();
    // Saved on blur
    fireEvent.blur(input);
    const stored = JSON.parse(localStorage.getItem('volley_recentColors')!);
    expect(stored).toContain('#aabbcc');
  });

  it('does not save invalid hex to recent colors on blur', () => {
    renderWithI18n(<ColorPicker color="#000000" onChange={onChange} data-testid="picker" />);
    fireEvent.click(screen.getByTestId('picker'));
    const input = screen.getByTestId('picker-hex');
    fireEvent.change(input, { target: { value: '#gg' } });
    fireEvent.blur(input);
    expect(localStorage.getItem('volley_recentColors')).toBeNull();
  });

  it('deduplicates recent colors and keeps most recent first', () => {
    localStorage.setItem('volley_recentColors', JSON.stringify(['#111111', '#222222']));
    renderWithI18n(<ColorPicker color="#000000" onChange={onChange} data-testid="picker" />);
    fireEvent.click(screen.getByTestId('picker'));
    // Pick #222222 again via preset-style click
    fireEvent.click(screen.getByLabelText('#222222'));
    const stored = JSON.parse(localStorage.getItem('volley_recentColors')!);
    expect(stored[0]).toBe('#222222');
    // No duplicate
    expect(stored.filter((c: string) => c === '#222222').length).toBe(1);
  });
});
