<template>
  <section class="course-quick-reference" :aria-label="t('learningViews.quickReference')">
    <header class="course-quick-reference__header">
      <div>
        <span>{{ t('learningViews.courseReference') }}</span>
        <h2>{{ t('learningViews.quickReference') }}</h2>
      </div>
      <span v-if="!loading && items.length" class="course-quick-reference__count">
        {{ items.length }} {{ t('learningViews.referenceCount') }}
      </span>
    </header>

    <div v-if="loading" class="course-quick-reference__loading" role="status" :aria-label="t('learningViews.loadingReferences')">
      <span v-for="line in 5" :key="line" />
    </div>

    <div v-else-if="groups.length" class="course-quick-reference__groups">
      <details v-for="group in groups" :key="group.nodeId" class="course-quick-reference__group" open>
        <summary>
          <span class="course-quick-reference__chapter">{{ group.nodeName }}</span>
          <span class="course-quick-reference__group-count">{{ group.items.length }}</span>
        </summary>
        <ol>
          <li v-for="(item, index) in group.items" :key="item.id">
            <button type="button" class="course-quick-reference__item" @click="emit('locate', item)">
              <span class="course-quick-reference__item-heading">
                <span class="course-quick-reference__number">{{ index + 1 }}</span>
                <span class="course-quick-reference__kind" :data-kind="item.kind">{{ kindLabel(item.kind) }}</span>
                <strong>{{ item.title }}</strong>
                <ArrowUpRight :size="14" aria-hidden="true" />
              </span>
              <MathText
                v-if="item.expression"
                class="course-quick-reference__formula"
                tag="div"
                :content="`$$${item.expression}$$`"
              />
              <MathText v-else class="course-quick-reference__summary" tag="div" :content="item.summary || t('learningViews.referenceNoSummary')" />
            </button>
          </li>
        </ol>
      </details>
    </div>

    <div v-else class="course-quick-reference__empty" role="status">
      <BookOpenText :size="21" aria-hidden="true" />
      <strong>{{ t('learningViews.noReferences') }}</strong>
      <span>{{ t('learningViews.noReferencesHint') }}</span>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ArrowUpRight, BookOpenText } from 'lucide-vue-next'
import MathText from './MathText.vue'
import { t } from '../shared/i18n'
import type { CourseQuickReferenceItem, CourseReferenceKind } from '../utils/course-quick-reference'

const props = withDefaults(defineProps<{
  items: CourseQuickReferenceItem[]
  loading?: boolean
}>(), { loading: false })

const emit = defineEmits<{ locate: [item: CourseQuickReferenceItem] }>()

const groups = computed(() => {
  const grouped = new Map<string, { nodeId: string; nodeName: string; items: CourseQuickReferenceItem[] }>()
  for (const item of props.items) {
    const group = grouped.get(item.nodeId) || { nodeId: item.nodeId, nodeName: item.nodeName, items: [] }
    group.items.push(item)
    grouped.set(item.nodeId, group)
  }
  return [...grouped.values()]
})

function kindLabel(kind: CourseReferenceKind) {
  return t(`learningViews.referenceKinds.${kind}`)
}
</script>

<style scoped>
.course-quick-reference { min-width:0; min-height:0; height:100%; display:flex; flex-direction:column; overflow:hidden; color:var(--lz-text-strong,#30364b); background:#fff; }
.course-quick-reference__header { flex:none; display:flex; align-items:flex-end; justify-content:space-between; gap:12px; padding:20px 18px 14px; border-bottom:1px solid #e8eaf2; }
.course-quick-reference__header > div > span { color:#7b6b9a; font-size:11px; font-weight:700; }
.course-quick-reference__header h2 { margin:4px 0 0; color:#34394e; font-size:19px; line-height:1.35; }
.course-quick-reference__count { flex:none; color:#81879c; font-size:11px; font-variant-numeric:tabular-nums; }
.course-quick-reference__groups { min-height:0; flex:1; overflow:auto; overscroll-behavior:contain; padding:4px 18px 24px; }
.course-quick-reference__group { border-bottom:1px solid #eceef4; }
.course-quick-reference__group > summary { min-height:43px; display:flex; align-items:center; justify-content:space-between; gap:10px; cursor:pointer; list-style:none; }
.course-quick-reference__group > summary::-webkit-details-marker { display:none; }
.course-quick-reference__chapter { min-width:0; overflow:hidden; color:#41475d; font-size:13px; font-weight:700; text-overflow:ellipsis; white-space:nowrap; }
.course-quick-reference__group-count { flex:none; color:#9298aa; font-size:11px; font-variant-numeric:tabular-nums; }
.course-quick-reference__group ol { display:grid; gap:2px; margin:0; padding:0 0 12px; list-style:none; }
.course-quick-reference__item { width:100%; display:block; padding:10px 9px 11px; border:0; border-radius:8px; color:inherit; background:transparent; text-align:left; cursor:pointer; transition:background .16s ease; }
.course-quick-reference__item:hover { background:#f7f6fc; }
.course-quick-reference__item:focus-visible { outline:2px solid #745fe0; outline-offset:1px; }
.course-quick-reference__item-heading { min-width:0; display:grid; grid-template-columns:18px auto minmax(0,1fr) 14px; align-items:center; gap:7px; }
.course-quick-reference__number { color:#989db0; font-size:11px; font-variant-numeric:tabular-nums; text-align:center; }
.course-quick-reference__kind { padding:2px 6px; border-radius:4px; color:#6953c8; background:#f1effb; font-size:10px; font-weight:700; white-space:nowrap; }
.course-quick-reference__kind[data-kind="definition"] { color:#28785a; background:#eef7f2; }
.course-quick-reference__kind[data-kind="law"] { color:#886027; background:#faf5e9; }
.course-quick-reference__kind[data-kind="theorem"] { color:#72509a; background:#f3eff8; }
.course-quick-reference__item-heading strong { min-width:0; overflow:hidden; color:#42485e; font-size:13px; font-weight:650; line-height:1.45; text-overflow:ellipsis; }
.course-quick-reference__item-heading svg { color:#8b83aa; }
.course-quick-reference__summary { display:-webkit-box; margin:7px 0 0 25px; overflow:hidden; color:#757c91; font-size:12px; line-height:1.58; -webkit-box-orient:vertical; -webkit-line-clamp:4; }
.course-quick-reference__formula { display:block; min-width:0; margin:7px 0 0 25px; overflow-x:auto; color:#484260; font-size:13px; line-height:1.6; }
.course-quick-reference__formula :deep(.katex-display) { margin:0; text-align:left; }
.course-quick-reference__empty { min-height:240px; display:flex; flex:1; flex-direction:column; align-items:center; justify-content:center; gap:9px; padding:24px; color:#8a90a4; text-align:center; }
.course-quick-reference__empty svg { color:#7664ca; }
.course-quick-reference__empty strong { color:#50566c; font-size:13px; }
.course-quick-reference__empty span { max-width:260px; font-size:12px; line-height:1.65; }
.course-quick-reference__loading { display:grid; gap:16px; padding:22px 18px; }
.course-quick-reference__loading span { height:54px; border-radius:7px; background:linear-gradient(90deg,#f1f2f7 20%,#f8f8fb 44%,#f1f2f7 68%); background-size:250% 100%; animation:reference-shimmer 1.2s ease-in-out infinite; }
@keyframes reference-shimmer { to { background-position-x:-120%; } }
@media(prefers-reduced-motion:reduce) { .course-quick-reference__loading span { animation:none; } }
</style>
