<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue';
import { useBranchesStore } from '../../stores/branches';
import { useChatStore } from '../../stores/chat';
import { useModulesStore } from '../../stores/modules';
import { useUiStore } from '../../stores/ui';
import type { SearchResult } from '../../types';
import AppIcon from '../base/AppIcon.vue';

const branches = useBranchesStore();
const chat = useChatStore();
const modules = useModulesStore();
const ui = useUiStore();

const query = ref('');
const input = ref<HTMLInputElement | null>(null);
let searchTimer: number | undefined;

onMounted(() => {
  void branches.load();
  void modules.loadBootstrap();
  void modules.runSearch('');
  void nextTick(() => input.value?.focus());
});

onUnmounted(() => {
  if (searchTimer) window.clearTimeout(searchTimer);
});

watch(query, (val) => {
  if (searchTimer) window.clearTimeout(searchTimer);
  const trimmed = val.trim();
  if (!trimmed) {
    void modules.runSearch('');
    return;
  }
  searchTimer = window.setTimeout(() => {
    void modules.runSearch(trimmed);
  }, 180);
});

const selected = computed(() => branches.selected);
const selectedKey = computed(() => selected.value?.key ?? '');
const agentName = computed(() => selected.value?.name ?? 'AI agent');

const moduleResults = computed(() =>
  modules.searchResults.filter(
    (item): item is Extract<SearchResult, { kind: 'module' }> => item.kind === 'module',
  ),
);

const documentResults = computed(() =>
  modules.searchResults.filter(
    (item): item is Extract<SearchResult, { kind: 'document' }> => item.kind === 'document',
  ),
);

function documentSubtext(item: Extract<SearchResult, { kind: 'document' }>): string {
  const parts: string[] = [item.module.label];
  for (const col of item.module.columns) {
    if (col.field === 'name') continue;
    const val = item.row[col.field];
    if (typeof val === 'string' && val.trim()) {
      parts.push(val.trim());
      break;
    }
  }
  return parts.join(' · ');
}

function openModuleResult(moduleKey: string) {
  query.value = '';
  ui.closeFlyouts();
  void modules.openModule(moduleKey);
}

function ask(text: string) {
  const q = text.trim();
  if (!q || !selectedKey.value) return;
  ui.openAgent();
  query.value = '';
  ui.closeFlyouts();
  void chat.send(selectedKey.value, q);
}
</script>

<template>
  <div class="flyout" role="dialog" aria-label="Pencarian">
    <div class="fl-scroll">
      <label class="fl-input">
        <AppIcon name="search" :size="18" />
        <input
          ref="input"
          v-model="query"
          placeholder="Cari atau tanyakan agent"
          aria-label="Pencarian"
          @keydown.enter.prevent="ask(query)"
        />
      </label>
      <template v-if="!query.trim()">
        <div v-if="modules.modules.length" class="sr-group">
          <h5>Modul</h5>
          <div class="sr-empty">
            <button
              v-for="m in modules.modules"
              :key="m.key"
              class="chip"
              type="button"
              @click="openModuleResult(m.key)"
            >
              <AppIcon :name="m.icon || 'file'" :size="14" />
              {{ m.label }}
            </button>
          </div>
        </div>
        <div class="sr-group">
          <h5>Atau tanyakan</h5>
          <div class="sr-empty">
            <button v-for="p in branches.suggestions(selectedKey)" :key="p" class="chip" @click="ask(p)">
              {{ p }}
            </button>
            <span v-if="!branches.suggestions(selectedKey).length" class="empty-note">
              Belum ada saran dari backend.
            </span>
          </div>
        </div>
      </template>
      <template v-else>
        <div class="sr-group">
          <h5>Tanyakan agent</h5>
          <button class="sr-item first" @click="ask(query)">
            <span v-if="selected" class="agent-dot" :data-branch="selected.key">{{ selected.name.charAt(0).toUpperCase() }}</span>
            <span class="t">Tanya {{ agentName }}: “{{ query }}”</span>
            <small>Enter</small>
          </button>
        </div>
        <div class="sr-group">
          <h5>Modul</h5>
          <template v-if="moduleResults.length">
            <button
              v-for="item in moduleResults"
              :key="item.module.key"
              class="sr-item"
              type="button"
              @click="openModuleResult(item.module.key)"
            >
              <span class="tile sm neutral"><AppIcon :name="item.module.icon || 'file'" :size="14" /></span>
              <span class="t">{{ item.module.label }}</span>
              <small>{{ item.module.group }}</small>
            </button>
          </template>
          <div v-else-if="modules.searchLoading" class="empty-note">Mencari modul & dokumen…</div>
          <div v-else-if="modules.searchError" class="empty-note">{{ modules.searchError }}</div>
          <div v-else class="empty-note">Tidak ada modul yang cocok.</div>
        </div>
        <div v-if="documentResults.length || (!modules.searchLoading && !modules.searchError)" class="sr-group">
          <h5>Dokumen</h5>
          <template v-if="documentResults.length">
            <button
              v-for="doc in documentResults"
              :key="`${doc.module.key}:${doc.name}`"
              class="sr-item"
              type="button"
              @click="openModuleResult(doc.module.key)"
            >
              <span class="tile sm neutral"><AppIcon :name="doc.module.icon || 'file'" :size="14" /></span>
              <span class="t">{{ doc.name }}</span>
              <small>{{ documentSubtext(doc) }}</small>
            </button>
          </template>
          <div v-else class="empty-note">Tidak ada dokumen yang cocok.</div>
        </div>
      </template>
    </div>
  </div>
</template>
