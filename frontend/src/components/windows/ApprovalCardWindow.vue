<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { fetchDraft } from '../../api/chat';
import { useBranchesStore } from '../../stores/branches';
import { useChatStore } from '../../stores/chat';
import { useSessionStore } from '../../stores/session';
import { useUiStore } from '../../stores/ui';
import type { DraftActionResult, DraftDetail } from '../../types';
import { formatDateTime, prettyJson } from '../../utils/format';
import AppIcon from '../base/AppIcon.vue';

const props = defineProps<{ draftId: string }>();

const session = useSessionStore();
const chat = useChatStore();
const branches = useBranchesStore();
const ui = useUiStore();

const draft = ref<DraftDetail | null>(null);
const payload = ref<Record<string, unknown> | null>(null);
const loading = ref(true);
const busy = ref(false);
const error = ref('');
const result = ref<DraftActionResult | null>(null);
const rejectReason = ref('');
const confirmingReject = ref(false);

const isPending = computed(() => draft.value?.status === 'PENDING_APPROVAL');

function loadErrorText(err: unknown): string {
  return err instanceof Error && err.message.trim() ? err.message : 'Draft tidak ditemukan.';
}

function dispatchFeedback(branchKey: string, feedbackMsg: string) {
  branches.selectBranch(branchKey);
  ui.openAgent();
  if (chat.isStreaming(branchKey)) {
    setTimeout(() => void chat.send(branchKey, feedbackMsg), 600);
  } else {
    void chat.send(branchKey, feedbackMsg);
  }
}

async function load(retry = 0) {
  loading.value = true;
  error.value = '';
  try {
    draft.value = await fetchDraft(props.draftId, session.csrfToken);
    try {
      const parsed = JSON.parse(draft.value.payload || '{}');
      payload.value = parsed && typeof parsed === 'object' ? parsed : null;
    } catch {
      payload.value = null;
    }
  } catch (err) {
    // Kartu bisa terbuka saat stream masih berjalan (commit transaksi terjadi
    // tepat sebelum event `done`), jadi "not found" awal di-retry, bukan final.
    const message = loadErrorText(err);
    if (retry < 4 && /not found|tidak ditemukan/i.test(message)) {
      loading.value = false;
      error.value = 'Menunggu draft tersinkron…';
      setTimeout(() => void load(retry + 1), 1500);
      return;
    }
    error.value = message;
    draft.value = null;
  } finally {
    loading.value = false;
  }
}

async function approve() {
  busy.value = true;
  result.value = null;
  try {
    const res = await chat.approveDraft(props.draftId);
    result.value = res.executed
      ? { ...res, message: res.message || `Draft dieksekusi${res.document ? ` (${res.document})` : ''}.` }
      : { ...res, message: res.message || 'Draft disetujui, tetapi eksekusi gagal.' };
    if (draft.value && typeof res.draft_status === 'string') draft.value.status = res.draft_status;

    if (res.executed) {
      const branchKey = draft.value?.branch || branches.selected?.key || 'sales';
      const docName = res.document || res.name || '';
      const docType = res.doctype || (payload.value?.doctype as string) || 'dokumen';
      const actionType = draft.value?.type || 'CREATE';

      let feedbackMsg = '';
      if (actionType === 'CREATE') {
        feedbackMsg = `Saya telah menyetujui draf ${props.draftId} (${docType}). Dokumen resmi ${docType} berhasil dibuat dengan nomor ${docName}. Mohon konfirmasi dan jelaskan langkah operasional selanjutnya.`;
      } else if (actionType === 'UPDATE_DRAFT') {
        feedbackMsg = `Saya telah menyetujui draf ${props.draftId} (${docType}). Perubahan pada dokumen resmi ${docType} ${docName} telah diterapkan. Mohon konfirmasi dan jelaskan langkah operasional selanjutnya.`;
      } else if (actionType === 'CANCEL_AND_AMEND') {
        feedbackMsg = `Saya telah menyetujui draf ${props.draftId} (${docType}). Dokumen lama telah dibatalkan dan dokumen amend resmi ${docName} telah diterbitkan. Mohon konfirmasi dan jelaskan langkah operasional selanjutnya.`;
      } else {
        feedbackMsg = `Saya telah menyetujui draf ${props.draftId} (${docType}). Dokumen resmi ${docName ? `dengan nomor ${docName}` : ''} telah diproses. Mohon konfirmasi dan jelaskan langkah operasional selanjutnya.`;
      }

      dispatchFeedback(branchKey, feedbackMsg);
    }
  } catch (err) {
    result.value = { executed: false, message: loadErrorText(err) };
  } finally {
    busy.value = false;
  }
}

async function reject() {
  busy.value = true;
  result.value = null;
  try {
    const reasonText = rejectReason.value.trim();
    const res = await chat.rejectDraft(props.draftId, reasonText);
    result.value = { ...res, message: res.message || 'Draft telah ditolak.' };
    if (draft.value) draft.value.status = 'REJECTED';
    confirmingReject.value = false;

    const branchKey = draft.value?.branch || branches.selected?.key || 'sales';
    const docType = (payload.value?.doctype as string) || 'dokumen';
    const reasonClause = reasonText ? ` dengan alasan: "${reasonText}"` : ' tanpa alasan khusus';
    const feedbackMsg = `Saya telah menolak draf ${props.draftId} (${docType})${reasonClause}. Mohon sesuaikan atau batalkan rencana tindakan ini.`;

    dispatchFeedback(branchKey, feedbackMsg);
  } catch (err) {
    result.value = { executed: false, message: loadErrorText(err) };
  } finally {
    busy.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div class="approval-card">
    <div v-if="loading" class="ac-note">Memuat draft…</div>
    <div v-else-if="error" class="ac-note">{{ error }}</div>
    <template v-else-if="draft">
      <div class="ac-meta">
        <span><b>Aksi:</b> {{ draft.type }}</span>
        <span><b>Doctype:</b> {{ payload?.doctype ?? '—' }}</span>
        <span v-if="draft.branch"><b>Cabang:</b> {{ draft.branch }}</span>
        <span><b>Status:</b> {{ draft.status }}</span>
        <span v-if="draft.created_by_agent"><b>Dibuat oleh:</b> {{ draft.created_by_agent }}</span>
        <span><b>Kedaluwarsa:</b> {{ formatDateTime(draft.expires_at) }}</span>
      </div>

      <div v-if="payload?.before" class="ac-json">
        <b>Sebelum</b>
        <pre>{{ prettyJson(payload.before) }}</pre>
      </div>
      <div class="ac-json">
        <b>Data diusulkan</b>
        <pre>{{ prettyJson(payload?.data ?? {}) }}</pre>
      </div>
      <div v-if="payload?.after" class="ac-json">
        <b>Sesudah</b>
        <pre>{{ prettyJson(payload.after) }}</pre>
      </div>
      <div v-if="draft.rejection_reason" class="ac-note">
        Alasan penolakan: {{ draft.rejection_reason }}
      </div>

      <div v-if="result" class="ac-result" :class="{ ok: result.executed, fail: !result.executed }">
        <AppIcon :name="result.executed ? 'check' : 'x'" :size="14" />
        <span>{{ result.message }}</span>
        <span v-if="result.code" class="ac-code">{{ result.code }}</span>
      </div>

      <div v-if="isPending" class="ac-actions">
        <textarea
          v-model="rejectReason"
          rows="2"
          placeholder="Alasan penolakan (opsional)"
          aria-label="Alasan penolakan"
        />
        <div class="ac-btns">
          <button class="btn ghost" :disabled="busy" @click="confirmingReject = !confirmingReject">
            Tolak
          </button>
          <button class="btn primary" :disabled="busy" @click="approve">
            {{ busy ? 'Memproses…' : 'Setujui & Eksekusi' }}
          </button>
        </div>
        <button
          v-if="confirmingReject"
          class="btn ghost wide"
          :disabled="busy"
          @click="reject"
        >
          {{ busy ? 'Memproses…' : 'Konfirmasi Penolakan' }}
        </button>
      </div>
      <div v-else class="ac-note">Draft sudah diproses ({{ draft.status }}).</div>
    </template>
  </div>
</template>

<style scoped>
.approval-card {
  display: flex;
  flex-direction: column;
  gap: var(--space-10);
  height: 100%;
  overflow: auto;
}
.ac-meta,
.ac-json,
.ac-note,
.ac-result {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-4) var(--space-12);
  padding: var(--space-8) var(--space-10);
  border: 1px solid var(--line);
  border-radius: var(--radius-6);
  background: var(--surface-2);
  color: var(--fg);
  font-size: var(--fs-12);
}
.ac-meta span b {
  color: var(--muted);
  font-weight: var(--fw-600);
}
.ac-json {
  flex-direction: column;
  gap: var(--space-4);
}
.ac-json b {
  color: var(--muted);
  font-size: var(--fs-11);
  text-transform: uppercase;
}
.ac-json pre {
  margin: 0;
  overflow: auto;
  font-family: var(--font-mono);
  font-size: var(--fs-11);
  color: var(--fg);
  white-space: pre-wrap;
  word-break: break-word;
}
.ac-note {
  color: var(--muted);
}
.ac-result {
  align-items: center;
}
.ac-result.ok {
  border-color: var(--ok);
  color: var(--ok);
}
.ac-result.fail {
  border-color: var(--bad);
  color: var(--bad);
}
.ac-code {
  font-family: var(--font-mono);
  font-size: var(--fs-11);
  color: var(--faint);
}
.ac-actions {
  display: flex;
  flex-direction: column;
  gap: var(--space-8);
  margin-top: auto;
}
.ac-actions textarea {
  resize: vertical;
  padding: var(--space-6) var(--space-8);
  border: 1px solid var(--line);
  border-radius: var(--radius-6);
  background: var(--surface);
  color: var(--fg);
  font: inherit;
  font-size: var(--fs-12);
}
.ac-btns {
  display: flex;
  gap: var(--space-8);
  justify-content: flex-end;
}
.ac-btns .btn.primary {
  background: var(--accent);
  color: var(--on-accent);
}
</style>
