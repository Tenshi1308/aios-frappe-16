<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { fetchDraft } from '../../api/chat';
import { useBranchesStore } from '../../stores/branches';
import { useChatStore } from '../../stores/chat';
import { useSessionStore } from '../../stores/session';
import { useUiStore } from '../../stores/ui';
import type { DraftActionResult, DraftDetail } from '../../types';
import {
  formatCurrency,
  formatDateTime,
  formatNumber,
  formatShortDate,
  prettyJson,
} from '../../utils/format';
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
const nowMs = ref(Date.now());
let expiryTimer: ReturnType<typeof setInterval> | null = null;

interface LabeledField {
  label: string;
  value: string;
}

interface ProposedItemRow {
  index: number;
  name: string;
  qtyText: string;
  rateText: string;
  subtotalText: string;
}

interface ProposedView {
  headerFields: LabeledField[];
  items: ProposedItemRow[];
  totalText: string;
  extraFields: LabeledField[];
  fallbackJson: string;
}

const CUSTOMER_INFO_MAPPED_KEYS = new Set([
  'customer_name',
  'customer_type',
  'mobile_no',
  'address',
  'contact_person',
  'payment_method',
]);

const FIELD_LABELS: Record<string, string> = {
  company: 'Perusahaan',
  customer: 'Pelanggan',
  customer_name: 'Customer',
  party_name: 'Pelanggan',
  supplier: 'Pemasok',
  delivery_date: 'Tanggal Pengiriman',
  transaction_date: 'Tanggal Transaksi',
  posting_date: 'Tanggal Posting',
  valid_till: 'Berlaku Hingga',
  schedule_date: 'Tanggal Jadwal',
  due_date: 'Jatuh Tempo',
  payment_method: 'Metode Pembayaran',
  mode_of_payment: 'Metode Pembayaran',
  voucher_type: 'Jenis Voucher',
  party_type: 'Tipe Pihak',
  party: 'Pihak',
  quotation_to: 'Penawaran Untuk',
  po_no: 'No. Referensi PO',
  remarks: 'Catatan',
  terms: 'Syarat & Ketentuan',
  paid_amount: 'Jumlah Dibayar',
  received_amount: 'Jumlah Diterima',
  selling_price_list: 'Daftar Harga',
  email_id: 'Email',
  territory: 'Wilayah',
  customer_group: 'Grup Pelanggan',
  order_type: 'Tipe Pesanan',
};

const DATE_FIELD_DEFS: Array<{ key: string; label: string }> = [
  { key: 'delivery_date', label: 'Tanggal Pengiriman' },
  { key: 'transaction_date', label: 'Tanggal Transaksi' },
  { key: 'posting_date', label: 'Tanggal Posting' },
  { key: 'valid_till', label: 'Berlaku Hingga' },
  { key: 'schedule_date', label: 'Tanggal Jadwal' },
  { key: 'due_date', label: 'Jatuh Tempo' },
];

const CURRENCY_EXTRA_KEYS = new Set([
  'paid_amount',
  'received_amount',
  'net_total',
  'base_total',
  'base_grand_total',
  'total_taxes_and_charges',
  'discount_amount',
]);

const TOTAL_KEYS = new Set(['total', 'grand_total', 'rounded_total']);

function isPlainObject(val: unknown): val is Record<string, unknown> {
  return typeof val === 'object' && val !== null && !Array.isArray(val);
}

function cleanText(val: unknown): string {
  if (typeof val === 'string') return val.trim();
  if (typeof val === 'number') return Number.isFinite(val) ? String(val) : '';
  if (typeof val === 'boolean') return val ? 'Ya' : 'Tidak';
  return '';
}

function toFiniteNumber(val: unknown): number | null {
  if (typeof val === 'number') return Number.isFinite(val) ? val : null;
  if (typeof val === 'string') {
    const trimmed = val.trim();
    if (!trimmed) return null;
    const parsed = Number(trimmed);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function parseExpiryMs(value: unknown): number | null {
  if (value instanceof Date) {
    const ms = value.getTime();
    return Number.isNaN(ms) ? null : ms;
  }
  if (typeof value !== 'string') return null;
  const trimmed = value.trim();
  if (!trimmed) return null;
  const normalized =
    trimmed.includes(' ') && !trimmed.includes('T') ? trimmed.replace(' ', 'T') : trimmed;
  const ms = Date.parse(normalized);
  return Number.isNaN(ms) ? null : ms;
}

function isPastExpiry(expiresAt: unknown, refNowMs: number): boolean {
  const ms = parseExpiryMs(expiresAt);
  return ms !== null && ms <= refNowMs;
}

function formatCustomerType(val: unknown): string {
  const text = cleanText(val);
  if (!text) return '';
  const lower = text.toLowerCase();
  if (lower === 'individual') return 'Perorangan';
  if (lower === 'company') return 'Perusahaan';
  return text;
}

function humanizeFieldKey(key: string): string {
  if (FIELD_LABELS[key]) return FIELD_LABELS[key];
  return key
    .split(/[_\s]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

function hasNonEmptyNestedValue(val: unknown): boolean {
  if (Array.isArray(val)) return val.length > 0;
  if (isPlainObject(val)) return Object.keys(val).length > 0;
  return false;
}

const EXPIRED_NOTICE = 'Draf sudah kedaluwarsa.';

function isDraftExpiredNow(refMs: number): boolean {
  const d = draft.value;
  if (!d) return false;
  if (d.status === 'EXPIRED') return true;
  if (d.status !== 'PENDING_APPROVAL') return false;
  return isPastExpiry(d.expires_at, refMs);
}

function blockIfExpired(): boolean {
  const now = Date.now();
  if (!isDraftExpiredNow(now)) return false;
  nowMs.value = now;
  confirmingReject.value = false;
  result.value = { executed: false, message: EXPIRED_NOTICE };
  return true;
}

const isPending = computed(() => draft.value?.status === 'PENDING_APPROVAL');
const isExpired = computed(() => isDraftExpiredNow(nowMs.value));
const isExecutedSalesOrder = computed(
  () =>
    draft.value?.status === 'EXECUTED' &&
    draft.value?.type === 'CREATE' &&
    payload.value?.doctype === 'Sales Order',
);
const paymentEntryName = computed(() => {
  if (result.value?.payment_entry) return result.value.payment_entry;
  const resObj = payload.value?.result as Record<string, unknown> | undefined;
  return typeof resObj?.payment_entry === 'string' ? resObj.payment_entry : '';
});

const customerFields = computed<LabeledField[]>(() => {
  const raw = payload.value?.customer_info;
  if (!isPlainObject(raw)) return [];

  const fields: LabeledField[] = [];
  const pushField = (label: string, text: string) => {
    if (text) fields.push({ label, value: text });
  };

  pushField('Customer', cleanText(raw.customer_name));
  pushField('Tipe', formatCustomerType(raw.customer_type));
  pushField('No. HP', cleanText(raw.mobile_no));
  pushField('Alamat', cleanText(raw.address));
  pushField('Contact Person', cleanText(raw.contact_person));

  for (const [key, val] of Object.entries(raw)) {
    if (CUSTOMER_INFO_MAPPED_KEYS.has(key)) continue;
    const text = cleanText(val);
    if (text) fields.push({ label: humanizeFieldKey(key), value: text });
  }

  return fields;
});

const proposedView = computed<ProposedView>(() => {
  const rawData = payload.value?.data;
  if (rawData === undefined || rawData === null) {
    return { headerFields: [], items: [], totalText: '', extraFields: [], fallbackJson: '' };
  }
  if (!isPlainObject(rawData)) {
    return {
      headerFields: [],
      items: [],
      totalText: '',
      extraFields: [],
      fallbackJson: prettyJson(rawData),
    };
  }

  const customerInfoObj = isPlainObject(payload.value?.customer_info)
    ? payload.value.customer_info
    : null;
  const resObj = isPlainObject(payload.value?.result) ? payload.value.result : null;
  const activeCurrency =
    cleanText(rawData.currency) || cleanText(resObj?.currency) || 'IDR';

  const headerFields: LabeledField[] = [];
  const handledKeys = new Set<string>(['currency']);
  const pushHeader = (label: string, val: string) => {
    if (val) headerFields.push({ label, value: val });
  };

  pushHeader('Perusahaan', cleanText(rawData.company));
  handledKeys.add('company');

  const customerVal = cleanText(rawData.customer);
  const partyVal = cleanText(rawData.party_name);
  if (customerVal) {
    pushHeader('Pelanggan', customerVal);
  } else if (partyVal) {
    pushHeader('Pelanggan', partyVal);
  }
  handledKeys.add('customer');
  handledKeys.add('party_name');

  pushHeader('Pemasok', cleanText(rawData.supplier));
  handledKeys.add('supplier');

  for (const { key, label } of DATE_FIELD_DEFS) {
    const rawDate = cleanText(rawData[key]);
    if (rawDate) pushHeader(label, formatShortDate(rawDate));
    handledKeys.add(key);
  }

  const paymentMethod =
    cleanText(rawData.payment_method) ||
    cleanText(rawData.mode_of_payment) ||
    cleanText(customerInfoObj?.payment_method);
  pushHeader('Metode Pembayaran', paymentMethod);
  handledKeys.add('payment_method');
  handledKeys.add('mode_of_payment');

  const items: ProposedItemRow[] = [];
  let computedSum = 0;
  let allSubtotalsValid = false;
  let itemsHandled = false;

  if (Array.isArray(rawData.items) && rawData.items.every(isPlainObject)) {
    itemsHandled = true;
    handledKeys.add('items');
    allSubtotalsValid = rawData.items.length > 0;

    rawData.items.forEach((it, idx) => {
      const name =
        cleanText(it.item_name) || cleanText(it.item_code) || cleanText(it.description) || '—';
      const qtyNum = toFiniteNumber(it.qty);
      const uom = cleanText(it.uom);
      const qtyText =
        qtyNum !== null ? `${formatNumber(qtyNum)}${uom ? ` ${uom}` : ''}` : '—';

      const rateNum = toFiniteNumber(it.rate);
      const rateText =
        rateNum !== null ? formatCurrency(rateNum, activeCurrency) : '—';

      const subtotalNum =
        qtyNum !== null && rateNum !== null ? qtyNum * rateNum : toFiniteNumber(it.amount);
      if (subtotalNum === null) {
        allSubtotalsValid = false;
      } else {
        computedSum += subtotalNum;
      }
      const subtotalText =
        subtotalNum !== null ? formatCurrency(subtotalNum, activeCurrency) : '—';

      items.push({ index: idx + 1, name, qtyText, rateText, subtotalText });
    });
  }

  let totalText = '';
  if (allSubtotalsValid) {
    totalText = formatCurrency(computedSum, activeCurrency);
  } else {
    const explicitTotal =
      toFiniteNumber(rawData.rounded_total) ??
      toFiniteNumber(rawData.grand_total) ??
      toFiniteNumber(rawData.total);
    if (explicitTotal !== null) {
      totalText = formatCurrency(explicitTotal, activeCurrency);
    }
  }

  const extraFields: LabeledField[] = [];
  const unmappedNested: Record<string, unknown> = {};

  for (const [key, val] of Object.entries(rawData)) {
    if (handledKeys.has(key)) continue;
    if (totalText && TOTAL_KEYS.has(key)) continue;

    if (Array.isArray(val) || isPlainObject(val)) {
      if (hasNonEmptyNestedValue(val) || (key === 'items' && !itemsHandled)) {
        unmappedNested[key] = val;
      }
      continue;
    }

    if (CURRENCY_EXTRA_KEYS.has(key) || (TOTAL_KEYS.has(key) && !totalText)) {
      const numVal = toFiniteNumber(val);
      if (numVal !== null) {
        extraFields.push({
          label: humanizeFieldKey(key),
          value: formatCurrency(numVal, activeCurrency),
        });
      }
      continue;
    }

    const text = cleanText(val);
    if (text) {
      extraFields.push({ label: humanizeFieldKey(key), value: text });
    }
  }

  return {
    headerFields,
    items,
    totalText,
    extraFields,
    fallbackJson: Object.keys(unmappedNested).length > 0 ? prettyJson(unmappedNested) : '',
  };
});

const hasProposedContent = computed(
  () =>
    proposedView.value.headerFields.length > 0 ||
    proposedView.value.items.length > 0 ||
    Boolean(proposedView.value.totalText) ||
    proposedView.value.extraFields.length > 0 ||
    Boolean(proposedView.value.fallbackJson),
);

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
  if (blockIfExpired()) return;
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
  if (blockIfExpired()) return;
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

async function confirmPayment() {
  busy.value = true;
  try {
    const res = await chat.confirmDraftCashPayment(props.draftId);
    const peName = res.payment_entry || '';
    result.value = {
      ...res,
      executed: true,
      message: res.message || `Pembayaran Cash berhasil dikonfirmasi (${peName}).`,
    };
    if (payload.value) {
      const prevRes =
        payload.value.result && typeof payload.value.result === 'object'
          ? (payload.value.result as Record<string, unknown>)
          : {};
      payload.value = {
        ...payload.value,
        result: { ...prevRes, payment_entry: peName, payment_confirmed: true },
      };
    }
  } catch (err) {
    result.value = { executed: false, message: loadErrorText(err) };
  } finally {
    busy.value = false;
  }
}

onMounted(() => {
  void load();
  expiryTimer = setInterval(() => {
    nowMs.value = Date.now();
  }, 15_000);
});

onUnmounted(() => {
  if (expiryTimer !== null) {
    clearInterval(expiryTimer);
    expiryTimer = null;
  }
});
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
        <span v-if="isExpired" class="ac-expired-badge">Kedaluwarsa</span>
      </div>

      <div v-if="payload?.before" class="ac-json">
        <b>Sebelum</b>
        <pre>{{ prettyJson(payload.before) }}</pre>
      </div>

      <section v-if="customerFields.length" class="ac-section" aria-label="Data Pelanggan Baru">
        <h3 class="ac-section-title">Data Pelanggan Baru</h3>
        <dl class="ac-dl">
          <div v-for="field in customerFields" :key="field.label" class="ac-dl-row">
            <dt>{{ field.label }}</dt>
            <dd>{{ field.value }}</dd>
          </div>
        </dl>
      </section>

      <section class="ac-section" aria-label="Data diusulkan">
        <h3 class="ac-section-title">Data diusulkan</h3>
        <template v-if="hasProposedContent">
          <dl v-if="proposedView.headerFields.length" class="ac-dl">
            <div v-for="field in proposedView.headerFields" :key="field.label" class="ac-dl-row">
              <dt>{{ field.label }}</dt>
              <dd>{{ field.value }}</dd>
            </div>
          </dl>

          <div
            v-if="proposedView.items.length"
            tabindex="0"
            role="region"
            aria-label="Daftar item diusulkan"
            class="ac-table-wrap"
          >
            <table class="ac-table">
              <thead>
                <tr>
                  <th scope="col" class="num col-no">No.</th>
                  <th scope="col">Nama Item</th>
                  <th scope="col" class="num">Jumlah</th>
                  <th scope="col" class="num">Harga Satuan</th>
                  <th scope="col" class="num">Subtotal</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="item in proposedView.items" :key="`${item.index}-${item.name}`">
                  <td class="num col-no" data-label="No.">{{ item.index }}</td>
                  <td class="item-name" data-label="Nama Item">{{ item.name }}</td>
                  <td class="num" data-label="Jumlah">{{ item.qtyText }}</td>
                  <td class="num" data-label="Harga Satuan">{{ item.rateText }}</td>
                  <td class="num subtotal-cell" data-label="Subtotal">{{ item.subtotalText }}</td>
                </tr>
              </tbody>
              <tfoot v-if="proposedView.totalText">
                <tr>
                  <td colspan="4" class="total-label">Total</td>
                  <td class="num total-value" data-label="Total">{{ proposedView.totalText }}</td>
                </tr>
              </tfoot>
            </table>
          </div>

          <div v-else-if="proposedView.totalText" class="ac-total">
            <span>Total</span>
            <strong>{{ proposedView.totalText }}</strong>
          </div>

          <dl v-if="proposedView.extraFields.length" class="ac-dl">
            <div v-for="field in proposedView.extraFields" :key="field.label" class="ac-dl-row">
              <dt>{{ field.label }}</dt>
              <dd>{{ field.value }}</dd>
            </div>
          </dl>

          <div v-if="proposedView.fallbackJson" class="ac-fallback">
            <b>Detail tambahan</b>
            <pre>{{ proposedView.fallbackJson }}</pre>
          </div>
        </template>
        <div v-else class="ac-empty">Tidak ada detail data diusulkan.</div>
      </section>

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

      <div v-if="isPending && !isExpired" class="ac-actions">
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
      <div v-else-if="isExpired" class="ac-note ac-expired" role="status">
        <span>Draf sudah kedaluwarsa.</span>
      </div>
      <div v-else class="ac-note">
        <span>Draft sudah diproses ({{ draft.status }}).</span>
        <span v-if="paymentEntryName"><b>Payment Entry:</b> {{ paymentEntryName }}</span>
      </div>

      <div v-if="isExecutedSalesOrder && !paymentEntryName" class="ac-actions">
        <div class="ac-btns">
          <button class="btn primary" :disabled="busy" @click="confirmPayment">
            {{ busy ? 'Memproses…' : 'Sudah Bayar (Cash)' }}
          </button>
        </div>
      </div>
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
.ac-section,
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
.ac-meta {
  align-items: center;
}
.ac-meta span b {
  color: var(--muted);
  font-weight: var(--fw-600);
}
.ac-expired-badge {
  padding: 1px var(--space-6);
  border: 1px solid var(--bad);
  border-radius: var(--radius-6);
  background: var(--bad-soft);
  color: var(--bad);
  font-size: var(--fs-11);
  font-weight: var(--fw-600);
}
.ac-section {
  flex-direction: column;
  flex-wrap: nowrap;
  gap: var(--space-8);
}
.ac-section-title {
  margin: 0;
  color: var(--muted);
  font-size: var(--fs-11);
  font-weight: var(--fw-600);
  text-transform: uppercase;
}
.ac-dl {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: var(--space-6) var(--space-12);
  margin: 0;
}
.ac-dl-row {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.ac-dl dt {
  color: var(--muted);
  font-size: var(--fs-11);
  font-weight: var(--fw-600);
}
.ac-dl dd {
  margin: 0;
  color: var(--fg);
  word-break: break-word;
}
.ac-table-wrap {
  max-inline-size: 100%;
  overflow: auto;
  border: 1px solid var(--line);
  border-radius: var(--radius-6);
  background: var(--surface);
  container-type: inline-size;
}
.ac-table-wrap:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.ac-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--fs-12);
  color: var(--fg);
}
.ac-table thead th {
  position: sticky;
  top: 0;
  z-index: 1;
  padding: var(--space-6) var(--space-8);
  border-bottom: 1px solid var(--line);
  background: var(--surface-2);
  color: var(--muted);
  font-size: var(--fs-11);
  font-weight: var(--fw-600);
  text-align: left;
  white-space: nowrap;
}
.ac-table tbody td,
.ac-table tfoot td {
  padding: var(--space-6) var(--space-8);
  border-bottom: 1px solid var(--line);
  vertical-align: top;
}
.ac-table tbody tr:last-child td {
  border-bottom: none;
}
.ac-table tbody tr:hover {
  background: var(--hover);
}
.ac-table tfoot td {
  border-top: 1px solid var(--line);
  border-bottom: none;
  background: var(--surface-2);
  font-weight: var(--fw-600);
}
.ac-table .num {
  text-align: right;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.ac-table th.col-no,
.ac-table td.col-no {
  width: 1%;
}
.ac-table td.item-name {
  min-width: 160px;
}
.ac-table .total-label {
  text-align: right;
  color: var(--muted);
}
.ac-table .total-value {
  color: var(--fg);
}
.ac-table .subtotal-cell {
  font-weight: var(--fw-600);
}
@container (width < 400px) {
  .ac-table thead {
    display: none;
  }
  .ac-table tbody tr,
  .ac-table tfoot tr {
    display: grid;
    grid-template-columns: minmax(92px, auto) 1fr;
    gap: var(--space-4) var(--space-8);
    padding: var(--space-8);
    border-bottom: 1px solid var(--line);
  }
  .ac-table tbody tr:last-child,
  .ac-table tfoot tr {
    border-bottom: none;
  }
  .ac-table tbody td,
  .ac-table tfoot td {
    display: contents;
    padding: 0;
    border-bottom: none;
  }
  .ac-table tbody td[data-label]::before,
  .ac-table tfoot td[data-label]::before {
    content: attr(data-label);
    color: var(--muted);
    font-size: var(--fs-11);
    font-weight: var(--fw-600);
  }
  .ac-table tfoot .total-label {
    display: none;
  }
  .ac-table .num {
    text-align: left;
    white-space: normal;
  }
  .ac-table td.item-name {
    min-width: 0;
  }
}
.ac-total {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-6) var(--space-8);
  border: 1px solid var(--line);
  border-radius: var(--radius-6);
  background: var(--surface);
  font-variant-numeric: tabular-nums;
}
.ac-empty {
  color: var(--muted);
  font-size: var(--fs-12);
}
.ac-json,
.ac-fallback {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}
.ac-json b,
.ac-fallback b {
  color: var(--muted);
  font-size: var(--fs-11);
  text-transform: uppercase;
}
.ac-json pre,
.ac-fallback pre {
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
.ac-note.ac-expired {
  border-color: var(--bad);
  background: var(--bad-soft);
  color: var(--bad);
  font-weight: var(--fw-600);
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
