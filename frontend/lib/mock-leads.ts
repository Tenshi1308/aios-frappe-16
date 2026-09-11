// ============================================================
// AIOS Lead AI Generator — Mock Data & Smart Timestamp Utility
// Sumber data prospek dari postingan publik internet (IG, FB, Forum)
// ============================================================

export type PlatformType = "instagram" | "facebook" | "forum";

export interface LeadItem {
  id: string;
  name: string;
  platform: PlatformType;
  platformLabel: string;
  contact: string;
  contactType: "Instagram Handle" | "Facebook Profil" | "User Forum";
  sourceUrl: string;
  content: string;
  detectedAt: string; // ISO 8601 string
}

// Utility Smart Timestamp Formatting:
// 1. Hari ini ➔ Jam (HH:mm)
// 2. < 1 minggu ➔ Nama hari (Senin, Selasa, dll.)
// 3. > 1 minggu ➔ Tanggal lengkap (dd/mm/yyyy)
export function formatSmartTimestamp(isoString: string): string {
  const date = new Date(isoString);
  const now = new Date();

  // Cek apakah tanggalnya adalah hari ini (kalender yang sama)
  const isToday =
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate();

  if (isToday) {
    const hours = date.getHours().toString().padStart(2, "0");
    const minutes = date.getMinutes().toString().padStart(2, "0");
    return `${hours}:${minutes}`;
  }

  // Hitung selisih waktu dalam hari
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  // Jika rentang kurang dari 7 hari (dan bukan hari ini)
  if (diffDays >= 1 && diffDays < 7) {
    const dayNames = ["Minggu", "Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu"];
    return dayNames[date.getDay()];
  }

  // Jika rentang 7 hari atau lebih ➔ dd/mm/yyyy
  const d = date.getDate().toString().padStart(2, "0");
  const m = (date.getMonth() + 1).toString().padStart(2, "0");
  const y = date.getFullYear();
  return `${d}/${m}/${y}`;
}

// Helper untuk format tanggal lengkap pada detail view
export function formatFullTimestamp(isoString: string): string {
  const date = new Date(isoString);
  const dayNames = ["Minggu", "Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu"];
  const monthNames = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember"
  ];
  
  const dayName = dayNames[date.getDay()];
  const day = date.getDate();
  const month = monthNames[date.getMonth()];
  const year = date.getFullYear();
  const hours = date.getHours().toString().padStart(2, "0");
  const minutes = date.getMinutes().toString().padStart(2, "0");

  return `${dayName}, ${day} ${month} ${year} • ${hours}:${minutes} WIB`;
}

// Helper untuk generate waktu dinamis relatif terhadap sekarang
// agar pengujian smart timestamp selalu valid kapan pun dijalankan
function getRelativeDate(hoursAgo: number, daysAgo: number = 0, minutesAgo: number = 0): string {
  const d = new Date();
  d.setDate(d.getDate() - daysAgo);
  d.setHours(d.getHours() - hoursAgo);
  d.setMinutes(d.getMinutes() - minutesAgo);
  return d.toISOString();
}

// Dataset Mock Prospek — Contoh Kasus Bisnis: Perusahaan Produsen/Distributor Keramik & Granit
// AI mendeteksi calon pembeli (kontraktor, arsitek, pemilik rumah) yang butuh produk keramik client di internet
export const MOCK_LEADS: LeadItem[] = [
  {
    id: "lead-01",
    name: "Bima Arya (Arsitek & Desain)",
    platform: "instagram",
    platformLabel: "Instagram",
    contact: "@bima_arya_interior",
    contactType: "Instagram Handle",
    sourceUrl: "https://www.instagram.com/p/DAxK82_b9L",
    content:
      "Lagi renovasi rumah tinggal 2 lantai di Surabaya Barat. Butuh granit tile polished 60x60 motif white carrara marmer sekitar 160 dus + step nose tangga anti-slip. Ada distributor atau pabrikan keramik yang ready stock dan bisa kirim minggu ini? Please DM katalog & price list ya!",
    detectedAt: getRelativeDate(2, 0), // Hari ini, 2 jam lalu
  },
  {
    id: "lead-02",
    name: "Pak Joko Susilo (Kontraktor Ruko)",
    platform: "facebook",
    platformLabel: "Facebook Group",
    contact: "facebook.com/groups/komunitas.kontraktor.jatim/posts/8912384756",
    contactType: "Facebook Profil",
    sourceUrl: "https://www.facebook.com/groups/komunitas.kontraktor.jatim/posts/8912384756",
    content:
      "Dicari supplier keramik langsung pabrik/distributor untuk proyek 4 unit ruko di Sidoarjo. Kebutuhan keramik lantai 50x50 putih polos 400 dus dan keramik dinding kamar mandi 25x40 motif glossy 120 dus. Diutamakan yang bisa terbitkan faktur pajak resmi.",
    detectedAt: getRelativeDate(5, 0), // Hari ini, 5 jam lalu
  },
  {
    id: "lead-03",
    name: "David Kristanto (Desain Cafe)",
    platform: "forum",
    platformLabel: "Forum Desain Arsitektur",
    contact: "forum.desainarsitektur.id/u/david_kris",
    contactType: "User Forum",
    sourceUrl: "https://forum.desainarsitektur.id/t/supplier-keramik-motif-kayu-rustic-cafe/48291",
    content:
      "Halo rekan desainer, ada rekomendasi produsen keramik lokal yang punya motif kayu (wood plank) ukuran 15x80 atau 20x100 dengan tekstur matte? Mau dipakai buat lantai cafe outdoor & indoor seluas 250m². Butuh harga grosir dan sample material.",
    detectedAt: getRelativeDate(0, 2), // 2 hari lalu
  },
  {
    id: "lead-04",
    name: "Citra Mandiri Property",
    platform: "instagram",
    platformLabel: "Instagram",
    contact: "@citra_mandiri_estate",
    contactType: "Instagram Handle",
    sourceUrl: "https://www.instagram.com/p/DAqZ19_k3M",
    content:
      "Persiapan pembangunan perumahan cluster tahap 2 (total 18 unit rumah). Sedang tender pengadaan keramik lantai utama homogeneous tile 60x60 dan keramik carport anti-slip 40x40. Distributor atau pabrikan keramik yang berminat silakan kirim penawaran harga terbaik.",
    detectedAt: getRelativeDate(0, 4), // 4 hari lalu
  },
  {
    id: "lead-05",
    name: "Ibu Maya Safitri (Owner Butik)",
    platform: "facebook",
    platformLabel: "Facebook Group",
    contact: "facebook.com/groups/renovasi.komersial.surabaya/posts/7823910245",
    contactType: "Facebook Profil",
    sourceUrl: "https://www.facebook.com/groups/renovasi.komersial.surabaya/posts/7823910245",
    content:
      "Rencana fitting out butik pakaian di Tunjungan Plaza. Butuh ubin keramik dekoratif motif terrazzo ukuran 60x60 warna beige pastel untuk area showroom 90m². Toko atau distributor keramik yang punya motif terrazzo estetik tolong info lokasinya ya.",
    detectedAt: getRelativeDate(0, 10), // 10 hari lalu
  },
  {
    id: "lead-06",
    name: "Rian Pratama (Kontraktor Villa)",
    platform: "instagram",
    platformLabel: "Instagram",
    contact: "@rian_villa_builder",
    contactType: "Instagram Handle",
    sourceUrl: "https://www.instagram.com/p/DAxZ90_k8P",
    content:
      "Butuh supply batu alam & granit unpolished outdoor anti-slip ukuran 30x60 untuk area bibir kolam renang (pool deck) villa di Kota Batu sekitar 80m². Mohon info supplier atau pabrik keramik yang ready stock kirim minggu ini.",
    detectedAt: getRelativeDate(0, 0, 35), // Hari ini, 35 menit lalu
  },
  {
    id: "lead-07",
    name: "Hj. Nurhayati (Toko Bangunan Berkah)",
    platform: "facebook",
    platformLabel: "Facebook Group",
    contact: "facebook.com/groups/pedagang.bahan.bangunan.jatim/posts/9018273645",
    contactType: "Facebook Profil",
    sourceUrl: "https://www.facebook.com/groups/pedagang.bahan.bangunan.jatim/posts/9018273645",
    content:
      "Buka PO stok toko awal bulan: dicari pabrik keramik yang bisa kirim 1 kontainer keramik lantai 40x40 motif marmer abu & krem (Grade A / KW1). Mau ambil continue tiap bulan jika harga partai dan tempo pembayaran cocok.",
    detectedAt: getRelativeDate(3, 0), // Hari ini, 3 jam lalu
  },
  {
    id: "lead-08",
    name: "Studio Karsa Interior",
    platform: "forum",
    platformLabel: "Forum Desain Arsitektur",
    contact: "forum.desainarsitektur.id/u/studiokarsa",
    contactType: "User Forum",
    sourceUrl: "https://forum.desainarsitektur.id/t/rekomendasi-keramik-subway-tile-dapur/51029",
    content:
      "Lagi garap kitchen set bergaya scandinavian untuk 5 unit apartemen. Perlu keramik dinding subway tile putih bevel ukuran 10x20 dan keramik lantai motif heksagonal (hexagon) hitam-putih. Rekomendasi distributor lokal yang potongannya presisi?",
    detectedAt: getRelativeDate(0, 1), // 1 hari lalu
  },
  {
    id: "lead-09",
    name: "PT Griya Selaras Asri",
    platform: "instagram",
    platformLabel: "Instagram",
    contact: "@griyaselaras_official",
    contactType: "Instagram Handle",
    sourceUrl: "https://www.instagram.com/p/DApM81_w2V",
    content:
      "Tender terbuka pengadaan finishing lantai proyek Rumah Sakit Swasta di Malang. Dibutuhkan homogeneous tile heavy-duty 60x60 anti-bakteri total 1.200m². Vendor resmi pabrikan keramik yang memiliki sertifikasi uji lab harap DM penawaran.",
    detectedAt: getRelativeDate(0, 5), // 5 hari lalu
  },
  {
    id: "lead-10",
    name: "Drs. Wahyu Hidayat (Panitia Masjid)",
    platform: "facebook",
    platformLabel: "Facebook Group",
    contact: "facebook.com/groups/renovasi.sarana.ibadah/posts/6541298732",
    contactType: "Facebook Profil",
    sourceUrl: "https://www.facebook.com/groups/renovasi.sarana.ibadah/posts/6541298732",
    content:
      "Pembangunan serambi masjid jami' seluas 300m² di Pasuruan. Memerlukan granit bakar / unpolished 60x60 warna hijau marmer atau abu tua yang sejuk dan tidak licin saat terkena air wudhu. Donatur / supplier pabrik keramik mohon info penawarannya.",
    detectedAt: getRelativeDate(0, 14), // 14 hari lalu
  },
];

export type SortOrder = "asc" | "desc";

// Sesuai definisi user:
// asc = dari yang terbaru (newest first)
// desc = dari yang terlama (oldest first)
export function sortLeads(leads: LeadItem[], order: SortOrder = "asc"): LeadItem[] {
  return [...leads].sort((a, b) => {
    const timeA = new Date(a.detectedAt).getTime();
    const timeB = new Date(b.detectedAt).getTime();
    return order === "asc" ? timeB - timeA : timeA - timeB;
  });
}

// Default helper tetap mengurutkan terbaru di paling atas
export function getSortedLeads(): LeadItem[] {
  return sortLeads(MOCK_LEADS, "asc");
}
