<template>
  <Teleport to="body">
    <div v-if="open" class="impact-workspace-shell" @click.self="emit('close')">
      <section
        class="impact-workspace"
        :data-state="workspaceState"
        role="dialog"
        aria-modal="true"
        :aria-label="t('teachingRepresentations.impactDialog.workspaceTitle', '同源影响工作台')"
      >
        <header class="impact-workspace__header">
          <div class="impact-workspace__identity">
            <span><GitBranch :size="20" /></span>
            <div>
              <small>{{ t('teachingRepresentations.impactDialog.eyebrow', '结构化同源 · 影响工作台') }}</small>
              <h2>{{ dialogTitle }}</h2>
              <p>{{ dialogDescription }}</p>
            </div>
          </div>

          <ol class="impact-progress" :aria-label="t('teachingRepresentations.impactDialog.progressLabel', '同源修改进度')">
            <li class="is-complete">
              <span><PencilLine :size="13" /></span>
              <div><b>01</b><small>{{ t('teachingRepresentations.impactDialog.stepChange', '识别修改') }}</small></div>
            </li>
            <li :class="{ 'is-active': !receipt, 'is-complete': Boolean(receipt) }">
              <span><ScanSearch :size="13" /></span>
              <div><b>02</b><small>{{ t('teachingRepresentations.impactDialog.stepImpact', '分析影响') }}</small></div>
            </li>
            <li :class="{ 'is-active': Boolean(receipt), 'is-working': syncing }">
              <span>
                <LoaderCircle v-if="syncing" :size="13" class="spinning" />
                <CircleCheck v-else :size="13" />
              </span>
              <div><b>03</b><small>{{ t('teachingRepresentations.impactDialog.stepResult', '确认结果') }}</small></div>
            </li>
          </ol>

          <button
            type="button"
            class="impact-workspace__close"
            :disabled="syncing"
            :title="t('common.close', '关闭')"
            @click="emit('close')"
          >
            <X :size="20" />
          </button>
        </header>

        <div class="impact-workspace__body">
          <section class="impact-column impact-source">
            <header class="impact-column__header">
              <span>01</span>
              <div>
                <small>{{ t('teachingRepresentations.impactDialog.sourceEyebrow', '本次修改') }}</small>
                <h3>{{ t('teachingRepresentations.impactDialog.sourceTitle', '从 PPT 改变课程含义') }}</h3>
              </div>
            </header>

            <div class="source-change">
              <article class="source-change__card is-before">
                <div>
                  <small>{{ t('teachingRepresentations.impactDialog.before', '修改前') }}</small>
                  <span>{{ semanticChange.from_label || t('teachingRepresentations.impactDialog.originalGoal', '原学习目标') }}</span>
                </div>
                <p>{{ beforeText }}</p>
              </article>

              <div class="source-change__transition">
                <i></i>
                <span><ArrowDown :size="16" /></span>
                <strong>{{ semanticChange.summary || t('teachingRepresentations.impactDialog.understood', '系统理解语义变化') }}</strong>
              </div>

              <article class="source-change__card is-after">
                <div>
                  <small>{{ t('teachingRepresentations.impactDialog.after', '修改后') }}</small>
                  <span>{{ semanticChange.to_label || t('teachingRepresentations.impactDialog.newGoal', '新学习目标') }}</span>
                </div>
                <p>{{ afterText }}</p>
              </article>
            </div>

            <div v-if="semanticChange.interpretation" class="semantic-reading">
              <div class="semantic-reading__title">
                <span><BrainCircuit :size="16" /></span>
                <strong>{{ t('teachingRepresentations.impactDialog.systemReading', '系统怎样理解这次修改') }}</strong>
              </div>
              <p>{{ semanticChange.interpretation }}</p>
              <ul v-if="semanticChange.instructional_implications?.length">
                <li v-for="item in semanticChange.instructional_implications" :key="item">
                  <CircleCheck :size="12" />{{ item }}
                </li>
              </ul>
            </div>

            <div class="source-truth-state" :class="{ 'is-published': receipt }">
              <DatabaseZap :size="16" />
              <div>
                <strong>{{ receipt
                  ? t('teachingRepresentations.impactDialog.sourceUpdated', '课程真源已生成新修订')
                  : t('teachingRepresentations.impactDialog.sourceUntouched', '课程真源尚未改变') }}</strong>
                <small>{{ receipt
                  ? t('teachingRepresentations.impactDialog.sourceUpdatedHelp', '所有教学表达都以这次确认后的课程修订为准')
                  : t('teachingRepresentations.impactDialog.sourceUntouchedHelp', '确认前只分析影响，不会静默改写课程') }}</small>
              </div>
            </div>
          </section>

          <section class="impact-column impact-scope">
            <header class="impact-column__header">
              <span>02</span>
              <div>
                <small>{{ t('teachingRepresentations.impactDialog.scopeEyebrow', '影响范围') }}</small>
                <h3>{{ t('teachingRepresentations.impactDialog.scopeTitle', '该动的动，不该动的不动') }}</h3>
              </div>
            </header>

            <div class="impact-metrics">
              <article class="is-affected">
                <strong>{{ affectedCount }}</strong>
                <span>{{ t('teachingRepresentations.impactDialog.affected', '处需要联动') }}</span>
                <small>{{ t('teachingRepresentations.impactDialog.affectedHelp', '共享同一教学来源') }}</small>
              </article>
              <article class="is-protected">
                <strong>{{ unaffectedCount }}</strong>
                <span>{{ t('teachingRepresentations.impactDialog.unchanged', '处保持不变') }}</span>
                <small>{{ t('teachingRepresentations.impactDialog.unchangedHelp', '没有共同来源依赖') }}</small>
              </article>
            </div>

            <div class="impact-list-heading">
              <span>{{ receipt
                ? t('teachingRepresentations.impactDialog.resultList', '同步结果')
                : t('teachingRepresentations.impactDialog.affectedList', '预计联动位置') }}</span>
              <small>{{ t('teachingRepresentations.impactDialog.selectHint', '点击查看依据与结果') }}</small>
            </div>

            <div class="impact-list">
              <button
                v-for="(item, index) in displayImpactItems"
                :key="itemKey(item)"
                type="button"
                :class="{
                  'is-selected': itemKey(item) === selectedImpactKey,
                  'is-changed': item.change_kind === 'content_changed',
                  'is-verified': item.change_kind === 'source_verified',
                  'is-syncing': syncing,
                }"
                :style="{ '--delay': `${Math.min(index, 8) * 45}ms` }"
                @click="selectedImpactKey = itemKey(item)"
              >
                <span class="impact-list__icon">
                  <LoaderCircle v-if="syncing" :size="15" class="spinning" />
                  <CircleCheck v-else-if="receipt" :size="15" />
                  <GitBranch v-else :size="15" />
                </span>
                <span class="impact-list__copy">
                  <small>{{ item.role || representationRole(item.representation_type, item) }}</small>
                  <strong>{{ item.label }}</strong>
                </span>
                <em>{{ itemStateLabel(item) }}</em>
                <ChevronRight :size="15" />
              </button>
              <p v-if="hiddenImpactCount > 0" class="impact-list__more">
                {{ t('teachingRepresentations.impactDialog.moreAffected', '还有 {count} 个相关位置按相同规则处理').replace('{count}', String(hiddenImpactCount)) }}
              </p>
              <div v-if="!displayImpactItems.length" class="impact-list__empty">
                <ShieldCheck :size="18" />
                <span>{{ t('teachingRepresentations.impactDialog.noDependentItems', '没有发现需要联动的课程内容') }}</span>
              </div>
            </div>

            <details class="protected-scope">
              <summary>
                <span><ShieldCheck :size="16" /></span>
                <div>
                  <strong>{{ t('teachingRepresentations.impactDialog.protectedTitle', '明确保持不变') }}</strong>
                  <small>{{ t('teachingRepresentations.impactDialog.protectedDescription', '无共同来源的内容不会被全量重生成') }}</small>
                </div>
                <b>{{ unaffectedCount }}</b>
                <ChevronDown :size="15" />
              </summary>
              <div>
                <span v-for="item in protectedItems" :key="`${item.representation_type}:${item.unit_id}`">
                  <LockKeyhole :size="12" />{{ item.label }}
                </span>
                <span v-if="!protectedItems.length">
                  <LockKeyhole :size="12" />{{ t('teachingRepresentations.unrelatedProtected', '无来源关系的内容不会修改') }}
                </span>
              </div>
            </details>
          </section>

          <section class="impact-column impact-detail">
            <header class="impact-column__header">
              <span>03</span>
              <div>
                <small>{{ receipt
                  ? t('teachingRepresentations.impactDialog.resultEyebrow', '真实同步结果')
                  : t('teachingRepresentations.impactDialog.detailEyebrow', '影响依据') }}</small>
                <h3>{{ receipt
                  ? t('teachingRepresentations.impactDialog.resultTitle', '具体改成了什么')
                  : t('teachingRepresentations.impactDialog.detailTitle', '为什么这里会受到影响') }}</h3>
              </div>
            </header>

            <article v-if="selectedImpactItem" class="impact-detail-card">
              <header>
                <div>
                  <span>{{ representationLabel(selectedImpactItem.representation_type) }}</span>
                  <span>{{ selectedImpactItem.role || representationRole(selectedImpactItem.representation_type, selectedImpactItem) }}</span>
                </div>
                <em :data-kind="selectedImpactItem.change_kind || workspaceState">
                  <LoaderCircle v-if="syncing" :size="13" class="spinning" />
                  <CircleCheck v-else-if="receipt" :size="13" />
                  <Clock3 v-else :size="13" />
                  {{ itemStateLabel(selectedImpactItem) }}
                </em>
              </header>
              <h4>{{ selectedImpactItem.label }}</h4>

              <div class="impact-reason">
                <span><GitBranch :size="15" /></span>
                <div>
                  <small>{{ t('teachingRepresentations.impactDialog.dependencyReason', '同源依赖依据') }}</small>
                  <p>{{ selectedImpactItem.reason || previewReason(selectedImpactItem) }}</p>
                </div>
              </div>

              <div v-if="selectedImpactItem.change_kind === 'content_changed'" class="actual-diff">
                <div class="actual-diff__heading">
                  <strong>{{ t('teachingRepresentations.impactDialog.actualDiff', '本次实际修改') }}</strong>
                  <small>{{ t('teachingRepresentations.impactDialog.actualDiffHelp', '来自安全重建后的正式同步回执') }}</small>
                </div>
                <article class="is-before">
                  <small>{{ t('teachingRepresentations.impactDialog.before', '修改前') }}</small>
                  <p>{{ selectedImpactItem.before }}</p>
                </article>
                <div class="actual-diff__arrow"><ArrowDown :size="15" /></div>
                <article class="is-after">
                  <small>{{ t('teachingRepresentations.impactDialog.after', '修改后') }}</small>
                  <p>{{ selectedImpactItem.after }}</p>
                </article>
              </div>

              <div v-else-if="selectedImpactItem.change_kind === 'source_verified'" class="verified-result">
                <span><ShieldCheck :size="19" /></span>
                <div>
                  <strong>{{ t('teachingRepresentations.impactDialog.noRewriteTitle', '内容无需改写') }}</strong>
                  <p>{{ t('teachingRepresentations.impactDialog.sourceVerified', '系统已用新课程修订重新校验来源，现有内容仍然正确。') }}</p>
                </div>
              </div>

              <div v-else-if="receipt" class="verified-result is-generic">
                <span><CircleCheck :size="19" /></span>
                <div>
                  <strong>{{ t('teachingRepresentations.impactDialog.syncedTitle', '已按新课程修订完成同步') }}</strong>
                  <p>{{ t('teachingRepresentations.impactDialog.syncedHelp', '当前回执未提供逐字差异，但该单元已通过同源重建与质量检查。') }}</p>
                </div>
              </div>

              <div v-else class="preview-path">
                <div class="preview-path__flow">
                  <span><Presentation :size="15" />{{ t('teachingRepresentations.impactDialog.pptGoalChanged', 'PPT 目标变化') }}</span>
                  <i><ArrowRight :size="14" /></i>
                  <span><GitBranch :size="15" />{{ selectedImpactItem.role || representationLabel(selectedImpactItem.representation_type) }}</span>
                  <i><ArrowRight :size="14" /></i>
                  <span><RefreshCw :size="15" />{{ t('teachingRepresentations.impactDialog.safeRebuild', '确认后安全重建') }}</span>
                </div>
                <div class="preview-path__notice">
                  <Sparkles :size="16" />
                  <p>{{ t('teachingRepresentations.impactDialog.previewHonesty', '这里展示的是已经确认的依赖范围。最终改写文本将在确认后由课程真源重新编译，并在本页给出真实前后差异。') }}</p>
                </div>
              </div>
            </article>

            <div v-else class="impact-detail-empty">
              <ShieldCheck :size="24" />
              <strong>{{ t('teachingRepresentations.impactDialog.noImpactTitle', '这次修改没有扩散到其他内容') }}</strong>
              <p>{{ t('teachingRepresentations.impactDialog.noImpactHelp', '可以只保存当前 PPT 表达，不需要重建课程。') }}</p>
            </div>
          </section>
        </div>

        <footer class="impact-workspace__footer">
          <div class="impact-footer-summary">
            <span :class="{ 'is-complete': receipt }">
              <strong>{{ receipt ? changedCount : affectedCount }}</strong>
              <small>{{ receipt
                ? t('teachingRepresentations.impactDialog.changed', '项实际更新')
                : t('teachingRepresentations.impactDialog.affected', '处预计联动') }}</small>
            </span>
            <i></i>
            <span>
              <strong>{{ receipt ? verifiedCount : unaffectedCount }}</strong>
              <small>{{ receipt
                ? t('teachingRepresentations.impactDialog.verified', '项确认无需改写')
                : t('teachingRepresentations.impactDialog.unchanged', '处保持不变') }}</small>
            </span>
            <p v-if="!receipt">
              <ShieldCheck :size="13" />
              {{ t('teachingRepresentations.impactDialog.confirmGuard', '确认前课程不会发生变化') }}
            </p>
          </div>

          <div class="impact-workspace__actions">
            <template v-if="receipt">
              <button type="button" class="primary" @click="emit('close')">
                <CircleCheck :size="16" />{{ t('teachingRepresentations.impactDialog.returnToDeck', '查看更新后的课件') }}
              </button>
            </template>
            <template v-else-if="proposalItem">
              <button type="button" :disabled="busy || syncing" @click="emit('reject')">
                {{ t('teachingRepresentations.rejectChange', '暂不应用') }}
              </button>
              <button type="button" class="primary" :disabled="busy || syncing" @click="emit('confirm')">
                <LoaderCircle v-if="syncing" :size="16" class="spinning" />
                <GitBranch v-else :size="16" />
                {{ syncing
                  ? t('teachingRepresentations.impactDialog.syncing', '正在精准同步…')
                  : t('teachingRepresentations.impactDialog.confirmWithCounts', '确认联动 {affected} 处 · 保留 {unaffected} 处')
                    .replace('{affected}', String(affectedCount))
                    .replace('{unaffected}', String(unaffectedCount)) }}
              </button>
            </template>
            <template v-else>
              <button type="button" :disabled="busy" @click="emit('choose-local')">
                {{ t('teachingRepresentations.onlyThisPpt', '只改当前 PPT') }}
              </button>
              <button type="button" class="primary" :disabled="busy" @click="emit('propose')">
                <GitBranch :size="16" />{{ t('teachingRepresentations.impactDialog.createPlan', '生成精准同步方案') }}
              </button>
            </template>
          </div>
        </footer>
      </section>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  ArrowDown,
  ArrowRight,
  BrainCircuit,
  ChevronDown,
  ChevronRight,
  CircleCheck,
  Clock3,
  DatabaseZap,
  GitBranch,
  LoaderCircle,
  LockKeyhole,
  PencilLine,
  Presentation,
  RefreshCw,
  ScanSearch,
  ShieldCheck,
  Sparkles,
  X,
} from 'lucide-vue-next'
import { t } from '../shared/i18n'

const props = withDefaults(defineProps<{
  open: boolean
  preview?: Record<string, any> | null
  proposalItem?: object | null
  receipt?: Record<string, any> | null
  beforeText: string
  afterText: string
  busy?: boolean
  syncing?: boolean
}>(), {
  preview: null,
  proposalItem: null,
  receipt: null,
  busy: false,
  syncing: false,
})

const emit = defineEmits<{
  (event: 'close' | 'choose-local' | 'propose' | 'confirm' | 'reject'): void
}>()

const selectedImpactKey = ref('')
const semanticChange = computed(() => props.preview?.semantic_change || {})
const affectedCount = computed(() => Number(props.preview?.impact?.affected_unit_count || 0))
const unaffectedCount = computed(() => Number(props.preview?.impact?.unaffected_unit_count || 0))
const protectedItems = computed(() => (props.preview?.impact?.protected_items || []).slice(0, 6))
const previewImpactItems = computed(() => (
  (props.preview?.impact?.change_items || [])
    .filter((item: Record<string, any>) => !item.origin)
    .sort(impactPriority)
))
const receiptImpactItems = computed(() => (
  (props.receipt?.changes || []).flatMap((group: Record<string, any>) => (
    (group.units || []).map((unit: Record<string, any>) => ({
      ...unit,
      representation_type: group.representation_type,
      role: representationRole(group.representation_type, unit),
    }))
  )).sort(impactPriority)
))
const impactItems = computed(() => (
  props.receipt && receiptImpactItems.value.length
    ? receiptImpactItems.value
    : previewImpactItems.value
))
const displayImpactItems = computed(() => impactItems.value.slice(0, 24))
const hiddenImpactCount = computed(() => Math.max(0, impactItems.value.length - displayImpactItems.value.length))
const selectedImpactItem = computed(() => (
  displayImpactItems.value.find((item: Record<string, any>) => itemKey(item) === selectedImpactKey.value)
  || displayImpactItems.value[0]
  || null
))
const changedCount = computed(() => Number(
  props.receipt?.changed_unit_count
  ?? receiptImpactItems.value.filter((item: Record<string, any>) => item.change_kind === 'content_changed').length,
))
const verifiedCount = computed(() => Number(
  props.receipt?.verified_unit_count
  ?? receiptImpactItems.value.filter((item: Record<string, any>) => item.change_kind === 'source_verified').length,
))
const workspaceState = computed(() => {
  if (props.receipt) return 'complete'
  if (props.syncing) return 'syncing'
  if (props.proposalItem) return 'confirm'
  return 'preview'
})
const dialogTitle = computed(() => {
  if (props.receipt) return t('teachingRepresentations.impactDialog.completedTitle', '一处改变，相关内容已精准联动')
  if (props.syncing) return t('teachingRepresentations.impactDialog.syncingTitle', '正在只更新真正受影响的内容')
  if (props.proposalItem) return t('teachingRepresentations.impactDialog.confirmTitle', '影响范围已确认，等待教师决定')
  return t('teachingRepresentations.impactDialog.title', '系统理解了这次教学修改')
})
const dialogDescription = computed(() => {
  if (props.receipt) return t('teachingRepresentations.impactDialog.completedDescription', '真实修改、来源校验与保持不变的内容都已在同一份回执中说明。')
  if (props.proposalItem) return t('teachingRepresentations.impactDialog.confirmDescription', '课程真源尚未改变；确认后只重建有共同来源依赖的内容。')
  return t('teachingRepresentations.impactDialog.description', '从 PPT 修改出发，沿课程来源与教学作用精确计算影响范围。')
})

watch(
  () => [props.open, impactItems.value.map((item: Record<string, any>) => itemKey(item)).join('|')],
  ([isOpen]) => {
    if (!isOpen) return
    selectedImpactKey.value = displayImpactItems.value[0] ? itemKey(displayImpactItems.value[0]) : ''
  },
  { immediate: true },
)

function itemKey(item: Record<string, any>) {
  return `${item.representation_type || 'unknown'}:${item.unit_id || item.label || 'unit'}`
}

function representationLabel(value: string) {
  return t(`teachingRepresentations.types.${value}`, value)
}

function representationRole(value: string, unit: Record<string, any>) {
  if (value === 'lesson_plan') return t('teachingRepresentations.impactDialog.roles.lessonPlan', '教案重点')
  if (value === 'handout') return t('teachingRepresentations.impactDialog.roles.handout', '讲义解释')
  if (value === 'practice_sheet') return t('teachingRepresentations.impactDialog.roles.practice', '理解检查')
  if (value === 'outline') return t('teachingRepresentations.impactDialog.roles.outline', '目标定位')
  if (value === 'slide_deck') {
    if (String(unit.unit_id || '').endsWith(':check')) return t('teachingRepresentations.impactDialog.roles.practice', '理解检查')
    return t('teachingRepresentations.impactDialog.roles.slides', '课堂课件')
  }
  return representationLabel(value)
}

function itemStateLabel(item: Record<string, any>) {
  if (props.syncing) return t('teachingRepresentations.impactDialog.itemSyncing', '同步中')
  if (item.change_kind === 'content_changed') return t('teachingRepresentations.impactDialog.itemChanged', '已改写')
  if (item.change_kind === 'source_verified') return t('teachingRepresentations.impactDialog.itemVerified', '已校验')
  if (props.receipt) return t('teachingRepresentations.impactDialog.itemSynced', '已同步')
  if (props.proposalItem) return t('teachingRepresentations.impactDialog.itemPending', '待确认')
  return t('teachingRepresentations.impactDialog.itemAffected', '将联动')
}

function previewReason(item: Record<string, any>) {
  return t(
    'teachingRepresentations.impactDialog.defaultReason',
    '该教学表达与本次修改共享课程来源，确认后需要按新的课程修订重新校验。',
  ).replace('{role}', item.role || representationLabel(item.representation_type))
}

function impactPriority(left: Record<string, any>, right: Record<string, any>) {
  const rank = (item: Record<string, any>) => {
    const type = String(item.representation_type || '')
    const role = String(item.role || '')
    if (type === 'lesson_plan') return 10
    if (type === 'handout') return 20
    if (type === 'slide_deck' && /概念|推理|图解|核心讲解|例题|迁移|课堂课件/.test(role)) return 30
    if (type === 'slide_deck' && /检查|易错/.test(role)) return 40
    if (type === 'practice_sheet') return 50
    if (type === 'outline') return 60
    return 70
  }
  const evidenceRank = (item: Record<string, any>) => {
    if (item.change_kind === 'content_changed') return -3
    if (item.change_kind === 'source_verified') return 3
    return 0
  }
  return rank(left) + evidenceRank(left) - rank(right) - evidenceRank(right)
}
</script>

<style scoped>
.impact-workspace-shell {
  position:fixed;
  inset:0;
  z-index:10020;
  display:grid;
  place-items:center;
  padding:16px;
  background:
    radial-gradient(circle at 14% 8%,rgba(79,70,229,.2),transparent 31%),
    radial-gradient(circle at 86% 84%,rgba(245,158,11,.13),transparent 30%),
    rgba(5,10,20,.82);
  backdrop-filter:blur(18px);
}
.impact-workspace {
  width:min(1480px,calc(100vw - 32px));
  height:min(900px,calc(100dvh - 32px));
  min-height:620px;
  display:grid;
  grid-template-rows:auto minmax(0,1fr) auto;
  overflow:hidden;
  border:1px solid rgba(255,255,255,.36);
  border-radius:24px;
  color:#152033;
  background:#f3f5f8;
  box-shadow:0 40px 120px rgba(0,0,0,.48);
  font-family:"Avenir Next","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
}
.impact-workspace__header {
  position:relative;
  display:grid;
  grid-template-columns:minmax(0,1fr) auto 42px;
  align-items:center;
  gap:28px;
  min-height:106px;
  padding:19px 24px;
  color:#f7f9fc;
  background:
    radial-gradient(circle at 7% -80%,rgba(99,102,241,.62),transparent 42%),
    radial-gradient(circle at 86% 0,rgba(56,189,248,.14),transparent 30%),
    linear-gradient(115deg,#111827 0%,#18263a 68%,#132033 100%);
}
.impact-workspace__header::after {
  content:"";
  position:absolute;
  inset:auto 0 0;
  height:3px;
  background:linear-gradient(90deg,#6366f1 0 33%,#f5c451 33% 66%,#38bdf8 66%);
}
.impact-workspace__identity { min-width:0; display:flex; align-items:center; gap:14px; }
.impact-workspace__identity > span {
  width:48px;
  height:48px;
  flex:0 0 48px;
  display:grid;
  place-items:center;
  border:1px solid rgba(255,255,255,.18);
  border-radius:14px;
  color:#fff;
  background:linear-gradient(145deg,#6366f1,#4054d6);
  box-shadow:0 10px 28px rgba(79,70,229,.38);
}
.impact-workspace__identity > div { min-width:0; }
.impact-workspace__identity small {
  display:block;
  color:#aebbf7;
  font-size:10px;
  font-weight:800;
  letter-spacing:.16em;
  text-transform:uppercase;
}
.impact-workspace__identity h2 {
  margin:4px 0 0;
  color:#fff;
  font-size:clamp(22px,2.05vw,31px);
  font-weight:780;
  letter-spacing:-.025em;
  line-height:1.16;
}
.impact-workspace__identity p { max-width:720px; margin:5px 0 0; color:#9faec2; font-size:11px; line-height:1.45; }
.impact-progress {
  display:flex;
  align-items:center;
  gap:0;
  margin:0;
  padding:0;
  list-style:none;
}
.impact-progress li { position:relative; display:flex; align-items:center; gap:8px; padding:0 22px; color:#66758a; }
.impact-progress li:first-child { padding-left:0; }
.impact-progress li:last-child { padding-right:0; }
.impact-progress li + li::before { content:""; position:absolute; left:-7px; width:14px; height:1px; background:#405066; }
.impact-progress li > span {
  width:29px;
  height:29px;
  display:grid;
  place-items:center;
  border:1px solid #3b4a5f;
  border-radius:50%;
  background:#1c2a3c;
}
.impact-progress li div { display:grid; }
.impact-progress li b { color:#708096; font-size:8px; letter-spacing:.1em; }
.impact-progress li small { margin-top:1px; color:inherit; font-size:9px; white-space:nowrap; }
.impact-progress li.is-complete { color:#aebbf7; }
.impact-progress li.is-complete > span { border-color:#6366f1; color:#fff; background:#4f46e5; }
.impact-progress li.is-active { color:#f7d87b; }
.impact-progress li.is-active > span { border-color:#f5c451; color:#7a4c00; background:#f5c451; box-shadow:0 0 0 5px rgba(245,196,81,.12); }
.impact-progress li.is-working > span { border-color:#38bdf8; color:#38bdf8; }
.impact-workspace__close {
  width:42px;
  height:42px;
  display:grid;
  place-items:center;
  border:1px solid rgba(255,255,255,.14);
  border-radius:12px;
  color:#cbd5e1;
  background:rgba(255,255,255,.05);
  cursor:pointer;
}
.impact-workspace__close:hover:not(:disabled) { color:#fff; background:rgba(255,255,255,.12); }
.impact-workspace__close:disabled { opacity:.45; cursor:not-allowed; }

.impact-workspace__body {
  min-height:0;
  display:grid;
  grid-template-columns:minmax(280px,.88fr) minmax(330px,1.02fr) minmax(360px,1.18fr);
  overflow:hidden;
}
.impact-column {
  min-width:0;
  min-height:0;
  overflow:auto;
  padding:22px;
  border-right:1px solid #dce1e8;
  background:#fff;
}
.impact-column:last-child { border-right:0; }
.impact-scope { background:#f7f8fa; }
.impact-detail { background:linear-gradient(160deg,#f8faff,#f4f7fb 72%); }
.impact-column__header { display:flex; align-items:center; gap:10px; min-height:40px; }
.impact-column__header > span {
  width:34px;
  height:34px;
  flex:0 0 34px;
  display:grid;
  place-items:center;
  border-radius:10px;
  color:#4f46e5;
  background:#eef0ff;
  font-size:10px;
  font-weight:850;
  letter-spacing:.06em;
}
.impact-scope .impact-column__header > span { color:#8a5b00; background:#fff3cc; }
.impact-detail .impact-column__header > span { color:#0369a1; background:#e6f6ff; }
.impact-column__header small { display:block; color:#8a96a6; font-size:9px; font-weight:750; letter-spacing:.08em; }
.impact-column__header h3 { margin:2px 0 0; color:#172033; font-size:14px; line-height:1.25; }

.source-change { margin-top:20px; }
.source-change__card {
  position:relative;
  overflow:hidden;
  padding:15px;
  border:1px solid #dce1e8;
  border-radius:14px;
  background:#f8fafc;
}
.source-change__card::before { content:""; position:absolute; inset:0 auto 0 0; width:4px; background:#94a3b8; }
.source-change__card.is-after { border-color:#c9cffd; background:linear-gradient(135deg,#f6f7ff,#fff); box-shadow:0 12px 32px rgba(79,70,229,.08); }
.source-change__card.is-after::before { background:#4f46e5; }
.source-change__card > div { display:flex; align-items:center; justify-content:space-between; gap:10px; }
.source-change__card small { color:#7d8998; font-size:9px; font-weight:760; }
.source-change__card span { padding:4px 7px; border-radius:999px; color:#536174; background:#e9edf2; font-size:9px; font-weight:720; }
.source-change__card.is-after span { color:#4338ca; background:#e8eafe; }
.source-change__card p { margin:10px 0 0; color:#334155; font-size:12px; font-weight:650; line-height:1.62; }
.source-change__transition { position:relative; min-height:82px; display:grid; place-items:center; align-content:center; gap:5px; color:#4f46e5; text-align:center; }
.source-change__transition i { position:absolute; inset:0 auto; width:1px; background:linear-gradient(#c5cbed,#818cf8,#c5cbed); }
.source-change__transition span {
  z-index:1;
  width:29px;
  height:29px;
  display:grid;
  place-items:center;
  border:1px solid #c5cbed;
  border-radius:50%;
  background:#fff;
}
.source-change__transition strong { z-index:1; max-width:88%; padding:4px 9px; border-radius:999px; color:#4338ca; background:#eef0ff; font-size:9px; line-height:1.35; }
.semantic-reading { margin-top:16px; padding:14px; border:1px solid #d8e4ff; border-radius:14px; background:#f5f8ff; }
.semantic-reading__title { display:flex; align-items:center; gap:7px; color:#2549a8; }
.semantic-reading__title span { width:28px; height:28px; display:grid; place-items:center; border-radius:8px; color:#fff; background:#3b5ccc; }
.semantic-reading__title strong { font-size:11px; }
.semantic-reading > p { margin:9px 0 0; color:#536174; font-size:10px; line-height:1.55; }
.semantic-reading ul { display:grid; gap:6px; margin:11px 0 0; padding:0; list-style:none; }
.semantic-reading li { display:flex; align-items:flex-start; gap:6px; color:#42516a; font-size:9px; line-height:1.45; }
.semantic-reading li svg { flex:0 0 auto; margin-top:1px; color:#4f46e5; }
.source-truth-state { display:grid; grid-template-columns:32px minmax(0,1fr); gap:9px; margin-top:16px; padding:12px; border:1px dashed #cbd5e1; border-radius:12px; color:#64748b; background:#fbfcfd; }
.source-truth-state > svg { margin-top:2px; }
.source-truth-state strong,.source-truth-state small { display:block; }
.source-truth-state strong { color:#475569; font-size:10px; }
.source-truth-state small { margin-top:3px; font-size:9px; line-height:1.4; }
.source-truth-state.is-published { border-color:#a7d8c9; color:#047857; background:#f0fbf7; }
.source-truth-state.is-published strong { color:#047857; }

.impact-metrics { display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-top:20px; }
.impact-metrics article { padding:12px; border:1px solid #e0e5ec; border-radius:13px; background:#fff; }
.impact-metrics strong,.impact-metrics span,.impact-metrics small { display:block; }
.impact-metrics strong { color:#172033; font-size:23px; line-height:1; }
.impact-metrics span { margin-top:5px; color:#475569; font-size:10px; font-weight:760; }
.impact-metrics small { margin-top:3px; color:#8b96a5; font-size:8px; }
.impact-metrics .is-affected { border-color:#f2d87b; background:#fffdf5; }
.impact-metrics .is-affected strong { color:#a16207; }
.impact-metrics .is-protected strong { color:#526174; }
.impact-list-heading { display:flex; align-items:center; justify-content:space-between; gap:10px; margin:18px 2px 8px; }
.impact-list-heading span { color:#263246; font-size:10px; font-weight:800; }
.impact-list-heading small { color:#8a96a6; font-size:8px; }
.impact-list { display:grid; gap:7px; }
.impact-list > button {
  --delay:0ms;
  width:100%;
  min-width:0;
  display:grid;
  grid-template-columns:30px minmax(0,1fr) auto 15px;
  align-items:center;
  gap:8px;
  padding:9px 10px;
  border:1px solid #e0e5eb;
  border-radius:11px;
  color:#475569;
  background:#fff;
  text-align:left;
  cursor:pointer;
  animation:impact-rise .32s both;
  animation-delay:var(--delay);
  transition:border-color .16s ease,box-shadow .16s ease,transform .16s ease;
}
.impact-list > button:hover { border-color:#d5b84e; transform:translateX(2px); }
.impact-list > button.is-selected { border-color:#e0b72f; background:#fffdf2; box-shadow:0 7px 20px rgba(161,98,7,.09); }
.impact-list > button.is-changed { border-color:#aebbf7; background:#f7f8ff; }
.impact-list > button.is-verified { border-color:#bfdacb; background:#f7fcfa; }
.impact-list__icon { width:30px; height:30px; display:grid; place-items:center; border-radius:9px; color:#a16207; background:#fef3c7; }
.impact-list > button.is-changed .impact-list__icon { color:#4338ca; background:#e8eafe; }
.impact-list > button.is-verified .impact-list__icon { color:#047857; background:#e6f6ef; }
.impact-list__copy { min-width:0; display:block; }
.impact-list__copy small,.impact-list__copy strong { display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.impact-list__copy small { color:#8a96a6; font-size:8px; }
.impact-list__copy strong { margin-top:2px; color:#263246; font-size:10px; }
.impact-list > button em { padding:3px 6px; border-radius:999px; color:#8a5b00; background:#fff1bd; font-size:8px; font-style:normal; font-weight:750; white-space:nowrap; }
.impact-list > button.is-changed em { color:#4338ca; background:#e8eafe; }
.impact-list > button.is-verified em { color:#047857; background:#e4f6ed; }
.impact-list__more { margin:4px 0 0; color:#7c8796; font-size:8px; text-align:center; }
.impact-list__empty { min-height:88px; display:grid; place-items:center; align-content:center; gap:7px; color:#64748b; font-size:9px; }
.protected-scope { margin-top:12px; border:1px solid #dfe4ea; border-radius:12px; background:#fff; }
.protected-scope summary {
  display:grid;
  grid-template-columns:30px minmax(0,1fr) auto 15px;
  align-items:center;
  gap:8px;
  padding:10px;
  cursor:pointer;
  list-style:none;
}
.protected-scope summary::-webkit-details-marker { display:none; }
.protected-scope summary > span { width:30px; height:30px; display:grid; place-items:center; border-radius:9px; color:#526174; background:#edf0f4; }
.protected-scope summary strong,.protected-scope summary small { display:block; }
.protected-scope summary strong { color:#3b4758; font-size:9px; }
.protected-scope summary small { margin-top:2px; color:#8a96a6; font-size:8px; }
.protected-scope summary b { min-width:27px; padding:4px 7px; border-radius:999px; color:#526174; background:#edf0f4; font-size:9px; text-align:center; }
.protected-scope[open] summary > svg { transform:rotate(180deg); }
.protected-scope > div { display:flex; flex-wrap:wrap; gap:5px; padding:0 10px 10px 48px; }
.protected-scope > div span { display:flex; align-items:center; gap:4px; padding:5px 7px; border-radius:7px; color:#687587; background:#f4f6f8; font-size:8px; }

.impact-detail-card { margin-top:20px; padding:18px; border:1px solid #dbe2ec; border-radius:16px; background:#fff; box-shadow:0 16px 40px rgba(31,41,55,.08); }
.impact-detail-card > header { display:flex; align-items:center; justify-content:space-between; gap:12px; }
.impact-detail-card > header > div { display:flex; flex-wrap:wrap; gap:5px; }
.impact-detail-card > header > div span { padding:5px 8px; border-radius:999px; color:#334155; background:#eef2f7; font-size:8px; font-weight:730; }
.impact-detail-card > header > div span:first-child { color:#4338ca; background:#e8eafe; }
.impact-detail-card > header em { display:flex; align-items:center; gap:4px; padding:5px 8px; border-radius:999px; color:#a16207; background:#fff1bd; font-size:8px; font-style:normal; font-weight:760; }
.impact-detail-card > header em[data-kind="content_changed"],.impact-detail-card > header em[data-kind="complete"] { color:#4338ca; background:#e8eafe; }
.impact-detail-card > header em[data-kind="source_verified"] { color:#047857; background:#e5f7ee; }
.impact-detail-card h4 { margin:14px 0 0; color:#172033; font-size:16px; line-height:1.35; }
.impact-reason { display:grid; grid-template-columns:32px minmax(0,1fr); gap:9px; margin-top:13px; padding:11px; border-radius:11px; background:#f5f7fa; }
.impact-reason > span { width:32px; height:32px; display:grid; place-items:center; border-radius:9px; color:#4f46e5; background:#e8eafe; }
.impact-reason small { color:#7f8a99; font-size:8px; font-weight:760; }
.impact-reason p { margin:4px 0 0; color:#4b596c; font-size:10px; line-height:1.55; }
.preview-path { margin-top:18px; }
.preview-path__flow { display:flex; align-items:center; justify-content:center; gap:7px; padding:14px 8px; border:1px solid #e1e6ec; border-radius:12px; background:#fbfcfd; }
.preview-path__flow span { min-width:0; display:flex; align-items:center; gap:5px; color:#3f4b5f; font-size:8px; font-weight:700; text-align:center; }
.preview-path__flow span svg { flex:0 0 auto; color:#4f46e5; }
.preview-path__flow i { color:#a2adbb; }
.preview-path__notice { display:grid; grid-template-columns:24px minmax(0,1fr); gap:8px; margin-top:11px; padding:11px; border:1px solid #f1d984; border-radius:11px; color:#8a5b00; background:#fffdf3; }
.preview-path__notice p { margin:0; font-size:9px; line-height:1.55; }
.actual-diff { margin-top:18px; }
.actual-diff__heading { display:flex; align-items:flex-end; justify-content:space-between; gap:12px; margin-bottom:9px; }
.actual-diff__heading strong { color:#263246; font-size:10px; }
.actual-diff__heading small { color:#8a96a6; font-size:8px; text-align:right; }
.actual-diff article { padding:12px; border-radius:11px; }
.actual-diff article small { font-size:8px; font-weight:780; }
.actual-diff article p { margin:6px 0 0; white-space:pre-wrap; font-size:10px; line-height:1.55; }
.actual-diff article.is-before { color:#7f4b4b; background:#fff1f1; }
.actual-diff article.is-after { color:#155e4b; background:#eaf9f2; }
.actual-diff__arrow { height:32px; display:grid; place-items:center; color:#64748b; }
.verified-result { display:grid; grid-template-columns:38px minmax(0,1fr); gap:10px; margin-top:18px; padding:14px; border:1px solid #b9dfce; border-radius:12px; color:#047857; background:#f0fbf7; }
.verified-result > span { width:38px; height:38px; display:grid; place-items:center; border-radius:10px; color:#fff; background:#0b9470; }
.verified-result strong { font-size:11px; }
.verified-result p { margin:4px 0 0; color:#4e7167; font-size:9px; line-height:1.5; }
.verified-result.is-generic { border-color:#c9cffd; color:#4338ca; background:#f5f6ff; }
.verified-result.is-generic > span { background:#4f46e5; }
.verified-result.is-generic p { color:#5a6285; }
.impact-detail-empty { min-height:260px; display:grid; place-items:center; align-content:center; gap:8px; color:#64748b; text-align:center; }
.impact-detail-empty strong { color:#334155; font-size:12px; }
.impact-detail-empty p { max-width:300px; margin:0; font-size:9px; line-height:1.5; }

.impact-workspace__footer {
  min-height:76px;
  display:flex;
  align-items:center;
  justify-content:space-between;
  gap:24px;
  padding:13px 24px;
  border-top:1px solid #d9dfe7;
  background:#fff;
  box-shadow:0 -10px 28px rgba(31,41,55,.05);
}
.impact-footer-summary { display:flex; align-items:center; gap:12px; }
.impact-footer-summary > span { display:flex; align-items:baseline; gap:6px; }
.impact-footer-summary strong { color:#a16207; font-size:23px; line-height:1; }
.impact-footer-summary span.is-complete strong { color:#4f46e5; }
.impact-footer-summary small { color:#697588; font-size:9px; }
.impact-footer-summary > i { width:1px; height:26px; background:#d7dde5; }
.impact-footer-summary p { display:flex; align-items:center; gap:5px; margin:0 0 0 8px; color:#7a8797; font-size:8px; }
.impact-workspace__actions { display:flex; gap:9px; }
.impact-workspace__actions button {
  min-height:44px;
  display:inline-flex;
  align-items:center;
  justify-content:center;
  gap:7px;
  padding:0 18px;
  border:1px solid #cfd6df;
  border-radius:11px;
  color:#536174;
  background:#fff;
  font-size:10px;
  font-weight:740;
  cursor:pointer;
}
.impact-workspace__actions button:hover:not(:disabled) { border-color:#9ea9b8; background:#f8fafc; }
.impact-workspace__actions button.primary {
  min-width:220px;
  color:#fff;
  border-color:#4f46e5;
  background:linear-gradient(135deg,#5b55e8,#4338ca);
  box-shadow:0 10px 24px rgba(79,70,229,.26);
}
.impact-workspace__actions button.primary:hover:not(:disabled) { border-color:#4338ca; background:linear-gradient(135deg,#4f46e5,#3730a3); }
.impact-workspace__actions button:disabled { opacity:.45; cursor:not-allowed; }
.spinning { animation:slide-spin .8s linear infinite; }
@keyframes impact-rise { from { opacity:0; transform:translateY(7px); } to { opacity:1; transform:translateY(0); } }
@keyframes slide-spin { to { transform:rotate(360deg); } }

@media (max-width:1120px) {
  .impact-workspace__header { grid-template-columns:minmax(0,1fr) 42px; }
  .impact-progress { display:none; }
  .impact-workspace__body { grid-template-columns:minmax(270px,.85fr) minmax(320px,1fr) minmax(340px,1.12fr); }
  .impact-column { padding:18px; }
}
@media (max-width:900px) {
  .impact-workspace-shell { padding:8px; }
  .impact-workspace { width:calc(100vw - 16px); height:calc(100dvh - 16px); min-height:0; border-radius:16px; }
  .impact-workspace__header { min-height:90px; padding:15px 17px; }
  .impact-workspace__identity > span { width:40px; height:40px; flex-basis:40px; }
  .impact-workspace__identity h2 { font-size:19px; }
  .impact-workspace__body { overflow:auto; grid-template-columns:1fr; }
  .impact-column { overflow:visible; border-right:0; border-bottom:1px solid #dce1e8; }
  .impact-workspace__footer { position:sticky; bottom:0; align-items:stretch; flex-direction:column; gap:10px; padding:12px 17px; }
  .impact-footer-summary { justify-content:center; }
  .impact-workspace__actions { justify-content:flex-end; }
}
@media (max-width:560px) {
  .impact-workspace__identity p { display:none; }
  .impact-workspace__identity h2 { font-size:16px; }
  .impact-workspace__close { width:38px; height:38px; }
  .impact-column { padding:16px; }
  .impact-metrics { grid-template-columns:1fr 1fr; }
  .impact-footer-summary p { display:none; }
  .impact-workspace__actions { flex-direction:column; }
  .impact-workspace__actions button,.impact-workspace__actions button.primary { width:100%; min-width:0; }
}
</style>
