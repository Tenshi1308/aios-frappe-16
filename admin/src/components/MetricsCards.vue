<script setup lang="ts">
import { computed } from 'vue';
import type { DashboardTotals } from '../types';

const props = defineProps<{ totals: DashboardTotals | null }>();

const cards = computed(() => {
  const totals = props.totals;
  return [
    { key: 'sites', label: 'Jumlah site', value: totals ? String(totals.sites) : '-' },
    { key: 'active_users', label: 'Pengguna aktif', value: totals ? String(totals.active_users) : '-' },
    { key: 'total_users', label: 'Total pengguna', value: totals ? String(totals.total_users) : '-' },
    {
      key: 'tokens_quota',
      label: 'Token site terpakai',
      value: totals ? `${totals.site_tokens_used} / ${totals.site_token_limit}` : '-',
    },
    { key: 'tokens_today', label: 'Token hari ini', value: totals ? String(totals.tokens_today) : '-' },
  ];
});
</script>

<template>
  <div class="aios-admin-cards">
    <div
      v-for="card in cards"
      :key="card.key"
      class="aios-admin-metric"
      :data-metric="card.key"
    >
      <span class="aios-admin-metric-label">{{ card.label }}</span>
      <span class="aios-admin-metric-value">{{ card.value }}</span>
    </div>
  </div>
</template>
