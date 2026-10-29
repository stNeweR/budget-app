import type {
  AuthPayload,
  Expense,
  ExpenseDraft,
  ExpenseFilter,
  ExpensePatch,
  Family,
  FamilyMember,
  Me,
  User,
} from '../types';

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

let accessToken: string | null = null;
let refreshPromise: Promise<AuthPayload | null> | null = null;

export function setAccessToken(token: string | null) {
  accessToken = token;
}

async function doRefresh(): Promise<AuthPayload | null> {
  try {
    const response = await fetch('/api/auth/refresh', {
      method: 'POST',
      credentials: 'include',
    });
    if (!response.ok) {
      accessToken = null;
      return null;
    }
    const payload = (await response.json()) as AuthPayload;
    accessToken = payload.access_token;
    return payload;
  } catch {
    accessToken = null;
    return null;
  }
}

export function refreshSession(): Promise<AuthPayload | null> {
  if (!refreshPromise) {
    refreshPromise = doRefresh().finally(() => {
      refreshPromise = null;
    });
  }
  return refreshPromise;
}

async function parseError(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { error?: string };
    if (body.error) return body.error;
  } catch {
    // ignore malformed error bodies
  }
  return `HTTP ${response.status}`;
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  retry = true,
): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  if (accessToken) {
    headers.set('Authorization', `Bearer ${accessToken}`);
  }

  const response = await fetch(`/api${path}`, {
    ...init,
    headers,
    credentials: 'include',
  });

  if (response.status === 401 && retry && !path.startsWith('/auth/')) {
    const session = await refreshSession();
    if (session) {
      return request<T>(path, init, false);
    }
  }

  if (!response.ok) {
    throw new ApiError(response.status, await parseError(response));
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export const api = {
  codeLogin(code: string): Promise<AuthPayload> {
    return request<AuthPayload>('/auth/code-login', {
      method: 'POST',
      body: JSON.stringify({ code }),
    });
  },

  login(email: string, password: string): Promise<AuthPayload> {
    return request<AuthPayload>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    });
  },

  logout(): Promise<void> {
    return request<void>('/auth/logout', { method: 'POST' });
  },

  me(): Promise<Me> {
    return request<Me>('/auth/me');
  },

  setPassword(payload: {
    email: string;
    password: string;
    current_password?: string;
  }): Promise<User> {
    return request<User>('/auth/password', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  },

  family(): Promise<{ family: Family; members: FamilyMember[] }> {
    return request<{ family: Family; members: FamilyMember[] }>('/family');
  },

  listUsers(): Promise<FamilyMember[]> {
    return request<FamilyMember[]>('/users');
  },

  listExpenses(filter: ExpenseFilter): Promise<Expense[]> {
    const params = new URLSearchParams();
    if (filter.user_id !== undefined) params.set('user_id', filter.user_id);
    if (filter.from) params.set('from', filter.from);
    if (filter.to) params.set('to', filter.to);
    if (filter.category) params.set('category', filter.category);
    params.set('limit', '500');
    const query = params.toString();
    return request<Expense[]>(`/expenses${query ? `?${query}` : ''}`);
  },

  createExpense(draft: ExpenseDraft): Promise<Expense> {
    return request<Expense>('/expenses', {
      method: 'POST',
      body: JSON.stringify(draft),
    });
  },

  updateExpense(id: string, patch: ExpensePatch): Promise<Expense> {
    return request<Expense>(`/expenses/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(patch),
    });
  },

  deleteExpense(id: string): Promise<void> {
    return request<void>(`/expenses/${id}`, { method: 'DELETE' });
  },
};
