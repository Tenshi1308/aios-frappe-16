import HttpClient from "@/helpers/http-client";

const API = "/api/method/spi_fintoedu.api.desktop_prefs";

export type Wallpaper = { kind: "preset" | "image"; value: string };
export type IconLayouts = Record<string, Record<string, [number, number]>>;
export type DesktopPrefs = { wallpaper: Wallpaper; presets: string[]; icon_layouts?: IconLayouts };

export async function getDesktopPrefs() {
  return (await HttpClient.get<{ message: DesktopPrefs }>(`${API}.get_desktop_prefs`)).data.message;
}

export async function setWallpaperPreset(preset: string) {
  return (await HttpClient.post<{ message: DesktopPrefs }>(`${API}.set_wallpaper_preset`, { preset })).data.message;
}

export async function uploadWallpaper(file: File) {
  const form = new FormData();
  form.append("file", file, file.name);
  return (await HttpClient.post<{ message: DesktopPrefs }>(`${API}.upload_wallpaper`, form)).data.message;
}

export async function resetWallpaper() {
  return (await HttpClient.post<{ message: DesktopPrefs }>(`${API}.reset_wallpaper`)).data.message;
}

/** Posisi ikon desktop per peran (seret & lepas), disimpan per pengguna di server. */
export async function setIconLayout(role: string, layout: Record<string, [number, number]>) {
  return (await HttpClient.post<{ message: { icon_layouts: IconLayouts } }>(`${API}.set_icon_layout`, { role, layout: JSON.stringify(layout) }))
    .data.message;
}

export async function resetIconLayout(role: string) {
  return (await HttpClient.post<{ message: { icon_layouts: IconLayouts } }>(`${API}.reset_icon_layout`, { role })).data.message;
}
