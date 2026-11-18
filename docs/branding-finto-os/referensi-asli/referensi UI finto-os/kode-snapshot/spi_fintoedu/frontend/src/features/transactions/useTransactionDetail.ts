import { reactive } from "vue";
import type { TransactionDoctype } from "./api";

/**
 * State bersama untuk TransactionDetailModal: klik baris transaksi → detail (keputusan pemilik 11 Nov 2026).
 *   const tx = useTransactionDetail();
 *   <tr class="tx-row" tabindex="0" @click="tx.open('Sales Invoice', fee.name)" @keydown.enter="tx.open(...)">
 *   <TransactionDetailModal v-model="tx.show" :doctype="tx.doctype" :name="tx.name" />
 * Sel berisi tombol/tautan lain: @click.stop agar tidak ikut membuka detail.
 */
export function useTransactionDetail() {
  const state = reactive({
    show: false,
    doctype: null as TransactionDoctype | null,
    name: null as string | null,
    open(doctype: TransactionDoctype, name: string | null | undefined) {
      if (!name) return;
      state.doctype = doctype;
      state.name = name;
      state.show = true;
    },
  });
  return state;
}
