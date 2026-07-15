<script setup lang="ts">
import type { PresentationQualityIssue } from '@/types/presentation'

defineProps<{
  status: 'passed' | 'blocked' | 'advisory'
  issues: PresentationQualityIssue[]
}>()
</script>

<template>
  <section class="quality-panel" :class="`is-${status}`">
    <div class="quality-heading">
      <strong>{{ status === 'passed' ? '课件质量检查通过' : status === 'blocked' ? '课件暂不能正式导出' : '课件有可优化项' }}</strong>
      <span>{{ issues.length }} 项</span>
    </div>
    <p v-if="!issues.length">目标覆盖、来源、版式容量和渲染结果均已对齐。</p>
    <ol v-else>
      <li v-for="issue in issues" :key="`${issue.code}:${issue.target_id}`">
        <span class="severity">{{ issue.severity === 'blocking' ? '必须修复' : issue.severity === 'warning' ? '建议' : '提示' }}</span>
        <div><b>{{ issue.message }}</b><p>{{ issue.fix_action }}</p></div>
      </li>
    </ol>
  </section>
</template>

<style scoped>
.quality-panel{padding:12px;border:1px solid #e2e8f0;border-radius:9px;color:#475569;background:#f8fafc;font-size:12px}.quality-panel.is-blocked{border-color:#fed7aa;background:#fffbeb}.quality-panel.is-passed{border-color:#bbf7d0;background:#f0fdf4}.quality-heading{display:flex;align-items:center;justify-content:space-between;color:#334155}.quality-heading span{color:#64748b}.quality-panel>p{margin:7px 0 0;line-height:1.55}.quality-panel ol{display:grid;gap:8px;margin:10px 0 0;padding:0;list-style:none}.quality-panel li{display:grid;grid-template-columns:auto minmax(0,1fr);gap:8px}.quality-panel li b{color:#334155;font-size:12px}.quality-panel li p{margin:2px 0 0;line-height:1.5}.severity{align-self:start;padding:2px 5px;border-radius:4px;color:#b45309;background:#fef3c7;font-size:10px}
</style>
