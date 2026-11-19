<script setup lang="ts">
import { computed } from 'vue';
import { currentBrand } from '../../utils/theme';
import finoSalesImg from '../../assets/branding/fino-sales.png';
import finoFinanceImg from '../../assets/branding/fino-finance.png';
import finoAccountingImg from '../../assets/branding/fino-accounting.png';
import finoPurchasingImg from '../../assets/branding/fino-purchasing.png';

const props = withDefaults(
  defineProps<{
    branchKey?: string;
    name?: string;
    size?: 'xs' | 'md' | 'lg';
  }>(),
  { branchKey: '', name: '', size: 'md' },
);

const OUTFITS: Record<string, string> = {
  sales: finoSalesImg,
  finance: finoFinanceImg,
  accounting: finoAccountingImg,
  purchasing: finoPurchasingImg,
};

const isFinto = computed(() => currentBrand.value === 'finto');
const avatarSrc = computed(() => OUTFITS[props.branchKey] ?? finoSalesImg);
const sizeClass = computed(() => (props.size === 'md' ? '' : props.size));
const initial = computed(() => (props.name || props.branchKey || 'A').charAt(0).toUpperCase());
</script>

<template>
  <span
    v-if="isFinto"
    class="agent-dot fino-avatar"
    :class="sizeClass"
    :data-branch="branchKey || undefined"
  >
    <img :src="avatarSrc" :alt="name || branchKey || 'Fino'" />
  </span>
  <span
    v-else
    class="agent-dot"
    :class="sizeClass"
    :data-branch="branchKey || undefined"
  >
    {{ initial }}
  </span>
</template>
