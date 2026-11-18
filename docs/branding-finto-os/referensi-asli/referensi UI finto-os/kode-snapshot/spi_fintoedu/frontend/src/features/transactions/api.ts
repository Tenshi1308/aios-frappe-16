import HttpClient from "@/helpers/http-client";

/** Detail dokumen transaksi (spi_fintoedu.api.transaction_detail, spec TRANSACTION_DETAIL.md). */
export type TransactionDoctype =
  | "Sales Invoice"
  | "Payment Entry"
  | "SPI Payment Submission"
  | "Journal Entry"
  | "Payroll Entry"
  | "Additional Salary"
  | "SPI Teacher Fee Payout"
  | "Student Transfer";

export interface TransactionField {
  label: string;
  value: string | number | null;
  type: "text" | "date" | "datetime" | "currency" | "file";
}

export interface TransactionColumn {
  key: string;
  label: string;
  type?: "date" | "currency" | "number";
  /** Nilai sel = nama dokumen DocType ini → dapat diklik untuk membuka detailnya. */
  link?: TransactionDoctype;
}

export interface TransactionDetail {
  doctype: TransactionDoctype;
  name: string;
  title: string;
  subtitle?: string | null;
  status: { label: string; variant: string };
  fields: TransactionField[];
  tables: { title: string; empty?: string; columns: TransactionColumn[]; rows: Record<string, any>[] }[];
  totals: { label: string; value: number; strong?: boolean }[];
  print_kind: "tagihan" | "kwitansi" | null;
}

export async function getTransactionDetail(doctype: TransactionDoctype, name: string) {
  const res = await HttpClient.get<{ message: TransactionDetail }>(
    "/api/method/spi_fintoedu.api.transaction_detail.get_transaction_detail",
    { params: { doctype, name } },
  );
  return res.data.message;
}

/** Cetak Tagihan/Kwitansi: jendela dibuka sinkron (tidak diblokir pop-up), lalu diisi HTML dari backend. */
export async function printInvoice(invoice: string): Promise<void> {
  const win = window.open("", "_blank");
  if (!win) throw new Error("Pop-up diblokir. Izinkan pop-up untuk situs ini agar dokumen bisa dicetak.");
  win.document.write("<p style='font-family:sans-serif'>Menyiapkan dokumen…</p>");
  try {
    const res = await HttpClient.get<{ message: { html: string } }>(
      "/api/method/spi_fintoedu.api.invoice_print.get_print_html",
      { params: { invoice } },
    );
    win.document.open();
    win.document.write(res.data.message.html);
    win.document.close();
    win.focus();
    setTimeout(() => win.print(), 400);
  } catch (err) {
    win.close();
    throw err;
  }
}
