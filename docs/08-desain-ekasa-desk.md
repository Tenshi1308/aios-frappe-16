# 08 — Desain Ekasa Desk (Antarmuka Desktop OS)

Dokumen ini menetapkan desain antarmuka klien AIOS: **Ekasa Desk**, sebuah *desktop OS* di browser. Sifatnya **normatif** — kode menyesuaikan dokumen ini.

Kontrak harness (trace, tool, approval) ada di `docs/02` §3 dan `docs/04` Alur 5. Dokumen ini hanya mengatur **permukaan dan tata letaknya**.

---

## 1. Konsep & Prinsip

1. **OS, bukan halaman web.** Pengguna masuk lewat layar boot dan sign-in, lalu bekerja di desktop dengan taskbar, jendela, dan panel samping — bukan deretan menu.
2. **Agent adalah warga utama.** Panel agent selalu ada. Modul dan artefak muncul sebagai jendela di desktop.
3. **Modul tetap ada.** Daftar dokumen dan kartu angka adalah nilai jual: pengguna bisa melihat data ERPNext langsung tanpa bertanya ke AI. Agent juga bisa membukakan modul.
4. **Tanpa emoji dekoratif.** Ikon garis vektor dan badge tipografi saja.
5. **Nol hardcoded.** Nama agent, nama modul, doctype, company, kuota, dan prompt saran **tidak boleh** ditulis di berkas komponen — semuanya dari backend (§7).

---

## 2. Struktur Layar

### 2.1. Boot

Layar gelap penuh dengan progres bertahap: menyambung ke site, memulihkan sesi, mengambil `frappe.boot`, memuat workspace & izin, mendaftarkan agent, membuka kanal realtime, menyiapkan desktop. Progres harus mencerminkan langkah nyata, bukan animasi palsu.

### 2.2. Sign-In

Form email + password, ditambah tautan ke pendaftaran mandiri. Kegagalan menampilkan pesan aman (tanpa detail internal). Setelah sukses, lanjut ke desktop sesuai peran.

### 2.3. Desktop

- **Taskbar** di bawah: tombol mulai, pencarian, daftar agent, jam, indikator status koneksi.
- **Area desktop**: jendela-jendela yang bisa dibuka, dipindah, diperkecil, dan ditutup.
- **Flyout**: pencarian (`Ctrl+K`) dan daftar agent (`Ctrl+J`). `Esc` menutup.
- **Tema**: terang dan gelap, mengikuti preferensi sistem, bisa dipaksa lewat atribut tema.

### 2.4. Panel Agent

Menempel di sisi kanan. Berisi riwayat percakapan, composer, pemilih agent, dan **Live Agent Trace** (§3). Panel bisa dilebarkan dan ditutup lewat tombol X; saat ditutup, buka lagi dari taskbar atau `Ctrl+J`. Agent tetap inti produk, jadi tidak ada mode tanpa akses agent.

#### Lampiran chat

Composer menyediakan tombol paperclip untuk memilih dan mengunggah file, menampilkan progress, chip file, error, serta aksi hapus lampiran. Client tidak pernah menampilkan atau meminta user mengetik File ID; ID hanya menjadi state internal frontend untuk mengirim `file_ids`.

Upload membuat Private `File` dengan `owner = frappe.session.user`, `is_private = 1`, `dt = "AIOS Conversation"`, dan `dn = conversation_id`. Request chat mengirim `file_ids`; backend memvalidasi kepemilikan, status private, keterikatan pada conversation yang sama, serta batas ukuran dan format yang diizinkan. Backend menyisipkan metadata file ke konteks model, lalu model dapat memanggil `document_extract(file_id)`; hasil ekstraksi tampil di chat.

Backend menolak file milik user lain, file publik, file dari conversation lain, dan file yang melampaui batas ukuran atau format. Respons ke client tidak membocorkan isi file; File ID tidak boleh muncul di pesan error maupun event — ia hanya state internal frontend.

**Status backend (H5 fase 1, `b07975f`, 2026-10-24):** endpoint upload `POST /api/chat/upload`, validasi `file_ids` sebelum konteks model dibentuk, dan binding `document_extract` ke conversation aktif sudah ada. **UI composer, chip lampiran, progress upload, dan aksi hapus chip (lokal) sudah ada di #12 fase 1 (`a4f4113`); endpoint hapus lampiran, jendela artefak, chart/Mermaid/iframe menyusul.**

**Acceptance:** client dapat melampirkan CSV, PDF, atau XLSX tanpa mengetik ID; model membaca isi file; file user lain ditolak; file publik ditolak.

---

## 3. *Live Agent Trace* di Panel Agent

Kontrak event ada di `docs/02` §3.1. Tata letaknya:

**Status implementasi:** H4 menyediakan event SSE backend untuk empat event delegasi dan `trace_cross_branch`. Event `artifact_created` Approval Card juga dikirim backend dengan `draft_id`; UI Live Agent Trace dan tampilan kartu belum dibuat dan masuk #12. File/workspace tetap H5.

1. Di bawah setiap jawaban agent ada baris ringkas: **jumlah langkah · token · durasi**, dengan tombol **Lihat detail**.
2. Menekan baris tersebut mekarkan daftar langkah (delegasi, panggilan tool, hasil).
3. Menekan satu langkah membuka isi lengkapnya: instruksi tugas, nama tool, **argumen asli**, dan hasil.
4. **Lihat detail** membuka jendela penuh di desktop.

**Wajib:** instruksi tugas, argumen tool, dan hasil terlihat apa adanya.
**Dilarang:** menampilkan *system prompt* internal AIOS (ETHOS, guard, instruksi dasar).

---

## 4. Agent

Daftar agent berasal dari backend (`registry.py`), bukan dari berkas komponen. Setiap agent punya nama, deskripsi singkat, warna aksen, dan saran pertanyaan — semuanya dari API.

Agent dapat membuka modul dan membuat artefak. Aksi tulis **tidak pernah** langsung ke ERPNext: selalu lewat `Pending Action Draft` dan persetujuan manusia (`docs/04` Alur 5).

---

## 5. Artefak sebagai File & Jendela

File yang dibuat agent disimpan sebagai Private `File` (`docs/02` §3.2) dan tampil sebagai **berkas di desktop**. Approval Card H4 adalah event backend virtual; UI #12 mengambil detail dari `get_draft`, dan kartu tidak membuat `File`:

| Jenis | Tampilan |
|---|---|
| Approval Card | Event backend H4; jendela kartu persetujuan di UI #12 (prioritas tertinggi), tanpa `File` |
| Tabel & grafik | Jendela data interaktif |
| Dokumen eksekutif + Mermaid | Jendela dokumen, bisa cetak/ekspor PDF |
| Spreadsheet `.xlsx` / `.csv` | Jendela preview + unduh |
| Presentasi HTML | Jendela slide terisolasi |

Berkas yang dibuat pada satu percakapan hanya terlihat oleh pemilik percakapan tersebut. **Status backend (H5 fase 1, `b07975f`):** file privat `.csv`/`.xlsx`/`.md`/`.pdf` dibuat oleh `workspace_create_file` dan event `artifact_created` (`FILE`) sudah dikirim backend; jendela artefak, grafik interaktif, Mermaid, dan iframe menyusul di #12.

---

## 6. Modul

Modul menampilkan **daftar dokumen** dan **kartu angka** dari ERPNext. Datanya dibaca langsung dari ERPNext site klien dengan izin user yang sedang login — tidak ada database perantara.

- Modul dibuka dari taskbar/pencarian, **atau** oleh agent saat diminta ("buka Sales Invoice").
- Daftar modul, ikon, warna, dan doctype-nya berasal dari backend (§7).
- Modul bersifat **baca saja**. Penulisan tetap lewat approval.
- Angka pada kartu adalah agregat yang dihitung server, bukan dihitung di browser.

---

## 7. Aturan *Zero Hardcoded*

| Data | Sumber |
|---|---|
| Daftar agent, nama, deskripsi, saran prompt | Backend (`registry.py`) |
| Daftar modul, ikon, warna, doctype | Backend |
| Company aktif, mata uang | `AIOS Setting` |
| Kuota & pemakaian token | `AIOS Setting.site_token_limit` (gerbang), `User.aios_tokens_used` (statistik) |
| Versi & URL API | `frappe.boot` / environment |

**Aturan yang bisa diuji:** tidak ada nama agent, nama modul, atau nama doctype yang ditulis sebagai teks di berkas komponen. Data contoh hanya boleh hidup di lapisan `api/mock/` dan tidak pernah diimpor jalur produksi.

**Aturan yang sama berlaku untuk gaya:** komponen dilarang menulis warna, font, bayangan, atau radius secara langsung. Semua lewat token (§8).

---

## 8. Token Visual & CSS

Dua lapis token di `styles/tokens.css`:

1. **Primitives** — nilai mentah (hex, px, font). Hanya boleh dipakai di berkas token.
2. **Semantic** — `--surface`, `--text`, `--accent`, `--ok`, `--warn`, `--bad`, `--shadow`, `--radius`. Inilah yang dipakai komponen.

Yang dijadikan token: warna, font family/ukuran/weight, radius, bayangan, blur, skala spasi, z-index, durasi animasi, tinggi taskbar, lebar panel.

Yang **tidak** perlu token: nilai sekali pakai seperti lebar kolom tabel di satu tempat.

**Pemeriksaan otomatis:** `grep -rE "#[0-9a-fA-F]{3,6}|rgba?\(" src/components/ src/views/` harus kosong.

**Gaya penulisan:** CSS *scoped* per komponen. **Tailwind tidak dipakai** — desain sudah final dan efek visualnya (glass, gradient, shadow berlapis) lebih tepat ditulis langsung.

**Aset lokal:** font dan Vue di-*bundle* sendiri. Aplikasi harus jalan tanpa internet.

---

## 9. Stack & Struktur Folder

| Bagian | Pilihan |
|---|---|
| Build | Vite |
| Framework | Vue 3 |
| Bahasa | TypeScript |
| Router | Vue Router |
| State | Pinia |
| CSS | CSS variables + scoped (tanpa Tailwind) |

```
desk/
├── index.html
├── vite.config.ts
├── tsconfig.json
└── src/
    ├── main.ts
    ├── App.vue
    ├── router/index.ts
    ├── stores/          session · agents · modules · conversations
    ├── api/
    │   ├── client.ts    frappe.call + CSRF
    │   ├── desktop.ts   bootstrap · module · list · search
    │   ├── agent.ts     chat stream (SSE)
    │   └── mock/        data contoh, tidak masuk jalur produksi
    ├── components/
    │   ├── base/        Icon · Button · Card · Badge · Table · Flyout · Window
    │   ├── shell/       BootScreen · SignIn · Taskbar · Clock · Desktop
    │   ├── agent/       AgentPanel · AgentMessage · AgentTrace · AgentComposer
    │   └── module/      ModuleWindow · ModuleCards · DocList
    ├── views/           LoginView · RegisterView · PendingView · DesktopView
    ├── styles/          tokens.css · base.css
    └── types/index.ts
```

Folder kerja bernama `desk/` selama migrasi. Setelah paritas, `frontend/` (Next.js) dihapus dan `desk/` di-*rename* menjadi `frontend/`.

---

## 10. Kontrak API Desktop

| Endpoint | Isi |
|---|---|
| `desktop.bootstrap` | `user`, `company`, `agents[]`, `modules[]`, `csrf_token` |
| `desktop.module` | kartu agregat + daftar doctype satu modul |
| `desktop.list` | baris dokumen (paging, filter) |
| `desktop.search` | hasil pencarian `Ctrl+K` |
| `desktop.chat` | stream SSE; memakai ulang dispatcher `/stream`; request membawa `file_ids[]` opsional untuk lampiran |
| `POST /api/chat/upload` | multipart `file` + `conversationId` (atau `branch` bila belum ada conversation); membuat Private `File` terikat conversation; respons `conversationId` + `attachment` (`id`, `file_name`, `file_size`, `format`) — H5 fase 1 |

Backend memvalidasi setiap ID pada `file_ids` sebagai Private `File` milik session user dan terikat ke `AIOS Conversation` yang sama dengan chat; ukuran dan format harus dalam batas yang diizinkan. File tidak valid ditolak sebelum konteks model dibentuk. `attachment.id` pada respons upload adalah ID `File` yang frontend butuhkan untuk mengirim `file_ids` — ID ini **hanya state internal frontend**: tidak ditampilkan ke user, tidak diketik user, dan tidak boleh muncul di pesan error maupun event `artifact_created`. Client tidak pernah menerima isi file melalui metadata maupun pesan error.

Semua endpoint memakai sesi Frappe yang sedang login dan tunduk pada `docs/03` §2.2. Tidak ada kredensial layanan di jalur ini.

---

## 11. Halaman yang Diport

| Halaman lama | Nasib |
|---|---|
| Login | Diport |
| Register (pendaftaran mandiri) | Diport |
| Pending provisioning | Diport |
| Workspace (`/home`) | Diganti desktop |
| Settings (kuota, persona, status) | **Masuk desktop** sebagai jendela Pengaturan |
| Onboarding koneksi DB | **Tidak diport** — adapter DB eksternal dihapus (`docs/03` §2) |
| Payment | **Tidak diport** — sudah mati |
| Dashboard developer | **Diport setelah `#11`**, bukan sekarang |

---

## 12. Batasan yang Diakui

1. **Belum ada isolasi level OS.** UI berjalan di browser; keamanan tetap di lapisan server (`docs/02` §2.3).
2. **Modul belum punya penulisan.** Semua aksi tulis lewat approval.
3. **Dashboard developer belum dibangun** — menunggu backend `#11`.
