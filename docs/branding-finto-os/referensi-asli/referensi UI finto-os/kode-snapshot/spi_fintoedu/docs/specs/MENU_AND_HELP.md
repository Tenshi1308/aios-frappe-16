# Feature Spec: Menu per Role, Wizard Panduan, FAQ, Notifikasi Lonceng & Akses Desk

| Metadata      | Value |
| ------------- | ----- |
| ID            | SPI-NAV |
| Status        | Live baseline (5 Nov 2026) |
| Key files     | `frontend/src/assets/data/menu-catalog.ts` (sumber tunggal), `page-tours.ts` (langkah tur per halaman), `menu-items.ts`, `features/onboarding/components/TourGuide.vue`, `features/onboarding/`, `features/faq/`, `helpers/notification-route.ts`, `layouts/components/TopBar.vue`, `spi_fintoedu/desk_guard.py`, `api/faq.py`, `api/onboarding.py`, `faq_seed.py` |
| Tests         | `spi_fintoedu/tests/test_help_and_access.py` |
| References    | [ROLE_PERMISSIONS.md](ROLE_PERMISSIONS.md), [business_flow/03_roles_permissions.md](../business_flow/03_roles_permissions.md) |

## 1. Aturan

1. **Menu disembunyikan bila role tidak bisa memakainya.** Menu hanya tampil bila halaman tersebut dapat dimuat oleh role (endpoint backend mengizinkan). Halaman yang hanya *read-only* untuk role tetap tampil, tetapi tombol aksi yang pasti ditolak backend disembunyikan.
2. **Menu dikelompokkan per kategori** dengan judul kategori di sidebar. Urutan: Utama → Admisi & Prospek → Data Murid → Akademik → Keuangan SPP → Laporan → Honor & Gaji → Master Data → Portal → Pengaturan Sistem → Bantuan. Kategori kosong tidak ditampilkan.
3. **Satu sumber kebenaran:** `menu-catalog.ts` (`MENU_FEATURES`). Setiap entri berisi kategori, label, ikon, deskripsi fungsi (tooltip sidebar), langkah wizard, peta rute per role, dan `documentTypes` untuk tujuan klik notifikasi. Jangan menambah menu langsung di `menu-items.ts`.
4. **Backend tetap penegak izin.** Menyembunyikan menu/tombol hanya untuk kenyamanan; setiap endpoint tetap memvalidasi role.
5. **Desk ERPNext (`/app`, `/desk`) hanya untuk Super Administrator (user `Administrator`).** User lain (termasuk System Manager lain) diarahkan ke SPA oleh hook `before_request` (`desk_guard.py`). URL SPA diambil dari site config `spi_frontend_url` (default `/`). API `/api/*` tidak terpengaruh.
6. **Menu juga disaring per kategori kepegawaian** (`MenuFeature.when`, data dari `employment.get_my_employment`): guru **Freelance** tidak melihat *Slip Gaji Saya* (riwayat honornya di *Honor Saya*); guru **Tetap** tidak melihat *Honor Saya* (tidak menerima honor sesi, digaji lewat Payroll).
7. **"Lihat sebagai" hanya Super Administrator.** User `Administrator` dapat memilih role di TopBar untuk melihat menu & dashboard role tersebut (router guard melewatkan cek role khusus untuk `Administrator`; data tetap dengan hak Super Administrator). Role lain — termasuk Branch Manager — tidak dapat membuka dashboard/rute role lain, dan tidak ada akun yang di-hardcode untuk akses portal (dicek lewat peran `System Manager`).
8. **CSO ≠ Marketing.** CSO punya Role Profile, dashboard (`/dashboard/cso`, "Dashboard CSO"), rute (`/cso/*`, nama `cso.*`) sendiri. Hak CSO saat ini sama dengan Marketing (keduanya ada di allow-list backend). Role Profile `CSO` dibuat oleh `setup.setup_role_profiles` saat migrate.

## 2. Menu per Dashboard & Fungsinya

Legenda: **R** = hanya lihat (aksi ubah disembunyikan/ditolak).

### Super Administrator (`Administrator`) — `/dashboard/administrator`
| Kategori | Menu | Fungsi |
|---|---|---|
| Utama | Dashboard Super Administrator | Ringkasan administrasi sistem. |
| Pengaturan Sistem | User | Kelola akun, Role Profile, dan cabang yang boleh diakses. |
| | Institusi | Data unit sekolah/cabang (Company), kode cabang, lokasi. |
| | AI Assistant | Penyedia model AI, tes koneksi, uji coba chat. |
| | Migrasi Data | Pindahkan data site SPI lama: pilih sumber, jalankan **per langkah** atau **semua langkah**, uji coba (dry-run), log proses langsung, catatan per langkah (spec [DATA_MIGRATION](DATA_MIGRATION.md)). |
| | Monitoring Aktivitas | Ringkasan, riwayat/timeline, sesi, profil aktivitas per user, dan **Pengaturan** (aktif/nonaktif, role yang direkam, pengecualian privasi). Hanya user `Administrator`; ditolak saat "Lihat sebagai" (spec [ACTIVITY_MONITORING](ACTIVITY_MONITORING.md)). |
| | Session Replay | Putar ulang satu sesi pengguna (rekonstruksi wireframe, kursor virtual, timeline, 1x/2x/4x). Hanya user `Administrator`; setiap pembukaan dicatat di Access Log. |
| Master Data | Kurikulum | Program, Course, Topik & Materi (juga milik Staff Yayasan — spec [CURRICULUM](CURRICULUM.md)). |
| | Desk ERPNext | Membuka `/app/home` (hanya user `Administrator`; System Manager lain tidak melihat tautan ini). |
| Bantuan | FAQ & Bantuan | Pencarian FAQ. |

### Staff Yayasan — `/dashboard/yayasan` (8 Nov 2026)
| Kategori | Menu | Fungsi |
|---|---|---|
| Utama | Dashboard Yayasan | Jumlah program, course, topik, dan topik tanpa materi murid. |
| Master Data | Kurikulum | Program (urutan course), Course (kategori murid, urutan bab/topik), Topik (materi murid, panduan guru, lampiran Murid/Guru). Berlaku untuk semua cabang. |

### Branch Manager — `/dashboard/branch-manager`
| Kategori | Menu | Fungsi |
|---|---|---|
| Utama | Dashboard Branch Manager | Angka langsung: pendaftar PPDB, presensi hari ini, realisasi & kolektibilitas SPP, LMS, plus pintasan. |
| | Perlu Tindakan | Semua pekerjaan cabang berurutan Mendesak → Hari Ini → Minggu Ini → Pantau. |
| | Follow-up Murid | Tindak lanjut murid/orang tua (SPP, cuti, off, akademik) dengan penanggung jawab & tenggat. |
| Admisi & Prospek | PPDB & Admisi | Calon siswa dari PPDB online/walk-in; konversi menjadi siswa. |
| | Jadwal Trial Class | Jadwal trial, guru, kehadiran & catatan hasil trial. |
| | Batal Registrasi | Arsip pendaftar batal + alasan; pulihkan. |
| | Buku Tamu | Catatan pengunjung cabang. |
| Data Murid | Murid | Data pokok murid **+ status** Pending/Aktif/Cuti/Off bertanggal efektif dalam satu halaman (11 Nov 2026): tambah/ubah/hapus data, ubah status, export. |
| | Wali Murid | Data wali & relasi ke anak. |
| | Mutasi Siswa | Pindah siswa antar unit (persetujuan dua pihak). |
| Akademik | Rombel & Kelas | Kelas, kapasitas, anggota. |
| | Sesi Mengajar | Realisasi sesi, guru pengganti, kehadiran; jadwal mingguan otomatis. |
| | Presensi Siswa | Presensi harian per rombel. |
| | Penilaian & Rapor | Rencana penilaian, input nilai, publikasi ke portal. |
| | Perkembangan Murid | Kehadiran 90 hari, level, final project (setujui → sertifikat). |
| | LMS & Pembelajaran | Materi, kuis, tugas; **Sinkronkan ke Rapor** (lihat §5). |
| Keuangan SPP | Tagihan SPP | Daftar invoice; buat tagihan manual/massal; **cetak Tagihan (belum lunas) / Kwitansi (lunas)**. |
| | Pembayaran SPP | Ajukan pembayaran (verifikasi oleh Finance). |
| | Harga SPP | Harga program & harga khusus murid. |
| | Akun Cara Bayar | Akun Kas/Bank default tiap cara bayar per cabang (Finance + Super Administrator). |
| Laporan | Laporan Cabang | Tren 12 bulan, laporan Off, matriks status. |
| | Laporan Keuangan | Neraca, Laba Rugi, Arus Kas, Buku Besar. |
| | Controlling Keuangan | Kas/bank, kapasitas vs realisasi SPP, setoran pusat, onsite vs online. |
| Honor & Gaji | Rekap Honor Guru | Honor freelance dari sesi, dompet honor, tarif (tidak bisa menandai dibayar). |
| | Slip Gaji Saya | Slip gaji pribadi. |
| Master Data | Pegawai | Data karyawan. |
| | Master Akademik | Tahun Akademik, Term, Program. |
| | Ruangan | Ruang offline/online & izin bentrok. |
| Bantuan | FAQ & Bantuan | |

### Principal — `/dashboard/principal`
Sama dengan Branch Manager, dengan batasan: status di menu Murid **R** (data murid boleh tambah/ubah/hapus), Follow-up Murid **R** (tombol Buat disembunyikan), Pembayaran SPP **R**, Harga SPP **R**, Rekap Honor Guru (tarif cabang **R**, tarif khusus rombel disembunyikan). Matriks SPP: dapat menerbitkan tagihan, tidak dapat mengajukan pembayaran.

### Finance — `/dashboard/finance`
| Kategori | Menu | Fungsi |
|---|---|---|
| Utama | Dashboard Finance, Perlu Tindakan, Follow-up Murid | Angka keuangan langsung; pekerjaan terbuka; follow-up (bisa membuat). |
| Data Murid | Murid **R** | Lihat data & status murid (menentukan siapa ditagih); tombol tambah/ubah/hapus/ubah status disembunyikan. |
| Akademik | Sesi Mengajar **R** | Lihat realisasi sesi (dasar honor). |
| Keuangan SPP | Tagihan SPP, Pembayaran SPP, Harga SPP (Matriks 12 Bulan = tab di Controlling) | Penuh (termasuk cetak Tagihan/Kwitansi); **verifikasi & void pembayaran hanya Finance**. |
| Laporan | Laporan Cabang, Laporan Keuangan, Controlling Keuangan | |
| Honor & Gaji | Rekap Honor Guru | Tarif, tarif khusus, **tandai honor bulanan dibayar**. |
| | Slip Gaji Saya | |
| Bantuan | FAQ & Bantuan | |

### CSO — `/dashboard/cso` (sama untuk Marketing — `/dashboard/marketing`)
| Kategori | Menu | Fungsi |
|---|---|---|
| Utama | Dashboard CSO, Perlu Tindakan, Follow-up Murid | Fokus lead, trial, follow-up; follow-up dapat dibuat/ditugaskan. |
| Admisi & Prospek | PPDB & Admisi, Jadwal Trial Class, Batal Registrasi, Buku Tamu | Kelola lead sampai siswa. |
| Data Murid | Murid | Tambah & ubah data murid, ubah status (Pending/Aktif/Cuti/Off); hapus disembunyikan. Marketing: ubah status, data **R**. |
| Akademik | Rombel & Kelas | **Satu-satunya peran yang mengubah rombel**: buat rombel, masukkan/keluarkan siswa, atur guru pengajar. |
| Akademik | Perkembangan Murid **R** | Pantau perkembangan untuk komunikasi orang tua. |
| Keuangan SPP | Tagihan SPP **R + cetak** (CSO saja) | Lihat tagihan & **cetak Tagihan/Kwitansi**; Buat/Terbitkan tagihan disembunyikan (11 Nov 2026). |
| | Pembayaran SPP | **Ajukan** pembayaran + bukti (verifikasi oleh Finance). |
| Laporan | Laporan Cabang | |
| Honor & Gaji | Slip Gaji Saya | |
| Bantuan | FAQ & Bantuan | |

### Rombel & Kelas — aturan khusus
Aturan ini juga berlaku untuk endpoint lama `finto_edu.api.student_group.*` dan `finto_edu.api.attendance.*` bila dipanggil langsung (di-override `spi_fintoedu.api.legacy_guard` lewat `override_whitelisted_methods`): ubah rombel hanya CSO; guru hanya membaca rombel & presensi rombel yang ia ajar.

Perubahan rombel (buat/ubah/hapus, tambah/keluarkan siswa, atur guru pengajar) **hanya CSO** (+ Super Administrator), lewat `spi_fintoedu.api.rombel` (menggantikan `finto_edu.api.student_group` di SPA SPI). Branch Manager & Principal: lihat. Guru: hanya rombel yang ia ajar (Student Group Instructor), lihat saja. Finance: tidak ada akses.

### Teacher — `/dashboard/teacher`
| Kategori | Menu | Fungsi |
|---|---|---|
| Utama | Dashboard Teacher | |
| Admisi & Prospek | Jadwal Trial Class | Trial yang ditugaskan; isi kehadiran & catatan hasil. |
| Akademik | Rombel & Kelas (hanya rombel yang diajar, lihat saja), Sesi Mengajar, Presensi Siswa, Penilaian & Rapor, Perkembangan Murid, LMS & Pembelajaran | Konfirmasi sesi sendiri, presensi, nilai, final project (ajukan), beri kuis/tugas, nilai & sinkron ke rapor. |
| Honor & Gaji | Honor Saya (guru freelance) / Slip Gaji Saya (guru tetap) | Freelance: riwayat honor per sesi + dompet honor (pengganti slip gaji). Tetap: slip gaji bulanan Payroll HRMS, tanpa honor sesi. |
| Bantuan | FAQ & Bantuan | |

> Syarat data: akun guru harus tertaut ke **Instructor** (via Employee). Tanpa itu Sesi Mengajar, Perkembangan Murid, dan dompet honor menolak akses.

### Parent — `/dashboard/parent`
Utama: Dashboard Parent · Portal: **Monitoring Anak** (kehadiran, tagihan, nilai terpublikasi; anak dicocokkan dari email login = email wali) · Bantuan: FAQ.

### Student — `/dashboard/student`
Utama: Dashboard Student · Portal: **Portal Hasil Belajar** (kehadiran, tagihan, nilai), **Materi & Tugas (LMS)** · Bantuan: FAQ.

LMS dipisah per peran: murid **mengerjakan kuis & mengumpulkan tugas**; guru **membuat tugas, menilai, menyinkronkan ke rapor** dan hanya bisa *pratinjau* kuis (form pengumpulan tidak tampil di guru; aksi guru tidak tampil di murid). Pengumpulan selalu atas nama murid yang login: `finto_edu.api.lms.submit_quiz/submit_assignment` di-override `spi_fintoedu.api.lms_guard` (parameter `student` dari klien diabaikan; non-murid ditolak).

### Menu yang disembunyikan pada perubahan ini
| Role | Menu | Alasan |
|---|---|---|
| Branch Manager, Principal | AI Assistant | Menyimpan konfigurasi AI ditolak backend (role System Manager/Principal/Academic Admin). Konfigurasi AI = tugas Super Administrator. |
| Student | Tombol Buat Tugas / Sinkronkan ke Rapor / Submisi Siswa di LMS | Ditolak backend untuk role Student. |
| Teacher | Tombol Tarif Freelance Cabang & Tarif Khusus Rombel | Ditolak backend. |
| Principal | Tombol Buat Tarif Khusus Rombel, Buat Follow-up | Ditolak backend. |
| Finance | Pintasan PPDB & LMS di dashboard | Finance tidak punya menu tersebut. |

## 3. Tur Panduan (Onboarding) — menyorot elemen, langkah demi langkah

- **Mesin tur:** `TourGuide.vue` — layar digelapkan, elemen target disorot (spotlight + garis biru), kartu penjelasan menempel di dekat elemen (posisi otomatis atas/bawah/kiri/kanan, menyesuaikan layar HP), halaman di-scroll ke elemen, progres "Langkah x / n", tombol Kembali/Lanjut/Lewati, keyboard ←/→/Enter/Esc.
- **Target:** atribut `data-guide="<feature-id>.<elemen>"` di halaman; langkah di `assets/data/page-tours.ts` (`PAGE_TOURS[featureId]`, 3–6 langkah per halaman, 31 halaman + dashboard). Langkah yang targetnya tidak tampil untuk user (tombol disembunyikan per role, tabel kosong) **dilewati otomatis**; langkah tanpa target tampil di tengah.
- **Login pertama:** tur "Selamat datang" menyorot sidebar, pilihan *Lihat sebagai* (khusus Super Administrator), lonceng, ikon panduan, kotak cari, dan menu FAQ.
- **Pertama kali membuka menu:** tur halaman tersebut. Cadangan bila halaman belum punya tur: langkah teks dari `menu-catalog.ts`.
- Menambah halaman baru: beri `data-guide` pada header, filter, tombol utama, dan tabel; tambahkan entri `PAGE_TOURS`.
- Buka ulang: ikon **?** di TopBar (panduan halaman aktif). Reset semua: menu profil → *Tampilkan ulang semua panduan*.
- Status tersimpan per user di backend (user default `spi_seen_guides`, JSON list) → ikut pindah perangkat. API: `onboarding.get_onboarding_state`, `mark_guide_seen(key)`, `reset_guides`. Kunci: `welcome`, `page.<feature id>`.

## 4. FAQ

- **Sumber data:** DocType inti Frappe **Help Article** (pertanyaan = `title`, jawaban = `content`, `published`) dan **Help Category** (kelompok). *Blog Post tidak ada di Frappe v16* (dipindah ke app terpisah), sedangkan Help Article memang untuk knowledge base.
- **Halaman:** `/faq` (rute `help.faq`, semua user login) — kotak pencarian (debounce, cari di pertanyaan & jawaban) + accordion per kategori. Kotak cari di TopBar juga mengarah ke `/faq?q=`.
- **API:** `faq.list_faqs(search)` — hanya artikel `published=1`, HTML jawaban disanitasi (`sanitize_html`).
- **FAQ per role (6 Nov 2026):** custom field Help Article `custom_spi_roles` (satu Role Profile per baris; kosong = semua). `list_faqs` hanya mengembalikan artikel untuk Role Profile user (atau role "Lihat sebagai"); Super Administrator melihat semua beserta badge "Tampil untuk". Murid tidak melihat FAQ kasus guru, guru tidak melihat FAQ portal murid, dst. Seed (`faq_seed.FAQ_ARTICLES`) memuat analisis kasus per role: umum (semua), staf, Admisi (CSO/Marketing/BM/Principal), Data Murid & Keuangan (+Finance), Akademik (Teacher/BM/Principal), kasus khusus Teacher, Finance, CSO, serta kategori **Portal Murid & Wali** (Student/Parent). Target role artikel lama diisi seed hanya bila masih kosong.
- **Kelola:** Super Administrator di Desk `/app/help-article`. Seed awal `faq_seed.setup_faq` (dijalankan `after_migrate`) hanya membuat artikel yang belum ada — artikel yang diedit tidak ditimpa; untuk menyembunyikan, hilangkan centang *published* (jangan hapus).

## 5a. Kunci / buka materi LMS per rombel (6 Nov 2026)

Meniru sistem lama: murid **tidak dapat membuka materi yang belum dibuka guru**, sedangkan materi yang sudah dibuka **tetap dapat dilihat seterusnya**.
- **Unit:** Topik/Bab sebuah Course, per **rombel** (DocType `SPI LMS Topic Access`: student_group, course, topic, is_unlocked, dibuka/dikunci oleh & pada). Tanpa catatan = terkunci. Tugas tanpa topik tidak dikunci.
- **Kelola:** di **Rombel Saya → detail rombel** (satu tombol per topik: terkunci → buka, terbuka → kunci; `spi_fintoedu.api.lms_access.set_topic_access`, spec TEACHER_CLASS.md). Tombol "Akses Materi per Rombel" di halaman LMS dihapus (6 Nov 2026): Teacher hanya rombel yang ia ajar; Branch Manager & Principal rombel cabangnya; Super Administrator semua. CSO/Finance/murid ditolak. Bisa per bab atau Buka semua / Kunci semua; guru dapat mengunci kembali.
- **Penegakan bagi murid** (override `finto_edu.api.lms.get_course_outline`, `get_material_detail`, `ask_ai_on_material`, `mark_article_read`, serta `lms_guard.submit_quiz/submit_assignment`): outline menandai bab `locked` dan tidak mengirim isinya; membuka materi/kuis/tugas/tanya AI dari bab terkunci ditolak (`PermissionError`). Murid melihat bab terbuka bila dibuka untuk **salah satu** rombel aktifnya. Staf melihat semua materi.
- **Catatan peluncuran:** semua bab berstatus terkunci sampai guru membukanya.

## 5. "Sinkronkan ke Rapor" (LMS)

Tombol di **LMS & Pembelajaran** (bukan di menu Siswa). Fungsi: menyalin nilai **tugas LMS** (yang sudah dinilai guru) atau **kuis LMS** (skor terbaik per siswa) menjadi **Assessment Result** resmi pada sebuah Assessment Plan (dibuat otomatis "Tugas LMS: …"/"Kuis LMS: …" atau memilih plan yang ada). Bila opsi *publish* aktif (default), Assessment Result & Plan di-*submit* sehingga nilai tampil di Portal Siswa & Orang Tua. Menjalankan ulang memperbarui hasil pada plan yang sama (tidak duplikat). Hanya Branch Manager, Principal, Teacher. Untuk siswa tombol disembunyikan.

Catatan teknis: grade A–E dihitung dari **persentase** skor terhadap skor maksimum Assessment Plan (mis. 40/50 = 80% → B; diperbaiki 6 Nov 2026 di finto_edu `services/assessment.py`). Bila tidak ada rombel, dibuat rombel "Kelas Umum LMS" otomatis.

## 6. Notifikasi Lonceng

- Badge angka merah = jumlah belum dibaca (`Notification Log.read = 0`); item belum dibaca ditebalkan + titik biru. Polling 2 menit + saat lonceng dibuka.
- **Klik notifikasi** → ditandai dibaca → diarahkan ke halaman sesuai `document_type` (peta `documentTypes` di katalog, hanya rute yang dimiliki role user), dengan `?doc=<nama dokumen>`; tanpa dokumen → tebakan dari subjek (follow-up/pembayaran) → cadangan *Perlu Tindakan*.

| document_type | Halaman tujuan |
|---|---|
| SPI Payment Submission, Payment Entry | Pembayaran SPP |
| SPI Student Follow Up | Follow-up Murid |
| SPI Final Project | Perkembangan Murid |
| Student (geser prabayar cuti, hangus saat Off, murid siap aktif) | Murid |

- **Sumber notifikasi:** pengajuan pembayaran baru → Finance cabang (kecuali pengaju); hasil verifikasi → pengaju; follow-up ditugaskan/jatuh tempo → penanggung jawab; final project diajukan → BM/Principal, diputuskan → guru; geser/hangus prabayar & murid siap aktif → Finance/CSO/Marketing(/BM). Helper: `notifications.create_notification` / `notify_branch`.

## 7. Akun Uji

Lihat [MASTER_TEST_PLAN.md §3.1](../MASTER_TEST_PLAN.md). Akun CSO uji `cso.spi@fintoedu.local` memakai Role Profile **CSO**.

## 8. Hub: satu menu untuk halaman sejenis (6 Nov 2026)

Keputusan pemilik: halaman sejenis tidak perlu menu terpisah. "Murid" & "Status Murid" bahkan digabung menjadi **satu halaman** (11 Nov 2026; rute `*.student-status` dialihkan ke `*.students`). `MENU_HUBS` di `menu-catalog.ts` + `hub` pada tiap fitur:

| Hub (menu) | Tab di dalamnya |
|---|---|
| Tindak Lanjut | Perlu Tindakan · Follow-up Murid — **panel kanan**, bukan menu (lihat di bawah) |
| PPDB & Admisi | Calon Siswa · Jadwal Trial · Batal Registrasi · Buku Tamu |
| Murid | Murid (data + status) · Wali Murid · Mutasi |
| Kelas & Sesi | Rombel & Kelas · Sesi Mengajar · Presensi |
| Penilaian | Penilaian & Rapor · Perkembangan Murid |
| SPP | Tagihan · Pembayaran · Harga SPP · Akun Cara Bayar (Finance) |
| Honor & Gaji | Honor Guru · Penggajian · Slip Gaji Saya |
| Laporan | Laporan Cabang · Laporan Keuangan · Controlling (tab Ringkasan · **Matriks SPP 12 Bulan**) |

**Tindak Lanjut = panel kanan, bukan menu (keputusan pemilik 6 Nov 2026).** Fitur `pane: true` (`action-center`, `follow-ups`) tidak tampil di sidebar/ikon desktop; dibuka lewat tombol tepi kanan "Tindak Lanjut" (lencana = jumlah MENDESAK + HARI INI) di mode web (`DefaultLayout`) maupun desktop (`DesktopShell`), komponen `features/action-center/components/ActionPane.vue`. Isi: tab Perlu Tindakan (ringkasan prioritas, daftar cek, tombol Follow-up/Catat/Buat, "Buka halaman ›") dan Follow-up Murid (follow-up terbuka, "Hanya tugas saya", Buat). Agar tidak menutupi layar utama: pada layar ≥ 1200px panel **menempel** — konten halaman web (`.page-content` margin kanan) dan jendela desktop yang dimaksimalkan menyusut selebar panel (CSS var `--spi-pane-w`, 360px); pada layar sempit panel melayang dan otomatis menutup saat form (modal) dari halaman utama dibuka. Panel berada di bawah lapisan modal. Status buka/tutup diingat per perangkat. Halaman penuh tetap ada lewat ikon "Buka halaman penuh" & tautan notifikasi.

**Matriks SPP 12 Bulan bukan menu sendiri (keputusan pemilik 6 Nov 2026)** — tampil sebagai tab di Controlling Keuangan (`ControllingPage.vue` → `FeeMatrixPage` `embedded`). Rute lama `*/fee-matrix` dialihkan ke `*/controlling?tab=matriks` (tautan Perlu Tindakan, Dashboard, Laporan Keuangan tetap berfungsi).
| Master Data | Pegawai · Master Akademik · Ruangan |

- Sidebar menampilkan **satu item per hub**, aktif di semua halaman hub. Tab hub (`components/HubTabs/HubTabs.vue`, dipasang di `DefaultLayout`) hanya menampilkan bagian yang boleh dipakai role; bila role hanya punya satu bagian, menu memakai label bagian itu dan tab tidak tampil.
- Rute, izin, dan tur per halaman tidak berubah (tetap per fitur).

## 9. Mode Tampilan Desktop — "Finto OS" (6 Nov 2026)

- **Pengaturan:** global untuk semua pengguna, **hanya Super Administrator (`Administrator`)** yang dapat mengubah — mode web: menu profil TopBar → *Ganti ke tampilan Desktop*; mode desktop: menu Start → *Mode tampilan*. Backend `spi_fintoedu.api.ui_settings` (`get_ui_settings` dapat dibaca tamu, `set_ui_mode`), disimpan sebagai default global `spi_ui_mode` (`web` | `desktop`, default `desktop`).
- **Belum login:** animasi booting **Finto OS** (`/boot`, `BootScreen.vue`, setiap halaman dimuat atau di-refresh — "restart" — selama belum login; tidak saat navigasi di dalam aplikasi seperti logout; tanpa tombol Lewati — 12 Nov 2026): logo utama Finto OS (`assets/images/finto-os-logo.png`, juga tombol Start di taskbar — pemilik 12 Nov 2026) muncul, berkilau & berdenyut; tema warna **palet Finto OS**: Navy `#0B1F3B` (primary/latar), Blue `#0E63FF` (brand), Cyan `#00D4C8` (intelligence), Lime `#A7F432` (growth, progress & [ OK ]), Violet `#8B5CF6` (innovation), Light `#F3F7FB` (teks/surface), log booting gaya terminal, progress, grid & scanline → layar kunci bergaya OS (jam besar; klik/tekan tombol → form login dengan **logo SPI**, `DesktopLogin.vue`, rute `/desktop/login`).
- **Splash screen logo SPI** (`index.html`) hanya untuk mode web; mode desktop menyembunyikannya sejak muat pertama (mode terakhir di-cache `localStorage.spi_ui_mode` oleh `stores/ui.ts`).
- **Ikon desktop dapat dipindah (seret & lepas)** ke sel grid mana pun; sel terisi → bertukar tempat. Posisi disimpan per
  pengguna & per peran yang ditampilkan (`api/desktop_prefs.set_icon_layout` / `reset_icon_layout`, user default
  `spi_desktop_icon_layout`). **Susunan bawaan** (12 Nov 2026): Master Data dulu → Utama → Murid & Admisi → Akademik →
  Keuangan → Laporan → Portal → Pengaturan Sistem → Bantuan; tiap kategori mulai di kolom baru (layar sempit: dipisah satu
  sel kosong). Menu baru otomatis ditempatkan dekat kategorinya. Klik kanan desktop → **Rapikan ikon (susunan bawaan)**.
  Logika: `features/desktop/iconLayout.ts`.
- **Jendela dibuka dengan ukuran normal** (keputusan pemilik 11 Nov 2026, menggantikan "langsung dimaksimalkan"; layar < 768px tetap penuh); tombol jendela berwarna: minimize **kuning**, maximize **hijau**, tutup **merah** (`DesktopWindow.vue`).
- **Ikon per menu berbeda** (warna & ikon, `features/desktop/appStyles.ts`) di desktop & menu Start; tombol Start memakai logo Finto OS.
- **Klik kanan di area kosong desktop** → menu konteks: Ganti latar belakang…, Buka menu Start, Tampilkan panduan, Muat ulang.
- **Latar belakang per pengguna** (personalisasi; user A tidak memengaruhi user B): 8 preset (`wallpapers.ts`) atau gambar unggahan sendiri (JPG/PNG/WEBP ≤ 5 MB, File privat yang dilampirkan ke User pemilik, unggahan lama dihapus). API `spi_fintoedu.api.desktop_prefs` (`get_desktop_prefs`, `set_wallpaper_preset`, `upload_wallpaper`, `reset_wallpaper`), disimpan sebagai user default `spi_desktop_wallpaper`. Dev: vite mem-proxy `/private` agar gambar privat tampil.
- **Sudah login:** langsung desktop (`/desktop`, `DesktopShell.vue`):
  - Ikon desktop = menu role (hub/menu yang sama dengan sidebar). Klik dua kali (layar sentuh: sekali) membuka jendela.
  - Setiap halaman terbuka sebagai **jendela** (`DesktopWindow.vue`): geser lewat judul, ubah ukuran dari sudut, minimalkan/maksimalkan/tutup, klik dua kali judul = maksimalkan, tombol **?** = tur halaman. Satu jendela per halaman; tab hub berpindah bagian di jendela yang sama. Di HP jendela selalu penuh.
  - Taskbar: tombol Start (logo), Cari, ikon jendela terbuka (klik = fokus/minimalkan), notifikasi (badge belum dibaca; klik → buka jendela terkait), panduan, jam & tanggal.
  - Menu Start: pencarian aplikasi (Enter = buka hasil pertama; tidak ditemukan → cari di FAQ), daftar aplikasi, *Terakhir dibuka*, pengguna, tampilkan ulang panduan, keluar. Super Administrator: *Lihat sebagai* role lain & *Mode tampilan*.
  - Jendela terbuka disimpan per sesi browser (refresh tidak menutup jendela).
- **Cara kerja:** router (`router/index.ts`, `desktopGuard`) memeriksa hak akses rute dengan aturan yang sama seperti mode web, lalu membuka rute tujuan sebagai jendela (URL tetap `/desktop`) — termasuk `router.push`/`router-link` dari dalam halaman. Halaman tidak perlu diubah: `DefaultLayout` mendeteksi `DESKTOP_WINDOW` dan hanya merender isi halaman.
- **Aturan untuk halaman baru:** baca rute lewat `usePageRoute()` (`composables/usePageRoute.ts`), **bukan** `useRoute()`, bila memakai `route.path/query/name` — di dalam jendela `useRoute()` menunjuk `/desktop`.
- Tur selamat datang mode desktop menyorot ikon, Start, Cari, jendela taskbar, dan notifikasi.

## 10. Ukuran huruf (8 Nov 2026)
Keputusan pemilik: ukuran dasar tetap (13px, kecil 12px). Hanya teks yang terlalu kecil yang dinaikkan:
9px → 11px dan 10px → 12px. Jangan memakai ukuran di bawah 11px untuk teks baru.

## 11. Ganti Password (8 Nov 2026)
Semua user: menu profil → **Ganti Password** (mode desktop: tombol kunci di samping Keluar). Isi password saat ini +
password baru 2× (kebijakan kekuatan password Frappe). User hasil migrasi (`User.custom_must_change_password = 1`,
password awal bersama) otomatis melihat jendela ini setelah login dan tidak bisa menutupnya sebelum mengganti password.
Backend `spi_fintoedu.api.account.get_password_status` / `change_my_password`.
