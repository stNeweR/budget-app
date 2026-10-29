export type Category =
  | 'еда'
  | 'транспорт'
  | 'жильё'
  | 'развлечения'
  | 'здоровье'
  | 'покупки'
  | 'другое';

export const CATEGORIES: Category[] = [
  'еда',
  'транспорт',
  'жильё',
  'развлечения',
  'здоровье',
  'покупки',
  'другое',
];

export interface User {
  id: string;
  email: string | null;
  full_name: string;
  tg_username: string;
  telegram_id: number | null;
  has_password: boolean;
}

export interface Family {
  id: string;
  name: string;
  invite_code: string;
}

export interface FamilyMember {
  id: string;
  full_name: string;
  tg_username: string;
  telegram_id: number | null;
  role: 'head' | 'member';
}

export interface Expense {
  id: string;
  user_id: string;
  amount: number;
  category: Category;
  spent_at: string;
  comment: string;
  created_at: string;
  updated_at: string;
}

export interface ExpenseDraft {
  user_id: string;
  amount: number;
  category: Category;
  spent_at: string;
  comment: string;
}

export interface ExpensePatch {
  amount?: number;
  category?: Category;
  spent_at?: string;
  comment?: string;
}

export interface ExpenseFilter {
  user_id?: string;
  from?: string;
  to?: string;
  category?: Category;
}

export interface AuthPayload {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: User;
  family: Family;
}

export interface Me {
  user: User;
  family: Family;
  has_password: boolean;
}
