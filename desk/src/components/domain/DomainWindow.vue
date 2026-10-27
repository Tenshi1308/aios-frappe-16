<script setup lang="ts">
import { computed, onMounted, watch } from 'vue';
import { useBranchesStore } from '../../stores/branches';
import { useChatStore } from '../../stores/chat';
import { useModulesStore } from '../../stores/modules';
import { useUiStore } from '../../stores/ui';
import type { DomainCard } from '../../types';
import { formatCurrency, formatNumber } from '../../utils/format';
import AppIcon from '../base/AppIcon.vue';

const props = defineProps<{ domainKey: string }>();

const modules = useModulesStore();
const branches = useBranchesStore();
const chat = useChatStore();
const ui = useUiStore();

const entry = computed(() => modules.domainDataFor(props.domainKey));
const meta = computed(() => entry.value?.domain ?? modules.domainByKey(props.domainKey) ?? null);
const loading = computed(() => modules.isDomainLoadingKey(props.domainKey));
const error = computed(() => modules.domainErrorFor(props.domainKey));

const cards = computed<DomainCard[]>(() => entry.value?.cards ?? []);
const domainModules = computed(() => entry.value?.modules ?? []);
const branch = computed(() => branches.byKey(props.domainKey));
const branchName = computed(() => branch.value?.name ?? meta.value?.label ?? props.domainKey);
const branchInitial = computed(() =>
  (branch.value?.name ?? meta.value?.label ?? props.domainKey).charAt(0).toUpperCase(),
);
const branchSuggestions = computed(() =>
  branch.value ? branches.suggestions(branch.value.key, 2) : [],
);

function formatCard(card: DomainCard): string {
  if (card.format === 'currency') {
    return formatCurrency(card.value, card.currency || entry.value?.company.currency);
  }
  return formatNumber(card.value);
}

async function onRefresh() {
  await modules.refreshDomain(props.domainKey);
}

function onAsk(prompt?: string) {
  if (branch.value) {
    branches.selectBranch(branch.value.key);
  }
  ui.openAgent();
  if (prompt && branch.value) {
    void chat.send(branch.value.key, prompt);
  }
}

watch(
  () => props.domainKey,
  (key) => {
    if (!modules.domainDataFor(key)) {
      void modules.refreshDomain(key);
    }
  },
);

onMounted(() => {
  if (!entry.value) {
    void modules.refreshDomain(props.domainKey);
  }
});
</script>

<template>
  <div class="domain-win">
    <header class="domain-head">
      <div class="domain-title">
        <span
          class="tile sm"
          :style="{ background: `var(--${meta?.color_token || 'domain-' + props.domainKey})` }"
        >
          <AppIcon :name="meta?.icon || 'tag'" :size="13" />
        </span>
        <div>
          <h4>{{ meta?.label || props.domainKey }}</h4>
          <small>Bidang · Baca saja</small>
        </div>
      </div>
      <button
        class="domain-refresh"
        type="button"
        :disabled="loading"
        aria-label="Muat ulang bidang"
        @click="onRefresh"
      >
        <AppIcon name="refresh" :size="14" />
        <span>{{ loading ? 'Memuat…' : 'Refresh' }}</span>
      </button>
    </header>

    <div v-if="error" class="domain-banner domain-error" role="alert">
      <span>{{ error }}</span>
      <button class="btn ghost" type="button" :disabled="loading" @click="onRefresh">
        Coba lagi
      </button>
    </div>

    <div v-if="loading && !entry" class="domain-state">Memuat data bidang…</div>

    <template v-else-if="entry">
      <section v-if="cards.length" class="domain-cards" aria-label="Ringkasan bidang">
        <article v-for="card in cards" :key="card.key" class="domain-card">
          <span class="domain-card-label">{{ card.label }}</span>
          <span class="domain-card-value">{{ formatCard(card) }}</span>
        </article>
      </section>
      <div v-else class="empty-note">Belum ada kartu KPI.</div>

      <h3 class="sec">Shortcuts</h3>
      <div v-if="domainModules.length" class="domain-shortcuts">
        <button
          v-for="m in domainModules"
          :key="m.key"
          class="domain-shortcut"
          type="button"
          @click="modules.openModule(m.key)"
        >
          <AppIcon :name="m.icon || 'file'" :size="16" />
          <span>{{ m.label }}</span>
          <em>{{ formatNumber(m.row_count) }}</em>
        </button>
      </div>
      <div v-else class="empty-note">Belum ada modul tersedia.</div>

      <div class="domain-ask">
        <span class="agent-dot" :data-branch="branch?.key">{{ branchInitial }}</span>
        <div class="domain-ask-text">
          <b>{{ branchName }}</b> memahami bidang ini.
        </div>
        <div v-if="branchSuggestions.length" class="domain-ask-prompts">
          <button
            v-for="p in branchSuggestions"
            :key="p"
            class="chip"
            type="button"
            @click="onAsk(p)"
          >
            {{ p }}
          </button>
        </div>
        <button class="btn agent" type="button" @click="onAsk()">
          <AppIcon name="sparkle" :size="14" />
          <span>Tanya agent</span>
        </button>
      </div>
    </template>
  </div>
</template>
