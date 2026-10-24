<script setup lang="ts">
import { onMounted, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import BootScreen from './components/shell/BootScreen.vue';
import DesktopView from './views/DesktopView.vue';
import LoginView from './views/LoginView.vue';
import PendingView from './views/PendingView.vue';
import RegisterView from './views/RegisterView.vue';
import { routeForPhase } from './router';
import { useSessionStore } from './stores/session';

const session = useSessionStore();
const router = useRouter();

const mq = window.matchMedia('(max-width: 720px)');
const narrow = ref(mq.matches);
const onMq = (e: MediaQueryListEvent) => (narrow.value = e.matches);
onMounted(() => {
  mq.addEventListener('change', onMq);
  void session.boot();
});

watch(
  () => session.phase,
  (phase) => {
    const target = routeForPhase(phase);
    if (router.currentRoute.value.name !== target) void router.replace({ name: target });
  },
  { immediate: true },
);
</script>

<template>
  <main class="os" :class="{ narrow }">
    <BootScreen v-if="session.phase === 'boot'" />
    <DesktopView v-else-if="session.phase === 'desktop'" :narrow="narrow" />
    <RegisterView v-else-if="session.phase === 'register'" />
    <PendingView v-else-if="session.phase === 'pending'" />
    <LoginView v-else />
  </main>
</template>
