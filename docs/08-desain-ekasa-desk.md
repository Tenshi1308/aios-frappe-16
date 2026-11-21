# 08 — Desain Finto Desk / Ekasa Desk (Antarmuka Desktop OS)

Dokumen ini menetapkan desain antarmuka klien AIOS: **Finto Desk / Ekasa Desk**, sebuah *desktop OS* di browser. Sifatnya **normatif** — kode menyesuaikan dokumen ini.

> **Sumber kebenaran visual:** untuk desain klasik **Ekasa Desk**, acuan visual tetap `ekasa-desk-prototype/index.html` (susunan/elemen yang tampak mengikuti prototype, sedangkan data nyata dan disiplin token CSS berlaku di `frontend/`). Untuk desain default **Finto Desk / Finto OS**, acuan normatifnya merujuk pada spesifikasi **Branding B2 + keputusan Ten 19 Nov 2026**: `0C` (Desain & Mode Warna dipisah; `Finto` default), `A3` (taskbar ikut Mode Warna — terang di Mode Terang, navy di Mode Gelap), `B3` (lockup penuh), `C1` (maskot Fino kontekstual), `D2` (boot penuh, tidak di-skip), kartu login/register/pending memakai glass transparan (`.lock-card`), favicon Finto OS, avatar Fino outfit per bidang tanpa dot badge, serta ikon desktop pindah kolom saat penuh (`base.css:720-731`).

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

Layar penuh dengan progres bertahap yang mengikuti tema & desain aktif (`--boot-*`): menyambung ke site, memulihkan sesi, mengambil `frappe.boot`, memuat workspace & izin, mendaftarkan agent, membuka kanal realtime, menyiapkan desktop. Pada desain default **Finto OS**, layar boot menampilkan lockup penuh Finto OS (`FintoMark` + wordmark `FINTO OS` dengan `--fw-300` dan `--boot-word-shadow` gaya video di `BootScreen.vue:30-35`), sapaan *"Menyalakan Finto OS…"* (`D2`: boot penuh, tidak di-skip), dan keluar dengan transisi `t-screen` (`App.vue`). Progres harus mencerminkan langkah nyata, bukan animasi palsu.

### 2.2. Sign-In

Form email + password, ditambah tautan ke pendaftaran mandiri. Kartu login/register/pending memakai permukaan glass transparan (`.lock-card` di `base.css:408-421`) dan menampilkan lockup Finto OS pada desain default. Kegagalan menampilkan pesan aman (tanpa detail internal). Setelah sukses, lanjut ke desktop sesuai peran.

### 2.3. Desktop

- **Ikon desktop** (kiri atas, kolom membungkus): **bidang ERP** (`Sales`, `Finance`, `Accounting`, `Purchasing` sesuai bidang aktif dari `modules.domains`) dengan tile besar (`.tile.xl`) berwarna `var(--domain-*)` + label di bawah, digabung bersama AI Agents, Files, dan `Tentang Finto OS` (saat desain `finto`) / `Tentang AIOS` (saat desain `ekasa`; `Classic Desk` tidak dibuat — §12 butir 4). Tata letak `.desk-icons` memakai `display: flex; flex-direction: column; flex-wrap: wrap; align-content: flex-start; gap: var(--space-6);` (`base.css:720-731`) sehingga ikon otomatis pindah ke kolom berikutnya saat tinggi layar penuh. Klik tunggal memilih ikon (state `.sel`); klik-ganda atau Enter membuka; pada layar sempit atau perangkat sentuh (`.os.narrow` / `pointer: coarse`) klik tunggal langsung membuka.
- **Jendela bidang**: membuka satu bidang menampilkan **kartu KPI** + **shortcut modul** + kartu "tanya agent" — diimplementasikan di `frontend/src/components/domain/DomainWindow.vue` (fase 3d-2, lihat §6).
- **Taskbar** di bawah: tiga kolom (`1fr auto 1fr`) yang **mengikuti Mode Warna** (`cc5b48c`: terang di Mode Terang, navy di Mode Gelap). Kiri: nama site + status + label produk (`Finto OS` / `AIOS`, `Taskbar.vue:65`). Tengah: tombol mulai, pencarian, tombol agent (menampilkan badge jumlah ringkasan proaktif Sales belum dibaca saat `proactiveUnreadCount > 0`, baik panel tertutup maupun terbuka, dan hilang setelah sesi ringkasan terbaru dibuka), tombol app yang sedang berjalan. Kanan: lonceng peringatan kanal (bell dengan badge hitungan total flag `Open` + total pesanan belum dibaca dari server, dibatasi `99+`, polling 30 detik), status koneksi, jam + tanggal. Tombol app memakai tile berwarna bidang.
- **Flyout**: pencarian (`Ctrl+K`), daftar agent (`Ctrl+J`), dan notifikasi. `Esc` menutup. Semua flyout berada di dalam `.desk-area` dan muncul di atas taskbar (`bottom: 10px`, `max-height: calc(100% - 20px)` di `base.css:1171, 1175`), lebar `min(660px, 100% - 16px)`, sudut 14px; kontainer `.toasts` memakai `bottom: 14px` (`base.css:2237`).
- **Start Menu** (§2.5): pencarian → **grid bidang** (`.mod-grid` 7 kolom) → AI agents → footer profil + tombol pengaturan + daya (Recent belum memiliki backend sehingga tidak dirender).
- **Desain & Mode Warna (dipisah — Keputusan `0C`):**
  - **Desain (`brand`):** dua opsi — `Finto Desk` (`"finto"`, **default**) dan `Ekasa Desk` (`"ekasa"`). Disimpan per-user via `desktop.brand_settings` / `desktop.save_brand_settings` (`frappe.defaults`, `desktop.py:688-718`) dan diatur di tab **Desain** pada Pengaturan (`SettingsWindow.vue`).
  - **Mode Warna (`theme`):** tiga opsi — `Automatic` (*Ikuti sistem*, default; menghapus atribut `data-theme` pada `<html>` sehingga mengikuti `prefers-color-scheme`), `Light` (`data-theme="light"`), dan `Dark` (`data-theme="dark"`). Wallpaper desktop (`tokens.css`) dan taskbar (`cc5b48c`) ikut menyesuaikan Mode Warna. Preferensi disimpan di field bawaan Frappe `User.desk_theme` lewat endpoint `frappe.core.doctype.user.user.switch_theme` dan dibaca dari `desktop.settings` (`theme.value`, `theme.options`). Saat boot (`main.ts`), `localStorage` (`aios.desk.theme`) dibaca semata-mata untuk menghilangkan kedipan awal; `User.desk_theme` dari server tetap menjadi sumber kebenaran dan menimpa cache bila berbeda.

### 2.4. Panel Agent

Menempel di sisi kanan (lebar default `410px`, jarak bawah `bottom: 10px` di dalam `.desk-area` pada `base.css:1400`, dapat di-drag-resize dari tepi kiri antara `340px` hingga `960px` dibatasi `deskW - 20`, serta mendukung mode layar penuh `.agent-panel.fullscreen` di atas taskbar). Berisi riwayat percakapan (diperbarui otomatis saat polling 30 detik mendeteksi sesi proaktif Sales baru, tanpa reload tab), composer, pemilih agent, dan **Live Agent Trace** (§3); dapat ditutup lewat tombol `X` dan dibuka lagi dari taskbar atau `Ctrl+J`. Pada layar sempit (`.os.narrow`), panel menempel tepat di atas taskbar (`bottom: 0`). Agent tetap inti produk, jadi tidak ada mode tanpa akses agent. Desktop juga mengirim ping `heartbeat` ringan tiap 60 detik saat tab aktif untuk deteksi jarak dari Desk (`DesktopView.vue`).

- **Layout hybrid & sidebar riwayat:** Pada lebar panel `>= 640px` atau mode `fullscreen` (`.agent-panel.wide`), sidebar riwayat (`260px`) tampil permanen di kiri dengan tab agent 2 kolom sejajar tanpa garis pembatas bawah (`.ap-tabs-sidebar`); pada mode sempit, daftar riwayat tampil sebagai overlay slide (`t-slide-left`). Header sidebar memuat tombol `+` untuk percakapan baru, label urutan non-interaktif (`Terbaru`/`Terlama`), tombol lipat/buka daftar (`chevron-down`/`chevron-right` dengan `<AccordionTransition>`), badge `Arsip` saat mode arsip aktif, serta menu titik tiga (`Terbaru`, `Terlama`, `Archived`/`Kembali ke aktif` via `<PopoverMenu>`). Setiap baris percakapan memiliki menu titik tiga hover/fokus (`Pin`, `Rename` inline, `Archive`, `Delete` via `<PopoverMenu>`). Kegagalan muat riwayat menampilkan `<ErrorState>` dengan pesan generik dan tombol `Coba lagi`.
- **Header panel (`.ap-head`):** Subtitle deskripsi agent disembunyikan dari judul (tersedia via atribut `title` pada tab agent). Di ujung kanan baris judul (`.ap-title`) terdapat satu tombol toggle sidebar (`.ap-head-sidebar-btn`, ikon `sidebar`) yang sejajar dengan lebar kolom sidebar saat terbuka di mode wide/fullscreen (`sidebar-open`) dan menyusut menempel ke judul saat tertutup. Di sisi kanan header hanya ada 3 tombol: menu titik tiga (`Riwayat percakapan` dan `Daftar dan riwayat draft` beserta badge jumlah draft & indikator `!` error), tombol fullscreen, dan tombol tutup (`X`).
- **Composer & tombol Stop:** `<textarea>` auto-grow hingga maksimal 5 baris (`max-height: 120px`), dengan baris ikon aksi (`.ap-input-actions`) rata kanan di bawah textarea (dikte suara Web Speech API `mic`/`mic-off`, lampiran `paperclip`, tombol kirim/stop `send`/`stop`) sehingga scrollbar kolom ketik berada di ujung kanan di atas baris ikon. Saat streaming berjalan, tombol kirim berubah menjadi tombol `Stop` yang membatalkan `AbortController` lokal dan memanggil `stop_stream` tanpa menimpa teks parsial yang sudah masuk.

#### Lampiran chat

Composer menyediakan tombol paperclip untuk memilih dan mengunggah file, menampilkan progress, chip file, error, serta aksi hapus lampiran. Client tidak pernah menampilkan atau meminta user mengetik File ID; ID hanya menjadi state internal frontend untuk mengirim `file_ids`.

Upload membuat Private `File` dengan `owner = frappe.session.user` dan `is_private = 1`. Sebelum pesan dikirim, file tetap tertaut langsung ke `AIOS Conversation`; setelah dikirim, backend memakai attachment bawaan Frappe untuk menautkan File ke `AIOS Message` milik user. File yang dibuat agent juga ditautkan ke pesan agent. Conversation tetap dapat ditentukan lewat `AIOS Message.conversation`, tanpa schema baru. Request chat mengirim `file_ids`; backend memvalidasi kepemilikan, status private, percakapan induk, serta batas ukuran dan format yang diizinkan. Backend menyisipkan metadata file ke konteks model, lalu model dapat memanggil `document_extract(file_id)`; hasil ekstraksi tampil di chat.

File tampil sebagai chip langsung di bawah pesan yang mengunggah atau membuatnya. File lama yang masih tertaut langsung ke `AIOS Conversation` tidak dihapus dan ditampilkan dalam satu entri khusus di alur chat, dengan keterangan bahwa pesan asalnya tidak tercatat.

Backend menolak file milik user lain, file publik, file dari conversation lain, dan file yang melampaui batas ukuran atau format. Respons ke client tidak membocorkan isi file; File ID tidak boleh muncul di pesan error maupun event — ia hanya state internal frontend.

**Status backend:** endpoint upload `POST /api/method/aios_v1.api.chat.upload_file`, validasi `file_ids` sebelum konteks model dibentuk, dan binding `document_extract` ke conversation aktif tersedia sejak H5 fase 1 (`b07975f`). Revisi 46 menautkan unggahan dan file agent ke pesan terkait melalui attachment Frappe dan menjaga akses dokumen di cakupan conversation. **UI:** composer, chip lampiran, progress upload, dan aksi hapus chip (lokal) ada sejak #12 fase 1 (`a4f4113`); revisi 46 menampilkan chip file per pesan dan menyediakan entri untuk file historis tanpa pesan asal. Belum ada endpoint hapus lampiran.

**Acceptance:** client dapat melampirkan CSV, PDF, atau XLSX tanpa mengetik ID; model membaca isi file; file user lain ditolak; file publik ditolak.

---

### 2.5. Start Menu

Susunan dari atas ke bawah, sesuai prototype:

1. **Tombol pencarian** selebar flyout, ikon + teks + `kbd` `Ctrl K`.
2. **Grid bidang** — header `Bidang` + jumlah bidang aktif, lalu `.mod-grid` (`display:grid; grid-template-columns:repeat(7,1fr); gap:4px`) berisi tombol `.mod` (tile 44px `.tile.lg` dengan background `var(--domain-*)`, label 12px di bawah, `flex-direction:column`, `align-items:center`). Pada desain default `finto` (`isFintoBrand`), ikon baris **Bidang** menggunakan `<AgentAvatar :branch-key="d.key" :name="d.label" size="lg" />` (avatar Fino per bidang), dengan fallback `<AppIcon>` untuk desain klasik `ekasa`. Klik tombol bidang langsung memanggil `modules.openDomain(key)`. **Ini bukan pill agent** — memakai grid bidang tersendiri; blok pill modul lama telah dipindahkan sepenuhnya ke dalam jendela bidang.
3. **AI agents** — deretan pill (`.agent-pill`) memakai `AgentAvatar.vue`: pada desain default `finto` menampilkan **avatar maskot Fino dengan outfit per bidang tanpa dot badge** (`fino-avatar`), dan pada desain klasik `ekasa` memakai inisial berwarna per cabang (`.agent-dot`).
4. **Recent** — dua kolom di prototype (tile + nama dokumen + subteks). **Status:** saat ini belum ada endpoint backend untuk riwayat dokumen/Recent, sehingga section ini tidak dirender di UI untuk mencegah data rekaan/palsu.
5. **Footer** — avatar + nama + peran · site; di kanan tombol Pengaturan dan tombol daya (Kunci / Muat ulang / Keluar).

---

## 3. *Live Agent Trace* di Panel Agent

Kontrak event ada di `docs/02` §3.1. Tata letaknya:

**Status implementasi:** H4 menyediakan event SSE backend untuk empat event delegasi, `trace_cross_branch`, dan `artifact_created`; #12 fase 2a menambah trace tool Orchestrator (`agent = "Orchestrator"`) serta kartu dari Sub-Agent. UI #12 fase 2a: blok trace **live di atas bubble jawaban** (bertumbuh tiap event, detail inline per langkah, mengecil jadi baris ringkas setelah `done`) dan jendela kartu persetujuan (get_draft + Setujui/Tolak + daftar draft pending `list_pending_drafts`; kartu dibuka setelah `done`). Jendela artefak file tetap menyusul (fase 2b).

1. **Selagi jawaban mengalir**, blok trace tampil **di atas bubble jawaban** bergaya *activity feed* (flat, seperti harness populer): header **"Working for …"** dengan timer hidup, tiap event menjadi **item berikon** (delegasi/peran, tool, hasil, konsultasi) dengan subteks ringkas dari argumen, durasi per item dihitung klien, dan item terakhir ber-status berjalan (spinner).
2. Setelah stream selesai, blok mengecil menjadi baris ringkas di atas jawaban: **jumlah langkah · token · durasi**, dengan tombol **Lihat detail**.
3. Expand menampilkan daftar item; **tiap item terbuka inline** di blok trace: instruksi tugas, nama tool, **argumen asli**, dan hasil.
4. Tidak ada jendela detail trace — semua detail inline; jendela desktop dipakai untuk Approval Card dan daftar persetujuan. Tidak ada item "thought" — model tidak mengirim reasoning via stream.

**Wajib:** instruksi tugas, argumen tool, dan hasil terlihat apa adanya.
**Dilarang:** menampilkan *system prompt* internal AIOS (ETHOS, guard, instruksi dasar).

---

## 4. Agent

Daftar agent berasal dari backend (`registry.py`), bukan dari berkas komponen. Setiap agent punya nama, deskripsi singkat, warna aksen, dan saran pertanyaan — semuanya dari API.

Agent dapat membuka modul dan membuat artefak. Aksi tulis **tidak pernah** langsung ke ERPNext: selalu lewat `Pending Action Draft` dan persetujuan manusia (`docs/04` Alur 5).

---

## 5. Artefak sebagai File & Jendela

File yang dibuat agent disimpan sebagai Private `File` (`docs/02` §3.2) dan tampil sebagai **berkas di desktop**. Approval Card H4 adalah event backend virtual; UI #12 fase 2a mengambil detail dari `get_draft` (jendela kartu dengan Setujui/Tolak, termasuk tampilan read-only blok **Data Pelanggan Baru** dari `payload.customer_info` untuk pesanan tamu, serta penanganan hasil gagal `executed:false` yang dijelaskan dengan code+message di mana draf tetap `APPROVED` dan staf dapat melakukan retry eksekusi atau menolak via `reject_draft`), daftar draft pending maupun riwayat lewat `list_pending_drafts`, dan kartu tidak membuat `File`. Jendela `PendingDraftsWindow` menyediakan tab **Menunggu** dan tab **Riwayat** (sub-filter `Semua`, `Disetujui`, `Dieksekusi`, `Ditolak` beserta status, tanggal, dan tautan dokumen untuk draft `EXECUTED`), menampilkan status memuat, daftar kartu, dan kondisi kosong ("Tidak ada draft yang menunggu persetujuan.") hanya bila pemanggilan berhasil; bila pemanggilan gagal, error tidak ditelan melainkan ditampilkan memakai `<ErrorState>` (`role="alert"`) dengan tombol coba lagi, dilaporkan ke DocType `Error Log` via `log_client_error`, serta memunculkan badge indikator `!` di tombol menu header Agent Panel:

| Jenis | Tampilan |
|---|---|
| Approval Card | Event backend H4; jendela kartu persetujuan di UI #12 (prioritas tertinggi), tanpa `File` |
| Tabel & grafik | Jendela data interaktif |
| Dokumen eksekutif + Mermaid | Jendela dokumen, bisa cetak/ekspor PDF |
| Spreadsheet `.xlsx` / `.csv` | Jendela preview + unduh — **ter implement #12 fase 2b (diperkaya)**: `.csv` dirender sebagai **tabel** (Papa Parse, header sticky), `.md` dirender **markdown** (markdown-it `html:false` + DOMPurify), `.pdf` embed iframe, `.xlsx` dirender sebagai **tabel** (SheetJS, sheet pertama), format lain hanya metadata + unduh; file > 2 MB tidak di-fetch; tombol unduh memakai `file_url` |
| Presentasi HTML | Jendela slide terisolasi |

Berkas yang dibuat pada satu percakapan hanya terlihat oleh pemilik percakapan tersebut. **Status backend (H5 fase 1, `b07975f` + revisi 46):** file privat `.csv`/`.xlsx`/`.md`/`.pdf` dibuat oleh `workspace_create_file`, dikaitkan dengan pesan agent melalui relasi attachment Frappe, dan event `artifact_created` (`FILE`) dikirim backend. File yang diunggah user dikaitkan ke pesan user saat dikirim; unggahan yang belum dikirim dan file historis tetap tertaut langsung ke conversation. Relasi pesan dan chip file tersimpan di server, sehingga tampil lagi setelah reload. **Jendela artefak FILE ada di #12 fase 2b** (chip dibuka manual, tidak auto-open saat event; pratinjau `.csv`/`.xlsx` tabel, `.md` markdown tersanitasi, `.pdf` embed iframe; file > 2 MB tanpa fetch). **Bubble jawaban agent merender markdown penuh** (markdown-it `html:false` + DOMPurify via `v-html` — persetujuan owner mengganti guard no-v-html lama). Grafik interaktif, Mermaid, dan iframe presentasi menyusul.

File yang sudah ada sebelum relasi per pesan diterapkan tetap ditampilkan sebagai entri “File lama dari percakapan ini; pesan asal tidak tercatat.” Sistem tidak memindahkan byte file atau menghapus/mengubah file lama secara destruktif.

### File Explorer

Jendela **Files** menyediakan Explorer baca-saja dengan tree virtual `root → cabang → percakapan → file`. Tree dibentuk dari `AIOS Conversation` dan `File`; ini representasi relasi percakapan, bukan struktur folder fisik. File tetap berada di `Home/Attachments`. Explorer menampilkan file percakapan milik user pada **cabang yang aktif** — sejak Batch B (21 Nov 2026) `list_my_files` menyaring percakapan ke cabang yang terlihat (`visible_branch_keys`, `lib/workspace.py:155-163`; D6: file percakapan cabang mati disembunyikan, bukan dihapus, dan muncul kembali saat cabang dinyalakan) — mencakup unggahan lampiran dan artefak agent karena DocType `File` tidak membedakan kedua asal tersebut.

Backend hanya mengembalikan file privat milik user yang terikat ke percakapan miliknya, dan mengecualikan baris folder. Payload listing Explorer dan detail percakapan boleh memuat `file_id` (`File.name`) sebagai identitas row internal; UI tidak menampilkannya. `file_url` tetap locator yang dipakai jendela `ArtifactWindow` untuk preview dan unduh. Payload tidak memuat path filesystem atau isi file. Event SSE `artifact_created` tetap tidak memuat `file_id`.

Explorer tidak mengubah, memindahkan, menghapus, atau membagikan file. Unduh memenuhi kebutuhan share. Rename dan hapus file adalah fase berikut dan memerlukan mutasi `File` serta audit trail.

---

## 6. Bidang, Modul & Jendela

### 6.1. Dua lapis: bidang lalu modul

Tampilan mengikuti prototype yang memakai **dua lapis**, dan keduanya tidak boleh dicampur:

1. **Bidang** (*domain*) — kelompok kerja tingkat atas, mis. `Sales`, `Finance`, `Inventory`, `Reports`. Satu bidang = satu ikon desktop + satu entri grid di Start Menu. Membuka bidang menampilkan **jendela bidang** berisi kartu KPI, daftar shortcut modul, dan kartu "tanya agent". Ini yang digambarkan prototype sebagai *workspace* ERPNext (`Accounting`, `Selling`, `Stock`, dst).
2. **Modul** — daftar dokumen satu DocType di dalam bidang, mis. `Sales Invoice` di dalam `Sales`. Klik shortcut membuka tampilan daftar; breadcrumb kembali ke bidang.

Jendela bidang (window ID `domain:<key>`, diimplementasikan di `frontend/src/components/domain/DomainWindow.vue`) merender:
- **Header ringkas**: ikon bidang + label + subteks "Bidang · Baca saja" + tombol refresh (`.domain-refresh`).
- **Kartu KPI** (`.domain-cards`, grid `auto-fit minmax(170px, 1fr)`): tiap kartu (`.domain-card`) berisi label (`.domain-card-label`) dan nilai angka (`.domain-card-value`). Angka dihitung **server** via agregat `desktop.domain()`, klien hanya memformat (angka pemisah ribuan atau mata uang dengan currency response).
- **Shortcut** (`.domain-shortcuts`): satu tombol per modul anggota (`.domain-shortcut`), berisi ikon + label + jumlah baris dokumen (`row_count`), klik memanggil `modules.openModule(key)` untuk membuka jendela modul yang sudah ada.
- **Kartu agent** (`.domain-ask`): avatar agent pemilik bidang (`AgentAvatar.vue`, dipakai juga di `DomainWindow.vue` dan `SearchFlyout.vue`) + nama agent + dua saran prompt (`.chip`); klik prompt langsung mengirim pesan ke agent terkait dan membuka panel chat, atau klik "Tanya agent" membuka panel chat di cabang tersebut.

Jendela modul (window ID `module:<key>`) mempertahankan kontrak yang sudah ada: header + refresh, form filter sesuai deklarasi backend (`date_from`, `date_to`, `status`, `party`), tabel kolom dari server, navigasi halaman.

### 6.2. Katalog server-owned

Daftar bidang dan modul berasal dari backend (§7), bukan dari komponen. Katalog modul ada di `aios_v1/lib/desktop_modules.py` (**17 modul**: `sales_invoice`, `sales_order`, `quotation`, `delivery_note`, `item_price`, `customer`, `item`, `purchase_invoice`, `payment_entry`, `supplier`, `journal_entry`, `gl_entry`, `account`, `company`, `purchase_order`, `purchase_receipt`, `supplier_quotation`); definisi bidang beserta KPI-nya ada di `aios_v1/lib/desktop_domains.py` (11 bidang ERP). Setiap bidang menyatakan: `key`, `label`, `icon`, `color_token` (nama token mis. `domain-sales`, bukan hex — §8), `status` (`"active"` | `"planned"`), daftar modul anggota (`modules`), dan definisi KPI (`cards`: `key`, `label`, `aggregate`, `doctype`, `field`, `format`, `filters`).

- **Dua tier (`active` vs `planned`):** **4 bidang** (`sales`, `finance`, `accounting`, `purchasing`) berstatus `"active"` dengan modul anggota dan kartu KPI penuh. **7 bidang** ERP lain (`inventory`, `manufacturing`, `projects`, `crm`, `assets`, `support`, `quality`) terdaftar di katalog dengan `status: "planned"`, `modules: ()`, dan `cards: ()`.
- **Aturan `planned` tidak dirender:** `get_domain_catalog()` (yang dikirim di `desktop.bootstrap().domains`) dan `get_domain_keys()` (yang dipakai enum tool `open_domain`) **hanya** mengembalikan bidang berstatus `"active"`. Bidang `"planned"` tidak dikirim ke UI, tidak dirender di desktop maupun Start Menu, tidak dievaluasi KPI-nya, dan ditolak oleh `desktop.domain()` dengan `ValidationError`. Membuka bidang baru di masa depan cukup mengubah `status` menjadi `"active"` serta mengisi `modules` dan `cards` di server tanpa perubahan kode frontend.

Bidang dibuka dari ikon desktop, grid Start Menu, pencarian (`Ctrl+K`), **atau** oleh agent ("buka Sales" → tool `open_domain` → event SSE `open_domain` → membuka jendela `domain:<key>`). Modul tetap dibuka lewat tool `open_module` → event SSE `open_module` → jendela `module:<key>`. Jendela bidang di-host di `WindowHost.vue` lewat `<DomainWindow :domain-key="w.id.slice(7)" />` (fase 3d-2).

### 6.3. Aturan angka

Kartu KPI adalah agregat yang dihitung server (`COUNT`/`SUM`), bukan dihitung di browser. Tidak ada jalur yang menembus izin: KPI dihitung dengan izin user yang sedang login (`frappe.get_list`), dan bila sebuah DocType tidak boleh dibaca user tersebut, KPI-nya tidak boleh ditampilkan. Tidak ada `ignore_permissions` untuk KPI.

Modul dan bidang bersifat **baca saja**. Penulisan tetap lewat approval.

### 6.4. Jendela Pengaturan (*Settings*)

Jendela **Pengaturan** (`frontend/src/components/windows/SettingsWindow.vue`, window ID `settings`, dibuka dari Start Menu) memiliki tata letak 2 kolom: menu navigasi kiri (`168px`) dengan **5 tab dasar** (**Umum** `gear`, **Desain** `desk`, **Percakapan** `arrow-right`, **Konektor** `link`, **Personalisasi** `sparkle`) plus **3 tab khusus `AIOS Client Owner`** (**Penerima Kanal** `bell`, **Kelola Staf** `users`, **Insight Proaktif** `sparkle`), beserta tombol muat ulang pengaturan di kiri bawah, dan panel konten kanan (`role="tabpanel"`) dengan scroll mandiri. Judul jendela tidak diduplikasi di dalam area konten window. Saat jendela di-maximize, tata letak mengikuti layar penuh (full screen 100% viewport) tanpa batas lebar (`max-width: none`). Seluruh tombol aksi di dalam jendela menggunakan tombol ikon minimalis (`AppIcon`, border tipis, latar surface seragam) yang dilengkapi `title` dan `aria-label` eksplisit untuk aksesibilitas keyboard dan pembaca layar.

- **Tab Umum:**
  - **Profil pengguna:** `name` (`User.full_name` atau `user`), `persona` (`User.aios_persona`), dan `status` (`User.aios_status`).
  - **Tema tampilan (Mode Warna):** kontrol radio berbasis ikon (`Ikuti sistem` dengan ikon `desk`, `Terang` dengan ikon `sun`, `Gelap` dengan ikon `moon`) yang di-render dari `data.theme.options` (`["Automatic", "Light", "Dark"]`). Perubahan tema memanggil `POST /api/method/frappe.core.doctype.user.user.switch_theme` dengan header `X-Frappe-CSRF-Token`; bila gagal, menampilkan banner status error tanpa mengubah `data.theme.value` maupun atribut `data-theme`.
  - **Company aktif:** `name` dan `currency` dari company tingkat site (`AIOS Setting.default_company` / `Global Defaults`).
  - **Kuota site:** menampilkan plafon tingkat site (`AIOS Setting.site_token_limit` dan `site_tokens_used`, bukan per user) dengan label eksplisit **Kuota site**, progress bar (`percent_used`, dibatasi 100% untuk lebar bar), nilai `terpakai / limit`, serta `remaining` (bernilai `null` bila `limit <= 0`).
  - **Jadwal reset kuota site:** waktu reset berikutnya diambil server dari method internal Frappe `ScheduledJobType.get_next_execution()` untuk job `aios_v1.services.usage.reset_daily_counters`. Server menghitung `seconds_remaining` (`int`) dan `at_label` (`HH:mm`). Bila hitung mundur mencapai `0`, UI menampilkan **"Menunggu reset berikutnya"**. Bila scheduler tidak aktif atau job tidak ditemukan, UI menampilkan peringatan **"Reset belum terjadwal"**.
- **Tab Desain:**
  - Memilih **Desain** tampilan (`Finto Desk` / `"finto"` default vs `Ekasa Desk` / `"ekasa"` klasik) terpisah dari Mode Warna (Keputusan `0C`); dibaca/disimpan via `desktop.brand_settings` dan `desktop.save_brand_settings`.
- **Tab Percakapan:**
  - Mengatur mode pindah cabang **Hand-off Opsi B** (`Minta konfirmasi dulu` / `"confirm"` default vs `Otomatis langsung pindah` / `"auto"`); dibaca/disimpan via `desktop.conversation_settings` dan `desktop.save_conversation_settings`.
- **Tab Konektor:**
  - Diwakili oleh ikon konektor umum `link` pada menu kiri.
  - Menampilkan kartu **Integrasi Telegram** (dipindahkan dari kartu bertumpuk lama ke tab terisolasi).
  - Status tersambung menampilkan `@username` staf/ID Telegram dengan tombol aksi ikon `unlink` (**Putuskan Tautan**).
  - Status belum tersambung menampilkan instruksi penautan dengan tombol aksi ikon `telegram` (**Hubungkan ke Telegram**), tombol ikon `copy` (**Salin Tautan**, berubah jadi ikon `check` saat tersalin), dan tombol ikon `external-link` (**Buka Telegram langsung**).
  - **Keadaan dinonaktifkan saat cabang Sales mati (Batch D, 21 Nov 2026):** fitur Telegram melekat pada bidang Sales — kartu menampilkan catatan persis **"Fitur ini hanya tersedia untuk bidang Sales"**, tombol **Hubungkan**, **Salin**, dan **Buka** dinonaktifkan (`:disabled="telegramDisabled"`, `SettingsWindow.vue:871,889,899`), sedangkan tombol **Putuskan Tautan** tetap aktif agar pengguna tidak terjebak terhubung (putus tautan tetap bisa dijalankan saat Sales mati — `docs/02` §2.4). Sumber status Sales: `fetchBranches` (`frontend/src/api/branches.ts`) yang memanggil `list_branches` dan membaca flag `enabled` cabang `sales`; katalog gagal dimuat dianggap tidak tersedia (fail-closed), dan backend tetap yang menolak pembuatan tautan dengan pesan yang sama. Saat Sales aktif kembali, ketiga tombol berfungsi normal.
- **Tab Personalisasi:**
  - Menampilkan kartu **Konteks Perusahaan** yang memetakan field `AIOS Setting.company_context_persona` (`Small Text`, dibatasi maksimal 2000 karakter).
  - Menyediakan area teks multi-baris (`textarea`) tanpa subjudul deskripsi kartu yang redundan, dengan counter karakter real-time `X / 2000 karakter`, indikator status simpan ("Menyimpan...", "Tersimpan", "Gagal menyimpan"), tombol aksi ikon `check` (**Simpan**, seragam 32×32 px border line latar surface, aktif hanya bila ada perubahan/dirty dan valid), serta tombol aksi ikon `x` (**Batalkan perubahan**).
  - Teks ini menjadi knowledge base dasar perusahaan yang disuntikkan ke seluruh agen AI di site tersebut.
  - Pengubahan disimpan oleh client melalui endpoint sempit `POST /api/method/aios_v1.api.desktop.save_company_persona`.
- **Tab Insight Proaktif (`cad237d`, khusus `AIOS Client Owner`):**
  - Mengatur jadwal **tujuh detektor proaktif Sales** dari Desk tanpa deploy (K9). Data dibaca dari `aios_v1.api.sales_proactive.get_detector_schedules` dan disimpan lewat `save_detector_schedules`; keduanya bukan endpoint `desktop.*`.
  - **Tab hilang saat cabang Sales mati (Batch B, 21 Nov 2026):** tab hanya ditambahkan bila ada bidang aktif yang punya detektor proaktif (`proactive_branches` dari payload `desktop.settings` tidak kosong — saat ini hanya Sales yang punya detektor), dikelompokkan per bidang; bagian Sales hilang dari tab saat Sales mati dan seluruh tab hilang bila tidak ada bidang berproaktif (`SettingsWindow.vue`, `hasProactiveBranch`).
  - Tiap detektor tampil sebagai **kartu** dalam **grid 2 kolom sama lebar** (`repeat(2, minmax(0, 1fr))`), bukan lebar mengikuti panjang teks.
  - **Tiap informasi tampil sekali:** judul kartu hanya nama Indonesia detektor (tanpa chip kode), status hanya lewat toggle, frekuensi hanya lewat dropdown, jam hanya lewat dropdown. Tidak ada teks ringkasan "Harian · jam 06:00" yang menduplikasi nilai kontrol.
  - **Toggle aktif/nonaktif** bergaya switch (teal saat aktif, `role="switch"`, `aria-checked`); detektor nonaktif meredup dan kontrolnya dinonaktifkan.
  - **Dropdown kustom `FintoSelect.vue`** (`frontend/src/components/base/`) menggantikan `<select>` bawaan browser: pil `--radius-pill`, aksen **teal** (`--teal`, `--teal-strong`, `--teal-soft`, `--teal-line`) untuk tema terang dan gelap, item terpilih bertanda ikon `check`, navigasi keyboard (Enter/Space/Arrow/Escape), dan `aria-haspopup="listbox"`.
  - **Daftar jam (24 opsi) dibatasi tinggi** `max-height: min(240px, 42vh)` dan di-scroll **di dalam** daftar, tidak memanjangkan halaman.
  - **Dropdown di-`Teleport` ke `<body>`** dengan posisi `fixed` agar tidak terpotong panel ber-`overflow-y: auto`; posisi dihitung ulang saat scroll/resize dan membuka ke atas bila ruang bawah tidak cukup.
  - **Motion Finto:** kartu masuk berurutan (`rise2` + delay 0–240 ms), hover mengangkat kartu, transisi buka/tutup dropdown `--dur-15`/`--dur-18`, dan seluruh animasi dinonaktifkan saat `prefers-reduced-motion: reduce`.
  - **Penanganan error:** kegagalan muat/simpan ditampilkan sebagai `.tg-error` dengan `role="alert"` berisi pesan generik, sementara detail dicatat di Error Log lewat `log_exception` — bukan layar kosong.
- **Kerahasiaan `AIOS Setting`:** endpoint `desktop.settings` hanya membaca field yang diizinkan untuk antarmuka pengguna (`site_token_limit`, `site_tokens_used`, `company_context_persona`); field sensitif/konfigurasi internal backend (`api_key`, `system_ethos`, `model_name`, `base_url`, `temperature`) tetap terlarang keras dan tidak pernah disertakan dalam respons maupun direferensikan di komponen UI.
- **Adapter API (`@modules-api`):** pemilihan adapter dilakukan saat build di `frontend/vite.config.ts` lewat `VITE_DESKTOP_ADAPTER=real|mock` (default `real`), di mana `frontend/src/api/modules.ts` dan `frontend/src/api/mock/modules.ts` keduanya memenuhi kontrak TypeScript `ModulesApi` (`satisfies ModulesApi`) mencakup fungsi `saveCompanyPersona`.

---

## 7. Aturan *Zero Hardcoded*

| Data | Sumber |
|---|---|
| Daftar agent, nama, deskripsi, saran prompt | Backend (`registry.py`) |
| Daftar bidang, label, ikon, nama token warna, modul anggota, definisi KPI | Backend (`aios_v1/lib/`, satu sumber dengan katalog modul) |
| Daftar modul, ikon, doctype, kolom, filter, kartu | Backend |
| Company aktif, mata uang | `AIOS Setting` |
| Kuota & pemakaian token | `AIOS Setting.site_token_limit` (gerbang), `User.aios_tokens_used` (statistik) |
| Versi & URL API | `frappe.boot` / environment |

**Aturan yang bisa diuji:** tidak ada nama agent, nama bidang, nama modul, atau nama doctype yang ditulis sebagai teks di berkas komponen. Data contoh hanya boleh hidup di lapisan `api/mock/` dan tidak pernah diimpor jalur produksi.

**Warna bidang tidak dikirim sebagai hex.** Prototype menulis `color:'#1F8A70'` inline; di `frontend/` itu dilarang (§8). Backend mengirim **nama token** (mis. `domain-sales`), dan komponen memetakannya ke `var(--domain-sales)`. Token nilainya didefinisikan sekali di `tokens.css`.

Endpoint `GET /api/method/aios_v1.api.branches.list_branches` memproyeksikan data di server untuk tampilan saja: cabang mengirim `key`, `name`, `description`, `tagline`, `enabled`; worker mengirim `key`, `branch`, `jobRole`, `description`, `exampleQuestions`, `enabled`. Materi prompt internal tidak pernah dikirim ke browser.

**Aturan yang sama berlaku untuk gaya:** komponen dilarang menulis warna, font, bayangan, atau radius secara langsung. Semua lewat token (§8).

---

## 8. Token Visual & CSS

**Aturan mutlak:** nilai visual hanya boleh ditulis di `frontend/src/styles/tokens.css`. Berkas `base.css` maupun komponen `.vue` dilarang menulis literal warna, ukuran font, ketebalan font, radius, spacing, z-index, durasi transisi/animasi, efek blur kaca, atau lebar panel — semuanya wajib mereferensikan `var(--token)`.

Dua lapis token di `styles/tokens.css`:

1. **Primitives & skala terukur** — nilai mentah (hex, rgba, px, ms/s, font) yang hanya boleh didefinisikan di `tokens.css`:
   - **Font family:** `--font-ui`, `--font-mono`.
   - **Spacing (`padding`/`margin`/`gap`):** `--space-{1,2,3,4,5,6,7,8,9,10,11,12,13,14,16,18,20,24,28,29}`.
   - **Radius:** `--radius-{3,4,5,6,8,9,10,12,13,14,20}`, `--radius-pill` (`999px`), `--radius-circle` (`50%`), `--radius-window-foot` (`0 0 14px 14px`).
   - **Ukuran font:** `--fs-{10,11,11-5,12,12-5,13,13-5,14,14-5,15,17,18,20,24,30}`.
   - **Ketebalan font:** `--fw-{300,400,500,600,700,800}`.
   - **Z-index:** `--z-base` (`1`), `--z-raised` (`2`), `--z-taskbar` (`50`), `--z-panel` (`55`), `--z-flyout` (`60`), `--z-toast` (`70`).
   - **Durasi:** `--dur-{12,15,18,20,22,30,40,45,50,90}` (`0.12s`…`0.9s`), `--dur-100` (`1s`), `--dur-110` (`1.1s`), `--dur-240` (`2.4s`), `--dur-instant` (`0.01ms`).
   - **Glass blur (`backdrop-filter` & `-webkit-backdrop-filter`):** `--glass-blur-sm` (`blur(24px) saturate(1.3)`), `--glass-blur-md` (`blur(26px) saturate(1.4)`), `--glass-blur-lg` (`blur(30px) saturate(1.4)`).
   - **Dimensi shell:** `--taskbar-h` (`52px`), `--panel-w` (`410px`).
2. **Semantic & tema** — `--wall-base`, `--wall-1..3`, `--glass`, `--glass-strong`, `--glass-line`, `--surface`, `--surface-2`, `--line`, `--fg`, `--muted`, `--faint`, `--accent`, `--accent-strong`, `--accent-soft`, `--on-accent`, `--ok`, `--ok-soft`, `--warn`, `--warn-soft`, `--bad`, `--bad-soft`, `--hover`, `--press`, `--shadow`, `--shadow-sm`, `--agent-accent-*`, token warna 11 bidang (`--domain-sales`, `--domain-finance`, `--domain-purchasing`, `--domain-inventory`, `--domain-manufacturing`, `--domain-projects`, `--domain-crm`, `--domain-assets`, `--domain-support`, `--domain-quality`, `--domain-accounting`), serta token layar boot yang mengikuti tema (`--boot-bg`, `--boot-fg`, `--boot-bar`, `--boot-status`, `--boot-log`, `--boot-log-ok`, `--boot-skip`, `--boot-word-shadow`) lengkap di `:root`, `@media (prefers-color-scheme: dark) :root:not([data-theme='light'])`, `:root[data-theme='dark']`, dan `:root[data-theme='light']`.

Yang **tidak** perlu token: nilai sekali pakai seperti lebar kolom tabel di satu tempat, serta nilai struktural `0`, `auto`, `100%`, dan `1px` pada `border: 1px solid var(--line)`.

**Scrollbar & animasi global:**
- **Scrollbar global (`GlassScrollbar.vue` di `App.vue`):** mendefinisikan scrollbar tipis `5px` bergaya glass Apple tanpa tombol panah (`--glass`, `--glass-line`, `--radius-pill`, `--glass-blur-sm`, hover `--faint`) untuk seluruh area scroll, serta `scrollbar-gutter: stable` pada `.win-body`, `.cf-list`, dan `.settings-pane` (area yang sengaja tanpa scrollbar seperti `.tb-center` dan `.ap-tabs` tetap tersembunyi).
- **Animasi & transisi seluruh Finto Desk:** seluruh permukaan memakai durasi token `--dur-*` dan menghormati `@media (prefers-reduced-motion: reduce)`, meliputi transisi `<Transition>`/`<TransitionGroup>` (`t-screen`, `t-flyout`, `t-panel-right`, `t-win`, `t-win-close`, `t-tb-app`, `t-pop`, `t-pop-up`, `t-toast`, `t-list`, `t-tab`, `t-slide-left`, `t-sidebar-left`), `<AccordionTransition>` (tinggi + opasitas untuk accordion daftar riwayat, trace, `AgentStep`, dan `FilesWindow`), animasi geometri non-drag/non-resize (`.win-geo-anim`, `.ap-geo-anim`), `.is-loading` (`skeletonShimmer`), `errorShake`, `micRipple`, `.spin`, dan press scale `:active`.

**Pemeriksaan otomatis:** `aios_v1/tests/test_frontend_no_hardcode.py` memindai `frontend/src/components/{module,domain,shell,windows}` dan `frontend/src/styles/base.css` (mengecualikan `styles/tokens.css` sebagai sumber kebenaran) terhadap warna literal hex/rgb/rgba.

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
frontend/
├── index.html
├── vite.config.ts
├── tsconfig.json
└── src/
    ├── main.ts
    ├── App.vue
    ├── router/index.ts
    ├── stores/          branches · chat · modules · session · ui
    ├── composables/     useWindowManager
    ├── api/
    │   ├── client.ts    apiFetch + CSRF + pesan aman
    │   ├── branches.ts  katalog cabang & worker
    │   ├── connector.ts thread · flag · order · tautan Telegram
    │   ├── modules.ts   bootstrap · domain · module · list · search · settings
    │   ├── session.ts   login · register · session context
    │   ├── chat.ts      chat stream (SSE) · kelola percakapan · stop_stream
    │   └── mock/        data contoh, tidak masuk jalur produksi
    ├── components/
    │   ├── base/        AccordionTransition · AgentAvatar · AppIcon · EkasaMark · ErrorState · FintoMark · GlassScrollbar · PopoverMenu · RichText · Toasts
    │   ├── shell/       BootScreen · Taskbar · StartMenu · SearchFlyout · WindowHost
    │   ├── agent/       AgentPanel · AgentStep
    │   ├── domain/      DomainWindow · DomainCards · DomainShortcuts
    │   ├── module/      ModuleWindow
    │   └── windows/     AboutWindow · ApprovalCardWindow · ArtifactWindow · ChannelFlagsWindow · FilesWindow · PendingDraftsWindow · SettingsWindow
    ├── assets/branding/ logo & maskot Fino (fino-{sales,finance,accounting,purchasing}.png, finto-*)
    ├── views/           LoginView · RegisterView · PendingView · DesktopView
    ├── styles/          tokens.css · base.css
    └── types/index.ts
public/
└── favicon.{svg,ico}    ikon tab browser Finto OS (`frontend/index.html:6-7`)
```

**Selisih yang disengaja terhadap prototype:** prototype adalah satu berkas HTML dengan data mock dan warna hex inline. `frontend/` memisahkan komponen, mengambil semua data dari backend, dan memakai token visual (§7, §8). Yang **tidak boleh berbeda** adalah susunan dan elemen yang tampak.

---

## 10. Kontrak API Desktop

| Endpoint | Isi |
|---|---|
| `GET /api/method/aios_v1.api.desktop.bootstrap` | `user{id,name}`, `company{id,name,currency}`, `agents[]`, `domains[]` (hanya bidang `active`: `{key,label,icon,color_token,module_count}` — ikut cabang per client, `DOMAIN_BRANCH_MAP`), `modules[]` (hanya modul cabang aktif — `MODULE_BRANCH_MAP`, Batch B), `csrf_token` |
| `GET /api/method/aios_v1.api.desktop.domain` | `domain{key,label,icon,color_token}`, `company{id,name,currency}`, `cards[{key,label,value,format,currency?}]`, `modules[{key,label,icon,row_count}]`; menerima `domain` (hanya bidang `active` yang cabangnya aktif — D8; KPI & `row_count` dihitung via `frappe.get_list` dengan izin user login tanpa `ignore_permissions`) |
| `GET /api/method/aios_v1.api.desktop.module` | `module`, `cards[]`, `doctypes[]`, `rows[]`, `pagination` (`page`, `page_size`, `total`, `total_pages`); menerima `module`, `page`, `page_size`, `filters` JSON (`date_from`, `date_to`, `status`, `party` sesuai allowlist modul); **menolak modul cabang mati** dengan pesan "Modul ini tidak aktif untuk client ini." (Batch B) |
| `GET /api/method/aios_v1.api.desktop.list` | `module`, `doctype`, `rows[]`, `pagination`; menerima `module`, `doctype`, `page`, `page_size`, `filters`; **menolak modul cabang mati** dengan pesan yang sama (Batch B) |
| `GET /api/method/aios_v1.api.desktop.search` | `results[]` berisi item modul (`type: "module"`, `module`) dan dokumen (`type: "document"`, `module`, `doctype`, `name`, `row`) yang di-scope ke company aktif dan hanya dari modul cabang aktif (Batch B); di UI (`frontend/src/api/modules.ts`) dinormalisasi menjadi `SearchResult` (`kind: "module" \| "document"`), klik item modul maupun dokumen membuka jendela `module:<key>` |
| `GET /api/method/aios_v1.api.desktop.settings` | `profile{name,persona,status}`, `company{id,name,currency}`, `quota{limit,used,remaining,percent_used}`, `reset{at,at_label,seconds_remaining,source,scheduler_active}`, `theme{value,options}`, `proactive_branches[]` (bidang aktif yang punya detektor proaktif — sumber tab Insight Proaktif, Batch B); baca-saja untuk `AIOS Client` aktif tanpa mengekspos field rahasia `AIOS Setting` (`User.desk_theme` kosong/invalid dinormalisasi ke `"Automatic"`, perubahan tema ditulis lewat `POST /api/method/frappe.core.doctype.user.user.switch_theme`). Jendela `SettingsWindow.vue` menampilkan 5 tab dasar (`Umum`, `Desain`, `Percakapan`, `Konektor`, `Personalisasi`) plus 3 tab khusus pemegang Role `AIOS Client Owner`: `Penerima Kanal`, `Kelola Staf`, dan `Insight Proaktif` (hilang saat tidak ada bidang berproaktif) |
| `GET /api/method/aios_v1.api.desktop.brand_settings` | Preferensi desain tampilan per-user (`{"brand": {"value": "finto"|"ekasa", "options": ["finto", "ekasa"]}}`) via Frappe Defaults (`desktop.py:688`) |
| `POST /api/method/aios_v1.api.desktop.save_brand_settings` | Simpan pilihan desain tampilan per-user (`finto` atau `ekasa`, `desktop.py:700`) |
| `GET /api/method/aios_v1.api.desktop.conversation_settings` | Preferensi mode hand-off per-user (`{"handoff_mode": {"value": "confirm"|"auto", "options": ["confirm", "auto"]}}`, `desktop.py:654`) |
| `POST /api/method/aios_v1.api.desktop.save_conversation_settings` | Simpan pilihan mode hand-off (`confirm` atau `auto`, `desktop.py:666`) |
| `GET /api/method/aios_v1.api.desktop.client_staff_and_recipients` | Khusus `AIOS Client Owner` aktif; mengembalikan `users[{email,full_name,persona,aios_status,enabled,is_owner,is_receiver}]` dan `quota{active_users,max_users,remaining_slots}` |
| `POST /api/method/aios_v1.api.desktop.set_channel_receiver` | Khusus `AIOS Client Owner` aktif; menerima `{target_user, is_receiver}`; memasang/mencopot `AIOS Channel Receiver Profile` pada staf `AIOS Client` aktif |
| `POST /api/method/aios_v1.api.desktop.create_client_staff` | Khusus `AIOS Client Owner` aktif; menerima `{full_name, email, persona}`; memeriksa plafon `AIOS Setting.max_users`, membuat `User` (`AIOS Client Profile`, `aios_status = "Active"`), dan mengembalikan `invitation_url` sekali pakai (`/update-password?key=...`, 20 menit) yang dinormalisasi memuat port webserver site bila non-produksi |
| `POST /api/method/aios_v1.api.desktop.set_client_staff_status` | Khusus `AIOS Client Owner` aktif; menerima `{target_user, status}` (`"Active"` atau `"Suspended"`); menolak menonaktifkan diri sendiri atau sesama `AIOS Client Owner` |
| `POST /api/method/aios_v1.api.desktop.regenerate_client_staff_invite` | Khusus `AIOS Client Owner` aktif; menerima `{target_user}`; menerbitkan ulang `invitation_url` sekali pakai untuk staf `AIOS Client` aktif yang dinormalisasi memuat port webserver site bila non-produksi |
| `POST /api/method/aios_v1.api.desktop.log_client_error` | Menerima `{message: str, context: str, stack: str}`; mencatat error kritis frontend ke DocType `Error Log` lewat `frappe.log_error` dengan sanitasi kredensial/DB/site; dibatasi laju (`@rate_limit(limit=10, seconds=60, methods=["POST"], ip_based=True)`); menolak Guest, mengizinkan user terautentikasi (termasuk Administrator); cakupan sempit: khusus kegagalan data vital (bootstrap gagal, dsb.) |
| `GET /api/method/aios_v1.api.control.health` | Control API token-only; `{status, site, time, version}` |
| `GET /api/method/aios_v1.api.control.users` | Control API token-only; menerima `status`, `page`, `page_size`; selalu memfilter role `AIOS Client` (filter melekat di endpoint, bukan parameter); mengembalikan `users[]` dengan hanya `name`, `full_name`, `aios_status`, `aios_persona`, `enabled`, `last_login`, serta `total`, `page`, `page_size`; mengecualikan `Administrator` dan `Guest` |
| `POST /api/method/aios_v1.api.control.activate_user` | Control API token-only; menerima `user`, `status` (`Active` atau `Suspended`); memperbarui `aios_status` dan `enabled` bersama; mengembalikan `{ok, user, aios_status}` |
| `GET /api/method/aios_v1.api.control.metrics` | Control API token-only; angka agregat `{site_tokens_used, site_token_limit, active_users, total_users, tokens_today}` tanpa isi `AIOS Setting` atau daftar user |
| `GET /api/method/aios_v1.api.branches.list_branches` | katalog cabang publik dengan flag `enabled` per cabang (mengikuti status aktivasi per client — sumber keadaan nonaktif kontrol Telegram di tab Konektor, Batch D); proyeksi field tampilan saja (lihat §7) |
| `POST /api/method/aios_v1.api.chat.stream_chat` | stream SSE (`werkzeug.wrappers.Response` ber-generator lewat *Response passthrough* resmi Frappe); header `Cache-Control: no-cache, no-transform`, `Connection: keep-alive`, `X-Accel-Buffering: no`; request membawa `file_ids[]` opsional untuk lampiran; mendukung event kontrol UI terpisah `{"type": "open_domain", "domain": "<key>"}` (untuk jendela bidang `domain:<key>`) dan `{"type": "open_module", "module": "<key>"}` (untuk jendela modul `module:<key>`) dari manager |
| `POST /api/method/aios_v1.api.chat.upload_file` | multipart `file` + `conversationId` (atau `branch` bila belum ada conversation); membuat Private `File` awalnya terikat conversation; respons `conversationId` + metadata `attachment` — H5 fase 1 |
| `POST /api/method/aios_v1.api.chat.parse_pdf` | ekstraksi teks/tabel dari PDF yang diunggah |
| `GET /api/method/aios_v1.api.chat.list_conversations` | daftar percakapan milik user per cabang; menerima `branch`, `archived` (`false` default), `sort` (`"desc"`\|`"asc"`), memprioritaskan `isPinned` di atas; **mengembalikan daftar kosong bila cabang tidak aktif** (D6, Batch B) |
| `POST /api/method/aios_v1.api.chat.rename_conversation` | ubah judul percakapan milik user (`conversation_id`, `title`); **ditolak bila cabang percakapan tidak aktif** (D6, Batch B) |
| `POST /api/method/aios_v1.api.chat.set_conversation_pin` | sematkan/lepas sematan percakapan milik user (`conversation_id`, `pinned`); **ditolak bila cabang percakapan tidak aktif** (D6, Batch B) |
| `POST /api/method/aios_v1.api.chat.set_conversation_archive` | arsipkan/keluarkan dari arsip percakapan milik user (`conversation_id`, `archived`); **ditolak bila cabang percakapan tidak aktif** (D6, Batch B) |
| `POST /api/method/aios_v1.api.chat.delete_conversation` | hapus percakapan milik user (`conversation_id`); **ditolak bila cabang percakapan tidak aktif** (D6, Batch B) |
| `POST /api/method/aios_v1.api.chat.stop_stream` | hentikan stream aktif percakapan milik user (`conversation_id`) |
| `GET /api/method/aios_v1.api.chat.get_conversation` | detail percakapan milik user; **ditolak bila cabang percakapan tidak aktif** dengan `PermissionError` "Riwayat percakapan cabang ini tidak aktif untuk client ini." (D6, Batch B — data muncul kembali saat cabang dinyalakan) |

> **Kontrak API Fase 1 (12 Nov 2026, keputusan Ten — Flow Utama langkah 6):** Seluruh rute kustom memakai `@frappe.whitelist()` resmi di `/api/method/aios_v1.api.<module>.<method>`; dispatcher kustom (`api/dispatcher.py`), `lib/auth.py`, hook `before_request`, cookie `aios_session`, `cookie_to_set/clear`, dan CORS manual (`add_cors_headers`) dihapus. Sesi `sid` + CSRF resmi: **semua POST wajib `X-Frappe-CSRF-Token`**, dan **Guest ditolak 403** (`frappe.PermissionError` lewat `is_whitelisted`), bukan 401 dari dispatcher lama. Logout memakai `/api/method/logout` bawaan, bukan `/api/auth/logout`. URL lama `/api/branches`, `/api/chat/*` (termasuk `/api/chat/<branch>/stream`), `/api/connector/*`, `/api/monitoring/usage*` tidak ada lagi. Enam rute legacy dihapus tanpa pengganti: `api/auth/me`, `api/auth/login`, `api/auth/register`, `api/payment/status`, `api/payment/checkout`, `api/connector/health`. Monitoring (`aios_v1.api.monitoring.*`) memakai gate `_is_admin` = Administrator + role `AIOS Admin`; **System Manager tidak lagi diizinkan**. CORS lintas-origin produksi memakai `allow_cors` resmi di `site_config` (saat ini hanya origin DEV `http://localhost:5173` & `http://aios-client1.localhost:5173`; domain produksi belum ada).

Backend memvalidasi setiap ID pada `file_ids` sebagai Private `File` milik session user dan terkait ke conversation chat yang sama; ukuran dan format harus dalam batas yang diizinkan. File tidak valid ditolak sebelum konteks model dibentuk. Setelah pesan user disimpan, attachment dipindahkan secara relasional ke `AIOS Message` lewat field attachment bawaan Frappe; file keluaran agent ditautkan ke pesan agent. Ini tidak menambah schema dan tidak memindahkan isi file. `attachment.id` pada respons upload hanya state internal frontend untuk mengirim `file_ids`: tidak ditampilkan ke user, tidak diketik user, dan tidak boleh muncul di pesan error maupun event `artifact_created`. Client tidak pernah menerima isi file melalui metadata maupun pesan error.

Semua endpoint **Desktop API** memakai sesi Frappe yang sedang login dan tunduk pada `docs/03` §2.2. Control API (`aios_v1.api.control.*`) memakai token `AIOS Control`, bukan sesi, dan dijelaskan di `docs/03` §1.4.

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
| Dashboard developer | **Bukan bagian Ekasa Desk** — app Vue terpisah di `admin/` (app `aios_v1`), dilayani app di `/aios-admin` (`#11` fase 1c-2) |

Paritas visual diukur terhadap `ekasa-desk-prototype/index.html`, bukan terhadap `frontend/` lama. Daftar selisih yang belum tertutup dipelihara di `docs/05.1`.

---

## 12. Batasan yang Diakui

1. **Belum ada isolasi level OS.** UI berjalan di browser; keamanan tetap di lapisan server (`docs/02` §2.3).
2. **Modul belum punya penulisan.** Semua aksi tulis lewat approval.
3. **Dashboard developer** dibangun sebagai **app Vue terpisah `/aios-admin`** (folder `admin/`, API `aios_v1.api.control_plane`, `#11` fase 1c-2) dan **bukan bagian Ekasa Desk**; tab undangan sekali pakai, tombol **Buat Site** (fase 2 `#11`), serta DocPerm/registry plugin `AIOS Admin` menyusul di `#11`.
4. **`Classic Desk` tidak diport.** Prototype menampilkan tombol ke `/app` (Frappe Desk). Di `frontend/` tombol itu **tidak boleh ada**: `AIOS Client` ber-`desk_access=0` dan `Administrator` tidak pernah dipakai jalur produk.
5. **Notifikasi dan Peringatan Kanal telah aktif.** Lonceng (bell) di Taskbar kanan terhubung langsung ke backend untuk menghitung total flag percakapan `Open` (`AIOS Conversation Flag` via `?status=Open`) dan total notifikasi draf pesanan baru belum dibaca (`Notification Log`). Dot bell membatasi tampilan hingga `99+` bila total melebihi 99. Mengklik lonceng membuka jendela `Peringatan Kanal` (`ChannelFlagsWindow.vue`) yang memungkinkan staf meninjau bukti pelanggaran aturan percakapan (hingga 50 flag `Open` terbaru) maupun membuka draf pesanan (`approval:<draft_id>`) serta menandai sudah ditinjau. Antrean pesanan dipaginasi 20 item per halaman dengan tata letak pinned footer (bar pagination menempel di bawah window tanpa scroll, kepala window terkunci di atas, daftar pesanan dan flag scroll mandiri), serta kepala window menampilkan total flag `Open` dan total antrean draf pesanan belum dibaca riil dari server.
6. **Selisih kode vs prototype yang masih terbuka** dicatat di `docs/05.1`, bukan disembunyikan di sini.
7. **Role kanal bukan bawaan wizard.** Tab **Penerima Kanal** / **Kelola Staf** di jendela Pengaturan hanya tersedia bagi `AIOS Client Owner` **aktif** (Keputusan #7). User pertama hasil setup wizard Frappe berstatus `Pending Provisioning` dengan `AIOS Client` + `AIOS Client Profile` saja: Frappe `create_or_update_user` menempelkan semua Role, tetapi `aios_v1.setup.strip_wizard_channel_roles` mencabut `AIOS Channel Receiver` / `AIOS Client Owner` beserta Role Profile-nya lewat primitif resmi `frappe.flags.in_setup_wizard`. Role itu baru muncul setelah aktivasi (`activate_user`, langkah 4 Flow Utama) atau saat pemilik memasangnya dari menu ini; `get_channel_recipients()` (`docs/02` §2.4) karenanya tetap hanya mengembalikan penerima aktif. Kontrak endpoint di §10 tidak berubah.
8. **Celah terbuka & pengaktifan cabang:** notifikasi approval `Quotation` ke tamu sudah ditutup pada Tahap 1 Sales (`2749d89`); pengaktifan cabang per client **sudah selesai** di Batch A–D (`7840b08`, `7ddab71`, `2add1ed`, `a1a8ef4`) — status cabang per client dibaca dari DocType `AIOS Branch Activation` (lihat `docs/03` §1.5), bukan lagi dari `_PRIORITY_BRANCHES`.
