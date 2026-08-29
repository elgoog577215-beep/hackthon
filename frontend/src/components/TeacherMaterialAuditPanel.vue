<template>
  <section v-if="hasMaterialContext" class="material-audit" :data-state="statusTone">
    <header>
      <button type="button" :aria-expanded="expanded" @click="expanded = !expanded">
        <span class="material-audit__icon"><ScanSearch :size="17" /></span>
        <span>
          <strong>{{ t('courseWorkbench.materialAudit.title', '材料审计') }}</strong>
          <small>{{ statusLabel }}</small>
        </span>
        <span class="material-audit__counts">
          <b v-if="sourceCount">{{ t('courseWorkbench.materialAudit.sources', '{count} 份来源').replace('{count}', String(sourceCount)) }}</b>
          <b v-if="issueCount" class="needs-review">{{ t('courseWorkbench.materialAudit.issues', '{count} 项待确认').replace('{count}', String(issueCount)) }}</b>
        </span>
        <ChevronDown :size="16" :class="{ rotated: expanded }" />
      </button>
    </header>

    <div v-if="expanded" class="material-audit__body">
      <div v-if="auditStore.loading || auditStore.refreshing" class="material-audit__loading">
        <LoaderCircle :size="17" class="spin" />
        {{ t('courseWorkbench.materialAudit.loading', '正在核对原文件与当前备课对象…') }}
      </div>

      <template v-else>
        <section v-if="target" class="material-audit__sources">
          <header>
            <div><strong>{{ target.title }}</strong><small>{{ t('courseWorkbench.materialAudit.sourceHelp', '主来源形成工作稿，其他文件作为可追溯参考。') }}</small></div>
            <span>{{ targetExecuted ? t('courseWorkbench.materialAudit.draftCreated', '工作稿已生成') : t('courseWorkbench.materialAudit.notFormal', '不覆盖正式内容') }}</span>
          </header>
          <ul>
            <li v-for="source in target.sources" :key="source.asset_id">
              <FileText :size="16" />
              <span><strong>{{ source.filename }}</strong><small>{{ sourceLocation(source) }}</small></span>
              <select
                :value="source.role"
                :disabled="isBusy(source.asset_id)"
                :aria-label="t('courseWorkbench.materialAudit.sourceRole', '设置 {name} 的来源角色').replace('{name}', source.filename)"
                @change="changeSourceRole(source, $event)"
              >
                <option value="primary">{{ t('courseWorkbench.materialAudit.primary', '主来源') }}</option>
                <option value="reference">{{ t('courseWorkbench.materialAudit.reference', '参考来源') }}</option>
              </select>
            </li>
          </ul>
        </section>

        <section v-if="unassignedAssets.length" class="material-audit__unassigned">
          <header><TriangleAlert :size="16" /><strong>{{ t('courseWorkbench.materialAudit.unassigned', '这些材料还没有对应备课对象') }}</strong></header>
          <div v-for="asset in unassignedAssets" :key="asset.asset_id">
            <span><strong>{{ asset.filename }}</strong><small>{{ asset.relative_path }}</small></span>
            <button
              v-if="targetScopeId"
              type="button"
              :disabled="isBusy(asset.asset_id)"
              @click="assignToCurrent(asset.asset_id)"
            >{{ t('courseWorkbench.materialAudit.assignCurrent', '归到当前讲') }}</button>
          </div>
        </section>

        <section v-if="findings.length" class="material-audit__findings">
          <strong>{{ t('courseWorkbench.materialAudit.findings', '审计发现') }}</strong>
          <ul>
            <li v-for="(item, index) in findings" :key="`${item.code}-${item.asset_id || index}`">
              <TriangleAlert v-if="isBlocking(item)" :size="14" />
              <Info v-else :size="14" />
              <span>{{ item.message }}</span>
            </li>
          </ul>
        </section>

        <details v-if="target?.structured_draft" class="material-audit__preview">
          <summary>
            <strong>{{ t('courseWorkbench.materialAudit.preview', '结构化结果') }}</strong>
            <small>{{ previewSummary }}</small>
          </summary>
          <ol>
            <li v-for="section in target.structured_draft.sections.slice(0, 6)" :key="section.section_id">
              <span>{{ section.title }}</span>
              <small>{{ sourceRoleLabel(section.source_role as any) }} · {{ section.blocks.length }} {{ t('courseWorkbench.materialAudit.blocks', '个内容块') }}</small>
            </li>
          </ol>
        </details>

        <p v-if="auditStore.error" class="material-audit__error" role="alert">{{ auditStore.error }}</p>
        <footer>
          <span>{{ t('courseWorkbench.materialAudit.confirmationBoundary', '执行后只生成结构化工作稿，教师确认后才成为正式修订。') }}</span>
          <div>
            <button
              v-if="canExecuteAll && targetType === 'outline'"
              type="button"
              :disabled="auditStore.executing"
              @click="executeAll"
            >{{ t('courseWorkbench.materialAudit.executeAll', '生成全部工作稿') }}</button>
            <button
              class="primary"
              type="button"
              :disabled="!canExecuteCurrent || auditStore.executing"
              @click="executeCurrent"
            >
              <LoaderCircle v-if="auditStore.executing" :size="14" class="spin" />
              <WandSparkles v-else :size="14" />
              {{ targetExecuted
                ? t('courseWorkbench.materialAudit.regenerateCurrent', '按当前审计重新整理')
                : t('courseWorkbench.materialAudit.executeCurrent', '整理当前工作稿') }}
            </button>
          </div>
        </footer>
      </template>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ChevronDown, FileText, Info, LoaderCircle, ScanSearch, TriangleAlert, WandSparkles } from 'lucide-vue-next'
import { t } from '../shared/i18n'
import {
  useTeacherMaterialAuditStore,
  type MaterialAuditIssue,
  type MaterialAuditSource,
  type MaterialDocumentType,
} from '../stores/teacherMaterialAudit'

const props = defineProps<{
  courseId: string
  targetType: 'outline' | 'lesson_plan' | 'script' | 'ppt'
  targetScopeId?: string
}>()
const emit = defineEmits<{ executed: [] }>()
const auditStore = useTeacherMaterialAuditStore()
const expanded = ref(false)

const expectedTargetId = computed(() => {
  if (props.targetType === 'outline') return 'managed:outline'
  if (!props.targetScopeId) return ''
  const prefix = props.targetType === 'lesson_plan'
    ? 'lesson-plan'
    : props.targetType === 'script'
      ? 'script'
      : 'ppt-v6'
  return `${prefix}:${props.targetScopeId}`
})
const target = computed(() => (auditStore.plan?.targets || []).find(item => item.target_id === expectedTargetId.value))
const typedAssets = computed(() => (auditStore.coursePackage?.assets || []).filter(item => item.document_type === props.targetType as MaterialDocumentType))
const targetSourceIds = computed(() => new Set((target.value?.sources || []).map(item => item.asset_id)))
const unassignedAssets = computed(() => typedAssets.value.filter(asset => (
  !targetSourceIds.value.has(asset.asset_id)
  && !String(asset.absorption_decision?.target_scope_id || '')
  && !(asset.structure_matches || []).length
)))
const targetIssues = computed(() => (auditStore.plan?.unresolved_items || []).filter(item => item.target_id === expectedTargetId.value))
const findings = computed<MaterialAuditIssue[]>(() => [
  ...targetIssues.value,
  ...(target.value?.review_items || []),
  ...unassignedAssets.value.map(asset => ({
    code: 'target_scope_unresolved',
    asset_id: asset.asset_id,
    message: `${asset.filename} 尚未确定对应讲次。`,
  })),
])
const currentPlanReceipts = computed(() => (auditStore.plan?.execution?.receipts || []).filter(
  item => item.plan_id === auditStore.plan?.plan_id,
))
const targetExecuted = computed(() => currentPlanReceipts.value.some(item => (item.target_ids || []).includes(expectedTargetId.value)))
const allExecuted = computed(() => {
  const ids = new Set(currentPlanReceipts.value.flatMap(item => item.target_ids || []))
  return Boolean(auditStore.plan?.targets.length) && auditStore.plan!.targets.every(item => ids.has(item.target_id))
})
const sourceCount = computed(() => target.value?.sources.length || typedAssets.value.length)
const issueCount = computed(() => findings.value.filter(isBlocking).length)
const hasMaterialContext = computed(() => Boolean(
  auditStore.loading || auditStore.error || typedAssets.value.length || target.value,
))
const statusTone = computed(() => issueCount.value ? 'warning' : targetExecuted.value ? 'success' : target.value ? 'ready' : 'neutral')
const statusLabel = computed(() => {
  if (auditStore.loading || auditStore.refreshing) return t('courseWorkbench.materialAudit.statusLoading', '正在分析')
  if (issueCount.value) return t('courseWorkbench.materialAudit.statusNeedsDecision', '需要确认')
  if (targetExecuted.value) return t('courseWorkbench.materialAudit.statusCreated', '结构化工作稿已生成')
  if (target.value) return t('courseWorkbench.materialAudit.statusReady', '已就绪，可整理到当前页')
  return t('courseWorkbench.materialAudit.statusEmpty', '未上传对应材料')
})
const previewSummary = computed(() => {
  const sections = target.value?.structured_draft?.sections || []
  const blocks = sections.reduce((total, section) => total + section.blocks.length, 0)
  return t('courseWorkbench.materialAudit.previewSummary', '{sections} 个结构段 · {blocks} 个内容块')
    .replace('{sections}', String(sections.length))
    .replace('{blocks}', String(blocks))
})
const canExecuteCurrent = computed(() => Boolean(target.value && !targetIssues.value.length && target.value.structured_draft))
const canExecuteAll = computed(() => Boolean(auditStore.plan?.status === 'ready' && !allExecuted.value))

function isBlocking(issue: MaterialAuditIssue) {
  return !['source_parse_review_required', 'reference_source_not_parsed'].includes(issue.code)
}
function isBusy(assetId: string) {
  return auditStore.executing || auditStore.updatingAssetIds.includes(assetId)
}
function sourceRoleLabel(role: MaterialAuditSource['role']) {
  if (role === 'primary') return t('courseWorkbench.materialAudit.primary', '主来源')
  if (role === 'reference') return t('courseWorkbench.materialAudit.reference', '参考')
  return t('courseWorkbench.materialAudit.candidate', '待判断')
}
function sourceLocation(source: MaterialAuditSource) {
  const warnings = source.parse_warnings?.length || 0
  const parse = source.parse_status === 'degraded'
    ? t('courseWorkbench.materialAudit.parseReview', '解析需复核')
    : source.parse_status === 'failed'
      ? t('courseWorkbench.materialAudit.parseFailed', '正文解析失败')
      : t('courseWorkbench.materialAudit.parsed', '正文已解析')
  return `${source.relative_path} · ${parse}${warnings ? ` · ${warnings} 条提示` : ''}`
}
async function changeSourceRole(source: MaterialAuditSource, event: Event) {
  const select = event.target as HTMLSelectElement
  const role = select.value as 'primary' | 'reference'
  try {
    if (role === 'primary') {
      const otherPrimarySources = (target.value?.sources || []).filter(item => (
        item.asset_id !== source.asset_id && item.role === 'primary'
      ))
      for (const item of otherPrimarySources) {
        await auditStore.updateDecision(item.asset_id, { role: 'reference', action: 'absorb' })
      }
    }
    await auditStore.updateDecision(source.asset_id, { role, action: 'absorb' })
  } catch {
    select.value = source.role
  }
}
async function assignToCurrent(assetId: string) {
  if (!props.targetScopeId) return
  await auditStore.updateDecision(assetId, { target_scope_id: props.targetScopeId, action: 'absorb' })
}
async function executeCurrent() {
  if (!expectedTargetId.value) return
  await auditStore.execute([expectedTargetId.value])
  expanded.value = false
  emit('executed')
}
async function executeAll() {
  await auditStore.execute()
  expanded.value = false
  emit('executed')
}

watch(() => props.courseId, courseId => { if (courseId) void auditStore.load(courseId) })
watch([() => props.targetType, () => props.targetScopeId], () => { expanded.value = issueCount.value > 0 })
watch(issueCount, count => { if (count > 0) expanded.value = true })
onMounted(() => { if (props.courseId && auditStore.courseId !== props.courseId) void auditStore.load(props.courseId) })
</script>

<style scoped>
.material-audit{max-width:860px;margin:0 auto 12px;border:1px solid #dfe5ee;border-radius:10px;background:#fff;box-shadow:0 3px 12px rgba(30,41,59,.035)}
.material-audit[data-state="warning"]{border-color:#efd5aa}.material-audit[data-state="success"]{border-color:#bfe3d2}
.material-audit>header>button{width:100%;min-height:50px;display:grid;grid-template-columns:30px minmax(0,1fr) auto 18px;align-items:center;gap:9px;padding:7px 12px;border:0;border-radius:10px;color:#475569;background:transparent;text-align:left;cursor:pointer}
.material-audit__icon{width:28px;height:28px;display:grid;place-items:center;border-radius:8px;color:#4f46e5;background:#eef0ff}.material-audit[data-state="warning"] .material-audit__icon{color:#a16207;background:#fff7df}.material-audit[data-state="success"] .material-audit__icon{color:#15825d;background:#eaf8f1}
.material-audit>header button>span:nth-child(2){display:grid;gap:2px}.material-audit>header strong{color:#273247;font-size:13px}.material-audit>header small{color:#728096;font-size:11px}.material-audit__counts{display:flex;align-items:center;gap:6px}.material-audit__counts b{padding:4px 7px;border-radius:6px;color:#64748b;background:#f1f4f8;font-size:10px}.material-audit__counts b.needs-review{color:#9a5b08;background:#fff3d6}.material-audit>header svg.rotated{transform:rotate(180deg)}
.material-audit__body{display:grid;gap:14px;padding:0 16px 16px;border-top:1px solid #edf0f4}.material-audit__loading{min-height:72px;display:flex;align-items:center;justify-content:center;gap:8px;color:#64748b;font-size:12px}
.material-audit__sources{display:grid;gap:8px;padding-top:14px}.material-audit__sources>header{display:flex;align-items:flex-start;justify-content:space-between;gap:14px}.material-audit__sources>header>div{display:grid;gap:3px}.material-audit__sources>header>span{color:#64748b;font-size:10px}.material-audit__sources ul{display:grid;margin:0;padding:0;border-top:1px solid #edf0f4;list-style:none}.material-audit__sources li{min-height:54px;display:grid;grid-template-columns:18px minmax(0,1fr) auto;align-items:center;gap:9px;border-bottom:1px solid #edf0f4;color:#6366f1}.material-audit__sources li>span{min-width:0;display:grid;gap:2px}.material-audit__sources li strong{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.material-audit__sources li small{overflow:hidden;color:#7b8799;font-size:10px;text-overflow:ellipsis;white-space:nowrap}.material-audit__sources select{min-height:30px;padding:0 24px 0 8px;border:1px solid #d8dee8;border-radius:7px;color:#4f46e5;background:#fff;font-size:10px;font-weight:700;cursor:pointer}.material-audit__sources select:focus-visible{outline:2px solid #6366f1;outline-offset:2px}.material-audit__unassigned button{min-height:30px;padding:0 8px;border:1px solid #d8dee8;border-radius:7px;color:#4f46e5;background:#fff;font-size:10px;font-weight:700;cursor:pointer}
.material-audit__unassigned,.material-audit__findings,.material-audit__preview{display:grid;gap:8px;padding:10px 11px;border-radius:8px;background:#f8fafc}.material-audit__unassigned>header{display:flex;align-items:center;gap:7px;color:#9a670d}.material-audit__unassigned>div{display:flex;align-items:center;justify-content:space-between;gap:12px;padding-top:8px;border-top:1px solid #e8edf3}.material-audit__unassigned>div>span{display:grid;gap:2px}.material-audit__unassigned small{color:#7b8799;font-size:10px}.material-audit__findings>ul{display:grid;gap:6px;margin:0;padding:0;list-style:none}.material-audit__findings li{display:flex;align-items:flex-start;gap:7px;color:#6b7280;font-size:11px;line-height:1.5}.material-audit__findings li svg{flex:none;margin-top:1px;color:#b7791f}
.material-audit__preview>summary{display:flex;align-items:center;justify-content:space-between;gap:12px;color:#475569;cursor:pointer;list-style:none}.material-audit__preview>summary::-webkit-details-marker{display:none}.material-audit__preview>summary::after{color:#94a3b8;content:'+'}.material-audit__preview[open]>summary::after{content:'−'}.material-audit__preview>summary small{margin-left:auto;color:#728096;font-size:10px}.material-audit__preview ol{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px;margin:8px 0 0;padding:0;list-style:none}.material-audit__preview li{min-width:0;display:grid;gap:2px;padding:7px 8px;border:1px solid #e4e8ef;border-radius:7px;background:#fff}.material-audit__preview li span{overflow:hidden;color:#475569;font-size:11px;font-weight:700;text-overflow:ellipsis;white-space:nowrap}.material-audit__preview li small{color:#8791a1;font-size:9px}.material-audit__error{margin:0;padding:9px 10px;border-radius:7px;color:#b42318;background:#fff1f0;font-size:11px}
.material-audit footer{display:flex;align-items:center;justify-content:space-between;gap:16px;padding-top:2px}.material-audit footer>span{max-width:480px;color:#778195;font-size:10px;line-height:1.5}.material-audit footer>div{display:flex;gap:7px}.material-audit footer button{min-height:34px;padding:0 10px;border:1px solid #d7dde7;border-radius:7px;color:#475569;background:#fff;font-size:11px;font-weight:750;cursor:pointer}.material-audit footer button.primary{display:flex;align-items:center;gap:6px;border-color:#514bdc;color:#fff;background:#514bdc}.material-audit button:disabled{opacity:.45;cursor:not-allowed}.spin{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}
@media(max-width:760px){.material-audit__counts{display:none}.material-audit__preview ol{grid-template-columns:1fr}.material-audit footer{align-items:stretch;flex-direction:column}.material-audit footer>div{justify-content:flex-end}}
</style>
