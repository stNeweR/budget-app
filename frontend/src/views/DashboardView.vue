<script setup lang="ts">
import { onMounted, ref, watch } from 'vue';
import { RouterLink, useRouter } from 'vue-router';
import FilterBar from '../components/FilterBar.vue';
import ExpenseTable from '../components/ExpenseTable.vue';
import ExpenseFormModal from '../components/ExpenseFormModal.vue';
import { api, ApiError } from '../api/client';
import { auth, clearSession, logout } from '../auth';
import type { Expense, ExpenseDraft, ExpenseFilter, FamilyMember } from '../types';

const router = useRouter();

const users = ref<FamilyMember[]>([]);
const expenses = ref<Expense[]>([]);
const filter = ref<ExpenseFilter>({});
const loading = ref(false);
const error = ref('');
const modalOpen = ref(false);
const editing = ref<Expense | null>(null);
const copied = ref(false);

async function loadUsers() {
  try {
    users.value = await api.listUsers();
  } catch (err) {
    handleError(err);
  }
}

async function loadExpenses() {
  loading.value = true;
  error.value = '';
  try {
    expenses.value = await api.listExpenses(filter.value);
  } catch (err) {
    handleError(err);
  } finally {
    loading.value = false;
  }
}

function handleError(err: unknown) {
  if (err instanceof ApiError && err.status === 401) {
    clearSession();
    void router.replace('/login');
    return;
  }
  error.value = err instanceof Error ? err.message : String(err);
}

function openCreate() {
  editing.value = null;
  modalOpen.value = true;
}

function openEdit(expense: Expense) {
  editing.value = expense;
  modalOpen.value = true;
}

async function save(payload: { id?: string; draft: ExpenseDraft }) {
  error.value = '';
  try {
    if (payload.id) {
      await api.updateExpense(payload.id, {
        amount: payload.draft.amount,
        category: payload.draft.category,
        spent_at: payload.draft.spent_at,
        comment: payload.draft.comment,
      });
    } else {
      await api.createExpense(payload.draft);
    }
    modalOpen.value = false;
    editing.value = null;
    await loadExpenses();
  } catch (err) {
    handleError(err);
  }
}

async function remove(expense: Expense) {
  if (!window.confirm(`Удалить трату на ${expense.amount} ₽?`)) return;
  error.value = '';
  try {
    await api.deleteExpense(expense.id);
    await loadExpenses();
  } catch (err) {
    handleError(err);
  }
}

async function copyInviteCode() {
  const value = auth.family?.invite_code;
  if (!value) return;
  try {
    await navigator.clipboard.writeText(value);
    copied.value = true;
    window.setTimeout(() => (copied.value = false), 1500);
  } catch {
    error.value = 'Не удалось скопировать код';
  }
}

async function signOut() {
  await logout();
  await router.replace('/login');
}

watch(filter, loadExpenses, { deep: true });

onMounted(async () => {
  await Promise.all([loadUsers(), loadExpenses()]);
});
</script>

<template>
  <div class="mx-auto max-w-6xl px-4 py-8 sm:px-6">
    <header class="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 class="text-2xl font-semibold tracking-tight text-slate-900">Семейный бюджет</h1>
        <p class="mt-1 text-sm text-slate-500">
          {{ auth.family?.name }} · траты всех членов семьи
        </p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <button
          class="rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition-colors hover:bg-blue-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2"
          type="button"
          @click="openCreate"
        >
          Добавить трату
        </button>
        <button
          class="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-600 shadow-sm transition-colors hover:bg-slate-50"
          type="button"
          @click="signOut"
        >
          Выйти
        </button>
      </div>
    </header>

    <section class="mb-4 flex flex-wrap items-center gap-x-6 gap-y-2 rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm shadow-sm">
      <div class="flex items-center gap-2">
        <span class="text-slate-500">Код приглашения:</span>
        <code class="rounded bg-slate-100 px-2 py-0.5 font-mono text-slate-800">
          {{ auth.family?.invite_code }}
        </code>
        <button
          class="rounded-md px-2 py-1 text-xs font-medium text-blue-600 transition-colors hover:bg-blue-50"
          type="button"
          @click="copyInviteCode"
        >
          {{ copied ? 'Скопировано' : 'Скопировать' }}
        </button>
      </div>
      <div class="ml-auto flex items-center gap-3 text-xs text-slate-400">
        <span>{{ auth.user?.full_name || auth.user?.tg_username }}</span>
        <RouterLink class="hover:text-slate-600" to="/setup-password">
          {{ auth.user?.has_password ? 'Сменить пароль' : 'Задать пароль' }}
        </RouterLink>
      </div>
    </section>

    <section class="mb-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <FilterBar v-model="filter" :users="users" />
    </section>

    <p
      v-if="error"
      class="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
    >
      {{ error }}
    </p>

    <section class="rounded-xl border border-slate-200 bg-white shadow-sm">
      <p v-if="loading" class="px-4 py-12 text-center text-sm text-slate-500">Загрузка…</p>
      <ExpenseTable
        v-else
        :expenses="expenses"
        :users="users"
        @edit="openEdit"
        @delete="remove"
      />
    </section>

    <ExpenseFormModal
      :open="modalOpen"
      :users="users"
      :expense="editing"
      @close="modalOpen = false"
      @save="save"
    />
  </div>
</template>
