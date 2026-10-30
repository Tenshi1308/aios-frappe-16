<script setup lang="ts">
import { ref } from 'vue';
import type { DashboardUser } from '../types';

const props = defineProps<{
  users: DashboardUser[];
  site: string;
  sites: string[];
  filter: 'pending' | 'all';
  loading?: boolean;
}>();

const emit = defineEmits<{
  (event: 'setStatus', payload: { site: string; user: string; status: string }): void;
  (event: 'changeSite', site: string): void;
  (event: 'changeFilter', filter: 'pending' | 'all'): void;
}>();

const busy = ref<string | null>(null);

function tone(status: string | null): string | undefined {
  if (status === 'Active') return 'ok';
  if (status === 'Pending Provisioning') return 'warn';
  if (status === 'Suspended') return 'bad';
  return undefined;
}

async function setPayload(user: DashboardUser, status: string): Promise<void> {
  busy.value = `${props.site}:${user.name}`;
  try {
    emit('setStatus', { site: props.site, user: user.name, status });
  } finally {
    busy.value = null;
  }
}
</script>

<template>
  <div>
    <div class="aios-admin-toolbar">
      <div class="aios-admin-select-wrap">
        <select
          :value="site"
          class="aios-admin-select"
          aria-label="Pilih site klien"
          @change="emit('changeSite', ($event.target as HTMLSelectElement).value)"
        >
          <option v-for="s in sites" :key="s" :value="s">{{ s }}</option>
        </select>
        <svg class="aios-admin-select-arrow" viewBox="0 0 16 16" fill="none" stroke="currentColor">
          <path d="M4 6l4 4 4-4" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
      </div>
      <div class="aios-admin-select-wrap">
        <select
          :value="filter"
          class="aios-admin-select"
          aria-label="Filter status pengguna"
          @change="emit('changeFilter', ($event.target as HTMLSelectElement).value as 'pending' | 'all')"
        >
          <option value="pending">Pending Provisioning</option>
          <option value="all">Semua</option>
        </select>
        <svg class="aios-admin-select-arrow" viewBox="0 0 16 16" fill="none" stroke="currentColor">
          <path d="M4 6l4 4 4-4" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
      </div>
      <span class="aios-admin-muted">{{ users.length }} pengguna</span>
    </div>
    <div class="aios-admin-table-wrap">
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
          <tr v-for="user in users" :key="`${site}:${user.name}`">
            <td>{{ user.full_name || user.name }}</td>
            <td class="aios-admin-muted">{{ site }}</td>
            <td><span class="aios-admin-badge" :data-tone="tone(user.aios_status)">{{ user.aios_status || '-' }}</span></td>
            <td>{{ user.aios_persona || '-' }}</td>
            <td>{{ user.last_login || 'Belum pernah' }}</td>
            <td>
              <div class="aios-admin-actions">
                <button
                  v-if="user.aios_status !== 'Active'"
                  class="aios-admin-button"
                  data-variant="primary"
                  :disabled="busy !== null"
                  @click="setPayload(user, 'Active')"
                >
                  Aktifkan
                </button>
                <button
                  v-else
                  class="aios-admin-button"
                  :disabled="busy !== null"
                  title="Terbitkan ulang tautan undangan atau reset sandi mandiri"
                  @click="setPayload(user, 'Active')"
                >
                  Reset Sandi
                </button>
                <button
                  class="aios-admin-button"
                  data-variant="danger"
                  :disabled="busy !== null || user.aios_status === 'Suspended'"
                  @click="setPayload(user, 'Suspended')"
                >
                  Suspend
                </button>
              </div>
            </td>
          </tr>
          <tr v-if="users.length === 0">
            <td colspan="6" class="aios-admin-muted">Tidak ada pengguna pada filter ini.</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
