<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue';
import AppIcon from './AppIcon.vue';

// Dropdown kustom bergaya Finto: teal + dark + rounded, list dibatasi tinggi
// layar dan di-scroll di dalam (bukan memanjang), dengan transisi motion Finto.
const props = defineProps<{
  modelValue: string | number;
  options: Array<{ value: string | number; label: string }>;
  ariaLabel: string;
  disabled?: boolean;
  icon?: string;
}>();

const emit = defineEmits<{
  'update:modelValue': [value: string | number];
}>();

const open = ref(false);
const rootEl = ref<HTMLElement | null>(null);
const listEl = ref<HTMLElement | null>(null);
const triggerEl = ref<HTMLElement | null>(null);
const popStyle = ref<Record<string, string>>({});

const current = computed(
  () => props.options.find((o) => String(o.value) === String(props.modelValue)) ?? props.options[0],
);

// Dropdown di-teleport ke <body> supaya tidak terpotong container
// ber-overflow (mis. .settings-pane dengan overflow-y: auto).
function positionPop() {
  const el = triggerEl.value;
  if (!el) return;
  const r = el.getBoundingClientRect();
  const spaceBelow = window.innerHeight - r.bottom;
  const openUp = spaceBelow < 260 && r.top > spaceBelow;
  popStyle.value = {
    position: 'fixed',
    left: `${Math.round(r.left)}px`,
    width: `${Math.round(r.width)}px`,
    ...(openUp
      ? { bottom: `${Math.round(window.innerHeight - r.top + 6)}px` }
      : { top: `${Math.round(r.bottom + 6)}px` }),
  };
}

function toggle() {
  if (props.disabled) return;
  open.value = !open.value;
  if (open.value) {
    positionPop();
    void nextTick(scrollToSelected);
  }
}

function onViewportChange() {
  if (open.value) positionPop();
}

function scrollToSelected() {
  const list = listEl.value;
  if (!list) return;
  const active = list.querySelector<HTMLElement>('[aria-selected="true"]');
  if (active) list.scrollTop = Math.max(0, active.offsetTop - list.clientHeight / 2 + active.offsetHeight / 2);
}

function pick(value: string | number) {
  emit('update:modelValue', value);
  open.value = false;
}

function onDocClick(e: MouseEvent) {
  if (open.value && rootEl.value && !rootEl.value.contains(e.target as Node)) open.value = false;
}

function onKeydown(e: KeyboardEvent) {
  if (!open.value) {
    if (e.key === 'Enter' || e.key === ' ' || e.key === 'ArrowDown') {
      e.preventDefault();
      toggle();
    }
    return;
  }
  const idx = props.options.findIndex((o) => String(o.value) === String(props.modelValue));
  if (e.key === 'Escape') {
    e.preventDefault();
    open.value = false;
  } else if (e.key === 'ArrowDown') {
    e.preventDefault();
    const next = props.options[Math.min(props.options.length - 1, idx + 1)];
    if (next) emit('update:modelValue', next.value);
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    const prev = props.options[Math.max(0, idx - 1)];
    if (prev) emit('update:modelValue', prev.value);
  }
}

onMounted(() => {
  document.addEventListener('click', onDocClick, true);
  window.addEventListener('scroll', onViewportChange, true);
  window.addEventListener('resize', onViewportChange);
});
onBeforeUnmount(() => {
  document.removeEventListener('click', onDocClick, true);
  window.removeEventListener('scroll', onViewportChange, true);
  window.removeEventListener('resize', onViewportChange);
});
</script>

<template>
  <div ref="rootEl" class="finto-select" :class="{ 'is-open': open, 'is-disabled': disabled }">
    <button
      ref="triggerEl"
      type="button"
      class="finto-select-trigger"
      :aria-label="ariaLabel"
      :aria-expanded="open"
      aria-haspopup="listbox"
      :disabled="disabled"
      @click.stop="toggle"
      @keydown="onKeydown"
    >
      <AppIcon v-if="icon" :name="icon" :size="13" />
      <span class="finto-select-value">{{ current?.label ?? '' }}</span>
      <AppIcon name="arrow-right" :size="12" class="finto-select-caret" />
    </button>

    <Teleport to="body">
    <Transition name="finto-select-pop">
      <div v-if="open" class="finto-select-pop" :style="popStyle">
        <ul ref="listEl" class="finto-select-list" role="listbox" :aria-label="ariaLabel">
          <li
            v-for="opt in options"
            :key="String(opt.value)"
            role="option"
            :aria-selected="String(opt.value) === String(modelValue)"
            :class="{ 'is-selected': String(opt.value) === String(modelValue) }"
            @click.stop="pick(opt.value)"
          >
            <span>{{ opt.label }}</span>
            <AppIcon
              v-if="String(opt.value) === String(modelValue)"
              name="check"
              :size="12"
              class="finto-select-check"
            />
          </li>
        </ul>
      </div>
    </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
.finto-select {
  position: relative;
  min-width: 0;
}

.finto-select-trigger {
  display: inline-flex;
  align-items: center;
  gap: var(--space-6);
  width: 100%;
  padding: 5px 9px;
  border-radius: var(--radius-pill);
  border: 1px solid var(--glass-line);
  background: var(--surface-2);
  color: var(--fg);
  font-size: var(--fs-12);
  font-weight: var(--fw-500);
  cursor: pointer;
  transition:
    border-color var(--dur-15) ease,
    background var(--dur-15) ease,
    box-shadow var(--dur-15) ease;
}

.finto-select-trigger:hover {
  background: var(--hover);
  border-color: var(--teal-line);
}

.finto-select.is-open .finto-select-trigger {
  border-color: var(--teal);
  box-shadow: 0 0 0 2px var(--teal-soft);
}

.finto-select.is-disabled .finto-select-trigger {
  opacity: 0.55;
  cursor: not-allowed;
}

.finto-select-value {
  flex: 1;
  text-align: left;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.finto-select-caret {
  transform: rotate(90deg);
  transition: transform var(--dur-18) ease;
  opacity: 0.6;
  flex: none;
}

.finto-select.is-open .finto-select-caret {
  transform: rotate(-90deg);
}

.finto-select-pop {
  z-index: var(--z-flyout);
  padding: var(--space-4);
  border-radius: var(--radius-10);
  background: var(--surface);
  border: 1px solid var(--teal-line);
  box-shadow: var(--shadow-sm);
  transform-origin: top center;
}

/* List dibatasi tinggi layar; sisanya di-scroll di dalam. */
.finto-select-list {
  margin: 0;
  padding: 0;
  list-style: none;
  max-height: min(240px, 42vh);
  overflow-y: auto;
  overscroll-behavior: contain;
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.finto-select-list li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-8);
  padding: var(--space-6) var(--space-10);
  border-radius: var(--radius-6);
  font-size: var(--fs-12);
  color: var(--fg);
  cursor: pointer;
  transition: background var(--dur-12) ease, color var(--dur-12) ease;
}

.finto-select-list li:hover {
  background: var(--teal-soft);
  color: var(--teal-strong);
}

.finto-select-list li.is-selected {
  background: var(--teal-soft);
  color: var(--teal-strong);
  font-weight: var(--fw-600);
}

.finto-select-check {
  flex: none;
}

/* Transisi buka/tutup sesuai motion Finto. */
.finto-select-pop-enter-active,
.finto-select-pop-leave-active {
  transition:
    opacity var(--dur-15) ease,
    transform var(--dur-18) cubic-bezier(0.2, 0.8, 0.2, 1);
}

.finto-select-pop-enter-from,
.finto-select-pop-leave-to {
  opacity: 0;
  transform: translateY(-4px) scale(0.98);
}

@media (prefers-reduced-motion: reduce) {
  .finto-select-pop-enter-active,
  .finto-select-pop-leave-active,
  .finto-select-caret {
    transition: none;
  }
}
</style>
