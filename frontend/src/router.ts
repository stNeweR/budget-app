import { createRouter, createWebHistory } from 'vue-router';
import { auth, restoreSession } from './auth';
import DashboardView from './views/DashboardView.vue';
import LoginView from './views/LoginView.vue';
import SetupPasswordView from './views/SetupPasswordView.vue';

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: LoginView,
      meta: { public: true },
    },
    {
      path: '/setup-password',
      name: 'setup-password',
      component: SetupPasswordView,
    },
    {
      path: '/',
      name: 'dashboard',
      component: DashboardView,
    },
  ],
});

router.beforeEach(async (to) => {
  await restoreSession();

  if (to.meta.public) {
    if (auth.user && !to.query.code) {
      return auth.user.has_password ? '/' : '/setup-password';
    }
    return true;
  }

  if (!auth.user) {
    return {
      path: '/login',
      query: to.fullPath === '/' ? {} : { next: to.fullPath },
    };
  }

  if (!auth.user.has_password && to.path !== '/setup-password') {
    return '/setup-password';
  }

  return true;
});
