<script setup lang="ts">
import type { SignupLead } from '../types';

defineProps<{
  leads: SignupLead[];
  loading?: boolean;
}>();

function formatDate(dateStr: string): string {
  if (!dateStr) return '-';
  try {
    return dateStr.split('.')[0] || dateStr;
  } catch {
    return dateStr;
  }
}

function statusTone(status?: string): 'ok' | 'warn' {
  if (status === 'Site Siap' || status === 'Active' || status === 'Aktif') return 'ok';
  return 'warn';
}
</script>

<template>
  <div class="aios-admin-table-wrap">
    <table class="aios-admin-table">
      <thead>
        <tr>
          <th>Tanggal Daftar</th>
          <th>Nama Calon Klien</th>
          <th>Email</th>
          <th>Perusahaan</th>
          <th>Negara</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody>
        <tr v-if="leads.length === 0">
          <td colspan="6" class="aios-admin-empty">
            {{ loading ? 'Memuat pendaftar...' : 'Belum ada pendaftar calon klien baru.' }}
          </td>
        </tr>
        <tr v-for="lead in leads" :key="lead.name">
          <td class="aios-admin-muted">{{ formatDate(lead.creation) }}</td>
          <td>
            <p class="aios-admin-site">{{ lead.lead_name || lead.first_name || lead.name }}</p>
          </td>
          <td>{{ lead.email_id || '-' }}</td>
          <td>{{ lead.company_name || '-' }}</td>
          <td>{{ lead.country || '-' }}</td>
          <td>
            <span class="aios-admin-badge" :data-tone="statusTone(lead.status)">
              {{ lead.status || 'Menunggu Penyiapan Site' }}
            </span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
