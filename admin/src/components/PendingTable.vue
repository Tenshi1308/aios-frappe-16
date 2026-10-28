<script setup lang="ts">
import { computed, ref } from 'vue';
import type { DashboardUser, SiteEntry } from '../types';

const props = defineProps<{ sites: SiteEntry[] }>();

const emit = defineEmits<{
  (event: 'setStatus', payload: { site: string; user: string; status: string }): void;
}>();

type Filter = 'pending' | 'all';

const filter = ref<Filter>('pending');
const busy = ref<string | null>(null);

const PENDING_LABEL = 'Pending Provisioning';

const rows = computed(() => {
  const result: Array<DashboardUser & { site: string }> = [];
  for (const site of props.sites) {
    for (const user of site.users) {
      if (filter.value === 'pending' && user.aios_status !== PENDING_LABEL) {
        continue;
      }
      result.push({ ...user, site: site.site_name });
    }
  }
  return result;
});

function tone(status: string | null): string | undefined {
  if (status === 'Active') return 'ok';
  if (status === 'Pending Provisioning') return 'warn';
  if (status === 'Suspended') return 'bad';
  return undefined;
}

async function setPayload(user: DashboardUser & { site: string }, status: string): Promise<void> {
  busy.value = `${user.site}:${user.name}`;
  try {
    emit('setStatus', { site: user.site, user: user.name, status });
  } finally {
    busy.value = null;
  }
}
</script>

<template>
  <div class="aios-admin-card">
    <div class="aios-admin-section">
      <select v-model="filter" class="aios-admin-select" aria-label="Filter status pengguna">
        <option value="pending">Pending Provisioning</option>
        <option value="all">Semua</option>
      </select>
      <span class="aios-admin-muted">{{ rows.length }} pengguna</span>
    </div>
    <table class="aios-admin-table">
      <thead>
        <tr>
          <th>Pengguna</th>
          <th>Site</th>
          <th>Status</th>
          <th>Persona</th>
          <th>Login terakhir</th>
          <th>Aksi</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="user in rows" :key="`${user.site}:${user.name}`">
          <td>{{ user.full_name || user.name }}</td>
          <td class="aios-admin-muted">{{ user.site }}</td>
          <td><span class="aios-admin-badge" :data-tone="tone(user.aios_status)">{{ user.aios_status || '-' }}</span></td>
          <td>{{ user.aios_persona || '-' }}</td>
          <td>{{ user.last_login || 'Belum pernah' }}</td>
          <td>
            <button
              class="aios-admin-button"
              data-variant="primary"
              :disabled="busy !== null || user.aios_status === 'Active'"
              @click="setPayload(user, 'Active')"
            >
              Aktifkan
            </button>
            <button
              class="aios-admin-button"
              data-variant="danger"
              :disabled="busy !== null || user.aios_status === 'Suspended'"
              @click="setPayload(user, 'Suspended')"
            >
              Suspend
            </button>
          </td>
        </tr>
        <tr v-if="rows.length === 0">
          <td colspan="6" class="aios-admin-muted">Tidak ada pengguna pada filter ini.</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
