<template>
  <b-modal v-model="visible" size="lg" scrollable hide-footer :title="detail?.title || 'Detail'" @hidden="onHidden">
    <div v-if="loading" class="text-center py-5"><b-spinner variant="primary" /></div>
    <b-alert v-else-if="error" :model-value="true" variant="danger">{{ error }}</b-alert>
    <template v-else-if="detail">
      <div class="d-flex flex-wrap align-items-center gap-2 mb-3">
        <b-button v-if="stack.length" size="sm" variant="outline-dark" @click="back">
          <i class="iconoir-arrow-left me-1"></i> Kembali
        </b-button>
        <span class="badge" :class="`bg-${detail.status.variant}`">{{ detail.status.label }}</span>
        <span v-if="detail.subtitle" class="fw-semibold">{{ detail.subtitle }}</span>
        <span class="ms-auto d-flex gap-2">
          <b-button v-if="detail.print_kind" size="sm" variant="outline-primary" :disabled="printing" @click="doPrint">
            <b-spinner v-if="printing" small class="me-1" /><i v-else class="iconoir-printer me-1"></i>
            Cetak {{ detail.print_kind === "kwitansi" ? "Kwitansi" : "Tagihan" }}
          </b-button>
          <slot name="actions" :detail="detail" />
        </span>
      </div>

      <dl class="row mb-3 tx-fields">
        <template v-for="f in shownFields" :key="f.label">
          <dt class="col-5 col-md-4 fw-semibold">{{ f.label }}</dt>
          <dd class="col-7 col-md-8">
            <a v-if="f.type === 'file'" :href="String(f.value)" target="_blank" rel="noopener">Lihat lampiran</a>
            <template v-else>{{ format(f.value, f.type) }}</template>
          </dd>
        </template>
      </dl>

      <div v-for="t in detail.tables" :key="t.title" class="mb-3">
        <h6 class="fw-bold mb-2">{{ t.title }}</h6>
        <div v-if="!t.rows.length" class="small text-muted border rounded p-2">{{ t.empty || "Tidak ada data." }}</div>
        <div v-else class="table-responsive">
          <table class="table table-sm align-middle mb-0">
            <thead class="table-light">
              <tr>
                <th v-for="c in t.columns" :key="c.key" :class="{ 'text-end': c.type === 'currency' || c.type === 'number' }">{{ c.label }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(r, i) in t.rows" :key="i">
                <td v-for="c in t.columns" :key="c.key" :class="{ 'text-end text-nowrap': c.type === 'currency' || c.type === 'number' }">
                  <a v-if="c.link && r[c.key]" href="#" class="fw-semibold" @click.prevent="open(c.link, r[c.key])">{{ r[c.key] }}</a>
                  <template v-else>{{ format(r[c.key], c.type) }}</template>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div v-if="detail.totals.length" class="border-top pt-2 ms-auto tx-totals">
        <div v-for="t in detail.totals" :key="t.label" class="d-flex justify-content-between" :class="{ 'fw-bold': t.strong }">
          <span>{{ t.label }}</span><span>{{ format(t.value, "currency") }}</span>
        </div>
      </div>
    </template>
  </b-modal>
</template>

<script setup lang="ts">
/**
 * Detail dokumen transaksi (Sales Invoice, Payment Entry, Pengajuan Pembayaran, Jurnal) — dibuka dengan mengklik baris
 * di daftar mana pun (keputusan pemilik 11 Nov 2026). Nomor dokumen terkait di tabel dapat diklik (tumpukan + Kembali).
 * Pemakaian: <TransactionDetailModal v-model="show" doctype="Sales Invoice" :name="fee.name" />
 */
import { computed, ref, watch } from "vue";
import Swal from "sweetalert2";
import { extractErrorMessage } from "@/features/students/api";
import { getTransactionDetail, printInvoice, type TransactionDetail, type TransactionDoctype } from "./api";

const props = defineProps<{ modelValue: boolean; doctype: TransactionDoctype | null; name: string | null }>();
const emit = defineEmits<{ (e: "update:modelValue", v: boolean): void }>();

const visible = computed({ get: () => props.modelValue, set: (v) => emit("update:modelValue", v) });
const detail = ref<TransactionDetail | null>(null);
const loading = ref(false);
const error = ref("");
const printing = ref(false);
const stack = ref<{ doctype: TransactionDoctype; name: string }[]>([]);
let current: { doctype: TransactionDoctype; name: string } | null = null;

const shownFields = computed(() => (detail.value?.fields || []).filter((f) => f.value !== null && f.value !== "" && f.value !== undefined));

async function load(doctype: TransactionDoctype, name: string) {
  current = { doctype, name };
  loading.value = true;
  error.value = "";
  try {
    detail.value = await getTransactionDetail(doctype, name);
  } catch (err) {
    detail.value = null;
    error.value = extractErrorMessage(err);
  } finally {
    loading.value = false;
  }
}

function open(doctype: TransactionDoctype, name: string) {
  if (current) stack.value.push(current);
  load(doctype, name);
}

function back() {
  const prev = stack.value.pop();
  if (prev) load(prev.doctype, prev.name);
}

watch(
  () => [props.modelValue, props.doctype, props.name] as const,
  ([show, doctype, name]) => {
    if (show && doctype && name) {
      stack.value = [];
      load(doctype, name);
    }
  },
  { immediate: true },
);

function onHidden() {
  detail.value = null;
  stack.value = [];
  current = null;
}

async function doPrint() {
  if (!detail.value) return;
  printing.value = true;
  try {
    await printInvoice(detail.value.name);
  } catch (err) {
    Swal.fire({ icon: "error", title: "Gagal mencetak", text: extractErrorMessage(err) });
  } finally {
    printing.value = false;
  }
}

const rupiah = new Intl.NumberFormat("id-ID");
function format(value: unknown, type?: string) {
  if (value === null || value === undefined || value === "") return "-";
  if (type === "currency") return `Rp ${rupiah.format(Number(value) || 0)}`;
  if (type === "date") return new Date(String(value)).toLocaleDateString("id-ID", { day: "2-digit", month: "short", year: "numeric" });
  if (type === "datetime") return new Date(String(value).replace(" ", "T")).toLocaleString("id-ID", { dateStyle: "medium", timeStyle: "short" });
  if (type === "number") return rupiah.format(Number(value) || 0);
  return String(value);
}
</script>

<style scoped>
.tx-fields dt,
.tx-fields dd {
  margin-bottom: 0.35rem;
}
.tx-totals {
  max-width: 340px;
}
</style>
