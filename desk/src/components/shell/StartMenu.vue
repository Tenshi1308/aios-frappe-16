<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useBranchesStore } from '../../stores/branches';
import { useModulesStore } from '../../stores/modules';
import { useSessionStore } from '../../stores/session';
import { useUiStore } from '../../stores/ui';
import AppIcon from '../base/AppIcon.vue';

const session = useSessionStore();
const branches = useBranchesStore();
const modules = useModulesStore();
const ui = useUiStore();

onMounted(() => {
  void modules.loadBootstrap();
});

const powerOpen = ref(false);
const siteLabel = computed(() => session.context?.aios_company_name || 'AIOS');
const roleLabel = computed(() => {
  const roles = session.context?.roles ?? [];
  if (roles.includes('AIOS Client')) return 'AIOS Client';
  if (roles.includes('System Manager')) return 'System Manager';
  return roles[0] ?? 'Pengguna';
});

function openAgent(branchKey: string) {
  branches.selectBranch(branchKey);
  ui.openAgent();
}

function openModule(key: string) {
  ui.closeFlyouts();
  void modules.openModule(key);
}

function openSettings() {
  ui.closeFlyouts();
  void modules.openSettings();
}
</script>

<template>
  <div class="flyout" role="dialog" aria-label="Menu mulai">
    <div class="fl-scroll">
      <button class="fl-search" @click="ui.openSearch()">
        <AppIcon name="search" :size="17" />
        <span>Cari modul, dokumen, atau tanyakan agent</span>
        <kbd>Ctrl K</kbd>
      </button>
      <div class="fl-head">
        <h4>AI agents</h4>
        <span>{{ branches.branches.length }} cabang aktif</span>
      </div>
      <div class="agent-row">
        <button v-for="b in branches.branches" :key="b.key" class="agent-pill" @click="openAgent(b.key)">
          <span class="agent-dot" :data-branch="b.key">{{ b.name.charAt(0).toUpperCase() }}</span>
          {{ b.name }}
        </button>
        <span v-if="!branches.branches.length" class="empty-note">Belum ada agent aktif.</span>
      </div>
      <div class="fl-head">
        <h4>Modul</h4>
        <span v-if="modules.modules.length">{{ modules.modules.length }} modul</span>
      </div>
      <template v-if="modules.grouped.length">
        <div v-for="grp in modules.grouped" :key="grp.group" class="sr-group">
          <h5>{{ grp.group }}</h5>
          <div class="agent-row">
            <button
              v-for="m in grp.items"
              :key="m.key"
              class="agent-pill"
              type="button"
              @click="openModule(m.key)"
            >
              <span class="tile sm neutral"><AppIcon :name="m.icon || 'file'" :size="13" /></span>
              {{ m.label }}
            </button>
          </div>
        </div>
      </template>
      <div v-else class="empty-note">
        {{ modules.loading ? 'Memuat modul…' : 'Belum ada modul tersedia.' }}
      </div>
    </div>
    <div class="start-foot">
      <div class="me">
        <span class="avatar">{{ session.initials }}</span>
        <div>
          <b>{{ session.context?.full_name ?? session.context?.user }}</b>
          <small>{{ roleLabel }} · {{ siteLabel }}</small>
        </div>
      </div>
      <div class="foot-actions">
        <button class="tb-btn" aria-label="Pengaturan" @click="openSettings">
          <AppIcon name="gear" :size="18" />
        </button>
        <div class="power-wrap">
          <button class="tb-btn" :class="{ on: powerOpen }" aria-label="Opsi daya" @click="powerOpen = !powerOpen">
            <AppIcon name="power" :size="18" />
          </button>
          <div v-if="powerOpen" class="power-menu">
            <button @click="powerOpen = false; session.lock()">
              <AppIcon name="lock" :size="16" /> Kunci
            </button>
            <button @click="powerOpen = false; session.restart()">
              <AppIcon name="refresh" :size="16" /> Muat ulang
            </button>
            <button @click="powerOpen = false; void session.logout()">
              <AppIcon name="power" :size="16" /> Keluar
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.foot-actions {
  display: flex;
  align-items: center;
  gap: var(--space-4);
}
</style>
