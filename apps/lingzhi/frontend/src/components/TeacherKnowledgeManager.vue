<template>
  <section class="knowledge-workspace teacher-knowledge-manager" :class="{ 'tree-only': treeOnly }">
    <div v-if="!treeOnly" class="manager-tools"><span>{{ data?.title }}</span><button @click="refresh" :disabled="busy">{{ t('common.refresh') }}</button></div>
    <p v-if="error" class="notice error" role="alert">{{ error }}</p>
    <p v-if="!data && !error" role="status">{{ t('knowledgeFirst.loading') }}</p>
    <template v-if="data">
      <section v-if="!data.enabled" class="empty-card">
        <h2>{{ t('knowledgeFirst.startTitle') }}</h2><p>{{ data.provenance }}</p>
        <button v-if="data.can_initialize && data.can_edit" class="primary" :disabled="busy" @click="mutate('initialize')">{{ t('knowledgeFirst.initialize') }}</button>
        <p v-else>{{ t('knowledgeFirst.emptyRequired') }}</p>
      </section>
      <template v-else>
        <section v-if="derived && !treeOnly" class="handout-source-panel">
          <div class="source-panel-heading"><div><span class="source-eyebrow">{{ t('knowledgeFirst.afterHandouts') }}</span><h2>{{ t('knowledgeFirst.deriveTitle') }}</h2><p>{{ t('knowledgeFirst.deriveHint') }}</p></div><span class="source-count">{{ data.source_handouts?.length || 0 }} {{ t('knowledgeFirst.sourceLectures') }}</span></div>
          <ol class="source-steps"><li>{{ t('knowledgeFirst.prepareCourse') }}</li><li>{{ t('knowledgeFirst.prepareHandouts') }}</li><li class="current">{{ t('knowledgeFirst.extractKnowledge') }}</li></ol>
          <p v-if="!data.can_generate_tree" class="source-empty">{{ t('knowledgeFirst.handoutsRequired') }}</p>
          <details v-else class="source-list"><summary>{{ t('knowledgeFirst.sourceVersions') }}</summary><ul><li v-for="source in data.source_handouts" :key="source.lesson_id"><strong>{{ source.title }}</strong><span>{{ short(source.script_revision_id) }}</span></li></ul></details>
          <button v-if="data.can_edit" type="button" @click="data.can_generate_tree ? tab = 'handout' : emit('open-handouts')">{{ t(data.can_generate_tree ? 'knowledgeFirst.viewHandouts' : 'knowledgeFirst.prepareHandoutAction') }}</button>
        </section>
        <details v-if="!treeOnly && generic && !derived && data.can_edit" class="notice generic-inputs" :open="!data.tree">
          <summary>{{ t('knowledgeFirst.inputsTitle') }}</summary>
          <form @submit.prevent="saveInputs">
            <label>{{ t('knowledgeFirst.courseGoals') }}<textarea v-model="inputs.requirements" rows="3" maxlength="5000" required :disabled="busy || !!activeJob" @input="inputDirty = true" /></label>
            <div class="input-row"><label>{{ t('knowledgeFirst.audience') }}<input v-model="inputs.target_audience" maxlength="500" :disabled="busy || !!activeJob" @input="inputDirty = true" /></label>
              <label>{{ t('knowledgeFirst.lessonCount') }}<input v-model.number="inputs.lesson_count" type="number" min="1" max="12" :disabled="busy || !!activeJob" @input="inputDirty = true" /></label></div>
            <label class="upload-label">{{ t('knowledgeFirst.uploadMaterials') }}<input type="file" multiple accept=".pdf,.docx,.pptx,.md,.txt" :disabled="busy || !!activeJob" @change="uploadMaterials" /></label>
            <p v-if="!materials.length">{{ t('knowledgeFirst.materialRequired') }}</p>
            <label v-for="asset in materials" :key="asset.material_asset_id" class="material-choice"><input v-model="inputs.material_asset_ids" type="checkbox" :value="asset.material_asset_id" :disabled="busy || !!activeJob || asset.parse_status !== 'parsed'" @change="inputDirty = true" />{{ asset.filename }} · {{ t(asset.parse_status === 'parsed' ? 'knowledgeFirst.materialReady' : 'knowledgeFirst.materialFailed') }}</label>
            <button type="submit" class="primary" :disabled="busy || !!activeJob || !inputs.requirements.trim() || !inputs.material_asset_ids.length">{{ t('knowledgeFirst.saveInputs') }}</button>
            <span v-if="!inputDirty && data.inputs?.material_asset_ids?.length" class="saved-inputs" role="status">{{ t('knowledgeFirst.inputsSaved') }}</span>
          </form>
        </details>
        <div class="toolbar">
          <h2 v-if="treeOnly">{{ t('knowledgeFirst.tree') }}</h2>
          <label v-if="treeOnly && (historyOptions.length || selectedCandidate)" class="tree-version"><span>{{ t('knowledgeFirst.version') }}</span><select v-model="treeChoice">
            <option v-if="selectedCandidate && selectedCandidate.revision_id !== data.knowledge_revision" value="candidate">{{ t('knowledgeFirst.candidate') }} · {{ short(selectedCandidate.revision_id) }}</option>
            <option v-for="v in historyOptions" :key="v.revision_id" :value="v.revision_id">{{ v.revision_id === data.knowledge_revision ? t('knowledgeFirst.current') : t('knowledgeFirst.history') }} · {{ short(v.revision_id) }}</option>
          </select></label>
          <button v-if="treeOnly && treeChoice === 'candidate' && displayTree && data.can_edit && canAdoptSelection" class="primary" :disabled="busy || activeJobs.length > 0 || displayTree.revision_id === data.knowledge_revision || displayTree.teaching_assessment?.ready_for_adoption === false" @click="adopt">{{ t('knowledgeFirst.adoptTree') }}</button>
          <div v-if="!treeOnly && (!derived || data.handouts?.length)" class="tabs"><button :class="{ active: tab === 'tree' }" @click="tab = 'tree'">{{ t('knowledgeFirst.tree') }}</button>
            <button :class="{ active: tab === 'handout' }" @click="tab = 'handout'">{{ t('knowledgeFirst.handouts') }}</button></div>
          <button v-if="data.can_edit" class="primary" :disabled="busy || blockingJobs.length > 0 || (perLesson ? !selectedLesson?.can_generate : derived ? !data.can_generate_tree : generic && (inputDirty || !data.inputs?.material_asset_ids?.length))" @click="generate('tree')">{{ t(perLesson ? 'knowledgeFirst.generateLessonTree' : derived ? (data.tree ? 'knowledgeFirst.updateFromHandouts' : 'knowledgeFirst.generateFromHandouts') : data.tree ? 'knowledgeFirst.regenerateTree' : 'knowledgeFirst.generateTree') }}</button>
        </div>
        <div v-if="perLesson" class="knowledge-lesson-switch">
          <button type="button" :disabled="lessonOptions[0]?.lesson_id === knowledgeLessonId" @click="stepLesson(-1)">{{ t('knowledgeFirst.previousLesson') }}</button>
          <select v-model="knowledgeLessonId" :aria-label="t('knowledgeFirst.lessonPicker')"><option v-for="l in lessonOptions" :key="l.lesson_id" :value="l.lesson_id">{{ lessonLabels[l.lesson_id] }}</option></select>
          <button type="button" :disabled="lessonOptions.at(-1)?.lesson_id === knowledgeLessonId" @click="stepLesson(1)">{{ t('knowledgeFirst.nextLesson') }}</button>
        </div>
        <section v-for="job in sourceBlockingJobs" :key="job.id" class="notice job" role="status" data-testid="knowledge-source-blocker">
          <strong>{{ blockingJobLabel(job) }}</strong>
          <span>{{ job.progress || 0 }}% · {{ t('knowledgeFirst.waitForSourceTask') }}</span>
        </section>
        <section v-if="activeJob" class="notice job" role="status"><strong>{{ activeJob.knowledge_lesson_id ? `${lessonLabels[activeJob.knowledge_lesson_id] || ''} · ` : '' }}{{ activeJob.message }}</strong>
          <span>{{ activeJob.progress }}%<template v-if="!treeOnly"> · {{ activeJob.id }}</template></span>
          <button v-if="data.can_edit" :disabled="busy" @click="mutate(`cancel/${activeJob.id}`)">{{ t('knowledgeFirst.cancel') }}</button></section>
        <p v-if="treeOnly && !activeJob && latestJob?.status === 'failed'" class="notice error" role="alert"><strong>{{ t('knowledgeFirst.lastGenerationFailed') }}：</strong>{{ latestJob.error?.message }} <button v-if="data.can_edit && latestJob.recheck_available" :disabled="busy" @click="recheck(latestJob.id)">{{ t('knowledgeFirst.recheck') }}</button></p>
        <details v-if="!treeOnly && failedJobs.length" class="notice"><summary>{{ t('knowledgeFirst.jobHistory') }} · {{ failedJobs.length }}</summary>
          <details v-for="job in failedJobs" :key="job.id" class="notice error"><summary>{{ t('knowledgeFirst.interrupted') }} · {{ job.id }}</summary>
            <p>{{ job.error?.code === 'AIRequestBudgetExceeded' ? t('knowledgeFirst.inputBudgetExceeded') : job.error?.code === 'ModelConnectionUnavailable' ? t('knowledgeFirst.modelDisconnected') : job.error?.message }}</p><button v-if="data.can_edit && job.recheck_available" :disabled="busy || !!activeJob" @click="recheck(job.id)">{{ t('knowledgeFirst.recheck') }}</button><pre v-if="job.partial_text">{{ job.partial_text }}</pre><p v-if="job.error?.code !== 'AIRequestBudgetExceeded'">{{ t('knowledgeFirst.retryHint') }}</p></details>
        </details>
        <section v-if="tab === 'tree'" class="tree-section">
          <details v-if="!treeOnly && generic && displayTree" class="notice source-review"><summary>{{ t('knowledgeFirst.extractionNotes') }}</summary><p>{{ t(displayTree.source_mode === 'handouts' ? 'knowledgeFirst.derivedReview' : displayTree.revision_id === data.knowledge_revision ? 'knowledgeFirst.adoptedReview' : 'knowledgeFirst.genericReview') }}</p><ul><li v-for="gap in displayTree.gaps" :key="gap">{{ gap }}</li></ul><p v-if="displayTree.uncovered_evidence_ids?.length">{{ t('knowledgeFirst.uncoveredSources') }} {{ displayTree.uncovered_evidence_ids.length }}</p></details>
          <div v-if="!treeOnly && displayTree?.teaching_assessment" class="notice" :class="{ stale: !displayTree.teaching_assessment.ready_for_adoption }">
            <strong>{{ t('knowledgeFirst.teachingRound') }}</strong><p>{{ t('knowledgeFirst.candidateWarning') }}</p>
            <p>{{ t('knowledgeFirst.capabilities') }} {{ displayTree.teaching_assessment.capability_units }} · {{ t('knowledgeFirst.masteryCriteria') }} {{ displayTree.teaching_assessment.criteria }} · {{ t('knowledgeFirst.mistakesAndRepair') }} {{ displayTree.teaching_assessment.new_mistakes }}</p>
            <p>{{ t('knowledgeFirst.wholePackagePass') }} {{ displayTree.teaching_assessment.semantic_passed_units }}/{{ displayTree.teaching_assessment.capability_units }}</p>
          </div>
          <div v-if="!treeOnly" class="section-heading"><div><h2>{{ t('knowledgeFirst.tree') }}</h2><p>{{ displayTree?.teaching_assessment ? t('knowledgeFirst.teachingProvenance') : displayTree?.provenance || data.provenance }}</p></div>
            <label v-if="historyOptions.length || selectedCandidate">{{ t('knowledgeFirst.version') }}<select v-model="treeChoice">
              <option v-if="selectedCandidate && selectedCandidate.revision_id !== data.knowledge_revision" value="candidate">{{ t('knowledgeFirst.candidate') }} · {{ short(selectedCandidate.revision_id) }}</option>
              <option v-for="v in historyOptions" :key="v.revision_id" :value="v.revision_id">{{ v.revision_id === data.knowledge_revision ? t('knowledgeFirst.current') : t('knowledgeFirst.history') }} · {{ short(v.revision_id) }}</option>
            </select></label></div>
          <div v-if="displayTree?.knowledge_points.length" class="tree-layout">
            <nav class="tree-nav" :aria-label="t('knowledgeFirst.tree')">
              <div class="tree-root">{{ perLesson ? lessonLabels[knowledgeLessonId] : data.title }} <span>{{ displayTree.knowledge_points.length }} {{ t('knowledgeFirst.points') }}</span></div>
              <KnowledgeCategoryBranch v-for="root in roots" :key="root.id" :category="root" :categories="displayTree.categories" :points="displayTree.knowledge_points" :selected-id="selectedId" @select="selectedId = $event" />
            </nav>
            <aside ref="detailPane" class="knowledge-detail-pane" :aria-label="t('knowledgeFirst.pointDetails')">
            <article v-if="selectedPoint" :key="selectedId" class="point-card">
              <div class="point-topline"><span>{{ selectedPoint.key }}</span><span>{{ t('knowledgeFirst.atom') }}</span></div>
              <h2>{{ selectedPoint.name }}</h2><MarkdownRenderer class="claim" :content="selectedPoint.statement" />
              <template v-if="selectedPoint.conditions?.length"><h3>{{ t('knowledgeFirst.conditions') }}</h3><ul><li v-for="c in selectedPoint.conditions" :key="c">{{ c }}</li></ul></template>
              <template v-if="selectedPoint.meta_question || selectedPoint.meta_answer"><h3>{{ t('knowledgeFirst.question') }}</h3><MarkdownRenderer :content="selectedPoint.meta_question || ''" /><MarkdownRenderer :content="selectedPoint.meta_answer || ''" /></template>
              <h3>{{ t('knowledgeFirst.relations') }}</h3>
              <p v-if="!relations.length" class="muted">{{ t('knowledgeFirst.noRelation') }}</p>
              <div v-for="link in relatedLinks" :key="link.edge.id" class="relation">
                <span v-if="link.crossLesson" class="relation-scope">{{ t('knowledgeFirst.crossLessonLinks') }}</span>
                <button type="button" :disabled="!link.point" @click="navigateRelated({ lesson_id: link.lessonId, knowledge_id: link.id })">{{ link.crossLesson ? `${lessonLabels[link.lessonId] || link.lessonId} · ` : '' }}{{ link.point?.name || link.id }}</button>
                <p class="relation-direction">{{ t(link.edge.source_id === selectedId ? 'knowledgeFirst.outgoing' : 'knowledgeFirst.incoming') }} · {{ pointName(link.edge.source_id) }} → {{ pointName(link.edge.target_id) }} · {{ t(`knowledgeFirst.relationTypes.${link.edge.type}`, link.edge.type) }}</p>
                <p v-if="link.edge.reason">{{ link.edge.reason }}</p><ul v-if="link.edge.conditions?.length"><li v-for="condition in link.edge.conditions" :key="condition">{{ condition }}</li></ul>
                <MarkdownRenderer v-if="link.point?.statement" class="related-statement" :content="link.point.statement" />
              </div>
              <template v-if="!treeOnly || diagnoses.length"><h3>{{ t('knowledgeFirst.diagnosis') }}</h3><div v-for="d in diagnoses" :key="d.key"><p>A · {{ d.hypothesis_a }}</p><p>B · {{ d.hypothesis_b }}</p><p>{{ d.repair_a }}</p><p>{{ d.repair_b }}</p></div>
              <p v-if="!diagnoses.length" class="muted">{{ t(generic ? 'knowledgeFirst.genericNoDiagnosis' : 'knowledgeFirst.noDiagnosis') }}</p></template>
              <TeachingCapabilityPanel v-if="!treeOnly" :tree="displayTree" :point-id="selectedId" />
              <KnowledgeQuestionSupply v-if="!generic && data.can_edit && displayTree.revision_id === data.knowledge_revision" :course-id="courseId" :knowledge-id="selectedId" :baseline-revision="data.knowledge_revision" />
              <div v-for="source in selectedPoint.source_quotes" :key="source.evidence_id + source.quote" class="source-evidence">
                <template v-if="source.handout_ref"><div class="source-evidence-heading"><span>{{ t('knowledgeFirst.handoutSource') }} · {{ lessonLabels[source.handout_ref.lesson_id] || source.handout_ref.lesson_id }} · {{ short(source.handout_ref.script_revision_id) }}</span><button v-if="!treeOnly" type="button" @click="showHandoutSource(source.handout_ref)">{{ t('knowledgeFirst.locateHandout') }}</button></div><details><summary>{{ t('knowledgeFirst.readSourceText') }}</summary><blockquote><MarkdownRenderer :content="source.quote" /></blockquote></details></template>
                <blockquote v-else><MarkdownRenderer :content="source.quote" /></blockquote>
              </div>
              <h3>{{ t('knowledgeFirst.trace') }}</h3><dl><dt>ID</dt><dd>{{ selectedPoint.knowledge_id }}</dd><dt>{{ t('knowledgeFirst.version') }}</dt><dd>{{ selectedPoint.revision_id }}</dd><dt>{{ t('knowledgeFirst.source') }}</dt><dd>{{ selectedPoint.source_refs.join(', ') }}</dd></dl>
            </article>
            <div v-else class="point-card point-placeholder"><h2>{{ t('knowledgeFirst.pointDetails') }}</h2><p>{{ t('knowledgeFirst.selectPointHint') }}</p></div>
            </aside>
          </div>
          <p v-else class="empty-card">{{ t(activeJob ? 'knowledgeFirst.treeGenerationInProgress' : blockingJobs.length ? 'knowledgeFirst.waitForSourceTask' : perLesson ? (selectedLesson?.can_generate ? 'knowledgeFirst.lessonTreeEmpty' : 'knowledgeFirst.lessonHandoutRequired') : derived ? (!data.can_generate_tree ? 'knowledgeFirst.handoutsRequired' : 'knowledgeFirst.noDerivedTree') : 'knowledgeFirst.noTree') }}</p>
          <div v-if="!treeOnly && treeChoice === 'candidate' && displayTree && data.can_edit && canAdoptSelection" class="adopt-bar"><p>{{ t(derived ? 'knowledgeFirst.derivedAdoptHint' : generic ? 'knowledgeFirst.genericAdoptHint' : displayTree.teaching_assessment ? 'knowledgeFirst.candidateWarning' : 'knowledgeFirst.adoptHint') }}</p>
            <button class="primary" :disabled="busy || activeJobs.length > 0 || displayTree.revision_id === data.knowledge_revision || displayTree.teaching_assessment?.ready_for_adoption === false" @click="adopt">{{ t('knowledgeFirst.adoptTree') }}</button></div>
        </section>
        <section v-else class="handout-layout">
          <aside class="lecture-nav"><h2>{{ t('knowledgeFirst.handouts') }}</h2><button v-for="h in data.handouts" :key="h.topic" :class="{ active: lesson === h.topic }" @click="lesson = h.topic; handoutChoice = ''">{{ h.title }}<small>{{ h.revisions.length ? t('knowledgeFirst.generated') : t('knowledgeFirst.pending') }}</small></button></aside>
          <article ref="handoutRoot" class="handout-reader handout-document">
            <div class="section-heading"><h2>{{ currentLesson?.title }}</h2><button v-if="data.can_edit && !derived" class="primary" :disabled="busy || !!activeJob || !data.tree || !currentLesson" @click="generate(lesson)">{{ t('knowledgeFirst.generateHandout') }}</button></div>
            <p v-if="!derived && !data.tree" class="notice">{{ t('knowledgeFirst.treeRequired') }}</p>
            <template v-if="handout">
              <label v-if="currentLesson.revisions.length > 1">{{ t('knowledgeFirst.version') }}<select v-model="handoutChoice"><option v-for="r in currentLesson.revisions" :key="r.revision_id" :value="r.revision_id">{{ short(r.revision_id) }}</option></select></label>
              <p v-if="handout.source_knowledge_revision" class="notice" :class="{ stale: handout.stale }">{{ t(handout.stale ? 'knowledgeFirst.stale' : 'knowledgeFirst.bound') }}
                <button @click="showSource(handout.source_knowledge_revision)">{{ short(handout.source_knowledge_revision) }}</button><br>{{ t(generic ? 'knowledgeFirst.genericReviewHint' : 'knowledgeFirst.reviewHint') }}</p>
              <p v-if="handout.source_terminology_revision" class="muted">{{ t('knowledgeFirst.termVersion') }} · <code>{{ handout.source_terminology_revision }}</code></p>
              <HandoutReadingGuide :target="handoutRoot" :title="currentLesson?.title || data.title" />
              <HandoutReadingLayout :show-map="conceptSections.some(section => section.nodes.length || section.sourceStatus)">
              <template #aside><HandoutConceptMap :sections="conceptSections" :target="handoutRoot" /></template>
              <section v-for="block in handoutBlocks" :id="`knowledge-handout-${block.block_id}`" :key="block.block_id" class="reading-block">
                <HandoutContentBlock :content-type="block.content_type || block.role" :title="block.title" :answer-to="block.answer_to"><MarkdownRenderer :content="block.content" /></HandoutContentBlock>
                <div class="ref-chips"><button v-for="r in block.knowledge_refs" :key="r.knowledge_id" :title="r.revision_id" @click="showSource(handout.source_knowledge_revision, r.knowledge_id)">{{ refName(handout.source_knowledge_revision, r.knowledge_id) }} ↗</button></div>
              </section>
              </HandoutReadingLayout>
            </template>
            <p v-else class="empty-card">{{ t('knowledgeFirst.noHandout') }}</p>
          </article>
        </section>
      </template>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import http from '../utils/http'
import { createUuid } from '../utils/client-id'
import { t } from '../shared/i18n'
import MarkdownRenderer from './MarkdownRenderer.vue'
import KnowledgeCategoryBranch from './KnowledgeCategoryBranch.vue'
import TeachingCapabilityPanel from './TeachingCapabilityPanel.vue'
import KnowledgeQuestionSupply from './KnowledgeQuestionSupply.vue'
import HandoutContentBlock from './HandoutContentBlock.vue'
import HandoutReadingGuide from './HandoutReadingGuide.vue'
import HandoutReadingLayout from './HandoutReadingLayout.vue'
import HandoutConceptMap from './HandoutConceptMap.vue'
import { buildHandoutConceptSections } from '../utils/handout-concepts'

const props = withDefaults(defineProps<{ courseId: string; treeOnly?: boolean; initialLessonId?: string }>(), { treeOnly: false, initialLessonId: '' })
const emit = defineEmits<{ updated: []; 'open-handouts': [] }>()
const courseId = computed(() => props.courseId)
const knowledgeLessonId = ref(props.initialLessonId)
const data = ref<any>(null), error = ref(''), busy = ref(false)
const generic = computed(() => data.value?.workflow === 'knowledge_first_generic_v1')
const inputs = reactive({ requirements: '', target_audience: '', lesson_count: 3, material_asset_ids: [] as string[] })
const inputDirty = ref(false), materials = ref<any[]>([]), handoutRoot = ref<HTMLElement | null>(null)
const tab = ref('tree'), treeChoice = ref(''), selectedId = ref(''), lesson = ref('types'), handoutChoice = ref('')
const detailPane = ref<HTMLElement | null>(null)
let timer: ReturnType<typeof setTimeout> | undefined
let disposed = false, requestSequence = 0
const base = computed(() => `/api/courses/${courseId.value}/knowledge-first`)
const activeJobs = computed<any[]>(() => (data.value?.active_jobs || data.value?.jobs || []).filter((j: any) => ['pending', 'running'].includes(j.status)))
const blockingJobs = computed(() => {
  const ids = perLesson.value ? selectedLesson.value?.blocking_job_ids : data.value?.blocking_job_ids
  if (Array.isArray(ids)) return activeJobs.value.filter(j => ids.includes(j.id))
  return activeJobs.value.filter(j => !perLesson.value || !j.knowledge_lesson_id || j.knowledge_lesson_id === knowledgeLessonId.value)
})
const activeJob = computed(() => blockingJobs.value.find(j => (data.value?.jobs || []).some((known: any) => known.id === j.id)))
const sourceBlockingJobs = computed(() => blockingJobs.value.filter(j => !(data.value?.jobs || []).some((known: any) => known.id === j.id)))
const latestJob = computed(() => (data.value?.jobs || []).filter((j: any) => !perLesson.value || j.knowledge_lesson_id === knowledgeLessonId.value).at(-1))
const failedJobs = computed(() => (data.value?.jobs || []).filter((j: any) => j.status === 'failed').slice(-3))
const derived = computed(() => data.value?.source_mode === 'handouts')
const lessonOptions = computed<any[]>(() => data.value?.lesson_options || [])
const perLesson = computed(() => props.treeOnly && derived.value && lessonOptions.value.length > 0)
const selectedLesson = computed(() => lessonOptions.value.find(l => l.lesson_id === knowledgeLessonId.value))
const lessonLabels = computed(() => Object.fromEntries(lessonOptions.value.map((l, i) => [l.lesson_id, t('knowledgeFirst.numberedLesson').replace('{number}', String(i + 1)).replace('{title}', (l.title || '').replace(/^第\s*[\d一二三四五六七八九十百]+\s*讲\s*[·:：、.-]?\s*/u, '').replace(/^(?:lecture|lesson)\s+\d+\s*[·:.-]?\s*/i, ''))])))
function blockingJobLabel(job: any) {
  const label = lessonLabels.value[job.knowledge_lesson_id || job.lesson_unit_id] || data.value?.title || ''
  const kind = job.type === 'teacher_lesson_script_generation' ? 'handoutTask'
    : job.type === 'teacher_lesson_plan_generation' ? 'lessonPlanTask' : 'courseTask'
  return `${label} · ${t(`knowledgeFirst.${kind}`)}`
}
const selectedCandidateRecord = computed(() => {
  if (!perLesson.value) return data.value?.candidate ? { tree: data.value.candidate, job_id: data.value.candidate_job_id, lesson_id: '' } : null
  const pending = (tree: any) => tree && !(data.value?.history || []).some((h: any) => h.revision_id === tree.revision_id)
  const candidates = (data.value?.candidates || []).filter((c: any) => !c.adopted && pending(c.tree) && (c.lesson_id || c.source_knowledge_revision === undefined || c.source_knowledge_revision === data.value.knowledge_revision))
  return candidates.find((c: any) => c.lesson_id === knowledgeLessonId.value)
    || candidates.find((c: any) => !c.lesson_id)
    || (!Array.isArray(data.value?.candidates) && pending(data.value?.candidate) && !data.value.candidate.scope_lesson_id ? { tree: data.value.candidate, job_id: data.value.candidate_job_id, lesson_id: '' } : null)
})
const selectedCandidate = computed(() => selectedCandidateRecord.value?.tree)
const canAdoptSelection = computed(() => !perLesson.value || selectedCandidateRecord.value?.lesson_id === knowledgeLessonId.value)
const historyOptions = computed<any[]>(() => {
  const history = data.value?.history || []
  if (!perLesson.value) return history
  const seen = new Set<string>()
  return [...history].reverse().filter((tree: any) => {
    const points = (tree.knowledge_points || []).filter((p: any) => (p.section_refs || [p.topic]).includes(knowledgeLessonId.value))
    if (!points.length) return false
    const ids = new Set(points.map((p: any) => p.knowledge_id))
    const fingerprint = JSON.stringify([tree.lesson_revisions?.[knowledgeLessonId.value] || points.map((p: any) => [p.knowledge_id, p.revision_id]).sort(), (tree.relations || []).filter((r: any) => ids.has(r.source_id) || ids.has(r.target_id)).map((r: any) => r.id).sort()])
    if (seen.has(fingerprint)) return false
    seen.add(fingerprint); return true
  }).reverse()
})
const displayTree = computed(() => {
  const tree = treeChoice.value === 'candidate' ? (selectedCandidate.value?.revision_id !== data.value?.knowledge_revision ? selectedCandidate.value : null) : data.value?.history.find((v: any) => v.revision_id === treeChoice.value)
  if (!tree) return null
  const allPoints = (tree.knowledge_points || []).map((p: any) => ({ ...p, parent_id: p.parent_id || p.primary_concept_group_id, source_refs: p.source_refs || [] }))
  const points = perLesson.value ? allPoints.filter((p: any) => (p.section_refs || [p.topic]).includes(knowledgeLessonId.value)) : allPoints
  const categories = tree.categories || (tree.concept_groups || []).map((g: any) => ({ ...g, id: g.concept_group_id || g.id }))
  const byId = new Map<string, any>(categories.map((c: any) => [c.id, c])); const needed = new Set<string>()
  for (const point of points) { let id = point.parent_id; while (id && byId.has(id) && !needed.has(id)) { needed.add(id); id = byId.get(id).parent_id } }
  const ids = new Set(points.map((p: any) => p.knowledge_id))
  return { ...tree, allKnowledgePoints: allPoints, categories: perLesson.value ? categories.filter((c: any) => needed.has(c.id)) : categories,
    knowledge_points: points, relations: (tree.relations || []).filter((r: any) => !perLesson.value || ids.has(r.source_id) || ids.has(r.target_id)) }
})
const roots = computed(() => displayTree.value?.categories.filter((c: any) => !c.parent_id) || [])
const selectedPoint = computed(() => displayTree.value?.knowledge_points.find((p: any) => p.knowledge_id === selectedId.value))
const relations = computed(() => displayTree.value?.relations.filter((r: any) => [r.source_id, r.target_id].includes(selectedId.value)) || [])
const diagnoses = computed(() => displayTree.value?.misconceptions?.filter((d: any) => d.hypothesis_a && (d.knowledge_keys || []).includes(selectedPoint.value?.key)) || [])
const pointName = (id: string) => displayTree.value?.allKnowledgePoints.find((p: any) => p.knowledge_id === id)?.name || id
const relatedLinks = computed(() => relations.value.map((edge: any) => {
  const id = edge.source_id === selectedId.value ? edge.target_id : edge.source_id
  const point = displayTree.value?.allKnowledgePoints.find((p: any) => p.knowledge_id === id)
  const refs = point?.section_refs || [point?.topic || '']
  const foreignLesson = refs.find((ref: string) => ref !== knowledgeLessonId.value && lessonLabels.value[ref])
  const crossLesson = perLesson.value && !!foreignLesson && (edge.cross_lesson || !refs.includes(knowledgeLessonId.value))
  return { id, point, edge, crossLesson, lessonId: crossLesson ? foreignLesson : knowledgeLessonId.value }
}))
const refName = (revision: string, id: string) => data.value.history.find((v: any) => v.revision_id === revision)?.knowledge_points.find((p: any) => p.knowledge_id === id)?.name || id
const currentLesson = computed(() => data.value?.handouts.find((h: any) => h.topic === lesson.value))
const handout = computed(() => currentLesson.value?.revisions.find((r: any) => r.revision_id === (handoutChoice.value || currentLesson.value.current_revision_id)))
const handoutBlocks = computed(() => (handout.value?.sections || []).flatMap((section: any) => section.blocks || []))
const conceptSections = computed(() => buildHandoutConceptSections(handout.value?.knowledge_sections, (handout.value?.sections || []).map((section: any) => ({
  id: section.section_node_id, title: section.title, anchor: '', blocks: (section.blocks || []).map((b: any) => ({
    id: b.block_id, title: b.title, content: b.content, anchor: `knowledge-handout-${b.block_id}`, knowledge: (b.knowledge_refs || []).map((r: any) => r.knowledge_id), knowledgeRefs: b.knowledge_refs, sourceRevision: b.source_knowledge_revision,
  })),
}))))
const short = (value: string) => value?.slice(0, 15)
function message(e: any) { return typeof e?.response?.data?.detail === 'string' ? e.response.data.detail : t('knowledgeFirst.requestFailed') }
function chooseTreeVersion() {
  treeChoice.value = selectedCandidate.value && selectedCandidate.value.revision_id !== data.value?.knowledge_revision ? 'candidate' : data.value?.knowledge_revision || ''
}
function stepLesson(delta: number) {
  const index = lessonOptions.value.findIndex(l => l.lesson_id === knowledgeLessonId.value)
  knowledgeLessonId.value = lessonOptions.value[index + delta]?.lesson_id || knowledgeLessonId.value
}
async function navigateRelated(target: { lesson_id: string; knowledge_id: string }) {
  const version = treeChoice.value === 'candidate' ? displayTree.value?.base_knowledge_revision : treeChoice.value
  const changingLesson = target.lesson_id !== knowledgeLessonId.value
  knowledgeLessonId.value = target.lesson_id
  await nextTick()
  if (changingLesson && version && data.value?.history.some((v: any) => v.revision_id === version)) treeChoice.value = version
  selectedId.value = target.knowledge_id
  await nextTick()
  const node = Array.from(document.querySelectorAll<HTMLElement>('[data-knowledge-id]')).find(item => item.dataset.knowledgeId === target.knowledge_id)
  let ancestor = node?.parentElement
  while (ancestor) {
    if (ancestor.tagName === 'DETAILS') (ancestor as HTMLDetailsElement).open = true
    ancestor = ancestor.parentElement
  }
  node?.scrollIntoView?.({ block: 'nearest' })
}
watch(selectedId, async () => { await nextTick(); if (detailPane.value) detailPane.value.scrollTop = 0 })
watch(knowledgeLessonId, () => { selectedId.value = ''; chooseTreeVersion() })
async function refresh() {
  clearTimeout(timer)
  const seq = ++requestSequence
  try {
    const response = await http.get(base.value, { params: { source_mode: 'handouts' } })
    if (disposed || seq !== requestSequence) return
    const followLatest = !handoutChoice.value || handoutChoice.value === currentLesson.value?.current_revision_id
    data.value = response.data; error.value = ''
    if (perLesson.value && !selectedLesson.value) knowledgeLessonId.value = lessonOptions.value[0]?.lesson_id || ''
    if (generic.value && !inputDirty.value && data.value.inputs) Object.assign(inputs, data.value.inputs)
    if (generic.value && !data.value.handouts.some((h: any) => h.topic === lesson.value)) lesson.value = data.value.handouts[0]?.topic || ''
    if (!treeChoice.value || (treeChoice.value === 'candidate' && !selectedCandidate.value && latestJob.value?.status === 'failed')) chooseTreeVersion()
    if (!selectedId.value && !props.treeOnly) selectedId.value = displayTree.value?.knowledge_points[0]?.knowledge_id || ''
    if (followLatest) handoutChoice.value = currentLesson.value?.current_revision_id || ''
    if (activeJobs.value.length) timer = setTimeout(refresh, 2000)
  } catch (e) { if (!disposed && seq === requestSequence) error.value = message(e) }
}
async function mutate(path: string, extra = {}) {
  busy.value = true; error.value = ''
  try { await http.post(`${base.value}/${path}`, { document_revision: data.value.document_revision, knowledge_revision: data.value.knowledge_revision, ...extra }); await refresh(); if (path === 'initialize') emit('updated') }
  catch (e) {
    if ((e as any)?.response?.status === 409) {
      await refresh()
      if (blockingJobs.value.length) return
    }
    error.value = message(e)
  }
  finally { busy.value = false }
}
async function generate(topic: string) {
  if (topic === 'tree') { tab.value = 'tree'; treeChoice.value = 'candidate' }
  else { tab.value = 'handout'; handoutChoice.value = '' }
  await mutate(`generate/${topic}`, { request_id: createUuid(), ...(derived.value ? { source_mode: 'handouts' } : {}), ...(perLesson.value ? { lesson_id: knowledgeLessonId.value } : {}) })
}
async function adopt() { if (!canAdoptSelection.value) return; await mutate(`adopt/${selectedCandidateRecord.value.job_id}`); if (!error.value) treeChoice.value = data.value.knowledge_revision }
async function recheck(id: string) { treeChoice.value = 'candidate'; tab.value = 'tree'; await mutate(`recheck/${id}`, { request_id: createUuid() }) }
async function loadMaterials() {
  if (!generic.value || derived.value || !data.value?.can_edit) return
  try { materials.value = (await http.get('/api/materials', { params: { course_id: courseId.value } })).data.assets || [] }
  catch (e) { error.value = message(e) }
}
async function saveInputs() { await mutate('inputs', { ...inputs, input_revision: data.value?.input_revision || '' }); if (!error.value) inputDirty.value = false }
async function uploadMaterials(event: Event) {
  const files = Array.from((event.target as HTMLInputElement).files || [])
  busy.value = true; error.value = ''
  try {
    const batch = createUuid()
    for (const file of files) {
      const form = new FormData(); form.append('file', file); form.append('course_id', courseId.value); form.append('upload_batch_id', batch)
      const result = (await http.post('/api/materials', form)).data
      if (result.parse_status === 'parsed') inputs.material_asset_ids = [...new Set([...inputs.material_asset_ids, result.asset_id])]
    }
    inputDirty.value = true; await loadMaterials()
  } catch (e) { error.value = message(e) }
  finally { busy.value = false; (event.target as HTMLInputElement).value = '' }
}
async function showHandoutSource(ref: { lesson_id: string; script_revision_id: string; block_id: string }) {
  lesson.value = ref.lesson_id
  await nextTick()
  handoutChoice.value = ref.script_revision_id
  tab.value = 'handout'
  await nextTick()
  document.getElementById(`knowledge-handout-${ref.block_id}`)?.scrollIntoView({ block: 'center', behavior: 'auto' })
}
async function showSource(revision: string, id = '') { treeChoice.value = revision; selectedId.value = id; tab.value = 'tree'; await nextTick(); document.querySelector('.point-card')?.scrollIntoView({ block: 'start' }) }
watch(lesson, () => { handoutChoice.value = currentLesson.value?.current_revision_id || '' })
watch(displayTree, tree => { if (tree && !tree.knowledge_points.some((p: any) => p.knowledge_id === selectedId.value)) selectedId.value = props.treeOnly ? '' : tree.knowledge_points[0]?.knowledge_id || '' })
watch(courseId, () => { knowledgeLessonId.value = props.initialLessonId; data.value = null; inputDirty.value = false; materials.value = []; treeChoice.value = ''; selectedId.value = ''; handoutChoice.value = ''; void refresh() })
watch(() => [generic.value, data.value?.enabled], () => { void loadMaterials() })
onMounted(refresh)
onBeforeUnmount(() => { disposed = true; requestSequence++; clearTimeout(timer) })
</script>

<style scoped>
.knowledge-workspace{max-width:1480px;margin:auto;padding:30px 36px 70px;color:#243454;font-size:15px}.knowledge-header,.section-heading,.toolbar{display:flex;justify-content:space-between;align-items:center;gap:24px}.knowledge-header h1{font-size:30px;letter-spacing:-.7px;margin:8px 0}.knowledge-header a{color:#5364bd;text-decoration:none}.eyebrow{font-size:13px;letter-spacing:2px;color:#777bb4;margin-top:24px}.knowledge-workspace p{line-height:1.8}.knowledge-workspace button,.knowledge-workspace select{font:inherit;border:1px solid #dfe4f1;border-radius:9px;padding:9px 14px;background:#fff;color:#465478;cursor:pointer}.knowledge-workspace button:disabled{opacity:.45;cursor:not-allowed}.knowledge-workspace button:focus-visible,.knowledge-workspace summary:focus-visible{outline:3px solid #9dacec;outline-offset:2px}.knowledge-workspace .primary{background:var(--lz-action-bg);border-color:var(--lz-action-border);color:var(--lz-action-text);border:1px solid var(--lz-action-border);border-radius:var(--lz-action-radius);box-shadow:var(--lz-action-shadow)}.steps{display:flex;list-style:none;padding:0;gap:12px;margin:28px 0}.steps li{flex:1;padding:16px 20px;background:#f0f2f8;border-radius:12px;color:#7c8499}.steps .done{background:#e8edfc;color:#475db6}.toolbar{margin:24px 0}.tabs{display:flex;gap:8px}.tabs .active,.lecture-nav .active{background:#e9edff;border-color:#b6c1ef;color:#4554a2}.section-heading h2{font-size:20px;margin:0}.section-heading p{font-size:14px;max-width:780px;color:#748097}.section-heading label{min-width:180px;font-size:14px}.section-heading select{display:block;width:100%;margin-top:6px}.tree-layout{display:grid;grid-template-columns:390px minmax(0,1fr);gap:24px;margin-top:18px;align-items:start}.tree-nav,.point-card,.lecture-nav,.handout-reader,.empty-card{background:white;border:1px solid #e2e7f2;border-radius:16px;padding:24px;box-shadow:0 6px 26px #35406d06}.tree-nav{max-height:75vh;overflow:auto;padding:20px}.tree-root{padding:4px 10px 22px;font-weight:700}.tree-root span{float:right;font-weight:400;font-size:13px;color:#7a849d}.tree-nav summary{cursor:pointer;padding:12px 4px;line-height:1.5}.tree-group{border-left:1px solid #dfe4f1;margin-left:8px;padding-left:14px}.tree-group summary{font-size:14px;color:#697496}.tree-nav button{display:flex;align-items:center;gap:10px;text-align:left;width:100%;border:0;background:transparent;padding:9px 10px;line-height:1.5}.tree-nav button.selected{background:#edf0ff;color:#4c5baf}.leaf-dot{height:6px;width:6px;flex-shrink:0;border-radius:50%;background:#a0abdb}.point-card{padding:30px;min-height:500px}.point-topline{display:flex;justify-content:space-between;color:#8791ad;font-size:13px}.point-card h2{font-size:25px}.claim{background:#f4f6fc;border-left:3px solid #8d9cdc;padding:18px;border-radius:5px}.point-card h3{margin-top:28px;font-size:16px}.point-card li{margin:8px 0;line-height:1.7}.point-card dl{font-size:13px;display:grid;grid-template-columns:65px 1fr;gap:10px;overflow-wrap:anywhere}.point-card dd{margin:0}.muted{color:#818ba1;font-size:14px}.relation{padding:14px;background:#f7f8fd;border-radius:10px}.adopt-bar{display:flex;align-items:center;justify-content:space-between;padding:20px;margin-top:20px;background:#ebeffe;border-radius:14px}.notice{padding:16px 20px;background:#edf2fe;border-radius:12px;margin:18px 0;line-height:1.8}.error{background:#fff0ee;color:#a94334}.stale{background:#fff4da}.job{display:flex;gap:20px;align-items:center}.job span{flex:1;font-size:13px}.notice pre{white-space:pre-wrap;max-height:240px;overflow:auto}.handout-layout{display:grid;grid-template-columns:255px minmax(0,1fr);gap:24px;align-items:start}.lecture-nav button{display:block;text-align:left;width:100%;margin:12px 0;line-height:1.7}.lecture-nav small{display:block;color:#929bb1}.handout-reader{padding:30px 38px;min-height:400px}.reading-block{border-bottom:1px solid #edf0f6;padding:18px 0 26px;line-height:1.9}.reading-block h3{font-size:19px}.ref-chips{display:flex;flex-wrap:wrap;gap:7px;margin-top:14px}.ref-chips button{font-size:12px;padding:4px 9px;color:#6474b5;background:#f4f6fd;border:0}code{overflow-wrap:anywhere}@media(max-width:1050px){.knowledge-workspace{padding:22px}.tree-layout{grid-template-columns:310px minmax(0,1fr)}.section-heading{align-items:flex-start}.handout-layout{grid-template-columns:210px minmax(0,1fr)}}
@media(max-width:900px){.knowledge-workspace{padding:20px 14px;min-width:0;width:100%;box-sizing:border-box}.knowledge-header,.section-heading,.toolbar,.adopt-bar,.job{flex-wrap:wrap;gap:12px}.knowledge-header h1{font-size:24px}.steps{flex-direction:column}.steps li{padding:12px 16px}.tree-layout,.handout-layout{grid-template-columns:minmax(0,1fr)}.tree-nav{max-height:330px}.point-card,.handout-reader{padding:20px;min-width:0}.point-card h2{font-size:22px;overflow-wrap:anywhere}.handout-reader pre{max-width:100%;overflow:auto}.lecture-nav{padding:16px}.section-heading label{min-width:0;width:100%}.tabs{flex-wrap:wrap}.knowledge-workspace button{overflow-wrap:anywhere}.job span{overflow-wrap:anywhere}.point-card dl{grid-template-columns:50px minmax(0,1fr)}}
</style>

<style scoped>
.teacher-knowledge-manager { width:100%; max-width:none; margin:0; padding:4px 8px 32px; box-sizing:border-box; }
.manager-tools { display:flex; align-items:center; justify-content:space-between; gap:16px; color:#8a789a; font-size:14px; }.teacher-knowledge-manager .toolbar { margin:18px 0; }.teacher-knowledge-manager .tree-layout { grid-template-columns:280px minmax(0,1fr); gap:18px; }.teacher-knowledge-manager .point-card { padding:24px; }
@media(max-width:900px) { .teacher-knowledge-manager .tree-layout { grid-template-columns:minmax(0,1fr); } }
</style>

<style scoped>
.generic-inputs form{display:grid;gap:16px;margin-top:16px}.generic-inputs label{display:grid;gap:6px;font-size:15px}.generic-inputs textarea,.generic-inputs input:not([type=checkbox]):not([type=file]){width:100%;box-sizing:border-box;padding:10px;border:1px solid #cbd2e5;border-radius:8px;background:white;font:inherit;color:inherit}.input-row{display:grid;grid-template-columns:1fr 140px;gap:18px}.generic-inputs .material-choice{display:flex;align-items:center;gap:8px}.saved-inputs{color:#39634a}.point-card blockquote{margin:12px 0;padding:12px 16px;border-left:3px solid #a69aca;background:#f5f2fa;font-size:15px;line-height:1.7}
</style>

<style scoped>
.handout-source-panel{margin:18px 0 24px;padding:24px;border:1px solid #e2e5f1;border-radius:14px;background:linear-gradient(120deg,#fafaff,#fff)}.source-panel-heading{display:flex;justify-content:space-between;align-items:flex-start;gap:24px}.source-eyebrow{color:#6965ae;font-size:15px}.source-panel-heading h2{margin:8px 0;font-size:22px}.source-panel-heading p{margin:0;max-width:680px;color:#718099;font-size:15px}.source-count{white-space:nowrap;border:1px solid #e2def4;padding:6px 12px;border-radius:20px;color:#645a9b;font-size:15px}.source-steps{display:flex;list-style:none;gap:12px;padding:0;margin:22px 0;color:#8791a6;font-size:15px}.source-steps li+li:before{content:'›';padding-right:12px;color:#b5bccd}.source-steps .current{color:#5b58a6;font-weight:600}.source-empty{padding:14px 18px;background:#f3f4fa;border-radius:8px;color:#67738b}.source-list{margin:16px 0;font-size:15px}.source-list summary{cursor:pointer;color:#667290}.source-list ul{padding:0;list-style:none}.source-list li{display:flex;justify-content:space-between;gap:16px;padding:10px 0;border-bottom:1px solid #edf0f6}.source-list span{font-size:13px;color:#8991a5}.toolbar:has(>.primary:only-child){justify-content:flex-end}.point-card blockquote footer{margin-top:10px;font-size:13px;color:#8892a7;overflow-wrap:anywhere}
</style>

<style scoped>
.source-evidence{margin-top:20px}.source-evidence-heading{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px;font-size:14px;color:#7c849b}.source-evidence summary{font-size:15px;cursor:pointer;color:#697496;margin-top:10px}.source-evidence blockquote{overflow-wrap:anywhere}.handout-reader{container-type:inline-size;min-width:0}.handout-reader :deep(.handout-reading-body),.handout-reader :deep(.handout-concept-map){width:100%;box-sizing:border-box}.source-steps{flex-wrap:wrap}
</style>

<style scoped>
.tree-only{padding:0;max-width:none}.tree-only .toolbar{margin:0 0 20px;gap:12px;flex-wrap:wrap}.tree-only .toolbar h2{flex:1;margin:0;font-size:24px;color:#343b70}.tree-version{display:flex;align-items:center;gap:8px;color:#7c849b;font-size:14px}.tree-version select{max-width:260px}.tree-only .tree-layout{display:grid;grid-template-columns:minmax(320px,1fr) minmax(340px,420px);gap:20px;margin:0;align-items:start}.tree-only .tree-nav{max-height:none;overflow:visible;padding:22px 28px;box-shadow:none;border-radius:12px}.tree-only .tree-root{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:0 0 18px;border-bottom:1px solid #eef0f7;margin-bottom:10px}.tree-only .tree-root span{float:none}.tree-only .notice{margin:0 0 18px}
</style>

<style scoped>
.knowledge-lesson-switch{display:flex;align-items:center;justify-content:center;gap:12px;margin:0 0 20px}.knowledge-lesson-switch select{min-width:0;max-width:560px;flex:1}.knowledge-lesson-switch button{white-space:nowrap}
</style>

<style scoped>
.knowledge-detail-pane{min-width:0}.tree-only .knowledge-detail-pane{position:sticky;top:0;max-height:calc(100dvh - 230px);overflow:auto;scrollbar-gutter:stable;border:1px solid #e2e7f2;border-radius:12px;background:#fff}.tree-only .point-card{min-height:0;border:0;box-shadow:none;border-radius:0;padding:24px}.tree-only .point-card h2{font-size:22px;line-height:1.5;margin:14px 0}.tree-only .point-placeholder{min-height:300px;color:#8590a4}.point-placeholder p{font-size:15px}.relation+.relation{margin-top:12px}.relation button{font-weight:600;text-align:left;line-height:1.6}.relation-scope{display:block;color:#7866a9;font-size:13px;margin-bottom:8px}.relation-direction{color:#697496;font-size:14px;line-height:1.6}.related-statement{border-top:1px solid #e3e7f2;padding-top:10px;margin-top:10px;font-size:15px}.tree-only .point-card :deep(.markdown-body){overflow-wrap:anywhere}.tree-only .point-card dl{font-size:13px}.tree-only .source-evidence-heading{line-height:1.7}
@media(max-width:1050px){.tree-only .tree-layout{grid-template-columns:minmax(270px,1fr) minmax(300px,380px);gap:14px}.tree-only .tree-nav{padding:20px}.tree-only .point-card{padding:20px}}
@media(max-width:760px){.tree-only .tree-layout{grid-template-columns:minmax(0,1fr)}.tree-only .knowledge-detail-pane{position:static;max-height:none}.tree-only .tree-nav{max-height:50vh;overflow:auto}}
</style>
