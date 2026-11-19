<script setup lang="ts">
const FALLBACK_TIMEOUT_MS = 240;

function prefersReducedMotion(): boolean {
  return (
    typeof window !== 'undefined' &&
    typeof window.matchMedia === 'function' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches
  );
}

function waitHeightTransition(node: HTMLElement, done: () => void) {
  let finished = false;
  const finish = () => {
    if (finished) return;
    finished = true;
    node.removeEventListener('transitionend', onEnd);
    window.clearTimeout(timer);
    done();
  };
  const onEnd = (e: TransitionEvent) => {
    if (e.target === node && e.propertyName === 'height') {
      finish();
    }
  };
  node.addEventListener('transitionend', onEnd);
  const timer = window.setTimeout(finish, FALLBACK_TIMEOUT_MS);
}

function onEnter(el: Element, done: () => void) {
  const node = el as HTMLElement;
  if (prefersReducedMotion()) {
    done();
    return;
  }
  node.style.overflow = 'hidden';
  node.style.height = '0';
  node.style.opacity = '0';
  void node.offsetHeight;
  node.style.transition = 'height var(--dur-20) ease-out, opacity var(--dur-18) ease-out';
  node.style.height = `${node.scrollHeight}px`;
  node.style.opacity = '1';
  waitHeightTransition(node, done);
}

function onAfterEnter(el: Element) {
  const node = el as HTMLElement;
  node.style.removeProperty('height');
  node.style.removeProperty('opacity');
  node.style.removeProperty('overflow');
  node.style.removeProperty('transition');
}

function onLeave(el: Element, done: () => void) {
  const node = el as HTMLElement;
  if (prefersReducedMotion()) {
    done();
    return;
  }
  node.style.overflow = 'hidden';
  node.style.height = `${node.scrollHeight}px`;
  node.style.opacity = '1';
  void node.offsetHeight;
  node.style.transition = 'height var(--dur-18) ease-in, opacity var(--dur-15) ease-in';
  node.style.height = '0';
  node.style.opacity = '0';
  waitHeightTransition(node, done);
}

function onAfterLeave(el: Element) {
  const node = el as HTMLElement;
  node.style.removeProperty('height');
  node.style.removeProperty('opacity');
  node.style.removeProperty('overflow');
  node.style.removeProperty('transition');
}
</script>

<template>
  <Transition
    :css="false"
    @enter="onEnter"
    @after-enter="onAfterEnter"
    @leave="onLeave"
    @after-leave="onAfterLeave"
  >
    <slot />
  </Transition>
</template>
