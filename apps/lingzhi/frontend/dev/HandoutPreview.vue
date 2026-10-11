<template>
  <div class="preview-shell">
    <header class="preview-topbar">
      <a class="preview-brand" href="/dev/handout-preview.html"><span>灵</span>{{ tr('灵知', 'Lingzhi') }} <small>{{ tr('讲义实验预览', 'Handout preview') }}</small></a>
      <div class="preview-controls">
        <button @click="mode = mode === 'reader' ? 'teacher' : 'reader'">{{ mode === 'reader' ? tr('教师视图', 'Teacher view') : tr('阅读视图', 'Reading view') }}</button>
        <button @click="setLocale(activeLocale === 'zh' ? 'en' : 'zh')">{{ activeLocale === 'zh' ? 'EN' : '中文' }}</button>
        <label class="preview-import">{{ tr('载入实验结果', 'Load experiment') }}<input type="file" accept=".json,application/json" @change="loadFile" /></label>
      </div>
    </header>
    <div class="preview-layout">
      <aside class="preview-sidebar">
        <p class="preview-eyebrow">{{ tr('课程讲义', 'COURSE HANDOUT') }}</p>
        <h2>{{ data.course_title || tr('本地课程实验', 'Local course experiment') }}</h2>
        <span class="preview-course-tag">{{ tr('独立实验 · 不写入正式课程', 'Isolated experiment') }}</span>
        <nav v-if="sections.length" :aria-label="tr('讲义小节', 'Handout sections')">
          <a v-for="(section, index) in sections" :key="section.section_node_id" :href="mode === 'reader' ? `#preview-${section.section_node_id}` : `#script-section-${section.section_node_id.replace(/[^a-zA-Z0-9_-]/g, '-')}`"><span>{{ String(index + 1).padStart(2, '0') }}</span>{{ section.title }}</a>
        </nav>
        <div class="preview-legend"><p>{{ tr('阅读标记', 'READING GUIDE') }}</p><span class="definition">{{ tr('定义与条件', 'Definitions & conditions') }}</span><span class="result">{{ tr('定理与结论', 'Theorems & results') }}</span><span class="example">{{ tr('例题与应用', 'Examples & applications') }}</span><span class="warning">{{ tr('易错与辨析', 'Common pitfalls') }}</span></div>
      </aside>
      <main class="preview-main">
        <header class="preview-hero"><p class="preview-eyebrow">{{ tr('第 01 讲', 'LECTURE 01') }}</p><h1>{{ data.lesson_title || tr('让知识清晰展开', 'Make knowledge clear') }}</h1><p>{{ tr('沿着概念、推导与例题理解知识，完成自测后再展开解答。', 'Follow concepts, derivations and examples. Try each exercise before opening its answer.') }}</p></header>
        <details class="preview-json" :open="!sections.length"><summary>{{ tr('粘贴实验 JSON', 'Paste experiment JSON') }}</summary><textarea v-model="jsonDraft" :aria-label="tr('实验结果 JSON', 'Experiment result JSON')" rows="5" /><button @click="loadJson(jsonDraft)">{{ tr('显示讲义', 'Show handout') }}</button><p v-if="error" role="alert">{{ error }}</p></details>
        <p v-if="data.error" class="preview-failure" role="status">{{ tr('本轮结构检查未通过，以下为保留草稿：', 'Structure check failed. Retained draft:') }} {{ data.error }}</p>
        <div v-if="sections.length" class="preview-paper">
          <template v-if="mode === 'reader'">
            <section v-for="(section, index) in sections" :id="`preview-${section.section_node_id}`" :key="section.section_node_id" class="preview-section">
              <header><span>{{ String(index + 1).padStart(2, '0') }}</span><h2>{{ section.title }}</h2></header>
              <CourseBlockStream :node="readerNode(section)" content="" read-only />
              <aside v-if="section.unassigned_fragment" class="preview-fragment"><h3>{{ tr('未归入内容块的片段', 'Unassigned fragment') }}</h3><MarkdownRenderer :content="section.unassigned_fragment" /></aside>
            </section>
          </template>
          <TeacherScriptDocument v-else course-id="local-preview" :lesson="lesson" external-toolbar />
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
import { activeLocale, setLocale } from '../src/shared/i18n'
import type { ContentBlock, Node } from '../src/stores/types'
import type { TeacherLessonProjection, TeacherLessonScriptSection } from '../src/stores/teacherLessonAuthoring'

const tr = (zh: string, en: string) => activeLocale.value === 'zh' ? zh : en
type ExperimentSection = TeacherLessonScriptSection & { unassigned_fragment?: string }
const data = ref<{ course_title?: string; lesson_title?: string; error?: string; sections?: ExperimentSection[] }>({})
const mode = ref('reader')
const jsonDraft = ref('')
const error = ref('')
const sections = computed(() => data.value.sections || [])
const lesson = computed(() => ({ lesson_unit_id: 'local-preview', number: 1, title: data.value.lesson_title || '', duration_minutes: 45,
  sections: sections.value, script: { current_revision_id: 'local-result', source_lesson_plan_revision_id: 'local-plan', source_state: 'current', ready: !data.value.error, sections: sections.value },
  arrangement: { schema_version: 'teacher_lesson_arrangement_v1', revision_id: 'local-arrangement', lesson_unit_id: 'local-preview', source_outline_revision_id: 'local-outline', lesson_type: 'theory', lesson_type_label: '', blocks: [], source_state: 'current' },
  plan: { lesson_unit_id: 'local-preview', working_revision_id: 'local-plan', source_state: 'current', current_revision: null, ppt_assets: [] },
}) as TeacherLessonProjection)

function readerNode(section: TeacherLessonScriptSection): Node {
  return { node_id: section.section_node_id, parent_node_id: 'local-preview', node_name: section.title, node_level: 2,
    node_type: 'original', node_content: '', generation_status: 'completed', generated_chars: 0,
    content_blocks: (section.blocks || []).map((block, index) => ({ block_id: block.block_id, type: block.role as ContentBlock['type'], title: block.title, content: block.content, order: index, status: 'final',
      metadata: { content_type: block.content_type, type_label: block.type_label, answer_to: block.answer_to } })),
  }
}
function loadJson(text: string) {
  try {
    const parsed = JSON.parse(text)
    if (!Array.isArray(parsed.sections) || !parsed.sections.length || parsed.sections.some((section: TeacherLessonScriptSection) => !section.section_node_id || !Array.isArray(section.blocks))) throw new Error('invalid')
    data.value = parsed
    error.value = ''
    jsonDraft.value = text
  } catch {
    error.value = tr('请载入实验脚本输出的 handout.json。', 'Load handout.json produced by the experiment script.')
  }
}
async function loadFile(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (file) loadJson(await file.text())
}
</script>

<style scoped>
.preview-shell{min-height:100vh;background:#f5f6fb;color:#2a3650;font-family:Inter,"Microsoft YaHei",sans-serif}
.preview-topbar{height:76px;position:sticky;top:0;z-index:10;display:flex;justify-content:space-between;align-items:center;padding:0 44px;background:#ffffffed;border-bottom:1px solid #e5e8f1;backdrop-filter:blur(16px)}
.preview-brand{display:flex;align-items:center;gap:12px;color:#2b3552;font-size:20px;font-weight:750;text-decoration:none}.preview-brand>span{display:grid;place-items:center;width:37px;height:37px;border-radius:11px;background:#6257cd;color:#fff;font-size:19px}.preview-brand small{margin-left:14px;padding-left:20px;border-left:1px solid #e2e5ef;color:#7b8498;font-size:15px;font-weight:400}
.preview-controls{display:flex;align-items:center;gap:10px}.preview-controls button,.preview-import,.preview-json button{min-height:39px;padding:8px 15px;border:1px solid #e1e4ee;border-radius:8px;background:#fff;color:#526078;font-size:15px;cursor:pointer}.preview-import{border-color:#6257cd;background:#6257cd;color:#fff}.preview-import input{display:none}
.preview-layout{display:grid;grid-template-columns:264px minmax(0,1fr);max-width:1490px;margin:auto}.preview-sidebar{position:sticky;top:76px;align-self:start;min-height:calc(100vh - 76px);padding:48px 28px 30px}.preview-eyebrow{color:#8684a4;font-size:13px;font-weight:750;letter-spacing:.13em}.preview-sidebar h2{margin:15px 0 12px;font-size:23px;line-height:1.6;letter-spacing:-.03em}.preview-course-tag{color:#7e879a;font-size:13px}.preview-sidebar nav{display:grid;gap:8px;margin-top:36px}.preview-sidebar nav a{display:flex;gap:12px;padding:14px 12px;border-radius:9px;background:#ebe9f8;color:#5c50b3;font-size:15px;text-decoration:none;line-height:1.6}.preview-sidebar nav a span{font-size:13px;font-weight:750}.preview-legend{margin-top:50px;padding-top:24px;border-top:1px solid #e1e5ef;display:grid;gap:14px;color:#788399;font-size:14px}.preview-legend p{font-size:12px;letter-spacing:.12em;margin:0 0 5px}.preview-legend span{display:flex;gap:10px;align-items:center}.preview-legend span:before{content:'';width:7px;height:7px;border-radius:50%;background:#137d78}.preview-legend .result:before{background:#6251c3}.preview-legend .example:before{background:#936617}.preview-legend .warning:before{background:#b34c62}
.preview-main{min-width:0;padding:45px 52px 80px 28px}.preview-hero{padding:5px 4px 28px}.preview-hero h1{margin:15px 0;color:#26324c;font-size:36px;font-weight:750;line-height:1.5;letter-spacing:-.035em}.preview-hero>p:last-child{margin:0;color:#77829a;font-size:16px;line-height:1.8}.preview-paper{background:#fff;border:1px solid #e7eaf2;border-radius:16px;box-shadow:0 12px 35px #25375806;overflow:hidden}.preview-section{padding:36px 42px 12px;scroll-margin-top:95px}.preview-section>header{display:flex;align-items:baseline;gap:16px;margin:0 0 28px;padding-bottom:22px;border-bottom:1px solid #e9ecf3}.preview-section>header span{font-size:15px;color:#9289c1;font-weight:750}.preview-section h2{margin:0;font-size:25px;color:#293650;font-weight:720}.preview-json{margin-bottom:22px;color:#7c869c;font-size:14px}.preview-json summary{cursor:pointer}.preview-json textarea{width:100%;margin:15px 0 10px;padding:16px;border:1px solid #d8ddea;border-radius:10px;background:#fff;font-size:15px}.preview-json p{color:#b34c62}.preview-paper :deep(.course-content-block){margin-bottom:0}.preview-paper :deep(.course-content-block[data-content-block-type="summary"]){border-top:0;padding-top:0}
.preview-failure,.preview-fragment{padding:18px 22px;margin-bottom:24px;border:1px solid #ead0a8;border-radius:10px;background:#fffbf3;color:#8e6228;font-size:15px;line-height:1.7}.preview-fragment h3{margin:0 0 15px;font-size:17px}
</style>
