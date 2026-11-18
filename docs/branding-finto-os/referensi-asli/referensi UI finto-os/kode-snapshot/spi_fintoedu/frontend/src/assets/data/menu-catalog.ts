/**
 * KATALOG MENU SPI — satu sumber kebenaran untuk:
 *   1. Sidebar (menu-items.ts): menu dikelompokkan per kategori dan HANYA tampil untuk role yang
 *      benar-benar bisa memakai halamannya (lihat docs/specs/MENU_AND_HELP.md §2).
 *   2. Wizard panduan halaman (PageGuide): `description` + `steps`.
 *   3. Tujuan klik notifikasi lonceng (notification-route.ts): `documentTypes`.
 *
 * Menambah menu baru: tambahkan entri di MENU_FEATURES + rute di router/profile-routes/<role>.ts,
 * lalu perbarui docs/specs/MENU_AND_HELP.md.
 */
import type { RoleProfile } from "@/types/auth";

export type MenuGroupId =
  | "utama"
  | "admisi"
  | "murid"
  | "akademik"
  | "keuangan"
  | "laporan"
  | "honor"
  | "master"
  | "portal"
  | "sistem"
  | "bantuan";

/** Urutan & label kategori di sidebar. */
export const MENU_GROUPS: { id: MenuGroupId; label: string }[] = [
  { id: "utama", label: "Utama" },
  { id: "admisi", label: "Murid & Admisi" },
  { id: "murid", label: "Murid & Admisi" },
  { id: "akademik", label: "Akademik" },
  { id: "keuangan", label: "Keuangan" },
  { id: "honor", label: "Keuangan" },
  { id: "laporan", label: "Laporan" },
  { id: "master", label: "Master Data" },
  { id: "portal", label: "Portal" },
  { id: "sistem", label: "Pengaturan Sistem" },
  { id: "bantuan", label: "Bantuan" },
];

export type GuideStepDef = { title: string; body: string; icon?: string };

/** Konteks user untuk menyaring menu di luar role (mis. kategori kepegawaian guru). */
export type MenuContext = {
  role: RoleProfile | null;
  /** "Tetap" | "Freelance" | null (dari spi_fintoedu.api.employment.get_my_employment). */
  employmentCategory: string | null;
};

/**
 * HUB = satu menu untuk beberapa halaman sejenis (keputusan pemilik 6 Nov 2026: "Status Murid" & "Murid" cukup
 * satu menu). Sidebar menampilkan satu item per hub; di dalam halaman, tab (HubTabs) berpindah antar bagian.
 * Hanya bagian yang boleh dipakai role yang muncul. Bila role hanya punya 1 bagian, menu memakai label bagian itu.
 */
export type MenuHub = { id: string; group: MenuGroupId; label: string; icon: string; description: string };

export const MENU_HUBS: MenuHub[] = [
  { id: "tindak-lanjut", group: "utama", label: "Tindak Lanjut", icon: "iconoir-warning-triangle", description: "Perlu Tindakan & Follow-up Murid dalam satu tempat." },
  { id: "admisi", group: "admisi", label: "PPDB & Admisi", icon: "iconoir-user-plus", description: "Calon siswa, trial class, batal registrasi, dan buku tamu." },
  { id: "murid", group: "admisi", label: "Murid", icon: "iconoir-user", description: "Data murid, status (Pending/Aktif/Cuti/Off), wali murid, dan mutasi." },
  { id: "kelas", group: "akademik", label: "Kelas & Sesi", icon: "iconoir-community", description: "Rombel, sesi mengajar, dan presensi." },
  { id: "penilaian", group: "akademik", label: "Penilaian", icon: "iconoir-graduation-cap", description: "Penilaian & rapor, perkembangan murid, dan final project." },
  { id: "spp", group: "keuangan", label: "SPP", icon: "iconoir-hand-cash", description: "Tagihan, pembayaran, dan harga SPP." },
  { id: "honor", group: "keuangan", label: "Honor & Gaji", icon: "iconoir-wallet", description: "Honor guru, penggajian, dan slip gaji." },
  { id: "laporan", group: "laporan", label: "Laporan", icon: "iconoir-stats-report", description: "Laporan cabang, laporan keuangan, dan controlling." },
  { id: "master", group: "master", label: "Master Data", icon: "iconoir-database", description: "Pegawai, master akademik, dan ruangan." },
];

export type MenuFeature = {
  id: string;
  group: MenuGroupId;
  /** Hub tempat halaman ini menjadi salah satu tab (lihat MENU_HUBS). */
  hub?: string;
  /** Label pendek di tab hub (default = label). */
  tabLabel?: string;
  label: string;
  /** Label khusus per role (misal "Honor Saya" untuk guru). */
  labelByRole?: Partial<Record<RoleProfile, string>>;
  icon: string;
  /** Ringkasan fungsi menu (tooltip sidebar & langkah pertama wizard). */
  description: string;
  /** Langkah wizard panduan saat halaman pertama kali dibuka. */
  steps: GuideStepDef[];
  /** Nama rute per role. Role yang tidak tercantum = menu disembunyikan. */
  routes: Partial<Record<RoleProfile, string>>;
  /** DocType notifikasi yang diarahkan ke menu ini saat diklik. */
  documentTypes?: string[];
  /** Syarat tambahan selain role (default: selalu tampil bila role punya rute). */
  when?: (ctx: MenuContext) => boolean;
  /**
   * Tidak tampil di sidebar/ikon desktop; dibuka lewat panel kanan "Tindak Lanjut" (keputusan pemilik 6 Nov 2026).
   * Rute halaman penuhnya tetap ada (tautan notifikasi, "Buka halaman penuh").
   */
  pane?: boolean;
};

const ROUTE_PREFIX: Partial<Record<RoleProfile, string>> = {
  "Branch Manager": "branch-manager",
  Principal: "principal",
  Finance: "finance",
  CSO: "cso",
  Marketing: "marketing",
  Teacher: "teacher",
  Parent: "parent",
  Student: "student",
  "Staff Yayasan": "yayasan",
};

/** Peta rute `<prefix role>.<slug>` untuk daftar role (+ override nama rute yang berbeda). */
const routesFor = (
  slug: string,
  roles: RoleProfile[],
  overrides: Partial<Record<RoleProfile, string>> = {},
): Partial<Record<RoleProfile, string>> => ({
  ...Object.fromEntries(roles.map((role) => [role, `${ROUTE_PREFIX[role]}.${slug}`])),
  ...overrides,
});

export const MENU_FEATURES: MenuFeature[] = [
  // ───────────── Utama ─────────────
  {
    id: "action-center",
    hub: "tindak-lanjut",
    pane: true,
    group: "utama",
    label: "Perlu Tindakan",
    icon: "iconoir-warning-triangle",
    description: "Daftar pekerjaan cabang yang harus ditindaklanjuti, diurutkan Mendesak → Hari Ini → Minggu Ini → Pantau.",
    steps: [
      { title: "Mulai hari dari sini", body: "Halaman ini mengumpulkan semua hal yang perlu dikerjakan cabang: tunggakan SPP, murid pending, follow-up jatuh tempo, pengajuan menunggu verifikasi, dan lainnya.", icon: "iconoir-warning-triangle" },
      { title: "Kerjakan dari yang Mendesak", body: "Klik sebuah kelompok untuk membuka daftarnya. Tombol pada setiap baris membawa Anda ke halaman tempat keputusan diambil.", icon: "iconoir-list" },
      { title: "Catat follow-up langsung", body: "Untuk murid yang perlu dihubungi, Anda bisa langsung membuat atau mencatat hasil follow-up dari halaman ini.", icon: "iconoir-chat-bubble" },
    ],
    routes: routesFor("action-center", ["Branch Manager", "Principal", "Finance", "CSO", "Marketing"]),
  },
  {
    id: "follow-ups",
    hub: "tindak-lanjut",
    pane: true,
    group: "utama",
    label: "Follow-up Murid",
    icon: "iconoir-chat-bubble",
    description: "Tindak lanjut ke murid/orang tua (SPP, cuti, off, akademik) beserta penanggung jawab dan tenggatnya.",
    steps: [
      { title: "Satu tempat untuk semua tindak lanjut", body: "Setiap follow-up punya jenis (SPP, Cuti, Off, Akademik, dll.), penanggung jawab, tenggat, dan riwayat catatan.", icon: "iconoir-chat-bubble" },
      { title: "Filter \"Tugas saya\"", body: "Gunakan filter status, jenis, atau Tugas Saya untuk fokus pada pekerjaan Anda. Penanggung jawab mendapat notifikasi lonceng saat ditugaskan.", icon: "iconoir-filter" },
      { title: "Otomatis selesai", body: "Follow-up SPP tertutup otomatis begitu tunggakan murid lunas, jadi Anda tidak perlu menutupnya manual.", icon: "iconoir-check-circle" },
    ],
    routes: routesFor("follow-ups", ["Branch Manager", "Principal", "Finance", "CSO", "Marketing"]),
    documentTypes: ["SPI Student Follow Up"],
  },

  // ───────────── Admisi & Prospek ─────────────
  {
    id: "admissions",
    hub: "admisi",
    tabLabel: "Calon Siswa",
    group: "admisi",
    label: "PPDB & Admisi",
    icon: "iconoir-user-plus",
    description: "Daftar calon siswa (lead) dari PPDB online maupun walk-in, sampai dikonversi menjadi siswa.",
    steps: [
      { title: "Semua calon siswa", body: "Pendaftar dari formulir publik /registers dan yang diinput staf muncul di sini beserta statistik pendaftar.", icon: "iconoir-user-plus" },
      { title: "Catat pendaftar baru", body: "Gunakan tombol tambah untuk mencatat calon siswa yang datang langsung atau menghubungi via WhatsApp.", icon: "iconoir-plus-circle" },
      { title: "Konversi jadi siswa", body: "Setelah orang tua setuju mendaftar, konversi calon menjadi Siswa. Siswa baru berstatus Pending sampai syarat aktivasi (pembayaran pertama terverifikasi & data wajib) terpenuhi.", icon: "iconoir-graduation-cap" },
    ],
    routes: routesFor("admissions", ["Branch Manager", "Principal", "CSO", "Marketing"]),
    documentTypes: ["Student Applicant"],
  },
  {
    id: "trial-schedule",
    hub: "admisi",
    group: "admisi",
    label: "Jadwal Trial Class",
    icon: "iconoir-calendar",
    description: "Jadwal kelas percobaan calon siswa, guru penanggung jawab, kehadiran, dan catatan hasil trial.",
    steps: [
      { title: "Pantau trial", body: "Lihat semua trial yang terjadwal beserta guru yang ditugaskan dan statusnya.", icon: "iconoir-calendar" },
      { title: "Hasil trial", body: "Guru mencatat kehadiran (Hadir / Tidak Hadir / Batal) dan catatan evaluasi. CSO tidak perlu menunggu catatan guru untuk melanjutkan pendaftaran.", icon: "iconoir-page-edit" },
    ],
    routes: routesFor("trial-schedule", ["Branch Manager", "Principal", "CSO", "Marketing", "Teacher"]),
    // Notifikasi trial (guru); CSO/BM diarahkan ke PPDB lebih dulu karena urutan katalog.
    documentTypes: ["Student Applicant"],
  },
  {
    id: "cancel-register",
    hub: "admisi",
    group: "admisi",
    label: "Batal Registrasi",
    icon: "iconoir-cancel",
    description: "Arsip calon siswa yang batal mendaftar beserta alasannya; bisa dipulihkan kembali.",
    steps: [
      { title: "Data tidak hilang", body: "Calon siswa yang batal diarsipkan beserta alasannya, bukan dihapus.", icon: "iconoir-archive" },
      { title: "Pulihkan bila berubah pikiran", body: "Klik Pulihkan untuk mengembalikan calon siswa ke antrean PPDB aktif.", icon: "iconoir-undo" },
    ],
    routes: routesFor("cancel-register", ["Branch Manager", "Principal", "CSO", "Marketing"]),
  },
  {
    id: "guest-book",
    hub: "admisi",
    group: "admisi",
    label: "Buku Tamu",
    icon: "iconoir-user-star",
    description: "Catatan pengunjung cabang: sekolah/instansi mitra, tamu umum, dan calon orang tua.",
    steps: [
      { title: "Catat setiap kunjungan", body: "Isi nama, asal instansi, kontak WhatsApp, dan tujuan kunjungan. Calon orang tua yang berkunjung bisa ditindaklanjuti sebagai lead.", icon: "iconoir-user-star" },
    ],
    routes: routesFor("guest-book", ["Branch Manager", "Principal", "CSO", "Marketing"]),
  },

  // ───────────── Data Murid ─────────────
  {
    // Murid + Status Murid jadi SATU menu & halaman (keputusan pemilik 11 Nov 2026); rute *.student-status dialihkan ke sini.
    id: "students",
    hub: "murid",
    tabLabel: "Murid",
    group: "murid",
    label: "Murid",
    icon: "iconoir-user",
    description: "Data pokok murid (NIS/NISN, kontak) sekaligus statusnya (Pending/Aktif/Cuti/Off) dengan tanggal efektif; hanya murid Aktif yang ditagih SPP.",
    steps: [
      { title: "Satu halaman untuk murid", body: "Data murid dan statusnya ada di sini. Tombol yang tidak bisa Anda pakai otomatis disembunyikan.", icon: "iconoir-user" },
      { title: "Empat status murid", body: "Pending = belum memenuhi syarat aktivasi. Aktif = ikut kelas & ditagih SPP. Cuti = berhenti sementara. Off = berhenti.", icon: "iconoir-user-badge-check" },
      { title: "Ubah status dengan tanggal efektif", body: "Branch Manager, CSO, dan Marketing dapat mengubah status. Bulan SPP prabayar di masa cuti digeser otomatis; saat Off, prabayar/saldo diproses sesuai aturan hangus.", icon: "iconoir-calendar" },
      { title: "Tambah & ubah data", body: "Branch Manager, Principal, dan CSO dapat menambah dan mengubah data murid; hapus hanya Branch Manager & Principal. Finance dan Marketing melihat saja.", icon: "iconoir-edit-pencil" },
    ],
    routes: routesFor("students", ["Branch Manager", "Principal", "Finance", "CSO", "Marketing"]),
    documentTypes: ["Student"],
  },
  {
    id: "guardians",
    hub: "murid",
    group: "murid",
    label: "Wali Murid",
    icon: "iconoir-shield-alert",
    description: "Data orang tua/wali murid, kontak, dan anak yang terhubung (satu wali bisa punya beberapa anak).",
    steps: [
      { title: "Hubungkan wali dan anak", body: "Tambahkan wali lalu tautkan ke satu atau lebih siswa. Email wali dipakai untuk login Portal Orang Tua.", icon: "iconoir-shield-alert" },
    ],
    routes: routesFor("guardians", ["Branch Manager", "Principal"]),
  },
  {
    id: "transfers",
    hub: "murid",
    group: "murid",
    label: "Mutasi Siswa",
    icon: "iconoir-shuffle",
    description: "Pengajuan pindah siswa antar unit dengan persetujuan unit asal dan unit tujuan.",
    steps: [
      { title: "Mutasi dua pihak", body: "Unit asal mengajukan & menyetujui, unit tujuan menerima. Pantau status setiap mutasi di sini.", icon: "iconoir-shuffle" },
    ],
    routes: routesFor("transfers", ["Branch Manager", "Principal"]),
  },

  // ───────────── Akademik ─────────────
  {
    id: "student-groups",
    hub: "kelas",
    group: "akademik",
    label: "Rombel & Kelas",
    labelByRole: { Teacher: "Rombel Saya" },
    icon: "iconoir-community",
    description: "Rombongan belajar/kelas: program, tahun ajaran, kapasitas, anggota siswa, dan guru pengajar. Perubahan rombel hanya oleh CSO; guru hanya melihat rombel yang diajar.",
    steps: [
      { title: "Kelola kelas", body: "Buat rombel, atur kapasitas, serta tambah atau keluarkan siswa dari kelas.", icon: "iconoir-community" },
    ],
    routes: routesFor("student-groups", ["Branch Manager", "Principal", "CSO", "Teacher"]),
  },
  {
    id: "sessions",
    hub: "kelas",
    group: "akademik",
    label: "Sesi Mengajar",
    icon: "iconoir-calendar",
    description: "Realisasi sesi kelas (Terlaksana/Batal/Make-up), guru pengganti, check-in/out, dan kehadiran murid. Sesi berhonor menjadi dasar honor guru freelance.",
    steps: [
      { title: "Sesi dibuat otomatis", body: "Sesi dibuat dari jadwal mingguan rombel. Anda cukup mengonfirmasi realisasinya.", icon: "iconoir-calendar" },
      { title: "Konfirmasi realisasi", body: "Tandai Terlaksana/Batal/Make-up, isi guru pengganti bila ada, dan presensi murid.", icon: "iconoir-check-circle" },
      { title: "Dasar honor", body: "Hanya sesi yang terkonfirmasi dan memenuhi syarat yang dihitung ke honor guru freelance.", icon: "iconoir-hand-cash" },
    ],
    routes: routesFor("sessions", ["Branch Manager", "Principal", "Finance", "Teacher"]),
  },
  {
    id: "attendance",
    hub: "kelas",
    group: "akademik",
    label: "Presensi Siswa",
    icon: "iconoir-calendar",
    description: "Presensi harian per rombel beserta ringkasan hadir, absen, terlambat, dan persentase kehadiran.",
    steps: [
      { title: "Isi presensi", body: "Pilih rombel dan tanggal, lalu tandai status kehadiran setiap siswa dan simpan.", icon: "iconoir-calendar" },
    ],
    routes: routesFor("attendance", ["Branch Manager", "Principal", "Teacher"]),
  },
  {
    id: "assessments",
    hub: "penilaian",
    group: "akademik",
    label: "Penilaian & Rapor",
    icon: "iconoir-page-edit",
    description: "Rencana penilaian per rombel, input nilai, dan publikasi nilai ke portal siswa/orang tua.",
    steps: [
      { title: "Buat rencana penilaian", body: "Tentukan jenis (tugas/UTS/UAS) dan rombelnya.", icon: "iconoir-page-edit" },
      { title: "Isi nilai lalu publikasikan", body: "Simpan sebagai draf selama masih diisi. Setelah dipublikasikan, nilai tampil di Portal Siswa & Orang Tua.", icon: "iconoir-send" },
    ],
    routes: routesFor("assessments", ["Branch Manager", "Principal", "Teacher"]),
  },
  {
    id: "academic-progress",
    hub: "penilaian",
    group: "akademik",
    label: "Perkembangan Murid",
    icon: "iconoir-graduation-cap",
    description: "Kehadiran 90 hari terakhir, level, dan final project murid; persetujuan final project menjadi sertifikat.",
    steps: [
      { title: "Pantau perkembangan", body: "Lihat kehadiran, grup/level, dan status final project setiap murid.", icon: "iconoir-graduation-cap" },
      { title: "Final project", body: "Guru mengisi dan mengajukan nilai. Branch Manager/Principal menyetujui atau menolak; jika disetujui & lulus, nomor sertifikat dibuat otomatis.", icon: "iconoir-medal" },
    ],
    routes: routesFor("academic-progress", ["Branch Manager", "Principal", "Teacher", "CSO", "Marketing"]),
    documentTypes: ["SPI Final Project"],
  },
  {
    id: "lms",
    group: "akademik",
    label: "LMS & Pembelajaran",
    icon: "iconoir-book-stack",
    description: "Materi, kuis, dan tugas per mata pelajaran. Guru menilai tugas dan menyinkronkan nilai ke rapor.",
    steps: [
      { title: "Pilih mata pelajaran", body: "Buka silabus untuk membaca materi, mengerjakan kuis, dan mengumpulkan tugas.", icon: "iconoir-book-stack" },
      { title: "Untuk guru: Sinkronkan ke Rapor", body: "Setelah tugas dinilai atau kuis selesai, tombol Sinkronkan ke Rapor menyalin nilai ke Penilaian & Rapor (Assessment Result). Bila opsi publikasi aktif, nilai langsung tampil di portal siswa & orang tua.", icon: "iconoir-refresh-double" },
    ],
    routes: routesFor("lms", ["Branch Manager", "Principal", "Teacher"]),
  },

  // ───────────── Keuangan SPP ─────────────
  {
    id: "fees",
    hub: "spp",
    group: "keuangan",
    label: "Tagihan SPP",
    icon: "iconoir-hand-cash",
    description: "Daftar invoice SPP (total, sisa, terbayar); buat tagihan manual atau tagihan bulanan massal.",
    steps: [
      { title: "Daftar tagihan", body: "Semua invoice SPP cabang beserta sisa tagihannya. Tagihan bulanan murid Aktif juga dibuat otomatis oleh sistem.", icon: "iconoir-hand-cash" },
      { title: "Buat tagihan", body: "Gunakan Buat Tagihan untuk satu murid atau tagihan bulanan massal. Nomor invoice: {kode cabang}/SPP/{tahun}/0001.", icon: "iconoir-plus-circle" },
    ],
    // CSO: lihat & cetak tagihan/kwitansi saja (11 Nov 2026)
    routes: routesFor("fees", ["Branch Manager", "Principal", "Finance", "CSO"]),
  },
  {
    id: "spp-payments",
    hub: "spp",
    group: "keuangan",
    label: "Pembayaran SPP",
    icon: "iconoir-wallet",
    description: "Pembayaran dua tahap: staf mengajukan pembayaran + bukti, Finance (bukan pengaju) memverifikasi menjadi Payment Entry.",
    steps: [
      { title: "Tahap 1: ajukan", body: "CSO/Finance/Branch Manager mengajukan pembayaran yang diterima beserta bukti transfer. Pengajuan belum mengurangi tagihan.", icon: "iconoir-upload" },
      { title: "Tahap 2: verifikasi Finance", body: "Finance yang bukan pengaju memverifikasi. Setelah Terverifikasi, Payment Entry dibuat dan dialokasikan FIFO ke tagihan tertua; kelebihan menjadi saldo murid.", icon: "iconoir-check-circle" },
      { title: "Notifikasi otomatis", body: "Finance mendapat notifikasi saat ada pengajuan baru, dan pengaju mendapat notifikasi hasil verifikasi.", icon: "iconoir-bell" },
    ],
    routes: routesFor("spp-payments", ["Branch Manager", "Principal", "Finance", "CSO", "Marketing"]),
    documentTypes: ["SPI Payment Submission", "Payment Entry"],
  },
  {
    id: "spp-prices",
    hub: "spp",
    group: "keuangan",
    label: "Harga SPP",
    icon: "iconoir-label",
    description: "Harga SPP per program per cabang & tahun ajaran, serta harga khusus murid (diskon, beasiswa, harga lama).",
    steps: [
      { title: "Harga program", body: "Atur harga SPP setiap program untuk cabang dan tahun ajaran.", icon: "iconoir-label" },
      { title: "Harga khusus murid", body: "Untuk diskon/beasiswa/harga lama, tambahkan harga khusus murid beserta alasannya. Tagihan otomatis memakai harga khusus bila ada.", icon: "iconoir-user" },
    ],
    routes: routesFor("spp-prices", ["Branch Manager", "Principal", "Finance"]),
  },
  {
    id: "payment-mode-accounts",
    hub: "spp",
    group: "keuangan",
    label: "Akun Cara Bayar",
    icon: "iconoir-bank",
    description: "Akun Kas/Bank default setiap cara bayar (Tunai, Transfer Bank, QRIS, VA, Lainnya) per cabang — dipakai otomatis saat mencatat pembayaran SPP.",
    steps: [
      { title: "Pilih cabang", body: "Setiap cabang punya pengaturan sendiri, mis. Transfer Bank cabang A masuk ke Bank BCA, cabang B ke Bank Mandiri.", icon: "iconoir-building" },
      { title: "Pilih akun", body: "Pilih akun Kas/Bank untuk tiap cara bayar. Tersimpan langsung dan tidak berubah saat sistem diperbarui.", icon: "iconoir-bank" },
      { title: "Kosongkan bila perlu", body: "Cara bayar tanpa pengaturan memakai akun Kas/Bank default cabang.", icon: "iconoir-undo" },
    ],
    routes: routesFor("payment-mode-accounts", ["Finance"]),
  },

  // ───────────── Laporan ─────────────
  {
    id: "reports",
    hub: "laporan",
    group: "laporan",
    label: "Laporan Cabang",
    icon: "iconoir-stats-report",
    description: "Tren 12 bulan (murid aktif, baru, rejoin, off, tagihan, kas masuk), laporan murid Off, dan matriks status murid.",
    steps: [
      { title: "Pengganti sheet Excel", body: "Laporan bulanan cabang yang dulu dibuat manual di Excel, kini otomatis dari data sistem.", icon: "iconoir-stats-report" },
    ],
    routes: routesFor("reports", ["Branch Manager", "Principal", "Finance", "CSO", "Marketing"]),
  },
  {
    id: "financial-statements",
    hub: "laporan",
    group: "laporan",
    label: "Laporan Keuangan",
    icon: "iconoir-graph-up",
    description: "Neraca, Laba Rugi, Arus Kas, dan Buku Besar per unit dengan filter tanggal dan cetak.",
    steps: [
      { title: "Laporan formal", body: "Pilih unit dan periode, lalu pindah antar tab Neraca, Laba Rugi, Arus Kas, dan Buku Besar. Gunakan tombol cetak untuk arsip.", icon: "iconoir-graph-up" },
    ],
    routes: routesFor("financial-statements", ["Branch Manager", "Principal", "Finance"]),
  },
  {
    id: "controlling",
    hub: "laporan",
    group: "laporan",
    label: "Controlling Keuangan",
    icon: "iconoir-percentage-square",
    description: "Pantauan eksekutif bulanan: saldo kas & bank, kapasitas vs realisasi SPP, estimasi setoran ke pusat, murid onsite vs online, serta Matriks SPP 12 bulan per murid.",
    steps: [
      { title: "Ringkasan eksekutif", body: "Bandingkan kapasitas pendapatan SPP dengan realisasi penerimaan, dan pantau saldo kas/bank cabang.", icon: "iconoir-percentage-square" },
      { title: "Matriks SPP 12 Bulan", body: "Buka tab Matriks SPP 12 Bulan untuk melihat status bayar Januari–Desember per murid. Hijau = lunas; klik sel untuk rincian, menerbitkan tagihan, atau mencatat pembayaran.", icon: "iconoir-table" },
    ],
    routes: routesFor("controlling", ["Branch Manager", "Principal", "Finance"]),
  },

  // ───────────── Honor & Gaji ─────────────
  {
    id: "teacher-fees",
    hub: "honor",
    tabLabel: "Honor Guru",
    group: "honor",
    label: "Rekap Honor Guru",
    labelByRole: { Teacher: "Honor Saya" },
    icon: "iconoir-hand-cash",
    description: "Rekap honor guru freelance dari sesi berhonor per periode, dompet honor (diperoleh vs dibayarkan), dan tarif honor.",
    steps: [
      { title: "Honor dari sesi", body: "Honor dihitung dari sesi mengajar yang terkonfirmasi, dirinci per tipe kelas dan level.", icon: "iconoir-hand-cash" },
      { title: "Dompet honor", body: "Dompet menunjukkan honor yang diperoleh dan yang sudah dibayarkan per bulan. Finance menandai honor bulanan sudah dibayar.", icon: "iconoir-wallet" },
      { title: "Tarif", body: "Tarif freelance cabang (tipe kelas × bahasa × level) dan tarif khusus rombel diatur oleh Finance/Branch Manager.", icon: "iconoir-label" },
    ],
    routes: routesFor("teacher-fees", ["Branch Manager", "Principal", "Finance"], { Teacher: "teacher.fee-recap" }),
    // Guru tetap digaji bulanan (Payroll), tidak menerima honor sesi.
    when: (ctx) => !(ctx.role === "Teacher" && ctx.employmentCategory === "Tetap"),
  },
  {
    id: "payroll",
    hub: "honor",
    tabLabel: "Penggajian",
    group: "honor",
    label: "Penggajian (Payroll)",
    icon: "iconoir-wallet",
    description: "Gaji bulanan pegawai & guru tetap lewat Payroll HRMS: atur gaji pokok, proses gaji per bulan, kirim slip. Guru freelance tidak masuk payroll (dibayar honor per sesi).",
    steps: [
      { title: "Siapkan akun & gaji pokok", body: "Pastikan akun hutang gaji & beban gaji cabang terisi, lalu isi gaji pokok setiap pegawai tetap." },
      { title: "Proses gaji bulanan", body: "Pilih bulan lalu buat slip gaji draf untuk semua pegawai tetap; periksa, kemudian kirim (submit) agar jurnal gaji tercatat dan slip tampil di Slip Gaji Saya." },
    ],
    routes: routesFor("payroll", ["Finance", "Branch Manager"]),
  },
  {
    id: "my-slip",
    hub: "honor",
    group: "honor",
    label: "Slip Gaji Saya",
    icon: "iconoir-page",
    description: "Riwayat slip gaji bulanan Anda (Payroll HRMS): gaji bersih, periode, rincian pendapatan dan potongan.",
    steps: [
      { title: "Slip pribadi", body: "Hanya slip milik Anda (ditautkan lewat data Employee) yang tampil. Jika kosong, hubungi Finance cabang.", icon: "iconoir-page" },
    ],
    routes: routesFor("my-slip", ["Branch Manager", "Principal", "Finance", "CSO", "Marketing", "Teacher"]),
    // Guru freelance tidak menerima slip gaji: riwayat honornya ada di "Honor Saya".
    when: (ctx) => !(ctx.role === "Teacher" && ctx.employmentCategory === "Freelance"),
  },

  // ───────────── Master Data ─────────────
  {
    id: "employees",
    hub: "master",
    group: "master",
    label: "Pegawai",
    icon: "iconoir-group",
    description: "Data karyawan unit: status, jabatan, dan unit; tambah, ubah, nonaktifkan, dan ekspor.",
    steps: [
      { title: "Data pegawai", body: "Kelola data karyawan dan guru unit Anda. Akun guru perlu ditautkan ke data Instructor agar bisa memakai Sesi Mengajar dan Honor.", icon: "iconoir-group" },
    ],
    routes: routesFor("employees", ["Branch Manager", "Principal"]),
  },
  {
    id: "academic-master",
    hub: "master",
    group: "master",
    label: "Master Akademik",
    icon: "iconoir-book-stack",
    description: "Data dasar kalender akademik: Tahun Akademik, Term, dan Program.",
    steps: [
      { title: "Fondasi akademik", body: "Tahun Akademik, Term, dan Program dipakai oleh rombel, harga SPP, dan penilaian. Atur di sini sebelum membuat rombel baru.", icon: "iconoir-book-stack" },
    ],
    routes: routesFor("academic-master", ["Branch Manager", "Principal"]),
  },
  {
    id: "curriculum",
    hub: "master",
    group: "master",
    label: "Kurikulum",
    icon: "iconoir-journal",
    description: "Program, course (level), dan topik/materi SPI untuk semua cabang. Hanya staf yayasan.",
    steps: [
      { title: "Susun kurikulum", body: "Program berisi daftar course; course berisi urutan bab/topik; topik berisi materi murid, panduan guru, dan lampiran.", icon: "iconoir-journal" },
      { title: "Urutan penting", body: "Urutan topik di course = urutan bab yang dibuka guru untuk rombel. Ubah urutan dengan tombol panah.", icon: "iconoir-sort" },
    ],
    routes: { "Staff Yayasan": "yayasan.curriculum" },
  },
  {
    id: "rooms",
    hub: "master",
    group: "master",
    label: "Ruangan",
    icon: "iconoir-home-alt",
    description: "Ruang kelas fisik (offline) dan virtual (online), kapasitas, lokasi/link, dan izin jadwal bentrok.",
    steps: [
      { title: "Ruangan & link kelas", body: "Ruangan offline punya alamat; ruangan online berisi link (misal Google Meet). Centang Izinkan Jadwal Bentrok untuk ruang online yang boleh dipakai bersamaan.", icon: "iconoir-home-alt" },
    ],
    routes: routesFor("rooms", ["Branch Manager", "Principal"]),
  },

  // ───────────── Portal ─────────────
  {
    id: "parent-portal",
    group: "portal",
    label: "Monitoring Anak",
    icon: "iconoir-user-star",
    description: "Pilih anak untuk melihat kehadiran, tagihan SPP yang belum lunas, dan nilai yang sudah dipublikasikan guru.",
    steps: [
      { title: "Pantau anak Anda", body: "Pilih nama anak untuk melihat kehadiran, tagihan, dan nilai. Anak tampil bila email akun Anda terdaftar sebagai wali di sekolah.", icon: "iconoir-user-star" },
    ],
    routes: { Parent: "parent.portal" },
  },
  {
    id: "student-portal",
    group: "portal",
    label: "Portal Hasil Belajar",
    icon: "iconoir-bookmark-book",
    description: "Kehadiran, status tagihan SPP, dan nilai yang sudah dipublikasikan guru.",
    steps: [
      { title: "Hasil belajarmu", body: "Lihat kehadiran, tagihan, dan nilai yang sudah dipublikasikan guru.", icon: "iconoir-bookmark-book" },
    ],
    routes: { Student: "student.portal" },
  },
  {
    id: "student-lms",
    group: "portal",
    label: "Materi & Tugas (LMS)",
    icon: "iconoir-book-stack",
    description: "Baca materi, kerjakan kuis, dan kumpulkan tugas.",
    steps: [
      { title: "Belajar mandiri", body: "Pilih mata pelajaran, baca materi, kerjakan kuis, dan kumpulkan tugas. Nilai akan muncul di Portal Hasil Belajar setelah dipublikasikan guru.", icon: "iconoir-book-stack" },
    ],
    routes: { Student: "student.lms" },
  },
];

/** Kalender global (semua role & admin): jadwal kelas, trial, dan kegiatan (spec CALENDAR.md). */
export const CALENDAR_FEATURE: MenuFeature = {
  id: "calendar",
  group: "utama",
  label: "Kalender",
  icon: "iconoir-calendar",
  description: "Jadwal kelas, jadwal kelas trial, dan kegiatan dalam satu kalender, dengan pengingat sebelum acara dimulai.",
  steps: [
    { title: "Satu kalender", body: "Biru = jadwal kelas, oranye = kelas trial, hijau = kegiatan. Gunakan tombol bulan/minggu/hari untuk berpindah tampilan.", icon: "iconoir-calendar" },
    { title: "Ubah & buat", body: "Bila peran Anda boleh mengatur jadwal, tombol pintas Buat Kegiatan, Atur Sesi Kelas, atau Jadwalkan Trial tampil di atas kalender.", icon: "iconoir-plus" },
  ],
  routes: {},
};

/** Entri FAQ global (semua role & administrator). */
export const FAQ_FEATURE: MenuFeature = {
  id: "faq",
  group: "bantuan",
  label: "FAQ & Bantuan",
  icon: "iconoir-help-circle",
  description: "Cari jawaban atas pertanyaan yang sering muncul.",
  steps: [
    { title: "Cari jawaban", body: "Ketik kata kunci di kotak pencarian; jawaban dikelompokkan per kategori. Klik pertanyaan untuk membuka jawabannya.", icon: "iconoir-search" },
  ],
  routes: {},
};

export const getHub = (id?: string) => MENU_HUBS.find((h) => h.id === id) ?? null;

/** Bagian hub yang terlihat untuk konteks user, sesuai urutan katalog. */
export const getHubFeatures = (hubId: string, ctx: MenuContext) =>
  MENU_FEATURES.filter((f) => f.hub === hubId && isFeatureVisible(f, ctx));

/**
 * Super Administrator (user "Administrator", tanpa "Lihat sebagai") mengakses SEMUA menu operasional tanpa
 * pembatasan cabang (keputusan pemilik 6 Nov 2026). Untuk tiap fitur dipakai rute role dengan hak terluas
 * menurut urutan ini; menu pribadi (Honor Saya, portal wali/murid) tidak ikut karena tidak punya padanan admin.
 */
export const SUPER_ADMIN_ROUTE_PRIORITY: RoleProfile[] = ["Branch Manager", "CSO", "Finance", "Principal", "Marketing", "Staff Yayasan"];

export const getSuperAdminRoute = (feature: MenuFeature): string | null => {
  for (const role of SUPER_ADMIN_ROUTE_PRIORITY) {
    const name = feature.routes[role];
    if (name) return name;
  }
  return null;
};

export const getSuperAdminHubFeatures = (hubId: string) =>
  MENU_FEATURES.filter((f) => f.hub === hubId && getSuperAdminRoute(f));

/** Rute `<prefix role>.<slug>` untuk role aktif; Super Administrator (role null) memakai urutan SUPER_ADMIN_ROUTE_PRIORITY. */
export const roleRouteCandidates = (slug: string, role: RoleProfile | null): string[] =>
  (role ? [role] : SUPER_ADMIN_ROUTE_PRIORITY).map((r) => `${ROUTE_PREFIX[r]}.${slug}`);

/** Fitur panel Tindak Lanjut yang boleh dipakai (role aktif, atau Super Administrator tanpa "Lihat sebagai"). */
export const getPaneFeatures = (ctx: MenuContext, isSuperAdministrator: boolean) =>
  MENU_FEATURES.filter((f) =>
    f.pane && (ctx.role ? isFeatureVisible(f, ctx) : isSuperAdministrator && Boolean(getSuperAdminRoute(f))),
  );

export const isFeatureVisible = (feature: MenuFeature, ctx: MenuContext) =>
  Boolean(ctx.role && feature.routes[ctx.role]) && (!feature.when || feature.when(ctx));

export const getFeatureLabel = (feature: MenuFeature, role: RoleProfile | null) =>
  (role && feature.labelByRole?.[role]) || feature.label;

/** Cari fitur dari nama rute aktif (untuk wizard panduan halaman). */
export const findFeatureByRouteName = (routeName: string | null | undefined): MenuFeature | null => {
  if (!routeName) return null;
  if (routeName === "help.faq") return FAQ_FEATURE;
  if (routeName === "calendar") return CALENDAR_FEATURE;
  return MENU_FEATURES.find((f) => Object.values(f.routes).includes(routeName)) ?? null;
};
