import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent, waitFor } from '@testing-library/react';
import AppDialogs, { AppDialogsProps, DialogState } from '../components/AppDialogs';
import * as api from '../api/client';
import { mockGameState, renderWithI18n } from './helpers';

// RecentAuditDrawer fetches the audit log on open via useAuditLog.
vi.mock('../api/client', () => ({
  getAudit: vi.fn(),
}));

const closedDialog: DialogState = {
  open: false,
  title: '',
  initialValue: 0,
  maxValue: 99,
  team: null,
  isSet: false,
};

function makeProps(overrides: Partial<AppDialogsProps> = {}): AppDialogsProps {
  return {
    dialog: closedDialog,
    onDialogSubmit: vi.fn(),
    onDialogClose: vi.fn(),
    resetConfirmOpen: false,
    onResetConfirm: vi.fn(),
    onResetConfirmClose: vi.fn(),
    stalePromptOpen: false,
    onStaleReset: vi.fn(),
    onStaleClose: vi.fn(),
    shareOpen: false,
    shareLinks: null,
    onShareClose: vi.fn(),
    oid: 'test-oid',
    historyOpen: false,
    confirmedState: mockGameState,
    onHistoryClose: vi.fn(),
    coachmarkOpen: false,
    onCoachmarkDismiss: vi.fn(),
    shortcutsHelpOpen: false,
    onShortcutsHelpClose: vi.fn(),
    ...overrides,
  };
}

describe('AppDialogs', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.getAudit).mockResolvedValue({ oid: 'test-oid', count: 0, records: [] });
  });

  it('renders no dialogs when every flag is closed', () => {
    renderWithI18n(<AppDialogs {...makeProps()} />);
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(screen.queryByTestId('recent-audit-drawer')).toBeNull();
    expect(screen.queryByTestId('gesture-coachmark')).toBeNull();
    expect(api.getAudit).not.toHaveBeenCalled();
  });

  it('renders the SetValueDialog and wires submit/close', () => {
    const props = makeProps({
      dialog: { ...closedDialog, open: true, title: 'Set Team 1 score', initialValue: 7 },
    });
    renderWithI18n(<AppDialogs {...props} />);
    expect(screen.getByText('Set Team 1 score')).toBeInTheDocument();

    const input = screen.getByRole('spinbutton');
    fireEvent.change(input, { target: { value: '12' } });
    fireEvent.click(screen.getByRole('button', { name: /OK/ }));
    expect(props.onDialogSubmit).toHaveBeenCalledWith(12);

    fireEvent.click(screen.getByRole('button', { name: /Cancel/ }));
    expect(props.onDialogClose).toHaveBeenCalledOnce();
  });

  it('renders the reset confirm and wires confirm/close', () => {
    const props = makeProps({ resetConfirmOpen: true });
    renderWithI18n(<AppDialogs {...props} />);
    expect(screen.getByText('Reset the match?')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('confirm-dialog-ok'));
    expect(props.onResetConfirm).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByTestId('confirm-dialog-cancel'));
    expect(props.onResetConfirmClose).toHaveBeenCalledOnce();
    expect(props.onStaleReset).not.toHaveBeenCalled();
  });

  it('renders the stale-set prompt and wires reset/continue', () => {
    const props = makeProps({ stalePromptOpen: true });
    renderWithI18n(<AppDialogs {...props} />);
    expect(screen.getByText('Match looks abandoned')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('confirm-dialog-ok'));
    expect(props.onStaleReset).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByTestId('confirm-dialog-cancel'));
    expect(props.onStaleClose).toHaveBeenCalledOnce();
    expect(props.onResetConfirm).not.toHaveBeenCalled();
  });

  it('renders the share dialog with links and wires close', () => {
    const props = makeProps({
      shareOpen: true,
      shareLinks: { control: 'https://example.com/c', overlay: 'https://example.com/o' },
    });
    renderWithI18n(<AppDialogs {...props} />);
    expect(screen.getByText('Links')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Control' })).toHaveAttribute(
      'href',
      'https://example.com/c',
    );
    fireEvent.click(screen.getByRole('button', { name: 'closeClose' }));
    expect(props.onShareClose).toHaveBeenCalledOnce();
  });

  it('falls back to empty share links when links are still null', () => {
    renderWithI18n(<AppDialogs {...makeProps({ shareOpen: true, shareLinks: null })} />);
    expect(screen.getByText('No links available for this session.')).toBeInTheDocument();
  });

  it('opens the audit drawer and fetches the audit log for the oid', async () => {
    renderWithI18n(<AppDialogs {...makeProps({ historyOpen: true })} />);
    expect(screen.getByTestId('recent-audit-drawer')).toBeInTheDocument();
    await waitFor(() => {
      expect(api.getAudit).toHaveBeenCalledWith('test-oid', expect.anything(), expect.anything());
    });
  });

  it('renders the gesture coachmark and wires dismiss', () => {
    const props = makeProps({ coachmarkOpen: true });
    renderWithI18n(<AppDialogs {...props} />);
    expect(screen.getByTestId('gesture-coachmark')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('gesture-coachmark-skip'));
    expect(props.onCoachmarkDismiss).toHaveBeenCalledOnce();
  });

  it('renders the shortcuts help and wires close', () => {
    const props = makeProps({ shortcutsHelpOpen: true });
    renderWithI18n(<AppDialogs {...props} />);
    expect(screen.getByText('Keyboard shortcuts')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'OK' }));
    expect(props.onShortcutsHelpClose).toHaveBeenCalledOnce();
  });
});
