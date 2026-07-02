import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent, waitFor } from '@testing-library/react';
import AdminPage from '../pages/AdminPage';
import * as api from '../api/client';
import { ToastProvider } from '../components/Toast';
import { renderWithI18n } from './helpers';

const refreshMock = vi.fn();
// A single stable ctx object — AdminPage's load effect depends on ``ctx``, so
// a fresh object per render would re-fire the list fetch on every render.
const authCtx = {
  authenticated: true,
  user: { id: 1, username: 'root', role: 'admin' },
  registration_open: true,
  needs_admin_bootstrap: false,
};
vi.mock('../auth/AuthContext', () => ({
  useAuth: () => ({ ctx: authCtx, refresh: refreshMock }),
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

  it('confirms a self-demotion, then refreshes the auth context (not the admin list)', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(api.adminUpdateUser).mockResolvedValue({ ...ROOT, role: 'user' });
    renderWithI18n(<AdminPage />);
    await waitFor(() => expect(screen.getByText('scorer')).toBeInTheDocument());

    const listCallsBefore = vi.mocked(api.adminListUsers).mock.calls.length;
    // root's own row is locked only when root is the last admin — with
    // OTHER_ADMIN present the demote button is active.
    fireEvent.click(screen.getAllByRole('button', { name: 'Make user' })[0]!);
    await waitFor(() => {
      expect(api.adminUpdateUser).toHaveBeenCalledWith(1, { role: 'user' });
      expect(refreshMock).toHaveBeenCalled();
    });
    expect(confirmSpy).toHaveBeenCalledWith(expect.stringMatching(/admin page/i));
    // The now-forbidden /admin/users reload must not have been retried.
    expect(vi.mocked(api.adminListUsers).mock.calls.length).toBe(listCallsBefore);
    confirmSpy.mockRestore();
  });

  it('a declined self-demotion confirm changes nothing', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    renderWithI18n(<AdminPage />);
    await waitFor(() => expect(screen.getByText('scorer')).toBeInTheDocument());

    fireEvent.click(screen.getAllByRole('button', { name: 'Make user' })[0]!);
    await waitFor(() => expect(confirmSpy).toHaveBeenCalled());
    expect(api.adminUpdateUser).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it('demoting another admin needs no confirm', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm');
    vi.mocked(api.adminUpdateUser).mockResolvedValue({ ...OTHER_ADMIN, role: 'user' });
    renderWithI18n(<AdminPage />);
    await waitFor(() => expect(screen.getByText('scorer')).toBeInTheDocument());

    fireEvent.click(screen.getAllByRole('button', { name: 'Make user' })[1]!);
    await waitFor(() => {
      expect(api.adminUpdateUser).toHaveBeenCalledWith(2, { role: 'user' });
    });
    expect(confirmSpy).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
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

  it('opening registration asks for confirmation and toasts on success', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);
    vi.mocked(api.adminGetRegistration).mockResolvedValue({ registration_open: false });
    vi.mocked(api.adminSetRegistration).mockResolvedValue({ registration_open: true });
    renderWithI18n(<ToastProvider><AdminPage /></ToastProvider>);
    await waitFor(() => expect(screen.getByText('scorer')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: 'Open registration' }));
    await waitFor(() => {
      expect(api.adminSetRegistration).toHaveBeenCalledWith(true);
    });
    expect(confirmSpy).toHaveBeenCalledWith(expect.stringMatching(/create an account/i));
    await waitFor(() => {
      expect(screen.getByText('Public registration is now open.')).toBeInTheDocument();
    });
    confirmSpy.mockRestore();
  });

  it('declining the open-registration confirm changes nothing', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    vi.mocked(api.adminGetRegistration).mockResolvedValue({ registration_open: false });
    renderWithI18n(<AdminPage />);
    await waitFor(() => expect(screen.getByText('scorer')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: 'Open registration' }));
    await waitFor(() => expect(confirmSpy).toHaveBeenCalled());
    expect(api.adminSetRegistration).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it('closing registration skips the confirm and toasts', async () => {
    const confirmSpy = vi.spyOn(window, 'confirm');
    vi.mocked(api.adminSetRegistration).mockResolvedValue({ registration_open: false });
    renderWithI18n(<ToastProvider><AdminPage /></ToastProvider>);
    await waitFor(() => expect(screen.getByText('scorer')).toBeInTheDocument());

    fireEvent.click(screen.getByRole('button', { name: 'Close registration' }));
    await waitFor(() => {
      expect(api.adminSetRegistration).toHaveBeenCalledWith(false);
    });
    expect(confirmSpy).not.toHaveBeenCalled();
    await waitFor(() => {
      expect(screen.getByText('Public registration is now closed.')).toBeInTheDocument();
    });
    confirmSpy.mockRestore();
  });
});
