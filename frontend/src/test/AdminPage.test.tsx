import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent, waitFor } from '@testing-library/react';
import AdminPage from '../pages/AdminPage';
import * as api from '../api/client';
import { renderWithI18n } from './helpers';

vi.mock('../auth/AuthContext', () => ({
  useAuth: () => ({
    ctx: {
      authenticated: true,
      user: { id: 1, username: 'root', role: 'admin' },
      registration_open: true,
      needs_admin_bootstrap: false,
    },
    refresh: vi.fn(),
  }),
}));

vi.mock('../api/client', () => {
  class ApiError extends Error {
    status: number;
    detail: string;
    constructor(status: number, message: string, detail?: string) {
      super(message);
      this.status = status;
      this.detail = detail || message;
    }
  }
  return {
    ApiError,
    adminListUsers: vi.fn(),
    adminCreateUser: vi.fn(),
    adminResetPassword: vi.fn(),
    adminUpdateUser: vi.fn(),
    adminDeleteUser: vi.fn(),
    adminGetRegistration: vi.fn(),
    adminSetRegistration: vi.fn(),
  };
});

const ROOT: api.UserOut = {
  id: 1, username: 'root', role: 'admin', is_active: true,
  must_change_password: false, display_name: null, email: null,
} as unknown as api.UserOut;
const OTHER_ADMIN: api.UserOut = {
  id: 2, username: 'backup', role: 'admin', is_active: true,
  must_change_password: false, display_name: null, email: null,
} as unknown as api.UserOut;
const PLAIN: api.UserOut = {
  id: 3, username: 'scorer', role: 'user', is_active: true,
  must_change_password: false, display_name: null, email: null,
} as unknown as api.UserOut;

describe('AdminPage user management', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.adminListUsers).mockResolvedValue([ROOT, OTHER_ADMIN, PLAIN]);
    vi.mocked(api.adminGetRegistration).mockResolvedValue({ registration_open: true });
  });

  it('promotes a user to admin from the row action', async () => {
    vi.mocked(api.adminUpdateUser).mockResolvedValue({ ...PLAIN, role: 'admin' });
    renderWithI18n(<AdminPage />);
    await waitFor(() => expect(screen.getByText('scorer')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: 'Make admin' }));
    await waitFor(() => {
      expect(api.adminUpdateUser).toHaveBeenCalledWith(3, { role: 'admin' });
    });
  });

  it('demotes another admin and disables the toggle for the last admin', async () => {
    vi.mocked(api.adminListUsers).mockResolvedValue([ROOT, PLAIN]);
    renderWithI18n(<AdminPage />);
    await waitFor(() => expect(screen.getByText('scorer')).toBeInTheDocument());

    // root is the only active admin — its demote control is locked.
    const demoteButtons = screen.getAllByRole('button', { name: 'Make user' });
    expect(demoteButtons).toHaveLength(1);
    expect(demoteButtons[0]).toBeDisabled();
  });

  it('refreshes the list after a password reset so the pill can appear', async () => {
    vi.mocked(api.adminResetPassword).mockResolvedValue({
      user: { ...PLAIN, must_change_password: true },
      temp_password: 'temp-1234',
    });
    renderWithI18n(<AdminPage />);
    await waitFor(() => expect(screen.getByText('scorer')).toBeInTheDocument());

    vi.mocked(api.adminListUsers).mockResolvedValue([
      ROOT, OTHER_ADMIN, { ...PLAIN, must_change_password: true },
    ]);
    fireEvent.click(screen.getAllByRole('button', { name: 'Reset pw' })[2]!);
    // The pill can only appear because resetPw reloaded the user list.
    await waitFor(() => {
      expect(screen.getByText('must change pw')).toBeInTheDocument();
    });
  });

  it('warns about self sign-out when deleting your own account', async () => {
    // Outside a ConfirmProvider the hook falls back to window.confirm — spy
    // on it to capture the message shown for the owner's own row.
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    renderWithI18n(<AdminPage />);
    await waitFor(() => expect(screen.getByText('scorer')).toBeInTheDocument());

    fireEvent.click(screen.getAllByRole('button', { name: 'Delete' })[0]!);
    await waitFor(() => {
      expect(confirmSpy).toHaveBeenCalledWith(expect.stringMatching(/your own account/i));
    });
    expect(api.adminDeleteUser).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });
});
