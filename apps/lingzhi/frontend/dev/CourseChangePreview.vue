<template>
  <div class="change-preview" :class="{ 'is-clean': clean }">
    <header v-if="!clean" class="preview-toolbar">
      <strong>{{ activeLocale === 'zh' ? '灵知 · 课程修改' : 'Lingzhi · Course changes' }}</strong>
      <span>{{ activeLocale === 'zh' ? '示例课程 · 仅预览，不写入正式数据' : 'Sample course · No production data is changed' }}</span>
      <nav aria-label="Preview screens">
        <button :aria-pressed="view === 'request'" @click="show('request')">{{ activeLocale === 'zh' ? '结构需求' : 'Structure request' }}</button>
        <button :aria-pressed="view === 'structure'" @click="show('structure')">{{ activeLocale === 'zh' ? '结构审阅' : 'Structure review' }}</button>
        <button :aria-pressed="view === 'semantic'" @click="show('semantic')">{{ activeLocale === 'zh' ? '全局语义' : 'Content changes' }}</button>
      </nav>
      <button @click="setLocale(activeLocale === 'zh' ? 'en' : 'zh')">{{ activeLocale === 'zh' ? 'English' : '中文' }}</button>
    </header>
    <CourseEvolutionWorkspace
      :key="`${view}-${version}`"
      :model-value="true"
      course-id="ui-preview-course"
      :course-title="activeLocale === 'zh' ? '大学物理' : 'University Physics'"
      :initial-mode="view === 'semantic' ? 'replace' : 'structure'"
      standalone
      :embedded-in-center="view === 'semantic'"
      @update:model-value="show(view)"
    />
    <p v-if="notice" class="preview-notice" role="status">{{ notice }}</p>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import CourseEvolutionWorkspace from '../src/components/CourseEvolutionWorkspace.vue'
import { activeLocale, setLocale } from '../src/shared/i18n'
import { useCourseEvolutionStore, type CourseEvolutionPlan, type TeacherCourseChangeContext, type TeacherCourseChangePlanning } from '../src/stores/courseEvolution'

type PreviewView = 'request' | 'structure' | 'semantic'
const query = new URLSearchParams(location.search)
const clean = query.get('clean') === '1'
const view = ref<PreviewView>(query.get('view') === 'semantic' ? 'semantic' : query.get('view') === 'request' ? 'request' : 'structure')
const version = ref(0)
const notice = ref('')
const store = useCourseEvolutionStore()
const titles = ['质点运动学', '牛顿运动定律', '功与能', '动量与碰撞', '刚体转动', '振动与波']
const outline = titles.map((node_name, index) => ({ node_id: `lesson-${index + 1}`, parent_node_id: 'root', node_name, node_level: 1 }))
const previewContext: TeacherCourseChangeContext = {
  schema_version: 'teacher_course_change_context_v1', index_schema_version: 'teacher_course_change_index_v1',
  course_id: 'ui-preview-course', course_title: '大学物理', source_mode: 'authoring_workspace', ready: true,
  readiness_message: '已连接课程文件', base_revision_vector: { teacher_outline: 'preview-outline' },
  assets: ['outline', 'course_content', 'lesson_plan', 'script', 'ppt'].map(asset_type => ({
    asset_type, label: asset_type, state: 'available' as const, count: 6, source: 'local_ui_fixture', revision: 'preview',
  })), outline, units: [], updated_at: '2026-10-20T08:00:00Z',
  summary: { available_assets: 5, missing_assets: 0, indexed_units: 30, outline_nodes: 6 },
}
const request = '将“功与能”移到“动量与碰撞”之后，保持其他讲次顺序。'

function makePlan(instruction = request): CourseEvolutionPlan {
  const planning: TeacherCourseChangePlanning = {
    schema_version: 'course_change_plan_v1', scenario_matrix_version: 'course_change_scenario_matrix_v1',
    plan_id: 'preview-plan', course_id: 'ui-preview-course',
    intent: { schema_version: 'course_change_intent_v1', intent_id: 'preview-intent', course_id: 'ui-preview-course', raw_request: instruction,
      interpreted_goal: instruction, scope_hint: {}, hard_constraints: [], soft_preferences: [], protected_requirements: ['保留原内容'],
      source_refs: [], signals: [], assumptions: [], blocking_questions: [], can_proceed_without_clarification: true, interpretation_revision: 'preview',
    },
    base_revision_vector: { teacher_outline: 'preview-outline' }, execution_strategies: ['structural_regeneration'],
    strategy_status: 'resolved', scenario_tags: [], structural_operations: [], unit_migrations: [],
    structure_review_status: 'pending', status: 'impact_ready', supersedes_plan_id: '', replan_reasons: [],
    created_at: '2026-10-20T08:00:00Z', updated_at: '2026-10-20T08:00:00Z',
  }
  return {
    change_set_id: 'preview-plan', hypothesis_id: '', evidence_ids: [], operations: [], allowed_scopes: [],
    request_text: instruction, expected_effect: instruction, status: 'pending', application_receipt: {}, undo_receipt: {}, effect_evaluation: {},
    teacher_change_planning: planning,
    impact_summary: {
      analysis_mode: 'deterministic_structure', current_outline: outline,
      proposed_outline: [0, 1, 3, 2, 4, 5].map(index => ({ provisional_id: `proposal-${index + 1}`, title: titles[index], parent_ref: 'root', source_node_ids: [`lesson-${index + 1}`], learning_focus: '' })),
      affected_units: [],
    },
  }
}

function makeSemanticPlan(instruction: string): CourseEvolutionPlan {
  const proposal = makePlan(instruction)
  proposal.teacher_change_planning!.execution_strategies = ['semantic_impact']
  proposal.teacher_change_planning!.structure_review_status = 'not_required'
  proposal.teacher_change_planning!.status = 'candidate_ready'
  proposal.operations = [{ operation_id: 'preview-replacement', operation_type: 'REPLACE_COURSE_BLOCK', target_block_id: 'preview-block', target_section_id: 'lesson-1', scope: 'current', reason: '示例术语修改', payload: {} }]
  proposal.impact_summary = {
    analysis_mode: 'deterministic_exact_replace', candidate_bundle: { operation_count: 1 },
    affected_units: [{ migration_id: 'preview-migration', unit_id: 'course_content:preview-block', asset_type: 'course_content', unit_type: 'course_block', title: '动能定理的表述',
      before_preview: '由动能定理可求得物体的末速度。', after_preview: '由动能定理（功—能定理）可求得物体的末速度。',
      section_ids: ['lesson-1'], source_state: 'current', disposition: 'rewrite_partial', reason: '示例：统一术语并保留原有内容。', confidence: 1,
      candidate_status: 'ready', operation_id: 'preview-replacement', change_count: 1,
    }],
  }
  return proposal
}

// This development entry renders the production component against in-memory fixtures.
// Every action is intercepted here; it never calls the course API or a model.
Object.assign(store, {
  refreshProgress: async () => ({}),
  loadCourseContext: async () => previewContext,
  createCoursePlan: async ({ instruction }: { instruction: string }) => {
    store.plans = [view.value === 'semantic' ? makeSemanticPlan(instruction) : makePlan(instruction)]
    return { course_evolution_plans: store.plans }
  },
  reviewCoursePlan: async (_id: string, _ids: string[], options: { proposedOutline?: unknown[]; confirmStructure?: boolean }) => {
    if (options.confirmStructure && store.plans[0]?.teacher_change_planning) {
      store.plans[0].teacher_change_planning.structure_review_status = 'confirmed'
      store.plans[0].impact_summary.proposed_outline = options.proposedOutline
    }
    return {}
  },
  generateSuggested: async () => {
    notice.value = activeLocale.value === 'zh' ? '预览已确认结构。正式页面将在此生成并展示联动修改建议。' : 'Preview: structure confirmed. The live page generates linked proposals at this step.'
    return {}
  },
  reject: async () => { show('request'); return {} },
  accept: async () => {
    notice.value = activeLocale.value === 'zh' ? '此处为交互预览，没有写入正式课程。正式页面将通过现有确认流程应用修改。' : 'Interactive preview only. No course data was changed. The live page uses the existing application flow.'
    return {}
  },
})

function show(next: PreviewView) {
  view.value = next
  notice.value = ''
  store.$patch({ courseId: 'ui-preview-course', courseContext: previewContext, plans: next === 'structure' ? [makePlan()] : [], generating: false, actingId: '', generationError: '' })
  version.value += 1
}
show(view.value)
</script>

<style scoped>
.change-preview { height: 100dvh; display: flex; flex-direction: column; overflow: hidden; background: #fff; }
.preview-toolbar { display: flex; align-items: center; flex-wrap: wrap; gap: 10px 20px; flex: none; min-height: 60px; padding: 10px 24px; border-bottom: 1px solid #dfe3ed; background: #fafaff; font-size: 14px; box-sizing: border-box; }
.preview-toolbar > span { flex: 1; color: #66728b; }
.preview-toolbar nav { display: flex; gap: 6px; }
.preview-toolbar button { padding: 7px 12px; border: 1px solid #dfe3ed; border-radius: 6px; color: #4b5671; background: #fff; cursor: pointer; }
.preview-toolbar button[aria-pressed=true] { color: #4f46e5; border-color: #c7c3fb; background: #efeeff; }
.change-preview > :deep(.course-change-layer) { min-height: 0; flex: 1; height: auto; }
.preview-notice { position: fixed; z-index: 100; left: 50%; bottom: 110px; max-width: 640px; transform: translateX(-50%); margin: 0; padding: 16px 24px; border: 1px solid #c7c3fb; border-radius: 8px; color: #302b91; background: #f5f4ff; font-size: 15px; box-shadow: 0 6px 24px #18213912; }
</style>
