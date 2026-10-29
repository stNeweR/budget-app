import { reactive } from 'vue';
import { api, refreshSession, setAccessToken } from './api/client';
import type { Family, User } from './types';

interface AuthState {
  user: User | null;
  family: Family | null;
  ready: boolean;
}

export const auth = reactive<AuthState>({
  user: null,
  family: null,
  ready: false,
});

function apply(payload: { user: User; family: Family }) {
  auth.user = payload.user;
  auth.family = payload.family;
}

export async function restoreSession(): Promise<void> {
  if (auth.ready) return;
  const session = await refreshSession();
  if (session) {
    setAccessToken(session.access_token);
    apply(session);
  }
  auth.ready = true;
}

export async function loginWithCode(code: string): Promise<void> {
  const payload = await api.codeLogin(code);
  setAccessToken(payload.access_token);
  apply(payload);
  auth.ready = true;
}

export async function loginWithPassword(email: string, password: string): Promise<void> {
  const payload = await api.login(email, password);
  setAccessToken(payload.access_token);
  apply(payload);
  auth.ready = true;
}

export async function changePassword(payload: {
  email: string;
  password: string;
  current_password?: string;
}): Promise<void> {
  const user = await api.setPassword(payload);
  auth.user = user;
}

export function clearSession(): void {
  setAccessToken(null);
  auth.user = null;
  auth.family = null;
  auth.ready = true;
}

export async function logout(): Promise<void> {
  try {
    await api.logout();
  } finally {
    clearSession();
  }
}
