<template>
  <section class="border-b border-slate-100 px-4 py-3">
    <button type="button" class="flex w-full items-center gap-2 text-left" @click="expanded = !expanded">
      <CircleCheck v-if="status === 'passed'" :size="15" class="text-emerald-600" />
      <TriangleAlert v-else :size="15" class="text-amber-600" />
      <span class="min-w-0 flex-1 truncate text-xs font-semibold text-slate-700">
        {{ t('courseGeneration.report.title', '生成质量报告') }}
      </span>
      <span class="text-[11px] text-slate-400">{{ statusLabel }}</span>
      <ChevronDown :size="14" class="text-slate-400 transition-transform" :class="{ 'rotate-180': expanded }" />
    </button>
    <div v-if="expanded" class="mt-3 space-y-3 text-xs">
      <div class="grid grid-cols-3 gap-2 text-center">
        <div class="rounded-lg bg-emerald-50 px-2 py-2 text-emerald-700">
          <strong class="block text-sm">{{ usedCount }}</strong>
          {{ t('courseGeneration.report.used', '已使用') }}
        </div>
        <div class="rounded-lg bg-slate-100 px-2 py-2 text-slate-600">
          <strong class="block text-sm">{{ unusedCount }}</strong>
          {{ t('courseGeneration.report.unused', '未使用') }}
        </div>
        <div class="rounded-lg bg-red-50 px-2 py-2 text-red-600">
          <strong class="block text-sm">{{ failedCount }}</strong>
          {{ t('courseGeneration.report.failed', '解析失败') }}
        </div>
      </div>
      <div v-if="coverage.length" class="space-y-1.5">
        <div v-for="item in coverage" :key="item.asset_id" class="flex items-center gap-2">
          <FileText :size="13" class="shrink-0 text-slate-400" />
          <span class="min-w-0 flex-1 truncate text-slate-600">{{ item.filename || item.asset_id }}</span>
          <span :class="coverageClass(item.coverage_level)">{{ coverageLabel(item.coverage_level) }}</span>
        </div>
      </div>
      <div v-if="conflicts.length || gaps.length" class="space-y-1 rounded-lg bg-amber-50 px-3 py-2 text-amber-800">
        <div v-if="conflicts.length">{{ t('courseGeneration.report.conflicts', '资料冲突') }}：{{ conflicts.length }}</div>
        <div v-if="gaps.length">{{ t('courseGeneration.report.gaps', '覆盖缺口') }}：{{ gaps.length }}</div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { ChevronDown, CircleCheck, FileText, TriangleAlert } from 'lucide-vue-next'
import { t } from '@/shared/i18n'

const props = defineProps<{ report: Record<string, any> }>()
const expanded = ref(false)
const grounding = computed(() => props.report?.grounding_quality || {})
const coverage = computed<any[]>(() => grounding.value.material_coverage || props.report?.material_coverage || [])
const conflicts = computed<any[]>(() => grounding.value.conflicts || [])
const gaps = computed<any[]>(() => grounding.value.gaps || [])
const status = computed(() => props.report?.final_status || 'completed_with_warnings')
const statusLabel = computed(() => status.value === 'passed'
  ? t('courseGeneration.report.passed', '通过')
  : t('courseGeneration.report.warnings', '有警告'))
const usedCount = computed(() => coverage.value.filter(item => item.coverage_level === 'used').length)
const failedCount = computed(() => coverage.value.filter(item => item.coverage_level === 'parse_failed').length)
const unusedCount = computed(() => coverage.value.length - usedCount.value - failedCount.value)

const coverageLabel = (level: string) => t(`courseGeneration.report.coverage.${level}`, level)
const coverageClass = (level: string) => level === 'used'
  ? 'text-emerald-600'
  : level === 'parse_failed' ? 'text-red-500' : 'text-slate-400'
</script>
