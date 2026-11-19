# Laporan implementasi — Perbaikan tombol toggle sidebar ke baris judul agent (v2, dikerjakan Muse sendiri)

- Tanggal: 19 Nov 2026, 23:20–23:29 WIB
- Dikerjakan oleh: Muse sendiri (bukan Gemini), atas perintah Ten "Coba km sendiri deh yg lakuin, bukan nyuruh gemini, task sesimple ini loh"
- Commit lokal: (lihat hash di laporan Ten)
- Status: commit lokal, TIDAK di-push

## Yang dikerjakan

1. Tombol toggle sidebar dipindah ke ujung kanan baris judul paling atas
   (`.ap-title` di `.ap-head`): avatar agent di kiri, judul agent di tengah,
   ikon toggle di kanan, dalam satu baris. Tombol selalu tampil (hapus
   `v-if="!sidebarVisible"`), label dan aria-label berganti mengikuti state
   (`Sembunyikan sidebar` / `Tampilkan sidebar`), tetap memanggil
   `toggleSidebarOrHistory`. Hanya ada SATU tombol toggle
   (`ap-head-sidebar-btn` = 1 di AgentPanel.vue).
2. Baris kosong `.ap-sidebar-top` (hanya berisi ikon, tidak ada isi) dihapus
   dari AgentPanel.vue beserta CSS-nya. Grep `ap-sidebar-top` di
   `frontend/src/` = 0.
3. Mode fullscreen / wide (`.agent-panel.wide`, berlaku saat fullscreen atau
   lebar panel >= 640px): `.ap-title` dibuat selebar kolom sidebar
   (`flex: none; width: calc(260px - var(--space-16))`) supaya ujung kanan
   baris judul sejajar dengan ujung kanan kolom sidebar (260px).
4. Perbaikan susulan: tombol titik tiga, fullscreen, dan close pindah ke kiri
   di mode fullscreen (ditemukan Ten 23:27 WIB). Penyebab: `.ap-title` yang
   tadinya `flex: 1` tidak lagi meregang, sehingga tidak mendorong menu ke
   kanan. Perbaikan: `.agent-panel.wide .ap-head-menu-wrap`
   (`margin-left: auto`) supaya menu tetap di ujung kanan header.
5. Tombol tidak digabung ke baris Terbaru; tombol plus, enum Terbaru/Terlama,
   pill Arsip, dan menu titik tiga tidak berubah.

## File yang diubah

- `frontend/src/components/agent/AgentPanel.vue` (26 baris berubah)
- `frontend/src/styles/base.css` (15 baris berubah)

## Verifikasi (oleh Muse sendiri)

- `npm run build`: LOLOS (2.88 detik)
- `pytest test_frontend_no_hardcode.py`: 25 passed
- `bench draft_manager`: OK
- `bench authz`: OK
- Ten mengonfirmasi 23:27 WIB: tombol sidebarnya sudah benar.

## Yang masih menunggu

- Verifikasi visual live di layar Ten (khususnya mode fullscreen: tombol
  titik tiga, fullscreen, dan close sudah kembali ke ujung kanan).
- Tidak di-push; push hanya atas perintah Ten.
