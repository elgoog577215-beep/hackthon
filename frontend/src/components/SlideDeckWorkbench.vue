<template>
  <section class="slide-workbench" :class="{ 'is-standalone': standalone }" :data-theme="theme" :data-preview-source="previewSource">
    <header class="slide-workbench__toolbar">
      <div class="slide-workbench__identity">
        <button v-if="standalone" type="button" class="slide-workbench__back" :title="t('pptWorkspace.backToCourse', '返回课程')" @click="emit('back')">
          <ArrowLeft :size="18" />
        </button>
        <div>
          <small>{{ t('pptWorkspace.eyebrow', 'PPT 工作台') }}</small>
          <strong>{{ deckTitle }}</strong>
        </div>
        <span class="slide-workbench__status" :data-state="error ? 'error' : building ? 'building' : qualityPassed ? 'ready' : 'warning'">
          <LoaderCircle v-if="building" :size="13" class="spinning" />
          <CircleCheck v-else-if="!error && qualityPassed" :size="13" />
          <TriangleAlert v-else :size="13" />
          {{ error ? t('teachingRepresentations.slides.buildFailed', '生成失败') : building ? stageLabel : qualityPassed ? t('teachingRepresentations.slides.qualityPassed', '质量检查通过') : t('teachingRepresentations.slides.qualityReview', '需要检查') }}
        </span>
        <small class="slide-workbench__count">{{ t('teachingRepresentations.slides.demoPageCount', '{count} 页 · Demo 标准 12–18 页').replace('{count}', String(slides.length)) }}</small>
      </div>
      <div class="slide-workbench__commands">
        <div class="slide-workbench__theme" role="radiogroup" :aria-label="t('pptWorkspace.themeLabel', '课件主题')">
          <button
            type="button"
            data-theme-option="qingfeng-classroom"
            :aria-pressed="theme === 'qingfeng-classroom'"
            :class="{ active: theme === 'qingfeng-classroom' }"
            @click="theme = 'qingfeng-classroom'"
          >{{ t('pptWorkspace.themes.qingfeng', '清风课堂') }}</button>
          <button
            type="button"
            data-theme-option="academic-bluegray"
            :aria-pressed="theme === 'academic-bluegray'"
            :class="{ active: theme === 'academic-bluegray' }"
            @click="theme = 'academic-bluegray'"
          >{{ t('pptWorkspace.themes.academic', '学术蓝灰') }}</button>
        </div>
        <button v-if="standalone" type="button" :disabled="building" :title="t('teachingRepresentations.rebuild', '同步课程最新内容')" @click="emit('rebuild')">
          <RefreshCw :size="16" :class="{ spinning: building }" /><span>{{ t('pptWorkspace.sync', '同步课程') }}</span>
        </button>
        <button type="button" :disabled="!activeSlide || building" :title="t('teachingRepresentations.slides.askAi', '交给 AI 老师讨论')" @click="askAi">
          <Sparkles :size="16" /><span>{{ t('teachingRepresentations.slides.askAi', '交给 AI 老师') }}</span>
        </button>
        <button type="button" :disabled="!activeSlide || building" :title="t('pptWorkspace.present', '全屏演示')" @click="openPresentation">
          <Play :size="16" /><span>{{ t('pptWorkspace.present', '全屏演示') }}</span>
        </button>
        <button type="button" class="slide-workbench__export" :disabled="exportDisabled" :title="exportTitle" @click="downloadSlides">
          <LoaderCircle v-if="exportBusy" :size="16" class="spinning" />
          <Download v-else :size="16" /><span>{{ t('teachingRepresentations.exportPptx', '导出 PPTX') }}</span>
        </button>
      </div>
      <div v-if="building" class="slide-workbench__progress" role="progressbar" :aria-valuenow="progress" aria-valuemin="0" aria-valuemax="100">
        <i :style="{ width: `${progress}%` }"></i>
      </div>
    </header>

    <div class="slide-workbench__body">
      <aside class="slide-thumbnails" :aria-label="t('teachingRepresentations.slides.pageList', '幻灯片页列表')">
        <button
          v-for="(slide, index) in slides"
          :key="slide.unit_id"
          type="button"
          :class="{ active: slide.unit_id === activeUnitId, stale: staleUnitIds.includes(slide.unit_id) }"
          @click="selectSlide(slide.unit_id)"
        >
          <span>{{ index + 1 }}</span>
          <div class="slide-thumbnail" :data-layout="slide.layout">
            <i></i>
            <strong>{{ slide.title }}</strong>
            <small>{{ layoutLabel(slide.layout) }}</small>
          </div>
        </button>
        <div v-if="building" class="slide-thumbnails__generating">
          <LoaderCircle :size="15" class="spinning" />
          <span>{{ t('teachingRepresentations.slides.generatingPage', '正在生成第 {count} 页').replace('{count}', String(slides.length + 1)) }}</span>
        </div>
      </aside>

      <main class="slide-stage">
        <SlideCanvas
          v-if="activeSlide"
          :slide="activeSlide"
          :page-number="activeIndex + 1"
          :page-count="slides.length"
          :deck-title="deckTitle"
          :theme="theme"
        />
        <div v-else class="slide-stage__empty">
          <LoaderCircle v-if="building" :size="24" class="spinning" />
          <Presentation v-else :size="24" />
          <span>{{ building ? stageLabel : t('teachingRepresentations.slides.noSlides', '还没有可预览的页面') }}</span>
        </div>
      </main>

      <aside class="slide-inspector">
        <section v-if="error && previewSource === 'draft' && slides.length" class="slide-workbench__failed-preview">
          <header>
            <span><TriangleAlert :size="14" />{{ t('pptWorkspace.failedPreview', '未发布问题预览') }}</span>
            <b>{{ qualityIssues.length }}</b>
          </header>
          <p>{{ t('pptWorkspace.failedPreviewHelp', '这是本次构建的未发布页面；修复以下问题后再同步课程。') }}</p>
          <ol v-if="qualityIssues.length">
            <li v-for="issue in qualityIssues" :key="issue.key" :data-severity="issue.severity">
              <div>
                <span>{{ issue.slide }}</span>
                <i>{{ layoutLabel(issue.layout) }}</i>
                <code>{{ issue.code }}</code>
              </div>
              <strong>{{ issue.message }}</strong>
              <small>{{ issue.suggestion }}</small>
            </li>
          </ol>
          <small v-else>{{ t('pptWorkspace.legacyQualityFallback', '后端未返回逐页问题，请检查本次预览后重试。') }}</small>
        </section>
        <section v-else-if="error && previewSource === 'published'" class="slide-inspector__receipt" data-state="failed_using_last_available">
          <TriangleAlert :size="15" />
          <div><strong>{{ t('pptWorkspace.publishedFailureFallback', '本次生成失败，当前展示上一可用版本') }}</strong></div>
        </section>
        <template v-if="activeSlide">
          <section>
            <header><span>{{ t('teachingRepresentations.slides.pageQuality', '本页质量') }}</span><b :data-passed="slideQualityPassed">{{ slideQualityPassed ? t('teachingRepresentations.slides.passed', '通过') : t('teachingRepresentations.slides.review', '检查') }}</b></header>
            <dl>
              <div><dt>{{ t('teachingRepresentations.slides.layout', '版式') }}</dt><dd>{{ layoutLabel(activeSlide.layout) }}</dd></div>
              <div><dt>{{ t('teachingRepresentations.slides.purpose', '教学作用') }}</dt><dd>{{ purposeLabel(activeSlide.slide_purpose) }}</dd></div>
              <div><dt>{{ t('teachingRepresentations.slides.textLoad', '文字负载') }}</dt><dd>{{ activeSlide.quality?.character_count || 0 }}</dd></div>
            </dl>
          </section>

          <section>
            <header><span>{{ t('teachingRepresentations.slides.source', '同源依据') }}</span><b>{{ sourceCount }}</b></header>
            <div class="slide-inspector__refs">
              <span v-for="label in activeSlide.knowledge_labels || []" :key="label">{{ label }}</span>
              <span v-for="label in activeSlide.ability_labels || []" :key="label" data-kind="ability">{{ label }}</span>
              <small v-if="!sourceCount">{{ t('teachingRepresentations.slides.noSource', '等待来源绑定') }}</small>
            </div>
            <p v-if="activeSlide.misconception_refs?.length"><TriangleAlert :size="13" />{{ t('teachingRepresentations.slides.misconceptionCount', '{count} 个易错点').replace('{count}', String(activeSlide.misconception_refs.length)) }}</p>
            <p v-if="activeSlide.practice_task_ids?.length"><ClipboardCheck :size="13" />{{ t('teachingRepresentations.slides.practiceCount', '{count} 道正式题目').replace('{count}', String(activeSlide.practice_task_ids.length)) }}</p>
          </section>

          <section class="slide-inspector__edit">
            <header><span>{{ t('teachingRepresentations.slides.pageEdit', '页面修改') }}</span><Pencil :size="14" /></header>
            <label>
              <span>{{ t('teachingRepresentations.slides.editField', '修改内容') }}</span>
              <select v-model="editField" :disabled="building" @change="resetEdit">
                <option value="title">{{ t('teachingRepresentations.slides.fields.title', '标题') }}</option>
                <option value="subtitle">{{ t('teachingRepresentations.slides.fields.subtitle', '副标题') }}</option>
                <option value="key_message">{{ t('teachingRepresentations.slides.fields.keyMessage', '核心信息') }}</option>
                <option value="speaker_notes">{{ t('teachingRepresentations.slides.fields.notes', '讲者备注') }}</option>
                <option value="layout">{{ t('teachingRepresentations.slides.fields.layout', '版式') }}</option>
              </select>
            </label>
            <label>
              <span>{{ t('teachingRepresentations.slides.updatedValue', '修改后') }}</span>
              <select v-if="editField === 'layout'" v-model="editValue" :disabled="building">
                <option v-for="layout in layouts" :key="layout" :value="layout">{{ layoutLabel(layout) }}</option>
              </select>
              <textarea v-else v-model="editValue" :disabled="building" rows="4"></textarea>
            </label>
            <div v-if="editPreview" class="slide-inspector__impact" data-state="affected">
              <strong>{{ classificationLabel(editPreview.classification) }}</strong>
              <div class="impact-flow">
                <div class="impact-flow__origin">
                  <small>{{ t('teachingRepresentations.impactOrigin', 'PPT 学习目标变化') }}</small>
                  <b>{{ editPreview.semantic_change?.summary || editPreview.reason }}</b>
                </div>
                <i></i>
                <div v-if="editPreview.impact?.affected_representations?.length" class="impact-flow__targets">
                  <span v-for="item in editPreview.impact.affected_representations" :key="item.representation_id">
                    <b>{{ representationLabel(item.representation_type) }}</b>
                    <small>{{ t('teachingRepresentations.affectedUnits', '{count} 处需联动').replace('{count}', String(item.unit_ids?.length || 0)) }}</small>
                  </span>
                </div>
              </div>
              <small>{{ t('teachingRepresentations.preciseImpactSummary', '预计联动 {affected} 处，保持 {unaffected} 处不变')
                .replace('{affected}', String(editPreview.impact?.affected_unit_count || 0))
                .replace('{unaffected}', String(editPreview.impact?.unaffected_unit_count || 0)) }}</small>
              <p class="protected"><ShieldCheck :size="12" />{{ t('teachingRepresentations.unrelatedProtected', '无来源关系的内容不会修改') }}</p>
              <button type="button" class="impact-open" @click="impactDialogOpen = true">
                <GitBranch :size="13" />{{ t('teachingRepresentations.impactDialog.open', '展开完整影响图') }}
              </button>
            </div>
            <div v-else-if="analysisQueued || (editBusy && changed)" class="slide-inspector__analyzing">
              <LoaderCircle :size="14" class="spinning" />
              <span>{{ t('teachingRepresentations.impactDialog.analyzing', '正在理解这次修改改变了什么教学目标…') }}</span>
            </div>
            <div v-if="pendingInlineItem" class="slide-inspector__confirmation" data-state="pending">
              <strong><Sparkles :size="13" />{{ t('teachingRepresentations.confirmCourseChange', '确认课程语义变化') }}</strong>
              <div class="objective-diff">
                <span>{{ proposalContent(pendingInlineItem.before) }}</span>
                <i>→</i>
                <b>{{ proposalContent(pendingInlineItem.after) }}</b>
              </div>
              <p>{{ pendingInlineItem.reason }}</p>
              <div class="slide-inspector__edit-actions">
                <button type="button" class="semantic" :disabled="editBusy" @click="confirmInlineChange"><CircleCheck :size="13" />{{ t('teachingRepresentations.confirmSync', '确认并同步相关内容') }}</button>
                <button type="button" :disabled="editBusy" @click="rejectInlineChange"><X :size="13" />{{ t('teachingRepresentations.rejectChange', '不应用') }}</button>
              </div>
            </div>
            <div v-if="syncReceipt" class="slide-inspector__receipt" :data-state="syncReceipt.status">
              <CircleCheck v-if="syncReceipt.status === 'synchronized'" :size="15" />
              <TriangleAlert v-else :size="15" />
              <div>
                <strong>{{ syncReceipt.status === 'synchronized'
                  ? t('teachingRepresentations.syncComplete', '课程同源同步完成')
                  : t('teachingRepresentations.syncFallback', '课程已更新，教学资源暂用上一版') }}</strong>
                <p v-if="syncReceipt.status === 'synchronized' && hasDetailedSyncReceipt">{{ t('teachingRepresentations.syncDetailedCounts', '{changed} 项实际更新，{verified} 项仅校验，{reused} 项确认无需处理')
                  .replace('{changed}', String(syncChangedCount))
                  .replace('{verified}', String(syncVerifiedCount))
                  .replace('{reused}', String(syncReusedCount)) }}</p>
                <p v-else-if="syncReceipt.status === 'synchronized'">{{ t('teachingRepresentations.syncCounts', '{rebuilt} 处已更新，{reused} 处确认无需修改')
                  .replace('{rebuilt}', String(syncRebuiltCount))
                  .replace('{reused}', String(syncReusedCount)) }}</p>
                <ul v-if="syncReceipt.status === 'synchronized' && hasDetailedSyncReceipt">
                  <li v-for="item in syncReceipt.changes" :key="item.representation_type">
                    <span>{{ representationLabel(item.representation_type) }}</span>
                    <b>{{ t('teachingRepresentations.syncGroupCounts', '{changed} 改 · {verified} 验')
                      .replace('{changed}', String(syncGroupCount(item, 'content_changed')))
                      .replace('{verified}', String(syncGroupCount(item, 'source_verified'))) }}</b>
                  </li>
                </ul>
                <ul v-else-if="syncReceipt.status === 'synchronized' && syncReceipt.rebuilt?.length">
                  <li v-for="item in syncReceipt.rebuilt" :key="item.representation_type">
                    <span>{{ representationLabel(item.representation_type) }}</span>
                    <b>{{ item.rebuilt_unit_ids?.length || 0 }} / {{ (item.rebuilt_unit_ids?.length || 0) + (item.reused_unit_ids?.length || 0) }}</b>
                  </li>
                </ul>
              </div>
            </div>
            <div v-if="!pendingInlineItem" class="slide-inspector__edit-actions">
              <button v-if="!editPreview" type="button" :disabled="editBusy || building || !changed" @click="previewEdit(true)"><ScanSearch :size="14" />{{ t('teachingRepresentations.previewEdit', '分析影响') }}</button>
              <template v-else>
                <button type="button" :disabled="editBusy" @click="applyEdit('representation_only')">{{ t('teachingRepresentations.onlyThisPpt', '只改当前 PPT') }}</button>
                <button type="button" class="semantic" :disabled="editBusy || editField === 'layout' || editField === 'speaker_notes'" @click="applyEdit('course_semantic')">{{ t('teachingRepresentations.changeCourseMeaning', '改变课程含义并联动') }}</button>
              </template>
            </div>
            <output v-if="editResult">{{ editResult }}</output>
          </section>

          <details v-if="activeSlide.speaker_notes">
            <summary>{{ t('teachingRepresentations.slides.speakerNotes', '讲者备注') }}</summary>
            <p>{{ activeSlide.speaker_notes }}</p>
          </details>
        </template>
      </aside>
    </div>

    <TeachingImpactDialog
      :open="impactDialogOpen"
      :preview="impactPreview"
      :proposal-item="pendingInlineItem"
      :receipt="syncReceipt"
      :before-text="impactBeforeText || currentFieldValue"
      :after-text="impactAfterText || editValue"
      :busy="editBusy"
      :syncing="syncing"
      @close="closeImpactDialog"
      @choose-local="applyEdit('representation_only')"
      @propose="applyEdit('course_semantic')"
      @confirm="confirmInlineChange"
      @reject="rejectInlineChange"
    />

    <Teleport to="body">
      <div v-if="presentationOpen && activeSlide" ref="presentationSurface" class="deck-presentation" role="dialog" aria-modal="true" :aria-label="t('pptWorkspace.present', '全屏演示')">
        <header>
          <div><small>{{ t('pptWorkspace.presenting', '正在演示') }}</small><strong>{{ deckTitle }}</strong></div>
          <div>
            <button type="button" :class="{ active: presentationBlank }" :title="t('pptWorkspace.toggleBlank', '临时黑屏')" @click="presentationBlank = !presentationBlank"><Moon :size="17" /></button>
            <button type="button" :class="{ active: notesVisible }" :title="t('pptWorkspace.toggleNotes', '显示或隐藏讲稿')" @click="notesVisible = !notesVisible"><NotebookText :size="17" /></button>
            <button type="button" :title="t('pptWorkspace.exitPresentation', '退出演示')" @click="closePresentation"><X :size="18" /></button>
          </div>
        </header>
        <main v-if="!presentationBlank">
          <SlideCanvas
            :slide="activeSlide"
            :page-number="activeIndex + 1"
            :page-count="slides.length"
            :deck-title="deckTitle"
            :theme="theme"
            presenting
          />
          <aside v-if="notesVisible">
            <small>{{ t('teachingRepresentations.slides.speakerNotes', '讲者备注') }}</small>
            <p>{{ activeSlide.speaker_notes || t('pptWorkspace.noNotes', '这一页还没有讲稿。') }}</p>
          </aside>
        </main>
        <main v-else class="deck-presentation__blank" @click="presentationBlank = false">
          <Moon :size="28" />
          <span>{{ t('pptWorkspace.blankHint', '已临时黑屏 · 按 B 或点击恢复') }}</span>
        </main>
        <footer>
          <button type="button" :disabled="activeIndex <= 0" @click="goToSlide(activeIndex - 1)"><ChevronLeft :size="20" /></button>
          <span>{{ activeIndex + 1 }} <i>/</i> {{ slides.length }}</span>
          <button type="button" :disabled="activeIndex >= slides.length - 1" @click="goToSlide(activeIndex + 1)"><ChevronRight :size="20" /></button>
          <small>{{ t('pptWorkspace.shortcuts', '← → 翻页 · N 讲稿 · B 黑屏 · Esc 退出') }}</small>
          <i class="deck-presentation__progress"><b :style="{ width: `${((activeIndex + 1) / Math.max(1, slides.length)) * 100}%` }"></b></i>
        </footer>
      </div>
    </Teleport>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { ArrowLeft, ChevronLeft, ChevronRight, CircleCheck, ClipboardCheck, Download, GitBranch, LoaderCircle, Moon, NotebookText, Pencil, Play, Presentation, RefreshCw, ScanSearch, ShieldCheck, Sparkles, TriangleAlert, X } from 'lucide-vue-next'
import { t } from '../shared/i18n'
import { useChangeProposalsStore } from '../stores/changeProposals'
import { useTeachingRepresentationsStore } from '../stores/teachingRepresentations'
import type { SlideDeckPreviewSource, SlideDeckTheme } from '../stores/teachingRepresentations'
import type { ChangeProposal, ChangeProposalContent, ChangeProposalItem } from '../types/changeProposal'
import SlideCanvas from './SlideCanvas.vue'
import TeachingImpactDialog from './TeachingImpactDialog.vue'

interface SlideBlock {
  block_id: string
  type: string
  title?: string
  content?: string
  items?: string[]
  metadata?: Record<string, any>
}

interface Slide {
  unit_id: string
  layout: string
  slide_purpose: string
  eyebrow?: string
  title: string
  subtitle?: string
  key_message?: string
  speaker_notes?: string
  section_id?: string
  blocks: SlideBlock[]
  source_section_ids?: string[]
  source_block_ids?: string[]
  source_keys?: string[]
  knowledge_refs?: string[]
  ability_refs?: string[]
  misconception_refs?: string[]
  practice_task_ids?: string[]
  knowledge_labels?: string[]
  ability_labels?: string[]
  quality?: { passed?: boolean; character_count?: number; issues?: Array<Record<string, any>> }
}

const props = withDefaults(defineProps<{
  courseId: string
  representationId: string
  deckTitle: string
  slides: Slide[]
  staleUnitIds: string[]
  building: boolean
  progress: number
  stage: string
  error: string
  quality?: Record<string, any> | null
  previewSource?: SlideDeckPreviewSource
  standalone?: boolean
}>(), {
  standalone: false,
})

const emit = defineEmits<{
  (event: 'ask-ai', payload: { text: string; nodeId: string; anchor: Record<string, unknown>; prefill: string }): void
  (event: 'back' | 'rebuild'): void
}>()

const store = useTeachingRepresentationsStore()
const changeProposalsStore = useChangeProposalsStore()
const activeUnitId = ref('')
const userSelected = ref(false)
const editField = ref('title')
const editValue = ref('')
const editPreview = ref<Record<string, any> | null>(null)
const impactPreview = ref<Record<string, any> | null>(null)
const impactBeforeText = ref('')
const impactAfterText = ref('')
const editResult = ref('')
const editBusy = ref(false)
const exportBusy = ref(false)
const inlineProposal = ref<ChangeProposal | null>(null)
const syncReceipt = ref<Record<string, any> | null>(null)
const impactDialogOpen = ref(false)
const analysisQueued = ref(false)
const syncing = ref(false)
const presentationOpen = ref(false)
const notesVisible = ref(false)
const presentationBlank = ref(false)
const presentationSurface = ref<HTMLElement | null>(null)
const theme = ref<SlideDeckTheme>('qingfeng-classroom')
const layouts = ['cover', 'roadmap', 'chapter', 'objective', 'concept', 'comparison', 'process', 'code', 'misconception', 'practice', 'recap']
let autoPreviewTimer: number | undefined

const activeIndex = computed(() => Math.max(0, props.slides.findIndex(slide => slide.unit_id === activeUnitId.value)))
const activeSlide = computed(() => props.slides[activeIndex.value] || null)
const qualityPassed = computed(() => props.quality?.passed === true)
const slideQualityPassed = computed(() => activeSlide.value?.quality?.passed === true)
const previewSource = computed<SlideDeckPreviewSource>(() => (
  props.previewSource || (props.error ? 'draft' : 'published')
))
const exportDisabled = computed(() => (
  props.building || exportBusy.value || !props.representationId || previewSource.value === 'draft'
))
const exportTitle = computed(() => (
  previewSource.value === 'draft'
    ? t('pptWorkspace.draftExportDisabled', '问题草稿不可导出；同步成功后可导出 PPTX')
    : t('teachingRepresentations.exportPptx', '导出 PPTX')
))
const qualityIssues = computed(() => {
  const deckIssues = Array.isArray(props.quality?.issues) ? props.quality.issues : []
  const slideIssues = props.slides.flatMap(slide => (
    Array.isArray(slide.quality?.issues)
      ? slide.quality.issues.map(issue => ({ ...issue, __slide: slide }))
      : []
  ))
  const seen = new Set<string>()
  return [...deckIssues, ...slideIssues].flatMap((raw: Record<string, any>) => {
    const slide = String(raw.slide_id || raw.slide || raw.target || raw.__slide?.unit_id || 'deck')
    const matchingSlide = props.slides.find(item => item.unit_id === slide) || raw.__slide
    const issue = {
      key: `${raw.code || 'quality_issue'}:${slide}:${raw.message || ''}`,
      severity: String(raw.severity || 'critical'),
      code: String(raw.code || 'quality_issue'),
      message: String(raw.message || t('pptWorkspace.legacyIssueMessage', '该页未通过质量检查。')),
      suggestion: String(raw.suggestion || t('pptWorkspace.legacyIssueSuggestion', '请检查该页内容与版式后重试。')),
      slide,
      layout: String(raw.layout || matchingSlide?.layout || 'deck'),
    }
    if (seen.has(issue.key)) return []
    seen.add(issue.key)
    return [issue]
  })
})
const sourceCount = computed(() => {
  const slide = activeSlide.value
  if (!slide) return 0
  return new Set([
    ...(slide.source_section_ids || []),
    ...(slide.source_block_ids || []),
    ...(slide.source_keys || []),
    ...(slide.knowledge_refs || []),
    ...(slide.ability_refs || []),
  ]).size
})
const changed = computed(() => Boolean(activeSlide.value) && editValue.value.trim() !== currentFieldValue.value.trim())
const currentFieldValue = computed(() => String((activeSlide.value as Record<string, any> | null)?.[editField.value] || ''))
const pendingInlineItem = computed<ChangeProposalItem | null>(() => (
  inlineProposal.value?.items.find(item => item.status === 'pending') || null
))
const syncRebuiltCount = computed(() => (
  Number(syncReceipt.value?.rebuilt_unit_count)
  || (syncReceipt.value?.rebuilt || []).reduce(
    (total: number, item: Record<string, any>) => total + (item.rebuilt_unit_ids?.length || 0),
    0,
  )
))
const syncReusedCount = computed(() => (
  Number(syncReceipt.value?.reused_unit_count)
  || (syncReceipt.value?.rebuilt || []).reduce(
    (total: number, item: Record<string, any>) => total + (item.reused_unit_ids?.length || 0),
    0,
  )
))
const syncChangedCount = computed(() => (
  Number(syncReceipt.value?.changed_unit_count)
  || (syncReceipt.value?.changes || []).reduce(
    (total: number, item: Record<string, any>) => total + syncGroupCount(item, 'content_changed'),
    0,
  )
))
const syncVerifiedCount = computed(() => (
  Number(syncReceipt.value?.verified_unit_count)
  || (syncReceipt.value?.changes || []).reduce(
    (total: number, item: Record<string, any>) => total + syncGroupCount(item, 'source_verified'),
    0,
  )
))
const hasDetailedSyncReceipt = computed(() => (
  Array.isArray(syncReceipt.value?.changes) && syncReceipt.value.changes.length > 0
))
const stageLabel = computed(() => ({
  planning: t('teachingRepresentations.slides.stages.planning', '正在准备课程结构'),
  slide_plan: t('teachingRepresentations.slides.stages.slidePlan', '正在规划页面'),
  slide_build: t('teachingRepresentations.slides.stages.slideBuild', '正在生成页面'),
  quality: t('teachingRepresentations.slides.stages.quality', '正在检查质量'),
  complete: t('teachingRepresentations.slides.stages.complete', '生成完成'),
}[props.stage] || t('teachingRepresentations.slides.stages.building', '正在生成课件')))

watch(() => props.slides.map(slide => slide.unit_id), unitIds => {
  if (!unitIds.length) {
    activeUnitId.value = ''
    return
  }
  if (!unitIds.includes(activeUnitId.value)) activeUnitId.value = unitIds[0] || ''
  if (props.building && !userSelected.value) activeUnitId.value = unitIds[unitIds.length - 1] || ''
}, { immediate: true })

watch(activeSlide, initializeEdit, { immediate: true })
watch(editValue, scheduleAutomaticPreview)

onMounted(() => window.addEventListener('keydown', handlePresentationKey))
onUnmounted(() => {
  window.removeEventListener('keydown', handlePresentationKey)
  if (autoPreviewTimer) window.clearTimeout(autoPreviewTimer)
})

function selectSlide(unitId: string) {
  activeUnitId.value = unitId
  userSelected.value = true
}

function goToSlide(index: number) {
  const slide = props.slides[Math.max(0, Math.min(index, props.slides.length - 1))]
  if (slide) selectSlide(slide.unit_id)
}

async function openPresentation() {
  if (!activeSlide.value) return
  presentationOpen.value = true
  notesVisible.value = false
  presentationBlank.value = false
  await nextTick()
  await presentationSurface.value?.requestFullscreen?.().catch(() => undefined)
}

async function closePresentation() {
  presentationOpen.value = false
  presentationBlank.value = false
  if (document.fullscreenElement) await document.exitFullscreen().catch(() => undefined)
}

function handlePresentationKey(event: KeyboardEvent) {
  if (!presentationOpen.value) return
  if (event.key === 'ArrowRight' || event.key === 'PageDown' || event.key === ' ') {
    event.preventDefault()
    goToSlide(activeIndex.value + 1)
  } else if (event.key === 'ArrowLeft' || event.key === 'PageUp') {
    event.preventDefault()
    goToSlide(activeIndex.value - 1)
  } else if (event.key === 'Escape') {
    presentationOpen.value = false
  } else if (event.key.toLowerCase() === 'n') {
    notesVisible.value = !notesVisible.value
  } else if (event.key.toLowerCase() === 'b') {
    presentationBlank.value = !presentationBlank.value
  }
}

async function downloadSlides() {
  if (exportDisabled.value) return
  exportBusy.value = true
  try {
    await store.downloadSlides(props.representationId, props.deckTitle, theme.value)
  } finally {
    exportBusy.value = false
  }
}

function resetEdit() {
  if (autoPreviewTimer) window.clearTimeout(autoPreviewTimer)
  analysisQueued.value = false
  editValue.value = currentFieldValue.value
  if (syncing.value) return
  editPreview.value = null
  impactPreview.value = null
  impactBeforeText.value = ''
  impactAfterText.value = ''
  editResult.value = ''
  inlineProposal.value = null
  syncReceipt.value = null
  impactDialogOpen.value = false
}

function initializeEdit() {
  editField.value = (
    activeSlide.value?.slide_purpose === 'learning_objective'
      ? 'key_message'
      : 'title'
  )
  resetEdit()
}

function scheduleAutomaticPreview() {
  if (autoPreviewTimer) window.clearTimeout(autoPreviewTimer)
  analysisQueued.value = false
  if (changed.value && !syncing.value) {
    editPreview.value = null
    impactPreview.value = null
    impactBeforeText.value = ''
    impactAfterText.value = ''
    editResult.value = ''
    inlineProposal.value = null
    syncReceipt.value = null
    impactDialogOpen.value = false
  }
  if (
    !props.standalone
    || activeSlide.value?.slide_purpose !== 'learning_objective'
    || editField.value !== 'key_message'
    || !changed.value
    || editValue.value.trim().length < 8
  ) return
  analysisQueued.value = true
  autoPreviewTimer = window.setTimeout(() => {
    void previewEdit(true)
  }, 900)
}

async function previewEdit(openDialog = true) {
  const slide = activeSlide.value
  if (!slide) return
  if (autoPreviewTimer) window.clearTimeout(autoPreviewTimer)
  analysisQueued.value = false
  const requestedAfter = editValue.value
  editBusy.value = true
  try {
    const result = await store.previewEdit(props.representationId, {
      unit_id: slide.unit_id,
      field: editField.value,
      before: currentFieldValue.value,
      after: requestedAfter,
    })
    if (requestedAfter !== editValue.value) return
    editPreview.value = result
    impactPreview.value = result
    impactBeforeText.value = currentFieldValue.value
    impactAfterText.value = requestedAfter
    if (openDialog && result?.classification === 'semantic') impactDialogOpen.value = true
  } finally {
    editBusy.value = false
  }
}

async function applyEdit(decision: 'representation_only' | 'course_semantic') {
  const slide = activeSlide.value
  if (!slide) return
  editBusy.value = true
  try {
    const result = await store.applyEdit(props.representationId, {
      unit_id: slide.unit_id,
      field: editField.value,
      before: currentFieldValue.value,
      after: editValue.value,
      decision,
      semantic_intent: decision === 'course_semantic',
    })
    if (decision === 'course_semantic') {
      await changeProposalsStore.fetchChangeProposals(props.courseId)
      inlineProposal.value = changeProposalsStore.findProposal(result.authoring_change?.proposal_id)
        || result.authoring_change
        || null
      editResult.value = t('teachingRepresentations.courseCandidateReady', '已生成课程修改候选，请确认影响范围')
      impactDialogOpen.value = true
    } else {
      editResult.value = t('teachingRepresentations.representationSaved', '当前 PPT 已更新，课程正文保持不变')
      editPreview.value = null
      impactPreview.value = null
      impactDialogOpen.value = false
    }
  } finally {
    editBusy.value = false
  }
}

async function confirmInlineChange() {
  const proposal = inlineProposal.value
  const item = pendingInlineItem.value
  if (!proposal || !item) return
  editBusy.value = true
  syncing.value = true
  try {
    const result = await changeProposalsStore.applyItem(proposal.proposal_id, item.item_id)
    await store.load(props.courseId)
    await store.select(props.representationId)
    // Loading the rebuilt deck replaces the active slide object and schedules
    // resetEdit(). Let that reset finish before exposing the durable sync receipt.
    await nextTick()
    inlineProposal.value = null
    editPreview.value = null
    syncReceipt.value = result?.representation_sync || null
    editResult.value = t('teachingRepresentations.syncComplete', '课程同源同步完成')
    impactDialogOpen.value = true
  } finally {
    syncing.value = false
    editBusy.value = false
  }
}

async function rejectInlineChange() {
  const proposal = inlineProposal.value
  const item = pendingInlineItem.value
  if (!proposal || !item) return
  editBusy.value = true
  try {
    await changeProposalsStore.rejectItem(proposal.proposal_id, item.item_id)
    inlineProposal.value = null
    editResult.value = t('teachingRepresentations.changeRejected', '本次课程语义修改未应用')
    impactDialogOpen.value = false
  } finally {
    editBusy.value = false
  }
}

function closeImpactDialog() {
  if (!syncing.value) impactDialogOpen.value = false
}

function proposalContent(content: ChangeProposalContent) {
  if (typeof content === 'string') return content
  if (!content || typeof content !== 'object') return ''
  const value = (
    'payload' in content && content.payload ? content.payload : content
  ) as Record<string, unknown>
  return String(value.learning_objective || value.markdown || value.summary || value.title || '')
}

function representationLabel(value: string) {
  return t(`teachingRepresentations.types.${value}`, ({
    outline: '课程大纲',
    lesson_plan: '教案',
    handout: '讲义',
    practice_sheet: '理解检查',
    slide_deck: 'PPT',
  } as Record<string, string>)[value] || value)
}

function syncGroupCount(item: Record<string, any>, changeKind: string) {
  return (item.units || []).filter((unit: Record<string, any>) => unit.change_kind === changeKind).length
}

function askAi() {
  const slide = activeSlide.value
  if (!slide) return
  emit('ask-ai', {
    text: `${t('teachingRepresentations.slides.page', '幻灯片')} ${activeIndex.value + 1} · ${slide.title}\n${slide.key_message || ''}`.trim(),
    nodeId: slide.section_id || '',
    anchor: { representation_id: props.representationId, slide_unit_id: slide.unit_id },
    prefill: t('teachingRepresentations.slides.aiPrompt', '请从教学目标、知识依据和页面表达三个角度检查这一页，并给出可执行的改进建议。'),
  })
}

function layoutLabel(value: string) {
  return t(`teachingRepresentations.slides.layouts.${value}`, ({
    cover: '封面', roadmap: '路线', chapter: '章节', objective: '目标', concept: '概念', comparison: '对比', process: '过程', code: '代码', misconception: '易错', practice: '练习', recap: '小结',
  } as Record<string, string>)[value] || value)
}

function purposeLabel(value: string) {
  return t(`teachingRepresentations.slides.purposes.${value}`, value || t('teachingRepresentations.slides.purposes.teaching', '教学讲解'))
}

function classificationLabel(value: string) {
  return ({
    presentation: t('teachingRepresentations.classification.presentation', '表现修改'),
    equivalent_semantic: t('teachingRepresentations.classification.equivalent', '等义修改'),
    semantic: t('teachingRepresentations.classification.semantic', '语义修改'),
    ambiguous: t('teachingRepresentations.classification.ambiguous', '需要确认'),
  } as Record<string, string>)[value] || value
}

</script>

<style scoped>
.slide-workbench { min-width:0; min-height:0; height:100%; display:grid; grid-template-rows:58px minmax(0,1fr); background:#f7f8fc; }
.slide-workbench__toolbar { position:relative; display:flex; align-items:center; justify-content:space-between; gap:18px; padding:0 14px 0 18px; border-bottom:1px solid var(--lz-border); background:#fff; }
.slide-workbench__toolbar > div:first-child { min-width:0; display:flex; align-items:center; gap:10px; }.slide-workbench__toolbar strong { overflow:hidden; color:var(--lz-text-strong); font-size:13px; text-overflow:ellipsis; white-space:nowrap; }.slide-workbench__toolbar small { flex:none; color:var(--lz-text-muted); font-size:9px; }
.slide-workbench__status { min-height:24px; display:inline-flex; align-items:center; gap:5px; padding:0 8px; border-radius:6px; color:#047857; background:#ecfdf5; font-size:9px; font-weight:700; }.slide-workbench__status[data-state="building"] { color:#4f46e5; background:#eef2ff; }.slide-workbench__status[data-state="warning"] { color:#b45309; background:#fffbeb; }
.slide-workbench__status[data-state="error"] { color:#b42318; background:#fef3f2; }
.slide-workbench__commands { flex:none; display:flex; gap:6px; }.slide-workbench__commands button { min-height:34px; display:inline-flex; align-items:center; gap:6px; padding:0 10px; border:1px solid var(--lz-border); border-radius:7px; color:var(--lz-text-secondary); background:#fff; font-size:10px; cursor:pointer; }.slide-workbench__commands button:hover { color:var(--lz-brand-strong); border-color:#c7d2fe; background:var(--lz-brand-soft); }.slide-workbench__commands button:disabled { opacity:.45; cursor:not-allowed; }
.slide-workbench__theme { display:grid; grid-template-columns:1fr 1fr; gap:2px; padding:3px; border:1px solid var(--lz-border); border-radius:9px; background:#f3f5f8; }
.slide-workbench__commands .slide-workbench__theme button { min-height:28px; padding:0 9px; border:0; border-radius:6px; color:#697586; background:transparent; box-shadow:none; }
.slide-workbench__commands .slide-workbench__theme button.active { color:#1f4fbe; background:#fff; box-shadow:0 2px 7px rgba(32,55,86,.12); }
.slide-workbench__progress { position:absolute; inset:auto 0 -1px; height:2px; background:#eef0f8; }.slide-workbench__progress i { display:block; height:100%; background:#6d5dfb; transition:width .2s ease; }
.slide-workbench__body { min-width:0; min-height:0; display:grid; grid-template-columns:176px minmax(430px,1fr) 236px; }
.slide-thumbnails { min-height:0; overflow:auto; padding:10px 8px 18px; border-right:1px solid var(--lz-border); background:#fbfcff; }.slide-thumbnails > button { width:100%; display:grid; grid-template-columns:20px minmax(0,1fr); align-items:start; gap:5px; margin:0 0 6px; padding:5px; border:1px solid transparent; border-radius:7px; color:var(--lz-text-muted); background:transparent; cursor:pointer; }.slide-thumbnails > button:hover { background:#f3f5fb; }.slide-thumbnails > button.active { border-color:#a5b4fc; color:var(--lz-brand); background:#fff; box-shadow:0 4px 12px rgba(79,70,229,.08); }.slide-thumbnails > button.stale { border-left-color:#f59e0b; }.slide-thumbnails > button > span { padding-top:3px; font:700 8px ui-monospace,monospace; text-align:center; }
.slide-thumbnail { aspect-ratio:16/9; min-width:0; overflow:hidden; display:flex; flex-direction:column; padding:8px; border:1px solid #e4e7f0; border-radius:4px; background:#fff; text-align:left; }.slide-thumbnail i { width:24px; height:2px; margin-bottom:6px; background:#6d5dfb; }.slide-thumbnail strong { display:-webkit-box; overflow:hidden; color:#27324a; font-size:7px; line-height:1.35; -webkit-box-orient:vertical; -webkit-line-clamp:2; }.slide-thumbnail small { margin-top:auto; color:#98a2b3; font-size:6px; }.slide-thumbnail[data-layout="chapter"],.slide-thumbnail[data-layout="cover"] { background:linear-gradient(90deg,#eeeafe 0 31%,#fff 31%); }.slide-thumbnail[data-layout="code"] { background:linear-gradient(90deg,#202536 0 64%,#f6f7fc 64%); }.slide-thumbnail[data-layout="code"] strong { color:#fff; }
.slide-thumbnails__generating { display:flex; align-items:center; gap:6px; padding:9px 8px; color:var(--lz-brand); font-size:8px; }
.slide-stage { min-width:0; min-height:0; overflow:auto; display:grid; place-items:center; padding:24px; background:#eef0f6; }
.slide-canvas { position:relative; width:min(100%,860px); aspect-ratio:16/9; overflow:hidden; color:#172033; background:#fff; box-shadow:0 18px 38px rgba(35,45,75,.14); container-type:inline-size; }.slide-canvas h2 { margin:0; letter-spacing:0; }.slide-canvas blockquote { margin:0; }
.slide-canvas__heading { position:absolute; inset:6.8% 6% auto; }.slide-canvas__heading small { color:#6d5dfb; font-size:1.2cqw; font-weight:750; }.slide-canvas__heading h2 { margin-top:.8%; font-size:2.55cqw; line-height:1.18; }.slide-canvas__heading i { display:block; width:7%; height:3px; margin-top:1.25%; background:#6d5dfb; }
.slide-canvas__message { position:absolute; inset:23% 6% auto; min-height:9%; padding:1.6% 2.1%; border-radius:6px; color:#27324a; background:#eeeafe; font-size:1.45cqw; font-weight:700; line-height:1.35; }
.slide-canvas__blocks { position:absolute; inset:34% 6% 10%; display:grid; grid-template-columns:repeat(auto-fit,minmax(0,1fr)); gap:2%; }.slide-canvas__blocks[data-layout="objective"] { inset:26% 6% 10%; grid-template-columns:1fr 1.25fr; }.slide-canvas__blocks[data-layout="code"] { inset:25% 6% 10%; grid-template-columns:1.65fr 1fr; }.slide-canvas__blocks[data-layout="practice"],.slide-canvas__blocks[data-layout="misconception"] { inset:26% 6% 10%; grid-template-columns:1.5fr .8fr; }.slide-canvas__blocks[data-layout="roadmap"],.slide-canvas__blocks[data-layout="process"] { inset:27% 6% 12%; grid-template-columns:repeat(auto-fit,minmax(0,1fr)); }
.slide-canvas__blocks article { min-width:0; overflow:hidden; padding:6%; border:1px solid #e0e4ee; border-radius:7px; background:#fff; }.slide-canvas__blocks article > span { display:block; margin-bottom:6%; color:#6d5dfb; font-size:1.1cqw; font-weight:750; }.slide-canvas__blocks p,.slide-canvas__blocks li { margin:0; font-size:1.22cqw; line-height:1.5; }.slide-canvas__blocks ul { margin:0; padding-left:1.3em; }.slide-canvas__blocks li + li { margin-top:.55em; }.slide-canvas__blocks pre { height:100%; margin:0; overflow:hidden; color:#f5f7ff; background:#202536; white-space:pre-wrap; }.slide-canvas__blocks article[data-type="code"] { padding:4%; border-color:#202536; background:#202536; }.slide-canvas__blocks code { font:1.03cqw/1.45 ui-monospace,SFMono-Regular,monospace; }.slide-canvas__blocks article[data-type="misconception"] { border-color:#f7c6cc; background:#fdedef; }.slide-canvas__blocks article[data-type="exercise"] { border-color:#f2d2ab; background:#fff2e5; }.slide-canvas__blocks ol { display:grid; gap:4%; margin:0; padding:0; list-style:none; }.slide-canvas__blocks ol li { display:flex; gap:6%; align-items:flex-start; }.slide-canvas__blocks ol b { width:2em; height:2em; flex:none; display:grid; place-items:center; border-radius:5px; color:#fff; background:#6d5dfb; }.slide-canvas table { width:100%; border-collapse:collapse; font-size:1cqw; }.slide-canvas th,.slide-canvas td { padding:.45em .55em; border:1px solid #dfe3ee; text-align:left; }.slide-canvas th { color:#4f46e5; background:#eeeafe; }
.slide-canvas footer { position:absolute; inset:auto 6% 3.4%; display:flex; justify-content:space-between; color:#98a2b3; font-size:.8cqw; }.slide-canvas__rail { position:absolute; inset:7% auto 12% 4%; width:5px; border-radius:3px; background:#6d5dfb; }.slide-cover__brand { position:absolute; inset:8% 6% auto auto; width:8%; aspect-ratio:1; display:grid; place-items:center; border-radius:8px; color:#fff; background:#14866d; font-size:1.25cqw; font-weight:800; }.slide-cover__content { position:absolute; inset:13% 22% 12% 8%; }.slide-cover__content small,.slide-chapter__content small { color:#6d5dfb; font-size:1.35cqw; font-weight:750; }.slide-cover__content h2 { margin-top:6%; font-size:4.2cqw; line-height:1.14; }.slide-cover__content p { margin:5% 0 0; color:#667085; font-size:1.55cqw; }.slide-cover__content blockquote { margin-top:8%; padding:3% 4%; border-radius:7px; background:#f6f7fc; font-size:1.55cqw; font-weight:700; }.slide-chapter__number { position:absolute; inset:0 auto 0 0; width:31%; display:grid; place-items:center; color:#6d5dfb; background:#eeeafe; font-size:7cqw; font-weight:800; }.slide-chapter__content { position:absolute; inset:20% 8% 16% 36%; }.slide-chapter__content h2 { margin-top:6%; font-size:3.45cqw; line-height:1.18; }.slide-chapter__content blockquote { margin-top:10%; padding:4%; border:1px solid #dfe3ee; border-radius:7px; font-size:1.65cqw; font-weight:700; }
.slide-stage__empty { display:flex; flex-direction:column; align-items:center; gap:10px; color:var(--lz-text-muted); font-size:11px; }
.slide-inspector { min-height:0; overflow:auto; padding:12px; border-left:1px solid var(--lz-border); background:#fff; }.slide-inspector section { padding:4px 0 14px; border-bottom:1px solid #edf0f5; }.slide-inspector section + section { padding-top:14px; }.slide-inspector section > header { display:flex; align-items:center; justify-content:space-between; margin-bottom:10px; color:var(--lz-text-strong); font-size:10px; font-weight:750; }.slide-inspector section > header b { padding:3px 6px; border-radius:5px; color:var(--lz-text-muted); background:#f3f4f7; font-size:8px; }.slide-inspector section > header b[data-passed="true"] { color:#047857; background:#ecfdf5; }
.slide-workbench__failed-preview { margin-bottom:16px; padding:14px !important; border:1px solid #f2c6bd; border-radius:10px; background:#fff8f6; }
.slide-workbench__failed-preview > header span { display:flex; align-items:center; gap:6px; color:#a83b2f; }
.slide-workbench__failed-preview > p { margin:0 0 10px; color:#7a4a43; font-size:10px; line-height:1.55; }
.slide-workbench__failed-preview > ol { display:grid; gap:8px; margin:0; padding:0; list-style:none; }
.slide-workbench__failed-preview li { padding:10px; border-left:3px solid #d14c3e; border-radius:0 7px 7px 0; background:#fff; }
.slide-workbench__failed-preview li[data-severity="major"] { border-left-color:#d28a28; }
.slide-workbench__failed-preview li > div { display:flex; align-items:center; flex-wrap:wrap; gap:5px; }
.slide-workbench__failed-preview li span,.slide-workbench__failed-preview li i,.slide-workbench__failed-preview li code { padding:2px 5px; border-radius:4px; color:#75534f; background:#f9ece9; font-size:8px; font-style:normal; }
.slide-workbench__failed-preview li strong { display:block; margin-top:7px; color:#532f2b; font-size:10px; line-height:1.45; }
.slide-workbench__failed-preview li small,.slide-workbench__failed-preview > small { display:block; margin-top:4px; color:#795d59; font-size:9px; line-height:1.5; }
.slide-inspector dl { margin:0; }.slide-inspector dl div { display:flex; justify-content:space-between; gap:10px; padding:4px 0; font-size:9px; }.slide-inspector dt { color:var(--lz-text-muted); }.slide-inspector dd { margin:0; color:var(--lz-text-secondary); text-align:right; }.slide-inspector__refs { display:flex; flex-wrap:wrap; gap:4px; }.slide-inspector__refs span { max-width:100%; overflow:hidden; padding:4px 6px; border-radius:5px; color:#4f46e5; background:#eef2ff; font-size:8px; text-overflow:ellipsis; white-space:nowrap; }.slide-inspector__refs span[data-kind="ability"] { color:#047857; background:#ecfdf5; }.slide-inspector__refs small { color:var(--lz-text-muted); font-size:8px; }.slide-inspector section > p { display:flex; align-items:center; gap:5px; margin:8px 0 0; color:var(--lz-text-secondary); font-size:8px; }
.slide-inspector__edit label { display:block; margin-top:9px; }.slide-inspector__edit label > span { display:block; margin-bottom:5px; color:var(--lz-text-muted); font-size:8px; }.slide-inspector__edit select,.slide-inspector__edit textarea { width:100%; box-sizing:border-box; border:1px solid var(--lz-border); border-radius:6px; color:var(--lz-text); background:#fff; font:9px/1.45 inherit; outline:none; }.slide-inspector__edit select { height:30px; padding:0 7px; }.slide-inspector__edit textarea { resize:vertical; min-height:72px; padding:7px; }.slide-inspector__edit select:focus,.slide-inspector__edit textarea:focus { border-color:#818cf8; }
.slide-inspector__impact { margin-top:9px; padding:9px; border-left:3px solid #eab308; background:#fffbea; }.slide-inspector__impact > strong { color:#854d0e; font-size:9px; }.slide-inspector__impact .semantic-change { margin:4px 0 7px; color:#713f12; font-size:9px; font-weight:700; line-height:1.45; }.slide-inspector__impact ul { display:grid; gap:3px; margin:0 0 7px; padding:0; list-style:none; }.slide-inspector__impact li { display:flex; align-items:center; justify-content:space-between; gap:6px; color:#475569; font-size:8px; }.slide-inspector__impact li b { color:#a16207; font-size:8px; }.slide-inspector__impact small { color:#78716c; font-size:8px; }.slide-inspector__impact .protected { display:flex; align-items:center; gap:4px; margin:6px 0 0; color:#64748b; font-size:8px; }
.impact-flow { display:grid; justify-items:center; gap:6px; margin:7px 0; }.impact-flow__origin { width:100%; padding:7px; border:1px solid #f0d576; border-radius:6px; background:#fff; }.impact-flow__origin small,.impact-flow__origin b { display:block; }.impact-flow__origin b { margin-top:3px; color:#713f12; font-size:8px; line-height:1.4; }.impact-flow > i { width:1px; height:10px; background:#d6a80a; }.impact-flow__targets { width:100%; display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:4px; }.impact-flow__targets > span { min-width:0; padding:6px; border:1px solid #f1df9e; border-radius:5px; background:#fff; }.impact-flow__targets b,.impact-flow__targets small { display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }.impact-flow__targets b { color:#475569; font-size:8px; }.impact-flow__targets small { margin-top:2px; color:#a16207; }
.slide-inspector__impact .impact-open { width:100%; min-height:29px; display:flex; align-items:center; justify-content:center; gap:5px; margin-top:8px; border:1px solid #dfc564; border-radius:6px; color:#713f12; background:#fff; font-size:8px; font-weight:700; cursor:pointer; }
.slide-inspector__impact .impact-open:hover { border-color:#c99b09; background:#fffdf5; }
.slide-inspector__analyzing { display:flex; align-items:center; gap:7px; margin-top:9px; padding:9px; border-left:3px solid #2556d8; color:#315486; background:#eef4ff; font-size:8px; line-height:1.45; }
.slide-inspector__confirmation { margin-top:9px; padding:9px; border-left:3px solid #8b5cf6; background:#f7f3ff; }.slide-inspector__confirmation > strong { display:flex; align-items:center; gap:5px; color:#6d28d9; font-size:9px; }.objective-diff { display:grid; grid-template-columns:minmax(0,1fr) 12px minmax(0,1fr); gap:4px; margin-top:7px; color:#64748b; font-size:8px; line-height:1.4; }.objective-diff i { color:#8b5cf6; font-style:normal; }.objective-diff b { color:#4c1d95; }.slide-inspector__confirmation > p { margin:6px 0 0; color:#64748b; font-size:8px; line-height:1.45; }
.slide-inspector__receipt { display:grid; grid-template-columns:18px minmax(0,1fr); gap:6px; margin-top:9px; padding:9px; border-left:3px solid #10b981; color:#047857; background:#ecfdf5; }.slide-inspector__receipt[data-state="failed_using_last_available"] { border-left-color:#f59e0b; color:#92400e; background:#fffbeb; }.slide-inspector__receipt strong { display:block; font-size:9px; }.slide-inspector__receipt p { margin:3px 0 0; color:#64748b; font-size:8px; line-height:1.45; }
.slide-inspector__receipt ul { display:grid; gap:3px; margin:7px 0 0; padding:0; list-style:none; }.slide-inspector__receipt li { display:flex; justify-content:space-between; gap:8px; color:#526174; font-size:8px; }.slide-inspector__receipt li b { color:#047857; }
.slide-inspector__edit-actions { display:flex; flex-wrap:wrap; gap:5px; margin-top:10px; }.slide-inspector__edit-actions button { min-height:29px; display:inline-flex; align-items:center; justify-content:center; gap:4px; padding:0 8px; border:1px solid var(--lz-border); border-radius:6px; color:var(--lz-text-secondary); background:#fff; font-size:8px; cursor:pointer; }.slide-inspector__edit-actions button.semantic { color:#fff; border-color:#6366f1; background:#6366f1; }.slide-inspector__edit-actions button:disabled { opacity:.45; cursor:not-allowed; }.slide-inspector output { display:block; margin-top:8px; color:#047857; font-size:8px; }.slide-inspector details { padding:13px 0; color:var(--lz-text-secondary); font-size:9px; }.slide-inspector summary { color:var(--lz-text-strong); font-weight:700; cursor:pointer; }.slide-inspector details p { white-space:pre-line; line-height:1.55; }
.spinning { animation:slide-spin .8s linear infinite; }@keyframes slide-spin { to { transform:rotate(360deg); } }
@media (max-width:1100px) { .slide-workbench__body { grid-template-columns:148px minmax(400px,1fr) 210px; }.slide-stage { padding:16px; } }
@media (max-width:840px) { .slide-workbench { grid-template-rows:auto minmax(0,1fr); }.slide-workbench__toolbar { min-height:58px; flex-wrap:wrap; padding:8px 10px; }.slide-workbench__commands button span { display:none; }.slide-workbench__body { grid-template-columns:1fr; grid-template-rows:96px minmax(260px,1fr) auto; }.slide-thumbnails { display:flex; overflow-x:auto; border-right:0; border-bottom:1px solid var(--lz-border); }.slide-thumbnails > button { width:130px; flex:none; }.slide-stage { padding:12px; }.slide-inspector { max-height:250px; border-top:1px solid var(--lz-border); border-left:0; }.slide-inspector section { padding-right:8px; padding-left:8px; } }

/* 独立 PPT 工作台：克制的编辑部风格，优先保证长时间备课与课堂投影的可读性。 */
.slide-workbench.is-standalone {
  height:100dvh;
  grid-template-rows:74px minmax(0,1fr);
  color:#17202c;
  background:#e9edf3;
  font-family:"Avenir Next","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
}
.is-standalone .slide-workbench__toolbar {
  z-index:8;
  padding:0 20px;
  border-bottom:0;
  color:#f7f9fc;
  background:#17202c;
  box-shadow:0 8px 24px rgba(16,25,38,.18);
}
.slide-workbench__identity { min-width:0; display:flex; align-items:center; gap:12px; }
.slide-workbench__identity > div { min-width:0; display:flex; flex-direction:column; gap:2px; }
.slide-workbench__identity > div small { color:#8fa0b4; font-size:10px; font-weight:760; letter-spacing:.13em; }
.slide-workbench__identity > div strong { max-width:min(34vw,520px); overflow:hidden; color:inherit; font-size:15px; font-weight:720; text-overflow:ellipsis; white-space:nowrap; }
.slide-workbench__back {
  width:38px;
  height:38px;
  flex:0 0 38px;
  display:grid;
  place-items:center;
  padding:0;
  border:1px solid rgba(255,255,255,.12);
  border-radius:10px;
  color:#d9e2ee;
  background:rgba(255,255,255,.04);
  cursor:pointer;
}
.slide-workbench__back:hover { color:#fff; background:rgba(255,255,255,.1); }
.is-standalone .slide-workbench__status { min-height:26px; padding:0 9px; font-size:10px; }
.is-standalone .slide-workbench__count { color:#8fa0b4; font-size:10px; }
.is-standalone .slide-workbench__commands { gap:7px; }
.is-standalone .slide-workbench__theme { border-color:rgba(255,255,255,.12); background:rgba(255,255,255,.05); }
.is-standalone .slide-workbench__commands .slide-workbench__theme button { min-height:30px; color:#9cacbf; background:transparent; }
.is-standalone .slide-workbench__commands .slide-workbench__theme button.active { color:#fff; background:#304052; box-shadow:0 2px 8px rgba(0,0,0,.22); }
.is-standalone .slide-workbench__commands button {
  min-height:38px;
  padding:0 12px;
  border-color:rgba(255,255,255,.13);
  border-radius:9px;
  color:#d9e2ee;
  background:rgba(255,255,255,.045);
  font-size:11px;
  font-weight:650;
}
.is-standalone .slide-workbench__commands button:hover:not(:disabled) {
  color:#fff;
  border-color:rgba(255,255,255,.28);
  background:rgba(255,255,255,.1);
}
.is-standalone .slide-workbench__commands .slide-workbench__export {
  padding:0 15px;
  color:#fff;
  border-color:#2d66e8;
  background:#2556d8;
  box-shadow:0 7px 18px rgba(37,86,216,.28);
}
.is-standalone .slide-workbench__commands .slide-workbench__export:hover:not(:disabled) { border-color:#3973f1; background:#2d66e8; }
.is-standalone .slide-workbench__progress { background:rgba(255,255,255,.08); }
.is-standalone .slide-workbench__progress i { background:#53d4c8; }
.is-standalone .slide-workbench__body { grid-template-columns:210px minmax(560px,1fr) 312px; }
.is-standalone .slide-thumbnails {
  padding:15px 12px 28px;
  border-right:1px solid #d8dee7;
  background:#f6f7f9;
}
.is-standalone .slide-thumbnails > button {
  grid-template-columns:24px minmax(0,1fr);
  gap:7px;
  margin-bottom:9px;
  padding:7px;
  border-radius:9px;
  font-size:10px;
}
.is-standalone .slide-thumbnails > button > span { padding-top:5px; color:#7f8a9a; font-size:9px; }
.is-standalone .slide-thumbnails > button.active {
  border-color:#2556d8;
  color:#2556d8;
  box-shadow:0 8px 20px rgba(32,61,115,.13);
}
.is-standalone .slide-thumbnail { padding:10px; border-color:#d9dfe8; border-radius:5px; }
.is-standalone .slide-thumbnail i { background:#2556d8; }
.is-standalone .slide-thumbnail strong { color:#263244; font-size:8px; }
.is-standalone .slide-thumbnail small { font-size:7px; }
.is-standalone .slide-thumbnail[data-layout="chapter"],
.is-standalone .slide-thumbnail[data-layout="cover"] { background:linear-gradient(90deg,#dce7ff 0 32%,#fff 32%); }
.is-standalone .slide-stage {
  position:relative;
  padding:clamp(22px,3vw,48px);
  background-color:#e9edf3;
  background-image:radial-gradient(circle at 1px 1px,rgba(76,91,113,.12) 1px,transparent 0);
  background-size:22px 22px;
}
.is-standalone .slide-inspector {
  padding:18px 16px 28px;
  border-left:1px solid #d8dee7;
  background:#fbfcfd;
}
.is-standalone .slide-inspector section { padding:4px 0 18px; }
.is-standalone .slide-inspector section + section { padding-top:18px; }
.is-standalone .slide-inspector section > header { margin-bottom:12px; font-size:12px; }
.is-standalone .slide-inspector section > header b { padding:4px 7px; font-size:10px; }
.is-standalone .slide-inspector dl div { padding:6px 0; font-size:11px; }
.is-standalone .slide-inspector__refs { gap:6px; }
.is-standalone .slide-inspector__refs span { padding:5px 7px; border-radius:6px; color:#214cae; background:#e8efff; font-size:10px; }
.is-standalone .slide-inspector__refs small,.is-standalone .slide-inspector section > p { font-size:10px; }
.is-standalone .slide-inspector__edit label { margin-top:12px; }
.is-standalone .slide-inspector__edit label > span { margin-bottom:6px; font-size:10px; font-weight:650; }
.is-standalone .slide-inspector__edit select,
.is-standalone .slide-inspector__edit textarea {
  border-color:#d4dae4;
  border-radius:8px;
  font-size:11px;
  line-height:1.55;
}
.is-standalone .slide-inspector__edit select { height:36px; padding:0 10px; }
.is-standalone .slide-inspector__edit textarea { min-height:96px; padding:10px; }
.is-standalone .slide-inspector__edit select:focus,
.is-standalone .slide-inspector__edit textarea:focus { border-color:#2556d8; box-shadow:0 0 0 3px rgba(37,86,216,.09); }
.is-standalone .slide-inspector__impact,
.is-standalone .slide-inspector__confirmation,
.is-standalone .slide-inspector__receipt { margin-top:12px; padding:12px; border-radius:0 8px 8px 0; }
.is-standalone .slide-inspector__impact > strong,
.is-standalone .slide-inspector__confirmation > strong,
.is-standalone .slide-inspector__receipt strong { font-size:11px; }
.is-standalone .slide-inspector__impact .semantic-change,
.is-standalone .slide-inspector__impact li,
.is-standalone .slide-inspector__impact li b,
.is-standalone .slide-inspector__impact small,
.is-standalone .slide-inspector__impact .protected,
.is-standalone .objective-diff,
.is-standalone .slide-inspector__confirmation > p,
.is-standalone .slide-inspector__receipt p { font-size:10px; }
.is-standalone .impact-flow { gap:8px; margin:9px 0; }
.is-standalone .impact-flow__origin { padding:9px; border-radius:8px; }
.is-standalone .impact-flow__origin b,.is-standalone .impact-flow__targets b { font-size:10px; }
.is-standalone .impact-flow__origin small,.is-standalone .impact-flow__targets small { font-size:9px; }
.is-standalone .impact-flow__targets { gap:6px; }
.is-standalone .impact-flow__targets > span { padding:8px; border-radius:7px; }
.is-standalone .slide-inspector__impact .impact-open { min-height:34px; border-radius:8px; font-size:10px; }
.is-standalone .slide-inspector__analyzing { margin-top:12px; padding:12px; border-radius:0 8px 8px 0; font-size:10px; }
.is-standalone .slide-inspector__receipt li,.is-standalone .slide-inspector__receipt li b { font-size:10px; }
.is-standalone .slide-inspector__edit-actions { gap:7px; margin-top:12px; }
.is-standalone .slide-inspector__edit-actions button {
  min-height:34px;
  padding:0 10px;
  border-radius:8px;
  font-size:10px;
  font-weight:650;
}
.is-standalone .slide-inspector__edit-actions button.semantic { border-color:#2556d8; background:#2556d8; }
.is-standalone .slide-inspector output { margin-top:10px; font-size:10px; line-height:1.5; }
.is-standalone .slide-inspector details { padding:16px 0; font-size:11px; }

.deck-presentation {
  position:fixed;
  inset:0;
  z-index:9999;
  display:grid;
  grid-template-rows:58px minmax(0,1fr) 58px;
  color:#fff;
  background:#080e17;
  font-family:"Avenir Next","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
}
.deck-presentation > header {
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:20px;
  padding:0 22px;
  border-bottom:1px solid rgba(255,255,255,.1);
  background:rgba(8,14,23,.9);
}
.deck-presentation > header > div:first-child { min-width:0; display:flex; align-items:baseline; gap:12px; }
.deck-presentation > header small { color:#7f91a9; font-size:10px; font-weight:750; letter-spacing:.13em; }
.deck-presentation > header strong { overflow:hidden; font-size:13px; text-overflow:ellipsis; white-space:nowrap; }
.deck-presentation > header > div:last-child { display:flex; gap:7px; }
.deck-presentation button {
  width:38px;
  height:38px;
  display:grid;
  place-items:center;
  border:1px solid rgba(255,255,255,.13);
  border-radius:10px;
  color:#cbd5e1;
  background:rgba(255,255,255,.05);
  cursor:pointer;
}
.deck-presentation button:hover:not(:disabled),.deck-presentation button.active { color:#fff; background:rgba(255,255,255,.13); }
.deck-presentation button:disabled { opacity:.28; cursor:not-allowed; }
.deck-presentation > main {
  min-height:0;
  display:flex;
  align-items:center;
  justify-content:center;
  gap:20px;
  padding:20px;
}
.deck-presentation > main > aside {
  width:min(310px,24vw);
  max-height:74vh;
  overflow:auto;
  padding:18px;
  border:1px solid rgba(255,255,255,.12);
  border-radius:12px;
  color:#cbd5e1;
  background:#121b28;
}
.deck-presentation > main > aside small { color:#54d4c8; }
.deck-presentation > main > aside p { margin:10px 0 0; white-space:pre-line; font-size:13px; line-height:1.7; }
.deck-presentation > footer {
  position:relative;
  display:flex;
  align-items:center;
  justify-content:center;
  gap:18px;
  border-top:1px solid rgba(255,255,255,.08);
}
.deck-presentation > footer span { min-width:72px; text-align:center; font:700 12px/1 "Aptos Mono","SFMono-Regular",monospace; }
.deck-presentation > footer i { color:#526176; font-style:normal; }
.deck-presentation > footer small { position:absolute; right:22px; color:#66758a; font-size:9px; letter-spacing:.02em; }
.deck-presentation__progress { position:absolute; inset:auto 0 0; height:2px; display:block; background:rgba(255,255,255,.08); }
.deck-presentation__progress b { height:100%; display:block; background:#54d4c8; transition:width .28s ease; }
.deck-presentation__blank { display:grid !important; place-items:center; align-content:center; gap:13px !important; color:#657489; background:#020407; cursor:pointer; }
.deck-presentation__blank span { font-size:11px; letter-spacing:.08em; }

@media (max-width:1180px) {
  .is-standalone .slide-workbench__body { grid-template-columns:172px minmax(460px,1fr) 270px; }
  .is-standalone .slide-workbench__commands button span { display:none; }
  .is-standalone .slide-workbench__commands button { width:38px; padding:0; }
  .is-standalone .slide-workbench__commands .slide-workbench__export { width:auto; padding:0 12px; }
  .is-standalone .slide-workbench__commands .slide-workbench__export span { display:inline; }
  .is-standalone .slide-workbench__commands .slide-workbench__theme button { width:auto; padding:0 8px; }
}
@media (max-width:900px) {
  .slide-workbench.is-standalone { grid-template-rows:auto minmax(0,1fr); }
  .is-standalone .slide-workbench__toolbar { min-height:72px; padding:10px 12px; }
  .is-standalone .slide-workbench__identity > div strong { max-width:42vw; }
  .is-standalone .slide-workbench__status,.is-standalone .slide-workbench__count { display:none; }
  .is-standalone .slide-workbench__body { grid-template-columns:1fr; grid-template-rows:108px minmax(300px,1fr) minmax(250px,38vh); }
  .is-standalone .slide-thumbnails { display:flex; overflow-x:auto; padding:9px; border-right:0; border-bottom:1px solid #d8dee7; }
  .is-standalone .slide-thumbnails > button { width:145px; flex:none; margin:0 6px 0 0; }
  .is-standalone .slide-stage { padding:16px; }
  .is-standalone .slide-inspector { max-height:none; border-top:1px solid #d8dee7; border-left:0; }
}
@media (max-width:620px) {
  .is-standalone .slide-workbench__identity > div { display:none; }
  .is-standalone .slide-workbench__commands { margin-left:auto; }
  .is-standalone .slide-workbench__theme { display:none; }
  .is-standalone .slide-workbench__commands > button:nth-of-type(1),
  .is-standalone .slide-workbench__commands > button:nth-of-type(2) { display:none; }
  .deck-presentation > main { padding:8px; }
  .deck-presentation > main > aside { position:absolute; inset:auto 8px 66px; width:auto; max-height:32vh; }
  .deck-presentation > footer small { display:none; }
}
</style>
