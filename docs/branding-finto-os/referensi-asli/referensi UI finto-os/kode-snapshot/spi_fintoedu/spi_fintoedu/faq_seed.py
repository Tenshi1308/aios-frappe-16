"""
Seed FAQ awal (Help Category + Help Article) untuk halaman /faq di SPA.

Idempoten: hanya MEMBUAT kategori/artikel yang belum ada (dicocokkan dari judul).
Artikel yang sudah ada TIDAK ditimpa, sehingga perubahan Super Administrator di
Desk (/app/help-article) aman — kecuali target role (``custom_spi_roles``) yang
diisi dari seed HANYA bila masih kosong.

FAQ per role (keputusan pemilik 6 Nov 2026): setiap artikel punya target Role Profile;
murid tidak melihat FAQ kasus guru, dst. Kosong = semua role. Untuk menyembunyikan artikel, hilangkan centang
``published`` (jangan hapus, karena akan dibuat ulang saat migrate).
"""

from __future__ import annotations

import frappe

AUTHOR = "SPI Digital System"
ROLES_FIELD = "custom_spi_roles"

# Kelompok Role Profile untuk target FAQ
BM, PRINCIPAL, FINANCE, CSO, MARKETING, TEACHER = "Branch Manager", "Principal", "Finance", "CSO", "Marketing", "Teacher"
PARENT, STUDENT = "Parent", "Student"
ALL: tuple[str, ...] = ()  # semua role
STAFF = (BM, PRINCIPAL, FINANCE, CSO, MARKETING, TEACHER)
FRONT = (CSO, MARKETING)  # CSO; Marketing disamakan sementara
ADMISSION = (*FRONT, BM, PRINCIPAL)
STUDENT_DATA = (*FRONT, BM, PRINCIPAL, FINANCE)
MONEY = (*FRONT, BM, PRINCIPAL, FINANCE)
ACADEMIC = (TEACHER, BM, PRINCIPAL)
PORTAL = (PARENT, STUDENT)

FAQ_CATEGORIES: list[tuple[str, str]] = [
	("Akun & Akses", "Login, menu, panduan, dan hak akses per peran."),
	("Admisi & Prospek", "Lead/PPDB, trial class, batal registrasi, buku tamu."),
	("Data Murid", "Status murid, aktivasi, cuti, wali murid, dokumen."),
	("Keuangan SPP", "Tagihan, pembayaran dua tahap, saldo, matriks SPP."),
	("Akademik & Sesi", "Sesi mengajar, presensi, LMS, perkembangan murid, final project."),
	("Honor & Gaji", "Honor guru freelance, dompet honor, slip gaji."),
	("Portal Murid & Wali", "Materi & tugas, nilai, tagihan, dan dokumen untuk murid dan orang tua."),
]

# Judul lama → judul baru (artikel seed yang sudah ada di database ikut diganti).
FAQ_RENAMED_TITLES: dict[str, str] = {
	"Kenapa menu saya berbeda dengan rekan kerja?": "Kenapa ada menu yang tidak tampil di akun saya?",
}
# Istilah yang tidak boleh lagi tampil di FAQ (sistem dikelola masing-masing cabang → cukup "admin").
FAQ_OUTDATED_TERMS = ("Super Administrator", "Super Admin", "rekan kerja")

FAQ_ARTICLES: list[tuple[str, str, str, tuple[str, ...]]] = [
	# (kategori, pertanyaan, jawaban HTML, target Role Profile — kosong = semua)
	# ───────── Akun & Akses
	(
		"Akun & Akses",
		"Kenapa ada menu yang tidak tampil di akun saya?",
		"<p>Menu disesuaikan dengan <b>peran</b> akun Anda (misalnya murid, orang tua, guru, atau staf sekolah). Menu yang tidak "
		"diperlukan untuk peran Anda tidak ditampilkan. Bila Anda merasa membutuhkan akses tambahan, hubungi admin.</p>",
		ALL,
	),
	(
		"Akun & Akses",
		"Bagaimana cara membuka lagi panduan (wizard) sebuah halaman?",
		"<p>Klik ikon <b>tanda tanya</b> di bar atas (atau di judul jendela pada tampilan desktop) untuk membuka panduan halaman yang sedang dibuka. "
		"Untuk menampilkan ulang <i>semua</i> panduan, buka menu profil lalu pilih <b>Tampilkan ulang semua panduan</b>.</p>",
		ALL,
	),
	(
		"Akun & Akses",
		"Apa arti angka merah di ikon lonceng?",
		"<p>Itu jumlah <b>notifikasi yang belum dibaca</b>. Klik lonceng untuk melihat daftarnya; klik salah satu notifikasi "
		"untuk langsung membuka halaman terkait. Notifikasi otomatis ditandai dibaca saat diklik.</p>",
		ALL,
	),
	(
		"Akun & Akses",
		"Saya tidak bisa membuka /app (Desk ERPNext). Kenapa?",
		"<p>Desk ERPNext (<code>/app</code>) hanya untuk <b>admin</b>. Semua pekerjaan operasional cabang "
		"dilakukan dari aplikasi SPI ini. Akun lain yang membuka <code>/app</code> otomatis diarahkan kembali ke aplikasi.</p>",
		STAFF,
	),
	(
		"Akun & Akses",
		"Apa itu panel Tindak Lanjut di sisi kanan layar?",
		"<p>Panel <b>Tindak Lanjut</b> berisi <b>Perlu Tindakan</b> (pekerjaan cabang berurutan Mendesak → Hari Ini → Minggu Ini → Pantau) "
		"dan <b>Follow-up Murid</b>. Buka lewat tombol di tepi kanan; angka merah = jumlah item Mendesak + Hari Ini. "
		"Di layar lebar panel menempel di samping sehingga halaman/form Anda tidak tertutup.</p>",
		(BM, PRINCIPAL, FINANCE, CSO, MARKETING),
	),
	(
		"Akun & Akses",
		"Data atau nama saya salah, siapa yang bisa mengubah?",
		"<p>Akun pengguna dikelola oleh <b>admin</b>. Data murid dan wali dikelola <b>CSO</b> cabang. "
		"Hubungi cabang Anda untuk perubahan data.</p>",
		ALL,
	),
	# ───────── Admisi & Prospek
	(
		"Admisi & Prospek",
		"Dari mana datangnya pendaftar baru?",
		"<p>Pendaftar masuk dari formulir publik <b>PPDB Online</b> (<code>/registers</code>) atau diinput CSO di menu "
		"<b>PPDB &amp; Admisi</b>. Pendaftar baru muncul di daftar admisi untuk ditindaklanjuti CSO.</p>",
		ADMISSION,
	),
	(
		"Admisi & Prospek",
		"Bagaimana menjadwalkan trial class?",
		"<p>Buka <b>Jadwal Trial Class</b>, pilih pendaftar, tentukan tanggal/jam dan guru. Guru yang ditugaskan akan melihat "
		"trial tersebut di menu miliknya dan mengisi catatan hasil trial. CSO tidak perlu menunggu catatan guru untuk melanjutkan pendaftaran.</p>",
		ADMISSION,
	),
	(
		"Admisi & Prospek",
		"Pendaftar batal, apakah datanya dihapus?",
		"<p>Tidak. Gunakan <b>Batal Registrasi</b> dengan alasan pembatalan; data diarsipkan dan dapat <b>dipulihkan</b> kembali "
		"ke antrean aktif dengan satu klik bila calon siswa berubah pikiran.</p>",
		ADMISSION,
	),
	(
		"Admisi & Prospek",
		"Kapan lead harus di-follow-up dan apa yang terjadi bila terlewat?",
		"<p>Catat setiap kontak dengan calon siswa sebagai <b>Follow-up Lead</b> (pilih level & tulis hasilnya). Sistem mengingatkan "
		"secara berkala; lead yang <b>tidak di-follow-up lebih dari 14 hari</b> muncul sebagai <b>MENDESAK</b> di panel Tindak Lanjut. "
		"Mencatat follow-up lead adalah tugas CSO; Branch Manager dapat memantau.</p>",
		(*FRONT, BM),
	),
	(
		"Admisi & Prospek",
		"Saya ditugaskan mengajar trial class. Apa yang harus saya isi?",
		"<p>Buka <b>Jadwal Trial Class</b>; hanya trial yang ditugaskan kepada Anda yang tampil. Setelah trial selesai, isi "
		"<b>catatan hasil trial</b> (kemampuan, rekomendasi kelas). Catatan ini membantu CSO menyampaikan hasil ke orang tua.</p>",
		(TEACHER,),
	),
	# ───────── Data Murid
	(
		"Data Murid",
		"Apa beda status Pending, Aktif, Cuti, dan Off?",
		"<p><b>Pending</b>: terdaftar tetapi belum memenuhi syarat aktivasi (misalnya pembayaran pertama belum terverifikasi). "
		"<b>Aktif</b>: mengikuti kelas dan ditagih SPP. <b>Cuti</b>: berhenti sementara; bulan SPP prabayar yang jatuh di masa cuti digeser otomatis. "
		"<b>Off</b>: berhenti; saldo/prabayar diproses sesuai aturan hangus. Setiap perubahan status memakai tanggal efektif.</p>",
		STUDENT_DATA,
	),
	(
		"Data Murid",
		"Siapa yang boleh mengubah status murid?",
		"<p>CSO dan Branch Manager dapat mengubah status. Principal dan Finance hanya dapat melihat. Perubahan tercatat di riwayat status murid.</p>",
		STUDENT_DATA,
	),
	(
		"Data Murid",
		"Siapa yang memasukkan atau mengeluarkan murid dari rombel?",
		"<p>Perubahan rombel (buat rombel, tambah/keluarkan murid, atur guru pengajar) <b>hanya dilakukan CSO</b>. "
		"Branch Manager dan Principal dapat melihat semua rombel cabang; guru hanya melihat rombel yang ia ajar.</p>",
		(*FRONT, BM, PRINCIPAL),
	),
	(
		"Data Murid",
		"Di mana dokumen murid (akta, KK, rapor lama) disimpan?",
		"<p>Dokumen murid ada di data murid bagian <b>Dokumen</b>. CSO dan Branch Manager dapat mengunggah dan menghapus; "
		"Principal dan Finance hanya melihat. Murid dan orang tua juga dapat mengunggah sendiri dari portal. "
		"Dokumen <b>bukan</b> syarat aktivasi murid.</p>",
		STUDENT_DATA,
	),
	# ───────── Keuangan SPP
	(
		"Keuangan SPP",
		"Kenapa pembayaran yang saya input belum dianggap lunas?",
		"<p>Pembayaran SPP memakai <b>dua tahap</b>: (1) pengajuan oleh CSO/Finance/Branch Manager, (2) <b>verifikasi oleh Finance</b> "
		"yang bukan pengaju. Setelah diverifikasi barulah Payment Entry dibuat dan tagihan berkurang. Pengaju akan mendapat notifikasi hasil verifikasi.</p>",
		MONEY,
	),
	(
		"Keuangan SPP",
		"Murid membayar beberapa bulan sekaligus, bagaimana pencatatannya?",
		"<p>Cukup satu pengajuan dengan total nominalnya. Pembayaran dialokasikan <b>FIFO</b> ke tagihan tertua lebih dulu; "
		"kelebihan bayar menjadi <b>saldo murid</b> yang otomatis dipakai untuk tagihan berikutnya. Matriks SPP 12 Bulan "
		"(tab di Controlling Keuangan) akan menandai bulan-bulan tersebut lunas.</p>",
		MONEY,
	),
	(
		"Keuangan SPP",
		"Kapan tagihan SPP bulanan dibuat?",
		"<p>Tagihan dibuat otomatis setiap bulan untuk murid Aktif berdasarkan <b>Harga SPP</b> (harga program atau harga khusus murid), "
		"dengan nomor <code>{kode cabang}/SPP/{tahun}/0001</code>.</p>",
		MONEY,
	),
	(
		"Keuangan SPP",
		"Kenapa tagihan berstatus Draf dan seluruh pembayaran masuk ke saldo murid?",
		"<p>Tagihan <b>Draf</b> belum diterbitkan sehingga belum bisa dibayar; pembayaran hanya dialokasikan ke tagihan yang sudah terbit, "
		"sisanya menjadi saldo murid. Finance atau Branch Manager menekan <b>Terbitkan</b> di Daftar Tagihan SPP, lalu ajukan pembayaran. "
		"Di form pembayaran, \"Sisa setelah bayar\" menunjukkan sisa tagihan dan \"Masuk saldo murid\" hanya kelebihan bayarnya.</p>",
		MONEY,
	),
	(
		"Keuangan SPP",
		"Bolehkah saya memverifikasi pengajuan pembayaran yang saya buat sendiri?",
		"<p>Tidak. Verifikasi harus dilakukan <b>Finance lain</b> (bukan pengaju) agar ada pemeriksaan dua pihak. "
		"Pengajuan yang salah dapat dibatalkan oleh pengaju atau Finance sebelum diverifikasi.</p>",
		(FINANCE,),
	),
	(
		"Keuangan SPP",
		"Di mana melihat status bayar 12 bulan per murid?",
		"<p>Buka <b>Laporan → Controlling Keuangan</b>, lalu tab <b>Matriks SPP 12 Bulan</b>. Hijau = lunas, biru = sebagian, "
		"kuning = belum bayar, merah = lewat jatuh tempo. Klik sel bulan untuk rincian atau menerbitkan tagihan.</p>",
		(BM, PRINCIPAL, FINANCE),
	),
	# ───────── Akademik & Sesi
	(
		"Akademik & Sesi",
		"Bagaimana guru mencatat sesi mengajar?",
		"<p>Sesi dibuat otomatis dari jadwal mingguan rombel. Guru membuka <b>Sesi Mengajar</b>, mengisi realisasi (hadir/tidak, "
		"materi) dan presensi siswa. Sesi yang memenuhi syarat akan dihitung sebagai honor (untuk guru freelance).</p>",
		ACADEMIC,
	),
	(
		"Akademik & Sesi",
		"Siapa yang menyetujui final project?",
		"<p>Guru mengisi dan <b>mengajukan</b> nilai final project. Branch Manager atau Principal <b>menyetujui/menolak</b>. "
		"Bila disetujui dan lulus, nomor sertifikat dibuat otomatis.</p>",
		ACADEMIC,
	),
	(
		"Akademik & Sesi",
		"Kenapa saya tidak bisa menambah atau mengubah rombel/kelas?",
		"<p>Rombel hanya dapat dibuat atau diubah oleh <b>CSO</b> (termasuk menambah/mengeluarkan murid). Guru dapat melihat rombel "
		"yang ia ajar. Bila ada murid yang belum masuk rombel Anda, hubungi CSO cabang.</p>",
		(TEACHER,),
	),
	(
		"Akademik & Sesi",
		"Bagaimana membuka atau mengunci materi LMS untuk murid?",
		"<p>Buka <b>LMS &amp; Pembelajaran</b>, pilih mata pelajaran, lalu klik <b>Akses Materi per Rombel</b>. Pilih rombel dan tekan "
		"<b>Terkunci/Terbuka</b> pada tiap bab (atau Buka semua / Kunci semua). Murid hanya dapat membuka bab yang sudah dibuka; "
		"bab yang sudah dibuka tetap bisa dibaca seterusnya kecuali Anda menguncinya lagi. Guru hanya dapat mengatur rombel yang ia ajar.</p>",
		ACADEMIC,
	),
	(
		"Akademik & Sesi",
		"Bagaimana nilai kuis/tugas LMS masuk ke rapor?",
		"<p>Di LMS, gunakan <b>Ke Rapor</b> pada kuis/tugas atau tombol <b>Sinkronkan ke Rapor</b>. Nilai terbaik setiap murid disalin "
		"ke rencana penilaian rombel. Murid harus sudah terdaftar di rombel (didaftarkan CSO).</p>",
		ACADEMIC,
	),
	(
		"Akademik & Sesi",
		"Bisakah saya menambah catatan perkembangan murid atau final project?",
		"<p>Tidak. CSO dapat <b>melihat</b> Perkembangan Murid untuk bahan komunikasi dengan orang tua. Catatan dan final project "
		"diisi guru, lalu disetujui Branch Manager atau Principal.</p>",
		FRONT,
	),
	# ───────── Honor & Gaji
	(
		"Honor & Gaji",
		"Bagaimana honor guru freelance dihitung?",
		"<p>Honor dihitung per <b>sesi berhonor</b> yang sudah dikonfirmasi, memakai tarif freelance cabang (tipe kelas × bahasa × level) "
		"atau tarif khusus rombel. Rinciannya terlihat di <b>Rekap Honor Guru</b>. Finance mencatat pembayaran honor per bulan.</p>",
		(TEACHER, BM, PRINCIPAL, FINANCE),
	),
	(
		"Honor & Gaji",
		"Di mana saya melihat slip gaji?",
		"<p>Buka menu <b>Slip Gaji Saya</b>. Slip hanya menampilkan dokumen milik akun Anda (ditautkan lewat data Employee). "
		"Jika kosong, hubungi Finance cabang. Guru freelance tidak memiliki slip gaji; riwayatnya ada di <b>Honor Saya</b>.</p>",
		STAFF,
	),
	(
		"Honor & Gaji",
		"Kenapa honor sesi saya belum muncul?",
		"<p>Honor hanya dihitung dari sesi yang <b>realisasinya sudah diisi dan dikonfirmasi</b>. Periksa Sesi Mengajar Anda. "
		"Guru <b>tetap</b> tidak mendapat honor per sesi karena digaji bulanan (lihat Slip Gaji Saya).</p>",
		(TEACHER,),
	),
	(
		"Honor & Gaji",
		"Bagaimana memproses gaji karyawan tetap?",
		"<p>Buka <b>Penggajian</b>: buat penggajian bulan berjalan, periksa slip, lalu ajukan. Slip dikirim ke email karyawan "
		"(gagal kirim email tidak menghalangi proses). Setelah gaji ditransfer, catat pembayarannya dari kas/bank agar pembukuan tutup.</p>",
		(FINANCE, BM),
	),
	# ───────── Portal Murid & Wali
	(
		"Portal Murid & Wali",
		"Kenapa ada materi LMS yang terkunci?",
		"<p>Materi dibuka bertahap oleh guru sesuai jadwal belajar rombel Anda. Bab yang masih bertanda <b>Terkunci</b> belum dibuka guru. "
		"Bab yang sudah dibuka tetap dapat dibaca kapan saja, termasuk setelah pertemuannya lewat.</p>",
		(STUDENT,),
	),
	(
		"Portal Murid & Wali",
		"Bagaimana mengerjakan kuis dan mengumpulkan tugas?",
		"<p>Buka <b>Materi &amp; Tugas (LMS)</b>, pilih mata pelajaran, lalu tekan <b>Kerjakan Kuis</b> atau buka tugas dan "
		"<b>Kumpulkan</b> (boleh dengan lampiran). Jawaban otomatis tercatat atas nama akun Anda.</p>",
		(STUDENT,),
	),
	(
		"Portal Murid & Wali",
		"Kapan nilai muncul di portal?",
		"<p>Nilai tampil setelah <b>dipublikasikan</b> oleh guru. Kehadiran dan tagihan SPP tampil otomatis.</p>",
		PORTAL,
	),
	(
		"Portal Murid & Wali",
		"Anak saya tidak muncul di Monitoring Anak. Kenapa?",
		"<p>Anak dicocokkan dari <b>email login Anda = email wali</b> di data wali murid. Bila berbeda, hubungi CSO cabang untuk "
		"memperbarui email wali.</p>",
		(PARENT,),
	),
	(
		"Portal Murid & Wali",
		"Bagaimana mengunggah dokumen (akta, KK, dan lainnya)?",
		"<p>Di portal, buka bagian <b>Dokumen</b>, pilih jenis dokumen lalu <b>Unggah</b>. Anda dapat menghapus dokumen yang Anda unggah sendiri; "
		"dokumen yang diunggah sekolah hanya dapat dihapus CSO/Branch Manager.</p>",
		PORTAL,
	),
	(
		"Portal Murid & Wali",
		"Bagaimana cara membayar SPP?",
		"<p>Lihat tagihan di portal, lalu bayar ke sekolah (transfer ke rekening sekolah atau tunai) dan kirim bukti ke CSO/Finance cabang. "
		"Status lunas berubah setelah pembayaran <b>diverifikasi Finance</b>.</p>",
		PORTAL,
	),
]


def setup_faq() -> None:
	if not frappe.db.exists("DocType", "Help Article"):
		return
	for name, description in FAQ_CATEGORIES:
		if not frappe.db.exists("Help Category", {"category_name": name}):
			frappe.get_doc(
				{
					"doctype": "Help Category",
					"category_name": name,
					"category_description": description,
					"published": 1,
				}
			).insert(ignore_permissions=True)

	has_roles = frappe.get_meta("Help Article").has_field(ROLES_FIELD)
	for old, new in FAQ_RENAMED_TITLES.items():
		name = frappe.db.get_value("Help Article", {"title": old})
		if name and not frappe.db.exists("Help Article", {"title": new}):
			frappe.db.set_value("Help Article", name, "title", new, update_modified=False)
	category_names = {
		c.category_name: c.name for c in frappe.get_all("Help Category", fields=["name", "category_name"])
	}
	for category, question, answer, roles in FAQ_ARTICLES:
		roles_text = "\n".join(roles)
		existing = frappe.db.get_value("Help Article", {"title": question}, ["name", ROLES_FIELD] if has_roles else ["name"], as_dict=True)
		if existing:
			# artikel seed yang masih memakai istilah lama → perbarui jawabannya ke versi seed terbaru
			content = frappe.db.get_value("Help Article", existing.name, "content") or ""
			if any(term in content for term in FAQ_OUTDATED_TERMS):
				frappe.db.set_value("Help Article", existing.name, "content", answer, update_modified=False)
			# hanya isi target role bila masih kosong (perubahan admin di Desk tidak ditimpa)
			if has_roles and roles_text and not (existing.get(ROLES_FIELD) or "").strip():
				frappe.db.set_value("Help Article", existing.name, ROLES_FIELD, roles_text, update_modified=False)
			continue
		doc = {
			"doctype": "Help Article",
			"title": question,
			"category": category_names.get(category, category),
			"content": answer,
			"published": 1,
			"author": AUTHOR,
			"level": "Beginner",
		}
		if has_roles:
			doc[ROLES_FIELD] = roles_text
		frappe.get_doc(doc).insert(ignore_permissions=True)
