# Detail Dokumen Transaksi (klik baris)

Keputusan pemilik 11 Nov 2026: setiap Sales Invoice — dan semua DocType berjenis transaksi — di daftar mana pun dapat
**diklik untuk melihat detailnya dulu**, tidak hanya lewat tombol aksi.

## Komponen

| Bagian | Lokasi |
| --- | --- |
| Endpoint | `spi_fintoedu.api.transaction_detail.get_transaction_detail(doctype, name)` — bentuk seragam (judul, status, field, tabel, total, `print_kind`). |
| Modal | `frontend/src/features/transactions/TransactionDetailModal.vue` (nomor dokumen terkait di tabel dapat diklik; tombol Kembali; Cetak Tagihan/Kwitansi; slot `actions`). |
| State | `features/transactions/useTransactionDetail.ts` → `tx.open(doctype, name)`. |
| Gaya | `assets/scss/componets/_spi-transactions.scss`: `tr.tx-row` / `.tx-card` (kursor, hover, fokus keyboard). Sel tombol memakai `@click.stop`. Enter pada baris juga membuka detail. |

## DocType & izin (mengikuti halaman asal; tidak ada akses baru)

| DocType | Izin |
| --- | --- |
| Sales Invoice | BM/Principal/Finance/CSO (`invoice_print._scope`); murid/wali hanya tagihannya. |
| Payment Entry | sama; murid/wali hanya pembayaran anaknya. |
| SPI Payment Submission | `spp_payment._ops_scope` (antrean Pembayaran SPP). |
| Journal Entry | BM/Principal/Finance (`fee._get_company_scope`). |
| Payroll Entry, Additional Salary | `payroll._payroll_scope`. |
| SPI Teacher Fee Payout | admin honor; guru hanya miliknya (`fee_wallet._resolve_instructor`). |
| Student Transfer | cabang asal atau tujuan dalam scope finto_edu mutasi. |
| Salary Slip | memakai modal rincian slip yang sudah ada (`PayrollPage`, `MySalarySlipPage`) — barisnya kini dapat diklik. |

## Daftar yang sudah dapat diklik

Tagihan SPP (+ Ajukan Bayar dari detail), Portal Orang Tua (riwayat tagihan), Matriks SPP (nomor invoice di rincian),
Pembayaran SPP (pengajuan, pembayaran resmi, nomor alokasi & Payment Entry), Laporan Keuangan → Buku Besar (dokumen
sumber SI/PE/JE), Penggajian (Proses Gaji: kartu Payroll Entry & baris slip; Riwayat Slip; Pembayaran Gaji → jurnal;
THR/Bonus), Slip Gaji Saya, Dompet Honor (bulan yang sudah dibayar), Mutasi Siswa.

Belum: label invoice di dalam modal Ajukan/Verifikasi Pembayaran (sudah berada di dalam modal) dan pesan Swal.

**Menambah daftar baru:** `class="tx-row" tabindex="0" @click="tx.open('<DocType>', row.name)"`; DocType baru → tambah
builder + aturan izin di `transaction_detail.py` dan tipe `TransactionDoctype`.

Tes: `tests/test_transaction_detail.py`.
