import { reactive, ref } from 'vue';

export interface DeskWindow {
  id: string;
  title: string;
  x: number;
  y: number;
  w: number;
  h: number;
  z: number;
  min: boolean;
  max: boolean;
}

const MIN_W = 440;
const MIN_H = 320;

function factory(bounds: () => { w: number; h: number }) {
  const windows = reactive<DeskWindow[]>([]);
  const activeId = ref<string | null>(null);
  let z = 10;
  let seq = 0;

  function open(id: string, title: string) {
    const existing = windows.find((w) => w.id === id);
    if (existing) {
      existing.min = false;
      focus(existing);
      return existing;
    }
    const b = bounds();
    const n = windows.length % 6;
    const w = Math.min(720, b.w - 140);
    const h = Math.min(480, b.h - 50);
    const win: DeskWindow = {
      id,
      title,
      x: Math.max(110, (b.w - w) / 2 - 60) + n * 30,
      y: 20 + n * 28,
      w,
      h,
      z: ++z,
      min: false,
      max: false,
    };
    windows.push(win);
    focus(win);
    return win;
  }

  function focus(win: DeskWindow) {
    win.z = ++z;
    activeId.value = win.id;
  }

  function minimize(win: DeskWindow) {
    win.min = true;
    const top = windows.filter((w) => !w.min).sort((a, b) => b.z - a.z)[0];
    activeId.value = top ? top.id : null;
  }

  function close(win: DeskWindow) {
    windows.splice(windows.indexOf(win), 1);
    const top = windows.filter((w) => !w.min).sort((a, b) => b.z - a.z)[0];
    activeId.value = top ? top.id : null;
  }

  function toggleMax(win: DeskWindow) {
    win.max = !win.max;
  }

  function winStyle(win: DeskWindow, narrow: boolean) {
    if (win.max || narrow) return { left: '0', top: '0', width: '100%', height: '100%', zIndex: win.z };
    return { left: `${win.x}px`, top: `${win.y}px`, width: `${win.w}px`, height: `${win.h}px`, zIndex: win.z };
  }

  function startDrag(e: PointerEvent, win: DeskWindow, narrow: boolean) {
    // Guard prototype: pointerdown di atas tombol kontrol bukan permulaan drag —
    // tanpa ini setPointerCapture menelan click tombol minimize/max/close.
    if (e.button !== 0 || win.max || narrow || (e.target as HTMLElement).closest('button')) return;
    focus(win);
    const sx = e.clientX;
    const sy = e.clientY;
    const ox = win.x;
    const oy = win.y;
    const el = e.currentTarget as HTMLElement;
    el.setPointerCapture(e.pointerId);
    const onMove = (ev: PointerEvent) => {
      const b = bounds();
      win.x = Math.max(120 - win.w, Math.min(ox + ev.clientX - sx, b.w - 120));
      win.y = Math.max(0, Math.min(oy + ev.clientY - sy, b.h - 40));
    };
    const onUp = () => {
      el.removeEventListener('pointermove', onMove);
      el.removeEventListener('pointerup', onUp);
      el.removeEventListener('pointercancel', onUp);
    };
    el.addEventListener('pointermove', onMove);
    el.addEventListener('pointerup', onUp);
    el.addEventListener('pointercancel', onUp);
  }

  function startResize(e: PointerEvent, win: DeskWindow, narrow: boolean) {
    if (win.max || narrow) return;
    focus(win);
    const sx = e.clientX;
    const sy = e.clientY;
    const ow = win.w;
    const oh = win.h;
    const el = e.currentTarget as HTMLElement;
    el.setPointerCapture(e.pointerId);
    const onMove = (ev: PointerEvent) => {
      win.w = Math.max(MIN_W, ow + ev.clientX - sx);
      win.h = Math.max(MIN_H, oh + ev.clientY - sy);
    };
    const onUp = () => {
      el.removeEventListener('pointermove', onMove);
      el.removeEventListener('pointerup', onUp);
      el.removeEventListener('pointercancel', onUp);
    };
    el.addEventListener('pointermove', onMove);
    el.addEventListener('pointerup', onUp);
    el.addEventListener('pointercancel', onUp);
  }

  function taskClick(id: string) {
    const win = windows.find((w) => w.id === id);
    if (!win) return;
    if (win.min) {
      win.min = false;
      focus(win);
    } else if (win.id === activeId.value) {
      minimize(win);
    } else {
      focus(win);
    }
  }

  return { windows, activeId, open, focus, minimize, close, toggleMax, winStyle, startDrag, startResize, taskClick };
}

type WindowManager = ReturnType<typeof factory>;

let instance: WindowManager | null = null;
let boundsFn: () => { w: number; h: number } = () => ({ w: window.innerWidth, h: window.innerHeight - 52 });

export function setWindowBounds(fn: () => { w: number; h: number }) {
  boundsFn = fn;
}

/** Singleton desktop: WindowHost, Taskbar, dan ikon desktop berbagi state jendela. */
export function useWindowManager(): WindowManager {
  if (!instance) instance = factory(boundsFn);
  return instance;
}
