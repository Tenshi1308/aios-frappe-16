<template>
  <section
    v-show="!win.minimized"
    class="os-window"
    :class="{ maximized: win.maximized, active: active }"
    :style="frameStyle"
    role="dialog"
    :aria-label="win.title"
    @pointerdown="desktop.focus(win.id)"
  >
    <header class="os-titlebar" @pointerdown="startDrag" @dblclick="desktop.toggleMaximize(win.id)">
      <i :class="win.icon" class="os-title-icon"></i>
      <span class="os-title text-truncate">{{ win.title }}</span>
      <div class="os-title-actions" @pointerdown.stop @dblclick.stop>
        <button type="button" class="os-btn" title="Panduan halaman ini" aria-label="Panduan" @click="$emit('tour', win)">
          <i class="iconoir-help-circle"></i>
        </button>
        <button type="button" class="os-btn os-min" title="Minimalkan" aria-label="Minimalkan" @click="desktop.minimize(win.id)">
          <i class="iconoir-minus"></i>
        </button>
        <button
          type="button"
          class="os-btn os-max"
          :title="win.maximized ? 'Pulihkan' : 'Maksimalkan'"
          :aria-label="win.maximized ? 'Pulihkan' : 'Maksimalkan'"
          @click="desktop.toggleMaximize(win.id)"
        >
          <i :class="win.maximized ? 'iconoir-collapse' : 'iconoir-square'"></i>
        </button>
        <button type="button" class="os-btn os-close" title="Tutup" aria-label="Tutup" @click="desktop.close(win.id)">
          <i class="iconoir-xmark"></i>
        </button>
      </div>
    </header>

    <div class="os-window-body" :data-window="win.id">
      <Suspense>
        <component :is="pageComponent" v-if="pageComponent" :key="win.routeName" v-bind="pageProps" />
        <template #fallback>
          <div class="text-center py-5"><b-spinner variant="primary" /></div>
        </template>
      </Suspense>
      <div v-if="!pageComponent" class="text-center text-muted py-5">Halaman tidak ditemukan.</div>
    </div>

    <div v-if="!win.maximized" class="os-resize" @pointerdown.stop="startResize" aria-hidden="true"></div>
  </section>
</template>

<script setup lang="ts">
/**
 * Satu jendela di mode desktop. Isi = komponen halaman dari rute (sama persis dengan mode web).
 * DESKTOP_WINDOW di-provide sehingga DefaultLayout hanya merender isi halaman (tanpa TopBar/sidebar).
 */
import { computed, defineAsyncComponent, provide, toRef, type Component } from "vue";
import { useRouter, type RouteRecordRaw } from "vue-router";
import { DESKTOP_WINDOW } from "../context";
import { useDesktopStore, type DesktopWindow } from "@/stores/desktop";

const props = defineProps<{ win: DesktopWindow; active: boolean }>();
defineEmits<{ (e: "tour", win: DesktopWindow): void }>();

const desktop = useDesktopStore();
const router = useRouter();

const componentCache = new Map<string, Component>();

const record = computed(() => router.getRoutes().find((r) => r.name === props.win.routeName));

const pageComponent = computed<Component | null>(() => {
  const rec = record.value;
  const comp = rec?.components?.default as RouteRecordRaw["component"] | undefined;
  if (!rec || !comp) return null;
  const key = String(rec.name);
  if (!componentCache.has(key)) {
    componentCache.set(
      key,
      typeof comp === "function" ? defineAsyncComponent(comp as () => Promise<Component>) : (comp as Component),
    );
  }
  return componentCache.get(key)!;
});

/** Props rute (mis. dashboard variant / roleProfile) seperti saat dibuka lewat router. */
const pageProps = computed(() => {
  const option = record.value?.props?.default;
  if (!option) return {};
  const resolved = router.resolve({ name: props.win.routeName, query: props.win.query });
  if (option === true) return resolved.params;
  if (typeof option === "function") return (option as (to: unknown) => Record<string, unknown>)(resolved);
  return option;
});

provide(DESKTOP_WINDOW, {
  id: props.win.id,
  routeName: toRef(() => props.win.routeName),
  query: toRef(() => props.win.query),
  navigate: (routeName, query) => desktop.navigate(props.win.id, routeName, query ?? {}),
  close: () => desktop.close(props.win.id),
});

const frameStyle = computed(() =>
  props.win.maximized
    ? { zIndex: props.win.z }
    : { zIndex: props.win.z, left: `${props.win.x}px`, top: `${props.win.y}px`, width: `${props.win.w}px`, height: `${props.win.h}px` },
);

function track(e: PointerEvent, onMove: (dx: number, dy: number) => void) {
  const sx = e.clientX;
  const sy = e.clientY;
  const move = (ev: PointerEvent) => onMove(ev.clientX - sx, ev.clientY - sy);
  const up = () => {
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", up);
    document.body.classList.remove("os-dragging");
  };
  document.body.classList.add("os-dragging");
  window.addEventListener("pointermove", move);
  window.addEventListener("pointerup", up);
}

function startDrag(e: PointerEvent) {
  if (props.win.maximized || e.button !== 0) return;
  const { x, y } = props.win;
  track(e, (dx, dy) => {
    const maxX = window.innerWidth - 120;
    const maxY = window.innerHeight - desktop.TASKBAR_HEIGHT - 40;
    desktop.update(props.win.id, {
      x: Math.min(Math.max(-props.win.w + 120, x + dx), maxX),
      y: Math.min(Math.max(0, y + dy), maxY),
    });
  });
}

function startResize(e: PointerEvent) {
  const { w, h } = props.win;
  track(e, (dx, dy) => {
    desktop.update(props.win.id, { w: Math.max(420, w + dx), h: Math.max(260, h + dy) });
  });
}
</script>

<style scoped>
.os-window {
  position: absolute;
  display: flex;
  flex-direction: column;
  background: var(--bs-body-bg);
  border-radius: 10px;
  border: 1px solid rgba(0, 0, 0, 0.12);
  box-shadow: 0 18px 50px rgba(15, 23, 42, 0.28);
  overflow: hidden;
}
.os-window.active {
  box-shadow: 0 22px 60px rgba(15, 23, 42, 0.38);
}
.os-window.maximized {
  /* --spi-pane-w: lebar panel Tindak Lanjut yang menempel (0 bila tertutup) agar jendela tidak tertutup panel */
  inset: 0 var(--spi-pane-w, 0px) var(--os-taskbar-h, 48px) 0;
  border-radius: 0;
}
.os-titlebar {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 38px;
  padding-left: 12px;
  background: var(--bs-tertiary-bg);
  border-bottom: 1px solid var(--bs-border-color);
  cursor: default;
  user-select: none;
  touch-action: none;
  flex-shrink: 0;
}
.os-window:not(.active) .os-titlebar {
  opacity: 0.85;
}
.os-title-icon {
  color: var(--bs-primary);
  font-size: 16px;
}
.os-title {
  font-size: 13px;
  font-weight: 600;
  flex: 1;
}
.os-title-actions {
  display: flex;
  height: 100%;
}
.os-btn {
  width: 44px;
  height: 100%;
  border: 0;
  background: transparent;
  color: var(--bs-body-color);
  font-size: 15px;
}
.os-btn:hover {
  background: rgba(0, 0, 0, 0.08);
}
/* Tombol jendela berwarna (keputusan pemilik): minimalkan kuning, maksimalkan hijau, tutup merah. */
.os-min,
.os-max,
.os-close {
  color: #fff;
  font-size: 14px;
  transition: filter 0.15s;
}
.os-min {
  background: #f5b400;
}
.os-max {
  background: #22a559;
}
.os-close {
  background: #e81123;
}
.os-min:hover,
.os-max:hover,
.os-close:hover {
  filter: brightness(1.12);
}
.os-min:hover {
  background: #f5b400;
}
.os-max:hover {
  background: #22a559;
}
.os-close:hover {
  background: #e81123;
  color: #fff;
}
.os-window-body {
  flex: 1;
  overflow: auto;
  padding: 16px 20px;
  background: var(--bs-body-bg);
}
.os-resize {
  position: absolute;
  right: 0;
  bottom: 0;
  width: 16px;
  height: 16px;
  cursor: nwse-resize;
  touch-action: none;
}
</style>
