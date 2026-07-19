<template>
  <section class="generation-lesson-plan">
    <header class="generation-lesson-plan__header">
      <div>
        <span>{{ t('courseGeneration.lessonPlan.eyebrow', '整门课一次规划') }}</span>
        <h2>{{ t('courseGeneration.lessonPlan.title', '课程教案') }}</h2>
        <p>{{ planReady
          ? t('courseGeneration.lessonPlan.ready', '教案、知识点与教学块已经由同一份全课计划生成')
          : live
            ? t('courseGeneration.lessonPlan.pending', '目录已经确定；全课教案返回后会一次展开到每个小节')
            : t('courseGeneration.lessonPlan.legacyUnavailable', '这门旧课程还没有结构化全课教案，现展示已有学习目标') }}</p>
      </div>
      <dl v-if="planReady">
        <div><dt>{{ t('courseGeneration.lessonPlan.sections', '小节') }}</dt><dd>{{ plan?.section_count || sections.length }}</dd></div>
        <div><dt>{{ t('courseGeneration.lessonPlan.knowledge', '知识点') }}</dt><dd>{{ plan?.knowledge_point_count || knowledgeCount }}</dd></div>
        <div><dt>{{ t('courseGeneration.lessonPlan.modules', '教学块') }}</dt><dd>{{ plan?.teaching_module_count || moduleCount }}</dd></div>
      </dl>
      <span v-else-if="live" class="generation-lesson-plan__working"><LoaderCircle :size="14" />{{ t('courseGeneration.lessonPlan.generating', '正在规划') }}</span>
    </header>

    <div class="generation-lesson-plan__sections">
      <article
        v-for="(section, index) in sections"
        :key="section.node.node_id"
        :class="{ 'is-active': section.node.node_id === activeNodeId }"
        @click="emit('select', section.node)"
      >
        <div class="generation-lesson-plan__index">{{ String(index + 1).padStart(2, '0') }}</div>
        <div class="generation-lesson-plan__body">
          <header>
            <div>
              <strong>{{ section.node.node_name }}</strong>
              <p>{{ section.node.learning_objective || t('courseGeneration.lessonPlan.objectivePending', '学习目标随目录确认') }}</p>
            </div>
            <span :data-ready="Boolean(section.plan)">{{ section.plan
              ? t('courseGeneration.lessonPlan.planned', '已规划')
              : live
                ? t('courseGeneration.lessonPlan.waiting', '等待全课计划')
                : t('courseGeneration.lessonPlan.unavailable', '暂无结构化教案') }}</span>
          </header>

          <template v-if="section.plan">
            <div v-if="section.plan.key_points?.length" class="generation-lesson-plan__knowledge">
              <span v-for="point in section.plan.key_points" :key="point">{{ point }}</span>
            </div>
            <ol>
              <li v-for="(module, moduleIndex) in section.plan.teaching_modules || []" :key="module.module_id || moduleIndex">
                <span>{{ String(moduleIndex + 1).padStart(2, '0') }}</span>
                <div>
                  <strong>{{ module.teaching_purpose || module.module_id }}</strong>
                  <p v-if="module.teaching_guidance">{{ module.teaching_guidance }}</p>
                  <small v-if="module.knowledge_names?.length">{{ module.knowledge_names.join(' · ') }}</small>
                </div>
              </li>
            </ol>
          </template>
          <div v-else-if="live" class="generation-lesson-plan__skeleton" aria-hidden="true">
            <i /><i /><i />
          </div>
        </div>
      </article>

      <div v-if="!sections.length" class="generation-lesson-plan__empty">
        <LoaderCircle :size="22" />
        <strong>{{ t('courseGeneration.lessonPlan.outlinePending', '正在生成课程目录') }}</strong>
        <p>{{ t('courseGeneration.lessonPlan.outlinePendingHelp', '目录出现后，这里会先显示每个小节的教案占位。') }}</p>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { LoaderCircle } from 'lucide-vue-next'
import type { CourseTeachingPlanProjection, Node } from '../stores/types'
import { t } from '../shared/i18n'

const props = withDefaults(defineProps<{
  plan?: CourseTeachingPlanProjection | null
  nodes?: Node[]
  activeNodeId?: string
  live?: boolean
}>(), {
  plan: null,
  nodes: () => [],
  activeNodeId: '',
  live: false,
})

const emit = defineEmits<{
  (event: 'select', node: Node): void
}>()

const planByNode = computed(() => new Map(
  (props.plan?.sections || []).map(section => [section.node_id, section]),
))
const lessonNodes = computed(() => props.nodes.filter(node => node.node_level === 2))
const sections = computed(() => lessonNodes.value.map(node => ({
  node,
  plan: planByNode.value.get(node.node_id),
})))
const planReady = computed(() => props.plan?.status === 'completed' && Boolean(props.plan.sections?.length))
const moduleCount = computed(() => (props.plan?.sections || []).reduce(
  (sum, section) => sum + (section.teaching_modules?.length || 0),
  0,
))
const knowledgeCount = computed(() => (props.plan?.sections || []).reduce(
  (sum, section) => sum + (section.key_points?.length || 0),
  0,
))
</script>

<style scoped>
.generation-lesson-plan { min-height:0; flex:1; overflow:auto; padding:28px clamp(20px,4vw,56px) 70px; background:#f7f8fb; }
.generation-lesson-plan__header { width:min(980px,100%); display:grid; grid-template-columns:minmax(0,1fr) auto; align-items:end; gap:24px; margin:0 auto 20px; padding:0 2px 18px; border-bottom:1px solid #dfe3eb; }
.generation-lesson-plan__header > div > span { color:#5b61cf; font-size:9px; font-weight:850; letter-spacing:.08em; }
.generation-lesson-plan__header h2 { margin:4px 0 3px; color:#182230; font:700 27px/1.2 Georgia,"Noto Serif SC",serif; }
.generation-lesson-plan__header p { margin:0; color:#697386; font-size:11px; }
.generation-lesson-plan__header dl { display:flex; gap:8px; margin:0; }
.generation-lesson-plan__header dl div { min-width:64px; padding:8px 10px; border:1px solid #e0e4ec; border-radius:8px; background:#fff; }
.generation-lesson-plan__header dt { color:#8992a3; font-size:8px; }
.generation-lesson-plan__header dd { margin:2px 0 0; color:#263247; font:750 15px/1 ui-monospace,SFMono-Regular,monospace; }
.generation-lesson-plan__working { display:inline-flex; align-items:center; gap:6px; color:#5b61cf; font-size:10px; font-weight:750; }
.generation-lesson-plan__working svg,.generation-lesson-plan__empty svg { animation:lesson-plan-spin .9s linear infinite; }
.generation-lesson-plan__sections { width:min(980px,100%); display:grid; gap:11px; margin:0 auto; }
.generation-lesson-plan__sections > article { display:grid; grid-template-columns:46px minmax(0,1fr); border:1px solid #e0e4ec; border-radius:12px; background:#fff; box-shadow:0 5px 16px rgba(40,48,70,.04); cursor:pointer; transition:border-color .16s,box-shadow .16s,transform .16s; }
.generation-lesson-plan__sections > article:hover,.generation-lesson-plan__sections > article.is-active { border-color:#aeb4f4; box-shadow:0 8px 22px rgba(79,70,229,.08); transform:translateY(-1px); }
.generation-lesson-plan__index { display:flex; justify-content:center; padding-top:18px; border-right:1px solid #edf0f4; color:#8a93a4; font:700 10px ui-monospace,SFMono-Regular,monospace; }
.generation-lesson-plan__body { min-width:0; padding:15px 17px 16px; }
.generation-lesson-plan__body > header { display:flex; justify-content:space-between; gap:14px; }
.generation-lesson-plan__body > header > div { min-width:0; }
.generation-lesson-plan__body > header strong { color:#273144; font-size:13px; }
.generation-lesson-plan__body > header p { margin:4px 0 0; color:#758094; font-size:10px; line-height:1.5; }
.generation-lesson-plan__body > header > span { flex:0 0 auto; align-self:start; padding:4px 7px; border-radius:999px; color:#8a93a4; background:#f1f3f7; font-size:8px; font-weight:750; }
.generation-lesson-plan__body > header > span[data-ready="true"] { color:#087a5b; background:#eafaf4; }
.generation-lesson-plan__knowledge { display:flex; flex-wrap:wrap; gap:5px; margin-top:11px; }
.generation-lesson-plan__knowledge span { padding:4px 7px; border:1px solid #e1e4fb; border-radius:5px; color:#5057b9; background:#f7f7ff; font-size:9px; }
.generation-lesson-plan__body ol { display:grid; gap:7px; margin:12px 0 0; padding:0; list-style:none; }
.generation-lesson-plan__body li { display:grid; grid-template-columns:24px minmax(0,1fr); gap:8px; padding:9px 10px; border-left:2px solid #c8ccf8; background:#f9fafc; }
.generation-lesson-plan__body li > span { color:#7d85a0; font:700 9px ui-monospace,SFMono-Regular,monospace; }
.generation-lesson-plan__body li strong { display:block; color:#354052; font-size:10px; }
.generation-lesson-plan__body li p { margin:3px 0 0; color:#697386; font-size:9px; line-height:1.5; }
.generation-lesson-plan__body li small { display:block; margin-top:4px; color:#5b61cf; font-size:8px; }
.generation-lesson-plan__skeleton { display:grid; gap:7px; margin-top:13px; }
.generation-lesson-plan__skeleton i { height:9px; border-radius:3px; background:linear-gradient(90deg,#eef0f4 20%,#f8f9fb 45%,#eef0f4 70%); background-size:220% 100%; animation:lesson-plan-shimmer 1.4s ease infinite; }
.generation-lesson-plan__skeleton i:nth-child(2) { width:78%; }.generation-lesson-plan__skeleton i:nth-child(3) { width:56%; }
.generation-lesson-plan__empty { display:grid; place-items:center; min-height:240px; color:#7b8496; text-align:center; }
.generation-lesson-plan__empty strong { margin-top:10px; color:#384356; font-size:13px; }.generation-lesson-plan__empty p { margin:4px 0 0; font-size:10px; }
@keyframes lesson-plan-spin { to { transform:rotate(360deg); } }
@keyframes lesson-plan-shimmer { to { background-position:-220% 0; } }
@media (max-width:767px) {
  .generation-lesson-plan { padding:20px 12px 80px; }
  .generation-lesson-plan__header { grid-template-columns:1fr; align-items:start; gap:12px; }
  .generation-lesson-plan__header h2 { font-size:23px; }
  .generation-lesson-plan__sections > article { grid-template-columns:36px minmax(0,1fr); }
  .generation-lesson-plan__body { padding:13px 12px 14px; }
}
@media (prefers-reduced-motion:reduce) {
  .generation-lesson-plan__working svg,.generation-lesson-plan__empty svg,.generation-lesson-plan__skeleton i { animation:none; }
}
</style>
