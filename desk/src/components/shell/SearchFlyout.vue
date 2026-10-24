<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue';
import { useBranchesStore } from '../../stores/branches';
import { useChatStore } from '../../stores/chat';
import { useUiStore } from '../../stores/ui';
import AppIcon from '../base/AppIcon.vue';

const branches = useBranchesStore();
const chat = useChatStore();
const ui = useUiStore();

const query = ref('');
const input = ref<HTMLInputElement | null>(null);
onMounted(() => {
  void branches.load();
  void nextTick(() => input.value?.focus());
});

const selected = computed(() => branches.selected);
const selectedKey = computed(() => selected.value?.key ?? '');
const agentName = computed(() => selected.value?.name ?? 'AI agent');

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
          <div class="empty-note">Pencarian modul & dokumen menyusul di fase berikutnya.</div>
        </div>
      </template>
    </div>
  </div>
</template>
