import { createRouter, createWebHistory } from 'vue-router';
import BootScreen from '../components/shell/BootScreen.vue';
import DesktopView from '../views/DesktopView.vue';
import LockScreen from '../views/LoginView.vue';
import PendingView from '../views/PendingView.vue';
import RegisterView from '../views/RegisterView.vue';
import type { SessionPhase } from '../stores/session';

const ROUTE_FOR: Record<SessionPhase, string> = {
  boot: 'boot',
  lock: 'lock',
  register: 'register',
  pending: 'pending',
  desktop: 'desktop',
};

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'desktop', component: DesktopView },
    { path: '/boot', name: 'boot', component: BootScreen },
    { path: '/lock', name: 'lock', component: LockScreen },
    { path: '/register', name: 'register', component: RegisterView },
    { path: '/pending', name: 'pending', component: PendingView },
    { path: '/:pathMatch(.*)*', redirect: { name: 'desktop' } },
  ],
});

export function routeForPhase(phase: SessionPhase): string {
  return ROUTE_FOR[phase];
}

export default router;
