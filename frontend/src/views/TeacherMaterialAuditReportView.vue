<template>
  <main class="update-center-page">
    <Teleport to="#app-header-route-context">
      <div class="update-route-context">
        <button type="button" :aria-label="returnLabel" @click="backToWorkbench"><ArrowLeft :size="17" /></button>
        <ScanSearch :size="18" />
        <div>
          <h1>{{ t('courseAuditUpdates.title', '审计与更新中心') }}</h1>
          <small>{{ courseName || t('courseAuditUpdates.subtitle', '课程材料审计与结构化同源更新') }}</small>
        </div>
      </div>
    </Teleport>

    <Teleport to="#app-header-route-actions">
      <div class="update-route-actions">
        <button type="button" @click="showHistory('execution')"><History :size="15" />{{ t('courseAuditUpdates.executionHistory', '执行记录') }}</button>
        <button type="button" @click="showHistory('version')"><Clock3 :size="15" />{{ t('courseAuditUpdates.versionHistory', '版本历史') }}</button>
        <button class="primary" type="button" @click="backToWorkbench">{{ returnLabel }}<ArrowRight :size="15" /></button>
      </div>
    </Teleport>

    <section v-if="center.loading && !center.sources.length" class="center-state" role="status">
      <LoaderCircle :size="22" class="spin" />{{ t('courseAuditUpdates.loading', '正在读取材料、课程结构和历史变化…') }}
    </section>

    <section v-else class="update-center-shell" :class="{ 'has-error': Boolean(center.error || auditStore.error) }">
      <header class="update-status-strip" :data-state="statusTone">
        <div>
          <CircleCheckBig v-if="statusTone === 'synced'" :size="18" />
          <LoaderCircle v-else-if="center.loading || auditStore.refreshing" :size="18" class="spin" />
          <TriangleAlert v-else :size="18" />
          <strong>{{ statusSummary }}</strong>
        </div>
        <small>{{ lastAppliedLabel }}</small>
        <button type="button" :disabled="center.loading || auditStore.refreshing" @click="refreshAll">
          <RefreshCw :size="14" :class="{ spin: center.loading || auditStore.refreshing }" />
          {{ t('courseAuditUpdates.rescan', '重新扫描') }}
        </button>
      </header>

      <p v-if="center.error || auditStore.error" class="center-error" role="alert">
        <TriangleAlert :size="15" />{{ center.error || auditStore.error }}
      </p>

      <div class="update-center-grid" :class="{ 'is-course-change': isCourseChangeMode }">
        <aside class="source-ledger">
          <header>
            <div><h2>{{ t('courseAuditUpdates.changeSources', '变化来源') }}</h2><Info :size="14" /></div>
            <span>
              <input ref="fileInput" hidden type="file" multiple @change="captureFiles">
              <button type="button" :disabled="uploading || !coursePackage" @click="fileInput?.click()">
                <LoaderCircle v-if="uploading" :size="14" class="spin" /><Upload v-else :size="14" />
                {{ t('courseAuditUpdates.uploadReplace', '上传/替换') }}
              </button>
              <button class="new-change-button" type="button" @click="startNewCourseChange"><Sparkles :size="14" />{{ t('courseAuditUpdates.newCourseChange', '提出调整') }}</button>
            </span>
          </header>

          <div class="source-filters">
            <select v-model="documentTypeFilter" :aria-label="t('courseAuditUpdates.filterType', '筛选材料类型')">
              <option value="">{{ t('courseAuditUpdates.allTypes', '全部类型') }}</option>
              <option value="outline">{{ t('courseFiles.preparation.documentTypes.outline', '课程大纲') }}</option>
              <option value="lesson_plan">{{ t('courseFiles.preparation.documentTypes.lessonPlan', '教案') }}</option>
              <option value="script">{{ t('courseFiles.preparation.documentTypes.script', '讲稿') }}</option>
              <option value="ppt">{{ t('courseFiles.preparation.documentTypes.ppt', 'PPT') }}</option>
            </select>
            <select v-model="sourceStateFilter" :aria-label="t('courseAuditUpdates.filterState', '筛选变化状态')">
              <option value="">{{ t('courseAuditUpdates.allStates', '全部状态') }}</option>
              <option value="changed">{{ t('courseAuditUpdates.changed', '有变化') }}</option>
              <option value="applied">{{ t('courseAuditUpdates.synced', '已同步') }}</option>
              <option value="failed">{{ t('courseAuditUpdates.needsAttention', '需处理') }}</option>
            </select>
          </div>

          <section class="source-group">
            <header><strong>{{ t('courseAuditUpdates.materialChanges', '材料变化') }}</strong><small>{{ filteredMaterialSources.length }}</small></header>
            <div class="source-list">
              <button
                v-for="source in filteredMaterialSources"
                :key="source.key"
                type="button"
                :class="{ active: center.activeSourceKey === source.key }"
                :data-status="source.status"
                @click="selectMaterialSource(source.key)"
              >
                <component :is="sourceIcon(source.material?.document_type)" :size="17" />
                <span><b>{{ source.title }}</b><small>{{ materialRoleLabel(source.material) }} · {{ parseQualityLabel(source.material) }}</small></span>
                <em>{{ materialVersionLabel(source.material) }}</em>
                <i>{{ sourceStatusLabel(source.status) }}</i>
              </button>
              <p v-if="!filteredMaterialSources.length" class="source-empty">{{ t('courseAuditUpdates.noMaterials', '还没有符合条件的材料') }}</p>
            </div>
          </section>

          <section class="source-group course-change-group">
            <header><strong>{{ t('courseAuditUpdates.courseChanges', '全课调整') }}</strong><small>{{ center.courseChangeSources.length }}</small></header>
            <div class="source-list">
              <button
                v-for="source in center.courseChangeSources"
                :key="source.key"
                type="button"
                :class="{ active: center.activeSourceKey === source.key }"
                :data-status="source.status"
                @click="selectCourseChange(source.key, source.sourceId)"
              >
                <GitBranchPlus :size="17" />
                <span><b>{{ source.title }}</b><small>{{ formatTime(source.updatedAt) || t('courseAuditUpdates.pendingTime', '待处理') }}</small></span>
                <i>{{ sourceStatusLabel(source.status) }}</i>
              </button>
              <button class="create-change-row" type="button" :class="{ active: center.activeSourceKey === 'new-change' }" @click="startNewCourseChange">
                <Plus :size="16" /><span><b>{{ t('courseAuditUpdates.describeChange', '描述一次新的全课调整') }}</b><small>{{ t('courseAuditUpdates.scanHint', '统一扫描大纲、教案、讲稿与 PPT') }}</small></span>
              </button>
            </div>
          </section>

          <footer>
            <span>{{ t('courseAuditUpdates.sourceCount', '共 {count} 个来源').replace('{count}', String(center.sources.length)) }}</span>
            <span>{{ t('courseAuditUpdates.pendingCount', '{count} 项待处理').replace('{count}', String(center.pendingCount)) }}</span>
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
          />
        </section>

        <template v-else>
          <section class="relationship-pane">
            <header class="pane-header">
              <h2>{{ t('courseAuditUpdates.relationships', '生成关系') }}</h2>
              <nav :aria-label="t('courseAuditUpdates.relationshipView', '生成关系视图')">
                <button type="button" :class="{ active: relationshipView === 'relation' }" @click="relationshipView = 'relation'">{{ t('courseAuditUpdates.relation', '关系') }}</button>
                <button type="button" :class="{ active: relationshipView === 'list' }" @click="relationshipView = 'list'">{{ t('courseAuditUpdates.list', '列表') }}</button>
              </nav>
            </header>

            <div v-if="selectedMaterial" class="selected-source-card">
              <component :is="sourceIcon(selectedMaterial.document_type)" :size="20" />
              <span><strong>{{ selectedMaterial.filename }}</strong><small>{{ materialVersionLabel(selectedMaterial) }} · {{ t('courseAuditUpdates.currentChangeSource', '本次变化来源') }}</small></span>
              <b>{{ parseQualityLabel(selectedMaterial) }}</b>
            </div>

            <div v-if="relationshipView === 'relation'" class="relationship-tree">
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

            <div v-else class="relationship-table">
              <header><span>{{ t('courseAuditUpdates.generatedObject', '生成对象') }}</span><span>{{ t('courseAuditUpdates.sourceRole', '来源作用') }}</span><span>{{ t('courseAuditUpdates.structure', '结构') }}</span><span>{{ t('courseAuditUpdates.state', '状态') }}</span></header>
              <button v-for="target in selectedMaterialTargets" :key="target.target_id" type="button" :class="{ active: selectedTargetId === target.target_id }" @click="selectTarget(target.target_id)">
                <span><component :is="targetIcon(target.target_type)" :size="15" />{{ target.title }}</span><span>{{ sourceRoleForTarget(target) }}</span><span>{{ relationshipItemSummary(target) }}</span><b>{{ targetStatusLabel(target) }}</b>
              </button>
            </div>

            <div v-if="!selectedMaterialTargets.length" class="relationship-empty">
              <Link2Off :size="24" /><strong>{{ t('courseAuditUpdates.noRelationship', '这份材料尚未进入生成关系') }}</strong><p>{{ t('courseAuditUpdates.noRelationshipHint', '先确认材料类型、版本与用途，再重新扫描。') }}</p>
            </div>
          </section>

          <aside class="detail-pane">
            <header class="pane-header"><h2>{{ detailTitle }}</h2><span v-if="selectedTarget" :data-status="targetStatus(selectedTarget)">{{ targetStatusLabel(selectedTarget) }}</span></header>

            <template v-if="detailMode !== 'detail'">
              <section class="history-panel">
                <header><History :size="16" /><strong>{{ historyTitle }}</strong><button type="button" @click="detailMode = 'detail'"><X :size="14" /></button></header>
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
                <label><span>{{ t('courseAuditUpdates.documentType', '材料类型') }}</span><select :value="selectedMaterial.document_type" :disabled="materialBusy" @change="changeDocumentType"><option value="outline">{{ t('courseFiles.preparation.documentTypes.outline', '课程大纲') }}</option><option value="lesson_plan">{{ t('courseFiles.preparation.documentTypes.lessonPlan', '教案') }}</option><option value="script">{{ t('courseFiles.preparation.documentTypes.script', '讲稿') }}</option><option value="ppt">{{ t('courseFiles.preparation.documentTypes.ppt', 'PPT') }}</option><option value="other">{{ t('courseFiles.preparation.documentTypes.other', '其他资料') }}</option></select></label>
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

            <section v-else class="detail-empty"><ScanSearch :size="25" /><strong>{{ t('courseAuditUpdates.selectSource', '选择一个变化来源查看生成关系') }}</strong></section>
          </aside>
        </template>
      </div>

      <footer v-if="!isCourseChangeMode" class="center-actionbar">
        <div><strong>{{ actionSummary }}</strong><small>{{ t('courseAuditUpdates.actionBoundary', '只处理老师确认的范围；其他内容保持当前版本。') }}</small></div>
        <button type="button" :disabled="auditStore.executing || !selectedTarget" @click="executionScope = 'skip'">{{ t('courseAuditUpdates.saveForLater', '保存判断，稍后处理') }}</button>
        <button class="primary" type="button" :disabled="!canExecuteSelection" @click="executeSelection">
          <LoaderCircle v-if="auditStore.executing" :size="15" class="spin" /><Check v-else :size="15" />{{ executeLabel }}
        </button>
      </footer>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch, type Component } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ArrowLeft, ArrowRight, BookOpenText, Check, ChevronDown, CircleCheckBig, Clock3,
  FileText, GitBranchPlus, History, Info, Link2Off, LoaderCircle, Plus, Presentation,
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
const evolutionWorkspaceRef = ref<{ openPlan?: (id: string) => void; startNewRequest?: () => void } | null>(null)
const selectedTargetId = ref('')
const selectedSectionId = ref('')
const relationshipView = ref<'relation' | 'list'>('relation')
const detailMode = ref<'detail' | 'execution' | 'version' | 'unaffected'>('detail')
const executionScope = ref<'current' | 'all' | 'skip'>('current')
const documentTypeFilter = ref('')
const sourceStateFilter = ref('')
const uploading = ref(false)

const courseId = computed(() => String(props.courseId || route.params.courseId || ''))
const coursePackage = computed(() => auditStore.coursePackage)
const plan = computed(() => auditStore.plan)
const courseName = computed(() => String(coursePackage.value?.course_name || evolutionStore.courseContext?.course_title || ''))
const activeSource = computed(() => center.activeSource)
const isCourseChangeMode = computed(() => ['course_change', 'new_change'].includes(activeSource.value?.kind || ''))
const activeCoursePlanId = computed(() => activeSource.value?.kind === 'course_change' ? activeSource.value.sourceId : '')
const selectedMaterial = computed(() => activeSource.value?.kind === 'material' ? activeSource.value.material || null : null)
const filteredMaterialSources = computed(() => center.materialSources.filter(source => (
  (!documentTypeFilter.value || source.material?.document_type === documentTypeFilter.value)
  && (!sourceStateFilter.value || source.status === sourceStateFilter.value)
)))
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
  const labels: Record<string, string> = { outline: '课程大纲', lesson_plan: '教案', script: '讲稿', ppt: 'PPT' }
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
const historyTitle = computed(() => detailTitle.value)
const historyItems = computed(() => {
  if (detailMode.value === 'unaffected') return (plan.value?.targets || []).filter(target => !selectedMaterialTargets.value.some(item => item.target_id === target.target_id)).map(target => ({ key: target.target_id, title: target.title, detail: t('courseAuditUpdates.notReferenced', '未引用当前变化来源，保持当前版本'), time: '', status: 'unchanged' }))
  const materialItems = (plan.value?.execution?.receipts || []).map(receipt => ({ key: receipt.bundle_id, title: t('courseAuditUpdates.materialExecution', '材料结构化执行'), detail: `${receipt.target_ids?.length || 0} ${t('courseAuditUpdates.objects', '个对象')} · ${receipt.status}`, time: formatTime(receipt.executed_at), status: receipt.status.includes('failed') ? 'failed' : 'applied' }))
  const courseItems = center.courseChangeSources.map(source => ({ key: source.key, title: source.title, detail: source.subtitle, time: formatTime(source.updatedAt), status: source.status }))
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
function materialVersionLabel(asset?: MaterialAuditAsset) { return ({ current: 'V当前', older: 'V历史', reference: 'V参考', unknown: 'V待确认' } as Record<string, string>)[asset?.version_role || 'unknown'] }
function parseQualityLabel(asset?: MaterialAuditAsset) {
  if (asset?.parse_status === 'failed') return t('courseAuditUpdates.parseLow', '解析失败')
  if (asset?.parse_status === 'degraded' || asset?.parse_warnings?.length) return t('courseAuditUpdates.parseMedium', '解析需复核')
  return t('courseAuditUpdates.parseHigh', '高质量解析')
}
function sourceStatusLabel(status: CourseUpdateSource['status']) { return ({ changed: t('courseAuditUpdates.changed', '有变化'), pending: t('courseAuditUpdates.scanningShort', '扫描中'), ready: t('courseAuditUpdates.pendingReview', '待审阅'), applied: t('courseAuditUpdates.synced', '已同步'), failed: t('courseAuditUpdates.needsAttention', '需处理'), unchanged: t('courseAuditUpdates.unchanged', '不变') } as Record<string, string>)[status] }
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
async function startNewCourseChange() { center.selectSource('new-change'); await nextTick(); evolutionWorkspaceRef.value?.startNewRequest?.() }
function selectTarget(targetId: string) { selectedTargetId.value = targetId; detailMode.value = 'detail' }
function showHistory(mode: 'execution' | 'version' | 'unaffected') { if (isCourseChangeMode.value) return; detailMode.value = mode }
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
.update-center-page{height:100%;min-height:0;overflow:hidden;color:#253047;background:#f6f7fb}.update-route-context{min-width:0;display:flex;align-items:center;gap:9px}.update-route-context>button{width:34px;height:34px;display:grid;place-items:center;border:0;border-radius:8px;color:#64748b;background:transparent;cursor:pointer}.update-route-context>button:hover{color:#5148dc;background:#efeeff}.update-route-context>svg{flex:none;color:#5148dc}.update-route-context>div{min-width:0;display:grid;gap:1px}.update-route-context h1{margin:0;color:#172033;font-size:17px}.update-route-context small{overflow:hidden;color:#7c8798;font-size:10px;text-overflow:ellipsis;white-space:nowrap}.update-route-actions{display:flex;align-items:center;gap:8px}.update-route-actions button{min-height:36px;display:inline-flex;align-items:center;gap:7px;padding:0 11px;border:1px solid #dbe1e9;border-radius:8px;color:#475569;background:#fff;font-size:11px;font-weight:700;cursor:pointer}.update-route-actions button:hover{border-color:#b8b4f2;color:#4d46cf}.update-route-actions button.primary{border-color:#514bdc;color:#fff;background:#514bdc}.center-state{height:100%;display:grid;place-content:center;justify-items:center;gap:12px;color:#728096}.update-center-shell{height:100%;min-height:0;display:grid;grid-template-rows:auto minmax(0,1fr) auto;gap:0;padding:14px 18px 12px;box-sizing:border-box}.update-center-shell.has-error{grid-template-rows:auto auto minmax(0,1fr) auto}.update-status-strip{min-height:54px;display:grid;grid-template-columns:minmax(0,1fr) auto auto;align-items:center;gap:18px;padding:0 14px;border:1px solid #dfe4ec;border-radius:10px 10px 0 0;background:#fff}.update-status-strip>div{display:flex;align-items:center;gap:9px;color:#087354}.update-status-strip[data-state=changed]>div{color:#a35d00}.update-status-strip[data-state=scanning]>div{color:#5148dc}.update-status-strip strong{color:#273247;font-size:12px}.update-status-strip>small{color:#7a8595;font-size:9px}.update-status-strip>button{min-height:31px;display:inline-flex;align-items:center;gap:6px;padding:0 9px;border:1px solid #d9dee7;border-radius:7px;color:#596579;background:#fff;font-size:10px;font-weight:700;cursor:pointer}.center-error{display:flex;align-items:center;gap:7px;margin:0;padding:8px 12px;border-right:1px solid #f0c2bd;border-left:1px solid #f0c2bd;color:#b42318;background:#fff4f2;font-size:10px}.update-center-grid{min-height:0;display:grid;grid-template-columns:minmax(270px,.86fr) minmax(420px,1.25fr) minmax(310px,.9fr);overflow:hidden;border:1px solid #dfe4ec;border-top:0;background:#fff}.source-ledger,.relationship-pane,.detail-pane,.course-change-surface{min-width:0;min-height:0}.source-ledger{display:grid;grid-template-rows:auto auto minmax(0,1fr) auto;overflow:hidden;border-right:1px solid #dfe4ec;background:#fff}.source-ledger>header,.pane-header{min-height:49px;display:flex;align-items:center;justify-content:space-between;gap:8px;padding:0 13px;border-bottom:1px solid #e5e9ef}.source-ledger>header>div{display:flex;align-items:center;gap:5px}.source-ledger h2,.pane-header h2{margin:0;color:#24314a;font-size:13px}.source-ledger>header>div svg{color:#8791a1}.source-ledger>header>span{display:flex;gap:5px}.source-ledger>header button{min-height:30px;display:inline-flex;align-items:center;gap:5px;padding:0 8px;border:1px solid #d5dbe5;border-radius:7px;color:#5148dc;background:#fff;font-size:9px;font-weight:700;cursor:pointer}.source-ledger>header button.new-change-button{border-color:#d8d5ff;background:#f6f5ff}.source-filters{display:grid;grid-template-columns:1fr 1fr;gap:7px;padding:9px 12px;border-bottom:1px solid #e7ebf1}.source-filters select,.material-decisions select,.detail-section-selector select{min-width:0;height:31px;padding:0 25px 0 8px;border:1px solid #d7dde6;border-radius:7px;color:#566176;background:#fff;font-size:9px}.source-ledger>section{min-height:0;overflow:auto}.source-group{border-bottom:1px solid #e4e8ef}.source-group>header{height:32px;display:flex;align-items:center;justify-content:space-between;padding:0 12px;color:#5f6b7d;background:#f8f9fb;font-size:9px}.source-group>header small{color:#8b95a4}.source-list{display:grid}.source-list>button{position:relative;display:grid;grid-template-columns:20px minmax(0,1fr) auto;align-items:center;gap:7px;min-height:59px;padding:8px 10px;border:0;border-bottom:1px solid #edf0f4;color:#586479;background:#fff;text-align:left;cursor:pointer}.source-list>button:hover{background:#fafaff}.source-list>button.active{color:#4d46cf;background:#efeeff}.source-list>button>svg{color:#6172dc}.source-list>button span{min-width:0;display:grid;gap:3px}.source-list>button b{overflow:hidden;color:#263249;font-size:10px;text-overflow:ellipsis;white-space:nowrap}.source-list>button small{overflow:hidden;color:#7b8697;font-size:8px;text-overflow:ellipsis;white-space:nowrap}.source-list>button em{align-self:start;color:#596579;font-size:8px;font-style:normal}.source-list>button i{position:absolute;right:10px;bottom:8px;color:#16805f;font-size:8px;font-style:normal}.source-list>button[data-status=changed] i,.source-list>button[data-status=pending] i,.source-list>button[data-status=ready] i{color:#c26a00}.source-list>button[data-status=failed] i{color:#b42318}.source-list>button.create-change-row{min-height:53px}.source-empty{margin:0;padding:18px 12px;color:#8a94a4;font-size:9px;text-align:center}.course-change-group{min-height:142px}.source-ledger>footer{display:flex;justify-content:space-between;gap:8px;padding:9px 12px;border-top:1px solid #e0e5ec;color:#7d8796;background:#fff;font-size:8px}.relationship-pane{display:grid;grid-template-rows:auto auto minmax(0,1fr);overflow:hidden;border-right:1px solid #dfe4ec;background:#fff}.pane-header nav{display:flex;gap:2px}.pane-header nav button{min-height:31px;padding:0 9px;border:0;border-bottom:2px solid transparent;color:#7c8697;background:transparent;font-size:9px;cursor:pointer}.pane-header nav button.active{border-color:#5148dc;color:#5148dc;font-weight:800}.selected-source-card{display:grid;grid-template-columns:26px minmax(0,1fr) auto;align-items:center;gap:9px;margin:11px 13px 7px;padding:10px 12px;border:1px solid #d9d7ff;border-radius:8px;color:#5148dc;background:#f6f5ff}.selected-source-card span{min-width:0;display:grid;gap:3px}.selected-source-card strong{overflow:hidden;color:#263249;font-size:10px;text-overflow:ellipsis;white-space:nowrap}.selected-source-card small{color:#7b8498;font-size:8px}.selected-source-card b{color:#087354;font-size:8px}.relationship-tree{min-height:0;overflow:auto;padding:3px 13px 18px}.relationship-group{position:relative;margin-top:10px;padding-left:20px}.relationship-group::before{position:absolute;top:14px;bottom:7px;left:7px;border-left:1px solid #d8ddec;content:""}.relationship-group>header{position:relative;display:flex;align-items:center;gap:5px;min-height:28px}.relationship-group>header>span{position:absolute;left:-16px;width:7px;height:7px;border:2px solid #625be1;border-radius:50%;background:#fff}.relationship-group>header strong{color:#38445a;font-size:10px}.relationship-group>header small{color:#8a94a3;font-size:8px}.relationship-group>div{display:grid;margin-left:5px;border:1px solid #e1e5eb;border-radius:7px;overflow:hidden}.relationship-group button{display:grid;grid-template-columns:minmax(0,1fr) auto auto;align-items:center;gap:8px;min-height:38px;padding:0 10px;border:0;border-bottom:1px solid #edf0f3;color:#667085;background:#fff;font-size:9px;text-align:left;cursor:pointer}.relationship-group button:last-child{border-bottom:0}.relationship-group button:hover,.relationship-group button.active{background:#fafaff}.relationship-group button.active{color:#5148dc}.relationship-group button span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.relationship-group button small{color:#8a94a3;font-size:8px}.relationship-group button b{color:#919aaa;font-size:8px}.relationship-group button[data-status=pending] b,.relationship-group button[data-status=warning] b{color:#d26f00}.unaffected-row{width:100%;display:grid;grid-template-columns:16px minmax(0,1fr) auto;align-items:center;gap:7px;margin-top:13px;padding:9px 11px;border:1px solid #e0e5ec;border-radius:8px;color:#6e7888;background:#f8f9fb;text-align:left;cursor:pointer}.unaffected-row span{display:grid;gap:2px}.unaffected-row strong{font-size:9px}.unaffected-row small{font-size:8px}.unaffected-row b{color:#16805f;font-size:9px}.relationship-table{min-height:0;overflow:auto;padding:8px 13px 18px}.relationship-table>header,.relationship-table>button{display:grid;grid-template-columns:minmax(140px,1fr) 75px 110px 52px;gap:8px;align-items:center}.relationship-table>header{padding:7px 9px;color:#8a94a3;font-size:8px}.relationship-table>button{width:100%;min-height:42px;padding:0 9px;border:0;border-top:1px solid #e6e9ee;color:#5b6678;background:#fff;font-size:9px;text-align:left;cursor:pointer}.relationship-table>button.active{color:#5148dc;background:#f7f6ff}.relationship-table>button span:first-child{display:flex;align-items:center;gap:6px}.relationship-empty,.detail-empty{display:grid;place-content:center;justify-items:center;gap:7px;padding:24px;color:#8a94a3;text-align:center}.relationship-empty strong,.detail-empty strong{color:#596579;font-size:11px}.relationship-empty p{margin:0;font-size:9px}.detail-pane{display:block;overflow:auto;background:#fff}.detail-pane>.pane-header{position:sticky;z-index:2;top:0;background:#fff}.detail-pane>.pane-header>span{padding:4px 7px;border-radius:6px;color:#16805f;background:#edf8f4;font-size:8px}.detail-pane>.pane-header>span[data-status=pending],.detail-pane>.pane-header>span[data-status=warning]{color:#bd6500;background:#fff5e6}.detail-source,.detail-section-selector,.structured-preview,.material-decisions,.protection-note,.execution-scope{margin:0 13px;padding:13px 0;border-bottom:1px solid #e8ebf0}.detail-source>small,.detail-section-selector>small{display:block;margin-bottom:8px;color:#7c8797;font-size:8px;font-weight:700}.detail-source>div{display:grid;grid-template-columns:20px minmax(0,1fr) auto;align-items:center;gap:8px;padding:9px;border:1px solid #e0e5ec;border-radius:8px}.detail-source span{min-width:0;display:grid;gap:2px}.detail-source strong{overflow:hidden;color:#344054;font-size:9px;text-overflow:ellipsis;white-space:nowrap}.detail-source small{overflow:hidden;color:#8a94a3;font-size:8px;text-overflow:ellipsis;white-space:nowrap}.detail-source button{display:inline-flex;align-items:center;gap:3px;border:0;color:#5148dc;background:transparent;font-size:8px;font-weight:700;cursor:pointer}.detail-section-selector select{width:100%}.structured-preview>header,.material-decisions>header{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-bottom:9px}.structured-preview>header strong,.material-decisions>header strong,.execution-scope>strong{color:#3b4659;font-size:9px}.structured-preview>header small,.material-decisions>header small{color:#8b95a3;font-size:8px}.structured-preview>div{display:grid;gap:5px}.structured-preview p{margin:0;padding:7px 8px;border-radius:6px;color:#556071;background:#f7f8fa;font-size:8px;line-height:1.55}.structured-preview p span{margin-right:6px;color:#5148dc;font-weight:800}.preview-empty{color:#8a94a3!important;text-align:center}.material-decisions{display:grid;grid-template-columns:1fr 1fr;gap:8px}.material-decisions>header{grid-column:1/-1}.material-decisions label{display:grid;gap:4px}.material-decisions label>span{color:#788393;font-size:8px}.protection-note{display:grid;grid-template-columns:18px minmax(0,1fr);gap:8px;color:#087354}.protection-note span{display:grid;gap:3px}.protection-note strong{font-size:9px}.protection-note small{color:#5b776d;font-size:8px;line-height:1.5}.execution-scope{display:grid;gap:8px;border-bottom:0}.execution-scope label{display:flex;align-items:center;gap:7px;color:#596579;font-size:9px;cursor:pointer}.execution-scope input{position:absolute;opacity:0}.execution-scope label>span{width:13px;height:13px;border:1px solid #98a2b3;border-radius:50%;background:#fff}.execution-scope input:checked+span{border:4px solid #5148dc}.history-panel{padding:13px}.history-panel>header{display:grid;grid-template-columns:18px minmax(0,1fr) 28px;align-items:center;gap:7px;color:#5148dc}.history-panel>header strong{color:#344054;font-size:10px}.history-panel>header button{width:28px;height:28px;display:grid;place-items:center;border:0;border-radius:6px;color:#667085;background:#f5f6f8;cursor:pointer}.history-panel ol{display:grid;gap:0;margin:12px 0 0;padding:0;list-style:none}.history-panel li{display:grid;grid-template-columns:8px minmax(0,1fr) auto;gap:8px;padding:9px 0;border-bottom:1px solid #e8ebef}.history-panel li>span{width:7px;height:7px;margin-top:3px;border-radius:50%;background:#16a36a}.history-panel li[data-status=failed]>span{background:#d92d20}.history-panel li[data-status=ready]>span,.history-panel li[data-status=pending]>span{background:#e78b16}.history-panel li div{display:grid;gap:3px}.history-panel li b{color:#344054;font-size:9px}.history-panel li small,.history-panel time{color:#8a94a3;font-size:8px}.history-panel>p{color:#8a94a3;font-size:9px}.course-change-surface{grid-column:2/4;overflow:hidden;background:#fff}.center-actionbar{min-height:62px;display:grid;grid-template-columns:minmax(0,1fr) auto auto;align-items:center;gap:9px;padding:0 12px;border:1px solid #dfe4ec;border-top:0;border-radius:0 0 10px 10px;background:#fff}.center-actionbar>div{display:grid;gap:3px}.center-actionbar strong{color:#344054;font-size:10px}.center-actionbar small{color:#7e8897;font-size:8px}.center-actionbar>button{min-height:36px;display:inline-flex;align-items:center;gap:6px;padding:0 12px;border:1px solid #d7dde6;border-radius:8px;color:#5148dc;background:#fff;font-size:10px;font-weight:750;cursor:pointer}.center-actionbar>button.primary{border-color:#5148dc;color:#fff;background:#5148dc}.center-actionbar>button:disabled,.source-ledger button:disabled,.update-status-strip button:disabled{opacity:.45;cursor:not-allowed}.spin{animation:spin .85s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}@media(max-width:1180px){.update-center-grid{grid-template-columns:minmax(230px,.72fr) minmax(390px,1.18fr) minmax(280px,.82fr)}.source-ledger>header button{width:30px;padding:0;font-size:0}.source-ledger>header button svg{margin:auto}.relationship-group button{grid-template-columns:minmax(0,1fr) auto}.relationship-group button small{display:none}.material-decisions{grid-template-columns:1fr}}@media(prefers-reduced-motion:reduce){.spin{animation:none}}
</style>
