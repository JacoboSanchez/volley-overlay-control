/** Account authentication surface — ``/api/v1/auth/*``. */

import { request } from './http';

export interface UserOut {
  id: number;
  storage_namespace: string;
  username: string;
  display_name: string | null;
  email: string | null;
  role: 'admin' | 'user';
  is_active: boolean;
  must_change_password: boolean;
}

export interface AuthContext {
  authenticated: boolean;
  user: UserOut | null;
  registration_open: boolean;
  needs_admin_bootstrap: boolean;
}

export function getAuthContext(): Promise<AuthContext> {
  return request<AuthContext>('GET', '/auth/context');
}

export function login(
  username: string,
  password: string,
): Promise<{ user: UserOut; must_change_password: boolean }> {
  return request('POST', '/auth/login', { username, password });
}

export function registerAccount(
  username: string,
  password: string,
  display_name?: string,
  email?: string,
): Promise<{ user: UserOut }> {
  return request('POST', '/auth/register', { username, password, display_name, email });
}

export function claimAdmin(
  token: string,
  username: string,
  password: string,
): Promise<{ user: UserOut }> {
  return request('POST', '/auth/claim-admin', { token, username, password });
}

export function logout(): Promise<{ ok: boolean }> {
  return request('POST', '/auth/logout', {});
}

export function changePassword(current_password: string, new_password: string): Promise<UserOut> {
  return request('POST', '/auth/change-password', { current_password, new_password });
}

export function updateMe(data: { display_name?: string; email?: string }): Promise<UserOut> {
  return request('PATCH', '/auth/me', data);
}

export function deleteMe(): Promise<{ ok: boolean }> {
  return request('DELETE', '/auth/me');
}
