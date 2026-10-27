<template>
  <section class="knowledge-profile" :aria-label="knowledgeOnly ? t('courseKnowledgeStudy.title') : t('knowledgeProfile.title', '知识掌握画像')">
    <header v-show="!selected && !knowledgeOnly" class="profile-heading"><div><span class="profile-eyebrow">{{ t('knowledgeProfile.eyebrow', '每一点理解，都有依据') }}</span><h2>{{ t('knowledgeProfile.title', '知识掌握画像') }}</h2></div><span class="profile-badge"><GitBranch :size="15" />{{ t('knowledgeProfile.byKnowledge', '按元知识点') }}</span></header>
    <div v-if="preview" class="profile-notice"><Info :size="18" /><p>{{ t('knowledgeProfile.preview', '当前为教师预览，不读取或写入任何学生的正式画像。') }}</p></div>
    <div v-else-if="loading && !profile" class="profile-empty" role="status">{{ t('knowledgeProfile.loading', '正在汇总知识点证据…') }}</div>
    <div v-else-if="error && !profile" class="profile-empty" role="alert">{{ t('knowledgeProfile.error', '画像暂时无法读取，请稍后刷新。未读取不代表掌握度为零。') }}</div>
    <template v-else-if="profile?.availability === 'ready'">
      <div v-if="baselineChanged" class="profile-notice" role="status"><Info :size="18" /><p>{{ t('knowledgeProfile.baselineChanged', '知识范围已更新。比例变化可能来自新增知识点或待重新验证的证据。') }}</p></div>
      <div v-show="!selected && !knowledgeOnly" class="profile-metrics">
        <article><span>{{ t('knowledgeProfile.progress', '已验证掌握进度') }}</span><strong data-testid="profile-progress">{{ profile.summary.verified_progress }}<small>%</small></strong><div class="profile-meter"><i :style="{ width: `${profile.summary.verified_progress}%` }" /></div><p>{{ t('knowledgeProfile.progressHint', '按全课范围计算，未评估部分暂不贡献进度') }}</p></article>
        <article><span>{{ t('knowledgeProfile.coverage', '评估覆盖率') }}</span><strong data-testid="profile-coverage">{{ profile.summary.coverage }}<small>%</small></strong><div class="profile-meter coverage"><i :style="{ width: `${profile.summary.coverage}%` }" /></div><p>{{ profile.summary.assessed_count }} / {{ profile.summary.total_count }} {{ t('knowledgeProfile.pointsAssessed', '个知识点已有有效检查') }}</p></article>
        <article><span>{{ t('knowledgeProfile.average', '已评估部分平均值') }}</span><strong>{{ profile.summary.assessed_average ?? '—' }}<small v-if="profile.summary.assessed_average !== null">%</small></strong><p>{{ t('knowledgeProfile.averageHint', '仅描述已有评估的部分，不代表整课能力') }}</p></article>
      </div>
      <div v-show="!selected && !knowledgeOnly" class="profile-scope"><span>{{ t('knowledgeProfile.courseScope', '全课范围') }} · {{ profile.summary.total_count }} {{ t('knowledgeProfile.points', '个元知识点') }}</span><span><i class="status-dot unassessed" />{{ profile.summary.unknown_count }} {{ t('knowledgeProfile.unassessed', '未评估') }}</span><span><i class="status-dot supported_mastery" />{{ profile.summary.mastered_count }} {{ t('knowledgeProfile.supported_mastery', '有掌握证据') }}</span><span><i class="status-dot needs_review" />{{ profile.summary.attention_count }} {{ t('knowledgeProfile.needs_review', '待巩固') }}</span></div>
      <KnowledgeMasteryTree v-show="!selected" ref="treeRef" :profile="profile" :course-title="courseTitle" @select="openPoint" />
      <section v-if="selected" class="knowledge-detail-inline" :aria-labelledby="detailTitleId" @keydown.esc.stop="closePoint">
        <header class="point-dialog-header"><span>{{ parentName }}</span><button type="button" @click="closePoint"><ArrowLeft :size="15" />{{ t('companionWorkspace.backTree') }}</button></header>
        <article class="profile-detail">
          <h3 ref="detailHeading" tabindex="-1" :id="detailTitleId"><MathText :content="selected.name" /></h3>
          <div class="point-evaluation" :data-status="selected.status">
            <div class="detail-orb" :style="{ '--mastery': `${selected.mastery ?? 0}%` }"><span data-testid="detail-mastery">{{ selected.mastery ?? '—' }}<small v-if="selected.mastery !== null">%</small></span></div>
            <div class="mastery-status"><b>{{ t(`knowledgeProfile.${selected.status}`) }}</b><details :key="selected.knowledge_id" class="mastery-explanation"><summary :aria-label="t('knowledgeDetail.scoreInfo')"><Info :size="15" />{{ t('knowledgeDetail.scoreInfo') }}</summary><p>{{ t('knowledgeDetail.scoreHint') }} {{ t(`knowledgeProfile.confidence.${selected.confidence}`) }}</p></details></div>
          </div>
          <p v-if="selected.mastery === null" class="point-explanation">{{ t('knowledgeProfile.unknownHint') }}</p>
          <KnowledgeTerms :point="selected" />
          <section class="point-rule"><h4>{{ t('knowledgeDetail.rule') }}</h4><MarkdownRenderer :content="selectedContent?.rule || selected.statement" /></section>
          <section v-if="selectedContent?.example" class="point-example"><h4>{{ selectedContent.exampleTitle || t('knowledgeDetail.example') }}</h4><MarkdownRenderer v-if="selectedContent.exampleMarkdown" :content="selectedContent.example" /><p v-else>{{ selectedContent.example }}</p></section>
          <KnowledgeCheckJourney v-if="courseId" :key="selected.knowledge_id" :course-id="courseId" :knowledge-id="selected.knowledge_id" :knowledge-revision="selected.knowledge_revision_id" :preview="preview || checkPreview" @graded="emit('graded')" />
          <section v-if="selected.links?.length" class="point-connections">
            <h4>{{ t('knowledgeFirst.relations') }}</h4>
            <article v-for="link in selected.links" :key="link.relation_id" class="point-connection">
              <p>{{ t(`knowledgeFirst.${link.direction}`) }} · {{ t(`knowledgeFirst.relationTypes.${link.type}`, link.type) }}</p>
              <button type="button" @click="openPoint(link.knowledge_id)">{{ link.name }} <ArrowUpRight :size="14" /></button>
              <small v-if="link.lecture_names.length">{{ link.lecture_names.join(' · ') }}</small>
              <p>{{ link.reason }}</p><ul v-if="link.conditions.length"><li v-for="condition in link.conditions" :key="condition">{{ condition }}</li></ul>
            </article>
          </section>
          <details :key="selected.knowledge_id" class="learning-evidence">
            <summary><span>{{ t('knowledgeDetail.records') }}</span><span>{{ selected.assessment_count }} {{ t('knowledgeProfile.checks') }}<ChevronRight :size="16" /></span></summary>
          <ul v-if="selected.evidence.length" class="point-evidence">
            <li v-for="entry in [...selected.evidence].reverse()" :key="entry.source_id"><CheckCircle2 v-if="entry.outcome === 'passed'" :size="17" /><CircleHelp v-else :size="17" /><div><strong>{{ t(`knowledgeProfile.outcomes.${entry.outcome}`) }} · {{ t(`knowledgeProfile.support.${entry.support}`) }}</strong><span>{{ formatDate(entry.observed_at) }}</span><small v-if="!entry.counted">{{ t('knowledgeProfile.notCounted', '保留活动记录，不计入掌握参考值') }}</small></div><button class="evidence-discuss" type="button" @click="emit('evidence', selected, entry)">{{ t('companionWorkspace.discussCheck', '讨论这次检查') }}<ChevronRight :size="15" /></button></li>
          </ul>
          <p v-else class="point-explanation">{{ t('knowledgeProfile.noChecks', '还没有与当前知识修订匹配的有效检查。') }}</p>
          <div class="evidence-footnotes"><p v-if="selected.activity_count">{{ selected.activity_count }} {{ t('knowledgeProfile.activityHint', '条提问或学习记录：参与本身不加减掌握分。') }}</p><p v-if="selected.pending_attribution_count">{{ selected.pending_attribution_count }} {{ t('knowledgeProfile.compositeHint', '次综合检查待逐点归因，未分摊总成绩。') }}</p><p v-if="selected.historical_count">{{ selected.historical_count }} {{ t('knowledgeProfile.historyHint', '条旧版本或未精确绑定的证据，保留历史并等待重新验证。') }}</p></div>
          </details>
          <div class="detail-actions">
            <button v-if="practiceIds?.includes(selected.knowledge_id)" type="button" class="practice-action" @click="emit('practice', selected)"><CircleHelp :size="17" />{{ t('knowledgeDetail.practice') }}</button>
            <button v-if="canRead || selected.section_refs.length" type="button" class="lecture-action" @click="emit('lecture', selected)"><BookOpen :size="16" />{{ t('knowledgeDetail.reading') }}<ArrowUpRight :size="15" /></button>
          </div>
        </article>
      </section>
      <details v-show="!selected && !knowledgeOnly" class="profile-method"><summary>{{ t('knowledgeProfile.method', '这些百分比如何计算？') }}</summary><p>{{ t('knowledgeProfile.methodBody', '按唯一元知识点等权汇总。独立检查的权重高于提示作答，同一道题采用最新有效结果。分数是首版参考指标，尚未校准为能力概率；提问、阅读和保存笔记不会自动加减分。') }}</p></details>
    </template>
    <div v-else class="profile-empty"><GitBranch :size="30" /><h3>{{ t('knowledgeProfile.noTree', '知识画像等待课程知识基线') }}</h3><p>{{ t('knowledgeProfile.noTreeHint', '课程需要先有可用的元知识点与精确检查绑定。此时不显示虚假的掌握百分比。') }}</p></div>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, useId, watch } from 'vue'
import { ArrowLeft, ArrowUpRight, BookOpen, CheckCircle2, ChevronRight, CircleHelp, GitBranch, Info } from 'lucide-vue-next'
import type { KnowledgeProfile, KnowledgeProfileNode } from '../types/knowledge-profile'
import MarkdownRenderer from './MarkdownRenderer.vue'
import KnowledgeMasteryTree from './KnowledgeMasteryTree.vue'
import KnowledgeTerms from './KnowledgeTerms.vue'
import KnowledgeCheckJourney from './KnowledgeCheckJourney.vue'
import MathText from './MathText.vue'
import { activeLocale, t } from '../shared/i18n'

const props = defineProps<{ profile?: KnowledgeProfile | null; preview?: boolean; knowledgeOnly?: boolean; loading?: boolean; error?: string; canLocate?: boolean; canRead?: boolean; courseTitle?: string; courseId?: string; checkPreview?: boolean; learningContent?: Record<string, { rule?: string; example?: string; exampleTitle?: string; exampleMarkdown?: boolean }>; practiceIds?: string[] }>()
const emit = defineEmits<{ (event: 'graded'): void; (event: 'practice', point: KnowledgeProfileNode): void; (event: 'locate', id: string): void; (event: 'select', point: KnowledgeProfileNode | null): void; (event: 'ask', point: KnowledgeProfileNode): void; (event: 'lecture', point: KnowledgeProfileNode): void; (event: 'evidence', point: KnowledgeProfileNode, evidence: KnowledgeProfileNode['evidence'][number]): void }>()
const selectedId = ref('')
const treeRef = ref<InstanceType<typeof KnowledgeMasteryTree> | null>(null)
const detailHeading = ref<HTMLElement | null>(null)
const detailTitleId = `knowledge-detail-${useId()}`
let detailTrigger: HTMLElement | null = null
const baselineChanged = ref(false)
watch(() => props.profile?.baseline_revision, (current, previous) => { if (current && previous && current !== previous) { baselineChanged.value = true; closePoint() } })
watch(() => props.profile?.course_id, () => { baselineChanged.value = false; closePoint() })
const selected = computed(() => props.profile?.nodes.find(p => p.knowledge_id === selectedId.value))
const selectedContent = computed(() => props.learningContent?.[selectedId.value])
const parentName = computed(() => props.profile?.branches.find(b => b.id === selected.value?.parent_id)?.name || '')
async function openPoint(id: string, trigger?: HTMLElement) {
  detailTrigger = trigger || null
  selectedId.value = id
  emit('select', selected.value || null)
  await nextTick()
  detailHeading.value?.focus({ preventScroll: true })
}
function closePoint() {
  selectedId.value = ''
  emit('select', null)
  const trigger = detailTrigger
  detailTrigger = null
  void nextTick(() => { if (trigger?.isConnected) trigger.focus({ preventScroll: true }) })
}
defineExpose({ openPoint, closePoint })
watch(() => props.preview, value => { if (value) closePoint() })
watch(selected, value => { if (!value && selectedId.value) closePoint() })

function formatDate(value: string | null) {
  if (!value || !Number.isFinite(Date.parse(value))) return ''
  return new Date(value).toLocaleString(activeLocale.value === 'zh' ? 'zh-CN' : 'en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}
</script>

<style scoped>
.knowledge-detail-dialog { position:fixed; inset:0; margin:auto; width:min(660px,calc(100vw - 40px)); max-width:none; max-height:90vh; padding:0; border:1px solid #e0d6ed; border-radius:20px; background:#fff; color:#45364f; box-shadow:0 25px 90px #34204438; }
.knowledge-detail-dialog::backdrop { background:#21162d55; backdrop-filter:blur(3px); }
.point-dialog-header { display:flex; align-items:center; justify-content:space-between; padding:14px 20px 14px 28px; border-bottom:1px solid #eee7f4; background:#faf8fd; }
.point-dialog-header>span { font-size:13px; color:#92799f; }
.point-dialog-header button { display:grid; place-items:center; width:34px; height:34px; border:0; border-radius:9px; background:#f0ebf6; color:#8c729b; cursor:pointer; }
.point-dialog-header button:hover { background:#e9e0f2; color:#624376; }

.knowledge-profile { --profile-violet:#7260d4; color:#2c3044; padding:24px; font-size:15px; }
.profile-heading { display:flex; align-items:center; justify-content:space-between; gap:12px; margin-bottom:22px; }
.profile-eyebrow { color:#74658f; font-size:13px; }
.profile-heading h2 { margin:6px 0 0; font-size:24px; font-weight:650; }
.profile-badge { display:flex; align-items:center; gap:6px; padding:7px 10px; border-radius:20px; background:#f0edfb; color:#6753ae; white-space:nowrap; font-size:13px; }
.profile-metrics { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:12px; }
.profile-metrics article { padding:18px; border:1px solid #e8e5f0; border-radius:14px; background:linear-gradient(145deg,#fff,#faf9ff); }
.profile-metrics article>span { display:block; font-size:14px; color:#625d76; }
.profile-metrics strong { display:block; font-size:34px; color:#453883; font-weight:650; margin:12px 0; font-variant-numeric:tabular-nums; }
.profile-metrics strong small { margin-left:3px; font-size:16px; font-weight:500; }
.profile-metrics p { color:#797486; font-size:12px; line-height:1.7; margin:10px 0 0; }
.profile-meter { height:5px; background:#ebe7f5; overflow:hidden; border-radius:5px; }
.profile-meter i { display:block; height:100%; background:#8973dc; border-radius:5px; }
.profile-meter.coverage i { background:#779bbb; }
.profile-scope { display:flex; align-items:center; gap:16px; flex-wrap:wrap; margin:19px 0; color:#756e86; font-size:12px; }
.profile-scope span { display:flex; gap:5px; align-items:center; }
.status-dot { display:inline-block; flex:none; width:7px; height:7px; border-radius:50%; background:#b3afc0; }
.status-dot.supported_mastery { background:#5c9a85; }.status-dot.needs_review { background:#cd945a; }.status-dot.checking { background:#8c7ada; }
.profile-detail { min-width:0; padding:24px 28px 28px; max-height:calc(85vh - 64px); overflow:auto; }
.point-path { display:flex; align-items:center; gap:5px; color:#92879e; font-size:12px; }.profile-detail h3 { margin:12px 0; font-size:21px; line-height:1.5; }
.point-statement { color:#6a6279; line-height:1.8; margin:0 0 20px; }
.point-evaluation { display:flex; align-items:center; justify-content:space-between; gap:12px; padding:16px 18px; background:#f7f4fe; border-radius:12px; }
.point-evaluation>div { display:flex; flex-direction:column; gap:6px; }.point-evaluation span { font-size:12px; color:#8a7c99; }.point-evaluation strong { font-size:32px; font-weight:650; color:#6b51aa; }.point-evaluation strong small { font-size:16px; }.point-evaluation b { color:#73627e; font-size:13px; }
.point-evaluation[data-status=needs_review] { background:#fff6ec; }.point-evaluation[data-status=supported_mastery] { background:#eef7f3; }
.point-explanation { color:#8a7e91; font-size:13px; line-height:1.8; margin:14px 0; }
.point-next { display:flex; align-items:flex-start; gap:10px; margin:22px 0 12px; color:#7863b5; }.point-next svg { flex:none; margin-top:3px; }.point-next strong { color:#514463; font-size:14px; }.point-next p { margin:5px 0 0; color:#7c7087; font-size:13px; line-height:1.8; }
.point-locate { display:flex; align-items:center; gap:7px; border:1px solid #ded5f0; border-radius:8px; background:#fff; padding:8px 10px; color:#7257a6; font:inherit; font-size:13px; cursor:pointer; }
.evidence-heading { display:flex; align-items:center; justify-content:space-between; gap:8px; margin:24px 0 10px; border-top:1px solid #eee9f2; padding-top:18px; }.evidence-heading h4 { margin:0; font-size:14px; }.evidence-heading span { font-size:12px; color:#9b8fa3; }
.point-evidence { list-style:none; padding:0; margin:0; max-height:240px; overflow:auto; }.point-evidence li { display:flex; gap:9px; padding:10px 0; }.point-evidence svg { color:#8d7aa7; flex:none; margin-top:3px; }.point-evidence li div { display:flex; flex-direction:column; gap:4px; }.point-evidence strong { font-size:13px; font-weight:500; color:#66596f; }.point-evidence span,.point-evidence small { font-size:11px; color:#9b8e9f; }
.evidence-footnotes { font-size:12px; color:#917f94; line-height:1.8; }.evidence-footnotes p { margin:6px 0; }
.profile-method { margin-top:18px; color:#8b7f94; font-size:12px; line-height:1.8; }.profile-method summary { cursor:pointer; }.profile-method p { max-width:850px; }
.profile-notice { display:flex; align-items:center; gap:12px; padding:16px; border:1px solid #e6ddf3; background:#f8f5fc; border-radius:12px; color:#807187; }.profile-notice svg { flex:none; }.profile-notice p { margin:0; line-height:1.8; }
.profile-empty { padding:45px 25px; display:flex; flex-direction:column; align-items:center; gap:12px; text-align:center; color:#8d7c9c; border:1px dashed #dfd5e9; border-radius:14px; }.profile-empty h3 { margin:0; font-size:18px; color:#64536f; }.profile-empty p { max-width:480px; margin:0; line-height:1.8; }.profile-no-results { padding:12px; color:#92829b; font-size:13px; }
button:focus-visible,summary:focus-visible,input:focus-visible { outline:2px solid #8170c6; outline-offset:3px; }
@media(max-width:900px) { .knowledge-profile { padding:16px; }.profile-metrics { gap:8px; }.profile-metrics article { padding:12px; }.profile-detail { padding:16px; } }
</style>

<style scoped>
.knowledge-profile:has(.knowledge-detail-inline) { padding:0; }
.knowledge-detail-inline { min-height:100%; background:#fff; border-radius:18px; }
.point-dialog-header { background:transparent; padding:24px 28px 0; border:0; }
.point-dialog-header button { width:auto; height:auto; display:flex; gap:7px; padding:9px 12px; background:#fff; border:1px solid #e1dcf0; font-size:13px; }
.profile-detail { padding:12px 28px 28px; max-height:none; overflow:visible; }
.point-path { display:none; }.profile-detail h3 { font-size:28px; color:#25234e; letter-spacing:-.6px; margin:14px 0 12px; }.profile-detail h3:focus { outline:none; }
.point-statement { font-size:15px; margin-bottom:24px; }
.point-evaluation { justify-content:flex-start; padding:22px; gap:24px; border:1px solid #eae5f4; }
.point-evaluation .detail-orb { width:94px; height:94px; flex:none; border-radius:50%; display:grid; place-items:center; background:conic-gradient(#9071dd var(--mastery),#e8e1f5 0); padding:4px; }
.point-evaluation[data-status=needs_review] .detail-orb { background:conic-gradient(#ca944e var(--mastery),#efe4d5 0); }
.detail-orb>span { width:86px; height:86px; display:grid; align-content:center; grid-auto-flow:column; align-items:baseline; justify-content:center; background:#fff; border-radius:50%; font-size:28px; font-weight:650; color:#7655ad; }.detail-orb small { font-size:16px; }
.point-evaluation[data-status=needs_review] .detail-orb>span,.point-evaluation[data-status=needs_review] strong { color:#aa681f; }
.point-evaluation>div:last-child { margin-left:auto; }.point-evaluation b { font-size:15px; }
.point-next { background:#f5f2fd; border:1px solid #ebe5f8; border-radius:14px; padding:18px; margin-top:24px; }.point-next strong { font-size:17px; color:#6b49c1; }.point-next p { font-size:15px; }
.evidence-heading h4 { font-size:20px; color:#302951; }.point-evidence { max-height:none; }.point-evidence li { align-items:center; padding:16px; margin:9px 0; border-radius:12px; background:#f8f7fc; }.point-evidence strong { font-size:15px; }.point-evidence span { font-size:12px; }.evidence-discuss { display:flex; align-items:center; gap:3px; flex:none; margin-left:auto; border:0; color:#7855c3; background:transparent; font-size:13px; cursor:pointer; }
.detail-actions { display:flex; gap:12px; margin-top:25px; }.detail-actions button { flex:1; display:flex; justify-content:center; align-items:center; gap:8px; min-height:46px; background:var(--lz-action-bg); border:1px solid var(--lz-action-border); border-radius:var(--lz-action-radius); color:var(--lz-action-text); font:inherit; cursor:pointer; box-shadow:var(--lz-action-shadow); }.detail-actions button:first-child { background:var(--lz-action-bg); color:var(--lz-action-text); border-color:var(--lz-action-border); border:1px solid var(--lz-action-border); border-radius:var(--lz-action-radius); box-shadow:var(--lz-action-shadow); }
@media(max-width:1100px) { .profile-detail { padding:12px 20px 24px; }.profile-detail h3 { font-size:24px; }.point-evaluation { gap:12px; padding:15px; }.point-evaluation>div:last-child { max-width:100px; }.evidence-discuss { font-size:12px; } }
</style>

<style scoped>
.point-dialog-header button { border:0; padding:6px 0 6px 8px; background:transparent; color:#8c79a3; }
.profile-detail h3 { margin:18px 0 22px; }
.point-evaluation { padding:0!important; gap:16px; border:0; background:transparent!important; margin-bottom:26px; }
.point-evaluation>div.mastery-status { margin-left:0; max-width:none; gap:8px; }
.mastery-explanation { position:relative; color:#8c7b9c; font-size:12px; }.mastery-explanation summary { display:flex; align-items:center; gap:5px; cursor:pointer; list-style:none; }.mastery-explanation summary::-webkit-details-marker { display:none; }.mastery-explanation p { position:absolute; top:26px; left:0; z-index:4; width:235px; padding:12px; margin:0; border:1px solid #e6dcef; border-radius:10px; background:#fff; box-shadow:0 8px 24px #4e32691a; font-size:13px; line-height:1.75; }
.point-rule { margin:0 0 22px; }.point-rule h4,.point-example h4 { margin:0 0 10px; font-size:16px; font-weight:600; color:#413255; }.point-rule p,.point-example p { margin:0; font-size:16px; line-height:1.85; color:#675574; white-space:pre-wrap; }
.point-example { margin:0 0 26px; padding:18px 20px; border:1px solid #eae3f4; border-radius:12px; background:#f8f5fd; }.point-example p { font-size:15px; }
.learning-evidence { border-top:1px solid #eee7f4; border-bottom:1px solid #eee7f4; margin-top:8px; }.learning-evidence>summary { display:flex; align-items:center; justify-content:space-between; gap:12px; padding:17px 0; list-style:none; cursor:pointer; color:#72617f; font-size:14px; }.learning-evidence>summary::-webkit-details-marker { display:none; }.learning-evidence>summary>span:last-child { display:flex; align-items:center; gap:7px; font-size:12px; color:#95859f; }.learning-evidence[open]>summary svg { transform:rotate(90deg); }.learning-evidence .point-evidence li { padding:12px; }.learning-evidence .point-evidence strong { font-size:13px; }.learning-evidence .point-evidence span { font-size:11px; }
.detail-actions { margin-top:22px; justify-content:flex-start; align-items:center; gap:18px; }.detail-actions button { flex:none; padding:10px 15px; min-height:40px; font-size:14px; }.detail-actions .practice-action { background:var(--lz-action-bg); border-color:var(--lz-action-border); color:var(--lz-action-text); border:1px solid var(--lz-action-border); border-radius:var(--lz-action-radius); box-shadow:var(--lz-action-shadow); }.detail-actions button.lecture-action { background:none; border:0; padding:8px 0; color:#80639b; }
</style>

<style scoped>
.point-example :deep(.markdown-renderer) { font-size:15px; line-height:1.8; color:#675574; }.point-example :deep(pre) { max-width:100%; overflow:auto; font-size:13px; }
</style>

<style scoped>
.point-connections{margin:24px 0}.point-connection{padding:16px 18px;margin-top:12px;background:#f7f5fc;border:1px solid #e8e2f2;border-radius:12px}.point-connection button{display:flex;align-items:center;gap:8px;background:white;border:1px solid #ded5ee;border-radius:8px;padding:9px 12px;color:#66519b;font:inherit;cursor:pointer}.point-connection p,.point-connection li{font-size:15px;line-height:1.8}.point-connection small{display:block;margin-top:8px;color:#857494}
</style>
