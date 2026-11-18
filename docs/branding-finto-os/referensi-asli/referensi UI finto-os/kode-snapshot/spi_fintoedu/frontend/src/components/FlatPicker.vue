<template>
	<label class="form-label" :class="labelClass" v-if="label">{{ label }}</label>
	<b-form-input
		:type="type ?? 'text'"
		:id="id"
		:placeholder="placeholder"
		:model-value="modelValue"
		:class="customClass"
		@input="updateValue"
		v-bind="$attrs"
	/>
</template>

<script setup lang="ts">
import flatpickr from "flatpickr";
import type { Instance } from "flatpickr/dist/types/instance";
import type { Options } from "flatpickr/dist/types/options";

import { onBeforeUnmount, onMounted, watch } from "vue";
import type { InputType } from "bootstrap-vue-next";

type FlatPickerProps = {
	label?: string;
	type?: InputType;
	customClass?: string;
	labelClass?: string;
	placeholder?: string;
	id: string;
	modelValue?: string;
	options?: Options;
};

const props = defineProps<FlatPickerProps>();

const emit = defineEmits(["update:modelValue"]);
let picker: Instance | null = null;

const updateValue = (e: Event) => {
	emit("update:modelValue", (e.target as HTMLInputElement).value);
};

onMounted(() => {
	const element = document.getElementById(props.id) as HTMLInputElement | null;
	if (!element) return;
	picker = flatpickr(element, {
		...props.options,
		defaultDate: props.modelValue,
	});
});

watch(
	() => props.modelValue,
	(value) => {
		if (!picker || value === picker.input.value) return;
		picker.setDate(value || "", false);
	},
);

onBeforeUnmount(() => picker?.destroy());
</script>
