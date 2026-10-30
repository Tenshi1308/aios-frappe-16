<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue';
import { useModulesStore } from '../../stores/modules';
import type {
  ModuleCard,
  ModuleColumn,
  ModuleFilterDef,
  ModuleFilterKey,
  ModuleFilters,
  ModuleRow,
} from '../../types';
import { formatCurrency, formatNumber, formatShortDate } from '../../utils/format';
import AppIcon from '../base/AppIcon.vue';

const props = defineProps<{ moduleKey: string }>();

const modules = useModulesStore();

const filterDraft = reactive<Record<ModuleFilterKey, string>>({
  date_from: '',
  date_to: '',
  status: '',
  party: '',
});
const filterError = ref('');

const entry = computed(() => modules.dataFor(props.moduleKey));
const meta = computed(() => entry.value?.module ?? modules.byKey(props.moduleKey) ?? null);
const loading = computed(() => modules.isLoadingKey(props.moduleKey));
const error = computed(() => modules.errorFor(props.moduleKey));

const cards = computed<ModuleCard[]>(() => entry.value?.cards ?? []);
const columns = computed<ModuleColumn[]>(() => {
  const dtCols = entry.value?.doctypes[0]?.columns;
  if (dtCols && dtCols.length) return dtCols;
  return meta.value?.columns ?? [];
});
const rows = computed<ModuleRow[]>(() => entry.value?.rows ?? []);
const pagination = computed(
  () => entry.value?.pagination ?? { page: 1, page_size: 25, total: 0, total_pages: 0 },
);
const filterDefs = computed<ModuleFilterDef[]>(() => meta.value?.filters ?? []);

const cardCurrency = computed(() => {
  const c = cards.value.find((item) => item.currency)?.currency;
  return c ?? '';
});

function syncDraftFromStore() {
  filterError.value = '';
  const saved = entry.value?.filters ?? {};
  filterDraft.date_from = saved.date_from ?? '';
  filterDraft.date_to = saved.date_to ?? '';
  filterDraft.status = saved.status ?? '';
  filterDraft.party = saved.party ?? '';
}

watch(
  () => props.moduleKey,
  (key) => {
    syncDraftFromStore();
    if (!modules.dataFor(key)) {
      void modules.refreshModule(key, { page: 1, filters: {} });
    }
  },
);

watch(
  () => entry.value?.filters,
  () => {
    syncDraftFromStore();
  },
);

onMounted(() => {
  syncDraftFromStore();
  if (!entry.value) {
    void modules.refreshModule(props.moduleKey, { page: 1, filters: {} });
  }
});

function formatCard(card: ModuleCard): string {
  if (card.format === 'currency') {
    return formatCurrency(card.value, card.currency || cardCurrency.value);
  }
  return formatNumber(card.value);
}

function scopeLabel(card: ModuleCard): string {
  if (card.scope === 'site') return 'Cakupan site';
  if (hasActiveFilter()) return 'Hasil filter';
  return 'Cakupan company';
}

function formatCell(row: ModuleRow, col: ModuleColumn): string {
  const raw = row[col.field];
  if (raw === null || raw === undefined || raw === '') return '—';
  if (col.format === 'currency') {
    return formatCurrency(
      typeof raw === 'number' || typeof raw === 'string' ? raw : String(raw),
      cardCurrency.value,
    );
  }
  if (col.format === 'number') {
    return formatNumber(typeof raw === 'number' || typeof raw === 'string' ? raw : String(raw));
  }
  if (col.format === 'date') {
    return formatShortDate(raw);
  }
  if (col.format === 'boolean') {
    const truthy = raw === true || raw === 1 || raw === '1';
    return truthy ? 'Ya' : 'Tidak';
  }
  return String(raw);
}

function currentFiltersPayload(): ModuleFilters {
  const payload: ModuleFilters = {};
  for (const def of filterDefs.value) {
    const val = filterDraft[def.key]?.trim();
    if (val) payload[def.key] = val;
  }
  return payload;
}

function hasActiveFilter(): boolean {
  return filterDefs.value.some((def) => !!filterDraft[def.key]?.trim());
}

async function onApplyFilter() {
  const dFrom = filterDraft.date_from?.trim();
  const dTo = filterDraft.date_to?.trim();
  if (dFrom && dTo && dFrom > dTo) {
    filterError.value = 'Tanggal mulai tidak boleh melebihi tanggal akhir.';
    return;
  }
  filterError.value = '';
  await modules.applyFilter(props.moduleKey, currentFiltersPayload());
}

async function onResetFilter() {
  filterError.value = '';
  for (const def of filterDefs.value) {
    filterDraft[def.key] = '';
  }
  await modules.applyFilter(props.moduleKey, {});
}

async function onRefresh() {
  await modules.refreshModule(props.moduleKey, {
    page: pagination.value.page,
    filters: currentFiltersPayload(),
  });
}

const canPrev = computed(() => !loading.value && pagination.value.page > 1);
const canNext = computed(
  () =>
    !loading.value &&
    pagination.value.total_pages > 0 &&
    pagination.value.page < pagination.value.total_pages,
);

async function onPrevPage() {
  if (!canPrev.value) return;
  await modules.loadPage(props.moduleKey, pagination.value.page - 1);
}

async function onNextPage() {
  if (!canNext.value) return;
  await modules.loadPage(props.moduleKey, pagination.value.page + 1);
}
</script>

<template>
  <div class="mod-win">
    <header class="mod-head">
      <div class="mod-title">
        <span class="mod-icon">
          <AppIcon :name="meta?.icon || 'file'" :size="16" />
        </span>
        <div>
          <h4>{{ meta?.label || props.moduleKey }}</h4>
          <small v-if="meta?.group">{{ meta.group }} · Baca saja</small>
        </div>
      </div>
      <button
        class="mod-refresh"
        type="button"
        :disabled="loading"
        aria-label="Muat ulang modul"
        @click="onRefresh"
      >
        <AppIcon name="refresh" :size="14" />
        <span>{{ loading ? 'Memuat…' : 'Refresh' }}</span>
      </button>
    </header>

    <div v-if="error" class="mod-banner mod-error" role="alert">
      <span>{{ error }}</span>
      <button class="btn ghost" type="button" :disabled="loading" @click="onRefresh">
        Coba lagi
      </button>
    </div>

    <div v-if="loading && !entry" class="mod-state">Memuat data modul…</div>

    <template v-else-if="entry">
      <section v-if="cards.length" class="mod-cards" aria-label="Ringkasan modul">
        <article v-for="card in cards" :key="card.key" class="mod-card">
          <div class="mod-card-top">
            <span class="mod-card-label">{{ card.label }}</span>
            <span class="mod-card-scope">{{ scopeLabel(card) }}</span>
          </div>
          <div class="mod-card-val">
            <b>{{ formatCard(card) }}</b>
            <small v-if="card.currency">{{ card.currency }}</small>
          </div>
        </article>
      </section>

      <form
        v-if="filterDefs.length"
        class="mod-filters"
        aria-label="Filter dokumen"
        @submit.prevent="onApplyFilter"
      >
        <label v-for="f in filterDefs" :key="f.key" class="mod-filter-field">
          <span>{{ f.label }}</span>
          <input
            v-model="filterDraft[f.key]"
            :type="f.type === 'date' ? 'date' : 'text'"
            :placeholder="f.label"
            :aria-label="f.label"
            :max="f.key === 'date_from' && filterDraft.date_to ? filterDraft.date_to : undefined"
            :min="f.key === 'date_to' && filterDraft.date_from ? filterDraft.date_from : undefined"
            @input="filterError = ''"
          />
        </label>
        <div class="mod-filter-actions">
          <button class="btn agent" type="submit" :disabled="loading">Terapkan</button>
          <button
            v-if="hasActiveFilter()"
            class="btn ghost"
            type="button"
            :disabled="loading"
            @click="onResetFilter"
          >
            Reset
          </button>
        </div>
        <div v-if="filterError" class="mod-filter-error" role="alert">
          {{ filterError }}
        </div>
      </form>

      <div v-if="!rows.length" class="mod-state">
        Belum ada dokumen yang sesuai pada modul ini.
      </div>

      <div v-else class="mod-table-wrap">
        <table class="mod-table">
          <thead>
            <tr>
              <th
                v-for="col in columns"
                :key="col.key"
                :class="{ num: col.format === 'currency' || col.format === 'number' }"
              >
                {{ col.label }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, ri) in rows" :key="String(row.name ?? ri)">
              <td
                v-for="col in columns"
                :key="col.key"
                :class="{ num: col.format === 'currency' || col.format === 'number' }"
              >
                {{ formatCell(row, col) }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>

      <footer class="mod-foot">
        <span class="mod-page-info">
          Halaman {{ pagination.page }} dari {{ Math.max(1, pagination.total_pages) }} ·
          {{ formatNumber(pagination.total) }} baris
        </span>
        <div class="mod-page-btns">
          <button
            class="btn ghost"
            type="button"
            :disabled="!canPrev"
            aria-label="Halaman sebelumnya"
            @click="onPrevPage"
          >
            Sebelumnya
          </button>
          <button
            class="btn ghost"
            type="button"
            :disabled="!canNext"
            aria-label="Halaman berikutnya"
            @click="onNextPage"
          >
            Berikutnya
          </button>
        </div>
      </footer>
    </template>
  </div>
</template>

<style scoped>
.mod-win {
  display: flex;
  flex-direction: column;
  gap: var(--space-12);
  height: 100%;
  min-height: 280px;
  color: var(--fg);
}
.mod-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-10);
}
.mod-title {
  display: flex;
  align-items: center;
  gap: var(--space-10);
  min-width: 0;
}
.mod-icon {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-8);
  display: grid;
  place-items: center;
  background: var(--accent-soft);
  color: var(--accent-strong);
  flex: none;
}
.mod-title h4 {
  margin: 0;
  font-size: var(--fs-14);
  font-weight: var(--fw-700);
}
.mod-title small {
  display: block;
  color: var(--muted);
  font-size: var(--fs-11-5);
}
.mod-refresh {
  display: inline-flex;
  align-items: center;
  gap: var(--space-6);
  padding: var(--space-6) var(--space-10);
  border: 1px solid var(--line);
  border-radius: var(--radius-8);
  background: var(--surface-2);
  color: var(--fg);
  font-size: var(--fs-12);
  font-weight: var(--fw-600);
}
.mod-refresh:hover:not(:disabled) {
  background: var(--hover);
}
.mod-refresh:disabled {
  opacity: 0.65;
  cursor: wait;
}
.mod-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-10);
  padding: var(--space-8) var(--space-12);
  border: 1px solid var(--line);
  border-radius: var(--radius-8);
  background: var(--surface-2);
  font-size: var(--fs-12);
}
.mod-error {
  border-color: var(--bad);
  background: var(--bad-soft);
  color: var(--bad);
}
.mod-cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: var(--space-10);
}
.mod-card {
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
  padding: var(--space-10) var(--space-12);
  border: 1px solid var(--line);
  border-radius: var(--radius-10);
  background: var(--surface-2);
}
.mod-card-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-6);
}
.mod-card-label {
  color: var(--muted);
  font-size: var(--fs-11-5);
  font-weight: var(--fw-600);
}
.mod-card-scope {
  padding: var(--space-1) var(--space-6);
  border-radius: var(--radius-pill);
  border: 1px solid var(--line);
  background: var(--surface);
  color: var(--faint);
  font-size: var(--fs-10);
}
.mod-card-val {
  display: flex;
  align-items: baseline;
  gap: var(--space-6);
}
.mod-card-val b {
  font-size: var(--fs-17);
  font-weight: var(--fw-700);
  font-variant-numeric: tabular-nums;
}
.mod-card-val small {
  color: var(--muted);
  font-size: var(--fs-11);
}
.mod-filters {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: var(--space-8);
  padding: var(--space-10);
  border: 1px solid var(--line);
  border-radius: var(--radius-10);
  background: var(--surface-2);
}
.mod-filter-field {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  flex: 1 1 130px;
  min-width: 120px;
}
.mod-filter-field span {
  color: var(--muted);
  font-size: var(--fs-11);
  font-weight: var(--fw-600);
}
.mod-filter-field input {
  padding: var(--space-6) var(--space-8);
  border: 1px solid var(--line);
  border-radius: var(--radius-6);
  background: var(--surface);
  color: var(--fg);
  font-size: var(--fs-12);
}
.mod-filter-actions {
  display: flex;
  align-items: center;
  gap: var(--space-6);
}
.mod-filter-error {
  width: 100%;
  color: var(--bad);
  font-size: var(--fs-11);
  font-weight: var(--fw-600);
  margin-top: var(--space-4);
}
.mod-state {
  flex: 1;
  display: grid;
  place-items: center;
  padding: var(--space-24) var(--space-12);
  border: 1px dashed var(--line);
  border-radius: var(--radius-10);
  background: var(--surface-2);
  color: var(--muted);
  font-size: var(--fs-12-5);
  text-align: center;
}
.mod-table-wrap {
  flex: 1;
  min-height: 0;
  overflow: auto;
  border: 1px solid var(--line);
  border-radius: var(--radius-10);
  background: var(--surface);
}
.mod-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--fs-12);
}
.mod-table th,
.mod-table td {
  padding: var(--space-8) var(--space-10);
  border-bottom: 1px solid var(--line);
  text-align: left;
  white-space: nowrap;
}
.mod-table th {
  position: sticky;
  top: 0;
  background: var(--surface-2);
  color: var(--muted);
  font-size: var(--fs-11);
  font-weight: var(--fw-700);
}
.mod-table th.num,
.mod-table td.num {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.mod-table tbody tr:hover {
  background: var(--hover);
}
.mod-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-10);
  padding-top: var(--space-2);
}
.mod-page-info {
  color: var(--muted);
  font-size: var(--fs-12);
  font-variant-numeric: tabular-nums;
}
.mod-page-btns {
  display: flex;
  gap: var(--space-6);
}
.mod-page-btns button:disabled {
  opacity: 0.5;
  cursor: default;
}
</style>
