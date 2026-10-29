<script setup lang="ts">
import { reactive, ref } from 'vue';
import { useRouter } from 'vue-router';
import { auth, changePassword, logout } from '../auth';

const router = useRouter();

const form = reactive({
  email: auth.user?.email ?? '',
  password: '',
  confirm: '',
  currentPassword: '',
});

const loading = ref(false);
const error = ref('');
const changing = Boolean(auth.user?.has_password);

async function submit() {
  error.value = '';
  if (form.password.length < 8) {
    error.value = 'Пароль должен содержать не менее 8 символов';
    return;
  }
  if (form.password !== form.confirm) {
    error.value = 'Пароли не совпадают';
    return;
  }
  loading.value = true;
  try {
    await changePassword({
      email: form.email.trim(),
      password: form.password,
      current_password: changing ? form.currentPassword : undefined,
    });
    await router.replace('/');
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

async function signOut() {
  await logout();
  await router.replace('/login');
}
</script>

<template>
  <div class="flex min-h-screen items-center justify-center px-4 py-10">
    <div class="w-full max-w-md">
      <div class="mb-6 text-center">
        <h1 class="text-2xl font-semibold tracking-tight text-slate-900">
          {{ changing ? 'Смена пароля' : 'Задайте пароль' }}
        </h1>
        <p class="mt-2 text-sm text-slate-500">
          {{
            changing
              ? 'После смены пароля вход по одноразовым кодам продолжит работать.'
              : 'Вы вошли по одноразовому коду. Задайте email и пароль, чтобы входить без ссылки из бота.'
          }}
        </p>
      </div>

      <div class="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <p
          v-if="error"
          class="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
        >
          {{ error }}
        </p>

        <form class="grid gap-4" @submit.prevent="submit">
          <label class="flex flex-col gap-1.5 text-sm font-medium text-slate-600">
            <span>Email</span>
            <input
              v-model="form.email"
              class="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/30"
              type="email"
              autocomplete="email"
              required
            />
          </label>

          <label
            v-if="changing"
            class="flex flex-col gap-1.5 text-sm font-medium text-slate-600"
          >
            <span>Текущий пароль</span>
            <input
              v-model="form.currentPassword"
              class="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/30"
              type="password"
              autocomplete="current-password"
              required
            />
          </label>

          <label class="flex flex-col gap-1.5 text-sm font-medium text-slate-600">
            <span>Новый пароль</span>
            <input
              v-model="form.password"
              class="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/30"
              type="password"
              autocomplete="new-password"
              minlength="8"
              required
            />
          </label>

          <label class="flex flex-col gap-1.5 text-sm font-medium text-slate-600">
            <span>Повторите пароль</span>
            <input
              v-model="form.confirm"
              class="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/30"
              type="password"
              autocomplete="new-password"
              minlength="8"
              required
            />
          </label>

          <button
            class="rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
            type="submit"
            :disabled="loading"
          >
            {{ loading ? 'Сохраняем…' : changing ? 'Сменить пароль' : 'Сохранить и продолжить' }}
          </button>
        </form>

        <div class="mt-4 flex justify-between text-xs text-slate-400">
          <button class="hover:text-slate-600" type="button" @click="signOut">
            Выйти
          </button>
          <RouterLink v-if="changing" class="hover:text-slate-600" to="/">
            Вернуться к тратам
          </RouterLink>
        </div>
      </div>
    </div>
  </div>
</template>
