<template>
  <section class="companion-studio">
    <div v-if="loading && !templates.length && !documents.length" class="studio-state" role="status"><LoaderCircle :size="20" class="spin" />{{ t('companionDocuments.loading', '正在读取配套文档模板…') }}</div>
    <div v-else-if="loadError && !templates.length && !documents.length" class="studio-state studio-state--error" role="alert"><TriangleAlert :size="21" /><strong>{{ t('companionDocuments.loadFailed', '配套文档读取失败') }}</strong><span>{{ loadError }}</span><button type="button" @click="loadStudio">{{ t('common.retry', '重试') }}</button></div>
    <p v-else-if="loadError" class="studio-inline-error" role="alert"><TriangleAlert :size="15" />{{ loadError }}<button type="button" @click="loadStudio">{{ t('common.retry', '重试') }}</button></p>

    <template v-else-if="!activeTemplate">
      <div class="template-summary"><span>{{ t('companionDocuments.availableTemplates', '可用模板') }}</span><strong>{{ templates.length }}</strong></div>
      <div class="template-grid">
        <button v-for="template in templates" :key="template.template_id" type="button" class="template-card" @click="openTemplate(template)">
          <span class="template-icon"><component :is="templateIcon(template.document_type)" :size="22" /></span>
          <span class="template-copy"><strong>{{ templateName(template) }}</strong></span>
          <span class="template-meta"><small>{{ template.institution }}</small><b :data-ready="Boolean(documentFor(template.template_id))">{{ documentFor(template.template_id) ? t('companionDocuments.continueEditing', '继续编辑') : t('companionDocuments.create', '创建') }}</b></span>
          <ChevronRight :size="18" />
        </button>
      </div>
      <p v-if="!templates.length" class="studio-empty">{{ t('companionDocuments.noTemplates', '当前没有可用的学校模板。') }}</p>
    </template>

    <template v-else-if="mode === 'preview' && activeDocument">
      <header class="document-toolbar">
        <button type="button" class="back-action" @click="backToTemplates"><ArrowLeft :size="16" />{{ t('companionDocuments.allTemplates', '全部模板') }}</button>
        <div><strong>{{ activeDocument.title }}</strong><small>{{ t('companionDocuments.savedRevision', '已保存为正式文件 · 第 {revision} 版').replace('{revision}', String(activeDocument.revision_number)) }}</small></div>
        <div class="toolbar-actions"><button type="button" @click="mode = 'edit'"><Pencil :size="15" />{{ t('common.edit', '编辑') }}</button><button type="button" class="primary-action" @click="exportDocument(activeDocument)"><Download :size="15" />{{ t('courseFiles.exportFile', '导出') }}</button></div>
      </header>
      <p v-if="submitError" class="submit-error submit-error--preview" role="alert">{{ submitError }}</p>
      <article class="document-preview"><MarkdownRenderer :content="activeDocument.rendered_markdown" /></article>
    </template>

    <form v-else class="document-form" @submit.prevent="generateDocument">
      <header class="document-toolbar">
        <button type="button" class="back-action" @click="backToTemplates"><ArrowLeft :size="16" />{{ t('companionDocuments.allTemplates', '全部模板') }}</button>
        <div><strong>{{ templateName(activeTemplate) }}</strong><small>{{ activeTemplate.institution }} · {{ t('companionDocuments.formalTemplate', '正式文件模板') }}</small></div>
        <button v-if="activeDocument" type="button" @click="mode = 'preview'"><Eye :size="15" />{{ t('common.preview', '预览') }}</button>
      </header>

      <div class="form-body">
        <div class="field-grid field-grid--identity">
          <label class="field field--wide"><span>{{ t('companionDocuments.fields.title', '文档标题') }} <b>*</b></span><input v-model.trim="draftInputs.title" required /></label>
          <label class="field"><span>{{ t('companionDocuments.fields.courseName', '课程名称') }} <b>*</b></span><input v-model.trim="draftInputs.course_name" required /></label>
          <label class="field"><span>{{ t('companionDocuments.fields.teacherName', '任课教师') }}</span><input v-model.trim="draftInputs.teacher_name" :placeholder="t('companionDocuments.fields.teacherPlaceholder', '可稍后填写或签字')" /></label>
        </div>

        <template v-if="activeTemplate.form_kind === 'grading_rubric'">
          <section class="form-section">
            <header><strong>{{ t('companionDocuments.rubric.components', '考核项目') }}</strong><span class="weight-total" :data-valid="rubricTotal === 100">{{ rubricTotal }}%</span></header>
            <div class="rubric-columns" aria-hidden="true">
              <span />
              <span>{{ t('companionDocuments.rubric.name', '项目名称') }}</span>
              <span>{{ t('companionDocuments.rubric.weight', '比例') }}</span>
              <span>{{ t('companionDocuments.rubric.scope', '评价对象') }}</span>
              <span />
            </div>
            <div class="rubric-list">
              <article v-for="(component, index) in rubricComponents" :key="component.component_id || index" class="rubric-row">
                <div class="rubric-heading">
                  <span class="rubric-index">{{ index + 1 }}</span>
                  <input v-model.trim="component.name" class="rubric-input" required :aria-label="t('companionDocuments.rubric.name', '项目名称')" />
                  <label class="weight-field"><input v-model.number="component.weight" type="number" min="0.01" max="100" step="0.01" required :aria-label="t('companionDocuments.rubric.weight', '比例')" /><b>%</b></label>
                  <input v-model.trim="component.scope" class="rubric-input" :aria-label="t('companionDocuments.rubric.scope', '评价对象')" />
                  <button type="button" :aria-label="t('common.delete', '删除')" :disabled="rubricComponents.length <= 1" @click="removeRubricComponent(index)"><Trash2 :size="15" /></button>
                </div>
                <label class="rubric-details"><span>{{ t('companionDocuments.rubric.details', '评分项目与提交物') }}</span><textarea v-model.trim="component.details" v-autogrow rows="1" /></label>
              </article>
            </div>
            <button type="button" class="add-row" @click="addRubricComponent"><Plus :size="15" />{{ t('companionDocuments.rubric.addComponent', '添加考核项目') }}</button>
          </section>
          <label class="field"><span>{{ t('companionDocuments.rubric.specialRules', '补交与特殊情况') }}</span><textarea v-model.trim="draftInputs.special_rules" rows="4" /></label>
          <label class="field date-field"><span>{{ t('companionDocuments.fields.effectiveDate', '落款日期') }}</span><input v-model.trim="draftInputs.effective_date" :placeholder="t('companionDocuments.fields.datePlaceholder', '例如：2026年9月1日')" /></label>
        </template>

        <template v-else-if="activeTemplate.form_kind === 'material_checklist'">
          <div class="field-grid">
            <label class="field"><span>{{ t('companionDocuments.fields.collegeName', '学院名称') }}</span><input v-model.trim="draftInputs.college_name" /></label>
            <label class="field"><span>{{ t('companionDocuments.fields.courseCode', '课程代码') }}</span><input v-model.trim="draftInputs.course_code" /></label>
            <label class="field"><span>{{ t('companionDocuments.fields.academicYear', '开课学年') }}</span><input v-model.trim="draftInputs.academic_year" /></label>
            <label class="field"><span>{{ t('companionDocuments.fields.term', '学期') }}</span><input v-model.trim="draftInputs.term" /></label>
            <label class="field"><span>{{ t('companionDocuments.fields.examTime', '考试时间') }}</span><input v-model.trim="draftInputs.exam_time" /></label>
            <label class="field"><span>{{ t('companionDocuments.fields.courseType', '课程类型') }}</span><input v-model.trim="draftInputs.course_type" /></label>
          </div>
          <section class="form-section checklist-section">
            <header><strong>{{ t('companionDocuments.checklist.items', '材料清单') }}</strong><span>{{ checklistCompleted }}/{{ checklistItems.length }}</span></header>
            <label v-for="(item, index) in checklistItems" :key="item.item_id" class="checklist-row">
              <input v-model="item.completed" type="checkbox" />
              <span><b>{{ index + 1 }}</b>{{ checklistLabel(item.item_id) }}</span>
              <input v-model.trim="item.notes" type="text" :placeholder="t('companionDocuments.checklist.notePlaceholder', '备注（选填）')" />
            </label>
          </section>
          <label class="field date-field"><span>{{ t('companionDocuments.fields.submittedAt', '递交日期') }}</span><input v-model.trim="draftInputs.submitted_at" :placeholder="t('companionDocuments.fields.datePlaceholder', '例如：2026年9月1日')" /></label>
        </template>

        <p v-if="submitError" class="submit-error" role="alert">{{ submitError }}</p>
      </div>
      <footer class="form-footer"><button class="primary-action" type="submit" :disabled="saving || !canSubmit"><LoaderCircle v-if="saving" :size="16" class="spin" /><Sparkles v-else :size="16" />{{ saving ? t('companionDocuments.saving', '正在生成…') : t('companionDocuments.generateAndSave', '生成并保存') }}</button></footer>
    </form>
  </section>
</template>

<script setup lang="ts">
import { computed, markRaw, ref, watch } from 'vue'
import { ArrowLeft, CheckSquare2, ChevronRight, ClipboardCheck, Download, Eye, FileCheck2, LoaderCircle, Pencil, Plus, Sparkles, Trash2, TriangleAlert } from 'lucide-vue-next'
import { activeLocale, t } from '../shared/i18n'
import http, { teacherReadRequestConfig, teacherRequestConfig } from '../utils/http'
import MarkdownRenderer from './MarkdownRenderer.vue'

type Template = { template_id: string; template_version: number; document_type: string; name: string; name_en: string; description: string; description_en: string; institution: string; form_kind: 'grading_rubric' | 'material_checklist'; default_inputs: Record<string, any> }
type CompanionDocument = { document_id: string; template_id: string; document_type: string; title: string; status: string; revision_id: string; revision_number: number; inputs: Record<string, any>; rendered_markdown: string; updated_at: string }
type RubricComponent = { component_id: string; name: string; weight: number; scope: string; details: string }
type ChecklistItem = { item_id: string; completed: boolean; notes: string }

const props = defineProps<{ courseId: string }>()
const emit = defineEmits<{ (event: 'saved', document: CompanionDocument): void }>()
const templates = ref<Template[]>([])
const documents = ref<CompanionDocument[]>([])
const activeTemplateId = ref('')
const draftInputs = ref<Record<string, any>>({})
const mode = ref<'edit' | 'preview'>('edit')
const loading = ref(false)
const saving = ref(false)
const loadError = ref('')
const submitError = ref('')
const activeTemplate = computed(() => templates.value.find(item => item.template_id === activeTemplateId.value))
const activeDocument = computed(() => activeTemplate.value ? documentFor(activeTemplate.value.template_id) : undefined)
const rubricComponents = computed<RubricComponent[]>(() => Array.isArray(draftInputs.value.components) ? draftInputs.value.components : [])
const checklistItems = computed<ChecklistItem[]>(() => Array.isArray(draftInputs.value.items) ? draftInputs.value.items : [])
const rubricTotal = computed(() => Math.round(rubricComponents.value.reduce((sum, item) => sum + Number(item.weight || 0), 0) * 100) / 100)
const checklistCompleted = computed(() => checklistItems.value.filter(item => item.completed).length)
const canSubmit = computed(() => Boolean(String(draftInputs.value.title || '').trim() && String(draftInputs.value.course_name || '').trim() && (activeTemplate.value?.form_kind !== 'grading_rubric' || rubricTotal.value === 100)))

const checklistLabels: Record<string, string> = {
  actual_papers: '实考试卷按实际份数上交存档',
  paper_a: '空白试卷A卷、A卷标准答案（含参考答案、评分细则）各一份上交存档',
  paper_b: '空白试卷B卷、B卷标准答案（含参考答案、评分细则）各一份上交存档；多个平行班由出卷老师提供',
  grade_sheets: '含平时成绩、期末成绩和总评成绩的成绩单2份，签名后上交存档',
  exam_analysis: '试卷分析填写规范完整，签名后上交存档',
  teaching_calendar: '从教务系统导出本学期教学日历，打印上交存档',
  grading_rubric: '课程成绩评定细则完整，与教学大纲一致，签名上交存档',
  grade_breakdown: '课程成绩明细汇总表与成绩评定细则对应',
  syllabus_alignment: '考核方式、成绩评定方式与课程教学大纲实际情况相符',
  paper_duplication: '近三年A卷重复率不超过30%，当年A卷、B卷不重复，卷首课程信息完整',
  marking_signature: '考生实考试卷卷首评阅人签全名，卷首和卷面标明各题得分',
  total_signature: '考生实考试卷卷首登分表总分处由任课老师签全名',
  room_records: '考场情况记录表、考场签到表上交存档',
}

const resizeTextarea = (element: HTMLTextAreaElement) => {
  element.style.height = 'auto'
  element.style.height = `${element.scrollHeight}px`
}
const vAutogrow = {
  mounted: resizeTextarea,
  updated: resizeTextarea,
}

function templateName(template: Template) { return activeLocale.value === 'en' ? template.name_en : template.name }
function templateIcon(type: string) { return markRaw(type === 'grading_rubric' ? ClipboardCheck : type === 'course_material_checklist' ? CheckSquare2 : FileCheck2) }
function documentFor(templateId: string) { return documents.value.find(item => item.template_id === templateId) }
function checklistLabel(itemId: string) { return t(`companionDocuments.checklist.labels.${itemId}`, checklistLabels[itemId] || itemId) }
function clone<T>(value: T): T { return JSON.parse(JSON.stringify(value)) as T }

function openTemplate(template: Template) {
  activeTemplateId.value = template.template_id
  const document = documentFor(template.template_id)
  draftInputs.value = clone(document?.inputs || template.default_inputs || {})
  mode.value = 'edit'
  submitError.value = ''
}

function backToTemplates() { activeTemplateId.value = ''; draftInputs.value = {}; mode.value = 'edit'; submitError.value = '' }
function addRubricComponent() { rubricComponents.value.push({ component_id: `component_${Date.now()}`, name: '', weight: 0, scope: '', details: '' }) }
function removeRubricComponent(index: number) { if (rubricComponents.value.length > 1) rubricComponents.value.splice(index, 1) }

async function loadStudio() {
  if (!props.courseId) return
  loading.value = true; loadError.value = ''
  try {
    const response = await http.get(`/api/courses/${props.courseId}/companion-documents`, teacherReadRequestConfig({ silentError: true }))
    templates.value = Array.isArray(response.data?.templates) ? response.data.templates : []
    documents.value = Array.isArray(response.data?.documents) ? response.data.documents : []
    if (activeTemplate.value) openTemplate(activeTemplate.value)
  } catch (error: any) { loadError.value = String(error?.response?.data?.detail || error?.message || t('companionDocuments.loadFailed', '配套文档读取失败')) }
  finally { loading.value = false }
}

async function generateDocument() {
  if (!activeTemplate.value || !canSubmit.value) return
  saving.value = true; submitError.value = ''
  try {
    const response = await http.post(`/api/courses/${props.courseId}/companion-documents/${activeTemplate.value.template_id}/generate`, { inputs: draftInputs.value }, teacherRequestConfig({ silentError: true }))
    const document = response.data as CompanionDocument
    documents.value = [document, ...documents.value.filter(item => item.document_id !== document.document_id)]
    draftInputs.value = clone(document.inputs)
    mode.value = 'preview'
    emit('saved', document)
  } catch (error: any) { submitError.value = String(error?.response?.data?.detail || error?.message || t('companionDocuments.generateFailed', '生成失败，请检查表单后重试。')) }
  finally { saving.value = false }
}

async function exportDocument(document: CompanionDocument) {
  try {
    const response = await http.get(`/api/courses/${props.courseId}/companion-documents/${document.document_id}/export`, teacherRequestConfig({ params: { format: 'docx' }, responseType: 'blob', silentError: true }))
    const url = URL.createObjectURL(response.data)
    const anchor = window.document.createElement('a'); anchor.href = url; anchor.download = `${document.title}.docx`; anchor.click()
    setTimeout(() => URL.revokeObjectURL(url), 100)
  } catch (error: any) { submitError.value = String(error?.response?.data?.detail || error?.message || t('companionDocuments.exportFailed', '导出失败，请稍后重试。')) }
}

watch(() => props.courseId, () => { backToTemplates(); void loadStudio() }, { immediate: true })
</script>

<style scoped>
.studio-inline-error{display:flex;align-items:center;gap:8px;margin:0 0 12px;padding:9px 11px;border-radius:8px;color:#9f1239;background:#fff1f2;font-size:12px}.studio-inline-error button{margin-left:auto;border:0;color:#4f46e5;background:transparent;font-weight:700;cursor:pointer}
.companion-studio{max-width:860px;margin:0 auto}.studio-state{min-height:280px;display:flex;align-items:center;justify-content:center;gap:9px;color:#64748b;font-size:13px}.studio-state--error{flex-direction:column;color:#b91c1c}.studio-state button,.back-action,.document-toolbar>button,.toolbar-actions button{min-height:34px;display:inline-flex;align-items:center;justify-content:center;gap:6px;padding:0 10px;border:1px solid #d7dde7;border-radius:8px;color:#475569;background:#fff;font-size:12px;font-weight:700;cursor:pointer}.template-summary{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;color:#64748b;font-size:12px}.template-summary strong{color:#334155}.template-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.template-card{min-height:104px;display:grid;grid-template-columns:44px minmax(0,1fr) auto;grid-template-rows:1fr auto;gap:6px 12px;padding:15px 16px;border:1px solid #dfe5ee;border-radius:13px;color:#475569;background:#fff;text-align:left;cursor:pointer;transition:border-color .16s ease-out,box-shadow .16s ease-out,transform .16s ease-out}.template-card:hover{border-color:#aaaaf7;box-shadow:0 9px 22px rgba(30,41,59,.08);transform:translateY(-1px)}.template-card:focus-visible{outline:2px solid #5b57e8;outline-offset:2px}.template-icon{grid-row:1/3;width:42px;height:42px;display:grid;place-items:center;border-radius:10px;color:#4f46e5;background:#eef2ff}.template-copy{min-width:0;display:grid;align-content:start}.template-copy strong{color:#243047;font-size:14px}.template-meta{grid-column:2/3;display:flex;align-items:center;justify-content:space-between;gap:10px}.template-meta small{color:#64748b;font-size:11px}.template-meta b{color:#4f46e5;font-size:12px}.template-meta b[data-ready="true"]{color:#047857}.template-card>svg{grid-column:3;grid-row:1/3;align-self:center}.studio-empty{padding:80px 0;text-align:center;color:#64748b}.document-form,.document-preview{overflow:hidden;border:1px solid #e0e6ef;border-radius:14px;background:#fff;box-shadow:0 10px 30px rgba(30,41,59,.05)}.document-toolbar{min-height:66px;display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:center;gap:13px;padding:0 18px;border:1px solid #e0e6ef;border-radius:14px 14px 0 0;background:#fff}.document-form>.document-toolbar{border:0;border-bottom:1px solid #e7ebf2;border-radius:0}.document-toolbar>div:not(.toolbar-actions){min-width:0;display:grid;gap:3px}.document-toolbar strong{overflow:hidden;color:#263147;font-size:13px;text-overflow:ellipsis;white-space:nowrap}.document-toolbar small{color:#64748b;font-size:11px}.toolbar-actions{display:flex;gap:7px}.toolbar-actions .primary-action,.primary-action{border-color:#514bdc;color:#fff;background:#514bdc}.document-preview{max-height:calc(100vh - 250px);overflow:auto;padding:24px 30px 44px;border-top:0;border-radius:0 0 14px 14px}.form-body{display:grid;gap:22px;padding:24px 26px 28px}.field-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:15px}.field-grid--identity{grid-template-columns:1fr 1fr}.field--wide{grid-column:1/-1}.field{display:grid;gap:7px}.field>span{color:#334155;font-size:12px;font-weight:700}.field b{color:#dc2626}.field input,.field textarea,.rubric-heading input,.checklist-row>input[type="text"]{width:100%;min-height:40px;padding:9px 10px;border:1px solid #cfd7e3;border-radius:8px;outline:0;color:#172033;background:#fff;font:inherit;font-size:12px}.field textarea{resize:vertical;line-height:1.55}.field input:focus,.field textarea:focus,.rubric-heading input:focus,.checklist-row>input[type="text"]:focus{border-color:#5b57e8;box-shadow:0 0 0 3px rgba(91,87,232,.11)}.date-field{max-width:300px}.form-section{display:grid;gap:12px;padding-top:2px}.form-section>header{display:flex;align-items:flex-end;justify-content:space-between;gap:16px}.form-section>header>div{display:grid;gap:3px}.form-section>header strong{color:#263147;font-size:14px}.weight-total{min-width:60px;padding:5px 8px;border-radius:7px;color:#b45309;background:#fff7ed;text-align:center;font-size:13px;font-weight:800}.weight-total[data-valid="true"]{color:#047857;background:#ecfdf5}.rubric-list{display:grid;gap:0}.rubric-row{display:grid;gap:11px;padding:14px 0;border-bottom:1px solid #e7ebf2}.rubric-heading{display:grid;grid-template-columns:24px minmax(140px,1fr) 98px 120px 30px;align-items:center;gap:9px}.weight-field{position:relative}.weight-field input{padding-right:25px}.weight-field b{position:absolute;right:9px;top:50%;transform:translateY(-50%);color:#64748b;font-size:11px}.rubric-heading>button{width:30px;height:40px;display:grid;place-items:center;border:0;border-radius:7px;color:#94a3b8;background:transparent;cursor:pointer}.rubric-heading>button:hover:not(:disabled){color:#b91c1c;background:#fff1f2}.rubric-heading>button:disabled{opacity:.35;cursor:not-allowed}.add-row{width:max-content;min-height:34px;display:flex;align-items:center;gap:6px;padding:0 10px;border:1px solid #d7dde7;border-radius:8px;color:#4f46e5;background:#fff;font-size:12px;font-weight:700;cursor:pointer}.checklist-section>header>span{color:#475569;font-size:12px;font-weight:800}.checklist-row{display:grid;grid-template-columns:20px minmax(0,1fr) 170px;align-items:center;gap:10px;min-height:51px;padding:7px 9px;border-bottom:1px solid #edf1f6;cursor:pointer}.checklist-row:first-of-type{border-top:1px solid #edf1f6}.checklist-row>input[type="checkbox"]{width:16px;height:16px;accent-color:#514bdc}.checklist-row>span{display:flex;align-items:flex-start;gap:8px;color:#334155;font-size:12px;line-height:1.5}.checklist-row>span b{min-width:18px;color:#64748b}.checklist-row>input[type="text"]{min-height:34px}.submit-error{margin:0;padding:10px 12px;border-radius:8px;color:#b91c1c;background:#fff1f2;font-size:12px}.form-footer{min-height:68px;display:flex;align-items:center;justify-content:flex-end;gap:16px;padding:0 26px;border-top:1px solid #e7ebf2}.primary-action{min-height:38px;display:inline-flex;align-items:center;gap:7px;padding:0 13px;border:1px solid #514bdc;border-radius:8px;font-size:12px;font-weight:750;cursor:pointer;box-shadow:0 7px 18px rgba(81,75,220,.14)}.primary-action:disabled{opacity:.48;cursor:not-allowed}.spin{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}
.rubric-columns{display:grid;grid-template-columns:24px minmax(140px,1fr) 98px 120px 30px;gap:9px;padding:0 0 7px;color:#64748b;font-size:11px;font-weight:700}.rubric-index{color:#64748b;text-align:center;font-size:12px;font-weight:800}.rubric-details{display:grid;gap:6px;padding-left:33px}.rubric-details>span{color:#475569;font-size:11px;font-weight:700}.rubric-details textarea{width:100%;min-height:58px;overflow:hidden;resize:none;padding:10px 12px;border:0;border-radius:8px;outline:0;color:#334155;background:#f6f8fb;font:inherit;font-size:12px;line-height:1.6;transition:background-color .16s ease-out,box-shadow .16s ease-out}.rubric-details textarea:hover{background:#f1f4f8}.rubric-details textarea:focus{background:#fff;box-shadow:inset 0 0 0 1px #7c78ee,0 0 0 3px rgba(91,87,232,.1)}
@media(max-width:960px){.template-grid{grid-template-columns:1fr}.rubric-columns{display:none}.rubric-heading{grid-template-columns:24px minmax(130px,1fr) 88px 30px}.rubric-heading>.rubric-input:last-of-type{grid-column:2/5}.rubric-heading>button{grid-column:4;grid-row:1}.rubric-details{padding-left:33px}.checklist-row{grid-template-columns:20px minmax(0,1fr)}.checklist-row>input[type="text"]{grid-column:2}}@media(max-width:720px){.field-grid,.field-grid--identity{grid-template-columns:1fr}.field--wide{grid-column:auto}.document-toolbar{grid-template-columns:auto minmax(0,1fr)}.document-toolbar>.toolbar-actions,.document-toolbar>button:last-child{grid-column:1/-1;justify-self:end;margin-bottom:10px}.form-body{padding:18px 16px}.form-footer{align-items:stretch;flex-direction:column;padding:14px 16px}.primary-action{justify-content:center}.rubric-heading{grid-template-columns:22px minmax(0,1fr) 82px 30px}.rubric-heading>.rubric-input:last-of-type{grid-column:2/5}.rubric-details{padding-left:0}.document-preview{padding-inline:18px}}
</style>
