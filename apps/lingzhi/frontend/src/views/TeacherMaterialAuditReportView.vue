<template>
  <main class="update-center-page">
    <Teleport to="#app-header-route-context">
      <div class="update-route-context">
        <button type="button" :aria-label="returnLabel" @click="backToWorkbench"><ArrowLeft :size="17" /></button>
        <FolderOpen :size="18" />
        <h1>{{ courseName || t('courseFiles.untitledCourse', '未命名课程') }}</h1>
        <small>{{ t('courseAuditUpdates.title', '审计与更新') }}</small>
      </div>
    </Teleport>

    <Teleport to="#app-header-route-actions">
      <div class="update-route-actions">
        <button type="button" @click="showHistory('version')"><History :size="15" />{{ t('courseAuditUpdates.historyRecords', '历史记录') }}</button>
        <button type="button" @click="backToWorkbench">{{ returnLabel }}<ArrowRight :size="15" /></button>
      </div>
    </Teleport>

    <section v-if="center.loading && !center.sources.length" class="center-state" role="status">
      <LoaderCircle :size="22" class="spin" />{{ t('courseAuditUpdates.loading', '正在读取材料、课程结构和历史变化…') }}
    </section>

    <section v-else class="update-center-shell" :class="{ 'has-error': Boolean(center.error || auditStore.error) }">
      <p v-if="center.error || auditStore.error" class="center-error" role="alert">
        <TriangleAlert :size="15" />{{ center.error || auditStore.error }}
      </p>

      <div class="update-center-grid" :class="{ 'is-course-change': isCourseChangeMode }">
        <aside class="source-ledger">
          <header>
            <div class="source-heading">
              <h2>{{ t('courseAuditUpdates.changeSources', '变化来源') }}</h2>
            </div>
          </header>

          <div class="source-groups">
            <section v-if="actionableCourseChanges.length || activeSource?.kind === 'new_change'" class="source-group course-change-group">
              <header><strong>{{ t('courseAuditUpdates.pendingCourseChanges', '待处理调整') }}</strong><small>{{ actionableCourseChanges.length + (activeSource?.kind === 'new_change' ? 1 : 0) }}</small></header>
              <div class="source-list">
                <button v-if="activeSource?.kind === 'new_change'" type="button" class="active" data-status="ready">
                  <span class="source-icon"><Sparkles :size="16" /></span>
                  <span><b>{{ t('courseAuditUpdates.newChangeDraft', '新的全课调整') }}</b><small>{{ t('courseAuditUpdates.newChangeDraftHint', '请在右侧描述本次调整') }}</small></span>
                  <i>{{ t('courseAuditUpdates.editing', '编辑中') }}</i>
                </button>
                <button
                  v-for="source in actionableCourseChanges"
                  :key="source.key"
                  type="button"
                  :class="{ active: center.activeSourceKey === source.key, 'no-row-status': !showCourseChangeRowStatus }"
                  :data-status="source.status"
                  @click="selectCourseChange(source.key, source.sourceId)"
                >
                  <span class="source-icon"><GitBranchPlus :size="16" /></span>
                  <span><b>{{ source.title }}</b><small>{{ courseChangeMeta(source) }}</small></span>
                  <i v-if="showCourseChangeRowStatus">{{ sourceStatusLabel(source.status) }}</i>
                </button>
              </div>
            </section>

            <section class="source-group">
              <header><strong>{{ t('courseAuditUpdates.courseMaterials', '课程材料') }}</strong><small>{{ center.materialSources.length }}</small></header>
              <div class="source-list">
                <button
                  v-for="source in center.materialSources"
                  :key="source.key"
                  type="button"
                  :class="{ active: center.activeSourceKey === source.key, 'no-row-status': !showMaterialRowStatus }"
                  :data-status="materialListStatus(source)"
                  @click="selectMaterialSource(source.key)"
                >
                  <span class="source-icon"><component :is="sourceIcon(source.material?.document_type)" :size="16" /></span>
                  <span><b>{{ source.title }}</b><small>{{ materialSourceMeta(source.material) }}</small></span>
                  <i v-if="showMaterialRowStatus">{{ materialListStatusLabel(source) }}</i>
                </button>
                <p v-if="!center.materialSources.length" class="source-empty">{{ t('courseAuditUpdates.noMaterials', '还没有课程材料') }}</p>
              </div>
            </section>
          </div>

          <footer class="source-ledger-footer">
            <input ref="fileInput" hidden type="file" multiple @change="captureFiles">
            <div ref="sourceAddMenu" class="source-add-menu" :data-open="sourceMenuOpen" @focusout="handleSourceMenuFocusout" @keydown.esc.stop="sourceMenuOpen = false">
              <button class="source-add-trigger" type="button" aria-haspopup="menu" :aria-expanded="sourceMenuOpen" @click="sourceMenuOpen = !sourceMenuOpen" @keydown.enter.prevent="sourceMenuOpen = !sourceMenuOpen" @keydown.space.prevent="sourceMenuOpen = !sourceMenuOpen">
                <Plus :size="15" />{{ t('courseAuditUpdates.addSource', '新增变化') }}<ChevronDown :size="13" />
              </button>
              <div v-if="sourceMenuOpen" role="menu">
                <button role="menuitem" type="button" :disabled="uploading || !coursePackage" @click="openMaterialPicker">
                  <LoaderCircle v-if="uploading" :size="16" class="spin" /><Upload v-else :size="16" />
                  <span><b>{{ t('courseAuditUpdates.addMaterial', '上传或替换材料') }}</b><small>{{ t('courseAuditUpdates.addMaterialHint', '重新扫描材料与生成内容的关系') }}</small></span>
                </button>
                <button role="menuitem" type="button" @click="startNewCourseChange">
                  <GitBranchPlus :size="16" />
                  <span><b>{{ t('courseAuditUpdates.addCourseChange', '提出全课调整') }}</b><small>{{ t('courseAuditUpdates.addCourseChangeHint', '扫描大纲、教案、讲义与 PPT') }}</small></span>
                </button>
              </div>
            </div>
            <small>{{ sourceOverview }}</small>
          </footer>
        </aside>

        <section v-if="isCourseChangeMode" class="course-change-surface">
          <CourseEvolutionWorkspace
            ref="evolutionWorkspaceRef"
            :key="`course-change-${courseId}`"
            :model-value="true"
            standalone
            embedded-in-center
            :course-id="courseId"
            :course-title="courseName"
            :focus-plan-id="activeCoursePlanId"
            @update:model-value="backToWorkbench"
            @plan-selected="center.selectSource(`course-change:${$event}`)"
          />
        </section>

        <template v-else>
          <section class="relationship-pane">
            <header class="content-header">
              <div class="content-heading">
                <small>{{ t('courseAuditUpdates.currentChangeSource', '当前变化来源') }}</small>
                <h2>{{ selectedMaterial?.filename || t('courseAuditUpdates.relationships', '生成关系') }}</h2>
                <p :data-state="statusTone">
                  <CircleCheckBig v-if="statusTone === 'synced'" :size="14" />
                  <LoaderCircle v-else-if="center.loading || auditStore.refreshing" :size="14" class="spin" />
                  <TriangleAlert v-else :size="14" />
                  <span>{{ statusSummary }}</span>
                  <small>{{ lastAppliedLabel }}</small>
                </p>
              </div>
              <div class="content-operations">
                <nav class="relationship-view-switch" :aria-label="t('courseAuditUpdates.relationshipView', '生成关系视图')">
                  <button type="button" :class="{ active: relationshipView === 'relation' }" @click="relationshipView = 'relation'">{{ t('courseAuditUpdates.relation', '关系') }}</button>
                  <button type="button" :class="{ active: relationshipView === 'list' }" @click="relationshipView = 'list'">{{ t('courseAuditUpdates.list', '列表') }}</button>
                </nav>
                <button class="rescan-button" type="button" :disabled="center.loading || auditStore.refreshing" @click="refreshAll">
                  <RefreshCw :size="14" :class="{ spin: center.loading || auditStore.refreshing }" />
                  {{ t('courseAuditUpdates.rescan', '重新扫描') }}
                </button>
              </div>
            </header>

            <div v-if="selectedMaterialTargets.length && relationshipView === 'relation'" class="relationship-tree">
              <section v-for="group in relationshipGroups" :key="group.key" class="relationship-group">
                <header><span /><strong>{{ group.label }}</strong><small>（{{ group.items.length }} {{ t('courseAuditUpdates.items', '项') }}）</small></header>
                <div>
                  <button
                    v-for="item in group.items"
                    :key="item.target_id"
                    type="button"
                    :class="{ active: selectedTargetId === item.target_id }"
                    :data-status="targetStatus(item)"
                    @click="selectTarget(item.target_id)"
                  >
                    <span>{{ item.title }}</span>
                    <small>{{ relationshipItemSummary(item) }}</small>
                    <b>{{ targetStatusLabel(item) }}</b>
                  </button>
                </div>
              </section>
              <button v-if="unaffectedTargetCount" class="unaffected-row" type="button" @click="showHistory('unaffected')">
                <ChevronDown :size="14" /><span><strong>{{ t('courseAuditUpdates.unaffected', '其他不受影响的内容') }}</strong><small>{{ t('courseAuditUpdates.unaffectedHint', '未引用本次变化来源，继续保持当前版本') }}</small></span><b>{{ unaffectedTargetCount }}</b>
              </button>
            </div>

            <div v-else-if="selectedMaterialTargets.length" class="relationship-table">
              <header><span>{{ t('courseAuditUpdates.generatedObject', '生成对象') }}</span><span>{{ t('courseAuditUpdates.sourceRole', '来源作用') }}</span><span>{{ t('courseAuditUpdates.structure', '结构') }}</span><span>{{ t('courseAuditUpdates.state', '状态') }}</span></header>
              <button v-for="target in selectedMaterialTargets" :key="target.target_id" type="button" :class="{ active: selectedTargetId === target.target_id }" @click="selectTarget(target.target_id)">
                <span><component :is="targetIcon(target.target_type)" :size="15" />{{ target.title }}</span><span>{{ sourceRoleForTarget(target) }}</span><span>{{ relationshipItemSummary(target) }}</span><b>{{ targetStatusLabel(target) }}</b>
              </button>
            </div>

            <div v-else class="relationship-empty">
              <Link2Off :size="24" /><strong>{{ t('courseAuditUpdates.noRelationship', '这份材料尚未进入生成关系') }}</strong><p>{{ t('courseAuditUpdates.noRelationshipHint', '先确认材料类型、版本与用途，再重新扫描。') }}</p>
            </div>
          </section>

          <aside class="detail-pane">
            <header class="pane-header">
              <h2>{{ detailTitle }}</h2>
              <span v-if="detailMode === 'detail' && selectedTarget" :data-status="targetStatus(selectedTarget)">{{ targetStatusLabel(selectedTarget) }}</span>
              <button v-else-if="detailMode !== 'detail'" class="close-detail-mode" type="button" :aria-label="t('common.close', '关闭')" @click="detailMode = 'detail'"><X :size="14" /></button>
            </header>

            <div class="detail-body">
            <template v-if="detailMode !== 'detail'">
              <section class="history-panel">
                <nav class="history-switch" :aria-label="t('courseAuditUpdates.historyRecords', '历史记录')">
                  <button type="button" :class="{ active: detailMode === 'execution' }" @click="detailMode = 'execution'">{{ t('courseAuditUpdates.executionHistory', '执行记录') }}</button>
                  <button type="button" :class="{ active: detailMode === 'version' }" @click="detailMode = 'version'">{{ t('courseAuditUpdates.versionHistory', '版本历史') }}</button>
                </nav>
                <ol v-if="historyItems.length">
                  <li v-for="item in historyItems" :key="item.key" :data-status="item.status"><span /><div><b>{{ item.title }}</b><small>{{ item.detail }}</small></div><time>{{ item.time }}</time></li>
                </ol>
                <p v-else>{{ t('courseAuditUpdates.noHistory', '还没有相关记录') }}</p>
              </section>
            </template>

            <template v-else-if="selectedMaterial && selectedTarget">
              <section class="detail-source">
                <small>{{ t('courseAuditUpdates.sourceEvidence', '来源证据') }}</small>
                <div><FileText :size="17" /><span><strong>{{ selectedMaterial.filename }}</strong><small>{{ selectedMaterial.relative_path }}</small></span><button type="button" @click="previewSource">{{ t('courseAuditUpdates.viewSource', '查看原文') }}<ArrowRight :size="13" /></button></div>
              </section>

              <section class="detail-section-selector" v-if="selectedTarget.structured_draft?.sections.length">
                <small>{{ t('courseAuditUpdates.structuredPosition', '结构化位置') }}</small>
                <select v-model="selectedSectionId">
                  <option v-for="section in selectedTarget.structured_draft.sections" :key="section.section_id" :value="section.section_id">{{ section.title }}</option>
                </select>
              </section>

              <section class="structured-preview">
                <header><strong>{{ t('courseAuditUpdates.structuredPreview', '结构化内容预览') }}</strong><small>{{ selectedSection?.blocks.length || 0 }} {{ t('courseAuditUpdates.blocks', '个内容块') }}</small></header>
                <div v-if="selectedSection?.blocks.length">
                  <p v-for="block in selectedSection.blocks.slice(0, 5)" :key="block.block_id"><span>{{ block.kind }}</span>{{ block.text }}</p>
                </div>
                <p v-else class="preview-empty">{{ t('courseAuditUpdates.noPreview', '当前对象还没有可预览的结构化内容') }}</p>
              </section>

              <section class="material-decisions">
                <header><strong>{{ t('courseAuditUpdates.materialDecision', '材料判断') }}</strong><small>{{ t('courseAuditUpdates.savedImmediately', '修改后立即重新计算关系') }}</small></header>
                <label><span>{{ t('courseAuditUpdates.documentType', '材料类型') }}</span><select :value="selectedMaterial.document_type" :disabled="materialBusy" @change="changeDocumentType"><option value="outline">{{ t('courseFiles.preparation.documentTypes.outline', '课程大纲') }}</option><option value="lesson_plan">{{ t('courseFiles.preparation.documentTypes.lessonPlan', '教案') }}</option><option value="script">{{ t('courseFiles.preparation.documentTypes.script', '讲义') }}</option><option value="ppt">{{ t('courseFiles.preparation.documentTypes.ppt', 'PPT') }}</option><option value="other">{{ t('courseFiles.preparation.documentTypes.other', '其他资料') }}</option></select></label>
                <label v-if="plan?.scope_options?.length"><span>{{ t('courseAuditUpdates.coursePosition', '课程位置') }}</span><select :value="selectedMaterial.absorption_decision?.target_scope_id || ''" :disabled="materialBusy" @change="changeScope"><option value="">{{ t('courseAuditUpdates.positionPending', '待确认') }}</option><option v-for="scope in plan.scope_options" :key="scope.scope_id" :value="scope.scope_id">{{ scope.label }}</option></select></label>
                <label><span>{{ t('courseAuditUpdates.versionRole', '版本作用') }}</span><select :value="selectedMaterial.version_role || 'unknown'" :disabled="materialBusy" @change="changeVersion"><option value="current">{{ t('courseFiles.preparation.versionRoles.current', '当前版本') }}</option><option value="older">{{ t('courseFiles.preparation.versionRoles.older', '历史版本') }}</option><option value="reference">{{ t('courseFiles.preparation.versionRoles.reference', '参考资料') }}</option><option value="unknown">{{ t('courseFiles.preparation.versionRoles.unknown', '版本待确认') }}</option></select></label>
                <label><span>{{ t('courseAuditUpdates.sourceRole', '来源作用') }}</span><select :value="selectedSourceRole" :disabled="materialBusy" @change="changeRole"><option value="primary">{{ t('courseWorkbench.materialAudit.primary', '主来源') }}</option><option value="reference">{{ t('courseWorkbench.materialAudit.reference', '参考来源') }}</option></select></label>
                <label><span>{{ t('courseAuditUpdates.useMethod', '处理方式') }}</span><select :value="selectedMaterial.absorption_decision?.action || 'absorb'" :disabled="materialBusy" @change="changeAction"><option value="absorb">{{ t('courseFiles.materialAuditReport.absorb', '进入结构化同源链') }}</option><option value="reference_only">{{ t('courseFiles.materialAuditReport.referenceOnly', '仅作参考') }}</option><option value="ignore">{{ t('courseFiles.materialAuditReport.ignore', '本次不使用') }}</option></select></label>
              </section>

              <section class="protection-note"><ShieldCheck :size="16" /><span><strong>{{ t('courseAuditUpdates.protectionTitle', '老师手工修改不会被覆盖') }}</strong><small>{{ t('courseAuditUpdates.protectionDetail', '系统只生成可审阅候选；已确认内容和原始文件继续保留。') }}</small></span></section>

              <section class="execution-scope">
                <strong>{{ t('courseAuditUpdates.executionScope', '执行范围') }}</strong>
                <label><input v-model="executionScope" type="radio" value="current"><span />{{ t('courseAuditUpdates.currentObjectOnly', '只整理当前对象') }}</label>
                <label><input v-model="executionScope" type="radio" value="all"><span />{{ t('courseAuditUpdates.allAffected', '整理本次全部受影响对象') }}</label>
                <label><input v-model="executionScope" type="radio" value="skip"><span />{{ t('courseAuditUpdates.skipCurrent', '暂不处理') }}</label>
              </section>
            </template>

            <section v-else class="detail-empty"><ScanSearch :size="25" /><strong>{{ selectedMaterial ? t('courseAuditUpdates.noChangeDetails', '当前没有需要处理的变更详情') : t('courseAuditUpdates.selectSource', '选择一个变化来源查看生成关系') }}</strong></section>
            </div>

            <footer v-if="detailMode === 'detail' && selectedTarget" class="detail-actions">
              <small>{{ actionSummary }}</small>
              <div>
                <button type="button" :disabled="auditStore.executing" @click="executionScope = 'skip'">{{ t('courseAuditUpdates.saveForLater', '稍后处理') }}</button>
                <button class="primary" type="button" :disabled="!canExecuteSelection" @click="executeSelection">
                  <LoaderCircle v-if="auditStore.executing" :size="15" class="spin" /><Check v-else :size="15" />{{ executeLabel }}
                </button>
              </div>
            </footer>
          </aside>
        </template>
      </div>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch, type Component } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ArrowLeft, ArrowRight, BookOpenText, Check, ChevronDown, CircleCheckBig,
  FileText, FolderOpen, GitBranchPlus, History, Link2Off, LoaderCircle, Plus, Presentation,
  RefreshCw, ScanSearch, ScrollText, ShieldCheck, Sparkles, TriangleAlert, Upload, X,
} from 'lucide-vue-next'
import CourseEvolutionWorkspace from '../components/CourseEvolutionWorkspace.vue'
import { t } from '../shared/i18n'
import {
  useCourseUpdateCenterStore,
  type CourseUpdateSource,
} from '../stores/courseUpdateCenter'
import type {
  MaterialAbsorptionAction,
  MaterialAuditAsset,
  MaterialAuditTarget,
  MaterialDocumentType,
} from '../stores/teacherMaterialAudit'
import http, { teacherRequestConfig } from '../utils/http'

const props = withDefaults(defineProps<{ courseId?: string; planId?: string }>(), { courseId: '', planId: '' })
const route = useRoute()
const router = useRouter()
const center = useCourseUpdateCenterStore()
const auditStore = center.materialAudit
const evolutionStore = center.courseEvolution
const fileInput = ref<HTMLInputElement | null>(null)
const sourceAddMenu = ref<HTMLElement | null>(null)
const sourceMenuOpen = ref(false)
const evolutionWorkspaceRef = ref<{ openPlan?: (id: string) => void; startNewRequest?: () => void; showHistory?: () => void } | null>(null)
const selectedTargetId = ref('')
const selectedSectionId = ref('')
const relationshipView = ref<'relation' | 'list'>('relation')
const detailMode = ref<'detail' | 'execution' | 'version' | 'unaffected'>('detail')
const executionScope = ref<'current' | 'all' | 'skip'>('current')
const uploading = ref(false)

const courseId = computed(() => String(props.courseId || route.params.courseId || ''))
const coursePackage = computed(() => auditStore.coursePackage)
const plan = computed(() => auditStore.plan)
const courseName = computed(() => String(coursePackage.value?.course_name || evolutionStore.courseContext?.course_title || ''))
const activeSource = computed(() => center.activeSource)
const isCourseChangeMode = computed(() => ['course_change', 'new_change'].includes(activeSource.value?.kind || ''))
const activeCoursePlanId = computed(() => activeSource.value?.kind === 'course_change' ? activeSource.value.sourceId : '')
const selectedMaterial = computed(() => activeSource.value?.kind === 'material' ? activeSource.value.material || null : null)
type CourseChangeListItem = CourseUpdateSource & { repeatCount: number }
const actionableCourseChanges = computed<CourseChangeListItem[]>(() => {
  const groups = new Map<string, CourseUpdateSource[]>()
  center.courseChangeSources
    .filter(source => !['applied', 'unchanged', 'undone'].includes(source.status) || source.key === center.activeSourceKey)
    .forEach(source => {
      const fingerprint = source.title.trim().replace(/\s+/g, ' ')
      groups.set(fingerprint, [...(groups.get(fingerprint) || []), source])
    })
  return [...groups.values()].map(group => ({
    ...(group.find(source => source.key === center.activeSourceKey) || group[0]!),
    repeatCount: group.length,
  }))
})
const sourceOverview = computed(() => t('courseAuditUpdates.sourceOverview', '{materials} 份材料 · {changes} 项待处理调整')
  .replace('{materials}', String(center.materialSources.length))
  .replace('{changes}', String(actionableCourseChanges.value.length)))
const materialStatusLabels = computed(() => [...new Set(center.materialSources.map(materialListStatusLabel))])
const showMaterialRowStatus = computed(() => materialStatusLabels.value.length > 1)
const courseChangeStatusLabels = computed(() => [...new Set([
  ...actionableCourseChanges.value.map(source => sourceStatusLabel(source.status)),
  ...(activeSource.value?.kind === 'new_change' ? [t('courseAuditUpdates.editing', '编辑中')] : []),
])])
const showCourseChangeRowStatus = computed(() => courseChangeStatusLabels.value.length > 1)
const selectedMaterialTargets = computed(() => !selectedMaterial.value ? [] : (plan.value?.targets || []).filter(target => (
  target.sources.some(source => source.asset_id === selectedMaterial.value?.asset_id)
)))
const selectedTarget = computed(() => selectedMaterialTargets.value.find(target => target.target_id === selectedTargetId.value) || selectedMaterialTargets.value[0] || null)
const selectedSection = computed(() => selectedTarget.value?.structured_draft?.sections.find(section => section.section_id === selectedSectionId.value) || selectedTarget.value?.structured_draft?.sections[0] || null)
const selectedSourceRole = computed(() => selectedTarget.value?.sources.find(source => source.asset_id === selectedMaterial.value?.asset_id)?.role || selectedMaterial.value?.absorption_decision?.role || 'reference')
const executedTargetIds = computed(() => new Set(
  (plan.value?.execution?.receipts || [])
    .filter(receipt => receipt.plan_id === plan.value?.plan_id)
    .flatMap(receipt => receipt.target_ids || []),
))
const pendingMaterialTargetCount = computed(() => (plan.value?.targets || []).filter(target => !executedTargetIds.value.has(target.target_id)).length)
const pendingCourseChangeCount = computed(() => center.courseChangeSources.filter(source => !['applied', 'unchanged'].includes(source.status)).length)
const changedSourceCount = computed(() => center.sources.filter(source => ['changed', 'pending', 'ready', 'failed'].includes(source.status)).length)
const pendingTotal = computed(() => pendingMaterialTargetCount.value + pendingCourseChangeCount.value)
const statusTone = computed(() => center.loading || auditStore.refreshing ? 'scanning' : pendingTotal.value || plan.value?.status === 'stale' ? 'changed' : 'synced')
const statusSummary = computed(() => statusTone.value === 'scanning'
  ? t('courseAuditUpdates.scanning', '正在扫描课程变化和生成关系')
  : statusTone.value === 'synced'
    ? t('courseAuditUpdates.allSynced', '当前材料与生成内容已经同步')
    : t('courseAuditUpdates.statusSummary', '发现 {sources} 个变化来源 · {targets} 个生成内容待处理 · 其余内容保持不变')
      .replace('{sources}', String(changedSourceCount.value))
      .replace('{targets}', String(pendingTotal.value)))
const lastAppliedAt = computed(() => {
  const materialTimes = (plan.value?.execution?.receipts || []).map(receipt => receipt.executed_at).filter(Boolean)
  const changeTimes = center.courseChangeSources.filter(source => source.status === 'applied').map(source => source.updatedAt).filter(Boolean)
  return [...materialTimes, ...changeTimes].sort().at(-1) || ''
})
const lastAppliedLabel = computed(() => lastAppliedAt.value
  ? t('courseAuditUpdates.lastApplied', '上次应用：{time}').replace('{time}', formatTime(lastAppliedAt.value))
  : t('courseAuditUpdates.noApplied', '尚未执行过联动更新'))
const returnLabel = computed(() => String(route.query?.returnLabel || t('courseAuditUpdates.returnWorkbench', '返回备课工作台')))
const materialBusy = computed(() => Boolean(selectedMaterial.value && (
  auditStore.executing || auditStore.updatingAssetIds.includes(selectedMaterial.value.asset_id)
)))
const relationshipGroups = computed(() => {
  const labels: Record<string, string> = { outline: '课程大纲', lesson_plan: '教案', script: '讲义', ppt: 'PPT' }
  const groups = new Map<string, MaterialAuditTarget[]>()
  selectedMaterialTargets.value.forEach(target => groups.set(target.target_type, [...(groups.get(target.target_type) || []), target]))
  return [...groups].map(([key, items]) => ({ key, label: t(`courseAuditUpdates.type.${key}`, labels[key] || key), items }))
})
const unaffectedTargetCount = computed(() => Math.max(0, (plan.value?.targets.length || 0) - selectedMaterialTargets.value.length))
const detailTitle = computed(() => detailMode.value === 'execution'
  ? t('courseAuditUpdates.executionHistory', '执行记录')
  : detailMode.value === 'version'
    ? t('courseAuditUpdates.versionHistory', '版本历史')
    : detailMode.value === 'unaffected'
      ? t('courseAuditUpdates.unaffected', '其他不受影响的内容')
      : t('courseAuditUpdates.changeDetails', '变更详情'))
const historyItems = computed(() => {
  if (detailMode.value === 'unaffected') return (plan.value?.targets || []).filter(target => !selectedMaterialTargets.value.some(item => item.target_id === target.target_id)).map(target => ({ key: target.target_id, title: target.title, detail: t('courseAuditUpdates.notReferenced', '未引用当前变化来源，保持当前版本'), time: '', status: 'unchanged' }))
  const materialItems = (plan.value?.execution?.receipts || []).map(receipt => ({ key: receipt.bundle_id, title: t('courseAuditUpdates.materialExecution', '材料结构化执行'), detail: `${receipt.target_ids?.length || 0} ${t('courseAuditUpdates.objects', '个对象')} · ${receipt.status.includes('failed') ? t('courseAuditUpdates.needsAttention', '需处理') : t('courseAuditUpdates.executed', '已执行')}`, time: formatTime(receipt.executed_at), status: receipt.status.includes('failed') ? 'failed' : 'applied' }))
  const courseItems = center.courseChangeSources.map(source => ({ key: source.key, title: source.title, detail: sourceStatusLabel(source.status), time: formatTime(source.updatedAt), status: source.status }))
  return detailMode.value === 'version' ? [...courseItems, ...materialItems] : [...materialItems, ...courseItems.filter(item => item.status === 'applied')]
})
const canExecuteSelection = computed(() => Boolean(
  !auditStore.executing
  && selectedTarget.value
  && executionScope.value !== 'skip'
  && !(plan.value?.unresolved_items || []).length,
))
const executeLabel = computed(() => executionScope.value === 'all'
  ? t('courseAuditUpdates.applyAll', '应用全部待处理更新')
  : t('courseAuditUpdates.applyCurrent', '应用当前对象更新'))
const actionSummary = computed(() => executionScope.value === 'skip'
  ? t('courseAuditUpdates.savedOnly', '本次只保存材料判断，不执行更新')
  : executionScope.value === 'all'
    ? t('courseAuditUpdates.allScopeSummary', '将整理本次全部受影响对象')
    : t('courseAuditUpdates.currentScopeSummary', '将整理“{target}”').replace('{target}', selectedTarget.value?.title || '—'))

watch(selectedMaterialTargets, targets => {
  if (!targets.some(target => target.target_id === selectedTargetId.value)) selectedTargetId.value = targets[0]?.target_id || ''
}, { immediate: true })
watch(selectedTarget, target => {
  const sections = target?.structured_draft?.sections || []
  if (!sections.some(section => section.section_id === selectedSectionId.value)) selectedSectionId.value = sections[0]?.section_id || ''
}, { immediate: true })

function sourceIcon(type?: string): Component {
  return ({ outline: BookOpenText, lesson_plan: FileText, script: ScrollText, ppt: Presentation } as Record<string, Component>)[String(type || '')] || FileText
}
function targetIcon(type: MaterialAuditTarget['target_type']): Component { return sourceIcon(type) }
function materialRoleLabel(asset?: MaterialAuditAsset) { return asset?.absorption_decision?.role === 'primary' ? t('courseAuditUpdates.primary', '主来源') : t('courseAuditUpdates.reference', '参考') }
function materialTypeLabel(asset?: MaterialAuditAsset) {
  const fallback = t('courseFiles.preparation.documentTypes.other', '其他资料')
  return ({ outline: t('courseFiles.preparation.documentTypes.outline', '课程大纲'), lesson_plan: t('courseFiles.preparation.documentTypes.lessonPlan', '教案'), script: t('courseFiles.preparation.documentTypes.script', '讲义'), ppt: 'PPT', question_bank: t('courseFiles.preparation.documentTypes.questionBank', '题库与试卷'), school_material: t('courseFiles.preparation.documentTypes.schoolMaterial', '教务材料'), other: fallback } as Record<string, string>)[asset?.document_type || 'other'] || fallback
}
function materialSourceMeta(asset?: MaterialAuditAsset) { return `${materialTypeLabel(asset)} · ${materialRoleLabel(asset)}` }
function parseQualityLabel(asset?: MaterialAuditAsset) {
  if (asset?.parse_status === 'failed') return t('courseAuditUpdates.parseLow', '解析失败')
  if (asset?.parse_status === 'degraded' || asset?.parse_warnings?.length) return t('courseAuditUpdates.parseMedium', '解析需复核')
  return t('courseAuditUpdates.parseHigh', '高质量解析')
}
function sourceStatusLabel(status: CourseUpdateSource['status']): string { return ({ changed: t('courseAuditUpdates.changed', '有变化'), pending: t('courseAuditUpdates.scanningShort', '扫描中'), ready: t('courseAuditUpdates.pendingReview', '待审阅'), applied: t('courseAuditUpdates.synced', '已同步'), failed: t('courseAuditUpdates.needsAttention', '需处理'), unchanged: t('courseAuditUpdates.unchanged', '不变') } as Record<string, string>)[status] || status }
function materialListStatus(source: CourseUpdateSource): CourseUpdateSource['status'] {
  const asset = source.material
  if (asset?.parse_status === 'failed' || asset?.parse_status === 'degraded' || asset?.parse_warnings?.length) return 'failed'
  if (!asset?.version_role || asset.version_role === 'unknown') return 'ready'
  return source.status
}
function materialListStatusLabel(source: CourseUpdateSource) {
  if (materialListStatus(source) === 'failed') return parseQualityLabel(source.material)
  if (!source.material?.version_role || source.material.version_role === 'unknown') return t('courseAuditUpdates.versionPending', '版本待确认')
  return sourceStatusLabel(source.status)
}
function courseChangeMeta(source: CourseChangeListItem) {
  const time = formatTime(source.updatedAt) || t('courseAuditUpdates.pendingTime', '待处理')
  return source.repeatCount > 1
    ? `${time} · ${t('courseAuditUpdates.repeatedChanges', '{count} 次同类调整').replace('{count}', String(source.repeatCount))}`
    : time
}
function targetStatus(target: MaterialAuditTarget) { return target.issues?.length || target.review_items?.length ? 'warning' : executedTargetIds.value.has(target.target_id) ? 'synced' : 'pending' }
function targetStatusLabel(target: MaterialAuditTarget) { return targetStatus(target) === 'warning' ? t('courseAuditUpdates.needsDecision', '需判断') : targetStatus(target) === 'synced' ? t('courseAuditUpdates.unchanged', '不变') : t('courseAuditUpdates.pendingUpdate', '待更新') }
function relationshipItemSummary(target: MaterialAuditTarget) { const sections = target.structured_draft?.sections || []; const blocks = sections.reduce((total, section) => total + section.blocks.length, 0); return `${sections.length} ${t('courseAuditUpdates.sections', '个结构段')} · ${blocks} ${t('courseAuditUpdates.blocks', '个内容块')}` }
function sourceRoleForTarget(target: MaterialAuditTarget) { return target.sources.find(source => source.asset_id === selectedMaterial.value?.asset_id)?.role === 'primary' ? t('courseAuditUpdates.primary', '主来源') : t('courseAuditUpdates.reference', '参考') }
function formatTime(value: string) { if (!value) return ''; const date = new Date(value); return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(date) }

function preferredSourceKey() {
  const planId = String(props.planId || route.params?.planId || route.query?.planId || '')
  if (planId) return `course-change:${planId}`
  if (route.query?.view === 'changes') return 'new-change'
  return ''
}
async function loadCenter() {
  await center.load(courseId.value, preferredSourceKey())
  if (preferredSourceKey() === 'new-change') await nextTick(() => evolutionWorkspaceRef.value?.startNewRequest?.())
}
async function refreshAll() { await center.refreshAll() }
function selectMaterialSource(key: string) { center.selectSource(key); detailMode.value = 'detail'; executionScope.value = 'current' }
async function selectCourseChange(key: string, planId: string) { center.selectSource(key); await nextTick(); evolutionWorkspaceRef.value?.openPlan?.(planId) }
function closeSourceAddMenu() { sourceMenuOpen.value = false }
function handleSourceMenuFocusout(event: FocusEvent) {
  const nextTarget = event.relatedTarget as Node | null
  if (!nextTarget || !sourceAddMenu.value?.contains(nextTarget)) closeSourceAddMenu()
}
function openMaterialPicker() { closeSourceAddMenu(); fileInput.value?.click() }
async function startNewCourseChange() { closeSourceAddMenu(); center.selectSource('new-change'); await nextTick(); evolutionWorkspaceRef.value?.startNewRequest?.() }
function selectTarget(targetId: string) { selectedTargetId.value = targetId; detailMode.value = 'detail' }
function showHistory(mode: 'execution' | 'version' | 'unaffected') { if (isCourseChangeMode.value) { evolutionWorkspaceRef.value?.showHistory?.(); return }; detailMode.value = mode }
function backToWorkbench() {
  const returnTo = String(route.query?.returnTo || '')
  if (returnTo.startsWith(`/course/${courseId.value}/workspace`)) { void router.push(returnTo); return }
  void router.push({ name: 'course-workspace', params: { courseId: courseId.value, mode: 'build' } })
}
function previewSource() {
  if (!coursePackage.value || !selectedMaterial.value) return
  window.open(`/api/teacher-course-spaces/${coursePackage.value.package_id}/assets/${selectedMaterial.value.asset_id}/preview`, '_blank', 'noopener,noreferrer')
}
async function captureFiles(event: Event) {
  const input = event.target as HTMLInputElement
  const files = [...(input.files || [])]
  input.value = ''
  if (!files.length || !coursePackage.value) return
  uploading.value = true
  try {
    const form = new FormData()
    files.forEach(file => {
      form.append('files', file, file.name)
      form.append('relative_paths', `辅助资料/其他资料/${file.name}`)
    })
    const response = await http.post(
      `/api/teacher-course-spaces/${coursePackage.value.package_id}/imports`,
      form,
      teacherRequestConfig(),
    )
    auditStore.coursePackage = response.data.package
    const imported = response.data?.outcomes?.filter((item: any) => item.asset_id).at(-1)
    center.selectFirstAvailable(imported?.asset_id ? `material:${imported.asset_id}` : '')
  } finally {
    uploading.value = false
  }
}
async function changeDocumentType(event: Event) { if (!selectedMaterial.value) return; await auditStore.updateDocumentType(selectedMaterial.value.asset_id, (event.target as HTMLSelectElement).value as MaterialDocumentType) }
async function changeVersion(event: Event) { if (!selectedMaterial.value) return; await auditStore.updateDecision(selectedMaterial.value.asset_id, { version_role: (event.target as HTMLSelectElement).value as MaterialAuditAsset['version_role'] }) }
async function changeScope(event: Event) { if (!selectedMaterial.value) return; await auditStore.updateDecision(selectedMaterial.value.asset_id, { target_scope_id: (event.target as HTMLSelectElement).value, action: 'absorb' }) }
async function changeRole(event: Event) {
  if (!selectedMaterial.value || !selectedTarget.value) return
  const role = (event.target as HTMLSelectElement).value as 'primary' | 'reference'
  if (role === 'primary') {
    for (const source of selectedTarget.value.sources.filter(item => item.asset_id !== selectedMaterial.value?.asset_id && item.role === 'primary')) {
      await auditStore.updateDecision(source.asset_id, { role: 'reference', action: 'absorb' })
    }
  }
  await auditStore.updateDecision(selectedMaterial.value.asset_id, { role, action: 'absorb' })
}
async function changeAction(event: Event) { if (!selectedMaterial.value) return; await auditStore.updateDecision(selectedMaterial.value.asset_id, { action: (event.target as HTMLSelectElement).value as MaterialAbsorptionAction }) }
async function executeSelection() {
  if (!selectedTarget.value || executionScope.value === 'skip') return
  await auditStore.execute(executionScope.value === 'all' ? [] : [selectedTarget.value.target_id])
}

onMounted(() => { if (courseId.value) void loadCenter() })
</script>

<style scoped>
.update-center-page{height:100%;min-height:0;overflow:hidden;color:#253047;background:#f6f7fb}.update-route-context{min-width:0;display:flex;align-items:center;gap:9px}.update-route-context>button{width:34px;height:34px;display:grid;place-items:center;border:0;border-radius:8px;color:#64748b;background:transparent;cursor:pointer}.update-route-context>button:hover{color:#5148dc;background:#efeeff}.update-route-context>svg{flex:none;color:#5148dc}.update-route-context>div{min-width:0;display:grid;gap:1px}.update-route-context h1{margin:0;color:#172033;font-size:17px}.update-route-context small{overflow:hidden;color:#7c8798;font-size:10px;text-overflow:ellipsis;white-space:nowrap}.update-route-actions{display:flex;align-items:center;gap:8px}.update-route-actions button{min-height:36px;display:inline-flex;align-items:center;gap:7px;padding:0 11px;border:1px solid #dbe1e9;border-radius:8px;color:#475569;background:#fff;font-size:11px;font-weight:700;cursor:pointer}.update-route-actions button:hover{border-color:#b8b4f2;color:#4d46cf}.update-route-actions button.primary{border-color:#514bdc;color:#fff;background:#514bdc}.center-state{height:100%;display:grid;place-content:center;justify-items:center;gap:12px;color:#728096}.update-center-shell{height:100%;min-height:0;display:grid;grid-template-rows:auto minmax(0,1fr) auto;gap:0;padding:14px 18px 12px;box-sizing:border-box}.update-center-shell.has-error{grid-template-rows:auto auto minmax(0,1fr) auto}.update-status-strip{min-height:54px;display:grid;grid-template-columns:minmax(0,1fr) auto auto;align-items:center;gap:18px;padding:0 14px;border:1px solid #dfe4ec;border-radius:10px 10px 0 0;background:#fff}.update-status-strip>div{display:flex;align-items:center;gap:9px;color:#087354}.update-status-strip[data-state=changed]>div{color:#a35d00}.update-status-strip[data-state=scanning]>div{color:#5148dc}.update-status-strip strong{color:#273247;font-size:12px}.update-status-strip>small{color:#7a8595;font-size:9px}.update-status-strip>button{min-height:31px;display:inline-flex;align-items:center;gap:6px;padding:0 9px;border:1px solid #d9dee7;border-radius:7px;color:#596579;background:#fff;font-size:10px;font-weight:700;cursor:pointer}.center-error{display:flex;align-items:center;gap:7px;margin:0;padding:8px 12px;border-right:1px solid #f0c2bd;border-left:1px solid #f0c2bd;color:#b42318;background:#fff4f2;font-size:10px}.update-center-grid{min-height:0;display:grid;grid-template-columns:minmax(270px,310px) minmax(420px,1fr) minmax(310px,370px);overflow:hidden;border:1px solid #dfe4ec;border-top:0;background:#fff}.source-ledger,.relationship-pane,.detail-pane,.course-change-surface{min-width:0;min-height:0}.source-ledger{display:grid;grid-template-rows:auto minmax(0,1fr);overflow:hidden;border-right:1px solid #dfe4ec;background:#fff}.source-ledger>header,.pane-header{min-height:49px;display:flex;align-items:center;justify-content:space-between;gap:8px;padding:0 13px;border-bottom:1px solid #e5e9ef}.source-ledger>header{min-height:56px}.source-heading{min-width:0;display:grid;gap:2px}.source-ledger h2,.pane-header h2{margin:0;color:#24314a;font-size:13px}.source-heading small{overflow:hidden;color:#8993a2;font-size:8px;text-overflow:ellipsis;white-space:nowrap}.source-add-menu{position:relative;flex:none}.source-add-menu summary{min-height:31px;display:inline-flex;align-items:center;gap:5px;padding:0 8px;border:1px solid #d7d9ff;border-radius:7px;color:#5148dc;background:#f7f6ff;font-size:9px;font-weight:750;list-style:none;cursor:pointer}.source-add-menu summary::-webkit-details-marker{display:none}.source-add-menu[open] summary{border-color:#aaa5f3;background:#efeeff}.source-add-menu>div{position:absolute;z-index:8;top:calc(100% + 6px);right:0;width:232px;padding:5px;border:1px solid #dfe3ea;border-radius:9px;background:#fff;box-shadow:0 12px 28px rgba(35,42,70,.16)}.source-add-menu>div button{width:100%;min-height:50px;display:grid;grid-template-columns:22px minmax(0,1fr);align-items:center;gap:8px;padding:7px 8px;border:0;border-radius:7px;color:#596579;background:#fff;text-align:left;cursor:pointer}.source-add-menu>div button:hover{background:#f7f6ff}.source-add-menu>div button>svg{color:#5e57dc}.source-add-menu>div button span{min-width:0;display:grid;gap:3px}.source-add-menu>div button b{color:#344054;font-size:9px}.source-add-menu>div button small{color:#8791a1;font-size:8px;line-height:1.35}.source-groups{min-height:0;overflow:auto}.source-group{border-bottom:1px solid #e4e8ef}.source-group>header{height:34px;display:flex;align-items:center;justify-content:space-between;padding:0 12px;color:#5f6b7d;background:#f8f9fb;font-size:9px}.source-group>header small{color:#8b95a4}.source-list{display:grid}.source-list>button{display:grid;grid-template-columns:28px minmax(0,1fr) auto;align-items:center;gap:8px;min-height:55px;padding:7px 10px;border:0;border-bottom:1px solid #edf0f4;color:#586479;background:#fff;text-align:left;cursor:pointer}.source-list>button:hover{background:#fafaff}.source-list>button.active{color:#4d46cf;background:#efeeff}.source-icon{width:28px;height:28px;display:grid!important;place-items:center;border-radius:7px;color:#5e57dc;background:#f3f2ff}.source-list>button span:not(.source-icon){min-width:0;display:grid;gap:3px}.source-list>button b{overflow:hidden;color:#263249;font-size:10px;text-overflow:ellipsis;white-space:nowrap}.source-list>button small{overflow:hidden;color:#7b8697;font-size:8px;text-overflow:ellipsis;white-space:nowrap}.source-list>button i{padding:4px 6px;border-radius:999px;color:#087354;background:#edf8f4;font-size:8px;font-style:normal;white-space:nowrap}.source-list>button[data-status=changed] i,.source-list>button[data-status=pending] i,.source-list>button[data-status=ready] i{color:#b66000;background:#fff4e5}.source-list>button[data-status=failed] i{color:#b42318;background:#fff0ee}.source-list>button[data-status=pending] i{color:#5148dc;background:#efeeff}.source-empty{margin:0;padding:20px 12px;color:#8a94a4;font-size:9px;text-align:center}.course-change-group{border-bottom:0}.material-decisions select,.detail-section-selector select{min-width:0;height:31px;padding:0 25px 0 8px;border:1px solid #d7dde6;border-radius:7px;color:#566176;background:#fff;font-size:9px}.relationship-pane{display:grid;grid-template-rows:auto auto minmax(0,1fr);overflow:hidden;border-right:1px solid #dfe4ec;background:#fff}.pane-header nav{display:flex;gap:2px}.pane-header nav button{min-height:31px;padding:0 9px;border:0;border-bottom:2px solid transparent;color:#7c8697;background:transparent;font-size:9px;cursor:pointer}.pane-header nav button.active{border-color:#5148dc;color:#5148dc;font-weight:800}.selected-source-card{display:grid;grid-template-columns:26px minmax(0,1fr) auto;align-items:center;gap:9px;margin:11px 13px 7px;padding:10px 12px;border:1px solid #d9d7ff;border-radius:8px;color:#5148dc;background:#f6f5ff}.selected-source-card span{min-width:0;display:grid;gap:3px}.selected-source-card strong{overflow:hidden;color:#263249;font-size:10px;text-overflow:ellipsis;white-space:nowrap}.selected-source-card small{color:#7b8498;font-size:8px}.selected-source-card b{color:#087354;font-size:8px}.relationship-tree{min-height:0;overflow:auto;padding:3px 13px 18px}.relationship-group{position:relative;margin-top:10px;padding-left:20px}.relationship-group::before{position:absolute;top:14px;bottom:7px;left:7px;border-left:1px solid #d8ddec;content:""}.relationship-group>header{position:relative;display:flex;align-items:center;gap:5px;min-height:28px}.relationship-group>header>span{position:absolute;left:-16px;width:7px;height:7px;border:2px solid #625be1;border-radius:50%;background:#fff}.relationship-group>header strong{color:#38445a;font-size:10px}.relationship-group>header small{color:#8a94a3;font-size:8px}.relationship-group>div{display:grid;margin-left:5px;border:1px solid #e1e5eb;border-radius:7px;overflow:hidden}.relationship-group button{display:grid;grid-template-columns:minmax(0,1fr) auto auto;align-items:center;gap:8px;min-height:38px;padding:0 10px;border:0;border-bottom:1px solid #edf0f3;color:#667085;background:#fff;font-size:9px;text-align:left;cursor:pointer}.relationship-group button:last-child{border-bottom:0}.relationship-group button:hover,.relationship-group button.active{background:#fafaff}.relationship-group button.active{color:#5148dc}.relationship-group button span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.relationship-group button small{color:#8a94a3;font-size:8px}.relationship-group button b{color:#919aaa;font-size:8px}.relationship-group button[data-status=pending] b,.relationship-group button[data-status=warning] b{color:#d26f00}.unaffected-row{width:100%;display:grid;grid-template-columns:16px minmax(0,1fr) auto;align-items:center;gap:7px;margin-top:13px;padding:9px 11px;border:1px solid #e0e5ec;border-radius:8px;color:#6e7888;background:#f8f9fb;text-align:left;cursor:pointer}.unaffected-row span{display:grid;gap:2px}.unaffected-row strong{font-size:9px}.unaffected-row small{font-size:8px}.unaffected-row b{color:#16805f;font-size:9px}.relationship-table{min-height:0;overflow:auto;padding:8px 13px 18px}.relationship-table>header,.relationship-table>button{display:grid;grid-template-columns:minmax(140px,1fr) 75px 110px 52px;gap:8px;align-items:center}.relationship-table>header{padding:7px 9px;color:#8a94a3;font-size:8px}.relationship-table>button{width:100%;min-height:42px;padding:0 9px;border:0;border-top:1px solid #e6e9ee;color:#5b6678;background:#fff;font-size:9px;text-align:left;cursor:pointer}.relationship-table>button.active{color:#5148dc;background:#f7f6ff}.relationship-table>button span:first-child{display:flex;align-items:center;gap:6px}.relationship-empty,.detail-empty{display:grid;place-content:center;justify-items:center;gap:7px;padding:24px;color:#8a94a3;text-align:center}.relationship-empty strong,.detail-empty strong{color:#596579;font-size:11px}.relationship-empty p{margin:0;font-size:9px}.detail-pane{display:block;overflow:auto;background:#fff}.detail-pane>.pane-header{position:sticky;z-index:2;top:0;background:#fff}.detail-pane>.pane-header>span{padding:4px 7px;border-radius:6px;color:#16805f;background:#edf8f4;font-size:8px}.detail-pane>.pane-header>span[data-status=pending],.detail-pane>.pane-header>span[data-status=warning]{color:#bd6500;background:#fff5e6}.detail-source,.detail-section-selector,.structured-preview,.material-decisions,.protection-note,.execution-scope{margin:0 13px;padding:13px 0;border-bottom:1px solid #e8ebf0}.detail-source>small,.detail-section-selector>small{display:block;margin-bottom:8px;color:#7c8797;font-size:8px;font-weight:700}.detail-source>div{display:grid;grid-template-columns:20px minmax(0,1fr) auto;align-items:center;gap:8px;padding:9px;border:1px solid #e0e5ec;border-radius:8px}.detail-source span{min-width:0;display:grid;gap:2px}.detail-source strong{overflow:hidden;color:#344054;font-size:9px;text-overflow:ellipsis;white-space:nowrap}.detail-source small{overflow:hidden;color:#8a94a3;font-size:8px;text-overflow:ellipsis;white-space:nowrap}.detail-source button{display:inline-flex;align-items:center;gap:3px;border:0;color:#5148dc;background:transparent;font-size:8px;font-weight:700;cursor:pointer}.detail-section-selector select{width:100%}.structured-preview>header,.material-decisions>header{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:9px}.structured-preview>header strong,.material-decisions>header strong,.execution-scope>strong{color:#3b4659;font-size:9px}.structured-preview>header small,.material-decisions>header small{color:#8b95a3;font-size:8px}.structured-preview>div{display:grid;gap:5px}.structured-preview p{margin:0;padding:7px 8px;border-radius:6px;color:#556071;background:#f7f8fa;font-size:8px;line-height:1.55}.structured-preview p span{margin-right:6px;color:#5148dc;font-weight:800}.preview-empty{color:#8a94a3!important;text-align:center}.material-decisions{display:grid;grid-template-columns:1fr 1fr;gap:8px}.material-decisions>header{grid-column:1/-1}.material-decisions label{display:grid;gap:4px}.material-decisions label>span{color:#788393;font-size:8px}.protection-note{display:grid;grid-template-columns:18px minmax(0,1fr);gap:8px;color:#087354}.protection-note span{display:grid;gap:3px}.protection-note strong{font-size:9px}.protection-note small{color:#5b776d;font-size:8px;line-height:1.5}.execution-scope{display:grid;gap:8px;border-bottom:0}.execution-scope label{display:flex;align-items:center;gap:7px;color:#596579;font-size:9px;cursor:pointer}.execution-scope input{position:absolute;opacity:0}.execution-scope label>span{width:13px;height:13px;border:1px solid #98a2b3;border-radius:50%;background:#fff}.execution-scope input:checked+span{border:4px solid #5148dc}.history-panel{padding:13px}.history-panel>header{display:grid;grid-template-columns:18px minmax(0,1fr) 28px;align-items:center;gap:7px;color:#5148dc}.history-panel>header strong{color:#344054;font-size:10px}.history-panel>header button{width:28px;height:28px;display:grid;place-items:center;border:0;border-radius:6px;color:#667085;background:#f5f6f8;cursor:pointer}.history-panel ol{display:grid;gap:0;margin:12px 0 0;padding:0;list-style:none}.history-panel li{display:grid;grid-template-columns:8px minmax(0,1fr) auto;gap:8px;padding:9px 0;border-bottom:1px solid #e8ebef}.history-panel li>span{width:7px;height:7px;margin-top:3px;border-radius:50%;background:#16a36a}.history-panel li[data-status=failed]>span{background:#d92d20}.history-panel li[data-status=ready]>span,.history-panel li[data-status=pending]>span{background:#e78b16}.history-panel li div{display:grid;gap:3px}.history-panel li b{color:#344054;font-size:9px}.history-panel li small,.history-panel time{color:#8a94a3;font-size:8px}.history-panel>p{color:#8a94a3;font-size:9px}.course-change-surface{grid-column:2/4;overflow:hidden;background:#fff}.center-actionbar{min-height:62px;display:grid;grid-template-columns:minmax(0,1fr) auto auto;align-items:center;gap:9px;padding:0 12px;border:1px solid #dfe4ec;border-top:0;border-radius:0 0 10px 10px;background:#fff}.center-actionbar>div{display:grid;gap:3px}.center-actionbar strong{color:#344054;font-size:10px}.center-actionbar small{color:#7e8897;font-size:8px}.center-actionbar>button{min-height:36px;display:inline-flex;align-items:center;gap:6px;padding:0 12px;border:1px solid #d7dde6;border-radius:8px;color:#5148dc;background:#fff;font-size:10px;font-weight:750;cursor:pointer}.center-actionbar>button.primary{border-color:#5148dc;color:#fff;background:#5148dc}.center-actionbar>button:disabled,.source-ledger button:disabled,.update-status-strip button:disabled{opacity:.45;cursor:not-allowed}.spin{animation:spin .85s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}@media(max-width:1180px){.update-center-grid{grid-template-columns:minmax(240px,270px) minmax(390px,1fr) minmax(280px,320px)}.source-add-menu summary{padding:0 7px}.relationship-group button{grid-template-columns:minmax(0,1fr) auto}.relationship-group button small{display:none}.material-decisions{grid-template-columns:1fr}}@media(prefers-reduced-motion:reduce){.spin{animation:none}}
</style>

<style scoped>
.update-center-page {
  color: var(--lz-text-strong);
  background: var(--lz-surface);
}

.update-route-context {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 9px;
}
.update-route-context > button {
  width: 34px;
  height: 34px;
  flex: none;
  display: grid;
  place-items: center;
  border: 0;
  border-radius: 8px;
  color: var(--lz-text-secondary);
  background: transparent;
  cursor: pointer;
}
.update-route-context > button:hover {
  color: var(--lz-brand-strong);
  background: var(--lz-brand-soft);
}
.update-route-context > button:focus-visible,
.update-route-actions button:focus-visible,
.source-add-trigger:focus-visible,
.relationship-view-switch button:focus-visible,
.rescan-button:focus-visible,
.detail-actions button:focus-visible,
.history-switch button:focus-visible {
  outline: 2px solid var(--lz-brand);
  outline-offset: 2px;
}
.update-route-context > svg {
  flex: none;
  color: var(--lz-brand);
}
.update-route-context h1 {
  min-width: 0;
  margin: 0;
  overflow: hidden;
  color: var(--lz-text-strong);
  font-size: 18px;
  font-weight: 800;
  letter-spacing: -.012em;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.update-route-context > small {
  flex: none;
  padding: 4px 7px;
  border-radius: 6px;
  color: var(--lz-brand-strong);
  background: var(--lz-brand-soft);
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
}
.update-route-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.update-route-actions button {
  min-height: 38px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  padding: 0 11px;
  border: 1px solid var(--lz-border);
  border-radius: 8px;
  color: var(--lz-text-secondary);
  background: var(--lz-surface);
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
}
.update-route-actions button:hover {
  border-color: var(--lz-brand-border);
  color: var(--lz-brand-strong);
  background: #f8f8ff;
}

.update-center-shell,
.update-center-shell.has-error {
  height: 100%;
  min-height: 0;
  display: grid;
  grid-template-rows: minmax(0, 1fr);
  padding: 0;
  background: var(--lz-surface);
}
.update-center-shell.has-error { grid-template-rows: auto minmax(0, 1fr); }
.center-error {
  border: 0;
  border-bottom: 1px solid #f0c2bd;
  font-size: 11px;
}
.update-center-grid {
  min-height: 0;
  display: grid;
  grid-template-columns: 204px minmax(0, 1fr) 314px;
  overflow: hidden;
  border: 0;
  background: var(--lz-surface);
}

.source-ledger {
  min-width: 0;
  min-height: 0;
  display: grid;
  grid-template-rows: 72px minmax(0, 1fr) auto;
  overflow: hidden;
  border-right: 1px solid var(--lz-border);
  background: var(--lz-surface);
}
.source-ledger > header {
  min-height: 72px;
  display: flex;
  align-items: center;
  padding: 0 18px;
  border-bottom: 0;
}
.source-heading h2 {
  margin: 0;
  color: var(--lz-text-strong);
  font-size: 18px;
  font-weight: 800;
}
.source-groups {
  min-height: 0;
  overflow: auto;
  padding: 0 8px 14px;
}
.source-group,
.course-change-group {
  border: 0;
}
.source-group + .source-group {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--lz-border);
}
.source-group > header {
  height: 30px;
  padding: 0 10px;
  color: var(--lz-text-muted);
  background: transparent;
  font-size: 11px;
  font-weight: 700;
}
.source-group > header small {
  min-width: 20px;
  color: var(--lz-text-muted);
  text-align: right;
}
.source-list {
  display: grid;
  gap: 2px;
}
.source-list > button {
  width: 100%;
  min-height: 52px;
  display: grid;
  grid-template-columns: 25px minmax(0, 1fr) auto;
  align-items: center;
  gap: 7px;
  padding: 7px 9px;
  border: 0;
  border-radius: 9px;
  color: var(--lz-text-secondary);
  background: transparent;
}
.source-list > button.no-row-status {
  grid-template-columns: 25px minmax(0, 1fr);
}
.source-list > button:hover { background: #f7f7fb; }
.source-list > button.active {
  color: var(--lz-brand-strong);
  background: #f0efff;
}
.source-icon {
  width: 25px;
  height: 25px;
  display: grid !important;
  place-items: center;
  border-radius: 0;
  color: #667085;
  background: transparent;
}
.source-list > button.active .source-icon { color: var(--lz-brand-strong); }
.source-list > button span:not(.source-icon) { gap: 4px; }
.source-list > button b {
  color: inherit;
  font-size: 11px;
  font-weight: 700;
}
.source-list > button small {
  color: var(--lz-text-muted);
  font-size: 9px;
}
.source-list > button i {
  padding: 3px 5px;
  font-size: 8px;
}
.source-empty {
  padding: 18px 10px;
  color: var(--lz-text-muted);
  font-size: 11px;
}
.source-ledger-footer {
  display: grid;
  gap: 7px;
  padding: 11px 12px 13px;
  border-top: 1px solid var(--lz-border);
  background: var(--lz-surface);
}
.source-ledger-footer > small {
  color: var(--lz-text-muted);
  font-size: 9px;
  text-align: center;
}
.source-add-menu {
  position: relative;
  width: 100%;
}
.source-add-trigger {
  width: 100%;
  min-height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 0 10px;
  border: 0;
  border-radius: 8px;
  color: var(--lz-brand-strong);
  background: var(--lz-brand-soft);
  font-size: 11px;
  font-weight: 750;
  cursor: pointer;
}
.source-add-trigger:hover,
.source-add-trigger[aria-expanded="true"] { background: #e8e7ff; }
.source-add-trigger svg:last-child { margin-left: auto; }
.source-add-menu > div {
  top: auto;
  right: auto;
  bottom: calc(100% + 7px);
  left: 0;
  width: 244px;
  padding: 6px;
  border-color: var(--lz-border);
  border-radius: 10px;
  box-shadow: 0 14px 34px rgba(15, 23, 42, .14);
}
.source-add-menu > div button {
  min-height: 54px;
  border-radius: 7px;
}
.source-add-menu > div button b { font-size: 11px; }
.source-add-menu > div button small { font-size: 9px; }

.relationship-pane {
  min-width: 0;
  min-height: 0;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  overflow: hidden;
  border-right: 1px solid var(--lz-border);
  background: var(--lz-surface);
}
.content-header {
  min-height: 126px;
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 18px;
  padding: 24px 26px 18px;
  border-bottom: 1px solid var(--lz-border);
}
.content-heading {
  min-width: 0;
  display: grid;
  gap: 5px;
}
.content-heading > small {
  color: var(--lz-brand-strong);
  font-size: 10px;
  font-weight: 750;
}
.content-heading h2 {
  min-width: 0;
  margin: 0;
  overflow: hidden;
  color: var(--lz-text-strong);
  font-size: 22px;
  font-weight: 800;
  letter-spacing: -.018em;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.content-heading p {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0;
  color: var(--lz-warning);
  font-size: 10px;
}
.content-heading p[data-state="synced"] { color: var(--lz-success); }
.content-heading p[data-state="scanning"] { color: var(--lz-brand-strong); }
.content-heading p span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.content-heading p small {
  flex: none;
  color: var(--lz-text-muted);
  font-size: 9px;
}
.content-heading p small::before {
  margin-right: 6px;
  content: "·";
}
.content-operations {
  flex: none;
  display: flex;
  align-items: center;
  gap: 8px;
}
.relationship-view-switch,
.history-switch {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 3px;
  border: 1px solid var(--lz-border);
  border-radius: 8px;
  background: #f5f6fa;
}
.relationship-view-switch button,
.history-switch button {
  min-height: 30px;
  padding: 0 10px;
  border: 0;
  border-radius: 6px;
  color: var(--lz-text-secondary);
  background: transparent;
  font-size: 10px;
  font-weight: 700;
  cursor: pointer;
}
.relationship-view-switch button.active,
.history-switch button.active {
  color: var(--lz-brand-strong);
  background: var(--lz-surface);
  box-shadow: 0 1px 3px rgba(15, 23, 42, .08);
}
.rescan-button {
  min-height: 36px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 0 10px;
  border: 1px solid var(--lz-border);
  border-radius: 8px;
  color: var(--lz-text-secondary);
  background: var(--lz-surface);
  font-size: 10px;
  font-weight: 700;
  cursor: pointer;
}
.rescan-button:hover {
  color: var(--lz-brand-strong);
  border-color: var(--lz-brand-border);
}
.rescan-button:disabled,
.source-ledger button:disabled,
.detail-actions button:disabled { opacity: .45; cursor: not-allowed; }

.relationship-tree,
.relationship-table {
  min-height: 0;
  overflow: auto;
  padding: 18px 26px 28px;
}
.relationship-group {
  margin: 0 0 18px;
  padding: 0;
}
.relationship-group::before,
.relationship-group > header > span { display: none; }
.relationship-group > header {
  min-height: 32px;
  gap: 6px;
}
.relationship-group > header strong {
  color: var(--lz-text-strong);
  font-size: 12px;
}
.relationship-group > header small {
  color: var(--lz-text-muted);
  font-size: 10px;
}
.relationship-group > div {
  margin-left: 0;
  border-color: var(--lz-border);
  border-radius: 8px;
}
.relationship-group button {
  min-height: 46px;
  padding: 0 12px;
  color: var(--lz-text-secondary);
  font-size: 11px;
}
.relationship-group button:hover,
.relationship-group button.active { background: #f8f8ff; }
.relationship-group button.active { color: var(--lz-brand-strong); }
.relationship-group button small,
.relationship-group button b { font-size: 9px; }
.unaffected-row {
  margin-top: 8px;
  padding: 10px 12px;
  border-color: var(--lz-border);
  background: #f8fafc;
}
.relationship-table > header,
.relationship-table > button {
  grid-template-columns: minmax(130px, 1fr) 70px 100px 48px;
}
.relationship-table > header { font-size: 10px; }
.relationship-table > button {
  min-height: 46px;
  font-size: 11px;
}
.relationship-empty {
  min-height: 0;
  display: grid;
  place-content: center;
  justify-items: center;
  gap: 9px;
  padding: 28px;
  color: var(--lz-text-muted);
}
.relationship-empty strong {
  color: var(--lz-text-secondary);
  font-size: 13px;
}
.relationship-empty p { font-size: 10px; }

.detail-pane {
  min-width: 0;
  min-height: 0;
  display: grid;
  grid-template-rows: 50px minmax(0, 1fr) auto;
  overflow: hidden;
  background: var(--lz-surface);
}
.detail-pane > .pane-header {
  position: static;
  min-height: 50px;
  padding: 0 14px;
  border-bottom: 1px solid var(--lz-border);
}
.pane-header h2 {
  margin: 0;
  color: var(--lz-text-strong);
  font-size: 13px;
}
.detail-pane > .pane-header > span { font-size: 9px; }
.close-detail-mode {
  width: 28px;
  height: 28px;
  display: grid;
  place-items: center;
  border: 0;
  border-radius: 6px;
  color: var(--lz-text-secondary);
  background: #f5f6f8;
  cursor: pointer;
}
.close-detail-mode:hover { color: var(--lz-brand-strong); }
.close-detail-mode:focus-visible {
  outline: 2px solid var(--lz-brand);
  outline-offset: 2px;
}
.detail-body {
  min-height: 0;
  overflow: auto;
}
.detail-source,
.detail-section-selector,
.structured-preview,
.material-decisions,
.protection-note,
.execution-scope {
  margin: 0 14px;
  padding: 14px 0;
  border-bottom-color: var(--lz-border);
}
.detail-source > small,
.detail-section-selector > small,
.material-decisions label > span {
  color: var(--lz-text-muted);
  font-size: 10px;
}
.detail-source > div {
  padding: 10px;
  border-color: var(--lz-border);
}
.detail-source strong { font-size: 11px; }
.detail-source small,
.detail-source button { font-size: 9px; }
.material-decisions {
  grid-template-columns: 1fr;
  gap: 10px;
}
.material-decisions > header { grid-column: 1; }
.material-decisions select,
.detail-section-selector select {
  height: 34px;
  border-color: var(--lz-border);
  color: var(--lz-text-secondary);
  font-size: 10px;
}
.structured-preview > header strong,
.material-decisions > header strong,
.execution-scope > strong { font-size: 11px; }
.structured-preview > header small,
.material-decisions > header small { font-size: 9px; }
.structured-preview p {
  font-size: 10px;
  line-height: 1.6;
}
.protection-note strong { font-size: 11px; }
.protection-note small,
.execution-scope label { font-size: 10px; }
.execution-scope { gap: 10px; }
.detail-empty {
  min-height: 100%;
  color: var(--lz-text-muted);
}
.detail-empty strong {
  color: var(--lz-text-secondary);
  font-size: 11px;
}
.detail-actions {
  display: grid;
  gap: 8px;
  padding: 11px 12px 12px;
  border-top: 1px solid var(--lz-border);
  background: var(--lz-surface);
}
.detail-actions > small {
  overflow: hidden;
  color: var(--lz-text-muted);
  font-size: 9px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.detail-actions > div {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 7px;
}
.detail-actions button {
  min-height: 36px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 0 10px;
  border: 1px solid var(--lz-border);
  border-radius: 8px;
  color: var(--lz-text-secondary);
  background: var(--lz-surface);
  font-size: 10px;
  font-weight: 700;
  cursor: pointer;
}
.detail-actions button.primary {
  border-color: var(--lz-brand);
  color: #fff;
  background: var(--lz-brand);
}
.history-panel { padding: 14px; }
.history-panel > header strong { font-size: 12px; }
.history-switch { margin-top: 0; }
.history-switch button { flex: 1; }
.history-panel li b { font-size: 10px; }
.history-panel li small,
.history-panel time { font-size: 9px; }

.course-change-surface {
  grid-column: 2 / 4;
  border: 0;
}

@media (max-width: 1180px) {
  .update-center-grid { grid-template-columns: 188px minmax(0, 1fr) 292px; }
  .content-header { padding-right: 18px; padding-left: 20px; }
  .content-heading h2 { font-size: 19px; }
  .content-heading p small { display: none; }
  .source-ledger > header { padding: 0 14px; }
  .source-heading h2 { font-size: 16px; }
  .rescan-button { width: 36px; padding: 0; font-size: 0; }
  .rescan-button svg { margin: auto; }
}

@media (prefers-reduced-motion: reduce) {
  .spin { animation: none; }
}
</style>
