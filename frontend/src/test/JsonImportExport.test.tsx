import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { screen, fireEvent, waitFor } from '@testing-library/react';
import JsonImportExport from '../pages/JsonImportExport';
import * as api from '../api/client';
import { renderWithI18n } from './helpers';

vi.mock('../api/client', () => ({
  ApiError: class ApiError extends Error {
    status: number;
    detail: string;
    constructor(status: number, message: string, detail?: string) {
      super(message);
      this.status = status;
      this.detail = detail || message;
    }
  },
}));

function setup(overrides: Partial<{ exportFn: () => Promise<never>; importFn: () => Promise<never> }> = {}) {
  const exportFn = vi.fn().mockResolvedValue({ Lions: { color: '#112233' } });
  const importFn = vi.fn().mockResolvedValue({ imported: 1 });
  const onImported = vi.fn();
  renderWithI18n(
    <JsonImportExport
      label="Teams"
      exportFn={(overrides.exportFn as never) ?? exportFn}
      importFn={(overrides.importFn as never) ?? importFn}
      onImported={onImported}
    />,
  );
  // The panel is collapsed behind a disclosure toggle.
  fireEvent.click(screen.getByText(/Teams/));
  return { exportFn, importFn, onImported };
}

describe('JsonImportExport', () => {
  let confirmSpy: ReturnType<typeof vi.spyOn>;
  beforeEach(() => {
    confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
  });
  afterEach(() => {
    confirmSpy.mockRestore();
  });

  it('export fills the textarea with pretty JSON', async () => {
    const { exportFn } = setup();
    fireEvent.click(screen.getByText('Export'));
    await waitFor(() => expect(exportFn).toHaveBeenCalled());
    const textarea = screen.getByPlaceholderText('{"Name": { … }}') as HTMLTextAreaElement;
    await waitFor(() => expect(textarea.value).toContain('"Lions"'));
  });

  it('surfaces the ApiError detail when import fails server-side', async () => {
    const importFn = vi
      .fn()
      .mockRejectedValue(new api.ApiError(400, 'API POST failed', 'Bad team colour "#zzz".'));
    setup({ importFn: importFn as never });
    const textarea = screen.getByPlaceholderText('{"Name": { … }}');
    fireEvent.change(textarea, { target: { value: '{"Lions": {}}' } });
    fireEvent.click(screen.getByText('Import'));
    await waitFor(() => {
      expect(screen.getByText('Bad team colour "#zzz".')).toBeInTheDocument();
    });
  });

  it('rejects malformed JSON before calling the API', async () => {
    const { importFn } = setup();
    const textarea = screen.getByPlaceholderText('{"Name": { … }}');
    fireEvent.change(textarea, { target: { value: '{oops' } });
    fireEvent.click(screen.getByText('Import'));
    await waitFor(() => {
      expect(screen.getByText('That is not valid JSON.')).toBeInTheDocument();
    });
    expect(importFn).not.toHaveBeenCalled();
  });

  it('replace-import asks for confirmation and cancel aborts', async () => {
    confirmSpy.mockReturnValue(false);
    const { importFn } = setup();
    const textarea = screen.getByPlaceholderText('{"Name": { … }}');
    fireEvent.change(textarea, { target: { value: '{"Lions": {}}' } });
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByText('Import'));
    await waitFor(() => expect(confirmSpy).toHaveBeenCalled());
    expect(importFn).not.toHaveBeenCalled();
  });

  it('replace-import proceeds after confirmation', async () => {
    const { importFn, onImported } = setup();
    const textarea = screen.getByPlaceholderText('{"Name": { … }}');
    fireEvent.change(textarea, { target: { value: '{"Lions": {}}' } });
    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByText('Import'));
    await waitFor(() => expect(importFn).toHaveBeenCalledWith({ Lions: {} }, true));
    await waitFor(() => expect(onImported).toHaveBeenCalled());
  });

  it('plain (non-replace) import never asks for confirmation', async () => {
    const { importFn } = setup();
    const textarea = screen.getByPlaceholderText('{"Name": { … }}');
    fireEvent.change(textarea, { target: { value: '{"Lions": {}}' } });
    fireEvent.click(screen.getByText('Import'));
    await waitFor(() => expect(importFn).toHaveBeenCalledWith({ Lions: {} }, false));
    expect(confirmSpy).not.toHaveBeenCalled();
  });

  it('loading a file fills the textarea for the normal import path', async () => {
    setup();
    const file = new File(['{"FromFile": {}}'], 'teams.json', { type: 'application/json' });
    fireEvent.change(screen.getByTestId('json-file-input'), { target: { files: [file] } });
    const textarea = screen.getByPlaceholderText('{"Name": { … }}') as HTMLTextAreaElement;
    await waitFor(() => expect(textarea.value).toBe('{"FromFile": {}}'));
  });
});
