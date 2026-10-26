<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import BootScreen from './components/shell/BootScreen.vue';
import DesktopView from './views/DesktopView.vue';
import LoginView from './views/LoginView.vue';
import PendingView from './views/PendingView.vue';
import RegisterView from './views/RegisterView.vue';
import { routeForPhase } from './router';
import { useModulesStore } from './stores/modules';
import { useSessionStore } from './stores/session';
import { applyTheme } from './utils/theme';

const session = useSessionStore();
const modules = useModulesStore();
const router = useRouter();

const mq = window.matchMedia('(max-width: 720px)');
const narrow = ref(mq.matches);
const onMq = (e: MediaQueryListEvent) => (narrow.value = e.matches);

const colorSchemeMq = window.matchMedia('(prefers-color-scheme: dark)');
const onColorSchemeChange = () => {
  const current = modules.settings?.theme.value;
  if (!current || current === 'Automatic') {
    applyTheme('Automatic');
  }
};

onMounted(() => {
  mq.addEventListener('change', onMq);
  colorSchemeMq.addEventListener('change', onColorSchemeChange);
  void session.boot();
});
onUnmounted(() => {
  mq.removeEventListener('change', onMq);
  colorSchemeMq.removeEventListener('change', onColorSchemeChange);
});

watch(
  () => session.phase,
  (phase) => {
    const target = routeForPhase(phase);
    if (router.currentRoute.value.name !== target) void router.replace({ name: target });
    if (phase === 'desktop' && !modules.settings && !modules.settingsLoading) {
      void modules.loadSettings();
    }
  },
  { immediate: true },
);

watch(
  () => modules.settings?.theme.value,
  (themeValue) => {
    if (themeValue) applyTheme(themeValue);
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
