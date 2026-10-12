<template>
  <div class="preview-shell">
    <div class="preview-layout">
      <aside class="preview-sidebar">
        <a class="preview-brand" href="/dev/handout-preview.html">{{ tr('灵知 / 课程讲义', 'Lingzhi / Course handouts') }}</a>
        <h2>{{ data.course_title || tr('本地课程实验', 'Local course experiment') }}</h2>
        <p class="preview-course-tag">{{ data.lesson_title }}</p>
        <details v-if="sections.length" class="preview-toc"><summary>{{ tr('讲义目录', 'Contents') }}</summary><HandoutTableOfContents :entries="contents" /></details>
        <HandoutConceptMap v-if="sections.length" :sections="conceptSections" :target="paper" />
        <p class="preview-isolation">{{ tr('独立实验 · 不写入正式课程', 'Isolated experiment') }}</p>
      </aside>
      <main class="preview-main">
        <div class="preview-utility">
          <span>{{ tr('课程讲义 / 本地实验', 'Course handout / Local experiment') }}</span>
          <div class="preview-controls">
            <button @click="mode = mode === 'reader' ? 'teacher' : 'reader'">{{ mode === 'reader' ? tr('教师视图', 'Teacher view') : tr('阅读视图', 'Reading view') }}</button>
            <button @click="setLocale(activeLocale === 'zh' ? 'en' : 'zh')">{{ activeLocale === 'zh' ? 'EN' : '中文' }}</button>
            <label class="preview-import">{{ tr('载入实验结果', 'Load experiment') }}<input type="file" accept=".json,application/json" @change="loadFile" /></label>
          </div>
        </div>
        <header class="preview-hero"><p class="preview-eyebrow">{{ tr('第 01 讲 · 学习讲义', 'LECTURE 01 · STUDY NOTES') }}</p><h1>{{ data.lesson_title || tr('让知识清晰展开', 'Make knowledge clear') }}</h1><p>{{ data.course_title }} · {{ tr('沿着概念、推导与例题理解知识', 'Concepts, derivations and worked examples') }}</p></header>
        <HandoutReadingGuide v-if="sections.length" :target="paper" :title="data.lesson_title" />
        <details class="preview-json" :open="!sections.length"><summary>{{ tr('粘贴实验 JSON', 'Paste experiment JSON') }}</summary><textarea v-model="jsonDraft" :aria-label="tr('实验结果 JSON', 'Experiment result JSON')" rows="5" /><button @click="loadJson(jsonDraft)">{{ tr('显示讲义', 'Show handout') }}</button><p v-if="error" role="alert">{{ error }}</p></details>
        <p v-if="data.error" class="preview-failure" role="status">{{ tr('本轮结构检查未通过，以下为保留草稿：', 'Structure check failed. Retained draft:') }} {{ data.error }}</p>
        <div v-if="sections.length" ref="paper" class="preview-paper handout-document">
          <template v-if="mode === 'reader'">
            <section v-for="(section, index) in sections" :id="`preview-${section.section_node_id}`" :key="section.section_node_id" class="preview-section">
              <header><span>{{ String(index + 1).padStart(2, '0') }}</span><h2>{{ section.title }}</h2></header>
              <CourseBlockStream :node="readerNode(section)" content="" read-only :reading-tools="false" :concept-map="false" />
              <aside v-if="section.unassigned_fragment" class="preview-fragment"><h3>{{ tr('未归入内容块的片段', 'Unassigned fragment') }}</h3><MarkdownRenderer :content="section.unassigned_fragment" /></aside>
            </section>
          </template>
          <TeacherScriptDocument v-else course-id="local-preview" :lesson="lesson" external-toolbar :reading-tools="false" :concept-map="false" />
          <template v-if="mode === 'teacher'"><aside v-for="section in sections.filter(item => item.unassigned_fragment)" :key="section.section_node_id" class="preview-fragment"><h3>{{ tr('未归入内容块的片段', 'Unassigned fragment') }}</h3><MarkdownRenderer :content="section.unassigned_fragment || ''" /></aside></template>
        </div>
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import CourseBlockStream from '../src/components/CourseBlockStream.vue'
import TeacherScriptDocument from '../src/components/TeacherScriptDocument.vue'
import MarkdownRenderer from '../src/components/MarkdownRenderer.vue'
import HandoutReadingGuide from '../src/components/HandoutReadingGuide.vue'
import HandoutTableOfContents from '../src/components/HandoutTableOfContents.vue'
import HandoutConceptMap from '../src/components/HandoutConceptMap.vue'
import { buildHandoutConceptSections } from '../src/utils/handout-concepts'
import { activeLocale, setLocale } from '../src/shared/i18n'
import type { ContentBlock, Node } from '../src/stores/types'
import type { TeacherLessonProjection, TeacherLessonScriptSection } from '../src/stores/teacherLessonAuthoring'

const tr = (zh: string, en: string) => activeLocale.value === 'zh' ? zh : en
type ExperimentSection = TeacherLessonScriptSection & { unassigned_fragment?: string }
const data = ref<{ course_title?: string; lesson_title?: string; error?: string; sections?: ExperimentSection[]; plan_sections?: Record<string, Record<string, unknown>> }>({})
const mode = ref('reader')
const jsonDraft = ref('')
const error = ref('')
const sections = computed(() => data.value.sections || [])
const paper = ref<HTMLElement | null>(null)
const conceptSections = computed(() => buildHandoutConceptSections(Object.entries(data.value.plan_sections || {}).map(([node_id, plan]) => ({ ...plan, node_id })), sections.value.map(section => ({
  id: section.section_node_id, title: section.title,
  anchor: mode.value === 'reader' ? `preview-${section.section_node_id}` : `script-section-${section.section_node_id.replace(/[^a-zA-Z0-9_-]/g, '-')}`,
  blocks: (section.blocks || []).map(block => ({ id: block.block_id, title: block.title, anchor: `${mode.value === 'reader' ? 'course' : 'script'}-block-${block.block_id}`, content: block.content, knowledge: block.knowledge_refs?.map(ref => ref.knowledge_id) || block.knowledge_names || [], knowledgeRefs: block.knowledge_refs, sourceRevision: block.source_knowledge_revision })),
}))))
const contents = computed(() => sections.value.flatMap((section, index) => [
  { id: mode.value === 'reader' ? `preview-${section.section_node_id}` : `script-section-${section.section_node_id.replace(/[^a-zA-Z0-9_-]/g, '-')}`, title: `${index + 1} ${section.title}`, child: false },
  ...(section.blocks || []).filter(block => block.title && !block.answer_to).map(block => ({ id: `${mode.value === 'reader' ? 'course' : 'script'}-block-${block.block_id}`, title: block.title, child: true })),
]))
const lesson = computed(() => ({ lesson_unit_id: 'local-preview', number: 1, title: data.value.lesson_title || '', duration_minutes: 45,
  sections: sections.value, script: { current_revision_id: 'local-result', source_lesson_plan_revision_id: 'local-plan', source_state: 'current', ready: !data.value.error, sections: sections.value },
  arrangement: { schema_version: 'teacher_lesson_arrangement_v1', revision_id: 'local-arrangement', lesson_unit_id: 'local-preview', source_outline_revision_id: 'local-outline', lesson_type: 'theory', lesson_type_label: '', blocks: [], source_state: 'current' },
  plan: { lesson_unit_id: 'local-preview', working_revision_id: 'local-plan', source_state: 'current', current_revision: null, ppt_assets: [] },
}) as TeacherLessonProjection)

function readerNode(section: TeacherLessonScriptSection): Node {
  return { node_id: section.section_node_id, parent_node_id: 'local-preview', node_name: section.title, node_level: 2,
    node_type: 'original', node_content: '', generation_status: data.value.error ? 'error' : 'completed', generated_chars: 0,
    content_blocks: (section.blocks || []).map((block, index) => ({ block_id: block.block_id, type: block.role as ContentBlock['type'], title: block.title, content: block.content, order: index, status: data.value.error ? 'draft' : 'final',
      metadata: { content_type: block.content_type, type_label: block.type_label, answer_to: block.answer_to, concept_refs: block.knowledge_refs?.map(ref => ref.knowledge_id) || block.knowledge_names || [], knowledge_refs: block.knowledge_refs, source_knowledge_revision: block.source_knowledge_revision } })),
  }
}
function loadJson(text: string) {
  try {
    const parsed = JSON.parse(text)
    if (!Array.isArray(parsed.sections) || !parsed.sections.length || parsed.sections.some((section: TeacherLessonScriptSection) => !section.section_node_id || !Array.isArray(section.blocks))) throw new Error('invalid')
    data.value = parsed
    error.value = ''
    jsonDraft.value = text
    try { sessionStorage.setItem('lingzhi-dev-handout-preview', text) } catch { /* Large local experiments can still be read without retaining the preview. */ }
  } catch {
    error.value = tr('请载入实验脚本输出的 handout.json。', 'Load handout.json produced by the experiment script.')
  }
}
async function loadFile(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (file) loadJson(await file.text())
}
const retainedPreview = sessionStorage.getItem('lingzhi-dev-handout-preview')
if (retainedPreview) loadJson(retainedPreview)
</script>

<style scoped>
/* This standalone document scrolls at page level; the app shell locks body scrolling. */
:global(body.handout-preview-page){overflow-x:hidden;overflow-y:auto}
.preview-shell{min-height:100vh;background:#f5f4f0;color:#242a35;font-family:var(--handout-sans)}
.preview-layout{display:grid;grid-template-columns:minmax(0,1100px) 360px;max-width:1460px;margin:0 auto}
.preview-sidebar{grid-column:2;grid-row:1;position:sticky;top:0;align-self:start;height:100vh;overflow:auto;padding:32px 24px;border-left:1px solid #e1e5ec;font-size:15px;line-height:1.65}
.preview-brand{color:#315e91;font-size:15px;text-underline-offset:3px}
.preview-sidebar h2{margin:26px 0 4px;font:700 16px/1.65 var(--handout-sans)}
.preview-course-tag{margin:0 0 24px;color:#657080;font-size:15px;line-height:1.7}
.preview-isolation{margin-top:32px;padding-top:20px;border-top:1px solid #e1e5ec;font-size:15px;color:#657080}
.preview-toc{margin-bottom:22px}.preview-toc summary{font-weight:700;cursor:pointer;margin-bottom:10px}.preview-sidebar :deep(.handout-concept-map){border:0;background:transparent}.preview-sidebar :deep(.handout-concept-map header){padding:16px 0}.preview-sidebar :deep(.concept-relations){padding-inline:0}.preview-sidebar :deep(.concept-section-title){padding-inline:0}.preview-sidebar :deep(.handout-concept-map footer){padding-inline:0}
.preview-main{grid-column:1;grid-row:1;min-width:0;min-height:100vh;padding:46px 70px 90px;background:#fff}
.preview-utility{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;margin-bottom:36px;font-size:15px;color:#657080}
.preview-controls{display:flex;align-items:center;gap:12px}
.preview-controls button,.preview-import,.preview-json button{border:0;border-radius:0;padding:7px 9px;background:transparent;color:#526071;font:15px/1.6 var(--handout-sans);cursor:pointer}
.preview-controls button:hover,.preview-import:hover,.preview-json button:hover{background:#eae6f2;color:#523279}
.preview-controls button:focus-visible,.preview-import:focus-within{outline:3px solid #328dcc;outline-offset:3px}
.preview-import input{position:absolute;width:1px;height:1px;opacity:0;overflow:hidden}
.preview-eyebrow{margin:0 0 12px;color:#6e4a9c;font:700 15px/1.65 var(--handout-sans);letter-spacing:1.7px}
.preview-hero h1{margin:0 0 18px;color:#242a35;font:700 42px/1.3 var(--handout-serif);letter-spacing:1px}
.preview-hero>p:last-child{margin:0;font:700 18px/1.95 var(--handout-serif)}
.preview-paper{min-width:0;background:#fff}
.preview-section{padding:0;scroll-margin-top:30px}
.preview-section>header{display:flex;align-items:baseline;gap:12px;margin:42px 0 24px;padding-top:22px;border-top:1px solid #d4dae4}
.preview-section>header span{font:700 20px/1.45 var(--handout-serif)}
.preview-section h2{margin:0;font:700 27px/1.45 var(--handout-serif);color:#242a35}
.preview-json{margin:0 0 22px;color:#657080;font:15px/1.7 var(--handout-sans)}
.preview-json summary{cursor:pointer}.preview-json textarea{width:100%;margin:15px 0 10px;padding:16px;border:1px solid #d8ddea;border-radius:0;background:#fff;font-size:15px}
.preview-json p{color:#a64355}
.preview-paper :deep(.course-content-block){margin:0;padding:0;border:0;scroll-margin-top:30px}
.preview-paper :deep(.script-document){border:0;border-radius:0;box-shadow:none;background:transparent}
.preview-paper :deep(.script-continuous){width:100%;max-width:none}
.preview-paper :deep(.handout-reading-body>.script-body){padding:0}
.preview-paper :deep(.script-tabs){display:none}
.preview-failure,.preview-fragment{padding:18px 22px;margin-bottom:24px;border:1px solid #ead5c3;border-left:4px solid #9a531d;border-radius:0;background:#fcf2e9;color:#9a531d;font-size:15px;line-height:1.7}
.preview-fragment h3{margin:0 0 15px;font-size:17px}
@media(max-width:1150px){.preview-layout{grid-template-columns:minmax(0,1fr) 330px}.preview-sidebar{padding-inline:18px}.preview-main{padding-inline:40px}}
@media(max-width:850px){.preview-layout{display:flex;flex-direction:column}.preview-sidebar{position:static;width:100%;height:auto;max-height:560px;border-right:0;border-bottom:1px solid #e1e5ec}.preview-main{width:100%;padding:28px 24px 60px}.preview-hero h1{font-size:32px}}
@media print{.preview-sidebar,.preview-utility,.preview-json{display:none}.preview-layout{display:block}.preview-main{padding:0;border:0}.preview-shell{background:#fff}}
</style>
