# 01 — Profil dan Visi Produk AIOS V1

## 1. Esensi Produk: Apa Itu AIOS V1?

**AIOS (Artificial Intelligence Operating System for Enterprise)** adalah platform SaaS **Business AI Harness** yang dibangun di atas **Frappe Framework v16 + ERPNext** dengan antarmuka desktop **Ekasa Desk** berbasis **Vue 3**.

Berbeda dari asisten AI umum (yang hanya menjawab teks tanpa konteks operasional) dan berbeda pula dari *coding harness* (seperti Claude Code, OpenCode, atau Cline yang mengoperasikan kode sumber & terminal), **AIOS mengoperasikan proses bisnis perusahaan**. Setiap perusahaan klien yang berlangganan AIOS mendapatkan **1 dedicated site instance (`1 Client = 1 Site`)** berisi "organisasi staf ahli dan manajer AI virtual" yang terhubung langsung ke pembukuan dan operasional ERPNext perusahaan mereka sendiri.

| Dimensi | Coding AI Harness (OpenCode / Claude Code) | Business AI Harness (AIOS V1) |
|---|---|---|
| **Target Pengguna** | Software Engineer / Developer | Pemilik Bisnis, Direktur (CFO), Manajer, Staf Operasional |
| **Objek yang Dioperasikan** | File kode sumber, Git repository, Shell/Terminal | Dokumen transaksi ERP (`Sales Order`, `Sales Invoice`, `GL Entry`), Laporan Keuangan, Dokumen Bisnis |
| **Struktur Agen** | Planner, Coder, Reviewer, Researcher | **AI Manager (Orchestrator Divisi)** + **Sub-Agents Spesialis Jabatan** |
| **Sistem Ekstensi** | Konfigurasi `jsonc`, MCP Server, CLI Plugins | **UI-driven Provider/Model Routing** + **Built-in & External Business Plugins/MCP** |
| **Ruang Kerja Output** | Diff kode, file proyek lokal | **Ekasa Desk** — artefak muncul sebagai file & jendela di desktop (Approval Card, Chart Keuangan, Laporan PDF/Excel) |
| **Gerbang Keamanan** | Sandbox terminal & izin eksekusi perintah | Isolasi Database per Site (`1 Client = 1 Site`) + Isolasi Sesi `User` + **Human-in-the-Loop Draft Approval** |

---

## 2. Strategi Fokus: *Depth over Breadth* (Finance & Sales)

Dalam arsitektur besar AIOS terdapat 9 cabang divisi ERP (`planning`, `finance`, `sales`, `procurement`, `material`, `production`, `project`, `hr`, `maintenance`) serta integrasi kanal eksternal (seperti Telegram yang saat ini disimpan dalam status *hidden/dormant* untuk pengembangan masa depan).

Namun, untuk membuktikan kemampuan AIOS secara maksimal dan kritis pada tahap ini, pengembangan difokuskan secara mendalam (**deep implementation**) pada **2 cabang inti yang menjadi jantung operasional perusahaan**:

1. **Divisi Sales & Distribution (`sales`)** — ujung tombak pemasukan dan relasi pelanggan.
2. **Divisi Finance & Accounting (`finance`)** — penjaga arus kas, piutang/utang, anggaran, dan laporan keuangan.

Kedua divisi ini membentuk siklus bisnis nyata **Order-to-Cash (O2C)** yang utuh dan saling bergantung layaknya dua departemen di perusahaan sungguhan.

### 2.1. Organisasi Agen Divisi Sales (`sales`)
Dipimpin oleh **Sales AI Manager (Orchestrator)** yang mengoordinasikan 4 Sub-Agents spesialis:
- **Sales Representative (`sales-representative`):** Menangani prospek penjualan, pengecekan ketersediaan barang & harga, pembuatan draf *Quotation* dan *Sales Order*, serta memantau pencapaian target penjualan.
- **Customer Service (`customer-service`):** Memantau status pemenuhan pesanan (*Delivery Note* / pengiriman), riwayat transaksi pelanggan, dan tindak lanjut pesanan yang tertunda.
- **Sales Data Analyst (`sales-data-analyst`):** Menganalisis tren penjualan multi-periode, kontribusi per produk/pelanggan/wilayah, konsentrasi pendapatan, serta deteksi anomali penjualan.
- **Marketing Specialist (`marketing-specialist`):** Menganalisis segmentasi pelanggan bernilai tinggi (*high-value segments*), peluang *cross-sell/up-sell*, dan menyusun materi/rekomendasi kampanye berbasis data transaksi nyata.

### 2.2. Organisasi Agen Divisi Finance (`finance`)
Dipimpin oleh **Finance AI Manager (Orchestrator)** yang mengoordinasikan 5 Sub-Agents spesialis:
- **Finance Staff (`finance-staff`):** Menangani pencatatan operasional harian—memeriksa status tagihan (*Sales Invoice* / *Purchase Invoice*), menyiapkan draf pencatatan pembayaran (*Payment Entry*), dan draf jurnal umum (*Journal Entry*).
- **Treasurer (`treasurer`):** Mengawasi likuiditas harian, umur piutang tertagih (*Accounts Receivable Aging*), utang jatuh tempo (*Accounts Payable Aging*), dan risiko gagal bayar per pelanggan.
- **Budgeting Staff (`budgeting-staff`):** Memantau realisasi pengeluaran terhadap anggaran per pos/pemasok, menghitung variansi (*over/under budget*), dan mendeteksi risiko konsentrasi biaya.
- **Financial Analyst (`financial-analyst`):** Melakukan analisis kuantitatif laporan keuangan (*Profit & Loss*, *Balance Sheet*, *General Ledger*), margin profitabilitas, serta rasio pertumbuhan antar-periode.
- **CFO (`cfo`):** Menyintesis temuan dari seluruh staf Finance (likuiditas dari *Treasurer*, variansi dari *Budgeting*, tren dari *Financial Analyst*) menjadi ringkasan eksekutif, peringatan risiko strategis, dan rekomendasi keputusan bagi pimpinan perusahaan.

---

## 3. Kolaborasi Agen Nyata (Intra-Divisi & Lintas-Divisi)

Target utama AIOS adalah setiap cabang bekerja **seperti perusahaan mandiri yang hidup**, bukan sekadar kumpulan prompt statis yang saling melempar tanggung jawab:

1. **Delegasi Nyata di Dalam Divisi (Orchestrator → Sub-Agent):**
   - Ketika pengguna bertanya kepada **Finance AI Manager**, Orchestrator dapat memecah masalah dan memanggil Sub-Agent spesifik (misalnya meminta *Treasurer* menarik data piutang jatuh tempo sekaligus meminta *Financial Analyst* menghitung margin bulan berjalan).
   - Setiap panggilan delegasi benar-benar menjalankan *agent execution loop* milik Sub-Agent tersebut beserta tool-nya, lalu mengembalikan hasilnya ke Orchestrator untuk disintesis.
2. **Konsultasi Lintas Divisi (Sales ↔ Finance via Swarm Router):**
   - Sebelum **Sales Representative / Sales Manager** menerbitkan draf *Sales Order* bernilai besar untuk seorang pelanggan, divisi Sales secara otonom berkonsultasi ke divisi **Finance** (*Treasurer*) untuk memverifikasi sisa plafon kredit (*credit limit*) dan memastikan pelanggan tersebut tidak memiliki tagihan *overdue* yang macet.
3. **Transparansi Visual Penuh di UI (*Live Agent Trace*):**
   - Seluruh proses delegasi dan komunikasi antar-agen **tidak terjadi secara diam-diam di belakang layar**.
   - UI menampilkan panel/kartu jejak komunikasi agen secara *real-time* (menggunakan tipografi dan ikon vektor minimalis tanpa emoji dekoratif), sehingga pengguna dapat membuka dan melihat:
     - Instruksi/prompt yang dikirim Orchestrator ke Sub-Agent.
     - Tool/plugin ERPNext apa yang dieksekusi oleh Sub-Agent.
     - Data dan analisis yang dikembalikan Sub-Agent kepada Orchestrator.

---

## 4. Model Multi-Tenant (`1 Client = 1 Site`) & Peta Peran Lintas Site

AIOS V1 menerapkan arsitektur **Site-Level Multi-Tenancy (`1 Client = 1 Site`)** menggunakan kemampuan native Frappe Bench (`dns_multitenant`):
- Setiap perusahaan klien beroperasi di *site* Frappe tersendiri (dengan database MariaDB terpisah).
- Di dalam setiap *site*, seluruh atribut pengguna dan kuota langsung melekat pada DocType **`User`** bawaan Frappe (tanpa membutuhkan DocType perantara `AIOS Tenant`).
- Pengelolaan lintas klien (provisioning *site*, persetujuan pendaftaran, undangan pengguna, kuota, monitoring) dilakukan dari satu **Developer Control Plane** — *site* Frappe khusus developer — yang berkomunikasi dengan tiap *site* klien lewat **Control API** (`docs/03` §1.4, `docs/04` Alur 6).

Pengguna berinteraksi melalui dua permukaan aplikasi (pengguna klien tidak pernah diarahkan ke halaman Frappe Desk):

| Karakteristik | Developer Control Plane (site developer) | Ekasa Desk (site klien) |
|---|---|---|
| **Bentuk** | Dashboard operasional berbasis halaman | **Desktop OS** — boot, sign-in, taskbar, jendela, panel agent (`docs/08`) |
| **Target Pengguna** | `AIOS Admin` — operator AIOS (bukan `Administrator`) | Pebisnis / Direktur / Staf Perusahaan Klien |
| **Role & Tipe User Frappe** | Role `AIOS Admin` (`AIOS Admin Profile`, target `desk_access = 0`); hanya ada di site developer | Role `AIOS Client` (`AIOS Client Profile`, tipe `Website User` dengan `desk_access = 0`); tidak ada role `AIOS Admin` di site klien |
| **Kewenangan Utama** | • Mendaftarkan & mem-provision *site* klien baru (registry `AIOS Managed Site`)<br>• Menyetujui pendaftaran mandiri & menerbitkan undangan pengguna (tautan set-password sekali pakai)<br>• Mengelola status (`aios_status`) `User` lintas site<br>• Memonitor pemakaian token & kesehatan site klien<br>• UI pengaturan Provider LLM, Model Routing, dan Plugin/MCP — data tetap tersimpan di site klien | • Bekerja di desktop: membuka modul Finance & Sales, melihat daftar dokumen dan kartu angka dari ERPNext<br>• Berdialog dengan agent di panel samping, dan membuka **Live Agent Trace** untuk melihat langkah, tool, dan hasilnya<br>• Membuka artefak (laporan, grafik, spreadsheet) sebagai jendela di desktop<br>• Menyetujui (**Approve**) atau menolak (**Reject**) draf transaksi bisnis sebelum masuk ke ERPNext |

> **Peran Khusus `Administrator` (Root Frappe) & Pendaftaran Skema via Hooks:**
> Akun `Administrator` bawaan Frappe digunakan untuk administrasi tingkat sistem/bench dan **tidak pernah dimodifikasi atau dibatasi** — di luar itu seluruh operasi harian dijalankan `AIOS Admin` dari Developer Control Plane. Jalur programatik ke *site* klien memakai role layanan **`AIOS Control`** (bukan `AIOS Admin`, bukan `Administrator`). Seluruh ekstensi skema AIOS pada DocType inti `User` (seperti `aios_persona`, `aios_status`, `aios_token_limit`, `aios_tokens_used`) serta pembuatan Role & Role Profile di-script secara otomatis di Python pada hook **`after_install` dan `after_migrate`** di `hooks.py` menggunakan fungsi resmi `create_custom_fields`.
