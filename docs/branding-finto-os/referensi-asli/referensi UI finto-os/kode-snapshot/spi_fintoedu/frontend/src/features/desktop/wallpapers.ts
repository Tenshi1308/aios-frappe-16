/** Latar belakang bawaan mode desktop (nilai CSS background). Disimpan per pengguna (api/desktop_prefs.py). */
export type WallpaperPreset = { id: string; label: string; css: string };

export const WALLPAPER_PRESETS: WallpaperPreset[] = [
  {
    id: "finto",
    label: "Finto Biru",
    css: "radial-gradient(ellipse 60% 55% at 70% 60%, rgba(56,130,246,.85), transparent 70%), radial-gradient(ellipse 45% 45% at 30% 35%, rgba(14,165,233,.55), transparent 70%), radial-gradient(ellipse 50% 50% at 55% 85%, rgba(99,102,241,.55), transparent 70%), linear-gradient(160deg, #0b1e3f 0%, #10325f 45%, #0a1a35 100%)",
  },
  {
    id: "aurora",
    label: "Aurora",
    css: "radial-gradient(ellipse 70% 50% at 20% 20%, rgba(52,211,153,.55), transparent 70%), radial-gradient(ellipse 60% 50% at 80% 30%, rgba(168,85,247,.5), transparent 70%), radial-gradient(ellipse 60% 60% at 50% 100%, rgba(34,211,238,.45), transparent 70%), linear-gradient(180deg, #020617, #0f172a)",
  },
  {
    id: "sunset",
    label: "Senja",
    css: "radial-gradient(ellipse 80% 60% at 50% 100%, rgba(251,146,60,.85), transparent 70%), radial-gradient(ellipse 60% 50% at 80% 20%, rgba(236,72,153,.55), transparent 70%), linear-gradient(180deg, #312e81 0%, #7c2d12 100%)",
  },
  {
    id: "forest",
    label: "Hutan",
    css: "radial-gradient(ellipse 60% 50% at 30% 70%, rgba(34,197,94,.5), transparent 70%), radial-gradient(ellipse 50% 50% at 75% 30%, rgba(132,204,22,.35), transparent 70%), linear-gradient(160deg, #052e16 0%, #14532d 50%, #022c22 100%)",
  },
  {
    id: "midnight",
    label: "Tengah Malam",
    css: "radial-gradient(ellipse 50% 40% at 50% 30%, rgba(99,102,241,.35), transparent 70%), linear-gradient(180deg, #000000 0%, #0b1020 100%)",
  },
  {
    id: "ocean",
    label: "Samudra",
    css: "radial-gradient(ellipse 70% 60% at 60% 40%, rgba(6,182,212,.6), transparent 70%), radial-gradient(ellipse 60% 50% at 20% 80%, rgba(59,130,246,.55), transparent 70%), linear-gradient(170deg, #083344 0%, #0c4a6e 60%, #082f49 100%)",
  },
  {
    id: "graphite",
    label: "Grafit",
    css: "radial-gradient(ellipse 60% 50% at 50% 40%, rgba(148,163,184,.25), transparent 70%), linear-gradient(160deg, #111827 0%, #1f2937 50%, #0b0f17 100%)",
  },
  {
    id: "sakura",
    label: "Sakura",
    css: "radial-gradient(ellipse 60% 50% at 30% 30%, rgba(244,114,182,.55), transparent 70%), radial-gradient(ellipse 60% 50% at 75% 75%, rgba(251,207,232,.45), transparent 70%), linear-gradient(160deg, #500724 0%, #831843 55%, #3b0764 100%)",
  },
];

export const presetCss = (id: string) => (WALLPAPER_PRESETS.find((p) => p.id === id) ?? WALLPAPER_PRESETS[0]).css;
