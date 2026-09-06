<template>
  <section
    v-if="affectedSections.length"
    class="impact-preview"
    data-testid="course-impact-preview"
    :aria-label="countLabel"
  >
    <header class="impact-preview__head">
      <ListTree :size="14" />
      <strong>{{ countLabel }}</strong>
    </header>

    <ul class="impact-preview__list">
      <li
        v-for="section in affectedSections"
        :key="section.id"
        class="impact-preview__item"
        data-testid="impact-section"
      >
        <span class="impact-preview__dot" aria-hidden="true" />
        <span class="impact-preview__name">{{ section.label }}</span>
        <span v-if="!section.known" class="impact-preview__unknown">
          {{ t('courseWorkspace.impactPreview.unknownSection', '不在当前目录中') }}
        </span>
      </li>
    </ul>

    <p class="impact-preview__note">
      {{ t('courseWorkspace.impactPreview.note', '确认前不会修改正式课程。') }}
    </p>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { ListTree } from 'lucide-vue-next'
import { t } from '../shared/i18n'

const props = withDefaults(defineProps<{
  /** Section ids the domain reports as affected — the same list it applies against. */
  affectedSectionIds: string[]
  /** Course outline, used only to turn ids into names. */
  sections?: Array<{ node_id: string; node_name: string }>
}>(), { sections: () => [] })

/**
 * Resolve ids to display rows.
 *
 * Two rules exist to keep the number honest, because this preview is the only
 * thing a learner sees before a broad change is applied:
 *  - deduplicate, since the domain derives sections from block ids and can
 *    repeat one;
 *  - keep ids that are missing from the outline instead of filtering them out.
 *    Dropping one would under-report the blast radius, which is the single
 *    direction of error that matters here.
 */
const affectedSections = computed(() => {
  const seen = new Set<string>()
  const rows: Array<{ id: string; label: string; known: boolean }> = []
  for (const rawId of props.affectedSectionIds || []) {
    const id = String(rawId || '')
    if (!id || seen.has(id)) continue
    seen.add(id)
    const match = props.sections.find(section => section.node_id === id)
    rows.push({ id, label: match?.node_name || id, known: Boolean(match) })
  }
  return rows
})

const countLabel = computed(() => {
  const count = affectedSections.value.length
  const template = count === 1
    ? t('courseWorkspace.impactPreview.countOne', '将影响 {count} 个小节')
    : t('courseWorkspace.impactPreview.count', '将影响 {count} 个小节')
  return template.replace('{count}', String(count))
})
</script>

<style scoped>
.impact-preview { min-width:0; margin:10px 0; padding:10px 11px; border:1px solid rgba(199,210,254,.8); border-radius:9px; background:rgba(248,250,255,.9); }
.impact-preview__head { display:flex; align-items:center; gap:6px; color:var(--lz-brand-strong); }
.impact-preview__head strong { font-size:10px; font-weight:750; }
.impact-preview__list { margin:7px 0 0; padding:0; list-style:none; display:grid; gap:4px; }
.impact-preview__item { min-width:0; display:flex; align-items:baseline; gap:6px; color:var(--lz-text-secondary); font-size:10px; line-height:1.5; }
.impact-preview__dot { flex:0 0 auto; width:4px; height:4px; border-radius:999px; background:#a5b4fc; }
.impact-preview__name { min-width:0; overflow-wrap:anywhere; }
.impact-preview__unknown { flex:0 0 auto; color:var(--lz-text-muted); font-size:9px; }
.impact-preview__note { margin:8px 0 0; color:var(--lz-text-muted); font-size:9px; line-height:1.5; }
</style>
