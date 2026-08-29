<template>
  <main class="audit-report-page">
    <Teleport to="#app-header-route-context">
      <div class="audit-route-context">
        <button type="button" :aria-label="t('common.back', '返回')" @click="backToWorkbench"><ArrowLeft :size="17" /></button>
        <ScanSearch :size="18" />
        <h1>{{ t('courseFiles.materialAuditReport.title', '课程材料审计报告') }}</h1>
        <small v-if="courseName">{{ courseName }}</small>
      </div>
    </Teleport>

    <Teleport to="#app-header-route-actions">
      <div class="audit-route-actions">
        <button type="button" :disabled="auditStore.refreshing" @click="refreshReport">
          <RefreshCw :size="15" :class="{ spin: auditStore.refreshing }" />
          {{ t('courseFiles.materialAuditReport.refresh', '重新审计') }}
        </button>
        <button class="primary" type="button" @click="backToWorkbench">
          {{ t('courseFiles.materialAuditReport.enterWorkbench', '进入备课工作台') }}<ArrowRight :size="15" />
        </button>
      </div>
    </Teleport>

    <section v-if="auditStore.loading" class="report-state" role="status">
      <LoaderCircle :size="22" class="spin" />{{ t('courseWorkbench.materialAudit.loading', '正在核对原文件与当前备课对象…') }}
    </section>
    <section v-else-if="!coursePackage" class="report-state">
      <FileQuestion :size="28" />
      <strong>{{ t('courseFiles.materialAuditReport.empty', '还没有可审计的课程材料') }}</strong>
      <button type="button" @click="backToWorkbench">{{ t('courseFiles.materialAuditReport.returnUpload', '返回上传材料') }}</button>
    </section>
    <section v-else class="report-shell">
      <header class="report-overview" :data-state="reportTone">
        <div>
          <span class="report-overview__icon"><ScanSearch :size="21" /></span>
          <span>
            <strong>{{ reportStatus }}</strong>
            <small>{{ t('courseFiles.materialAuditReport.boundary', '报告统一判断原始材料怎样进入大纲、教案、讲稿和 PPT；执行只生成工作稿。') }}</small>
          </span>
        </div>
        <dl>
          <div><dt>{{ sourceCount }}</dt><dd>{{ t('courseFiles.materialAuditReport.sourceFiles', '原始文件') }}</dd></div>
          <div><dt>{{ targetCount }}</dt><dd>{{ t('courseFiles.materialAuditReport.workObjects', '备课对象') }}</dd></div>
          <div><dt>{{ unresolvedCount }}</dt><dd>{{ t('courseFiles.materialAuditReport.needsDecision', '待确认') }}</dd></div>
          <div><dt>{{ executedCount }}</dt><dd>{{ t('courseFiles.materialAuditReport.workingDrafts', '已生成工作稿') }}</dd></div>
        </dl>
        <button
          class="execute-all"
          type="button"
          :disabled="!canExecuteAll || auditStore.executing"
          @click="executeAll"
        >
          <LoaderCircle v-if="auditStore.executing" :size="15" class="spin" />
          <WandSparkles v-else :size="15" />
          {{ allExecuted ? t('courseFiles.materialAuditReport.allCreated', '全部工作稿已生成') : t('courseWorkbench.materialAudit.executeAll', '生成全部工作稿') }}
        </button>
      </header>

      <p v-if="auditStore.error" class="report-error" role="alert">{{ auditStore.error }}</p>

      <section v-if="unresolvedItems.length" class="report-decisions">
        <header>
          <div><TriangleAlert :size="17" /><strong>{{ t('courseFiles.materialAuditReport.confirmTitle', '需要老师确认') }}</strong></div>
          <small>{{ t('courseFiles.materialAuditReport.confirmHelp', '这些判断会改变工作稿内容，确认后系统自动更新整份报告。') }}</small>
        </header>
        <ul>
          <li v-for="(item, index) in unresolvedItems" :key="`${item.code}-${item.asset_id || index}`">
            <span><strong>{{ issueTitle(item) }}</strong><small>{{ item.message }}</small></span>
            <select
              v-if="item.asset_id && isScopeIssue(item)"
              :value="assetById(item.asset_id)?.absorption_decision?.target_scope_id || ''"
              :disabled="isBusy(item.asset_id)"
              :aria-label="t('courseFiles.materialAuditReport.assignScope', '设置材料对应讲次')"
              @change="assignScope(item.asset_id, $event)"
            >
              <option value="" disabled>{{ t('courseFiles.materialAuditReport.chooseScope', '选择对应讲次') }}</option>
              <option v-for="scope in plan?.scope_options || []" :key="scope.scope_id" :value="scope.scope_id">{{ scope.label }}</option>
            </select>
          </li>
        </ul>
      </section>

      <section class="report-section report-files">
        <header>
          <div><h2>{{ t('courseFiles.materialAuditReport.fileConclusions', '文件审计结论') }}</h2><small>{{ t('courseFiles.materialAuditReport.fileHelp', '保留原件，只决定它在结构化工作稿中的位置和作用。') }}</small></div>
        </header>
        <div class="report-table" role="table" :aria-label="t('courseFiles.materialAuditReport.fileConclusions', '文件审计结论')">
          <div class="report-table__head" role="row">
            <span>{{ t('courseFiles.materialAuditReport.file', '文件') }}</span>
            <span>{{ t('courseFiles.materialAuditReport.type', '识别类型') }}</span>
            <span>{{ t('courseFiles.materialAuditReport.target', '对应对象') }}</span>
            <span>{{ t('courseFiles.materialAuditReport.version', '版本') }}</span>
            <span>{{ t('courseFiles.materialAuditReport.action', '处理方式') }}</span>
          </div>
          <div v-for="asset in coursePackage.assets" :key="asset.asset_id" class="report-table__row" role="row">
            <span class="file-cell"><FileText :size="16" /><span><strong>{{ asset.filename }}</strong><small>{{ parseLabel(asset) }} · {{ asset.relative_path }}</small></span></span>
            <select :value="asset.document_type" :disabled="isBusy(asset.asset_id)" @change="changeDocumentType(asset.asset_id, $event)">
              <option value="outline">{{ t('courseFiles.preparation.documentTypes.outline', '课程大纲') }}</option>
              <option value="lesson_plan">{{ t('courseFiles.preparation.documentTypes.lessonPlan', '教案') }}</option>
              <option value="script">{{ t('courseFiles.preparation.documentTypes.script', '讲稿') }}</option>
              <option value="ppt">{{ t('courseFiles.preparation.documentTypes.ppt', 'PPT') }}</option>
              <option value="question_bank">{{ t('courseFiles.preparation.documentTypes.questionBank', '题库与试卷') }}</option>
              <option value="school_material">{{ t('courseFiles.preparation.documentTypes.schoolMaterial', '教务材料') }}</option>
              <option value="other">{{ t('courseFiles.preparation.documentTypes.other', '其他资料') }}</option>
            </select>
            <span>{{ targetLabelForAsset(asset.asset_id) }}</span>
            <select :value="asset.version_role || 'unknown'" :disabled="isBusy(asset.asset_id)" @change="changeVersion(asset.asset_id, $event)">
              <option value="current">{{ t('courseFiles.preparation.versionRoles.current', '当前版本') }}</option>
              <option value="older">{{ t('courseFiles.preparation.versionRoles.older', '历史版本') }}</option>
              <option value="reference">{{ t('courseFiles.preparation.versionRoles.reference', '参考资料') }}</option>
              <option value="unknown">{{ t('courseFiles.preparation.versionRoles.unknown', '版本待确认') }}</option>
            </select>
            <select :value="asset.absorption_decision?.action || 'absorb'" :disabled="isBusy(asset.asset_id)" @change="changeAction(asset.asset_id, $event)">
              <option value="absorb">{{ t('courseFiles.materialAuditReport.absorb', '形成工作稿') }}</option>
              <option value="reference_only">{{ t('courseFiles.materialAuditReport.referenceOnly', '仅作参考') }}</option>
              <option value="ignore">{{ t('courseFiles.materialAuditReport.ignore', '本次不使用') }}</option>
            </select>
          </div>
        </div>
      </section>

      <section class="report-section report-targets">
        <header>
          <div><h2>{{ t('courseFiles.materialAuditReport.structureTitle', '结构化结果') }}</h2><small>{{ t('courseFiles.materialAuditReport.structureHelp', '这是执行后将写入各备课页面的工作稿结构。') }}</small></div>
        </header>
        <div class="target-list">
          <article v-for="target in plan?.targets || []" :key="target.target_id" class="target-row" :data-state="targetTone(target)">
            <header>
              <span class="target-kind">{{ targetTypeLabel(target.target_type) }}</span>
              <span><strong>{{ target.title }}</strong><small>{{ target.target_scope_label || t('courseFiles.materialAuditReport.courseLevel', '整课') }}</small></span>
              <b>{{ targetStatusLabel(target) }}</b>
            </header>
            <div class="target-sources">
              <span v-for="source in target.sources" :key="source.asset_id">
                <FileText :size="14" /><strong>{{ source.filename }}</strong>
                <select :value="source.role" :disabled="isBusy(source.asset_id)" @change="changeSourceRole(target, source, $event)">
                  <option value="primary">{{ t('courseWorkbench.materialAudit.primary', '主来源') }}</option>
                  <option value="reference">{{ t('courseWorkbench.materialAudit.reference', '参考来源') }}</option>
                </select>
              </span>
            </div>
            <ul v-if="targetFindings(target).length" class="target-findings">
              <li v-for="(issue, index) in targetFindings(target)" :key="`${issue.code}-${index}`"><TriangleAlert :size="13" />{{ issue.message }}</li>
            </ul>
            <details v-if="target.structured_draft" class="target-preview">
              <summary>
                {{ previewSummary(target) }}
                <ChevronDown :size="14" />
              </summary>
              <ol>
                <li v-for="section in target.structured_draft.sections" :key="section.section_id">
                  <strong>{{ section.title }}</strong><small>{{ section.blocks.length }} {{ t('courseWorkbench.materialAudit.blocks', '个内容块') }}</small>
                </li>
              </ol>
            </details>
            <footer>
              <RouterLink :to="targetRoute(target)">{{ t('courseFiles.materialAuditReport.viewInWorkbench', '到对应工作台查看') }}<ArrowRight :size="14" /></RouterLink>
              <button type="button" :disabled="!canExecuteTarget(target) || auditStore.executing" @click="executeTarget(target.target_id)">
                {{ targetExecuted(target.target_id) ? t('courseWorkbench.materialAudit.regenerateCurrent', '按当前审计重新整理') : t('courseWorkbench.materialAudit.executeCurrent', '整理当前工作稿') }}
              </button>
            </footer>
          </article>
        </div>
      </section>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ArrowLeft, ArrowRight, ChevronDown, FileQuestion, FileText, LoaderCircle,
  RefreshCw, ScanSearch, TriangleAlert, WandSparkles,
} from 'lucide-vue-next'
import { t } from '../shared/i18n'
import {
  useTeacherMaterialAuditStore,
  type MaterialAuditAsset,
  type MaterialAuditIssue,
  type MaterialAuditSource,
  type MaterialAuditTarget,
  type MaterialDocumentType,
} from '../stores/teacherMaterialAudit'

const props = defineProps<{ courseId: string }>()
const route = useRoute()
const router = useRouter()
const auditStore = useTeacherMaterialAuditStore()

const courseId = computed(() => String(props.courseId || route.params.courseId || ''))
const coursePackage = computed(() => auditStore.coursePackage)
const plan = computed(() => auditStore.plan)
const courseName = computed(() => String(coursePackage.value?.course_name || ''))
const sourceCount = computed(() => coursePackage.value?.asset_count || coursePackage.value?.assets.length || 0)
const targetCount = computed(() => plan.value?.targets.length || 0)
const unresolvedItems = computed(() => plan.value?.unresolved_items || [])
const unresolvedCount = computed(() => unresolvedItems.value.length)
const executedTargetIds = computed(() => new Set(
  (plan.value?.execution?.receipts || []).flatMap(receipt => receipt.target_ids || []),
))
const executedCount = computed(() => executedTargetIds.value.size)
const allExecuted = computed(() => Boolean(targetCount.value) && executedCount.value >= targetCount.value)
const canExecuteAll = computed(() => Boolean(targetCount.value && !unresolvedCount.value && !allExecuted.value))
const reportTone = computed(() => unresolvedCount.value ? 'warning' : allExecuted.value ? 'success' : 'ready')
const reportStatus = computed(() => {
  if (unresolvedCount.value) return t('courseFiles.materialAuditReport.statusNeedsDecision', '审计完成，部分判断需要老师确认')
  if (allExecuted.value) return t('courseFiles.materialAuditReport.statusExecuted', '审计已执行，工作稿已经生成')
  return t('courseFiles.materialAuditReport.statusReady', '审计完成，可以生成结构化工作稿')
})

function backToWorkbench() {
  void router.push({ name: 'course-workspace', params: { courseId: courseId.value, mode: 'build' } })
}
async function refreshReport() { await auditStore.refresh() }
async function executeAll() { await auditStore.execute() }
async function executeTarget(targetId: string) { await auditStore.execute([targetId]) }
function isBusy(assetId: string) { return auditStore.executing || auditStore.updatingAssetIds.includes(assetId) }
function assetById(assetId: string) { return coursePackage.value?.assets.find(asset => asset.asset_id === assetId) }
function isScopeIssue(issue: MaterialAuditIssue) { return ['target_scope_unresolved', 'lesson_scope_unresolved'].includes(issue.code) }
function issueTitle(issue: MaterialAuditIssue) { return issue.filename || assetById(String(issue.asset_id || ''))?.filename || issue.target_label || t('courseFiles.materialAuditReport.auditFinding', '审计发现') }
async function assignScope(assetId: string, event: Event) {
  await auditStore.updateDecision(assetId, { target_scope_id: (event.target as HTMLSelectElement).value, action: 'absorb' })
}
async function changeVersion(assetId: string, event: Event) {
  await auditStore.updateDecision(assetId, { version_role: (event.target as HTMLSelectElement).value as MaterialAuditAsset['version_role'] })
}
async function changeDocumentType(assetId: string, event: Event) {
  await auditStore.updateDocumentType(assetId, (event.target as HTMLSelectElement).value as MaterialDocumentType)
}
async function changeAction(assetId: string, event: Event) {
  await auditStore.updateDecision(assetId, { action: (event.target as HTMLSelectElement).value as 'absorb' | 'reference_only' | 'ignore' })
}
async function changeSourceRole(target: MaterialAuditTarget, source: MaterialAuditSource, event: Event) {
  const role = (event.target as HTMLSelectElement).value as 'primary' | 'reference'
  if (role === 'primary') {
    for (const current of target.sources.filter(item => item.asset_id !== source.asset_id && item.role === 'primary')) {
      await auditStore.updateDecision(current.asset_id, { role: 'reference', action: 'absorb' })
    }
  }
  await auditStore.updateDecision(source.asset_id, { role, action: 'absorb' })
}
function parseLabel(asset: MaterialAuditAsset) {
  if (asset.parse_status === 'failed') return t('courseWorkbench.materialAudit.parseFailed', '正文解析失败')
  if (asset.parse_status === 'degraded') return t('courseWorkbench.materialAudit.parseReview', '解析需复核')
  return t('courseWorkbench.materialAudit.parsed', '正文已解析')
}
function targetLabelForAsset(assetId: string) {
  const labels = (plan.value?.targets || []).filter(target => target.sources.some(source => source.asset_id === assetId)).map(target => target.title)
  return labels.length ? labels.join('、') : t('courseFiles.materialAuditReport.unassigned', '待确定')
}
function targetTypeLabel(type: MaterialAuditTarget['target_type']) {
  if (type === 'outline') return t('courseFiles.preparation.documentTypes.outline', '课程大纲')
  if (type === 'lesson_plan') return t('courseFiles.preparation.documentTypes.lessonPlan', '教案')
  if (type === 'script') return t('courseFiles.preparation.documentTypes.script', '讲稿')
  return t('courseFiles.preparation.documentTypes.ppt', 'PPT')
}
function targetExecuted(targetId: string) { return executedTargetIds.value.has(targetId) }
function targetFindings(target: MaterialAuditTarget) {
  return [...(target.issues || []), ...(target.review_items || []), ...unresolvedItems.value.filter(item => item.target_id === target.target_id)]
}
function targetTone(target: MaterialAuditTarget) { return targetFindings(target).length ? 'warning' : targetExecuted(target.target_id) ? 'success' : 'ready' }
function targetStatusLabel(target: MaterialAuditTarget) {
  if (targetFindings(target).length) return t('courseWorkbench.materialAudit.statusNeedsDecision', '需要确认')
  if (targetExecuted(target.target_id)) return t('courseWorkbench.materialAudit.draftCreated', '工作稿已生成')
  return t('courseFiles.materialAuditReport.ready', '可执行')
}
function canExecuteTarget(target: MaterialAuditTarget) { return Boolean(target.structured_draft && !targetFindings(target).some(issue => !['source_parse_review_required', 'reference_source_not_parsed'].includes(issue.code))) }
function previewSummary(target: MaterialAuditTarget) {
  const sections = target.structured_draft?.sections || []
  const blocks = sections.reduce((total, section) => total + section.blocks.length, 0)
  return t('courseWorkbench.materialAudit.previewSummary', '{sections} 个结构段 · {blocks} 个内容块').replace('{sections}', String(sections.length)).replace('{blocks}', String(blocks))
}
function targetRoute(target: MaterialAuditTarget) {
  const stage = target.target_type === 'outline' ? 'foundation' : target.target_type === 'lesson_plan' ? 'lesson' : target.target_type
  const lesson = target.target_type === 'outline' ? '' : target.target_scope_id
  return { name: 'course-workspace', params: { courseId: courseId.value, mode: 'build' }, query: { stage, ...(lesson ? { lesson } : {}) } }
}

onMounted(() => { if (courseId.value) void auditStore.load(courseId.value) })
</script>

<style scoped>
.audit-report-page{height:100%;min-height:0;overflow:auto;color:#273247;background:#f6f7fb}.audit-route-context{min-width:0;display:flex;align-items:center;gap:9px}.audit-route-context>button{width:34px;height:34px;display:grid;place-items:center;border:0;border-radius:8px;color:#64748b;background:transparent;cursor:pointer}.audit-route-context>svg{color:#514bdc}.audit-route-context h1{margin:0;font-size:18px}.audit-route-context small{overflow:hidden;color:#7c8798;font-size:12px;text-overflow:ellipsis;white-space:nowrap}.audit-route-actions{display:flex;gap:8px}.audit-route-actions button{min-height:36px;display:inline-flex;align-items:center;gap:7px;padding:0 11px;border:1px solid #dbe1e9;border-radius:8px;color:#475569;background:#fff;font-size:12px;font-weight:700;cursor:pointer}.audit-route-actions button.primary{border-color:#514bdc;color:#fff;background:#514bdc}.report-state{min-height:360px;display:grid;place-content:center;justify-items:center;gap:12px;color:#728096}.report-state button{min-height:34px;padding:0 12px;border:1px solid #d7dce5;border-radius:8px;color:#514bdc;background:#fff;cursor:pointer}.report-shell{width:min(1120px,calc(100% - 40px));display:grid;gap:14px;margin:24px auto 48px}.report-overview{display:grid;grid-template-columns:minmax(0,1.5fr) auto auto;align-items:center;gap:24px;padding:20px 22px;border:1px solid #dfe5ed;border-radius:12px;background:#fff}.report-overview>div{min-width:0;display:flex;align-items:center;gap:12px}.report-overview__icon{width:42px;height:42px;display:grid;place-items:center;flex:none;border-radius:10px;color:#514bdc;background:#eef0ff}.report-overview[data-state="warning"] .report-overview__icon{color:#a16207;background:#fff5d8}.report-overview[data-state="success"] .report-overview__icon{color:#15825d;background:#eaf8f1}.report-overview>div>span:last-child{display:grid;gap:4px}.report-overview>div strong{font-size:16px}.report-overview>div small{color:#748094;font-size:11px;line-height:1.5}.report-overview dl{display:flex;margin:0}.report-overview dl>div{min-width:72px;padding:0 14px;border-left:1px solid #e5e9ef;text-align:center}.report-overview dt{font-size:20px;font-weight:800}.report-overview dd{margin:2px 0 0;color:#7a8596;font-size:10px}.execute-all{min-height:38px;display:flex;align-items:center;gap:7px;padding:0 13px;border:0;border-radius:8px;color:#fff;background:#514bdc;font-size:12px;font-weight:750;cursor:pointer}.execute-all:disabled{color:#8b95a5;background:#edf0f4;cursor:not-allowed}.report-error{margin:0;padding:10px 12px;border-radius:8px;color:#b42318;background:#fff1f0;font-size:12px}.report-decisions,.report-section{border:1px solid #e0e5ec;border-radius:12px;background:#fff}.report-decisions{border-color:#ecd7ad}.report-decisions>header,.report-section>header{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:15px 18px;border-bottom:1px solid #e7ebf0}.report-decisions>header>div{display:flex;align-items:center;gap:8px;color:#955b09}.report-decisions header small,.report-section header small{color:#7a8596;font-size:11px}.report-decisions ul{display:grid;margin:0;padding:0 18px;list-style:none}.report-decisions li{min-height:58px;display:grid;grid-template-columns:minmax(0,1fr) 190px;align-items:center;gap:16px;border-bottom:1px solid #edf0f3}.report-decisions li:last-child{border-bottom:0}.report-decisions li>span{display:grid;gap:3px}.report-decisions li small{color:#7a8596;font-size:11px}.report-decisions select,.report-table select,.target-sources select{height:31px;padding:0 25px 0 8px;border:1px solid #d8dee7;border-radius:7px;color:#475569;background:#fff;font-size:11px}.report-section h2{margin:0;font-size:15px}.report-section>header>div{display:grid;gap:3px}.report-table__head,.report-table__row{display:grid;grid-template-columns:minmax(230px,1.5fr) 110px minmax(150px,1fr) 130px 130px;align-items:center;gap:14px;padding:0 18px}.report-table__head{min-height:38px;color:#7a8596;background:#f8f9fb;font-size:10px;font-weight:700}.report-table__row{min-height:62px;border-top:1px solid #edf0f3;color:#4a5568;font-size:11px}.file-cell{min-width:0;display:flex;align-items:center;gap:9px;color:#6366f1}.file-cell>span{min-width:0;display:grid;gap:2px}.file-cell strong,.file-cell small{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.file-cell strong{color:#344054}.file-cell small{color:#7d8797;font-size:10px}.target-list{display:grid}.target-row{display:grid;gap:11px;padding:16px 18px;border-top:1px solid #e8ecf1}.target-row:first-child{border-top:0}.target-row>header{display:grid;grid-template-columns:68px minmax(0,1fr) auto;align-items:center;gap:12px}.target-kind{padding:5px 7px;border-radius:6px;color:#514bdc;background:#eef0ff;font-size:10px;font-weight:750;text-align:center}.target-row>header>span:nth-child(2){display:grid;gap:2px}.target-row>header small{color:#7c8798;font-size:10px}.target-row>header>b{color:#64748b;font-size:10px}.target-row[data-state="warning"]>header>b{color:#a16207}.target-row[data-state="success"]>header>b{color:#15825d}.target-sources{display:flex;flex-wrap:wrap;gap:7px;padding-left:80px}.target-sources>span{display:flex;align-items:center;gap:6px;padding:5px 6px 5px 8px;border:1px solid #e2e6ec;border-radius:7px;color:#64748b;background:#fafbfc;font-size:10px}.target-sources select{height:26px;border:0;background:transparent;font-size:10px}.target-findings{display:grid;gap:4px;margin:0;padding:8px 10px 8px 90px;border-radius:7px;color:#92600c;background:#fff8e7;font-size:10px;list-style:none}.target-findings li{display:flex;align-items:flex-start;gap:6px}.target-preview{margin-left:80px;padding:8px 10px;border-radius:7px;background:#f7f8fb}.target-preview summary{display:flex;align-items:center;justify-content:space-between;color:#64748b;font-size:10px;cursor:pointer;list-style:none}.target-preview summary::-webkit-details-marker{display:none}.target-preview[open] summary svg{transform:rotate(180deg)}.target-preview ol{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px;margin:9px 0 0;padding:0;list-style:none}.target-preview li{display:grid;gap:2px;padding:7px 8px;border:1px solid #e3e7ed;border-radius:6px;background:#fff}.target-preview li strong{font-size:10px}.target-preview li small{color:#8993a2;font-size:9px}.target-row footer{display:flex;justify-content:flex-end;gap:8px}.target-row footer a,.target-row footer button{min-height:31px;display:inline-flex;align-items:center;gap:5px;padding:0 9px;border:1px solid #d8dee7;border-radius:7px;color:#5156ba;background:#fff;font-size:10px;font-weight:700;text-decoration:none;cursor:pointer}.target-row footer button{border-color:#514bdc;color:#fff;background:#514bdc}.target-row footer button:disabled{border-color:#e3e6eb;color:#98a1af;background:#f0f2f5;cursor:not-allowed}.spin{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}
@media(max-width:900px){.report-shell{width:min(100% - 24px,1120px);margin-top:12px}.report-overview{grid-template-columns:1fr}.report-overview dl{justify-content:flex-start}.report-table{overflow:auto}.report-table__head,.report-table__row{min-width:850px}.target-sources,.target-preview{padding-left:0;margin-left:0}.target-preview ol{grid-template-columns:1fr}.audit-route-context small{display:none}}
</style>
