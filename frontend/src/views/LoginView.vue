<script setup lang="ts">
import { onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { auth, loginWithCode, loginWithPassword } from '../auth';

const route = useRoute();
const router = useRouter();

const tab = ref<'code' | 'password'>('code');
const code = ref(typeof route.query.code === 'string' ? route.query.code : '');
const email = ref('');
const password = ref('');
const loading = ref(false);
const error = ref('');
const autoLogin = ref(Boolean(code.value));

async function finish() {
  const next = typeof route.query.next === 'string' ? route.query.next : '/';
  await router.replace(auth.user?.has_password ? next : '/setup-password');
}

async function submitCode() {
  if (!code.value.trim()) return;
  loading.value = true;
  error.value = '';
  try {
    await loginWithCode(code.value.trim());
    await finish();
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

async function submitPassword() {
  if (!email.value.trim() || !password.value) return;
  loading.value = true;
  error.value = '';
  try {
    await loginWithPassword(email.value.trim(), password.value);
    await finish();
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  if (autoLogin.value) {
    autoLogin.value = false;
    void submitCode();
  }
});
</script>

<template>
  <div class="flex min-h-screen items-center justify-center px-4 py-10">
    <div class="w-full max-w-md">
      <div class="mb-6 text-center">
        <h1 class="text-2xl font-semibold tracking-tight text-slate-900">Семейный бюджет</h1>
        <p class="mt-2 text-sm text-slate-500">
          Панель доступна только главе семьи. Получите одноразовую ссылку командой
          <span class="font-medium text-slate-700">/panel</span> в Telegram-боте.
        </p>
      </div>

      <div class="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div class="mb-5 grid grid-cols-2 gap-1 rounded-lg bg-slate-100 p-1">
          <button
            class="rounded-md px-3 py-2 text-sm font-medium transition-colors"
            :class="tab === 'code' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'"
            type="button"
            @click="tab = 'code'"
          >
            Код из бота
          </button>
          <button
            class="rounded-md px-3 py-2 text-sm font-medium transition-colors"
            :class="tab === 'password' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-700'"
            type="button"
            @click="tab = 'password'"
          >
            Email и пароль
          </button>
        </div>

        <p
          v-if="error"
          class="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
        >
          {{ error }}
        </p>

        <form v-if="tab === 'code'" class="grid gap-4" @submit.prevent="submitCode">
          <label class="flex flex-col gap-1.5 text-sm font-medium text-slate-600">
            <span>Одноразовый код</span>
            <textarea
              v-model="code"
              class="min-h-20 w-full resize-none rounded-lg border border-slate-300 bg-white px-3 py-2 font-mono text-sm text-slate-800 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/30"
              placeholder="Вставьте код из ссылки /panel"
              autocomplete="one-time-code"
            />
          </label>
          <button
            class="rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
            type="submit"
            :disabled="loading || !code.trim()"
          >
            {{ loading ? 'Проверяем…' : 'Войти' }}
          </button>
        </form>

        <form v-else class="grid gap-4" @submit.prevent="submitPassword">
          <label class="flex flex-col gap-1.5 text-sm font-medium text-slate-600">
            <span>Email</span>
            <input
              v-model="email"
              class="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/30"
              type="email"
              autocomplete="email"
              required
            />
          </label>
          <label class="flex flex-col gap-1.5 text-sm font-medium text-slate-600">
            <span>Пароль</span>
            <input
              v-model="password"
              class="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-800 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500/30"
              type="password"
              autocomplete="current-password"
              required
            />
          </label>
          <button
            class="rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
            type="submit"
            :disabled="loading || !email.trim() || !password"
          >
            {{ loading ? 'Входим…' : 'Войти' }}
          </button>
        </form>
      </div>

      <p class="mt-6 text-center text-xs text-slate-400">
        Остальные члены семьи работают через Telegram-бота и не имеют доступа к панели.
      </p>
    </div>
  </div>
</template>
