/**
 * Activity Monitoring — tracker browser (core finto_edu, spec finto_edu/docs/specs/ACTIVITY_MONITORING.md §3).
 *
 * - Konfigurasi diambil dari server setelah login; `enabled = false` → TIDAK ada listener, timer, atau request lain.
 * - Listener delegated pada `document` (capture, passive) — tidak mencegat/menunda klik atau submit aplikasi.
 * - Event masuk antrean memori lalu dikirim per batch (interval/ambang), retry dengan backoff + jitter.
 * - Nilai field sensitif (password, OTP, PIN, token, file, [data-sensitive], [data-activity-ignore], dst.) tidak
 *   pernah masuk antrean. Tidak ada keypress logging, tidak ada snapshot DOM, tidak ada penyimpanan lokal.
 * - Replay memakai data posisi (viewport, kotak elemen, titik klik) — bukan rekaman layar.
 */
import type { RouteLocationNormalized } from "vue-router";
import HttpClient from "@/helpers/http-client";

const API = "/api/method/finto_edu.api.activity_monitor";

export type TrackerConfig = {
  enabled: boolean;
  application?: string;
  flush_interval_seconds: number;
  max_batch_events: number;
  max_event_bytes: number;
  heartbeat_interval_seconds: number;
  idle_after_seconds: number;
  excluded_field_names: string[];
  excluded_input_types: string[];
  excluded_selectors: string[];
  excluded_pages: string[];
  track_page_view: boolean;
  track_navigation: boolean;
  track_click: boolean;
  track_input: boolean;
  track_form_submit: boolean;
  track_session: boolean;
};

type EventType =
  | "page_view"
  | "navigation"
  | "button_click"
  | "input_change"
  | "field_blur"
  | "form_submit"
  | "session_start"
  | "heartbeat"
  | "session_end";

type TrackedEvent = {
  event_id: string;
  event_type: EventType;
  event_time: string;
  sequence: number;
  page: string;
  route_name?: string | null;
  menu_name?: string | null;
  element?: Record<string, string | undefined>;
  field?: Record<string, string | boolean | undefined>;
  value?: unknown;
  metadata?: Record<string, unknown>;
};

const MAX_QUEUE = 500;
const MAX_EVENT_AGE_MS = 24 * 60 * 60 * 1000;
const MAX_RETRIES = 8;
const INPUT_DEBOUNCE_MS = 1500;
const CONFIG_REFRESH_MS = 5 * 60 * 1000;
const MAX_VALUE = 1000;
const MAX_LABEL = 80;

// Sama dengan daftar wajib backend (services/activity_monitor.py) — backend tetap memeriksa ulang.
const SENSITIVE_SUBSTRINGS = ["password", "passwd", "katasandi", "sandi", "token", "secret", "apikey", "credential", "kredensial", "authorization", "recoverycode", "cardnumber", "nomorkartu", "cvv", "cvc"];
const SENSITIVE_WORDS = new Set(["otp", "pwd", "pin", "mpin", "pan", "auth", "sid", "csrf", "expiry", "kadaluarsa"]);
const ACTIONABLE =
  "button, a, [role=button], [role=tab], [role=menuitem], [role=option], [role=switch], input[type=submit], input[type=button], input[type=checkbox], input[type=radio], summary, label, .nav-link, .dropdown-item, [data-activity-name]";
const FIELD_SELECTOR = "input, textarea, select, [contenteditable=true]";

type State = {
  user: string;
  cfg: TrackerConfig;
  sessionId: string;
  seq: number;
  queue: TrackedEvent[];
  sending: boolean;
  failures: number;
  retryAt: number;
  dropped: number;
  lastPath: string | null;
  page: string | null;
  lastLayoutSig: string;
  lastRoute: { name: string | null; menu: string | null };
  lastInteraction: number;
  lastValues: Map<string, string>;
  inputTimers: Map<Element, number>;
  timers: number[];
  cleanup: (() => void)[];
  sensitiveSelector: string;
  validSelectors: string[];
};

let state: State | null = null;
let starting: Promise<void> | null = null;
const onStateChange = new Set<(active: boolean) => void>();

export const isTrackerActive = () => Boolean(state);
/** Untuk pemberitahuan transparansi (footer). */
export const onTrackerStateChange = (fn: (active: boolean) => void) => {
  onStateChange.add(fn);
  fn(Boolean(state));
  return () => onStateChange.delete(fn);
};
const emitState = () => onStateChange.forEach((fn) => fn(Boolean(state)));

const uuid = (): string =>
  typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : "10000000-1000-4000-8000-100000000000".replace(/[018]/g, (c) =>
        (Number(c) ^ (Math.random() * 16) >> (Number(c) / 4)).toString(16),
      );

const clip = (text: unknown, max = MAX_LABEL): string | undefined => {
  if (text === null || text === undefined) return undefined;
  const value = String(text).replace(/\s+/g, " ").trim();
  return value ? value.slice(0, max) : undefined;
};

/** Mode desktop: URL tetap /desktop, jadi halaman diambil dari rute terakhir yang dibuka. */
const currentPage = () => state?.page || window.location.pathname;

// ───────────────────────── Privasi ─────────────────────────

const isSensitiveName = (name: string | undefined | null, cfg: TrackerConfig): boolean => {
  if (!name) return false;
  const norm = name.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
  const compact = norm.replace(/_/g, "");
  if (cfg.excluded_field_names.includes(norm)) return true;
  if (SENSITIVE_SUBSTRINGS.some((s) => compact.includes(s))) return true;
  return norm.split("_").some((w) => SENSITIVE_WORDS.has(w));
};

const pageExcluded = (cfg: TrackerConfig) => cfg.excluded_pages.some((p) => currentPage().startsWith(p));

const isSensitiveElement = (el: Element, s: State, name?: string, label?: string): boolean => {
  if (s.sensitiveSelector && el.closest(s.sensitiveSelector)) return true;
  const type = (el.getAttribute("type") || "").toLowerCase();
  if (s.cfg.excluded_input_types.includes(type)) return true;
  const autocomplete = (el.getAttribute("autocomplete") || "").toLowerCase();
  if (/password|one-time-code|^cc-/.test(autocomplete)) return true;
  return (
    isSensitiveName(name, s.cfg) ||
    isSensitiveName(label, s.cfg) ||
    isSensitiveName(el.getAttribute("name"), s.cfg) ||
    isSensitiveName(el.getAttribute("id"), s.cfg)
  );
};

/** Hanya selector yang valid (selector konfigurasi yang salah ketik diabaikan, bukan merusak tracker). */
const buildSelectors = (selectors: string[]) =>
  selectors.filter((sel) => {
    try {
      document.createDocumentFragment().querySelector(sel);
      return true;
    } catch {
      return false;
    }
  });

// ───────────────────────── Identifikasi elemen ─────────────────────────

const stableId = (el: Element) => {
  const id = el.getAttribute("id");
  return id && !/^__BVID__|^\d|^[a-f0-9-]{20,}$/i.test(id) ? id : undefined;
};

const fieldLabel = (el: Element): string | undefined => {
  const explicit = el.getAttribute("data-activity-label") || el.getAttribute("aria-label");
  if (explicit) return clip(explicit);
  const labels = (el as HTMLInputElement).labels;
  if (labels && labels.length) return clip(labels[0].textContent);
  const group = el.closest(".mb-3, .mb-2, .form-group, .input-group, [class*='col-']");
  const label = group?.querySelector("label, .form-label");
  if (label) return clip(label.textContent);
  return clip(el.getAttribute("placeholder"));
};

const fieldName = (el: Element): string | undefined =>
  clip(el.getAttribute("data-activity-name")) ||
  clip(el.getAttribute("name")) ||
  stableId(el) ||
  fieldLabel(el) ||
  clip(el.tagName.toLowerCase());

const elementInfo = (el: Element) => ({
  tag: el.tagName,
  name: clip(el.getAttribute("data-activity-name")) || clip(el.getAttribute("name")) || stableId(el),
  label:
    clip(el.getAttribute("data-activity-label")) ||
    clip(el.getAttribute("aria-label")) ||
    clip(el.getAttribute("title")) ||
    clip((el as HTMLElement).innerText) ||
    clip((el as HTMLInputElement).value && (el as HTMLInputElement).type === "submit" ? (el as HTMLInputElement).value : undefined),
  id: stableId(el),
});

const geometry = (el: Element | null, point?: { x: number; y: number }) => {
  const meta: Record<string, unknown> = {
    vw: window.innerWidth,
    vh: window.innerHeight,
    sx: Math.round(window.scrollX),
    sy: Math.round(window.scrollY),
  };
  if (el) {
    const r = el.getBoundingClientRect();
    meta.rect = { x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height) };
    if (!point) point = { x: r.left + r.width / 2, y: r.top + r.height / 2 };
  }
  if (point) {
    meta.x = Math.round(point.x);
    meta.y = Math.round(point.y);
  }
  return meta;
};

// ───────────────────────── Konteks & kerangka layar (untuk replay) ─────────────────────────

type Region = { k: string; t?: string; r: [number, number, number, number]; a?: 1 };

/** Wilayah utama layar (hanya kotak + judul pendek, tanpa isi halaman). */
const REGIONS: [string, string, string?][] = [
  ["sidebar", ".startbar"],
  ["topbar", ".topbar"],
  ["icons", ".os-icons"],
  ["window", ".os-window", ".os-title"],
  ["start", ".os-start"],
  ["modal", ".modal.show .modal-dialog", ".modal-title"],
  ["panel", ".offcanvas.show", ".offcanvas-title"],
  ["taskbar", ".os-taskbar"],
];

const visibleRect = (el: Element) => {
  const r = el.getBoundingClientRect();
  if (r.width < 4 || r.height < 4 || r.bottom < 0 || r.right < 0 || r.top > window.innerHeight || r.left > window.innerWidth) return null;
  return [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)] as [number, number, number, number];
};

const captureLayout = (): Region[] => {
  const out: Region[] = [];
  for (const [k, selector, titleSel] of REGIONS) {
    document.querySelectorAll(selector).forEach((el) => {
      if (out.length >= 12) return;
      const r = visibleRect(el);
      if (!r) return;
      const region: Region = { k, r };
      const title = titleSel ? clip(el.querySelector(titleSel)?.textContent, 60) : undefined;
      if (title) region.t = title;
      if (k === "window" && el.classList.contains("active")) region.a = 1;
      out.push(region);
    });
  }
  // judul halaman (mode web) / judul halaman di jendela aktif (mode desktop)
  const scope = document.querySelector(".os-window.active .os-window-body") || document.querySelector(".page-content");
  const heading = scope?.querySelector("h3, h4");
  const hr = heading ? visibleRect(heading) : null;
  if (heading && hr && out.length < 12) out.push({ k: "heading", t: clip(heading.textContent, 60), r: hr });
  return out;
};

/** Lampirkan kerangka layar hanya bila berubah dari yang terakhir dikirim (payload tetap ringan). */
const withLayout = (meta: Record<string, unknown>) => {
  const s = state;
  if (!s) return meta;
  const layout = captureLayout();
  const sig = JSON.stringify(layout);
  if (sig !== s.lastLayoutSig) {
    s.lastLayoutSig = sig;
    meta.layout = layout;
  }
  return meta;
};

const textOf = (el: Element | null | undefined, selector: string) => clip(el?.querySelector(selector)?.textContent, 50);

/** Konteks singkat elemen: modal / jendela / area layout / kartu. */
const contextOf = (el: Element): string | undefined => {
  const parts: string[] = [];
  const modal = el.closest(".modal");
  const win = el.closest(".os-window");
  if (win) parts.push(`jendela "${textOf(win, ".os-title") || "?"}"`);
  if (modal) parts.push(`dialog "${textOf(modal, ".modal-title") || "?"}"`);
  if (!win && !modal) {
    if (el.closest(".startbar")) parts.push("menu samping");
    else if (el.closest(".topbar")) parts.push("bar atas");
    else if (el.closest(".os-taskbar")) parts.push("taskbar");
    else if (el.closest(".os-start")) parts.push("menu Start");
    else if (el.closest(".os-icons")) parts.push("desktop");
  }
  const card = el.closest(".card");
  const cardTitle = card ? textOf(card, ".card-title, .card-header, h5, h6") : undefined;
  if (cardTitle) parts.push(`bagian "${cardTitle}"`);
  return clip(parts.join(" › "), 140);
};

/** Jenis elemen dalam bahasa sehari-hari (untuk narasi replay). */
const kindOf = (el: Element): string => {
  const cls = el.classList;
  if (cls.contains("os-close")) return "tombol tutup jendela";
  if (cls.contains("os-min")) return "tombol minimalkan jendela";
  if (cls.contains("os-max")) return "tombol maksimalkan/pulihkan jendela";
  if (cls.contains("os-icon") || cls.contains("os-start-app") || cls.contains("os-recent")) return "ikon aplikasi";
  if (el.closest(".os-taskbar")) return "tombol taskbar";
  if (el.getAttribute("role") === "tab" || (cls.contains("nav-link") && el.closest(".nav-tabs, .nav-pills"))) return "tab";
  if (el.closest(".startbar") && el.tagName === "A") return "menu";
  if (cls.contains("dropdown-item") || el.getAttribute("role") === "menuitem") return "pilihan menu";
  if (el instanceof HTMLInputElement) {
    if (el.type === "checkbox") return "kotak centang";
    if (el.type === "radio") return "pilihan";
    if (["submit", "button"].includes(el.type)) return "tombol";
    return "isian";
  }
  if (el instanceof HTMLSelectElement) return "daftar pilihan";
  if (el instanceof HTMLTextAreaElement) return "isian teks";
  if (el.tagName === "A") return "tautan";
  if (el.tagName === "LABEL") return "label";
  return "tombol";
};

const readValue = (el: Element): { value: unknown; label?: string; fileSelected?: boolean } => {
  if (el instanceof HTMLInputElement) {
    if (el.type === "checkbox" || el.type === "radio") return { value: el.checked };
    if (el.type === "file") return { value: null, fileSelected: Boolean(el.files?.length) };
    return { value: el.value.slice(0, MAX_VALUE) };
  }
  if (el instanceof HTMLSelectElement) {
    const selected = Array.from(el.selectedOptions).map((o) => o.text);
    return {
      value: el.multiple ? Array.from(el.selectedOptions).map((o) => o.value).slice(0, 20) : el.value,
      label: clip(selected.join(", "), 200),
    };
  }
  if (el instanceof HTMLTextAreaElement) return { value: el.value.slice(0, MAX_VALUE) };
  return { value: ((el as HTMLElement).innerText || "").slice(0, MAX_VALUE) };
};

// ───────────────────────── Antrean & pengiriman ─────────────────────────

const push = (type: EventType, data: Partial<TrackedEvent> = {}, countSequence = true) => {
  const s = state;
  if (!s) return;
  if (countSequence) s.seq += 1;
  const event: TrackedEvent = {
    event_id: uuid(),
    event_type: type,
    event_time: new Date().toISOString(),
    sequence: s.seq,
    page: currentPage(),
    route_name: s.lastRoute.name,
    menu_name: s.lastRoute.menu,
    ...data,
  };
  if (s.queue.length >= MAX_QUEUE) {
    // Buffer penuh: buang event tertua (celah urutan → replay ditandai tidak lengkap).
    s.queue.shift();
    s.dropped += 1;
  }
  s.queue.push(event);
  if (s.queue.length >= s.cfg.max_batch_events) void flush();
};

const csrfHeaders = (): Record<string, string> => {
  const token = HttpClient.defaults.headers.common["X-Frappe-CSRF-Token"];
  return {
    "Content-Type": "application/json",
    Accept: "application/json",
    "X-Requested-With": "XMLHttpRequest",
    ...(token ? { "X-Frappe-CSRF-Token": String(token) } : {}),
  };
};

const flush = async (keepalive = false): Promise<void> => {
  const s = state;
  if (!s || s.sending || !s.queue.length) return;
  if (!keepalive && Date.now() < s.retryAt) return;
  const cutoff = Date.now() - MAX_EVENT_AGE_MS;
  s.queue = s.queue.filter((e) => Date.parse(e.event_time) >= cutoff);
  const batch = s.queue.splice(0, s.cfg.max_batch_events);
  if (!batch.length) return;
  s.sending = true;
  try {
    const response = await fetch(`${API}.collect`, {
      method: "POST",
      credentials: "include",
      keepalive,
      headers: csrfHeaders(),
      body: JSON.stringify({ client_session_id: s.sessionId, events: batch }),
    });
    let body: { message?: { accepted?: boolean; reason?: string } } = {};
    try {
      body = await response.json();
    } catch {
      body = {};
    }
    const result = body.message ?? (body as { accepted?: boolean; reason?: string });
    if (response.ok && result?.accepted) {
      s.failures = 0;
      s.retryAt = 0;
    } else if (result?.reason === "disabled" || result?.reason === "not_tracked" || response.status === 401 || response.status === 403) {
      stopActivityTracker(null);
      return;
    } else if (response.status === 400 || response.status === 413) {
      s.dropped += batch.length; // tidak akan pernah diterima; jangan diulang
    } else {
      retryLater(s, batch);
    }
  } catch {
    retryLater(s, batch);
  } finally {
    if (state === s) s.sending = false;
  }
  if (state === s && s.queue.length >= s.cfg.max_batch_events && !keepalive) void flush();
};

const retryLater = (s: State, batch: TrackedEvent[]) => {
  s.failures += 1;
  if (s.failures > MAX_RETRIES) {
    s.dropped += batch.length;
    s.failures = 0;
    return;
  }
  s.queue.unshift(...batch); // event_id tetap → retry idempotent
  if (s.queue.length > MAX_QUEUE) {
    s.dropped += s.queue.length - MAX_QUEUE;
    s.queue.splice(0, s.queue.length - MAX_QUEUE);
  }
  const backoff = Math.min(60_000, 2_000 * 2 ** (s.failures - 1));
  s.retryAt = Date.now() + backoff + Math.random() * 1_000;
};

// ───────────────────────── Listener ─────────────────────────

const markInteraction = () => {
  if (state) state.lastInteraction = Date.now();
};

const onClick = (ev: MouseEvent) => {
  const s = state;
  if (!s) return;
  markInteraction();
  if (!s.cfg.track_click) return;
  const target = ev.target instanceof Element ? ev.target.closest(ACTIONABLE) : null;
  if (!target || target.closest("[data-activity-ignore]")) return;
  const info = elementInfo(target);
  const sensitive = s.sensitiveSelector ? Boolean(target.closest(s.sensitiveSelector)) : false;
  push("button_click", {
    element: sensitive ? { tag: info.tag, name: info.name } : info,
    metadata: withLayout({ ...geometry(target, { x: ev.clientX, y: ev.clientY }), context: contextOf(target), kind: kindOf(target) }),
  });
};

const fieldKey = (name?: string) => `${currentPage()}::${name ?? ""}`;

const recordField = (el: Element, type: "input_change" | "field_blur") => {
  const s = state;
  if (!s || !s.cfg.track_input) return;
  if (el.closest("[data-activity-ignore]")) return;
  const name = fieldName(el);
  const label = fieldLabel(el);
  const inputType = (el.getAttribute("type") || el.tagName).toLowerCase();
  const sensitive = isSensitiveElement(el, s, name, label) || pageExcluded(s.cfg);
  const field = { name, label, type: inputType, sensitive: sensitive || undefined };
  const meta = withLayout({ ...geometry(el), context: contextOf(el), kind: kindOf(el) });
  if (sensitive) {
    // Hanya catat bahwa field diisi (tanpa nilai), sekali per field per halaman.
    const key = fieldKey(name);
    if (s.lastValues.get(key) === "__redacted__") return;
    s.lastValues.set(key, "__redacted__");
    push(type, { field, value: null, metadata: meta });
    return;
  }
  const { value, label: valueLabel, fileSelected } = readValue(el);
  const key = fieldKey(name);
  const serialized = JSON.stringify(value);
  if (s.lastValues.get(key) === serialized) return; // nilai identik → tidak digandakan
  s.lastValues.set(key, serialized);
  if (s.lastValues.size > 500) s.lastValues.clear();
  push(type, {
    field,
    value,
    metadata: { ...meta, ...(valueLabel ? { value_label: valueLabel } : {}), ...(fileSelected !== undefined ? { file_selected: fileSelected } : {}) },
  });
};

const onInput = (ev: Event) => {
  const s = state;
  if (!s) return;
  markInteraction();
  const el = ev.target instanceof Element ? ev.target.closest(FIELD_SELECTOR) : null;
  if (!el || !s.cfg.track_input) return;
  const existing = s.inputTimers.get(el);
  if (existing) window.clearTimeout(existing);
  s.inputTimers.set(
    el,
    window.setTimeout(() => {
      state?.inputTimers.delete(el);
      recordField(el, "input_change");
    }, INPUT_DEBOUNCE_MS),
  );
};

const onChange = (ev: Event) => {
  const el = ev.target instanceof Element ? ev.target : null;
  if (!el || !state) return;
  markInteraction();
  // select / checkbox / radio / file: langsung (bukan ketikan)
  if (el instanceof HTMLSelectElement || (el instanceof HTMLInputElement && ["checkbox", "radio", "file"].includes(el.type))) {
    recordField(el, "input_change");
  }
};

const onFocusOut = (ev: FocusEvent) => {
  const s = state;
  const el = ev.target instanceof Element ? ev.target.closest(FIELD_SELECTOR) : null;
  if (!s || !el) return;
  const pending = s.inputTimers.get(el);
  if (pending) {
    window.clearTimeout(pending);
    s.inputTimers.delete(el);
  }
  recordField(el, "field_blur");
};

const onSubmit = (ev: Event) => {
  const s = state;
  if (!s || !s.cfg.track_form_submit) return;
  const form = ev.target instanceof HTMLFormElement ? ev.target : null;
  if (!form || form.closest("[data-activity-ignore]")) return;
  const excludedPage = pageExcluded(s.cfg);
  const fields = Array.from(form.querySelectorAll(FIELD_SELECTOR))
    .filter((el) => !(el instanceof HTMLInputElement && ["submit", "button", "reset"].includes(el.type)))
    .slice(0, 50)
    .map((el) => {
      const name = fieldName(el);
      const label = fieldLabel(el);
      const type = (el.getAttribute("type") || el.tagName).toLowerCase();
      const sensitive = excludedPage || isSensitiveElement(el, s, name, label);
      return { name, label, type, sensitive: sensitive || undefined, value: sensitive ? null : readValue(el).value };
    });
  push("form_submit", {
    element: { tag: "FORM", name: clip(form.getAttribute("data-activity-name") || form.getAttribute("name")) || stableId(form) },
    metadata: { ...geometry(form), form_name: clip(form.getAttribute("data-activity-label") || form.getAttribute("name")), fields },
  });
};

const pointerActivity = () => markInteraction();

const onVisibility = () => {
  if (!state) return;
  if (state.cfg.track_session) {
    push("heartbeat", { metadata: { visibility: document.visibilityState, idle: isIdle() } }, false);
  }
  if (document.visibilityState === "hidden") void flush(true);
};

const onPageHide = () => {
  if (!state) return;
  if (state.cfg.track_session) push("session_end", { metadata: { reason: "tab_close" } });
  void flush(true); // best-effort; tidak dijamin terkirim
};

const isIdle = () => (state ? Date.now() - state.lastInteraction > state.cfg.idle_after_seconds * 1000 : false);

const listen = <K extends keyof DocumentEventMap>(type: K, fn: (ev: DocumentEventMap[K]) => void, s: State) => {
  document.addEventListener(type, fn as EventListener, { capture: true, passive: true });
  s.cleanup.push(() => document.removeEventListener(type, fn as EventListener, { capture: true }));
};

// ───────────────────────── API publik ─────────────────────────

const fetchConfig = async (): Promise<TrackerConfig | null> => {
  try {
    const response = await HttpClient.get<{ message: TrackerConfig }>(`${API}.get_client_config`);
    return response.data.message?.enabled ? response.data.message : null;
  } catch {
    return null; // fail open
  }
};

/** Dipanggil setelah login/inisialisasi sesi. Monitoring nonaktif → tidak memasang apa pun. */
export const startActivityTracker = async (user: string | null | undefined): Promise<void> => {
  if (!user) {
    stopActivityTracker(null);
    return;
  }
  if (state?.user === user) return;
  if (starting) return starting;
  starting = (async () => {
    if (state) stopActivityTracker("user_changed");
    const cfg = await fetchConfig();
    if (!cfg) return;
    const validSelectors = buildSelectors(cfg.excluded_selectors);
    const s: State = {
      user,
      cfg,
      sessionId: uuid(),
      seq: 0,
      queue: [],
      sending: false,
      failures: 0,
      retryAt: 0,
      dropped: 0,
      lastPath: null,
      page: null,
      lastLayoutSig: "",
      lastRoute: { name: null, menu: null },
      lastInteraction: Date.now(),
      lastValues: new Map(),
      inputTimers: new Map(),
      timers: [],
      cleanup: [],
      sensitiveSelector: validSelectors.join(", "),
      validSelectors,
    };
    state = s;
    if (cfg.track_session) {
      push("session_start", { metadata: { vw: window.innerWidth, vh: window.innerHeight, title: clip(document.title, 140) } });
    }
    listen("click", onClick, s);
    listen("input", onInput, s);
    listen("change", onChange, s);
    listen("focusout", onFocusOut, s);
    listen("submit", onSubmit, s);
    listen("keydown", pointerActivity, s); // hanya menandai interaksi (idle), isi tombol TIDAK dibaca
    listen("pointerdown", pointerActivity, s);
    listen("visibilitychange", onVisibility, s);
    window.addEventListener("pagehide", onPageHide);
    s.cleanup.push(() => window.removeEventListener("pagehide", onPageHide));
    const onOnline = () => void flush();
    window.addEventListener("online", onOnline);
    s.cleanup.push(() => window.removeEventListener("online", onOnline));

    s.timers.push(window.setInterval(() => void flush(), cfg.flush_interval_seconds * 1000));
    if (cfg.track_session) {
      s.timers.push(
        window.setInterval(() => {
          // Tab tersembunyi tidak dianggap aktif hanya karena timer berjalan.
          if (document.visibilityState === "visible") {
            push("heartbeat", { metadata: { visibility: "visible", idle: isIdle() } }, false);
          }
        }, cfg.heartbeat_interval_seconds * 1000),
      );
    }
    s.timers.push(
      window.setInterval(async () => {
        const fresh = await fetchConfig();
        if (state !== s) return;
        if (!fresh) stopActivityTracker(null);
        else {
          s.cfg = fresh;
          s.validSelectors = buildSelectors(fresh.excluded_selectors);
          s.sensitiveSelector = s.validSelectors.join(", ");
        }
      }, CONFIG_REFRESH_MS),
    );
    emitState();
  })().finally(() => {
    starting = null;
  });
  return starting;
};

/** Logout / ganti user: kirim sisa antrean (best-effort) lalu lepas semua listener & timer. */
export const stopActivityTracker = (reason: "logout" | "user_changed" | null = "logout"): Promise<void> => {
  const s = state;
  if (!s) return Promise.resolve();
  if (reason && s.cfg.track_session) push("session_end", { metadata: { reason } });
  s.inputTimers.forEach((t) => window.clearTimeout(t));
  s.timers.forEach((t) => window.clearInterval(t));
  s.cleanup.forEach((fn) => fn());
  s.sending = false;
  s.retryAt = 0;
  const done = reason ? flush(true) : Promise.resolve();
  state = null;
  emitState();
  return done;
};

/** Dipanggil router setiap perpindahan rute (web) / pembukaan jendela (desktop). Tidak mengganda saat re-render. */
export const trackRoute = (to: RouteLocationNormalized) => {
  const s = state;
  if (!s) return;
  const path = to.fullPath;
  if (path === s.lastPath) return;
  const from = s.lastPath;
  s.lastPath = path;
  const title = typeof to.meta.title === "string" ? to.meta.title.split(" | ")[0] : null;
  s.lastRoute = { name: to.name ? String(to.name) : null, menu: title };
  const page = to.path;
  s.page = page;
  if (from && s.cfg.track_navigation) {
    push("navigation", { page, metadata: { from_page: from.split("?")[0], to_page: page, vw: window.innerWidth, vh: window.innerHeight } });
  }
  if (s.cfg.track_page_view) {
    push("page_view", { page, metadata: { title: clip(title, 140), vw: window.innerWidth, vh: window.innerHeight } });
    const event = s.queue[s.queue.length - 1];
    // Kerangka layar diambil setelah halaman/jendela selesai dirender; hanya bila event belum terkirim.
    window.setTimeout(() => {
      if (state === s && event && s.queue.includes(event)) event.metadata = withLayout({ ...(event.metadata || {}) });
    }, 600);
  }
};

/** Mode desktop: rute dibuka di jendela (URL tetap /desktop) — router/index.ts mendaftarkan resolver nama rute. */
let routeResolver: ((name: string, query: Record<string, unknown>) => RouteLocationNormalized | null) | null = null;
export const setRouteResolver = (fn: typeof routeResolver) => {
  routeResolver = fn;
};
/** Dipanggil store desktop saat jendela dibuka/difokuskan: jendela aktif dicatat sebagai halaman. */
export const trackWindowRoute = (routeName: string, query: Record<string, unknown> = {}) => {
  if (!state || !routeResolver) return;
  try {
    const to = routeResolver(routeName, query);
    if (to) trackRoute(to);
  } catch {
    // rute tidak dikenal: abaikan
  }
};
