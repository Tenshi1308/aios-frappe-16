/**
 * Katalog Preset Otomasi Alur Kerja ERP (Phase 5E / Step 6K).
 * Menggunakan metadata profesional, kategori, dan ikon Lucide SVG tanpa emoji aislop.
 */

export interface AutomationPreset {
  id: string;
  title: string;
  category: "analytics" | "audit" | "operational" | "forecast";
  iconName: string;
  description: string;
  targetRole?: string;
  prompt: string;
}

export const BRANCH_AUTOMATIONS: Record<string, AutomationPreset[]> = {
  finance: [
    {
      id: "fin-pnl",
      title: "Laporan Laba/Rugi (P&L)",
      category: "analytics",
      iconName: "BarChart3",
      description: "Hitung revenue, HPP, margin kotor, dan laba bersih periode berjalan.",
      targetRole: "financial_analyst",
      prompt: "Tolong buatkan ringkasan Laporan Laba/Rugi (Profit & Loss) untuk periode bulan ini termasuk margin kotor dan laba bersih."
    },
    {
      id: "fin-ar-aging",
      title: "Analisis Umur Piutang (AR Aging)",
      category: "audit",
      iconName: "Clock",
      description: "Identifikasi piutang tertunggak 0-30, 31-60, 61-90, dan >90 hari.",
      targetRole: "financial_analyst",
      prompt: "Tolong tampilkan ringkasan analisis umur piutang (AR Aging) dan identifikasi pelanggan dengan risiko kredit tinggi."
    },
    {
      id: "fin-cashflow",
      title: "Proyeksi Arus Kas 30 Hari",
      category: "forecast",
      iconName: "TrendingUp",
      description: "Hitung proyeksi kas masuk dan keluar untuk 30 hari ke depan.",
      targetRole: "treasurer",
      prompt: "Tolong hitung proyeksi arus kas (cashflow forecast) untuk 30 hari ke depan berdasarkan jadwal jatuh tempo AR dan AP."
    },
    {
      id: "fin-ratios",
      title: "Kalkulasi Rasio Keuangan",
      category: "analytics",
      iconName: "Calculator",
      description: "Analisis Current Ratio, Gross Margin, Net Margin, dan ROA.",
      targetRole: "financial_analyst",
      prompt: "Tolong hitung rasio keuangan kunci perusahaan (Current Ratio, Net Margin, ROA) dan evaluasi status likuiditasnya."
    }
  ],
  sales: [
    {
      id: "sal-pareto",
      title: "Analisis Pareto Pelanggan VIP",
      category: "analytics",
      iconName: "Award",
      description: "Identifikasi 20% pelanggan teratas yang menyumbang 80% omzet.",
      targetRole: "sales_data_analyst",
      prompt: "Tolong jalankan analisis Pareto untuk mengidentifikasi 20% pelanggan VIP teratas yang menyumbang mayoritas pendapatan."
    },
    {
      id: "sal-forecast",
      title: "Proyeksi Tren Penjualan Q4",
      category: "forecast",
      iconName: "LineChart",
      description: "Estimasi pendapatan penjualan untuk 3 bulan ke depan.",
      targetRole: "sales_data_analyst",
      prompt: "Tolong buatkan proyeksi estimasi penjualan (sales forecast) untuk 3 bulan ke depan dengan asumsi tren pertumbuhan terkini."
    },
    {
      id: "sal-churn",
      title: "Deteksi Risiko Churn Pelanggan",
      category: "audit",
      iconName: "AlertTriangle",
      description: "Identifikasi pelanggan yang inaktif dan berpotensi churn.",
      targetRole: "marketing_specialist",
      prompt: "Tolong cek pelanggan yang sudah tidak aktif memesan lebih dari 60 hari dan berikan rekomendasi tindakan retensinya."
    },
    {
      id: "sal-pipeline",
      title: "Status Pipeline Penjualan",
      category: "operational",
      iconName: "Kanban",
      description: "Pantau sebaran deal di tahap Prospect, Proposal, dan Won.",
      targetRole: "sales_representative",
      prompt: "Tolong tampilkan ringkasan status sales pipeline saat ini beserta total potensi nilai deals yang sedang berjalan."
    }
  ],
  material: [
    {
      id: "mat-stock",
      title: "Cek Stok Kritis & Titik ROP",
      category: "operational",
      iconName: "Package",
      description: "Identifikasi barang yang stoknya di bawah batas pemesanan ulang.",
      targetRole: "inventory_clerk",
      prompt: "Tolong cek ketersediaan stok barang di Gudang Utama dan hitung apakah ada item yang sudah menyentuh Reorder Point (ROP)."
    },
    {
      id: "mat-abc",
      title: "Analisis ABC Inventory",
      category: "analytics",
      iconName: "Layers",
      description: "Klasifikasi persediaan kategori A (nilai tinggi), B, dan C.",
      targetRole: "sourcing_specialist",
      prompt: "Tolong lakukan analisis ABC pada seluruh persediaan barang untuk memetakan kategori nilai konsumsi tahunan."
    },
    {
      id: "mat-slow",
      title: "Laporan Slow-Moving / Dead Stock",
      category: "audit",
      iconName: "Hourglass",
      description: "Identifikasi barang usang yang tidak bergerak >90 hari.",
      targetRole: "warehouse_supervisor",
      prompt: "Tolong buatkan laporan stock aging untuk mengidentifikasi barang slow-moving yang tertahan di gudang lebih dari 90 hari."
    },
    {
      id: "mat-eoq",
      title: "Kalkulasi Kuantitas Pesanan (EOQ)",
      category: "operational",
      iconName: "Calculator",
      description: "Hitung kuantitas pesanan paling ekonomis untuk efisiensi biaya.",
      targetRole: "purchasing_officer",
      prompt: "Tolong hitung Economic Order Quantity (EOQ) optimal untuk pengadaan barang dengan memperhitungkan biaya pesan dan simpan."
    }
  ],
  hr: [
    {
      id: "hr-payroll",
      title: "Kalkulasi Penggajian Bulanan",
      category: "operational",
      iconName: "DollarSign",
      description: "Hitung gaji massal bulanan, PPh 21, BPJS, dan draf batch payroll.",
      targetRole: "payroll_officer",
      prompt: "Tolong hitung kalkulasi penggajian bulanan untuk seluruh karyawan dan buatkan draf batch payroll untuk diotorisasi."
    },
    {
      id: "hr-attendance",
      title: "Rekapitulasi Absensi & Lembur",
      category: "audit",
      iconName: "Clock",
      description: "Laporan kehadiran bulanan, tingkat absensi, dan jam lembur.",
      targetRole: "hr_staff",
      prompt: "Tolong buatkan rekapitulasi kehadiran dan jam lembur karyawan untuk periode bulan ini."
    },
    {
      id: "hr-probation",
      title: "Pantau Karyawan Masa Probation",
      category: "operational",
      iconName: "UserCheck",
      description: "Deteksi karyawan yang masa evaluasi probation-nya akan berakhir.",
      targetRole: "hr_staff",
      prompt: "Tolong periksa daftar karyawan yang masa percobaannya (probation) akan berakhir dalam 30 hari ke depan."
    },
    {
      id: "hr-turnover",
      title: "Analisis Rasio Turnover Karyawan",
      category: "analytics",
      iconName: "Users",
      description: "Hitung retensi dan perbandingan turnover terhadap standar industri.",
      targetRole: "hr_manager",
      prompt: "Tolong lakukan analisis tingkat perputaran karyawan (turnover rate) tahunan dan bandingkan dengan standar industri."
    }
  ],
  manufacturing: [
    {
      id: "mfg-oee",
      title: "Evaluasi Metrik OEE Mesin",
      category: "analytics",
      iconName: "Gauge",
      description: "Hitung Availability, Performance, dan Quality OEE lini pabrik.",
      targetRole: "production_supervisor",
      prompt: "Tolong hitung metrik Overall Equipment Effectiveness (OEE) mesin produksi dan evaluasi apakah masuk rating World Class."
    },
    {
      id: "mfg-mrp",
      title: "Pengecekan Kebutuhan Material (MRP)",
      category: "operational",
      iconName: "ClipboardList",
      description: "Verifikasi ketersediaan material sebelum merilis jadwal produksi.",
      targetRole: "production_planner",
      prompt: "Tolong lakukan pengecekan kebutuhan material (MRP) untuk rencana produksi berikutnya dan pastikan semua komponen siap."
    },
    {
      id: "mfg-cost",
      title: "Kalkulasi HPP Produksi (COGM)",
      category: "analytics",
      iconName: "Coins",
      description: "Hitung biaya bahan baku, tenaga kerja langsung, dan overhead mesin.",
      targetRole: "production_planner",
      prompt: "Tolong hitung estimasi HPP Produksi per unit (COGM) termasuk alokasi upah teknisi dan biaya overhead mesin."
    },
    {
      id: "mfg-takt",
      title: "Sinkronisasi Takt Time & Lini",
      category: "operational",
      iconName: "Timer",
      description: "Hitung Takt Time per unit sesuai kuota permintaan pasar.",
      targetRole: "production_planner",
      prompt: "Tolong hitung Takt Time yang dibutuhkan lini produksi agar dapat memenuhi target kuota permintaan pelanggan tepat waktu."
    }
  ],
  quality: [
    {
      id: "qa-aql",
      title: "Sampling Uji Mutu AQL",
      category: "operational",
      iconName: "Microscope",
      description: "Hitung ukuran sampel dan batas toleransi standar ISO 2859-1.",
      targetRole: "quality_inspector",
      prompt: "Tolong hitung rekomendasi ukuran sampel pengujian mutu berdasarkan standar AQL 1.5% untuk inspeksi barang masuk."
    },
    {
      id: "qa-spc",
      title: "Analisis Kapabilitas Proses (SPC / Cpk)",
      category: "analytics",
      iconName: "Activity",
      description: "Evaluasi stabilitas dimensi mesin dan indeks Cpk presisi.",
      targetRole: "quality_engineer",
      prompt: "Tolong lakukan analisis Statistical Process Control (SPC) dan hitung indeks kapabilitas Cpk dari data sampel pengukuran."
    },
    {
      id: "qa-fpy",
      title: "Analisis First Pass Yield (FPY)",
      category: "analytics",
      iconName: "CheckCircle2",
      description: "Hitung persentase barang yang lolos QC tanpa rework.",
      targetRole: "quality_engineer",
      prompt: "Tolong hitung rasio First Pass Yield (FPY) untuk mengetahui persentase produk yang langsung lolos tanpa pengerjaan ulang."
    },
    {
      id: "qa-pareto",
      title: "Analisis Tren Jenis Cacat (Defect Pareto)",
      category: "audit",
      iconName: "PieChart",
      description: "Identifikasi kontributor cacat terbesar untuk tindakan CAPA.",
      targetRole: "quality_manager",
      prompt: "Tolong tampilkan analisis tren cacat terbesar (Defect Pareto) untuk menentukan fokus perbaikan mutu utama."
    }
  ],
  logistics: [
    {
      id: "log-otif",
      title: "Laporan Performa Pengiriman (OTIF)",
      category: "analytics",
      iconName: "Truck",
      description: "Evaluasi rasio pengiriman On-Time In-Full dan kendala rute.",
      targetRole: "logistics_manager",
      prompt: "Tolong buatkan laporan performa pengiriman On-Time In-Full (OTIF) dan ringkasan kendala keterlambatan armada."
    },
    {
      id: "log-load",
      title: "Optimasi Muatan Truk Kargo",
      category: "operational",
      iconName: "Boxes",
      description: "Hitung persentase utilisasi tonase dan kubikasi (CBM) armada.",
      targetRole: "logistics_coordinator",
      prompt: "Tolong lakukan optimasi muatan kargo truk untuk memastikan kubikasi CBM dan batas berat aman sebelum diberangkatkan."
    },
    {
      id: "log-fuel",
      title: "Analisis Efisiensi BBM & Emisi CO2",
      category: "audit",
      iconName: "Fuel",
      description: "Pantau rasio Km/Liter armada dan kalkulasi jejak karbon operasional.",
      targetRole: "fleet_manager",
      prompt: "Tolong evaluasi efisiensi konsumsi BBM armada truk logistik dan hitung estimasi jejak emisi karbon (CO2e) perjalanannya."
    },
    {
      id: "log-3pl",
      title: "Bandingkan Tarif Kurir 3PL",
      category: "operational",
      iconName: "Tags",
      description: "Bandingkan estimasi tarif dan lead-time ekspedisi pihak ketiga.",
      targetRole: "logistics_coordinator",
      prompt: "Tolong bandingkan opsi tarif dan estimasi waktu pengiriman kurir ekspedisi logistik 3PL terbaik."
    }
  ],
  maintenance: [
    {
      id: "mnt-mtbf",
      title: "Analisis Reliabilitas (MTBF & MTTR)",
      category: "analytics",
      iconName: "Wrench",
      description: "Hitung rata-rata waktu bebas rusak dan durasi perbaikan mesin.",
      targetRole: "reliability_engineer",
      prompt: "Tolong hitung metrik keandalan mesin MTBF dan MTTR serta evaluasi tingkat ketersediaan operasi (inherent availability)."
    },
    {
      id: "mnt-pred",
      title: "Deteksi Dini Kerusakan (Predictive Maintenance)",
      category: "audit",
      iconName: "Cpu",
      description: "Evaluasi anomali sensor getaran dan temperatur motor mesin.",
      targetRole: "reliability_engineer",
      prompt: "Tolong periksa pembacaan sensor suhu dan getaran mesin terkini untuk memprediksi apakah ada indikasi kerusakan dini."
    },
    {
      id: "mnt-backlog",
      title: "Cek Antrean Servis (Maintenance Backlog)",
      category: "operational",
      iconName: "ListTodo",
      description: "Identifikasi perintah kerja perawatan yang overdue atau tertunda.",
      targetRole: "maintenance_planner",
      prompt: "Tolong tampilkan daftar antrean pekerjaan servis mesin (maintenance backlog) yang sedang tertunda atau overdue."
    },
    {
      id: "mnt-cost",
      title: "Estimasi Biaya Perawatan Mesin",
      category: "analytics",
      iconName: "Coins",
      description: "Hitung total estimasi biaya suku cadang dan jam kerja teknisi.",
      targetRole: "maintenance_planner",
      prompt: "Tolong hitung estimasi total biaya servis perbaikan mesin termasuk alokasi suku cadang dan jam kerja teknisi."
    }
  ],
  planning: [
    {
      id: "pln-kpi",
      title: "Executive KPI Dashboard",
      category: "analytics",
      iconName: "BarChart3",
      description: "Ringkasan performa 360 derajat (Finance, Sales, Ops, HR).",
      targetRole: "bi_analyst",
      prompt: "Tolong tampilkan ringkasan Executive KPI Dashboard menyeluruh dari seluruh fungsi operasional dan finansial perusahaan."
    },
    {
      id: "pln-whatif",
      title: "Simulasi Skenario Bisnis What-If",
      category: "forecast",
      iconName: "Sliders",
      description: "Simulasi dampak kenaikan harga jual, inflasi biaya, dan volume.",
      targetRole: "planning_manager",
      prompt: "Tolong jalankan simulasi skenario What-If untuk menganalisis dampak kenaikan harga jual terhadap proyeksi laba bersih."
    },
    {
      id: "pln-scorecard",
      title: "Evaluasi Balanced Scorecard",
      category: "analytics",
      iconName: "Target",
      description: "Kalkulasi 4 Perspektif: Finansial, Pelanggan, Proses, SDM.",
      targetRole: "planning_manager",
      prompt: "Tolong hitung skor komposit Balanced Scorecard korporat mencakup perspektif keuangan, pelanggan, proses, dan pembelajaran."
    },
    {
      id: "pln-budget",
      title: "Evaluasi Budget vs Actual",
      category: "audit",
      iconName: "Scale",
      description: "Bandingkan realisasi pengeluaran terhadap target pagu RKAP.",
      targetRole: "report_developer",
      prompt: "Tolong bandingkan realisasi pengeluaran aktual terhadap anggaran target RKAP dan tandai jika ada pos yang melebihi pagu."
    }
  ]
};

export function getAutomationsForBranch(branchKey: string): AutomationPreset[] {
  const normKey = branchKey.toLowerCase().replace(/[^a-z0-9]/g, "");
  if (normKey.includes("finance") || normKey.includes("akuntansi")) return BRANCH_AUTOMATIONS.finance || [];
  if (normKey.includes("sales") || normKey.includes("penjualan") || normKey.includes("distribusi")) return BRANCH_AUTOMATIONS.sales || [];
  if (normKey.includes("material") || normKey.includes("inventory") || normKey.includes("purchasing") || normKey.includes("pengadaan")) return BRANCH_AUTOMATIONS.material || [];
  if (normKey.includes("hr") || normKey.includes("human") || normKey.includes("sdm")) return BRANCH_AUTOMATIONS.hr || [];
  if (normKey.includes("manufactur") || normKey.includes("produksi")) return BRANCH_AUTOMATIONS.manufacturing || [];
  if (normKey.includes("quality") || normKey.includes("mutu") || normKey.includes("qc")) return BRANCH_AUTOMATIONS.quality || [];
  if (normKey.includes("logistic") || normKey.includes("logistik") || normKey.includes("fleet")) return BRANCH_AUTOMATIONS.logistics || [];
  if (normKey.includes("maintenance") || normKey.includes("pemeliharaan") || normKey.includes("perawatan")) return BRANCH_AUTOMATIONS.maintenance || [];
  if (normKey.includes("plan") || normKey.includes("strategic") || normKey.includes("bi") || normKey.includes("perencanaan")) return BRANCH_AUTOMATIONS.planning || [];
  
  return BRANCH_AUTOMATIONS.planning || [];
}
