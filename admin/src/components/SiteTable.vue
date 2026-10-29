<script setup lang="ts">
import { computed, ref } from 'vue';
import type { SiteEntry } from '../types';

const props = defineProps<{ sites: SiteEntry[] }>();

const emit = defineEmits<{
  (event: 'health', site: string): void;
  (event: 'openPending', site: string): void;
}>();

const busy = ref<string | null>(null);

const rows = computed(() => props.sites);

function tone(status: string | null): string | undefined {
  if (status === 'Active') return 'ok';
  if (status === 'Suspended' || status === 'Provisioning') return 'warn';
  if (status === 'Decommissioned') return 'bad';
  return undefined;
}

async function onHealth(site: string): Promise<void> {
  busy.value = site;
  try {
    emit('health', site);
  } finally {
    busy.value = null;
  }
}
</script>

<template>
  <div class="aios-admin-table-wrap">
    <table class="aios-admin-table">
      <thead>
        <tr>
          <th>Site</th>
          <th>Perusahaan</th>
          <th>Status</th>
          <th>Terakhir dilihat</th>
          <th>Kesalahan terakhir</th>
          <th>Pending</th>
          <th>Aksi</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="site in rows" :key="site.site_name">
          <td>
            <p class="aios-admin-site">{{ site.site_name }}</p>
            <span class="aios-admin-muted">{{ site.base_url }}</span>
          </td>
          <td>
            <p class="aios-admin-site">{{ site.company_name || '-' }}</p>
            <span class="aios-admin-muted">
              {{ site.contact_name || '-' }} &middot; {{ site.contact_email || '-' }}
            </span>
          </td>
          <td>
            <span class="aios-admin-badge" :data-tone="tone(site.status)">{{ site.status || '-' }}</span>
          </td>
          <td>{{ site.last_seen || 'Belum pernah' }}</td>
          <td>{{ site.error || site.last_error || '-' }}</td>
          <td>
            <button
              v-if="site.metrics && site.metrics.pending_users > 0"
              type="button"
              class="aios-admin-badge"
              data-tone="warn"
              @click="emit('openPending', site.site_name)"
            >
              {{ site.metrics.pending_users }} pending
            </button>
            <span v-else class="aios-admin-muted">—</span>
          </td>
          <td>
            <button
              class="aios-admin-button"
              data-variant="primary"
              :disabled="busy === site.site_name"
              @click="onHealth(site.site_name)"
            >
              Cek kesehatan
            </button>
          </td>
        </tr>
        <tr v-if="rows.length === 0">
          <td colspan="7" class="aios-admin-muted">Belum ada site klien terdaftar.</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
