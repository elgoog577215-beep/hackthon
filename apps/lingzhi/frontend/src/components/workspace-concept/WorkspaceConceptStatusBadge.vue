<template>
  <span class="concept-status-badge" :data-status="visualStatus">
    <component :is="icon" :size="12" aria-hidden="true" />
    {{ label }}
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { BadgeCheck, CircleDashed, RefreshCw, TriangleAlert } from 'lucide-vue-next'

const props = defineProps<{
  status?: string
  hasUnpublishedChanges?: boolean
  failed?: boolean
}>()

const visualStatus = computed(() => {
  if (props.failed) return 'failed'
  if (props.status === 'published' && props.hasUnpublishedChanges) return 'stale'
  if (props.status === 'published') return 'published'
  return 'draft'
})

const label = computed(() => ({
  draft: '草稿',
  published: '已发布',
  stale: '有未发布更改',
  failed: '发布失败',
}[visualStatus.value]))

const icon = computed(() => ({
  draft: CircleDashed,
  published: BadgeCheck,
  stale: RefreshCw,
  failed: TriangleAlert,
}[visualStatus.value]))
</script>

<style scoped>
.concept-status-badge{display:inline-flex;align-items:center;gap:5px;width:max-content;padding:4px 7px;border-radius:var(--lz-radius-control);color:var(--lz-text-secondary);background:var(--lz-surface-muted);font-size:10px;font-weight:750;white-space:nowrap}
.concept-status-badge[data-status="published"]{color:var(--lz-success);background:var(--lz-success-soft)}
.concept-status-badge[data-status="stale"]{color:var(--lz-warning);background:var(--lz-warning-soft)}
.concept-status-badge[data-status="failed"]{color:var(--lz-danger);background:var(--lz-danger-soft)}
</style>
