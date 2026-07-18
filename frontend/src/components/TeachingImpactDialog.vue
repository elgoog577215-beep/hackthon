<template>
  <Teleport to="body">
    <div v-if="open" class="impact-dialog-shell" @click.self="emit('close')">
      <section class="impact-dialog" role="dialog" aria-modal="true" :aria-label="t('teachingRepresentations.impactDialog.title', '教学语义影响分析')">
        <header class="impact-dialog__header">
          <div>
            <small><GitBranch :size="13" />{{ t('teachingRepresentations.impactDialog.eyebrow', '同源课程影响图') }}</small>
            <h2>{{ dialogTitle }}</h2>
            <p>{{ dialogDescription }}</p>
          </div>
          <button type="button" :disabled="syncing" :title="t('common.close', '关闭')" @click="emit('close')"><X :size="19" /></button>
        </header>

        <div class="impact-dialog__body">
          <section class="semantic-shift">
            <div class="semantic-shift__value is-before">
              <small>{{ t('teachingRepresentations.impactDialog.before', '修改前 · 教学证据') }}</small>
              <b>{{ semanticChange.from_label || t('teachingRepresentations.impactDialog.originalGoal', '原学习目标') }}</b>
              <p>{{ beforeText }}</p>
            </div>
            <div class="semantic-shift__bridge">
              <span><BrainCircuit :size="22" /></span>
              <strong>{{ t('teachingRepresentations.impactDialog.understood', '系统理解') }}</strong>
              <i><ArrowRight :size="18" /></i>
            </div>
            <div class="semantic-shift__value is-after">
              <small>{{ t('teachingRepresentations.impactDialog.after', '修改后 · 教学证据') }}</small>
              <b>{{ semanticChange.to_label || t('teachingRepresentations.impactDialog.newGoal', '新学习目标') }}</b>
              <p>{{ afterText }}</p>
            </div>
          </section>

          <section v-if="semanticChange.interpretation" class="impact-interpretation">
            <Sparkles :size="17" />
            <div>
              <strong>{{ semanticChange.summary }}</strong>
              <p>{{ semanticChange.interpretation }}</p>
              <ul v-if="semanticChange.instructional_implications?.length">
                <li v-for="item in semanticChange.instructional_implications" :key="item">{{ item }}</li>
              </ul>
            </div>
          </section>

          <section class="impact-network">
            <div class="impact-network__source">
              <span><Presentation :size="18" /></span>
              <div><small>{{ t('teachingRepresentations.impactDialog.trigger', '唯一触发动作') }}</small><b>{{ t('teachingRepresentations.impactDialog.pptGoalChanged', 'PPT 学习目标变化') }}</b></div>
            </div>
            <div class="impact-network__connector">
              <i></i><BrainCircuit :size="18" /><i></i>
              <span>{{ t('teachingRepresentations.impactDialog.preciseDependency', '按来源与教学作用精准判断') }}</span>
            </div>
            <div class="impact-network__targets">
              <article
                v-for="(item, index) in visibleImpactItems"
                :key="`${item.representation_type}:${item.unit_id}`"
                :class="{ 'is-complete': receipt, 'is-verifying': syncing }"
                :style="{ '--delay': `${index * 80}ms` }"
              >
                <span>
                  <LoaderCircle v-if="syncing" :size="15" />
                  <CircleCheck v-else-if="receipt" :size="15" />
                  <BookOpenCheck v-else :size="15" />
                </span>
                <div>
                  <small>{{ item.role || representationLabel(item.representation_type) }}</small>
                  <b>{{ item.label }}</b>
                  <p v-if="item.reason">{{ item.reason }}</p>
                  <div v-if="receipt && item.change_kind === 'content_changed'" class="impact-network__diff">
                    <del>{{ item.before }}</del>
                    <ins>{{ item.after }}</ins>
                  </div>
                  <em v-else-if="receipt && item.change_kind === 'source_verified'">
                    {{ t('teachingRepresentations.impactDialog.sourceVerified', '内容无需改写，来源版本已重新校验') }}
                  </em>
                </div>
              </article>
            </div>
            <p v-if="hiddenImpactCount > 0" class="impact-network__more">
              {{ t('teachingRepresentations.impactDialog.moreAffected', '还有 {count} 个相关位置按相同规则处理').replace('{count}', String(hiddenImpactCount)) }}
            </p>
          </section>

          <section class="impact-protected">
            <header>
              <span><ShieldCheck :size="17" /></span>
              <div>
                <strong>{{ t('teachingRepresentations.impactDialog.protectedTitle', '不该动的，明确保持不变') }}</strong>
                <small>{{ t('teachingRepresentations.impactDialog.protectedDescription', '没有共同来源依赖的章节、资料与历史事实不会被全量重生成') }}</small>
              </div>
              <b>{{ unaffectedCount }}</b>
            </header>
            <div>
              <span v-for="item in protectedItems" :key="`${item.representation_type}:${item.unit_id}`">
                <LockKeyhole :size="12" />{{ item.label }}
              </span>
              <span v-if="!protectedItems.length"><LockKeyhole :size="12" />{{ t('teachingRepresentations.unrelatedProtected', '无来源关系的内容不会修改') }}</span>
            </div>
          </section>
        </div>

        <footer class="impact-dialog__footer">
          <div class="impact-dialog__summary">
            <template v-if="receipt">
              <strong>{{ changedCount }}</strong><span>{{ t('teachingRepresentations.impactDialog.changed', '项实际更新') }}</span>
              <i></i>
              <strong>{{ verifiedCount }}</strong><span>{{ t('teachingRepresentations.impactDialog.verified', '项确认无需改写') }}</span>
            </template>
            <template v-else>
              <strong>{{ affectedCount }}</strong><span>{{ t('teachingRepresentations.impactDialog.affected', '处预计联动') }}</span>
              <i></i>
              <strong>{{ unaffectedCount }}</strong><span>{{ t('teachingRepresentations.impactDialog.unchanged', '处保持不变') }}</span>
            </template>
          </div>
          <div class="impact-dialog__actions">
            <template v-if="receipt">
              <button type="button" class="primary" @click="emit('close')"><CircleCheck :size="16" />{{ t('teachingRepresentations.impactDialog.returnToDeck', '查看更新后的课件') }}</button>
            </template>
            <template v-else-if="proposalItem">
              <button type="button" :disabled="busy || syncing" @click="emit('reject')">{{ t('teachingRepresentations.rejectChange', '暂不应用') }}</button>
              <button type="button" class="primary" :disabled="busy || syncing" @click="emit('confirm')">
                <LoaderCircle v-if="syncing" :size="16" class="spinning" />
                <CircleCheck v-else :size="16" />
                {{ syncing ? t('teachingRepresentations.impactDialog.syncing', '正在精准同步…') : t('teachingRepresentations.confirmSync', '确认同步相关内容') }}
              </button>
            </template>
            <template v-else>
              <button type="button" :disabled="busy" @click="emit('choose-local')">{{ t('teachingRepresentations.onlyThisPpt', '只改当前 PPT') }}</button>
              <button type="button" class="primary" :disabled="busy" @click="emit('propose')"><GitBranch :size="16" />{{ t('teachingRepresentations.impactDialog.createPlan', '生成精准同步方案') }}</button>
            </template>
          </div>
        </footer>
      </section>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import {
  ArrowRight,
  BookOpenCheck,
  BrainCircuit,
  CircleCheck,
  GitBranch,
  LoaderCircle,
  LockKeyhole,
  Presentation,
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

const semanticChange = computed(() => props.preview?.semantic_change || {})
const affectedCount = computed(() => Number(props.preview?.impact?.affected_unit_count || 0))
const unaffectedCount = computed(() => Number(props.preview?.impact?.unaffected_unit_count || 0))
const protectedItems = computed(() => (props.preview?.impact?.protected_items || []).slice(0, 4))
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
const visibleImpactItems = computed(() => {
  const seen = new Set<string>()
  return impactItems.value.filter((item: Record<string, any>) => {
    const key = `${item.representation_type}:${item.role || ''}`
    if (seen.has(key)) return false
    seen.add(key)
    return true
  }).slice(0, 8)
})
const hiddenImpactCount = computed(() => Math.max(0, impactItems.value.length - visibleImpactItems.value.length))
const changedCount = computed(() => Number(
  props.receipt?.changed_unit_count
  ?? receiptImpactItems.value.filter((item: Record<string, any>) => item.change_kind === 'content_changed').length,
))
const verifiedCount = computed(() => Number(
  props.receipt?.verified_unit_count
  ?? receiptImpactItems.value.filter((item: Record<string, any>) => item.change_kind === 'source_verified').length,
))
const dialogTitle = computed(() => {
  if (props.receipt) return t('teachingRepresentations.impactDialog.completedTitle', '相关内容已精准同步')
  if (props.syncing) return t('teachingRepresentations.impactDialog.syncingTitle', '正在更新该动的内容')
  if (props.proposalItem) return t('teachingRepresentations.impactDialog.confirmTitle', '同步范围已准备好，等待教师确认')
  return t('teachingRepresentations.impactDialog.title', '系统理解了这次教学修改')
})
const dialogDescription = computed(() => {
  if (props.receipt) return t('teachingRepresentations.impactDialog.completedDescription', '下面展示真实修改差异，以及经过校验后无需改写的位置。')
  if (props.proposalItem) return t('teachingRepresentations.impactDialog.confirmDescription', '课程真源尚未改变；确认后只重建有来源依赖的内容。')
  return t('teachingRepresentations.impactDialog.description', '系统判断这次修改改变了什么教学证据，并沿同源依赖图计算影响范围。')
})

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
.impact-dialog-shell {
  position:fixed;
  inset:0;
  z-index:10020;
  display:grid;
  place-items:center;
  padding:12px;
  background:rgba(9,16,27,.72);
  backdrop-filter:blur(14px);
}
.impact-dialog {
  width:min(1160px,calc(100vw - 24px));
  max-height:calc(100dvh - 24px);
  display:grid;
  grid-template-rows:auto minmax(0,1fr) auto;
  overflow:hidden;
  border:1px solid rgba(255,255,255,.38);
  border-radius:20px;
  color:#1b2635;
  background:#f7f8fa;
  box-shadow:0 34px 90px rgba(0,0,0,.35);
  font-family:"Avenir Next","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
}
.impact-dialog__header {
  display:flex;
  align-items:flex-start;
  justify-content:space-between;
  gap:24px;
  padding:17px 24px 15px;
  color:#f5f8fc;
  background:
    radial-gradient(circle at 78% -20%,rgba(66,208,195,.28),transparent 34%),
    #172230;
}
.impact-dialog__header > div { min-width:0; }
.impact-dialog__header small { display:flex; align-items:center; gap:7px; color:#65d7cd; font-size:11px; font-weight:760; letter-spacing:.12em; }
.impact-dialog__header h2 { margin:5px 0 0; color:#f5f8fc; font:720 clamp(22px,2.2vw,29px)/1.18 "STSong","Songti SC","Noto Serif CJK SC",serif; }
.impact-dialog__header p { max-width:700px; margin:4px 0 0; color:#aebaca; font-size:11px; line-height:1.5; }
.impact-dialog__header button {
  width:38px;
  height:38px;
  flex:0 0 38px;
  display:grid;
  place-items:center;
  border:1px solid rgba(255,255,255,.14);
  border-radius:10px;
  color:#dbe4ef;
  background:rgba(255,255,255,.05);
  cursor:pointer;
}
.impact-dialog__header button:hover:not(:disabled) { color:#fff; background:rgba(255,255,255,.12); }
.impact-dialog__body { min-height:0; overflow:auto; padding:16px 24px 19px; }
.semantic-shift { display:grid; grid-template-columns:minmax(0,1fr) 150px minmax(0,1fr); gap:16px; align-items:stretch; }
.semantic-shift__value { min-width:0; padding:11px 15px; border:1px solid #dce2ea; border-radius:13px; background:#fff; }
.semantic-shift__value small { color:#7a8797; font-size:10px; font-weight:720; }
.semantic-shift__value b { display:block; margin-top:5px; font-size:14px; }
.semantic-shift__value p { margin:5px 0 0; color:#536174; font-size:11px; line-height:1.45; }
.semantic-shift__value.is-before { border-left:4px solid #94a3b8; }
.semantic-shift__value.is-after { border-left:4px solid #2556d8; background:#f8faff; }
.semantic-shift__value.is-after b { color:#214cae; }
.semantic-shift__bridge { display:grid; place-items:center; align-content:center; gap:6px; color:#2556d8; text-align:center; }
.semantic-shift__bridge > span { width:38px; height:38px; display:grid; place-items:center; border-radius:50%; color:#fff; background:#2556d8; box-shadow:0 9px 24px rgba(37,86,216,.24); }
.semantic-shift__bridge strong { font-size:11px; }
.semantic-shift__bridge i { color:#8da4db; }
.impact-interpretation { display:grid; grid-template-columns:22px minmax(0,1fr); gap:9px; margin-top:11px; padding:10px 13px; border:1px solid #cfe8e5; border-radius:11px; color:#0f766e; background:#f0fbf9; }
.impact-interpretation strong { font-size:12px; }
.impact-interpretation p { margin:3px 0 0; color:#526c6a; font-size:10px; line-height:1.45; }
.impact-interpretation ul { display:flex; flex-wrap:wrap; gap:5px; margin:6px 0 0; padding:0; list-style:none; }
.impact-interpretation li { padding:5px 8px; border-radius:999px; color:#25645f; background:#dff4f1; font-size:9px; }
.impact-network { margin-top:13px; }
.impact-network__source { width:max-content; max-width:100%; display:flex; align-items:center; gap:9px; margin:auto; padding:9px 13px; border:1px solid #cbd8f5; border-radius:10px; background:#f2f6ff; }
.impact-network__source > span { width:32px; height:32px; display:grid; place-items:center; border-radius:8px; color:#fff; background:#2556d8; }
.impact-network__source small,.impact-network__source b { display:block; }
.impact-network__source small { color:#7c89a0; font-size:9px; }
.impact-network__source b { margin-top:2px; color:#214cae; font-size:11px; }
.impact-network__connector { position:relative; height:43px; display:grid; place-items:center; align-content:center; color:#2556d8; }
.impact-network__connector i:first-child { position:absolute; inset:0 auto auto 50%; width:1px; height:10px; background:#99addc; }
.impact-network__connector i:nth-of-type(2) { position:absolute; inset:auto 8% 0; height:1px; background:#99addc; }
.impact-network__connector span { margin-top:3px; padding:2px 7px; border-radius:999px; color:#62708a; background:#f7f8fa; font-size:9px; }
.impact-network__targets { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:10px; }
.impact-network__targets article {
  min-width:0;
  display:grid;
  grid-template-columns:28px minmax(0,1fr);
  gap:8px;
  padding:9px 10px;
  border:1px solid #dce2ea;
  border-radius:12px;
  background:#fff;
  animation:impact-rise .38s both;
  animation-delay:var(--delay);
}
.impact-network__targets article > span { width:28px; height:28px; display:grid; place-items:center; border-radius:8px; color:#2556d8; background:#edf3ff; }
.impact-network__targets article.is-complete { border-color:#b9e5d9; background:#fbfffd; }
.impact-network__targets article.is-complete > span { color:#047857; background:#e9f9f3; }
.impact-network__targets article.is-verifying > span svg { animation:slide-spin .9s linear infinite; }
.impact-network__targets small,.impact-network__targets b { display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.impact-network__targets small { color:#788597; font-size:9px; }
.impact-network__targets b { margin-top:3px; color:#253246; font-size:11px; }
.impact-network__targets p { margin:4px 0 0; color:#687587; font-size:9px; line-height:1.35; }
.impact-network__targets em { display:block; margin-top:7px; color:#047857; font-size:9px; font-style:normal; line-height:1.45; }
.impact-network__diff { display:grid; gap:4px; margin-top:7px; font-size:9px; line-height:1.45; }
.impact-network__diff del,.impact-network__diff ins { padding:5px 6px; border-radius:5px; text-decoration:none; }
.impact-network__diff del { color:#8a5353; background:#fff0f0; }
.impact-network__diff ins { color:#17644d; background:#eaf9f2; }
.impact-network__more { margin:9px 0 0; color:#758194; font-size:10px; text-align:center; }
.impact-protected { margin-top:12px; padding:10px 13px; border:1px solid #dfe4eb; border-radius:12px; background:#fff; }
.impact-protected header { display:grid; grid-template-columns:34px minmax(0,1fr) auto; gap:10px; align-items:center; }
.impact-protected header > span { width:34px; height:34px; display:grid; place-items:center; border-radius:9px; color:#526174; background:#f0f2f5; }
.impact-protected header strong,.impact-protected header small { display:block; }
.impact-protected header strong { font-size:11px; }
.impact-protected header small { margin-top:3px; color:#7b8797; font-size:9px; }
.impact-protected header b { min-width:32px; padding:5px 8px; border-radius:999px; color:#4d5969; background:#edf0f4; font-size:11px; text-align:center; }
.impact-protected > div { display:flex; flex-wrap:wrap; gap:5px; margin-top:7px; }
.impact-protected > div span { display:flex; align-items:center; gap:4px; padding:5px 8px; border:1px solid #e1e5eb; border-radius:999px; color:#687587; background:#fafbfc; font-size:9px; }
.impact-dialog__footer { display:flex; align-items:center; justify-content:space-between; gap:20px; padding:13px 24px; border-top:1px solid #dfe4eb; background:#fff; }
.impact-dialog__summary { display:flex; align-items:baseline; gap:5px; color:#697588; font-size:10px; }
.impact-dialog__summary strong { color:#172230; font-size:18px; }
.impact-dialog__summary i { width:1px; height:18px; margin:0 8px; background:#d8dee7; }
.impact-dialog__actions { display:flex; gap:8px; }
.impact-dialog__actions button { min-height:39px; display:inline-flex; align-items:center; justify-content:center; gap:6px; padding:0 15px; border:1px solid #d2d9e3; border-radius:9px; color:#536174; background:#fff; font-size:11px; font-weight:680; cursor:pointer; }
.impact-dialog__actions button.primary { color:#fff; border-color:#2556d8; background:#2556d8; box-shadow:0 7px 18px rgba(37,86,216,.22); }
.impact-dialog__actions button:disabled { opacity:.45; cursor:not-allowed; }
.spinning { animation:slide-spin .8s linear infinite; }
@keyframes impact-rise { from { opacity:0; transform:translateY(8px); } to { opacity:1; transform:translateY(0); } }
@keyframes slide-spin { to { transform:rotate(360deg); } }
@media (max-width:900px) {
  .impact-dialog-shell { padding:10px; }
  .impact-dialog { width:calc(100vw - 20px); max-height:calc(100dvh - 20px); border-radius:14px; }
  .semantic-shift { grid-template-columns:1fr; }
  .semantic-shift__bridge { grid-template-columns:auto auto auto; }
  .impact-network__targets { grid-template-columns:repeat(2,minmax(0,1fr)); }
  .impact-dialog__footer { align-items:stretch; flex-direction:column; }
  .impact-dialog__actions { justify-content:flex-end; }
}
@media (max-width:560px) {
  .impact-dialog__header,.impact-dialog__body,.impact-dialog__footer { padding-right:16px; padding-left:16px; }
  .impact-network__targets { grid-template-columns:1fr; }
  .impact-dialog__actions { flex-direction:column; }
  .impact-dialog__actions button { width:100%; }
}
</style>
