<script setup lang="ts">
import { computed } from 'vue';
import type { DashboardTotals } from '../types';

const props = defineProps<{ totals: DashboardTotals | null }>();

const cards = computed(() => {
  const totals = props.totals;
  return [
    { label: 'Jumlah site', value: totals ? String(totals.sites) : '-' },
    { label: 'Pengguna aktif', value: totals ? String(totals.active_users) : '-' },
    { label: 'Total pengguna', value: totals ? String(totals.total_users) : '-' },
    {
      label: 'Token site terpakai',
      value: totals ? `${totals.site_tokens_used} / ${totals.site_token_limit}` : '-',
    },
    { label: 'Token hari ini', value: totals ? String(totals.tokens_today) : '-' },
  ];
});
</script>

<template>
  <div class="aios-admin-cards">
    <div v-for="card in cards" :key="card.label" class="aios-admin-metric">
      <span class="aios-admin-metric-label">{{ card.label }}</span>
      <span class="aios-admin-metric-value">{{ card.value }}</span>
    </div>
  </div>
</template>
