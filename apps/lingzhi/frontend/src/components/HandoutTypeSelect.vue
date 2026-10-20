<template>
  <div class="handout-type-select" :data-group="definition?.group || undefined">
    <label>
      <span>{{ t('courseWorkbench.scriptDocument.typeGuide.selectType') }}</span>
      <select :value="modelValue" @change="emit('update:modelValue', ($event.target as HTMLSelectElement).value)">
        <option v-if="retainOriginal" :value="originalType ?? modelValue">{{ currentLabel || originalType || modelValue || t('courseWorkbench.scriptDocument.typeGuide.originalType') }}</option>
        <optgroup v-for="group in handoutContentGroups" :key="group.id" :label="group.label[activeLocale]">
          <option v-for="item in handoutTypesForGroup(group.id)" :key="item.id" :value="item.id">{{ item.label[activeLocale] }}</option>
        </optgroup>
      </select>
    </label>
    <p v-if="definition?.purpose">{{ definition.purpose[activeLocale] }}</p>
    <p v-if="definition?.checkpoints" class="handout-type-select__points">{{ definition.checkpoints[activeLocale].join(' · ') }}</p>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { activeLocale, t } from '../shared/i18n'
import { handoutContentGroups, handoutContentTypes, handoutTypeDefinition, handoutTypesForGroup } from '../utils/handout-content'
const props = defineProps<{ modelValue: string; originalType?: string; currentLabel?: string }>()
const emit = defineEmits<{ (event: 'update:modelValue', value: string): void }>()
const definition = computed(() => handoutTypeDefinition(props.modelValue))
const retainOriginal = computed(() => !handoutContentTypes.some(item => item.id === (props.originalType ?? props.modelValue) && !item.legacy))
</script>

<style scoped>
.handout-type-select{margin:0 0 12px;color:#435066;font:15px/1.65 var(--handout-sans)}.handout-type-select label{display:flex;align-items:center;flex-wrap:wrap;gap:10px;font-weight:650}.handout-type-select select{min-width:180px;max-width:100%;padding:7px 10px;border:1px solid #cbd4e1;border-radius:6px;background:#fff;color:#263147;font:inherit}.handout-type-select select:focus-visible{outline:2px solid #6366f1;outline-offset:2px}.handout-type-select p{margin:7px 0 0}.handout-type-select__points{color:#65738a}
</style>
