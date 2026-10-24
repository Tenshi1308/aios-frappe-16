<script setup lang="ts">
import { computed, ref } from 'vue';
import { useBranchesStore } from '../../stores/branches';
import { useSessionStore } from '../../stores/session';
import { useUiStore } from '../../stores/ui';
import AppIcon from '../base/AppIcon.vue';
import EkasaMark from '../base/EkasaMark.vue';

const session = useSessionStore();
const branches = useBranchesStore();
const ui = useUiStore();

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
      </div>
      <div class="empty-note">Modul ERPNext menyusul di fase berikutnya.</div>
    </div>
    <div class="start-foot">
      <div class="me">
        <span class="avatar">{{ session.initials }}</span>
        <div>
          <b>{{ session.context?.full_name ?? session.context?.user }}</b>
          <small>{{ roleLabel }} · {{ siteLabel }}</small>
        </div>
      </div>
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
</template>
